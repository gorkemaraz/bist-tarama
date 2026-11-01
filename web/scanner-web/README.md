# BIST Tarama

Günlük kapanış verisiyle BIST hisselerinde mum formasyonu ve indikatör taraması.

## Kurulum (bir kez)

```powershell
cd "C:\Users\gorke\Desktop\Algo projects"
.venv\Scripts\pip install -r web\scanner-web\requirements.txt
```

## Çalıştırma

```powershell
cd "C:\Users\gorke\Desktop\Algo projects\web\scanner-web"
..\..\.venv\Scripts\python -m data.update        # veriyi güncelle (ilk seferde 5 yıllık geçmiş iner)
..\..\.venv\Scripts\uvicorn app:app --reload     # http://127.0.0.1:8000
```

Veri arayüzdeki **Veriyi Güncelle** butonuyla da güncellenebilir. En doğru sonuç için seans kapanışından sonra (18:15+) güncelle.

## Yapı

| Yol | Görev |
|---|---|
| `data/tickers.txt` | Taranan semboller (düzenlenebilir) |
| `data/sources.py` | Yahoo (ana kaynak) ve İş Yatırım (doğrulama) veri çekimi |
| `data/quality.py` | Eksik kapanış tamamlama, kaynak karşılaştırma, şüpheli hareket tespiti |
| `data/update.py` | Artımlı güncelleme, bedelsiz/bölünme sonrası geçmişi yeniden indirme |
| `data/market.db` | Yerel SQLite veritabanı |
| `scanners/candles.py` | Mum formasyonları |
| `scanners/technical.py` | RSI, MACD, EMA, hacim, 52 haftalık zirve sinyalleri |
| `scanners/__init__.py` | Tarama kaydı (`SCANS`) |
| `scanners/filters.py` | Bağlam filtreleri (trend, hacim, RSI, 52h aralık, likidite) |
| `backtest.py` | Sinyallerin geçmiş performansı ve piyasa ortalamasıyla karşılaştırma |
| `static/vendor/` | TradingView Lightweight Charts 4.2.0 (yerel kopya) |

## Backtest kuralları

- Sinyal t günü kapanışında bilinir → giriş **t+1 açılış**, çıkış **t+h kapanış** (h = 1, 5, 10, 20 gün).
- Gidiş-dönüş %0,2 komisyon düşülür. Günlük %30'u aşan hareket içeren işlemler veri hatası sayılıp atılır.
- **Fark** = sinyal ortalaması − aynı kuralla tüm hisse/günlerin ortalaması. Formasyonun değeri bu farktır.
- **Filtreler** sinyalle VE'lenir. Filtre analizi, mevcut kombinasyona her filtre tek tek eklenince sonucu gösterir.
- **Dönem ayırma testi:** fark verinin ilk %60 ve son %40 döneminde ayrı ölçülür; ✓ iki dönemde de beklenen yönde demektir.
  Çok filtre denemek şans eseri iyi sonuç bulma ihtimalini artırır, tutarlı olmayanlara güvenme.
- Sınırlar: gözlemler bağımsız değil (aynı gün çok hisse), sadece bugün işlem gören hisseler var (hayatta kalma yanlılığı).

## Yeni tarama eklemek

1. `scanners/candles.py` veya `technical.py` içine `df -> bool Series` döndüren bir fonksiyon yaz
   (her bar için "sinyal bu barda oluştu mu"). Aynı fonksiyon ileride backtest'te de kullanılacak.
2. `scanners/__init__.py` içindeki `SCANS` listesine bir `Scan(...)` satırı ekle.

## Veri kaynakları hakkında

- **Yahoo (yfinance):** Ücretsiz, gayriresmi. Son günün kapanışı bazen boş gelir → önce İş Yatırım'dan
  resmi kapanış, o da yoksa Yahoo saatlik verisinden yaklaşık kapanış alınır ve raporlanır.
- **İş Yatırım (isyatirimhisse):** Resmi API değil, sitenin veri adresi. Açılış fiyatı yok; yoğun istekte
  kısıtlama uyguluyor, bu yüzden her güncellemede sınırlı sayıda sembol karşılaştırılır.
