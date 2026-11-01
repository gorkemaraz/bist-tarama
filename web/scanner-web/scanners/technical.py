"""İndikatör tabanlı sinyaller. candles.py ile aynı sözleşme: DataFrame -> bool Series."""
from .indicators import crossed_above, crossed_below, ema, macd, rsi, sma


def rsi_oversold_exit(df):
    """RSI(14) aşırı satım bölgesinden (30) yukarı çıktı."""
    return crossed_above(rsi(df["close"]), 30)


def rsi_overbought_exit(df):
    return crossed_below(rsi(df["close"]), 70)


def macd_bull_cross(df):
    line, signal = macd(df["close"])
    return crossed_above(line, signal)


def macd_bear_cross(df):
    line, signal = macd(df["close"])
    return crossed_below(line, signal)


def ema_golden_cross(df):
    """EMA20, EMA50'yi yukarı kesti."""
    return crossed_above(ema(df["close"], 20), ema(df["close"], 50))


def ema_death_cross(df):
    return crossed_below(ema(df["close"], 20), ema(df["close"], 50))


def volume_spike_up(df):
    """Hacim 20 günlük ortalamanın 2 katından fazla ve gün yükselişle kapandı."""
    avg = sma(df["volume"], 20).shift(1)
    return (df["volume"] > 2 * avg) & (df["close"] > df["close"].shift(1))


def high_52w_breakout(df):
    """Kapanış son 52 haftanın (252 bar) en yüksek kapanışını geçti."""
    return df["close"] > df["close"].rolling(252).max().shift(1)
