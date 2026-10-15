# A5l — SEC 12(b) listelenmiş pay sınıfı kanıtları, SPAC ordinary share vs unit ayrımı

**Denetim:** 15 Ekim 2026. **Kaynak directory as-of:** 14 Ekim 2026.
**Sürüm:** \`a5l-sec-listed-class-evidence-v1\`.
**Durum:** \`SEC_LISTED_CLASS_ROWS_REVIEW_ONLY\`.
**Nihai security_id/type/production onayı: 0.**

## Tekrar üretilebilir kaynak zinciri

A5k SEC pilotunun orijinal 9 SEC filing belgesi ve 9 SEC submissions
JSON ham dosyası, **A5k 13.287 kayıtlık resmî A4 source-replay
DENY envanteri** ile yeniden bağlandı:

| Kaynak | Tam SHA256 |
|---|---|
| A5k 9 issuer SEC raporu \`a5k-sec-pilot-evidence.json\` | \`e34c0fe0a2260a4d1a323591364ac9b509c1fc39ea49d9c9c40a4bc36c3d63ef\` |
| A5k \`a5k-full-universe-deny.json\` | \`e31bcca870189207e9273eea6ba4e48a55949e78822d2b7e8feb7fb3fc851a76\` |
| **A5l çıktı: 9 issuer ayrıntılı listed-class audit** | \`cf342e3f17ba5d600f3bcfd0ed958976ef97272fe8b2749582a2a21093475992\` |

Her 9 issuer için SEC CIK adayı, filing accession, filingDate,
orijinal SEC primary-document URL, orijinal SEC asıl kaynak SHA256
ve byte uzunluğu A5k dondurulmuş kayıtlarıyla eşleştirildi.
SEC submissions orijinal dosya hash'leri ayrı ayrı doğrulandı.
A4 listed kaynak adı, ticker, MIC ve original
\`REVIEW_REQUIRED\` + \`DENY_OFFICIAL_SECURITY_TYPE_UNAPPROVED\`
durumu da A5k tüm evren kaydına karşı doğrulandı.

[A5l gerçek GitHub Actions koşusu — **245 test**](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38797915978).
[A5l satır kanıtı JSON ve hash manifesti](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38797915978/artifacts/12002284456).
Ham 9 SEC asıl raporun SHA-pinned artifact'ı:
[A5k SEC orijinal arşivi](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38763550078/artifacts/11986213819).
Artifact'ların saklama süresi **90 gün**; kalıcı,
historical \`known_at\` kanıt arşivi henüz kurulmadı.

## SEC 10-Q section 12(b) satır kanıtı — 6/6 pozitif

A5e'nin \`Common Stock\` arama örüntüsünü körü körüne
tekrar etmek yerine şu daha dar ve daha kesin yöntem uygulandı:

- HTML \`<tr>\` içindeki **ayrı ticker hücresi tam eşleşmeli**
  (\`AACI\` ve \`AACIU\`, \`ARR\` ve \`ARR-PRC\` farklı kalır).
- Öncesindeki **pay başlığı** hücresi ve sonrasındaki
  **nasdaq/NYSE borsa** hücresi aynı SEC satırında olmalı.
- Başlık, \`Class A ordinary shares\`, \`Common Stock\`,
  \`Common Shares\`, \`preferred\`, \`unit\`, \`warrant\`,
  \`depositary\` gibi farklı metin şablonları üzerinden
  *kanıt adayı* olarak ayrıştırılır. Ayrı sınıflar
  otomatik birleştirilmez.
- SEC financial cover tablosu öncelikli; ilk 100 satır
  dışında kalan serbest finansal terimler sınıf onayı sayılmaz.

| Ticker | SEC 10-Q'da birebir pay başlığı ve borsa | Kanıt türü |
|---|---|---|
| **AACI** | *Class A ordinary shares, par value $0.0001 per share, included as part of the units* / Nasdaq | \`CLASS_A_ORDINARY_SHARES\`, ayrıca \`UNIT\` dipnotu |
| **ADAC** | *Class A ordinary shares, par value $0.0001 per share* / Nasdaq | \`CLASS_A_ORDINARY_SHARES\` |
| **ASPC** | *Class A ordinary shares, no par value* / Nasdaq | \`CLASS_A_ORDINARY_SHARES\` |
| **ARR** | *Common Stock, $0.001 par value* / NYSE | \`COMMON_STOCK\` |
| **RHP** | *Common stock, par value $.01* / NYSE | \`COMMON_STOCK\` |
| **WPC** | *Common Stock, $0.001 Par Value* / NYSE | \`COMMON_STOCK\` |

SEC asıl kaynakları:
[AACI 10-Q](https://www.sec.gov/Archives/edgar/data/2092897/000119312526346822/d137286d10q.htm),
[ADAC 10-Q](https://www.sec.gov/Archives/edgar/data/2083002/000110465926097135/adac-20260630x10q.htm),
[ASPC 10-Q](https://www.sec.gov/Archives/edgar/data/1890361/000121390026088396/ea0299312-10q_aspac3.htm),
[ARR 10-Q](https://www.sec.gov/Archives/edgar/data/1428205/000142820526000090/arr-20260630.htm),
[RHP 10-Q](https://www.sec.gov/Archives/edgar/data/1040829/000110465926092580/rhp-20260630x10q.htm),
[WPC 10-Q](https://www.sec.gov/Archives/edgar/data/1025378/000102537826000119/wpc-20260630.htm).

**Önemli AACI ayrımı:** \`Class A ordinary shares\` başlığında
\`included as part of the units\` sözcükleri bulunması,
AACI'nin unit koduyla aynı security_id veya aynı işlem
sözleşmesi olduğu anlamına **gelmez**. Resmî unit/warrant
ayrışması ve trading commencement history ayrıca gerekir.

## Fon adaylarında N-CSRS — 3/3 issuer belgesi, 0 listed-class

- **CCD:** [SEC N-CSRS](https://www.sec.gov/Archives/edgar/data/1602584/000110465926080383/tm2610083d8_ncsrs.htm)
- **CGO:** [SEC N-CSRS](https://www.sec.gov/Archives/edgar/data/1285650/000110465926080370/tm2610083d3_ncsrs.htm)
- **CSQ:** [SEC N-CSRS](https://www.sec.gov/Archives/edgar/data/1275214/000110465926080392/tm2610083d4_ncsrs.htm)

N-CSRS'nin varlığı ve source CIK kimliği, şirket/fon düzeyi
SEC raporlama kanıtıdır. **SEC 10-Q section 12(b)
ticker-cell tablosu değildir**. Fonun resmî borsa
pay sınıfı, MIC/ticker, açık-kapalı fon türü, N-2 ve
kapsam politikasının onayı ayrı değerlendirilmelidir.
SEC N-CSRS içinde genel olarak \`common shares\` veya
\`preferred shares\` ifadesi bulunması listed ticker
hakkında sınıf onayı değildir.

## Denetim sonucu ve açık kapılar

| Sonuç | Adet |
|---|---:|
| Kaynak bütünlüğü ve original REVIEW_REQUIRED durumu doğrulanan | 9 |
| SEC ticker + başlık + borsa aynı satırda \`Class A ordinary shares\` | 3 |
| SEC ticker + başlık + borsa aynı satırda \`Common Stock\` | 3 |
| N-CSRS issuer/fon raporu; borsaya kayıtlı pay sınıfı ayrıca belirsiz | 3 |
| Nihai güvenlik sınıfı \`security_id\` onayı | **0** |
| Nihai kapsam/type onayı | **0** |
| Production izinli | **0** |

**A5k tam evren güvenlik kapısı korunur:** 13.287 resmî listed
satırından 4.556 provisional INCLUDE ve 1.010 review olmak
üzere toplam 5.566 adayın hepsi **DENY** durumunda,
7.721 EXCLUDE dışarıda. A5l herhangi bir satırı
REFI/LIEN dahil \`INCLUDE\` veya production'a yükseltmedi.

Devam eden kanıt ihtiyacı: resmî borsa *listed security*
master veya eşdeğer veri; SPAC ordinary/share vs unit/
warrant effective date; fon open-end vs closed-end ve
resmî listed-share class; REIT issuer legal ve common
security kimliğinin ayrı onayı; tüm 1.010 inceleme
kaydı için belge-temelli karar; source \`known_at\`
ile \`effective_at\` ve ayrı yetkili imza onayı.
2026-10-15'te alınmış SEC kaydı
\`known_at=2026-10-14\` olarak otomatik kabul edilmez.

**Sistem değişiklik kapsamı:** Draft branch dışında yok.
\`main\`, BIST V2.0.1 production, US fiyat/Yahoo/ATR,
momentum/FIP hesaplama, 90 seans tradability,
SQLite production migration, yayın ve portföy
kararları değiştirilmedi.
