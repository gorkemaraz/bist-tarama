"""Veri güncelleme. Komut satırından:

    python -m data.update              # artımlı güncelleme (yeni semboller için 5 yıllık geçmiş)
    python -m data.update --full       # tüm geçmişi baştan indir
    python -m data.update THYAO ASELS  # sadece belirli semboller
"""
import argparse
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from . import load_tickers, store
from .quality import reconcile
from .sources import fetch_isyatirim, fetch_yahoo, fetch_yahoo_last_close

ISTANBUL = ZoneInfo("Europe/Istanbul")
SESSION_CLOSE = time(18, 15)  # kapanış seansı sonrası mum kesinleşmiş sayılır
OVERLAP_DAYS = 10             # artımlı güncellemede geriye dönük tekrar çekilen gün
VALIDATE_DAYS = 20            # İş Yatırım ile karşılaştırılan son gün sayısı
VALIDATE_SAMPLE = 25          # her güncellemede ayrıca karşılaştırılan sembol sayısı (dönüşümlü)
MAX_GAP_DAYS = 60             # bundan eski verisi olan sembol baştan indirilir
RESTATE_TOLERANCE = 0.01


def find_restated(fresh: pd.DataFrame, symbols: list[str], start: date) -> list[str]:
    """Geçmiş fiyatı değişmiş (bedelsiz/bölünme sonrası yeniden düzeltilmiş) sembolleri bulur."""
    stored = store.load_prices(symbols, start=start.isoformat())
    restated = []
    for s, g in fresh.groupby("symbol"):
        if s not in stored:
            continue
        old = stored[s]["close"]
        new = g.assign(date=pd.to_datetime(g["date"])).set_index("date")["close"]
        both = pd.concat([old, new], axis=1, keys=["old", "new"]).dropna()
        if ((both["old"] - both["new"]).abs() / both["old"] > RESTATE_TOLERANCE).any():
            restated.append(s)
    return restated


def keep_stored_closes(yahoo: pd.DataFrame) -> None:
    """Yahoo kapanışı boş gelen satırlarda daha önce kaydedilmiş resmi (ör. İş Yatırım) kapanışı korur.
    Yaklaşık kapanışlar korunmaz; resmi değer için yeniden denenir."""
    gaps = yahoo[yahoo["close"].isna()]
    if gaps.empty:
        return
    approx = store.approx_pairs()
    stored = store.load_prices(sorted(set(gaps["symbol"])), start=gaps["date"].min())
    for idx, s, d in zip(gaps.index, gaps["symbol"], gaps["date"]):
        df = stored.get(s)
        ts = pd.Timestamp(d)
        if (s, d) in approx:
            continue
        if df is not None and ts in df.index and pd.notna(df.at[ts, "close"]):
            yahoo.loc[idx, ["close", "high", "low"]] = df.loc[ts, ["close", "high", "low"]].to_numpy()


def validation_targets(yahoo: pd.DataFrame, symbols: list[str], today: date) -> list[str]:
    """İş Yatırım'a sorulacak semboller: kapanışı eksik olanlar + günlük dönen bir örneklem."""
    missing = sorted(set(yahoo.loc[yahoo["close"].isna(), "symbol"]))
    if len(symbols) <= VALIDATE_SAMPLE:
        sample = symbols
    else:
        offset = (today.toordinal() * VALIDATE_SAMPLE) % len(symbols)
        sample = (symbols + symbols)[offset:offset + VALIDATE_SAMPLE]
    # Süre bütçesi dolarsa önce eksik kapanışlar alınmış olsun
    return missing + [s for s in sample if s not in missing]


def fill_approx_closes(yahoo: pd.DataFrame, isy: pd.DataFrame, log) -> list[dict]:
    """İş Yatırım'dan da gelmeyen boş kapanışları Yahoo saatlik verisiyle doldurur (yerinde değiştirir)."""
    covered = set(zip(isy["symbol"], isy["date"]))
    gaps = yahoo[yahoo["close"].isna() & ~pd.Series(list(zip(yahoo["symbol"], yahoo["date"])), index=yahoo.index).isin(covered)]
    issues = []
    for day, g in gaps.groupby("date"):
        log(f"{day} için {len(g)} sembolün kapanışı saatlik veriden tahmin ediliyor...")
        closes = fetch_yahoo_last_close(list(g["symbol"]), day)
        for idx, s in zip(g.index, g["symbol"]):
            if s in closes:
                yahoo.loc[idx, "close"] = closes[s]
                issues.append({"symbol": s, "date": day, "kind": "close_approx",
                               "detail": f"Kapanış saatlik veriden alındı: {closes[s]:.2f} (resmi kapanıştan biraz farklı olabilir)"})
    return issues


def update(symbols: list[str] | None = None, years: int = 5, full: bool = False, log=print) -> dict:
    symbols = symbols or load_tickers()
    now = datetime.now(ISTANBUL)
    today = now.date()
    history_start = today - timedelta(days=365 * years)

    last = {} if full else store.last_dates()
    cutoff = (today - timedelta(days=MAX_GAP_DAYS)).isoformat()
    fresh_syms = [s for s in symbols if last.get(s, "") >= cutoff]
    backfill = [s for s in symbols if s not in fresh_syms]
    if full:
        store.delete_symbols(symbols)

    frames = []
    if fresh_syms:
        start = date.fromisoformat(min(last[s] for s in fresh_syms)) - timedelta(days=OVERLAP_DAYS)
        log(f"{len(fresh_syms)} sembol güncelleniyor ({start} sonrası)...")
        inc = fetch_yahoo(fresh_syms, start)
        restated = find_restated(inc, fresh_syms, start)
        if restated:
            log(f"Geçmiş fiyatı değişen {len(restated)} sembol baştan indirilecek: {', '.join(restated)}")
            store.delete_symbols(restated)
            inc = inc[~inc["symbol"].isin(restated)]
            backfill += restated
        frames.append(inc)
    if backfill:
        log(f"{len(backfill)} sembol için {years} yıllık geçmiş indiriliyor...")
        frames.append(fetch_yahoo(backfill, history_start))

    yahoo = pd.concat(frames, ignore_index=True)
    if today.weekday() < 5 and now.time() < SESSION_CLOSE:
        yahoo = yahoo[yahoo["date"] != today.isoformat()]  # seans sürüyor, bugünün mumu kesin değil

    keep_stored_closes(yahoo)
    found = set(yahoo["symbol"])
    issues = [{"symbol": s, "kind": "no_data", "detail": "Yahoo'dan veri gelmedi (sembol değişmiş/kapanmış olabilir)"}
              for s in symbols if s not in found and s not in last]

    validate_from = today - timedelta(days=VALIDATE_DAYS)
    to_check = validation_targets(yahoo, sorted(found), today)
    log(f"İş Yatırım ile karşılaştırılıyor ({len(to_check)} sembol)...")
    isy = fetch_isyatirim(to_check, validate_from)
    issues += fill_approx_closes(yahoo, isy, log)
    clean, quality_issues = reconcile(yahoo, isy, validate_from.isoformat())
    issues += quality_issues

    written = store.upsert_prices(clean)
    marked = [(i["symbol"], i["date"]) for i in issues if i["kind"] == "close_approx"]
    store.set_approx(marked, cleared=list(set(zip(clean["symbol"], clean["date"])) - set(marked)))
    store.save_issues(issues)
    store.set_meta("last_update", now.isoformat(timespec="seconds"))

    counts = pd.Series([i["kind"] for i in issues]).value_counts().to_dict() if issues else {}
    log(f"Bitti: {written} satır yazıldı, {len(found)} sembol. Uyarılar: {counts or 'yok'}")
    return {"rows": written, "symbols": len(found), "issues": counts}


def main():
    p = argparse.ArgumentParser(description="BIST fiyat verisini güncelle")
    p.add_argument("symbols", nargs="*", help="Sadece bu semboller (varsayılan: tickers.txt)")
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--full", action="store_true", help="Geçmişi baştan indir")
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    update([s.upper() for s in args.symbols] or None, years=args.years, full=args.full)


if __name__ == "__main__":
    main()
