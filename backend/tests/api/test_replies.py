"""A specialist replies to a traveller (R6 "a specialist will confirm", R7 follow-up status).

The reply goes into the traveller's chat exactly as written (never through the LLM), a mock
email with a link to that chat is recorded (never delivered), and the enquiry moves to
contacted. Mira never sees the reply, so she can't repeat a specialist's price as her own.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db.models import Enquiry, EnquiryNote, SpecialistReply
from tests.api.test_api import S02, api, base, db, engine  # noqa: F401
from tests.api.test_staff import fresh_limiter, login, users  # noqa: F401
from tests.unit.test_graph import FakeModel, R, T

REPLY = "Good news: we can do the safari on 10 January. The jeep is USD 999 extra. Shall I hold it?"
TOUR = "Sigiriya and Minneriya day tour from Kandy"


def two_turns():
    from datetime import date
    t = T(tour_mention=TOUR, start_date=date(2027, 1, 10), adults=2)
    return FakeModel(RouterDecision=[R("quote", TOUR), R("quote", TOUR)], TripDetails=[t, t])


def priced_enquiry(api, db, email: str | None = "traveller@example.test") -> tuple[Enquiry, dict]:
    body = api.use(two_turns()).chat(S02).json()
    e = db.scalars(select(Enquiry).where(Enquiry.quote_id == uuid.UUID(body["quote_id"]))).one()
    if email:
        e.contact = {"name": "Asha", "email": email}
        db.flush()
    return e, body


def send(api, e, body=REPLY):
    return api.client.post(f"/api/v1/staff/enquiries/{e.id}/replies", json={"body": body})


def test_reply_reaches_the_chat_as_written_with_a_mock_email(api, db, users):
    e, first = priced_enquiry(api, db)
    login(api, users)
    r = send(api, e)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["body"] == REPLY and out["in_chat"] and out["status"] == "contacted"
    assert out["emailed_to"] == "traveller@example.test" and out["emailed_at"]
    link = f"/?chat={first['conversation_id']}"
    assert "Hello Asha" in out["email_text"] and link in out["email_text"]
    assert REPLY not in out["email_text"]                  # the email only says there is a reply

    history = api.client.get(f"/api/v1/conversations/{first['conversation_id']}").json()["messages"]
    assert [m["role"] for m in history] == ["traveller", "mira", "specialist"]
    assert history[-1]["text"] == REPLY                    # exactly as written
    assert users["staff"][0] not in str(history)           # the traveller never sees staff emails

    db.refresh(e)
    notes = db.scalars(select(EnquiryNote.body).where(EnquiryNote.enquiry_id == e.id)).all()
    assert e.status == "contacted"
    assert any("mock email" in n for n in notes) and any("to contacted" in n for n in notes)


def test_reply_keeps_its_place_and_mira_never_sees_it(api, db, users):
    e, first = priced_enquiry(api, db)
    login(api, users)
    assert send(api, e).status_code == 201
    second = api.chat(S02, conversation_id=first["conversation_id"]).json()    # the chat goes on
    assert "999" not in second["message"]                  # never repeated as Mira's price
    state = api.graph.get_state({"configurable": {"thread_id": _thread(db, first)}}).values
    assert REPLY not in str(state["messages"])             # not in what the LLM is given

    history = api.client.get(f"/api/v1/conversations/{first['conversation_id']}").json()["messages"]
    assert [m["role"] for m in history] == ["traveller", "mira", "specialist", "traveller", "mira"]
    staff_view = api.client.get(f"/api/v1/staff/enquiries/{e.id}").json()
    assert [m["role"] for m in staff_view["conversation"]][:3] == ["traveller", "mira", "specialist"]
    assert staff_view["replies"][0]["body"] == REPLY


def _thread(db, body) -> str:
    from app.db.models import Conversation
    return db.get(Conversation, uuid.UUID(body["conversation_id"])).thread_id


def test_confirmed_or_closed_enquiries_keep_their_status(api, db, users):
    e, _ = priced_enquiry(api, db)
    e.status = "confirmed"
    db.flush()
    login(api, users)
    assert send(api, e).json()["status"] == "confirmed"


def test_email_only_and_unreachable_enquiries(api, db, users):
    login(api, users)
    only_email = Enquiry(kind="custom", contact={"name": "Ravi", "email": "ravi@example.test"})
    nobody = Enquiry(kind="custom")
    db.add_all([only_email, nobody])
    db.flush()
    out = send(api, only_email).json()
    assert not out["in_chat"] and out["emailed_to"] == "ravi@example.test"
    assert "?chat=" not in out["email_text"]
    r = send(api, nobody)
    assert r.status_code == 409 and "no way to reach" in r.json()["message"]


def test_chat_only_enquiry_gets_no_email(api, db, users):
    e, _ = priced_enquiry(api, db, email=None)
    login(api, users)
    out = send(api, e).json()
    assert out["in_chat"] and out["emailed_to"] is None and out["email_text"] is None


def test_only_signed_in_staff_can_reply(api, db, users):
    e, _ = priced_enquiry(api, db)
    assert send(api, e).status_code == 401
    login(api, users)
    assert send(api, e, body="   ").status_code == 422
    assert send(api, e, body="x" * 4001).status_code == 422


def test_replies_cannot_be_edited_or_deleted(api, db, users):
    e, _ = priced_enquiry(api, db)
    login(api, users)
    reply_id = send(api, e).json()["id"]
    for sql in ("UPDATE specialist_replies SET body = 'changed'", "DELETE FROM specialist_replies"):
        with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
            db.execute(text(f"{sql} WHERE id = :id"), {"id": reply_id})
    assert db.get(SpecialistReply, uuid.UUID(reply_id)).body == REPLY
