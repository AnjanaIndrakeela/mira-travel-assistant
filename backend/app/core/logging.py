"""Log masking (step 9.10): personal data never reaches the logs.

Every log record's final message is passed through mask_personal_data(), whichever module
logged it (ours, uvicorn, SQLAlchemy, LangChain). Emails, phone numbers, card-like and
passport-like numbers become [email], [phone], [card number], [id number].
"""

from __future__ import annotations

import logging

from app.guards.input_guard import mask_personal_data

_installed = False


def install_log_masking() -> None:
    """Wrap the log record factory once, so every record is masked when it is created."""
    global _installed
    if _installed:
        return
    base = logging.getLogRecordFactory()

    def factory(*args, **kwargs) -> logging.LogRecord:
        record = base(*args, **kwargs)
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001  (a bad format string: leave it to logging)
            return record
        masked = mask_personal_data(message)
        if masked != message:
            record.msg, record.args = masked, None
        return record

    logging.setLogRecordFactory(factory)
    _installed = True
