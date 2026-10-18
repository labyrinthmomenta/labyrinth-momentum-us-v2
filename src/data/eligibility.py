"""US equity price and dollar-liquidity eligibility filter."""

from dataclasses import dataclass
from datetime import date
import math
from collections.abc import Sequence

from src.calculation.engine import PriceBar, DataQualityError
from src.data.providers.sessions import validate_recent_sessions


@dataclass(frozen=True)
class EligibilityResult:
    status: str
    last_close: float | None
    adv90_usd: float | None
    reason: str


def check_eligibility(
    bars: Sequence[PriceBar],
    *,
    as_of: date,
    min_price: float = 5.0,
    min_adv90_usd: float = 1_000_000.0,
) -> EligibilityResult:
    """Evaluate completed-session close and 90-session ADV."""
    try:
        validate_recent_sessions(
            bars,
            as_of=as_of,
            required_sessions=90,
        )

        eligible = [bar for bar in bars if bar.date <= as_of]
        recent = eligible[-90:]

        if len(recent) != 90 or recent[-1].date != as_of:
            raise DataQualityError("Incomplete 90-session window")

        last_close = recent[-1].close
        dollar_values = [
            bar.close * bar.volume for bar in recent
        ]

        if not all(math.isfinite(v) for v in dollar_values):
            raise DataQualityError("Non-finite dollar volume")

        adv90 = sum(dollar_values) / 90

    except (DataQualityError, ValueError) as exc:
        return EligibilityResult(
            status="DATA_INCOMPLETE",
            last_close=None,
            adv90_usd=None,
            reason=str(exc),
        )

    if last_close > min_price and adv90 > min_adv90_usd:
        status = "PASS"
        reason = "Price and ADV90 thresholds met"
    else:
        status = "FILTER_FAIL"
        reason = "Price or ADV90 threshold not met"

    return EligibilityResult(
        status=status,
        last_close=last_close,
        adv90_usd=adv90,
        reason=reason,
    )
