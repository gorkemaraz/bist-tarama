"""Bağlam filtreleri: bir sinyalle VE'lenerek "hangi koşulda işe yarıyor?" sorusunu test etmeye yarar.
Sözleşme sinyallerle aynı: DataFrame -> bool Series (o gün koşul sağlanıyor mu)."""
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from .indicators import ema, rsi, sma


@dataclass(frozen=True)
class Filter:
    id: str
    title: str
    group: str  # aynı gruptaki filtreler birbirini dışlar (ör. trend yukarı/aşağı)
    fn: Callable[[pd.DataFrame], pd.Series]


def _rel_volume(df):
    return df["volume"] / sma(df["volume"], 20).shift(1)


def _tl_volume(df):
    return sma(df["close"] * df["volume"], 20)


FILTERS = {f.id: f for f in [
    Filter("above_ema50", "Fiyat > EMA50", "trend_mid", lambda df: df["close"] > ema(df["close"], 50)),
    Filter("below_ema50", "Fiyat < EMA50", "trend_mid", lambda df: df["close"] < ema(df["close"], 50)),
    Filter("above_sma200", "Fiyat > SMA200", "trend_long", lambda df: df["close"] > sma(df["close"], 200)),
    Filter("below_sma200", "Fiyat < SMA200", "trend_long", lambda df: df["close"] < sma(df["close"], 200)),
    Filter("vol_confirm", "Hacim > 1,5x ort.", "volume", lambda df: _rel_volume(df) > 1.5),
    Filter("vol_quiet", "Hacim < 1x ort.", "volume", lambda df: _rel_volume(df) < 1.0),
    Filter("rsi_below_35", "RSI < 35", "rsi", lambda df: rsi(df["close"]) < 35),
    Filter("rsi_above_65", "RSI > 65", "rsi", lambda df: rsi(df["close"]) > 65),
    Filter("near_52w_high", "52h zirveye %10 yakın", "range", lambda df: df["close"] >= 0.9 * df["close"].rolling(252).max()),
    Filter("near_52w_low", "52h dibe %10 yakın", "range", lambda df: df["close"] <= 1.1 * df["close"].rolling(252).min()),
    Filter("liquid", "Günlük işlem > 50 mn TL", "liquidity", lambda df: _tl_volume(df) > 50e6),
]}


def apply_filters(signal: pd.Series, df: pd.DataFrame, filter_ids: tuple[str, ...]) -> pd.Series:
    for fid in filter_ids:
        signal = signal & FILTERS[fid].fn(df).fillna(False)
    return signal
