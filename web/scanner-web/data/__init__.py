from pathlib import Path

DATA_DIR = Path(__file__).parent


def load_tickers() -> list[str]:
    """tickers.txt dosyasındaki sembolleri tekrarsız ve sıralı döndürür."""
    symbols = []
    for line in (DATA_DIR / "tickers.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0]
        symbols += [s.strip().upper().removesuffix(".IS") for s in line.split(",") if s.strip()]
    return list(dict.fromkeys(symbols))
