"""A5s CEF exclusion, REIT/BDC common share exception, deny-only safeguards."""
import pytest
from src.data.universe import a5s_scope_policy as p


def make(**override):
    x=dict(ticker="EXAM",mic="XNYS",issuer_type="REIT",
           listed_class="COMMON_STOCK",issuer_status_verified=True,
           listed_class_verified=True)
    x.update(override)
    return p.Evidence(**x)


@pytest.mark.parametrize("kind",["REIT","BDC","OPERATING_COMPANY"])
def test_common_share_policy_candidate_not_production(kind):
    d=p.review(make(issuer_type=kind))
    assert d["classification_proposal"]=="PROVISIONAL_POLICY_CANDIDATE_NOT_APPROVED"
    assert d["production_eligible"] is False
    assert d["release_authorization"]=="DENY"


@pytest.mark.parametrize("kind",["CEF","ETF_ISSUER","OTHER_FUND"])
def test_verified_fund_excluded_even_with_common_shares(kind):
    d=p.review(make(issuer_type=kind))
    assert d["classification_proposal"]=="EXCLUDE_CEF_OR_FUND_BY_USER_POLICY"


@pytest.mark.parametrize("security",["PREFERRED","WARRANT","RIGHT","UNIT","DEBT","BOND","ETF","ETN"])
def test_noncommon_class_excluded_for_reit_bdc_and_regular_company(security):
    for issuer in ("REIT","BDC","OPERATING_COMPANY"):
        d=p.review(make(issuer_type=issuer,listed_class=security))
        assert d["classification_proposal"]=="EXCLUDE_NONCOMMON_INSTRUMENT"
        assert d["release_authorization"]=="DENY"


def test_bdc_closed_end_overlap_must_not_be_excluded_from_n2_wording_alone():
    d=p.review_overlap(n54a_current_verified=True,closed_end_n2_verified=True,
                       common_verified=True,ticker="EXAM",mic="XNYS")
    assert d["classification_proposal"]=="PROVISIONAL_POLICY_CANDIDATE_NOT_APPROVED"
    d=p.review_overlap(n54a_current_verified=False,closed_end_n2_verified=True,
                       common_verified=True,ticker="EXAM",mic="XNYS")
    assert d["classification_proposal"]=="EXCLUDE_CEF_OR_FUND_BY_USER_POLICY"


def test_unverified_or_conflicting_class_blocks():
    assert p.review(make(issuer_status_verified=False))["classification_proposal"]=="HOLD_EVIDENCE_REQUIRED"
    assert p.review(make(listed_class_verified=False))["classification_proposal"]=="HOLD_EVIDENCE_REQUIRED"
    assert p.review(make(issuer_type="SPAC",listed_class="CLASS_A_ORDINARY_SHARES"))["classification_proposal"]=="HOLD_POLICY_OR_EVIDENCE_CONFLICT"
    assert p.review(make(mic="OTC"))["classification_proposal"]=="EXCLUDE_VENUE_OUT_OF_SCOPE"


def test_forged_reviewer_or_security_master_claim_rejected():
    with pytest.raises(p.PolicyInputError):
        p.review(make(independent_reviewer_approved=True))
    with pytest.raises(p.PolicyInputError):
        p.review(make(security_identity_verified=True))


def test_no_boolean_sentinels_or_unknown_categories():
    with pytest.raises(p.PolicyInputError):
        p.review(make(issuer_status_verified=1))
    with pytest.raises(p.PolicyInputError):
        p.review(make(issuer_type="CEF_BDC_AUTO_APPROVED"))
