# A5d — SEC N-54A asıl belge içeriği ve BDC statü güvenlik kapıları

**15 Ekim 2026 — REVIEW_ONLY / production uygunluğu yok.**
A5c'nin [303/303 başarılı resmî SEC Submissions taraması](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38703798184) üzerinden, **tam A5c receipt hash'i** `38b3773641c5e104ae6da7aaf19f32682b3aef66b6d0d4bb8fedeb9d3aa186ea`
ile dondurulmuş ham SEC şirket yanıtlarını yeniden okuyarak çalışıldı.
A5c ilk 60 başvuruyu gösteren kısa rapor yerine **şirketin bütün
`filings.recent` satırları** kullanıldı.

## Doğrulanan canlı sonuç

- [Başarılı A5d iş akışı](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38706374436): **145 test geçti**.
- İncelenen N-54A'sı bilinen **16** farklı issuer/CIK.
- `www.sec.gov/Archives/edgar/data/` üzerinden gerçekten indirilen ve
  resmî N-54A metin işaretleri doğrulanan **17** belge: **16 N-54A + 1 N-54A/A**.
- 17 belgede doğrulama başarısızlığı: **0**.
- Dondurulmuş 16 issuer'ın SEC recent satırlarında `N-54C`/`N-54C/A`
  **görülmedi (0)**. Bu kayıtların SEC `filings.files` ek geçmiş parçası
  **bildirilmedi (0/16)**. Bu yalnız mevcut SEC API snapshot kapsamının
  gözlemidir; geçmişte hiç çekilme/iptal olmadığının veya güncel BDC
  statüsünün kesin kanıtı değildir.
- **Güncel BDC statüsü onayı 0**, **listelenmiş pay sınıfı onayı 0**,
  **production onayı 0**.

Her belgenin `CIK`, accession, form, filing date, resmî URL,
ham `SHA256`, dosya boyutu, indirme anı ve metin işaretleri
`a5d-election-evidence.json` içinde. Orijinal 17 SEC belge yanıtı ayrı
ham artifact dosyalarında saklanmıştır:
[17 belge + audit artifact](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38706374436/artifacts/11957904269).
Saklama süresi 90 gün; **kalıcı arşiv değildir**.

## 16 N-54A belge kaydı

| Ticker adayı | SEC issuer CIK | N-54A tarihi | Resmî SEC belge | Statü kararı |
|---|---|---|---|---|
| GAIN | `0001321741` | 2005-03-31 | [0000950133-05-001383](https://www.sec.gov/Archives/edgar/data/1321741/000095013305001383/w0719154nv54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| SAR | `0001377936` | 2007-03-21 | [0000950103-07-000712](https://www.sec.gov/Archives/edgar/data/1377936/000095010307000712/dp05102e_n54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| PNNT | `0001383414` | 2007-04-19 | [0001193125-07-084707](https://www.sec.gov/Archives/edgar/data/1383414/000119312507084707/dn54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| HRZN | `0001487428` | 2010-10-28 | [0000950123-10-097368](https://www.sec.gov/Archives/edgar/data/1487428/000095012310097368/w80285nv54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| NMFC | `0001496099` | 2011-05-19 | [0001104659-11-030268](https://www.sec.gov/Archives/edgar/data/1496099/000110465911030268/a11-12674_1n54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| PFLT | `0001504619` | 2011-04-07 | [0001193125-11-090967](https://www.sec.gov/Archives/edgar/data/1504619/000119312511090967/dn54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| CION | `0001534254` | 2012-07-02 | [0001144204-12-037586](https://www.sec.gov/Archives/edgar/data/1534254/000114420412037586/v317015_n54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| SCM | `0001551901` | 2012-11-07 | [0001144204-12-059923](https://www.sec.gov/Archives/edgar/data/1551901/000114420412059923/v326852_n54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| GSBD | `0001572694` | 2013-03-29 | [0000895345-13-000113](https://www.sec.gov/Archives/edgar/data/1572694/000089534513000113/ptn54a_goldmanliberty.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| ICMB | `0001578348` | 2014-02-05 | [0001193125-14-036774](https://www.sec.gov/Archives/edgar/data/1578348/000119312514036774/d666476dn54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| TPVG | `0001580345` | 2014-03-05 | [0001104659-14-016358](https://www.sec.gov/Archives/edgar/data/1580345/000110465914016358/a13-16230_11n54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| CCAP | `0001633336` | 2015-06-05 | [0001140361-15-023401](https://www.sec.gov/Archives/edgar/data/1633336/000114036115023401/formn54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| OBDC | `0001655888` | 2016-03-03 | [0001193125-16-490471](https://www.sec.gov/Archives/edgar/data/1655888/000119312516490471/d140108dn54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| KBDC | `0001747172` | 2021-02-05 | [0001193125-21-030922](https://www.sec.gov/Archives/edgar/data/1747172/000119312521030922/d32675dn54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| PSBD | `0001794776` | 2020-01-16 | [0001213900-20-001220](https://www.sec.gov/Archives/edgar/data/1794776/000121390020001220/fn54a011520_palmersquare.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |
| LIEN | `0001843162` | 2021-06-29 | [0000950103-21-009571](https://www.sec.gov/Archives/edgar/data/1843162/000095010321009571/dp153455_n54a.htm) | Başvuru içeriği doğrulandı; mevcut BDC statüsü açık |

**CCAP ek kayıt:** 2020-01-30 tarihli
[N-54A/A, accession 0001193125-20-019656](https://www.sec.gov/Archives/edgar/data/1633336/000119312520019656/d874298dn54aa.htm)
içeriği ayrıca doğrulandı. Bu nedenle belge sayısı 17; 17 farklı issuer
değil, **16 issuer** var. CCAP'in ilk N-54A tarihi 2015-06-05.

## Kanıtın doğru yorumu

ABD [Investment Company Act, §54](https://www.govinfo.gov/content/pkg/USCODE-2024-title15/html/USCODE-2024-title15-chap2D-subchapI-sec80a-53.htm),
uygun şirketlerin N-54A bildirimiyle BDC düzenleme rejimine
seçim yapmasına imkân verir; N-54C seçimin geri alınması bildirimi
içindir. [SEC N-54C formunun açıklaması](https://www.sec.gov/files/formn-54c.pdf)
bu bildirimle çekilme mekanizmasını açıklar.

**Bu çalışma sadece 16 issuer'a ait geçmiş BDC seçim bildirimlerinin
orijinal metinlerini doğrular.** Metin sinyali, şirketin ilgili tarihte
yaptığı bildirimin türüne ilişkin güvenilir kanıttır; ticari veya yasal
statünün bütün sonraki dönemlerde aynı kaldığını göstermeye yetmez.
Özellikle kurumsal birleşme, dönüşüm, yeniden adlandırma, kayıt durumu,
izaha dönük ek açıklamalar ve pay sınıfı değişiklikleri ayrıca incelenir.

Borsa listesi ile SEC issuer CIK eşleşmesi `security_id` ataması değildir.
Örneğin N-54A'da bir equity class kaydından söz edilmesi, A4'teki
ticker'ın hangi share class olduğunu otomatik doğrulamaz.
Tüm sınıflandırmalar **REVIEW_REQUIRED** kaldı.

## Kaynak zamanı ve kapanmayan kanıt kapıları

- A4 Nasdaq ve SEC kaynakları: 14 Ekim 2026. A5c SEC retrieval:
  15 Ekim 2026. A5d N-54A belge indirmesi: 15 Ekim 2026.
  `filingDate <= 2026-10-14` filtrelenmesi tek başına
  **point-in-time known_at** kanıtı değildir.
- SEC'ye ait son dönem `10-K` veya `10-Q` belgelerinin BDC
  statüsü/sınıf açıklaması henüz A5d kapsamında **okunmadı**;
  N-54A'ya ait text-signal alanları işletildi. Güncel statüyle sınıf
  kanıtı ayrıca eşleştirilecek.
- N-54C meta verisinin 16 issuer'ın alınan recent kayıtlarında olmaması
  **kesin yokluk** şeklinde yorumlanmayacak. Gerekirse tarihsel full
  filing index ve SEC düzenleyici statü geçmişi çapraz kontrol edilecek.
- BDC/SPAC ortak hisse kapsam politikası **onaylanmadı**;
  işlem yapılabilirlik/fiyat, pay sınıfı ve evren üyeliği için hiçbir
  otomatik promotion söz konusu değil.
- Kalıcı raw snapshot deposu, manual review/known_at/effective_at
  ve security master eşleştirmesi daha sonra tamamlanmalı.

**Mimari sınırlar:** BIST V2.0.1 production, US momentum/FIP çekirdeği,
SQL storage schema, Yahoo/fiyat, takvim, tradability ve live publication
değiştirilmedi. Bu değişiklikler yalnız ayrı A5d geliştirme dalındadır.
