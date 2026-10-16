# A6b — US-only synthetic OHLCV, completed-session calendar and liquidity/indicator smoke

**Date:** 2026-10-16. **Scope:** Offline **SYNTHETIC** US V2 STAGING ONLY. **Publication:** DENY. **Real US price data acquired:** zero. **Independent calendar/security ID/provider approved:** zero.

## Evidence of completed tests

[A6b GitHub Actions source-pinned staging smoke — 390 tests successful](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38956866891).
[A6b synthetic-only fixture result artifact](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38956866891/artifacts/12071295585).

The workflow first downloads and checks the **A6a original US-only `DENY` preflight artifact**, including repo identity, candidate_DENY=5,566, ALLOW=0 and `production_database_created=false`. This does not activate any publisher.

## 90-session liquidity policy: implemented for strictly validated input mechanics

- Price threshold: **last fully closed session's close_USD > 5.00**, strict; exactly 5.00 fails.
- Dollar liquidity: mean of **the 90 most recently completed individual session's `Close_USD × Share_Volume`** strictly **> $1,000,000**; exactly $1m fails.
- Not a test of mean share volume; not TradingView's aggregate 90-day volume value. **No separate share-volume minimum**.
- Missing, duplicated, misdated, future, incomplete or non-final daily sessions/price bars must fail; zero volume counts as zero dollar volume (if a valid final bar), missing volume cannot be imputed as zero.
- Explicit `USD` currency, non-negative share count, positive finite OHLC values, correct high/low bounds, consistent adjustment basis for price and volume and fixed source over the window.
- Venue must be **XNAS / XNYS / XASE**. Session open and close timestamps must be timezone-aware; their local dates use `America/New_York` (IANA DST offsets, never a fixed UTC offset). Early-close flagged sessions count **one session**. Last session must exceed a bounded 15-minute observation grace before evaluation.
- **Critical caveat:** supplying a calendar is not the same thing as authenticating its official source and complete history; the validator checks internal consistency, **not** exchange calendar authority. An absent date in a fabricated calendar cannot be discovered without comparing to an official versioned calendar. Thus `final_tradability_approved=false` regardless of arithmetic success.

## US momentum/FIP engine compatibility — 253 synthetic bars

The synthetic fixture supplies **253 consecutively enumerated MOCK weekday sessions** (not a genuine historical NYSE/Nasdaq holiday schedule) to the existing core `src/calculation/engine.py`. It reproduces **252 daily returns**, 12-minus-1 core momentum using the first 231 returns of the final 252, a 21-session short swing layer, FIP and same-basis ATR14 compatibility.

**Do not mistake this for a verified real US momentum signal:** a synthetic weekday calendar can include market holidays. The existing engine consumes *one* OHLC series; a real US system still requires **separately verified total-return adjusted close** for momentum/FIP and **split-adjusted technical OHLC** for ATR/VCP, with split/dividend and other corporate-action reconciliation. Prior BIST engine tests do not prove source price adjustment parity for US stocks.

Fixture labels include `SYNTHETIC_FIXTURE_NOT_A_PRICE_PROVIDER`, `PROGRAMMATIC_WEEKDAY_ONLY_NOT_OFFICIAL_MARKET_CALENDAR`, `real_US_price_data_rows=0`, `US_publication_permission=DENY`. The synthetic early-close example is deliberately not claimed to be an actual early-close session.

## Next A6c: what must be selected before real data integration

1. **US daily OHLCV vendor and use/license terms** — coverage XNAS/XNYS/XASE; ticker/security identity and as-of history; available volume; delist/split/dividend; historic revisions; provider fair use; second source/parity policy. Yahoo may be a research candidate, **not pre-approved production**.
2. **Authoritative exchange calendar source and audit** — actual holidays, half-days, ad-hoc closure, DST, source version/known_at, and close finalization grace. No weekday fallback for historical gaps.
3. **Full adjustment semantics** — capture provider-native and split-adjusted technical OHLCV, cash/special dividends and total-return adjusted close *as distinct baselines*; verify prices and volume share basis, no double adjustment.
4. **Independent US security identity and scope gate** — CEF excluded, REIT/BDC verified common candidates per approved scope, issuer CIK != security_id; 1,010 REVIEW_REQUIRED and 4,556 provisional INCLUDE not yet authoritatively promoted.
5. **Staging 1→pilot→full universe** — start single verified listed class after resolving symbol/MIC and price/corporate-action history, then representative SPAC/REIT/BDC/excluded and halt/delist, then coverage/full universe. Human signed approval + production release and rollback will be separate.

## Protected boundaries

This branch does **not** create live US SQLite, scheduler, publisher or signals; `config/us.json` continues to disable production publication and tradability evaluation. No Yahoo/fetch vendor API calls. No external repo writes or branch merges. Main remains unchanged, all prior draft PRs remain draft, and A5r **5,566 DENY/0 ALLOW** remains in force. The synthetic smoke artifact is stored only for 90 days by GitHub Actions, not a permanent historical market-data archive.
