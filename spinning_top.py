import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def check_spinning_top(df):
    if len(df) < 1:
        return False

    # Son mum çubuğunu al
    last_candle = df.iloc[-1]

    if last_candle.isna().any():
        return False

    # Değerleri floata çevir
    open_price = float(last_candle['Open'])
    close_price = float(last_candle['Close'])
    high_price = float(last_candle['High'])
    low_price = float(last_candle['Low'])

    # Mumun gövde büyüklüğünü ve fitil uzunluklarını hesapla
    body_size = abs(close_price - open_price)
    upper_shadow = high_price - max(open_price, close_price)
    lower_shadow = min(open_price, close_price) - low_price

    # Spinning Top kriterlerini kontrol et
    if (
        body_size <= 0.1 * (high_price - low_price) and  # Gövde, toplam aralığın %10'undan küçük olmalı
        upper_shadow >= 0.3 * (high_price - low_price) and  # Üst fitil, toplam aralığın %30'undan büyük olmalı
        lower_shadow >= 0.3 * (high_price - low_price)  # Alt fitil, toplam aralığın %30'undan büyük olmalı
    ):
        return True

    return False


def get_bist_stocks():
    """Borsa İstanbul'da işlem gören bazı hisse senetlerini döndürür"""
    bist_tickers = [
        "AKBNK.IS", "GARAN.IS", "THYAO.IS", "KRDMD.IS", "SISE.IS"]
    return bist_tickers


def find_spinning_top_stocks():
    """Spinning Top formasyonu olan hisseleri bulur"""
    today = datetime.now().strftime('%Y-%m-%d')
    stocks = get_bist_stocks()
    spinning_top_stocks = []

    for stock in stocks:
        # Son 10 günün verilerini çek
        df = yf.download(stock, start=(datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d'), end=today)
        
        # Veri kontrolü: DataFrame boşsa veya NaN içeriyorsa devam etme
        if df.empty or df.isna().any().any():
            continue

        # Spinning Top formasyonunu kontrol et
        if check_spinning_top(df):
            spinning_top_stocks.append(stock)
    
    return spinning_top_stocks

if __name__ == "__main__":
    result = find_spinning_top_stocks()
    if result:
        print("Spinning Top formasyonu görülen hisseler:", result)
    else:
        print("Bugün Spinning Top formasyonu görülen hisse yok.")