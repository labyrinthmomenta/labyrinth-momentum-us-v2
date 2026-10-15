"""A5k: full 13,287-row official-source replay and offline DENY-only release audit.

Every provisional INCLUDE requires an explicit security identity and a
separately verified approval. No approval path exists in this module. This is
not connected to the runtime, prices, tradability, or production publication.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from .a5_review import A4_HASHES, A4_COUNTS, reconstruct_a4
from .a5i_decision_ledger import A4_REVIEW_HASH
from .a5j_type_release import VERSION as A5J_VERSION

A5J_TRIAGE_SHA = "48e686707c763b71c1ecb0c63a7361a87df04dec59ed2d75873250fdd64b1ed5"
A5J_GATE_SHA = "ade63abe33ed1f80e7c5c8f866473cc93cf10a0a1dca19abb2354601e6909d8f"
VERSION = "a5k-all-universe-source-deny-v1"
AS_OF = "2026-10-14"
EXPECTED_LISTINGS = 13287
EXPECTED_CANDIDATES = 4556 + 1010
EXPECTED_EXCLUDED = 7721


class A5kSourceError(ValueError):
    pass


def _frozen_json(path: Path, sha: str) -> dict:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != sha:
        raise A5kSourceError(f"Source checksum mismatch: {path.name}")
    obj = json.loads(raw.decode("utf-8"))
    if not isinstance(obj, dict):
        raise A5kSourceError("Expected immutable JSON object")
    return obj


def read_pinned(a4: Path, a5j: Path) -> tuple[dict,dict,dict]:
    a4_raw = _frozen_json(a4 / "directory-review"/"review.json", A4_REVIEW_HASH)
    # Reparse BOTH Nasdaq directories AND SEC exact official source bytes,
    # rather than trusting A4 JSON/counts alone. Also compares each row.
    verified, sec = reconstruct_a4(
        a4/"nasdaq-capture", a4/"sec-capture",
        a4/"directory-review"/"review.json")
    if (a4_raw.get("counts") != A4_COUNTS
            or a4_raw.get("total") != EXPECTED_LISTINGS
            or a4_raw.get("production_eligible") is not False
            or verified["counts"] != A4_COUNTS
            or len(sec.companies) != 10451):
        raise A5kSourceError("Original Nasdaq/SEC snapshot not complete")
    triage = _frozen_json(a5j/"a5j-type-evidence-triage.json", A5J_TRIAGE_SHA)
    earlier = _frozen_json(a5j/"a5j-release-gate-simulation.json", A5J_GATE_SHA)
    if (triage.get("status")!="CLASSIFICATION_EVIDENCE_TRIAGE_REVIEW_ONLY"
            or triage.get("version")!=A5J_VERSION
            or triage.get("as_of")!=AS_OF
            or triage.get("production_eligible") is not False
            or triage.get("total_review_records")!=1010
            or triage.get("approved_security_ids")!=0
            or triage.get("promoted_instruments")!=0
            or triage.get("provisional_include_refi_separate_hold") is not True
            or triage.get("sources",{}).get("a5i_ledger_sha256")
               != "306be7c6293649b367caa999fa374c1fcd7f7caa41af6f9f3bef58b95387922a"
            or len(triage.get("triage_rows",[]))!=1010):
        raise A5kSourceError("Frozen A5j type triage not complete")
    if (earlier.get("status")!="OFFLINE_RELEASE_SIMULATION_DENY_ALL"
            or earlier.get("connected_to_production") is not False
            or earlier.get("candidate_count")!=1011
            or earlier.get("allowed_count")!=0
            or earlier.get("denied_count")!=1011
            or earlier.get("other_4555_provisional_includes_evaluated") is not False
            or earlier.get("global_release_permission")!="DENY"):
        raise A5kSourceError("Previous partial release simulation misrepresented")
    return a4_raw,triage,earlier


def replay_all(a4: dict, triage: dict, previous: dict) -> dict:
    """Conservative REVIEW ONLY: 5,566 candidates DENY, 7,721 exclusions held."""
    reviewed={}
    for r in triage["triage_rows"]:
        key=(r["listing_source"],r["symbol"],r["mic"])
        if key in reviewed:
            raise A5kSourceError("Duplicate A5j review ticker/source/MIC")
        if (r.get("a5i_decision")!="REVIEW_REQUIRED"
                or r.get("release_hold") is not True
                or r.get("production_eligible") is not False
                or r.get("known_at_established") is not False
                or r.get("separate_security_id") is not None
                or r.get("human_type_review_approved") is not False
                or r.get("source_listing_sha256") != A4_HASHES.get(r["listing_source"])):
            raise A5kSourceError("A5j review row was promoted/altered")
        reviewed[key]=r
    original=set()
    results=[]
    counts=Counter()
    denominators=Counter()
    for row in a4["rows"]:
        key=(row["source"],row["symbol"],row["mic"])
        if key in original or row.get("production_eligible") is not False:
            raise A5kSourceError("Duplicate or approved source listing")
        original.add(key)
        if row["source"] not in ("nasdaqlisted","otherlisted"):
            raise A5kSourceError("Unexpected Nasdaq source for listing")
        decision=row["decision"]
        if decision == "EXCLUDE":
            if key in reviewed:
                raise A5kSourceError("A5j has review for excluded instrument")
            result="EXCLUDED_BY_ORIGINAL_A4_NEVER_RELEASED"
        elif decision == "REVIEW_REQUIRED":
            j=reviewed.pop(key,None)
            if j is None or j.get("a5_original_reason")!=row["reason"]:
                raise A5kSourceError("A5 review row missing or changed")
            result="DENY_OFFICIAL_SECURITY_TYPE_UNAPPROVED"
        elif decision == "INCLUDE":
            if key in reviewed:
                raise A5kSourceError("Provisional INCLUDE has A5j reviewed identity")
            if row["symbol"]=="REFI" and row["source"]=="nasdaqlisted":
                if (row["mic"]!="XNAS"
                        or triage["provisional_include_refi_separate_hold"] is not True):
                    raise A5kSourceError("REFI mandatory corporate action hold missing")
                result="DENY_REFI_PENDING_MERGER_AND_BDC_ELECTION"
            else:
                result="DENY_PROVISIONAL_INCLUDE_NO_APPROVED_SECURITY_ID"
        else:
            raise A5kSourceError("Unexpected A4 decision")
        denominators[decision]+=1
        counts[result]+=1
        results.append({
            "source":row["source"],"symbol":row["symbol"],"mic":row["mic"],
            "name":row["name"],"original_a4_decision":decision,
            "original_a4_reason":row["reason"],
            "release_result":result,"release_eligible":False,
            "approved_security_id":None,"independent_approval":False,
            "known_at_proven":False,"as_of":AS_OF,
            "listing_source_sha256":A4_HASHES[row["source"]],
        })
    if (reviewed or len(original)!=EXPECTED_LISTINGS
            or denominators!=Counter(A4_COUNTS)
            or counts["DENY_OFFICIAL_SECURITY_TYPE_UNAPPROVED"]!=1010
            or counts["DENY_REFI_PENDING_MERGER_AND_BDC_ELECTION"]!=1
            or counts["DENY_PROVISIONAL_INCLUDE_NO_APPROVED_SECURITY_ID"]!=4555
            or counts["EXCLUDED_BY_ORIGINAL_A4_NEVER_RELEASED"]!=EXPECTED_EXCLUDED):
        raise A5kSourceError("Full universe reconciliation or REFI block failed")
    return {
        "status":"FULL_UNIVERSE_SOURCE_REPLAY_DENY_ONLY",
        "version":VERSION,"as_of":AS_OF,"production_eligible":False,
        "source_sha256":{"a4_review":A4_REVIEW_HASH,
            "a4_nasdaq":A4_HASHES["nasdaqlisted"],
            "a4_nyse_american_and_nyse":A4_HASHES["otherlisted"],
            "a4_sec":A4_HASHES["sec"],
            "a5j_review":A5J_TRIAGE_SHA,"a5j_gate":A5J_GATE_SHA},
        "all_source_listings_checked":EXPECTED_LISTINGS,
        "original_a4_counts":dict(denominators),
        "provisional_includes_checked":4556,"review_required_checked":1010,
        "original_exclusions_checked":7721,
        "candidate_count":EXPECTED_CANDIDATES,"candidate_DENY":EXPECTED_CANDIDATES,
        "candidate_ALLOW":0,
        "release_reason_counts":dict(sorted(counts.items())),
        "independent_reviewer_authority_verified":False,
        "registered_security_master_identity_approved":False,
        "known_at_complete":False,
        "connected_to_production":False,
        "publication_permission":"DENY",
        "no_allow_codepath":True,
        "review_records":results,
    }


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a4",type=Path,required=True)
    p.add_argument("--a5j",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        a4,triage,previous=read_pinned(args.a4,args.a5j)
        report=replay_all(a4,triage,previous)
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/"a5k-full-universe-deny.json").write_text(
            json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        small={k:v for k,v in report.items() if k!="review_records"}
        (args.output/"a5k-universe-summary.json").write_text(
            json.dumps(small,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(json.dumps(small,indent=2,ensure_ascii=False))
        return 0
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print(f"A5K_UNIVERSE_BLOCKED: {type(exc).__name__}: {exc}")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
