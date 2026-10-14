# A4 — Gerçek SEC × Nasdaq kaynak eşleştirme audit'i

Tarih: 14 Ekim 2026. Durum: **REVIEW_ONLY**, hiçbir menkul kıymet production onayı almadı. Sonuçlar GitHub Actions [38629237276](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38629237276) ile üretildi. Çevrimdışı 93 test geçti.

## Kaynak ve eşleşme

- Nasdaq + otherlisted toplam: **13.287 satır**; 4.556 adi hisse adayı, 7.721 kapsam dışı, 1.010 inceleme.
- SEC `company_tickers_exchange.json`: **10.451 şirket–ticker–borsa satırı**. Bunların **171** adedinde SEC borsa alanı `null`; **MIC atanmadı**, ilgili satırlar source error sayılmadan bilinmeyen olarak korundu.
- Eşleşme sadece tam SEC ticker + doğrulanmış MIC üzerinden yapıldı; CIK yalnız `issuer` adayıdır, `security_id` veya pay sınıfı kanıtı değildir.
- SEC eşleşmesi yokluğu delist veya EXCLUDE kararı değildir. SEC'te bulunmak da kapsam onayı değildir.

| Directory ilk sınıflandırması | Toplam | Tek SEC CIK adayı | Tam ticker+MIC eşleşmeyen | Çoklu CIK |
|---|---:|---:|---:|---:|
| INCLUDE — provisional | 4.556 | **4.303** | **253** | 0 |
| EXCLUDE — kapsam dışı | 7.721 | **1.406** | **6.315** | 0 |
| REVIEW_REQUIRED | 1.010 | **954** | **56** | 0 |
| **Toplam** | **13.287** | **6.663** | **6.624** | **0** |

Aday INCLUDE grubunda **%94,45** (4.303/4.556) SEC ticker+MIC eşleşmesi var. Bu, security/instrument-type doğrulama oranı değildir.

İnceleme kuyruğunun ayrıntılı eşleştirmesi:

| İlk inceleme nedeni | Toplam | SEC tek aday | Eşleşmeyen |
|---|---:|---:|---:|
| FINANCIAL_STATUS_REVIEW | 268 | 268 | 0 |
| FUND_NAME_REQUIRES_TYPE_EVIDENCE | 297 | 270 | 27 |
| SPAC_BDC_OR_FINANCIAL_REVIEW | 307 | 304 | 3 |
| TYPE_UNCONFIRMED | 128 | 112 | 16 |
| UNKNOWN_EXCHANGE_CODE | 10 | 0 | 10 |

**Toplam 309** adet INCLUDE veya REVIEW_REQUIRED kaydı tam ticker+MIC üzerinden eşleşmedi. MIC dağılımı: **XASE 261**, **XNYS 32**, **XNAS 6**, **bilinmeyen MIC 10**. Bu 309 kaydın **269** adedinin ticker'ı SEC'te başka/belirsiz venue ile yer alıyor; özellikle SEC `NYSE` ibaresini `XASE` diye kabul etmek yanlış borsa ataması riski taşır. Eşleşmeyenler otomatik elenmedi.

## Ayrı zamanlı kaynak snapshot'ları

**Önemli:** Güncel ve önceki A1 snapshot'larının toplam satır ve kategori sayıları **aynı olmasına rağmen kaynak byte'ları farklıdır**. `a1_byte_identical=false`. Yeni dosyalar 14 Ekim 2026 **15:41 New York** oluşturma zamanına sahipken A1 dosyaları **08:31 New York** zamanına aittir. Bu sonuç iki veri setinin aynı snapshot olduğunu iddia etmez.

| Kaynak | A1 08:31 SHA256 | A4 15:41 SHA256 |
|---|---|---|
| nasdaqlisted | `d795709ce99f50ad29e58231dab1b4116ce9d9a0657671d20b9ccd7a944b2c0e` | `2dc5b607a42c3eefe9cf6f7d6e681c30b8fb55bb51ae04d998cdf51af02d6694` |
| otherlisted | `e41a3966c23c1ba66dc69de9cc2dce60b50acba87993bfe5cd889b3d6b491f62` | `12deeb989a1b515304eda04318a0af1db127ff6340d1055329c62d9a5cbcde28` |

SEC SHA256: `c90bb2d57bb62fae8171abf37b7eb040917f9fb6b5238e6d5dc028baaec318e5`, alım zamanı `2026-10-14T20:06:29.762827+00:00`.

## Kaynak makbuzları ve tekrar üretilebilirlik

[GitHub Actions sonuç ve ham veri artifact'ı](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38629237276/artifacts/11926190129): A4 directory ham dosyaları, SEC ham JSON, SHA256 receipt'ler, 13.287 satırlık review, SEC-enriched review ve `final-audit.json`. Artifact saklama süresi **30 gün**; kalıcı bağımsız ham snapshot arşivi henüz kurulmadı. Git'e büyük ham dosyalar/DB eklenmedi.

## Açık inceleme işleri ve kapılar

1. 261 XASE uyuşmazlığı öncelikle exchange'in resmî type/listing kaynağı ile çözülecek; SEC `NYSE` otomatik `XASE` kabul edilmeyecek.
2. XNYS 32 / XNAS 6 / bilinmeyen 10 kayıt ayrı evidence/reason bazında incelenecek; sembol noktalama ve alias eşitlemesi otomatik yapılmayacak.
3. SEC CIK, security master için yalnız destekleyici issuer kanıtı olacak. Share class ve REIT/SPAC/BDC kararı ayrıca kaynaklı.
4. Geçmişi güvenilir `known_at/effective_at` kayıtları, SQLite sürümlü snapshot tabloları, fiyat/takvim/tradability ve production publication **yapılmadı**.
5. BIST V2.0.1 production, hesaplama çekirdeği, Yahoo/fiyat akışı ve canlı yayın değiştirilmedi.

A4 veri kaynağı incelemesi başarıyla sonuçlandı; resmi evrenin tamamı **onaylanmış değildir**.
