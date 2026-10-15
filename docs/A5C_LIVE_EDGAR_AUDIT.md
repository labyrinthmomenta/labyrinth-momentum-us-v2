# A5c — Tam SEC EDGAR başvuru metaverisi denetimi

**15 Ekim 2026 — canlı kaynaklı, REVIEW_ONLY; production onayı yok.**
[GitHub Actions successful full scan](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38703798184)
ve [artefact / raw SEC filings metadata](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38703798184/artifacts/11957178840).
Tamamı kaynak receipt ve SHA256 ile izlenebilir; 90 günlük artifact ömrü
kalıcı arşiv anlamına gelmez.

## Girdi ve kapsam

Başlangıç, 14 Ekim A4 Nasdaq/SEC snapshot'ına bağlı 1.010 satırlık A5
enstrüman inceleme kuyruğudur. İkinci SEC Mutual Fund dosyası A5b'de
kaydedilmişti. Bu aşama yalnız ilk nedende
`SPAC_BDC_OR_FINANCIAL_REVIEW` olan **307 satır** içindir.
Tam A5 queue SHA256:
`ea4a8e3112e3e30d9c3e67fc33fac86a3a6aa3fcf2f58391ecc50896ba3bdb37`.

| Etkin kaynak/başvuru kapısı | Toplam |
|---|---:|
| Tür inceleme kuyruğundaki SPAC/BDC/finansal aday | 307 |
| SEC tam ticker+MIC üzerinden CIK adayı olmayan | 3 |
| CIK adayına sahip menkul kıymet satırı | 304 |
| Farklı CIK issuer adayı | 303 |
| Resmî `data.sec.gov/submissions/CIK##########.json` başarıyla alındı | **303** |
| Başarısız indirme / yanıt doğrulaması | **0** |
| Otomatik enstrüman veya pay sınıfı production onayı | **0** |

CIK adayı bulunmayan ticker'lar: `ELLO`, `SACH`, `UAC`.
Bunların neden eşleşmediği ayrıca araştırılmalıdır; SEC'de eşleşmeme
delist veya güvenilir EXCLUDE kanıtı değildir.

`GLIBA` ile `GLIBK`, aynı CIK `0002057463` issuer adayı
altında raporlanmıştır. **İki farklı ticker/pay sınıfı otomatik
birleştirilmez**, ayrı güvenlik kimliği incelemesi gerekir.

## 303 farklı CIK için SEC recent filing form gözlemi

Aşağıdaki sayılar **bir form türü SEC submissions `filings.recent`
alanında en az bir kez görülen CIK sayısıdır**; toplamlar örtüşür.

| Form | En az bir kaydı görülen CIK | Yorum |
|---|---:|---|
| N-54A | **16** | BDC seçimine ilişkin resmî belge *adayı* |
| N-54C | **0** | Recent'ta görülmedi; yokluk/etkinlik kanıtı değil |
| N-2 / N-2/A | 20 / 20 | Yatırım şirketi prospektüs kanıtı adayı |
| S-1 / S-1/A | 263 / 244 | Halka arz belgesi; SPAC kanıtı tek başına değil |
| 10-K | 208 | Şirket ve pay sınıfı incelemesinin yıllık kaynağı |
| 10-Q | 289 | Ara dönem durum kaynakları |
| 8-K | 298 | Önemli olayların kronolojisi için kanıt |

20-issuer pilotunda da 20/20 başarı sağlanmıştı. Tam koşuda
**136 Python testi geçti**.
303 şirket için toplam **5.693 ilgili başvuru metaverisi satırı**
(issuer başına rapora en çok 60 kayıt) ayrıldı.
Raporlanan belgelere ait güvenli URL üretiminde **0 reddedilmiş yol**.
Yalnızca URL üretildi; tam dosya metinleri otomatik analiz edilmedi.

### SEC recent tarihsel kapsam uyarısı

**12 issuer** için SEC `filings.files` altında eski kayıtları gösteren
**13 history parçası** tespit edildi; bunlar **indirilmedi**.
SEC API dokümanı `filings.recent` alanının en az 1 yıl / 1.000 kayıt
sunduğunu, daha eski arşivin parçalı olabileceğini söyler.
Dolayısıyla `N-54C=0`, geçmişte çekilme hiç olmadığını kanıtlamaz.
`recent_window_exhaustive=true` yalnız SEC yanıtında ayrıca history
parçası bildirilmediği anlamındadır; filing içeriğinin doğrulandığı veya
tarihsel bilgi bütünlüğünün kanıtlandığı anlamına gelmez.

A5 as-of tarihi **14 Ekim 2026**, SEC veri edinimi **15 Ekim 2026**.
Seçilen `filingDate <= 2026-10-14` olsa bile as-of tarihindeki
`known_at` kanıtlanmadı. Retrieval time ve filing time ayrı tutulur.

## N-54A bulunan issuer adayları (16)

| Ticker | SEC CIK | Tür kanıtı aşaması |
|---|---|---|
| GAIN | 0001321741 | N-54A belgesi okunmalı |
| GSBD | 0001572694 | N-54A belgesi okunmalı |
| ICMB | 0001578348 | N-54A belgesi okunmalı |
| TPVG | 0001580345 | N-54A belgesi okunmalı |
| CCAP | 0001633336 | N-54A belgesi okunmalı |
| KBDC | 0001747172 | N-54A belgesi okunmalı |
| PSBD | 0001794776 | N-54A belgesi okunmalı |
| LIEN | 0001843162 | N-54A belgesi okunmalı |
| SAR | 0001377936 | N-54A belgesi okunmalı |
| PNNT | 0001383414 | N-54A belgesi okunmalı |
| HRZN | 0001487428 | N-54A belgesi okunmalı |
| NMFC | 0001496099 | N-54A belgesi okunmalı |
| PFLT | 0001504619 | N-54A belgesi okunmalı |
| CION | 0001534254 | N-54A belgesi okunmalı |
| SCM | 0001551901 | N-54A belgesi okunmalı |
| OBDC | 0001655888 | N-54A belgesi okunmalı |

Bu tablo **aktif BDC sınıflandırması veya pay sınıfı onayı değildir**.
Önce accession bazında N-54A belgesi okunmalı, varsa eski N-54C
ve kurumsal olaylar kontrol edilmeli, sonra resmî security type / pay
sınıfı kanıtı ile ilişkilendirilmeli.

## Şu anda uygulanmaması gereken otomatik kurallar

- `S-1` görüldü -> SPAC olarak kabul.
- `N-54A` görüldü -> hâlâ BDC, enstrüman işlem yapılabilir kabul.
- `N-54C` görülmedi -> BDC seçimi hiç geri alınmadı.
- `CIK` eşleşti -> o ticker/pay sınıfı kesin doğrulandı.
- `get_all_tickers` tarayıcı/API listesinde var -> resmî adi hisse.
- Fiyat/hacim verisi yok -> filtreyi veri boşluklarını doldurup geçer.

Bunların tamamı engellendi. Belgelerin kendisini incelemek, 
hisse türü kanıtını, BDC/SPAC kapsam politikasını ve pay sınıfını
ayrı ayrı doğrulamak A5'in sonraki adımıdır.

## Kullanılan resmî dokümantasyon

- [SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC Fair Access](https://www.sec.gov/about/developer-resources)
- [SEC raw filing access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

**US main/BIST production değişmedi.** Bu bir kaynağa dayalı
araştırma raporudur; resmî evren üyeliği veya yatırım tavsiyesi değildir.
