"""Sinyal backtest'i: her sinyalden sonra N gün içinde fiyat ne yaptı?

Kurallar (bilinçli olarak basit ve dürüst):
- Sinyal t gününün kapanışında bilinir; giriş t+1 açılışından yapılır (geleceği görme yok).
- Çıkış t+h kapanışı. Getiriden gidiş-dönüş komisyon düşülür.
- Karşılaştırma ölçütü (baseline): aynı giriş/çıkış kuralıyla tüm hisselerin tüm günleri.
  Formasyonun değeri, baseline'dan farkıdır; piyasa yükselirken her sinyal "kazandırır".
- Pencere içinde günlük %30'dan büyük hareket varsa (BIST marjı ±%10) veri hatası sayılıp işlem atılır.
"""
import numpy as np
import pandas as pd

from scanners import FILTERS, SCANS, signal_for

HORIZONS = [1, 5, 10, 20]
COMMISSION = 0.002  # gidiş-dönüş ~%0,2
BAD_MOVE = 0.30
MIN_BARS = 60
SPLIT = 0.6  # dönem ayırma testi: ilk %60 / son %40


def forward_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Her bar için 'yarın açılışta al, h gün sonra kapanışta sat' getirisi (geçersizler NaN)."""
    entry = df["open"].shift(-1)
    bad = (df["close"].pct_change().abs() > BAD_MOVE).astype(float)
    out = {}
    for h in HORIZONS:
        ret = df["close"].shift(-h) / entry - 1 - COMMISSION
        bad_ahead = bad.rolling(h).max().shift(-h)
        out[h] = ret.where((bad_ahead == 0) & (entry > 0))
    return pd.DataFrame(out, index=df.index)


def _stats(rets: pd.Series, direction: str, base_mean: float) -> dict:
    rets = rets.dropna()
    n = len(rets)
    if n == 0:
        return {"n": 0}
    hit = (rets < 0) if direction == "down" else (rets > 0)
    mean = rets.mean()
    std = rets.std(ddof=1) if n > 1 else np.nan
    return {
        "n": n,
        "hit_rate": round(float(hit.mean() * 100), 1),
        "mean": round(float(mean * 100), 2),
        "median": round(float(rets.median() * 100), 2),
        "baseline": round(float(base_mean * 100), 2),
        "edge": round(float((mean - base_mean) * 100), 2),
        # Aynı gün çok sayıda hissede sinyal çıkabildiği için gözlemler bağımsız değil; t değeri iyimserdir.
        "t_stat": round(float((mean - base_mean) / (std / np.sqrt(n))), 2) if n > 1 and std > 0 else None,
    }


class Backtester:
    """Fiyat setine ait ileri getirileri bir kez hesaplar, tüm taramalar için yeniden kullanır."""

    def __init__(self, prices: dict[str, pd.DataFrame]):
        self.prices = {s: df for s, df in prices.items() if len(df) >= MIN_BARS}
        self.fwd = {s: forward_returns(df) for s, df in self.prices.items()}
        all_fwd = pd.concat(self.fwd.values())
        self.baseline = {h: all_fwd[h].mean() for h in HORIZONS}
        self.baseline_5d_by_year = all_fwd[5].groupby(all_fwd.index.year).mean().to_dict()
        dates = sorted(set().union(*(df.index for df in self.prices.values())))
        self.period = (dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d")) if dates else (None, None)
        # Aşırı uyuma karşı: farkı ilk %60 ve son %40 dönemde ayrı ayrı ölç
        self.split_date = dates[int(len(dates) * SPLIT)] if dates else None
        early = all_fwd.index < self.split_date
        self.baseline_split = {h: (all_fwd.loc[early, h].mean(), all_fwd.loc[~early, h].mean()) for h in HORIZONS}

    def stats(self, rets: pd.Series, direction: str, horizon: int) -> dict:
        st = _stats(rets, direction, self.baseline[horizon])
        if st["n"]:
            rets = rets.dropna()
            early = rets.index < self.split_date
            for key, part, base in (("edge_early", rets[early], self.baseline_split[horizon][0]),
                                    ("edge_late", rets[~early], self.baseline_split[horizon][1])):
                st[key] = round(float((part.mean() - base) * 100), 2) if len(part) >= 10 else None
            sign = {"up": 1, "down": -1, "neutral": 1}[direction]
            st["consistent"] = (st["edge_early"] is not None and st["edge_late"] is not None
                                and st["edge_early"] * sign > 0 and st["edge_late"] * sign > 0)
        return st

    def signal_returns(self, scan_id: str, filters: tuple[str, ...] = ()) -> pd.DataFrame:
        frames = []
        for s, df in self.prices.items():
            sig = signal_for(scan_id, df, filters)
            if sig.any():
                frames.append(self.fwd[s][sig].assign(symbol=s))
        return pd.concat(frames) if frames else pd.DataFrame(columns=HORIZONS + ["symbol"])

    def run(self, scan_id: str, filters: tuple[str, ...] = ()) -> dict:
        scan = SCANS[scan_id]
        rets = self.signal_returns(scan_id, filters)
        by_year = {}
        if not rets.empty:
            for year, g in rets.groupby(rets.index.year):
                by_year[int(year)] = _stats(g[5], scan.direction, self.baseline_5d_by_year[year])
        return {
            "scan": scan_id,
            "title": scan.title,
            "direction": scan.direction,
            "filters": [FILTERS[f].title for f in filters],
            "period": self.period,
            "symbols": len(self.prices),
            "commission_pct": COMMISSION * 100,
            "split_date": self.split_date.strftime("%Y-%m-%d"),
            "horizons": {h: self.stats(rets[h], scan.direction, h) for h in HORIZONS},
            "by_year_5d": by_year,
        }

    def leaderboard(self, horizon: int = 5, filters: tuple[str, ...] = ()) -> list[dict]:
        rows = []
        for scan_id, scan in SCANS.items():
            st = self.stats(self.signal_returns(scan_id, filters)[horizon], scan.direction, horizon)
            rows.append({"scan": scan_id, "title": scan.title, "category": scan.category,
                         "direction": scan.direction, **st})
        return sorted(rows, key=lambda r: _goodness(r, r["direction"]), reverse=True)

    def filter_analysis(self, scan_id: str, filters: tuple[str, ...] = (), horizon: int = 5) -> dict:
        """Mevcut filtrelere ek olarak her bir filtre eklenseydi sonuç ne olurdu?"""
        scan = SCANS[scan_id]
        used_groups = {FILTERS[f].group for f in filters}
        candidates = [f for f in FILTERS if f not in filters and FILTERS[f].group not in used_groups]
        base_parts, parts = [], {f: [] for f in candidates}
        for s, df in self.prices.items():
            sig = signal_for(scan_id, df, filters)
            if not sig.any():
                continue
            fwd = self.fwd[s][horizon]
            base_parts.append(fwd[sig])
            for f in candidates:
                parts[f].append(fwd[sig & FILTERS[f].fn(df).fillna(False)])

        def stats(p):
            return self.stats(pd.concat(p) if p else pd.Series(dtype=float), scan.direction, horizon)

        rows = [{"filter": f, "title": FILTERS[f].title, **stats(parts[f])} for f in candidates]
        rows.sort(key=lambda r: _goodness(r, scan.direction), reverse=True)
        return {"horizon": horizon, "split_date": self.split_date.strftime("%Y-%m-%d"),
                "base": stats(base_parts), "rows": rows}


def _goodness(st: dict, direction: str) -> float:
    """Beklenen yönde fark: yükselişte pozitif, düşüşte negatif fark iyidir. Küçük örneklemler sona."""
    if (st.get("n") or 0) < 30:
        return float("-inf")
    sign = {"up": 1, "down": -1, "neutral": 1}[direction]
    return (st.get("edge") or 0) * sign
