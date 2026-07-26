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
            logger.info(f"📂 Loaded {len(self.signal_tracker)} signals from {self.data_file}")
        except (FileNotFoundError, json.JSONDecodeError):
            self.signal_tracker = {}
            logger.info(f"📂 No signal file found, starting fresh")

    def _save_signals(self):
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.signal_tracker, f, indent=2)
            logger.info(f"💾 Saved {len(self.signal_tracker)} signals to {self.data_file}")
        except Exception as e:
            logger.error(f"❌ Save error: {e}")

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
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5]),
                    'time': k[0]
                })
            return klines
        return None

    # ============ TECHNICAL INDICATORS ============
    def calculate_rsi(self, closes, period=14):
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def calculate_ema(self, closes, period):
        if len(closes) < period:
            return closes[-1] if closes else 0
        multiplier = 2 / (period + 1)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def calculate_macd(self, closes, fast=12, slow=26, signal=9):
        if len(closes) < slow:
            return {'macd': 0, 'signal': 0, 'histogram': 0}
        ema_fast = self.calculate_ema(closes, fast)
        ema_slow = self.calculate_ema(closes, slow)
        macd_line = ema_fast - ema_slow
        macd_signal = macd_line
        histogram = macd_line - macd_signal
        return {'macd': macd_line, 'signal': macd_signal, 'histogram': histogram}

    def calculate_bollinger(self, closes, period=20, std_dev=2):
        if len(closes) < period:
            return {'upper': closes[-1], 'middle': closes[-1], 'lower': closes[-1]}
        sma = sum(closes[-period:]) / period
        variance = sum((c - sma) ** 2 for c in closes[-period:]) / period
        std = variance ** 0.5
        return {
            'upper': sma + std_dev * std,
            'middle': sma,
            'lower': sma - std_dev * std
        }

    def calculate_volume_avg(self, klines, period=20):
        if len(klines) < period:
            return sum(k['volume'] for k in klines) / len(klines) if klines else 0
        return sum(k['volume'] for k in klines[-period:]) / period

    # ============ CORE ANALYSIS ============
    def analyze_coin_for_short(self, symbol):
        """Original short analysis - unchanged"""
        try:
            klines = self.get_klines(symbol, '5m', 50)
            ticker = self.get_ticker(symbol)
            if not klines or not ticker:
                return None

            closes = [k['close'] for k in klines]
            current_price = ticker['last']
            rsi = self.calculate_rsi(closes)
            ema_20 = self.calculate_ema(closes, 20)
            ema_50 = self.calculate_ema(closes, 50) if len(closes) >= 50 else ema_20
            bb = self.calculate_bollinger(closes)
            macd = self.calculate_macd(closes)
            avg_vol = self.calculate_volume_avg(klines)
            current_vol = klines[-1]['volume']
            change_24h = ticker['percentage']

            score = 0
            reasons = []
            strict_filters = 0

            # RSI analysis
            if rsi > 70:
                score += 25
                reasons.append(f"RSI overbought ({rsi:.1f})")
                strict_filters += 1
            elif rsi > 60:
                score += 15
                reasons.append(f"RSI elevated ({rsi:.1f})")

            # Price vs EMA
            if current_price < ema_20:
                score += 20
                reasons.append(f"Price below EMA20")
                if current_price < ema_50:
                    score += 10
                    reasons.append(f"Price below EMA50")
                    strict_filters += 1

            # Bollinger
            if current_price > bb['upper']:
                score += 20
                reasons.append("Above upper Bollinger")
                strict_filters += 1
            elif current_price > bb['middle']:
                score += 10
                reasons.append("Above mid Bollinger")

            # MACD
            if macd['histogram'] < -0.5:
                score += 15
                reasons.append("MACD bearish cross")
                strict_filters += 1
            elif macd['histogram'] < 0:
                score += 8
                reasons.append("MACD weakening")

            # Volume
            if current_vol > avg_vol * 1.5:
                score += 10
                reasons.append("High volume")
            if current_vol > avg_vol * 2:
                strict_filters += 1

            # Change 24h
            if change_24h > 2:
                score += 5
                reasons.append(f"Up {change_24h:.1f}% 24h")

            return {
                'symbol': symbol,
                'score': min(score, 100),
                'rsi': rsi,
                'current_price': current_price,
                'ema_20': ema_20,
                'ema_50': ema_50,
                'bollinger_upper': bb['upper'],
                'bollinger_lower': bb['lower'],
                'macd': macd,
                'volume_ratio': current_vol / avg_vol if avg_vol > 0 else 1,
                'change_24h': change_24h,
                'reasons': reasons,
                'strict_filters': strict_filters,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Analysis error {symbol}: {e}")
            return None

    def get_top_short_coins(self, limit=5):
        """Original - unchanged"""
        results = []
        for coin in COINS:
            try:
                analysis = self.analyze_coin_for_short(coin)
                if analysis and analysis['score'] >= 50:
                    results.append(analysis)
                time.sleep(0.05)
            except:
                continue
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

    # ============ TIMEFRAME ANALYSIS ============
    def analyze_coin_for_short_timeframe(self, symbol, timeframe='5m'):
        try:
            klines = self.get_klines(symbol, timeframe, 50)
            ticker = self.get_ticker(symbol)
            if not klines or not ticker:
                return None

            closes = [k['close'] for k in klines]
            current_price = ticker['last']
            rsi = self.calculate_rsi(closes)
            ema_20 = self.calculate_ema(closes, 20)
            ema_50 = self.calculate_ema(closes, 50) if len(closes) >= 50 else ema_20
            bb = self.calculate_bollinger(closes)
            macd = self.calculate_macd(closes)
            avg_vol = self.calculate_volume_avg(klines)
            current_vol = klines[-1]['volume']
            change_24h = ticker.get('percentage', 0)

            score = 0
            reasons = []
            strict_filters = 0

            if rsi > 70:
                score += 25; reasons.append(f"RSI overbought ({rsi:.1f})"); strict_filters += 1
            elif rsi > 60:
                score += 15; reasons.append(f"RSI elevated ({rsi:.1f})")
            if current_price < ema_20:
                score += 20; reasons.append(f"Price below EMA20")
                if current_price < ema_50:
                    score += 10; reasons.append(f"Price below EMA50"); strict_filters += 1
            if current_price > bb['upper']:
                score += 20; reasons.append("Above upper Bollinger"); strict_filters += 1
            elif current_price > bb['middle']:
                score += 10; reasons.append("Above mid Bollinger")
            if macd['histogram'] < -0.5:
                score += 15; reasons.append("MACD bearish cross"); strict_filters += 1
            elif macd['histogram'] < 0:
                score += 8; reasons.append("MACD weakening")
            if current_vol > avg_vol * 1.5:
                score += 10; reasons.append("High volume")
            if current_vol > avg_vol * 2:
                strict_filters += 1
            if change_24h > 2:
                score += 5; reasons.append(f"Up {change_24h:.1f}% 24h")

            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'score': min(score, 100),
                'rsi': rsi,
                'current_price': current_price,
                'change_24h': change_24h,
                'reasons': reasons,
                'strict_filters': strict_filters,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"TF analysis error {symbol} {timeframe}: {e}")
            return None

    def get_top_short_coins_timeframe(self, limit=20, timeframe='5m'):
        results = []
        for coin in COINS:
            try:
                analysis = self.analyze_coin_for_short_timeframe(coin, timeframe)
                if analysis and analysis['score'] >= 40:
                    results.append(analysis)
                time.sleep(0.05)
            except:
                continue
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

    # ============ SIGNAL GENERATION ============
    def find_short_signal(self, symbol):
        try:
            analysis = self.analyze_coin_for_short(symbol)
            if not analysis or analysis['score'] < 50:
                return None

            entry = analysis['current_price']
            # TP1 = entry - (5 x ATR approximation)
            tp1 = entry * 0.97
            tp2 = entry * 0.93
            sl = entry * 1.03

            signal_key = f"{symbol}_SHORT_{int(time.time())}"
            signal = {
                'key': signal_key,
                'symbol': symbol,
                'signal': 'SHORT',
                'timeframe': '5m',
                'entry': entry,
                'take_profit_1': tp1,
                'take_profit_2': tp2,
                'stop_loss': sl,
                'confidence': analysis['score'],
                'rsi': analysis['rsi'],
                'change_24h': analysis.get('change_24h', 0),
                'reasons': analysis['reasons'],
                'strict_filters': analysis['strict_filters'],
                'status': 'ACTIVE',
                'win_percentage': 50,
                'timestamp': datetime.now().isoformat(),
                'is_user_signal': False
            }

            self.signal_tracker[signal_key] = signal
            self._save_signals()
            logger.info(f"🚨 SHORT signal generated: {symbol} ({analysis['score']}%)")
            return signal
        except Exception as e:
            logger.error(f"Short signal error {symbol}: {e}")
            return None

    def find_long_signal(self, symbol):
        try:
            klines = self.get_klines(symbol, '5m', 50)
            ticker = self.get_ticker(symbol)
            if not klines or not ticker:
                return None
            closes = [k['close'] for k in klines]
            rsi = self.calculate_rsi(closes)
            entry = ticker['last']
            tp1 = entry * 1.03
            sl = entry * 0.97
            if rsi < 30:
                signal = {
                    'key': f"{symbol}_LONG_{int(time.time())}",
                    'symbol': symbol, 'signal': 'LONG', 'timeframe': '5m',
                    'entry': entry, 'take_profit_1': tp1, 'stop_loss': sl,
                    'confidence': 70 if rsi < 25 else 50,
                    'rsi': rsi, 'reasons': [f"RSI oversold ({rsi:.1f})"],
                    'status': 'ACTIVE', 'win_percentage': 50,
                    'timestamp': datetime.now().isoformat(),
                    'is_user_signal': False
                }
                self.signal_tracker[signal['key']] = signal
                self._save_signals()
                return signal
            return None
        except Exception as e:
            return None

    def generate_short_signal_from_scan_timeframe(self, symbol, timeframe='5m'):
        try:
            analysis = self.analyze_coin_for_short_timeframe(symbol, timeframe)
            if not analysis or analysis['score'] < 40:
                return None

            entry = analysis['current_price']
            tp1 = entry * 0.97
            tp2 = entry * 0.93
            sl = entry * 1.03

            signal_key = f"{symbol}_SHORT_{int(time.time())}"
            signal = {
                'key': signal_key,
                'symbol': symbol,
                'signal': 'SHORT',
                'timeframe': timeframe,
                'entry': entry,
                'take_profit_1': tp1,
                'take_profit_2': tp2,
                'stop_loss': sl,
                'confidence': analysis['score'],
                'rsi': analysis['rsi'],
                'change_24h': analysis.get('change_24h', 0),
                'reasons': analysis.get('reasons', []),
                'strict_filters': analysis.get('strict_filters', 0),
                'status': 'ACTIVE',
                'win_percentage': 50,
                'timestamp': datetime.now().isoformat(),
                'is_user_signal': False
            }

            self.signal_tracker[signal_key] = signal
            self._save_signals()
            logger.info(f"🚨 SHORT signal ({timeframe}): {symbol} ({analysis['score']}%)")
            return signal
        except Exception as e:
            logger.error(f"TF signal gen error {symbol}: {e}")
            return None

    # ============ LIVE TRACKING ============
    def get_live_signal_percentage(self, symbol, signal_type='SHORT'):
        try:
            ticker = self.get_ticker(symbol)
            if not ticker:
                return None
            current = ticker['last']

            # Find most recent signal for this symbol
            signal = None
            for key, sig in self.signal_tracker.items():
                if sig.get('symbol') == symbol and sig.get('signal') == signal_type:
                    if signal is None or sig.get('timestamp', '') > signal.get('timestamp', ''):
                        signal = sig

            if not signal:
                return None

            entry = signal['entry']
            tp1 = signal.get('take_profit_1', signal.get('tp1', entry * 0.97))
            sl = signal.get('stop_loss', signal.get('sl', entry * 1.03))
            status = signal.get('status', 'ACTIVE')

            # Calculate win percentage
            if signal_type == 'SHORT':
                # TP below entry, SL above entry
                total_range = abs(entry - tp1) + abs(entry - sl)
                if total_range == 0:
                    win_pct = 50
                elif status == 'WIN':
                    win_pct = 100
                elif status == 'LOST':
                    win_pct = 0
                else:
                    if current <= tp1:
                        win_pct = 100
                        status = 'WIN'
                    elif current >= sl:
                        win_pct = 0
                        status = 'LOST'
                    elif current < entry:
                        progress = (entry - current) / (entry - tp1)
                        win_pct = min(99, progress * 100)
                    else:
                        progress = (current - entry) / (sl - entry)
                        win_pct = max(1, (1 - progress) * 100)
            else:
                total_range = abs(tp1 - entry) + abs(sl - entry)
                if total_range == 0:
                    win_pct = 50
                elif status == 'WIN':
                    win_pct = 100
                elif status == 'LOST':
                    win_pct = 0
                else:
                    if current >= tp1:
                        win_pct = 100; status = 'WIN'
                    elif current <= sl:
                        win_pct = 0; status = 'LOST'
                    elif current > entry:
                        progress = (current - entry) / (tp1 - entry)
                        win_pct = min(99, progress * 100)
                    else:
                        progress = (entry - current) / (entry - sl)
                        win_pct = max(1, (1 - progress) * 100)

            # Update tracker
            for key in list(self.signal_tracker.keys()):
                if self.signal_tracker[key].get('key') == signal.get('key'):
                    self.signal_tracker[key]['status'] = status
                    self.signal_tracker[key]['win_percentage'] = win_pct
                    self._save_signals()
                    break

            return {
                'symbol': symbol,
                'signal': signal_type,
                'entry': entry,
                'current_price': current,
                'tp1': tp1,
                'sl': sl,
                'status': status,
                'win_percentage': win_pct
            }
        except Exception as e:
            logger.error(f"Live tracking error {symbol}: {e}")
            return None

    def update_active_signals(self):
        updated = 0
        for key, sig in self.signal_tracker.items():
            if sig.get('status') == 'ACTIVE':
                try:
                    live = self.get_live_signal_percentage(sig['symbol'], sig['signal'])
                    if live:
                        sig['status'] = live['status']
                        sig['win_percentage'] = live['win_percentage']
                        updated += 1
                except:
                    pass
        if updated > 0:
            self._save_signals()
        return updated

    # ============ LIVE PRICES ============
    def get_all_live_prices(self):
        try:
            prices = []
            for coin in COINS:
                ticker = self.get_ticker(coin)
                if ticker:
                    prices.append({
                        'symbol': coin,
                        'price': ticker['last'],
                        'change_24h': ticker['percentage'],
                        'volume_24h': ticker['quoteVolume']
                    })
                time.sleep(0.05)
            return prices
        except Exception as e:
            logger.error(f"Live prices error: {e}")
            return []

    # ============ POWER BUY SHANA ============
    def check_power_buy_shana(self):
        power_signals = []
        try:
            for key, sig in self.signal_tracker.items():
                if sig.get('status') == 'WIN' and sig.get('win_percentage', 0) >= 80:
                    if not sig.get('power_buy_sent', False):
                        power_signals.append({
                            'symbol': sig['symbol'],
                            'message': f"💀🔥 *POWER BUY SHANA* 🔥💀\n\n🏆 *{sig['symbol']}* TP HIT!\n📊 WIN%: {sig['win_percentage']:.1f}%\n💰 Entry: ${sig['entry']:.8f}\n🎯 {sig['signal']} Signal WIN ✅"
                        })
                        self.signal_tracker[key]['power_buy_sent'] = True
                        self._save_signals()
        except Exception as e:
            logger.error(f"Power buy error: {e}")
        return power_signals

    # ============ STATS & RECALL (ORIGINAL) ============
    def get_enhanced_stats(self):
        stats = {
            'total_signals': len(self.signal_tracker),
            'total_wins': 0, 'total_losses': 0,
            'active_signals': 0, 'expired_signals': 0,
            'win_rate': 0, 'loss_rate': 0,
            'best_signal': None, 'worst_signal': None,
            'by_symbol': {}
        }
        for key, sig in self.signal_tracker.items():
            status = sig.get('status', 'ACTIVE')
            if status == 'WIN': stats['total_wins'] += 1
            elif status == 'LOST': stats['total_losses'] += 1
            elif status == 'ACTIVE': stats['active_signals'] += 1
            elif status == 'EXPIRED': stats['expired_signals'] += 1

            sym = sig.get('symbol', 'UNKNOWN')
            if sym not in stats['by_symbol']:
                stats['by_symbol'][sym] = {'wins': 0, 'losses': 0, 'active': 0, 'expired': 0}
            if status == 'WIN': stats['by_symbol'][sym]['wins'] += 1
            elif status == 'LOST': stats['by_symbol'][sym]['losses'] += 1
            elif status == 'ACTIVE': stats['by_symbol'][sym]['active'] += 1
            elif status == 'EXPIRED': stats['by_symbol'][sym]['expired'] += 1

        completed = stats['total_wins'] + stats['total_losses']
        if completed > 0:
            stats['win_rate'] = (stats['total_wins'] / completed) * 100
            stats['loss_rate'] = (stats['total_losses'] / completed) * 100
        return stats

    def get_signal_recall_list(self, limit=50):
        signals = []
        for key, sig in self.signal_tracker.items():
            signals.append({
                'key': key,
                'symbol': sig.get('symbol', ''),
                'signal': sig.get('signal', ''),
                'entry': sig.get('entry', 0),
                'confidence': sig.get('confidence', 0),
                'status': sig.get('status', 'ACTIVE'),
                'win_percentage': sig.get('win_percentage', 50),
                'timestamp': sig.get('timestamp', '')
            })
        signals.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return signals[:limit]

    def get_signal_journey(self, signal_key):
        if signal_key in self.signal_tracker:
            sig = self.signal_tracker[signal_key]
            return {
                'signal_key': signal_key,
                'symbol': sig.get('symbol', ''),
                'signal': sig.get('signal', ''),
                'entry': sig.get('entry', 0),
                'tp1': sig.get('take_profit_1', sig.get('tp1', 0)),
                'sl': sig.get('stop_loss', sig.get('sl', 0)),
                'confidence': sig.get('confidence', 0),
                'status': sig.get('status', 'ACTIVE'),
                'win_percentage': sig.get('win_percentage', 50),
                'timestamp': sig.get('timestamp', ''),
                'reasons': sig.get('reasons', []),
                'history': [
                    {'time': sig.get('timestamp', ''), 'price': sig.get('entry', 0), 'action': 'ENTRY'}
                ]
            }
        return None

    def format_signal_journey_display(self, journey):
        if not journey:
            return "No journey data"
        lines = [
            f"📋 SIGNAL JOURNEY: {journey.get('symbol', '')}",
            f"{'═'*40}",
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
            lines.append(f"{'═'*40}")
            for h in journey['history']:
                lines.append(f"  {h.get('time','')[:16]} - ${h.get('price',0):.8f} ({h.get('action','')})")
        return '\n'.join(lines)

    # ============ 🔥 NEW: USER-SPECIFIC SIGNAL TRACKING (for STATS & Recall) ============
    def mark_user_signal(self, symbol, signal_type, entry, timestamp):
        """Mark a signal as belonging to USER (for STATS/Recall filtering only)"""
        try:
            # Try exact match first
            for key, sig in list(self.signal_tracker.items()):
                if (sig.get('symbol') == symbol and 
                    sig.get('signal') == signal_type and
                    abs(float(sig.get('entry', 0)) - float(entry)) < 0.0001 and
                    str(sig.get('timestamp', ''))[:10] == str(timestamp)[:10]):
                    
                    sig['is_user_signal'] = True
                    sig['user_timestamp'] = str(datetime.now())
                    self._save_signals()
                    logger.info(f"✅ Marked user signal: {symbol} {signal_type}")
                    return True
            
            # Fallback: match by symbol + signal type only
            for key, sig in list(self.signal_tracker.items()):
                if sig.get('symbol') == symbol and sig.get('signal') == signal_type:
                    sig['is_user_signal'] = True
                    sig['user_timestamp'] = str(datetime.now())
                    self._save_signals()
                    logger.info(f"✅ Marked user signal (generic): {symbol} {signal_type}")
                    return True
            
            logger.warning(f"⚠️ Could not find signal to mark: {symbol} {signal_type}")
            return False
        except Exception as e:
            logger.error(f"mark_user_signal error: {e}")
            return False

    def get_user_stats(self):
        """Get stats for USER signals only (not system/scan signals)"""
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
        """Get recall list for USER signals only (not system/scan signals)"""
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
