import os
from dotenv import load_dotenv

load_dotenv()

# ============ BINANCE ============
BINANCE_API_KEY = os.getenv("YcOlogq4DNe36jV0XhtceL19b56bkNKgOPEUqJYCUCWgaQBNn1Bx1pP3lgT8ukqH", "")
BINANCE_SECRET_KEY = os.getenv("5VcyO8O8cwCNKAQuO1kanYaPMS5cf9EhCUGPG0Lj7XqPBReDoR4rp6ERNO6dYsVo", "")

# ============ TELEGRAM ============
TELEGRAM_BOT_TOKEN = os.getenv("8250452036:AAE00tft6EXXrd2uK92VVfGq3bkiFT5bTOA", "")
TELEGRAM_CHAT_ID = os.getenv("8250452036", "")

# ============ COINS ============
COINS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
    "MATIC/USDT", "UNI/USDT", "ATOM/USDT", "ETC/USDT", "LTC/USDT"
]

# ============ SETTINGS ============
TIMEFRAME = "1m"
ANALYSIS_INTERVAL = 120
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
VOLUME_THRESHOLD = 1.5
