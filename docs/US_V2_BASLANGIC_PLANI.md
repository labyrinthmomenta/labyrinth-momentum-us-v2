# Labyrinth Momentum US V2 — başlangıç ve mimari karar taslağı

İnceleme: 14 Ekim 2026. Bu belge aşama 0 çıktısıdır; tasarım kararları ile
uygulanmış özellikleri ayırır. Canlı US veri hattı henüz kurulmadı.

## 1. Kaynak sabitleme ve US V1 envanteri

GitHub bağlantısıyla iki deponun dosya ağaçları ve aşağıdaki kritik kaynaklar okundu.
BIST production deposuna yazma yapılmadı.

- [US V1 sabit referans](https://github.com/labyrinthmomenta/us-momentum-screener/tree/5b27dea70365d15964b5d3c0bff37cbe26a64422)
- [BIST V2.0.1 sabit referans](https://github.com/labyrinthmomenta/labyrinth-momentum-v2/tree/c62d3d3a0bf41eaad4082373bb6c46a650a646fc)

| V1 bileşeni | Gözlenen işlev / teknik borç | V2 yaklaşımı |
|---|---|---|
| `engine_us.py` | Excel günlük yüzde getirilerini okuyor; 2000. satır sınırı var; ticker anahtar | SQLite OHLCV ve kalıcı security_id |
| `engine_us.py::calc_fip_monthly` | `mom * (neg/N-pos/N)` | `sign(mom)*(neg-pos)/N` |
| `engine_us.py::compute_all` | Yıllık FIP aylık FIP ortalaması; en az bir ay yeterli | Aynı core return penceresinde FIP; eksik veri NULL |
| Aynı core momentum | İçinde bulunulan aydan 13 ay önceki ay sonu → bir ay önceki ay sonu; gerçek son 21 seansı atlamıyor | 252 return içinden son 21 çıkarılır: 231 return |
| Aylık hesaplar | Mevcut gözlemleri çarpıyor; tam seans kapsamı kontrolü yok; partial etiketi 15 güne bağlı | Resmi seanslarla tamlık ve tamamlanmış ay kontrolü |
| `fetch.py` | yfinance, auto_adjust=True, actions=False; sadece Close getirileri; 7 günlük overlap | Kaynak OHLCV + action/factor provenance; revision denetimi |
| `fetch.py` | Per-ticker son tarih sonrasını alıyor; geçmiş iç boşluklar ve eski adjustment değişiklikleri yakalanmayabilir | İç boşluk taraması, overlap reconciliation, kontrollü backfill |
| `fetch_initial.py` | Statik tickers.json; Excel başlangıcı; 26×31 günlük yaklaşık aralık | Sürümlü resmi evren ve seans tabanlı başlangıç |
| `update_excel.py` | Dosyayı doğrudan kaydediyor; transactional DB yok | Transaction, staging ve run_id |
| `tickers.json` | Ticker/name/sector/market_cap; değişmez menkul kimliği ve tarih aralığı yok | Ayrı issuer/security/listing/identifier kayıtları |
| `strategies_us.py` | Sabit S/A eşikleri ve bonuslarla composite skor; `or 0` kullanımı; son aylık kayıt tamamlanmamış olabilir | BIST Core percentile; FIP quality ayrı; tamamlanmış ay bağlamı |
| `build_site.py` | Doğrudan detail/stocks/meta yazımı; manifest/gate yok | Tam snapshot staging ve tek release aktivasyonu |
| `run.py` | Screener günlük, strateji Cuma; çalışma tarihi ile veri tarihi karışabiliyor | Aynı as_of/run_id; generated_at ayrı |
| `.github/workflows/update.yml` | 21:00 UTC, Cuma ek 21:30; concurrency yok; Excel/log/site Git'e yazılıyor | Seans kapanışı + grace period kontrolü; tek yazar; runtime ayrı |
| `requirements.txt` | Alt sınırlar; workflow doğrudan pinsiz paket kuruyor | Test edilmiş sabit bağımlılıklar |

Dosya ağacında test paketi görülmedi. İki workflow (`initial_fetch`, `update`),
Python betikleri, Excel, CSV, iki HTML şablonu, üretilmiş site/detail JSON'ları,
tickers.json ve loglar mevcut. Excel dosyası ağaçta 8.485.603 byte; binary içeriği
bu aşamada okunmadı. CSV ve tüm detail kayıtlarının sayısal yeniden üretimi yapılmadı.
Bu nedenle tablo kaynak kod incelemesidir, tamamlanmış tarihsel veri audit'i değildir.
V1'de bulunan TCEHY/ADYEY gibi semboller ve fon isimli kayıtlar, yeni evrenin
ayrı sınıflandırılmasını gerektirir; yalnız ticker adına bakıp tür kesinleştirmeyiz.

## 2. BIST V2'den taşıma haritası

| Kaynak modül | Karar | US için gereken kontrol |
|---|---|---|
| `src/indicators/{momentum,fip,atr,acceleration}.py` | Bu aşamada aynen taşındı | Girdi fiyat bazının açık olması |
| `src/calculation/engine.py` | Bu aşamada aynen taşındı | Önünde US takvim/kalite gate'i zorunlu |
| `src/strategy/{features,ranking}.py` | Sonraki aşamada port | VIOP alanları çıkarılacak; sector provenance; security_id anahtar |
| `technical_prices`, `technical_price_adapter`, `swing_*`, `vcp_*` | Algoritma ve testleri port adayı | Split-adjusted OHLCV, US seansları, config ayrımı |
| `src/data/storage/*` | Şema ve transaction prensipleri referans | US issuer/listing/action/version modeli; BIST DB kopyalanmaz |
| `src/data/universe/{manager,official}.py` | İş akışı örneği | KAP/BIST ayrıştırıcıları yerine US kaynakları |
| `src/data/{calendar,calendar_store}.py` | Store prensibi korunur | Venue-aware US takvimi |
| `src/data/providers/{base,yahoo}.py` | Sözleşme/batching/reconciliation referansı | `.IS`, benchmark ve US symbol mapping ayrımı |
| `src/pipeline/{update,adjustment_backfill,preflight,daily}.py` | Kontrol akışı port | US corporate actions ve kaynak politikası |
| `src/output/publication.py`, reporting, web | Yayın contract'ı/UI yaklaşımı | USD, New York as_of; VIOP yok; release manifest hash |
| `src/research/vcp_*` | Araştırma sınırı ve protokol port | Yeni US cohort; yeni freeze; BIST sonuçları aktarılmaz |
| `bist_thb.py`, BIST/KAP kaynakları, VIOP, BIST runtime DB | Taşınmaz | US eşdeğeri ayrıca tasarlanır |

Dosya adları envanterden; tüm port adayları satır satır denetlenmiş değildir.
Taşınan çekirdek ve testler `migration/provenance.json` ile blob bazında kayıtlıdır.
BIST'in 511 testlik önceki release bilgisi US test sonucu olarak sunulmaz.

Hesaplama sözleşmesi: M_N=∏(1+r)-1, N=252/126/63/21.
Core 12-1, son 252 return'ün son 21'i çıkarılmış 231 return'üdür; 253 kapanış gerekir.
FIP aynı pencereye uygulanır; flat günler paydada kalır.
Wilder ATR14/Close×100; ΔMom=M21−M63 ve ΔFIP=FIP21−FIP63.
Core ranking momentum percentile; FIP quality ayrı. Rejim ve kısa vade delta
Core sırasını değiştirmez. 1M, M21'den ayrı tamamlanmış takvim ayıdır.

## 3. Yeni repo ve yapı

Öneri: `labyrinthmomenta/labyrinth-momentum-us-v2`.
Bağımsız repo, BIST production'dan ayrı; başlangıçta ortak paket çıkarılmayacak.

```text
src/indicators/          # mevcut: BIST saf çekirdek
src/calculation/         # mevcut: gözlem bazlı motor
src/data/universe/       # plan: Nasdaq + sınıflandırma + SEC enrichment
src/data/calendar/       # plan: venue, session, close_utc, revisions
src/data/providers/      # plan: capabilities, raw snapshots, mapping
src/data/storage/        # plan: migration, identity, bars, actions, runs
src/pipeline/            # plan: preflight → ingest → validate → stage
src/strategy/            # plan: ranking/context/VCP
src/output/              # plan: manifest, JSON/CSV, immutable releases
src/research/            # plan: US OOS; production'dan ayrılmış
config/us.json           # mevcut: yayın kapalı tasarım ayarları
tests/                   # mevcut: taşınan core testleri
migration/provenance.json
docs/US_V2_BASLANGIC_PLANI.md
.github/workflows/validation.yml  # yalnız offline test
runtime/                 # Git dışında: DB, raw, staging, backups
```

Plan satırları uygulanmış modül değildir. İskelette publisher veya downloader yok.
Başlangıç commitleri önce çekirdek/provenance, sonra tasarım/config/CI olarak ayrılacak.
GitHub bağlayıcısında repo oluşturma aracı bulunmuyor; yerel GitHub CLI da yok.
Bu nedenle yerel ayrı Git deposu hazırlanır; uzak repo oluşturulduğu iddia edilmez.

## 4. Authoritative universe tasarımı

Nasdaq Trader `nasdaqlisted.txt` ve `otherlisted.txt` liste üyeliğinin başlangıç
kaynağıdır. İki ham dosya birlikte, URL/download time/source creation time/SHA256
ile saklanır. Başlık, footer, satır sayısı ve duplicate kontrolleri geçmeden snapshot
kabul edilmez. Eski ya da çelişkili dosya yeni evren üretmez.
[Resmi alan tanımları](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs).

Önerilen kapsam: Nasdaq, NYSE, NYSE American adi hisseleri; ortaklığın ülkesi
değil US primary listing esas. Common REIT hisseleri dahil. ADR/ADS, preferred,
ETF/ETN, fon, warrant/right/unit, test issue, OTC ve when-issued kayıtlar ilk
scope dışında. SPAC common ve BDC gibi sınır türler ilk aşamada review kuyruğuna;
politika açıkça onaylanıp sürümlenmeden otomatik kabul edilmez.

ETF=N tek başına common stock kanıtı sayılmaz. Açık security-name/type kanıtı,
exchange referansı ve gerektiğinde issuer filing birlikte tutulur. Sonuçlar:
INCLUDE / EXCLUDE / REVIEW_REQUIRED + reason + evidence + policy_version.
Belirsizlerin sayısı dashboard/manifest'te görünür; sessizce tam evren denmez.
Ad desenleri yalnız yardımcıdır. Kaynaklar türü kesin ayıramazsa lisanslı security
master veya kaynaklı manuel karar gerekir. Ek borsalar sessizce kapsam içine alınmaz.

SEC CIK/ticker/exchange dosyası issuer eşleştirmesine yardımcıdır, evrenin tek
otoritesi değildir. CIK eksikliği otomatik delist değildir; CIK security_id değildir.
[SEC dosyası](https://www.sec.gov/file/company-tickers-exchange).
GOOG/GOOGL gibi share class'lar ayrı security_id alır. Resmi ve provider symbol'leri
ayrı tutulur; nokta/tire dönüşümü genel ve kayıpsız bir kuralmış gibi uygulanmaz.

Snapshot üyeliği observed_at ve effective_at ayrımıyla saklanır. Bugünkü dizin
geçmiş evreni ispatlamaz. Arşiv öncesi backtest açıkça survivorship-limited diye
etiketlenir. Tek günlük kaybolma delist kabul edilmez; resmi olay/ikinci doğrulama
beklenir. Liste churn eşiği baseline ölçümünden sonra config'e yazılır.

## 5. Trading calendar ve corporate actions

Calendar contract: venue/MIC, session_date, open_utc, close_utc, early_close,
source/version, known_at. Yerel saat `America/New_York`; UTC offset sabitlenmez.
Resmi [NYSE takvimi](https://www.nyse.com/trade/hours-calendars) ve Nasdaq duyuruları
doğrulama otoritesi; bir Python calendar kütüphanesi ancak bu kayıtlarla test edilen
uygulama olabilir. Yarım gün bir seanstır. Olağanüstü kapanışlar sürümlü override.
Takvim kapsama yılı bitince weekdays fallback yapılmaz, işlem durur.

as_of yalnız kapanmış seans olabilir; close + sağlayıcıya göre ölçülmüş grace period
ve bar finality kontrolü gerekir. Tatil günü yeni tarihli eski snapshot yayınlanmaz.
İlk canlı aşama manuel; sonraki cron yalnız tetikleyicidir, seans seçen otorite değildir.
IPO öncesi günler missing değildir. Halt günü işlem yoksa getiri sıfıra çevrilmez;
kalite nedeni kaydedilir, eksik seans hesaplamadan atılarak pencere sıkıştırılmaz.

Üç ayrı fiyat temsili: sağlayıcının native OHLCV kaydı, doğrulanmış split-adjusted
teknik OHLCV, total-return adjusted kapanış. Native veriye otomatik 'raw' denmez:
sağlayıcı split'i zaten uygulamış olabilir. Capabilities ve fixture ile kanıt gerekir.
Öneri: momentum/FIP total-return; ATR/VCP split-adjusted teknik seri. BIST adapter
semantiğiyle farklar golden fixture üzerinden migration raporunda açıklanacak.

Split oranı q=new/old: gerçekten unadjusted eski fiyatlar 1/q, eski hacim q ile
aynı baza çevrilir. Zaten düzeltilmiş veri ikinci kez düzeltilmez. Cash dividend
faktörü ayrı; temettü hacmi ölçeklemez. Normal/special dividend, reverse split,
spin-off, merger, class conversion, ticker change ve delisting ayrı olay türleri.
Kompleks/çelişkili olaylarda otomatik fiyat zinciri kurulmaz: QUARANTINE.

Her olay source_event_id, ex/effective date, amount/ratio/currency, announced_at,
observed_at, revision ve evidence taşır. Provider action akışı araştırma için başlangıç
olabilir; evrensel resmi corporate-action kapsamı varmış gibi davranılmaz. Exchange
Daily List/issuer duyuruları doğrulama adayıdır; kapsam/erişim bedeli sonraki aşama kapısı.

Adjustment revision görülürse etkilenen geçmiş yeniden indirilir, faktörler ve
getiriler karşılaştırılır; gerekiyorsa tam tarih backfill yapılır. Tüm dependent
features tek revision altında yeniden hesaplanır. Önceki yayın/OOS snapshot'ları
değiştirilmez; düzeltilmiş sürüm yeni run olarak kaydedilir.

## 6. Provider, SQLite ve security_id

Başlangıç provider adayı Yahoo; production onayı değildir. Batching/retry/backoff,
rate limit, timeout, inclusive end sözleşmesi ve UTC/seans mapping ayrı adapter'da.
Birincil/alternatif provider aynı adjustment/volume semantiğine sahip değilse barlar
satır satır birleştirilmez. Fallback ancak overlap parity ve identity doğrulamasından
sonra seçilmiş bütün pencere için, provenance ile. Henüz onaylı ikinci provider yok;
eksiklikte NULL + reason. Lisans/yeniden dağıtım koşulları sağlayıcı seçimi kapısında.

| Tablo | Önerilen anahtar ve rol |
|---|---|
| issuers | issuer_id; CIK nullable, source ve validity |
| securities | kalıcı security_id; issuer_id; share class/instrument type |
| listings | listing_id/security_id/MIC/currency/valid_from/valid_to |
| identifiers | security_id/namespace/value/valid interval/known_at; provider symbol ayrı namespace |
| universe_snapshots + members | snapshot_id/hash/policy; security_id/decision/reason |
| calendar_sessions | MIC/session_date/calendar_version; UTC open/close |
| ingest_runs + raw_snapshots | run_id/code/config hash; immutable payload ref/checksum |
| price_versions | security_id/session/provider/basis/revision; OHLCV/source_run |
| corporate_actions | security_id/source_event_id/revision; event time + knowledge time |
| adjustment_factors | security_id/session/basis/version/source_event refs |
| data_status | run_id/security_id/status/reason; tüm beklenen evreni kapsar |
| feature_snapshots | run_id/security_id/calculation_version/input_version |
| publications | run_id/as_of/manifest hash/location/status |

Kimlik otomatik ticker hash'i değildir; yerel monoton anahtar veya UUID atanır.
Ticker reuse yeni security_id; yalnız sembol/ad değişiminde kanıtla aynı security_id.
Merger yeni menkul doğuruyorsa yeni kimlik ve successor ilişkisi; geçmiş yapıştırılmaz.
Identifier geçerlilik aralıkları çakışamaz; belirsiz match manuel incelemeye gider.
SQLite foreign_keys ON, şema migration sürümü, tek yazar, transaction, idempotent
source-event ingest gerekir. Aktif DB dosyasını kopyalamak yerine SQLite backup API
ile tutarlı snapshot alınır. WAL kullanılıyorsa backup prosedürü buna göre test edilir.
DB/ham veri Git dışında; checksum'lı kalıcı object storage önerilir. CI cache tek
kalıcı depo olamaz; retention ve restore testi production önkoşuludur.

## 7. VCP / OOS sınırı

Production VCP varsayılanı NOT_AVAILABLE. Açık, sürümlü US production config ve
veri kalitesi kapısı olmadan araştırma eşikleri devreye girmez. BIST eşikleri ve
26 Ekim / 26 Kasım BIST vade tarihleri US'e taşınmaz.

Yeni US protokolünde freeze timestamp, code/config/universe/calendar/input hash,
cohort inclusion, benchmark, holding horizon ve maliyet varsayımları önceden kayıt.
Önerilen +40 US-session horizon ancak protokol freeze'inde kesinleşir. Sinyal kapanışta
üretilirse en erken sonraki seans execution varsayılır. Selection fonksiyonu yalnız
as_of verisini alır; forward outcomes ayrı dosya/işlemde, vade sonrasında hesaplanır.
Delisted ve veri kaybı yaşayan adaylar denominator'dan sessizce çıkarılmaz; unresolved
outcome ve censoring ayrıca raporlanır. BIST'ten US'e edge aktarımı varsayılmaz.

SPY geniş piyasa bağlamı için öneri; QQQ ikincil bağlam olabilir. Benchmark ETF'leri
ayrı benchmark tablosunda; common-stock evrenine sokulmaz. Rejim descriptivedir.
VIOP yerine ilk sürümde otomatik options/shortable alt evreni yok. Weak Momentum
listesi borçlanılabilirlik/short execution garantisi değildir.

## 8. Test, migration ve publication planı

| Kapı | Kabul ölçütü |
|---|---|
| A0 core | BIST'ten taşınan hesap/test dosyalarının provenance kontrolü; offline testler |
| A1 universe | İki directory fixture; bozuk footer/stale/duplicate/exchange/type; REVIEW reason; ticker reuse; iki sınıflı issuer |
| A2 calendar | DST geçişleri, normal/yarım seans, tatil, olağanüstü kapanış, yıl sonu kapsama, kapanış öncesi reddi |
| A3 actions/storage | 2:1/reverse split, dividend, special dividend, çift adjustment, eski revision backfill, transaction rollback ve idempotence |
| A4 provider | Kısmî batch/timeout/429, missing bar, sıfır hacim, OHLC tutarlılığı, stale as_of, yanlış symbol; replay fixture |
| A5 regression | V1 arşiv getirisi→V1 çıktı yeniden üretimi ayrı; V2 matematik golden ayrı; fark sebepleri sınıflı rapor |
| A6 ranking/VCP | Tie/NULL/full-universe percentile, subset ranking kapalı; araştırma config sızıntısı; causal prefix/no-lookahead |
| A7 publication | Crash sırasında eski yayın korunur; count/hash/JSON finiteness/schema; CSV/JSON parity; snapshot restore |
| A8 pilot | Seçilmiş US örnekleri ve sonra tam evren dry-run; coverage/unresolved raporu; ardından manuel ilk yayın |

V1 karşılaştırması eski hatalara eşit olmayı hedeflemez. Fark reason'ları: FIP_FORMULA,
WINDOW_DEFINITION, PRICE_REVISION, UNIVERSE_SCOPE, MISSING_DATA, ROUNDING.
Excel/CSV/detail arşivi SHA ile sabitlenecek, canonical DB'ye otorite olarak alınmayacak.
Test örnekleri common stock, ADR dışlama, share class, IPO, split/reverse split,
temettü, halt, delisting ve symbol reuse olaylarını kapsayacak.

Yayın hattı: universe freeze → calendar preflight → raw ingest → identity/actions
reconciliation → canonical transaction → status coverage → features/ranks → staging
JSON/CSV/detail → manifest validation → immutable release → tek current pointer.
Pointer değişimi atomic olmalı; iki directory rename arasındaki boşluk gerçek
tek-adımlı atomiklik sayılmaz. GitHub Pages'e bütün build artifact'ı tek deployment
olarak gider; dosya dosya live dizin güncellenmez. Detail dosya yolu security_id ile.

Manifest: schema_version, run_id, as_of, generated_at, code/config/calendar/universe
hash, price_basis/version, expected/published/available/unavailable/quarantined counts,
file checksums. JSON NaN/Infinity reddedilir. Eksik veri NULL + reason; bütün beklenen
hisselerin status kaydı zorunlu. Kaynak bozukluğu/eksik status/kimlik çatışması tüm
promote'u durdurur; önceden tanımlı security-level unavailable durumları açık NULL
olarak yayımlanabilir. Coverage eşiği pilot baseline sonrası freeze edilir; yalnız
'dosya oluştu' diye PASS verilmez. Subset dry-run'da full-market percentile yayınlanmaz.

## Sonraki somut adım

A1: resmi dizinlerin fixture'larını al, source metadata/parse doğrulamasını ve
INCLUDE/EXCLUDE/REVIEW raporunu üret. Aynı aşamada issuer/security/listing şemasının
ilk migration'ını ve çakışan identifier testlerini uygula. Tam evren sayısı ve
sınıflandırma coverage görülmeden provider backfill'e geçme.
