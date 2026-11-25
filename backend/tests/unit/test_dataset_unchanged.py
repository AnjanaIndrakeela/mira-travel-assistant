"""The supplied dataset must be byte-for-byte what we were given."""

import shutil

from app.data_loader.integrity import MANIFEST_PATH, compute_manifest, verify, write_manifest


def test_real_dataset_matches_manifest(dataset_dir):
    report = verify(dataset_dir)
    assert report.ok, report.summary()
    assert report.files_checked == 37


def test_check_detects_a_changed_file(dataset_dir, tmp_path):
    # Work on a copy: the original dataset is never touched.
    copy = tmp_path / "dataset"
    shutil.copytree(dataset_dir, copy)
    manifest = tmp_path / "manifest.json"
    write_manifest(copy, manifest)

    (copy / "rates" / "sample_quotes.md").write_text("tampered", encoding="utf-8")
    (copy / "README.md").unlink()
    (copy / "new.txt").write_text("extra", encoding="utf-8")

    report = verify(copy, manifest)
    assert not report.ok
    assert report.changed == ["rates/sample_quotes.md"]
    assert report.missing == ["README.md"]
    assert report.extra == ["new.txt"]


def test_manifest_paths_are_portable():
    import json
    keys = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert all("\\" not in k for k in keys)  # POSIX paths: same manifest on Windows and Linux


def test_manifest_covers_every_dataset_file(dataset_dir):
    import json
    assert set(json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))) == set(compute_manifest(dataset_dir))
