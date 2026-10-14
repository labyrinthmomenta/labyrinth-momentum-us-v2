import hashlib
import json
import sys
from pathlib import Path

from src.data.universe.review import main


def capture(tmp_path, source, payload):
    path = tmp_path / f"{source}.txt"
    path.write_bytes(payload)
    meta = {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
            "retrieved_at": "2026-10-14T12:00:00+00:00", "synthetic": True}
    (tmp_path / f"{source}.json").write_text(json.dumps(meta))


def test_html_rejection_leaves_no_success_csv(tmp_path, monkeypatch):
    for source in ("nasdaqlisted", "otherlisted"):
        capture(tmp_path, source, b"<html>not a directory</html>")
    output = tmp_path / "rejected"
    monkeypatch.setattr(sys, "argv", ["review", "--raw-dir", str(tmp_path), "--output", str(output)])
    assert main() == 2
    report = json.loads((output / "review.json").read_text())
    assert report["status"] == "SOURCE_REJECTED"
    assert report["counts"] is None
    assert not (output / "review.csv").exists()


def test_fixture_review_is_complete_and_remains_provisional(tmp_path, monkeypatch):
    for source in ("nasdaqlisted", "otherlisted"):
        path = Path(__file__).parent / "fixtures" / "universe" / f"{source}.txt"
        capture(tmp_path, source, path.read_bytes())
    output = tmp_path / "review"
    monkeypatch.setattr(sys, "argv", ["review", "--raw-dir", str(tmp_path), "--output", str(output)])
    assert main() == 0
    report = json.loads((output / "review.json").read_text())
    assert report["status"] == "REVIEW_ONLY"
    assert report["total"] == sum(report["counts"].values()) == 9
    assert not report["production_eligible"]
    assert (output / "review.csv").exists()
