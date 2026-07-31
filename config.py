import os
from dotenv import load_dotenv

load_dotenv()

# ============ BINANCE ============
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

# ============ TELEGRAM ============
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Chat ID එක int විදියට convert කරන්න (Telegram එකට int ඕනේ)
try:
    TELEGRAM_CHAT_ID = int(TELEGRAM_CHAT_ID)
except (ValueError, TypeError):
    TELEGRAM_CHAT_ID = 0

# ============ OWNER ID ============
# OWNER_ID නැත්නම් TELEGRAM_CHAT_ID එකම use කරනවා (warning එක නවතිනවා)
OWNER_ID = os.getenv("OWNER_ID", str(TELEGRAM_CHAT_ID))
try:
    OWNER_ID = int(OWNER_ID)
except (ValueError, TypeError):
    OWNER_ID = 0

# ============ COINS ============
COINS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT", "LTCUSDT"
]

# ============ SETTINGS ============
TIMEFRAME = "1m"
ANALYSIS_INTERVAL = 120
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
VOLUME_THRESHOLD = 1.5
