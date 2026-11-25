"""Hotel bookings that go with a tour booking (mock, like the payment).

The stays come from the pricing package (app.pricing.hotel_stays): the rate sheet's hotel for
each night of the tour, rooms as priced, so what is booked is exactly what was priced.
"""

from __future__ import annotations

import secrets

from app.pricing import hotel_stays as stays  # noqa: F401  (re-exported for the bookings route)


def reference() -> str:
    """A mock hotel confirmation number."""
    return f"HTL-{secrets.token_hex(3).upper()}"
