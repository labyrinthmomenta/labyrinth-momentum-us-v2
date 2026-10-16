# A5n — TradingView ABD hisse CSV × 14 Ekim 2026 resmî Nasdaq/SEC

**Durum: REVIEW ONLY — production ve security_id onayı 0.**

## Kaynak ve değişmez parmak izi

16 Ekim 2026 etiketli kullanıcı CSV dosyası: **US_Momentum_2026-10-16_88551.csv**, **14.174 satır, 31 sütun, 4.848.688 byte**, SHA256:

`df1a21bb55222b6fe480db22aa0ea22e50ad1995562597fef476a18fe2ba17fc`

Frozen 14 Ekim A4 directory-review/review.json, **13.287 satır**, SHA256:

`5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d`

CSV'deki iki ayrı **Sector** başlığı korunur. TradingView ham CSV'si **public GitHub reposuna veya Actions artifact'ına konulmadı**. Gerçek kaynak karşılaştırması kullanıcı dosyası ile yerel ortamda gerçekleştirildi; CI sentetik örneklerle algoritmayı sınar.

## Eşleştirme özeti

| Veri | Kayıt |
|---|---:|
| TradingView CSV toplam | 14.174 |
| OTC | 7.485 |
| NASDAQ | 3.738 |
| NYSE | 2.643 |
| NYSE Arca | 307 |
| CBOE | 1 |
| Karşılaştırılabilir TradingView NASDAQ+NYSE | **6.381** |
| Resmî A4 üç MIC (XNAS/XNYS/XASE) | **8.850** |
| Ticker + MIC birebir eşleşme | **6.034** |
| NYSE /P<seri> → Nasdaq $<seri> **format adayı** | **340** |
| TradingView için hâlâ eşleşmeyen | **7** |
| Resmî A4-only (üç MIC) | **2.476** |
| Bunlardan XASE coverage gap | **314** |

Resmî venue dağılımı: **XNAS 5.629, XNYS 2.907, XASE 314**. A4-only 2.476 kaydın **2.162'si XNAS/XNYS**, 314'ü **XASE**. TradingView NYSE ile NYSE American/XASE **otomatik eşlenmez**, NYSE Arca da XASE kabul edilmez.

## NYSE tercihli sembol formatı

TradingView örneği `JPM/PM`, Nasdaq otherlisted karşılığı `JPM$M` — bu, **nihai security_id kanıtı değil yalnız format adayıdır**. 340 adayın **331'i A4 EXCLUDE**, **9'u A4 REVIEW_REQUIRED**. `T/PC` asla `TPC` gibi slash silinerek eşlenmez.

## TradingView-only kalan yedi sembol

**NASDAQ:** BMMX, AMRO, IAM. **NYSE seri belirsiz preferred:** DCOM/P, TFIN/P, ETI/P, TY/P. Eksiklik veya yeni listing kararı verilmedi; iki snapshot arasında iki gün var. Seri harfi olmayan /P kodları kendiliğinden dönüştürülmez.

## Kritik 21 tür uyarısı

Geçici A4 INCLUDE içinde TradingView CFI farklı sınıfa işaret eden **21 kayıt**: **20 CI (kolektif yatırım aracı işareti)** — BSTZ, GAB, GAM, TYG, BCX, BOE, GUT, ETO, VKQ, GGT, ETX, MPV, GRX, JHS, GGZ, JHI, ECAT, MCI, BTX, BMEZ — ve **1 EP (preferred equity işareti)** TVC.

Bu **fon veya tercihli pay olduğunun kesin hukuki kanıtı değildir** ve kaynak A4 INCLUDE kararları değiştirilmemiştir. Önce SEC N-2/N-CSRS, borsada listelenen pay sınıfı ve yetkili security-master kontrolü gerekir.

## Bilinçli olarak açık kalan kontroller

- CCD/CGO/CSQ ve 20 CI-adayının SEC N-2 / N-CSRS, kalıcı menkul kıymet sınıfı / resmî borsa kanıtlarının ayrı incelemesi;
- XASE (314 resmî satır) için TradingView filter/exchange kapsamı;
- 14 Ekim resmî as-of ile 16 Ekim CSV tarihlerinin ayrımı; `known_at` geçmişe taşınmaz;
- CUSIP/ISIN/FIGI değerleri resmî kalıcı security_id onayı sayılamaz;
- TV `Average volume, 90 days` != 90 completed daily sessions mean(close×volume).

**A4 özgün statüleri değişmedi: 4.556 provisional INCLUDE, 1.010 REVIEW_REQUIRED, 7.721 EXCLUDE. A5k 5.566 DENY-only kararı korunuyor; production yayın bağlantısı ve onay sıfır.**

**Üretim sınırı:** main, BIST V2.0.1 production, US momentum/FIP, Yahoo/fiyat, tradability, SQLite ve canlı publication değiştirilmedi.
