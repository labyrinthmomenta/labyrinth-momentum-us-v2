# A5b — SEC fon seri/sınıf çapraz denetimi ve SPAC/BDC/REIT kanıt standardı

**15 Ekim 2026 — REVIEW_ONLY.** A5'in 14 Ekim A4 snapshot'ına dayanan tam **1.010 satırlık** enstrüman inceleme kuyruğu değişmeden korundu. US `main` ve BIST production üzerinde değişiklik yapılmadı.

## Denenen resmî ikinci SEC kaynağı

[SEC company_tickers_mf.json](https://www.sec.gov/files/company_tickers_mf.json), SEC [EDGAR kaynak açıklaması](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) uyarınca fon registrant CIK, seriesId, classId ve symbol ilişkilerini içerir.

- İndirme/doğrulama: **CAPTURE_VALIDATED**, 15 Ekim 2026 05:43 UTC.
- Toplam **28.589** SEC fund series/class kaydı; **1 kaydın ticker'ı boş** — saklandı, eşleşmede kullanılmadı.
- Ham SEC JSON SHA256: `6a98923d0aad49aa386be6423892f19d489047a9041ef09c81af89302d599efc`.
- A5 1.010 tam inceleme kaydından **0** tanesi SEC mutual-fund class ticker ile birebir eşleşiyor.
- **Bu sonuç 1.010 kaydın hiçbirinin fon olmadığı anlamına GELMEZ.** SEC'nin [Investment Company Series and Class Information](https://www.sec.gov/data-research/sec-markets-data/investment-company-series-class-information) notu, fon seri/sınıf listesinin *çoğu kapalı uçlu fonu* kapsamadığını; özellikle Form N-2 kapsamının eksik olduğunu açıkça belirtir.
- `SEC_FUND_CLASS_CANDIDATE` olsaydı bile issuer CIK / series / class bir security_id olmazdı; as_of ve share class doğrulaması istenecekti.
- SEC fon kaynağının 15 Ekim alım zamanı, A4'ün 14 Ekim Nasdaq/SEC snapshot'ından ayrı bir **knowledge time**; geçmişe uygulanmış eş zamanlı veri değildir.

## İncelenen 1.010 kaydın tamamı

| Önceki A5 nedeni | Adet | SEC MF dosyasında tam ticker eşleşmesi | Durum |
|---|---:|---:|---|
| FINANCIAL_STATUS_REVIEW | 268 | 0 | REVIEW_REQUIRED |
| FUND_NAME_REQUIRES_TYPE_EVIDENCE | 297 | 0 | REVIEW_REQUIRED |
| SPAC_BDC_OR_FINANCIAL_REVIEW | 307 | 0 | REVIEW_REQUIRED |
| TYPE_UNCONFIRMED | 128 | 0 | REVIEW_REQUIRED |
| UNKNOWN_EXCHANGE_CODE | 10 | 0 | A5'te TXSE scope dışı önerisi, A4 statüsü korunuyor |
| **Toplam** | **1.010** | **0** | **Otomatik production onayı 0** |

Nasdaq security-name tanımındaki *Closed End Fund* gibi ifadeler açıklayıcı olabilir fakat türün tek kesin kanıtı değildir; BDC şirketleri de teknik olarak kapalı uçlu yatırım şirketi olabilir. Toplam inceleme kuyruğunda 32 ad *Closed End Fund*, 243 ad *Acquisition*, 9 ad *BDC*, 4 ad *REIT* ifadesini içerir (örtüşme mümkündür). Bunlar resmî Nasdaq isim alanından türetilen **ipuçlarıdır**, nihai sınıflandırma sayıları değildir.

## Kaynaklı EDGAR örnekleri — issuer düzeyi, sınıf onayı değil

| Ticker | SEC issuer CIK | Dosyalanmış kanıt | Desteklenen issuer türü | Son karar |
|---|---|---|---|---|
| ARCC | 0001287750 | [SEC 2025 10-K, 2026 başı](https://www.sec.gov/Archives/edgar/data/1287750/000128775026000006/arcc-20251231.htm) | Şirket BDC olarak faaliyet gösterdiğini bildiriyor | Enstrüman REVIEW_REQUIRED, SPAC/BDC kapsam kararı bekler |
| CGBD | 0001544206 | [SEC 2026 Q1 XBRL financial statement note](https://www.sec.gov/Archives/edgar/data/1544206/000154420626000033/R10.htm) | Şirket BDC statüsünü bildiriyor | REVIEW_REQUIRED, pay sınıfı kanıtı bekler |
| AGNC | 0001423689 | [SEC 2025 10-K, 23 Şubat 2026](https://www.sec.gov/Archives/edgar/data/1423689/000142368926000043/agnc-20251231.htm) | Şirket REIT olarak vergilendirilmeyi seçtiğini açıklıyor | REVIEW_REQUIRED; REIT common security class ayrıca doğrulanmalı |
| AACI | 0002092897 | [SEC 12 Şubat 2026 S-1/A](https://www.sec.gov/Archives/edgar/data/2092897/000119312526049050/d942100ds1a.htm) | Şirket SPAC/blank-check issuer olduğunu bildiriyor | REVIEW_REQUIRED; unit/common/warrant ayrımı ayrıca kanıtlanmalı |

Bu örnekler A4'teki CIK adaylarına ve yayımlanmış SEC dosyalarına dayanır. Belge metni **şirketin/registrant'ın hukuki statüsünü** destekler. Listeleme ticker'ının o tarihte tam olarak hangi menkul kıymeti ifade ettiğini otomatik doğrulamaz ve A4'teki source state'i değiştirmez.

### BDC canlı statü kontrolü

SEC [N-54A](https://www.sec.gov/Archives/edgar/data/2025369/000110465926040357/tm2611086d1_n54a.htm) formu BDC statüsüne seçim bildirimidir; [N-54C](https://www.sec.gov/Archives/edgar/data/2071136/000207113626000023/bdcv-formnx54cmay2026.htm) bu seçimin geri alınmasını bildirir. Dolayısıyla yalnız geçmiş bir N-54A kaydı veya şirket adındaki `BDC` yeterli değildir. Etkin tarih ve en son ilgili bildirim birlikte değerlendirilmelidir.

### SPAC security/share-class kontrolü

SEC S-1/S-1/A, 10-K, 8-K ve borsa listing belgeleri üzerinden SPAC'in Class A common/ordinary share, unit ve warrant türleri birbirinden ayrı çözülmelidir. Tek bir issuer CIK tüm bu menkul kıymetlere sahip olabilir; `CIK != security_id`.

## Mimari ve güvenlik

Yeni `src.data.universe.fund_registry` yalnız sabit resmî SEC HTTPS adresine sınırlı, yönlendirmesiz indirme yapar; checksum/receipt ve timestamp tutar, HTML/bozuk şemayı reddeder. SEC ticker alanı gerçekten boş olabilen sınıf için sessiz symbol ataması yapmaz.

`src.data.universe.a5b_fund_review` yalnız önceki 1.010 satırlık A5 kanıt kuyruğunu ve geçerli SEC fon kaynak receipt'ini kullanır. Çıktı `full-fund-evidence.json` (1.010 kayıt) ve `fund-summary.json` olup hiçbiri `production_eligible` değerini true yapmaz. **121 test geçti**.

- [A5b bir defalık başarılı GitHub Actions](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38688288380)
- [A5b ham SEC dosyası, checksum ve tam inceleme raporu](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38688288380/artifacts/11951060067) — 90 gün; kalıcı dış arşiv henüz yok.

## Sonraki kanıt kapısı

1. NYSE Group Security Master'ın **güncel, lisanslı günlük verisini** veya aynı kapsamda resmî security-type bilgisini edin; [ürün açıklaması](https://www.nyse.com/data-products/catalog/nyse-group-security-master) gerçek günlük dosya değildir. 2024/2025 örnekleri 2026-10-14 snapshot'ını kanıtlamaz.
2. SEC EDGAR issuer filinglerinden **CIK + accession + filing_date + reported_security_title + class + effective/known_at** kanıtı derle. Tekil form ve issuer CIK otomatik ticker-security eşleşmesi değildir. BDC için N-54A ve N-54C sırası, REIT için güncel 10-K, SPAC için S-1 ve güncel durum birlikte kontrol edilir.
3. Açık kapsam politikası gereği SPAC common ile BDC menkul kıymetleri onaylanmadan US evrenine alınamaz. Fon/REIT ayrımı da per-security kanıt ister.
4. 1.010 A5 incelemesinin tür kararı **tamamlanmadı**. Bunun 10 adedi TXSE kapsam dışı önerisi olarak kayıtlıdır; kalan **1.000** yine tür kanıtı bekler. Yahoo/fiyat/tradability ve publication kapalıdır.

**Sonuç:** SEC MF dosyasının bu 1.010 kayıt için tek başına karar verici kaynak olmadığı deneysel olarak kanıtlandı. Kanıt yokluğu, ortak hisse sayılmaz.
