"""A5l: evidence-only security-class rows from frozen official SEC filings.

Class A ordinary shares are not the same words as 'Common Stock'; SEC
12(b) exact ticker-celled rows can support a candidate class. Do NOT
convert issuer CIK to a security ID, determine fund eligibility, or release.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata

from .a5k_sec_type_pilot import PILOT, FORM_ALLOW

VERSION="a5l-sec-listed-class-evidence-v1"
A5K_PILOT_SHA="e34c0fe0a2260a4d1a323591364ac9b509c1fc39ea49d9c9c40a4bc36c3d63ef"
A5K_UNIVERSE_SHA="e31bcca870189207e9273eea6ba4e48a55949e78822d2b7e8feb7fb3fc851a76"
KNOWN_MIC={"SPAC_OR_BLANK_CHECK":"XNAS","REIT_VS_FUND":"XNYS",
           "CLOSED_END_FUND_VS_BDC":"XNAS"}
SOURCE_SHAS={
 "nasdaqlisted":"2dc5b607a42c3eefe9cf6f7d6e681c30b8fb55bb51ae04d998cdf51af02d6694",
 "otherlisted":"12deeb989a1b515304eda04318a0af1db127ff6340d1055329c62d9a5cbcde28",
}
MAX_SEC_BYTES=64*1024*1024
TICKER=re.compile(r"[A-Z][A-Z0-9.-]{0,11}")
HASH=re.compile(r"[a-f0-9]{64}")
CLASS_PATTERNS=(
 ("CLASS_A_ORDINARY_SHARES",re.compile(r"\bclass\s+a\s+ordinary\s+shares?\b",re.I)),
 ("COMMON_STOCK",re.compile(r"\bcommon\s+stocks?\b",re.I)),
 ("COMMON_SHARES",re.compile(r"\bcommon\s+shares?\b",re.I)),
 ("PREFERRED_STOCK",re.compile(r"\bpreferred\s+(?:stock|shares?)\b",re.I)),
 ("UNIT",re.compile(r"\bunits?\b",re.I)),
 ("WARRANT",re.compile(r"\bwarrants?\b",re.I)),
 ("DEPOSITARY",re.compile(r"\bdepositary\s+(?:shares?|receipts?)\b",re.I)),
)
MARKET_WORDS=re.compile(r"\bnasdaq\b|\bnew\s+york\s+stock\s+exchange\b|\bnyse\b",re.I)


class SourceError(ValueError):
    pass


def _source(path:Path,digest:str)->tuple[dict,bytes]:
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=digest:
        raise SourceError(f"Source bytes differ: {path.name}")
    doc=json.loads(raw)
    if not isinstance(doc,dict):
        raise SourceError("Frozen source must be JSON object")
    return doc,raw


def _norm(s:str)->str:
    return " ".join(unicodedata.normalize("NFKC",s).replace("\u200b","").split())


class CellRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[]
        self.current_row=None
        self.cell_fragments=None
        self.current_cell=None

    def handle_starttag(self,tag,attrs):
        if tag=="tr":
            if self.current_row is None:
                self.current_row=[]
        elif tag in ("td","th") and self.current_row is not None:
            if self.cell_fragments is None:
                self.cell_fragments=[]

    def handle_data(self,data):
        if self.cell_fragments is not None:
            self.cell_fragments.append(data)

    def handle_endtag(self,tag):
        if tag in ("td","th") and self.cell_fragments is not None:
            self.current_row.append(_norm(" ".join(self.cell_fragments)))
            self.cell_fragments=None
        elif tag=="tr" and self.current_row is not None:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row=None


def extract_security_rows(raw:bytes,*,ticker:str,mic:str)->list[dict]:
    """Only ticker in its own <td> cell, class and exchange adjacent."""
    if (not isinstance(raw,bytes) or not 200<=len(raw)<=MAX_SEC_BYTES
            or not TICKER.fullmatch(ticker) or mic not in ("XNAS","XNYS")):
        raise SourceError("Invalid source, listing ticker or MIC")
    if b"access denied" in raw[:600].lower():
        raise SourceError("SEC HTML access denied")
    parser=CellRows()
    parser.feed(raw.decode("utf-8",errors="replace"))
    found=[]
    # Registration cover table is at the beginning of 10-Q. Limit to 100
    # rows to avoid other, non-security figures and unrelated company data.
    for row_no,cells in enumerate(parser.rows[:100]):
        indexes=[i for i,v in enumerate(cells) if _norm(v).upper()==ticker]
        for i in indexes:
            earlier=" ".join(cells[max(0,i-2):i])
            later=" ".join(cells[i+1:i+3])
            title=_norm(earlier)
            exchange=_norm(later)
            if not MARKET_WORDS.search(exchange):
                continue
            if mic=="XNAS" and "nasdaq" not in exchange.casefold():
                continue
            if mic=="XNYS" and not (
                    "new york stock exchange" in exchange.casefold()
                    or re.search(r"\bnyse\b",exchange,re.I)):
                continue
            types=[name for name,pattern in CLASS_PATTERNS if pattern.search(title)]
            if not types:
                continue
            # Class A ordinary shares can be "included as part of the
            # units"; unit mention is a qualification, not reclassification.
            if "CLASS_A_ORDINARY_SHARES" in types:
                main="CLASS_A_ORDINARY_SHARES"
            elif "COMMON_STOCK" in types:
                main="COMMON_STOCK"
            elif "COMMON_SHARES" in types:
                main="COMMON_SHARES"
            elif "PREFERRED_STOCK" in types:
                main="PREFERRED_STOCK"
            elif "WARRANT" in types:
                main="WARRANT"
            elif "UNIT" in types:
                main="UNIT"
            elif "DEPOSITARY" in types:
                main="DEPOSITARY"
            else:
                main="CLASS_NOT_RESOLVED"
            found.append({
                "table_row_index":row_no,
                "ticker_cell":ticker,
                "security_title_cell_candidate":title[:400],
                "exchange_cell_candidate":exchange[:150],
                "main_class_wording":main,
                "qualifier_mentions_units":("UNIT" in types),
                "all_title_wording_clues":types,
                "share_class_approved":False,
                "security_id":None,
            })
    unique={(v["security_title_cell_candidate"],v["ticker_cell"],
             v["exchange_cell_candidate"]):v for v in found}
    return list(unique.values())


def build(a5k_root:Path, full_root:Path)->dict:
    previous,_=_source(a5k_root/"a5k-sec-pilot-evidence.json",A5K_PILOT_SHA)
    universe,_=_source(full_root/"a5k-full-universe-deny.json",A5K_UNIVERSE_SHA)
    if (previous.get("status")!="OFFICIAL_SEC_PILOT_REVIEW_ONLY"
            or previous.get("pilot_size")!=9
            or previous.get("official_primary_filings_verified")!=9
            or previous.get("listed_security_id_approved")!=0
            or previous.get("instrument_type_decisions_completed")!=0
            or previous.get("production_eligible") is not False
            or len(previous.get("records",[]))!=9):
        raise SourceError("A5k SEC pilot was not a verified review-only source")
    if (universe.get("status")!="FULL_UNIVERSE_SOURCE_REPLAY_DENY_ONLY"
            or universe.get("candidate_DENY")!=5566
            or universe.get("candidate_ALLOW")!=0
            or universe.get("all_source_listings_checked")!=13287
            or len(universe.get("review_records",[]))!=13287
            or universe.get("connected_to_production") is not False):
        raise SourceError("A5k full universe source hold not verified")
    bykey={}
    for r in universe["review_records"]:
        key=(r["symbol"],r["mic"])
        if key[0] in PILOT:
            if key in bykey:
                raise SourceError("Ambiguous listing ticker and MIC")
            bykey[key]=r
    if len(bykey)!=9:
        raise SourceError("Nine official listings missing")
    records=[]
    seen=set()
    counts=Counter()
    for r in previous["records"]:
        ticker=r["ticker"]
        if ticker in seen or ticker not in PILOT:
            raise SourceError("Unexpected or duplicate frozen pilot ticker")
        seen.add(ticker)
        cik,group=PILOT[ticker]
        mic=KNOWN_MIC[group]
        directory=bykey.get((ticker,mic))
        if (not directory or directory.get("original_a4_decision")!="REVIEW_REQUIRED"
                or directory.get("release_result")!="DENY_OFFICIAL_SECURITY_TYPE_UNAPPROVED"
                or directory.get("release_eligible") is not False
                or directory.get("listing_source_sha256")!=SOURCE_SHAS[directory["source"]]
                or r.get("cik")!=cik
                or r.get("category_for_manual_review")!=group
                or r.get("status")!="SEC_ISSUER_FILING_CAPTURED_REVIEW_ONLY"
                or r.get("production_eligible") is not False
                or r.get("source_security_identity_approved") is not False):
            raise SourceError("SEC issuer/official listing crosswalk was altered")
        meta=r["metadata"]
        if not HASH.fullmatch(meta["metadata_sha256"]):
            raise SourceError("No SEC original metadata SHA")
        _source(a5k_root/r["metadata_raw_filename"],meta["metadata_sha256"])
        filing=r["primary_source"]
        obs=r["primary_observation"]
        if (filing!=meta["candidate_filing"]
                or filing["form"] not in FORM_ALLOW[group]
                or filing["filing_date"]>"2026-10-14"
                or not HASH.fullmatch(obs["source_sha256"])
                or obs["title_class_security_id_verified"] is not False):
            raise SourceError("SEC form/source or type approval unexpectedly changed")
        original=(a5k_root/r["primary_raw_filename"]).read_bytes()
        if (sha256(original).hexdigest()!=obs["source_sha256"]
                or len(original)!=obs["source_bytes"]):
            raise SourceError("Original SEC primary filing checksum mismatch")
        if filing["form"] in ("10-Q","10-K"):
            candidates=extract_security_rows(original,ticker=ticker,mic=mic)
            if len(candidates)==1:
                class_evidence="SEC_SECTION_12B_CLASS_ROW_CANDIDATE"
                counts[candidates[0]["main_class_wording"]]+=1
            elif not candidates:
                class_evidence="SEC_SECTION_12B_ROW_NOT_FOUND_NOT_NEGATIVE"
            else:
                class_evidence="AMBIGUOUS_MULTIPLE_SEC_ROWS"
        else:
            candidates=[]
            if filing["form"] not in ("N-CSRS","N-CSR","N-2","N-2/A","N-CEN"):
                raise SourceError("Unexpected SEC nonfinancial form")
            class_evidence="SEC_N_CSRS_FUND_ISSUER_REPORT_NOT_LISTED_CLASS"
            counts["N_CSRS_ISSUER_REPORT_ONLY"]+=1
        records.append({
            "ticker":ticker,"mic":mic,"cik":cik,"issuer_category_for_review":group,
            "a4_security_name":directory["name"],
            "official_directory_sha256":directory["listing_source_sha256"],
            "sec_form":filing["form"],"filing_date":filing["filing_date"],
            "sec_accession":filing["accession"],"sec_url":filing["document_url"],
            "sec_primary_sha256":obs["source_sha256"],
            "sec_metadata_sha256":meta["metadata_sha256"],
            "source_retrieved_at":r["primary_retrieved_at"],
            "class_evidence":class_evidence,
            "same_row_candidates":candidates,
            "security_id":None,
            "legal_issuer_type_approved":False,
            "listed_class_approved":False,
            "known_at_as_of_proven":False,
            "human_review_complete":False,
            "a4_decision_unchanged":"REVIEW_REQUIRED",
            "production_eligible":False,
        })
    if seen!=set(PILOT):
        raise SourceError("Pilot issuer inventory changed")
    class_rows=[r for r in records if r["class_evidence"]=="SEC_SECTION_12B_CLASS_ROW_CANDIDATE"]
    if len(class_rows)!=6 or counts["CLASS_A_ORDINARY_SHARES"]!=3 or counts["COMMON_STOCK"]!=3:
        raise SourceError("Unexpected SEC class row evidence population")
    return {
        "status":"SEC_LISTED_CLASS_ROWS_REVIEW_ONLY",
        "version":VERSION,"as_of":"2026-10-14",
        "source_pilot_sha256":A5K_PILOT_SHA,
        "source_universe_sha256":A5K_UNIVERSE_SHA,
        "source_count":9,"same_row_class_candidates":len(class_rows),
        "class_wording_counts":dict(sorted(counts.items())),
        "fund_issuer_only_not_security_id":3,
        "review_required":9,
        "final_security_class_approvals":0,
        "final_security_type_approvals":0,
        "production_approvals":0,
        "production_eligible":False,
        "known_at_2026_10_14_established":False,
        "release_gate_updated":False,
        "records":records,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5k-sec",type=Path,required=True)
    p.add_argument("--a5k-universe",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        d=build(args.a5k_sec,args.a5k_universe)
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/"a5l-listed-class-evidence.json").write_text(
            json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({k:v for k,v in d.items() if k!="records"},
                         ensure_ascii=False,indent=2))
        return 0
    except (ValueError,TypeError,KeyError,OSError) as exc:
        print(f"A5L_BLOCKED: {type(exc).__name__}: {exc}")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
