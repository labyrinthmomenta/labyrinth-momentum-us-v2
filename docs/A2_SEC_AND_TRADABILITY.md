# A2 — SEC issuer eşleştirmesi ve işlem yapılabilirlik politikası

Durum: 14 Ekim 2026; geliştirme dalında, **offline / provisional**. US V2 dışındaki
production sistemleri değiştirilmez. A1 audit: 13.287 kayıt = 4.556 aday +
7.721 kapsam dışı + 1.010 inceleme. Bunlar production onayı değildir.

## A2-01: Bağımsız tradability filtresi — kabul edilen karar

- Son tamamlanmış US işlem seansının kapanış fiyatı kesin olarak **> 5 USD**.
- Son **90 tamamlanmış işlem seansının** her biri için günlük USD işlem
  değeri `close_USD * share_volume`; aritmetik ortalama kesin olarak **> 1.000.000 USD**.
- Ek bir adet hacmi eşiği **yoktur**.
- Eksik veya geçersiz veri, eksik seans ve doğrulanmamış para birimi `FAIL_CLOSED`.
- Tam 5 veya tam 1.000.000 sınır değerleri başarısız; 90 tamamlanmış seans şart.
- Yarım gün tek tamamlanmış seanstır; tatil/hafta sonu değildir.
- Resmi evren ve enstrüman sınıflandırması değişmez; karar ayrı, `as_of` ve
  veri sürümüyle izlenmesi gereken işlem yapılabilirlik katmanıdır.
- **Henüz çalıştırılmayacak.** `config/us.json` içinde
  `tradability.status=SPECIFICATION_ONLY` ve `evaluation_enabled=false`.
  Seans takvimi, kapanış doğrulaması ve fiyat/volume baz uyumu henüz yok.
  Yahoo/fiyat backfill, scheduler ve canlı yayın bu aşamanın dışında.

## A2-02: SEC issuer match — offline aday eşleştirme

- Beklenen SEC kaynağı: `company_tickers_exchange.json`; `fields` tam olarak
  `[cik, name, ticker, exchange]`, satırları `data` içindedir. **SEC indirilmedi.**
- Yeni `src.data.universe.sec` supplied JSON'u offline işler; SHA256 ve timezone-aware
  retrieval zamanı kaydeder. Bilinmeyen/bozuk şema güvenli biçimde reddedilir.
- CIK 10 haneli issuer kimliği **adayıdır**, asla `security_id` değildir.
  GOOG ve GOOGL gibi pay sınıfları ayrı kalır.
- Yalnız tam sembol + doğrulanmış MIC ile eşleşme: Nasdaq/XNAS, NYSE/XNYS,
  NYSE American/XASE. Nokta-tire/alias dönüştürmesi tahmin edilmez.
- Tek kayıt `SEC_CIK_CANDIDATE`, sıfır kayıt `SEC_NOT_FOUND` (delist değildir).
  Birden çok kayıt `SEC_IDENTITY_AMBIGUOUS`: dışlanmamış aday karantinaya gider.
- SEC eşleşmesi instrument type, share class veya üretim uygunluğunu kanıtlamaz.
  SQLite issuer/security/listing kaydı otomatik oluşturulmaz.
- Güncel SEC kaydı geçmişteki durumu kanıtlamaz. `retrieved_at` etkinleşme
  tarihi veya zamanında bilinen verinin yerini tutmaz.

## A2-03: Kanıt bazlı sınıflandırma

- `src.data.universe.triage` tür/venue/share-class kanıtı gereksinimleri ve
  inceleme önceliği üretir; otomatik INCLUDE veya production onayı vermez.
- A1 inceleme kırılımı: 307 SPAC/BDC/finansal isim, 297 fon adı, 268 financial
  status, 128 tür belirsiz ve 10 bilinmeyen borsa kodu.
- Common REIT, Class C capital stock, registry shares, SPAC/BDC gibi kayıtlar
  ayrı resmi exchange/issuer/security-type kanıtıyla incelenmelidir.
- `EXCLUDE` kayıtları SEC'te bulunsa bile geri alınmaz; kaynak dosyalarının
  directory-only kararı değiştirilmeyip SEC uyuşmazlıkları ayrı raporlanır.
- Sürümlü SQLite evren üyelikleri, bitemporal karar geçmişi ve manuel karar
  kanıtı ileriki çalışma; mevcut şema v1'e dokunulmadı.

## Yerel kullanım — resmi SEC dosyası ayrıca temin edildiğinde

```sh
.venv/bin/python -m src.data.universe.sec_review \
  --sec-json runtime/sec/company_tickers_exchange.json \
  --review-json runtime/reports/a1-final/review.json \
  --output runtime/reports/sec-a2-review
.venv/bin/python -m pytest -q
```

Önce ham SEC dosyası, kaynak URL, checksum, zaman ve erişim politikası ayrıca
doğrulanmalı. GitHub'daki `docs/audits` özeti tam 13.287 satırı içermez.
Bu komut SEC download yapmaz, sadece local offline inceleme raporu üretir.

## Kabul kapıları

1. Sentetik testler CIK, ikili share-class, eksik/eşsiz/ambiguous match,
   bilinmeyen SEC borsası, noktalama farkı ve bozuk girdiyi kapsar.
2. Mevcut 53 baseline test korunur ve GitHub Actions yeşil olmalıdır.
3. BIST production, calculation/indicators, Yahoo/fiyat, calendar, DB migration
   veya canlı publication değiştirilmez.
4. Canlı SEC indirmesi, kapsam analizi ve kaynaklı kararlardan önce hiçbir
   enstrüman production'a alınmaz.
