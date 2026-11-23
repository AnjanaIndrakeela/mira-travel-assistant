"""Content loader: structure, cleaning and trust flags."""

from datetime import date

from app.data_loader.content_loader import Trust, has_expired_season
from tests.conftest import issue_codes


def test_all_pages_load(content):
    assert len(content.by_type("tour", published_only=False)) == 16
    assert len(content.by_type("destination")) == 10
    assert {d.id for d in content.docs if d.path.startswith("content/policies/")} == \
        {"P01", "P02", "P03", "P04", "P05", "P06"}


def test_front_matter_is_split_from_body(content):
    t09 = content.get("T09")
    assert t09.title == "Cultural Triangle Sri Lanka Package"
    assert t09.last_updated == date(2026, 9, 12)
    assert t09.meta["duration"] == "6 nights / 7 days"
    assert "status:" not in t09.body


def test_every_doc_has_sections(content):
    assert all(d.sections for d in content.docs)


def test_itinerary_days_only_on_t07_t08_t09(content):
    with_days = {d.id for d in content.docs if d.itinerary}
    assert with_days == {"T07", "T08", "T09"}


def test_itinerary_fields_are_parsed(content):
    day1 = content.get("T09").itinerary[0]
    assert (day1.day, day1.title) == (1, "Colombo to Anuradhapura")
    assert day1.meals == "Dinner"
    assert day1.accommodation.startswith("Anuradhapura Heritage Lodge")
    assert day1.entrance_tickets == "None"
    assert "**" not in day1.description


def test_html_comments_are_stripped(content):
    assert all("<!--" not in d.body for d in content.docs)
    assert "loyalty discount" not in content.get("D08").body
    assert len(issue_codes(content.issues, "hidden_comment_removed")) == 1


def test_testimonials_are_opinion(content):
    assert content.get("P06").trust is Trust.OPINION
    assert all(d.trust is Trust.FACT for d in content.docs if d.id != "P06")


def test_stale_pages(content):
    assert {d.id for d in content.docs if d.stale} == {"T06", "T07", "T14", "T16"}


def test_expired_offer(content):
    assert {d.id for d in content.docs if d.expired_offer} == {"T14"}


def test_expired_season_rule():
    today = date(2026, 11, 19)
    assert has_expired_season("Winter 2023/24 deal", today)
    assert not has_expired_season("Season 2026/27 rates", today)
    assert not has_expired_season("Call 2023/99 today", today)   # not a season pair


def test_drafts_are_never_published(content):
    assert content.get("T15").status == "draft"
    assert "T15" not in {d.id for d in content.published()}
    assert content.get_published("T15") is None
    assert content.get_published("T09") is not None
