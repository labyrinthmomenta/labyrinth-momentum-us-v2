# A1 — US evren ve kimlik altyapısı

Güncelleme: aynı gün sonraki indirmeler başarılı oldu. Aşağıdaki kayıt ilk denemenin
tarihçesidir; güncel sonuç [A1 canlı audit](A1_LIVE_AUDIT.md) belgesindedir.

14 Ekim 2026. Durum: offline altyapı tamamlandı; canlı kaynak doğrulaması açık.

## Uygulananlar

- İki Nasdaq directory biçimi için katı header/row/footer doğrulaması.
- UTF-8, duplicate symbol, bilinen flag/category değerleri, round lot kontrolü.
- Kaynak oluşturma zamanı ve SHA256; tarih uyuşmazlığında snapshot reddi.
- INCLUDE / EXCLUDE / REVIEW_REQUIRED ön sınıflandırması; her kayıtta neden ve
  kaynak satırı bulunur. INCLUDE yalnız adaydır; bütün kayıtlar için
  `production_eligible=false`. İsim kuralları gerçek enstrüman master'ı değildir.
- Bilinmeyen borsa kodu incelemeye gider. Dosyalar arası ticker çakışması birleştirilmez.
- JSON/CSV raporu; hatalı kaynaktan CSV veya evren sayısı üretilmez.
- SQLite schema v1: issuers, securities, listings, identifiers. Foreign key ve
  insert/update üzerinde çakışan identifier/listing tarih aralığı kontrolleri.
- Tarih aralıkları `[valid_from, valid_to)`; valid_to günü yeni sahibin başlangıcı
  olabilir. CIK issuer seviyesinde; farklı pay sınıfları ayrı security_id alır.
- Kimlik kaydı açık kanıt ister; directory isimlerinden otomatik kimlik oluşturmaz.

## Kaynak denemesi

Resmi [alan tanımları](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs)
esas alındı. İki HTTPS directory adresi 14 Ekim 2026 15:04 İstanbul saatinde
liste yerine HTML erişim koruma içeriği döndürdü. Parser ikisini de
`SOURCE_REJECTED` olarak reddetti. Alternatif resmi FTP hostname'inin HTTPS
erişim denemesi zaman aşımına uğradı. Erişim koruması aşılmaya çalışılmadı.

Reddedilen iki payload'ın SHA256 değeri:
`d02032286070b4dd9d8fbd985a7bdca8af8edf52b89ff177db3bfcb2c8a9c43d`.

Ham yanıtlar ve receipt metadata `runtime/raw/` altında, Git dışında saklandı.
Canlı deneme raporu: `runtime/reports/live-2026-10-14/review.json`.
**Gerçek US evren sayısı ve coverage bu aşamada belirlenemedi.**

## Doğrulama

Python 3.12.10 ile 42 test geçti (16 mevcut core + 26 yeni test).
Testler HTML/stale/future/malformed source, duplicate, çakışan source date,
cross-source ticker collision, rapor başarısızlık yolu, identity foreign key,
ticker reuse, share class, symbol change, transaction rollback ve migration
yeniden açılışını kapsar. SQLite runtime dosyası schema v1 olarak oluşturuldu;
gerçek menkul verisiyle doldurulmadı.

`tests/fixtures/universe/` içeriği **sentetik** örneklerdir. Sentetik rapor 9 kayıt:
3 INCLUDE adayı, 4 EXCLUDE, 2 REVIEW_REQUIRED. Bunlar piyasa coverage ölçümü değildir.

## Tekrar çalıştırma

Proje kökünden, capture JSON'larında `path`, `sha256`, timezone-aware
`retrieved_at` alanları bulunan yerel payload'ları incelemek için:

```sh
.venv/bin/python -m src.data.universe.review \
  --raw-dir runtime/raw --output runtime/reports/new-review
.venv/bin/python -m pytest -q
```

Output dizini yeni olmalıdır; eski CSV'nin başarısız yeni raporla karışması engellenir.
Komut ağ çağrısı yapmaz; yakalanmış kaynakları receipt zamanına göre yeniden oynatır.
Canlı downloader/scheduler henüz yoktur. URL kaynak doğrulaması bir sonraki fetch
katmanının sorumluluğudur; bu CLI yerel metadata'yı inceleme girdisi kabul eder.

## Sınırlar ve sonraki kapı

- Footer zamanı New York yerel saati olarak yorumlanır; ilk canlı payload ile
  doğrulanacak. Varsayılan dört günlük yaş toleransı yalnız audit içindir; resmi
  seans takvimi veya canlı freshness kararı yerine geçmez.
- İsim eşleşmeleri yanlış pozitif/negatif üretebilir. SEC/exchange/issuer kanıtı ve
  kaynaklı karar kaydı olmadan adaylar production evrenine alınmaz. SPAC/BDC gibi
  tipler isimden tamamen yakalanamaz. When-issued durumu ayrı kaynakla doğrulanacak.
- İlk schema bir identity temeli; universe membership/version tabloları, SEC
  enrichment, otomatik reconciliation ve corporate-action modeli henüz yok.
- `known_at` saklanır; mevcut resolver yalnız effective interval'a bakar. Bu
  resolver knowledge-time filtreli OOS replay için kullanılamaz. Bitemporal
  revision/audit ve geçmişte bilinen kimliği çözme sonraki aşamadır.
- Canlı dosyalar erişilebilir olduğunda aynı parser ile iki snapshot alınacak;
  gerçek coverage, tür belirsizlikleri ve churn ölçülecek. A1 canlı kapısı geçmeden
  provider backfill ve production publication başlatılmayacak.

Yerel Git deposu hazır; uzak GitHub deposu henüz yok, push yapılmadı.
BIST production ve `sources/` dosyalarında değişiklik yapılmadı.
