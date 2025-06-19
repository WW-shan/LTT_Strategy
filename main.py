import logging
import os
import schedule
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from config import LOGLEVEL, TIMEFRAMES, MAX_WORKERS, DC_PERIOD, SYMBOLS, MA_LONG, MAX_MSG_LEN
from exchange_utils import get_data, get_all_usdt_swap_symbols
from signal import check_signal
from notifier import send_to_allowed_users, monitor_new_users, send_telegram_message, set_bot_commands
logging.basicConfig(
    level=getattr(logging, LOGLEVEL),
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("tmp/strategy.log"),
        logging.StreamHandler()
    ]
)

def ensure_dir_exists(directory):
    """确保目录存在，不存在则创建"""
    os.makedirs(directory, exist_ok=True)

def ensure_file_exists(file_path):
    """确保文件存在，不存在则创建空文件"""
    if not os.path.exists(file_path):
        parent_dir = os.path.dirname(file_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            pass

if __name__ == "__main__":
    ensure_dir_exists("tmp")
    ensure_file_exists("allowed_users.txt")

threading.Thread(target=monitor_new_users, daemon=True).start()

def send_long_telegram_message(text):
    for i in range(0, len(text), MAX_MSG_LEN):
        send_to_allowed_users(text[i:i+MAX_MSG_LEN])

def job():
    all_symbols = get_all_usdt_swap_symbols()
    rsi6_signals = []
    can_biao_xiu_signals = []
    df_cache = {}

    def fetch_data(symbol, timeframe):
        limit = max(DC_PERIOD, MA_LONG, 500)
        df = get_data(symbol, timeframe, limit)
        return symbol, timeframe, df

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_data, symbol, timeframe) for symbol in all_symbols for timeframe in TIMEFRAMES]

        for future in as_completed(futures):
            try:
                symbol, timeframe, df = future.result()
                if df.empty:
                    logging.warning(f"{symbol} {timeframe} 获取数据失败或数据为空")
                    continue
                symbol_short = symbol.split('/')[0].upper()
                df_cache[(symbol_short, timeframe)] = df
                logging.info(f"{symbol} {timeframe} K线数量: {len(df)}")
                required_cols = {'timestamp', 'open', 'high', 'low', 'close', 'volume'}
                if not required_cols.issubset(df.columns):
                    logging.error(f"{symbol} {timeframe} 数据缺少必要字段: {df.columns}")
                    continue

                extra_signal = symbol in SYMBOLS
                signals = check_signal(symbol, timeframe, df, extra_signal=extra_signal)
                if not signals:
                    continue

                for sig in signals:
                    if sig["type"] == "rsi6_extreme":
                        rsi6_signals.append(sig)
                    elif sig["type"] == "can_biao_xiu":
                        can_biao_xiu_signals.append(sig)
                    else:
                        handle_signal(sig)
            except Exception as e:
                logging.error(f"处理{symbol} {timeframe}异常: {e}", exc_info=True)
    if rsi6_signals:
        rsi6_summary(rsi6_signals)
    if can_biao_xiu_signals:
        send_can_biao_xiu_signals(can_biao_xiu_signals, df_cache)

    # 汇总推送RSI6极值
def rsi6_summary(rsi6_signals):
    rsi6_signals.sort(key=lambda x: x['rsi6'], reverse=True)
    table = f"{'交易对':<18}{'周期':<7}{'RSI6':<7}\n"
    table += f"{'-'*18}{'-'*7}{'-'*7}\n"
    for s in rsi6_signals:
        table += f"{s['symbol']:<20}{s['timeframe']:<8}{s['rsi6']:<8.2f}\n"
    send_long_telegram_message(f"RSI6极值信号汇总：\n```\n{table}```")
        
    # 汇总推送参标修信号
def send_can_biao_xiu_signals(signals, df_cache):
    table = f"{'交易对':<8}{'信号':<4}{'时间':<10}\n"
    table += f"{'-'*10}{'-'*4}{'-'*16}\n"
    for sig in signals:
        df = df_cache.get((sig['symbol'], sig['timeframe']))
        if df is None:
            continue
        can_time = str(df['timestamp'].iloc[sig['can_idx']])[:10]
        table += f"{sig['symbol']:<10}{'参':<4}{can_time:<16}\n"
        if sig['biao_idx'] is not None:
            biao_time = str(df['timestamp'].iloc[sig['biao_idx']])[:10]
            table += f"{sig['symbol']:<10}{'标':<4}{biao_time:<16}\n"
        if sig['xiu_idx'] is not None:
            xiu_time = str(df['timestamp'].iloc[sig['xiu_idx']])[:10]
            table += f"{sig['symbol']:<10}{'修':<4}{xiu_time:<16}\n"
    msg = f"参的低点是标的压力位\n标的低点是修的压力位\n修的低点是最强支撑位\n\n日线级别参标修信号汇总：\n```\n{table}```"
    send_long_telegram_message(msg)

def handle_signal(sig):
    if sig["type"] == "turtle_buy":
        msg = (
            f"[海龟交易法] {sig['symbol']} {sig['timeframe']} 发现买入信号\n"
            f"时间    : {sig['time']}\n"
            f"开盘价  : {sig['open']}\n"
            f"收盘价  : {sig['close']}\n"
            f"MA200   : {sig['ma200']}\n"
            f"DC中轨  : {sig['mid']}\n"
        )
        logging.info(msg)
        send_to_allowed_users(msg)

    elif sig["type"] == "turtle_sell":
        msg = (
            f"[海龟交易法] {sig['symbol']} {sig['timeframe']} 发现卖出信号\n"
            f"时间    : {sig['time']}\n"
            f"开盘价  : {sig['open']}\n"
            f"收盘价  : {sig['close']}\n"
            f"MA200   : {sig['ma200']}\n"
            f"DC中轨  : {sig['mid']}\n"
        )
        logging.info(msg)
        send_to_allowed_users(msg)

    elif sig["type"] == "five_down":
        msg = (
            f"[五连阴] {sig['symbol']} {sig['timeframe']} 发现五连阴卖出信号\n"
            f"时间    : {sig['time']}\n"
            f"最近5根K线收盘价: {sig['closes']}\n"
            f"最近5根K线开盘价: {sig['opens']}\n"
        )
        logging.info(msg)
        send_to_allowed_users(msg)

    else:
        logging.warning(f"未知信号类型: {sig['type']}")

set_bot_commands()
logging.info("策略开始")
send_telegram_message("策略开始")
schedule.every(60).minutes.do(job)
job()
while True:
    schedule.run_pending()
    time.sleep(0.1)