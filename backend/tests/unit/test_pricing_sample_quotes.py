"""Step 4.4: the engine against the sales team's sample quotes (rates/sample_quotes.md).

Q-1041, Q-1042 and Q-1044 match the engine exactly. Q-1043 does NOT, and the engine is right:
the sample's hotel line (LKR 146,000) is the double room only. READ ME rule 4 gives each child
aged 2-11 an extra bed every night; for 2 children over 6 nights that is LKR 64,000 more:
    H12 4,500 x 2 x 2 + H02 6,000 x 2 x 2 + H03 5,500 x 2 x 2 = 64,000
so hotels are 210,000, cost 667,000, price USD 2,965 and deposit 742 (= eval case S03),
not USD 2,680 / 670. Logged in docs/data-issues.md ("Found by the pricing tests").
"""

import re
from datetime import date

import pytest

from app.data_loader.issues import TEST_FINDINGS, issues_to_markdown
from app.pricing import QuoteRequest, calculate_quote

TODAY = date(2026, 11, 19)
INPUTS = {   # the "Travellers" and "Start date" lines of each sample quote
    "Q-1041": ("T01", date(2027, 1, 10), 2, ()),
    "Q-1042": ("T09", date(2027, 5, 3), 2, ()),
    "Q-1043": ("T09", date(2027, 4, 12), 2, (7, 10)),
    "Q-1044": ("T08", date(2026, 12, 1), 2, ()),
}


def _int(text: str) -> int:
    return int(text.replace(",", ""))


def sample_quotes(dataset_dir) -> dict[str, dict]:
    """Parse the sample quotes file as sent (the file itself is never changed)."""
    text = (dataset_dir / "rates" / "sample_quotes.md").read_text(encoding="utf-8")
    quotes = {}
    for block in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
        qid = block.split()[0]
        lines = {m.group(1).split(" (")[0].lower(): _int(m.group(2))
                 for m in re.finditer(r"^- (Guide|Vehicle \(\w+\)|Entrance|Meals|Hotels): LKR ([\d,]+)", block, re.M)}
        quotes[qid] = dict(
            lines=lines,
            cost=_int(re.search(r"Total cost: LKR ([\d,]+)", block).group(1)),
            price=_int(re.search(r"Price: USD ([\d,]+)", block).group(1)),
            deposit=_int(re.search(r"Deposit: USD ([\d,]+)", block).group(1)))
    return quotes


def engine(rates, content, qid):
    tour, start, adults, ages = INPUTS[qid]
    r = calculate_quote(QuoteRequest(tour_id=tour, start_date=start, adults=adults, child_ages=ages),
                        rates=rates, content=content, today=TODAY)
    assert r.status == "ok", r.reasons
    return r


def test_the_file_has_the_four_quotes(dataset_dir):
    assert list(sample_quotes(dataset_dir)) == list(INPUTS)


@pytest.mark.parametrize("qid", ["Q-1041", "Q-1042", "Q-1044"])
def test_engine_matches_correct_sample_quotes(rates, content, dataset_dir, qid):
    sample, r = sample_quotes(dataset_dir)[qid], engine(rates, content, qid)
    assert {line.item: line.lkr for line in r.staff.cost_lines} == sample["lines"]
    assert r.staff.cost_lkr == sample["cost"]
    assert (r.public.price_usd, r.public.deposit_usd) == (sample["price"], sample["deposit"])


def test_q1043_sample_is_wrong_and_the_engine_charges_the_extra_beds(rates, content, dataset_dir):
    sample, r = sample_quotes(dataset_dir)["Q-1043"], engine(rates, content, "Q-1043")
    ours = {line.item: line.lkr for line in r.staff.cost_lines}

    # the sample as sent: USD 2,680 / 670 on a cost of 603,000
    assert (sample["price"], sample["deposit"], sample["cost"]) == (2680, 670, 603_000)
    # the engine, following READ ME rule 4: USD 2,965 / 742 on a cost of 667,000
    assert (r.public.price_usd, r.public.deposit_usd, r.staff.cost_lkr) == (2965, 742, 667_000)

    # every line agrees except hotels, and the gap is exactly the extra beds
    assert {k: v for k, v in ours.items() if k != "hotels"} == \
           {k: v for k, v in sample["lines"].items() if k != "hotels"}
    assert ours["hotels"] - sample["lines"]["hotels"] == 64_000
    # the sample's hotel figure is what the same dates cost with no children (doubles only)
    no_kids = calculate_quote(QuoteRequest(tour_id="T09", start_date=date(2027, 4, 12), adults=2),
                              rates=rates, content=content, today=TODAY)
    assert next(line.lkr for line in no_kids.staff.cost_lines if line.item == "hotels") == sample["lines"]["hotels"]


def test_q1043_finding_is_in_the_data_issues_log():
    assert [f.code for f in TEST_FINDINGS] == ["sample_quote_wrong"]
    md = issues_to_markdown([])
    assert "## Found by the pricing tests" in md and "Q-1043" in md and "2,965" in md
