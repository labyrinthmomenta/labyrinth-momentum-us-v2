"""Run a deterministic MOCK US OHLCV price/volume + indicator smoke.

The calendar is intentionally a weekday-only TEST FIXTURE; it is *not* an
NYSE/Nasdaq/XASE holiday calendar or official US trading history.
Nothing may be published to a production listing or database.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .us_staging_marketdata import (
    USSession,USDailyBar,liquidity_dry_run,indicator_compatibility_smoke,
)

VERSION="a6b-us-synthetic-ohlcv-smoke-v1"
SYNTHETIC_AS_OF=date(2026,10,14)
ET=ZoneInfo("America/New_York")


def generate_synthetic_fixture()->tuple[list[USSession],list[USDailyBar],datetime]:
    days=[]
    day=SYNTHETIC_AS_OF
    while len(days)<253:
        if day.weekday()<5:days.append(day)
        day-=timedelta(days=1)
    days.reverse()
    sessions=[]
    bars=[]
    example_early=days[-15]  # deliberately NOT asserted an official half-day
    for idx,d in enumerate(days):
        opens=datetime.combine(d,time(9,30),ET)
        closes=datetime.combine(
            d,time(13,0) if d==example_early else time(16,0),ET
        )
        session=USSession(
            date=d,mic="XNAS",opens_at=opens.astimezone(timezone.utc),
            closes_at=closes.astimezone(timezone.utc),
            early_close=(d==example_early),
        )
        sessions.append(session)
        close=10+0.03*idx
        bars.append(USDailyBar(
            date=d,open_usd=close,high_usd=close+0.10,
            low_usd=close-0.10,close_usd=close,
            share_volume=150_000.0,currency="USD",
            price_basis="AS_TRADED",volume_basis="AS_TRADED",
            final=True,
            received_at=closes.astimezone(timezone.utc)+timedelta(minutes=2),
            source_id="SYNTHETIC_FIXTURE_NOT_A_PRICE_PROVIDER",
        ))
    evaluated_at=sessions[-1].closes_at+timedelta(minutes=35)
    return sessions,bars,evaluated_at


def run_mock()->dict:
    sessions,bars,now=generate_synthetic_fixture()
    liquidity=liquidity_dry_run(
        sessions,bars,as_of=SYNTHETIC_AS_OF,mic="XNAS",evaluated_at=now,
    )
    indicators=indicator_compatibility_smoke(
        sessions,bars,as_of=SYNTHETIC_AS_OF,mic="XNAS",evaluated_at=now,
    )
    if (not liquidity["policy_arithmetic_passed"]
        or indicators["returns_observed"]!=252
        or indicators["momentum_12_1"] is None
        or indicators["fip_12_1"] is None):
        raise ValueError("Synthetic fixture did not meet expected mechanics")
    return {
        "version":VERSION,
        "status":"SYNTHETIC_US_STAGING_RULES_SMOKE_SUCCESS_NO_REAL_DATA",
        "fixture_as_of":SYNTHETIC_AS_OF.isoformat(),
        "fixture_source":"PROGRAMMATIC_WEEKDAY_ONLY_NOT_OFFICIAL_MARKET_CALENDAR",
        "fixture_has_deliberately_mock_early_close":True,
        "real_US_price_data_rows":0,
        "independent_security_id_verified":False,
        "trading_calendar_independently_verified":False,
        "price_provider_selected_or_approved":False,
        "corporate_actions_and_total_return_adjustments_verified":False,
        "US_production_database_created":False,
        "published_US_securities":0,
        "liquidity_mechanics":liquidity,
        "indicator_compatibility":indicators,
        "US_publication_permission":"DENY",
        "production_eligible":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    path=args.output
    if path.is_absolute() or ".." in path.parts or (
            not str(path).startswith("runtime/us_v2_staging/")):
        raise SystemExit("A6B_BLOCKED: only temporary relative US staging output allowed")
    if path.exists():
        raise SystemExit("A6B_BLOCKED: output directory must not preexist")
    data=run_mock()
    path.mkdir(parents=True)
    (path/"a6b-synthetic-us-price-indicators.json").write_text(
        json.dumps(data,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":data["status"],"as_of":data["fixture_as_of"],
        "synthetic_close_gt_5":data["liquidity_mechanics"]["last_close_strictly_gt_5"],
        "synthetic_liquidity_gt_1m":data["liquidity_mechanics"]["mean_dollar_volume_strictly_gt_1m"],
        "synthetic_returns":data["indicator_compatibility"]["returns_observed"],
        "real_market_data_rows":data["real_US_price_data_rows"],
        "production_permission":data["US_publication_permission"],
    },indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
