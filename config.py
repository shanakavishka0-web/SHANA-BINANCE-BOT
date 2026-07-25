import os
from dotenv import load_dotenv

load_dotenv()

# බයිනැන්ස් API (Read-only ඇපි කී එකක් හදාගන්න)
BINANCE_API_KEY = os.getenv("YcOlogq4DNe36jV0XhtceL19b56bkNKgOPEUqJYCUCWgaQBNn1Bx1pP3lgT8ukqH")
BINANCE_SECRET_KEY = os.getenv("5VcyO8O8cwCNKAQuO1kanYaPMS5cf9EhCUGPG0Lj7XqPBReDoR4rp6ERNO6dYsVo")

# ටෙලිග්‍රෑම් බොට්
TELEGRAM_BOT_TOKEN = os.getenv("8250452036:AAE00tft6EXXrd2uK92VVfGq3bkiFT5bTOA")
TELEGRAM_CHAT_ID = os.getenv("8250452036")

# ඇනලයිස් කරන්න කොයින් ලිස්ට් එක
COINS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT", "LTCUSDT"
]

# TIME FRAMES
TIMEFRAME = "1m"        # 1-minute chart
ANALYSIS_INTERVAL = 120  # තත්පර 120කට (විනාඩි 2) වරක් ඇනලයිස් කරන්න
SIGNAL_CONFIRM_BARS = 3 # පුල් බැක් එක කන්ෆර්ම් කරන්න bars 3ක් බලන්න

# Signal thresholds
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
VOLUME_THRESHOLD = 1.5  # average එකට වඩා 1.5x volume
