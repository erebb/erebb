# Kod Denetim Raporu — 2026-07-06

Kapsam: `xauusd_fvg_engine_v10.py` (motor + 5 strateji), `xauusd_live_trader.py`,
`gui.py`, `config.py` + `config/default.json`, `download_data.py`,
`download_data_mt5.py`, `scripts/`, `tests/`, depo hijyeni.

Yöntem: satır-satır inceleme + config anahtarı çapraz-kontrol scripti +
tüm test paketinin çalıştırılması + dört stratejinin regresyon backtest'leri.

---

## 1. Bulunan ve DÜZELTİLEN sorunlar

### 1.1 London Reversal'da geometri koruması eksikti (RİSK → düzeltildi)
`QweBacktestEngine._make_entry_trade` girişin SL'ye gap'lenmesine karşı korumalıydı
(`geom_ok`), fakat `LondonBacktestEngine._make_entry_trade` değildi. Sinyal barından
sonraki açılış SL'nin ötesine gap yaparsa `risk_per` 0.01 tabanına düşer → devasa
pozisyon + anlamsız RR. Aynı koruma + gün-limiti iadesi London'a eklendi.
Regresyon değişmedi (mevcut veride hiç tetiklenmiyor; sigorta niteliğinde).

### 1.2 GUI, doğrulanmış preset'lere TBE uyguluyordu (HATA → düzeltildi)
`london` ve `qwe` sabit-bias preset'leri **TBE'siz** doğrulandı; ama GUI'nin TBE
seçimi (varsayılan önerisi 8h!) bu stratejilere de uygulanıyordu → GUI sonuçları
rapor edilen tablolardan sessizce sapabiliyordu; 8h zaman çıkışı QWE swing
işlemlerini (medyan ~10-26h, max 14 gün) keserdi. Artık london/qwe her zaman
`time_exit_bars=None` ile koşar; menü bu stratejilerde TBE sorusunu atlar.

### 1.3 `tests/test_engine_full.py` çalışmıyordu (HATA → düzeltildi)
Motordan geçmişte kaldırılmış `BreakerEngine` ve `detect_horseshoe_1h` import
ediliyordu → koleksiyon aşamasında ImportError, TÜM dosya çalışmaz durumdaydı.
Bayat iki test grubu + bir entegrasyon testi kaldırıldı. Paket artık yeşil:
**179 test geçiyor** (`python3 -m pytest tests -q`).

### 1.4 Bayat debug scriptleri kaldırıldı (YANILTICI → silindi)
`scripts/debug_london.py` ve `debug_london2.py`, London mantığının ESKİ bir
kopyasını gömülü taşıyordu (motor o zamandan beri üç kez yeniden yazıldı).
Çalıştıran birini yanlış sonuçlarla yanıltırdı. Git geçmişinde duruyorlar.

### 1.5 Küçük temizlikler (düzeltildi)
- `download_data_mt5.py`: `datetime.utcnow()` → tz-bilinçli eşdeğeri
  (Python 3.12+ deprecation; modül kullanıcının Windows makinesinde koşuyor).
- `xauusd_live_trader.py`: strategy='qwe' iken gereksiz MarketBrain kurulumu
  kaldırıldı; dosya başlığındaki kullanım örneklerine `--strategy` eklendi.
- `README.md` eklendi (depoda hiç yoktu).

## 2. Doğrulanan ve TEMİZ çıkan alanlar

- **Lookahead güvenliği**: London (5 giriş modu, `_pass_filters`, `_progress_setup`)
  ve QWE (swing confirm gecikmesi, `avail_ts`/`expire_ts` zaman damgaları, 15M
  kümülatif onay mumları, 4H tamamlanmış-blok yönü) — sinyaller yalnızca kapanmış
  bar bilgisiyle üretiliyor; girişler `O[idx+1]`. Ayrıca mekanik assert'lerle test edildi.
- **Kısmi-çıkış muhasebesi** (`_process_exit`): TP1 kısmi + BE + runner PnL
  toplamları tutarlı; test paketi kapsıyor.
- **Config anahtarları çapraz-kontrolü**: kodda okunan her anahtar JSON'da mevcut
  (tek istisna `london_reversal.require_mss` — bilinçli geriye-uyum anahtarı,
  yokluğu doğru varsayılan verir).
- **Depo hijyeni**: `.gitignore` `live_config.json` (API anahtarları) ve
  `live_state.json`'ı dışlıyor; depoda sır yok; `__pycache__` izlenmiyor.
- **Canlı/backtest drift koruması**: QWE bağlam dizileri tek fonksiyondan
  (`QweBacktestEngine.prepare_kwargs`); stub-client simülasyonu canlı yolun
  backtest ile aynı barda aynı sinyali ürettiğini doğruladı.

## 3. Bilinen sınırlamalar (kod hatası değil — takip önerilir)

1. **Veri inceliği**: tüm sonuçlar ~4.5 aylık 5M kripto-altın verisiyle. London
   private preset'i N=2, QWE none N=24 işlem üretiyor. MT5'ten 1 yıllık veri
   inince tüm grid'ler yeniden doğrulanmalı (özellikle hafta sonu davranışı
   değişecek: MT5 verisinde Cmt/Paz bar yok).
2. **Canlı QWE breakeven'i yazılımsaldır**: TP1 dolduktan sonra BE, bot döngüsü
   tespit edince uygulanır (borsa-taraflı değil); bot kapalıyken fiyat girişe
   sararsa yalnızca orijinal borsa SL'i korur. Backtest'teki anlık BE'nin
   yaklaşığıdır — bilinçli tasarım kararı, kodda ve logda belirtilir.
3. **`config/default.json → live`** bölümündeki `risk_pct/leverage/symbol/tbe_minutes`
   anahtarları canlı bot tarafından OKUNMAZ (bot kendi `live_config.json`'ını
   kullanır; config modülünden yalnız `live.strategy` okunur). Yanıltıcı olabilir;
   şimdilik dokunulmadı çünkü GUI ayarlar menüsü bu bölümü gösteriyor olabilir.
4. **Motor `main()` CLI'ı yalnızca FVG akışını koşar** (tarihsel giriş noktası);
   london/qwe backtest'leri GUI veya `scripts/` üzerinden. Birleştirme istenirse
   ayrı iş.
5. **MT5 saat dilimi**: broker EET ise `--utc-offset 2/3` verilmezse killzone
   stratejileri kayar — modül bunu başlıkta ve çıktıda uyarıyor ama zorlayamıyor.
6. **PDH/PDL hafta sonu tanımı** kripto-altın verisine göre (takvim günü);
   MT5 verisinde Pazartesi'nin "önceki günü" Cuma olur — mevcut kod bunu doğal
   karşılar (tamamlanmış son gün), davranış değişikliği beklenmez ama 1 yıllık
   veriyle test edilmeli.

## 4. Regresyon durumu (denetim sonrası)

| Test | Sonuç |
|---|---|
| pytest paketi | 179 geçti / 0 kaldı |
| FVG daily 1:1 | 21 işlem / +667.75 (değişmedi) |
| ThreeVol daily 1:2fix | 26 / +2049.33 (değişmedi) |
| London private (preset) | 2 / +501.08 (değişmedi) |
| QWE none (preset) | 24 / +594.33 (değişmedi) |
| GUI qwe/london sabit-bias + TBE'siz akış | doğrulandı |
