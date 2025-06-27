import ccxt
import pandas as pd
import logging

exchange = ccxt.bitget({
    'options': {'defaultType': 'swap'},
})

def get_data(symbol, timeframe, limit=200, retry=2):
    logging.debug(f"{symbol} {timeframe} 获取K线数据 limit={limit}")
    for _ in range(retry):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv or len(ohlcv) == 0:
                return pd.DataFrame()
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            logging.debug(f"{symbol} {timeframe} K线数据获取成功, 数据量: {len(df)}")
            return df
        except Exception as e:
            logging.error(f"{symbol} {timeframe} 获取K线数据失败: {e}")
    return pd.DataFrame()

def get_all_usdt_swap_symbols():
    markets = exchange.load_markets()
    symbols = [
        m for m in markets
        if markets[m]['type'] == 'swap'
        and markets[m]['active']
        and ('USDT' in m and ':' in m)
    ]
    return symbols