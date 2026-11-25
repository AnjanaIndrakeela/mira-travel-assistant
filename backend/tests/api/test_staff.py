"""Phase 13: staff sign-in, the enquiry console, and what travellers can never read (R7).

Users are created inside the rolled-back test transaction with throwaway passwords, so the
tests don't depend on the passwords in .env.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core import security
from app.core.security import COOKIE, LoginLimiter, hash_password, token_hash, verify_password
from app.db.models import Enquiry, EnquiryNote, StaffSession, User
from app.main import app
from tests.api.test_api import (COST_WORDS, S02, api, base, db, engine, quote_s02,  # noqa: F401
                                s02_model)

STAFF_ROUTES = [("get", "/api/v1/staff/enquiries"),
                ("get", f"/api/v1/staff/enquiries/{uuid.uuid4()}"),
                ("post", f"/api/v1/staff/enquiries/{uuid.uuid4()}/notes"),
                ("patch", f"/api/v1/staff/enquiries/{uuid.uuid4()}/status"),
                ("get", "/api/v1/auth/me")]


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    monkeypatch.setattr("app.api.staff.login_limiter", LoginLimiter())
    monkeypatch.setattr("app.api.staff.trace_url", lambda tid: f"https://langfuse.test/traces/{tid}" if tid else None)


@pytest.fixture
def users(db):
    """{role: (email, password)} for one staff and one approver account."""
    made = {}
    for role in ("staff", "approver"):
        email, password = f"{role}-{uuid.uuid4().hex[:8]}@test.example", secrets.token_urlsafe(12)
        db.add(User(email=email, role=role, password_hash=hash_password(password)))
        made[role] = (email, password)
    db.flush()
    return made


def login(api, users, role="staff"):
    email, password = users[role]
    r = api.client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r


# ---- 13.1 security helpers -------------------------------------------------------------------

def test_password_hash_round_trip():
    h = hash_password("correct horse")
    assert h.startswith("scrypt$") and "correct horse" not in h
    assert verify_password("correct horse", h) and not verify_password("wrong", h)
    assert not verify_password("x", "not-a-hash")


def test_limiter_blocks_after_five_failures():
    lim = LoginLimiter(limit=5)
    for _ in range(5):
        assert not lim.blocked("k")
        lim.failed("k")
    assert lim.blocked("k")
    lim.clear("k")
    assert not lim.blocked("k")


# ---- 13.2 login / logout / me ----------------------------------------------------------------

def test_login_sets_an_httponly_cookie_and_stores_only_a_hash(api, db, users):
    r = login(api, users)
    assert r.json() == {"email": users["staff"][0], "role": "staff"}
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    token = api.client.cookies[COOKIE]
    assert db.get(StaffSession, token) is None                    # the raw token is never stored
    assert db.get(StaffSession, token_hash(token)) is not None
    assert api.client.get("/api/v1/auth/me").json()["role"] == "staff"


def test_wrong_password_and_unknown_email_get_the_same_answer(api, users):
    a = api.client.post("/api/v1/auth/login", json={"email": users["staff"][0], "password": "nope"})
    b = api.client.post("/api/v1/auth/login", json={"email": "nobody@test.example", "password": "nope"})
    assert a.status_code == b.status_code == 401
    assert a.json()["message"] == b.json()["message"]
    assert COOKIE not in api.client.cookies


def test_email_is_case_insensitive(api, users):
    email, password = users["staff"]
    r = api.client.post("/api/v1/auth/login", json={"email": email.upper(), "password": password})
    assert r.status_code == 200


def test_too_many_failures_are_refused(api, users):
    email, password = users["staff"]
    for _ in range(5):
        api.client.post("/api/v1/auth/login", json={"email": email, "password": "nope"})
    r = api.client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 429                              # even the right password, for a while


def test_logout_ends_the_session_on_the_server(api, db, users):
    login(api, users)
    token = api.client.cookies[COOKIE]
    assert api.client.post("/api/v1/auth/logout").status_code == 204
    assert db.get(StaffSession, token_hash(token)) is None
    api.client.cookies.set(COOKIE, token)                     # replaying the old cookie
    assert api.client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_signed_out(api, db, users):
    login(api, users)
    row = db.get(StaffSession, token_hash(api.client.cookies[COOKIE]))
    row.expires_at = security._now() - timedelta(minutes=1)
    db.flush()
    assert api.client.get("/api/v1/staff/enquiries").status_code == 401


# ---- 13.3 list and detail --------------------------------------------------------------------

def test_list_shows_flagged_first_and_filters_by_status(api, db, users):
    quote = quote_s02(api, db)
    plain = db.scalar(select(Enquiry).where(Enquiry.quote_id == quote.id))
    flagged = Enquiry(kind="no_price", flags=["no_price", "missing_rate"])
    db.add(flagged)
    db.flush()
    login(api, users)
    body = api.client.get("/api/v1/staff/enquiries").json()
    ids = [r["id"] for r in body["enquiries"]]
    assert ids.index(str(flagged.id)) < ids.index(str(plain.id))
    first_unflagged = next(i for i, r in enumerate(body["enquiries"]) if not r["flagged"])
    assert all(not r["flagged"] for r in body["enquiries"][first_unflagged:])
    row = next(r for r in body["enquiries"] if r["id"] == str(plain.id))
    assert (row["tour_id"], row["price_usd"], row["flagged"]) == ("T01", 315, False)
    assert set(body["counts"]) == {"new", "contacted", "pending", "confirmed", "closed"}
    closed = api.client.get("/api/v1/staff/enquiries", params={"status": "closed"}).json()["enquiries"]
    assert all(r["status"] == "closed" for r in closed) and str(plain.id) not in [r["id"] for r in closed]
    only_flagged = api.client.get("/api/v1/staff/enquiries", params={"flagged": True}).json()["enquiries"]
    assert only_flagged and all(r["flagged"] for r in only_flagged)


def test_detail_has_cost_gp_trace_link_and_transcript(api, db, users):
    quote = quote_s02(api, db)
    enquiry = db.scalar(select(Enquiry).where(Enquiry.quote_id == quote.id))
    login(api, users)
    d = api.client.get(f"/api/v1/staff/enquiries/{enquiry.id}").json()
    q = d["quote"]
    assert (q["price_usd"], q["deposit_usd"], q["adults"], q["tour_id"]) == (315, 315, 2, "T01")
    assert float(q["cost_usd"]) == pytest.approx(220, abs=0.01)
    assert float(q["gp_pct"]) == pytest.approx(30.16, abs=0.01)          # (315 - 220) / 315
    assert q["cost_lines"]
    assert d["trace_url"] == (f"https://langfuse.test/traces/{d['trace_id']}" if d["trace_id"] else None)
    assert [m["role"] for m in d["conversation"]] == ["traveller", "mira"]
    assert d["conversation"][0]["text"] == S02


def test_unknown_enquiry_is_404(api, users):
    login(api, users)
    assert api.client.get(f"/api/v1/staff/enquiries/{uuid.uuid4()}").status_code == 404


def test_bad_status_filter_is_rejected(api, users):
    login(api, users)
    assert api.client.get("/api/v1/staff/enquiries", params={"status": "deleted"}).status_code == 422


# ---- 13.4 notes and status -------------------------------------------------------------------

def test_notes_are_appended_with_the_author(api, db, users):
    e = Enquiry(kind="custom", flags=["handoff_requested"])
    db.add(e)
    db.flush()
    login(api, users)
    for body in ("Called, no answer.", "Emailed a plan."):
        r = api.client.post(f"/api/v1/staff/enquiries/{e.id}/notes", json={"body": body})
        assert r.status_code == 201 and r.json()["author"] == users["staff"][0]
    notes = api.client.get(f"/api/v1/staff/enquiries/{e.id}").json()["notes"]
    assert [n["body"] for n in notes] == ["Called, no answer.", "Emailed a plan."]


def test_notes_cannot_be_edited_or_deleted(api, db, users):
    login(api, users)
    e = Enquiry(kind="custom")
    db.add(e)
    db.flush()
    note_id = api.client.post(f"/api/v1/staff/enquiries/{e.id}/notes", json={"body": "First"}).json()["id"]
    for method in ("put", "patch", "delete"):                        # no route for it
        assert getattr(api.client, method)(f"/api/v1/staff/enquiries/{e.id}/notes/{note_id}").status_code in (404, 405)
    for sql in ("UPDATE enquiry_notes SET body = 'changed'", "DELETE FROM enquiry_notes"):   # nor in SQL
        with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
            db.execute(text(f"{sql} WHERE id = :id"), {"id": note_id})


def test_empty_note_is_rejected(api, db, users):
    login(api, users)
    e = Enquiry(kind="custom")
    db.add(e)
    db.flush()
    assert api.client.post(f"/api/v1/staff/enquiries/{e.id}/notes", json={"body": "  "}).status_code == 422


def test_status_change_is_saved_and_noted(api, db, users):
    e = Enquiry(kind="custom")
    db.add(e)
    db.flush()
    login(api, users)
    for status in ("contacted", "pending", "confirmed", "closed"):
        r = api.client.patch(f"/api/v1/staff/enquiries/{e.id}/status", json={"status": status})
        assert r.status_code == 200 and r.json()["status"] == status
    db.refresh(e)
    assert e.status == "closed"
    notes = db.scalars(select(EnquiryNote.body).where(EnquiryNote.enquiry_id == e.id)
                       .order_by(EnquiryNote.created_at)).all()
    assert notes[0] == "Status changed from new to contacted." and len(notes) == 4
    bad = api.client.patch(f"/api/v1/staff/enquiries/{e.id}/status", json={"status": "deleted"})
    assert bad.status_code == 422


def test_approver_can_use_the_staff_console(api, users):
    login(api, users, "approver")
    assert api.client.get("/api/v1/staff/enquiries").status_code == 200


# ---- 13.6 security -----------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", STAFF_ROUTES)
def test_no_session_is_401(api, method, path):
    body = {"json": {"body": "x"}} if method == "post" else {"json": {"status": "closed"}} if method == "patch" else {}
    assert getattr(api.client, method)(path, **body).status_code == 401


@pytest.mark.parametrize("cookie", ["", "made-up-token", "a" * 43])
def test_forged_cookie_is_401(api, cookie):
    api.client.cookies.set(COOKIE, cookie)
    assert api.client.get("/api/v1/staff/enquiries").status_code == 401


def test_staff_is_refused_approver_only_checks(db, users):
    from fastapi import HTTPException
    staff = db.scalar(select(User).where(User.email == users["staff"][0]))
    with pytest.raises(HTTPException) as err:
        security.require_role("approver")(user=staff)
    assert err.value.status_code == 403


def test_no_traveller_route_returns_enquiries_or_cost(api, db):
    """Every route outside /staff and /auth: none lists enquiries, none returns cost fields."""
    quote = quote_s02(api, db)
    enquiry = db.scalar(select(Enquiry).where(Enquiry.quote_id == quote.id))
    public = [r for r in app.routes if getattr(r, "path", "").startswith("/api/v1")
              and not r.path.startswith(("/api/v1/staff", "/api/v1/auth"))]
    for route in public:
        assert "enquiries/{" not in route.path, route.path          # no way to read one back
        if "GET" in route.methods and "{" not in route.path:
            r = api.client.get(route.path)
            assert str(enquiry.id) not in r.text, route.path
            assert not any(f'"{w}' in r.text.lower() for w in COST_WORDS), route.path
    r = api.client.get(f"/api/v1/quotes/{quote.id}")
    assert r.status_code == 200 and not any(w in k.lower() for k in r.json() for w in COST_WORDS)
    assert api.client.get(f"/api/v1/enquiries/{enquiry.id}").status_code in (404, 405)
    assert api.client.get("/api/v1/enquiries").status_code in (404, 405)


def test_staff_responses_are_the_only_ones_with_cost(api, db, users):
    quote = quote_s02(api, db)
    enquiry = db.scalar(select(Enquiry).where(Enquiry.quote_id == quote.id))
    login(api, users)
    assert "cost_usd" in api.client.get(f"/api/v1/staff/enquiries/{enquiry.id}").json()["quote"]


def test_unpriced_quote_still_shows_the_tour_name(api, db, users):
    from app.db.models import Quote
    q = Quote(status="needs_specialist", tour_id="T11", start_date=__import__("datetime").date(2027, 1, 20),
              adults=2, child_ages=[], reasons=[{"code": "missing_rate"}])
    db.add(q)
    db.flush()
    e = Enquiry(kind="no_price", quote_id=q.id, flags=["no_price", "missing_rate"])
    db.add(e)
    db.flush()
    login(api, users)
    row = next(r for r in api.client.get("/api/v1/staff/enquiries").json()["enquiries"] if r["id"] == str(e.id))
    assert row["tour_name"] and row["price_usd"] is None
    assert api.client.get(f"/api/v1/staff/enquiries/{e.id}").json()["quote"]["tour_name"] == row["tour_name"]
