import ccxt
import pandas as pd
import logging
import yfinance as yf

# 使用bitget作为主要交易所数据源
exchange = ccxt.bitget({
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True,
})

# 币种映射：交易所符号 -> Yahoo Finance符号
YAHOO_SYMBOL_MAP = {
    'BTC': 'BTC-USD',
    'ETH': 'ETH-USD',
    'BNB': 'BNB-USD',
    'ADA': 'ADA-USD',
    'SOL': 'SOL-USD',
    'XRP': 'XRP-USD',
    'DOT': 'DOT-USD',
    'DOGE': 'DOGE-USD',
    'AVAX': 'AVAX-USD',
    'SHIB': 'SHIB-USD',
    'MATIC': 'MATIC-USD',
    'LTC': 'LTC-USD',
    'LINK': 'LINK-USD',
    'UNI': 'UNI-USD',
    'ATOM': 'ATOM-USD',
    'ETC': 'ETC-USD',
    'XLM': 'XLM-USD',
    'ALGO': 'ALGO-USD',
    'VET': 'VET-USD',
    'ICP': 'ICP-USD',
}

def get_yahoo_data(symbol, limit=500):
    """从Yahoo Finance获取日线数据（专门用于海龟交易法）"""
    try:
        # 提取币种符号
        base_symbol = symbol.split('/')[0].upper()
        yahoo_symbol = YAHOO_SYMBOL_MAP.get(base_symbol)
        
        if not yahoo_symbol:
            logging.debug(f"Yahoo Finance不支持 {base_symbol}，这是正常的")
            return pd.DataFrame()
        
        logging.debug(f"从Yahoo Finance获取 {yahoo_symbol} 日线数据")
        
        # 获取2年日线数据
        ticker = yf.Ticker(yahoo_symbol)
        hist = ticker.history(period='2y', interval='1d')
        
        if hist.empty:
            return pd.DataFrame()
        
        # 转换为标准格式
        df = pd.DataFrame()
        df['timestamp'] = hist.index
        df['open'] = hist['Open'].values
        df['high'] = hist['High'].values  
        df['low'] = hist['Low'].values
        df['close'] = hist['Close'].values
        df['volume'] = hist['Volume'].values
        
        # 限制数据量
        if len(df) > limit:
            df = df.tail(limit)
        
        df = df.reset_index(drop=True)
        logging.debug(f"Yahoo Finance {yahoo_symbol} 获取成功，数据量: {len(df)}")
        return df
        
    except Exception as e:
        logging.error(f"Yahoo Finance获取 {symbol} 数据失败: {e}")
        return pd.DataFrame()

def get_bitget_data(symbol, timeframe, limit=500):
    """从Bitget获取数据（用于其他指标）"""
    try:
        logging.debug(f"从Bitget获取 {symbol} {timeframe} 数据")
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        if not ohlcv or len(ohlcv) == 0:
            return pd.DataFrame()
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        logging.debug(f"Bitget {symbol} {timeframe} 获取成功，数据量: {len(df)}")
        return df
        
    except Exception as e:
        logging.error(f"Bitget获取 {symbol} {timeframe} 数据失败: {e}")
        return pd.DataFrame()

def get_data(symbol, timeframe, limit=500, retry=2):
    """
    获取K线数据：
    - 海龟交易法：严格只使用Yahoo Finance日线数据
    - 其他指标：使用Bitget数据
    """
    # 其他指标使用Bitget数据（1h, 4h等）
    return get_bitget_data(symbol, timeframe, limit)

def get_turtle_data(symbol, timeframe, limit=500):
    """
    海龟交易法专用数据获取：严格只使用Yahoo Finance数据（所有时间级别）
    如果Yahoo Finance不支持或数据不足，返回空DataFrame
    """
    # 提取币种符号
    base_symbol = symbol.split('/')[0].upper()
    yahoo_symbol = YAHOO_SYMBOL_MAP.get(base_symbol)
    
    if not yahoo_symbol:
        logging.debug(f"海龟交易法跳过 {symbol} {timeframe}: Yahoo Finance不支持此币种")
        return pd.DataFrame()
    
    try:
        logging.debug(f"海龟交易法从Yahoo Finance获取 {yahoo_symbol} {timeframe} 数据")
        
        # 根据时间级别设置获取参数
        if timeframe == '1h':
            # 1小时需要更多数据点来满足203根K线的要求
            period = '3mo'  # 获取3个月数据（约2200小时）
            interval = '1h'
        elif timeframe == '4h':
            # 4小时需要约1年数据
            period = '1y'   # 获取1年数据（约2190个4小时）
            interval = '1h'  # Yahoo Finance没有4h间隔，需要从1h数据重采样
        elif timeframe == '1d':
            period = '2y'   # 获取2年日线数据
            interval = '1d'
        else:
            logging.warning(f"海龟交易法不支持时间级别: {timeframe}")
            return pd.DataFrame()
        
        ticker = yf.Ticker(yahoo_symbol)
        hist = ticker.history(period=period, interval=interval)
        
        if hist.empty:
            logging.warning(f"海龟交易法 {symbol} {timeframe}: Yahoo Finance返回空数据")
            return pd.DataFrame()
        
        # 转换为标准格式
        df = pd.DataFrame()
        df['timestamp'] = hist.index
        df['open'] = hist['Open'].values
        df['high'] = hist['High'].values  
        df['low'] = hist['Low'].values
        df['close'] = hist['Close'].values
        df['volume'] = hist['Volume'].values
        
        # 如果是4小时，需要重采样
        if timeframe == '4h':
            df = df.set_index('timestamp')
            df_resampled = df.resample('4h').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            df = df_resampled.reset_index()
        
        # 限制数据量
        if len(df) > limit:
            df = df.tail(limit)
        
        df = df.reset_index(drop=True)
        
        # 检查是否满足海龟交易法的最低要求
        if len(df) >= 203:
            logging.info(f"Yahoo Finance {symbol} {timeframe} 海龟交易法数据获取成功，数据量: {len(df)}")
            return df
        else:
            logging.warning(f"海龟交易法跳过 {symbol} {timeframe}: 数据不足 (仅{len(df)}根K线，需要>=203)")
            return pd.DataFrame()
        
    except Exception as e:
        logging.error(f"海龟交易法获取 {symbol} {timeframe} Yahoo Finance数据失败: {e}")
        return pd.DataFrame()

def get_all_usdt_swap_symbols():
    """获取所有USDT永续合约交易对"""
    try:
        markets = exchange.load_markets()
        symbols = [
            m for m in markets
            if markets[m]['type'] == 'swap'
            and markets[m]['active']
            and ('USDT' in m and ':' in m)
        ]
        logging.info(f"从Bitget获取到 {len(symbols)} 个USDT永续合约交易对")
        return symbols
    except Exception as e:
        logging.error(f"获取交易对失败: {e}")
        # 返回默认的主要交易对
        return ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'ADA/USDT:USDT', 'SOL/USDT:USDT']