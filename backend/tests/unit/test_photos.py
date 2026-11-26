"""Tour pictures: chosen by code from our media library, credited, never repeated in a tour."""

import pytest
from pydantic import ValidationError

from app.graph.nodes import Deps
from app.guards.ui_validator import validate_ui
from app.ui import photos
from app.ui.build import choose_components, itinerary_days, tour_card
from app.ui.catalog import Image


@pytest.fixture(scope="module")
def deps():
    return Deps.default()


def test_every_photo_is_valid_and_credited():
    lib = photos.library()
    assert {"sigiriya", "kandy", "ella", "galle", "yala"} <= set(lib)
    for imgs in lib.values():
        for img in imgs:
            Image(**img)                                     # passes the catalog's own checks
            if img.get("credit"):
                assert img["licence"] and img["source"].startswith("https://commons.wikimedia.org/wiki/File:")


def test_places_in_text():
    assert photos.places_in("Sigiriya to Kandy") == ["sigiriya", "kandy"]
    assert photos.places_in("A walk on Galle Face Green") == ["colombo"]      # not Galle
    assert photos.places_in("Galle Fort and the lighthouse") == ["galle"]
    assert photos.places_in("Arrival and rest") == []
    assert photos.places_in("Umbrella stand") == []                           # "ella" only as a word


def test_tour_cards_show_their_places(deps):
    card = tour_card("T08", content=deps.content, rates=deps.rates)
    assert 1 <= len(card["images"]) <= 3
    assert card["images"][0]["src"].startswith("/api/v1/media/sigiriya/")
    assert len({i["src"] for i in card["images"]}) == len(card["images"])
    for tid in ("T01", "T05", "T09", "T12"):
        assert tour_card(tid, content=deps.content, rates=deps.rates)["images"]


def test_suggestion_card_photos_match_the_places_it_names(deps):
    """A card saying "Visits Galle, Yala" shows Galle and Yala first, not the start of the route."""
    def folders(card):
        return [i["src"].split("/")[4] for i in card["images"]]

    card = tour_card("T12", content=deps.content, rates=deps.rates, why="13 nights / 14 days, visits Galle, Yala")
    assert card["why"] == "Visits Galle, Yala"
    assert folders(card)[:2] == ["galle", "yala"]
    card = tour_card("T08", content=deps.content, rates=deps.rates, why="7 nights / 8 days, visits Galle, Minneriya")
    assert folders(card)[:2] == ["galle", "minneriya"]
    # a named place the tour doesn't visit is never pictured
    card = tour_card("T08", content=deps.content, rates=deps.rates, why="visits Yala")
    assert "yala" not in folders(card)


def test_itinerary_day_pictures_follow_the_day_and_never_repeat(deps):
    days = itinerary_days("T08", content=deps.content)
    srcs = [d["image"]["src"] for d in days if d["image"]]
    assert len(srcs) == len(set(srcs))
    by_day = {d["day"]: d["image"] for d in days}
    assert by_day[1] is None                                 # "Airport to Negombo": no picture we have
    assert "/kandy/" in by_day[4]["src"]                     # "Sigiriya to Kandy" shows where it ends


def test_gallery_for_named_places(deps):
    ui = choose_components({"action": "match_tours", "tour_cards": [{"tour_id": "T10"}],
                            "destinations": ["Ella", "Yala"]}, content=deps.content, rates=deps.rates)
    assert ui[0]["type"] == "photo_gallery" and ui[0]["title"] == "Your trip: Ella, Yala"
    ok, bad = validate_ui(ui, quote_id=None)
    assert not bad and len(ok) == len(ui)
    custom = choose_components({"unmatched_tour": "Jaffna", "destinations": ["Mirissa"]},
                               content=deps.content, rates=deps.rates)
    assert [c["type"] for c in custom] == ["photo_gallery", "specialist_notice"]
    plain = choose_components({"action": "match_tours", "tour_cards": [{"tour_id": "T10"}]},
                              content=deps.content, rates=deps.rates)
    assert all(c["type"] != "photo_gallery" for c in plain)  # no places named: the cards' photos are enough


@pytest.mark.parametrize("bad", [
    {"src": "https://evil.example/x.jpg", "alt": "x"},
    {"src": "/api/v1/media/../../etc/passwd", "alt": "x"},
    {"src": "/api/v1/media/ella/x.jpg", "alt": "<img onerror=alert(1)>"},
    {"src": "/api/v1/media/ella/x.jpg", "alt": "x", "source": "https://evil.example/File:x"},
    {"src": "/api/v1/media/ella/x.jpg", "alt": "x", "width": 10},
])
def test_image_refuses_outside_or_unsafe_values(bad):
    with pytest.raises(ValidationError):
        Image(**bad)
