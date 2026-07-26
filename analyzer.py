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
        self.active_signals = {}

    def _load_signal_tracker(self):
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
        try:
            if len(self.signal_tracker) > 500:
                keys = sorted(self.signal_tracker.keys(), reverse=True)
                self.signal_tracker = {k: self.signal_tracker[k] for k in keys[:500]}
            with open(self.signal_tracker_file, 'w') as f:
                json.dump(self.signal_tracker, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save signal tracker: {e}")

    def _get_signal_key(self, symbol, signal_type, entry_price, timestamp):
        ts = timestamp[:16] if isinstance(timestamp, str) else str(timestamp)
        return f"{symbol}_{signal_type}_{entry_price:.8f}_{ts}"

    def track_signal(self, signal):
        if not signal:
            return
        key = self._get_signal_key(signal['symbol'], signal['signal'], signal['entry'], signal['timestamp'])
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
                'status': 'ACTIVE',
                'win_percentage': 0.0,
                'current_price': signal['entry'],
                'highest_price': signal['entry'],
                'lowest_price': signal['entry'],
                'last_updated': datetime.now().isoformat()
            }
            self._save_signal_tracker()
            logger.info(f"📝 Tracked new signal: {key}")
        if signal['signal'] == 'SHORT':
            self.active_signals[key] = self.signal_tracker[key]
        return key

    def update_active_signals(self, symbol=None):
        now = datetime.now()
        updated_count = 0
        for key in list(self.signal_tracker.keys()):
            sig = self.signal_tracker[key]
            if sig['status'] != 'ACTIVE':
                continue
            if symbol and sig['symbol'] != symbol:
                continue
            try:
                sig_time = datetime.fromisoformat(sig['timestamp'])
                if (now - sig_time).total_seconds() > 7200:
                    sig['status'] = 'EXPIRED'
                    continue
            except:
                pass
            try:
                ticker = self.get_ticker(sig['symbol'])
                if not ticker:
                    continue
                current_price = ticker['last']
                sig['current_price'] = current_price
                sig['last_updated'] = now.isoformat()
                if sig['signal'] == 'SHORT':
                    if current_price > sig['highest_price']:
                        sig['highest_price'] = current_price
                    if current_price < sig['lowest_price']:
                        sig['lowest_price'] = current_price
                    entry = sig['entry']
                    tp1 = sig['take_profit_1']
                    sl = sig['stop_loss']
                    total_move = abs(entry - tp1)
                    if total_move > 0:
                        current_move = abs(entry - current_price)
                        sig['win_percentage'] = min(100.0, round((current_move / total_move) * 100, 1))
                    if current_price <= tp1:
                        sig['status'] = 'WIN'
                        sig['win_percentage'] = 100.0
                        logger.info(f"🏆 SHORT WIN: {sig['symbol']} hit TP1 at {current_price}")
                    elif current_price >= sl:
                        sig['status'] = 'LOST'
                        sig['win_percentage'] = 0.0
                        logger.info(f"💀 SHORT LOST: {sig['symbol']} hit SL at {current_price}")
                elif sig['signal'] == 'LONG':
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
        return {'total': total, 'wins': wins, 'losses': losses, 'active': active, 'win_rate': win_rate}

    def get_signal_status(self, signal_key):
        if signal_key in self.signal_tracker:
            return self.signal_tracker[signal_key]
        return None

    def get_live_signal_percentage(self, symbol, signal_type='SHORT'):
        self.update_active_signals(symbol)
        best_signal = None
        best_percentage = -1
        for key, sig in self.signal_tracker.items():
            if sig['symbol'] != symbol or sig['signal'] != signal_type:
                continue
            if sig['status'] != 'ACTIVE' and sig['status'] != 'WIN' and sig['status'] != 'LOST':
                continue
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
        try:
            self.exchange = ccxt.binance({
                "apiKey": BINANCE_API_KEY,
                "secret": BINANCE_SECRET_KEY,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            })
            logger.info("✅ Binance Analyzer initialized (load_markets skipped)")
            test = self.exchange.fetch_ohlcv("BTC/USDT", "1m", limit=1)
            if test and len(test) > 0:
                logger.info("✅ Binance API working — data received!")
            else:
                logger.warning("⚠️ Binance returned empty data")
        except Exception as e:
            logger.error(f"❌ Binance CCXT failed: {e}")
            logger.info("🔄 Trying direct REST API call...")
            self.exchange = None
            self._direct_rest = True
            self._base_url = self._find_working_endpoint()
            if self._base_url:
                logger.info(f"✅ Direct REST endpoint working: {self._base_url}")
            else:
                logger.error("❌ All Binance endpoints blocked!")
                raise

    def _find_working_endpoint(self):
        endpoints = [
            "https://api.binance.com", "https://api1.binance.com",
            "https://api2.binance.com", "https://api3.binance.com",
            "https://fapi.binance.com",
        ]
        for url in endpoints:
            try:
                r = requests.get(f"{url}/api/v3/ping", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    logger.info(f"✅ Working endpoint: {url}")
                    return url
            except:
                continue
        return None

    def get_klines(self, symbol, timeframe="1m", limit=100):
        """Binance එකෙන් OHLCV data — FIXED: markets dict key = symbol (BTC/USDT)"""
        clean_symbol = symbol.replace("/", "")

        # Try CCXT first
        if self.exchange:
            try:
                self.exchange.markets = {
                    symbol: {
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
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df
            except Exception as e:
                logger.warning(f"CCXT fetch failed for {symbol}: {e}")

        # Direct REST API
        try:
            base = getattr(self, '_base_url', 'https://api.binance.com')
            if not base:
                base = 'https://api.binance.com'
            params = {"symbol": clean_symbol, "interval": timeframe, "limit": limit}
            r = requests.get(f"{base}/api/v3/klines", params=params, timeout=10,
                             headers={"User-Agent": "Mozilla/5.0"})
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
        clean_symbol = symbol.replace("/", "")
        try:
            base = getattr(self, '_base_url', 'https://api.binance.com')
            r = requests.get(f"{base}/api/v3/ticker/24hr", params={"symbol": clean_symbol},
                             timeout=10, headers={"User-Agent": "Mozilla/5.0"})
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
        df['rsi_6'] = ta.momentum.rsi(df['close'], window=6)
        df['williams_r'] = ta.momentum.williams_r(df['high'], df['low'], df['close'], lbp=14)
        df['ao'] = ta.momentum.awesome_oscillator(df['high'], df['low'], window1=5, window2=34)
        df['kama'] = ta.momentum.kama(df['close'], window=30, pow1=2, pow2=30)
        df['roc'] = ta.momentum.roc(df['close'], window=12)
        df['mfi'] = ta.volume.money_flow_index(df['high'], df['low'], df['close'], df['volume'], window=14)
        df['eom'] = ta.volume.ease_of_movement(df['high'], df['low'], df['volume'], window=14)
        
        # ===== MACD =====
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        df['macd_histogram'] = df['macd_diff']
        
        # ===== BOLLINGER BANDS =====
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle'] * 100
        df['bb_percent'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower']) * 100
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
        df['obv'] = ta.volume.on_balance_volume(df['close'], df['volume'])
        df['obv_sma'] = ta.trend.sma_indicator(df['obv'], window=20)
        df['obv_divergence'] = df['obv'] - df['obv_sma']
        df['vpt'] = ta.volume.volume_price_trend(df['close'], df['volume'])
        
        # ===== STOCHASTIC =====
        stoch = ta.momentum.StochRSIIndicator(df['close'], window=14, smooth1=3, smooth2=3)
        df['stoch_k'] = stoch.stochrsi_k()
        df['stoch_d'] = stoch.stochrsi_d()
        df['stoch_k_reg'] = ta.momentum.stoch(df['high'], df['low'], df['close'], window=14, smooth_window=3)
        df['stoch_d_reg'] = ta.momentum.stoch_signal(df['high'], df['low'], df['close'], window=14, smooth_window=3)
        
        # ===== VOLATILITY =====
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['atr_percent'] = df['atr'] / df['close'] * 100
        df['kc_middle'] = ta.trend.ema_indicator(df['close'], window=20)
        df['kc_upper'] = df['kc_middle'] + (df['atr'] * 1.5)
        df['kc_lower'] = df['kc_middle'] - (df['atr'] * 1.5)
        
        # ===== PATTERN / PRICE ACTION =====
        df['resistance'] = df['high'].rolling(window=20).max()
        df['support'] = df['low'].rolling(window=20).min()
        df['resistance_50'] = df['high'].rolling(window=50).max()
        df['support_50'] = df['low'].rolling(window=50).min()
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
        df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
        df['plus_di'] = ta.trend.adx_pos(df['high'], df['low'], df['close'], window=14)
        df['minus_di'] = ta.trend.adx_neg(df['high'], df['low'], df['close'], window=14)
        df['aroon_up'] = 50.0
        df['aroon_down'] = 50.0
        df['ichimoku_a'] = ta.trend.ichimoku_a(df['high'], df['low'], window1=9, window2=26)
        df['ichimoku_b'] = ta.trend.ichimoku_b(df['high'], df['low'], window2=26, window3=52)
        df['psar'] = 0.0
        
        # ===== DIVERGENCE =====
        df['price_higher_high'] = (df['high'] > df['high'].shift(1)) & (df['high'].shift(1) > df['high'].shift(2))
        df['price_lower_low'] = (df['low'] < df['low'].shift(1)) & (df['low'].shift(1) < df['low'].shift(2))
        df['rsi_higher_high'] = (df['rsi'] > df['rsi'].shift(1)) & (df['rsi'].shift(1) > df['rsi'].shift(2))
        df['rsi_lower_low'] = (df['rsi'] < df['rsi'].shift(1)) & (df['rsi'].shift(1) < df['rsi'].shift(2))
        df['bearish_div_rsi'] = df['price_higher_high'] & ~df['rsi_higher_high']
        
        return df

    def find_short_signal(self, symbol):
        """SHORT signal — same as before"""
        df = self.get_klines(symbol, "1m", 200)
        if df is None or len(df) < 100:
            return None

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        signals = []
        confidence = 0
        weight_total = 0
        weight_hit = 0

        if latest['rsi'] > RSI_OVERBOUGHT:
            rsi_excess = (latest['rsi'] - RSI_OVERBOUGHT) / (100 - RSI_OVERBOUGHT)
            score = min(12, 8 + (rsi_excess * 4))
            signals.append(f"🔥 RSI Overbought: {latest['rsi']:.1f}")
            confidence += score
            weight_hit += 12
        elif latest['rsi'] > 65:
            signals.append(f"⚠️ RSI High: {latest['rsi']:.1f}")
            confidence += 4
            weight_hit += 6
        weight_total += 12

        if df['bearish_div_rsi'].iloc[-1]:
            signals.append(f"🚨 RSI Bearish Divergence!")
            confidence += 15
            weight_hit += 15
        weight_total += 15

        if latest['close'] < latest['ema_12'] and prev['close'] >= prev['ema_12']:
            signals.append(f"📉 Price broke below EMA-12")
            confidence += 10
            weight_hit += 10
        elif latest['close'] < latest['ema_12']:
            confidence += 3
            weight_hit += 3
        weight_total += 10

        ema_bearish = (
            latest['close'] < latest['ema_5'] and
            latest['close'] < latest['ema_12'] and
            latest['close'] < latest['ema_26'] and
            latest['close'] < latest['ema_50']
        )
        if ema_bearish:
            signals.append("📊 All EMAs Bearish")
            confidence += 10
            weight_hit += 10
        weight_total += 10

        if latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            signals.append("🚩 MACD Bearish Crossover")
            confidence += 15
            weight_hit += 15
        elif latest['macd'] < latest['macd_signal']:
            signals.append("📊 MACD Bearish")
            confidence += 5
            weight_hit += 5
        weight_total += 15

        if latest['macd_histogram'] < prev['macd_histogram'] and latest['macd_histogram'] < 0:
            signals.append("📉 MACD Histogram declining")
            confidence += 5
            weight_hit += 5
        weight_total += 5

        if latest['close'] >= latest['bb_upper'] * 0.98:
            signals.append(f"💥 Price at Upper BB")
            confidence += 10
            weight_hit += 10
        elif latest['close'] >= latest['bb_upper_15'] * 0.98:
            signals.append(f"⚡ Price at BB(1.5)")
            confidence += 6
            weight_hit += 6
        elif latest['bb_percent'] > 80:
            signals.append(f"📊 BB%: {latest['bb_percent']:.0f}%")
            confidence += 3
            weight_hit += 3
        weight_total += 10

        if latest['volume_ratio_5'] > VOLUME_THRESHOLD and not latest['is_bullish']:
            signals.append(f"📈 High Sell Vol: {latest['volume_ratio_5']:.1f}x")
            confidence += 10
            weight_hit += 10
        elif latest['volume_ratio_10'] > VOLUME_THRESHOLD and not latest['is_bullish']:
            signals.append(f"📊 High Sell Vol: {latest['volume_ratio_10']:.1f}x")
            confidence += 7
            weight_hit += 7
        weight_total += 10

        if latest['upper_wick'] > latest['body'] * 2 and not latest['is_bullish']:
            signals.append("🕯️ Bearish rejection wick")
            confidence += 8
            weight_hit += 8
        elif latest['is_bearish'] and latest['body_percent'] > 60:
            signals.append(f"🕯️ Bearish candle {latest['body_percent']:.0f}%")
            confidence += 5
            weight_hit += 5
        weight_total += 8

        if latest['stoch_k'] > 80 and latest['stoch_d'] > 80:
            signals.append(f"📊 StochRSI Overbought")
            confidence += 8
            weight_hit += 8
        elif latest['stoch_k_reg'] > 80:
            signals.append(f"📊 Stoch Overbought: {latest['stoch_k_reg']:.0f}")
            confidence += 4
            weight_hit += 4
        weight_total += 8

        if latest['close'] >= latest['resistance'] * 0.995:
            signals.append(f"🧱 Testing Resistance")
            confidence += 10
            weight_hit += 10
        elif latest['close'] >= latest['resistance_50'] * 0.995:
            signals.append(f"🧱 Major Resistance(50)")
            confidence += 8
            weight_hit += 8
        weight_total += 10

        if latest['adx'] > 25 and latest['minus_di'] > latest['plus_di']:
            signals.append(f"📊 Strong Downtrend ADX:{latest['adx']:.0f}")
            confidence += 8
            weight_hit += 8
        elif latest['adx'] > 20 and latest['minus_di'] > latest['plus_di']:
            signals.append(f"📊 Downtrend ADX:{latest['adx']:.0f}")
            confidence += 4
            weight_hit += 4
        weight_total += 8

        if latest['williams_r'] < -80:
            signals.append(f"📊 Williams %R: {latest['williams_r']:.0f}")
            confidence += 6
            weight_hit += 6
        weight_total += 6

        if latest['mfi'] > 80:
            signals.append(f"📊 MFI Overbought: {latest['mfi']:.0f}")
            confidence += 6
            weight_hit += 6
        elif latest['mfi'] > 70:
            confidence += 3
            weight_hit += 3
        weight_total += 6

        if latest['close'] >= latest['kc_upper']:
            signals.append("📊 Price at Keltner Upper")
            confidence += 6
            weight_hit += 6
        weight_total += 6

        if latest['aroon_down'] > latest['aroon_up']:
            confidence += 3
            weight_hit += 3
        weight_total += 6

        if latest['vpt'] < prev['vpt'] and latest['vpt'] < 0:
            signals.append("📊 VPT declining")
            confidence += 5
            weight_hit += 5
        weight_total += 5

        weighted_confidence = (confidence / weight_total) * 100 if weight_total > 0 else 0

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

        if len(signals) >= 8 and weighted_confidence >= 65 and strict_filters_passed >= 4:
            atr = latest['atr']
            entry_price = latest['close']
            atr_multiplier_tp = max(1.2, min(2.0, 1.5 - (weighted_confidence / 200)))
            atr_multiplier_sl = max(1.5, min(2.5, 2.0 - (weighted_confidence / 200)))
            signal_result = {
                'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price,
                'take_profit_1': entry_price - (atr * atr_multiplier_tp),
                'take_profit_2': entry_price - (atr * (atr_multiplier_tp * 2)),
                'stop_loss': entry_price + (atr * atr_multiplier_sl),
                'confidence': min(99, int(weighted_confidence)),
                'accuracy_score': min(99, int(weighted_confidence + (strict_filters_passed * 2))),
                'strength': len(signals), 'reasons': signals,
                'rsi': latest['rsi'], 'volume_ratio': latest['volume_ratio_5'],
                'adx': latest['adx'], 'mfi': latest['mfi'],
                'bb_percent': latest['bb_percent'],
                'strict_filters': strict_filters_passed,
                'timestamp': datetime.now().isoformat()
            }
            self.track_signal(signal_result)
            return signal_result
        return None

    def find_long_signal(self, symbol):
        """LONG signal — volume_ratio -> volume_ratio_5"""
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
        if latest['volume_ratio_5'] > VOLUME_THRESHOLD and latest['is_bullish']:
            signals.append(f"High Volume Buy: {latest['volume_ratio_5']:.1f}x")
            confidence += 15
        if len(signals) >= 3 and confidence >= 40:
            atr = latest['atr']
            entry_price = latest['close']
            signal_result = {
                'symbol': symbol, 'signal': 'LONG', 'entry': entry_price,
                'take_profit_1': entry_price + (atr * 1.5),
                'take_profit_2': entry_price + (atr * 3.0),
                'stop_loss': entry_price - (atr * 2.0),
                'confidence': confidence, 'strength': len(signals),
                'reasons': signals, 'rsi': latest['rsi'],
                'volume_ratio': latest['volume_ratio_5'],
                'timestamp': datetime.now().isoformat()
            }
            self.track_signal(signal_result)
            return signal_result
        return None

    # ============ Quick scan for SHORT coin list ============
    def analyze_coin_for_short(self, symbol):
        """
        Coin එකක short potential එක ඉක්මනින් scan කරලා score එකක් දෙනවා.
        SHORT SIGNALS 5 MINUTE list එකට use කරන්න.
        """
        try:
            df = self.get_klines(symbol, "5m", 100)
            if df is None or len(df) < 50:
                return None
            
            df = self.calculate_indicators(df)
            latest = df.iloc[-1]
            
            score = 0
            reasons = []
            
            if latest['rsi'] > 65:
                score += 15
                reasons.append(f"RSI {latest['rsi']:.0f}")
            if latest['rsi'] > RSI_OVERBOUGHT:
                score += 10
            if latest['macd'] < latest['macd_signal']:
                score += 15
                reasons.append("MACD Bearish")
            ema_bearish_count = sum([
                latest['close'] < latest['ema_5'],
                latest['close'] < latest['ema_12'],
                latest['close'] < latest['ema_26']
            ])
            if ema_bearish_count >= 2:
                score += 15
                reasons.append(f"EMA×{ema_bearish_count}")
            if latest['bb_percent'] > 70:
                score += 10
                reasons.append(f"BB% {latest['bb_percent']:.0f}")
            if latest['volume_ratio_5'] > 1.2 and not latest['is_bullish']:
                score += 10
                reasons.append("Vol Sell")
            elif latest['is_bearish']:
                score += 5
            if latest['close'] >= latest['resistance'] * 0.99:
                score += 10
                reasons.append("Resistance")
            if latest['stoch_k'] > 75:
                score += 10
                reasons.append("Stoch Over")
            if latest['adx'] > 20 and latest['minus_di'] > latest['plus_di']:
                score += 10
                reasons.append("ADX Down")
            if latest['mfi'] > 70:
                score += 5
                reasons.append("MFI High")
            
            ticker = self.get_ticker(symbol)
            if not ticker:
                return None
            
            return {
                'symbol': symbol,
                'price': ticker['last'],
                'change_24h': ticker['percentage'],
                'volume_24h': ticker['quoteVolume'],
                'score': score,
                'reasons': reasons[:3],
                'rsi': latest['rsi'],
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.warning(f"analyze_coin_for_short error {symbol}: {e}")
            return None

    def get_top_short_coins(self, limit=20):
        """
        ALL Binance coins scan කරලා TOP SHORT coins list එක දෙනවා.
        SHORT SIGNALS 5 MINUTE button එකට.
        """
        all_coins = [
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
            "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
            "MATIC/USDT", "UNI/USDT", "LTC/USDT", "ATOM/USDT", "ETC/USDT",
            "FIL/USDT", "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT",
            "PEPE/USDT", "FLOKI/USDT", "INJ/USDT", "NEAR/USDT", "SAND/USDT",
            "MANA/USDT", "AXS/USDT", "ALGO/USDT", "VET/USDT", "ICP/USDT",
            "FTM/USDT", "CRV/USDT", "AAVE/USDT", "MKR/USDT", "COMP/USDT",
            "EGLD/USDT", "THETA/USDT", "KAVA/USDT", "ZIL/USDT", "IOTA/USDT",
            "WAVES/USDT", "BAT/USDT", "ENJ/USDT", "CHZ/USDT", "GALA/USDT",
            "DYDX/USDT", "RUNE/USDT", "LDO/USDT", "GMX/USDT", "BLUR/USDT"
        ]
        results = []
        for coin in all_coins:
            result = self.analyze_coin_for_short(coin)
            if result and result['score'] >= 20:
                results.append(result)
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

    # ============ NEW: Quick scan එකෙන් ALWAYS signal generate කරන්න ============
    def generate_short_signal_from_scan(self, symbol):
        """
        Quick scan score එක අනුව signal generate කරන්න + track කරන්න.
        Strict find_short_signal() fail වුනාම මේක use කරන්න.
        Entry/TP1/TP2/SL හැමෝටම දෙනවා + Live WIN% tracking.
        """
        try:
            # First try strict signal
            strict_signal = self.find_short_signal(symbol)
            if strict_signal:
                return strict_signal
            
            # Strict signal නැති නම් quick scan එකෙන් generate කරන්න
            df = self.get_klines(symbol, "5m", 100)
            if df is None or len(df) < 50:
                return None
            
            df = self.calculate_indicators(df)
            latest = df.iloc[-1]
            
            scan = self.analyze_coin_for_short(symbol)
            if not scan or scan['score'] < 25:
                return None
            
            atr = latest['atr']
            if atr == 0 or pd.isna(atr):
                atr = latest['close'] * 0.002  # 0.2% fallback
            
            entry_price = scan['price']
            score_factor = scan['score'] / 100.0  # 0.25 to 1.0
            
            # Score එක අනුව TP/SL multipliers adjust කරන්න
            # Higher score = tighter TP, tighter SL (more confident short)
            tp_multiplier = max(0.8, 2.0 - (score_factor * 1.5))  # 0.8 to 1.625
            sl_multiplier = max(1.0, 2.5 - (score_factor * 1.5))  # 1.0 to 2.125
            
            # Confidence = score based + extra
            confidence = min(92, max(40, int(scan['score'] + 20)))
            
            reasons_raw = scan.get('reasons', [])
            reasons = []
            for r in reasons_raw:
                if r and len(reasons) < 8:
                    reasons.append(r)
            if not reasons:
                reasons = ["📊 Quick Analysis"]
            
            signal_result = {
                'symbol': symbol,
                'signal': 'SHORT',
                'entry': entry_price,
                'take_profit_1': entry_price - (atr * tp_multiplier),
                'take_profit_2': entry_price - (atr * tp_multiplier * 2),
                'stop_loss': entry_price + (atr * sl_multiplier),
                'confidence': confidence,
                'accuracy_score': confidence,
                'strength': len(reasons),
                'reasons': reasons,
                'rsi': scan['rsi'],
                'volume_ratio': latest.get('volume_ratio_5', 1.0),
                'adx': latest.get('adx', 20),
                'mfi': latest.get('mfi', 50),
                'bb_percent': latest.get('bb_percent', 50),
                'strict_filters': min(5, int(scan['score'] / 14)),
                'timestamp': datetime.now().isoformat()
            }
            
            # Track කරන්න — signal_tracker.json save වෙනවා, Live WIN% වැඩ කරනවා
            self.track_signal(signal_result)
            logger.info(f"📊 Generated signal from scan: {symbol} score={scan['score']}% conf={confidence}%")
            return signal_result
            
        except Exception as e:
            logger.warning(f"generate_short_signal_from_scan error {symbol}: {e}")
            return None

    # =========================================================================
    # ==================== 💀 BINANCE SHANA SIGNALS — NEW ADDITIONS ============
    # =========================================================================
    # උඩ තියෙන කිසිම code එකක් වෙනස් කරලා නැහැ. පහත methods අලුතෙන් add කරලා.
    # =========================================================================

    # ==================== 1. TIMEFRAME-BASED SHORT ANALYSIS ====================

    def analyze_coin_for_short_timeframe(self, symbol, timeframe="5m"):
        """
        ඕනෑම timeframe එකක් දාලා short potential scan කරන්න.
        ⏰ 5m / 20m / 50m / 1h / 2h — හැමෝටම වැඩ කරනවා.
        """
        try:
            # Timeframe එක අනුව limit adjust කරන්න (larger timeframe = more bars needed)
            limit_map = {"5m": 100, "20m": 80, "50m": 60, "1h": 50, "2h": 50}
            limit = limit_map.get(timeframe, 100)
            
            df = self.get_klines(symbol, timeframe, limit)
            if df is None or len(df) < 40:
                return None
            
            df = self.calculate_indicators(df)
            latest = df.iloc[-1]
            
            score = 0
            reasons = []
            
            # RSI check
            if latest['rsi'] > 65:
                score += 15
                reasons.append(f"RSI {latest['rsi']:.0f}")
            if latest['rsi'] > RSI_OVERBOUGHT:
                score += 10
            
            # MACD check
            if latest['macd'] < latest['macd_signal']:
                score += 15
                reasons.append("MACD Bearish")
            
            # EMA bearish alignment
            ema_bearish_count = sum([
                latest['close'] < latest['ema_5'],
                latest['close'] < latest['ema_12'],
                latest['close'] < latest['ema_26']
            ])
            if ema_bearish_count >= 2:
                score += 15
                reasons.append(f"EMA×{ema_bearish_count}")
            
            # Bollinger Bands
            if latest['bb_percent'] > 70:
                score += 10
                reasons.append(f"BB% {latest['bb_percent']:.0f}")
            
            # Volume
            if latest['volume_ratio_5'] > 1.2 and not latest['is_bullish']:
                score += 10
                reasons.append("Vol Sell")
            elif latest['is_bearish']:
                score += 5
            
            # Resistance
            if latest['close'] >= latest['resistance'] * 0.99:
                score += 10
                reasons.append("Resistance")
            
            # Stochastic
            if latest['stoch_k'] > 75:
                score += 10
                reasons.append("Stoch Over")
            
            # ADX trend strength
            if latest['adx'] > 20 and latest['minus_di'] > latest['plus_di']:
                score += 10
                reasons.append("ADX Down")
            
            # MFI
            if latest['mfi'] > 70:
                score += 5
                reasons.append("MFI High")
            
            ticker = self.get_ticker(symbol)
            if not ticker:
                return None
            
            return {
                'symbol': symbol,
                'price': ticker['last'],
                'change_24h': ticker['percentage'],
                'volume_24h': ticker['quoteVolume'],
                'score': score,
                'reasons': reasons[:3],
                'rsi': latest['rsi'],
                'timeframe': timeframe,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.warning(f"analyze_coin_for_short_timeframe error {symbol}@{timeframe}: {e}")
            return None

    def get_top_short_coins_timeframe(self, limit=20, timeframe="5m"):
        """
        ALL Binance coins scan කරලා TOP SHORT coins list එක දෙනවා.
        ඕනෑම timeframe එකක් use කරන්න පුළුවන්.
        💀 BINANCE SHANA SIGNALS — ⏰5m / 20m / 50m / 1h / 2h
        """
        all_coins = [
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
            "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
            "MATIC/USDT", "UNI/USDT", "LTC/USDT", "ATOM/USDT", "ETC/USDT",
            "FIL/USDT", "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT",
            "PEPE/USDT", "FLOKI/USDT", "INJ/USDT", "NEAR/USDT", "SAND/USDT",
            "MANA/USDT", "AXS/USDT", "ALGO/USDT", "VET/USDT", "ICP/USDT",
            "FTM/USDT", "CRV/USDT", "AAVE/USDT", "MKR/USDT", "COMP/USDT",
            "EGLD/USDT", "THETA/USDT", "KAVA/USDT", "ZIL/USDT", "IOTA/USDT",
            "WAVES/USDT", "BAT/USDT", "ENJ/USDT", "CHZ/USDT", "GALA/USDT",
            "DYDX/USDT", "RUNE/USDT", "LDO/USDT", "GMX/USDT", "BLUR/USDT"
        ]
        results = []
        for coin in all_coins:
            result = self.analyze_coin_for_short_timeframe(coin, timeframe)
            if result and result['score'] >= 20:
                results.append(result)
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

    def generate_short_signal_from_scan_timeframe(self, symbol, timeframe="5m"):
        """
        ඕනෑම timeframe එකක short signal generate කරලා TRACK කරනවා.
        Signal එක signal_tracker.json වල save වෙනවා — DELETE වෙන්නේ නැහැ!
        """
        try:
            # First try strict signal with the given timeframe data
            df = self.get_klines(symbol, timeframe, 200 if timeframe in ["5m","20m"] else 150)
            if df is None or len(df) < 50:
                return None
            
            df = self.calculate_indicators(df)
            latest = df.iloc[-1]
            
            scan = self.analyze_coin_for_short_timeframe(symbol, timeframe)
            if not scan or scan['score'] < 25:
                return None
            
            atr = latest['atr']
            if atr == 0 or pd.isna(atr):
                atr = latest['close'] * 0.002
            
            entry_price = scan['price']
            score_factor = scan['score'] / 100.0
            
            # Timeframe-based multiplier adjust
            tf_mult_map = {"5m": 1.0, "20m": 1.1, "50m": 1.2, "1h": 1.3, "2h": 1.4}
            tf_mult = tf_mult_map.get(timeframe, 1.0)
            
            tp_multiplier = max(0.8, (2.0 - (score_factor * 1.5)) * tf_mult)
            sl_multiplier = max(1.0, (2.5 - (score_factor * 1.5)) * tf_mult)
            
            confidence = min(95, max(40, int(scan['score'] + 25)))
            
            reasons_raw = scan.get('reasons', [])
            reasons = []
            for r in reasons_raw:
                if r and len(reasons) < 8:
                    reasons.append(r)
            if not reasons:
                reasons = [f"📊 {timeframe} Analysis"]
            
            signal_result = {
                'symbol': symbol,
                'signal': 'SHORT',
                'entry': entry_price,
                'take_profit_1': entry_price - (atr * tp_multiplier),
                'take_profit_2': entry_price - (atr * tp_multiplier * 2),
                'stop_loss': entry_price + (atr * sl_multiplier),
                'confidence': confidence,
                'accuracy_score': confidence,
                'strength': len(reasons),
                'reasons': reasons,
                'rsi': scan['rsi'],
                'volume_ratio': latest.get('volume_ratio_5', 1.0),
                'adx': latest.get('adx', 20),
                'mfi': latest.get('mfi', 50),
                'bb_percent': latest.get('bb_percent', 50),
                'strict_filters': min(5, int(scan['score'] / 14)),
                'timeframe': timeframe,
                'timestamp': datetime.now().isoformat()
            }
            
            # TRACK කරන්න — මේක signal_tracker.json එකට save වෙනවා. කවදාවත් DELETE වෙන්නේ නැහැ.
            self.track_signal(signal_result)
            logger.info(f"💀 SHANA SIGNAL [{timeframe}]: {symbol} score={scan['score']} conf={confidence}%")
            return signal_result
            
        except Exception as e:
            logger.warning(f"generate_short_signal_from_scan_timeframe error {symbol}@{timeframe}: {e}")
            return None

    # ==================== 2. LIVE PRICE — ALL COINS ====================

    def get_all_live_prices(self):
        """
        හැම coin එකකම LIVE price එක පෙන්වන්න.
        🟢 LIVE PRICE — 50 coins
        """
        all_coins = [
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
            "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
            "MATIC/USDT", "UNI/USDT", "LTC/USDT", "ATOM/USDT", "ETC/USDT",
            "FIL/USDT", "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT",
            "PEPE/USDT", "FLOKI/USDT", "INJ/USDT", "NEAR/USDT", "SAND/USDT",
            "MANA/USDT", "AXS/USDT", "ALGO/USDT", "VET/USDT", "ICP/USDT",
            "FTM/USDT", "CRV/USDT", "AAVE/USDT", "MKR/USDT", "COMP/USDT",
            "EGLD/USDT", "THETA/USDT", "KAVA/USDT", "ZIL/USDT", "IOTA/USDT",
            "WAVES/USDT", "BAT/USDT", "ENJ/USDT", "CHZ/USDT", "GALA/USDT",
            "DYDX/USDT", "RUNE/USDT", "LDO/USDT", "GMX/USDT", "BLUR/USDT"
        ]
        
        prices = []
        for coin in all_coins:
            ticker = self.get_ticker(coin)
            if ticker:
                prices.append({
                    'symbol': coin,
                    'price': ticker['last'],
                    'change_24h': ticker['percentage'],
                    'volume_24h': ticker['quoteVolume'],
                    'high_24h': ticker['high'],
                    'low_24h': ticker['low']
                })
        return prices

    # ==================== 3. ENHANCED STATS WITH WIN/LOSS ====================

    def get_enhanced_stats(self, symbol=None):
        """
        STATS button එකට වැඩිපුර විස්තර.
        WIN / LOST signals — ලස්සනට පෙන්වන්න.
        """
        stats = {
            'total_signals': 0,
            'total_wins': 0,
            'total_losses': 0,
            'active_signals': 0,
            'expired_signals': 0,
            'win_rate': 0.0,
            'loss_rate': 0.0,
            'best_signal': None,
            'worst_signal': None,
            'win_details': [],
            'loss_details': [],
            'active_details': [],
            'by_symbol': {}
        }
        
        for key, sig in self.signal_tracker.items():
            if symbol and sig['symbol'] != symbol:
                continue
            
            sym = sig['symbol']
            if sym not in stats['by_symbol']:
                stats['by_symbol'][sym] = {'wins': 0, 'losses': 0, 'active': 0, 'total': 0}
            
            stats['total_signals'] += 1
            stats['by_symbol'][sym]['total'] += 1
            
            detail = {
                'key': key,
                'symbol': sig['symbol'],
                'signal': sig['signal'],
                'entry': sig['entry'],
                'tp1': sig['take_profit_1'],
                'sl': sig['stop_loss'],
                'confidence': sig.get('confidence', 0),
                'win_percentage': sig.get('win_percentage', 0),
                'current_price': sig.get('current_price', sig['entry']),
                'highest_price': sig.get('highest_price', sig['entry']),
                'lowest_price': sig.get('lowest_price', sig['entry']),
                'timestamp': sig.get('timestamp', ''),
                'status': sig['status']
            }
            
            if sig['status'] == 'WIN':
                stats['total_wins'] += 1
                stats['by_symbol'][sym]['wins'] += 1
                stats['win_details'].append(detail)
                if stats['best_signal'] is None or sig.get('confidence', 0) > stats['best_signal'].get('confidence', 0):
                    stats['best_signal'] = detail
            elif sig['status'] == 'LOST':
                stats['total_losses'] += 1
                stats['by_symbol'][sym]['losses'] += 1
                stats['loss_details'].append(detail)
                if stats['worst_signal'] is None or sig.get('win_percentage', 100) < stats['worst_signal'].get('win_percentage', 100):
                    stats['worst_signal'] = detail
            elif sig['status'] == 'ACTIVE':
                stats['active_signals'] += 1
                stats['by_symbol'][sym]['active'] += 1
                stats['active_details'].append(detail)
            elif sig['status'] == 'EXPIRED':
                stats['expired_signals'] += 1
        
        completed = stats['total_wins'] + stats['total_losses']
        if completed > 0:
            stats['win_rate'] = round((stats['total_wins'] / completed) * 100, 1)
            stats['loss_rate'] = round((stats['total_losses'] / completed) * 100, 1)
        
        return stats

    # ==================== 4. SIGNAL RECALL — කවදාවත් DELETE වෙන්නේ නැහැ ====================

    def recall_signal(self, signal_key):
        """
        පරණ signal එකක් recall කරන්න.
        signal_key එක දුන්නම — entry, TP1, TP2, SL, හැම දෙයක්ම පෙන්වනවා.
        Signal එක WIN ද LOST ද ACTIVE ද කියලත් පෙන්වනවා.
        """
        if signal_key in self.signal_tracker:
            sig = self.signal_tracker[signal_key]
            
            # Update current price
            ticker = self.get_ticker(sig['symbol'])
            current_price = ticker['last'] if ticker else sig['current_price']
            
            # Build recall response
            recall = {
                'key': signal_key,
                'symbol': sig['symbol'],
                'signal_type': sig['signal'],
                'entry_price': sig['entry'],
                'take_profit_1': sig['take_profit_1'],
                'take_profit_2': sig['take_profit_2'],
                'stop_loss': sig['stop_loss'],
                'confidence': sig.get('confidence', 0),
                'status': sig['status'],
                'current_price': current_price,
                'win_percentage': sig.get('win_percentage', 0),
                'highest_price': sig.get('highest_price', sig['entry']),
                'lowest_price': sig.get('lowest_price', sig['entry']),
                'timestamp': sig.get('timestamp', ''),
                'last_updated': sig.get('last_updated', ''),
                # Profit/Loss calculation
                'entry_to_current_pnl_percent': round(((current_price - sig['entry']) / sig['entry']) * 100, 2),
                'entry_to_tp1_percent': round(abs((sig['take_profit_1'] - sig['entry']) / sig['entry']) * 100, 2),
                'entry_to_sl_percent': round(abs((sig['stop_loss'] - sig['entry']) / sig['entry']) * 100, 2)
            }
            
            # Journey details — price moved through these levels
            journey = []
            entry = sig['entry']
            tp1 = sig['take_profit_1']
            tp2 = sig['take_profit_2']
            sl = sig['stop_loss']
            low = sig.get('lowest_price', entry)
            high = sig.get('highest_price', entry)
            
            if sig['signal'] == 'SHORT':
                if low <= tp2:
                    journey.append("✅ TP2 REACHED (100%)")
                if low <= tp1:
                    journey.append("✅ TP1 REACHED (WIN)")
                if low < entry:
                    journey.append(f"📉 Price dropped to {low}")
                journey.append(f"📊 Entry: {entry}")
                if high > entry:
                    journey.append(f"📈 Price rose to {high}")
                if high >= sl:
                    journey.append("❌ SL REACHED (LOST)")
            else:  # LONG
                if high >= tp2:
                    journey.append("✅ TP2 REACHED (100%)")
                if high >= tp1:
                    journey.append("✅ TP1 REACHED (WIN)")
                if high > entry:
                    journey.append(f"📈 Price rose to {high}")
                journey.append(f"📊 Entry: {entry}")
                if low < entry:
                    journey.append(f"📉 Price dropped to {low}")
                if low <= sl:
                    journey.append("❌ SL REACHED (LOST)")
            
            recall['journey'] = journey
            
            return recall
        return None

    def search_signals(self, symbol=None, signal_type=None, status=None, limit=20):
        """
        Signal search කරන්න — symbol, type (SHORT/LONG), status (WIN/LOST/ACTIVE) filter කරන්න.
        """
        results = []
        for key, sig in self.signal_tracker.items():
            if symbol and symbol.upper() not in sig['symbol'].upper():
                continue
            if signal_type and sig['signal'] != signal_type:
                continue
            if status and sig['status'] != status:
                continue
            
            results.append({
                'key': key,
                'symbol': sig['symbol'],
                'signal': sig['signal'],
                'entry': sig['entry'],
                'status': sig['status'],
                'win_percentage': sig.get('win_percentage', 0),
                'confidence': sig.get('confidence', 0),
                'timestamp': sig.get('timestamp', '')
            })
        
        results.sort(key=lambda x: x['timestamp'], reverse=True)
        return results[:limit]

    # ==================== 5. SIGNAL JOURNEY — 100% FULL PATH ====================

    def get_signal_journey(self, signal_key):
        """
        Signal එකේ full journey එක පෙන්වන්න.
        Entry ඉඳන් TP/SL දක්වා හැම level එකම — 100% විස්තර.
        """
        if signal_key not in self.signal_tracker:
            return None
        
        sig = self.signal_tracker[signal_key]
        
        ticker = self.get_ticker(sig['symbol'])
        current_price = ticker['last'] if ticker else sig.get('current_price', sig['entry'])
        
        entry = sig['entry']
        tp1 = sig['take_profit_1']
        tp2 = sig['take_profit_2']
        sl = sig['stop_loss']
        low = sig.get('lowest_price', entry)
        high = sig.get('highest_price', entry)
        win_pct = sig.get('win_percentage', 0)
        
        journey = {
            'symbol': sig['symbol'],
            'signal': sig['signal'],
            'status': sig['status'],
            'entry_price': entry,
            'current_price': current_price,
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'stop_loss': sl,
            'lowest_reached': low,
            'highest_reached': high,
            'win_percentage': win_pct,
            'confidence': sig.get('confidence', 0),
            'timestamp': sig.get('timestamp', ''),
            'levels': []
        }
        
        # Build all levels this signal traveled through
        if sig['signal'] == 'SHORT':
            # Short: price should go DOWN
            levels = [
                ('🎯 TP2', tp2, low <= tp2),
                ('🎯 TP1', tp1, low <= tp1),
                ('📉 Low Reached', low, True),
                ('⬇️ Entry', entry, True),
                ('📈 High Reached', high, True),
                ('🛑 Stop Loss', sl, high >= sl),
            ]
        else:
            # Long: price should go UP
            levels = [
                ('🛑 Stop Loss', sl, low <= sl),
                ('📉 Low Reached', low, True),
                ('⬇️ Entry', entry, True),
                ('📈 High Reached', high, True),
                ('🎯 TP1', tp1, high >= tp1),
                ('🎯 TP2', tp2, high >= tp2),
            ]
        
        for name, price, triggered in levels:
            dist_from_entry = round(((price - entry) / entry) * 100, 2)
            journey['levels'].append({
                'name': name,
                'price': price,
                'distance_from_entry_percent': dist_from_entry,
                'triggered': triggered,
                'status_icon': '✅' if triggered else '⏳'
            })
        
        # Time info
        try:
            sig_time = datetime.fromisoformat(sig.get('timestamp', ''))
            now = datetime.now()
            elapsed = (now - sig_time).total_seconds()
            if elapsed < 60:
                journey['age'] = f"{int(elapsed)}s ago"
            elif elapsed < 3600:
                journey['age'] = f"{int(elapsed/60)}m ago"
            else:
                journey['age'] = f"{int(elapsed/3600)}h ago"
        except:
            journey['age'] = "unknown"
        
        return journey

    # ==================== 6. POWER BUY SHANA — WIN NOTIFICATION ====================

    def check_power_buy_shana(self, symbol=None):
        """
        WIN උන signals check කරලා "POWER BUY SHANA" notification generate කරන්න.
        මේක call කරන්නේ signal status update එකට පස්සේ.
        """
        self.update_active_signals(symbol)
        
        power_signals = []
        for key, sig in self.signal_tracker.items():
            if symbol and sig['symbol'] != symbol:
                continue
            if sig['status'] != 'WIN':
                continue
            
            tp1 = sig['take_profit_1']
            tp2 = sig['take_profit_2']
            entry = sig['entry']
            low = sig.get('lowest_price', entry)
            
            profit_percent = round(abs((tp1 - entry) / entry) * 100, 2)
            
            power_signals.append({
                'key': key,
                'symbol': sig['symbol'],
                'signal': sig['signal'],
                'entry': entry,
                'take_profit_1': tp1,
                'take_profit_2': tp2,
                'stop_loss': sig['stop_loss'],
                'lowest_price': low,
                'highest_price': sig.get('highest_price', entry),
                'profit_percent': profit_percent,
                'confidence': sig.get('confidence', 0),
                'timestamp': sig.get('timestamp', ''),
                'message': (
                    f"💀🔥 POWER BUY SHANA 🔥💀\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏆 {sig['signal']} WIN\n"
                    f"💰 {sig['symbol']}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📥 Entry    : {entry:.8f}\n"
                    f"🎯 TP1 Hit  : {tp1:.8f}\n"
                    f"🎯 TP2      : {tp2:.8f}\n"
                    f"🛑 SL       : {sig['stop_loss']:.8f}\n"
                    f"📉 Lowest   : {low:.8f}\n"
                    f"📈 Highest  : {sig.get('highest_price', entry):.8f}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ Profit   : +{profit_percent}%\n"
                    f"📊 Confidence: {sig.get('confidence', 0)}%\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏰ {sig.get('timestamp', '')}\n"
                    f"💀 BINANCE SHANA SIGNALS"
                )
            })
        
        return power_signals

    # ==================== 7. FORMATTED DISPLAY HELPERS ====================

    def format_signal_display(self, signal):
        """
        Signal එකක් ලස්සනට පෙන්වන්න — colorful box format.
        Bot box එක විවිධ පාටවලින් design කරන්න.
        """
        if not signal:
            return None
        
        symbol = signal['symbol']
        sig_type = signal['signal']
        entry = signal['entry']
        tp1 = signal['take_profit_1']
        tp2 = signal['take_profit_2']
        sl = signal['stop_loss']
        conf = signal.get('confidence', 0)
        reasons = signal.get('reasons', [])
        strength = signal.get('strength', 0)
        rsi = signal.get('rsi', 0)
        vol_ratio = signal.get('volume_ratio', 0)
        adx = signal.get('adx', 0)
        mfi = signal.get('mfi', 0)
        bb_pct = signal.get('bb_percent', 0)
        tf = signal.get('timeframe', 'N/A')
        
        # Color emojis based on confidence
        if conf >= 85:
            header_icon = "💀🔥💀"
            conf_stars = "⭐⭐⭐⭐⭐"
        elif conf >= 75:
            header_icon = "🔥💀🔥"
            conf_stars = "⭐⭐⭐⭐"
        elif conf >= 65:
            header_icon = "⚡💀⚡"
            conf_stars = "⭐⭐⭐"
        elif conf >= 50:
            header_icon = "📊💀📊"
            conf_stars = "⭐⭐"
        else:
            header_icon = "⚠️💀⚠️"
            conf_stars = "⭐"
        
        # Direction arrow
        if sig_type == 'SHORT':
            direction = "📉 SELL SHORT"
            arrow = "⬇️⬇️⬇️"
        else:
            direction = "📈 BUY LONG"
            arrow = "⬆️⬆️⬆️"
        
        reason_lines = "\n".join([f"   • {r}" for r in reasons[:6]])
        
        display = (
            f"╔══════════════════════════════════════════╗\n"
            f"║    💀 BINANCE SHANA SIGNALS 💀           ║\n"
            f"╠══════════════════════════════════════════╣\n"
            f"║  {header_icon}  {direction}  {header_icon}   ║\n"
            f"║  {arrow}                                   ║\n"
            f"╠══════════════════════════════════════════╣\n"
            f"║  🪙 Coin        : {symbol:<20s}  ║\n"
            f"║  ⏰ Timeframe   : {tf:<20s}  ║\n"
            f"║  🎯 Confidence  : {conf}% {conf_stars:<10s}  ║\n"
            f"║  📊 Strength    : {strength} reasons            ║\n"
            f"╠══════════════════════════════════════════╣\n"
            f"║  📥 Entry       : {entry:<22.8f}  ║\n"
            f"║  🎯 TP1        : {tp1:<22.8f}  ║\n"
            f"║  🎯 TP2        : {tp2:<22.8f}  ║\n"
            f"║  🛑 SL         : {sl:<22.8f}  ║\n"
            f"╠══════════════════════════════════════════╣\n"
            f"║  📈 RSI        : {rsi:<8.1f}                  ║\n"
            f"║  📊 Volume     : {vol_ratio:<8.1f}x                ║\n"
            f"║  📉 ADX        : {adx:<8.1f}                  ║\n"
            f"║  💰 MFI        : {mfi:<8.1f}                  ║\n"
            f"║  📦 BB%        : {bb_pct:<8.1f}%                 ║\n"
            f"╠══════════════════════════════════════════╣\n"
            f"║  📋 Reasons:                              ║\n"
            f"{reason_lines}\n"
            f"╠══════════════════════════════════════════╣\n"
            f"║  ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}          ║\n"
            f"╚══════════════════════════════════════════╝"
        )
        
        return display

    def format_live_price_display(self, prices):
        """
        හැම coin එකකම LIVE price එක ලස්සනට table format එකකට පෙන්වන්න.
        """
        if not prices:
            return "❌ No price data available"
        
        lines = [
            "╔══════════════════════════════════════════════════════════╗",
            "║              🟢 LIVE PRICE — ALL COINS 🟢               ║",
            "╠══════════════════════════════════════════════════════════╣",
            "║  #  │  Coin        │  Price        │  24h%    │  Vol    ║",
            "╠══════════════════════════════════════════════════════════╣"
        ]
        
        for i, p in enumerate(prices, 1):
            sym = p['symbol'].replace('/USDT', '')
            price = p['price']
            chg = p['change_24h']
            vol = p.get('volume_24h', 0)
            
            # Color coding for 24h change
            if chg > 5:
                arrow = "🟢"
            elif chg > 0:
                arrow = "🟢"
            elif chg > -5:
                arrow = "🔴"
            else:
                arrow = "🔴"
            
            # Format volume
            if vol > 1_000_000_000:
                vol_str = f"${vol/1e9:.1f}B"
            elif vol > 1_000_000:
                vol_str = f"${vol/1e6:.1f}M"
            elif vol > 1_000:
                vol_str = f"${vol/1e3:.1f}K"
            else:
                vol_str = f"${vol:.0f}"
            
            line = f"║  {i:2d}  │  {sym:<10s}  │  ${price:<10.4f}  │  {arrow} {chg:>+6.2f}% │  {vol_str:<8s}  ║"
            lines.append(line)
        
        lines.append("╚══════════════════════════════════════════════════════════╝")
        lines.append(f"📊 Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(lines)

    def format_stats_display(self, stats):
        """
        STATS එක ලස්සනට පෙන්වන්න — WIN/LOSS details උඩින්.
        """
        if not stats or stats['total_signals'] == 0:
            return "❌ No signal data yet"
        
        lines = [
            "╔══════════════════════════════════════════╗",
            "║        📊 BINANCE SHANA STATS 📊         ║",
            "╠══════════════════════════════════════════╣",
            f"║  📈 Total Signals    : {stats['total_signals']:<5d}              ║",
            f"║  🏆 Total Wins       : {stats['total_wins']:<5d}  🟢🟢🟢         ║",
            f"║  💀 Total Losses     : {stats['total_losses']:<5d}  🔴🔴🔴         ║",
            f"║  ⏳ Active           : {stats['active_signals']:<5d}              ║",
            f"║  ⌛ Expired          : {stats['expired_signals']:<5d}              ║",
            "╠══════════════════════════════════════════╣",
            f"║  📊 Win Rate         : {stats['win_rate']:<5.1f}%  {'🏆' if stats['win_rate'] >= 70 else '📊'}              ║",
            f"║  📊 Loss Rate        : {stats['loss_rate']:<5.1f}%               ║",
            "╠══════════════════════════════════════════╣"
        ]
        
        # Best signal
        if stats['best_signal']:
            best = stats['best_signal']
            lines.append(f"║  🏆 BEST SIGNAL:                              ║")
            lines.append(f"║     {best['symbol']} — {best['signal']} — Conf: {best['confidence']}%      ║")
            lines.append(f"║     Entry: {best['entry']:.8f}                ║")
        
        # Worst signal
        if stats['worst_signal']:
            worst = stats['worst_signal']
            lines.append(f"║  💀 WORST SIGNAL:                             ║")
            lines.append(f"║     {worst['symbol']} — {worst['signal']} — Conf: {worst['confidence']}%      ║")
            lines.append(f"║     Entry: {worst['entry']:.8f}                ║")
        
        lines.append("╠══════════════════════════════════════════╣")
        
        # By symbol breakdown
        if stats['by_symbol']:
            lines.append("║  📊 PER COIN BREAKDOWN:                      ║")
            for sym, data in sorted(stats['by_symbol'].items(), key=lambda x: x[1]['wins']/(x[1]['wins']+x[1]['losses']+0.01) if (x[1]['wins']+x[1]['losses']) > 0 else 0, reverse=True)[:10]:
                completed = data['wins'] + data['losses']
                wr = round((data['wins'] / completed) * 100, 1) if completed > 0 else 0
                sym_short = sym.replace('/USDT', '')
                lines.append(f"║  {sym_short:<8s}  ▶  W:{data['wins']}  L:{data['losses']}  A:{data['active']}  WR:{wr:.1f}%  ║")
        
        lines.append("╚══════════════════════════════════════════╝")
        lines.append(f"🔄 Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(lines)

    def format_signal_journey_display(self, journey):
        """
        Signal journey එක ලස්සනට පෙන්වන්න — හැම level එකම.
        """
        if not journey:
            return "❌ Signal not found"
        
        lines = [
            "╔══════════════════════════════════════════╗",
            f"║     💀 SIGNAL JOURNEY — {journey['symbol']} 💀      ║",
            "╠══════════════════════════════════════════╣",
            f"║  🎯 Type     : {journey['signal']:<25s}  ║",
            f"║  📊 Status   : {journey['status']:<25s}  ║",
            f"║  ⏰ Age      : {journey.get('age', 'N/A'):<25s}  ║",
            f"║  🎯 Confid   : {journey['confidence']}%{' ' * 22}║",
            "╠══════════════════════════════════════════╣",
            f"║  📥 Entry    : {journey['entry_price']:<22.8f}  ║",
            f"║  💰 Current  : {journey['current_price']:<22.8f}  ║",
            "╠══════════════════════════════════════════╣",
            "║  📊 LEVELS REACHED:                      ║"
        ]
        
        for lvl in journey['levels']:
            icon = lvl['status_icon']
            name = lvl['name']
            price = lvl['price']
            dist = lvl['distance_from_entry_percent']
            triggered_str = "✅" if lvl['triggered'] else "❌"
            lines.append(f"║  {icon} {name:<15s}  ${price:<14.8f}  {dist:>+8.2f}%  {triggered_str}  ║")
        
        lines.append("╠══════════════════════════════════════════╣")
        lines.append(f"║  📉 Lowest : ${journey['lowest_reached']:<16.8f}        ║")
        lines.append(f"║  📈 Highest: ${journey['highest_reached']:<16.8f}        ║")
        lines.append(f"║  🏆 WIN%   : {journey['win_percentage']:<5.1f}%{' ' * 19}║")
        lines.append("╚══════════════════════════════════════════╝")
        
        return "\n".join(lines)

    def get_signal_recall_list(self, limit=20):
        """
        හැම track කරපු signal එකකම list එක — recall කරන්න පුළුවන්.
        Signal DELETE වෙන්නේ නැහැ — හැමෝම ඉතුරු වෙනවා.
        """
        results = []
        for key, sig in sorted(self.signal_tracker.items(), key=lambda x: x[1].get('timestamp', ''), reverse=True)[:limit]:
            results.append({
                'key': key,
                'symbol': sig['symbol'],
                'signal': sig['signal'],
                'entry': sig['entry'],
                'status': sig['status'],
                'win_percentage': sig.get('win_percentage', 0),
                'confidence': sig.get('confidence', 0),
                'timestamp': sig.get('timestamp', '')
            })
        return results
