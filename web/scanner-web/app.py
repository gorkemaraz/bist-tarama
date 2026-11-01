"""Çalıştırma (web/scanner-web klasöründen):  ..\\..\\.venv\\Scripts\\uvicorn app:app --reload"""
import threading
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from backtest import HORIZONS, Backtester
from data import store
from data.update import update
from scanners import FILTERS, SCANS, run_scan, signal_for
from scanners.indicators import ema

SCAN_HISTORY_DAYS = 550  # 52 haftalık zirve ve EMA50 için yeterli geçmiş

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

_cache = {"key": None, "prices": {}}
_bt_cache = {"key": None, "bt": None}
_bt_lock = threading.Lock()
_job = {"running": False, "log": [], "error": None}


def get_prices():
    """Fiyatları bellekte tutar; veri güncellenince yeniden yükler."""
    key = store.get_meta("last_update")
    if _cache["key"] != key:
        start = (datetime.now() - timedelta(days=SCAN_HISTORY_DAYS)).strftime("%Y-%m-%d")
        _cache.update(key=key, prices=store.load_prices(start=start))
    return _cache["prices"]


def get_backtester() -> Backtester:
    """Backtest tüm geçmişi kullanır; ileri getiriler veri güncellenene kadar bellekte kalır."""
    with _bt_lock:
        key = store.get_meta("last_update")
        if _bt_cache["key"] != key:
            _bt_cache.update(key=key, bt=Backtester(store.load_prices()))
        return _bt_cache["bt"]


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/scans")
def list_scans():
    return {"scans": [
        {"id": s.id, "title": s.title, "description": s.description,
         "category": s.category, "direction": s.direction}
        for s in SCANS.values()
    ]}


def parse_filters(filters: str | list[str] | None) -> tuple[str, ...]:
    ids = [f for f in (filters.split(",") if isinstance(filters, str) else filters or []) if f]
    unknown = [f for f in ids if f not in FILTERS]
    if unknown:
        raise HTTPException(400, f"Bilinmeyen filtre: {', '.join(unknown)}")
    return tuple(dict.fromkeys(ids))


@app.get("/api/filters")
def list_filters():
    return {"filters": [{"id": f.id, "title": f.title, "group": f.group} for f in FILTERS.values()]}


class RunParams(BaseModel):
    days: int = 1
    filters: list[str] = []


@app.post("/api/run/{scan_id}")
def run(scan_id: str, params: RunParams = RunParams()):
    if scan_id not in SCANS:
        raise HTTPException(404, "Tarama bulunamadı")
    prices = get_prices()
    if not prices:
        raise HTTPException(409, "Veri yok. Önce 'Veriyi Güncelle' ile veri indir.")
    results = run_scan(scan_id, prices, days=max(1, min(params.days, 20)), filters=parse_filters(params.filters))
    return {"scan": scan_id, "count": len(results), "results": results}


@app.get("/api/chart/{symbol}")
def chart(symbol: str, scan_id: str | None = None, filters: str = "", bars: int = 250):
    prices = store.load_prices([symbol.upper()])
    if not prices:
        raise HTTPException(404, "Sembol bulunamadı")
    df = next(iter(prices.values()))
    signal = signal_for(scan_id, df, parse_filters(filters)) if scan_id in SCANS else None
    e20, e50 = ema(df["close"], 20), ema(df["close"], 50)

    view = df.iloc[-bars:]
    t = view.index.strftime("%Y-%m-%d")
    return {
        "symbol": symbol.upper(),
        "candles": [{"time": d, "open": o, "high": h, "low": l, "close": c}
                    for d, o, h, l, c in zip(t, view["open"], view["high"], view["low"], view["close"])],
        "volume": [{"time": d, "value": v, "up": bool(c >= o)}
                   for d, v, o, c in zip(t, view["volume"].fillna(0), view["open"], view["close"])],
        "ema20": [{"time": d, "value": round(v, 4)} for d, v in zip(t, e20.iloc[-bars:])],
        "ema50": [{"time": d, "value": round(v, 4)} for d, v in zip(t, e50.iloc[-bars:])],
        "signals": [d for d in t[signal.iloc[-bars:].to_numpy()]] if signal is not None else [],
        "direction": SCANS[scan_id].direction if scan_id in SCANS else None,
    }


@app.get("/api/backtest")
def backtest_leaderboard(horizon: int = 5, filters: str = ""):
    if horizon not in HORIZONS:
        raise HTTPException(400, f"Vade şunlardan biri olmalı: {HORIZONS}")
    bt = get_backtester()
    return {"horizon": horizon, "period": bt.period, "symbols": len(bt.prices),
            "split_date": bt.split_date.strftime("%Y-%m-%d"),
            "rows": bt.leaderboard(horizon, parse_filters(filters))}


@app.get("/api/backtest/{scan_id}")
def backtest_scan(scan_id: str, filters: str = ""):
    if scan_id not in SCANS:
        raise HTTPException(404, "Tarama bulunamadı")
    return get_backtester().run(scan_id, parse_filters(filters))


@app.get("/api/backtest/{scan_id}/filters")
def backtest_filter_analysis(scan_id: str, filters: str = "", horizon: int = 5):
    if scan_id not in SCANS:
        raise HTTPException(404, "Tarama bulunamadı")
    if horizon not in HORIZONS:
        raise HTTPException(400, f"Vade şunlardan biri olmalı: {HORIZONS}")
    return get_backtester().filter_analysis(scan_id, parse_filters(filters), horizon)


@app.get("/api/status")
def status():
    return {**store.summary(), "job": _job}


@app.post("/api/update")
def start_update():
    if _job["running"]:
        return {"started": False}

    def work():
        try:
            update(log=_job["log"].append)
        except Exception as e:
            _job["error"] = str(e)
        finally:
            _job["running"] = False

    _job.update(running=True, log=[], error=None)
    threading.Thread(target=work, daemon=True).start()
    return {"started": True}


@app.get("/api/issues")
def issues():
    return {"issues": store.recent_issues()}
