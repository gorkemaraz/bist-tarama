"""Fiyat veri kaynakları.

Her kaynak uzun formatta DataFrame döndürür: symbol, date (YYYY-MM-DD), open, high, low, close, volume
- Yahoo: ana kaynak (OHLCV, adet bazında hacim). Son günün kapanışı bazen boş gelir.
- İş Yatırım: doğrulama kaynağı. Açılış fiyatı yok, hacim TL bazında.
"""
import warnings
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date

import pandas as pd
import yfinance as yf
from isyatirimhisse import fetch_stock_data

# yfinance'ın pandas 3 ile ürettiği deprecation uyarıları
warnings.filterwarnings("ignore", module="yfinance")

COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume"]


def fetch_yahoo(symbols: list[str], start: date, chunk: int = 50) -> pd.DataFrame:
    frames = []
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        raw = yf.download(
            [f"{s}.IS" for s in part], start=start.isoformat(),
            group_by="ticker", auto_adjust=False, progress=False, threads=True,
        )
        if raw.empty:
            continue
        tickers = set(raw.columns.get_level_values(0))
        for s in part:
            if f"{s}.IS" not in tickers:
                continue
            df = raw[f"{s}.IS"].rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
            df = df.dropna(how="all")
            if df.empty:
                continue
            df = df.reset_index().rename(columns={"Date": "date"})
            df["symbol"] = s
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out[COLUMNS]


def fetch_yahoo_last_close(symbols: list[str], day: str) -> dict[str, float]:
    """Günlük kapanışı boş gelen semboller için o günün son saatlik barının kapanışı (yaklaşık değer)."""
    raw = yf.download([f"{s}.IS" for s in symbols], period="5d", interval="1h",
                      group_by="ticker", auto_adjust=False, progress=False, threads=True)
    out = {}
    if raw.empty:
        return out
    tickers = set(raw.columns.get_level_values(0))
    for s in symbols:
        if f"{s}.IS" not in tickers:
            continue
        close = raw[f"{s}.IS"]["Close"].dropna()
        close = close[close.index.strftime("%Y-%m-%d") == day]
        if not close.empty:
            out[s] = float(close.iloc[-1])
    return out


def fetch_isyatirim(symbols: list[str], start: date, workers: int = 4, budget_s: float = 90) -> pd.DataFrame:
    """İş Yatırım günlük verisi. Sunucu sembol başına istek istiyor ve yoğun istekte kısıtlıyor;
    bu yüzden sınırlı paralellik ve toplam süre bütçesiyle çağrılır. Yetişmeyen/hata veren semboller atlanır."""
    start_str = start.strftime("%d-%m-%Y")

    def one(symbol):
        try:
            return fetch_stock_data(symbol, start_date=start_str)
        except Exception:
            return None

    pool = ThreadPoolExecutor(workers)
    futures = [pool.submit(one, s) for s in symbols]
    done, _ = wait(futures, timeout=budget_s)
    pool.shutdown(wait=False, cancel_futures=True)
    frames = [f.result() for f in done]
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    raw = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame({
        "symbol": raw["HGDG_HS_KODU"],
        "date": pd.to_datetime(raw["HGDG_TARIH"]).dt.strftime("%Y-%m-%d"),
        "open": float("nan"),
        "high": raw["HGDG_MAX"],
        "low": raw["HGDG_MIN"],
        "close": raw["HGDG_KAPANIS"],
        "volume": raw["HGDG_HACIM"],  # TL bazında
    })
    return out
