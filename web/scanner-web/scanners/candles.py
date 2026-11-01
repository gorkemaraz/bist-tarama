"""Mum formasyonları. Her fonksiyon OHLCV DataFrame alır, her bar için formasyonun
o barda tamamlanıp tamamlanmadığını gösteren bool Series döndürür (tarama ve backtest ortak kullanır).

Dönüş formasyonlarında öncesinde trend şartı aranır: formasyondan önceki kapanış,
TREND_BARS bar öncesinin altında (düşüş) veya üstünde (yükseliş) olmalı.
"""
import numpy as np
import pandas as pd

TREND_BARS = 5
LONG_BODY_BARS = 10


class Candle:
    """Tek tek barlar için sık kullanılan ölçüler. c.shift(k) ile k bar öncesine bakılır."""

    def __init__(self, df: pd.DataFrame):
        self.o, self.h, self.l, self.c = df["open"], df["high"], df["low"], df["close"]
        self.body = (self.c - self.o).abs()
        self.range = (self.h - self.l).replace(0, np.nan)
        self.upper = self.h - np.maximum(self.o, self.c)
        self.lower = np.minimum(self.o, self.c) - self.l
        self.bull = self.c > self.o
        self.bear = self.c < self.o
        self.long_body = self.body > self.body.rolling(LONG_BODY_BARS).mean()

    def downtrend_before(self, k: int) -> pd.Series:
        """k bar önce başlayan formasyondan önce düşüş trendi var mı."""
        return self.c.shift(k + 1) < self.c.shift(k + 1 + TREND_BARS)

    def uptrend_before(self, k: int) -> pd.Series:
        return self.c.shift(k + 1) > self.c.shift(k + 1 + TREND_BARS)


def S(s: pd.Series, k: int) -> pd.Series:
    return s.shift(k)


def three_inside_up(df):
    """1: uzun kırmızı, 2: birincinin gövdesi içinde yeşil (harami), 3: birincinin açılışının üstünde kapanan yeşil."""
    x = Candle(df)
    o1, c1, o2, c2 = S(x.o, 2), S(x.c, 2), S(x.o, 1), S(x.c, 1)
    return (
        x.downtrend_before(2)
        & S(x.bear, 2) & S(x.long_body, 2)
        & S(x.bull, 1) & (o2 >= c1) & (c2 <= o1) & (S(x.body, 1) < S(x.body, 2))
        & x.bull & (x.c > o1)
    )


def three_inside_down(df):
    x = Candle(df)
    o1, c1, o2, c2 = S(x.o, 2), S(x.c, 2), S(x.o, 1), S(x.c, 1)
    return (
        x.uptrend_before(2)
        & S(x.bull, 2) & S(x.long_body, 2)
        & S(x.bear, 1) & (o2 <= c1) & (c2 >= o1) & (S(x.body, 1) < S(x.body, 2))
        & x.bear & (x.c < o1)
    )


def bullish_engulfing(df):
    x = Candle(df)
    return (
        x.downtrend_before(1)
        & S(x.bear, 1) & x.bull
        & (x.o <= S(x.c, 1)) & (x.c >= S(x.o, 1)) & (x.body > S(x.body, 1))
    )


def bearish_engulfing(df):
    x = Candle(df)
    return (
        x.uptrend_before(1)
        & S(x.bull, 1) & x.bear
        & (x.o >= S(x.c, 1)) & (x.c <= S(x.o, 1)) & (x.body > S(x.body, 1))
    )


def hammer(df):
    """Düşüş sonrası: küçük gövde üstte, alt gölge gövdenin en az 2 katı, üst gölge çok kısa."""
    x = Candle(df)
    return (
        x.downtrend_before(0)
        & (x.body <= 0.35 * x.range) & (x.lower >= 2 * x.body) & (x.upper <= 0.1 * x.range)
    )


def shooting_star(df):
    x = Candle(df)
    return (
        x.uptrend_before(0)
        & (x.body <= 0.35 * x.range) & (x.upper >= 2 * x.body) & (x.lower <= 0.1 * x.range)
    )


def doji(df):
    x = Candle(df)
    return x.body <= 0.1 * x.range


def spinning_top(df):
    """Küçük gövde (aralığın %10-30'u), iki gölge de gövdeden uzun. Doji'den ayrı tutulur."""
    x = Candle(df)
    return (
        (x.body > 0.1 * x.range) & (x.body <= 0.3 * x.range)
        & (x.upper > x.body) & (x.lower > x.body)
    )


def morning_star(df):
    """1: uzun kırmızı, 2: birincinin kapanışının altında küçük gövde, 3: birincinin gövde ortasının üstünde kapanan yeşil."""
    x = Candle(df)
    return (
        x.downtrend_before(2)
        & S(x.bear, 2) & S(x.long_body, 2)
        & (S(x.body, 1) <= 0.3 * S(x.body, 2)) & (np.minimum(S(x.o, 1), S(x.c, 1)) < S(x.c, 2))
        & x.bull & (x.c > (S(x.o, 2) + S(x.c, 2)) / 2)
    )


def evening_star(df):
    x = Candle(df)
    return (
        x.uptrend_before(2)
        & S(x.bull, 2) & S(x.long_body, 2)
        & (S(x.body, 1) <= 0.3 * S(x.body, 2)) & (np.maximum(S(x.o, 1), S(x.c, 1)) > S(x.c, 2))
        & x.bear & (x.c < (S(x.o, 2) + S(x.c, 2)) / 2)
    )
