"""POST /chat, POST /chat/stream and GET /conversations/{id} (steps 9.2, 11.1).

One request = one traveller turn = one graph run = one trace. The LangGraph thread is the
conversation ID, so two calls with the same ID share the context. Unknown or missing IDs
start a new conversation (the client never chooses database IDs).

/chat/stream sends the same turn as an AG-UI-style event stream (Server-Sent Events):
RUN_STARTED -> STEP_FINISHED per graph node -> TEXT_MESSAGE_START/CONTENT/END ->
CUSTOM "ui_component" per validated catalog component -> RUN_FINISHED (with the full
ChatResponse), or RUN_ERROR. /chat returns the ChatResponse as plain JSON (tests, evals).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_chat_graph, get_db
from app.api.schemas import ChatMessage, ChatRequest, ChatResponse, ConversationOut, Source
from app.db.models import Conversation, Visitor
from app.db.repo import create_enquiry
from app.graph import replies
from app.graph.tracing import run_turn
from app.guards.input_guard import mask_personal_data
from app.guards.ui_validator import validate_ui
from app.llm.client import text_of
from app.ui.build import NOTICE

router = APIRouter(tags=["chat"])
logger = logging.getLogger("mira.api.chat")


def _conversation(db: Session, req: ChatRequest) -> Conversation:
    if req.conversation_id and (conv := db.get(Conversation, req.conversation_id)):
        return conv
    visitor = db.get(Visitor, req.visitor_id) if req.visitor_id else None
    if visitor is None:
        visitor = Visitor(id=req.visitor_id or uuid.uuid4())
        db.add(visitor)
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, visitor=visitor, thread_id=str(conv_id))
    db.add(conv)
    db.commit()            # the graph's persist node writes in its own transaction
    db.refresh(conv)       # load the IDs now, not lazily from another thread
    return conv


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _turn(db: Session, graph, conv: Conversation, message: str, on_step=None) -> ChatResponse:
    """Run the turn; any LLM or graph failure becomes a polite handoff (9.9), never an error."""
    try:
        result = run_turn(graph, conv.thread_id, message, visitor_id=str(conv.visitor_id),
                          conversation_id=str(conv.id), on_step=on_step)
    except Exception as exc:  # noqa: BLE001
        logger.error("chat turn failed: %s", exc.__class__.__name__)
        enquiry = create_enquiry(db, "custom", conversation_id=conv.id, flags=["chat_error"],
                                 notes=mask_personal_data(message)[:500])
        db.commit()
        ui, _ = validate_ui([{"type": "specialist_notice", "reason": "handoff", "message": NOTICE["handoff"],
                              "enquiry_id": str(enquiry.id)}], quote_id=None)
        return ChatResponse(conversation_id=conv.id, visitor_id=conv.visitor_id, message=replies.HANDOFF,
                            ui=ui, enquiry_id=enquiry.id)
    ui = result.get("ui") or []
    sources = next((c["items"] for c in ui if c["type"] == "source_list"), [])
    return ChatResponse(conversation_id=conv.id, visitor_id=conv.visitor_id, message=result["response"],
                        ui=ui, sources=[Source(**s) for s in sources],
                        quote_id=_uuid(result.get("quote_id")), enquiry_id=_uuid(result.get("enquiry_id")))


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db), graph=Depends(get_chat_graph)) -> ChatResponse:
    return _turn(db, graph, _conversation(db, req), req.message)


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@router.post("/chat/stream", response_class=StreamingResponse,
             responses={200: {"content": {"text/event-stream": {}},
                              "description": "AG-UI-style events, one JSON object per `data:` line"}})
async def chat_stream(req: ChatRequest, db: Session = Depends(get_db),
                      graph=Depends(get_chat_graph)) -> StreamingResponse:
    conv = await run_in_threadpool(_conversation, db, req)
    thread_id, run_id = str(conv.id), str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | ChatResponse | None] = asyncio.Queue()

    def step(node: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"type": "STEP_FINISHED", "stepName": node})

    def work() -> None:
        try:
            out: ChatResponse | None = _turn(db, graph, conv, req.message, on_step=step)
        except Exception as exc:  # noqa: BLE001  (e.g. the database is down)
            logger.error("chat stream failed: %s", exc.__class__.__name__)
            out = None
        loop.call_soon_threadsafe(queue.put_nowait, out)

    async def events() -> AsyncIterator[str]:
        yield _sse({"type": "RUN_STARTED", "threadId": thread_id, "runId": run_id})
        worker = loop.run_in_executor(None, work)
        while True:
            item = await queue.get()
            if isinstance(item, dict):
                yield _sse(item)
                continue
            break
        await worker
        if item is None:
            yield _sse({"type": "RUN_ERROR", "message": "Something went wrong on our side. Please try again."})
            return
        res = item.model_dump(mode="json")
        msg_id = str(uuid.uuid4())
        yield _sse({"type": "TEXT_MESSAGE_START", "messageId": msg_id, "role": "assistant"})
        yield _sse({"type": "TEXT_MESSAGE_CONTENT", "messageId": msg_id, "delta": res["message"]})
        yield _sse({"type": "TEXT_MESSAGE_END", "messageId": msg_id})
        for component in res["ui"]:
            yield _sse({"type": "CUSTOM", "name": "ui_component", "value": component})
        yield _sse({"type": "RUN_FINISHED", "threadId": thread_id, "runId": run_id, "result": res})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: uuid.UUID, visitor_id: uuid.UUID, db: Session = Depends(get_db),
                        graph=Depends(get_chat_graph)) -> None:
    """"New chat": the traveller's old chat is deleted (its messages and cards). Only the visitor
    who owns it can delete it. Staff records stay: quotes, enquiries and specialist replies keep
    their own copies and just lose the link to the chat (ON DELETE SET NULL). What R2 remembers
    about the visitor (party, interests, last quote) is kept on the visitor, not the chat."""
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.visitor_id != visitor_id:
        raise HTTPException(404, "We couldn't find that conversation.")
    try:
        graph.checkpointer.delete_thread(conv.thread_id)
    except Exception as exc:  # noqa: BLE001  (the thread may already be gone after a restart)
        logger.warning("delete_thread failed: %s", exc.__class__.__name__)
    db.delete(conv)
    db.commit()


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db),
                 graph=Depends(get_chat_graph)) -> ConversationOut:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(404, "We couldn't find that conversation.")
    state = graph.get_state({"configurable": {"thread_id": conv.thread_id}}).values or {}
    msgs = state.get("messages", [])
    # one ui_log entry per reply, newest last (a chat older than ui_log has fewer: align the ends)
    replies = [i for i, m in enumerate(msgs) if not isinstance(m, HumanMessage)]
    log = list(state.get("ui_log") or [])[-len(replies):] if replies else []
    ui_at = dict(zip(replies[len(replies) - len(log):], log))
    messages = [ChatMessage(role="traveller" if isinstance(m, HumanMessage) else "mira", text=text_of(m),
                            ui=ui_at.get(i, []))
                for i, m in enumerate(msgs)]
    # a specialist's replies, exactly as written, where they were sent (never in the graph state)
    from app import specialist
    from app.db.models import SpecialistReply
    replies = db.scalars(select(SpecialistReply).where(SpecialistReply.conversation_id == conv.id)).all()
    messages = specialist.merge(messages, replies, lambda r: ChatMessage(role="specialist", text=r.body))
    return ConversationOut(conversation_id=conv.id, visitor_id=conv.visitor_id, messages=messages)
