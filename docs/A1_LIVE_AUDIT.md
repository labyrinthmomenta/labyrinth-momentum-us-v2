# A1 resmi kaynak doğrulaması — 14 Ekim 2026

Nasdaq'ın iki resmi HTTPS directory dosyası doğrudan indirildi. Önceki HTML
erişim hatası bu denemede oluşmadı; nedeninin kalıcı olarak giderildiği varsayılmaz.
Yahoo veya üçüncü taraf liste kullanılmadı. BIST production'a dokunulmadı.

## Sabitlenen snapshot

Kaynak zamanı: 14 Ekim 2026 08:31 New York (15:31 İstanbul).
İndirme: 15:34 İstanbul. Hash, kaynak zamanı ve karar sayıları
[audit JSON](audits/universe-2026-10-14.json) içinde kayıtlıdır.

| Kaynak | Toplam | Adi hisse adayı | Kapsam dışı | İnceleme |
|---|---:|---:|---:|---:|
| Nasdaq-listed | 5.629 | 2.678 | 2.394 | 557 |
| Other-listed | 7.658 | 1.878 | 5.327 | 453 |
| Toplam | 13.287 | 4.556 | 7.721 | 1.010 |

Resmi kaynaklar: [nasdaqlisted](https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt),
[otherlisted](https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt).
Bunlar değişken URL'lerdir; gelecekteki içerik audit hash'iyle eşleşmeyebilir.
İlk başarılı 08:16 snapshot'ı ile 08:31 snapshot'ı arasında toplam iki kayıt artışı
gözlendi; farklı zamanların rakamları tek snapshot olarak birleştirilmedi.

## İnceleme kuyruğu

- 307 SPAC/BDC/finansal isim sınıflandırması.
- 297 fon adı nedeniyle tür kanıtı gerektiren kayıt.
- 268 normal dışı Nasdaq financial status.
- 128 açık pay türü belirlenemeyen kayıt.
- 10 tanınmayan exchange kodu (F); otomatik kapsam genişletilmedi.

Bu sayılar ön karar kategorileridir. Örneğin GOOG'un Class C Capital Stock veya
ASML'nin New York Registry Shares tanımı yalnız dar common-stock isim kuralıyla
onaylanmaz. Common REIT'ler isimdeki investment ifadesi nedeniyle incelemeye düşebilir.
SPAC/BDC'ler isimde belirgin ifade taşımayabilir. Bu nedenle INCLUDE da yalnız
adaydır; bütün kayıtların `production_eligible` değeri false kalır.

## Kaynakla ortaya çıkan düzeltmeler

Other-listed footer'ında sekiz sütunlu header'a karşılık yedi alanlı kapanış satırı
gözlendi. Parser yalnız bilinen yedi/sekiz alanlı footer biçimlerini, boş trailing
alanlarla kabul eder; bozuk footer reddedilir. Test fixture'ı bu farkı kapsar.
When-issued/distributed hisseler kapsam dışına ayrıldı; ADRs/ADSs çoğul biçimleri
yakalandı ve Common Share tekil biçimi aday sınıfına eklendi. Politika sürümü v2 oldu.
Bu değişiklikler yatırım performansına bakılarak yapılmadı; yalnız kaynak formatı
ve enstrüman tanımı denetimi sonucudur.

## İndirme ve doğrulama

Yeni `src.data.universe.capture` komutu yalnız sabit iki resmi HTTPS adresini
kullanır. Redirect, 10 MiB üstü yanıt, timeout, HTML, bozuk/stale kaynak ve eksik
dosya çifti başarısız olur. Yeni output dizini şarttır. Her ham yanıt hash adıyla
ve receipt ile tutulur; hatalı içerik başarı diye yayımlanmaz. Otomatik zamanlama yok.

```sh
.venv/bin/python -m src.data.universe.capture --output runtime/new-capture
.venv/bin/python -m src.data.universe.review --raw-dir runtime/new-capture --output runtime/new-review
.venv/bin/python -m pytest -q
```

Yerel doğrulama: **53 test geçti**. Capture komutu gerçek iki kaynak için
CAPTURE_VALIDATED; ön inceleme REVIEW_ONLY üretti. Tam yerel raporlar
`runtime/reports/a1-final/review.json` ve `review.csv`; ham dosyalar
`runtime/capture-a1-final/` altında. Büyük ham dosyalar ve runtime DB Git'e eklenmedi.
GitHub'a özet audit/provenance yüklenir; henüz harici kalıcı snapshot arşivi yoktur.

## Sonraki adım ve sınırlar

Kaynak erişim kapısı geçildi; üretim evreninin tamamı onaylanmadı. Sıradaki iş SEC
issuer eşleştirmesi ve kaynaklı enstrüman kararlarıdır. CIK security_id olmayacak;
pay sınıfları birleştirilmeyecek. Karar snapshot'larını SQLite'a sürümlü yazmak ve
known_at/effective_at ayrımını korumak gerekiyor. Güncel directory tarihsel evren
kanıtı değildir. Takvim, fiyat backfill, VCP ve site yayını hâlâ devrede değil.
