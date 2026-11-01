import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def check_three_inside_up(df):
    if len(df) < 3:
        return False

    first, second, third = df.iloc[-3], df.iloc[-2], df.iloc[-1]

    if (
        first.isna().any() or
        second.isna().any() or
        third.isna().any()
    ):
        return False

    first_open = float(first['Open'])
    first_close = float(first['Close'])
    first_high = float(first['High'])
    first_low = float(first['Low'])

    second_open = float(second['Open'])
    second_close = float(second['Close'])

    third_open = float(third['Open'])
    third_close = float(third['Close'])

    # Formasyonu kontrol edin
    if (
       (first_close < first_open) and       # İlk mum düşüş olmalı
        (second_open > first_close) and (second_close < first_open) and  # İkinci mum harami
        (third_close > second_open) and (third_close > first_open) and (third_open < third_close)  # Üçüncü mum yükseliş
    ):
        return True

    return False


def get_bist_stocks():
    """Borsa İstanbul'da işlem gören bazı hisse senetlerini döndürür"""
    bist_tickers = [
        # Ana Pazar ve diğer pazarlar için bazı örnek hisseler
        "AKBNK.IS", "GARAN.IS", "THYAO.IS", "KRDMD.IS", "SISE.IS", "TUPRS.IS", "PETKM.IS",
        "YKBNK.IS", "HALKB.IS", "ISCTR.IS", "ASELS.IS", "BIMAS.IS", "KOZAA.IS", "KOZAL.IS",
        "FROTO.IS", "TOASO.IS", "SAHOL.IS", "EREGL.IS", "VESTL.IS", "HEKTS.IS", "LOGO.IS",
        "ALKIM.IS", "TCELL.IS", "AKSEN.IS", "DOHOL.IS", "SELEC.IS", "KCHOL.IS", "ARCLK.IS",
        "GOZDE.IS", "ENJSA.IS", "OTKAR.IS", "SASA.IS", "MGROS.IS", "PINSU.IS", "AGHOL.IS",
        "KORDS.IS", "TTRAK.IS", "GUBRF.IS", "CIMSA.IS", "NUHCM.IS", "ALARK.IS", "TRGYO.IS",
        "TKFEN.IS", "BRSAN.IS", "PRKME.IS", "MPARK.IS", "ISFIN.IS", "ODAS.IS", "DOAS.IS",
        "IZMDC.IS", "TAVHL.IS", "CCOLA.IS", "OZKGY.IS", "IPEKE.IS", "VERUS.IS", "KARSN.IS",
        "EGPRO.IS", "SOKM.IS", "ULKER.IS", "EGEEN.IS", "TURSG.IS", "BAGFS.IS", "AYGAZ.IS",
        "ANSGR.IS", "AVISA.IS", "EKGYO.IS", "TRCAS.IS", "OTTO.IS", "THETH.IS", "ISGYO.IS",
        "TUKAS.IS", "ARDYZ.IS", "VAKBN.IS", "PENTA.IS", "NTHOL.IS", "ESCOM.IS","A1CAP.IS", "ACSEL.IS", "ADEL.IS", "ADESE.IS", "ADGYO.IS", "AEFES.IS", "AFYON.IS",
        "AGESA.IS", "AGROT.IS", "AGYO.IS", "AHGAZ.IS", "AHSGY.IS", "AKCNS.IS", "AKENR.IS", 
        "AKFGY.IS", "AKFYE.IS", "AKGRT.IS", "AKMGY.IS", "AKSA.IS", "AKSGY.IS", "AKSUE.IS",
        "AKYHO.IS", "ALBRK.IS", "ALCAR.IS", "ALCTL.IS", "AGHOL.IS", "AGROT.IS", "AGYO.IS", "AHGAZ.IS",
        "AHSGY.IS", "AKBNK.IS", "AKCNS.IS", "AKENR.IS", "AKFGY.IS", "AKFYE.IS", "AKGRT.IS", "AKMGY.IS", "AKSA.IS",
        "AKSEN.IS", "AKSGY.IS", "AKSUE.IS", "AKYHO.IS", "ALARK.IS", "ALBRK.IS", "ALCAR.IS", "ALCTL.IS", "ALFAS.IS",
        "ALGYO.IS", "ALKA.IS", "ALKIM.IS", "ALKLC.IS", "ALMAD.IS", "ALTNY.IS", "ALVES.IS", "ANELE.IS", "ANGEN.IS",
        "ANHYT.IS", "ANSGR.IS", "ARASE.IS", "ARCLK.IS", "ARDYZ.IS", "ARENA.IS", "ARSAN.IS", "ARTMS.IS", "ARZUM.IS",
        "ASELS.IS", "ASGYO.IS", "ASTOR.IS", "ASUZU.IS", "ATAGY.IS", "ATAKP.IS", "ATATP.IS", "ATEKS.IS", "ATLAS.IS",
        "ATSYH.IS", "AVGYO.IS", "AVHOL.IS", "AVOD.IS", "AVPGY.IS", "AVTUR.IS", "AYCES.IS", "AYDEM.IS", "AYEN.IS",
        "AYES.IS", "AYGAZ.IS", "AZTEK.IS", "BAGFS.IS", "BAHKM.IS", "BAKAB.IS", "BALAT.IS", "BANVT.IS", "BARMA.IS",
        "BASCM.IS", "BASGZ.IS", "BAYRK.IS", "BEGYO.IS", "BERA.IS", "BEYAZ.IS", "BFREN.IS", "BIENY.IS", "BIGCH.IS",
        "BIMAS.IS", "BINBN.IS", "BINHO.IS", "BIOEN.IS", "BIZIM.IS", "BJKAS.IS", "BLCYT.IS", "BMSCH.IS", "BMSTL.IS",
        "BNTAS.IS", "BOBET.IS", "BORLS.IS", "BORSK.IS", "BOSSA.IS", "BRISA.IS", "BRKO.IS", "BRKSN.IS", "BRKVY.IS",
        "BRLSM.IS", "BRMEN.IS", "BRSAN.IS", "BRYAT.IS", "BSOKE.IS", "BTCIM.IS", "BUCIM.IS", "BURCE.IS", "BURVA.IS",
        "BVSAN.IS", "BYDNR.IS", "CANTE.IS", "CASA.IS", "CATES.IS", "CCOLA.IS", "CELHA.IS", "CEMAS.IS", "CEMTS.IS",
        "CEMZY.IS", "CEOEM.IS", "CIMSA.IS", "CLEBI.IS", "CMBTN.IS", "CMENT.IS", "CONSE.IS", "COSMO.IS", "CRDFA.IS",
        "CRFSA.IS", "CUSAN.IS", "CVKMD.IS", "CWENE.IS", "DAGHL.IS", "DAGI.IS", "DAPGM.IS", "DARDL.IS", "DCTTR.IS",
        "DENGE.IS", "DERHL.IS", "DERIM.IS", "DESA.IS", "DESPC.IS",
    ]
    return bist_tickers

def find_three_inside_up_stocks():
    """Three Inside Up formasyonu olan hisseleri bulur"""
    today = datetime.now().strftime('%Y-%m-%d')
    stocks = get_bist_stocks()
    three_inside_up_stocks = []

    for stock in stocks:
        # Son 10 günün verilerini çek
        df = yf.download(stock, start=(datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d'), end=today)
        
        # Veri kontrolü: DataFrame boşsa veya NaN içeriyorsa devam etme
        if df.empty or df.isna().any().any():
            continue

        # Three Inside Up formasyonunu kontrol et
        if check_three_inside_up(df):
            three_inside_up_stocks.append(stock)
    
    return three_inside_up_stocks

if __name__ == "__main__":
    result = find_three_inside_up_stocks()
    if result:
        print("Three Inside Up formasyonu görülen hisseler:", result)
    else:
        print("Bugün Three Inside Up formasyonu görülen hisse yok.")
