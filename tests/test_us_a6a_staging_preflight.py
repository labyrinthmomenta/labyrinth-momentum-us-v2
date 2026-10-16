"""US V2 staging-only evidence checks, BIST/other repository isolation."""
from hashlib import sha256
import pytest
from src.data.universe import a6a_us_staging_preflight as a


def inputs():
    release={
        "status":"RELEASE_READINESS_DENIED",
        "version":"a5r-independent-readiness-deny-v1",
        "as_of":"2026-10-14",
        "all_listings_checked":13287,
        "candidate_DENY":5566,"candidate_ALLOW":0,
        "source_exclusions_unchanged":7721,
        "manual_reviewer_approvals":0,
        "production_publication_permission":"DENY",
        "gate_prototype_NOT_production_connected":True,
        "corporate_event_holds":["LIEN","REFI"],
    }
    events={
        "status":"OFFICIAL_SEC_EVENT_SOURCES_CAPTURED_REVIEW_ONLY",
        "version":"a5u-post-financial-40-8k-review-only-v1",
        "as_of":"2026-10-14",
        "official_BDC_candidate_issuers":16,
        "N54A_original_primary_files_reverified":17,
        "post_financial_SEC_8K_metadata_expected":40,
        "original_8K_primary_documents_verified":40,
        "N54C_current_absence_proven":False,
        "SEC_8K_exhibit_document_reviews_completed":0,
        "independent_current_BDC_status_approvals":0,
        "candidate_ALLOW":0,
        "US_production_ready":False,
        "production_eligible":False,
    }
    return release,events


def test_separate_us_staging_contract_does_not_start_production():
    r,e=inputs()
    result=a.evaluate(r,e)
    assert result["status"]=="US_V2_STAGING_PREFLIGHT_DENIED_NO_PRODUCTION"
    assert result["owned_repository"]=="labyrinthmomenta/labyrinth-momentum-us-v2"
    assert result["data_namespace"]=="us_v2"
    assert result["recommended_us_sqlite_path_NOT_CREATED"]=="data/us_v2/labyrinth_us.db"
    assert result["candidate_DENY"]==5566
    assert result["candidate_ALLOW"]==0
    assert result["publication_permission"]=="DENY"
    assert result["us_publisher_enabled"] is False
    assert result["production_database_created"] is False
    assert result["other_repositories_accessed"] is False
    assert result["SEC_8K_primary_sources_verified"]==40


@pytest.mark.parametrize("repository,environment,root",[
    ("labyrinthmomenta/labyrinth-momentum-v2","staging","data/us_v2"),
    ("labyrinthmomenta/labyrinth-momentum-us-v2","production","data/us_v2"),
    ("labyrinthmomenta/labyrinth-momentum-us-v2","staging","data/labyrinth.db"),
    ("labyrinthmomenta/labyrinth-momentum-us-v2","staging","../other-repo"),
])
def test_other_repository_or_production_namespace_rejected(repository,environment,root):
    r,e=inputs()
    with pytest.raises(a.USPreflightError):
        a.evaluate(r,e,repository=repository,environment=environment,existing_data_root=root)


@pytest.mark.parametrize("change",[
    ("candidate_ALLOW",1),
    ("gate_prototype_NOT_production_connected",False),
    ("manual_reviewer_approvals",1),
    ("production_publication_permission","ALLOW"),
    ("source_exclusions_unchanged",0),
])
def test_manipulated_prior_release_or_scope_blocks(change):
    r,e=inputs();r[change[0]]=change[1]
    with pytest.raises(a.USPreflightError):
        a.evaluate(r,e)


@pytest.mark.parametrize("change",[
    ("original_8K_primary_documents_verified",39),
    ("N54C_current_absence_proven",True),
    ("SEC_8K_exhibit_document_reviews_completed",40),
    ("independent_current_BDC_status_approvals",16),
    ("US_production_ready",True),
])
def test_claims_of_approved_bdc_legal_status_or_missing_source_block(change):
    r,e=inputs();e[change[0]]=change[1]
    with pytest.raises(a.USPreflightError):
        a.evaluate(r,e)


def test_exact_source_SHA256_required(tmp_path):
    file=tmp_path/"a5r.json"
    file.write_text("{}")
    with pytest.raises(a.USPreflightError,match="SHA256"):
        a._read(file,a.A5R_SHA)
