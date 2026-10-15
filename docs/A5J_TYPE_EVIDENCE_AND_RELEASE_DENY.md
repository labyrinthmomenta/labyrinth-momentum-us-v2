# A5j — Resmî enstrüman kanıtı matrisi ve bağımsız DENY release gate

**15 Ekim 2026**, araştırma as-of **14 Ekim 2026**. 
**Sürüm:** \`a5j-type-review-release-deny-v1\`. 
**Durum:** \`CLASSIFICATION_EVIDENCE_TRIAGE_REVIEW_ONLY\`.
Bu aşama **production evren onayı, type promotion, menkul kıymet
kimliği ataması veya canlı yayın değildir**.

## Kaynağı doğrulanmış çalışma

A5j, A5i + A5b + A5e'nin **birbirinden ayrı resmî Nasdaq/SEC
kaynaklarını** tekrar kullanır. Eski ya da karışmış snapshot'lardan
yeni karar üretmemek için önce aşağıdaki artefaktların birebir SHA256
değerini doğrular.

| Resmî kanıt zinciri | Dondurulmuş kaynak SHA256 |
|---|---|
| A5i: 1.010 A5 review satırı + REFI/LIEN overlay | \`306be7c6293649b367caa999fa374c1fcd7f7caa41af6f9f3bef58b95387922a\` |
| A5b: 1.010 SEC mutual-fund class çapraz taraması | \`8268c9368d1a25cad184ad79434d69d328fca550ad1a265ff224497783ff85d7\` |
| A5e: 16 issuer 2026 10-Q rapor kanıtı | \`a58638402bbdc59b7afb2de3dfe439c6672cc0a1ede40fb59bd8a283aea7612f\` |
| SEC mutual-fund registry ham resmî kaynak | \`6a98923d0aad49aa386be6423892f19d489047a9041ef09c81af89302d599efc\` |
| **A5j tamamlanmış 1.010 satırlık kanıt matrisi** | \`48e686707c763b71c1ecb0c63a7361a87df04dec59ed2d75873250fdd64b1ed5\` |
| **A5j DENY-only gate simülasyonu** | \`ade63abe33ed1f80e7c5c8f866473cc93cf10a0a1dca19abb2354601e6909d8f\` |

[Başarılı, 220 testlik tek seferlik GitHub Actions](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38743416303).
[Ham A5j araştırma çıktısı: 1.010 satırlık triage, summary ve gate simülasyonu](https://github.com/labyrinthmomenta/labyrinth-momentum-us-v2/actions/runs/38743416303/artifacts/11976601105).
Arşiv **90 gün** saklanır, kalıcı kanıt deposu olarak kabul edilmez.
A5j yeni internet fiyat/veri sağlayıcısı istemedi: yalnız geçmiş
SEC/Nasdaq **hash ile sabitlenmiş** kaynakları yeniden denetledi.

A5e'nin 16 10-Q asıl HTML dosyası SHA256 + byte uzunluğuyla tek
tek yeniden doğrulandı. SEC 10-Q kapaklarında ilgili ticker,
Common Stock ve borsa aynı satırda raporlandığı için *pay sınıfı
adayı* düzeyinde kanıt var. 10-Q içeriğinde görülen BDC ifadesi
şirketin 2026'da hukukî statüsünün kesintisiz sürdüğünü kendi
başına kesinleştirmez; **SEC issuer CIK ayrı, security_id ayrı**.
Bu nedenle 16 adayın her biri REVIEW_REQUIRED kaldı.

## A5 enstrüman türü doğrulama matrisi

| Orijinal A5 nedeni | Kayıt | Sıradaki gerçek kanıt | A5j onayı |
|---|---:|---|---:|
| FINANCIAL_STATUS_REVIEW | 268 | Nasdaq finansal statü çözümü; resmî listed class | 0 |
| FUND_NAME_REQUIRES_TYPE_EVIDENCE | 297 | SEC N-2/10-K; REIT ile open/closed-end fund ayrımı; share class | 0 |
| SPAC_BDC_OR_FINANCIAL_REVIEW | 307 | S-1, N-54A/N-54C, SPAC unit/common/warrant; kapsam politikası | 0 |
| TYPE_UNCONFIRMED | 128 | Yetkili borsa security type/class ve as-of | 0 |
| UNKNOWN_EXCHANGE_CODE / TXSE | 10 | Resmî MIC/source scope + insan onayı | 0 |
| **Toplam** | **1.010** | **Hâlâ incelemede** | **0** |

A5b'nin SEC \`company_tickers_mf.json\` fon sınıfı kaynağında
1.010 ticker için **0 tam eşleşme** bulundu. Kaynak çoğu
closed-end fund (özellikle N-2 kapsamı) için bütüncül bir security
master değildir. Dolayısıyla **1.010 kayıt fon dışıdır** veya
**1.010 adi hissedir** sonucu çıkarılamaz.

İlk 1.010 kaydın Nasdaq ad alanından türetilmiş, **örtüşebilen
yalnızca metin ipuçları**: \`Acquisition=243\`,
\`BDC=9\`, \`Closed End Fund=32\`, \`REIT=4\`,
\`Trust=61\`; bazı adlarda \`Common Stock=350\` ve
\`Common Shares=102\`. Bu işaretler kaynak şirket menkul kıymet
türünü veya yasal statüyü nihai olarak doğrulamaz.

## CIK eşleştirme boşlukları

SEC'nin tam ticker+MIC issuer adayı bulunmayan **56** inceleme kaydı:

| Kategori | Eksik exact issuer CIK adayı |
|---|---:|
| Fon/tür adayı | 27 |
| SPAC/BDC/finansal adayı | 3 |
| Tür doğrulanmamış | 16 |
| Resmî kapsamı henüz çözülmemiş exchange kodu | 10 |
| **Toplam** | **56** |

Bu sayı **56 delist veya 56 EXCLUDE** anlamına gelmez. Özellikle
exchange/MIC eşdeğerliği için daha önce görülen XASE ve SEC'nin
daha genel \`NYSE\` etiketi ayrımı otomatik normalleştirilmedi.
CIK olmadan şirketin türü/SEC security title kararını otomatik
kapatmak yasaktır.

## DENY-only release gate — bağımsız, uygulamaya bağlı değil

A5j \`src.data.universe.a5j_type_release\` çalışma sınırları:

- Dondurulmuş 1.010 REVIEW_REQUIRED kaydının her biri için
  \`release_hold=true\`, \`production_eligible=false\`,
  \`known_at_established=false\` ve \`security_id=null\`.
- A4 \`INCLUDE\` olarak kalmış **REFI**, 1.010 A5 inceleme
  satırı içinde değildir. Bu nedenle LIEN'den ayrı ek
  \`PROVISIONAL_INCLUDE_CORPORATE_EVENT_HOLD\` kaydı tutulur.
- Simülasyonda **1.011/1.011 DENY**; **ALLOW=0**, **release
  permission=DENY**. Onaylanmamış türü, CIK'i, simge
  kaydını veya corporate hold'u manuel veri manipülasyonu
  değiştirmişse testler/denetim fail-closed.
- A4'teki geri kalan **4.555 provisional INCLUDE** bu A5j
  kapısında değerlendirilmedi. Simülasyon **tüm evrenin yayın
  uygunluğunu doğrulamaz**.
- **Bağımsız gerçek yetkili onay doğrulaması uygulanmış değildir**.
  A5j'nin DENY-only simülasyonu **production yayın motoruna
  bağlanmadı**. Yalnız sahte bir \`approved=true\` veya
  kaynak ismi üzerinden ALLOW üretilemez.
- Bu sürümde **hiçbir ALLOW yolu yoktur**. Gelecek gerçek
  release gate için ayrı onay tasarımı, testler ve kullanıcının
  onayı gerekir.

## Gerçek release gate'e geçmeden gerekli koşullar

1. **Tüm universe adayları** kapsanmalı: 4.556 provisional
   INCLUDE + 1.010 REVIEW_REQUIRED ve özellikle sonraki
   14 Ekim snapshot'larında değişen semboller.
2. Resmî **security master** veya aynı kanıt gücünde tarihli
   borsa ve SEC sınıf kaynağından, \`MIC/ticker/class/security_id\`
   bağımsızlığı sağlanmalı. Issuer CIK tek başına yeterli değil.
3. BDC/SPAC/REIT/fon kapsam politikası, Class A/B common,
   unit/warrant, ADR ve tercihli paylar için açık olarak
   kabul edilmeli. A5j araştırma kuralları politika kararı değildir.
4. \`known_at\` ile \`filing_date\`/\`effective_at\` ayrı tutulmalı;
   15 Ekim alınmış yeni SEC içeriği 14 Ekim'de varmış gibi
   geriye dönük uygulanamaz.
5. Yetkili reviewer kararının özgün kaynak hash, as-of,
   security ID ve policy version'a bağlandığı **bağımsız
   doğrulanabilir onay/sahiplik katmanı** tasarlanmalı.
   İmzasız metin, Github PR açılması veya bir SHA hash'i
   tek başına yetkilendirme değildir.
6. Gerçek release gate kodu production'a bağlanmadan önce
   \`REFI/LIEN\` ve kaynak eksikliği dahil **fail-closed
   uçtan uca entegrasyon testleri** yapılmalı. Artık 90 günlük
   GitHub artifacts kalıcı kaynak saklama çözümü sayılmamalı.

**Değişmedi:** \`main\`, BIST V2.0.1 production,
US momentum/FIP çekirdeği, Yahoo/fiyat, ATR/tradability,
SQLite production schema ve canlı yayın; hiçbir hisse production
üyeliği veya portföy işlemi kazanmadı.
