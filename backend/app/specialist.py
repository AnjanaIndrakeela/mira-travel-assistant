"""A travel specialist's reply to a traveller (R6 "a specialist will confirm", R7 follow-up).

- The reply is shown in the traveller's own chat exactly as the specialist wrote it, labelled
  as theirs. Mira never rewrites it, and it never goes into the graph's messages, so the LLM
  doesn't see it and can't repeat a specialist's price as if it were a verified quote.
- The traveller finds out by email: an "our specialist has replied" note with a link that
  opens that chat on any device. The email is a MOCK (like the payment): it is recorded on the
  reply (who and when, and the text that would be sent) and nothing is delivered.
- Nothing here runs inside a chat turn, so the traveller's email never reaches a trace.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger("mira.specialist")

SENDER = "Travel specialist, Ceylon Compass Holidays"    # what the traveller sees (no staff email)
EMAIL_SUBJECT = "Our travel specialist has replied"


def chat_link(conversation_id: uuid.UUID) -> str:
    """Opens this chat in the traveller's browser, on any device (the ID is a random UUID)."""
    return f"{get_settings().frontend_origin.rstrip('/')}/?chat={conversation_id}"


def mock_email(name: str | None, link: str | None) -> str:
    """The email text that would be sent. It says there is a reply; the reply stays in the chat."""
    hello = f"Hello {name}," if name else "Hello,"
    where = (f"Open your chat to read it and carry on planning:\n{link}" if link
             else "Reply to this email and we'll pick it up from there.")
    return (f"{hello}\n\nOne of our travel specialists has replied to your enquiry with "
            f"Ceylon Compass Holidays.\n\n{where}\n\nCeylon Compass Holidays")


def record_mock_email(enquiry_id: uuid.UUID) -> None:
    # no address in the log: personal details stay in the database only
    logger.info("mock email recorded for enquiry %s (not delivered)", enquiry_id)


def merge(lines: list[Any], replies: list[Any], make) -> list[Any]:
    """Chat lines with the specialist replies put where they were sent: after the message
    count the chat had at that time (`after_message`), oldest first."""
    out = list(lines)
    for r in sorted(replies, key=lambda r: (r.after_message, r.created_at), reverse=True):
        out.insert(min(r.after_message, len(lines)), make(r))
    return out
