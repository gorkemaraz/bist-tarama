"""Yerel SQLite fiyat veritabanı (data/market.db)."""
import sqlite3
from datetime import datetime

import pandas as pd

from . import DATA_DIR

DB_PATH = DATA_DIR / "market.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS issues (
    symbol TEXT, date TEXT, kind TEXT, detail TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
-- Kapanışı resmi kaynak yerine saatlik veriden tahmin edilen satırlar; resmi değer gelince silinir
CREATE TABLE IF NOT EXISTS approx_closes (symbol TEXT, date TEXT, PRIMARY KEY (symbol, date));
"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    return con


def upsert_prices(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    rows = df[["symbol", "date", "open", "high", "low", "close", "volume"]].astype(object)
    rows = rows.where(pd.notna(rows), None).itertuples(index=False, name=None)
    with connect() as con:
        con.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)", list(rows))
    return len(df)


def delete_symbols(symbols: list[str]) -> None:
    with connect() as con:
        con.executemany("DELETE FROM prices WHERE symbol = ?", [(s,) for s in symbols])


def last_dates() -> dict[str, str]:
    with connect() as con:
        return dict(con.execute("SELECT symbol, MAX(date) FROM prices GROUP BY symbol"))


def load_prices(symbols: list[str] | None = None, start: str | None = None) -> dict[str, pd.DataFrame]:
    """Sembol -> tarih indeksli OHLCV DataFrame."""
    sql, params = "SELECT * FROM prices WHERE 1=1", []
    if symbols:
        sql += f" AND symbol IN ({','.join('?' * len(symbols))})"
        params += symbols
    if start:
        sql += " AND date >= ?"
        params.append(start)
    with connect() as con:
        df = pd.read_sql_query(sql + " ORDER BY symbol, date", con, params=params)
    df["date"] = pd.to_datetime(df["date"])
    return {s: g.drop(columns="symbol").set_index("date") for s, g in df.groupby("symbol")}


def approx_pairs() -> set[tuple[str, str]]:
    with connect() as con:
        return set(con.execute("SELECT symbol, date FROM approx_closes"))


def set_approx(marked: list[tuple[str, str]], cleared: list[tuple[str, str]]) -> None:
    with connect() as con:
        con.executemany("DELETE FROM approx_closes WHERE symbol = ? AND date = ?", cleared)
        con.executemany("INSERT OR IGNORE INTO approx_closes VALUES (?, ?)", marked)


def save_issues(issues: list[dict]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as con:
        con.executemany(
            "INSERT INTO issues VALUES (?,?,?,?,?)",
            [(i["symbol"], i.get("date"), i["kind"], i.get("detail", ""), now) for i in issues],
        )


def recent_issues(limit: int = 200) -> list[dict]:
    with connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM issues WHERE created_at = (SELECT MAX(created_at) FROM issues) "
            "ORDER BY kind, symbol, date LIMIT ?", (limit,),
        )
        return [dict(r) for r in rows]


def get_meta(key: str) -> str | None:
    with connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None


def set_meta(key: str, value: str) -> None:
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))


def summary() -> dict:
    with connect() as con:
        symbols, rows, latest = con.execute(
            "SELECT COUNT(DISTINCT symbol), COUNT(*), MAX(date) FROM prices").fetchone()
    return {"symbols": symbols, "rows": rows, "latest_date": latest, "last_update": get_meta("last_update")}
