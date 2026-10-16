"""A6b full deterministic mocked US pre-indicator smoke and no live publishing."""
import json
from pathlib import Path
import pytest
from src.data import us_synthetic_smoke as s


def test_synthetic_full_pipeline_has_clear_mock_source_flag():
    result=s.run_mock()
    assert result["status"]=="SYNTHETIC_US_STAGING_RULES_SMOKE_SUCCESS_NO_REAL_DATA"
    assert result["real_US_price_data_rows"]==0
    assert result["liquidity_mechanics"]["completed_calendar_sessions_evaluated"]==90
    assert result["liquidity_mechanics"]["policy_arithmetic_passed"] is True
    assert result["indicator_compatibility"]["returns_observed"]==252
    assert result["trading_calendar_independently_verified"] is False
    assert result["corporate_actions_and_total_return_adjustments_verified"] is False
    assert result["US_publication_permission"]=="DENY"
    assert result["production_eligible"] is False


def test_synthetic_output_cli_writes_staging_only(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv",["cli","--output","runtime/us_v2_staging/a6b"])
    assert s.main()==0
    p=Path("runtime/us_v2_staging/a6b/a6b-synthetic-us-price-indicators.json")
    obj=json.loads(p.read_text())
    assert obj["published_US_securities"]==0
    assert obj["real_US_price_data_rows"]==0
    # Cannot overwrite or silently modify an existing test artifact.
    with pytest.raises(SystemExit,match="must not preexist"):
        s.main()


@pytest.mark.parametrize("bad",[
    "/mnt/data/us_v2_staging/a6b",
    "data/us_v2/releases",
    "../labyrinth-momentum-v2/data",
    "runtime/otherrepo/staging",
])
def test_synthetic_smoke_never_writes_outside_isolated_us_runtime(bad,monkeypatch):
    monkeypatch.setattr("sys.argv",["cli","--output",bad])
    with pytest.raises(SystemExit,match="A6B_BLOCKED"):
        s.main()
