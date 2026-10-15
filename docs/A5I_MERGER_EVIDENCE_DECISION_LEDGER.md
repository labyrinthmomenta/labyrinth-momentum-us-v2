# A5i — LIEN/REFI as-of SEC kanıtı ve 1.010 satırlık sürümlü karar envanteri

**Denetim tarihi:** 15 Ekim 2026. **Referans as-of:** 14 Ekim 2026.
**Durum:** \`EVIDENCE_LEDGER_REVIEW_ONLY\`.
**Politika/ledger sürümü:** \`a5i-evidence-ledger-review-v1\`.
**Karar:** Otomatik production onayı, legal status onayı ve security_id onayı **0**.

## Resmî kaynak zinciri ve tekrar üretim

| Kaynak | İmmutable kanıt SHA256 | Kapsam |
|---|---|---|
| A4 Nasdaq+SEC tam directory review | \`5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d\` | **13.287** listeleme kaydı |
| A4 resmî Nasdaq nasdaqlisted.txt | \`2dc5b607a42c3eefe9cf6f7d6e681c30b8fb55bb51ae04d998cdf51af02d6694\` | LIEN/REFI kaynak isimleri ve XNAS |
| A5 frozen instrument-review.json | \`ea4a8e3112e3e30d9c3e67fc33fac86a3a6aa3fcf2f58391ecc50896ba3bdb37\` | **1.010** orijinal REVIEW_REQUIRED |
| A5h SEC timeline & exhibits | \`7cee3b11745081f31774bb28f9949c769f583c688cc63941b52ca9ee6966c571\` | LIEN, REFI SEC CIK; N-14; 29 ek |
| **A5i tam karar ledger JSON** | \`306be7c6293649b367caa999fa374c1fcd7f7caa41af6f9f3bef58b95387922a\` | **1.010** açık review + LIEN/REFI overlay |

[A5i başarılı GitHub Actions — 208 Python testi](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38740703627)
ve [1.010 satır ledger, resmî SEC EFFECT notice ve REFI 10-Q ham kaynak dosyaları](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38740703627/artifacts/11975867265).
GitHub artifact saklama süresi 90 gündür, kalıcı kaynak arşivi değildir.

SEC belgelerinin gerçek alınma zamanı **15 Ekim 2026**, Nasdaq/A4
directory as-of **14 Ekim 2026**. Belge filingDate veya Nasdaq tarihinin
eski olması, SEC kaynak içeriğinin \`known_at=2026-10-14\` olarak
kanıtlandığı anlamına gelmez.

## Kritik düzeltme: 30 Eylül SEC EFFECT, N-14 değil N-2

LIEN resmî SEC [30 Eylül 2026 Notice of Effectiveness](
https://www.sec.gov/Archives/edgar/data/1843162/999999999526003107/xslEFFECTX01/primary_doc.xml)
bağlantısında uzantı \`.xml\` olsa da **gerçek sunucu yanıtı HTML'dir**.
SEC kaydının kaynak metnindeki açık alanlar:

| SEC notice alanı | Doğrulanmış değer |
|---|---|
| Notice | Notice of Effectiveness |
| Company name | Chicago Atlantic BDC, Inc. |
| CIK | \`0001843162\` |
| Form | **N-2** |
| File Number | **333-295756** |
| Effective Date | **30 Eylül 2026, 15:00** |

Ham SEC yanıtının SHA256 değeri
\`30e6f558c72ad5e6b2f08a7dcfa4a6201d9084a601a8d3945818fd3a23d9facd\`.

**Bu EFFECT'nin N-14 birleşme kayıt beyanının etkinliğine kanıt
olduğu iddiası yanlış olur.** Belge N-2'ye aittir; N-14'ün
etkinleşmesi, hissedar onayları veya merger effective time bu
EFFECT'den çıkarılamaz. Koddaki doğrulama artık SEC'nin HTML olarak
sunduğu etkinlik bildirimini, açık **CIK + Form + File Number** alanıyla
kontrol eder. Yanlış filer veya N-14 etiketi otomatik kabul edilmez.

EFFECT belgesinin orijinal ham yanıtı hash ile saklanmıştır;
ilk tanınmayan HTML biçimini belgelemek için aynı byte'ların
ayrı karantina kopyası da artifact'ta bulunur.

## REFI — Nasdaq common stock kanıtı, BDC onayı değil

REFI [SEC 2026-06-30 dönemine ait 10-Q asıl belgesi](
https://www.sec.gov/Archives/edgar/data/1867949/000119312526343398/refi-20260630.htm)
indirildi, SHA256
\`0ca7229e971b8975c4e8ecd8a21bd3f0f4f2a9035c98f0dab3cca3f0317b9acc\`,
**4.521.075 byte**.

SEC kapak tablosunda:

- **Title of Class**: Common Stock, $0.01 par value per share
- **Trading Symbol**: REFI
- **Exchange**: NASDAQ Global Market.

Aynı finansal rapor, REFI'nin geçmişte REIT olarak vergilendirilmeyi
seçtiğini, **planlanan birleşme öncesinde** Form N-54A sunarak BDC
statüsünü seçmesinin öngörüldüğünü anlatıyor. Bu **geleceğe dönük
ifadedir**, 14 Ekim itibarıyla N-54A seçiminin kesin gerçekleştiği
anlamına gelmez.

Kaynak taramasında 17 Haziran–14 Ekim aralığına ait frozen REFI
SEC submissions veri setinde **N-54A bulunamadı**; bu kayıt yokluğu
resmî tüm tarihsel arşivlerde N-54A hiç olmadığına dair kesin olumsuz
kanıt değildir. REFI için \`BDC_ELECTION=NOT_ESTABLISHED\`.

## LIEN ve REFI'nin A4/A5 statüsü: farklı kaynak kararı

| Sembol | A4 orijinal karar | A5/A5i enstrüman durumu | Yeni kurumsal olay güvenlik kapısı |
|---|---|---|---|
| **LIEN** | \`REVIEW_REQUIRED\` | 1.010 A5 incelemesinin içinde kalır | \`HOLD_FOR_CORPORATE_EVENT_AND_STATUS_REVIEW\` |
| **REFI** | \`INCLUDE\` (provisional common-stock candidate) | 1.010 A5 review satırları **içinde değil** | **Bağımsız** \`HOLD_FOR_CORPORATE_EVENT_AND_STATUS_REVIEW\` |

Kaynakta \`INCLUDE\` olan REFI **production eligible değildi**.
A5i, A4 kaynak gerçeğini geriye dönük olarak REFI için
\`REVIEW_REQUIRED\` ile değiştirmez. Bunun yerine karar ledger'ında
REFI için açık ayrı bir release hold ve \`explicit_release_hold=true\`
alanı bulunur. Bu alan **henüz production release pipeline'ına
bağlanmış bir enforcement kontrolü değildir**; ileride production
adayı seçen katman, ledger'daki bu engeli doğrulamadıkça geçişe izin
vermemelidir.

Her iki ticker'ın LIEN/REFI Nasdaq listing isimleri, 14 Ekim A4
orijinal \`nasdaqlisted.txt\` dosyası ve XNAS kodu üzerinden
doğrulandı. **Issuer CIK ≠ security_id**; pay sınıfı/MIC bilgileri
resmî kanıt adayıdır, nihai onay değildir.

## Orijinal tüm 1.010 REVIEW_REQUIRED kaydı

| A5 kaynak nedeni | A5i inceleme sayısı | Otomatik INCLUDE / approval |
|---|---:|---:|
| FINANCIAL_STATUS_REVIEW | 268 | 0 |
| FUND_NAME_REQUIRES_TYPE_EVIDENCE | 297 | 0 |
| SPAC_BDC_OR_FINANCIAL_REVIEW | 307 | 0 |
| TYPE_UNCONFIRMED | 128 | 0 |
| UNKNOWN_EXCHANGE_CODE / TXSE | 10 | 0 |
| **Toplam** | **1.010** | **0** |

10 TXSE kaydı A5 scope dışında **öneri**, onaylanmış EXCLUDE
değildir. Kalan **1.000 tür incelemesi** için bağımsız
security master, issuer-class, fon/REIT/SPAC/BDC kaynakları
ve açık kapsam politikası hâlâ gerekir.

Orijinal A4 sayıları değiştirilmedi:
\`INCLUDE=4.556\` (hepsi provisional),
\`EXCLUDE=7.721\`, \`REVIEW_REQUIRED=1.010\`,
**toplam=13.287**. A5i bir karar overlay raporudur, A4
directory verisini yeniden sınıflandıran production motoru değildir.

## LIEN–REFI merger status — belgelenen kanıt ≠ kapanış

17 Haziran imzalanan anlaşma ve 18 Haziran SEC 8-K ile
23 Eylül \`N-14 8C/A\` kaynakları A5g/A5h'de saklandı.
İki SEC filer için alınan filings metaverisi ve asıl ön proxy
metninde **14 Ekim tarihi itibarıyla kesin oylama sonucu,
tamamlanmış birleşme veya yeni security_id** doğrulanmadı.
Bu, anlaşmanın hiçbir zaman kapanmayacağına veya başka
yetkili borsa kaydında bilgi bulunmadığına dair iddia değildir.

Özellikle **N-2 EFFECT** kaydını,
**N-14 effectiveness** veya **merger closing** olarak
değerlendirmemek zorunludur.

A5i overlay alanları her iki issuer için:
\`merger_completion=NOT_ESTABLISHED\`,
\`voting_result=NOT_ESTABLISHED\`,
\`issuer_legal_status=NOT_APPROVED\`,
\`share_class_security_id=NOT_APPROVED\`,
\`production_eligible=false\`.

## Production öncesi kapanmamış şartlar

1. LIEN/REFI gerçek hissedar oylama sonuçları ve birleşme kapanış
   belgeleri: yetkili SEC / şirket / Nasdaq kaynakları, etkin tarih
   ve \`known_at\` ile **ayrı** doğrulanmalı.
2. REFI N-54A/N-54C düzenleyici seçim statüsü SEC'nin uygun
   filing kronolojisinden doğrulanmalı. \`N-2 EFFECT\` N-54A
   seçiminin kanıtı sayılamaz.
3. SEC CIK adayları ile resmî listed-security identity/share-class
   ve corporate action mapping ayrı doğrulanmalı.
4. Geri kalan 1.000 instrument-type ve 10 TXSE scope önerisi
   resmî master/type kanıtlarıyla nihai reviewer kararı almalı.
5. \`known_at\`, \`effective_at\`, kaynak bütünlüğü ve manual
   approval/denial sürümlenerek release pipeline'ında zorunlu
   enforce edilmeli. Mevcut **ledger overlay henüz production
   gate enforcement değildir**.
6. Ham resmi SEC/Nasdaq kaynakları 90 günlük GitHub
   artifact'tan daha uzun ömürlü izlenebilir arşive aktarılmalı.

**Değişmeyen katmanlar:** \`main\`, BIST V2.0.1 production,
US momentum/FIP hesaplama çekirdeği, Yahoo/fiyat, 90-seans
tradability evaluation, SQLite production şeması, canlı yayın
ve herhangi bir portföy pozisyonu. Bütün değişiklikler ayrı Draft
PR'dadır.
