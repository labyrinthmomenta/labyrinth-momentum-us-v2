"""US V2 offline staging preflight — isolated production contract, DENY only.

This module NEVER creates DBs, fetches prices, publishes symbols, trades,
or reaches other repositories. It pins A5r and A5u source reports, and
writes an OFFLINE preflight JSON into a US-only staging output directory.
A real US production release controller is NOT implemented.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path

VERSION="a6a-us-only-staging-preflight-v1"
A5R_SHA="19bf7052c3b1b2d9c1b306076302aca5b868d4d5f7cb58e4828685889a9e7ac6"
A5U_SHA="e194403fe11d34565b28fbae07f91453e180532dfa08c023176fa759d1c4f443"
OWN_REPOSITORY="labyrinthmomenta/labyrinth-momentum-us-v2"
OWN_NAMESPACE="us_v2"
PROPOSED_US_DB="data/us_v2/labyrinth_us.db"
PROPOSED_US_RELEASE="data/us_v2/releases/"
BLOCKERS={
    "APPROVED_SECURITY_ID_AND_SHARE_CLASS_MASTER_MISSING",
    "LEGAL_REIT_BDC_CURRENT_STATUS_AND_8K_EXHIBIT_REVIEW_PENDING",
    "LIEN_REFI_MERGER_BDC_ELECTION_UNRESOLVED",
    "SIGNED_INDEPENDENT_HUMAN_SCOPE_DECISIONS_MISSING",
    "REPLAYABLE_POINT_IN_TIME_KNOWN_AT_NOT_ESTABLISHED",
    "US_PRICE_PROVIDER_NOT_APPROVED",
    "US_90_COMPLETED_SESSIONS_DOLLAR_VOLUME_GATE_NOT_IMPLEMENTED",
    "US_DATABASE_SCHEMA_AND_DEPLOYMENT_NOT_IMPLEMENTED",
    "US_PUBLISHER_RELEASE_GATE_NOT_CONNECTED",
    "US_MONITORING_SCHEDULER_AND_RELIABLE_DATA_RETENTION_NOT_CONFIGURED",
}


class USPreflightError(ValueError):
    pass


def _read(path:Path, digest:str)->dict:
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=digest:
        raise USPreflightError(f"Immutable US source SHA256 mismatch: {path.name}")
    result=json.loads(raw)
    if type(result)!=dict:
        raise USPreflightError("US source report is not JSON object")
    return result


def evaluate(release:dict,events:dict,*,repository:str=OWN_REPOSITORY,
             environment:str="staging",existing_data_root:str="data/us_v2")->dict:
    if repository!=OWN_REPOSITORY or environment!="staging":
        raise USPreflightError("Only isolated US V2 STAGING permitted")
    if not isinstance(existing_data_root,str) or existing_data_root.replace("\\","/").rstrip("/")!="data/us_v2":
        raise USPreflightError("Reject unspecified or cross-repository data namespace")
    if (release.get("status")!="RELEASE_READINESS_DENIED"
        or release.get("version")!="a5r-independent-readiness-deny-v1"
        or release.get("as_of")!="2026-10-14"
        or release.get("all_listings_checked")!=13287
        or release.get("candidate_DENY")!=5566
        or release.get("candidate_ALLOW")!=0
        or release.get("source_exclusions_unchanged")!=7721
        or release.get("manual_reviewer_approvals")!=0
        or release.get("production_publication_permission")!="DENY"
        or release.get("gate_prototype_NOT_production_connected") is not True
        or release.get("corporate_event_holds")!=["LIEN","REFI"]):
        raise USPreflightError("Frozen A5r release denial unexpectedly altered")
    if (events.get("status")!="OFFICIAL_SEC_EVENT_SOURCES_CAPTURED_REVIEW_ONLY"
        or events.get("version")!="a5u-post-financial-40-8k-review-only-v1"
        or events.get("as_of")!="2026-10-14"
        or events.get("official_BDC_candidate_issuers")!=16
        or events.get("N54A_original_primary_files_reverified")!=17
        or events.get("post_financial_SEC_8K_metadata_expected")!=40
        or events.get("original_8K_primary_documents_verified")!=40
        or events.get("N54C_current_absence_proven") is not False
        or events.get("SEC_8K_exhibit_document_reviews_completed")!=0
        or events.get("independent_current_BDC_status_approvals")!=0
        or events.get("candidate_ALLOW")!=0
        or events.get("US_production_ready") is not False
        or events.get("production_eligible") is not False):
        raise USPreflightError("BDC SEC source/status not validated as review only")
    return {
        "status":"US_V2_STAGING_PREFLIGHT_DENIED_NO_PRODUCTION",
        "version":VERSION,
        "owned_repository":OWN_REPOSITORY,
        "data_namespace":OWN_NAMESPACE,
        "environment":"staging",
        "recommended_us_sqlite_path_NOT_CREATED":PROPOSED_US_DB,
        "recommended_us_release_directory_NOT_CREATED":PROPOSED_US_RELEASE,
        "production_database_created":False,
        "us_scheduler_enabled":False,
        "us_price_provider_used":False,
        "us_independent_security_master_ready":False,
        "us_release_approver_ready":False,
        "us_publisher_enabled":False,
        "other_repositories_accessed":False,
        "source_SHA256":{"A5r_DENY":A5R_SHA,"A5u_SEC_events":A5U_SHA},
        "frozen_source_as_of":"2026-10-14",
        "source_listed_records":13287,
        "provisional_include_unapproved":4556,
        "review_required_open":1010,
        "original_excluded_records":7721,
        "candidate_DENY":5566,
        "candidate_ALLOW":0,
        "SEC_8K_primary_sources_verified":40,
        "N54A_original_sources_verified":17,
        "current_BDC_issuer_status_approved":0,
        "independent_listed_security_id_approved":0,
        "approved_us_price_history_sessions":0,
        "unresolved_blockers":sorted(BLOCKERS),
        "publication_permission":"DENY",
        "production_eligible":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5r",required=True,type=Path)
    p.add_argument("--a5u",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    try:
        if os.environ.get("US_V2_PRODUCTION","0") not in ("0","false","False"):
            raise USPreflightError("Production flag explicitly forbidden for staging preflight")
        if str(args.output).replace("\\","/").startswith(("data/","../","/")):
            # Absolute output path and production data path prohibited in this
            # GitHub Actions-only staging preflight.
            raise USPreflightError("Preflight cannot write in production or external directories")
        q=evaluate(_read(args.a5r,A5R_SHA),_read(args.a5u,A5U_SHA),
                   repository=os.environ.get("GITHUB_REPOSITORY",OWN_REPOSITORY),
                   environment=os.environ.get("US_V2_ENVIRONMENT","staging"),
                   existing_data_root=os.environ.get("US_V2_DATA_ROOT","data/us_v2"))
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/"a6a-us-only-preflight.json").write_text(
            json.dumps(q,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
        print(json.dumps(q,indent=2,ensure_ascii=False))
        return 0
    except (ValueError,TypeError,KeyError,OSError) as exc:
        print(f"US_V2_PREFLIGHT_BLOCKED: {type(exc).__name__}: {exc}")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
