import os

LOGLEVEL = os.getenv('LOGLEVEL', 'INFO').upper()
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')
SYMBOLS = ['BTC/USDT:USDT']
TIMEFRAMES = ['1h', '4h', '1d']
DC_PERIOD = 28
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 10))
MA_FAST = 5
MA_MID = 10
MA_SLOW = 20
MA_LONG = 200
MAX_MSG_LEN = 4096
SUBSCRIBE_PASSWORD = os.getenv('SUBSCRIBE_PASSWORD', '')
USER_SETTINGS_FILE = "user_settings.json"
DEFAULT_USER_SETTINGS = {
    "enabled_timeframes": ["1h", "4h", "1d"],  # 默认全部启用
    "enabled_signals": ["turtle_buy", "turtle_sell", "can_biao_xiu", "five_down"]
}
