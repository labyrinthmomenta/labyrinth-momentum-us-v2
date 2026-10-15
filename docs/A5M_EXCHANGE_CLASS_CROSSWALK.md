# A5m — Resmî Nasdaq directory × SEC pay sınıfı karşılaştırması

**Denetim:** 15 Ekim 2026. **Directory snapshot:** 14 Ekim 2026.
**Sürüm:** \`a5m-exchange-class-crosswalk-review-v1\`.
**Karar:** \`OFFICIAL_EXCHANGE_CLASS_CROSSWALK_REVIEW_ONLY\`.

Amaç: A5l'nin resmî SEC 12(b) 9 issuer/pay sınıfı kanıtını,
**ayrı kaynaktan gelen Nasdaq Trader security-directory**
ile tam ticker + MIC + tarihli ham snapshot eşleştirerek doğrulamak.
Böylece SPAC sıradan/ordinary payları ile unit/warrant/right
sembollerinin karıştırılmadığını göstermek. İlgili CIK, hisse
sembolü veya Nasdaq adı **kalıcı \`security_id\` değildir**.

## 1. Birbirinden bağımsız kaynaklar ve SHA zinciri

| Dondurulmuş kaynak | SHA256 |
|---|---|
| A4 13.287 satırlık \`directory-review/review.json\` | \`5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d\` |
| Nasdaq \`nasdaqlisted.txt\` | \`2dc5b607a42c3eefe9cf6f7d6e681c30b8fb55bb51ae04d998cdf51af02d6694\` |
| Nasdaq \`otherlisted.txt\` | \`12deeb989a1b515304eda04318a0af1db127ff6340d1055329c62d9a5cbcde28\` |
| A5l 9 issuer SEC Listed Class Evidence | \`cf342e3f17ba5d600f3bcfd0ed958976ef97272fe8b2749582a2a21093475992\` |
| **A5m tam crosswalk kanıtı** | \`0de1300e09282cd75bca99584a6450b77c5f4e89ddc0980a43514c17641d8000\` |

Resmî **Nasdaq Trader SymDir** kaynakları 14 Ekim 2026'da
\`2026-10-14T20:06:28Z\` civarında indirildi ve dosya
oluşturma tarihi \`2026-10-14T15:41:00-04:00\` olarak
saklandı. Tam ham hash'ler önce doğrulandı.
A4 13.287 satırın tamamındaki \`source, symbol, MIC,
Security Name\` ve orijinal alanlar, resmî \`nasdaqlisted\`
ya da \`otherlisted\` metinlerinin gerçek satırlarıyla
birebir karşılaştırıldı. Artık bu bağımsız
bütünlük doğrulamasından sonra seçilmiş 15 sembole inildi.

Resmî kaynak tanımları:
[Nasdaq Trader — Symbol Directory Definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs).
\`nasdaqlisted\` kaynağı Nasdaq-listed, \`otherlisted\`
kaynağı ise **Nasdaq tarafından tutulan diğer borsaların**
listeleme sembolleri dosyasıdır. \`otherlisted Exchange=N\`,
New York Stock Exchange (XNYS) anlamına gelir; **NYSE'nin
bağımsız issued security master'ı değildir**.

[Başarılı A5m source-replay — 256 regression testi](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38800564010).
[15 ticker için A5m hash ve kanıt JSON arşivi](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38800564010/artifacts/12004525532).
GitHub Actions artifact'ları **90 gün** tutulur.

## 2. SPAC listed ordinary shares, unit/warrant/right ayrımı

Kaynak as-of: 14 Ekim Nasdaq \`nasdaqlisted.txt\`.
Her üç ana ticker için A5l SEC 10-Q aynı satırda
\`ticker + Class A ordinary shares + Nasdaq\`
bulgusuyla borsa adındaki pay türü adayını
çapraz doğruladı.

| SPAC issuer aday grubu | Ana listed ordinary share | Resmî directory'de ayrı unit | Warrant/right | A4 kararları |
|---|---|---|---|---|
| Armada Acquisition Corp. III | **AACI** | \`AACIU\` — Units | \`AACIW\` — Warrant | AACI REVIEW; U/W EXCLUDE |
| American Drive Acquisition Company | **ADAC** | \`ADACU\` — Units | \`ADACW\` — Warrant | ADAC REVIEW; U/W EXCLUDE |
| A SPAC III Acquisition Corp. | **ASPC** | \`ASPCU\` — Unit | \`ASPCR\` — Right | ASPC REVIEW; U/R EXCLUDE |

**6 ayrı unit/warrant/right sembolü** resmî directory'de
bulundu. Bunların tamamı A4'te
\`EXCLUDE / NON_COMMON_INSTRUMENT_NAME\`, ana ordinary
hisseler **REVIEW_REQUIRED** olarak kaldı; bu kararların
hiçbiri yeniden yazılmadı.

AACI SEC pay başlığındaki \`included as part of the units\`
notu korundu. Bu açıklama AACI'yi \`AACIU\` sembolüyle
otomatik **aynı işlem sözleşmesi veya aynı kalıcı
security_id** saymak için yeterli değildir.
Borsa listesinde farklı ticker ve isim bulunması
ise iki sembolün kalıcı kimlikleri arasındaki
ilişkinin tamamının çözüldüğünü kanıtlamaz.

### Nasdaq finansal statü kodu — ayrı risk kapısı

14 Ekim tarihli resmî \`nasdaqlisted\` dosyası:

| Sembol | Financial Status | Kaynak yorum |
|---|---|---|
| AACI, AACIU, AACIW | \`N\` | Normal / snapshot düzeyi |
| ADAC, ADACU, ADACW | \`N\` | Normal / snapshot düzeyi |
| **ASPC, ASPCU, ASPCR** | **\`D\`** | **Deficient — devam eden kotasyon gereksinimlerinde eksiklik** |

Nasdaq'ın [resmî finansal statü tanımı](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs)
\`D\` kodunu *Deficient: Issuer Failed to Meet Nasdaq
Continued Listing Requirements* olarak açıklar.
Bu **fiilî delisting, ticker silinmesi, otomatik EXCLUDE
veya SEC issuer BDC statüsü değişikliği kararı değildir**.
As-of snapshot'taki durumun açıklamasıdır; ayrı
\`NASDAQ_DEFICIENT_LISTING_STANDARD_REVIEW\`
inceleme uyarısı oluşturuldu.

## 3. REIT ve closed-end fund — ayrı kaynak gücü

| Grup | Borsa directory kaydı | SEC kanıtı | Sonuç |
|---|---|---|---|
| ARR, RHP, WPC | \`otherlisted\`, \`Exchange=N\` (XNYS) | Her bir 10-Q'da ticker + Common Stock + NYSE aynı satırda | **3 listed common class adayı**, REIT hukuki statüsü ve security_id hâlâ onaysız |
| CCD, CGO, CSQ | \`nasdaqlisted\` adında **Closed End Fund** | Üç resmî N-CSRS issuer filing | **3 fon statüsü/tür incelemesi**, N-CSRS listed share identity sağlamaz |

**İnceleme sınırı:** ARR/RHP/WPC için ikincil borsa
sembol alanını veren Nasdaq-operated \`otherlisted\`
ile şirketin SEC 10-Q'su birbirinden ayrı kanıtlar.
Ama bunlar birlikte bile NYSE **bağımsız security master
identifier** sağlamaz. Kullanıcının XNYS / XNAS / XASE
kapsam politikasında kesin listed-class kararına
otomatik yükseltme yapılmamalıdır.

CCD/CGO/CSQ için Nasdaq adındaki \`Closed End Fund\`
ifadesi, SEC'nin N-CSRS issuer raporu ile birlikte
**fon sınıflandırması yönünde güçlü inceleme adayıdır**;
yine de bu iki kaynak tek başına fonun borsada listelenen
pay sınıfı, instrument ID, closed-end tax/legal subtype,
ETP kapsam kararı veya işlem yapılabilirlik onayı değildir.

## 4. Tam kapsam tutarlılığı

| Sınıflandırma | A4 kaynak sayısı | A5m sonucu |
|---|---:|---|
| Provisional \`INCLUDE\` | 4.556 | Karar değişmedi; production onayı 0 |
| \`REVIEW_REQUIRED\` | 1.010 | Karar değişmedi; 9 pilot bu grupta kaldı |
| \`EXCLUDE\` | 7.721 | Karar değişmedi; 6 unit/warrant/right dışarıda |
| **Toplam** | **13.287** | **Hiçbir production yükseltmesi yapılmadı** |

A5k'deki **5.566/5.566 DENY** yayın kontrolü
ve ayrı REFI kurumsal olay hold'u değiştirilmedi.
A5m kaynak eşleştirmesi **production'a bağlanmış
gerçek approval/release gate** değildir.

### Açık kanıt kapıları

1. XNAS/XNYS için borsa tarafından yetkilendirilmiş
   **kalıcı listed-security identifier/class master**
   (gerekirse CUSIP/ISIN ve kullanım/lisans koşulları)
   ve ticker zaman geçmişi, özellikle AACI share
   vs unit dönüşümleri ayrı doğrulanmalı.
2. Nasdaq \`D\` statüsünün hangi olaya dayandığı,
   bu durumun geçerlilik/effective date'i,
   sonraki giderilme veya suspension bilgisi
   resmî notices ile ayrıca gözden geçirilmeli.
3. Closed-end fund kapsam kararı, NYSE common
   class kaydı, SPAC ordinary shares'in politika
   kapsamı ve unit/right/warrant dışlama kuralları
   yetkili insan onayıyla açıkça netleştirilmeli.
4. Kaynak \`known_at\` ile \`listing as_of\`,
   15 Ekim retrieval edilmiş SEC belgesi ile
   14 Ekim dizini ayrı tutulmalı.
5. Review/production gate'in gerçek imzalı
   onay yetkisi ve bağımsız data master
   ile entegrasyonu hâlâ yapılmadı.

**Korunan alanlar:** \`main\`, BIST V2.0.1 production,
US momentum/FIP hesaplamaları, Yahoo/price/ATR,
90-session tradability, SQLite production schema,
portfolio decisions ve live publication değiştirilmedi.
A5m yalnız Draft geliştirme dalındadır.
