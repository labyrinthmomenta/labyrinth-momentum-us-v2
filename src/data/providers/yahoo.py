"""Convert Yahoo Finance split-adjusted daily OHLCV to PriceBar.

Input contract:
- A single-symbol pandas DataFrame
- Date/DatetimeIndex
- Open, High, Low, Close, Volume columns
- auto_adjust=False when downloading from yfinance
- Yahoo Close/Volume are on a consistent split-adjusted basis

No network calls are made by this module.
"""

from datetime import date
import math

from src.calculation.engine import DataQualityError, PriceBar


_REQUIRED = ("Open", "High", "Low", "Close", "Volume")


def to_price_bars(frame) -> list[PriceBar]:
    """Validate and convert a single-symbol Yahoo daily DataFrame."""
    if frame is None or frame.empty:
        raise DataQualityError("Yahoo OHLCV data is empty")

    if getattr(frame.columns, "nlevels", 1) != 1:
        raise DataQualityError(
            "Expected single-symbol, flat OHLCV columns"
        )

    missing = [name for name in _REQUIRED if name not in frame.columns]
    if missing:
        raise DataQualityError(f"Missing Yahoo columns: {missing}")

    if not frame.index.is_monotonic_increasing:
        raise DataQualityError("Yahoo dates must be increasing")

    if frame.index.has_duplicates:
        raise DataQualityError("Duplicate Yahoo dates")

    bars = []

    for timestamp, row in frame.iterrows():
        try:
            session = timestamp.date()
        except AttributeError as exc:
            raise DataQualityError("Invalid Yahoo date index") from exc

        if not isinstance(session, date):
            raise DataQualityError("Invalid Yahoo session date")

        values = {}

        for field in _REQUIRED:
            try:
                value = float(row[field])
            except (TypeError, ValueError) as exc:
                raise DataQualityError(
                    f"Invalid {field} on {session}"
                ) from exc

            if not math.isfinite(value):
                raise DataQualityError(
                    f"Non-finite {field} on {session}"
                )

            values[field] = value

        prices = [values[k] for k in ("Open", "High", "Low", "Close")]

        if any(price <= 0 for price in prices):
            raise DataQualityError(
                f"Non-positive price on {session}"
            )

        if values["Volume"] < 0:
            raise DataQualityError(
                f"Negative volume on {session}"
            )

        if (
            values["High"] < max(values["Open"], values["Close"])
            or values["Low"] > min(values["Open"], values["Close"])
            or values["High"] < values["Low"]
        ):
            raise DataQualityError(
                f"Inconsistent OHLC on {session}"
            )

        bars.append(
            PriceBar(
                date=session,
                open=values["Open"],
                high=values["High"],
                low=values["Low"],
                close=values["Close"],
                volume=values["Volume"],
            )
        )

    return bars


def fetch_price_bars(
    symbol: str,
    *,
    start: date,
    end: date,
    downloader=None,
) -> list[PriceBar]:
    """Download daily Yahoo prices and return validated PriceBar objects.

    start is inclusive; end is exclusive.
    A downloader may be injected for offline unit testing.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("A non-empty symbol is required")

    if not isinstance(start, date) or not isinstance(end, date):
        raise ValueError("start and end must be dates")

    if start >= end:
        raise ValueError("start must be earlier than end")

    if downloader is None:
        import yfinance as yf
        downloader = yf.download

    symbol = symbol.strip().upper()

    try:
        frame = downloader(
            symbol,
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=True,
            progress=False,
            threads=False,
        )
    except Exception as exc:
        raise DataQualityError(
            f"Yahoo download failed for {symbol}"
        ) from exc

    if frame is None or frame.empty:
        raise DataQualityError(
            f"Yahoo returned no data for {symbol}"
        )

    if getattr(frame.columns, "nlevels", 1) > 1:
        if "Ticker" not in frame.columns.names:
            raise DataQualityError(
                "Unexpected Yahoo column structure"
            )
        try:
            frame = frame.xs(
                symbol,
                axis=1,
                level="Ticker",
            )
        except KeyError as exc:
            raise DataQualityError(
                f"Yahoo result missing ticker {symbol}"
            ) from exc

    return to_price_bars(frame)
