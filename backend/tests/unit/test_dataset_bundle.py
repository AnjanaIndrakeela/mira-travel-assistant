"""The whole dataset loads into one bundle, with every known problem logged."""

import time
from collections import Counter
from datetime import date

from app.core.config import get_settings
from app.data_loader import load_dataset
from tests.conftest import issue_codes

EXPECTED_ISSUES = {
    # workbook
    "inconsistent_tour_id": 1, "tour_note": 1, "text_price": 2, "missing_rate": 4,
    "text_date": 1, "usd_rate": 4, "rate_conflict": 1, "expired_rate": 1,
    # content
    "hidden_comment_removed": 1, "opinion_content": 1, "stale_page": 4, "draft_content": 1,
    "expired_offer": 1, "teaser_price": 1,
    # cross-checks
    "no_rate_row": 2, "duration_mismatch": 1, "overridden_by_policy": 2, "eval_count_mismatch": 1,
}


def test_every_expected_issue_is_found(dataset):
    assert dict(Counter(i.code for i in dataset.issues)) == EXPECTED_ISSUES


def test_every_issue_says_how_it_is_handled(dataset):
    assert all(i.location and i.detail and i.handling for i in dataset.issues)


def test_published_tours_without_rates(dataset):
    assert {i.detail.split()[0] for i in issue_codes(dataset.issues, "no_rate_row")} == {"T10", "T16"}


def test_duration_mismatch_is_t06(dataset):
    [issue] = issue_codes(dataset.issues, "duration_mismatch")
    assert issue.detail.startswith("T06")


def test_policies_override_older_tour_pages(dataset):
    found = {(i.detail.split()[0], i.detail.split("; ")[1].split()[0])
             for i in issue_codes(dataset.issues, "overridden_by_policy")}
    assert found == {("T04", "P02"), ("T07", "P03")}


def test_all_17_starter_cases_are_kept(dataset):
    assert [c.id for c in dataset.eval_seed] == [f"S{n:02d}" for n in range(1, 18)]


def test_brand_pack(dataset):
    assert dataset.brand.assistant_name == "Mira"
    assert dataset.brand.colors.orange == "#F26B1D"
    assert dataset.brand.radius_px["card"] == 12


def test_loads_quickly():
    start = time.perf_counter()
    load_dataset(get_settings().mira_dataset_dir, date(2026, 11, 19))
    assert time.perf_counter() - start < 2.0
