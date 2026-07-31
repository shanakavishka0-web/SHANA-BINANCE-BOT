import logging
import json
import time
from datetime import datetime, timedelta
from config import COINS
import requests

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class BinanceAnalyzer:
    def __init__(self, data_file='signal_tracker.json'):
        self.data_file = data_file
        self.signal_tracker = {}
        self.base_url = "https://api.binance.com"
        self.load_signals()

    # ============ DATA PERSISTENCE ============
    def load_signals(self):
        try:
            with open(self.data_file, 'r') as f:
                self.signal_tracker = json.load(f)
            logger.info(f"Loaded {len(self.signal_tracker)} signals from {self.data_file}")
        except (FileNotFoundError, json.JSONDecodeError):
            self.signal_tracker = {}
            logger.info(f"No signal file found, starting fresh")

    def _save_signals(self):
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.signal_tracker, f, indent=2)
            logger.info(f"Saved {len(self.signal_tracker)} signals to {self.data_file}")
        except Exception as e:
            logger.error(f"Save error: {e}")

    # ============ API HELPERS ============
    def _make_request(self, endpoint, params=None):
        try:
            url = f"{self.base_url}{endpoint}"
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"API error {resp.status_code}: {endpoint}")
            return None
        except Exception as e:
            logger.error(f"Request error {endpoint}: {e}")
            return None

    def get_ticker(self, symbol):
        data = self._make_request("/api/v3/ticker/24hr", {"symbol": symbol})
        if data:
            return {
                'symbol': symbol,
                'last': float(data.get('lastPrice', 0)),
                'percentage': float(data.get('priceChangePercent', 0)),
                'volume': float(data.get('volume', 0)),
                'quoteVolume': float(data.get('quoteVolume', 0)),
                'high': float(data.get('highPrice', 0)),
                'low': float(data.get('lowPrice', 0))
            }
        return None

    def get_klines(self, symbol, interval='5m', limit=50):
        data = self._make_request("/api/v3/klines", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        })
        if data:
            klines = []
            for k in data:
                klines.append({
                    'time': k[0],
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5])
                })
            return klines
        return None

    def get_order_book(self, symbol, limit=10):
        data = self._make_request("/api/v3/depth", {"symbol": symbol, "limit": limit})
        if data:
            bids = [[float(b[0]), float(b[1])] for b in data.get('bids', [])]
            asks = [[float(a[0]), float(a[1])] for a in data.get('asks', [])]
            return {'bids': bids, 'asks': asks}
        return None

    def get_recent_trades(self, symbol, limit=10):
        return self._make_request("/api/v3/trades", {"symbol": symbol, "limit": limit})

    def calculate_prices(self, klines):
        if not klines:
            return None, None, None, None, None, None
        opens = [k['open'] for k in klines]
        highs = [k['high'] for k in klines]
        lows = [k['low'] for k in klines]
        closes = [k['close'] for k in klines]
        volumes = [k['volume'] for k in klines]
        times = [k['time'] for k in klines]
        return opens, highs, lows, closes, volumes, times

    def make_decision(self, symbol):
        try:
            klines_15m = self.get_klines(symbol, '15m', 100)
            klines_1h = self.get_klines(symbol, '1h', 100)
            klines_4h = self.get_klines(symbol, '4h', 100)
            if not all([klines_15m, klines_1h, klines_4h]):
                return None

            o15, h15, l15, c15, v15, t15 = self.calculate_prices(klines_15m)
            o1h, h1h, l1h, c1h, v1h, t1h = self.calculate_prices(klines_1h)
            o4h, h4h, l4h, c4h, v4h, t4h = self.calculate_prices(klines_4h)

            ticker = self.get_ticker(symbol)
            if not ticker:
                return None

            current_price = ticker['last']
            change_24h = ticker['percentage']
            volume_24h = ticker['volume']

            short_term_trend = self._sma(c15, 8)[-1] > self._sma(c15, 20)[-1]
            mid_term_trend = self._sma(c1h, 20)[-1] > self._sma(c1h, 50)[-1]
            long_term_trend = self._sma(c4h, 50)[-1] > self._sma(c4h, 200)[-1]

            rsi_15m = self._rsi(c15, 14)[-1]
            rsi_1h = self._rsi(c1h, 14)[-1]
            rsi_4h = self._rsi(c4h, 14)[-1]

            macd_line, signal_line, histogram = self._macd(c1h, 12, 26, 9)
            macd_bullish = histogram[-1] > 0 and histogram[-2] <= 0

            bb_upper, bb_middle, bb_lower = self._bollinger_bands(c15, 20, 2)
            bb_position = (current_price - bb_lower[-1]) / (bb_upper[-1] - bb_lower[-1]) if bb_upper[-1] != bb_lower[-1] else 0.5

            signal_buy = 0
            signal_sell = 0
            confluences = []

            if short_term_trend:
                signal_buy += 1
                confluences.append("15m Trend Bullish")
            else:
                signal_sell += 1
                confluences.append("15m Trend Bearish")

            if mid_term_trend:
                signal_buy += 1
                confluences.append("1h Trend Bullish")
            else:
                signal_sell += 1
                confluences.append("1h Trend Bearish")

            if long_term_trend:
                signal_buy += 1
                confluences.append("4h Trend Bullish")
            else:
                signal_sell += 1
                confluences.append("4h Trend Bearish")

            if rsi_15m < 30 or rsi_1h < 30:
                signal_buy += 2
                confluences.append(f"RSI Oversold ({rsi_1h:.1f})")
            elif rsi_15m > 70 or rsi_1h > 70:
                signal_sell += 2
                confluences.append(f"RSI Overbought ({rsi_1h:.1f})")

            if rsi_1h > 50:
                signal_buy += 1
            else:
                signal_sell += 1

            if macd_bullish:
                signal_buy += 2
                confluences.append("MACD Bullish Cross")
            elif histogram[-1] < 0:
                signal_sell += 1
                confluences.append("MACD Bearish")

            if bb_position < 0.2:
                signal_buy += 1
                confluences.append("Near BB Lower")
            elif bb_position > 0.8:
                signal_sell += 1
                confluences.append("Near BB Upper")

            volume_confirmation = volume_24h > 10000
            if volume_confirmation:
                if change_24h > 0:
                    signal_buy += 1
                    confluences.append("High Volume + Positive")
                else:
                    signal_sell += 1
                    confluences.append("High Volume + Negative")

            total = signal_buy + signal_sell
            buy_ratio = (signal_buy / total) * 100 if total > 0 else 50
            sell_ratio = (signal_sell / total) * 100 if total > 0 else 50

            if buy_ratio > 60:
                decision = "BUY"
                confidence = min(buy_ratio + 10, 95)
            elif sell_ratio > 60:
                decision = "SELL"
                confidence = min(sell_ratio + 10, 95)
            else:
                decision = "NEUTRAL"
                confidence = max(buy_ratio, sell_ratio)

            entry_price = current_price
            atr = self._atr(h15, l15, c15, 14)[-1]
            if decision == "BUY":
                tp1 = entry_price + atr
                tp2 = entry_price + (atr * 2)
                sl = entry_price - (atr * 0.75)
            elif decision == "SELL":
                tp1 = entry_price - atr
                tp2 = entry_price - (atr * 2)
                sl = entry_price + (atr * 0.75)
            else:
                tp1 = tp2 = sl = 0

            result = {
                'symbol': symbol,
                'signal': decision,
                'confidence': round(confidence, 1),
                'entry': round(entry_price, 8),
                'tp1': round(tp1, 8),
                'tp2': round(tp2, 8),
                'sl': round(sl, 8),
                'win_percentage': round(buy_ratio if decision == 'BUY' else sell_ratio, 1),
                'method': 'Multi-Timeframe Analysis',
                'confluences': confluences,
                'rsi_1h': round(rsi_1h, 1),
                'rsi_15m': round(rsi_15m, 1),
                'macd_bullish': macd_bullish,
                'bb_position': round(bb_position, 2),
                'change_24h': round(change_24h, 2),
                'volume_24h': round(volume_24h, 2),
                'timestamp': str(datetime.now()),
                'long_term_trend': 'BULLISH' if long_term_trend else 'BEARISH',
                'mid_term_trend': 'BULLISH' if mid_term_trend else 'BEARISH'
            }

            self._add_journey_entry(symbol, decision, entry_price, tp1, sl, confidence, result['win_percentage'])
            return result

        except Exception as e:
            logger.error(f"Decision error: {e}")
            return None

    def _add_journey_entry(self, symbol, signal, entry, tp1, sl, confidence, win_pct):
        try:
            timestamp = str(datetime.now())
            signal_key = f"{symbol}_{timestamp}"
            self.signal_tracker[signal_key] = {
                'symbol': symbol,
                'signal': signal,
                'entry': entry,
                'tp1': tp1,
                'sl': sl,
                'confidence': confidence,
                'win_percentage': win_pct,
                'status': 'ACTIVE',
                'timestamp': timestamp,
                'history': [
                    {'time': timestamp, 'price': entry, 'action': 'ENTRY'}
                ]
            }
            self._save_signals()
        except Exception as e:
            logger.error(f"Journey add error: {e}")

    def format_signal_journey_display(self, journey):
        if not journey:
            return "No journey data"
        lines = [
            f"SIGNAL JOURNEY: {journey.get('symbol', '')}",
            f"{'='*40}",
            f"Signal: {journey.get('signal', '')}",
            f"Entry: ${journey.get('entry', 0):.8f}",
            f"TP1: ${journey.get('tp1', 0):.8f}",
            f"SL: ${journey.get('sl', 0):.8f}",
            f"Confidence: {journey.get('confidence', 0)}%",
            f"Status: {journey.get('status', '')}",
            f"WIN%: {journey.get('win_percentage', 50):.1f}%",
            f"Time: {journey.get('timestamp', '')[:19]}",
        ]
        if journey.get('history'):
            lines.append(f"{'='*40}")
            for h in journey['history']:
                lines.append(f"  {h.get('time','')[:16]} - ${h.get('price',0):.8f} ({h.get('action','')})")
        return '\n'.join(lines)

    def mark_user_signal(self, symbol, signal_type, entry, timestamp):
        try:
            for key, sig in list(self.signal_tracker.items()):
                if (sig.get('symbol') == symbol and 
                    sig.get('signal') == signal_type and
                    abs(float(sig.get('entry', 0)) - float(entry)) < 0.0001 and
                    str(sig.get('timestamp', ''))[:10] == str(timestamp)[:10]):
                    
                    sig['is_user_signal'] = True
                    sig['user_timestamp'] = str(datetime.now())
                    self._save_signals()
                    logger.info(f"Marked user signal: {symbol} {signal_type}")
                    return True
            
            for key, sig in list(self.signal_tracker.items()):
                if sig.get('symbol') == symbol and sig.get('signal') == signal_type:
                    sig['is_user_signal'] = True
                    sig['user_timestamp'] = str(datetime.now())
                    self._save_signals()
                    logger.info(f"Marked user signal (generic): {symbol} {signal_type}")
                    return True
            
            logger.warning(f"Could not find signal to mark: {symbol} {signal_type}")
            return False
        except Exception as e:
            logger.error(f"mark_user_signal error: {e}")
            return False

    def get_user_stats(self):
        stats = {
            'total_signals': 0, 'total_wins': 0, 'total_losses': 0,
            'active_signals': 0, 'expired_signals': 0,
            'win_rate': 0.0, 'loss_rate': 0.0,
            'best_signal': None, 'worst_signal': None, 'by_symbol': {}
        }
        
        user_signals = {k: v for k, v in self.signal_tracker.items() 
                       if v.get('is_user_signal') == True}
        
        for key, sig in user_signals.items():
            status = sig.get('status', 'ACTIVE')
            stats['total_signals'] += 1
            
            if status == 'WIN':
                stats['total_wins'] += 1
            elif status == 'LOST':
                stats['total_losses'] += 1
            elif status == 'ACTIVE':
                stats['active_signals'] += 1
            elif status == 'EXPIRED':
                stats['expired_signals'] += 1
            
            symbol = sig.get('symbol', 'UNKNOWN')
            if symbol not in stats['by_symbol']:
                stats['by_symbol'][symbol] = {'wins': 0, 'losses': 0, 'active': 0, 'expired': 0}
            if status == 'WIN':
                stats['by_symbol'][symbol]['wins'] += 1
            elif status == 'LOST':
                stats['by_symbol'][symbol]['losses'] += 1
            elif status == 'ACTIVE':
                stats['by_symbol'][symbol]['active'] += 1
            elif status == 'EXPIRED':
                stats['by_symbol'][symbol]['expired'] += 1
            
            if status == 'WIN':
                if stats['best_signal'] is None or sig.get('confidence', 0) > stats['best_signal'].get('confidence', 0):
                    stats['best_signal'] = {
                        'symbol': sig.get('symbol', ''),
                        'signal': sig.get('signal', ''),
                        'entry': sig.get('entry', 0),
                        'tp1': sig.get('take_profit_1', sig.get('tp1', 0)),
                        'confidence': sig.get('confidence', 0)
                    }
            elif status == 'LOST':
                if stats['worst_signal'] is None or sig.get('confidence', 0) > stats['worst_signal'].get('confidence', 0):
                    stats['worst_signal'] = {
                        'symbol': sig.get('symbol', ''),
                        'signal': sig.get('signal', ''),
                        'entry': sig.get('entry', 0),
                        'sl': sig.get('stop_loss', sig.get('sl', 0)),
                        'confidence': sig.get('confidence', 0)
                    }
        
        completed = stats['total_wins'] + stats['total_losses']
        if completed > 0:
            stats['win_rate'] = (stats['total_wins'] / completed) * 100
            stats['loss_rate'] = (stats['total_losses'] / completed) * 100
        
        return stats

    def get_user_recall_list(self, limit=50):
        user_signals = []
        for key, sig in self.signal_tracker.items():
            if sig.get('is_user_signal') == True:
                user_signals.append({
                    'key': key,
                    'symbol': sig.get('symbol', 'UNKNOWN'),
                    'signal': sig.get('signal', 'SHORT'),
                    'entry': sig.get('entry', 0),
                    'confidence': sig.get('confidence', 0),
                    'status': sig.get('status', 'ACTIVE'),
                    'win_percentage': sig.get('win_percentage', 50),
                    'timestamp': sig.get('timestamp', ''),
                })
        
        user_signals.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return user_signals[:limit]

    def _sma(self, values, period):
        sma = []
        for i in range(len(values)):
            if i < period - 1:
                sma.append(None)
            else:
                sma.append(sum(values[i-period+1:i+1]) / period)
        return sma

    def _ema(self, values, period):
        multiplier = 2 / (period + 1)
        ema = [values[0]]
        for i in range(1, len(values)):
            ema.append((values[i] - ema[-1]) * multiplier + ema[-1])
        return ema

    def _rsi(self, values, period=14):
        deltas = [values[i] - values[i-1] for i in range(1, len(values))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[:period]) / period if len(gains) >= period else (sum(gains) / len(gains) if gains else 0)
        avg_loss = sum(losses[:period]) / period if len(losses) >= period else (sum(losses) / len(losses) if losses else 0)
        rsi = [50.0]
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs = 100 if avg_loss == 0 else avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))
        while len(rsi) < len(values):
            rsi.insert(0, 50.0)
        return rsi[:len(values)]

    def _macd(self, values, fast=12, slow=26, signal=9):
        ema_fast = self._ema(values, fast)
        ema_slow = self._ema(values, slow)
        macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(values))]
        signal_line = self._ema(macd_line, signal)
        histogram = [macd_line[i] - signal_line[i] for i in range(len(values))]
        return macd_line, signal_line, histogram

    def _bollinger_bands(self, values, period=20, std_dev=2):
        sma = self._sma(values, period)
        upper = [None] * len(values)
        lower = [None] * len(values)
        for i in range(period - 1, len(values)):
            slice_data = values[i-period+1:i+1]
            mean = sma[i]
            variance = sum((x - mean) ** 2 for x in slice_data) / period
            std = variance ** 0.5
            upper[i] = mean + std_dev * std
            lower[i] = mean - std_dev * std
        return upper, sma, lower

    def _atr(self, high, low, close, period=14):
        tr = [high[0] - low[0]]
        for i in range(1, len(close)):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i-1])
            lc = abs(low[i] - close[i-1])
            tr.append(max(hl, hc, lc))
        atr = []
        atr.append(sum(tr[:period]) / period)
        for i in range(period, len(tr)):
            atr.append((atr[-1] * (period - 1) + tr[i]) / period)
        while len(atr) < len(close):
            atr.insert(0, atr[0])
        return atr[:len(close)]

    # ==================== STATIC HELPERS ====================

    @staticmethod
    def _calc_ema(values, period):
        multiplier = 2 / (period + 1)
        ema = [values[0]]
        for i in range(1, len(values)):
            ema.append((values[i] - ema[-1]) * multiplier + ema[-1])
        return ema

    @staticmethod
    def _calc_sma(values, period):
        sma = []
        for i in range(len(values)):
            if i < period - 1:
                sma.append(None)
            else:
                sma.append(sum(values[i-period+1:i+1]) / period)
        return sma

    @staticmethod
    def _calc_rsi(values, period=14):
        deltas = [values[i] - values[i-1] for i in range(1, len(values))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[:period]) / period if len(gains) >= period else (sum(gains) / len(gains) if gains else 0)
        avg_loss = sum(losses[:period]) / period if len(losses) >= period else (sum(losses) / len(losses) if losses else 0)
        rsi = [50.0]
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs = 100 if avg_loss == 0 else avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))
        while len(rsi) < len(values):
            rsi.insert(0, 50.0)
        return rsi[:len(values)]

    @staticmethod
    def _calc_macd(close, fast=12, slow=26, signal=9):
        ema_fast = BinanceAnalyzer._calc_ema(close, fast)
        ema_slow = BinanceAnalyzer._calc_ema(close, slow)
        macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(close))]
        signal_line = BinanceAnalyzer._calc_ema(macd_line, signal)
        histogram = [macd_line[i] - signal_line[i] for i in range(len(close))]
        return macd_line, signal_line, histogram

    @staticmethod
    def _calc_bollinger_bands(close, period=20, std_dev=2):
        sma = BinanceAnalyzer._calc_sma(close, period)
        upper = [None] * len(close)
        lower = [None] * len(close)
        for i in range(period - 1, len(close)):
            slice_data = close[i-period+1:i+1]
            mean = sma[i]
            variance = sum((x - mean) ** 2 for x in slice_data) / period
            std = variance ** 0.5
            upper[i] = mean + std_dev * std
            lower[i] = mean - std_dev * std
        return upper, sma, lower

    @staticmethod
    def _calc_atr(high, low, close, period=14):
        tr = [high[0] - low[0]]
        for i in range(1, len(close)):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i-1])
            lc = abs(low[i] - close[i-1])
            tr.append(max(hl, hc, lc))
        atr = []
        atr.append(sum(tr[:period]) / period)
        for i in range(period, len(tr)):
            atr.append((atr[-1] * (period - 1) + tr[i]) / period)
        while len(atr) < len(close):
            atr.insert(0, atr[0])
        return atr[:len(close)]

    @staticmethod
    def _calc_stoch_rsi(close, period=14, k_period=3, d_period=3):
        rsi = BinanceAnalyzer._calc_rsi(close, period)
        raw_stoch = [50.0] * len(rsi)
        for i in range(period, len(rsi)):
            slice_rsi = rsi[i-period+1:i+1]
            mn, mx = min(slice_rsi), max(slice_rsi)
            raw_stoch[i] = 50 if mx == mn else ((rsi[i] - mn) / (mx - mn)) * 100
        k_line = [raw_stoch[i] for i in range(len(raw_stoch))]
        for i in range(k_period - 1, len(raw_stoch)):
            k_line[i] = sum(raw_stoch[i-k_period+1:i+1]) / k_period
        d_line = [k_line[i] for i in range(len(k_line))]
        for i in range(d_period - 1, len(k_line)):
            d_line[i] = sum(k_line[i-d_period+1:i+1]) / d_period
        return k_line, d_line, raw_stoch

    @staticmethod
    def _calc_supertrend(high, low, close, period=10, multiplier=3):
        atr = BinanceAnalyzer._calc_atr(high, low, close, period)
        hl2 = [(high[i] + low[i]) / 2 for i in range(len(close))]
        basic_upper = [hl2[i] + multiplier * atr[i] for i in range(len(close))]
        basic_lower = [hl2[i] - multiplier * atr[i] for i in range(len(close))]
        final_upper = [0.0] * len(close)
        final_lower = [0.0] * len(close)
        direction = [1] * len(close)
        final_upper[0], final_lower[0] = basic_upper[0], basic_lower[0]
        for i in range(1, len(close)):
            final_upper[i] = basic_upper[i] if (basic_upper[i] < final_upper[i-1] or close[i-1] > final_upper[i-1]) else final_upper[i-1]
            final_lower[i] = basic_lower[i] if (basic_lower[i] > final_lower[i-1] or close[i-1] < final_lower[i-1]) else final_lower[i-1]
            if direction[i-1] == 1 and close[i] <= final_lower[i]:
                direction[i] = -1
            elif direction[i-1] == -1 and close[i] >= final_upper[i]:
                direction[i] = 1
            else:
                direction[i] = direction[i-1]
        return direction, final_upper, final_lower

    @staticmethod
    def _calc_ichimoku(high, low, close, tenkan=9, kijun=26, senkou_b=52):
        n = len(close)
        tenkan_sen = [None] * n
        kijun_sen = [None] * n
        senkou_a = [None] * n
        senkou_b_arr = [None] * n
        chikou = [None] * n
        for i in range(tenkan - 1, n):
            tenkan_sen[i] = (max(high[i-tenkan+1:i+1]) + min(low[i-tenkan+1:i+1])) / 2
        for i in range(kijun - 1, n):
            kijun_sen[i] = (max(high[i-kijun+1:i+1]) + min(low[i-kijun+1:i+1])) / 2
        for i in range(senkou_b - 1, n):
            senkou_b_arr[i] = (max(high[i-senkou_b+1:i+1]) + min(low[i-senkou_b+1:i+1])) / 2
        for i in range(len(tenkan_sen)):
            if tenkan_sen[i] is not None and kijun_sen[i] is not None:
                senkou_a[i] = (tenkan_sen[i] + kijun_sen[i]) / 2
        for i in range(n):
            chikou[i] = close[i] if i + kijun < n else None
        return tenkan_sen, kijun_sen, senkou_a, senkou_b_arr, chikou

    @staticmethod
    def _calc_mfi(high, low, close, volume, period=14):
        typical = [(high[i] + low[i] + close[i]) / 3 for i in range(len(close))]
        mf = [typical[i] * volume[i] for i in range(len(close))]
        mfi = [50.0] * len(close)
        for i in range(period, len(close)):
            pos_flow = neg_flow = 0
            for j in range(i - period + 1, i + 1):
                if j > i - period + 1:
                    if typical[j] > typical[j-1]:
                        pos_flow += mf[j]
                    else:
                        neg_flow += mf[j]
            if neg_flow == 0:
                mfi[i] = 100
            else:
                mfi[i] = 100 - (100 / (1 + pos_flow / neg_flow))
        return mfi

    @staticmethod
    def _calc_obv(close, volume):
        obv = [0.0] * len(close)
        for i in range(1, len(close)):
            if close[i] > close[i-1]:
                obv[i] = obv[i-1] + volume[i]
            elif close[i] < close[i-1]:
                obv[i] = obv[i-1] - volume[i]
            else:
                obv[i] = obv[i-1]
        return obv

    @staticmethod
    def _calc_cmf(high, low, close, volume, period=20):
        mfm = [((close[i] - low[i]) - (high[i] - close[i])) / (high[i] - low[i]) if high[i] != low[i] else 0 for i in range(len(close))]
        mfv = [mfm[i] * volume[i] for i in range(len(close))]
        cmf = [0.0] * len(close)
        for i in range(period - 1, len(close)):
            sum_mfv = sum(mfv[i-period+1:i+1])
            sum_vol = sum(volume[i-period+1:i+1])
            cmf[i] = sum_mfv / sum_vol if sum_vol != 0 else 0
        return cmf

    @staticmethod
    def _calc_cci(high, low, close, period=20):
        tp = [(high[i] + low[i] + close[i]) / 3 for i in range(len(close))]
        sma_tp = BinanceAnalyzer._calc_sma(tp, period)
        cci = [0.0] * len(close)
        for i in range(period - 1, len(close)):
            mean_dev = sum(abs(tp[j] - sma_tp[i]) for j in range(i-period+1, i+1)) / period
            cci[i] = (tp[i] - sma_tp[i]) / (0.015 * mean_dev) if mean_dev != 0 else 0
        return cci

    @staticmethod
    def _calc_volume_profile(high, low, volume, num_bins=12):
        price_range = max(high) - min(low)
        bin_size = price_range / num_bins if price_range != 0 else 1
        bins = {}
        for i in range(len(high)):
            bin_idx = int((high[i] - min(low)) / bin_size) if bin_size > 0 else 0
            bin_idx = min(bin_idx, num_bins - 1)
            bin_price = min(low) + (bin_idx + 0.5) * bin_size
            if bin_price not in bins:
                bins[bin_price] = 0
            bins[bin_price] += volume[i]
        poc_price = max(bins, key=bins.get) if bins else (high[-1] + low[-1]) / 2
        bin_sz = (max(high) - min(low)) / num_bins if price_range != 0 else 1
        val = poc_price - bin_sz if poc_price - bin_sz >= min(low) else min(low)
        vah = poc_price + bin_sz if poc_price + bin_sz <= max(high) else max(high)
        return {'poc': poc_price, 'value_area_low': val, 'value_area_high': vah, 'bins': bins}

    @staticmethod
    def _calc_pivot_points(high, low, close):
        pp = (high[-1] + low[-1] + close[-1]) / 3
        r1 = 2 * pp - low[-1]
        r2 = pp + (high[-1] - low[-1])
        r3 = high[-1] + 2 * (pp - low[-1])
        s1 = 2 * pp - high[-1]
        s2 = pp - (high[-1] - low[-1])
        s3 = low[-1] - 2 * (high[-1] - pp)
        return {'pp': pp, 'r1': r1, 'r2': r2, 'r3': r3, 's1': s1, 's2': s2, 's3': s3}

    @staticmethod
    def _calc_fib_retracement(high, low):
        rng = max(high) - min(low)
        return {
            '0.0': max(high),
            '0.236': max(high) - 0.236 * rng,
            '0.382': max(high) - 0.382 * rng,
            '0.5': max(high) - 0.5 * rng,
            '0.618': max(high) - 0.618 * rng,
            '0.786': max(high) - 0.786 * rng,
            '1.0': min(low)
        }

    @staticmethod
    def _calc_fvg(high, low, close, lookback=10):
        fvg_signals = []
        for i in range(1, len(close) - 1):
            if low[i+1] > high[i-1]:
                fvg_signals.append({'index': i, 'type': 'BULLISH', 'gap_high': low[i+1], 'gap_low': high[i-1]})
            elif high[i+1] < low[i-1]:
                fvg_signals.append({'index': i, 'type': 'BEARISH', 'gap_high': low[i-1], 'gap_low': high[i+1]})
        return fvg_signals[-lookback:] if len(fvg_signals) > lookback else fvg_signals

    @staticmethod
    def _calc_chop_index(high, low, close, period=14):
        import math
        tr = [high[0] - low[0]]
        for i in range(1, len(close)):
            tr.append(max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])))
        highest = [0.0] * len(close)
        lowest = [0.0] * len(close)
        for i in range(period - 1, len(close)):
            highest[i] = max(high[i-period+1:i+1])
            lowest[i] = min(low[i-period+1:i+1])
        sum_tr = [0.0] * len(close)
        for i in range(period - 1, len(close)):
            sum_tr[i] = sum(tr[i-period+1:i+1])
        chop = [0.0] * len(close)
        for i in range(period - 1, len(close)):
            if highest[i] != lowest[i] and sum_tr[i] != 0:
                ratio = sum_tr[i] / (highest[i] - lowest[i])
                chop[i] = 100 * (math.log10(ratio) / math.log10(period)) if ratio > 0 else 0
            else:
                chop[i] = 50
        return chop

    @staticmethod
    def _calc_connors_rsi(close, period=3, streak_period=2, percentile_period=100):
        rsi = BinanceAnalyzer._calc_rsi(close, period)
        streak = [0] * len(close)
        for i in range(1, len(close)):
            if close[i] > close[i-1]:
                streak[i] = streak[i-1] + 1 if streak[i-1] >= 0 else 1
            elif close[i] < close[i-1]:
                streak[i] = streak[i-1] - 1 if streak[i-1] <= 0 else -1
            else:
                streak[i] = 0
        rsi_streak = BinanceAnalyzer._calc_rsi([float(s) for s in streak], streak_period)
        percentile = [50.0] * len(close)
        for i in range(percentile_period, len(close)):
            count = sum(1 for j in range(i-percentile_period+1, i+1) if close[j] <= close[i])
            percentile[i] = (count / percentile_period) * 100
        crsi = [(rsi[i] + rsi_streak[i] + percentile[i]) / 3 for i in range(len(close))]
        return crsi

    @staticmethod
    def _calc_dpo(close, period=14):
        sma = BinanceAnalyzer._calc_sma(close, period)
        shift = period // 2 + 1
        dpo = [0.0] * len(close)
        for i in range(shift, len(close)):
            if sma[i - shift] is not None:
                dpo[i] = close[i] - sma[i - shift]
        return dpo

    @staticmethod
    def _calc_smi_ergodic(close, period=14, smooth1=3, smooth2=3):
        high_max = [0.0] * len(close)
        low_min = [0.0] * len(close)
        for i in range(period - 1, len(close)):
            high_max[i] = max(close[i-period+1:i+1])
            low_min[i] = min(close[i-period+1:i+1])
        smi_raw = [0.0] * len(close)
        for i in range(period - 1, len(close)):
            if high_max[i] != low_min[i]:
                smi_raw[i] = ((close[i] - low_min[i]) / (high_max[i] - low_min[i]) - 0.5) * 200
        smi = BinanceAnalyzer._calc_ema(smi_raw, smooth1)
        signal = BinanceAnalyzer._calc_ema(smi, smooth2)
        return smi, signal

    @staticmethod
    def _calc_force_index(close, volume, period=13):
        force = [0.0] * len(close)
        for i in range(1, len(close)):
            force[i] = (close[i] - close[i-1]) * volume[i]
        fi = BinanceAnalyzer._calc_ema(force, period)
        return fi

    @staticmethod
    def _calc_nvi(close, volume):
        nvi = [1000.0] * len(close)
        for i in range(1, len(close)):
            if volume[i] < volume[i-1]:
                nvi[i] = nvi[i-1] + ((close[i] - close[i-1]) / close[i-1]) * nvi[i-1]
            else:
                nvi[i] = nvi[i-1]
        return nvi

    @staticmethod
    def _calc_pvi(close, volume):
        pvi = [1000.0] * len(close)
        for i in range(1, len(close)):
            if volume[i] > volume[i-1]:
                pvi[i] = pvi[i-1] + ((close[i] - close[i-1]) / close[i-1]) * pvi[i-1]
            else:
                pvi[i] = pvi[i-1]
        return pvi

    @staticmethod
    def _calc_ad_line(high, low, close, volume):
        ad = [0.0] * len(close)
        for i in range(1, len(close)):
            mfm = ((close[i] - low[i]) - (high[i] - close[i])) / (high[i] - low[i]) if high[i] != low[i] else 0
            ad[i] = ad[i-1] + mfm * volume[i]
        return ad

    @staticmethod
    def _calc_chaikin_volatility(high, low, period=10, ema_period=10):
        hl_range = [high[i] - low[i] for i in range(len(high))]
        ema_range = BinanceAnalyzer._calc_ema(hl_range, ema_period)
        cv = [0.0] * len(high)
        for i in range(period + ema_period - 1, len(high)):
            if ema_range[i - period] != 0:
                cv[i] = ((ema_range[i] - ema_range[i - period]) / ema_range[i - period]) * 100
        return cv

    @staticmethod
    def _calc_standard_error_bands(close, period=20, deviations=2):
        sma = BinanceAnalyzer._calc_sma(close, period)
        upper = [None] * len(close)
        lower = [None] * len(close)
        for i in range(period - 1, len(close)):
            y = close[i-period+1:i+1]
            x = list(range(period))
            n = period
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(x[j] * y[j] for j in range(n))
            sum_x2 = sum(x[j]**2 for j in range(n))
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x**2) if (n * sum_x2 - sum_x**2) != 0 else 0
            intercept = (sum_y - slope * sum_x) / n
            se = (sum((y[j] - (slope * x[j] + intercept))**2 for j in range(n)) / (n - 2)) ** 0.5 if n > 2 else 0
            upper[i] = sma[i] + deviations * se
            lower[i] = sma[i] - deviations * se
        return upper, sma, lower

    @staticmethod
    def _calc_squeeze_momentum(high, low, close, bb_period=20, bb_std=2, kc_period=20, kc_mult=1.5):
        bb_upper, bb_mid, bb_lower = BinanceAnalyzer._calc_bollinger_bands(close, bb_period, bb_std)
        atr = BinanceAnalyzer._calc_atr(high, low, close, kc_period)
        ema = BinanceAnalyzer._calc_ema(close, kc_period)
        kc_upper = [ema[i] + kc_mult * atr[i] for i in range(len(close))]
        kc_lower = [ema[i] - kc_mult * atr[i] for i in range(len(close))]
        squeeze_on = [False] * len(close)
        for i in range(len(close)):
            if bb_lower[i] is not None:
                squeeze_on[i] = bb_lower[i] > kc_lower[i] and bb_upper[i] < kc_upper[i]
        highest_high = [0.0] * len(close)
        lowest_low = [0.0] * len(close)
        for i in range(20, len(close)):
            highest_high[i] = max(high[i-19:i+1])
            lowest_low[i] = min(low[i-19:i+1])
        linreg = [0.0] * len(close)
        for i in range(19, len(close)):
            y = close[i-19:i+1]
            x = list(range(20))
            n = 20
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(x[j] * y[j] for j in range(n))
            sum_x2 = sum(x[j]**2 for j in range(n))
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x**2) if (n * sum_x2 - sum_x**2) != 0 else 0
            linreg[i] = slope * 19 + (sum_y / n)
        momentum = [close[i] - linreg[i] for i in range(len(close))]
        max_mom = max(abs(m) for m in momentum) if any(momentum) else 1
        momentum_norm = [m / max_mom * 100 for m in momentum]
        mom_sma = BinanceAnalyzer._calc_sma(momentum, 2)
        return squeeze_on, momentum_norm, mom_sma

    @staticmethod
    def _calc_hma(values, period=20):
        half_period = period // 2
        sqrt_period = int(period ** 0.5)
        wma_half = []
        for i in range(len(values)):
            if i < half_period - 1:
                wma_half.append(None)
            else:
                weights = sum(j+1 for j in range(half_period))
                wma_half.append(sum(values[i-half_period+1+j] * (j+1) for j in range(half_period)) / weights)
        wma_full = []
        for i in range(len(values)):
            if i < period - 1:
                wma_full.append(None)
            else:
                weights = sum(j+1 for j in range(period))
                wma_full.append(sum(values[i-period+1+j] * (j+1) for j in range(period)) / weights)
        diff = []
        for i in range(len(values)):
            if wma_half[i] is not None and wma_full[i] is not None:
                diff.append(2 * wma_half[i] - wma_full[i])
            else:
                diff.append(None)
        hma = []
        for i in range(len(values)):
            if i < sqrt_period - 1 or diff[i] is None:
                hma.append(None)
            else:
                valid = [d for d in diff[i-sqrt_period+1:i+1] if d is not None]
                if len(valid) == sqrt_period:
                    weights = sum(j+1 for j in range(sqrt_period))
                    hma.append(sum(valid[j] * (j+1) for j in range(sqrt_period)) / weights)
                else:
                    hma.append(None)
        return hma

    @staticmethod
    def _calc_keltner(high, low, close, period=20, multiplier=2):
        ema = BinanceAnalyzer._calc_ema(close, period)
        atr = BinanceAnalyzer._calc_atr(high, low, close, period)
        upper = [ema[i] + multiplier * atr[i] for i in range(len(close))]
        lower = [ema[i] - multiplier * atr[i] for i in range(len(close))]
        return upper, ema, lower

    @staticmethod
    def _calc_donchian(high, low, period=20):
        upper = [0.0] * len(high)
        lower = [0.0] * len(high)
        middle = [0.0] * len(high)
        for i in range(period - 1, len(high)):
            upper[i] = max(high[i-period+1:i+1])
            lower[i] = min(low[i-period+1:i+1])
            middle[i] = (upper[i] + lower[i]) / 2
        return upper, middle, lower

    @staticmethod
    def _calc_parabolic_sar(high, low, acceleration=0.02, max_acceleration=0.2):
        sar = [0.0] * len(high)
        ep = [0.0] * len(high)
        af = [acceleration] * len(high)
        trend = [1] * len(high)
        sar[0] = low[0]
        ep[0] = high[0]
        trend[0] = 1
        for i in range(1, len(high)):
            if trend[i-1] == 1:
                sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
                if low[i] < sar[i]:
                    trend[i] = -1
                    sar[i] = ep[i-1]
                    ep[i] = low[i]
                    af[i] = acceleration
                else:
                    trend[i] = 1
                    if high[i] > ep[i-1]:
                        ep[i] = high[i]
                        af[i] = min(af[i-1] + acceleration, max_acceleration)
                    else:
                        ep[i] = ep[i-1]
                        af[i] = af[i-1]
            else:
                sar[i] = sar[i-1] - af[i-1] * (sar[i-1] - ep[i-1])
                if high[i] > sar[i]:
                    trend[i] = 1
                    sar[i] = ep[i-1]
                    ep[i] = high[i]
                    af[i] = acceleration
                else:
                    trend[i] = -1
                    if low[i] < ep[i-1]:
                        ep[i] = low[i]
                        af[i] = min(af[i-1] + acceleration, max_acceleration)
                    else:
                        ep[i] = ep[i-1]
                        af[i] = af[i-1]
            if trend[i] == 1:
                sar[i] = min(sar[i], low[i-1])
            else:
                sar[i] = max(sar[i], high[i-1])
        return sar, trend

    @staticmethod
    def _calc_mcginley(close, period=20):
        md = [close[0]]
        for i in range(1, len(close)):
            if md[-1] != 0:
                md.append(md[-1] + (close[i] - md[-1]) / (0.6 * period * (close[i] / md[-1]) ** 4))
            else:
                md.append(md[-1] + (close[i] - md[-1]) / period)
        return md

    @staticmethod
    def _calc_dema(values, period=20):
        ema1 = BinanceAnalyzer._calc_ema(values, period)
        ema2 = BinanceAnalyzer._calc_ema(ema1, period)
        dema = [2 * ema1[i] - ema2[i] for i in range(len(values))]
        return dema

    @staticmethod
    def _calc_tema(values, period=20):
        ema1 = BinanceAnalyzer._calc_ema(values, period)
        ema2 = BinanceAnalyzer._calc_ema(ema1, period)
        ema3 = BinanceAnalyzer._calc_ema(ema2, period)
        tema = [3 * ema1[i] - 3 * ema2[i] + ema3[i] for i in range(len(values))]
        return tema

    @staticmethod
    def _calc_awesome_oscillator(high, low, fast=5, slow=34):
        hl_avg = [(high[i] + low[i]) / 2 for i in range(len(high))]
        sma_fast = BinanceAnalyzer._calc_sma(hl_avg, fast)
        sma_slow = BinanceAnalyzer._calc_sma(hl_avg, slow)
        ao = []
        for i in range(len(hl_avg)):
            f = sma_fast[i] if sma_fast[i] is not None else hl_avg[i]
            s = sma_slow[i] if sma_slow[i] is not None else hl_avg[i]
            ao.append(f - s)
        return ao

    @staticmethod
    def _calc_accelerator_oscillator(high, low, fast=5, slow=34):
        ao = BinanceAnalyzer._calc_awesome_oscillator(high, low, fast, slow)
        sma_ao = BinanceAnalyzer._calc_sma(ao, 5)
        ac = []
        for i in range(len(ao)):
            s = sma_ao[i] if sma_ao[i] is not None else ao[i]
            ac.append(ao[i] - s)
        return ac

    @staticmethod
    def _calc_cmo(close, period=14):
        sm = [0.0] * len(close)
        for i in range(1, len(close)):
            sm[i] = close[i] - close[i-1]
        su = [s if s > 0 else 0 for s in sm]
        sd = [-s if s < 0 else 0 for s in sm]
        cmo = [0.0] * len(close)
        for i in range(period, len(close)):
            sum_u = sum(su[i-period+1:i+1])
            sum_d = sum(sd[i-period+1:i+1])
            if sum_u + sum_d != 0:
                cmo[i] = ((sum_u - sum_d) / (sum_u + sum_d)) * 100
        return cmo

    @staticmethod
    def _calc_bollinger_b(close, period=20, std_dev=2):
        upper, mid, lower = BinanceAnalyzer._calc_bollinger_bands(close, period, std_dev)
        b = [0.5] * len(close)
        for i in range(len(close)):
            if upper[i] is not None and lower[i] is not None and upper[i] != lower[i]:
                b[i] = (close[i] - lower[i]) / (upper[i] - lower[i])
        return b

    @staticmethod
    def _calc_bbw(close, period=20, std_dev=2):
        upper, mid, lower = BinanceAnalyzer._calc_bollinger_bands(close, period, std_dev)
        bbw = [0.0] * len(close)
        for i in range(len(close)):
            if upper[i] is not None and lower[i] is not None and mid[i] is not None and mid[i] != 0:
                bbw[i] = (upper[i] - lower[i]) / mid[i]
        return bbw

    def _prepare_ohlcv(self, symbol, interval, limit):
        data = self._make_request("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
        if not data:
            return None, None, None, None, None, None
        open_p = [float(k[1]) for k in data]
        high = [float(k[2]) for k in data]
        low = [float(k[3]) for k in data]
        close = [float(k[4]) for k in data]
        volume = [float(k[5]) for k in data]
        times = [k[0] for k in data]
        return open_p, high, low, close, volume, times

    # ==================== TREND FOLLOWING METHODS (1-12) ====================

    def analyze_ema_50_200(self, symbol, interval='1h', limit=200):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'EMA 50/200', 'num': 1}
        ema50 = self._calc_ema(cl, min(50, len(cl)-1))
        ema200 = self._calc_ema(cl, min(200, len(cl)-1))
        last_50 = ema50[-1] if len(ema50) > 0 else cl[-1]
        last_200 = ema200[-1] if len(ema200) > 0 else cl[-1]
        prev_50 = ema50[-2] if len(ema50) > 1 else last_50
        prev_200 = ema200[-2] if len(ema200) > 1 else last_200
        if prev_50 <= prev_200 and last_50 > last_200:
            return {'signal': 'BUY', 'confidence': 80, 'method': 'EMA 50/200 Golden Cross', 'num': 1}
        elif prev_50 >= prev_200 and last_50 < last_200:
            return {'signal': 'SELL', 'confidence': 80, 'method': 'EMA 50/200 Death Cross', 'num': 1}
        elif last_50 > last_200:
            return {'signal': 'BUY', 'confidence': 40, 'method': 'EMA 50 > 200', 'num': 1}
        else:
            return {'signal': 'SELL', 'confidence': 40, 'method': 'EMA 50 < 200', 'num': 1}

    def analyze_sma_50_200(self, symbol, interval='1h', limit=200):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'SMA 50/200', 'num': 2}
        sma50 = self._calc_sma(cl, min(50, len(cl)-1))
        sma200 = self._calc_sma(cl, min(200, len(cl)-1))
        last_50 = sma50[-1] if sma50[-1] is not None else cl[-1]
        last_200 = sma200[-1] if sma200[-1] is not None else cl[-1]
        prev_50 = sma50[-2] if len(sma50) > 1 and sma50[-2] is not None else last_50
        prev_200 = sma200[-2] if len(sma200) > 1 and sma200[-2] is not None else last_200
        if prev_50 <= prev_200 and last_50 > last_200:
            return {'signal': 'BUY', 'confidence': 75, 'method': 'SMA 50/200 Golden Cross', 'num': 2}
        elif prev_50 >= prev_200 and last_50 < last_200:
            return {'signal': 'SELL', 'confidence': 75, 'method': 'SMA 50/200 Death Cross', 'num': 2}
        elif last_50 > last_200:
            return {'signal': 'BUY', 'confidence': 35, 'method': 'SMA 50 > 200', 'num': 2}
        else:
            return {'signal': 'SELL', 'confidence': 35, 'method': 'SMA 50 < 200', 'num': 2}

    def analyze_supertrend(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'SuperTrend', 'num': 3}
        direction, upper, lower = self._calc_supertrend(hi, lo, cl, 10, 3)
        if direction[-1] == 1:
            return {'signal': 'BUY', 'confidence': 70, 'method': 'SuperTrend Uptrend', 'num': 3, 'stop': lower[-1]}
        else:
            return {'signal': 'SELL', 'confidence': 70, 'method': 'SuperTrend Downtrend', 'num': 3, 'stop': upper[-1]}

    def analyze_ichimoku(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Ichimoku Cloud', 'num': 4}
        tenkan, kijun, senkou_a, senkou_b, chikou = self._calc_ichimoku(hi, lo, cl)
        price = cl[-1]
        bull = 0
        if senkou_a[-1] is not None and senkou_b[-1] is not None:
            cloud_top = max(senkou_a[-1], senkou_b[-1])
            cloud_bot = min(senkou_a[-1], senkou_b[-1])
            if price > cloud_top:
                bull += 2
            elif price < cloud_bot:
                bull -= 2
        if tenkan[-1] is not None and kijun[-1] is not None:
            if tenkan[-1] > kijun[-1]:
                bull += 1
            else:
                bull -= 1
        if chikou[-1] is not None and chikou[-1] > price:
            bull += 1
        elif chikou[-1] is not None:
            bull -= 1
        if bull >= 2:
            return {'signal': 'BUY', 'confidence': 65, 'method': 'Ichimoku Bullish', 'num': 4}
        elif bull <= -2:
            return {'signal': 'SELL', 'confidence': 65, 'method': 'Ichimoku Bearish', 'num': 4}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 30, 'method': 'Ichimoku Neutral', 'num': 4}

    def analyze_hma(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'HMA', 'num': 5}
        hma = self._calc_hma(cl, 20)
        if hma[-1] is None or hma[-2] is None:
            return {'signal': 'NEUTRAL', 'confidence': 20, 'method': 'HMA', 'num': 5}
        if cl[-1] > hma[-1] and cl[-2] <= hma[-2]:
            return {'signal': 'BUY', 'confidence': 72, 'method': 'HMA Bullish Crossover', 'num': 5}
        elif cl[-1] < hma[-1] and cl[-2] >= hma[-2]:
            return {'signal': 'SELL', 'confidence': 72, 'method': 'HMA Bearish Crossover', 'num': 5}
        elif cl[-1] > hma[-1]:
            return {'signal': 'BUY', 'confidence': 30, 'method': 'HMA Bullish', 'num': 5}
        else:
            return {'signal': 'SELL', 'confidence': 30, 'method': 'HMA Bearish', 'num': 5}

    def analyze_keltner(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Keltner Channels', 'num': 6}
        upper, mid, lower = self._calc_keltner(hi, lo, cl, 20, 2)
        price = cl[-1]
        if price > upper[-1]:
            return {'signal': 'SELL', 'confidence': 60, 'method': 'Keltner Overextended', 'num': 6}
        elif price < lower[-1]:
            return {'signal': 'BUY', 'confidence': 60, 'method': 'Keltner Oversold', 'num': 6}
        elif price > mid[-1]:
            return {'signal': 'BUY', 'confidence': 25, 'method': 'Keltner Bullish Bias', 'num': 6}
        else:
            return {'signal': 'SELL', 'confidence': 25, 'method': 'Keltner Bearish Bias', 'num': 6}

    def analyze_donchian(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Donchian Channels', 'num': 7}
        upper, mid, lower = self._calc_donchian(hi, lo, 20)
        price = cl[-1]
        if price >= upper[-1]:
            return {'signal': 'BUY', 'confidence': 65, 'method': 'Donchian Breakout Up', 'num': 7}
        elif price <= lower[-1]:
            return {'signal': 'SELL', 'confidence': 65, 'method': 'Donchian Breakout Down', 'num': 7}
        elif price > mid[-1]:
            return {'signal': 'BUY', 'confidence': 20, 'method': 'Donchian Bullish', 'num': 7}
        else:
            return {'signal': 'SELL', 'confidence': 20, 'method': 'Donchian Bearish', 'num': 7}

    def analyze_parabolic_sar(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Parabolic SAR', 'num': 8}
        sar, trend = self._calc_parabolic_sar(hi, lo)
        if trend[-1] == 1 and cl[-1] > sar[-1]:
            return {'signal': 'BUY', 'confidence': 55, 'method': 'Parabolic SAR Buy', 'num': 8, 'sar': sar[-1]}
        elif trend[-1] == -1 and cl[-1] < sar[-1]:
            return {'signal': 'SELL', 'confidence': 55, 'method': 'Parabolic SAR Sell', 'num': 8, 'sar': sar[-1]}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 15, 'method': 'Parabolic SAR Neutral', 'num': 8}

    def analyze_heikin_ashi(self, symbol, interval='1h', limit=50):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Heikin Ashi', 'num': 9}
        ha_close = [(op[i] + hi[i] + lo[i] + cl[i]) / 4 for i in range(len(cl))]
        ha_open = [op[0]]
        for i in range(1, len(cl)):
            ha_open.append((ha_open[-1] + ha_close[i-1]) / 2)
        bull_candles = sum(1 for i in range(max(0, len(ha_close)-5), len(ha_close)) if ha_close[i] > ha_open[i])
        if bull_candles >= 4 and ha_close[-1] > ha_open[-1]:
            return {'signal': 'BUY', 'confidence': 60, 'method': 'Heikin Ashi Strong Buy', 'num': 9}
        elif bull_candles <= 1 and ha_close[-1] < ha_open[-1]:
            return {'signal': 'SELL', 'confidence': 60, 'method': 'Heikin Ashi Strong Sell', 'num': 9}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 20, 'method': 'Heikin Ashi Indecision', 'num': 9}

    def analyze_mcginley(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'McGinley Dynamic', 'num': 10}
        md = self._calc_mcginley(cl, 20)
        if cl[-1] > md[-1] and cl[-2] <= md[-2]:
            return {'signal': 'BUY', 'confidence': 60, 'method': 'McGinley Dynamic Buy', 'num': 10}
        elif cl[-1] < md[-1] and cl[-2] >= md[-2]:
            return {'signal': 'SELL', 'confidence': 60, 'method': 'McGinley Dynamic Sell', 'num': 10}
        elif cl[-1] > md[-1]:
            return {'signal': 'BUY', 'confidence': 25, 'method': 'McGinley Bullish', 'num': 10}
        else:
            return {'signal': 'SELL', 'confidence': 25, 'method': 'McGinley Bearish', 'num': 10}

    def analyze_dema(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'DEMA', 'num': 11}
        dema = self._calc_dema(cl, 20)
        if cl[-1] > dema[-1] and cl[-2] <= dema[-2]:
            return {'signal': 'BUY', 'confidence': 65, 'method': 'DEMA Bullish Cross', 'num': 11}
        elif cl[-1] < dema[-1] and cl[-2] >= dema[-2]:
            return {'signal': 'SELL', 'confidence': 65, 'method': 'DEMA Bearish Cross', 'num': 11}
        elif cl[-1] > dema[-1]:
            return {'signal': 'BUY', 'confidence': 25, 'method': 'DEMA Bullish', 'num': 11}
        else:
            return {'signal': 'SELL', 'confidence': 25, 'method': 'DEMA Bearish', 'num': 11}

    def analyze_tema(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'TEMA', 'num': 12}
        tema = self._calc_tema(cl, 20)
        if cl[-1] > tema[-1] and cl[-2] <= tema[-2]:
            return {'signal': 'BUY', 'confidence': 68, 'method': 'TEMA Bullish Cross', 'num': 12}
        elif cl[-1] < tema[-1] and cl[-2] >= tema[-2]:
            return {'signal': 'SELL', 'confidence': 68, 'method': 'TEMA Bearish Cross', 'num': 12}
        elif cl[-1] > tema[-1]:
            return {'signal': 'BUY', 'confidence': 28, 'method': 'TEMA Bullish', 'num': 12}
        else:
            return {'signal': 'SELL', 'confidence': 28, 'method': 'TEMA Bearish', 'num': 12}

    # ==================== MOMENTUM & OSCILLATORS (13-24) ====================

    def analyze_rsi(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'RSI', 'num': 13}
        rsi = self._calc_rsi(cl, 14)
        val = rsi[-1]
        if val < 25:
            return {'signal': 'BUY', 'confidence': 85, 'method': 'RSI Oversold', 'num': 13, 'rsi': val}
        elif val > 75:
            return {'signal': 'SELL', 'confidence': 85, 'method': 'RSI Overbought', 'num': 13, 'rsi': val}
        elif val < 35:
            return {'signal': 'BUY', 'confidence': 55, 'method': 'RSI Near Oversold', 'num': 13, 'rsi': val}
        elif val > 65:
            return {'signal': 'SELL', 'confidence': 55, 'method': 'RSI Near Overbought', 'num': 13, 'rsi': val}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 15, 'method': 'RSI Neutral', 'num': 13, 'rsi': val}

    def analyze_stoch_rsi(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Stochastic RSI', 'num': 14}
        k, d, raw = self._calc_stoch_rsi(cl, 14, 3, 3)
        if k[-1] < 10 and d[-1] < 10:
            return {'signal': 'BUY', 'confidence': 80, 'method': 'StochRSI Oversold', 'num': 14, 'k': k[-1], 'd': d[-1]}
        elif k[-1] > 90 and d[-1] > 90:
            return {'signal': 'SELL', 'confidence': 80, 'method': 'StochRSI Overbought', 'num': 14, 'k': k[-1], 'd': d[-1]}
        elif k[-1] < 20 and d[-1] < 20:
            return {'signal': 'BUY', 'confidence': 50, 'method': 'StochRSI Low', 'num': 14}
        elif k[-1] > 80 and d[-1] > 80:
            return {'signal': 'SELL', 'confidence': 50, 'method': 'StochRSI High', 'num': 14}
        elif k[-1] > d[-1] and k[-2] <= d[-2]:
            return {'signal': 'BUY', 'confidence': 45, 'method': 'StochRSI Bullish Cross', 'num': 14}
        elif k[-1] < d[-1] and k[-2] >= d[-2]:
            return {'signal': 'SELL', 'confidence': 45, 'method': 'StochRSI Bearish Cross', 'num': 14}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'StochRSI Neutral', 'num': 14}

    def analyze_macd(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'MACD', 'num': 15}
        macd, signal, hist = self._calc_macd(cl, 12, 26, 9)
        if hist[-1] > 0 and hist[-2] <= 0:
            return {'signal': 'BUY', 'confidence': 78, 'method': 'MACD Histo Bullish Cross', 'num': 15}
        elif hist[-1] < 0 and hist[-2] >= 0:
            return {'signal': 'SELL', 'confidence': 78, 'method': 'MACD Histo Bearish Cross', 'num': 15}
        elif macd[-1] > signal[-1] and macd[-2] <= signal[-2]:
            return {'signal': 'BUY', 'confidence': 72, 'method': 'MACD Bullish Cross', 'num': 15}
        elif macd[-1] < signal[-1] and macd[-2] >= signal[-2]:
            return {'signal': 'SELL', 'confidence': 72, 'method': 'MACD Bearish Cross', 'num': 15}
        elif hist[-1] > 0:
            return {'signal': 'BUY', 'confidence': 30, 'method': 'MACD Bullish Momentum', 'num': 15}
        elif hist[-1] < 0:
            return {'signal': 'SELL', 'confidence': 30, 'method': 'MACD Bearish Momentum', 'num': 15}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'MACD Neutral', 'num': 15}

    def analyze_awesome_oscillator(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Awesome Oscillator', 'num': 16}
        ao = self._calc_awesome_oscillator(hi, lo, 5, 34)
        if ao[-1] > 0 and ao[-2] <= 0:
            return {'signal': 'BUY', 'confidence': 65, 'method': 'AO Bullish Cross Zero', 'num': 16}
        elif ao[-1] < 0 and ao[-2] >= 0:
            return {'signal': 'SELL', 'confidence': 65, 'method': 'AO Bearish Cross Zero', 'num': 16}
        elif ao[-1] > 0 and ao[-1] > ao[-2]:
            return {'signal': 'BUY', 'confidence': 30, 'method': 'AO Bullish Momentum', 'num': 16}
        elif ao[-1] < 0 and ao[-1] < ao[-2]:
            return {'signal': 'SELL', 'confidence': 30, 'method': 'AO Bearish Momentum', 'num': 16}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'AO Neutral', 'num': 16}

    def analyze_accelerator_oscillator(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Accelerator Oscillator', 'num': 17}
        ac = self._calc_accelerator_oscillator(hi, lo, 5, 34)
        if ac[-1] > 0 and ac[-2] <= 0:
            return {'signal': 'BUY', 'confidence': 55, 'method': 'AC Bullish Turn', 'num': 17}
        elif ac[-1] < 0 and ac[-2] >= 0:
            return {'signal': 'SELL', 'confidence': 55, 'method': 'AC Bearish Turn', 'num': 17}
        elif ac[-1] > 0:
            return {'signal': 'BUY', 'confidence': 20, 'method': 'AC Positive', 'num': 17}
        else:
            return {'signal': 'SELL', 'confidence': 20, 'method': 'AC Negative', 'num': 17}

    def analyze_cmo(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'CMO', 'num': 18}
        cmo = self._calc_cmo(cl, 14)
        if cmo[-1] < -50:
            return {'signal': 'BUY', 'confidence': 70, 'method': 'CMO Oversold', 'num': 18, 'cmo': cmo[-1]}
        elif cmo[-1] > 50:
            return {'signal': 'SELL', 'confidence': 70, 'method': 'CMO Overbought', 'num': 18, 'cmo': cmo[-1]}
        elif cmo[-1] < -30:
            return {'signal': 'BUY', 'confidence': 40, 'method': 'CMO Bearish', 'num': 18}
        elif cmo[-1] > 30:
            return {'signal': 'SELL', 'confidence': 40, 'method': 'CMO Bullish', 'num': 18}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'CMO Neutral', 'num': 18}

    def analyze_cci(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'CCI', 'num': 19}
        cci = self._calc_cci(hi, lo, cl, 20)
        if cci[-1] < -100:
            return {'signal': 'BUY', 'confidence': 68, 'method': 'CCI Oversold', 'num': 19, 'cci': cci[-1]}
        elif cci[-1] > 100:
            return {'signal': 'SELL', 'confidence': 68, 'method': 'CCI Overbought', 'num': 19, 'cci': cci[-1]}
        elif cci[-1] < -50:
            return {'signal': 'BUY', 'confidence': 30, 'method': 'CCI Weak Oversold', 'num': 19}
        elif cci[-1] > 50:
            return {'signal': 'SELL', 'confidence': 30, 'method': 'CCI Weak Overbought', 'num': 19}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'CCI Neutral', 'num': 19}

    def analyze_mfi(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'MFI', 'num': 20}
        mfi = self._calc_mfi(hi, lo, cl, vol, 14)
        if mfi[-1] < 20:
            return {'signal': 'BUY', 'confidence': 75, 'method': 'MFI Oversold', 'num': 20, 'mfi': mfi[-1]}
        elif mfi[-1] > 80:
            return {'signal': 'SELL', 'confidence': 75, 'method': 'MFI Overbought', 'num': 20, 'mfi': mfi[-1]}
        elif mfi[-1] < 30:
            return {'signal': 'BUY', 'confidence': 45, 'method': 'MFI Low', 'num': 20}
        elif mfi[-1] > 70:
            return {'signal': 'SELL', 'confidence': 45, 'method': 'MFI High', 'num': 20}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'MFI Neutral', 'num': 20}

    def analyze_cmf(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'CMF', 'num': 21}
        cmf = self._calc_cmf(hi, lo, cl, vol, 20)
        if cmf[-1] > 0.1:
            return {'signal': 'BUY', 'confidence': 60, 'method': 'CMF Strong Accumulation', 'num': 21, 'cmf': cmf[-1]}
        elif cmf[-1] < -0.1:
            return {'signal': 'SELL', 'confidence': 60, 'method': 'CMF Strong Distribution', 'num': 21, 'cmf': cmf[-1]}
        elif cmf[-1] > 0.05:
            return {'signal': 'BUY', 'confidence': 30, 'method': 'CMF Weak Accumulation', 'num': 21}
        elif cmf[-1] < -0.05:
            return {'signal': 'SELL', 'confidence': 30, 'method': 'CMF Weak Distribution', 'num': 21}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'CMF Neutral', 'num': 21}

    def analyze_connors_rsi(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Connors RSI', 'num': 22}
        crsi = self._calc_connors_rsi(cl, 3, 2, 100)
        if crsi[-1] < 20:
            return {'signal': 'BUY', 'confidence': 75, 'method': 'CRSI Oversold', 'num': 22, 'crsi': crsi[-1]}
        elif crsi[-1] > 80:
            return {'signal': 'SELL', 'confidence': 75, 'method': 'CRSI Overbought', 'num': 22, 'crsi': crsi[-1]}
        elif crsi[-1] < 30:
            return {'signal': 'BUY', 'confidence': 40, 'method': 'CRSI Low', 'num': 22}
        elif crsi[-1] > 70:
            return {'signal': 'SELL', 'confidence': 40, 'method': 'CRSI High', 'num': 22}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'CRSI Neutral', 'num': 22}

    def analyze_dpo(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'DPO', 'num': 23}
        dpo = self._calc_dpo(cl, 14)
        if dpo[-1] > 0 and dpo[-2] <= 0:
            return {'signal': 'BUY', 'confidence': 50, 'method': 'DPO Bullish Cross', 'num': 23}
        elif dpo[-1] < 0 and dpo[-2] >= 0:
            return {'signal': 'SELL', 'confidence': 50, 'method': 'DPO Bearish Cross', 'num': 23}
        elif dpo[-1] > 0:
            return {'signal': 'BUY', 'confidence': 20, 'method': 'DPO Bullish', 'num': 23}
        else:
            return {'signal': 'SELL', 'confidence': 20, 'method': 'DPO Bearish', 'num': 23}

    def analyze_smi_ergodic(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'SMI Ergodic', 'num': 24}
        smi, signal = self._calc_smi_ergodic(cl, 14, 3, 3)
        if smi[-1] < -40 and signal[-1] < -40:
            return {'signal': 'BUY', 'confidence': 60, 'method': 'SMI Oversold', 'num': 24, 'smi': smi[-1]}
        elif smi[-1] > 40 and signal[-1] > 40:
            return {'signal': 'SELL', 'confidence': 60, 'method': 'SMI Overbought', 'num': 24, 'smi': smi[-1]}
        elif smi[-1] > signal[-1] and smi[-2] <= signal[-2]:
            return {'signal': 'BUY', 'confidence': 40, 'method': 'SMI Bullish Cross', 'num': 24}
        elif smi[-1] < signal[-1] and smi[-2] >= signal[-2]:
            return {'signal': 'SELL', 'confidence': 40, 'method': 'SMI Bearish Cross', 'num': 24}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'SMI Neutral', 'num': 24}

    # ==================== VOLUME-BASED METHODS (25-32) ====================

    def analyze_volume_profile(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Volume Profile', 'num': 25}
        vp = self._calc_volume_profile(hi, lo, vol, 12)
        price = cl[-1]
        if price < vp['value_area_low']:
            return {'signal': 'BUY', 'confidence': 60, 'method': 'VPVR Below Value Area', 'num': 25}
        elif price > vp['value_area_high']:
            return {'signal': 'SELL', 'confidence': 60, 'method': 'VPVR Above Value Area', 'num': 25}
        elif abs(price - vp['poc']) / price < 0.005:
            return {'signal': 'NEUTRAL', 'confidence': 20, 'method': 'VPVR At POC', 'num': 25}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 15, 'method': 'VPVR In Value Area', 'num': 25}

    def analyze_anchored_vwap(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Anchored VWAP', 'num': 26}
        typ = [(hi[i] + lo[i] + cl[i]) / 3 for i in range(len(cl))]
        cum_pv = sum(typ[i] * vol[i] for i in range(len(vol)))
        cum_v = sum(vol)
        vwap = cum_pv / cum_v if cum_v != 0 else cl[-1]
        price = cl[-1]
        if price < vwap * 0.97:
            return {'signal': 'BUY', 'confidence': 65, 'method': 'VWAP Discount', 'num': 26, 'vwap': vwap}
        elif price > vwap * 1.03:
            return {'signal': 'SELL', 'confidence': 65, 'method': 'VWAP Premium', 'num': 26, 'vwap': vwap}
        elif price < vwap:
            return {'signal': 'BUY', 'confidence': 25, 'method': 'VWAP Below', 'num': 26}
        else:
            return {'signal': 'SELL', 'confidence': 25, 'method': 'VWAP Above', 'num': 26}

    def analyze_obv(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'OBV', 'num': 27}
        obv = self._calc_obv(cl, vol)
        obv_ema = self._calc_ema(obv, 20)
        if obv[-1] > obv_ema[-1] and obv[-2] <= obv_ema[-2]:
            return {'signal': 'BUY', 'confidence': 55, 'method': 'OBV Bullish Cross', 'num': 27}
        elif obv[-1] < obv_ema[-1] and obv[-2] >= obv_ema[-2]:
            return {'signal': 'SELL', 'confidence': 55, 'method': 'OBV Bearish Cross', 'num': 27}
        elif obv[-1] > obv_ema[-1]:
            return {'signal': 'BUY', 'confidence': 20, 'method': 'OBV Bullish', 'num': 27}
        else:
            return {'signal': 'SELL', 'confidence': 20, 'method': 'OBV Bearish', 'num': 27}

    def analyze_vwma(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'VWMA', 'num': 28}
        period = 20
        vwma = []
        for i in range(len(cl)):
            if i < period - 1:
                vwma.append(cl[i])
            else:
                pv = sum(cl[i-period+1+j] * vol[i-period+1+j] for j in range(period))
                v = sum(vol[i-period+1+j] for j in range(period))
                vwma.append(pv / v if v != 0 else cl[i])
        if cl[-1] > vwma[-1] and cl[-2] <= vwma[-2]:
            return {'signal': 'BUY', 'confidence': 60, 'method': 'VWMA Bullish Cross', 'num': 28}
        elif cl[-1] < vwma[-1] and cl[-2] >= vwma[-2]:
            return {'signal': 'SELL', 'confidence': 60, 'method': 'VWMA Bearish Cross', 'num': 28}
        elif cl[-1] > vwma[-1]:
            return {'signal': 'BUY', 'confidence': 25, 'method': 'VWMA Bullish', 'num': 28}
        else:
            return {'signal': 'SELL', 'confidence': 25, 'method': 'VWMA Bearish', 'num': 28}

    def analyze_force_index(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Force Index', 'num': 29}
        fi = self._calc_force_index(cl, vol, 13)
        if fi[-1] > 0 and fi[-2] <= 0:
            return {'signal': 'BUY', 'confidence': 50, 'method': 'Force Index Bullish', 'num': 29}
        elif fi[-1] < 0 and fi[-2] >= 0:
            return {'signal': 'SELL', 'confidence': 50, 'method': 'Force Index Bearish', 'num': 29}
        elif fi[-1] > 0:
            return {'signal': 'BUY', 'confidence': 20, 'method': 'Force Index Positive', 'num': 29}
        else:
            return {'signal': 'SELL', 'confidence': 20, 'method': 'Force Index Negative', 'num': 29}

    def analyze_nvi(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'NVI', 'num': 30}
        nvi = self._calc_nvi(cl, vol)
        nvi_ema = self._calc_ema(nvi, 20)
        if nvi[-1] > nvi_ema[-1]:
            return {'signal': 'BUY', 'confidence': 40, 'method': 'NVI Bullish', 'num': 30}
        else:
            return {'signal': 'SELL', 'confidence': 40, 'method': 'NVI Bearish', 'num': 30}

    def analyze_pvi(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'PVI', 'num': 31}
        pvi = self._calc_pvi(cl, vol)
        pvi_ema = self._calc_ema(pvi, 20)
        if pvi[-1] > pvi_ema[-1]:
            return {'signal': 'BUY', 'confidence': 35, 'method': 'PVI Bullish', 'num': 31}
        else:
            return {'signal': 'SELL', 'confidence': 35, 'method': 'PVI Bearish', 'num': 31}

    def analyze_ad_line(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'A/D Line', 'num': 32}
        ad = self._calc_ad_line(hi, lo, cl, vol)
        ad_ema = self._calc_ema(ad, 20)
        if ad[-1] > ad_ema[-1] and ad[-2] <= ad_ema[-2]:
            return {'signal': 'BUY', 'confidence': 55, 'method': 'A/D Bullish Cross', 'num': 32}
        elif ad[-1] < ad_ema[-1] and ad[-2] >= ad_ema[-2]:
            return {'signal': 'SELL', 'confidence': 55, 'method': 'A/D Bearish Cross', 'num': 32}
        elif ad[-1] > ad_ema[-1]:
            return {'signal': 'BUY', 'confidence': 20, 'method': 'AD Accumulating', 'num': 32}
        else:
            return {'signal': 'SELL', 'confidence': 20, 'method': 'A/D Distributing', 'num': 32}

    # ==================== VOLATILITY & BREAKOUT (33-39) ====================

    def analyze_bollinger_bands(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Bollinger Bands', 'num': 33}
        upper, mid, lower = self._calc_bollinger_bands(cl, 20, 2)
        if lower[-1] is not None and upper[-1] is not None:
            price = cl[-1]
            if price <= lower[-1]:
                return {'signal': 'BUY', 'confidence': 75, 'method': 'BB Lower Band Touch', 'num': 33}
            elif price >= upper[-1]:
                return {'signal': 'SELL', 'confidence': 75, 'method': 'BB Upper Band Touch', 'num': 33}
            elif price < mid[-1]:
                return {'signal': 'BUY', 'confidence': 20, 'method': 'BB Below Mid', 'num': 33}
            else:
                return {'signal': 'SELL', 'confidence': 20, 'method': 'BB Above Mid', 'num': 33}
        return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Bollinger Bands', 'num': 33}

    def analyze_atr(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'ATR', 'num': 34}
        atr = self._calc_atr(hi, lo, cl, 14)
        atr_pct = (atr[-1] / cl[-1]) * 100
        if atr_pct > 5:
            return {'signal': 'SELL', 'confidence': 35, 'method': 'ATR High Volatility', 'num': 34, 'atr%': atr_pct}
        elif atr_pct < 1:
            return {'signal': 'BUY', 'confidence': 30, 'method': 'ATR Low Volatility', 'num': 34, 'atr%': atr_pct}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'ATR Normal', 'num': 34, 'atr%': atr_pct}

    def analyze_bollinger_b(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': '%B', 'num': 35}
        b = self._calc_bollinger_b(cl, 20, 2)
        if b[-1] < 0:
            return {'signal': 'BUY', 'confidence': 72, 'method': '%B Below 0', 'num': 35, 'b': b[-1]}
        elif b[-1] > 1:
            return {'signal': 'SELL', 'confidence': 72, 'method': '%B Above 1', 'num': 35, 'b': b[-1]}
        elif b[-1] < 0.2:
            return {'signal': 'BUY', 'confidence': 40, 'method': '%B Near Oversold', 'num': 35}
        elif b[-1] > 0.8:
            return {'signal': 'SELL', 'confidence': 40, 'method': '%B Near Overbought', 'num': 35}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': '%B Neutral', 'num': 35}

    def analyze_bbw(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'BBW', 'num': 36}
        bbw = self._calc_bbw(cl, 20, 2)
        valid_bbw = [b for b in bbw if b > 0]
        if len(valid_bbw) < 20:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'BBW', 'num': 36}
        recent_avg = sum(bbw[-20:]) / 20 if bbw[-20] > 0 else sum(valid_bbw[-20:]) / 20
        current = bbw[-1]
        squeeze_ratio = current / recent_avg if recent_avg > 0 else 1
        if squeeze_ratio < 0.6:
            return {'signal': 'NEUTRAL', 'confidence': 50, 'method': 'BBW Squeeze Detected', 'num': 36, 'ratio': squeeze_ratio}
        elif squeeze_ratio > 1.5 and bbw[-1] > bbw[-2]:
            return {'signal': 'SELL', 'confidence': 55, 'method': 'BBW Expansion Bearish', 'num': 36}
        elif squeeze_ratio > 1.5 and bbw[-1] < bbw[-2]:
            return {'signal': 'BUY', 'confidence': 55, 'method': 'BBW Expansion Bullish', 'num': 36}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'BBW Normal', 'num': 36}

    def analyze_chaikin_volatility(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Chaikin Vol', 'num': 37}
        cv = self._calc_chaikin_volatility(hi, lo, 10, 10)
        valid_cv = [c for c in cv if c != 0]
        if len(valid_cv) < 2:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'Chaikin Vol', 'num': 37}
        if cv[-1] > 0 and cv[-1] > cv[-2]:
            return {'signal': 'BUY', 'confidence': 30, 'method': 'Chaikin Vol Expanding', 'num': 37}
        elif cv[-1] < 0 and cv[-1] < cv[-2]:
            return {'signal': 'SELL', 'confidence': 30, 'method': 'Chaikin Vol Expanding Down', 'num': 37}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'Chaikin Vol Stable', 'num': 37}

    def analyze_standard_error_bands(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'SE Bands', 'num': 38}
        upper, mid, lower = self._calc_standard_error_bands(cl, 20, 2)
        if upper[-1] is not None and lower[-1] is not None:
            price = cl[-1]
            if price <= lower[-1]:
                return {'signal': 'BUY', 'confidence': 60, 'method': 'SE Bands Lower Touch', 'num': 38}
            elif price >= upper[-1]:
                return {'signal': 'SELL', 'confidence': 60, 'method': 'SE Bands Upper Touch', 'num': 38}
        return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'SE Bands Neutral', 'num': 38}

    def analyze_squeeze_momentum(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Squeeze Momentum', 'num': 39}
        squeeze_on, momentum, mom_sma = self._calc_squeeze_momentum(hi, lo, cl)
        if squeeze_on[-1] and abs(momentum[-1]) < 5:
            return {'signal': 'NEUTRAL', 'confidence': 40, 'method': 'Squeeze Active', 'num': 39, 'squeeze': True}
        if momentum[-1] > 50 and momentum[-2] <= 50:
            return {'signal': 'BUY', 'confidence': 78, 'method': 'Squeeze Momentum Buy', 'num': 39}
        elif momentum[-1] < -50 and momentum[-2] >= -50:
            return {'signal': 'SELL', 'confidence': 78, 'method': 'Squeeze Momentum Sell', 'num': 39}
        elif momentum[-1] > 20:
            return {'signal': 'BUY', 'confidence': 30, 'method': 'Squeeze Bullish', 'num': 39}
        elif momentum[-1] < -20:
            return {'signal': 'SELL', 'confidence': 30, 'method': 'Squeeze Bearish', 'num': 39}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'Squeeze Neutral', 'num': 39}

    # ==================== S/R & STRUCTURE (40-46) ====================

    def analyze_pivot_points(self, symbol, interval='1d', limit=2):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Pivot Points', 'num': 40}
        pivots = self._calc_pivot_points(hi, lo, cl)
        price = cl[-1]
        if price <= pivots['s1']:
            return {'signal': 'BUY', 'confidence': 55, 'method': 'Pivot Below S1', 'num': 40}
        elif price >= pivots['r1']:
            return {'signal': 'SELL', 'confidence': 55, 'method': 'Pivot Above R1', 'num': 40}
        elif price < pivots['pp']:
            return {'signal': 'BUY', 'confidence': 20, 'method': 'Pivot Below PP', 'num': 40}
        else:
            return {'signal': 'SELL', 'confidence': 20, 'method': 'Pivot Above PP', 'num': 40}

    def analyze_fib_retracement(self, symbol, interval='4h', limit=50):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Fib Retracement', 'num': 41}
        fibs = self._calc_fib_retracement(hi, lo)
        price = cl[-1]
        for level_name in ['0.786', '0.618', '0.5', '0.382', '0.236']:
            level = fibs[level_name]
            dist_pct = abs(price - level) / price * 100
            if dist_pct < 0.5:
                fib_val = float(level_name)
                if fib_val <= 0.382:
                    return {'signal': 'SELL', 'confidence': 60, 'method': f'Fib {level_name} Resistance', 'num': 41}
                elif fib_val >= 0.618:
                    return {'signal': 'BUY', 'confidence': 60, 'method': f'Fib {level_name} Support', 'num': 41}
        if price > fibs['0.618'] and price < fibs['0.382']:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'Fib Mid-Range', 'num': 41}
        elif price < fibs['0.786']:
            return {'signal': 'BUY', 'confidence': 35, 'method': 'Fib Deep Retrace', 'num': 41}
        elif price > fibs['0.236']:
            return {'signal': 'SELL', 'confidence': 35, 'method': 'Fib Shallow Retrace', 'num': 41}
        return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'Fib Neutral', 'num': 41}

    def analyze_fib_extension(self, symbol, interval='4h', limit=50):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Fib Extension', 'num': 42}
        price_range = max(hi) - min(lo)
        ext_423 = max(hi) + 3.236 * price_range
        price = cl[-1]
        if price > ext_423:
            return {'signal': 'SELL', 'confidence': 40, 'method': 'Fib 4.236 Extended', 'num': 42}
        elif price < min(lo) * 0.95:
            return {'signal': 'BUY', 'confidence': 40, 'method': 'Fib Below 1.0', 'num': 42}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 15, 'method': 'Fib Extension Neutral', 'num': 42}

    def analyze_order_block(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Order Block', 'num': 43}
        bullish_obs = []
        bearish_obs = []
        for i in range(5, len(cl) - 3):
            if cl[i] < op[i] and cl[i+1] > op[i+1] and cl[i+2] > op[i+2]:
                bullish_obs.append({'low': lo[i], 'high': hi[i], 'strength': vol[i+1] + vol[i+2]})
            if cl[i] > op[i] and cl[i+1] < op[i+1] and cl[i+2] < op[i+2]:
                bearish_obs.append({'low': lo[i], 'high': hi[i], 'strength': vol[i+1] + vol[i+2]})
        price = cl[-1]
        for ob in bullish_obs[-5:]:
            if price >= ob['low'] * 0.995 and price <= ob['high'] * 1.005:
                return {'signal': 'BUY', 'confidence': 70, 'method': 'Order Block Support', 'num': 43}
        for ob in bearish_obs[-5:]:
            if price >= ob['low'] * 0.995 and price <= ob['high'] * 1.005:
                return {'signal': 'SELL', 'confidence': 70, 'method': 'Order Block Resistance', 'num': 43}
        return {'signal': 'NEUTRAL', 'confidence': 15, 'method': 'Order Block Neutral', 'num': 43}

    def analyze_fvg(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'FVG', 'num': 44}
        fvg_list = self._calc_fvg(hi, lo, cl, 5)
        price = cl[-1]
        for fvg in reversed(fvg_list):
            if fvg['type'] == 'BULLISH' and price >= fvg['gap_low'] * 0.995 and price <= fvg['gap_high'] * 1.005:
                return {'signal': 'BUY', 'confidence': 65, 'method': 'FVG Bullish Gap Fill', 'num': 44}
            elif fvg['type'] == 'BEARISH' and price >= fvg['gap_low'] * 0.995 and price <= fvg['gap_high'] * 1.005:
                return {'signal': 'SELL', 'confidence': 65, 'method': 'FVG Bearish Gap Fill', 'num': 44}
        if fvg_list and fvg_list[-1]['type'] == 'BULLISH':
            return {'signal': 'BUY', 'confidence': 20, 'method': 'FVG Near Bullish', 'num': 44}
        elif fvg_list and fvg_list[-1]['type'] == 'BEARISH':
            return {'signal': 'SELL', 'confidence': 20, 'method': 'FVG Near Bearish', 'num': 44}
        return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'FVG None', 'num': 44}

    def analyze_supply_demand(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Supply & Demand', 'num': 45}
        demand_zones = []
        supply_zones = []
        for i in range(10, len(cl) - 5):
            base_range = max(hi[i-5:i+1]) - min(lo[i-5:i+1])
            avg_range = (max(hi) - min(lo)) / 20
            if base_range < avg_range * 2:
                base_high = max(hi[i-5:i+1])
                base_low = min(lo[i-5:i+1])
                breakout_avg = sum(cl[i+1:i+6]) / 5 if i + 6 <= len(cl) else cl[-1]
                if breakout_avg > base_high * 1.02:
                    demand_zones.append({'high': base_high, 'low': base_low, 'strength': sum(vol[i-5:i+1])})
                elif breakout_avg < base_low * 0.98:
                    supply_zones.append({'high': base_high, 'low': base_low, 'strength': sum(vol[i-5:i+1])})
        price = cl[-1]
        for zone in demand_zones[-5:]:
            if price >= zone['low'] * 0.99 and price <= zone['high'] * 1.01:
                return {'signal': 'BUY', 'confidence': 65, 'method': 'Demand Zone Bounce', 'num': 45}
        for zone in supply_zones[-5:]:
            if price >= zone['low'] * 0.99 and price <= zone['high'] * 1.01:
                return {'signal': 'SELL', 'confidence': 65, 'method': 'Supply Zone Reject', 'num': 45}
        return {'signal': 'NEUTRAL', 'confidence': 15, 'method': 'Supply/Demand Neutral', 'num': 45}

    def analyze_trendline(self, symbol, interval='1h', limit=50):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Trendline', 'num': 46}
        peaks = []
        troughs = []
        for i in range(2, len(cl) - 2):
            if cl[i] > cl[i-1] and cl[i] > cl[i-2] and cl[i] > cl[i+1] and cl[i] > cl[i+2]:
                peaks.append({'idx': i, 'price': cl[i]})
            if cl[i] < cl[i-1] and cl[i] < cl[i-2] and cl[i] < cl[i+1] and cl[i] < cl[i+2]:
                troughs.append({'idx': i, 'price': cl[i]})
        price = cl[-1]
        if len(troughs) >= 2:
            last_trough = troughs[-1]['price']
            prev_trough = troughs[-2]['price']
            if last_trough > prev_trough and price < last_trough:
                return {'signal': 'SELL', 'confidence': 55, 'method': 'Uptrend Broken', 'num': 46}
            elif last_trough < prev_trough and price > last_trough:
                return {'signal': 'BUY', 'confidence': 55, 'method': 'Downtrend Broken', 'num': 46}
        if len(peaks) >= 2:
            last_peak = peaks[-1]['price']
            prev_peak = peaks[-2]['price']
            if last_peak < prev_peak and price > last_peak:
                return {'signal': 'BUY', 'confidence': 55, 'method': 'Downtrend Resistance Break', 'num': 46}
            elif last_peak > prev_peak and price < last_peak:
                return {'signal': 'SELL', 'confidence': 55, 'method': 'Uptrend Resistance Reject', 'num': 46}
        return {'signal': 'NEUTRAL', 'confidence': 15, 'method': 'Trendline Neutral', 'num': 46}

    # ==================== ADVANCED (47-50) ====================

    def analyze_lorentzian_ml(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Lorentzian ML', 'num': 47}
        rsi = self._calc_rsi(cl, 14)[-1]
        mfi_val = self._calc_mfi(hi, lo, cl, vol, 14)[-1]
        macd, sig, hist = self._calc_macd(cl, 12, 26, 9)
        bb_upper, bb_mid, bb_lower = self._calc_bollinger_bands(cl, 20, 2)
        bb_pct = (cl[-1] - bb_lower[-1]) / (bb_upper[-1] - bb_lower[-1]) if bb_lower[-1] is not None and bb_upper[-1] != bb_lower[-1] else 0.5
        score = 0
        if rsi < 35: score += 1
        elif rsi > 65: score -= 1
        if mfi_val < 30: score += 1
        elif mfi_val > 70: score -= 1
        if hist[-1] > 0: score += 1
        elif hist[-1] < 0: score -= 1
        if bb_pct < 0.2: score += 1
        elif bb_pct > 0.8: score -= 1
        confidence = abs(score) * 15
        if score >= 3:
            return {'signal': 'BUY', 'confidence': min(confidence, 85), 'method': 'Lorentzian ML Buy', 'num': 47}
        elif score <= -3:
            return {'signal': 'SELL', 'confidence': min(confidence, 85), 'method': 'Lorentzian ML Sell', 'num': 47}
        elif score >= 1:
            return {'signal': 'BUY', 'confidence': 30, 'method': 'Lorentzian ML Weak Buy', 'num': 47}
        elif score <= -1:
            return {'signal': 'SELL', 'confidence': 30, 'method': 'Lorentzian ML Weak Sell', 'num': 47}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 10, 'method': 'Lorentzian ML Neutral', 'num': 47}

    def analyze_luxalgo(self, symbol, interval='1h', limit=100):
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'LuxAlgo Suite', 'num': 48}
        rsi = self._calc_rsi(cl, 14)[-1]
        macd, sig, hist = self._calc_macd(cl, 12, 26, 9)
        bb_upper, bb_mid, bb_lower = self._calc_bollinger_bands(cl, 20, 2)
        cmf_val = self._calc_cmf(hi, lo, cl, vol, 20)[-1]
        squeeze, momentum, _ = self._calc_squeeze_momentum(hi, lo, cl)
        score = 0
        if hist[-1] > 0 and hist[-2] <= 0: score += 2
        elif hist[-1] < 0 and hist[-2] >= 0: score -= 2
        if rsi < 30: score += 1.5
        elif rsi > 70: score -= 1.5
        if cmf_val > 0.05: score += 1
        elif cmf_val < -0.05: score -= 1
        if not squeeze[-1] and momentum[-1] > 30: score += 1.5
        elif not squeeze[-1] and momentum[-1] < -30: score -= 1.5
        if cl[-1] > bb_mid[-1]: score += 0.5
        else: score -= 0.5
        confidence = min(abs(score) * 18, 90)
        if score >= 3:
            return {'signal': 'BUY', 'confidence': confidence, 'method': 'LuxAlgo Bullish', 'num': 48}
        elif score <= -3:
            return {'signal': 'SELL', 'confidence': confidence, 'method': 'LuxAlgo Bearish', 'num': 48}
        elif score >= 1:
            return {'signal': 'BUY', 'confidence': 35, 'method': 'LuxAlgo Weak Buy', 'num': 48}
        elif score <= -1:
            return {'signal': 'SELL', 'confidence': 35, 'method': 'LuxAlgo Weak Sell', 'num': 48}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 15, 'method': 'LuxAlgo Neutral', 'num': 48}

    def analyze_chop_zone(self, symbol, interval='1h', limit=100):
        import math
        op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, interval, limit)
        if not cl:
            return {'signal': 'NEUTRAL', 'confidence': 0, 'method': 'Chop Zone', 'num': 49}
        chop = self._calc_chop_index(hi, lo, cl, 14)
        if chop[-1] > 61.8:
            return {'signal': 'NEUTRAL', 'confidence': 70, 'method': 'Chop Zone Ranging', 'num': 49, 'chop': chop[-1]}
        elif chop[-1] < 38.2:
            ema8 = self._calc_ema(cl, 8)[-1]
            ema21 = self._calc_ema(cl, 21)[-1]
            if cl[-1] > ema8 and ema8 > ema21:
                return {'signal': 'BUY', 'confidence': 75, 'method': 'Chop Zone Trending Up', 'num': 49, 'chop': chop[-1]}
            elif cl[-1] < ema8 and ema8 < ema21:
                return {'signal': 'SELL', 'confidence': 75, 'method': 'Chop Zone Trending Down', 'num': 49, 'chop': chop[-1]}
            return {'signal': 'NEUTRAL', 'confidence': 40, 'method': 'Chop Zone Trending Unclear', 'num': 49, 'chop': chop[-1]}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 25, 'method': 'Chop Zone Transition', 'num': 49, 'chop': chop[-1]}

    def analyze_mtf_ma(self, symbol, interval='15m', limit=200):
        results = []
        for tf, period in [('15m', 50), ('1h', 50), ('4h', 50)]:
            op, hi, lo, cl, vol, ts = self._prepare_ohlcv(symbol, tf, period)
            if not cl:
                results.append({'signal': 'NEUTRAL', 'confidence': 0})
                continue
            ema20 = self._calc_ema(cl, min(20, len(cl)-1))[-1]
            ema50 = self._calc_ema(cl, min(period, len(cl)-1))[-1]
            price = cl[-1]
            if price > ema20 > ema50:
                results.append({'signal': 'BUY', 'confidence': 85})
            elif price < ema20 < ema50:
                results.append({'signal': 'SELL', 'confidence': 85})
            elif price > ema50:
                results.append({'signal': 'BUY', 'confidence': 40})
            elif price < ema50:
                results.append({'signal': 'SELL', 'confidence': 40})
            else:
                results.append({'signal': 'NEUTRAL', 'confidence': 10})
        buy_count = sum(1 for r in results if r['signal'] == 'BUY')
        sell_count = sum(1 for r in results if r['signal'] == 'SELL')
        avg_conf = sum(r['confidence'] for r in results) / 3
        if buy_count >= 3:
            return {'signal': 'BUY', 'confidence': min(90, avg_conf + 20), 'method': 'MTF MA Triple Bullish', 'num': 50}
        elif sell_count >= 3:
            return {'signal': 'SELL', 'confidence': min(90, avg_conf + 20), 'method': 'MTF MA Triple Bearish', 'num': 50}
        elif buy_count >= 2:
            return {'signal': 'BUY', 'confidence': min(70, avg_conf + 10), 'method': 'MTF MA Partial Bullish', 'num': 50}
        elif sell_count >= 2:
            return {'signal': 'SELL', 'confidence': min(70, avg_conf + 10), 'method': 'MTF MA Partial Bearish', 'num': 50}
        else:
            return {'signal': 'NEUTRAL', 'confidence': 20, 'method': 'MTF MA No Confluence', 'num': 50}

    # ==================== FINAL AGGREGATE + DISPLAY ====================

    def analyze_all_50(self, symbol, interval='1h'):
        method_map = {
            1: self.analyze_ema_50_200, 2: self.analyze_sma_50_200,
            3: self.analyze_supertrend, 4: self.analyze_ichimoku,
            5: self.analyze_hma, 6: self.analyze_keltner,
            7: self.analyze_donchian, 8: self.analyze_parabolic_sar,
            9: self.analyze_heikin_ashi, 10: self.analyze_mcginley,
            11: self.analyze_dema, 12: self.analyze_tema,
            13: self.analyze_rsi, 14: self.analyze_stoch_rsi,
            15: self.analyze_macd, 16: self.analyze_awesome_oscillator,
            17: self.analyze_accelerator_oscillator, 18: self.analyze_cmo,
            19: self.analyze_cci, 20: self.analyze_mfi,
            21: self.analyze_cmf, 22: self.analyze_connors_rsi,
            23: self.analyze_dpo, 24: self.analyze_smi_ergodic,
            25: self.analyze_volume_profile, 26: self.analyze_anchored_vwap,
            27: self.analyze_obv, 28: self.analyze_vwma,
            29: self.analyze_force_index, 30: self.analyze_nvi,
            31: self.analyze_pvi, 32: self.analyze_ad_line,
            33: self.analyze_bollinger_bands, 34: self.analyze_atr,
            35: self.analyze_bollinger_b, 36: self.analyze_bbw,
            37: self.analyze_chaikin_volatility, 38: self.analyze_standard_error_bands,
            39: self.analyze_squeeze_momentum, 40: self.analyze_pivot_points,
            41: self.analyze_fib_retracement, 42: self.analyze_fib_extension,
            43: self.analyze_order_block, 44: self.analyze_fvg,
            45: self.analyze_supply_demand, 46: self.analyze_trendline,
            47: self.analyze_lorentzian_ml, 48: self.analyze_luxalgo,
            49: self.analyze_chop_zone, 50: self.analyze_mtf_ma
        }
        
        all_results = []
        weighted_buy_score = 0.0
        weighted_sell_score = 0.0
        total_weight = 0.0
        buy_confidence_sum = 0.0
        sell_confidence_sum = 0.0
        buy_count = 0
        sell_count = 0
        neutral_count = 0
        
        for num, method_func in method_map.items():
            try:
                result = method_func(symbol, interval)
                all_results.append(result)
                signal = result.get('signal', 'NEUTRAL')
                conf = result.get('confidence', 0)
                
                if signal == 'BUY':
                    weighted_buy_score += conf
                    buy_confidence_sum += conf
                    buy_count += 1
                elif signal == 'SELL':
                    weighted_sell_score += conf
                    sell_confidence_sum += conf
                    sell_count += 1
                else:
                    neutral_count += 1
                total_weight += conf
            except Exception as e:
                logger.warning(f"Method {num} failed: {e}")
                all_results.append({'signal': 'NEUTRAL', 'confidence': 0})
        
        if total_weight > 0:
            final_bias = (weighted_buy_score - weighted_sell_score) / total_weight
        else:
            final_bias = 0.0
        
        if buy_count + sell_count > 0:
            avg_win_conf = (buy_confidence_sum + sell_confidence_sum) / (buy_count + sell_count)
        else:
            avg_win_conf = 0
        
        if final_bias > 0.15:
            final_signal = 'BUY'
            confidence = (weighted_buy_score / total_weight) * 100
        elif final_bias < -0.15:
            final_signal = 'SELL'
            confidence = (weighted_sell_score / total_weight) * 100
        else:
            final_signal = 'NEUTRAL'
            confidence = (1 - abs(final_bias)) * 50
        
        entry_price = 0
        ticker = self.get_ticker(symbol)
        if ticker:
            entry_price = ticker['last']
        
        atr_val = 0
        try:
            _, hi, lo, cl, vol, _ = self._prepare_ohlcv(symbol, interval, 50)
            if cl:
                atr_arr = self._calc_atr(hi, lo, cl, 14)
                atr_val = atr_arr[-1] * 2
        except:
            atr_val = entry_price * 0.015
        
        if final_signal == 'BUY':
            tp1 = entry_price + atr_val
            tp2 = entry_price + atr_val * 1.5
            tp3 = entry_price + (atrif * final_signal == 'BUY')
            tp1 = entry_price + atr_val
            tp2 = entry_price + atr_val * 1.5
            tp3 = entry_price + atr_val * 2.2
            sl = entry_price - atr_val * 0.8
        elif final_signal == 'SELL':
            tp1 = entry_price - atr_val
            tp2 = entry_price - atr_val * 1.5
            tp3 = entry_price - atr_val * 2.2
            sl = entry_price + atr_val * 0.8
        else:
            tp1 = tp2 = tp3 = sl = 0
        
        summary = {
            'total': 50,
            'buy': buy_count,
            'sell': sell_count,
            'neutral': neutral_count,
            'avg_confidence': round(avg_win_conf, 1),
            'bias': round(final_bias, 3)
        }
        
        agree_methods = sorted(
            [r for r in all_results if r.get('signal') == final_signal],
            key=lambda x: x.get('confidence', 0), reverse=True
        )[:5]
        
        result_data = {
            'symbol': symbol,
            'interval': interval,
            'signal': final_signal,
            'confidence': round(min(confidence, 100), 1),
            'entry': round(entry_price, 8),
            'tp1': round(tp1, 8),
            'tp2': round(tp2, 8),
            'tp3': round(tp3, 8),
            'sl': round(sl, 8),
            'rr_ratio': round(1.25, 2),
            'win_percentage': round(50 + final_bias * 30, 1),
            'method': f'Aggregate 50 ({final_signal})',
            'summary': summary,
            'top_methods': [{'method': m.get('method',''), 'confidence': m.get('confidence',0)} for m in agree_methods],
            'timestamp': str(datetime.now()),
            'all_results_count': len(all_results)
        }
        
        signal_key = f"{symbol}_{final_signal}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.signal_tracker[signal_key] = result_data
        self._save_signals()
        
        return result_data
      # ============ FIX 1: Signal keys normalize කරන helper (tp1 -> take_profit_1) ============
    def _normalize_signal_dict(self, result):
        """
        tp1/tp2/sl keys තියෙන signal dict එකකට
        take_profit_1/take_profit_2/stop_loss keys දෙකම add කරනවා.
        main.py දෙකම use කරන නිසා.
        """
        if not result or not isinstance(result, dict):
            return result
        result.setdefault('signal', 'NEUTRAL')
        result.setdefault('entry', 0)
        result.setdefault('tp1', result.get('take_profit_1', 0))
        result.setdefault('tp2', result.get('take_profit_2', 0))
        result.setdefault('tp3', result.get('take_profit_3', 0))
        result.setdefault('sl', result.get('stop_loss', 0))
        result['take_profit_1'] = result.get('tp1', 0)
        result['take_profit_2'] = result.get('tp2', 0)
        result['take_profit_3'] = result.get('tp3', 0)
        result['stop_loss'] = result.get('sl', 0)
        result.setdefault('confidence', 0)
        result.setdefault('rsi', 50)
        result.setdefault('volume_ratio', 1.0)
        result.setdefault('adx', 20)
        result.setdefault('mfi', 50)
        result.setdefault('bb_percent', 50)
        result.setdefault('strict_filters', 0)
        result.setdefault('reasons', [m.get('method', '') for m in result.get('top_methods', [])])
        result.setdefault('timestamp', str(datetime.now()))
        return result

    # ============ FIX 2: 50-method aggregate method එක හොයලා run කරන helper ============
    def _run_any_analysis(self, symbol, interval='5m'):
        """
        ඔයාගේ aggregate method එක (නම කුමක් වුනත්) හොයලා run කරනවා.
        Method එක හම්බුනා නම් ඒකේ result එක return කරනවා.
        """
        aggregate_names = [
            'analyze', 'get_signal', 'analyze_aggregate', 'aggregate_analysis',
            'full_analysis', 'analyze_symbol', 'analyze_coin', 'analyze_all',
            'run_full_analysis', 'get_aggregate_signal', 'check_signal'
        ]
        for name in aggregate_names:
            method = getattr(self, name, None)
            if method is None:
                continue
            try:
                result = method(symbol, interval)
            except TypeError:
                try:
                    result = method(symbol)
                except Exception as e:
                    logger.warning(f"{name}({symbol}) failed: {e}")
                    result = None
            except Exception as e:
                logger.warning(f"{name}({symbol}) failed: {e}")
                result = None
            if result:
                return result
            break  # Method එක හම්බුනා — result නැත්නම් fallback එකට යන්න
        return None

    # ============ FIX 3: find_short_signal — REPLACE (normalize කරලා දෙනවා) ============
    def find_short_signal(self, symbol, interval='5m'):
        """
        main.py call කරනවා — SELL signal එක හොයනවා.
        දැන් take_profit_1/stop_loss keys එක්ක return වෙනවා.
        """
        result = self._run_any_analysis(symbol, interval)
        if result is None:
            result = self._quick_short_analysis(symbol, interval)
        result = self._normalize_signal_dict(result)
        if result and result.get('signal') == 'SELL':
            key = f"{symbol}_SELL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if key not in self.signal_tracker:
                self.signal_tracker[key] = result
                self._save_signals()
            return result
        return None

    # ============ FIX 4: find_long_signal — NEW (BUY signals) ============
    def find_long_signal(self, symbol, interval='5m'):
        """
        main.py call කරනවා — BUY signal එක හොයනවා.
        මේක නැති නිසා තමයි 'no attribute' error එක ආවේ.
        """
        result = self._run_any_analysis(symbol, interval)
        if result is None:
            result = self._quick_short_analysis(symbol, interval)
        result = self._normalize_signal_dict(result)
        if result and result.get('signal') == 'BUY':
            key = f"{symbol}_BUY_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if key not in self.signal_tracker:
                self.signal_tracker[key] = result
                self._save_signals()
            return result
        return None

    # ============ FIX 5: check_power_buy_shana — REPLACE ('message' key එක add කරලා) ============
    def check_power_buy_shana(self, *args, **kwargs):
        """
        main.py call කරනවා — strong BUY signals list එක.
        හැම result එකකටම 'message' key එක add කරනවා
        (main.py ඒකෙන් තමයි Telegram message send කරන්නේ).
        """
        results = []
        for coin in COINS:
            try:
                result = self._run_any_analysis(coin, '5m')
                if result is None:
                    result = self._quick_short_analysis(coin, '5m')
                result = self._normalize_signal_dict(result)
                if result and result.get('signal') == 'BUY' and result.get('confidence', 0) >= 55:
                    # main.py එකට ඕනේ 'message' key එක pre-build කරනවා
                    result['message'] = (
                        f"🟢 *POWER BUY SIGNAL* 🟢\n\n"
                        f"📈 *{result['symbol']}*\n"
                        f"💰 Entry: `{result['entry']}`\n"
                        f"🎯 TP1: `{result['take_profit_1']}`\n"
                        f"🎯 TP2: `{result['take_profit_2']}`\n"
                        f"🛑 SL: `{result['stop_loss']}`\n"
                        f"⚡ Confidence: `{result['confidence']}%`\n"
                        f"📌 {', '.join(result['reasons'][:3])}\n\n"
                        f"⏰ {result['timestamp']}"
                    )
                    results.append(result)
            except Exception as e:
                logger.warning(f"check_power_buy_shana error {coin}: {e}")
                continue
        results.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        return results

    # ============ FIX 6: update_active_signals — REPLACE (tracker entries normalize කරලා) ============
    def update_active_signals(self, *args, **kwargs):
        """
        main.py call කරනවා — tracked signals වල live win% + status update කරනවා.
        හැම entry එකකටම take_profit_1/stop_loss keys add කරනවා.
        """
        updated = 0
        now = datetime.now()
        for key, sig in list(self.signal_tracker.items()):
            try:
                # tracker entries වලටත් take_profit_1/stop_loss keys add කරනවා
                sig.setdefault('take_profit_1', sig.get('tp1', 0))
                sig.setdefault('take_profit_2', sig.get('tp2', 0))
                sig.setdefault('take_profit_3', sig.get('tp3', 0))
                sig.setdefault('stop_loss', sig.get('sl', 0))
                sig.setdefault('status', 'ACTIVE')
                sig.setdefault('win_percentage', 0.0)

                symbol = sig.get('symbol', '')
                if not symbol:
                    continue
                ticker = self.get_ticker(symbol)
                if not ticker:
                    continue
                current = ticker['last']
                entry = sig.get('entry', 0) or 0
                tp1 = sig.get('take_profit_1', 0) or 0
                sl = sig.get('stop_loss', 0) or 0
                signal = sig.get('signal', 'NEUTRAL')

                sig['current_price'] = current
                sig['last_updated'] = now.isoformat()

                if signal == 'SELL':
                    # SHORT: price පහළට ගියොත් win
                    total = abs(entry - tp1)
                    if total > 0:
                        pct = min(100.0, round(abs(entry - current) / total * 100, 1))
                    else:
                        pct = float(sig.get('win_percentage', 50) or 50)
                    if current <= tp1:
                        sig['status'] = 'WIN'
                        sig['win_percentage'] = 100.0
                    elif current >= sl:
                        sig['status'] = 'LOST'
                        sig['win_percentage'] = 0.0
                    else:
                        sig['status'] = 'ACTIVE'
                        sig['win_percentage'] = pct
                elif signal == 'BUY':
                    # LONG: price උඩට ගියොත් win
                    total = abs(tp1 - entry)
                    if total > 0:
                        pct = min(100.0, round(abs(current - entry) / total * 100, 1))
                    else:
                        pct = float(sig.get('win_percentage', 50) or 50)
                    if current >= tp1:
                        sig['status'] = 'WIN'
                        sig['win_percentage'] = 100.0
                    elif current <= sl:
                        sig['status'] = 'LOST'
                        sig['win_percentage'] = 0.0
                    else:
                        sig['status'] = 'ACTIVE'
                        sig['win_percentage'] = pct
                else:
                    continue  # NEUTRAL signals skip

                updated += 1
            except Exception as e:
                logger.warning(f"update_active_signals error {key}: {e}")
                continue

        if updated > 0:
            self._save_signals()
        return updated
