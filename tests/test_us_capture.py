from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.data.universe.capture import capture_pair, URLS, NoRedirect
from src.data.universe.directory import DirectoryError, classify, parse_directory

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent / "fixtures" / "universe"


def fixture_fetch(url):
    source = next(k for k, v in URLS.items() if v == url)
    return (FIXTURES / f"{source}.txt").read_bytes()


def test_pair_capture_validates_and_preserves_receipts(tmp_path):
    folder = tmp_path / "run"
    result = capture_pair(folder, fetcher=fixture_fetch, clock=lambda: NOW)
    assert result["status"] == "CAPTURE_VALIDATED"
    assert len(result["receipts"]) == 2
    assert not result["production_eligible"]
    with pytest.raises(FileExistsError):
        capture_pair(folder, fetcher=fixture_fetch, clock=lambda: NOW)


def test_partial_capture_cannot_pass(tmp_path):
    def fetcher(url):
        if url == URLS["otherlisted"]:
            raise OSError("Timeout")
        return fixture_fetch(url)
    result = capture_pair(tmp_path / "run", fetcher=fetcher, clock=lambda: NOW)
    assert result["status"] == "SOURCE_REJECTED"
    assert len(result["receipts"]) == 1
    assert result["errors"][0]["source"] == "otherlisted"


def test_html_is_preserved_but_rejected(tmp_path):
    result = capture_pair(tmp_path / "run", fetcher=lambda url: b"<html>challenge</html>", clock=lambda: NOW)
    assert result["status"] == "SOURCE_REJECTED"
    assert len(result["receipts"]) == len(result["errors"]) == 2


def test_redirect_requires_source_review():
    with pytest.raises(DirectoryError):
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example")


def test_observed_official_otherlisted_footer_width():
    payload = fixture_fetch(URLS["otherlisted"]).replace(b"17:00|||||||", b"17:00||||||")
    assert len(parse_directory(payload, "otherlisted", retrieved_at=NOW).rows) == 4
    for bad in (b"17:00|||||", b"17:00||||||X"):
        with pytest.raises(DirectoryError):
            parse_directory(payload.replace(b"17:00||||||", bad), "otherlisted", retrieved_at=NOW)


@pytest.mark.parametrize("name,decision,reason", [
    ("Example - Common Stock When Issued", "EXCLUDE", "WHEN_ISSUED_OR_DISTRIBUTED"),
    ("Example - Common Stock when-distributed", "EXCLUDE", "WHEN_ISSUED_OR_DISTRIBUTED"),
    ("Example - ADRs representing one common share.", "EXCLUDE", "DEPOSITARY_RECEIPT_NAME"),
    ("Example - ADSs", "EXCLUDE", "DEPOSITARY_RECEIPT_NAME"),
    ("Example - Common Share", "INCLUDE", "EXPLICIT_COMMON_NAME_CANDIDATE"),
    ("Example - Class C Capital Stock", "REVIEW_REQUIRED", "TYPE_UNCONFIRMED"),
])
def test_observed_name_forms(name, decision, reason):
    row = {"Symbol": "EXAMPLE", "Security Name": name, "ETF": "N", "NextShares": "N", "Test Issue": "N", "Financial Status": "N"}
    result = classify(row, "nasdaqlisted")
    assert (result["decision"], result["reason"]) == (decision, reason)
    assert not result["production_eligible"]
