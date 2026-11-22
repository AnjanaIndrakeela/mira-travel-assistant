"""Load the whole supplied dataset into memory, read-only, with a log of data issues.

    python -m app.data_loader              # print a summary and every data issue
    python -m app.data_loader --markdown   # print the issues as a Markdown table
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.data_loader.brand_loader import BrandPack, load_brand
from app.data_loader.content_loader import ContentDoc, ContentLibrary, load_content
from app.data_loader.eval_seed_loader import EvalCase, load_eval_seed
from app.data_loader.issues import DataIssue
from app.data_loader.rate_loader import RateBook, load_rate_book

__all__ = ["DatasetBundle", "load_dataset", "get_dataset"]


@dataclass(frozen=True)
class DatasetBundle:
    rates: RateBook
    content: ContentLibrary
    brand: BrandPack
    eval_seed: list[EvalCase]
    issues: list[DataIssue]          # all issues: workbook + content + cross-checks


_NIGHTS = re.compile(r"(\d+)\s+nights?", re.IGNORECASE)
_README_CASES = re.compile(r"(\d+)\s+starter test cases", re.IGNORECASE)

# Topics where a current policy page says it replaces older tour pages.
_POLICY_TOPICS = {
    "cancellation": {"policy_title": "cancellation", "tour_markers": ("cancellation",)},
    "children": {"policy_title": "children", "tour_markers": ("stay free", "family offer", "kids under")},
}


def _content_nights(doc: ContentDoc) -> int | None:
    duration = str(doc.meta.get("duration", ""))
    m = _NIGHTS.search(duration)
    if m:
        return int(m.group(1))
    if re.search(r"\b(1 day|half day|full day)\b", duration, re.IGNORECASE):
        return 0
    return None


def _cross_check(rates: RateBook, content: ContentLibrary) -> list[DataIssue]:
    issues: list[DataIssue] = []
    tours = content.by_type("tour", published_only=False)

    for doc in tours:
        rate = rates.tours.get(doc.id)
        if doc.is_published and rate is None:
            issues.append(DataIssue(
                code="no_rate_row", location=doc.path,
                detail=f"{doc.id} {doc.title!r} is published but has no row in the rate workbook.",
                handling="Described from content; price requests go to a specialist."))
        if rate is not None:
            nights = _content_nights(doc)
            if nights is not None and nights != rate.nights:
                issues.append(DataIssue(
                    code="duration_mismatch", location=f"{doc.path} / Tours!row {rate.row}",
                    detail=(f"{doc.id} page says {doc.meta.get('duration')!r}; the workbook says "
                            f"{rate.days} day(s), {rate.nights} night(s)."),
                    handling="Priced from the workbook (the pricing source of truth)."))

    for tour_id in sorted(set(rates.tours) - {d.id for d in tours}):
        issues.append(DataIssue(
            code="rate_without_content", location=f"Tours!row {rates.tours[tour_id].row}",
            detail=f"{tour_id} has rates but no tour page.",
            handling="Never offered to travellers."))

    policies = content.by_type("policy")
    for topic, rule in _POLICY_TOPICS.items():
        policy = next((p for p in policies
                       if rule["policy_title"] in p.title.lower() and "replace" in p.body.lower()), None)
        if policy is None:
            continue
        for doc in tours:
            if not doc.is_published:
                continue
            headings = " ".join(s.heading.lower() for s in doc.sections if s.heading != "Overview")
            text = doc.body.lower()
            hit = (topic == "cancellation" and any(m in headings for m in rule["tour_markers"])) or \
                  (topic == "children" and any(m in text for m in rule["tour_markers"]))
            if hit:
                issues.append(DataIssue(
                    code="overridden_by_policy", location=doc.path,
                    detail=f"{doc.id} has its own {topic} terms; {policy.id} ({policy.title}) replaces older pages.",
                    handling=f"{policy.id} always wins; it is retrieved with any {topic} question."))
    return issues


def _check_eval_count(dataset_dir: Path, seed: list[EvalCase]) -> list[DataIssue]:
    readme = (dataset_dir / "README.md").read_text(encoding="utf-8")
    m = _README_CASES.search(readme)
    if m and int(m.group(1)) != len(seed):
        return [DataIssue(
            code="eval_count_mismatch", location="README.md / evals/eval_seed.jsonl",
            detail=f"The dataset README says {m.group(1)} starter cases; the file has {len(seed)}.",
            handling=f"All {len(seed)} cases are used, unchanged.")]
    return []


def load_dataset(dataset_dir: Path, today: date) -> DatasetBundle:
    rates = load_rate_book(dataset_dir)
    content = load_content(dataset_dir, today)
    brand = load_brand(dataset_dir)
    seed = load_eval_seed(dataset_dir)
    issues = [*rates.issues, *content.issues, *_cross_check(rates, content),
              *_check_eval_count(dataset_dir, seed)]
    return DatasetBundle(rates=rates, content=content, brand=brand, eval_seed=seed, issues=issues)


@lru_cache
def get_dataset() -> DatasetBundle:
    from app.core.config import get_settings

    s = get_settings()
    return load_dataset(s.mira_dataset_dir, s.mira_today)
