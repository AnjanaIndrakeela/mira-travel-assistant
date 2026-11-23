"""Staff security: password hashing, sessions and role checks (step 13.1).

Passwords: the standard library's scrypt (no extra dependency). Stored format
"scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>", so parameters can be raised later without
breaking old hashes. Comparison is constant-time.

Sessions: the browser gets a random token in an HttpOnly, SameSite=Lax cookie; the database
keeps only its SHA-256, so a leaked table can't be replayed as a login. Logout deletes the row.

Roles: checked here, in code, by require_role(). Never by a prompt.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_db

_N, _R, _P, _DKLEN = 2**14, 8, 1, 32

COOKIE = "mira_staff"
ROLES_ALLOWED = {"staff": {"staff", "approver"}, "approver": {"approver"}}   # an approver is also staff


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password is empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p), dklen=len(digest_hex) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# checked when the email is unknown, so response time doesn't reveal which emails exist
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def authenticate(db: Session, email: str, password: str):
    """The user for this email and password, or None. Always does exactly one scrypt check."""
    from app.db.models import User
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    return user if user and ok else None


def start_session(db: Session, response: Response, user, *, hours: float, secure: bool) -> None:
    from app.db.models import StaffSession
    token = secrets.token_urlsafe(32)
    db.execute(delete(StaffSession).where(StaffSession.expires_at < _now()))     # tidy expired ones
    db.add(StaffSession(token_hash=token_hash(token), user_id=user.id,
                        expires_at=_now() + timedelta(hours=hours)))
    db.flush()
    response.set_cookie(COOKIE, token, max_age=int(hours * 3600), httponly=True, secure=secure,
                        samesite="lax", path="/")


def end_session(db: Session, request: Request, response: Response) -> None:
    from app.db.models import StaffSession
    if token := request.cookies.get(COOKIE):
        db.execute(delete(StaffSession).where(StaffSession.token_hash == token_hash(token)))
    response.delete_cookie(COOKIE, path="/")


def current_user(request: Request, db: Session = Depends(get_db)):
    """The signed-in staff user, or 401. An expired session counts as signed out."""
    from app.db.models import StaffSession
    token = request.cookies.get(COOKIE)
    row = db.get(StaffSession, token_hash(token)) if token else None
    if row is None or row.expires_at <= _now():
        raise HTTPException(401, "Please sign in.")
    return row.user


def require_role(role: str):
    """Dependency: the signed-in user if their role allows `role`; else 401 (not signed in)
    or 403 (signed in, wrong role)."""
    allowed = ROLES_ALLOWED[role]

    def check(user=Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, "You don't have permission to do that.")
        return user
    return check


class LoginLimiter:
    """At most `limit` failed logins per key (email, client) in `window` seconds."""

    def __init__(self, limit: int = 5, window: float = 900.0):
        self.limit, self.window = limit, window
        self._fails: dict[str, deque] = defaultdict(deque)

    def _recent(self, key: str) -> deque:
        q, cutoff = self._fails[key], time.monotonic() - self.window
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def blocked(self, *keys: str) -> bool:
        return any(len(self._recent(k)) >= self.limit for k in keys)

    def failed(self, *keys: str) -> None:
        for k in keys:
            self._recent(k).append(time.monotonic())

    def clear(self, *keys: str) -> None:
        for k in keys:
            self._fails.pop(k, None)


login_limiter = LoginLimiter()
