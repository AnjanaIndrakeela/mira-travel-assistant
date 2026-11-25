"""Deterministic pricing engine: the only source of every price Mira shows.

No LLM is involved: an LLM may *ask* for a quote, but this code calculates it, with
Decimal arithmetic only. Travellers see the selling price and deposit; cost and gross
profit are for staff only.

PRICING RULES (rate workbook, READ ME tab; numbers match the workbook)
-----------------------------------------------------------------------
 1. Currency. Buy costs are in LKR; we sell in USD. Convert at the FX rate on the
    Settings tab (300 LKR = 1 USD). The rate is fixed for quoting until 31 Oct 2027.
    -> money.py (lkr_to_usd), validators.py (no tour day after that date)

 2. Cost of a booking =
        guide fee per day × days
      + vehicle per day × days
      + entrance fees per person (whole tour)
      + meals per person per day × days
      + hotel rooms for each night.
    -> calculator.py

 3. Vehicle depends on group size = adults + children aged 2–11 (infants don't count).
    Transport tab: Car 1–3, Van 4–8, Mini coach 9–20.
    -> party.py (vehicle_headcount), RateBook.vehicle_for

 4. Rooms: two adults share a double room; an odd adult takes a single room. Each
    child aged 2–11 gets an extra bed in a parent's room, every night.
    -> calculator.py (hotels)

 5. Children aged 2–11 pay the child entrance fee and 50% of the adult meal cost.
    Infants under 2 are free: no seat, entrance, meals or bed.
    -> party.py, calculator.py

 6. Hotel rate = the row whose Valid from / Valid to dates cover that night.
    Night 1 is the tour start date, night 2 the next day, and so on.
    -> calculator.py (hotels), RateBook.hotel_rates_for

 7. Margin is gross profit on the selling price: Sell = Cost ÷ (1 − margin).
    Settings tab: 30% for day tours, 25% for multi-day tours.
    -> money.py (apply_margin), service.py (margins and overrides)

 8. Round the booking total UP to the next USD 5.
    -> money.py (round_up_to)

 9. Deposit: day tours pay in full. Multi-day tours pay 25%, rounded up to the next
    whole USD, with the balance due 30 days before the start. If the tour starts
    within 30 days of booking, they pay in full.
    -> calculator.py (deposit), money.py (ceil_usd)

10. Maximum 20 travellers per private tour (adults + children aged 2–11).
    Bigger groups go to Sales.
    -> validators.py

11. If a rate isn't in the workbook, don't make one up: send it to Sales.
    A missing, expired or conflicting rate means no price, only a refusal with a
    reason, and a specialist confirms.
    -> reasons.py, calculator.py (collects every problem), QuoteResult "needs_specialist"

DECISIONS WHERE THE READ ME IS SILENT (documented, so they can be challenged)
-----------------------------------------------------------------------------
 a. Age 12 and over counts as an adult (policy P03: "Children 12 and over pay adult rates").
 b. "Within 30 days" means 30 days or fewer between today and the start date.
 c. The deposit is 25% of the *rounded* selling price; gross profit % uses the rounded price.
 d. The cost is not rounded before the margin is applied (only the final total is rounded).
 e. Hotel rows in USD (H10) are added in USD, never divided by the FX rate.
 f. Two hotel rows covering the same night is a conflict, not a choice: no price.
 g. "Today" is a parameter (MIRA_TODAY, default 2026-11-19), never the system clock.
 h. There are no other supplements: single, child and accommodation effects come only
    from rules 4 and 5. No discount input exists. (The assignment brief's "child & single
    supplements" are exactly these: the odd adult's single room, and the child's extra bed,
    child entrance fee and 50% meals. The READ ME has no separate supplement charge.)
"""

from app.pricing.models import PublicQuote, QuoteRequest, QuoteResult, StaffQuote
from app.pricing.reasons import Refusal, RefusalCode
from app.pricing.service import calculate_quote

__all__ = ["calculate_quote", "QuoteRequest", "QuoteResult", "PublicQuote", "StaffQuote",
           "Refusal", "RefusalCode"]
