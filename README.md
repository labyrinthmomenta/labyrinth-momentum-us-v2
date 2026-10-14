# Labyrinth Momentum US V2

Durum: A1 offline evren/kimlik altyapısı ve BIST V2.0.1 saf hesaplama çekirdeği.
Bu depo henüz canlı US screener değildir. Veri indirme, production yayın,
VCP ve zamanlanmış görevler etkin değildir.

- Mimari/core referansı: BIST V2.0.1, `c62d3d3a0bf41eaad4082373bb6c46a650a646fc`.
- US V1: yalnızca migration/regression referansı; kod taşınmadı.
- Kararlar ve uygulama sırası: [Başlangıç planı](docs/US_V2_BASLANGIC_PLANI.md).
- Taşınan dosyaların kaynak blob kimlikleri: [provenance](migration/provenance.json).
- Güncel resmi kaynak doğrulaması: [A1 canlı audit](docs/A1_LIVE_AUDIT.md).
- Önceki altyapı aşaması: [A1 durum raporu](docs/A1_UNIVERSE_STATUS.md).

Python 3.11+ ile proje kökünde:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

`src/calculation` ve `src/indicators` BIST etiketinden alınmıştır.
Çekirdek gözlem sıralamasıyla çalışır; US seans doğrulaması ve adjustment
adapter'ı tamamlanmadan production için kullanılmamalıdır.
Kaynakta kalan BIST takvimi açıklaması provenance korunması için değiştirilmedi.

Runtime DB ve ham veri Git'e eklenmez. İleride dış depolamada sürümlü
snapshot + checksum + geri yükleme kontrolü kullanılacak.

Evren ön incelemesi ve SQLite kimlik şeması eklendi. Resmi Nasdaq dosyaları
14 Ekim 2026 tarihinde indirildi ve kaynak doğrulaması geçti. 13.287 kayıt üzerinde
4.556 aday, 7.721 kapsam dışı ve 1.010 inceleme kaydı belirlendi. Bu aday sınıflaması
production onayı değildir. Toplam 53 test geçiyor; production kapalı.
