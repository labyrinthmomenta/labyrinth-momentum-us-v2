"""SQLite storage for validated US daily price bars."""

from collections.abc import Sequence
from pathlib import Path
import math
import sqlite3

from src.calculation.engine import PriceBar, DataQualityError


def save_bars(
    db_path: str | Path,
    symbol: str,
    bars: Sequence[PriceBar],
) -> int:
    """Atomically upsert validated daily bars.

    Returns the number of submitted bars.
    """
    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Symbol cannot be empty")

    if not bars:
        return 0

    previous = None
    records = []

    for bar in bars:
        if previous is not None and bar.date <= previous:
            raise DataQualityError(
                "Bars must have strictly increasing dates"
            )

        previous = bar.date

        prices = (bar.open, bar.high, bar.low, bar.close)

        if not all(math.isfinite(p) and p > 0 for p in prices):
            raise DataQualityError(
                f"Invalid price on {bar.date}"
            )

        if (
            bar.high < bar.low
            or bar.high < max(bar.open, bar.close)
            or bar.low > min(bar.open, bar.close)
        ):
            raise DataQualityError(
                f"Inconsistent OHLC on {bar.date}"
            )

        if (
            bar.volume is None
            or not math.isfinite(bar.volume)
            or bar.volume < 0
        ):
            raise DataQualityError(
                f"Invalid volume on {bar.date}"
            )

        records.append((
            symbol,
            bar.date.isoformat(),
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
        ))

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO daily_bars (
                symbol, session_date,
                open, high, low, close, volume
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, session_date)
            DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume
            """,
            records,
        )
        conn.commit()

    return len(records)


def load_bars(
    db_path: str | Path,
    symbol: str,
) -> list[PriceBar]:
    """Load stored daily bars in ascending session order."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT session_date, open, high, low, close, volume
            FROM daily_bars
            WHERE symbol = ?
            ORDER BY session_date
            """,
            (symbol.strip().upper(),),
        ).fetchall()

    from datetime import date

    return [
        PriceBar(
            date=date.fromisoformat(row[0]),
            open=row[1],
            high=row[2],
            low=row[3],
            close=row[4],
            volume=row[5],
        )
        for row in rows
    ]


def replace_history(
    db_path: str | Path,
    symbol: str,
    bars: Sequence[PriceBar],
) -> int:
    """Atomically replace one symbol's complete stored history.

    Caller must supply the complete, independently validated
    history for the intended coverage period.
    """
    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Symbol cannot be empty")

    if not bars:
        raise DataQualityError("Cannot replace history with empty bars")

    import math

    records = []
    previous = None

    for bar in bars:
        if previous is not None and bar.date <= previous:
            raise DataQualityError(
                "Bars must have strictly increasing dates"
            )

        previous = bar.date

        prices = (bar.open, bar.high, bar.low, bar.close)

        if not all(math.isfinite(v) and v > 0 for v in prices):
            raise DataQualityError(
                f"Invalid price on {bar.date}"
            )

        if (
            bar.high < bar.low
            or bar.high < max(bar.open, bar.close)
            or bar.low > min(bar.open, bar.close)
        ):
            raise DataQualityError(
                f"Inconsistent OHLC on {bar.date}"
            )

        if (
            bar.volume is None
            or not math.isfinite(bar.volume)
            or bar.volume < 0
        ):
            raise DataQualityError(
                f"Invalid volume on {bar.date}"
            )

        records.append((
            symbol,
            bar.date.isoformat(),
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
        ))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM daily_bars WHERE symbol = ?",
            (symbol,),
        )

        conn.executemany(
            """
            INSERT INTO daily_bars (
                symbol, session_date,
                open, high, low, close, volume
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )

        conn.commit()

    return len(records)
