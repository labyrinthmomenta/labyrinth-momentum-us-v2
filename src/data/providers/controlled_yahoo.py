"""Controlled Yahoo data-fetch adapter for US ingestion."""

from collections.abc import Callable
from datetime import date

from src.calculation.engine import PriceBar
from src.data.providers.controlled_fetch import (
    FetchPolicy,
    fetch_with_retry,
)
from src.data.providers.request_pacer import RequestPacer
from src.data.providers.yahoo import fetch_price_bars


def make_controlled_yahoo_fetcher(
    *,
    start: date,
    end: date,
    pacer: RequestPacer | None = None,
    policy: FetchPolicy | None = None,
    provider: Callable[..., list[PriceBar]] = fetch_price_bars,
) -> Callable[[str], list[PriceBar]]:
    """Create a reusable, paced and retry-bounded Yahoo fetcher.

    One shared pacer instance is retained across symbol calls.
    The provider can be replaced in offline tests.
    """
    if not isinstance(start, date) or not isinstance(end, date):
        raise ValueError("start and end must be dates")

    if start >= end:
        raise ValueError("start must be earlier than end")

    if pacer is None:
        pacer = RequestPacer()

    if policy is None:
        policy = FetchPolicy()

    def fetch(symbol: str) -> list[PriceBar]:
        return fetch_with_retry(
            lambda: provider(symbol, start=start, end=end),
            policy=policy,
            pacer=pacer,
        )

    return fetch
