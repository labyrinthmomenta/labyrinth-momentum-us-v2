"""A6b: US-only, provider-neutral CLOSED session OHLCV input quality.

Source receipts/calendar approval/security master are external obligations.
This module establishes only the *mechanics* and never approves a stock
for production. The liquidity rule is 90 completed session mean(close
USD * shares traded) strictly > 1,000,000 and last close strictly > $5.
No live price provider, adjustment, database, or publisher is connected.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
from typing import Sequence
from zoneinfo import ZoneInfo

from src.calculation.engine import PriceBar, compute_snapshot

USD = "USD"
ALLOWED_MICS = frozenset({"XNAS", "XNYS", "XASE"})
US_TZ = ZoneInfo("America/New_York")
ALLOWED_BASES = frozenset({"AS_TRADED", "SPLIT_ADJUSTED_PRICE_AND_VOLUME"})
LOOKBACK_SESSIONS = 90
CORE_CLOSED_SESSIONS = 253
CLOSE_USD_EXCLUSIVE = 5.0
AVG_DOLLAR_VOLUME_EXCLUSIVE = 1_000_000.0
GRACE_MINUTES = 15
VERSION = "a6b-synthetic-staging-us-market-data-contract-v1"


class USMarketDataError(ValueError):
    """Fail-closed: source/calendar/bar mechanics invalid; no fallback."""


@dataclass(frozen=True)
class USSession:
    date: date
    mic: str
    opens_at: datetime
    closes_at: datetime
    early_close: bool = False


@dataclass(frozen=True)
class USDailyBar:
    date: date
    open_usd: float
    high_usd: float
    low_usd: float
    close_usd: float
    share_volume: float
    currency: str
    price_basis: str
    volume_basis: str
    final: bool
    received_at: datetime
    source_id: str


def _aware(value: datetime) -> bool:
    return (isinstance(value, datetime) and value.tzinfo is not None
            and value.utcoffset() is not None)


def _valid_float(value: object, *, strictly_positive: bool) -> bool:
    return (type(value) in (int, float)
            and math.isfinite(float(value))
            and (value > 0 if strictly_positive else value >= 0))


def validate_sessions(
    sessions: Sequence[USSession], *,
    as_of: date, mic: str, evaluated_at: datetime,
    grace_minutes: int = GRACE_MINUTES,
) -> list[USSession]:
    """Validate *supplied* session calendar with no weekday approximation.

    This DOES NOT authenticate the calendar's issuer/source. A real
    production source with versioned official coverage remains required.
    """
    if mic not in ALLOWED_MICS or not _aware(evaluated_at) or type(grace_minutes) is not int or grace_minutes < 0:
        raise USMarketDataError("US venue/evaluation instant/grace invalid")
    if not isinstance(as_of, date) or isinstance(as_of, datetime):
        raise USMarketDataError("as_of must be a US session date")
    if not sessions or any(not isinstance(s, USSession) for s in sessions):
        raise USMarketDataError("Verified session manifest not supplied")
    previous: date | None = None
    ordered = list(sessions)
    for session in ordered:
        if (session.mic != mic or not isinstance(session.date, date)
            or isinstance(session.date, datetime) or type(session.early_close) is not bool
            or not _aware(session.opens_at) or not _aware(session.closes_at)):
            raise USMarketDataError("Inconsistent MIC, session time or early-close flag")
        if previous is not None and session.date <= previous:
            raise USMarketDataError("Session calendar duplicated/unordered")
        previous = session.date
        if session.date > as_of:
            raise USMarketDataError("Calendar contains a future session")
        if (session.opens_at.astimezone(US_TZ).date() != session.date
            or session.closes_at.astimezone(US_TZ).date() != session.date
            or session.opens_at >= session.closes_at):
            raise USMarketDataError("Wrong New York date, time zone or close ordering")
        if session.closes_at + timedelta(minutes=grace_minutes) > evaluated_at:
            raise USMarketDataError("Session close or data grace period not elapsed")
    if ordered[-1].date != as_of:
        raise USMarketDataError("Stale or mismatched as_of / last completed session")
    return ordered


def validate_bars(
    calendar: Sequence[USSession],
    bars: Sequence[USDailyBar],
    *,
    evaluated_at: datetime,
    min_sessions: int = LOOKBACK_SESSIONS,
) -> list[USDailyBar]:
    """No dropping missing/suspended sessions; provider basis must be explicit.

    The *supplied calendar* is not an independently verified official US
    calendar. Each OHLCV row is tied to its exact listed session date.
    """
    if not _aware(evaluated_at) or type(min_sessions) is not int or min_sessions < 1:
        raise USMarketDataError("Missing evaluation clock or invalid lookback")
    if len(calendar) < min_sessions or len(bars) != len(calendar):
        raise USMarketDataError("Not enough complete calendar sessions / missing OHLCV rows")
    checked = list(bars)
    price_basis: str | None = None
    source: str | None = None
    for s, b in zip(calendar, checked):
        if not isinstance(b, USDailyBar) or b.date != s.date:
            raise USMarketDataError("Duplicate, omitted, substituted or mismatched session bar")
        if (b.currency != USD or b.price_basis not in ALLOWED_BASES
            or b.volume_basis != b.price_basis):
            raise USMarketDataError("Unapproved currency or inconsistent price-volume adjustment basis")
        if (b.final is not True or not _aware(b.received_at)
            or type(b.source_id) is not str or not b.source_id.strip()):
            raise USMarketDataError("Unfinalized bar, missing provider ID or received_at")
        if (b.received_at < s.closes_at or b.received_at > evaluated_at):
            raise USMarketDataError("Bar received before session close or after evaluation")
        if (price_basis is not None and b.price_basis != price_basis
            or source is not None and b.source_id != source):
            raise USMarketDataError("Changing provider/basis inside a window is prohibited")
        price_basis = b.price_basis
        source = b.source_id
        if (not all(_valid_float(x,strictly_positive=True)
                for x in (b.open_usd,b.high_usd,b.low_usd,b.close_usd))
            or not _valid_float(b.share_volume,strictly_positive=False)):
            raise USMarketDataError("Bad price/volume (NaN, missing or negative)")
        if (b.high_usd < max(b.open_usd,b.close_usd,b.low_usd)
            or b.low_usd > min(b.open_usd,b.close_usd,b.high_usd)):
            raise USMarketDataError("OHLC bounds inconsistent")
    return checked


def liquidity_dry_run(
    sessions: Sequence[USSession],
    bars: Sequence[USDailyBar],
    *,
    as_of: date, mic: str, evaluated_at: datetime,
) -> dict:
    """Policy arithmetic ONLY. Never implies security eligibility."""
    calendar=validate_sessions(sessions,as_of=as_of,mic=mic,evaluated_at=evaluated_at)
    valid=validate_bars(calendar,bars,evaluated_at=evaluated_at,min_sessions=LOOKBACK_SESSIONS)
    sample=valid[-LOOKBACK_SESSIONS:]
    last=sample[-1].close_usd
    mean_dollar=sum(b.close_usd * b.share_volume for b in sample) / LOOKBACK_SESSIONS
    passed_close=last>CLOSE_USD_EXCLUSIVE
    passed_volume=mean_dollar>AVG_DOLLAR_VOLUME_EXCLUSIVE
    return {
        "status":"SYNTHETIC_OR_UNAPPROVED_DATA_RULES_EVALUATED",
        "version":VERSION,
        "as_of":as_of.isoformat(),"mic":mic,
        "completed_calendar_sessions_evaluated":LOOKBACK_SESSIONS,
        "last_close_usd":last,
        "mean_daily_close_times_volume_usd":mean_dollar,
        "last_close_strictly_gt_5":passed_close,
        "mean_dollar_volume_strictly_gt_1m":passed_volume,
        "policy_arithmetic_passed":passed_close and passed_volume,
        "calendar_authority_independently_verified":False,
        "provider_adjustment_and_corporate_actions_approved":False,
        "issuer_security_id_and_class_approved":False,
        "final_tradability_approved":False,
        "production_eligible":False,
        "publication_permission":"DENY",
    }


def indicator_compatibility_smoke(
    sessions: Sequence[USSession],
    bars: Sequence[USDailyBar],
    *,
    as_of: date, mic: str, evaluated_at: datetime,
) -> dict:
    """Exercise existing indicator engine with synthetic SAME-basis OHLC.

    This is NOT a total-return/cash-dividend adjusted US price adapter.
    In real data, return prices and ATR technical prices require two
    separately validated series and corporate action reconciliation.
    """
    calendar=validate_sessions(sessions,as_of=as_of,mic=mic,evaluated_at=evaluated_at)
    valid=validate_bars(calendar,bars,evaluated_at=evaluated_at,
                        min_sessions=CORE_CLOSED_SESSIONS)
    if len(valid)<CORE_CLOSED_SESSIONS:
        raise USMarketDataError("253 closes required for 252-return core")
    # Use exactly the final 253 complete sessions; no compression or
    # substitution for missing sessions.
    selected=valid[-CORE_CLOSED_SESSIONS:]
    prices=[PriceBar(date=b.date,open=b.open_usd,high=b.high_usd,
                     low=b.low_usd,close=b.close_usd,volume=b.share_volume)
            for b in selected]
    snapshot=compute_snapshot(prices,as_of=as_of)
    if (snapshot.observations!=252 or snapshot.momentum_12_1 is None
        or snapshot.fip_12_1 is None):
        raise USMarketDataError("Expected 252 complete return observations")
    return {
        "status":"SYNTHETIC_INDICATOR_COMPATIBILITY_ONLY",
        "as_of":as_of.isoformat(),"mic":mic,
        "input_completed_sessions":CORE_CLOSED_SESSIONS,
        "returns_observed":snapshot.observations,
        "momentum_12_1":snapshot.momentum_12_1,
        "fip_12_1":snapshot.fip_12_1,
        "momentum_21":snapshot.momentum_21,
        "fip_21":snapshot.fip_21,
        "atr14_percent_same_basis_smoke_only":snapshot.atr14_percent,
        "completed_month_from_engine":snapshot.completed_month,
        "completed_month_calendar_verified":False,
        "total_return_adjustment_parity_verified":False,
        "corporate_action_events_reconciled":False,
        "provider_data_real":False,
        "production_eligible":False,
        "publication_permission":"DENY",
    }
