# A3 — Resmî SEC kaynak yakalama ve kaynak-korumalı issuer audit

Durum: 14 Ekim 2026 — **offline kod / çevrimdışı sentetik testler**.
Bu çalışma A2 Draft PR üzerine kuruludur. `main` ve BIST production değişmedi.

## Resmî kaynak ve sınırlamalar

- SEC şirket kimlik/ticker/exchange kaynağı:
  https://www.sec.gov/files/company_tickers_exchange.json
- SEC, bu dosyanın güncellendiğini ancak kapsam ve doğruluk garantisi
  bulunmadığını belirtiyor. SEC CIK yalnız issuer adayıdır; menkul
  kıymet/payı veya kapsam onayı değildir.
- İndirme bir kez, sınırlı boyutta, özel User-Agent iletişim bilgisi ile,
  30 saniye timeout; redirect veya alternatif/üçüncü taraf kaynağa
  otomatik geçiş olmadan gerçekleştirilir.
- `runtime/` altındaki ham dosya SHA256 isimli, receipt içeriğinde kaynak URL,
  indirme zamanı (timezone-aware) ve doğrulama sonucu kayıtlıdır.
- Yanıt bozuk/HTML, kaynak erişim engelli veya checksum yanlış ise
  `SOURCE_REJECTED` / `SEC_REVIEW_BLOCKED`. Yayın yoktur.

## Çalıştırma

SEC'nin gerektirdiği açık kimlik bilgisini **kendi gerçek iletişim adresiniz**
ile shell ortam değişkenine koyun; örnekteki placeholder kullanılmamalıdır:

```sh
export SEC_USER_AGENT='LabyrinthMomentumUSV2 YourContactEmail@yourdomain.com'
.venv/bin/python -m src.data.universe.sec_capture \
  --output runtime/sec/capture-YYYYMMDD-unique
.venv/bin/python -m src.data.universe.sec_review \
  --sec-capture runtime/sec/capture-YYYYMMDD-unique/capture.json \
  --review-json runtime/reports/a1-final/review.json \
  --output runtime/reports/sec-a3-unique
.venv/bin/python -m pytest -q
```

Yeni çıktı dizini şarttır; aynı dizinin üzerine yazılmaz.
Tam A1 `review.json` yerel runtime ortamında bulunmazsa eşleştirme
çalışmaz. GitHub'daki `docs/audits/universe-2026-10-14.json` dosyası
yalnızca özet audit metadata'sıdır; 13.287 menkul kıymet satırlarını
içermez ve yerine konulamaz.

## Audit güvenlik ilkeleri

- SEC dosyası hangi tarihte edinildiyse o `retrieved_at` tarihi saklanır.
  Bir inceleme komutunu daha sonra çalıştırmak SEC edinim zamanını değiştirmez.
- Tek SEC CIK eşleşmesi `SEC_CIK_CANDIDATE` olarak kalır.
  Eksik eşleşme delist değildir. Çelişen CIK'ler `REVIEW_REQUIRED` olur.
- GOOG/GOOGL farklı pay sınıflarının ayrı security_id ilişkisi korunur.
- 14 Ekim A1 denetimi: 13.287 kayıt / 4.556 INCLUDE adayı /
  7.721 EXCLUDE / 1.010 REVIEW_REQUIRED — yalnız **referans**.
  Yeni dosyanın satır sayısı A1 ile eşleşse bile veri snapshot'ının
  aynı olduğu veya geçmiş zaman uygunluğu kanıtlanmış olmaz.
- Sonuç `sec-review.json` ve `sec-summary.json`, production değil
  analizdir. `production_eligible=false` tutulur. Universe membership
  snapshot/known_at/effective_at tabloları ayrıca yapılacaktır.
- Yahoo/fiyat katmanı, seans takvimi, tradability uygulaması ve
  publication kapalıdır.

## Gerçek canlı doğrulama blokajı

Bu geliştirme sırasında çalışma ortamında doğrudan SEC dosyası indirilemedi
(DNS/ağ erişimi). Kaynak URL ve SEC belge açıklaması doğrulandı fakat
**gerçek SEC SHA256, satır sayısı veya A1 eşleşme oranı henüz hesaplanmadı**.
Bu nedenle A3 uygulaması henüz production-ready değildir.
