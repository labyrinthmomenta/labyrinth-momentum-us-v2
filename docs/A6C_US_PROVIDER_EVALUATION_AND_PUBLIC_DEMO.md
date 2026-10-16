# A6c — Real US daily OHLCV provider due diligence and bounded public demo

**As-of of requested bars:** 2026-10-14 (historical requested end, **NOT** proved historical known_at). **Retrieved:** 2026-10-16 UTC. **Status:** `PUBLIC_DOCS_EVALUATION_NOT_PRODUCTION_APPROVAL`; US production/feed publication remains DENY. GitHub tests **405 passed** on the source/demo capture run.

## Independent official vendor documentation and shortlist

| Vendor | Verifiable primary-vendor capabilities | Basis/licensing/scope concern | Staging decision |
|---|---|---|---|
| [Tiingo EOD](https://www.tiingo.com/documentation/end-of-day) | `open/high/low/close/volume`, separate `adjOpen/adjHigh/adjLow/adjClose/adjVolume`, `divCash` and `splitFactor`; end-of-day corrections as vendors update prices | Credentials needed. Raw vs adjusted **price AND volume** parity; correction/backfill; exact ticker class and MIC; licensing and completeness not proven | **First full US-data adjustment pilot candidate** |
| [Massive Stocks (formerly Polygon)](https://massive.com/stocks) and [split/dividend statements](https://polygon.io/knowledge-base/article/is-polygons-stock-data-adjusted-for-splits-or-dividends) | US aggregate stock data; default split-adjusted bars, `adjusted=false` for unadjusted. Splits/dividends via separate corporate-action API. Broad US active/delisted reference docs | No dividend-adjusted daily price in aggregates; must establish full total return using events. Need provider symbol→independent security ID + MIC validation; API key and terms | **Strong alternative whole-universe candidate** |
| [Alpaca historical bars](https://docs.alpaca.markets/us/reference/stockbars) and [IEX vs SIP](https://docs.alpaca.markets/us/docs/market-data-faq) | Multi-ticker historical bars, raw / split / dividend / spin-off / all options and PIT symbol rename `asof` | IEX represents **one venue** rather than consolidated SIP; inadequate for US share-volume completeness. SIP entitlement, source adjustment and class mapping still unverified | **Cross-check only with SIP entitlement** |
| [EODHD EOD historical API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes) and [delisted coverage](https://eodhd.com/financial-apis/delisted-stock-companies-data-2) | Raw daily OHLC, split+dividend-adjusted `adjusted_close`, split-adjusted daily `volume`; public DEMO on AAPL.US and TSLA.US | **Raw price vs split-adjusted volume is not a compatible price-volume basis**: historical `raw close × volume` is unsafe across splits; `adjusted_close × volume` also incorporates cash dividends. .US is provider exchange *aggregate code*, not XNAS/XNYS/XASE MIC | **Read-only connectivity and schema verification only** |

Vendor claims are **documentation statements**, not independent verified data rights. We did not connect a Tiingo, Massive, or Alpaca personal account or claim full source coverage. Do not purchase, subscribe, or supply any secret through the repository or conversation solely on this report.

### Publicly advertised price snapshot (not an account entitlement)

[Massive Stocks pricing](https://massive.com/pricing?product=stocks) (checked 2026-10-16): Basic **$0/mo, 5 calls/min and 2 years**, Starter **$29/mo, 5 years**, Developer **$79/mo, 10 years**, Advanced **$199/mo, 20+ years**, individual plans only. The business/redistribution terms differ and require their own written verification. Tiingo plan price was **not confirmed** from an official current pricing table. [EODHD demo/free coverage](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes): public no-signup demo for six symbols, free personal tier has stated daily limits, paid plans advertised from $19.99/mo; this does not establish production license or full US venue coverage. Alpaca SIP subscription/entitlement cost was not validated.

## Genuine no-credential demo connectivity test — succeeded

[Official A6c GitHub Actions live public-demo run](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38960932658), [receipt-only artifact](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38960932658/artifacts/12071968912). Full run: **405 offline regressions passed**, **2/2** actual EODHD documented public demo sources returned well-formed JSON. No user API token, subscription or account used.

| Official public DEMO symbol | Returned price rows | Source start/end | Raw response SHA256 |
|---|---:|---|---|
| AAPL.US | **303** | 2025-08-01 → 2026-10-14 | `1ead128857cd105a8641313d39b882bcbca45a23c07b8bdfa90b81e617ef7793` |
| TSLA.US | **303** | 2025-08-01 → 2026-10-14 | `6247b5b4389fe3bcc694372a5f9ec96151e54b68f8646efd298cf9dc9365f5f5` |

Receipt-only report SHA256: `c8d3029fc030e9c0777ed4574662147bfad3f1ff307e25caf90e73ec144b82ad`. The original demo response bytes were **not stored or redistributed** in GitHub or GitHub Actions. The SHA allows comparison if independently retrieved later, but since data can be revised and adjusted, a future different digest is not by itself a data-integrity failure or proof of corruption. The receipts include timezone-aware retrieved_at.

**Evidence significance**: 303 returned records per symbol exceed the **253 closing observations** required for 252 momentum returns. **NOT** proven: 303 actual NYSE/Nasdaq completed sessions, 90 verified contiguous completed sessions without missing holidays, current issuer/security_id mapping, trading availability, valid split-adjusted price×volume liquidity, dividend-adjusted total-return reconstruction, end-of-day revisions or data redistribution rights. No market indicator or investable signal computed from those real prices.

## Why the EODHD demo is not promoted

[EODHD's own adjusted/raw field declaration](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes) explicitly states `open/high/low/close` **raw**, `adjusted_close` **split and dividend adjusted**, while `volume` is **split adjusted**. Combining raw close with an already split-adjusted volume can mismeasure historical daily USD turnover around splits. The currently approved A6b liquidity calculation must use mutually consistent price and actual share-volume bases and verified historical sessions. Therefore EODHD base endpoint is **BLOCKED** from A6b tradability ingestion until separately reconciled.

Similarly, Massive split-adjusted aggregates do **not** establish a dividend-total-return price series. Tiingo raw and adjusted price/volume fields need independent cross-source validation against known splits, dividend dates and corrections before a source feed can be approved.

## Next US V2 A6d — explicit provider entitlements and test requirements

1. Start bounded **full-US provider-capability pilot**: Tiingo raw vs adjusted EOD plus corporate actions, Massive aggregate `adjusted=true/false` and splits/dividends; compare one representative XNAS/XNYS/XASE security each, and separate split/large cash dividend/rename/delist cases. **Only when authorized credentials become available.**
2. Verify vendor symbols vs independently approved security_id/MIC/class. Include NYSE American, REIT, BDC and Class A; do not turn ADR/CEF/SPAC exceptions into automatic production approvals. Do not pass security_id by ticker alias guess.
3. Obtain/version authentic NYSE/Nasdaq calendars for 253 consecutive completed sessions and abnormal/early closes; compare provider trading dates and source receipt timestamps, fail closed on missing sessions.
4. Confirm a valid paired share-volume and split-adjusted technical OHLCV series, plus independently supported total-return-adjusted close for Momentum/FIP. Backfill all impacted history after dividend or corporate action corrections; no tail patch over silently recomputed adjustment history.
5. Validate 90 separate completed-session **average of daily close×shares >$1m**, latest fully completed close **>$5**, strict; then US strategy rankings on full eligible cohort only, not a selected/demo subset. A5r production release remains 5,566 DENY/0 ALLOW.

**Never published:** No market data fetched through a paid account, no live US provider connected, no US production SQLite, scheduler, publisher or pricing/tradability calculation on a security. Main unchanged. Stacked Draft PR; BIST repository not relevant to this US-only production.
