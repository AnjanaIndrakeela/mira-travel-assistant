"""Write the evaluation report (step 14.4): Markdown for people, JSON for tools.

evaluation/reports/evaluation_report.md (+ .json): targets vs actual, pass rate per
requirement and per check, dataset integrity, Gemini fallbacks, and every failing case with its
replies and Langfuse trace links. A partial run (--case / --category) writes
evaluation_report_partial.md instead, so it never overwrites the full report.
"""

from __future__ import annotations

import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evaluation.cases import COVERAGE_TAGS, REQUIREMENT_ORDER

REPORTS = Path(__file__).resolve().parent / "reports"
SRI_LANKA = timezone(timedelta(hours=5, minutes=30))


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a"


def _check(r: dict, name: str):
    return next((c for c in r["checks"] if c.name == name), None)


def _cell(s: str, n: int = 160) -> str:
    s = " ".join(str(s).split()).replace("|", "\\|")
    return s if len(s) <= n else s[: n - 1] + "…"


def _targets(results: list[dict]) -> list[tuple[str, str, str, bool]]:
    def rate(name, pick=lambda r: True):
        rows = [c for r in results if pick(r) and (c := _check(r, name))]
        return sum(c.passed for c in rows), len(rows)

    def fails(name):
        return sum(1 for r in results if (c := _check(r, name)) and not c.passed)

    quote_ok, quote_n = rate("price_exact")
    rever_ok, rever_n = rate("price_reverified")
    flag_cases = [r for r in results if r["case"].kind == "flag_no_price"]
    flag_ok = sum(all(c.passed for c in r["checks"] if c.name in ("no_price_when_flagged", "flag_saved"))
                  for r in flag_cases)
    ui_ok, ui_n = rate("ui_valid")
    q_ok, q_n = rate("questions_le_3")
    return [
        ("Price accuracy (exact price and deposit)", "100%", _pct(quote_ok, quote_n), quote_ok == quote_n),
        ("Quotes equal to the engine re-run", "100%", _pct(rever_ok, rever_n), rever_ok == rever_n),
        ("Invented amounts (cases with one)", "0", str(fails("no_invented_amount")), fails("no_invented_amount") == 0),
        ("Missing / expired rate handled (no price + flag saved)", "100%", _pct(flag_ok, len(flag_cases)),
         flag_ok == len(flag_cases)),
        ("Cost / margin / GP% leaks", "0", str(fails("no_cost_leak")), fails("no_cost_leak") == 0),
        ("Draft or unpublished docs retrieved", "0", str(fails("no_draft_retrieved")), fails("no_draft_retrieved") == 0),
        ("UI payloads valid", "100%", _pct(ui_ok, ui_n), ui_ok == ui_n),
        ("At most 3 questions", "100%", _pct(q_ok, q_n), q_ok == q_n),
    ]


def _environment() -> dict:
    from app.core.config import get_settings
    from app.data_loader.integrity import verify
    s = get_settings()
    integrity = verify()
    return {"mira_today": str(s.mira_today), "model_fast": s.gemini_model_fast, "model_strong": s.gemini_model_strong,
            "model_backup": s.gemini_model_backup, "embedding": s.gemini_embedding_model,
            "tracing": s.tracing_enabled, "integrity_ok": integrity.ok, "integrity": integrity.summary(),
            "git_commit": os.environ.get("MIRA_GIT_COMMIT", "")}


def build_markdown(results: list[dict], *, started: float, env: dict, title: str) -> str:
    n, passed = len(results), sum(r["passed"] for r in results)
    turns = [t for r in results for t in r["run"].turns]
    fallback = sum(t.llm_unavailable for t in turns)
    judged = [r["run"].judge for r in results if r["run"].judge]
    j_ok = sum(1 for j in judged if j.get("passed") is True)
    j_na = sum(1 for j in judged if j.get("passed") is None)
    when = datetime.fromtimestamp(started, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [f"# {title}", "",
           f"Run {when} · `MIRA_TODAY={env['mira_today']}` · models `{env['model_fast']}` (fast), "
           f"`{env['model_strong']}` (strong), `{env['model_backup']}` (backup)"
           + (f" · commit `{env['git_commit']}`" if env["git_commit"] else ""), "",
           f"**{passed}/{n} cases passed** ({100 * passed / max(n, 1):.0f}%) · {len(turns)} turns · "
           f"{sum(r['case'].multi_turn for r in results)} multi-turn cases · "
           f"average {sum(t.seconds for t in turns) / max(len(turns), 1):.1f} s per turn", "",
           f"- **Dataset integrity:** {'OK' if env['integrity_ok'] else 'CHANGED'}. {env['integrity']}",
           f"- **Gemini fallbacks:** {fallback} of {len(turns)} turns were read by the code rules because every "
           "Gemini model failed (quota, overload or timeout). Those turns still count.",
           f"- **LLM judge:** {len(judged)} cases have a behaviour rubric; the judge passed {j_ok}, failed "
           f"{len(judged) - j_ok - j_na}" + (f", and was unavailable for {j_na} (not counted)" if j_na else "")
           + ". Code checks decide prices, flags and leaks; the judge grades wording only.",
           "", "## Targets vs actual", "", "| Measure | Target | Actual | |", "|---|---|---|---|"]
    out += [f"| {m} | {t} | {a} | {'✅' if ok else '❌'} |" for m, t, a, ok in _targets(results)]

    out += ["", "## Pass rate per requirement", "", "| Requirement | Cases | Passed | Rate |", "|---|---|---|---|"]
    by_req = defaultdict(list)
    for r in results:
        by_req[r["case"].requirement].append(r)
    for req in sorted(by_req, key=lambda k: (REQUIREMENT_ORDER.index(k) if k in REQUIREMENT_ORDER else 99, k)):
        rs = by_req[req]
        ok = sum(r["passed"] for r in rs)
        out.append(f"| {req} | {len(rs)} | {ok} | {_pct(ok, len(rs))} |")

    out += ["", "## Coverage", "", "| Tag | Cases | Passed |", "|---|---|---|"]
    for tag in COVERAGE_TAGS:
        rs = [r for r in results if tag in r["case"].all_tags]
        out.append(f"| {tag} | {len(rs)} | {sum(r['passed'] for r in rs)} |" + ("" if rs else " ❌ no case"))

    out += _calibration_section()
    out += ["", "## Pass rate per check", "", "| Check | Applies to | Passed | Rate |", "|---|---|---|---|"]
    by_check = defaultdict(list)
    for r in results:
        for c in r["checks"]:
            by_check[c.name].append(c.passed)
    for name, vals in by_check.items():
        out.append(f"| `{name}` | {len(vals)} | {sum(vals)} | {_pct(sum(vals), len(vals))} |")

    failing = [r for r in results if not r["passed"]]
    out += ["", f"## Failing cases ({len(failing)})", ""]
    if not failing:
        out.append("None.")
    for r in failing:
        c = r["case"]
        out += [f"### {c.id} · {c.requirement} · {c.kind}", ""]
        if c.note:
            out.append(f"_{c.note}_  ")
        if exp := c.expected.get("behaviour"):
            out.append(f"Expected: {exp}  ")
        out += [f"- ❌ **{x.name}**: {_cell(x.detail, 400)}" for x in r["checks"] if not x.passed]
        out.append("")
        for i, t in enumerate(r["run"].turns, 1):
            trace = f"[trace]({t.trace_url})" if t.trace_url else (f"trace `{t.trace_id}`" if t.trace_id else "no trace")
            extra = " · Gemini down, rules used" if t.llm_unavailable else ""
            out += [f"{i}. **Traveller:** {_cell(t.message, 300)}",
                    f"   **Mira** ({t.action}, {t.seconds:.1f} s{extra}, {trace}): {_cell(t.response, 500)}"]
        out.append("")

    out += ["## All cases", "", "| Case | Req | Type | Turns | Result | Time | Failed checks |", "|---|---|---|---|---|---|---|"]
    for r in results:
        c = r["case"]
        secs = sum(t.seconds for t in r["run"].turns)
        failed = ", ".join(x.name for x in r["checks"] if not x.passed)
        out.append(f"| {c.id} | {c.requirement} | {c.kind} | {len(c.turns)} | {'✅' if r['passed'] else '❌'} | "
                   f"{secs:.1f} s | {failed} |")
    out += ["", "Generated by `python -m evaluation.runner`. Quotes and enquiries from this run are saved under "
            "the fixed eval visitor, so they show in the staff console like real chats.", ""]
    return "\n".join(out)


def _calibration_section() -> list[str]:
    from evaluation.judge import CALIBRATION
    if not CALIBRATION.exists():
        return ["", "## Judge calibration", "", "Not run yet: `python -m evaluation.judge --calibrate`."]
    c = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    out = ["", "## Judge calibration", "",
           f"The judge agreed with the hand labels on **{c['agree']}/{c['judged']} answers "
           f"({c['agreement_pct']}%)** (labels in `test_cases/human_labels.jsonl`, labelled by: "
           f"{', '.join(c['labeller'])})."]
    diffs = [r for r in c["rows"] if r["agree"] is False]
    if diffs:
        out += ["", "| Label | Human | Judge | Judge's reason |", "|---|---|---|---|"]
        out += [f"| {r['id']} | {r['human']} | {r['judge']} | {_cell(r['reason'], 220)} |" for r in diffs]
    return out


def build_json(results: list[dict], *, started: float, env: dict) -> dict:
    return {"started": started, "environment": env,
            "summary": {"cases": len(results), "passed": sum(r["passed"] for r in results)},
            "targets": [{"measure": m, "target": t, "actual": a, "met": ok} for m, t, a, ok in _targets(results)],
            "coverage": {tag: [r["case"].id for r in results if tag in r["case"].all_tags] for tag in COVERAGE_TAGS},
            "cases": [{"id": r["case"].id, "requirement": r["case"].requirement, "type": r["case"].kind,
                       "passed": r["passed"],
                       "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in r["checks"]],
                       **r["run"].to_dict()} for r in results]}


def write_reports(results: list[dict], *, started: float, name: str | None = None, baseline: bool = False,
                  partial: bool = False) -> list[Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    env = _environment()
    name = name or ("evaluation_report_partial" if partial else "evaluation_report")
    title = "Mira evaluation report" + (" (partial run)" if partial else "")
    md, js = REPORTS / f"{name}.md", REPORTS / f"{name}.json"
    md.write_text(build_markdown(results, started=started, env=env, title=title), encoding="utf-8")
    js.write_text(json.dumps(build_json(results, started=started, env=env), indent=1, default=str), encoding="utf-8")
    paths = [md, js]
    if baseline:
        day = datetime.fromtimestamp(started, tz=SRI_LANKA).strftime("%Y-%m-%d")   # the team's date
        for src, ext in ((md, "md"), (js, "json")):
            dst = REPORTS / f"baseline_{day}.{ext}"
            shutil.copyfile(src, dst)
            paths.append(dst)
    return paths
