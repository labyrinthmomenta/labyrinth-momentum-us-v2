# A5c — Resmî EDGAR filing metadata ve alternatif ticker kaynağı değerlendirmesi

**15 Ekim 2026 — REVIEW_ONLY.** A4/A5 resmi liste snapshot'ı korunur;
BIST V2 production, US gösterge çekirdeği, fiyat/Yahoo katmanı, tradability ve
canlı yayına dokunulmaz. PR üst üste açılır; main'e merge yapılmaz.

## Harici GitHub yöntemi: `shilewenuw/get_all_tickers`

İncelenen kod: [get_tickers.py](https://github.com/shilewenuw/get_all_tickers/blob/ef8c0b81abfcd14daf1cc03d9905a9cae44b682e/get_all_tickers/get_tickers.py),
[README](https://github.com/shilewenuw/get_all_tickers/tree/master),
[MIT lisans](https://github.com/shilewenuw/get_all_tickers/blob/master/LICENSE.txt).
Son repo commit'i 4 Eylül 2022, paket 1.7. GitHub'da kod var, güncel
Nasdaq API yanıtı doğrulaması yapılmadı.

Gerçek yöntem: `https://api.nasdaq.com/api/screener/stocks` adresine
`exchange=nyse/nasdaq/amex`, `letter=0`, `download=true` gönderir.
Dönen `data.rows` tablosundan ticker'ları alır. Market cap/sektör
filtreler, filtreli ve büyük-n fonksiyonları dolar hacmine değil piyasa değerine
dayalıdır. `__exchange2list` ve filtreli varyantlar `.` ve `^` içeren
ticker'ları atar; bu farklı pay sınıflarının kaçmasına neden olabilir.
README site anti-scraping headers ve Google Colab sorununu bildirir.
Kod `requests` import ettiği halde `setup.py` içinde `install_requires`
yalnız `pandas` listeler. Bölgesel sorgu `old.nasdaq.com` kullanır.

**Sonuç:** Nasdaq Screener kaynakları aynı sağlayıcının farklı ürünüdür;
SEC'den veya ayrı yetkili listeleme verisinden bağımsız kesin doğrulama
olduğu varsayılmamalıdır. Kullanım önerisi yalnız opsiyonel, *read-only
discovery/diff* raporu: Screener'da var/resmî Nasdaq Trader directory'de yok
ve tersi, kaynak tarihleri ve endpoint response hash'leriyle;
production universe, security_id, CIK, type ve as_of kararına otomatik etkisi
olmasın. Bu kütüphaneyi bağımlılık olarak eklemeyin; MIT kodu kopyalanmadı.

## SEC EDGAR submissions — kanıt üretimi, sınıflandırma değil

SEC API dokümanı:
<https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
ve fair-access:
<https://www.sec.gov/about/developer-resources>.
Resmî kaynak:
`https://data.sec.gov/submissions/CIK##########.json`.
SEC resmi açıklamasına göre `filings.recent` yalnız en az son bir yıl veya
1000 kayıt (hangisi büyükse) içerir; daha eski dosyalar
`filings.files[]` içinde ayrıca bulunabilir. Eski dosyalar okunmadığında
**N-54A/N-54C'nin yokluğu kanıtlanmış değildir**.

`src.data.universe.a5c_edgar_pilot`:
- A5'teki tam 1.010 satırlık frozen `instrument-review.json` dosyasının
  SHA256 `ea4a8e3112e3e30d9c3e67fc33fac86a3a6aa3fcf2f58391ecc50896ba3bdb37`
  değerini doğrular. 307 SPAC/BDC/finansal nedene odaklanır.
- 303 benzersiz CIK adayı saptandı. `ELLO`, `SACH`, `UAC` için
  **tam ticker+MIC üzerinde CIK adayı bulunmadı**; asla delist veya EXCLUDE
  yapılmaz. 307 satır / 303 CIK farkında bir CIK birden fazla ticker için
  aday olabildiğinden bire bir sayım varsayılmaz.
- CIK bazında bir resmî SEC HTTPS isteği; özdeş `CIK` kontrolü, 
  JSON şeması, 12 MB yanıt sınırı, 25s timeout, fail-closed; asgari
  0,75 saniye aralık (> SEC limitinden daha yavaş). Redirect ve başka
  kaynaklarla otomatik devam etmez. Hatalar açıkça `PARTIAL_SOURCE_FAILURE`.
- Accessions, `form`, `filingDate`, güvenli primary document URL,
  dosya SHA256, `retrieved_at`, eksik history uyarıları ve mevcut
  N-54A/N-54C/S-1/N-2/10-K/8-K vb. meta verileri saklanır.
  Geçerli iç-altklasör belge yolu kabul edilir, `../` gibi traversal yolu
  URL olarak kullanılmaz. En fazla 60 ilgili başvuru rapora yazılır;
  tam ham SEC yanıtı ayrı artifact dosyasıdır.
- Yalnız `filingDate <= 2026-10-14` başvuruları rapora seçilir,
  ancak SEC dosyası 15 Ekimde edinildiği için **14 Ekim tarihinde biliniyor
  olduğunun garantisi değildir**. Filing tarihini veri edinim tarihiyle
  karıştırmayın.
- `N-54A` görülmesi, aktif BDC onayı değildir; varsa en güncel
  `N-54C`, eski history, hukukî statü ve listed-security share class
  belgesi ayrıca incelenmeli. `S-1` bulunması SPAC kanıtı değildir.
  `issuer_CIK != security_id`. Bütün satırlar REVIEW_REQUIRED.

## Pilot

[İlk test koşusunda](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38703075418)
resmî SEC erişimi başarılıydı fakat parser, SEC dosyalarında meşru olan
`xslF345X03/primary_doc.xml` gibi göreli altklasörleri reddetti.
Kod bu durumda **hiçbir şirketi onaylamadı** ve işlemi durdurdu.

[Başarılı 20-CIK pilotu](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38703554440):
20/20 SEC kaynak yanıtı indirilip doğrulandı; 136 test geçti.
20 adayın incelenen `filings.recent` kısmında 8 CIK için `N-54A`
formu vardı, `N-54C` görülmedi. Ancak bir issuer'ın overflow history
dosyaları bulundu ve okunmadı; bu istatistik *aktif BDC* sayısı değildir.
11 civarı farklı şirketin S-1 bulundurması da otomatik SPAC etiketi değildir.
[Ham SEC ve receipt artifact'ı](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38703554440/artifacts/11957462122)
90 gün tutulur; kalıcı arşiv değildir.

## Bütün CIK'leri inceleme ve kalan güven kapıları

[303 benzersiz CIK için ayrı GitHub Actions](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/workflows/a5c-edgar-full.yml)
başlatıldı. Bu koşu yalnız EDGAR başvuru metaverisini toplar, otomatik
sınıflandırma yapmaz. Tamamlandığında başarılı/başarısız CIK sayıları
ve resmî belge referansları ayrıca rapora işlenir.

Açık kalması gerekenler: SEC tam başvuru metni incelemesi, N-54C tarih sırası,
SPAC vs BDC kapsam politikası, Nasdaq/NYSE Security Master share class kanıtı,
SEC CIK eşleşmeyen 3 kayıt, eksik historical filings, as-of/known_at modelleme,
önerilen ayrıştırmanın manuel kanıtlı kabul kontrolü. **Production onayı 0**.
