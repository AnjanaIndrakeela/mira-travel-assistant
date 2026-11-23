"""Checks on every traveller message before the LLM sees it (plan §16 step 9).

Flagged messages are still answered, but the flags go into the trace and the graph makes no
tool calls (no quote, no booking) on an injection turn. Personal data is masked for logs.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

MAX_CHARS = 2000

INJECTION = re.compile(
    r"ignore (all |any |the |your |previous |prior |above )*(instructions|rules|prompt)"
    r"|disregard (all |any |the |your |previous )*(instructions|rules)"
    r"|forget (all |your |the )*(instructions|rules)"
    r"|(system|developer) prompt|your (instructions|prompt|rules)\b"
    r"|you are now|act as (a|an|my)\b|pretend (to be|you are)|role[- ]?play|jailbreak|\bDAN\b"
    r"|</?(system|assistant|user|s)>|\[/?INST\]|<\|im_(start|end)\|>",
    re.IGNORECASE,
)
COST_REQUEST = re.compile(
    r"\b(your|the|internal|real|net|buy|supplier|hotel)\s+(costs?|rates?|price)\b.*\b(margin|profit|pay|charge|real)\b"
    r"|\b(margin|mark-?up|gross profit|profit|gp ?%?|cost price|net rate|rate sheet|workbook)\b",
    re.IGNORECASE,
)
DISCOUNT_REQUEST = re.compile(
    r"\b(discount|\d+\s?% off|percent off|cheaper price|promo(tion)?( code)?|coupon|voucher|special price|deal on)\b",
    re.IGNORECASE,
)
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
PASSPORT = re.compile(r"\b[A-Z]{1,2}\d{6,8}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Not a phone number: ISO dates ("2027-04-12") and date ranges, which travellers type often,
# or the start of a UUID ("12345678-1234-4f67-...": the number must not run into letters).
PHONE = re.compile(r"(?<![\w-])(?!\d{4}-\d{1,2}-\d{1,2}(?!\d))\+?\d[\d ()-]{8,}\d(?![\w-])")


class InputCheck(BaseModel):
    text: str                 # what the LLM gets (trimmed to MAX_CHARS)
    flags: list[str]          # too_long, injection, cost_request, discount_request, personal_data
    for_log: str              # personal data masked

    @property
    def injection(self) -> bool:
        return "injection" in self.flags


def mask_personal_data(text: str) -> str:
    text = CARD.sub("[card number]", text)
    text = EMAIL.sub("[email]", text)
    text = PASSPORT.sub("[id number]", text)
    return PHONE.sub("[phone]", text)


def check_input(text: str) -> InputCheck:
    flags: list[str] = []
    text = text.strip()
    if len(text) > MAX_CHARS:
        flags.append("too_long")
        text = text[:MAX_CHARS]
    if INJECTION.search(text):
        flags.append("injection")
    if COST_REQUEST.search(text):
        flags.append("cost_request")
    if DISCOUNT_REQUEST.search(text):
        flags.append("discount_request")
    masked = mask_personal_data(text)
    if masked != text:
        flags.append("personal_data")
    return InputCheck(text=text, flags=flags, for_log=masked)
