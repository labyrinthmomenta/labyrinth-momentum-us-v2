"""A5s user-approved US listed security scope policy, evidence gated.

Issuer type + EXACT security class + venue are independent. BDCs are an
explicit exception to the generic CEF exclusion, not an auto-approval.
Policy review output is never production eligibility or an A4 mutation.
"""
from __future__ import annotations
from dataclasses import dataclass

POLICY_VERSION="2026-10-16-cef-out-reit-bdc-common-conditional"
ACCEPTED_MIC=frozenset(("XNAS","XNYS","XASE"))
BLOCKED_CLASS=frozenset(("PREFERRED","UNIT","WARRANT","RIGHT","DEBT","BOND","ETF","ETN"))
COMMON=frozenset(("COMMON_STOCK","COMMON_SHARES","ORDINARY_SHARES","CLASS_A_ORDINARY_SHARES"))
ISSUER=frozenset(("OPERATING_COMPANY","REIT","BDC","CEF","ETF_ISSUER","OTHER_FUND","SPAC","UNKNOWN"))
SECTYPES=COMMON|BLOCKED_CLASS|frozenset(("UNKNOWN",))


class PolicyInputError(ValueError):
    pass


@dataclass(frozen=True)
class Evidence:
    ticker: str
    mic: str
    issuer_type: str
    listed_class: str
    issuer_status_verified: bool
    listed_class_verified: bool
    security_identity_verified: bool=False
    independent_reviewer_approved: bool=False


def review(e:Evidence)->dict:
    if not isinstance(e,Evidence) or not e.ticker or e.issuer_type not in ISSUER or e.listed_class not in SECTYPES:
        raise PolicyInputError("Untrusted security identity, issuer category or class")
    if type(e.issuer_status_verified)!=bool or type(e.listed_class_verified)!=bool:
        raise PolicyInputError("Evidence verification flags must be boolean")
    if e.security_identity_verified or e.independent_reviewer_approved:
        raise PolicyInputError("No independent security master or signer connected")
    status="HOLD_EVIDENCE_REQUIRED"
    if e.mic not in ACCEPTED_MIC:
        status="EXCLUDE_VENUE_OUT_OF_SCOPE"
    elif e.listed_class_verified and e.listed_class in BLOCKED_CLASS:
        status="EXCLUDE_NONCOMMON_INSTRUMENT"
    elif not e.issuer_status_verified or not e.listed_class_verified:
        status="HOLD_EVIDENCE_REQUIRED"
    elif e.issuer_type in ("CEF","ETF_ISSUER","OTHER_FUND"):
        status="EXCLUDE_CEF_OR_FUND_BY_USER_POLICY"
    elif e.issuer_type in ("REIT","BDC","OPERATING_COMPANY") and e.listed_class in COMMON:
        status="PROVISIONAL_POLICY_CANDIDATE_NOT_APPROVED"
    else:
        # SPAC Class A, ADR, issuer unknown / contradictory proof remain held
        status="HOLD_POLICY_OR_EVIDENCE_CONFLICT"
    return {
        "ticker":e.ticker,"mic":e.mic,"policy":POLICY_VERSION,
        "classification_proposal":status,
        "issuer_type_evidence":e.issuer_type,
        "listed_class_evidence":e.listed_class,
        "independent_security_id_approved":False,
        "release_authorization": "DENY",
        "production_eligible":False,
        "source_A4_decision_unchanged":True,
    }


def review_overlap(*,n54a_current_verified:bool, closed_end_n2_verified:bool,common_verified:bool, ticker:str,mic:str)->dict:
    """BDC may be a legal closed-end investment company; require separate current election proof."""
    issuer="BDC" if n54a_current_verified else "CEF" if closed_end_n2_verified else "UNKNOWN"
    # Closed-end and BDC evidence are not mutually exclusive. An N-2
    # descriptor by itself MUST NOT override a positively proven BDC election.
    return review(Evidence(ticker=ticker,mic=mic,issuer_type=issuer,
        listed_class="COMMON_STOCK" if common_verified else "UNKNOWN",
        issuer_status_verified=n54a_current_verified or closed_end_n2_verified,
        listed_class_verified=common_verified))
