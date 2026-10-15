# A5h — Tam SEC ek belge arşivi ve LIEN–REFI N-14 / EFFECT kronolojisi

**İnceleme tarihi:** 15 Ekim 2026. **As-of snapshot:** 14 Ekim 2026.
**Durum:** \`DOCUMENTS_CAPTURED_REVIEW_ONLY\`. Nihai birleşme,
hissedar oylaması, BDC statüsü, security_id ve production onayı verilmedi.

## Resmî kaynak denetimi

Başlangıç: A5g'nin dondurulmuş \`a5g-exhibits-and-merger.json\` çıktısı,
SHA256 \`58ed3bee2f66e14bbc6930747569388b1b28f127927a6125377b3cf6cda184f5\`.
Başlamadan önce **34** SEC *Filing Detail* kaynak index'i, daha önce
indirilmiş **17** asıl exhibit dosyası ve bunlara bağlı SHA256'lar
yeniden doğrulandı.

- **29/29** kalan exhibit, yalnızca SEC'nin orijinal HTTPS kaynak
  adresinden indirildi, içeriği incelemeye uygun metin olarak
  doğrulandı, ham dosya ve SHA256 ile saklandı.
- Böylece A5g + A5h içinde toplam **46/46 EX-\*** exhibit'in ham dosyası
  toplandı. **27 EX-99.1 + 2 EX-99.2** A5h'de tamamlandı.
- **LIEN** SEC CIK \`0001843162\` ve **REFI** SEC CIK \`0001867949\`
  için resmî SEC submissions JSON ayrı ayrı indirildi, gerçek CIK
  (SEC'nin sıfır dolgulu string veya sayı biçiminde göndermesi fark
  etmez) teyit edildi, kaynak SHA256 ve \`retrieved_at\` saklandı.
- LIEN'in **23 Eylül 2026** tarihli N-14 değişiklik dosyasının
  **4.612.120 byte** ham SEC metni de indirildi, kaynak SHA256
  \`1de5f953a1197f8617eb0826989fbb4b36e97f2387da67a5e85faeeeb3845a9e\`
  kontrol edildi.
- Kaynak indirme/ayrıştırma hatası **0**; **196** regresyon testi geçti.
- [Başarılı canlı GitHub Actions koşusu](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38737013765)
- [29 asıl SEC exhibit + iki SEC submissions JSON + N-14 aslı ve denetim dosyası](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38737013765/artifacts/11973313072)
  — **90 günlük GitHub artifact**, kalıcı veritabanı değildir.
- Yeni A5h \`a5h-exhibits-and-timeline.json\` SHA256
  \`7cee3b11745081f31774bb28f9949c769f583c688cc63941b52ca9ee6966c571\`.

İndirilen bu 29 belgenin tüm metinleri **kaynak doğrulaması**
açısından tamamlandı; sözleşmelerin hukukî sonucu ve şirketlerin
faaliyet/yasal statüleri bakımından **insan incelemesi tamamlanmadı**.

## 29 exhibit içeriğinde otomatik inceleme sinyalleri

- 28/29 belgede A5g'nin sınırlı birleşme/kapanış/menkul kıymet
  değişikliği örüntüleri otomatik bir işaret üretmedi.
- **HRZN** [2026 Q2 finansal sonuç açıklaması, EX-99.1](https://www.sec.gov/Archives/edgar/data/1487428/000143774926025688/ex_998180.htm)
  içinde birleşme gideri ve \`closing\` ifadesi bağlama duyarlı
  inceleme sinyali oluşturdu. Bu **LIEN–REFI birleşmesiyle ilgili
  değildir**, HRZN'nin tamamlanmış kurumsal işlemine veya ticker
  değişikliğine dair karar verilmemiştir.
- Bu sinyal sayıları *gerçekleşen olay sayısı* değildir.
  Standart SEC kapak ifadeleri, yatırımcı açıklamaları, olumsuz
  ve geleceğe yönelik cümleler yanlış pozitif yaratabilir.

## LIEN–REFI — iki bağımsız SEC filer kronolojisi

SEC filer kaynağı (timestamp + ham hash çıktı dosyasında):

- [LIEN resmî SEC submissions](https://data.sec.gov/submissions/CIK0001843162.json)
- [REFI resmî SEC submissions](https://data.sec.gov/submissions/CIK0001867949.json)

| Tarih | Filer / Form | Kanıtın durumu | Güvenli yorum |
|---|---|---|---|
| 17–18 Haziran | LIEN 8-K + EX-2.1 | A5g orijinal birleşme anlaşması | İmzalanmış sözleşme; kapanış değil |
| 31 Temmuz | LIEN \`N-14 8C\` | SEC form metaverisi | İlk kayıt/proxy |
| 11 Ağustos | REFI \`DEFA14A\` | SEC form metaverisi | Ek oylama/solicitation bildirimi; oy sonucu değil |
| 13 Ağustos | LIEN \`DEFA14A\` | SEC form metaverisi | Ek oylama/solicitation bildirimi; oy sonucu değil |
| 23 Eylül | LIEN \`N-14 8C/A\` | **Asıl SEC metni indirildi** | Ön değişiklik/ortak proxy; hâlâ \`PRELIMINARY\` |
| 30 Eylül | LIEN \`EFFECT\` | **SEC submissions form/metaveri kaydı** | SEC kayıt beyanının etkinleşme bildirimi; *birleşme kapanışı değil* |

**N-14 asıl belgesi:**
[0001140361-26-037360](https://www.sec.gov/Archives/edgar/data/1843162/000114036126037360/ny20077966x2_n148ca.htm).
Kaynak metninde \`registration statement\`,
\`joint proxy statement\`, \`preliminary\` ve birleşme planı
işaretleri var. \`EFFECT\` için bu koşuda yalnız SEC submissions
metaverisi doğrulandı, **EFFECT asıl XML içeriği ayrıca indirilmedi**.

Her iki SEC filer'ının 17 Haziran – 14 Ekim aralığındaki
\`filings.recent\` kaydında, kapsam dahilindeki bu dönemde
**ayrıca listelenmiş bir oylama sonucuna veya birleşme kapanışına
kesin kanıt oluşturacak içerik doğrulanmadı**. Bu bir kaynak tarama
sonucudur; tüm filing içeriklerinin, bağımsız borsa kayıtlarının veya
hissedar toplantı sonuçlarının eksiksiz incelendiği iddiası değildir.
İki filer'ın ilgili SEC \`filings.files[]\` listesinde ek eski parça
bildirilmedi; yine de geçmişte ilgili form hiç verilmediğine dair
mutlak kanıt sayılmaz.

**As-of kararı:** \`LIEN_REFI_MERGER_COMPLETION=NOT_ESTABLISHED\`;
\`VOTE_RESULT=NOT_ESTABLISHED\`; \`REFI_BDC_ELECTION_NOT_APPROVED\`.
LIEN ve REFI birbirine otomatik bağlanmadı, ticker değişikliği /
security_id dönüşümü yapılmadı, \`production_eligible=false\`.

## Mevcut kapılar

1. **Oylama ve birleşme kapanışı:** definitive proxy, kayıt/proxy'nin
   son eki, LIEN/REFI özel hissedar toplantısının fiilî sonuçları,
   merger effective time, SEC closing 8-K ve varsa 14 Ekim'e kadar
   resmî Nasdaq duyurusu ayrıca çapraz kontrol edilmeli.
   Dosyada \`EFFECT\` görülmesi tek başına bunların yerine geçmez.
2. **REFI BDC election:** N-54A/N-54C zinciri, REFI'nin BDC statüsünü
   kazanması veya geri çekmesi ile ilgili ayrıca resmî belge;
   yokluk varsayımı yok.
3. **Menkul kıymet kimliği:** tarihli borsa security master, Nasdaq
   listing security id / MIC / class ve gerçek etkinleşme tarihi;
   yalnız SEC issuer CIK ve proxy ile çözülmez.
4. **Belge içeriği:** 29 yeni exhibit ve önceki 17 exhibit kaynağı
   toplanmış olsa da tamamının hukuki/operasyonel manuel gözden
   geçirilmesi ve material-event kararı ayrı denetimdir.
5. **Zaman:** SEC filing date ile 15 Ekim 2026 kaynak
   retrieval time ayrı. \`known_at=2026-10-14\` her belge
   için bağımsız kanıtlanmadı.
6. **Arşivleme:** 90 günlük GitHub artifacts production için kalıcı
   kaynak arşivi sayılamaz. Snapshot yaşam döngüsü ayrıca kurulmalı.

**Değişiklik sınırları:** BIST V2.0.1 production,
Labyrinth Momentum US V2 hesaplama/FIP çekirdeği, Yahoo/fiyat,
90-seans tradability, SQLite production şeması ve canlı yayın
değiştirilmedi; \`main\` merge yapılmadı. A5h ayrı Draft PR'dadır.
