# A5 — Resmî borsa kanıtı, issuer uyuşmazlıkları ve enstrüman inceleme kapıları

**Durum: REVIEW_ONLY / fail-closed.** 14 Ekim 2026 A4 ham verisinin
SHA256 değerleriyle yeniden üretilmiş inceleme. A5 kaynağı yeni bir piyasa
snapshot'ı değildir; A4 ham receipt ve resmî dosyalarından türetilmiştir.

## Kaynak kanıtı

- [Nasdaq Trader symbol directory definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs):
  `otherlisted.txt` Exchange=A, NYSE American; Exchange=N, NYSE.
- [Nasdaq 2026 Texas Stock Exchange teknik duyurusu](https://www.nasdaqtrader.com/TraderNews.aspx?id=DTN2026-10):
  Texas Stock Exchange participant code `F`.
- [Texas Stock Exchange resmî kodları](https://www.txse.com/regulations/id-codes):
  `SIP participant ID=F`, MIC=`TXSE`.
- [SEC company_tickers_exchange.json](https://www.sec.gov/file/company-tickers-exchange):
  SEC issuer/CIK kanıt adayıdır; exchange etiketini otomatik MIC kabul etmeyiz.
- [NYSE Group Security Master](https://www.nyse.com/market-data/reference):
  menkul kıymet türü/pay sınıfı için ayrıca edinilmesi ve doğrulanması gereken
  veri kaynağı. **Bu data feed'i alınmadı**; tüm enstrüman türleri doğrulanmış değildir.

## A4 snapshot'ına bağlı yeniden üretilebilirlik

Resmî Nasdaq hash'leri: nasdaqlisted
`2dc5b607a42c3eefe9cf6f7d6e681c30b8fb55bb51ae04d998cdf51af02d6694`,
otherlisted `12deeb989a1b515304eda04318a0af1db127ff6340d1055329c62d9a5cbcde28`.
SEC hash'i `c90bb2d57bb62fae8171abf37b7eb040917f9fb6b5238e6d5dc028baaec318e5`.

`src.data.universe.a5_review` önce indirilen A4 artifact'ı içinde yalnız bu
hash'lere, ilgili resmî kaynak URL'lerine, receipt zamanlarına, 13.287 Nasdaq
satırına, 10.451 SEC satırına ve 4.556/7.721/1.010 sınıfına izin verir.
Kaynak veya kayıt sırası / kararları değişirse işlem DURUR.

## A5 borsa eşleştirme bulguları — 309 vaka

| Vaka | Kayıt | Kanıtla açıklanan durum | Kimlik kararı |
|---|---:|---|---|
| XASE | 261 | Nasdaq `Exchange=A`; SEC ticker aynı fakat label `NYSE` | Listeleme borsası XASE doğrulandı; SEC CIK henüz onaylanmadı |
| XNYS | 31 | SEC'de nokta/dolar işaretli sembole benzeyen tire biçimi | Yalnız alias *adayı*, birleştirme yok |
| XNYS | 1 | ASBH için doğrudan SEC/variant eşleşmesi yok | Ek issuer/security kanıtı gerekli |
| XNAS | 6 | Borsa Nasdaq; SEC ticker'da yok | CIK yokluğu delist değil, inceleme |
| TXSE | 10 | Nasdaq `Exchange=F`, resmî TXSE participant code F | Scope dışı **önerisi**; A4 kararı değişmedi |
| **Toplam** | **309** | | **Production onayı 0** |

NYSE American'daki 261 kayıt için SEC `NYSE` etiketinin kapsamı veya
CIK eşleşmesi mic-level kesinliği göstermez. Venue kanıtı NASDAQ directory
kodudur; SEC kaydı bağımsız issuer **adayı** olarak raporlanır.

31 sembol biçimi farkından örnekler `BRK.B` → `BRK-B`,
`BAC$L` → `BAC-PL`, `BF.A` → `BF-A`. Bunlar alias eşdeğerliği
kanıtı değildir; yalnız manuel inceleme için önerilen eşleşmelerdir.
TXSE `F` kayıtlarından sekiz ticker SEC'de `TXSE` label'ıyla vardır;
iki kayıt tam SEC ticker eşleşmesi bulmamıştır. Mevcut kapsam yalnız
`XNAS`, `XNYS`, `XASE` olduğu için 10 TXSE kaydı
`OUT_OF_SCOPE_TXSE` önerisine ayrılmıştır. Bu yeni bir kapsam açılımı değildir.

## 1.010 enstrüman türü incelemesinin sonucu

| İlk neden | Adet | A5 kapısı |
|---|---:|---|
| Nasdaq financial status | 268 | Status'un resmî son durumu + tür/sınıf |
| Fon/REIT isim belirsizliği | 297 | Resmî REIT vs fon security type |
| SPAC/BDC/finansal tür | 307 | Açık politika + security type |
| Tanımı belirsiz tür | 128 | Resmî menkul kıymet türü + share class |
| Bilinmeyen `F` borsa kodu | 10 | TXSE olarak tanımlandı; mevcut scope dışında |
| **Toplam** | **1.010** | **1.000 tür kararı hâlâ kanıt bekliyor** |

**Önemli:** 1.000 açık tür vakası otomatik INCLUDE yapılmadı.
10 TXSE scope dışı önerisi A4 `REVIEW_REQUIRED` kaydını geriye dönük
değiştirmez. Ortada SEC, Nasdaq ve TXSE kaynaklarıyla doğrulanan venue
bulguları ile menkul kıymet türünün doğrulanması için eksik kalan
security-master/filing kanıtları ayrı tutuluyor.

## Üretilen denetim çıktıları

Başarılı [A5 GitHub Actions koşusu](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38632921444)
104 Python regresyon testini geçmiş, kaynak hash/karar sayılarını doğrulamıştır.
Raporlar `summary.json`, `venue-exceptions.json` (309 satır),
`instrument-review.json` (1.010 satır) olarak çıktı verir; her inceleme
satırında listing source hash'i, SEC hash'i, resmî ham listing alanları
ve onaylanmamış SEC CIK adayı bulunur.

Son tam satır alanlı koşu sonrası artifact linki PR'de güncellenecek;
GitHub Actions artifact'ı kalıcı bağımsız arşiv değildir.

## Kapanış için hâlâ eksik resmî deliller

1. NYSE American/NYSE Group Security Master (veya eşdeğer yetkili
   enstrüman master) ile security type, pay sınıfı ve uygun alias kanıtı.
2. SPAC common ve BDC kapsam politikasının açık sürümlü onayı.
3. Nasdaq financial-status vakalarının resmî güncel durum değerlendirmesi.
4. Sürümlü `known_at`/`effective_at` ve kaynaklı manuel karar kayıtları.
5. A5'in ön kararlarını ancak tüm gerekli kaynaklar geldiğinde production
   evrenine bağlayacak ayrı release onay mekanizması.

**BIST production, saf momentum/FIP çekirdeği, Yahoo/fiyat, tradability
değerlendirmesi ve canlı yayın değiştirilmedi.** Kod ayrı Draft PR'dadır.
