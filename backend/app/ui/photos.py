"""Pictures for tours and plans, chosen by code from our media library (never by the LLM).

backend/media/<place>/media.json lists each file with its alt text and, for open-licence
photos (Wikimedia Commons), the author, licence and source page, which the UI shows under the
image as the licences require. A tour's pictures come from its destinations (front matter) and
the places its title names; an itinerary day gets a picture of the place it names.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

URL = "/api/v1/media/{path}"
SRC = re.compile(r"^/api/v1/media/[a-z0-9-]+/[a-z0-9][a-z0-9.-]*\.(?:jpg|jpeg|png|svg|webp)$")

# how places are written in titles and text -> media folder
PLACE_NAMES: dict[str, tuple[str, ...]] = {
    "sigiriya": ("sigiriya",), "kandy": ("kandy", "temple of the tooth", "sacred tooth"),
    "ella": ("ella", "nine arch", "little adam"), "nuwara-eliya": ("nuwara eliya", "tea country", "tea estate"),
    "galle": ("galle fort", "galle"), "mirissa": ("mirissa", "whale"), "yala": ("yala", "leopard"),
    "minneriya": ("minneriya",), "anuradhapura": ("anuradhapura",), "polonnaruwa": ("polonnaruwa",),
    "colombo": ("colombo", "galle face"), "dambulla": ("dambulla",),
}
# slugs used in tour front matter that differ from the folder names
ALIASES = {"minneriya-national-park": "minneriya", "yala-national-park": "yala"}


@lru_cache
def library(media_dir: str | None = None) -> dict[str, list[dict]]:
    """{place: [image, ...]}, photos first. Read once from the manifests."""
    if media_dir is None:
        from app.core.config import get_settings
        media_dir = str(get_settings().mira_media_dir)
    out: dict[str, list[dict]] = {}
    for manifest in sorted(Path(media_dir).glob("*/media.json")):
        place = manifest.parent.name
        for e in json.loads(manifest.read_text(encoding="utf-8")):
            if not (manifest.parent / e["file"]).is_file():
                continue
            img = {"src": URL.format(path=f"{place}/{e['file']}"), "alt": e["alt"][:200]}
            if e.get("kind") == "photo":
                img.update(credit=(e.get("credit") or "Unknown")[:120], licence=e.get("licence") or None,
                           source=e.get("source") or None)
            out.setdefault(place, []).append(img)
        out.get(place, []).sort(key=lambda i: "credit" not in i)       # real photos before illustrations
    return out


def places_in(text: str) -> list[str]:
    """Places a text names, in the order they appear ("Galle Face" is Colombo, not Galle)."""
    low = text.lower()
    hits: list[tuple[int, str]] = []
    for place, names in PLACE_NAMES.items():
        for name in names:
            for m in re.finditer(rf"\b{re.escape(name)}\b", low):
                if place == "galle" and low.startswith("galle face", m.start()):
                    continue
                hits.append((m.start(), place))
    return list(dict.fromkeys(p for _, p in sorted(hits)))


def for_places(places: list[str], n: int = 3, *, offset: int = 0) -> list[dict]:
    """Up to n images, taking one per place in turn so a multi-place tour shows several places."""
    lib = library()
    places = [ALIASES.get(p, p) for p in dict.fromkeys(places)]
    pools = [lib[p] for p in places if p in lib]
    out: list[dict] = []
    i = 0
    while pools and len(out) < n and i < n * 4:
        pool = pools[i % len(pools)]
        img = pool[(offset + i // len(pools)) % len(pool)]
        if img not in out:
            out.append(img)
        i += 1
    return out


def for_tour(doc: Any, n: int = 3, *, first: list[str] | tuple[str, ...] = ()) -> list[dict]:
    """A tour's pictures. `first`: places to show before the rest of the route, such as the
    stops a suggestion card names ("Visits Galle, Yala"), so the photos match the card's text."""
    route = [*(str(d) for d in doc.meta.get("destinations", [])), *places_in(doc.title)]
    on_route = {ALIASES.get(p, p) for p in route}
    places = [*(p for p in first if ALIASES.get(p, p) in on_route), *route]
    if not places:
        places = places_in(doc.body[:1500])
    return for_places(places, n)


def for_days(days: list[tuple[str, str]]) -> list[dict | None]:
    """One picture per itinerary day (title, description), never the same one twice in a tour.
    "Sigiriya to Kandy" shows Kandy: where the day ends. A day with no unused picture gets none."""
    lib, used, out = library(), set(), []
    for title, description in days:
        named = places_in(title)
        places = [*reversed(named), *(p for p in places_in(description) if p not in named)]
        pick = next((img for p in places for img in lib.get(p, []) if img["src"] not in used), None)
        if pick:
            used.add(pick["src"])
        out.append(pick)
    return out
