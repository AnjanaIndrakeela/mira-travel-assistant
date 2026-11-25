"""Guards for the pricing spec: it follows the READ ME, and no invented rule can creep in.

These checks keep holding as the engine grows (Phase 3): if someone adds a 'discount' or
'supplement' input to the pricing code, or the spec drifts from the workbook, a test fails.
"""

import ast
import re
from pathlib import Path

from openpyxl import load_workbook

import app.pricing as pricing

PRICING_DIR = Path(pricing.__file__).parent
FORBIDDEN = re.compile(r"discount|supplement|surcharge|promo|coupon", re.IGNORECASE)


def _readme_rules(dataset_dir) -> dict[int, str]:
    wb = load_workbook(dataset_dir / "rates" / "rate_sheet_2026-27.xlsx", read_only=True, data_only=True)
    try:
        lines = [str(r[0]) for r in wb["READ ME"].iter_rows(values_only=True) if r and r[0]]
    finally:
        wb.close()
    return {int(m.group(1)): m.group(2) for line in lines if (m := re.match(r"(\d+)\.\s+(.*)", line))}


def test_spec_has_the_same_numbered_rules_as_the_readme(dataset_dir):
    spec_numbers = [int(n) for n in re.findall(r"^\s{0,2}(\d{1,2})\. ", pricing.__doc__, re.MULTILINE)]
    assert spec_numbers == sorted(_readme_rules(dataset_dir)) == list(range(1, 12))


def test_readme_has_no_supplement_or_discount_rule(dataset_dir):
    assert not any(FORBIDDEN.search(rule) for rule in _readme_rules(dataset_dir).values())


def test_pricing_code_has_no_discount_or_supplement_inputs():
    """No function parameter, field or variable in app/pricing/ may introduce such a rule."""
    offenders = []
    for path in PRICING_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = [node.name] + [a.arg for a in node.args.args + node.args.kwonlyargs]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]                       # model fields
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names = [node.id]
            offenders += [f"{path.name}:{getattr(node, 'lineno', '?')} {n}" for n in names if FORBIDDEN.search(n)]
    assert offenders == []
