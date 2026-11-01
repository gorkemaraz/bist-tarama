"""Tarama kaydı. Yeni tarama eklemek için: candles.py / technical.py'ye bir sinyal fonksiyonu yaz,
aşağıdaki SCANS listesine bir satır ekle."""
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from . import candles, technical
from .filters import FILTERS, apply_filters

MIN_BARS = 30


@dataclass(frozen=True)
class Scan:
    id: str
    title: str
    description: str
    category: str   # "Mum Formasyonu" | "İndikatör"
    direction: str  # "up" | "down" | "neutral"
    signal: Callable[[pd.DataFrame], pd.Series]


SCANS = {s.id: s for s in [
    Scan("three_inside_up", "Three Inside Up", "Düşüş sonrası uzun kırmızı mum, içinde yeşil harami, ardından birincinin açılışını aşan yeşil mum.", "Mum Formasyonu", "up", candles.three_inside_up),
    Scan("three_inside_down", "Three Inside Down", "Yükseliş sonrası uzun yeşil mum, içinde kırmızı harami, ardından birincinin açılışının altında kapanış.", "Mum Formasyonu", "down", candles.three_inside_down),
    Scan("bullish_engulfing", "Yutan Boğa", "Düşüş sonrası yeşil mum önceki kırmızı mumun gövdesini tamamen yutar.", "Mum Formasyonu", "up", candles.bullish_engulfing),
    Scan("bearish_engulfing", "Yutan Ayı", "Yükseliş sonrası kırmızı mum önceki yeşil mumun gövdesini tamamen yutar.", "Mum Formasyonu", "down", candles.bearish_engulfing),
    Scan("morning_star", "Sabah Yıldızı", "Uzun kırmızı, küçük gövdeli kararsız mum, ardından güçlü yeşil mum.", "Mum Formasyonu", "up", candles.morning_star),
    Scan("evening_star", "Akşam Yıldızı", "Uzun yeşil, küçük gövdeli kararsız mum, ardından güçlü kırmızı mum.", "Mum Formasyonu", "down", candles.evening_star),
    Scan("hammer", "Çekiç", "Düşüş sonrası uzun alt gölgeli, küçük gövdeli mum.", "Mum Formasyonu", "up", candles.hammer),
    Scan("shooting_star", "Kayan Yıldız", "Yükseliş sonrası uzun üst gölgeli, küçük gövdeli mum.", "Mum Formasyonu", "down", candles.shooting_star),
    Scan("doji", "Doji", "Açılış ve kapanış neredeyse eşit; kararsızlık.", "Mum Formasyonu", "neutral", candles.doji),
    Scan("spinning_top", "Topaç (Spinning Top)", "Küçük gövde, iki yönde de gövdeden uzun gölgeler.", "Mum Formasyonu", "neutral", candles.spinning_top),
    Scan("rsi_oversold_exit", "RSI 30 Yukarı Kesişim", "RSI(14) aşırı satım bölgesinden çıktı.", "İndikatör", "up", technical.rsi_oversold_exit),
    Scan("rsi_overbought_exit", "RSI 70 Aşağı Kesişim", "RSI(14) aşırı alım bölgesinden çıktı.", "İndikatör", "down", technical.rsi_overbought_exit),
    Scan("macd_bull_cross", "MACD Al Kesişimi", "MACD(12,26) sinyal çizgisini (9) yukarı kesti.", "İndikatör", "up", technical.macd_bull_cross),
    Scan("macd_bear_cross", "MACD Sat Kesişimi", "MACD(12,26) sinyal çizgisini (9) aşağı kesti.", "İndikatör", "down", technical.macd_bear_cross),
    Scan("ema_golden_cross", "EMA 20/50 Yukarı Kesişim", "Kısa vadeli ortalama orta vadeliyi yukarı kesti.", "İndikatör", "up", technical.ema_golden_cross),
    Scan("ema_death_cross", "EMA 20/50 Aşağı Kesişim", "Kısa vadeli ortalama orta vadeliyi aşağı kesti.", "İndikatör", "down", technical.ema_death_cross),
    Scan("volume_spike_up", "Hacim Patlaması", "Hacim 20 günlük ortalamanın 2 katını aştı, gün yükselişle kapandı.", "İndikatör", "up", technical.volume_spike_up),
    Scan("high_52w_breakout", "52 Haftalık Zirve Kırılımı", "Kapanış son 1 yılın en yüksek kapanışını geçti.", "İndikatör", "up", technical.high_52w_breakout),
]}


def signal_for(scan_id: str, df: pd.DataFrame, filters: tuple[str, ...] = ()) -> pd.Series:
    """Taramanın sinyali, verilen bağlam filtreleriyle VE'lenmiş halde."""
    sig = SCANS[scan_id].signal(df).fillna(False).astype(bool)
    return apply_filters(sig, df, filters)


def run_scan(scan_id: str, prices: dict[str, pd.DataFrame], days: int = 1, filters: tuple[str, ...] = ()) -> list[dict]:
    """Son `days` işlem gününde sinyal veren hisseleri döndürür."""
    all_dates = sorted(set().union(*(df.index for df in prices.values()))) if prices else []
    window = set(all_dates[-days:])

    results = []
    for symbol, df in prices.items():
        if len(df) < MIN_BARS:
            continue
        sig = signal_for(scan_id, df, filters)
        hits = sig[sig & df.index.isin(window)]
        if hits.empty:
            continue
        d = hits.index[-1]
        i = df.index.get_loc(d)
        close, prev = df["close"].iloc[i], df["close"].iloc[i - 1]
        avg_vol = df["volume"].iloc[max(0, i - 20):i].mean()
        results.append({
            "symbol": symbol,
            "date": d.strftime("%Y-%m-%d"),
            "close": round(float(close), 2),
            "change_pct": round(float((close / prev - 1) * 100), 2),
            "volume": int(df["volume"].iloc[i]),
            "rel_volume": round(float(df["volume"].iloc[i] / avg_vol), 2) if avg_vol else None,
            "last_close": round(float(df["close"].iloc[-1]), 2),
        })
    return sorted(results, key=lambda r: (r["date"], r["rel_volume"] or 0), reverse=True)
