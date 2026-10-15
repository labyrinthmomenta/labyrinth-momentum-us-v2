"""A5k: 13,287 frozen A4 listings all evaluated by DENY-only source gate."""
from collections import Counter
from copy import deepcopy

import pytest

from src.data.universe import a5k_full_release as mod
from src.data.universe.a5_review import A4_HASHES


def fixture():
    a4={"status":"REVIEW_ONLY","production_eligible":False,
        "total":13287,
        "counts":{"INCLUDE":4556,"EXCLUDE":7721,"REVIEW_REQUIRED":1010},
        "rows":[]}
    triage={"status":"CLASSIFICATION_EVIDENCE_TRIAGE_REVIEW_ONLY",
            "version":"a5j-type-review-release-deny-v1",
            "as_of":"2026-10-14","known_at_established":False,
            "production_eligible":False,"total_review_records":1010,
            "approved_security_ids":0,"promoted_instruments":0,
            "provisional_include_refi_separate_hold":True,
            "sources":{},"triage_rows":[]}
    for dec,n in [("INCLUDE",4556),("REVIEW_REQUIRED",1010),("EXCLUDE",7721)]:
        for ix in range(n):
            symbol=("REFI" if dec=="INCLUDE" and ix==0 else
                    "LIEN" if dec=="REVIEW_REQUIRED" and ix==0 else
                    f"{dec[:1]}_{ix:05d}")
            src="nasdaqlisted" if ix%2==0 else "otherlisted"
            if symbol in ("REFI","LIEN"):src="nasdaqlisted"
            mic="XNAS" if src=="nasdaqlisted" else "XNYS"
            reason=("EXPLICIT_COMMON_NAME_CANDIDATE" if dec=="INCLUDE"
                    else "SPAC_BDC_OR_FINANCIAL_REVIEW" if dec=="REVIEW_REQUIRED"
                    else "TEST_ISSUE")
            a4["rows"].append({
                "source":src,"symbol":symbol,"mic":mic,
                "name":symbol+" Common Stock", "decision":dec,
                "reason":reason,"production_eligible":False,
            })
            if dec=="REVIEW_REQUIRED":
                triage["triage_rows"].append({
                    "listing_source":src,"symbol":symbol,"mic":mic,
                    "a5_original_reason":reason,
                    "a5i_decision":"REVIEW_REQUIRED",
                    "release_hold":True,"production_eligible":False,
                    "known_at_established":False,
                    "separate_security_id":None,"human_type_review_approved":False,
                    "source_listing_sha256":A4_HASHES[src],
                })
    old={"status":"OFFLINE_RELEASE_SIMULATION_DENY_ALL",
         "candidate_count":1011,"denied_count":1011,"allowed_count":0}
    return a4,triage,old


def test_complete_source_replay_evaluates_13287_unique_rows():
    a,j,old=fixture()
    r=mod.replay_all(a,j,old)
    assert r["all_source_listings_checked"]==13287
    assert r["provisional_includes_checked"]==4556
    assert r["review_required_checked"]==1010
    assert r["original_exclusions_checked"]==7721
    assert r["candidate_count"]==r["candidate_DENY"]==5566
    assert r["candidate_ALLOW"]==0
    assert r["publication_permission"]=="DENY"
    assert r["connected_to_production"] is False
    assert len(r["review_records"])==13287
    assert sum(v["release_eligible"] for v in r["review_records"])==0


def test_refi_separate_hold_and_lien_original_review():
    a,j,old=fixture()
    r=mod.replay_all(a,j,old)
    indexed={x["symbol"]:x for x in r["review_records"]}
    assert indexed["REFI"]["release_result"]=="DENY_REFI_PENDING_MERGER_AND_BDC_ELECTION"
    assert indexed["LIEN"]["release_result"]=="DENY_OFFICIAL_SECURITY_TYPE_UNAPPROVED"
    assert indexed["REFI"]["original_a4_decision"]=="INCLUDE"


def test_stale_false_revised_original_exclude_denied():
    a,j,old=fixture()
    a["rows"][-1]["decision"]="INCLUDE"
    with pytest.raises(mod.A5kSourceError):
        mod.replay_all(a,j,old)


def test_one_removed_review_or_forged_security_id_fails_closed():
    a,j,old=fixture()
    j["triage_rows"].pop()
    with pytest.raises(mod.A5kSourceError):
        mod.replay_all(a,j,old)
    a,j,old=fixture()
    j["triage_rows"][0]["separate_security_id"]="FAKE"
    with pytest.raises(mod.A5kSourceError,match="altered"):
        mod.replay_all(a,j,old)


def test_duplicate_listing_and_unapproved_refi_hold_rejected():
    a,j,old=fixture()
    a["rows"][1]=a["rows"][0]
    with pytest.raises(mod.A5kSourceError):
        mod.replay_all(a,j,old)
    a,j,old=fixture()
    j["provisional_include_refi_separate_hold"]=False
    with pytest.raises(mod.A5kSourceError):
        mod.replay_all(a,j,old)


def test_frozen_artifact_missing_is_not_ignored(tmp_path):
    with pytest.raises(FileNotFoundError):
        mod.read_pinned(tmp_path,tmp_path)
