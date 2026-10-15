# A5k — 13.287 satırlık tam evren emniyet kontrolü ve dokuz şirket SEC tür pilotu

**15 Ekim 2026 | Frozen directory as-of: 14 Ekim 2026.**
**Durum: REVIEW_ONLY / DENY-ONLY; production'a bağlı değil.**

A5k'de daha önce 1.011 aday için kurulan A5j denetimi tüm
A4 resmî listed universe'a genişletildi. Ayrıca resmî SEC
asıl dosyaları üzerinden **3 SPAC, 3 REIT ve 3 closed-end
fund adayı** ayrı bir kanıt pilotunda incelendi.
**Hisse türü, security_id, BDC/REIT hukukî statü veya canlı
yayın için hiçbir ALLOW/approval üretilmedi.**

## A. Kaynak bütünlüğü ve tüm liste satırlarının değerlendirilmesi

Dondurulmuş kaynaklar:

| Kaynak | Hash SHA256 |
|---|---|
| Nasdaq+SEC A4 \`directory-review/review.json\` (13.287 rows) | \`5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d\` |
| Nasdaq \`nasdaqlisted.txt\` | \`2dc5b607a42c3eefe9cf6f7d6e681c30b8fb55bb51ae04d998cdf51af02d6694\` |
| Nasdaq \`otherlisted.txt\` | \`12deeb989a1b515304eda04318a0af1db127ff6340d1055329c62d9a5cbcde28\` |
| SEC \`company_tickers_exchange.json\` | \`c90bb2d57bb62fae8171abf37b7eb040917f9fb6b5238e6d5dc028baaec318e5\` |
| A5j \`a5j-type-evidence-triage.json\` (1.010 row) | \`48e686707c763b71c1ecb0c63a7361a87df04dec59ed2d75873250fdd64b1ed5\` |
| A5j \`a5j-release-gate-simulation.json\` | \`ade63abe33ed1f80e7c5c8f866473cc93cf10a0a1dca19abb2354601e6909d8f\` |

A5k önce resmî Nasdaq **iki** metin dosyasını ve SEC
orijinal JSON'unu tekrar parser'dan geçirir; 13.287 adet
A4 satırını birebir yeniden üretip önceki kararlar ve
kaynak SHA değerleriyle karşılaştırır. A5j'nin 1.010
review satırı aynı ticker+MIC+kaynak bazında bağlanır;
bozuk/silinmiş/sahte karar veya SHA, tekrar eden kaynak
listing key ve kaybolan REFI blokajı fail-closed'dur.

| Önceki A4 durumu | Satır | A5k yayın kontrolü |
|---|---:|---|
| INCLUDE — yalnız geçici aday | 4.556 | **4.556 DENY**: 4.555 sınıf/onay yok + 1 REFI corporate-action hold |
| REVIEW_REQUIRED | 1.010 | **1.010 DENY**: menkul kıymet türü/onayı açık |
| EXCLUDE | 7.721 | **7.721 dışlama**, otomatik üretim yetkisi yok |
| **Tüm liste** | **13.287** | **Hiçbir satıra publication izin verilmedi** |

**Tüm adaylar: 5.566/5.566 DENY, 0 ALLOW.**
REFI orijinal A4 \`INCLUDE\` durumunda kalırken
\`DENY_REFI_PENDING_MERGER_AND_BDC_ELECTION\` uyarısıyla
ayrı güvenlik blokajı alır. LIEN normal 1.010
\`REVIEW_REQUIRED\` kümesinde tutulur.

**Tam evren raporu SHA256**
\`e31bcca870189207e9273eea6ba4e48a55949e78822d2b7e8feb7fb3fc851a76\`.

Bu güvenlik kontrolü **gerçek yetkili reviewer
onayı/veri kaynağı imzasını doğrulamıyor**; hiçbir
ALLOW işlevi bulunmuyor ve US canlı yayın/production
koduna bağlanmış değil. Tek başına yeni
production universe oluşturmaz.

## B. Resmî SEC enstrüman türü kanıt pilotu — 9 issuer

A5j'nin kaynaklı 1.010 kayıt içinden **CIK eşleşmesi bulunan
dokuz farklı issuer** seçildi. 14 Ekim'e kadarki
son kullanılabilir araştırma formu SEC
\`submissions\` üzerinden seçildi;
asıl SEC dosyası izinli SEC Archives HTTPS URL'sinden
indirildi. Her ham JSON ve asıl belge için SHA256,
SEC CIK, accession, filingDate ve \`retrieved_at\` korundu.

| Ticker | Kaynak SEC formu, filing date | Sinyal ve inceleme yorumu | SEC resmî asıl dosya |
|---|---|---|---|
| **AACI** | 10-Q, 12 Ağustos | Blank-check/SPAC dili; unit/warrant ve class-title işaretleri; **aynı satır Common Stock tespit edilmedi** | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/2092897/000119312526346822/d137286d10q.htm) |
| **ADAC** | 10-Q, 14 Ağustos | Blank-check/SPAC dili; unit/warrant; **class/ticker eşlemesi açık** | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/2083002/000110465926097135/adac-20260630x10q.htm) |
| **ASPC** | 10-Q, 12 Ağustos | Blank-check/SPAC dili; farklı pay sınıfı ve warrant ipuçları; **class/ticker eşlemesi açık** | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1890361/000121390026088396/ea0299312-10q_aspac3.htm) |
| **ARR** | 10-Q, 22 Temmuz | REIT dili; **Common Stock + ARR + NYSE aynı tablo satırında** | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1428205/000142820526000090/arr-20260630.htm) |
| **RHP** | 10-Q, 7 Ağustos | REIT dili; **Common Stock + RHP + NYSE aynı satırda** | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1040829/000110465926092580/rhp-20260630x10q.htm) |
| **WPC** | 10-Q, 29 Temmuz | REIT dili; **Common Stock + WPC + NYSE aynı satırda** | [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1025378/000102537826000119/wpc-20260630.htm) |
| **CCD** | N-CSRS, 2 Temmuz | Closed-end fund dili; bu form 10-Q cover row doğrulaması değildir | [SEC N-CSRS](https://www.sec.gov/Archives/edgar/data/1602584/000110465926080383/tm2610083d8_ncsrs.htm) |
| **CGO** | N-CSRS, 2 Temmuz | Closed-end fund dili; listed security_id yok | [SEC N-CSRS](https://www.sec.gov/Archives/edgar/data/1285650/000110465926080370/tm2610083d3_ncsrs.htm) |
| **CSQ** | N-CSRS, 2 Temmuz | Closed-end fund dili; listed security_id yok | [SEC N-CSRS](https://www.sec.gov/Archives/edgar/data/1275214/000110465926080392/tm2610083d4_ncsrs.htm) |

**SEC kaynak pilotu: 9/9 \`filings.recent\` issuer kaydı ve
9/9 gerçek asıl SEC dosyası doğrulandı; kaynak hatası 0.**

6 adet 10-Q için A5e'nin aynı satırda ticker+
Common Stock + Nasdaq/NYSE adı kontrolü çalıştırıldı.
**ARR, RHP, WPC: 3/6 pozitif pay sınıfı adayı.**
AACI/ADAC/ASPC: bu *dar Common Stock terim eşlemesinde*
pozitif bulunmadı; **Class A ordinary shares** gibi
başka resmî pay sınıfı ifade biçimleri bu negatif
sonuçtan dışlanamaz. N-CSRS kullanan 3 fon ayrı
belge türü olarak saklandı, 10-Q gibi işlenmedi.

Bu 9 kayıt A5'teki orijinal
\`REVIEW_REQUIRED\` konumlarını **korur**.
Belge dili **issuer düzeyi ve/veya güvenlik sınıfı
kanıt adaylarıdır**; otomatik SPAC/BDC/REIT,
fon kapsam sınıflaması veya lisanslı
market-security master doğrulaması değildir.
Kapanış/statü değişikliği, security_id ve
\`known_at\` hâlâ ayrı kapıdır.

**SEC pilot rapor SHA256**
\`e34c0fe0a2260a4d1a323591364ac9b509c1fc39ea49d9c9c40a4bc36c3d63ef\`.

## C. Denetlenebilir koşu ve ham dosyalar

- [Başarılı bir defalık A5k GitHub Actions — **236 test** ve tam resmî kaynak yeniden hesaplaması](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38763550078)
- [13.287 satırlık tam-deny ledger, orijinal kaynak hash referansları](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38763550078/artifacts/11987066915)
- [9 SEC asıl belge + 9 SEC issuer submissions, SHA256 ve meta raporu](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38763550078/artifacts/11986213819)

Artifact ömrü 90 gündür; kalıcı, tarihlemenmiş,
imzalı kaynak arşivi yerine geçmez. Bu
SEC belgeleri 15 Ekim'de kontrol edilmiş
olup 14 Ekim snapshot tarihi ile
\`known_at=2026-10-14\` aynı kabul edilemez.

## D. A5 sınıflandırmasının açık karar kapıları

1. **1.010 REVIEW_REQUIRED** için tür ve security_id:
   268 finansal statü, 297 fon/REIT ayrımı, 307
   SPAC/BDC/finansal tür, 128 bilinmeyen tür ve
   **10 TXSE venue scope önerisi** açık. Dokuzlu
   pilot bu karar sayılarını değiştirmez.
2. **4.556 geçici INCLUDE** için tarihli security master,
   pay sınıfı ve uygun kapsam onayı hâlâ yok.
3. **BDC/REIT/SPAC/fon** ve ADR/depositary, Class A/B,
   unit, warrant, preferred/security türleri için
   açık trade universe policy onayı verilmedi.
4. **LIEN–REFI** birleşme oylaması, REFI N-54A,
   gerçek merger closing ve tarihli borsa
   corporate-action bağımsız kanıtı açık.
5. **Gerçek yayın yetkilendirmesi**, reviewer rolü,
   imzalı/bağımsız kaynak kararı, audit-log ve
   release'in her adayda zorunlu kontrolü için
   ayrı tasarım + açık kullanıcı onayı gerektirir.
   A5k \`DENY_ONLY\` test katmanı bunu yapmaz.

**Değiştirilmedi:** \`main\`, BIST V2.0.1 production,
US momentum/FIP hesaplama, Yahoo/fiyat, ATR veya 90
seans tradability, SQLite production schema,
canlı publication ve portföy pozisyonları.
