"""A5r pre-production readiness certificate: DENY-only, NOT a release path.

The source registry is NOT an independent approved security master.
No token, self-asserted reviewer claim, mutable policy or symbol text can
turn a DENY into ALLOW. Publication integration intentionally absent.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

VERSION="a5r-independent-readiness-deny-v1"
A5Q_SHA="31fafa47387d20b76b36c5fc9c812c2e3ffc369e8b5b17845539d57b07f0104c"
REVIEW_COUNTS={"INCLUDE":4556,"REVIEW_REQUIRED":1010,"EXCLUDE":7721}
BLOCKERS={
    "POLICY_SCOPE_OWNER_SIGNATURE_NOT_VERIFIED",
    "INDEPENDENT_EXCHANGE_LISTED_SECURITY_MASTER_MISSING",
    "LISTED_CLASS_AND_SECURITY_ID_NOT_APPROVED",
    "REVIEWER_AUTHENTICATION_AND_TWO_PERSON_APPROVAL_MISSING",
    "SOURCE_KNOWN_AT_AND_EFFECTIVE_AT_NOT_APPROVED",
    "SEC_REGULATED_ENTITY_AND_CORPORATE_EVENTS_PENDING",
    "PER_SECURITY_90_COMPLETED_SESSIONS_PRICExVOLUME_GATE_NOT_EVALUATED",
    "REAL_PRODUCTION_PUBLISHER_GATE_NOT_WIRED",
}
class ReleaseDenied(ValueError):pass


def decide_one(r,*,authorization=None):
    """Explicitly no ALLOW path in this review-only version."""
    if (r.get("production_eligible") is not False
        or r.get("security_id_approved") is not False
        or r.get("listed_class_approved") is not False
        or r.get("independent_reviewer_approved") is not False
        or r.get("point_in_time_known_at_approved") is not False):
        raise ReleaseDenied("Incoming row carries unverified approval")
    if authorization is not None:
        raise ReleaseDenied("Self-asserted or external approval tokens not accepted")
    if r.get("original_a4_decision")=="EXCLUDE":
        if r.get("decision")!="EXCLUDE_ORIGINAL_RETAINED":
            raise ReleaseDenied("Original EXCLUDE improperly overridden")
        return "DENY_ORIGINAL_EXCLUDE"
    if (r.get("original_a4_decision") not in ("INCLUDE","REVIEW_REQUIRED")
        or r.get("decision")!="DENY_PENDING_EVIDENCE_AND_APPROVAL"):
        raise ReleaseDenied("Unrecognized provisional/review source state")
    return "DENY_UNVERIFIED_SECURITY_AND_APPROVAL"


def verify_queue(q):
    if (q.get("version")!="a5q-source-evidence-queue-v1"
        or q.get("status")!="A5Q_ALL_SOURCE_DECISIONS_REVIEW_ONLY"
        or q.get("source_records")!=13287
        or q.get("provisional_include")!=4556
        or q.get("review_required")!=1010
        or q.get("excluded_original")!=7721
        or q.get("candidate_DENY")!=5566
        or q.get("candidate_ALLOW")!=0
        or q.get("official_decisions_modified")!=0
        or q.get("independent_security_id_approvals")!=0
        or q.get("manual_type_approvals")!=0
        or q.get("production_gate_connected") is not False
        or q.get("production_eligible") is not False
        or len(q.get("queue",[]))!=13287):
        raise ReleaseDenied("Source queue not frozen DENY-only")
    keys=set()
    types=Counter()
    categories=Counter()
    release_rows=[]
    for row in q["queue"]:
        key=(row["source"],row["ticker"],row["mic"])
        if key in keys:raise ReleaseDenied("Duplicate source/security identity")
        keys.add(key)
        state=decide_one(row)
        types[row["original_a4_decision"]]+=1
        categories[state]+=1
        if state=="DENY_UNVERIFIED_SECURITY_AND_APPROVAL":
            release_rows.append({"ticker":row["ticker"],
                                 "source":row["source"],"mic":row["mic"],
                                 "release_permission":"DENY",
                                 "reason":state,
                                 "security_id":None,
                                 "reviewer_grant_verified":False})
    if types!=Counter(REVIEW_COUNTS) or len(release_rows)!=5566:
        raise ReleaseDenied("Candidate or type distribution changed")
    required={"LIEN","REFI"}
    holds={row["ticker"] for row in q["queue"] if
           "UNRESOLVED_LIEN_REFI_CORPORATE_EVENT" in row["review_flags"]}
    if holds!=required:
        raise ReleaseDenied("LIEN/REFI required unresolved corporate holds absent")
    if sum("SEC_FUND_OR_PREFERRED_ISSUER_FORM_REVIEW" in x["review_flags"]
           for x in q["queue"])!=21:
        raise ReleaseDenied("21 high-priority CFI SEC review flags missing")
    return {
        "status":"RELEASE_READINESS_DENIED",
        "version":VERSION,"as_of":"2026-10-14",
        "source_a5q_SHA256":A5Q_SHA,
        "all_listings_checked":13287,
        "provisional_and_review_candidates_checked":5566,
        "source_exclusions_unchanged":7721,
        "candidate_DENY":5566,"candidate_ALLOW":0,
        "decision_distribution":dict(types),
        "independent_policy_approvals":0,
        "legal_security_id_approvals":0,
        "manual_reviewer_approvals":0,
        "production_publication_permission":"DENY",
        "gate_prototype_NOT_production_connected":True,
        "all_missing_release_requirements":sorted(BLOCKERS),
        "REVIEW_REQUIRED_still_open":1010,
        "provisional_INCLUDE_not_authorized":4556,
        "high_priority_SEC_CFI_conflicts":21,
        "corporate_event_holds":sorted(holds),
        "unknown_point_in_time_SEClisting_retrieval":True,
        "release_rows":release_rows,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5q",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        b=args.a5q.read_bytes()
        if sha256(b).hexdigest()!=A5Q_SHA:raise ReleaseDenied("SHA256 mismatch: source A5q")
        report=verify_queue(json.loads(b))
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/"a5r-release-readiness-deny.json").write_text(
            json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        print(json.dumps({k:v for k,v in report.items() if k!="release_rows"},
                         ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as e:
        print("A5R_FAIL_CLOSED:",e);return 2

if __name__=="__main__":raise SystemExit(main())
