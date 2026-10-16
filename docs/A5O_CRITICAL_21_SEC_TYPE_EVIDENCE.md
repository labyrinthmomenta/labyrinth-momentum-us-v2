# A5o — 21 kritik TradingView CFI uyuşmazlığı, resmî SEC issuer kanıtı

**Sonuç (16 Ekim 2026 retrieval, 14 Ekim as-of):** 21/21 exact A4 XNYS provisional INCLUDE ↔ SEC CIK şirket kaydı hash-sabit kaynaklardan eşleştirildi. Resmî SEC `data.sec.gov/submissions/CIK*.json` özgün dosyaları 21/21 indirildi, SHA256 ve retrieval zamanı kaydedildi. **20/20 TradingView CFI "CI" fon sınıfı şüphesinde**, yakın SEC filing geçmişinde N-CSR/N-CSRS/N-CEN/N-2 sınıfından **en az bir SEC form kaydı** bulunuyor. TVC ise CFI "EP" ve SEC issuer `Tennessee Valley Authority`, **fon formu saptanmadı**. TVC'nin listed security class/debt/preferred ayrımı kesinleşmedi.

[SEC Actions kaynak doğrulaması — 273 test](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38894442577), [21 resmî SEC issuer başvuru ham arşivi](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38894442577/artifacts/12043735670).

Kaynak zinciri: frozen A4 review SHA256 `5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d`; frozen SEC company ticker/exchange SHA256 `c90bb2d57bb62fae8171abf37b7eb040917f9fb6b5238e6d5dc028baaec318e5`; özel kullanıcı TradingView CSV orijinal SHA256 `df1a21bb55222b6fe480db22aa0ea22e50ad1995562597fef476a18fe2ba17fc` repo'ya yüklenmedi.

SEC'de yatırım fonu formları bulunan 20 sembol: **BSTZ GAB GAM TYG BCX BOE GUT ETO VKQ GGT ETX MPV GRX JHS GGZ JHI ECAT MCI BTX BMEZ**. Tarihsel SEC parçalı arşivlerinin ikisi (GAM ve MCI) indirilmedi; **bir N-2'nin yakın kayıtlarda görünmemesi tarihi yokluğu ispatlamaz**. SEC CIK şirket düzeyindeki kimliktir, kesin listed security ID değildir.

**Hiçbir A4 kaydı otomatik EXCLUDE edilmedi.** Tüm 21 provisional INCLUDE orijinal durumunu korur ama ayrıca `release_hold_proposed=true` ile risk incelemesi bekler. `classification_decisions_closed=0`, `production_approvals=0`. SEC formu görülmesi tek başına alt tür/şirketin fon olup olmadığı ve nihai kapsam politikasını onaylamaz.

A5p–A5r kapıları: yedi ayrışan sembol, XASE 314 kapsam boşluğu, kalan 1.010 REVIEW ve 4.556 provisional INCLUDE için bağımsız security ID ve reviewer onayı, tarihli `known_at` ve resmi yazılı kapsam politikası.

`main`, BIST V2.0.1, ABD momentum/FIP, Yahoo fiyat, 90 completed sessions dollar-liquidity, DB production ve yayın katmanları değiştirilmedi. GitHub branch/PR sadece review-only kanıt toplar.
