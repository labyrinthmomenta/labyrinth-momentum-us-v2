# A6a — US Momentum V2 isolated staging / production-preflight contract

## Clarification: two independent repositories, two independent production targets

`labyrinthmomenta/labyrinth-momentum-us-v2` is its own GitHub repository with its own future US production **database, scheduler, price sources, universe publisher, releases, monitoring, access approvals**. It does not use the BIST V2 production runtime. **This A6a step creates no production DB and deploys no US service.** No cross-repository checkout, data migration or runtime access.

**Proposed US-only namespace (not created):** `data/us_v2/labyrinth_us.db` and `data/us_v2/releases/`. A6a only writes a **disposable dry-run result** to `runtime/us_v2_staging/a6a/` in GitHub Actions. It accepts `US_V2_ENVIRONMENT=staging`, `US_V2_PRODUCTION=0`, and repository `labyrinthmomenta/labyrinth-momentum-us-v2` only; BIST data paths and production environment values are blocked.

## Source-integrity / readiness gates

| Frozen official gate | SHA256 |
|---|---|
| A5r 13,287-listed / 5,566-DENY release readiness result | `19bf7052c3b1b2d9c1b306076302aca5b868d4d5f7cb58e4828685889a9e7ac6` |
| A5u 40 post-financial SEC 8-K + 17 N-54A original documents audited, no legal-status approval | `e194403fe11d34565b28fbae07f91453e180532dfa08c023176fa759d1c4f443` |

[Successful US-only staging preflight — 352 tests](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38955193175); [US V2 staging denial artifact](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38955193175/artifacts/12070242881).

**Current result**: `US_V2_STAGING_PREFLIGHT_DENIED_NO_PRODUCTION`. 13,287 frozen official listing source records; 4,556 provisional INCLUDE, 1,010 REVIEW_REQUIRED, 7,721 excluded. 5,566 provisional/review candidates DENY, 0 ALLOW, no valid production manifest, independent approvals or price history readiness. SEC 8-K original 40/40 and N-54A original 17/17 verified as **source evidence**; current BDC legal status **not independently approved**, 40 8-K exhibits not reviewed, LIEN–REFI pending.

## Concrete subsequent independent US implementation milestones

1. **Authoritative listed security master and issuer-type/status authority:** exact current REIT/BDC/CEF distinctions, pay class and MIC, permanent ID, event history and point-in-time availability. LIEN/REFI hold remains. CEF excluded, REIT/BDC ordinary candidates allowed by user policy, subject to evidence.
2. **Independent signed human decision ledger and production release gate:** two roles/reviewer and publisher, immutable decision audit, unknown/missing fail closed. A5r is an OFFLINE prototype; it is not a production control.
3. **US price source / OHLCV completeness:** approved licensed/datable US pricing data source and daily session calendar; don't infer missing daily data from TradingView 90-day average volume.
4. **Only after verified price data exists:** final fully completed session closing price **greater than $5**; 90 fully completed session mean of daily **Close × Volume** **greater than $1 million**, missing data fails; momentum/FIP calculations run in US system independently.
5. **US-only staging SQLite, output manifests, scheduler, observability:** separate namespace and release paths; explicit deployment approval after dry-run and rollback tests. This PR installs none of these services.

**Preservation:** no main merge; BIST repository untouched; no US live production database, scheduler, Yahoo/price feed, tradability, momentum/FIP calculation or universe publication changed. This is Draft A6a above Draft A5u.
