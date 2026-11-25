"""python -m app.data_loader [--markdown]: summary of the loaded dataset and its issues."""

import argparse
import sys
from collections import Counter

from app.data_loader import get_dataset
from app.data_loader.issues import issues_to_markdown


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", action="store_true", help="print issues as a Markdown table")
    args = parser.parse_args()
    ds = get_dataset()
    if args.markdown:
        sys.stdout.write(issues_to_markdown(ds.issues))
        return 0
    print(f"Tours with rates: {len(ds.rates.tours)} · hotel rows: {len(ds.rates.hotels)} · "
          f"vehicles: {len(ds.rates.vehicles)}")
    print(f"Content: {len(ds.content.docs)} docs ({len(ds.content.published())} published) · "
          f"starter eval cases: {len(ds.eval_seed)}")
    print(f"Data issues: {len(ds.issues)} {dict(Counter(i.code for i in ds.issues))}")
    for i in ds.issues:
        print(f"- [{i.code}] {i.location}: {i.detail} -> {i.handling}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
