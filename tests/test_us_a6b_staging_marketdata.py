"""A6b US 90-close×volume policy boundary and synthetic 252-return smoke."""
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
import math
from zoneinfo import ZoneInfo
import pytest

from src.data.us_staging_marketdata import (
    USSession,USDailyBar,USMarketDataError,validate_sessions,validate_bars,
    liquidity_dry_run,indicator_compatibility_smoke,
)

ET=ZoneInfo("America/New_York")
END=date(2026,10,14)


def synthetic(count:int=253, *,end:date=END,early_date:date|None=None,
              close:float=10.0,volume:float=150_000.0):
    """Weekdays only MOCK; deliberately NOT an authoritative US calendar."""
    days=[]
    cursor=end
    while len(days)<count:
        if cursor.weekday()<5:
            days.append(cursor)
        cursor-=timedelta(days=1)
    days.sort()
    sessions=[]
    bars=[]
    for day in days:
        op=datetime.combine(day,time(9,30),tzinfo=ET)
        cl=datetime.combine(day,time(13 if day==early_date else 16,0),tzinfo=ET)
        session=USSession(day,"XNAS",op.astimezone(timezone.utc),
                          cl.astimezone(timezone.utc),day==early_date)
        sessions.append(session)
        bars.append(USDailyBar(date=day,open_usd=close,high_usd=close+0.15,
            low_usd=close-0.15,close_usd=close,share_volume=volume,
            currency="USD",price_basis="AS_TRADED",volume_basis="AS_TRADED",
            final=True,received_at=session.closes_at+timedelta(minutes=2),
            source_id="SYNTHETIC_DO_NOT_USE"))
    evaluated=sessions[-1].closes_at+timedelta(minutes=25)
    return sessions,bars,evaluated


def screen(sessions,bars,at,as_of=END):
    return liquidity_dry_run(sessions,bars,as_of=as_of,mic="XNAS",evaluated_at=at)


def test_90_fully_completed_session_arithmetic_strict_gt():
    sessions,bars,at=synthetic(90)
    r=screen(sessions,bars,at)
    assert r["last_close_usd"]==10
    assert r["mean_daily_close_times_volume_usd"]==1_500_000
    assert r["completed_calendar_sessions_evaluated"]==90
    assert r["last_close_strictly_gt_5"] is True
    assert r["mean_dollar_volume_strictly_gt_1m"] is True
    assert r["policy_arithmetic_passed"] is True
    assert r["calendar_authority_independently_verified"] is False
    assert r["final_tradability_approved"] is False
    assert r["publication_permission"]=="DENY"


def test_exact_price_5_is_not_strictly_greater():
    s,b,at=synthetic(90,close=5,volume=300000)
    r=screen(s,b,at)
    assert r["last_close_strictly_gt_5"] is False
    assert r["mean_dollar_volume_strictly_gt_1m"] is True
    assert r["policy_arithmetic_passed"] is False


def test_exact_average_1million_is_rejected():
    s,b,at=synthetic(90,close=10,volume=100000)
    r=screen(s,b,at)
    assert r["last_close_strictly_gt_5"] is True
    assert r["mean_daily_close_times_volume_usd"]==1_000_000
    assert r["mean_dollar_volume_strictly_gt_1m"] is False


def test_dollar_volume_is_mean_of_close_times_volume_not_mean_volume():
    s,b,at=synthetic(90,close=10,volume=100000)
    b[0]=replace(b[0],close_usd=20,open_usd=20,high_usd=20.15,low_usd=19.85)
    r=screen(s,b,at)
    assert math.isclose(r["mean_daily_close_times_volume_usd"],1_000_000+1_000_000/90)
    assert r["policy_arithmetic_passed"] is True


def test_no_89_session_shortcut():
    s,b,at=synthetic(89)
    with pytest.raises(USMarketDataError,match="Not enough"):
        screen(s,b,at)


def test_253_sessions_feed_exact_252_returns_to_existing_core():
    s,b,at=synthetic(253)
    b=[replace(x,open_usd=20+i*0.05,high_usd=20+i*0.05+0.10,
               low_usd=20+i*0.05-0.10,close_usd=20+i*0.05)
       for i,x in enumerate(b)]
    out=indicator_compatibility_smoke(s,b,as_of=END,mic="XNAS",evaluated_at=at)
    assert out["returns_observed"]==252
    assert out["input_completed_sessions"]==253
    assert out["momentum_12_1"]>0
    assert out["fip_12_1"]==-1
    assert out["momentum_21"]>0
    assert out["provider_data_real"] is False
    assert out["total_return_adjustment_parity_verified"] is False
    assert out["publication_permission"]=="DENY"


def test_252_prices_do_not_make_252_returns():
    s,b,at=synthetic(252)
    with pytest.raises(USMarketDataError,match="Not enough"):
        indicator_compatibility_smoke(s,b,as_of=END,mic="XNAS",evaluated_at=at)


def test_synthetic_Dst_offsets_follow_new_york_IANA_rules():
    s,b,at=synthetic(253)
    winter=next(x for x in s if x.date.month==1)
    summer=next(x for x in s if x.date.month==7)
    assert winter.closes_at.hour==21  # NY 4 PM EST -> 21:00 UTC
    assert summer.closes_at.hour==20  # NY 4 PM EDT -> 20:00 UTC
    assert screen(s,b,at)["policy_arithmetic_passed"]


def test_early_close_one_session_not_missing_or_duplicated():
    s,b,at=synthetic(90,early_date=END-timedelta(days=1))
    special=next(x for x in s if x.early_close)
    assert special.closes_at.astimezone(ET).hour==13
    assert screen(s,b,at)["completed_calendar_sessions_evaluated"]==90


def test_calendar_absent_last_date_stale_and_future_refused():
    s,b,at=synthetic(90)
    with pytest.raises(USMarketDataError,match="Stale"):
        screen(s,b,at,as_of=END+timedelta(days=1))
    with pytest.raises(USMarketDataError,match="future"):
        screen(s,b,at,as_of=END-timedelta(days=1))


def test_grace_period_not_elapsed_fails_closed_even_after_close():
    s,b,at=synthetic(90)
    shortly_after_close=s[-1].closes_at+timedelta(minutes=9)
    with pytest.raises(USMarketDataError,match="grace"):
        screen(s,b,shortly_after_close)


@pytest.mark.parametrize("bad",["wrong_mic","bad_session_order","duplicated_session","wrong_local_date","naive_clock"])
def test_bad_exchange_calendar_never_uses_weekday_fallback(bad):
    s,b,at=synthetic(90)
    if bad=="wrong_mic":
        s[-1]=replace(s[-1],mic="XNYS")
    elif bad=="bad_session_order":
        s[-1],s[-2]=s[-2],s[-1]
    elif bad=="duplicated_session":
        s[-1]=replace(s[-1],date=s[-2].date)
    elif bad=="wrong_local_date":
        s[-1]=replace(s[-1],closes_at=s[-1].closes_at+timedelta(hours=10))
    else:
        at=at.replace(tzinfo=None)
    with pytest.raises(USMarketDataError):
        screen(s,b,at)


@pytest.mark.parametrize("bad",[
    "missing_bar","wrong_bar_date","not_final","received_before_close",
    "received_after_eval","wrong_currency","bad_volume","nan_volume",
    "negative_price","bad_high","basis_mismatch","provider_change","missing_source",
])
def test_corrupt_or_incomplete_price_history_never_silently_skips(bad):
    s,b,at=synthetic(90)
    if bad=="missing_bar":b.pop(-40)
    elif bad=="wrong_bar_date":b[11]=replace(b[11],date=END)
    elif bad=="not_final":b[-1]=replace(b[-1],final=False)
    elif bad=="received_before_close":b[-1]=replace(b[-1],received_at=s[-1].closes_at-timedelta(seconds=1))
    elif bad=="received_after_eval":b[-1]=replace(b[-1],received_at=at+timedelta(seconds=1))
    elif bad=="wrong_currency":b[-1]=replace(b[-1],currency="EUR")
    elif bad=="bad_volume":b[-1]=replace(b[-1],share_volume=-1)
    elif bad=="nan_volume":b[-1]=replace(b[-1],share_volume=float("nan"))
    elif bad=="negative_price":b[-1]=replace(b[-1],close_usd=-10)
    elif bad=="bad_high":b[-1]=replace(b[-1],high_usd=5)
    elif bad=="basis_mismatch":b[-1]=replace(b[-1],volume_basis="SPLIT_ADJUSTED_PRICE_AND_VOLUME")
    elif bad=="provider_change":b[-1]=replace(b[-1],source_id="UNMATCHED_VENDOR")
    elif bad=="missing_source":b[-1]=replace(b[-1],source_id="")
    with pytest.raises(USMarketDataError):
        screen(s,b,at)


def test_incomplete_no_volume_is_not_fake_zero():
    s,b,at=synthetic(90)
    b[-1]=replace(b[-1],share_volume=None)
    with pytest.raises(USMarketDataError):
        screen(s,b,at)


def test_volume_zero_is_valid_arithmetic_but_counts_as_zero_dollar_day():
    s,b,at=synthetic(90,close=10,volume=100001)
    b[18]=replace(b[18],share_volume=0.0)
    r=screen(s,b,at)
    assert r["policy_arithmetic_passed"] is False
    assert r["mean_daily_close_times_volume_usd"]<1_000_000


def test_price_volume_aligned_split_adjusted_basis_permitted_for_math_not_authority():
    s,b,at=synthetic(90)
    b=[replace(x,price_basis="SPLIT_ADJUSTED_PRICE_AND_VOLUME",
               volume_basis="SPLIT_ADJUSTED_PRICE_AND_VOLUME") for x in b]
    r=screen(s,b,at)
    assert r["policy_arithmetic_passed"]
    assert not r["provider_adjustment_and_corporate_actions_approved"]
