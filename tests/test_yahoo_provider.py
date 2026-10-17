from datetime import date

import pandas as pd
import pytest

from src.calculation.engine import DataQualityError, PriceBar
from src.data.providers.yahoo import to_price_bars


def sample_frame():
    return pd.DataFrame(
        {
            "Open": [100.0, 102.0],
            "High": [103.0, 105.0],
            "Low": [99.0, 101.0],
            "Close": [102.0, 104.0],
            "Volume": [1000, 1200],
        },
        index=pd.to_datetime(["2026-10-13", "2026-10-14"]),
    )


def test_converts_yahoo_rows_to_price_bars():
    bars = to_price_bars(sample_frame())

    assert len(bars) == 2
    assert isinstance(bars[0], PriceBar)
    assert bars[0].date == date(2026, 10, 13)
    assert bars[-1].close == 104.0
    assert bars[-1].volume == 1200.0


def test_rejects_empty_data():
    with pytest.raises(DataQualityError):
        to_price_bars(pd.DataFrame())


def test_rejects_missing_column():
    frame = sample_frame().drop(columns=["Volume"])
    with pytest.raises(DataQualityError):
        to_price_bars(frame)


def test_rejects_duplicate_dates():
    frame = sample_frame()
    frame.index = pd.to_datetime(["2026-10-14", "2026-10-14"])

    with pytest.raises(DataQualityError):
        to_price_bars(frame)


def test_rejects_unsorted_dates():
    frame = sample_frame().iloc[::-1]

    with pytest.raises(DataQualityError):
        to_price_bars(frame)


def test_rejects_nan():
    frame = sample_frame()
    frame.loc["2026-10-14", "Close"] = float("nan")

    with pytest.raises(DataQualityError):
        to_price_bars(frame)


def test_rejects_negative_volume():
    frame = sample_frame()
    frame.loc["2026-10-14", "Volume"] = -1

    with pytest.raises(DataQualityError):
        to_price_bars(frame)


def test_rejects_inconsistent_ohlc():
    frame = sample_frame()
    frame.loc["2026-10-14", "High"] = 101.0

    with pytest.raises(DataQualityError):
        to_price_bars(frame)


def test_allows_zero_volume():
    frame = sample_frame()
    frame.loc["2026-10-14", "Volume"] = 0

    bars = to_price_bars(frame)
    assert bars[-1].volume == 0.0


def test_rejects_multi_symbol_columns():
    frame = sample_frame()
    frame.columns = pd.MultiIndex.from_product(
        [frame.columns, ["AAPL"]]
    )

    with pytest.raises(DataQualityError):
        to_price_bars(frame)
