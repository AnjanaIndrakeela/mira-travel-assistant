"""POST /chat and GET /conversations/{id} (step 9.2).

One request = one traveller turn = one graph run = one trace. The LangGraph thread is the
conversation ID, so two calls with the same ID share the context. Unknown or missing IDs
start a new conversation (the client never chooses database IDs).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from app.api.deps import get_chat_graph, get_db
from app.api.schemas import ChatMessage, ChatRequest, ChatResponse, ConversationOut, Source
from app.db.models import Conversation, Visitor
from app.db.repo import create_enquiry
from app.graph import replies
from app.graph.tracing import run_turn
from app.guards.input_guard import mask_personal_data
from app.llm.client import text_of

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
    return conv


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db), graph=Depends(get_chat_graph)) -> ChatResponse:
    conv = _conversation(db, req)
    try:
        result = run_turn(graph, conv.thread_id, req.message, visitor_id=str(conv.visitor_id),
                          conversation_id=str(conv.id))
    except Exception as exc:  # noqa: BLE001  (9.9: an LLM or graph failure is a polite handoff)
        logger.error("chat turn failed: %s", exc.__class__.__name__)
        enquiry = create_enquiry(db, "custom", conversation_id=conv.id, flags=["chat_error"],
                                 notes=mask_personal_data(req.message)[:500])
        db.commit()
        return ChatResponse(conversation_id=conv.id, visitor_id=conv.visitor_id, message=replies.HANDOFF,
                            ui=[{"type": "handoff_card", "reason": "handoff"}], enquiry_id=enquiry.id)
    sources = next((c["items"] for c in result.get("ui") or [] if c["type"] == "sources"), [])
    return ChatResponse(conversation_id=conv.id, visitor_id=conv.visitor_id, message=result["response"],
                        ui=result.get("ui") or [], sources=[Source(**s) for s in sources],
                        quote_id=_uuid(result.get("quote_id")), enquiry_id=_uuid(result.get("enquiry_id")))


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db),
                 graph=Depends(get_chat_graph)) -> ConversationOut:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(404, "We couldn't find that conversation.")
    state = graph.get_state({"configurable": {"thread_id": conv.thread_id}}).values or {}
    messages = [ChatMessage(role="traveller" if isinstance(m, HumanMessage) else "mira", text=text_of(m))
                for m in state.get("messages", [])]
    return ConversationOut(conversation_id=conv.id, visitor_id=conv.visitor_id, messages=messages)
