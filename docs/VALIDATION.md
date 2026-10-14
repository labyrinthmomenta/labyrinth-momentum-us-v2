# Başlangıç doğrulaması

Güncel A1 sonucu: 42 test geçti. İlk 16 testin aşağıdaki kaydı korunmuştur.
US parser/identity kapsamı ve canlı kaynak sınırı için [A1 raporuna](A1_UNIVERSE_STATUS.md) bakın.

14 Ekim 2026, yerel Python 3.12.10 ortamında:

- `python -m pytest -q`: **16 passed**.
- BIST'ten taşınan 10 dosyanın Git blob SHA-1 değeri provenance manifest'indeki
  kaynak değerlerle birebir eşleşti (byte-level karşılaştırma).
- Testler momentum bileşik getirisi, FIP işareti, Wilder ATR, delta, 253 kapanış
  gerekliliği, 231-return core pencere, son 21 return'ün dışlanması, tamamlanmış
  ay ve bozuk OHLC reddini kapsar.
- GitHub Actions yalnız offline test çalıştıracak şekilde tanımlandı; uzakta
  çalıştırılmadı. CI Python 3.11 seçili; bu sürüm yerelde ayrıca denenmedi.
- Canlı US veri/provider, evren sınıflandırması, takvim, corporate actions,
  SQLite, VCP/OOS ve publication henüz uygulanmadığından doğrulanmış değildir.
- US V1 Excel/CSV/full JSON regression çalıştırılmadı; bu aşama kaynak audit'idir.

Yerel commit kimliği yalnız bu depoda `Codex <codex@localhost>` olarak kullanılır;
kullanıcı adına commit kimliği tahmin edilmez. Uzak repo/push/release yapılmadı.
