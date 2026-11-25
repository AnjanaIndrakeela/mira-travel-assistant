"""Try the pricing engine from a shell (staff view: shows cost and GP%).

    python -m app.pricing T09 2027-04-12 2 --kids 7 10
    python -m app.pricing T12 2027-04-10 1                 # -> needs a specialist
    python -m app.pricing T01 2027-01-10 2 --today 2026-11-19
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from app.pricing.models import QuoteRequest, QuoteResult
from app.pricing.service import calculate_quote


def _usd(n) -> str:
    return f"${n:,}"


def render(result: QuoteResult) -> str:
    req = result.request
    head = f"{req.tour_id} from {req.start_date}, {req.adults} adult{'' if req.adults == 1 else 's'}"
    if req.child_ages:
        head += f", child ages {', '.join(map(str, req.child_ages))}"
    out = [head, ""]

    if result.status == "needs_specialist":
        out.append("NEEDS A SPECIALIST")
        for r in result.reasons:
            out.append(f"  - {r.code.value}: {r.detail_staff}")
        out += ["", f"Traveller sees: {result.reasons[0].message_traveller}"]
        return "\n".join(out)

    s, p = result.staff, result.staff.public
    out.append(f"{p.tour_name} ({p.start_date} to {p.end_date}); "
               f"{p.adults} adults, {p.children} children, {p.infants} infants; {s.vehicle}")
    out.append("")
    for line in s.cost_lines:
        amount = f"LKR {line.lkr:>12,.2f}" + (f"  + USD {line.usd:,.2f}" if line.usd else "")
        out.append(f"  {line.item:<9} {amount}   {line.detail}")
    out.append(f"  {'cost':<9} LKR {s.cost_lkr:>12,.2f}   = USD {s.cost_usd:,.2f} at {s.fx_lkr_per_usd} LKR/USD")
    out.append("")
    out.append(f"Price    {_usd(p.price_usd)}   (margin {s.margin:.0%}, GP {s.gp_pct}%)")
    out.append(f"Deposit  {_usd(p.deposit_usd)}")
    if p.balance_due:
        out.append(f"Balance  {_usd(p.balance_usd)} due {p.balance_due}")
    else:
        out.append("Paid in full")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.pricing", description="Price one booking.")
    ap.add_argument("tour_id")
    ap.add_argument("start_date", type=date.fromisoformat)
    ap.add_argument("adults", type=int)
    ap.add_argument("--kids", type=int, nargs="*", default=[], metavar="AGE",
                    help="age of every non-adult traveller, infants included")
    ap.add_argument("--today", type=date.fromisoformat, default=None,
                    help="override MIRA_TODAY (YYYY-MM-DD)")
    args = ap.parse_args(argv)

    req = QuoteRequest(tour_id=args.tour_id, start_date=args.start_date,
                       adults=args.adults, child_ages=tuple(args.kids))
    result = calculate_quote(req, today=args.today)
    print(render(result))
    return 0 if result.status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
