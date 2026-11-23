"""Terminal chat with Mira (step 8.14).

    python -m app.graph.cli                       # interactive; empty line or "quit" ends
    python -m app.graph.cli --say "Hi" --say "..."  # scripted turns, then exit
    python -m app.graph.cli --debug               # also print intent, action, flags, state
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from app.graph.build import get_graph
from app.graph.tracing import get_langfuse, run_turn


def show(result: dict, debug: bool) -> None:
    print(f"\nMira: {result['response']}")
    for c in result.get("ui") or []:
        if c["type"] == "quote_card":
            q = c["quote"]
            print(f"  [quote] {q['tour_id']} {q['start_date']} price USD {q['price_usd']:,}, "
                  f"deposit USD {q['deposit_usd']:,}")
        elif c["type"] == "tour_cards":
            print("  [tours] " + ", ".join(f"{t['tour_id']} {t['name']}" for t in c["tours"]))
        elif c["type"] == "sources":
            print("  [sources] " + "; ".join(f"[{s['n']}] {s['title']} – {s['section']}" for s in c["items"]))
        else:
            print(f"  [{c['type']}] {c.get('reason', '')}")
    if debug:
        keys = ("intent", "action", "flags", "input_flags", "selected_tour_id", "start_date", "party",
                "traveller_type", "trip_type", "questions_asked", "abstain_reason", "trace_id")
        print("  " + json.dumps({k: result.get(k) for k in keys}, default=str))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Chat with Mira in the terminal")
    p.add_argument("--say", action="append", help="a message to send (repeatable); no prompt")
    p.add_argument("--thread", default=None, help="conversation ID (default: a new one)")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8")
    graph, thread = get_graph(), args.thread or f"cli-{uuid.uuid4().hex[:8]}"
    lf = get_langfuse()
    print(f"Mira terminal chat. Conversation {thread}. Tracing {'on' if lf else 'off'}.")
    messages = iter(args.say) if args.say else None
    while True:
        if messages is not None:
            text = next(messages, None)
            if text is None:
                break
            print(f"\nYou: {text}")
        else:
            try:
                text = input("\nYou: ").strip()
            except EOFError:
                break
            if not text or text.lower() in {"quit", "exit"}:
                break
        show(run_turn(graph, thread, text, langfuse=lf, flush=True), args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
