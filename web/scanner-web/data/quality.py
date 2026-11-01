"""Veri kalite kontrolü: Yahoo verisini İş Yatırım ile karşılaştırır, eksikleri doldurur, şüpheli satırları raporlar."""
import pandas as pd

# BIST günlük fiyat marjı ±%10. Bunun üzerindeki kapanış değişimi genelde düzeltilmemiş
# bedelsiz/bölünme ya da hatalı veri demektir.
DAILY_LIMIT = 0.105
MISMATCH_TOLERANCE = 0.02


def _issue(row, kind, detail=""):
    return {"symbol": row.symbol, "date": row.date, "kind": kind, "detail": detail}


def reconcile(yahoo: pd.DataFrame, isy: pd.DataFrame, compare_from: str) -> tuple[pd.DataFrame, list[dict]]:
    issues = []
    m = yahoo.merge(
        isy[["symbol", "date", "high", "low", "close"]], on=["symbol", "date"],
        how="left", suffixes=("", "_isy"),
    )

    # Yahoo kapanışı boşsa İş Yatırım'dan tamamla
    fill = m["close"].isna() & m["close_isy"].notna()
    for r in m[fill].itertuples():
        issues.append(_issue(r, "close_filled", f"Kapanış İş Yatırım'dan alındı: {r.close_isy:.2f}"))
    m.loc[fill, "close"] = m.loc[fill, "close_isy"]
    m.loc[fill, "high"] = m.loc[fill, ["high", "high_isy"]].max(axis=1)
    m.loc[fill, "low"] = m.loc[fill, ["low", "low_isy"]].min(axis=1)

    # İki kaynak arasında fark (yalnızca yakın dönem; eski tarihlerde temettü düzeltmesi farkı olağan)
    diff = (m["close"] - m["close_isy"]).abs() / m["close_isy"]
    bad = (m["date"] >= compare_from) & ~fill & (diff > MISMATCH_TOLERANCE)
    for r in m[bad].itertuples():
        issues.append(_issue(r, "source_mismatch", f"Yahoo {r.close:.2f} / İş Yatırım {r.close_isy:.2f}"))

    # Kapanışı hâlâ olmayan veya hiç işlem görmemiş (hayalet) satırları at
    phantom = (m["volume"].fillna(0) == 0) & (m["high"] == m["low"])
    no_close = m["close"].isna()
    for r in m[no_close].itertuples():
        issues.append(_issue(r, "no_close", "Kapanış verisi yok, satır atlandı"))
    m = m[~no_close & ~phantom]

    # OHLC tutarlılığı
    body_hi = m[["open", "close"]].max(axis=1)
    body_lo = m[["open", "close"]].min(axis=1)
    broken = (m["high"] < body_hi - 1e-6) | (m["low"] > body_lo + 1e-6)
    for r in m[broken].itertuples():
        issues.append(_issue(r, "ohlc_inconsistent", f"O {r.open:.2f} H {r.high:.2f} L {r.low:.2f} C {r.close:.2f}"))
    m.loc[broken, "high"] = pd.concat([m.loc[broken, "high"], body_hi[broken]], axis=1).max(axis=1)
    m.loc[broken, "low"] = pd.concat([m.loc[broken, "low"], body_lo[broken]], axis=1).min(axis=1)

    # Fiyat marjını aşan hareketler
    m = m.sort_values(["symbol", "date"])
    change = m.groupby("symbol")["close"].pct_change()
    for r, ch in zip(m[change.abs() > DAILY_LIMIT].itertuples(), change[change.abs() > DAILY_LIMIT]):
        issues.append(_issue(r, "limit_exceeded", f"Günlük değişim %{ch * 100:.1f} (bedelsiz/bölünme düzeltmesi olabilir)"))

    return m[["symbol", "date", "open", "high", "low", "close", "volume"]].reset_index(drop=True), issues
