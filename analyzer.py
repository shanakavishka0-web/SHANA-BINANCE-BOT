import ccxt
import pandas as pd
import numpy as np
import ta
import logging
from datetime import datetime
from config import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BinanceAnalyzer:
    """
    Multi-Exchange Analyzer (Binance / Bybit / OKX)
    CCXT library එක use කරලා location block error fix කරනවා.
    """

    def __init__(self):
        """Initialize exchange connection"""
        self.exchange = None
        self._connect()

    def _connect(self):
        """Exchange connection හදාගන්න"""
        exchange_map = {
            "binance": {
                "class": ccxt.binance,
                "config": {
                    "apiKey": BINANCE_API_KEY,
                    "secret": BINANCE_SECRET_KEY,
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                },
            },
            "bybit": {
                "class": ccxt.bybit,
                "config": {
                    "apiKey": BYBIT_API_KEY,
                    "secret": BYBIT_SECRET_KEY,
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                },
            },
            "okx": {
                "class": ccxt.okx,
                "config": {
                    "apiKey": OKX_API_KEY,
                    "secret": OKX_SECRET_KEY,
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                },
            },
            "kucoin": {
                "class": ccxt.kucoin,
                "config": {
                    "apiKey": "",
                    "secret": "",
                    "enableRateLimit": True,
                },
            },
        }

        selected = EXCHANGE.lower()
        if selected not in exchange_map:
            logger.warning(f"Exchange '{selected}' not found. Defaulting to binance.")
            selected = "binance"

        try:
            exchange_class = exchange_map[selected]["class"]
            config = exchange_map[selected]["config"]
            self.exchange = exchange_class(config)

            # Test connection
            self.exchange.load_markets()
            logger.info(f"✅ Connected to {selected.upper()} successfully!")

        except Exception as e:
            logger.error(f"❌ {selected.upper()} connection failed: {e}")
            logger.info("🔄 Falling back to public endpoints (read-only)...")

            # Public fallback — API keys නැතුව try කරන්න
            try:
                self.exchange = exchange_map[selected]["class"]({
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                })
                self.exchange.load_markets()
                logger.info(f"✅ Connected to {selected.upper()} (public mode)")
            except Exception as e2:
                logger.error(f"❌ Fallback also failed: {e2}")
                raise

    def get_klines(self, symbol, timeframe="1m", limit=100):
        """ඕනෑම exchange එකකින් kline data එකක් ගන්න"""
        try:
            # Symbol format: BTC/USDT (CCXT standard)
            klines = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume'
            ])

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df

        except Exception as e:
            logger.error(f"❌ Error fetching {symbol} from {EXCHANGE}: {e}")
            return None

    def calculate_indicators(self, df):
        """ටෙක්නිකල් ඉන්ඩිකේටර්ස් (වෙනසක් නැහැ)"""
        # SMA
        df['sma_7'] = ta.trend.sma_indicator(df['close'], window=7)
        df['sma_25'] = ta.trend.sma_indicator(df['close'], window=25)
        df['sma_99'] = ta.trend.sma_indicator(df['close'], window=99)

        # EMA
        df['ema_12'] = ta.trend.ema_indicator(df['close'], window=12)
        df['ema_26'] = ta.trend.ema_indicator(df['close'], window=26)

        # RSI
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)

        # MACD
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = df['bb_upper'] - df['bb_lower']

        # Volume Analysis
        df['volume_sma_20'] = ta.trend.sma_indicator(df['volume'], window=20)
        df['volume_ratio'] = df['volume'] / df['volume_sma_20']

        # Stochastic RSI
        stoch = ta.momentum.StochRSIIndicator(df['close'], window=14, smooth1=3, smooth2=3)
        df['stoch_k'] = stoch.stochrsi_k()
        df['stoch_d'] = stoch.stochrsi_d()

        # ATR
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)

        # Support & Resistance
        df['resistance'] = df['high'].rolling(window=20).max()
        df['support'] = df['low'].rolling(window=20).min()

        # Price Action
        df['body'] = abs(df['close'] - df['open'])
        df['upper_wick'] = df['high'] - df[['close', 'open']].max(axis=1)
        df['lower_wick'] = df[['close', 'open']].min(axis=1) - df['low']
        df['is_bullish'] = df['close'] > df['open']

        return df

    def find_short_signal(self, symbol):
        """SHORT signal (bearish)"""
        df = self.get_klines(symbol, "1m", 100)
        if df is None or len(df) < 50:
            return None

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        signals = []
        confidence = 0

        # Condition 1: RSI Overbought
        if latest['rsi'] > RSI_OVERBOUGHT:
            signals.append(f"RSI Overbought: {latest['rsi']:.1f}")
            confidence += 20

        # Condition 2: Price below EMA 12 & 26
        if latest['close'] < latest['ema_12'] and prev['close'] >= prev['ema_12']:
            signals.append("Price broke below EMA-12")
            confidence += 15
        if latest['close'] < latest['ema_26']:
            signals.append("Price below EMA-26")
            confidence += 10

        # Condition 3: MACD Bearish Crossover
        if latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            signals.append("MACD Bearish Crossover")
            confidence += 20

        # Condition 4: Near upper Bollinger Band
        if latest['close'] >= latest['bb_upper'] * 0.98:
            signals.append("Near Upper Bollinger Band")
            confidence += 10

        # Condition 5: Volume spike
        if latest['volume_ratio'] > VOLUME_THRESHOLD and not latest['is_bullish']:
            signals.append(f"High Volume Sell: {latest['volume_ratio']:.1f}x")
            confidence += 15

        # Condition 6: Bearish rejection wick
        if latest['upper_wick'] > latest['body'] * 2 and not latest['is_bullish']:
            signals.append("Bearish rejection wick")
            confidence += 10

        # Condition 7: StochRSI Overbought
        if latest['stoch_k'] > 80 and latest['stoch_d'] > 80:
            signals.append("StochRSI Overbought")
            confidence += 10

        # Condition 8: Near resistance
        if latest['close'] >= latest['resistance'] * 0.98:
            signals.append("Near Resistance level")
            confidence += 10

        if len(signals) >= 4 and confidence >= 50:
            atr = latest['atr']
            entry_price = latest['close']

            return {
                'symbol': symbol,
                'signal': 'SHORT',
                'entry': entry_price,
                'take_profit_1': entry_price - (atr * 1.5),
                'take_profit_2': entry_price - (atr * 3.0),
                'stop_loss': entry_price + (atr * 2.0),
                'confidence': confidence,
                'strength': len(signals),
                'reasons': signals,
                'rsi': latest['rsi'],
                'volume_ratio': latest['volume_ratio'],
                'timestamp': datetime.now().isoformat()
            }

        return None

    def find_long_signal(self, symbol):
        """LONG signal (bullish)"""
        df = self.get_klines(symbol, "1m", 100)
        if df is None or len(df) < 50:
            return None

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        signals = []
        confidence = 0

        if latest['rsi'] < RSI_OVERSOLD:
            signals.append(f"RSI Oversold: {latest['rsi']:.1f}")
            confidence += 20

        if latest['close'] > latest['ema_12'] and prev['close'] <= prev['ema_12']:
            signals.append("Price broke above EMA-12")
            confidence += 15

        if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            signals.append("MACD Bullish Crossover")
            confidence += 20

        if latest['close'] <= latest['bb_lower'] * 1.02:
            signals.append("Near Lower Bollinger Band")
            confidence += 10

        if latest['volume_ratio'] > VOLUME_THRESHOLD and latest['is_bullish']:
            signals.append(f"High Volume Buy: {latest['volume_ratio']:.1f}x")
            confidence += 15

        if len(signals) >= 3 and confidence >= 40:
            atr = latest['atr']
            entry_price = latest['close']

            return {
                'symbol': symbol,
                'signal': 'LONG',
                'entry': entry_price,
                'take_profit_1': entry_price + (atr * 1.5),
                'take_profit_2': entry_price + (atr * 3.0),
                'stop_loss': entry_price - (atr * 2.0),
                'confidence': confidence,
                'strength': len(signals),
                'reasons': signals,
                'rsi': latest['rsi'],
                'volume_ratio': latest['volume_ratio'],
                'timestamp': datetime.now().isoformat()
            }

        return None
