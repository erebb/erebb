# Kod Denetim Raporu — 2026-07-06 (güncelleme: 2026-07-08 lookahead denetimi)

## EK-2 — 2026-07-08: DAILY BIAS LOOKAHEAD'İ (majör, düzeltildi)

London'ın "yılda 5-6 işlem çok az" incelemesi sırasında projenin en eski ve en
büyük lookahead'i bulundu: `DailyBiasProvider` gün D'nin bias'ı olarak **gün
D'nin KENDİ gerçekleşen yönünü** (open→close) döndürüyordu — strateji sabah
06:00'da günün nasıl kapanacağını "biliyordu". Tarihteki TÜM daily-bias
sonuçları (ör. FVG daily %76 WR, ThreeVol daily +2049/+2994) bu nedenle
ŞİŞİKTİ. Kesme-değişmezliği testi bunu yakalayamaz (bias dosyası fiyat
kesmesinden bağımsız statik girdi).

Düzeltme: `DailyBiasProvider.get()` artık **en son TAMAMLANMIŞ günün** yönünü
döndürür (dünün momentumu; hafta sonu boşlukları için 4 güne kadar geriye
tarama). `build_from_1h` değişmedi (dürüst tarihsel kayıt). Düzeltme sonrası
dürüst daily sonuçları bu ekin altındaki tabloda ve commit mesajındadır —
önceki daily satırlarıyla karşılaştırılamaz.

Not: `PrivateBiasProvider` zaten nedenseldi (London-öncesi son 1H bar);
`weekly_bias.json` kullanıcının manuel/ileriye dönük çağrıları olduğundan
kapsam dışıdır.

**Dürüst daily ile 1 yıllık yeniden ölçüm** (eski şişik değerlerle
karşılaştırma): FVG daily 114/+417 (PF 1.11), ThreeVol daily 124/+697
(PF 1.09) — eski "+2994" düzeyleri lookahead ürünüydü.

**FVG/ThreeVol dürüst grid'i (bias × RR × EMA, 22 hücre, 1 yıl):**
- FVG kazananı: `none + EMA-MACD + 1:2fix` → 91/+748, PF 1.26, Sh 0.87, DD %3.5
  (private 1:2fix +795 ama DD %7.7; none bias EMA filtresiz TÜM RR'larda zararda —
  filtre fvg için none'ı kârlı yapan bileşen).
- ThreeVol kazananı: `daily + 1:2be` → 124/+1620, PF 1.27, Sh 0.91, DD %5.9
  (daily 1:1: +1430/Sh 1.01; none yalnız 1:2be+EMA'da artı: +640).
- GUI önerileri bu kazananlara çekildi (fvg: none+EMA, threevol: daily+1:2be);
  kullanıcı istediğini seçebilir. `backtest.default_bias` 'daily' yapıldı
  (weekly_bias.json manuel ve yalnız 20 haftayı kapsıyor).

**Nihai dürüst tablo (her strateji kendi kazananında, 1 yıl):**
| Strateji | Config | N | WR | PnL | PF | Sharpe | MaxDD |
|---|---|---|---|---|---|---|---|
| threevol | daily 1:2be | 124 | %39.1 | +1620 | 1.27 | 0.91 | %5.9 |
| fvg | none+EMA 1:2fix | 91 | %39.6 | +748 | 1.26 | 0.87 | %3.5 |
| qwe | none preset | 59 | %45.8 | +661 | 1.39 | 1.05 | %2.5 |
| london | private preset | 16 | %37.5 | +419 | 1.81 | 0.68 | %1.8 |
| **toplam** | | 290 | | **+3448** | | | |

**London preset güncellemesi** (kullanıcı isteği: yılda 5-6 işlem çok az):
1 yıllık dürüst grid kazananı `immediate + tüm killzone + daily bias` →
**67 işlem/yıl, WR %40.3, +1313$, PF 1.61, Sharpe 1.16, MaxDD %3.7**
(eski preset: retest+w12+private, 6/+363). Config varsayılanı buna çekildi;
retest/w12/private seçenek olarak duruyor. İkinci en iyi (bias'sız istenirse):
retest+w12+none → 50/+954, PF 1.53, DD %2.9.

## EK — 2026-07-08: Lookahead denetimi + 1 yıllık veri bulguları

Kullanıcının "işlemleri önceden görüp alıyorsa WR şişer" şüphesi üzerine
**kesme-değişmezliği testi** yazıldı (`scripts/lookahead_check.py`): her strateji
tam veri ve %70'te kesilmiş veriyle koşulur; kesme öncesi işlemler birebir aynı
olmak zorundadır (geleceğe bakan bir hesap varsa geçmiş işlemler değişir).

**Sonuçlar:**
- FVG, ThreeVol, London: **TEMİZ** (kesme-değişmez).
- Çıkış mantığı muhafazakâr doğrulandı: aynı barda TP+SL → **SL sayılır**;
  TP1 ile SL aynı barda → TP1 atlanır. Bu yönden WR şişmesi yok (hafif kötümser).
- **QWE: LOOKAHEAD BUG BULUNDU ve DÜZELTİLDİ.** `compute_4h_context` blok
  başlangıçlarını `asi8` ile (saniye) döndürüyor, 5M zaman damgaları ns idi;
  `searchsorted` bozulup her barı SON 4H bloğuna eşliyordu → 4H yön filtresi
  tüm geçmişe veri setinin EN SON rejimini uyguluyordu (geleceği görme).
  Düzeltme: ns normalizasyonu. Canlı trader etkilenmemişti (canlıda "son blok"
  zaten doğru blok). Düzeltme sonrası QWE kesme testi TEMİZ (69==69).

**GUI ThreeVol hatası:** GUI 'threevol' seçiminde `ThreeVolBrain` yerine
`MarketBrain(poi_mode='three_vol')` (farklı bir varyant) kuruyordu — yeni ince
hacimli veride 0 işlem üretip stratejiyi bozuk gösterdi. Düzeltildi; artık
benchmark'lardaki gerçek ThreeVolBrain koşuyor (1 yıllık veride daily +2994).

**1 yıllık gerçek veriyle dürüst QWE yeniden-grid'i** (bug düzeltmesi sonrası,
bias=none): kazanan `618 + use_4h_dir + max_retest_vol_ratio=1.0` → 59 işlem,
WR %45.8, +661$, PF 1.39, Sharpe 1.05, MaxDD %2.5. Hacim onayı gerçek hacim
verisinde tutarlı katkı sağlıyor (kripto verisinde etkisizdi) → config
varsayılanı `max_retest_vol_ratio: 1.0` yapıldı. Eski kripto-veri preset
sayıları (ör. QWE +594) artık geçersizdir; referans bu rapordur.

**Veri notu:** Yüklenen 1 yıllık set 7/24 kesintisiz ve UTC damgalı (hacim
zirvesi 13-16 UTC = NY seansı ✓); Cumartesi dahil bar var → `weekend_filter`
hâlâ gerekli. Kullanıcının plan.txt'teki tablosu eski/kısmi bir koşudan
geliyordu; güncel kodla 1 yıllık tablo: FVG none 180/−161, ThreeVol daily
69/+2994, London private 6/+363, QWE none (yeni varsayılan) 59/+661.

---

(İlk denetim raporu aşağıda.)

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
