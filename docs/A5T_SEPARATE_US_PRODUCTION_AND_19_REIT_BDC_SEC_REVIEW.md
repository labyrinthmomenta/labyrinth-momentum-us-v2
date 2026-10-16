# A5t — US V2 bağımsız production hazırlığı ve 19 resmî REIT/BDC SEC kanıt kaydı

**Hisse evreninin dondurulmuş tarihi:** 2026-10-14. **Resmî SEC asıl belgeleri ilk alım:** 2026-10-15. **Denetim:** 2026-10-16. **Durum:** yalnız SEC kaynak/kimlik incelemesi; asla yayın izni değil.

## 1. US V2 production kesinlikle bağımsız olacak

`labyrinthmomenta/labyrinth-momentum-us-v2` ayrı repository ve bağımsız US deployment/secret/environment, US data storage, US release manifest, US scheduler, US alert/monitoring gerektirir. **BIST repository'siyle aynı production katmanını paylaşması planlanmıyor.** Ancak bu gereksinimler tamamlanmış değildir: mevcut `main` tarihsel başı sabit, GitHub Draft PR zinciri merged değil, gerçek US production publisher/DB schema/secrets/deployment henüz kurulmadı.

Bağımsız US release aşaması yalnız yetkili kapsam politikası, tarihli listelenmiş security-class ve security_id, resmî şirket statüsü, point-in-time veri, iki kişi onay yetkisi, bağımsız 90 tamamlanmış seans fiyat×hacim kapısı ve uçtan uca testten sonra açılabilir. Bu dosya yalnız offline doğrulama; US production deployment oluşturmaz.

## 2. User-approved scope: REIT / BDC ordinary shares allowed candidates, CEF excluded

- CEF'ler kapsam dışı, BDC'ler (kapalı uçlu yatırım şirketi niteliği taşısalar bile) **doğrulanmış BDC seçimi + bağımsız doğrulanmış ordinary/common listed share** şartıyla kapsam adayı.
- REIT common/ordinary share sınıfı + issuer REIT statüsü yine bağımsız kanıt gerektirir.
- ETF, ETN, unit, warrant, right, preferred ve bond enstrümanları kapsam dışı; SPAC/ADR farklı politika incelemesi.
- N-54A varlığı, güncel BDC statüsünün devamını tek başına ispatlamaz. N-54C bulunmaması **absence proof değildir**; 8-K içerikleri ve kurumsal olaylar ayrıca incelenmeli.

## 3. SHA-locked 19 SEC primary documents (16 BDC + 3 REIT)

| Resmî arşiv | SHA256 |
|---|---|
| A5e 16 SEC financial filing source receipt (`a5e-financial-evidence.json`) | `a58638402bbdc59b7afb2de3dfe439c6672cc0a1ede40fb59bd8a283aea7612f` |
| A5k 9 issuer SEC pilot receipt (`a5k-sec-pilot-evidence.json`) | `e34c0fe0a2260a4d1a323591364ac9b509c1fc39ea49d9c9c40a4bc36c3d63ef` |

**16 SEC BDC issuer adayları:** GAIN, SAR, PNNT, HRZN, NMFC, PFLT, CION, SCM, GSBD, ICMB, TPVG, CCAP, OBDC, KBDC, PSBD, LIEN. A5e metadata orijinal 17 N-54A/A bildirimine bağlıdır; her issuer'ın as-of 14 Ekim son SEC 10-Q/10-K kapak tablosunda aynı ticker + Common Stock + Nasdaq/NYSE borsası satırı doğrulandı. Her 16 ham SEC primary SHA256 ve byte sayısı özgün A5e kanıt raporuyla yeniden doğrulandı.

**3 SEC REIT issuer adayları:** ARR, RHP, WPC. Original A5k 10-Q'da `Common Stock + exact ticker + New York Stock Exchange` satırı ve REIT ifade ipucu bulunuyor; her üçünün SEC asıl dosyası SHA256 ile yeniden doğrulandı.

[Başarılı A5t SEC kaynağını yeniden doğrulama — 328 test](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38952245203), [19 satırlık tarihli US evidence queue JSON](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38952245203/artifacts/12068388893), [16 BDC A5e orijinal SEC belgeleri](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38728679096/artifacts/11969461622), [3 REIT dahil A5k 9 SEC orijinal dosyası](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38763550078/artifacts/11986213819).

**Kaynak güvenliği ve kesin sınır:** 19 asıl SEC dosyasının SHA ve byte ölçüleri korunur; SEC issuer CIK **kalıcı listed security ID değildir**. N-54A + şirketin son finansal raporu ve NYSE/Nasdaq cover row **nihai hukuki/statü/onay** sağlamaz. BDC kayıtlarının tamamında post-financial 8-K içerik incelemesi ve current election proof açık. LIEN, REFI birleşme kapanışı ve REFI N-54A kanıtı olmadığı için ek hold. REIT'lerde tax/legal status bağımsız doğrulama henüz yapılmadı. 2026-10-15 retrieval `known_at=2026-10-14` ispatı değildir.

## 4. Ölçülebilir ilerleme

| A5t kontrol çıktısı | Sayı |
|---|---:|
| SEC orijinal kapak satırı ile desteklenen BDC pay sınıfı kanıt adayı | 16 |
| SEC orijinal kapak satırı ile desteklenen REIT pay sınıfı kanıt adayı | 3 |
| Toplam issuer/class kanıt adayı | 19 |
| Resmî güncel issuer statüsü kesin onaylanan | **0** |
| Bağımsız menkul kıymet security_id kesin onaylanan | **0** |
| Bağımsız reviewer tarafından kararı nihai kapanan | **0** |
| Gerçek US production deployment/publisher | **Henüz kurulmadı** |

Başlangıçtaki 13.287 dondurulmuş A4 karar dağılımı **4.556 provisional INCLUDE / 1.010 REVIEW_REQUIRED / 7.721 EXCLUDE** olarak kaldı. A5r'nin **5.566 DENY-only** kontrolü yürürlükte *offline* prototip olarak kalır. US üretim planı BIST'ten ayrı fakat bu PR onu kurmuyor; hiçbir PR main'e merge edilmedi.

**Sonraki somut iş:** 16 BDC'nin post-10-Q toplam 40 adet 8-K içeriği için kontrollü SEC event evidence, N-54C tarihsel dosya ve election current-status incelemesi; ardından REIT issuer'ın bağımsız hukuki statüsü ve otoritatif exchange-listed class/security-ID zaman çizelgesi. Bağımsız user-approved policy/reviewer kontrolü sonrasında US production gate için ayrı açık yetkilendirme gerekli.
