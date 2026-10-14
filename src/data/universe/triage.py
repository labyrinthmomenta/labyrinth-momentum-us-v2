"""Provisional instrument evidence requirements; never approves a security."""
EVIDENCE_BY_REASON = {
    "UNKNOWN_EXCHANGE_CODE": ("OFFICIAL_VENUE_MAPPING", "INSTRUMENT_TYPE", "SHARE_CLASS"),
    "CROSS_SOURCE_SYMBOL_COLLISION": ("OFFICIAL_LISTING_IDENTITY", "INSTRUMENT_TYPE", "SHARE_CLASS"),
    "FINANCIAL_STATUS_REVIEW": ("EXCHANGE_FINANCIAL_STATUS", "INSTRUMENT_TYPE", "SHARE_CLASS"),
    "TYPE_UNCONFIRMED": ("OFFICIAL_INSTRUMENT_TYPE", "SHARE_CLASS"),
    "FUND_NAME_REQUIRES_TYPE_EVIDENCE": ("FUND_VS_COMMON_REIT_EVIDENCE", "SHARE_CLASS"),
    "SPAC_BDC_OR_FINANCIAL_REVIEW": ("SPAC_BDC_POLICY_DECISION", "OFFICIAL_INSTRUMENT_TYPE", "SHARE_CLASS"),
    "SEC_IDENTITY_AMBIGUOUS": ("ISSUER_IDENTITY_SOURCE", "OFFICIAL_INSTRUMENT_TYPE", "SHARE_CLASS"),
}
HIGH_PRIORITY = frozenset({"UNKNOWN_EXCHANGE_CODE", "CROSS_SOURCE_SYMBOL_COLLISION",
                           "SEC_IDENTITY_AMBIGUOUS"})


def triage_record(row: dict) -> dict:
    """Only annotate requirements; preserve source decision and eligibility."""
    decision, reason = row["decision"], row["reason"]
    if decision == "EXCLUDE":
        return {"status": "OUT_OF_SCOPE", "priority": None, "required_evidence": []}
    if decision == "INCLUDE":
        return {"status": "PROVISIONAL_ONLY", "priority": 3,
                "required_evidence": ["OFFICIAL_INSTRUMENT_TYPE", "SHARE_CLASS",
                                      "LISTING_IDENTITY"]}
    if decision != "REVIEW_REQUIRED":
        raise ValueError("Unrecognized directory decision")
    return {"status": "EVIDENCE_REQUIRED", "priority": 1 if reason in HIGH_PRIORITY else 2,
            "required_evidence": list(EVIDENCE_BY_REASON.get(
                reason, ("OFFICIAL_INSTRUMENT_TYPE", "SHARE_CLASS", "LISTING_IDENTITY")))}
