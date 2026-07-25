import ccxt
import pandas as pd
import numpy as np
import ta
import logging
import requests
import time
import json
import os
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
        
        # ============ SIGNAL TRACKING ============
        self.signal_tracker_file = "signal_tracker.json"
        self.signal_tracker = self._load_signal_tracker()
        self.active_signals = {}  # Current active signals for live tracking

    def _load_signal_tracker(self):
        """Previous signals load කරන්න (WIN/LOSS track කරන්න)"""
        try:
            if os.path.exists(self.signal_tracker_file):
                with open(self.signal_tracker_file, 'r') as f:
                    data = json.load(f)
                    logger.info(f"✅ Loaded {len(data)} tracked signals")
                    return data
        except Exception as e:
            logger.warning(f"Could not load signal tracker: {e}")
        return {}

    def _save_signal_tracker(self):
        """Signal tracker save කරන්න"""
        try:
            # Keep only last 500 signals
            if len(self.signal_tracker) > 500:
                keys = sorted(self.signal_tracker.keys(), reverse=True)
                self.signal_tracker = {k: self.signal_tracker[k] for k in keys[:500]}
            
            with open(self.signal_tracker_file, 'w') as f:
                json.dump(self.signal_tracker, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save signal tracker: {e}")

    def _get_signal_key(self, symbol, signal_type, entry_price, timestamp):
        """Unique signal key generate කරන්න"""
        ts = timestamp[:16] if isinstance(timestamp, str) else str(timestamp)
        return f"{symbol}_{signal_type}_{entry_price:.8f}_{ts}"

    def track_signal(self, signal):
        """අලුත් signal එකක් tracker එකට add කරන්න"""
        if not signal:
            return
        
        key = self._get_signal_key(
            signal['symbol'], 
            signal['signal'],
            signal['entry'],
            signal['timestamp']
        )
        
        if key not in self.signal_tracker:
            self.signal_tracker[key] = {
                'symbol': signal['symbol'],
                'signal': signal['signal'],
                'entry': signal['entry'],
                'take_profit_1': signal.get('take_profit_1', 0),
                'take_profit_2': signal.get('take_profit_2', 0),
                'stop_loss': signal.get('stop_loss', 0),
                'confidence': signal.get('confidence', 0),
                'timestamp': signal.get('timestamp', ''),
                'status': 'ACTIVE',       # ACTIVE / WIN / LOST
                'win_percentage': 0.0,     # Live percentage 0-100
                'current_price': signal['entry'],
                'highest_price': signal['entry'],
                'lowest_price': signal['entry'],
                'last_updated': datetime.now().isoformat()
            }
            self._save_signal_tracker()
            logger.info(f"📝 Tracked new signal: {key}")
        
        # Also add to active_signals for faster live tracking
        if signal['signal'] == 'SHORT':
            self.active_signals[key] = self.signal_tracker[key]
        
        return key

    def update_active_signals(self, symbol=None):
        """Active signals වල current status update කරන්න (live price එක බලලා)"""
        now = datetime.now()
        updated_count = 0
        
        for key in list(self.signal_tracker.keys()):
            sig = self.signal_tracker[key]
            
            # Only update ACTIVE signals
            if sig['status'] != 'ACTIVE':
                continue
            
            # Filter by symbol if specified
            if symbol and sig['symbol'] != symbol:
                continue
            
            # Skip old signals (> 2 hours old)
            try:
                sig_time = datetime.fromisoformat(sig['timestamp'])
                if (now - sig_time).total_seconds() > 7200:  # 2 hours
                    sig['status'] = 'EXPIRED'
                    continue
            except:
                pass
            
            try:
                # Get current live price
                ticker = self.get_ticker(sig['symbol'])
                if not ticker:
                    continue
                
                current_price = ticker['last']
                sig['current_price'] = current_price
                sig['last_updated'] = now.isoformat()
                
                if sig['signal'] == 'SHORT':
                    # For SHORT: price going down = win
                    # Update highest/lowest
                    if current_price > sig['highest_price']:
                        sig['highest_price'] = current_price
                    if current_price < sig['lowest_price']:
                        sig['lowest_price'] = current_price
                    
                    entry = sig['entry']
                    tp1 = sig['take_profit_1']
                    sl = sig['stop_loss']
                    
                    # Calculate percentage (how far towards TP)
                    # SHORT: price goes DOWN from entry to TP
                    total_move = abs(entry - tp1)  # Total distance to TP
                    if total_move > 0:
                        current_move = abs(entry - current_price)
                        sig['win_percentage'] = min(100.0, round((current_move / total_move) * 100, 1))
                    
                    # Check if TP hit (WIN)
                    if current_price <= tp1:
                        sig['status'] = 'WIN'
                        sig['win_percentage'] = 100.0
                        logger.info(f"🏆 SHORT WIN: {sig['symbol']} hit TP1 at {current_price}")
                    
                    # Check if SL hit (LOST)
                    elif current_price >= sl:
                        sig['status'] = 'LOST'
                        sig['win_percentage'] = 0.0
                        logger.info(f"💀 SHORT LOST: {sig['symbol']} hit SL at {current_price}")
                    
                elif sig['signal'] == 'LONG':
                    # For LONG: price going up = win
                    if current_price > sig['highest_price']:
                        sig['highest_price'] = current_price
                    if current_price < sig['lowest_price']:
                        sig['lowest_price'] = current_price
                    
                    entry = sig['entry']
                    tp1 = sig['take_profit_1']
                    sl = sig['stop_loss']
                    
                    total_move = abs(tp1 - entry)
                    if total_move > 0:
                        current_move = abs(current_price - entry)
                        sig['win_percentage'] = min(100.0, round((current_move / total_move) * 100, 1))
                    
                    if current_price >= tp1:
                        sig['status'] = 'WIN'
                        sig['win_percentage'] = 100.0
                        logger.info(f"🏆 LONG WIN: {sig['symbol']} hit TP1 at {current_price}")
                    
                    elif current_price <= sl:
                        sig['status'] = 'LOST'
                        sig['win_percentage'] = 0.0
                        logger.info(f"💀 LONG LOST: {sig['symbol']} hit SL at {current_price}")
                
                updated_count += 1
                    
            except Exception as e:
                logger.warning(f"Error updating signal {key}: {e}")
                continue
        
        if updated_count > 0:
            self._save_signal_tracker()
        
        return updated_count

    def get_signal_win_rate(self, symbol=None):
        """Win rate percentage එක ගන්න (overall හෝ per symbol)"""
        total = 0
        wins = 0
        losses = 0
        active = 0
        
        for key, sig in self.signal_tracker.items():
            if symbol and sig['symbol'] != symbol:
                continue
            
            total += 1
            if sig['status'] == 'WIN':
                wins += 1
            elif sig['status'] == 'LOST':
                losses += 1
            elif sig['status'] == 'ACTIVE':
                active += 1
        
        if total == 0:
            return {'total': 0, 'wins': 0, 'losses': 0, 'active': 0, 'win_rate': 0.0}
        
        completed = wins + losses
        win_rate = round((wins / completed * 100), 1) if completed > 0 else 0.0
        
        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'active': active,
            'win_rate': win_rate
        }

    def get_signal_status(self, signal_key):
        """Specific signal එකක current status එක ගන්න"""
        if signal_key in self.signal_tracker:
            return self.signal_tracker[signal_key]
        return None

    def get_live_signal_percentage(self, symbol, signal_type='SHORT'):
        """Live signal percentage එක ගන්න — price move එක අනුව update වෙනවා"""
        self.update_active_signals(symbol)
        
        best_signal = None
        best_percentage = -1
        
        for key, sig in self.signal_tracker.items():
            if sig['symbol'] != symbol or sig['signal'] != signal_type:
                continue
            if sig['status'] != 'ACTIVE' and sig['status'] != 'WIN' and sig['status'] != 'LOST':
                continue
            
            # Return the latest active signal
            if sig['win_percentage'] > best_percentage:
                best_percentage = sig['win_percentage']
                best_signal = sig
        
        if best_signal:
            return {
                'symbol': best_signal['symbol'],
                'signal': best_signal['signal'],
                'entry': best_signal['entry'],
                'current_price': best_signal['current_price'],
                'tp1': best_signal['take_profit_1'],
                'sl': best_signal['stop_loss'],
                'status': best_signal['status'],
                'win_percentage': best_signal['win_percentage'],
                'confidence': best_signal['confidence']
            }
        
        return None

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
        """ටෙක්නිකල් ඉන්ඩිකේටර්ස් — 100% FULL ANALYSIS"""
        # ===== TREND INDICATORS =====
        df['sma_7'] = ta.trend.sma_indicator(df['close'], window=7)
        df['sma_25'] = ta.trend.sma_indicator(df['close'], window=25)
        df['sma_50'] = ta.trend.sma_indicator(df['close'], window=50)
        df['sma_99'] = ta.trend.sma_indicator(df['close'], window=99)
        df['sma_200'] = ta.trend.sma_indicator(df['close'], window=200)
        df['ema_5'] = ta.trend.ema_indicator(df['close'], window=5)
        df['ema_12'] = ta.trend.ema_indicator(df['close'], window=12)
        df['ema_26'] = ta.trend.ema_indicator(df['close'], window=26)
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=50)
        df['ema_200'] = ta.trend.ema_indicator(df['close'], window=200)
        
        # ===== MOMENTUM INDICATORS =====
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        df['rsi_6'] = ta.momentum.rsi(df['close'], window=6)  # Fast RSI
        
        # Williams %R
        df['williams_r'] = ta.momentum.williams_r(df['high'], df['low'], df['close'], lbp=14)
        
        # Awesome Oscillator
        df['ao'] = ta.momentum.awesome_oscillator(df['high'], df['low'], window1=5, window2=34)
        
        # KAMA (Kaufman's Adaptive Moving Average)
        df['kama'] = ta.momentum.kama(df['close'], window=30, pow1=2, pow2=30)
        
        # ROC (Rate of Change)
        df['roc'] = ta.momentum.roc(df['close'], window=12)
        
        # TSV / MFI (Money Flow Index)
        df['mfi'] = ta.volume.money_flow_index(df['high'], df['low'], df['close'], df['volume'], window=14)
        
        # Ease of Movement
        df['eom'] = ta.volume.ease_of_movement(df['high'], df['low'], df['volume'], window=14)
        
        # ===== MACD (FULL) =====
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        # MACD Extra
        df['macd_histogram'] = df['macd_diff']
        
        # ===== BOLLINGER BANDS (3 LEVELS) =====
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle'] * 100
        df['bb_percent'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower']) * 100
        
        # Bollinger Bands 1.5 deviation (tighter)
        bb_15 = ta.volatility.BollingerBands(df['close'], window=20, window_dev=1.5)
        df['bb_upper_15'] = bb_15.bollinger_hband()
        df['bb_lower_15'] = bb_15.bollinger_lband()
        
        # ===== VOLUME INDICATORS =====
        df['volume_sma_5'] = ta.trend.sma_indicator(df['volume'], window=5)
        df['volume_sma_10'] = ta.trend.sma_indicator(df['volume'], window=10)
        df['volume_sma_20'] = ta.trend.sma_indicator(df['volume'], window=20)
        df['volume_ratio_5'] = df['volume'] / df['volume_sma_5']
        df['volume_ratio_10'] = df['volume'] / df['volume_sma_10']
        df['volume_ratio_20'] = df['volume'] / df['volume_sma_20']
        
        # OBV (On-Balance Volume)
        df['obv'] = ta.volume.on_balance_volume(df['close'], df['volume'])
        df['obv_sma'] = ta.trend.sma_indicator(df['obv'], window=20)
        df['obv_divergence'] = df['obv'] - df['obv_sma']
        
        # Volume Price Trend
        df['vpt'] = ta.volume.volume_price_trend(df['close'], df['volume'])
        
        # ===== STOCHASTIC (FULL) =====
        stoch = ta.momentum.StochRSIIndicator(df['close'], window=14, smooth1=3, smooth2=3)
        df['stoch_k'] = stoch.stochrsi_k()
        df['stoch_d'] = stoch.stochrsi_d()
        
        # Regular Stochastic
        df['stoch_k_reg'] = ta.momentum.stoch(df['high'], df['low'], df['close'], window=14, smooth_window=3)
        df['stoch_d_reg'] = ta.momentum.stoch_signal(df['high'], df['low'], df['close'], window=14, smooth_window=3)
        
        # ===== VOLATILITY =====
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['atr_percent'] = df['atr'] / df['close'] * 100
        
        # Keltner Channels
        df['kc_middle'] = ta.trend.ema_indicator(df['close'], window=20)
        df['kc_upper'] = df['kc_middle'] + (df['atr'] * 1.5)
        df['kc_lower'] = df['kc_middle'] - (df['atr'] * 1.5)
        
        # ===== PATTERN / PRICE ACTION =====
        df['resistance'] = df['high'].rolling(window=20).max()
        df['support'] = df['low'].rolling(window=20).min()
        df['resistance_50'] = df['high'].rolling(window=50).max()  # Stronger resistance
        df['support_50'] = df['low'].rolling(window=50).min()      # Stronger support
        
        # Candlestick body/wick analysis
        df['body'] = abs(df['close'] - df['open'])
        df['upper_wick'] = df['high'] - df[['close', 'open']].max(axis=1)
        df['lower_wick'] = df[['close', 'open']].min(axis=1) - df['low']
        df['body_percent'] = df['body'] / (df['high'] - df['low']) * 100
        df['upper_wick_percent'] = df['upper_wick'] / (df['high'] - df['low']) * 100
        df['lower_wick_percent'] = df['lower_wick'] / (df['high'] - df['low']) * 100
        
        df['is_bullish'] = df['close'] > df['open']
        df['is_bearish'] = df['close'] < df['open']
        df['is_doji'] = df['body'] < ((df['high'] - df['low']) * 0.1)
        
        # ===== TREND STRENGTH =====
        # ADX
        df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
        df['plus_di'] = ta.trend.adx_pos(df['high'], df['low'], df['close'], window=14)
        df['minus_di'] = ta.trend.adx_neg(df['high'], df['low'], df['close'], window=14)

අලුත්:
df['aroon_up'] = 50.0
df['aroon_down'] = 50.0
        
        # Ichimoku Cloud
        df['ichimoku_a'] = ta.trend.ichimoku_a(df['high'], df['low'], window1=9, window2=26)
        df['ichimoku_b'] = ta.trend.ichimoku_b(df['high'], df['low'], window2=26, window3=52)
        
        # PSAR
        df['psar'] = ta.trend.psar_indicator(df['high'], df['low'], df['close'], step=0.02, max_step=0.2)
        
        # ===== DIVERGENCE DETECTION =====
        df['price_higher_high'] = (df['high'] > df['high'].shift(1)) & (df['high'].shift(1) > df['high'].shift(2))
        df['price_lower_low'] = (df['low'] < df['low'].shift(1)) & (df['low'].shift(1) < df['low'].shift(2))
        df['rsi_higher_high'] = (df['rsi'] > df['rsi'].shift(1)) & (df['rsi'].shift(1) > df['rsi'].shift(2))
        df['rsi_lower_low'] = (df['rsi'] < df['rsi'].shift(1)) & (df['rsi'].shift(1) < df['rsi'].shift(2))
        
        # Bearish divergence: price higher high, RSI lower high
        df['bearish_div_rsi'] = df['price_higher_high'] & ~df['rsi_higher_high']
        
        return df

    def find_short_signal(self, symbol):
        """SHORT signal — 90-95% ACCURACY TARGET — FULL ANALYSIS"""
        df = self.get_klines(symbol, "1m", 200)  # More data for accurate analysis
        if df is None or len(df) < 100:
            return None

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        signals = []
        confidence = 0
        weight_total = 0

        # 1. RSI OVERBOUGHT (Weight: 12)
        if latest['rsi'] > RSI_OVERBOUGHT:
            rsi_excess = (latest['rsi'] - RSI_OVERBOUGHT) / (100 - RSI_OVERBOUGHT)
            score = min(12, 8 + (rsi_excess * 4))
            signals.append(f"🔥 RSI Overbought: {latest['rsi']:.1f} (Strong)")
            confidence += score
            weight_hit += 12
        elif latest['rsi'] > 65:
            signals.append(f"⚠️ RSI High: {latest['rsi']:.1f}")
            confidence += 4
            weight_hit += 6
        weight_total += 12

        # 2. RSI DIVERGENCE (Weight: 15)
        if df['bearish_div_rsi'].iloc[-1]:
            signals.append(f"🚨 RSI Bearish Divergence Detected!")
            confidence += 15
            weight_hit += 15
        weight_total += 15

        # 3. EMA CROSSOVER (Weight: 10)
        if latest['close'] < latest['ema_12'] and prev['close'] >= prev['ema_12']:
            signals.append(f"📉 Price broke below EMA-12")
            confidence += 10
            weight_hit += 10
        elif latest['close'] < latest['ema_12']:
            confidence += 3
            weight_hit += 3
        weight_total += 10

        # 4. MULTIPLE EMA ALIGNMENT (Weight: 10)
        ema_bearish = (
            latest['close'] < latest['ema_5'] and
            latest['close'] < latest['ema_12'] and
            latest['close'] < latest['ema_26'] and
            latest['close'] < latest['ema_50']
        )
        if ema_bearish:
            signals.append(f"📊 All EMAs Bearish (5/12/26/50)")
            confidence += 10
            weight_hit += 10
        weight_total += 10

        # 5. MACD BEARISH CROSSOVER (Weight: 15)
        if latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            signals.append(f"🚩 MACD Bearish Crossover (Strong)")
            confidence += 15
            weight_hit += 15
        elif latest['macd'] < latest['macd_signal']:
            signals.append(f"📊 MACD Bearish")
            confidence += 5
            weight_hit += 5
        weight_total += 15

        # 6. MACD HISTOGRAM DECLINING (Weight: 5)
        if latest['macd_histogram'] < prev['macd_histogram'] and latest['macd_histogram'] < 0:
            signals.append(f"📉 MACD Histogram declining negative")
            confidence += 5
            weight_hit += 5
        weight_total += 5

        # 7. BOLLINGER BANDS (Weight: 10)
        if latest['close'] >= latest['bb_upper'] * 0.98:
            signals.append(f"💥 Price at Upper BB: {latest['close']:.4f}")
            confidence += 10
            weight_hit += 10
        elif latest['close'] >= latest['bb_upper_15'] * 0.98:
            signals.append(f"⚡ Price at Upper BB(1.5)")
            confidence += 6
            weight_hit += 6
        elif latest['bb_percent'] > 80:
            signals.append(f"📊 BB % above 80: {latest['bb_percent']:.1f}%")
            confidence += 3
            weight_hit += 3
        weight_total += 10

        # 8. VOLUME CONFIRMATION (Weight: 10)
        if latest['volume_ratio_5'] > VOLUME_THRESHOLD and not latest['is_bullish']:
            signals.append(f"📈 High Sell Volume: {latest['volume_ratio_5']:.1f}x (5MA)")
            confidence += 10
            weight_hit += 10
        elif latest['volume_ratio_10'] > VOLUME_THRESHOLD and not latest['is_bullish']:
            signals.append(f"📊 High Sell Volume: {latest['volume_ratio_10']:.1f}x (10MA)")
            confidence += 7
            weight_hit += 7
        weight_total += 10

        # 9. BEARISH CANDLE PATTERN (Weight: 8)
        if latest['upper_wick'] > latest['body'] * 2 and not latest['is_bullish']:
            signals.append(f"🕯️ Bearish rejection wick (Strong)")
            confidence += 8
            weight_hit += 8
        elif latest['is_bearish'] and latest['body_percent'] > 60:
            signals.append(f"🕯️ Strong bearish candle ({latest['body_percent']:.0f}% body)")
            confidence += 5
            weight_hit += 5
        weight_total += 8

        # 10. STOCHASTIC RSI OVERBOUGHT (Weight: 8)
        if latest['stoch_k'] > 80 and latest['stoch_d'] > 80:
            signals.append(f"📊 StochRSI Overbought (K:{latest['stoch_k']:.0f}, D:{latest['stoch_d']:.0f})")
            confidence += 8
            weight_hit += 8
        elif latest['stoch_k_reg'] > 80:
            signals.append(f"📊 Stoch Overbought: {latest['stoch_k_reg']:.0f}")
            confidence += 4
            weight_hit += 4
        weight_total += 8

        # 11. RESISTANCE TESTING (Weight: 10)
        if latest['close'] >= latest['resistance'] * 0.995:
            signals.append(f"🧱 Testing Resistance: {latest['resistance']:.4f}")
            confidence += 10
            weight_hit += 10
        elif latest['close'] >= latest['resistance_50'] * 0.995:
            signals.append(f"🧱 Testing Major Resistance(50): {latest['resistance_50']:.4f}")
            confidence += 8
            weight_hit += 8
        weight_total += 10

        # 12. ADX TREND STRENGTH (Weight: 8)
        if latest['adx'] > 25 and latest['minus_di'] > latest['plus_di']:
            signals.append(f"📊 Strong Downtrend (ADX:{latest['adx']:.0f})")
            confidence += 8
            weight_hit += 8
        elif latest['adx'] > 20 and latest['minus_di'] > latest['plus_di']:
            signals.append(f"📊 Downtrend (ADX:{latest['adx']:.0f})")
            confidence += 4
            weight_hit += 4
        weight_total += 8

        # 14. WILLIAMS %R (Weight: 6)
        if latest['williams_r'] < -80:
            signals.append(f"📊 Williams %R Oversold: {latest['williams_r']:.0f}")
            confidence += 6
            weight_hit += 6
        weight_total += 6

        # 15. MFI (Weight: 6)
        if latest['mfi'] > 80:
            signals.append(f"📊 MFI Overbought: {latest['mfi']:.0f}")
            confidence += 6
            weight_hit += 6
        elif latest['mfi'] > 70:
            confidence += 3
            weight_hit += 3
        weight_total += 6

        # 16. KELTNER CHANNEL (Weight: 6)
        if latest['close'] >= latest['kc_upper']:
            signals.append(f"📊 Price at Keltner Upper")
            confidence += 6
            weight_hit += 6
        weight_total += 6

        # 17. AROON (Weight: 6)
        if latest['aroon_down'] > latest['aroon_up'] and latest['aroon_down'] > 70:
            signals.append(f"📊 Aroon Strong Downtrend (Down:{latest['aroon_down']:.0f}%)")
            confidence += 6
            weight_hit += 6
        weight_total += 6

        # 19. VOLUME PRICE TREND (Weight: 5)
        if latest['vpt'] < prev['vpt'] and latest['vpt'] < 0:
            signals.append(f"📊 VPT declining (distribution)")
            confidence += 5
            weight_hit += 5
        weight_total += 5

        # ============ FINAL CALCULATION ============
        weighted_confidence = (confidence / weight_total) * 100 if weight_total > 0 else 0

        min_signals = 8
        strict_filters_passed = 0
        
        if latest['rsi'] > 60 or latest['stoch_k'] > 75:
            strict_filters_passed += 1
        
        ema_count = sum([
            latest['close'] < latest['ema_12'],
            latest['close'] < latest['ema_26'],
            latest['close'] < latest['ema_50'],
            latest['close'] < latest['sma_25']
        ])
        if ema_count >= 2:
            strict_filters_passed += 1
        
        if latest['macd'] < latest['macd_signal'] or latest['rsi'] > RSI_OVERBOUGHT:
            strict_filters_passed += 1
        
        if latest['volume_ratio_5'] > 1.2 or latest['is_bearish']:
            strict_filters_passed += 1
        
        if latest['close'] >= latest['resistance'] * 0.99 or latest['close'] >= latest['bb_upper'] * 0.97:
            strict_filters_passed += 1

        if len(signals) >= min_signals and weighted_confidence >= 65 and strict_filters_passed >= 4:
            atr = latest['atr']
            entry_price = latest['close']
            
            atr_multiplier_tp = max(1.2, min(2.0, 1.5 - (weighted_confidence / 200)))
            atr_multiplier_sl = max(1.5, min(2.5, 2.0 - (weighted_confidence / 200)))
            
            signal_result = {
                'symbol': symbol,
                'signal': 'SHORT',
                'entry': entry_price,
                'take_profit_1': entry_price - (atr * atr_multiplier_tp),
                'take_profit_2': entry_price - (atr * (atr_multiplier_tp * 2)),
                'stop_loss': entry_price + (atr * atr_multiplier_sl),
                'confidence': min(99, int(weighted_confidence)),
                'accuracy_score': min(99, int(weighted_confidence + (strict_filters_passed * 2))),
                'strength': len(signals),
                'reasons': signals,
                'rsi': latest['rsi'],
                'volume_ratio': latest['volume_ratio_5'],
                'adx': latest['adx'],
                'mfi': latest['mfi'],
                'bb_percent': latest['bb_percent'],
                'strict_filters': strict_filters_passed,
                'timestamp': datetime.now().isoformat()
            }
            
            self.track_signal(signal_result)
            return signal_result
        
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
            
            signal_result = {
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
            
            self.track_signal(signal_result)
            return signal_result
        return None


# ============ VERIFICATION (අනිවාර්යයෙන්ම මෙය පහළින් තියෙන්න ඕනේ!) ============
if __name__ == "__main__":
    print("✅ BinanceAnalyzer class loaded successfully!")
    print(f"   Class methods: {[m for m in dir(BinanceAnalyzer) if not m.startswith('__')]}")
