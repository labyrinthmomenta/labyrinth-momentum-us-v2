"""A5r: no code path may turn unresolved A5 type evidence into ALLOW."""
import pytest
from src.data.universe import a5r_release_readiness as m

def row(decision="INCLUDE",symbol="AAPL"):
    return {
        "source":"nasdaqlisted","ticker":symbol,"mic":"XNAS",
        "original_a4_decision":decision,
        "decision":"EXCLUDE_ORIGINAL_RETAINED" if decision=="EXCLUDE" else "DENY_PENDING_EVIDENCE_AND_APPROVAL",
        "production_eligible":False,"security_id_approved":False,
        "listed_class_approved":False,"independent_reviewer_approved":False,
        "point_in_time_known_at_approved":False,
        "review_flags":["ORIGINAL_SECURITY_TYPE_REVIEW_REQUIRED"],
    }

def test_no_source_record_can_become_allow():
    assert m.decide_one(row())=="DENY_UNVERIFIED_SECURITY_AND_APPROVAL"
    assert m.decide_one(row("REVIEW_REQUIRED"))=="DENY_UNVERIFIED_SECURITY_AND_APPROVAL"
    assert m.decide_one(row("EXCLUDE"))=="DENY_ORIGINAL_EXCLUDE"

@pytest.mark.parametrize("approval",["production_eligible","security_id_approved",
                                     "listed_class_approved",
                                     "independent_reviewer_approved",
                                     "point_in_time_known_at_approved"])
def test_self_approved_source_rejected(approval):
    x=row();x[approval]=True
    with pytest.raises(m.ReleaseDenied):m.decide_one(x)

def test_any_independent_permission_payload_is_rejected_until_real_verifier_exists():
    with pytest.raises(m.ReleaseDenied,match="tokens"):
        m.decide_one(row(),authorization={"signed":True,"user":"admin"})

def test_cannot_promote_source_excluded_security():
    x=row("EXCLUDE");x["decision"]="DENY_PENDING_EVIDENCE_AND_APPROVAL"
    with pytest.raises(m.ReleaseDenied):m.decide_one(x)

def test_missing_review_inventory_or_issuer_holds_deny():
    q={"version":"a5q-source-evidence-queue-v1",
       "status":"A5Q_ALL_SOURCE_DECISIONS_REVIEW_ONLY",
       "source_records":13287,"provisional_include":4556,
       "review_required":1010,"excluded_original":7721,
       "candidate_DENY":5566,"candidate_ALLOW":0,
       "official_decisions_modified":0,"independent_security_id_approvals":0,
       "manual_type_approvals":0,"production_gate_connected":False,
       "production_eligible":False,"queue":[]}
    with pytest.raises(m.ReleaseDenied):m.verify_queue(q)

def test_full_13287_source_candidate_replay_has_zero_allow():
    cases=[]
    for dec,num in [("INCLUDE",4556),("REVIEW_REQUIRED",1010),("EXCLUDE",7721)]:
        for i in range(num):
            sym=("REFI" if dec=="INCLUDE" and i==0 else
                 "LIEN" if dec=="REVIEW_REQUIRED" and i==0 else
                 f"{dec[0]}{i:05d}")
            r=row(dec,sym)
            if dec=="INCLUDE" and 20<=i<41:
                r["review_flags"].append("SEC_FUND_OR_PREFERRED_ISSUER_FORM_REVIEW")
            if sym in ("LIEN","REFI"):
                r["review_flags"].append("UNRESOLVED_LIEN_REFI_CORPORATE_EVENT")
            cases.append(r)
    q={
        "version":"a5q-source-evidence-queue-v1",
        "status":"A5Q_ALL_SOURCE_DECISIONS_REVIEW_ONLY",
        "source_records":13287,
        "provisional_include":4556,"review_required":1010,"excluded_original":7721,
        "candidate_DENY":5566,"candidate_ALLOW":0,
        "official_decisions_modified":0,"independent_security_id_approvals":0,
        "manual_type_approvals":0,"production_gate_connected":False,
        "production_eligible":False,"queue":cases,
    }
    result=m.verify_queue(q)
    assert result["candidate_DENY"]==5566
    assert result["candidate_ALLOW"]==0
    assert result["source_exclusions_unchanged"]==7721
    assert result["production_publication_permission"]=="DENY"
    assert len(result["release_rows"])==5566
    assert "REAL_PRODUCTION_PUBLISHER_GATE_NOT_WIRED" in result["all_missing_release_requirements"]

    # A fake external reviewer approval must stop rather than grant permission.
    q["queue"][21]["independent_reviewer_approved"]=True
    with pytest.raises(m.ReleaseDenied):m.verify_queue(q)
