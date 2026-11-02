"""Single-symbol Yahoo history adapter with explicit error raising."""

import warnings
from datetime import date

from src.calculation.engine import PriceBar
from src.data.providers.yahoo import to_price_bars


def fetch_history_bars(
    symbol: str,
    *,
    start: date,
    end: date,
    ticker_factory=None,
) -> list[PriceBar]:
    """Fetch validated daily OHLCV via Ticker.history.

    start is inclusive; end is exclusive.
    ticker_factory enables fully offline tests.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("A non-empty symbol is required")

    if not isinstance(start, date) or not isinstance(end, date):
        raise ValueError("start and end must be dates")

    if start >= end:
        raise ValueError("start must be earlier than end")

    if ticker_factory is None:
        from yfinance import Ticker
        ticker_factory = Ticker

    symbol = symbol.strip().upper()
    ticker = ticker_factory(symbol)

    # yfinance 1.7.0 supports raise_errors, but deprecates it.
    # Suppress only the specific compatibility warning.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=".*raise_errors.*deprecated.*",
            category=DeprecationWarning,
        )
        frame = ticker.history(
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=True,
            raise_errors=True,
        )

    return to_price_bars(frame)
