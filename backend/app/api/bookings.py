"""POST /bookings (step 9.8): mock booking and payment, straight from the form (never the LLM).

1. The quote must exist and be priced.
2. Its price is re-checked with the engine: if rates or dates changed, no charge (new quote).
3. The card is checked like a real one (checksum, card type, expiry, security code), then the
   deposit is charged by the mock provider. The card details are used for that only: never
   stored, logged or traced. The booking keeps the card type and last four digits.
Success and failure both return 200 with a status and a friendly message. A failure saves a
"booking_failed" enquiry, so the team can send a payment link: the traveller is never stuck.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas import BookingOut, BookingRequest
from app.booking.mock_payment import BRAND_NAMES, charge, check_card, digits_of
from app.core.config import get_settings
from app.db.models import Booking, Enquiry, Quote
from app.db.repo import create_enquiry
from app.pricing import QuoteRequest, calculate_quote

router = APIRouter(tags=["bookings"])
logger = logging.getLogger("mira.api.bookings")

FAILED = ("The payment didn't go through. Nothing was charged. You can try again, or we've saved "
          "this as an enquiry and our team will send you a payment link.")
BAD_CARD = "That card number doesn't look right. Nothing was charged. Please check it and try again."
CARD_PROBLEM = {
    "invalid_holder": "Please enter the name as it's written on the card. Nothing was charged.",
    "invalid_card": BAD_CARD,
    "brand_mismatch": "That number isn't a {brand} card. Please check the card type. Nothing was charged.",
    "invalid_expiry": "That expiry date doesn't look right. Please use MM/YY. Nothing was charged.",
    "card_expired": "That card has expired. Please use another card. Nothing was charged.",
    "invalid_cvc": "The security code should be {cvc} digits, from the {side} of the card. Nothing was charged.",
}
PRICE_CHANGED = ("The price for this trip has changed since your quote, so nothing was charged. "
                 "Please ask me for a new quote.")


@router.post("/bookings", response_model=BookingOut)
def book(req: BookingRequest, db: Session = Depends(get_db)) -> BookingOut:
    quote = db.get(Quote, req.quote_id)
    if quote is None:
        raise HTTPException(404, "We couldn't find that quote. Please ask me for a new one.")
    if quote.status != "ok":
        raise HTTPException(409, "A travel specialist needs to confirm the price before this trip can be booked.")
    if db.scalar(select(Booking.id).where(Booking.quote_id == quote.id, Booking.status == "confirmed")):
        raise HTTPException(409, "This quote is already booked.")

    check = calculate_quote(QuoteRequest(tour_id=quote.tour_id, start_date=quote.start_date,
                                         adults=quote.adults, child_ages=tuple(quote.child_ages)))
    if check.status != "ok" or check.staff.public.price_usd != quote.price_usd:
        return BookingOut(status="price_changed", message=PRICE_CHANGED, next_steps=["new_quote"])

    card = req.card
    digits = digits_of(card.number)
    kept = {"card_brand": card.brand, "card_last4": digits[-4:] if digits.isdigit() else None}
    if problem := check_card(holder=card.holder, brand=card.brand, number=card.number, exp_month=card.exp_month,
                             exp_year=card.exp_year, cvc=card.cvc, today=get_settings().mira_today):
        reason, field = problem
        booking = Booking(quote_id=quote.id, status="payment_failed", **kept)
        db.add(booking)
        db.commit()
        msg = CARD_PROBLEM[reason].format(brand=BRAND_NAMES[card.brand], cvc=4 if card.brand == "amex" else 3,
                                          side="front" if card.brand == "amex" else "back")
        return BookingOut(status="payment_failed", message=msg, booking_id=booking.id, next_steps=["retry"],
                          field=field)

    result = charge(quote.deposit_usd, digits)
    contact = req.contact.model_dump()
    if not result.ok:
        booking = Booking(quote_id=quote.id, status="payment_failed", **kept)
        db.add(booking)
        if result.reason == "invalid_card":
            db.commit()
            return BookingOut(status="payment_failed", message=BAD_CARD, booking_id=booking.id,
                              next_steps=["retry"], field="number")
        enquiry = create_enquiry(db, "booking_failed", quote=quote, flags=[result.reason or "payment_failed"],
                                 contact=contact, notes="Mock payment failed: send a payment link.")
        db.commit()
        logger.info("booking failed for quote %s: %s", quote.id, result.reason)
        return BookingOut(status="payment_failed", message=FAILED, booking_id=booking.id,
                          next_steps=["retry", "payment_link", "enquiry_saved"], enquiry_id=enquiry.id)

    booking = Booking(quote_id=quote.id, status="confirmed", payment_ref=result.reference, **kept)
    paid_with = f"{BRAND_NAMES[card.brand]} ending {kept['card_last4']}"
    db.add(booking)
    # the quote's own enquiry (R7) gets the contact and the outcome, for the team's follow-up
    enquiry = db.scalar(select(Enquiry).where(Enquiry.quote_id == quote.id, Enquiry.kind == "quote")
                        .order_by(Enquiry.created_at.desc()))
    note = f"Booked (mock). Deposit USD {quote.deposit_usd} paid with {paid_with}, ref {result.reference}."
    if enquiry is None:
        enquiry = create_enquiry(db, "quote", quote=quote, contact=contact, notes=note)
    else:
        enquiry.contact = contact
        enquiry.notes = "\n".join(filter(None, [enquiry.notes, note]))
    db.commit()
    paid_all = quote.balance_usd == 0
    msg = (f"Your booking for the {quote.tour_name} is confirmed. We charged USD {quote.deposit_usd:,} "
           + ("(the full price)." if paid_all else
              f"as the deposit; the balance of USD {quote.balance_usd:,} is due by "
              f"{quote.balance_due.day} {quote.balance_due:%B %Y}.")
           + " This is a demo: no real payment was taken.")
    return BookingOut(status="confirmed", message=msg, booking_id=booking.id,
                      payment_reference=result.reference, amount_charged_usd=quote.deposit_usd,
                      enquiry_id=enquiry.id, card=paid_with)
