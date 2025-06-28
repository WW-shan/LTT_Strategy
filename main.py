import logging
import schedule
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from config import LOGLEVEL, TIMEFRAMES, MAX_WORKERS, DC_PERIOD, SYMBOLS, MA_LONG, USER_SETTINGS_FILE
from exchange_utils import get_data, get_all_usdt_swap_symbols
from strategy_sig import check_signal
from notifier import monitor_new_users, send_telegram_message, set_bot_commands, rsi6_summary, handle_signals
from utils import ensure_dir_exists, ensure_file_exists

logging.basicConfig(
    level=getattr(logging, LOGLEVEL),
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("strategy.log"),
        logging.StreamHandler()
    ]
)

if __name__ == "__main__":
    ensure_dir_exists("tmp")
    ensure_file_exists("allowed_users.txt")
    ensure_file_exists(USER_SETTINGS_FILE)
    threading.Thread(target=monitor_new_users, daemon=True).start()

def job():
    all_symbols = get_all_usdt_swap_symbols()
    rsi6_signals = []
    df_cache = {}

    def fetch_data(symbol, timeframe):
        limit = max(DC_PERIOD, MA_LONG, 500)
        df = get_data(symbol, timeframe, limit)
        return symbol, timeframe, df

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(fetch_data, symbol, timeframe)
            for symbol in all_symbols
            for timeframe in TIMEFRAMES
        ]

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
                    handle_signals(sig, rsi6_signals=rsi6_signals)

            except Exception as e:
                logging.error(f"处理{symbol} {timeframe}异常: {e}", exc_info=True)
    if rsi6_signals:
        rsi6_summary(rsi6_signals)

set_bot_commands()
logging.info("策略开始")
send_telegram_message("策略开始")
schedule.every(60).minutes.do(job)
job()
while True:
    schedule.run_pending()
    time.sleep(0.1)
