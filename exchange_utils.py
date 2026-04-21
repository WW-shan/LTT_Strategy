import pandas as pd
import logging
import requests
import yfinance as yf
import time

BITGET_BASE_URL = "https://api.bitget.com"
BITGET_PRODUCT_TYPE = "USDT-FUTURES"
BITGET_TIMEFRAME_MAP = {
    '1h': '1H',
    '4h': '4H',
    '1d': '1D',
}
BITGET_CONTRACT_CACHE_TTL = 300
DEFAULT_FALLBACK_SYMBOLS = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'ADA/USDT:USDT', 'SOL/USDT:USDT']
RWA_FLAT_CANDLE_WINDOWS = {
    '1h': 6,
    '4h': 3,
    '1d': 2,
}

_contract_cache = {
    'loaded_at': 0.0,
    'contracts': {},
}

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

def _normalize_symbol(base_coin, quote_coin='USDT', settle_coin='USDT'):
    return f"{base_coin.upper()}/{quote_coin.upper()}:{settle_coin.upper()}"

def _symbol_to_market_id(symbol):
    base_coin = symbol.split('/')[0].upper()
    quote_coin = symbol.split('/')[1].split(':')[0].upper()
    return f"{base_coin}{quote_coin}"

def _bitget_get(path, params=None, timeout=30):
    response = requests.get(f"{BITGET_BASE_URL}{path}", params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if payload.get('code') != '00000':
        raise ValueError(f"Bitget API错误 {payload.get('code')}: {payload.get('msg')}")
    return payload.get('data') or []

def _load_bitget_contracts(force_refresh=False):
    cache_age = time.time() - _contract_cache['loaded_at']
    if not force_refresh and _contract_cache['contracts'] and cache_age < BITGET_CONTRACT_CACHE_TTL:
        return _contract_cache['contracts']

    raw_contracts = _bitget_get('/api/v2/mix/market/contracts', {'productType': BITGET_PRODUCT_TYPE})
    contracts = {}

    for item in raw_contracts:
        if item.get('quoteCoin') != 'USDT':
            continue
        if item.get('symbolStatus', '').lower() not in {'normal', ''}:
            continue

        symbol = _normalize_symbol(item['baseCoin'], item['quoteCoin'], 'USDT')
        contracts[symbol] = item

    _contract_cache['loaded_at'] = time.time()
    _contract_cache['contracts'] = contracts
    return contracts

def _get_contract(symbol):
    contracts = _load_bitget_contracts()
    return contracts.get(symbol)

def _is_rwa_symbol(symbol):
    contract = _get_contract(symbol)
    return bool(contract) and str(contract.get('isRwa', '')).upper() == 'YES'

def _should_skip_flat_rwa_symbol(symbol, timeframe, df):
    window = RWA_FLAT_CANDLE_WINDOWS.get(timeframe)
    if not window or len(df) < window or not _is_rwa_symbol(symbol):
        return False

    recent = df.tail(window)[['open', 'high', 'low', 'close']].round(10)
    is_flat = all(recent[col].nunique(dropna=False) == 1 for col in recent.columns)
    if is_flat:
        logging.info(f"{symbol} {timeframe} 为RWA标的，最近{window}根K线价格完全不变，跳过本次统计")
    return is_flat

def get_bitget_data(symbol, timeframe, limit=500, retry_count=5):
    """从Bitget获取数据（用于其他指标）"""
    # 对主要币种使用更长的延迟和更多重试
    is_major_coin = symbol in ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT']
    if is_major_coin:
        retry_count = max(retry_count, 5)  # 主要币种至少重试5次

    contract = None
    try:
        contract = _get_contract(symbol)
    except Exception as e:
        logging.warning(f"加载Bitget合约列表失败，将继续尝试直接抓取 {symbol}: {e}")

    if contract is None and _contract_cache['contracts']:
        logging.info(f"{symbol} 不在当前Bitget USDT永续合约列表中，跳过抓取")
        return pd.DataFrame()

    granularity = BITGET_TIMEFRAME_MAP.get(timeframe)
    if not granularity:
        logging.warning(f"Bitget不支持的时间级别: {timeframe}")
        return pd.DataFrame()

    market_id = contract['symbol'] if contract else _symbol_to_market_id(symbol)
    
    for attempt in range(retry_count):
        try:
            # 主要币种在重试前添加额外延迟
            if is_major_coin and attempt > 0:
                extra_delay = 1 + (attempt * 0.5)  # 额外延迟0.5-2秒
                logging.debug(f"主要币种 {symbol} 重试前额外等待 {extra_delay:.1f}s")
                time.sleep(extra_delay)
            
            logging.debug(f"从Bitget获取 {symbol} {timeframe} 数据 (尝试 {attempt + 1}/{retry_count})")
            ohlcv = _bitget_get(
                '/api/v2/mix/market/candles',
                {
                    'symbol': market_id,
                    'granularity': granularity,
                    'limit': limit,
                    'productType': BITGET_PRODUCT_TYPE,
                },
            )
            
            if not ohlcv or len(ohlcv) == 0:
                if attempt < retry_count - 1:
                    logging.warning(f"{symbol} {timeframe} 返回空数据，将重试")
                    time.sleep(1 + attempt)
                    continue
                return pd.DataFrame()
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'quote_volume'])
            df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp'], errors='coerce'), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].sort_values('timestamp').reset_index(drop=True)

            if _should_skip_flat_rwa_symbol(symbol, timeframe, df):
                return pd.DataFrame()

            logging.debug(f"Bitget {symbol} {timeframe} 获取成功，数据量: {len(df)}")
            return df
            
        except requests.RequestException as e:
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
        except ValueError as e:
            logging.warning(f"Bitget交易所错误 {symbol} {timeframe}: {e}")
            error_text = str(e).lower()
            if "40309" in error_text or "symbol not exist" in error_text:
                return pd.DataFrame()
            if attempt < retry_count - 1 and "rate limit" in error_text:
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

def get_data(symbol, timeframe, limit=500):
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
        contracts = _load_bitget_contracts(force_refresh=True)
        if contracts:
            logging.info(f"Bitget 连接正常，可用USDT永续合约数: {len(contracts)}")
            return True
        else:
            logging.warning("Bitget 连接异常: 无法获取合约列表")
            return False
    except requests.RequestException as e:
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
        contracts = _load_bitget_contracts(force_refresh=True)
        symbols = list(contracts.keys())
        
        # 将主要币种移到列表后面，避免并发时的冲突
        major_coins = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT']
        other_symbols = [s for s in symbols if s not in major_coins]
        major_symbols = [s for s in symbols if s in major_coins]
        
        # 重新排序：其他币种在前，主要币种在后
        reordered_symbols = other_symbols + major_symbols
        
        logging.info(f"从Bitget获取到 {len(symbols)} 个USDT永续合约交易对")
        logging.info(f"主要币种 {major_symbols} 已重排序到列表后部")
        return reordered_symbols
        
    except requests.RequestException as e:
        logging.error(f"获取交易对失败 - 网络错误: {e}")
        # 返回默认的主要交易对
        return DEFAULT_FALLBACK_SYMBOLS
    except Exception as e:
        logging.error(f"获取交易对失败: {e}")
        # 返回默认的主要交易对
        return DEFAULT_FALLBACK_SYMBOLS
