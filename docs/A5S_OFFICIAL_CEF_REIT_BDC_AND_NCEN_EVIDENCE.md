# A5s — User-approved CEF exclusion / REIT and BDC verified common-share exception

**User policy decision:** 2026-10-16. **Frozen official universe as-of:** 2026-10-14. **SEC primary retrieval:** 2026-10-16. **Status:** review-only; no production publication.

## 1. Scope policy (user-approved)

| Listed instrument and issuer | Policy interpretation |
|---|---|
| Ordinary / Common shares of operating companies | Candidate, only after official listing class and security identity verification |
| **REIT ordinary/common shares** | **INCLUDE candidate** if issuer legal REIT status and exact listed share class verified |
| **BDC ordinary/common shares** | **INCLUDE candidate** if current BDC election/status and exact listed share class verified |
| **Closed-end investment fund (CEF), including fund common shares** | **EXCLUDE** subject to resolving whether issuer is instead a verified BDC under the explicit exception |
| ETF, ETN, preferred share, unit, warrant, right, debt / bond | **EXCLUDE** with verified instrument classification |
| SPAC Class A shares, ADR or unresolved legal classification | Hold, no policy invented |

**BDC carve-out is essential:** an N-2/closed-end description and a verified BDC election could coexist. Never automatically classify a verified BDC as excluded CEF. Conversely, REIT and BDC status does not validate a preferred share or another class. No self-asserted reviewer, guessed ticker, or SEC issuer CIK can grant a permanent security ID.

Policy module: `src/data/universe/a5s_scope_policy.py`; regressions: `tests/test_us_a5s_scope_policy.py`.

## 2. Real original SEC evidence chain

- A5o issuer sources 21/21 were pinned to original SEC `data.sec.gov` submissions and as-of dates. Source A5o review SHA256 `a7661fc8a154028b7b7a519f9fa89575472198cbc6a0054f27f31c704ccbe8f6`.
- A5s SEC primary capture: **20 original Form N-CEN** (each latest `filing_date <= 2026-10-14`) plus **one 2025 TVC Form 10-K**, 21/21 downloaded and raw SHA256 verified; metadata/primary original bytes archived. [A5s original SEC primary archive](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38917414012/artifacts/12053026547).
- Source receipt inventory SHA256: `c4649f4502e5d6ca81267ce1e3bd8c878c396bff655b9f57c5a5d5e6c312e149`.
- Original primary documents were independently parsed in [A5s final successful CI, 323 tests](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38918624087), [classification evidence table](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38918624087/artifacts/12053487005), JSON SHA256 `79732b5efde9fce7d501723c0655e7657ed155150beaa0bd654ba6f95b1ed10f`.

All SEC original primary documents include filing date, SEC issuer CIK, accession, direct SEC Archives URL, raw file bytes SHA256 and retrieval timestamp; no 2026-10-16 source is backdated as proven `known_at=2026-10-14`. SEC issuer self-report and official Nasdaq `otherlisted` still do not equal independently confirmed NYSE security master.

## 3. Type evidence by exact original SEC Form N-CEN

| Evidence class | Count | Symbols |
|---|---:|---|
| Form N-2 Filer (Closed-End Investment Company) label in original SEC N-CEN | **20** | BSTZ, GAB, GAM, TYG, BCX, BOE, GUT, ETO, VKQ, GGT, ETX, MPV, GRX, JHS, GGZ, JHI, ECAT, MCI, BTX, BMEZ |
| Same Form N-CEN Part D.1 security record confirms **common stock + exact ticker + NYSE** | **17** | BSTZ, GAB, GAM, BCX, BOE, GUT, ETO, VKQ, GGT, ETX, MPV, GRX, GGZ, ECAT, MCI, BTX, BMEZ |
| Part D.1 exact ticker but **venue differs** | **2** | JHS, JHI: SEC reports `ARCA DARK`; original A4 MIC = XNYS |
| Part D.1 original SEC **ticker differs** | **1** | TYG: SEC reports `XTYGX`, official A4 listing `TYG` |
| Original SEC 10-K explicitly describes NYSE `TVC`/`TVE` as PARRS and TVC bond-market context | **1** | TVC: debt/security-type review candidate, not ordinary company shares |

Examples: [BSTZ SEC N-CEN filing](https://www.sec.gov/Archives/edgar/data/1768666/000141036826025355/xslFormN-CEN_X01/primary_doc.xml), [GAB N-CEN](https://www.sec.gov/Archives/edgar/data/794685/000094040026009875/xslFormN-CEN_X01/primary_doc.xml), [TYG N-CEN](https://www.sec.gov/Archives/edgar/data/1268533/000089418926003668/xslFormN-CEN_X01/primary_doc.xml), [JHS N-CEN](https://www.sec.gov/Archives/edgar/data/759866/000119312526008411/xslFormN-CEN_X01/primary_doc.xml), [JHI N-CEN](https://www.sec.gov/Archives/edgar/data/759828/000119312526008413/xslFormN-CEN_X01/primary_doc.xml), [TVC Form 10-K](https://www.sec.gov/Archives/edgar/data/1376986/000137698625000056/tve-20250930.htm).

## 4. Decisions genuinely closed vs evidence closed

**21/21 original SEC primary sources collected and evaluated**, **20/20 N-CEN issuer-level closed-end form labels supported**, **17 exact filed NYSE common class ticker candidates**, **2 venue discrepancies and 1 ticker discrepancy explicitly unresolved**, **TVC debt/PARRS instrument type candidate**. The user has approved the CEF-vs-REIT/BDC scope policy.

**Zero final listed-security approvals.** The 20 source N-2 filer entries cannot be automatically declared definitively excluded CEF without addressing BDC election/status, official security identity and independent decision approval. Every row remains A4 provisional INCLUDE and holds a classification/reviewer decision. The original A4 inventory: **4,556 provisional INCLUDE, 1,010 REVIEW_REQUIRED, 7,721 EXCLUDE**. A5r offline fail-closed 5,566 DENY candidate gate is unchanged and production disconnected.

Remaining: authoritative current BDC election vs registered CEF classification; exact identity/venue discrepancies for TYG/JHS/JHI; complete classification for REIT/BDC ordinary classes across full universe; historical source known_at and effective_at, reviewer signing/approval, proper runtime publication gate; 90 completed session price×volume checks later and only with explicit permission.

**Protected:** `main`, BIST V2.0.1 production, US momentum/FIP, Yahoo price/ATR, 90-session tradability, SQLite production schema, publications, and any actual positions remain unchanged. PR stays **Draft** stacked above A5r.
