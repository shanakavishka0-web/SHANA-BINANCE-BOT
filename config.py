import os
from dotenv import load_dotenv

load_dotenv()

# ============ BINANCE ============
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

# ============ TELEGRAM ============
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

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
