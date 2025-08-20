import ccxt
import pandas as pd
import logging
import yfinance as yf
import time

# 使用bitget作为主要交易所数据源
exchange = ccxt.bitget({
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True,
    'timeout': 30000,       # 30秒超时
    'rateLimit': 200,       # 200ms请求间隔
    'retries': 3,           # 重试次数
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

def get_bitget_data(symbol, timeframe, limit=500, retry_count=5):
    """从Bitget获取数据（用于其他指标）"""
    # 对主要币种使用更长的延迟和更多重试
    is_major_coin = symbol in ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT']
    if is_major_coin:
        retry_count = max(retry_count, 5)  # 主要币种至少重试5次
    
    for attempt in range(retry_count):
        try:
            # 主要币种在重试前添加额外延迟
            if is_major_coin and attempt > 0:
                extra_delay = 1 + (attempt * 0.5)  # 额外延迟0.5-2秒
                logging.debug(f"主要币种 {symbol} 重试前额外等待 {extra_delay:.1f}s")
                time.sleep(extra_delay)
            
            logging.debug(f"从Bitget获取 {symbol} {timeframe} 数据 (尝试 {attempt + 1}/{retry_count})")
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            if not ohlcv or len(ohlcv) == 0:
                if attempt < retry_count - 1:
                    logging.warning(f"{symbol} {timeframe} 返回空数据，将重试")
                    time.sleep(1 + attempt)
                    continue
                return pd.DataFrame()
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            logging.debug(f"Bitget {symbol} {timeframe} 获取成功，数据量: {len(df)}")
            return df
            
        except ccxt.NetworkError as e:
            base_delay = 2 ** attempt
            if is_major_coin:
                base_delay *= 1.5  # 主要币种延迟更长
            
            logging.warning(f"Bitget网络错误 {symbol} {timeframe} (尝试 {attempt + 1}/{retry_count}): {e}")
            if attempt < retry_count - 1:
                logging.info(f"等待 {base_delay:.1f}s 后重试...")
                time.sleep(base_delay)
                continue
            else:
                logging.error(f"Bitget获取 {symbol} {timeframe} 最终失败: 网络连接问题")
                return pd.DataFrame()
        except ccxt.ExchangeError as e:
            logging.warning(f"Bitget交易所错误 {symbol} {timeframe}: {e}")
            if attempt < retry_count - 1 and "rate limit" in str(e).lower():
                time.sleep(3 + attempt)  # 限流错误等待更久
                continue
            return pd.DataFrame()
        except Exception as e:
            logging.error(f"Bitget获取 {symbol} {timeframe} 数据失败: {e}")
            if attempt < retry_count - 1:
                time.sleep(2 ** attempt)
                continue
            else:
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

def test_exchange_connection():
    """测试交易所连接状态"""
    try:
        logging.info("测试 Bitget 连接...")
        # 尝试获取服务器时间，这是最轻量的API调用
        server_time = exchange.fetch_time()
        if server_time:
            logging.info(f"Bitget 连接正常，服务器时间: {server_time}")
            return True
        else:
            logging.warning("Bitget 连接异常: 无法获取服务器时间")
            return False
    except ccxt.NetworkError as e:
        logging.error(f"Bitget 网络连接失败: {e}")
        return False
    except Exception as e:
        logging.error(f"Bitget 连接测试失败: {e}")
        return False

def warmup_connection():
    """预热连接，避免主要币种获取数据时的冷启动问题"""
    try:
        logging.info("正在预热Bitget连接...")
        # 先测试连接
        if not test_exchange_connection():
            logging.warning("连接预热失败，但程序将继续运行")
            return False
        
        # 获取少量数据预热API连接
        test_symbol = 'DOGE/USDT:USDT'  # 使用小币种预热避免冲突
        logging.info(f"使用 {test_symbol} 预热API连接...")
        df = get_bitget_data(test_symbol, '1h', 5, retry_count=2)
        
        if not df.empty:
            logging.info("连接预热成功")
            time.sleep(1)  # 预热后等待一下
            return True
        else:
            logging.warning("连接预热部分失败，但程序将继续运行")
            return False
            
    except Exception as e:
        logging.error(f"连接预热异常: {e}")
        return False

def get_all_usdt_swap_symbols():
    """获取所有USDT永续合约交易对，主要币种排在后面以避免并发冲突"""
    try:
        markets = exchange.load_markets()
        symbols = [
            m for m in markets
            if markets[m]['type'] == 'swap'
            and markets[m]['active']
            and ('USDT' in m and ':' in m)
        ]
        
        # 将主要币种移到列表后面，避免并发时的冲突
        major_coins = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT']
        other_symbols = [s for s in symbols if s not in major_coins]
        major_symbols = [s for s in symbols if s in major_coins]
        
        # 重新排序：其他币种在前，主要币种在后
        reordered_symbols = other_symbols + major_symbols
        
        logging.info(f"从Bitget获取到 {len(symbols)} 个USDT永续合约交易对")
        logging.info(f"主要币种 {major_symbols} 已重排序到列表后部")
        return reordered_symbols
        
    except ccxt.NetworkError as e:
        logging.error(f"获取交易对失败 - 网络错误: {e}")
        # 返回默认的主要交易对
        return ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'ADA/USDT:USDT', 'SOL/USDT:USDT']
    except Exception as e:
        logging.error(f"获取交易对失败: {e}")
        # 返回默认的主要交易对
        return ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'ADA/USDT:USDT', 'SOL/USDT:USDT']