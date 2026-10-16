"""A5p: frozen symbol discrepancy triage safeguards."""
from collections import Counter
import pytest
from src.data.universe import a5p_date_mic_gaps as m

def frozen():
    rows=[]
    for mic,ss in m.OFFICIAL_ONLY_INCLUDE.items():
        for s in ss:
            rows.append({"symbol":s,"mic":mic,"name":s+" share",
                         "decision":"INCLUDE","production_eligible":False})
    for i in range(314):
        decision="INCLUDE" if i<225 else "EXCLUDE" if i<278 else "REVIEW_REQUIRED"
        rows.append({"symbol":f"XASE{i:03d}","mic":"XASE",
                     "decision":decision,"production_eligible":False})
    for i in range(13287-len(rows)):
        rows.append({"symbol":f"DUMMY{i:05d}","mic":"XNAS",
                     "decision":"EXCLUDE","production_eligible":False})
    return {"total":13287,"counts":m.DECISIONS,"production_eligible":False,
            "rows":rows}

def test_seven_six_and_314_held():
    r=m.reconcile(frozen())
    assert r["tv_only_unresolved"]==7
    assert r["official_only_provisional_includes"]==6
    assert r["XASE_no_TradingView_exchange_label"]==314
    assert r["XASE_original_decisions"]==m.XASE_DECISIONS
    assert r["production_approvals"]==0 and r["auto_promoted"]==0
    assert r["NYSE_Arca_is_not_XASE"] is True

def test_source_only_promoted_or_duplicate_fails_closed():
    x=frozen()
    x["rows"][0]["decision"]="EXCLUDE"
    with pytest.raises(m.SourceError):m.reconcile(x)
    x=frozen()
    x["rows"][-1]=x["rows"][0]
    with pytest.raises(m.SourceError):m.reconcile(x)

def test_undocumented_tv_only_entry_present_in_official_fails_closed():
    x=frozen()
    x["rows"][-1]["symbol"]="BMMX"
    with pytest.raises(m.SourceError):m.reconcile(x)

def test_xase_count_or_outcome_change_not_silently_ignored():
    x=frozen()
    x["rows"][6]["decision"]="EXCLUDE"
    with pytest.raises(m.SourceError):m.reconcile(x)
