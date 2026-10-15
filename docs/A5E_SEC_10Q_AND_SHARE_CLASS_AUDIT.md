# A5e — 16 BDC adayı: SEC 10-Q issuer ve pay sınıfı kanıt denetimi

**15 Ekim 2026 | REVIEW_ONLY.** Bu çalışma A4'ün 14 Ekim snapshot'ına
bağlanan A5c'nin 303 issuer SEC kaynak yanıtı ve A5d'nin 16 issuer için
17 N-54A/N-54A-A orijinal bildiriminden üretilmiştir.

## Canlı SEC kaynak doğrulaması

[Başarılı GitHub Actions (157 test)](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38728679096)
üzerinden şu şartlarla SEC 10-Q içeriği indirildi ve ayrıştırıldı:

- A5c tam rapor SHA256 `38b3773641c5e104ae6da7aaf19f32682b3aef66b6d0d4bb8fedeb9d3aa186ea`;
  303 raw SEC JSON ve seçilen 16 issuer dosyalarının ayrı kaynak hash'leri.
- A5d tam rapor SHA256 `b1a5b4ecdca3572ecd84baef85b5e9ec3ae47c422ec39ad6491c7cf89a2d11da`;
  16 issuer, 17 doğrulanmış özgün N-54A/A bildirimi ve ham dosya hash'leri.
- 16 issuer için `filingDate <= 2026-10-14` şartını sağlayan **en son**
  `10-Q` veya `10-K` başvurusu: **16 adet 10-Q, 0 adet 10-K fallback**.
- **16/16** SEC asıl finansal belge başarıyla indirildi, SHA256 ile ham olarak
  kaydedildi. **0** kaynak/indirme hatası. Bazı gerçek SEC inline-XBRL belgeleri
  20 MiB'den büyüktü; kontrol edilen 64 MiB üst sınırla yeniden çalışıldı.
- **16/16** dosyanın ilk 300 HTML tablo satırında, orijinal A4 ticker'ı,
  **Common Stock** başlığı ve NYSE/Nasdaq borsa adını **aynı satırda**
  içeren açık *kapak tablosu kanıt adayı* bulundu.
- **16/16** asıl rapor metninde `business development company` ifadesi var.
  Katı ifade örüntüsü bunların **11**'inde BDC statüsüyle ilgili cümle adayı
  üretti; GAIN, PNNT, PFLT, TPVG ve CCAP için bu özel örüntü yetersiz kaldı.
  Bu **5 şirketin BDC olmadığı anlamına GELMEZ**: örneğin GAIN/TPVG/CCAP
  belgelerinde `elected to be treated as a business development company`
  türünden ayrı ifadeler bulunuyor. **İnsan denetimi hâlâ gerekli**.
- En son 10-Q ile 14 Ekim arasında resmî SEC metadata'sında toplam
  **40** adet `8-K/8-K-A` bulundu; **başvuru içerikleri henüz incelenmedi**.
- Alınan A5c `filings.recent` alanında N-54C görülmemesi, çekilme
  bildirisinin hiç olmadığına veya seçim statüsünün kesin devam ettiğine
  ilişkin kanıt değildir.
- **Nihai BDC statü onayı 0, security_id/pay sınıfı onayı 0,
  production uygunluk onayı 0.**

Kaynak dosyaları, ham SHA256, retrieval time, SEC accession ve satır
adayları [GitHub Actions A5e artifact'ında](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38728679096/artifacts/11969461622)
saklandı. 90 gün tutulur; **kalıcı harici arşiv değildir**.

## Şirket bazında SEC 10-Q ve henüz okunmamış olay dosyaları

| Ticker | SEC başvuru tarihi | Asıl kaynak | Belgedeki pay | Borsa | BDC cümle işareti | Sonrası 8-K |
|---|---|---|---|---|---|---:|
| GAIN | 2026-08-06 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1321741/000132174126000017/gain-20260630.htm) | Common Stock | Nasdaq | İlave metin incelemesi | 4 |
| SAR | 2026-10-06 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1377936/000121390026107187/ea0306042-10q_saratoga.htm) | Common Stock | NYSE | İfade adayı | 2 |
| PNNT | 2026-08-10 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1383414/000119312526342350/pnnt-20260630.htm) | Common Stock | NYSE | İlave metin incelemesi | 5 |
| HRZN | 2026-08-04 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1487428/000143774926025689/hrzn20260630_10q.htm) | Common Stock | Nasdaq | İfade adayı | 3 |
| NMFC | 2026-08-03 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1496099/000149609926000029/nmfc-20260630.htm) | Common Stock | Nasdaq | İfade adayı | 1 |
| PFLT | 2026-08-10 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1504619/000119312526342352/pflt-20260630.htm) | Common Stock | NYSE | İlave metin incelemesi | 4 |
| CION | 2026-08-06 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1534254/000153425426000010/cion-20260630.htm) | Common Stock | NYSE | İfade adayı | 4 |
| SCM | 2026-08-10 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1551901/000110465926093435/scm-20260630x10q.htm) | Common Stock | NYSE | İfade adayı | 0 |
| GSBD | 2026-08-06 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1572694/000119312526338331/gsbd-20260630.htm) | Common Stock | NYSE | İfade adayı | 2 |
| ICMB | 2026-08-14 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1578348/000119312526352658/icmb-20260630.htm) | Common Stock | Nasdaq | İfade adayı | 0 |
| TPVG | 2026-08-05 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1580345/000158034526000025/tpvg-20260630.htm) | Common Stock | NYSE | İlave metin incelemesi | 2 |
| CCAP | 2026-08-10 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1633336/000119312526342351/ccap-20260630.htm) | Common Stock | Nasdaq | İlave metin incelemesi | 1 |
| OBDC | 2026-08-05 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1655888/000165588826000056/obdc-20260630.htm) | Common Stock | NYSE | İfade adayı | 3 |
| KBDC | 2026-08-10 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1747172/000119312526342385/kbdc-20260630.htm) | Common Stock | NYSE | İfade adayı | 2 |
| PSBD | 2026-08-05 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1794776/000119312526333791/psbd-20260630.htm) | Common Stock | NYSE | İfade adayı | 6 |
| LIEN | 2026-08-13 | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1843162/000119312526347342/lien-20260630.htm) | Common Stock | Nasdaq | İfade adayı | 1 |

**Borsa tablosu kanıtı**, SEC issuer'ın kayıtlı pay sınıfı başlığını ve
ticker'ını destekler; bağımsız bir NYSE Security Master/ayrı pay sınıfı
kimliği veya tarihlendirilmiş `security_id` ataması değildir.
Ticker formatının geçmişte değişmiş olup olmadığı ve listeleme statüsü
başka kaynakla teyit edilmelidir. Belgelerdeki `Common Stock` satırlarının
tamamı sistemde adi hisse olarak **otomatik işlenmedi**.

## Güvenlik ve sonraki zorunlu işler

1. **40 adet 8-K/A başvurusunun resmî asıl belgelerini** tarayıp birleşme,
   geri çekilme, delist, dönüşüm, ticker/share-class değişikliği veya olay
   riski açısından inceleme kuyruğuna ekle. Hiçbirini topluca 'önemsiz'
   varsayma. Şimdilik `post_financial_events_checked=false`.
2. GAIN, PNNT, PFLT, TPVG ve CCAP için yetersiz kalan katı BDC cümle
   örüntüsünü yalnız kanıt işaretlerini zenginleştirerek geliştir; yasal
   statü çıkarımını otomatikleştirme.
3. Resmî NYSE/Nasdaq listeleriyle güvenilir listed security ID, class,
   MIC ve event effective date eşleştir; SEC CIK yalnız issuer düzeyinde
   kanıt adayıdır. Kapsam politikası BDC common hisseler için açıkça
   onaylanmadan type/class promotion yapılmaz.
4. 14 Ekim `as_of` ile SEC retrieval'ın 15 Ekim `known_at` farklılığı
   korunur. SEC `filingDate` geçmişte bilinirliğin tek başına kanıtı değildir.
5. Gerçek ham SEC belge dosyaları Git'e eklenmez; checksum/adres/veri
   alınma tarihleriyle artifact olarak saklanır.
6. BIST V2.0.1 production, US momentum/FIP çekirdeği, Yahoo/fiyat,
   tradability, SQLite schema ve canlı yayın **değiştirilmez**.

**Sonuç:** 16 SEC kapak tablosunda ilgili ticker için adi hisse türü kanıtı
bulundu; ancak *issuer BDC legal status*, *security master kimliği*
ve *post-quarter 8-K incelemesi* tamamlanmadığı için 16 şirketin
tamamı **REVIEW_REQUIRED** kalmaktadır.
