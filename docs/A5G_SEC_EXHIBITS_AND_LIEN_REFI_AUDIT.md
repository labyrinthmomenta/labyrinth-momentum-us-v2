# A5g — SEC Item 9.01 ekleri ve LIEN–REFI birleşme kanıtı

**İnceleme tarihi:** 15 Ekim 2026. **As-of:** 14 Ekim 2026.  
**Status:** \`INDEXES_CAPTURED_REVIEW_ONLY\`. **Hiçbir issuer, security_id, BDC statüsü, gerçekleşmiş birleşme, ticker değişimi veya production kararı otomatik onaylanmadı.**

## 1. Resmî kaynak zinciri

A5f'nin **40** orijinal SEC 8-K kaydı ve JSON raporu birebir
SHA256 ile tekrar doğrulandı:

- A5f rapor SHA256: \`c5b91a0c0b886b2baf19dfc9c5891de9465b846ae9ef0055eeffcca869512b70\`.
- A5f sonucun \`human_review_complete=false\`, \`production_eligible=false\`,
  \`event_occurred_confirmed=0\` ve özgün kaynak SHA256 / boyut kontrolleri korunur.
- Tam **33 Item 9.01** başvurusunun resmî SEC *Filing Detail — Document
  Format Files* dizini okundu.
- Ayrıca **18 Haziran 2026 tarihli, A5f 10-Q sonrası penceresinin
  DIŞINDA kalan** LIEN 8-K'sı, ayrı tarihsel birleşme kanıtı olarak
  eklendi. Yanlışlıkla A5f'nin 40 dosyasından biri sayılmadı.
- **34/34 dizin** başarıyla indirildi, dosya SHA256 ve SEC CIK/accession
  kaynak kimliği doğrulandı. **46** resmî exhibit referansı bulundu.
- Beş A5f öncelikli accession ve tarihsel LIEN birleşme accession'ı
  için **17/17 metin exhibit'i** gerçek resmî SEC'den indirildi,
  kaynak hash/receipt saklandı. Kalan **29 exhibit** sadece
  indeks metaverisi olarak kaydedildi, içerik doğrulanmadı.
- [Başarılı A5g GitHub Actions — 183 test](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38734298003)
- [34 orijinal SEC Filing Detail dizini, 17 ham ek, SHA256 ve JSON denetim artifact'ı](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38734298003/artifacts/11972540037), **90 günlük** saklama. Kalıcı arşiv henüz kurulmadı.
- A5g çıktı \`a5g-exhibits-and-merger.json\` SHA256:
  \`58ed3bee2f66e14bbc6930747569388b1b28f127927a6125377b3cf6cda184f5\`.

Kaynak alım zamanı 15 Ekim, filingDate 14 Ekim veya öncesi.
**Bu iki zaman \`known_at\` açısından eşit sayılmamalıdır.**

## 2. SEC 8-K Item 9.01 envanteri

| Kapsam | SEC dosya dizini | Exhibit | Metin incelemesi |
|---|---:|---:|---:|
| A5f'de Item 9.01 olan 8-K | 33 | 41 | Yalnız 5 öncelikli başvuru exhibit'leri |
| A5f dışındaki tarihsel LIEN 18 Haziran 8-K | 1 | 5 | 5/5 |
| **Toplam** | **34** | **46** | **17/46** |

33 post-10-Q Item 9.01 dizininden **birinde (CION, accession
\`0001104659-26-108606\`)** SEC "Document Format Files" tablosunda
EX-* türü kayda rastlanmadı. Bu, eksik ek bulunmadığı veya CION'da
olay olmadığı anlamına gelmez. Diğer 28 öncelik dışı exhibit
sadece metaveri olarak saklandı; **toplam 29 kaynak içeriği açık**.

## 3. LIEN–REFI — öncelikli birleşme incelemesi

### Haziran 2026: anlaşma, ancak kapanış değil

[18 Haziran 2026 LIEN SEC 8-K, accession 0001213900-26-069853](https://www.sec.gov/Archives/edgar/data/1843162/000121390026069853/0001213900-26-069853-index.htm)
içinde 17 Haziran 2026 tarihli
[EX-2.1 Agreement and Plan of Merger](https://www.sec.gov/Archives/edgar/data/1843162/000121390026069853/ea029515901ex2-1.htm)
bulunuyor ve **ham orijinal belge indirildi**.

Dizinde bulunan, indirilen ve hash'i korunan 5 metin eki:

| Exhibit | Resmî belge | Kanıtın niteliği |
|---|---|---|
| EX-2.1 | [17 Haziran tarihli birleşme anlaşması](https://www.sec.gov/Archives/edgar/data/1843162/000121390026069853/ea029515901ex2-1.htm) | Plan, sözleşme koşulları, kapanış koşulları; **kapanış gerçekleşti kanıtı değil** |
| EX-10.1 | [REFI hissedarları için destek anlaşması *formu*](https://www.sec.gov/Archives/edgar/data/1843162/000121390026069853/ea029515901ex10-1.htm) | Sözleşme şablonu; her hissedarın imzaladığını göstermez |
| EX-10.2 | [LIEN hissedarları için destek anlaşması *formu*](https://www.sec.gov/Archives/edgar/data/1843162/000121390026069853/ea029515901ex10-2.htm) | Sözleşme şablonu; oy kullanıldığı/işlem tamamlandığı kanıtı değil |
| EX-99.1 | [Ortak basın açıklaması](https://www.sec.gov/Archives/edgar/data/1843162/000121390026069853/ea029515901ex99-1.htm) | Birleşme niyeti ve öngörülen koşullar |
| EX-99.2 | [Yatırımcı sunumu](https://www.sec.gov/Archives/edgar/data/1843162/000121390026069853/ea029515901ex99-2.htm) | Planlanan birleşmeye dair yönetim sunumu |

REFI'nin BDC rejimine geçerek LIEN'e katılması, LIEN'in devam eden
halka açık şirket olması planlanıyor. **Planlanan yapı ile tamamlanmış
işlem birbirine eşit değil**.

### Ağustos 2026: süreç hâlâ önerilen birleşme diliyle anılıyor

[13 Ağustos 2026 LIEN SEC 8-K, accession 0001213900-26-088673](https://www.sec.gov/Archives/edgar/data/1843162/000121390026088673/0001213900-26-088673-index.htm)
içinden:

- [EX-99.1, finansal sonuçlar ve birleşme güncellemesi](https://www.sec.gov/Archives/edgar/data/1843162/000121390026088673/ea030179101ex99-1.htm)
- [EX-99.2, earnings presentation](https://www.sec.gov/Archives/edgar/data/1843162/000121390026088673/ea030179101ex99-2.htm)

orijinal metinleri indirildi. Açıklamalarda "proposed merger"
niteliği, planlanan işlemin koşulları ve geleceğe dönük ifadeler var.
Bu belgeler **14 Ekim itibarıyla tamamlanmış birleşme veya ticker
değişikliği** kanıtı değildir. Ayrıca 14 Ekim'e kadarki diğer
resmî SEC N-14/proxy, etkinlik ve hissedar oylaması sonuçları
ayrı incelenmeden negatif kapanış hükmü de kurulamaz.

**A5g önerisi:** LIEN için \`MERGER_PENDING_EVIDENCE_REVIEW\`;
REFI'yi veya LIEN'i farklı security_id altında otomatik birleştirme
veya mevcut A4/A5 sınıflandırmasından çıkarma yok.

## 4. Öncelikli Item 1.01 ekleri

| Issuer | SEC filing date | İndirilen exhibit'ler | İnceleme odağı |
|---|---|---|---|
| **SAR** | 9 Ekim 2026 | [EX-10.1](https://www.sec.gov/Archives/edgar/data/1377936/000121390026108523/ea030824201ex10-1.htm) | Credit and security agreement değişikliği |
| **PNNT** | 1 Eylül 2026 | [EX-10.1](https://www.sec.gov/Archives/edgar/data/1383414/000119312526378418/d528646dex101.htm), EX-10.2, EX-10.3 | Notes purchase ve registration rights belgeleri |
| **HRZN** | 9 Eylül 2026 | EX-10.3, EX-10.5, EX-10.8 | Indenture / financing / servicing değişiklikleri |
| **OBDC** | 8 Eylül 2026 | EX-10.1, EX-10.2, EX-10.3 | CLO XXVI, indenture ve finansman düzenlemeleri |

Herhangi bir maddede geçen \`acquisition\`, \`amendment\`, \`closing\`
veya \`termination\` ifadesi, bu hisse senedinin devri, BDC statüsünün
sona ermesi ya da listeden çıkarılması olarak **sınıflandırılmadı**.
Bunlar ilgili sözleşmelerin tüm hükümleri/ilgili yükümlülük ve bağlı
şirket kimlikleri gözden geçirilerek değerlendirilmelidir.

## 5. Kalan zorunlu kapılar

1. **LIEN–REFI** işleminde 14 Ekim 2026 öncesi son bağımsız SEC
   N-14/N-14-A, proxy/hissedar onayları, \`EFFECT\`, closing 8-K ve
   Nasdaq işlem kimliği değişikliği çapraz kontrolü yapılmalı.
   \`EFFECT\` bir kayıt bildiriminin etkinliğine ilişkin olabilir;
   birleşme kapanışıyla eşit tutulmamalı.
2. **29 exhibit** henüz içerik düzeyinde doğrulanmadı; yalnızca
   dosya adı/tür/SEC dizin kaydı saklandı. Normal öncelikli kayıtların
   kendileri "olay yok" diye kapatılamaz.
3. SEC Item 9.01 belgesinin yokluğu/EX-* listesinde sıfır olması,
   share-class değişikliği yaşanmadığı anlamına gelmez.
4. Resmî Nasdaq/NYSE security-master, MIC, share class, effective date,
   N-54C geçmişi ve \`known_at\` vs \`as_of\` ayrımı halen açık.
5. **16 BDC issuer için geçerli durum**, \`issuer_bdc_status=REVIEW_REQUIRED\`,
   \`share_class=REVIEW_REQUIRED\`, \`production_eligible=false\`.
   A5g'de hiçbir otomatik promotion, yayın veya pozisyon kararı yok.

**Korunan alanlar:** GitHub \`main\`, BIST V2.0.1 production,
US momentum/FIP hesaplama çekirdeği, Yahoo/fiyat/tradability katmanı,
SQLite şema ve canlı yayın değiştirilmedi.
