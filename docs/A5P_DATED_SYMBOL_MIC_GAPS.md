# A5p — Dated ticker/MIC farklılıkları, 14 Ekim A4 vs 16 Ekim TradingView

**Başarılı denetim:** [A5p GitHub Actions — 277 test](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38894892527). Tam resmî A4 SHA256 `5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d`. TradingView CSV SHA256 `df1a21bb55222b6fe480db22aa0ea22e50ad1995562597fef476a18fe2ba17fc` (private CSV repo'da yok).

**7 TradingView-only**: XNAS BMMX, AMRO, IAM; NYSE DCOM/P, TFIN/P, ETI/P, TY/P (tercihli sembol seri harfi belirsiz). A4 14 Ekim snapshot'ında eşleşmez; TradingView export 16 Ekim etiketlidir. 7/7 `OFFICIAL_14OCT_ABSENT_REVIEW_ONLY`, **7 delisted veya 7 yeni resmi listing** sonucu çıkarılamaz.

**6 A4-only, geçici INCLUDE**: XNAS EFTY, HCHL, MCTA, OST, SVA ve XNYS TAP.A. Eski kaynak `INCLUDE` değeri hâlâ **provisional**, üretim onayı değildir. TradingView kapsamı, sembol yazımı ve tarih ayrımı araştırılmadan hiçbir otomatik çıkartma yok.

**314 XASE kapsama boşluğu**: 225 original INCLUDE, 53 EXCLUDE, 36 REVIEW_REQUIRED. TradingView CSV'de NYSE American ayrı borsa olarak doğrulanmıyor. NYSE Arca ≠ NYSE American. Bu 314 kaydı "TradingView yanlış/eksik" diye nihai etiketlemiyoruz.

[Ham A5p kaynaklı JSON artefaktı](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38894892527) — gerçekte CSV değil, A4 SEC/Nasdaq SHA doğrulaması ve daha önce A5n'de kanıtlanmış özel CSV türevli fark listesi kullanıldı.

**Kapanış:** 0 otomatik INCLUDE/EXCLUDE, 0 security_id, 0 production onayı. 1.010 REVIEW_REQUIRED ve 4.556 provisional INCLUDE sabit. A5r approval/release kapısı production'a bağlı değildir. main, BIST üretim, US momentum/FIP, Yahoo/fiyat/tradability, DB ve yayın değiştirilmedi.
