from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.data.universe.directory import DirectoryError, parse_directory, review_pair

FIXTURES = Path(__file__).parent / "fixtures" / "universe"
NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


def raw(source="nasdaqlisted"):
    return (FIXTURES / f"{source}.txt").read_bytes()


def parse(payload=None, source="nasdaqlisted", now=NOW):
    return parse_directory(raw(source) if payload is None else payload, source, retrieved_at=now)


def test_pair_review_covers_every_record_without_production_eligibility():
    report = review_pair(parse(), parse(source="otherlisted"))
    assert report["total"] == 9
    assert report["counts"] == {"INCLUDE": 3, "EXCLUDE": 4, "REVIEW_REQUIRED": 2}
    assert not any(r["production_eligible"] for r in report["rows"])
    assert next(r for r in report["rows"] if r["symbol"] == "SPCZ")["decision"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("payload", [
    b"<html>access denied</html>", b"", raw().replace(b"File Creation Time:", b"Unknown footer:"),
    raw().replace(b"1013202617:00", b"1001202617:00"),
    raw().replace(b"1013202617:00", b"1015202617:00"),
    raw().replace(b"1013202617:00", b"1332202617:00"),
    raw().replace(b"ALFB|", b"ALFA|"),
    raw().replace(b"|Q|N|N|100|N|N", b"|Q|N|N|100|X|N"),
    raw().replace(b"|Q|N|N|100|N|N", b"|Q|N|N|100|N"),
    raw().replace(b"|100|", b"|0|"),
    raw().replace(b"|Q|", b"|X|"),
    raw().replace(b"Symbol|", b"Ticker|", 1),
])
def test_bad_source_is_rejected(payload):
    with pytest.raises(DirectoryError):
        parse(payload)


def test_naive_capture_time_rejected():
    with pytest.raises(DirectoryError):
        parse(now=NOW.replace(tzinfo=None))


def test_mismatched_source_dates_fail():
    other = parse(raw("otherlisted").replace(b"10132026", b"10122026"), "otherlisted")
    with pytest.raises(DirectoryError):
        review_pair(parse(), other)


def test_cross_source_collision_does_not_merge():
    other = parse(raw("otherlisted").replace(b"REITZ", b"ALFA"), "otherlisted")
    report = review_pair(parse(), other)
    matches = [r for r in report["rows"] if r["symbol"] == "ALFA"]
    assert len(matches) == 2
    assert all(r["reason"] == "CROSS_SOURCE_SYMBOL_COLLISION" for r in matches)
