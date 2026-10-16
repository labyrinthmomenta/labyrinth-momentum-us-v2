# A5r — Production'a geçiş hazırlığı: bütünlük ve yetki eksikliğinde kesin DENY

**Kaynak ve sürüm:** A5q `a5q-evidence-decision-queue.json` SHA256 `31fafa47387d20b76b36c5fc9c812c2e3ffc369e8b5b17845539d57b07f0104c`.
A5r sürümü `a5r-independent-readiness-deny-v1`.
[Başarılı tek seferlik A5r Actions denetimi — 290 test](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38895762633) ve [A5r kanıt belgesi/5.566 DENY kaydı](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38895762633/artifacts/12044160844).

## Denetim sonucu

| Ölçüm | Sonuç |
|---|---:|
| Tüm resmî kaynak listed adayları | **13.287** |
| A4 provisional INCLUDE, henüz yetkili onaysız | **4.556** |
| A4 REVIEW_REQUIRED, hâlâ açık | **1.010** |
| Orijinal EXCLUDE, değiştirilmedi | **7.721** |
| Aday kontrolü (4.556+1.010) | **5.566** |
| **ALLOW / Production onayı** | **0** |
| **DENY** | **5.566** |
| A5o öncelikli SEC type-issuer/TV uyuşmazlığı | **21** |
| LIEN/REFI kurumsal olay açık blokajı | **2** |

Kaynak `production_eligible=true`, listelenmiş pay sınıfı ya da bağımsız security-ID `approved=true`, onaylanmış `known_at` veya reviewer rolü `approved=true` iddiasıyla geldiğinde **fail-closed hata** döndürür. Haricen verilen bir `authorization` token'ı veya `signed=true` metni ALLOW izni sağlamaz; sürümde gerçek imza doğrulayıcısı bulunmadığı için her durumda DENY.

## Bağımsız release için zorunlu sekiz açık koşul

1. **Kapsam politikasının yetkili sahiplerce kabulü ve bağımsız doğrulanabilir imza**: fon, closed-end, SPAC, BDC, REIT, ADR, preferred, unit/warrant/right, MIC kuralları.
2. **Listed-security kimliği sağlayan otoritatif borsa/security-master kaynağı**: SEC CIK tek başına security_id değildir.
3. **Pay sınıfı ve kalıcı security-ID eşleşmesinin açık, tarihli onayı**: ticker değişimi, split, merger, köken, CUSIP/ISIN/FIGI kimlik düzeyi.
4. **Kimliği doğrulanmış reviewer + iki bağımsız onay**: review owner ve production publisher görev ayrımı.
5. **as_of, source retrieved_at, effective_at ve known_at ayrı doğrulanması**: 16 Ekim TradingView snapshot'ı 14 Ekim SEC/Nasdaq tarihsel gerçeği gibi kullanılmaz.
6. **SEC yatırım aracı statüsü ve şirket olaylarının çözülmesi**: 21 CFI/issuer risk kaydı, A5x 1.010 review, LIEN/REFI oy/kapanış ve REFI BDC election; tarihsel SEC arşiv boşlukları dahil.
7. **Likidite/işlem yapılabilirlik koşulunun gerçek 90 tamamlanmış seansta test edilmesi**: son tamamen tamamlanmış günün kapanışı >$5 ve önceki 90 tamamlanmış seansın günlük close × volume ortalaması >$1 milyon; eksik/muğlak veri fail-closed.
8. **Canlı yayın/production sistemine entegre gerçek gate**: şu andaki A5r kodu production'a **bağlı değil**; DENY-only izole proof-of-control. Entegrasyon için ayrıca açık kullanıcı onayı ve uçtan uca test gerekir.

`main` sabit, tüm PR zinciri Draft. BIST V2.0.1 production, US momentum/FIP hesapları, Yahoo/prices, ATR, SQLite prod şeması, canlı yayın ve hiçbir strateji pozisyonu değiştirilmedi.

**Durum kararı: `RELEASE_READINESS_DENIED`.** Bu, teknik inceleme/güvenlik altyapısının tamamlanan adımlarını gösterir; gerçek ABD evreninin nihai hukuki/işlem türü sınıflandırması, tarihli kimlik ve onaylarının tamamlandığı iddia edilmez. 1.010 tür incelemesi ve 4.556 geçici INCLUDE hala nihai onay bekliyor.
