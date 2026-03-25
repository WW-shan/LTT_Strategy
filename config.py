import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DATA_DIR = os.path.join(BASE_DIR, 'data')
DATA_DIR = os.getenv('DATA_DIR', _DEFAULT_DATA_DIR)
TMP_DIR = os.path.join(DATA_DIR, 'tmp')
ALLOWED_USERS_FILE = os.path.join(DATA_DIR, 'allowed_users.txt')
USER_SETTINGS_FILE = os.path.join(DATA_DIR, 'user_settings.json')
LOG_FILE = os.path.join(DATA_DIR, 'strategy.log')

LOGLEVEL = os.getenv('LOGLEVEL', 'INFO').upper()
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')
SYMBOLS = ['BTC/USDT:USDT']
TIMEFRAMES = ['1h', '4h', '1d']
DC_PERIOD = 28
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 8))
MA_FAST = 5
MA_MID = 10
MA_SLOW = 20
MA_LONG = 200
MAX_MSG_LEN = 4096
SUBSCRIBE_PASSWORD = os.getenv('SUBSCRIBE_PASSWORD', '')
DEFAULT_USER_SETTINGS = {
    "enabled_timeframes": ["1h", "4h", "1d"],
    "enabled_signals": ["turtle_buy", "turtle_sell", "can_biao_xiu", "five_down"],
}
