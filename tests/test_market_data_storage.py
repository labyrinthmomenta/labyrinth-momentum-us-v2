from datetime import date, timedelta
import sqlite3

import pytest

from src.calculation.engine import DataQualityError, PriceBar
from src.data.storage.market_data import save_bars, load_bars


def create_database(path):
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE daily_bars (
                symbol TEXT NOT NULL,
                session_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY (symbol, session_date)
            )
        """)


def make_bar(day, close=100.0, volume=1000.0):
    return PriceBar(
        date=day,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=volume,
    )


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "market_data.db"
    create_database(path)
    return path


def test_save_and_load_bars(database):
    bars = [
        make_bar(date(2026, 10, 13)),
        make_bar(date(2026, 10, 14), close=105),
    ]

    assert save_bars(database, "AAPL", bars) == 2
    assert load_bars(database, "AAPL") == bars


def test_repeat_save_does_not_duplicate(database):
    bar = make_bar(date(2026, 10, 14))

    save_bars(database, "AAPL", [bar])
    save_bars(database, "AAPL", [bar])

    assert len(load_bars(database, "AAPL")) == 1


def test_upsert_updates_existing_bar(database):
    day = date(2026, 10, 14)

    save_bars(database, "AAPL", [make_bar(day, close=100)])
    save_bars(database, "AAPL", [make_bar(day, close=110)])

    stored = load_bars(database, "AAPL")

    assert len(stored) == 1
    assert stored[0].close == 110


def test_symbol_normalization(database):
    bar = make_bar(date(2026, 10, 14))

    save_bars(database, "aapl", [bar])

    assert load_bars(database, "AAPL") == [bar]
    assert load_bars(database, "aapl") == [bar]


def test_invalid_volume_is_rejected(database):
    bar = make_bar(date(2026, 10, 14), volume=-1)

    with pytest.raises(DataQualityError):
        save_bars(database, "AAPL", [bar])

    assert load_bars(database, "AAPL") == []


def test_duplicate_dates_are_rejected(database):
    bar = make_bar(date(2026, 10, 14))

    with pytest.raises(DataQualityError):
        save_bars(database, "AAPL", [bar, bar])

    assert load_bars(database, "AAPL") == []


def test_unsorted_dates_are_rejected(database):
    bars = [
        make_bar(date(2026, 10, 14)),
        make_bar(date(2026, 10, 13)),
    ]

    with pytest.raises(DataQualityError):
        save_bars(database, "AAPL", bars)


def test_empty_input_does_not_write(database):
    assert save_bars(database, "AAPL", []) == 0
    assert load_bars(database, "AAPL") == []


def test_failed_batch_preserves_previous_data(database):
    existing = make_bar(date(2026, 10, 12))
    save_bars(database, "AAPL", [existing])

    bars = [
        make_bar(date(2026, 10, 13)),
        make_bar(date(2026, 10, 14), volume=-1),
    ]

    with pytest.raises(DataQualityError):
        save_bars(database, "AAPL", bars)

    assert load_bars(database, "AAPL") == [existing]


def test_nan_close_is_rejected(database):
    bar = PriceBar(
        date=date(2026, 10, 14),
        open=100,
        high=101,
        low=99,
        close=float("nan"),
        volume=1000,
    )

    with pytest.raises(DataQualityError, match="Invalid price"):
        save_bars(database, "AAPL", [bar])

    assert load_bars(database, "AAPL") == []


def test_infinite_volume_is_rejected(database):
    bar = make_bar(
        date(2026, 10, 14),
        volume=float("inf"),
    )

    with pytest.raises(DataQualityError, match="Invalid volume"):
        save_bars(database, "AAPL", [bar])


def test_inconsistent_ohlc_is_rejected(database):
    bar = PriceBar(
        date=date(2026, 10, 14),
        open=100,
        high=99,
        low=98,
        close=101,
        volume=1000,
    )

    with pytest.raises(DataQualityError, match="Inconsistent OHLC"):
        save_bars(database, "AAPL", [bar])


def test_replace_history_updates_all_rows(database):
    from src.data.storage.market_data import replace_history

    old = [
        make_bar(date(2026, 10, 12), close=100),
        make_bar(date(2026, 10, 13), close=102),
    ]
    save_bars(database, "AAPL", old)

    new = [
        make_bar(date(2026, 10, 12), close=50),
        make_bar(date(2026, 10, 13), close=51),
        make_bar(date(2026, 10, 14), close=52),
    ]

    assert replace_history(database, "AAPL", new) == 3
    assert load_bars(database, "AAPL") == new


def test_replace_history_preserves_other_symbols(database):
    from src.data.storage.market_data import replace_history

    nvda = make_bar(date(2026, 10, 14), close=200)
    save_bars(database, "NVDA", [nvda])
    save_bars(
        database,
        "AAPL",
        [make_bar(date(2026, 10, 13))],
    )

    replace_history(
        database,
        "AAPL",
        [
            make_bar(date(2026, 10, 13), close=100),
            make_bar(date(2026, 10, 14), close=110),
        ],
    )

    assert load_bars(database, "NVDA") == [nvda]


def test_replace_history_rejects_invalid_without_deleting(database):
    from src.data.storage.market_data import replace_history

    original = make_bar(date(2026, 10, 12))
    save_bars(database, "AAPL", [original])

    invalid = [
        make_bar(date(2026, 10, 13)),
        make_bar(date(2026, 10, 14), volume=-1),
    ]

    with pytest.raises(DataQualityError):
        replace_history(database, "AAPL", invalid)

    assert load_bars(database, "AAPL") == [original]


def test_replace_history_rejects_empty(database):
    from src.data.storage.market_data import replace_history

    original = make_bar(date(2026, 10, 14))
    save_bars(database, "AAPL", [original])

    with pytest.raises(DataQualityError):
        replace_history(database, "AAPL", [])

    assert load_bars(database, "AAPL") == [original]


def test_replace_rejects_shorter_history(database):
    from src.data.storage.market_data import replace_history

    original = [
        make_bar(date(2026, 10, 12), close=100),
        make_bar(date(2026, 10, 13), close=102),
        make_bar(date(2026, 10, 14), close=104),
    ]

    save_bars(database, "AAPL", original)

    shorter = [
        make_bar(date(2026, 10, 13), close=51),
        make_bar(date(2026, 10, 14), close=52),
    ]

    with pytest.raises(DataQualityError, match="remove"):
        replace_history(database, "AAPL", shorter)

    assert load_bars(database, "AAPL") == original


def test_replace_rejects_missing_middle_session(database):
    from src.data.storage.market_data import replace_history

    original = [
        make_bar(date(2026, 10, 12)),
        make_bar(date(2026, 10, 13)),
        make_bar(date(2026, 10, 14)),
    ]

    save_bars(database, "AAPL", original)

    incoming = [
        make_bar(date(2026, 10, 12), close=50),
        make_bar(date(2026, 10, 14), close=52),
    ]

    with pytest.raises(DataQualityError, match="remove"):
        replace_history(database, "AAPL", incoming)

    assert load_bars(database, "AAPL") == original


def test_replace_accepts_extended_history(database):
    from src.data.storage.market_data import replace_history

    save_bars(
        database,
        "AAPL",
        [make_bar(date(2026, 10, 13), close=100)],
    )

    incoming = [
        make_bar(date(2026, 10, 12), close=49),
        make_bar(date(2026, 10, 13), close=50),
        make_bar(date(2026, 10, 14), close=51),
    ]

    assert replace_history(database, "AAPL", incoming) == 3
    assert load_bars(database, "AAPL") == incoming
