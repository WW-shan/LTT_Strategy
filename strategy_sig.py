import logging
import numpy as np
import os
from config import DC_PERIOD, MA_FAST, MA_MID, MA_SLOW, MA_LONG
from exchange_utils import get_turtle_data

def calculate_indicators(df):
    df['highest'] = df['high'].rolling(DC_PERIOD).max()
    df['lowest'] = df['low'].rolling(DC_PERIOD).min()
    df['mid'] = (df['highest'] + df['lowest']) / 2    
    df['ma5'] = df['close'].rolling(window=MA_FAST).mean()
    df['ma10'] = df['close'].rolling(window=MA_MID).mean()
    df['ma20'] = df['close'].rolling(window=MA_SLOW).mean()
    df['ma200'] = df['close'].rolling(window=MA_LONG).mean()  # 固定使用MA200
    
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/6, min_periods=6).mean()
    avg_loss = loss.ewm(alpha=1/6, min_periods=6).mean()
    avg_loss = avg_loss.replace(0, 1e-8)
    rs = avg_gain / avg_loss
    df['rsi6'] = 100 - (100 / (1 + rs))
    
    # 时区处理：检查是否已经有时区信息
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai')
    else:
        df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Shanghai')
    
    return df

def is_strong_uptrend(df, idx):
    if idx < MA_SLOW:
        return False
    # 防止NaN
    if any(np.isnan([df['ma5'].iloc[idx], df['ma10'].iloc[idx], df['ma20'].iloc[idx], df['close'].iloc[idx]])):
        return False
    return (
        df['ma5'].iloc[idx] > df['ma10'].iloc[idx] > df['ma20'].iloc[idx] and
        df['close'].iloc[idx] > df['ma5'].iloc[idx]
    )

def find_can_biao_xiu(df):
    try:
        can_idx = biao_idx = xiu_idx = None
        # 从后往前找参
        for i in range(len(df)-2, 0, -1):
            # 防止NaN
            if i < 1 or i >= len(df):
                continue
            if any(np.isnan([df['close'].iloc[i], df['open'].iloc[i], df['high'].iloc[i-1]])):
                continue
            # 参：阳线，最高价突破DC通道上轨，且上涨趋势
            if (
                df['close'].iloc[i] > df['open'].iloc[i] and
                df['high'].iloc[i] == df['highest'].iloc[i] and
                is_strong_uptrend(df, i)
            ):
                logging.info(f"找到参: idx={i}, close={df['close'].iloc[i]}, open={df['open'].iloc[i]}, high_pre={df['high'].iloc[i-1]}")
                can_idx = i
                break
        if can_idx is None:
            return None, None, None
        can_low = df['low'].iloc[can_idx]
        # 标：参的低点后，最高价低于参
        for j in range(can_idx+1, len(df)-1):
            if any(np.isnan([df['close'].iloc[j], df['open'].iloc[j], df['high'].iloc[j]])):
                continue
            if (
                df['close'].iloc[j] > df['open'].iloc[j] and
                df['high'].iloc[j] < can_low
            ):
                logging.info(f"找到标: idx={j}, close={df['close'].iloc[j]}, open={df['open'].iloc[j]}, high={df['high'].iloc[j]}")
                biao_idx = j
                break
        if biao_idx is None:
            return can_idx, None, None
        biao_low = df['low'].iloc[biao_idx]
        # 修：标的低点后，最高价低于标
        for k in range(biao_idx+1, len(df)-1):
            if any(np.isnan([df['close'].iloc[k], df['open'].iloc[k], df['high'].iloc[k]])):
                continue
            if (
                df['close'].iloc[k] > df['open'].iloc[k] and
                df['high'].iloc[k] < biao_low
            ):
                logging.info(f"找到修: idx={k}, close={df['close'].iloc[k]}, open={df['open'].iloc[k]}, high={df['high'].iloc[k]}")
                xiu_idx = k
                break
        return can_idx, biao_idx, xiu_idx
    except Exception as e:
        logging.error(f"find_can_biao_xiu异常: {e}", exc_info=True)
        return None, None, None

def get_last_can_signal(symbol_short):
    fname = f"tmp/last_can_signal_{symbol_short}.txt"
    if os.path.exists(fname):
        with open(fname, "r") as f:
            return f.read().strip()
    return None

def set_last_can_signal(symbol_short, can_time):
    fname = f"tmp/last_can_signal_{symbol_short}.txt"
    with open(fname, "w") as f:
        f.write(str(can_time))

def check_signal(symbol, timeframe, df, extra_signal=False):
    """
    检查并返回各种信号（除海龟交易法和参标修外的信号）
    使用Bitget数据
    """
    signals = []
    try:
        symbol_short = symbol.split('/')[0].upper()
        df = calculate_indicators(df)
        if df.empty or len(df) < 30:
            logging.warning(f"{symbol_short} {timeframe} 数据不足，跳过本次信号检测")
            return signals

        last_row = df.iloc[-1]
        if any(np.isnan([last_row.get(k, np.nan) for k in ['rsi6', 'close', 'open']])):
            logging.warning(f"RSI6 {symbol_short} {timeframe} 最后一行有NaN，跳过本次信号检测")
            return signals

        # RSI6极值
        if (last_row['rsi6'] > 95 or last_row['rsi6'] < 5):
            logging.info(f"{symbol_short} {timeframe} 检测到极值RSI6: {last_row['rsi6']}")
            signals.append({
                "type": "rsi6_extreme",
                "symbol": symbol_short,
                "timeframe": timeframe,
                "rsi6": last_row['rsi6'],
                "time": last_row['timestamp']
            })

        # 五连阴信号
        if extra_signal:
            if len(df) >= 5 and (df['close'].iloc[-5:] < df['open'].iloc[-5:]).all():
                signals.append({
                    "type": "five_down",
                    "symbol": symbol_short,
                    "timeframe": timeframe,
                    "time": last_row['timestamp'],
                    "closes": list(df['close'][-5:]),
                    "opens": list(df['open'][-5:])
                })
    except Exception as e:
        logging.error(f"{symbol} {timeframe} 检测信号异常: {e}", exc_info=True)
        return signals
    return signals

def check_can_biao_xiu_signal(symbol, timeframe):
    """
    专门检测参标修信号（使用Yahoo Finance数据获得更多历史数据）
    """
    signals = []
    if timeframe != '1d':  # 参标修只在日线检测
        return signals
        
    try:
        symbol_short = symbol.split('/')[0].upper()
        
        # 使用Yahoo Finance数据获取更多历史数据
        df = get_turtle_data(symbol, timeframe, limit=500)
        if df.empty:
            logging.debug(f"参标修 {symbol_short} {timeframe}: Yahoo Finance无数据")
            return signals
            
        df = calculate_indicators(df)
        if len(df) < 50:  # 参标修需要足够的历史数据
            logging.debug(f"参标修 {symbol_short} {timeframe}: 数据不足，需要50根K线，实际只有{len(df)}根")
            return signals

        # 搜索参标修信号
        can_idx, biao_idx, xiu_idx = find_can_biao_xiu(df)
        
        # 添加详细的搜索状态日志
        if can_idx is not None:
            can_time = str(df['timestamp'].iloc[can_idx])
            last_time = get_last_can_signal(symbol_short)
            
            if can_time != last_time:
                logging.info(f"参标修 {symbol_short} {timeframe} 检测到新信号: can_idx={can_idx}, biao_idx={biao_idx}, xiu_idx={xiu_idx}, can_time={can_time}")
                signals.append({
                    "type": "can_biao_xiu",
                    "symbol": symbol_short,
                    "timeframe": timeframe,
                    "can_idx": can_idx,
                    "biao_idx": biao_idx,
                    "xiu_idx": xiu_idx,
                    "can_time": can_time,
                    "biao_time": str(df['timestamp'].iloc[biao_idx]) if biao_idx is not None else None,
                    "xiu_time": str(df['timestamp'].iloc[xiu_idx]) if xiu_idx is not None else None,
                })
                set_last_can_signal(symbol_short, can_time)
            else:
                logging.debug(f"参标修 {symbol_short} {timeframe}: 信号已处理过 {can_time}")
        else:
            # 每10次输出一次搜索状态，避免日志过多
            import random
            if random.randint(1, 10) == 1:
                logging.debug(f"参标修 {symbol_short} {timeframe}: 暂无符合条件的参信号（需要强势突破DC通道上轨）")
                
    except Exception as e:
        logging.error(f"参标修 {symbol} {timeframe} 检测异常: {e}", exc_info=True)
        
    return signals

def check_turtle_signal(symbol, timeframe):
    """
    海龟交易法信号检测（严格只使用Yahoo Finance数据）
    """
    signals = []
    try:
        symbol_short = symbol.split('/')[0].upper()
        
        # 获取Yahoo Finance数据（支持所有时间级别）
        df = get_turtle_data(symbol, timeframe, limit=500)
        if df.empty:
            return signals
            
        df = calculate_indicators(df)
        if len(df) < 203:
            logging.debug(f"海龟交易法 {symbol_short} {timeframe} 数据不足，需要203根K线，实际只有{len(df)}根")
            return signals

        last_row = df.iloc[-2]
        prev_row = df.iloc[-3]
        
        # 检查数据完整性
        for k in ['ma200', 'mid', 'close', 'open']:
            if np.isnan(last_row[k]) or np.isnan(prev_row[k]):
                logging.warning(f"海龟交易法 {symbol_short} {timeframe} 有NaN，跳过本次信号检测")
                return signals
        
        # 海龟买入信号
        if prev_row['mid'] <= prev_row['ma200'] and last_row['mid'] > last_row['ma200']:
            if last_row['close'] > last_row['mid'] and last_row['open'] > last_row['mid']:
                logging.info(f"{symbol_short} {timeframe} 检测到海龟买入信号")
                signals.append({
                    "type": "turtle_buy",
                    "symbol": symbol_short,
                    "timeframe": timeframe,
                    "time": last_row['timestamp'],
                    "open": last_row['open'],
                    "close": last_row['close'],
                    "ma200": last_row['ma200'],
                    "mid": last_row['mid']
                })
        # 海龟卖出信号        
        elif prev_row['mid'] >= prev_row['ma200'] and last_row['mid'] < last_row['ma200']:
            if last_row['close'] < last_row['mid'] and last_row['open'] < last_row['mid']:
                logging.info(f"{symbol_short} {timeframe} 检测到海龟卖出信号")
                signals.append({
                    "type": "turtle_sell",
                    "symbol": symbol_short,
                    "timeframe": timeframe,
                    "time": last_row['timestamp'],
                    "open": last_row['open'],
                    "close": last_row['close'],
                    "ma200": last_row['ma200'],
                    "mid": last_row['mid']
                })
                
    except Exception as e:
        logging.error(f"海龟交易法 {symbol} {timeframe} 检测信号异常: {e}", exc_info=True)
        
    return signals
