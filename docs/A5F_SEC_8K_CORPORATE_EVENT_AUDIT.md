# A5f — SEC 8-K kurumsal olay kanıt denetimi (16 BDC issuer)

**Durum: REVIEW_ONLY.** A5e'nin 16 issuer için doğruladığı 10-Q/adi hisse
tablo kanıtını değiştirmeden, bu 10-Q'lardan 14 Ekim 2026 tarihine kadar
yapılan SEC 8-K/8-K-A başvurularını asıl belge düzeyinde inceleme kuyruğuna
aldık. Bu çalışma otomatik kurumsal olay gerçekleşme kararı, BDC yasal
statüsü, pay sınıfı `security_id` veya production onayı vermez.

## Tekrar üretilebilir kaynak zinciri

- A5e kaynak raporu: `a5e-financial-evidence.json`, tam SHA256
  `a58638402bbdc59b7afb2de3dfe439c6672cc0a1ede40fb59bd8a283aea7612f`.
- A5f indirme öncesi, 16 kaynak SEC 10-Q ham dosyasının SHA256 ve
  uzunluğu rapor ile **tek tek** eşleştirildi. 16 issuer CIK ve 40
  erişilecek 8-K accession/filing date/source URL envanteri değiştirilemez.
- [Tek seferlik başarılı A5f GitHub Actions](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38731812676):
  **174 Python testi geçti; 40/40 gerçek SEC asıl 8-K dosyası indirildi
  ve doğrulandı; 0 kaynak hatası**.
- Asıl 40 SEC HTML + tam satır bazlı kanıt:
  [A5f kaynak artifact'ı](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38731812676/artifacts/11971401155)
  (90 gün; **kalıcı bağımsız arşiv değil**).
- A5f `a5f-8k-evidence.json` tam SHA256:
  `c5b91a0c0b886b2baf19dfc9c5891de9465b846ae9ef0055eeffcca869512b70`.
  Her belgenin form, issuer CIK, accession, filing date, resmi URL,
  retrieval zamanı, kaynak SHA256 ve metin/Item işaretleri JSON'da bulunur.
- Dönem: A5e `10-Q` tarihi ile **14 Ekim 2026** (dahil). SEC
  gerçek dokümanları **15 Ekim 2026** alındı. Filing tarihi
  `known_at` yerine geçmez.

## 40 gerçek 8-K için ilk inceleme önceliği

| Kaynak temelli kategori | Başvuru | Durum |
|---|---:|---|
| **Yüksek öncelik**: metinde önerilen merger/acquisition | **1** | LIEN; öneri/niyet bildirimi, tamamlanmış birleşme değil |
| **Yükseltilmiş öncelik**: Form 8-K `Item 1.01` | **4** | SAR, PNNT, HRZN, OBDC; sözleşme içeriği ve varsa exhibits incelenecek |
| **Normal kuyruk**: diğer 8-K başvuruları | **35** | 8-K ve ekleri tamamıyla okunmadan "olaysız" kararı verilmez |
| **Toplam** | **40** | **Otomatik production onayı 0** |

### Öncelikli SEC accession dosyaları

| Ticker | Filing date | Gözlenen aday kanıt | Resmî SEC asıl belge |
|---|---|---|---|
| **LIEN** | 2026-08-13 | Metinde REFI ile **önerilen birleşme** ifadesi | [0001213900-26-088673](https://www.sec.gov/Archives/edgar/data/1843162/000121390026088673/ea0301791-8k425_chicago.htm) |
| SAR | 2026-10-09 | `Item 1.01` ve `Item 2.03` | [0001213900-26-108523](https://www.sec.gov/Archives/edgar/data/1377936/000121390026108523/ea0308242-8k_saratoga.htm) |
| PNNT | 2026-09-01 | `Item 1.01` ve `Item 2.03` | [0001193125-26-378418](https://www.sec.gov/Archives/edgar/data/1383414/000119312526378418/d528646d8k.htm) |
| HRZN | 2026-09-09 | `Item 1.01` | [0001437749-26-029978](https://www.sec.gov/Archives/edgar/data/1487428/000143774926029978/hrzn20260909_8k.htm) |
| OBDC | 2026-09-08 | `Item 1.01` ve `Item 2.03` | [0001193125-26-385210](https://www.sec.gov/Archives/edgar/data/1655888/000119312526385210/d168192d8k.htm) |

LIEN 8-K'sında REFI'nin şirkete birleşmesine yönelik **öneri ve
hissedar onayı sürecinden** bahsediliyor. Bu bilgi bir birleşme
konusunun varlığına kanıttır, **birleşmenin gerçekleştiği** veya
14 Ekim itibarıyla REFI/LIEN ticker'larının değiştiğine dair nihai
kanıt değildir. 8-K'nın sonraki başvuruları, pay sınıfı ve listelenme
olayları ayrıca izlenmelidir.

### SEC Item dağılımı (örtüşen sayılar)

| Item | Sayı | İnceleme amacı |
|---|---:|---|
| 1.01 | 4 | Material definitive agreement |
| 2.02 | 16 | Finansal sonuç açıklamaları |
| 7.01 | 17 | Regulation FD açıklamaları |
| 8.01 | 7 | Other Events |
| 9.01 | 33 | **Ek belgeler / exhibits varlığına işaret edebilir** |

Yukarıdaki Item sayıları aynı 8-K'da birlikte bulunabilir. 2.01, 3.01
ve 5.03 başlıkları bu 40 belgenin otomatik item taramasında görünmedi;
**başlık görülmemesi kurumsal olay olmadığını ispatlamaz.**
5.02 ve 5.07 gibi başka form başlıkları da tam JSON'da korunur.

## Sahte pozitif engeli ve yorum sınırları

İlk çalışma koşusunda 40 belgenin standart kapak tablosundaki
`Trading Symbol(s)` ifadesi hatalı olarak 40 ayrı hisse/ticker değişimi
uyarısı üretiyordu. SEC 8-K standardına ait **rutin form metni** olan
bu başlık artık kurumsal değişiklik kanıtı sayılmıyor.
[Yeniden çalıştırılan 174 testlik son koşuda](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38731812676)
**ticker/share-class değişimi için otomatik sinyal 0**; tek
non-boilerplate birleşme/acquisition **metin işareti LIEN**.
Bu sonuç 40 dosyada hiç ticker/pay sınıfı değişikliği
olmadığı anlamına gelmez.

`Item 1.01` maddesi varsa mutlaka birleşme olduğu
varsayılmaz; sözleşmeler kredi, borçlanma veya diğer işlemler olabilir.
`merger` gibi anahtar sözcükler öneri, taslak, gelecek dönem veya
olumsuz cümle içinde geçebilir. Tespit edilen sözcükler
`event_occurred_confirmed=false` kalır. `Form 8-K` asıl belge ve
`Item 9.01` referansı, ayrıca ekli exhibits veya
statü güncellemelerinin tamamının incelendiği anlamına gelmez.

SEC N-54C'nin 16 issuer A5c `filings.recent` evreninde
görülmemesi, geçmişte hiç gönderilmediği ve BDC statüsünün
tüm tarihler boyunca değişmediği yönünde **kanıt değildir**.
SEC'nin [Form N-54C açıklaması](https://www.sec.gov/files/formn-54c.pdf)
bu bildirimin ayrı bir düzenleyici işlem olduğunu göstermektedir.

## Kapanış için açık denetim kapıları

1. Önce **LIEN–REFI** önerilen birleşmesinin anlaşma metni, yatırımcı
   oylaması, sonradan sunulan 8-K'lar, etkinleşme ve security/ticker
   değişimi gerçekten olmuş mu bakılmalı. *Proposed* durumundan
   *completed* durumuna otomatik geçiş yok.
2. SAR, PNNT, HRZN ve OBDC'de `Item 1.01` sözleşme referansları ve
   `Item 9.01` altında ilişkilendirilmiş **exhibit belgeleri** incelenmeli.
3. Kalan 35 asıl 8-K için insan kaynaklı kontrol tamamlanmalı;
   henüz `human_review_complete=false`.
4. Resmî security master ve/veya yetkili borsa kayıtlarıyla ticker,
   share-class, MIC ve corporate-action effective date çapraz
   doğrulanmalı. **16 issuer'ı production'a alma kararı verilmedi.**
5. A5f 40 belgenin asıl kaynaklarını doğrular, yalnız bu 40 belgenin
   post-10-Q penceresini kapsar. Daha eski tarihlerdeki olaylar ve
   `N-54C` geçmişi ayrı kontrol edilmelidir.
6. `known_at` / `effective_at` ayrımı ve kalıcı ham snapshot arşivi
   production öncesi tamamlanmalıdır.

**Korunan sınırlar:** GitHub `main`, BIST production ve US hesaplama
çekirdeği/momentum/FIP, fiyat/Yahoo, 90-seans tradability, SQLite
migrasyon ve canlı yayın bu çalışma tarafından değiştirilmedi.
