import ccxt
import pandas as pd
import numpy as np
import ta
import logging
import requests
import time
from datetime import datetime
from config import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class BinanceAnalyzer:
    """
    Binance-Only Analyzer
    load_markets() SKIP කරලා directly data ගන්නවා
    Public endpoints — API keys අවශ්‍ය නැහැ
    """

    def __init__(self):
        """Binance connection — load_markets නැතුව"""
        self.exchange = None
        self._connect()

    def _connect(self):
        """Direct API calls — load_markets() error එක skip"""
        try:
            # CCXT config — load_markets auto එක off
            self.exchange = ccxt.binance({
                "apiKey": BINANCE_API_KEY,
                "secret": BINANCE_SECRET_KEY,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                },
            })

            # load_markets SKIP — ඒකෙන් 451 error එන නිසා
            # අපි directly fetch_ohlcv() call කරනවා
            logger.info("✅ Binance Analyzer initialized (load_markets skipped)")

            # Test connection with a simple request
            test = self.exchange.fetch_ohlcv("BTC/USDT", "1m", limit=1)
            if test and len(test) > 0:
                logger.info("✅ Binance API working — data received!")
            else:
                logger.warning("⚠️ Binance returned empty data")

        except Exception as e:
            logger.error(f"❌ Binance CCXT failed: {e}")
            logger.info("🔄 Trying direct REST API call...")
            
            # Fallback: Direct REST API call (no CCXT)
            self.exchange = None
            self._direct_rest = True
            self._base_url = self._find_working_endpoint()
            
            if self._base_url:
                logger.info(f"✅ Direct REST endpoint working: {self._base_url}")
            else:
                logger.error("❌ All Binance endpoints blocked!")
                raise

    def _find_working_endpoint(self):
        """වැඩ කරන Binance endpoint එක හොයාගන්න"""
        endpoints = [
            "https://api.binance.com",
            "https://api1.binance.com",
            "https://api2.binance.com",
            "https://api3.binance.com",
            "https://fapi.binance.com",   # Futures API
        ]

        for url in endpoints:
            try:
                r = requests.get(
                    f"{url}/api/v3/ping",
                    timeout=5,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if r.status_code == 200:
                    logger.info(f"✅ Working endpoint: {url}")
                    return url
            except:
                continue

        return None

    def get_klines(self, symbol, timeframe="1m", limit=100):
        """Binance එකෙන් OHLCV data ගන්න (load_markets නැතුව)"""
        
        # Symbol convert: BTC/USDT -> BTCUSDT
        clean_symbol = symbol.replace("/", "")

        # Try CCXT first
        if self.exchange:
            try:
                # markets dict එක manually populate කරන්න
                self.exchange.markets = {
                    clean_symbol: {
                        "id": clean_symbol,
                        "symbol": symbol,
                        "base": symbol.split("/")[0],
                        "quote": symbol.split("/")[1],
                        "active": True,
                        "spot": True,
                        "linear": None,
                        "inverse": None,
                        "type": "spot",
                    }
                }
                self.exchange.symbols = [symbol]
                
                klines = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume'
                ])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df

            except Exception as e:
                logger.warning(f"CCXT fetch failed for {symbol}: {e}")
                # Fall through to REST

        # Direct REST API call
        try:
            base = getattr(self, '_base_url', 'https://api.binance.com')
            if not base:
                base = 'https://api.binance.com'

            params = {
                "symbol": clean_symbol,
                "interval": timeframe,
                "limit": limit
            }

            r = requests.get(
                f"{base}/api/v3/klines",
                params=params,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"}
            )

            if r.status_code == 200:
                klines = r.json()
                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
                ])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            else:
                logger.error(f"REST API error {r.status_code} for {symbol}")
                return None

        except Exception as e:
            logger.error(f"REST fetch error {symbol}: {e}")
            return None

    def get_ticker(self, symbol):
        """ලයිව් price + 24h change ගන්න"""
        clean_symbol = symbol.replace("/", "")
        
        try:
            base = getattr(self, '_base_url', 'https://api.binance.com')
            r = requests.get(
                f"{base}/api/v3/ticker/24hr",
                params={"symbol": clean_symbol},
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            
            if r.status_code == 200:
                data = r.json()
                return {
                    'symbol': symbol,
                    'last': float(data['lastPrice']),
                    'percentage': float(data['priceChangePercent']),
                    'high': float(data['highPrice']),
                    'low': float(data['lowPrice']),
                    'baseVolume': float(data['volume']),
                    'quoteVolume': float(data['quoteVolume']),
                }
            return None
        except Exception as e:
            logger.error(f"Ticker error {symbol}: {e}")
            return None

    def calculate_indicators(self, df):
        """ටෙක්නිකල් ඉන්ඩිකේටර්ස්"""
        df['sma_7'] = ta.trend.sma_indicator(df['close'], window=7)
        df['sma_25'] = ta.trend.sma_indicator(df['close'], window=25)
        df['sma_99'] = ta.trend.sma_indicator(df['close'], window=99)
        df['ema_12'] = ta.trend.ema_indicator(df['close'], window=12)
        df['ema_26'] = ta.trend.ema_indicator(df['close'], window=26)
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        
        df['volume_sma_20'] = ta.trend.sma_indicator(df['volume'], window=20)
        df['volume_ratio'] = df['volume'] / df['volume_sma_20']
        
        stoch = ta.momentum.StochRSIIndicator(df['close'], window=14, smooth1=3, smooth2=3)
        df['stoch_k'] = stoch.stochrsi_k()
        df['stoch_d'] = stoch.stochrsi_d()
        
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['resistance'] = df['high'].rolling(window=20).max()
        df['support'] = df['low'].rolling(window=20).min()
        df['body'] = abs(df['close'] - df['open'])
        df['upper_wick'] = df['high'] - df[['close', 'open']].max(axis=1)
        df['lower_wick'] = df[['close', 'open']].min(axis=1) - df['low']
        df['is_bullish'] = df['close'] > df['open']
        
        return df

    def find_short_signal(self, symbol):
        """SHORT signal"""
        df = self.get_klines(symbol, "1m", 100)
        if df is None or len(df) < 50:
            return None

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        signals = []
        confidence = 0

        if latest['rsi'] > RSI_OVERBOUGHT:
            signals.append(f"RSI Overbought: {latest['rsi']:.1f}")
            confidence += 20
        if latest['close'] < latest['ema_12'] and prev['close'] >= prev['ema_12']:
            signals.append("Price broke below EMA-12")
            confidence += 15
        if latest['close'] < latest['ema_26']:
            signals.append("Price below EMA-26")
            confidence += 10
        if latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            signals.append("MACD Bearish Crossover")
            confidence += 20
        if latest['close'] >= latest['bb_upper'] * 0.98:
            signals.append("Near Upper Bollinger Band")
            confidence += 10
        if latest['volume_ratio'] > VOLUME_THRESHOLD and not latest['is_bullish']:
            signals.append(f"High Volume Sell: {latest['volume_ratio']:.1f}x")
            confidence += 15
        if latest['upper_wick'] > latest['body'] * 2 and not latest['is_bullish']:
            signals.append("Bearish rejection wick")
            confidence += 10
        if latest['stoch_k'] > 80 and latest['stoch_d'] > 80:
            signals.append("StochRSI Overbought")
            confidence += 10
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
        """LONG signal"""
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
