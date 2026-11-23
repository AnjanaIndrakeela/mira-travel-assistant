"""Prove the supplied dataset is unchanged: SHA-256 of every file vs a committed manifest.

    python -m app.data_loader.integrity           # check against the manifest
    python -m app.data_loader.integrity --write   # (re)create the manifest; only on first setup

Only reads the dataset. The manifest lives in backend/, never in the dataset folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from app.core.config import BACKEND_DIR, get_settings

MANIFEST_PATH = BACKEND_DIR / "dataset_manifest.json"


class IntegrityReport(BaseModel):
    ok: bool
    files_checked: int
    missing: list[str] = []
    changed: list[str] = []
    extra: list[str] = []

    def summary(self) -> str:
        if self.ok:
            return f"Dataset integrity OK ({self.files_checked} files unchanged)"
        return (f"Dataset integrity FAILED: {len(self.changed)} changed, "
                f"{len(self.missing)} missing, {len(self.extra)} extra")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def compute_manifest(dataset_dir: Path) -> dict[str, str]:
    """{relative POSIX path: sha256} for every file in the dataset folder."""
    return {p.relative_to(dataset_dir).as_posix(): _sha256(p)
            for p in sorted(dataset_dir.rglob("*")) if p.is_file()}


def write_manifest(dataset_dir: Path, manifest_path: Path = MANIFEST_PATH) -> int:
    manifest = compute_manifest(dataset_dir)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return len(manifest)


def verify(dataset_dir: Path | None = None, manifest_path: Path = MANIFEST_PATH) -> IntegrityReport:
    dataset_dir = dataset_dir or get_settings().mira_dataset_dir
    expected: dict[str, str] = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = compute_manifest(dataset_dir) if dataset_dir.is_dir() else {}
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(k for k in set(expected) & set(actual) if expected[k] != actual[k])
    return IntegrityReport(ok=not (missing or extra or changed), files_checked=len(expected),
                           missing=missing, changed=changed, extra=extra)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="(re)create the manifest")
    args = parser.parse_args()
    dataset_dir = get_settings().mira_dataset_dir
    if args.write:
        print(f"Wrote {write_manifest(dataset_dir)} files to {MANIFEST_PATH}")
        return 0
    report = verify(dataset_dir)
    print(report.summary())
    for label in ("changed", "missing", "extra"):
        for path in getattr(report, label):
            print(f"  {label}: {path}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
