"""The entry point (steps 3.36-3.37): calculate_quote() and the CLI."""

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import app
from app.core.config import Settings
from app.pricing import QuoteRequest, RefusalCode, calculate_quote
from app.pricing.__main__ import main

TODAY = date(2026, 11, 19)


def q(tour_id, start, adults, ages=(), **kw):
    req = QuoteRequest(tour_id=tour_id, start_date=start, adults=adults, child_ages=ages)
    kw.setdefault("today", TODAY)
    return calculate_quote(req, **kw)


def test_s03_ok(rates, content):
    r = q("T09", date(2027, 4, 12), 2, (7, 10), rates=rates, content=content)
    assert r.status == "ok" and r.reasons == ()
    assert (r.public.price_usd, r.public.deposit_usd) == (2965, 742)
    assert r.public.tour_name == content.get("T09").title
    assert r.staff.gp_pct == Decimal("25.01")


def test_defaults_come_from_dataset_and_settings():
    r = q("T01", date(2027, 1, 10), 2, today=None)              # MIRA_TODAY, get_dataset()
    assert r.public.price_usd == 315


def test_tour_id_is_normalised_on_the_way_in():
    assert q("t-9", date(2027, 4, 12), 2, (7, 10)).public.price_usd == 2965


@pytest.mark.parametrize("tour_id, start, adults, ages, expected", [
    ("T09", date(2027, 4, 12), 2, (25,), RefusalCode.INVALID_AGE),       # party
    ("T15", date(2027, 4, 12), 2, (), RefusalCode.NOT_PUBLISHED),         # validator
    ("T14", date(2027, 4, 12), 2, (), RefusalCode.STALE_TOUR),
    ("T10", date(2027, 4, 12), 2, (), RefusalCode.NO_RATE_ROW),
    ("T16", date(2027, 4, 12), 2, (), RefusalCode.NO_RATE_ROW),
    ("T09", date(2027, 4, 12), 0, (), RefusalCode.NO_ADULTS),
    ("T09", date(2027, 4, 12), 21, (), RefusalCode.GROUP_TOO_LARGE),
    ("T09", date(2026, 11, 1), 2, (), RefusalCode.DATE_IN_PAST),
    ("T09", date(2027, 10, 30), 2, (), RefusalCode.DATE_OUT_OF_RANGE),
    ("T12", date(2027, 4, 10), 1, (), RefusalCode.MISSING_RATE),          # calculator
    ("T11", date(2027, 1, 20), 2, (), RefusalCode.EXPIRED_RATE),
    ("T09", date(2027, 2, 1), 2, (), RefusalCode.RATE_CONFLICT),
])
def test_refusals_have_no_price(tour_id, start, adults, ages, expected):
    r = q(tour_id, start, adults, ages)
    assert r.status == "needs_specialist"
    assert r.reasons[0].code == expected
    assert r.staff is None and r.public is None


def test_every_night_problem_reaches_the_result():
    assert len(q("T11", date(2027, 1, 20), 2).reasons) == 6


def test_margin_override_from_settings(monkeypatch):
    monkeypatch.setenv("MIRA_MARGIN_DAY", "0.32")
    r = q("T01", date(2027, 1, 10), 2, settings=Settings())
    assert r.public.price_usd == 325 and r.staff.margin == Decimal("0.32")


def test_today_comes_from_settings_when_not_given(monkeypatch):
    monkeypatch.setenv("MIRA_TODAY", "2027-04-13")
    r = q("T09", date(2027, 4, 12), 2, today=None, settings=Settings())
    assert r.reasons[0].code == RefusalCode.DATE_IN_PAST


def test_nothing_outside_pricing_uses_the_engine_internals():
    """calculate_quote is the only way in: no other module imports calculator, money, etc."""
    internal = {"calculator", "money", "validators", "party"}
    root = Path(app.__file__).parent
    offenders = []
    for path in root.rglob("*.py"):
        if "pricing" in path.relative_to(root).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app.pricing."):
                if node.module.split(".")[2] in internal:
                    offenders.append(f"{path.name}: {node.module}")
    assert offenders == []


# 3.37 CLI ------------------------------------------------------------------------------------

def test_cli_s03(capsys):
    assert main(["T09", "2027-04-12", "2", "--kids", "7", "10", "--today", "2026-11-19"]) == 0
    out = capsys.readouterr().out
    assert "Price    $2,965" in out and "Deposit  $742" in out and "GP 25.01%" in out
    assert "Balance  $2,223 due 2027-03-13" in out
    assert "Van 26,000 × 7 days" in out


def test_cli_refusal(capsys):
    assert main(["T12", "2027-04-10", "1", "--today", "2026-11-19"]) == 2
    out = capsys.readouterr().out
    assert "NEEDS A SPECIALIST" in out and "missing_rate" in out
    assert out.startswith("T12 from 2027-04-10, 1 adult\n")
