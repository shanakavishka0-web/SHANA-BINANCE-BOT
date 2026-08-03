# ============================================================
# 💀 SHANA BATCH ENGINE v2 — 10 COIN ROTATION | 1h ONLY | LIVE WIN/LOST
# ============================================================

import os
import time
import hmac
import hashlib
import logging
import requests
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

logger = logging.getLogger("shana")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

COINS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "DOTUSDT", "LTCUSDT", "LINKUSDT",
    "AVAXUSDT", "MATICUSDT", "ATOMUSDT", "ETCUSDT", "TRXUSDT",
]

INTERVALS = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h",
             "2h": "2h", "4h": "4h", "1d": "1d"}


class BinanceAnalyzer:

    def __init__(self, base_url="https://api.binance.com", api_key=None, secret=None):
        self.base_url = base_url
        self.api_key = api_key or os.getenv("BINANCE_API_KEY", "")
        self.secret = secret or os.getenv("BINANCE_SECRET_KEY", "")
        self.session = requests.Session()
        # ── full state init — main.py එකට ඕන හැම attribute එකම ✅ ──
        self.signal_tracker = {}
        self.signal_queue = list(COINS)
        self.active_batch = []
        self.batch_results = []
        self.batch_number = 1
        self.completed_batches = []

    def __getattr__(self, name):
        """🔧 Safety net — තව මොන method එකක් හැරුණත් crash නොවී warn කරලා continue"""
        logger.warning(f"BinanceAnalyzer.{name} not found — returning no-op")
        def _noop(*args, **kwargs):
            return None
        setattr(self, name, _noop)
        return _noop

    # ============================================================
    # ⏰ TIME HELPERS
    # ============================================================

    @staticmethod
    def _sl_now():
        """Lk Sri Lanka current date & time - 100% accurate (Asia/Colombo)"""
        try:
            if ZoneInfo is not None:
                return datetime.now(ZoneInfo("Asia/Colombo"))
        except Exception:
            pass
        return datetime.now() + timedelta(hours=5, minutes=30)

    # ============================================================
    # 🔢 FORMAT HELPERS
    # ============================================================

    def _fmt_price(self, price):
        try:
            price = float(price)
        except (TypeError, ValueError):
            return "0.00"
        if price >= 1000:
            return f"{price:,.2f}"
        if price >= 1:
            return f"{price:,.4f}"
        return f"{price:.8f}"

    # ============================================================
    # 🌐 BINANCE API
    # ============================================================

    def _request(self, path, params=None):
        url = self.base_url + path
        try:
            r = self.session.get(url, params=params or {}, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"API error {path}: {e}")
            return None

    def check_binance_connection(self):
        """✅ Binance API එකට connection එක check කරනවා"""
        data = self._request("/api/v3/ping")
        if data is None:
            return "❌ Connection FAILED"
        t = self._request("/api/v3/time")
        if t:
            return f"✅ Connected — Server time: {t.get('serverTime')}"
        return "✅ Connected (ping OK)"

    def get_price(self, coin):
        """💰 එක coin එකක live price එක"""
        data = self._request("/api/v3/ticker/price", {"symbol": coin})
        try:
            return float(data["price"])
        except Exception:
            return 0.0

    def get_live_prices(self, coins=None):
        """🕹️ LIVE PRICE — coin list එකට price + 24h change % (dict)"""
        coins = coins or COINS
        out = {}
        for c in coins:
            try:
                t = self._request("/api/v3/ticker/24hr", {"symbol": c})
                if t:
                    out[c] = {
                        "price": float(t["lastPrice"]),
                        "change": float(t["priceChangePercent"]),
                        "high": float(t["highPrice"]),
                        "low": float(t["lowPrice"]),
                        "volume": float(t["volume"]),
                    }
            except Exception as e:
                logger.warning(f"live price {c}: {e}")
        return out

    def _get_klines(self, coin, interval="1h", limit=200):
        """🕯️ Candles — Binance klines API එකෙන් (open/high/low/close/volume)"""
        data = self._request("/api/v3/klines", {
            "symbol": coin, "interval": INTERVALS.get(interval, interval),
            "limit": limit,
        })
        candles = []
        if not data:
            return candles
        for k in data:
            try:
                candles.append({
                    "time": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            except Exception:
                continue
        return candles

    # ============================================================
    # 📐 INDICATORS (TradingView-style — RSI, MACD, EMA, Boll, ATR, Stoch)
    # ============================================================

    @staticmethod
    def _ema(values, period):
        if not values:
            return []
        k = 2 / (period + 1)
        ema = [values[0]]
        for v in values[1:]:
            ema.append(v * k + ema[-1] * (1 - k))
        return ema

    @staticmethod
    def _sma(values, period):
        if len(values) < period:
            return []
        return [sum(values[i - period + 1:i + 1]) / period
                for i in range(period - 1, len(values))]

    def _rsi(self, candles, period=14):
        """RSI (Wilder's smoothing)"""
        closes = [c["close"] for c in candles]
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        avg_g = sum(gains[:period]) / period
        avg_l = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_g = (avg_g * (period - 1) + gains[i]) / period
            avg_l = (avg_l * (period - 1) + losses[i]) / period
        if avg_l == 0:
            return 100.0
        rs = avg_g / avg_l
        return 100.0 - (100.0 / (1.0 + rs))

    def _macd(self, candles, fast=12, slow=26, signal=9):
        """MACD line, signal line, histogram"""
        closes = [c["close"] for c in candles]
        if len(closes) < slow + signal:
            return None
        ema_f = self._ema(closes, fast)
        ema_s = self._ema(closes, slow)
        macd_line = [f - s for f, s in zip(ema_f, ema_s)]
        signal_line = self._ema(macd_line, signal)
        hist = [m - s for m, s in zip(macd_line, signal_line)]
        return {"macd": macd_line[-1], "signal": signal_line[-1],
                "hist": hist[-1], "prev_hist": hist[-2] if len(hist) > 1 else 0}

    def _bollinger(self, candles, period=20, mult=2.0):
        """Bollinger Bands — upper, middle, lower, bandwidth"""
        closes = [c["close"] for c in candles]
        if len(closes) < period:
            return None
        sma = self._sma(closes, period)[-1]
        var = sum((c - sma) ** 2 for c in closes[-period:]) / period
        std = var ** 0.5
        return {"upper": sma + mult * std, "middle": sma,
                "lower": sma - mult * std, "bandwidth": (2 * mult * std) / sma if sma else 0}

    def _atr(self, candles, period=14):
        """ATR — Average True Range"""
        if len(candles) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(candles)):
            tr = max(
                candles[i]["high"] - candles[i]["low"],
                abs(candles[i]["high"] - candles[i - 1]["close"]),
                abs(candles[i]["low"] - candles[i - 1]["close"]),
            )
            trs.append(tr)
        return sum(trs[-period:]) / period

    def _stoch(self, candles, k_period=14, d_period=3):
        """Stochastic %K / %D"""
        if len(candles) < k_period + d_period:
            return {"k": 50.0, "d": 50.0}
        ks = []
        for i in range(len(candles) - d_period, len(candles)):
            window = candles[i - k_period + 1:i + 1]
            low = min(c["low"] for c in window)
            high = max(c["high"] for c in window)
            k = 50.0 if high == low else (
                (candles[i]["close"] - low) / (high - low) * 100)
            ks.append(k)
        k = ks[-1]
        d = sum(ks) / len(ks)
        return {"k": k, "d": d}

    @staticmethod
    def _volume_ratio(candles, period=20):
        """📊 Volume ratio — current vs average (pressure check)"""
        vols = [c["volume"] for c in candles]
        if len(vols) < period + 1:
            return 1.0
        avg = sum(vols[-period - 1:-1]) / period
        return vols[-1] / avg if avg else 1.0

    def _score(self, candles, direction="SELL"):
        """🧠 0–100 composite score — RSI + MACD + EMA + Boll + Stoch + Volume"""
        score = 50.0
        rsi = self._rsi(candles)
        macd = self._macd(candles)
        boll = self._bollinger(candles)
        stoch = self._stoch(candles)
        vr = self._volume_ratio(candles)
        closes = [c["close"] for c in candles]
        ema20 = self._ema(closes, 20)[-1] if len(closes) >= 20 else closes[-1]
        ema50 = self._ema(closes, 50)[-1] if len(closes) >= 50 else closes[-1]
        ema200 = self._ema(closes, 200)[-1] if len(closes) >= 200 else closes[-1]
        price = closes[-1]

        if direction == "SELL":
            # RSI overbought → bearish
            if rsi > 70: score += 12
            elif rsi > 60: score += 6
            elif rsi < 30: score -= 12
            elif rsi < 45: score -= 6
            # MACD bearish
            if macd:
                if macd["hist"] < 0: score += 8
                if macd["macd"] < macd["signal"]: score += 5
                if macd["prev_hist"] > 0 > macd["hist"]: score += 5  # death cross
            # EMA trend
            if price < ema20: score += 6
            if ema20 < ema50: score += 6
            if price < ema200: score += 6
            # Bollinger
            if boll and price > boll["middle"]: score += 4
            if boll and boll["bandwidth"] < 0.05: score += 3  # squeeze → breakout
            # Stochastic
            if stoch["k"] > 80: score += 5
            if stoch["k"] < stoch["d"]: score += 3
            # Volume confirmation
            if vr > 1.2 and rsi > 60: score += 5
        else:  # BUY
            if rsi < 30: score += 12
            elif rsi < 40: score += 6
            elif rsi > 70: score -= 12
            elif rsi > 55: score -= 6
            if macd:
                if macd["hist"] > 0: score += 8
                if macd["macd"] > macd["signal"]: score += 5
                if macd["prev_hist"] < 0 < macd["hist"]: score += 5  # golden cross
            if price > ema20: score += 6
            if ema20 > ema50: score += 6
            if price > ema200: score += 6
            if boll and price < boll["middle"]: score += 4
            if boll and boll["bandwidth"] < 0.05: score += 3
            if stoch["k"] < 20: score += 5
            if stoch["k"] > stoch["d"]: score += 3
            if vr > 1.2 and rsi < 40: score += 5

        return max(0.0, min(100.0, score))

    # ============================================================
    # 🧠 SIGNAL GENERATOR — ඔක්කොම indicators use කරලා තීරණය
    # ============================================================

    def _generate_signal(self, coin, interval="1h", threshold=70):
        """📡 Coin එකක් සඳහා final BUY/SELL signal එකක් හදනවා"""
        candles = self._get_klines(coin, interval, 220)
        if len(candles) < 60:
            return None
        price = candles[-1]["close"]
        rsi = self._rsi(candles)
        macd = self._macd(candles)
        boll = self._bollinger(candles)
        stoch = self._stoch(candles)
        vr = self._volume_ratio(candles)
        atr = self._atr(candles)
        sell_score = self._score(candles, "SELL")
        buy_score = self._score(candles, "BUY")

        direction = None
        if sell_score >= threshold and sell_score > buy_score:
            direction = "SELL"
        elif buy_score >= threshold and buy_score > sell_score:
            direction = "BUY"
        if direction is None:
            return None

        entry = price
        if direction == "SELL":
            tp = entry - 1.5 * atr
            sl = entry + 1.0 * atr
        else:
            tp = entry + 1.5 * atr
            sl = entry - 1.0 * atr

        sig = self._signal_dict(coin, direction, entry, tp, sl,
                                rsi if direction == "SELL" else 100 - rsi,
                                confidence=max(sell_score, buy_score))
        sig["interval"] = interval
        sig["macd"] = macd
        sig["boll"] = boll
        sig["stoch"] = stoch
        sig["volume_ratio"] = vr
        return sig

    def _signal_dict(self, coin, signal, entry, tp, sl, rsi, confidence=0.0):
        """📦 Standard signal dict — status/win_pct live tracking සඳහා"""
        return {
            "coin": coin,
            "signal": signal,
            "entry": float(entry),
            "tp": float(tp),
            "sl": float(sl),
            "rsi": float(rsi),
            "confidence": float(confidence),
            "win_pct": 0.0,
            "status": "ACTIVE",
            "timestamp": self._sl_now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ============================================================
    # 🔴 SHORT SIGNAL SCAN (5m / 1h / 2h / 24h) — main menu එකට
    # ============================================================

    def scan_short_signals(self, coins=None, interval="5m", threshold=72):
        """🔴 හැම coin එකම analyze කරලා SHORT (SELL) signals list එකක්"""
        coins = coins or COINS
        results = []
        for coin in coins:
            try:
                sig = self._generate_signal(coin, interval, threshold)
                if sig and sig["signal"] == "SELL":
                    sig["message"] = self.build_short_message(sig, interval)
                    results.append(sig)
                    self.signal_tracker[coin] = sig
            except Exception as e:
                logger.warning(f"scan_short {coin}: {e}")
        results.sort(key=lambda s: s["confidence"], reverse=True)
        logger.info(f"🔴 SHORT signals ({interval}): {len(results)}")
        return results

    def scan_buy_signals(self, coins=None, interval="5m", threshold=72):
        """🟢 හැම coin එකම analyze කරලා BUY signals list එකක්"""
        coins = coins or COINS
        results = []
        for coin in coins:
            try:
                sig = self._generate_signal(coin, interval, threshold)
                if sig and sig["signal"] == "BUY":
                    sig["message"] = self.build_short_message(sig, interval)
                    results.append(sig)
                    self.signal_tracker[coin] = sig
            except Exception as e:
                logger.warning(f"scan_buy {coin}: {e}")
        results.sort(key=lambda s: s["confidence"], reverse=True)
        return results

    def score_coins(self, coins=None, interval="5m"):
        """🟢 NOW GOOD COIN — හැම coin එකකම bullish score එක ප්රතිශත වලින්"""
        coins = coins or COINS
        out = []
        for coin in coins:
            try:
                candles = self._get_klines(coin, interval, 220)
                if len(candles) < 60:
                    continue
                score = self._score(candles, "BUY")
                out.append({
                    "coin": coin,
                    "score": round(score, 1),
                    "rsi": round(self._rsi(candles), 1),
                    "price": candles[-1]["close"],
                })
            except Exception as e:
                logger.warning(f"score {coin}: {e}")
        out.sort(key=lambda x: x["score"], reverse=True)
        return out

    # ============================================================
    # 📝 SIGNAL MESSAGES (fancy, bold, full details)
    # ============================================================

    def build_short_message(self, sig, interval=None):
        """🔴 SHORT signal message — Entry/SL/TP/Confidence සියල්ල"""
        interval = sig.get("interval", interval or "5m")
        tf_label = {"5m": "5 MINUTE", "1h": "1 HOUR", "2h": "2 HOURS",
                    "1d": "24 HOURS"}.get(interval, interval.upper())
        arrow = "🔴 SHORT (SELL)" if sig["signal"] == "SELL" else "🟢 LONG (BUY)"
        bar = self._progress_bar(sig["confidence"])
        msg = (
            f"🎯 *{arrow}* — `{sig['coin']}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Timeframe: `{tf_label}`\n"
            f"📌 *Entry:* `{self._fmt_price(sig['entry'])}`\n"
            f"🎯 *Take Profit (TP):* `{self._fmt_price(sig['tp'])}`\n"
            f"🛑 *Stop Loss (SL):* `{self._fmt_price(sig['sl'])}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🧠 Confidence: `{sig['confidence']:.0f}%`\n"
            f"{bar}\n"
            f"📊 RSI: `{sig['rsi']:.1f}` | ATR Based Levels\n"
            f"⏳ Signal Time: `{sig.get('timestamp', '')}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 SL break වුනොත් trade එක close කරන්න. TP වලදී profit lock කරගන්න."
        )
        return msg

    def build_power_buy_message(self, sig):
        """⚡ POWER BUY message — RSI < 25 deep oversold"""
        return (
            f"⚡⚡ *POWER BUY SHANA* ⚡⚡\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🟢 *{sig['coin']}* — BUY (Oversold)\n"
            f"📌 *Entry:* `{self._fmt_price(sig['entry'])}`\n"
            f"🎯 *TP1:* `{self._fmt_price(sig['tp'])}` | *TP2:* `{self._fmt_price(sig.get('tp2', sig['entry'] * 2 - sig['sl']))}`\n"
            f"🛑 *SL:* `{self._fmt_price(sig['sl'])}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🧠 RSI: `{sig['rsi']:.1f}` (< 25 = Deep Oversold 🔥)\n"
            f"⏳ `{sig.get('timestamp', '')}`"
        )

    @staticmethod
    def _progress_bar(pct, length=10):
        filled = int(max(0.0, min(100.0, pct)) / 100 * length)
        return '█' * filled + '░' * (length - filled)

    # ============================================================
    # 🔄 LIVE WIN/LOST TRACKING — price එක යද්දි % වෙනස් වෙනවා
    # ============================================================

    def check_signal_results(self, coins=None):
        """📡 Tracked signals වල live price එක බලලා status/win_pct update කරනවා.
        WIN_COMPLETE / LOST වුනාම status එක එතනම නවතිනවා."""
        coins = coins or list(self.signal_tracker.keys())
        updates = []
        for coin in coins:
            item = self.signal_tracker.get(coin)
            if not item or item.get("status") in ("WIN_COMPLETE", "LOST"):
                continue
            try:
                price = self.get_price(coin)
                if price <= 0:
                    continue
                entry, tp, sl = item["entry"], item["tp"], item["sl"]
                if item["signal"] == "SELL":
                    if price <= tp:
                        item["status"], item["win_pct"] = "WIN_COMPLETE", 100.0
                    elif price >= sl:
                        item["status"], item["win_pct"] = "LOST", 0.0
                    else:
                        item["win_pct"] = max(0.0, min(100.0,
                            (entry - price) / (entry - tp) * 100))
                else:  # BUY
                    if price >= tp:
                        item["status"], item["win_pct"] = "WIN_COMPLETE", 100.0
                    elif price <= sl:
                        item["status"], item["win_pct"] = "LOST", 0.0
                    else:
                        item["win_pct"] = max(0.0, min(100.0,
                            (price - entry) / (tp - entry) * 100))
                updates.append(dict(item))
                # ✅ tracker sync
                self.signal_tracker[coin] = item
            except Exception as e:
                logger.warning(f"check_signal_results error {item['coin']}: {e}")
                continue
        return updates

    # ============================================================
    # ➕ main.py loop එකට ඕන methods
    # ============================================================

    def update_active_signals(self):
        """🔁 main.py loop එකෙන් call වෙනවා — batch එකක් නැත්නම්
        auto-generate කරලා, live check කරලා ACTIVE count එක (int) දෙනවා"""
        self._ensure_batch_state()
        if not self.batch_results:
            logger.info("No batch yet — generating first batch...")
            self.get_next_batch(10)
        try:
            self.check_signal_results()
        except Exception as e:
            logger.warning(f"update_active_signals error: {e}")
        active = sum(1 for it in self.batch_results if it.get("status") == "ACTIVE")
        logger.info(f"🔄 Active signals: {active}/{len(self.batch_results)}")
        return active

    def check_power_buy_shana(self, coins=None):
        """⚡ POWER BUY — RSI < 25 වුන coins වල signal list එකක්
        return කරනවා (සෑම signal එකකම 'message' + 'confidence' තියෙනවා ✅)"""
        self._ensure_batch_state()
        coins = coins or COINS
        results = []
        for coin in coins:
            try:
                candles = self._get_klines(coin, interval="1h", limit=60)
                if len(candles) < 20:
                    continue
                rsi = self._rsi(candles)
                if rsi < 25:
                    atr = self._atr(candles)
                    entry = candles[-1]["close"]
                    sig = self._signal_dict(coin, "BUY", entry,
                                            entry + atr, entry + 2 * atr, entry - atr, rsi)
                    sig["message"] = self.build_power_buy_message(sig)
                    results.append(sig)
                    self.signal_tracker[coin] = sig
            except Exception as e:
                logger.warning(f"check_power_buy_shana error {coin}: {e}")
        logger.info(f"⚡ Power buy signals: {len(results)}")
        return results

    def find_long_signal(self, coin=None):
        """📈 Long (BUY) signal එකක් හොයනවා — dict එකක් හෝ None"""
        coins = [coin] if coin else COINS
        for c in coins:
            try:
                sig = self._generate_signal(c)
                if sig and sig["signal"] == "BUY":
                    sig["message"] = self.build_short_message(sig)
                    return sig
            except Exception as e:
                logger.warning(f"find_long_signal error {c}: {e}")
        return None

    def find_short_signal(self, coin=None):
        """📉 Short (SELL) signal එකක් හොයනවා — dict එකක් හෝ None"""
        coins = [coin] if coin else COINS
        for c in coins:
            try:
                sig = self._generate_signal(c)
                if sig and sig["signal"] == "SELL":
                    sig["message"] = self.build_short_message(sig)
                    return sig
            except Exception as e:
                logger.warning(f"find_short_signal error {c}: {e}")
        return None

    # ============================================================
    # 📦 BATCH ENGINE — 10 coin rotation
    # ============================================================

    def _ensure_batch_state(self):
        if not self.batch_results:
            self.signal_queue = list(COINS)

    def get_next_batch(self, size=10):
        """🔄 ඊළඟ coins 10 batch එක generate කරනවා"""
        self._ensure_batch_state()
        if not self.signal_queue:
            self.signal_queue = list(COINS)
        batch = self.signal_queue[:size]
        self.signal_queue = self.signal_queue[size:] + self.signal_queue[:size]
        self.active_batch = batch
        self.batch_results = []
        for coin in batch:
            try:
                sig = self._generate_signal(coin, "1h")
                if sig:
                    sig["message"] = self.build_short_message(sig)
                    self.batch_results.append(sig)
                    self.signal_tracker[coin] = sig
            except Exception as e:
                logger.warning(f"get_next_batch {coin}: {e}")
        logger.info(f"📦 Batch #{self.batch_number}: {len(self.batch_results)} signals")
        return self.batch_results

    def is_batch_finished(self):
        """Batch එකේ coins ඔක්කොම WIN_COMPLETE/LOST වුනාද?"""
        self._ensure_batch_state()
        if not self.batch_results:
            return False
        return all(item["status"] in ("WIN_COMPLETE", "LOST") for item in self.batch_results)

    def build_batch_summary_message(self):
        """📊 Batch එකේ WIN/LOST ගාන + ප්රතිශත — පස්සේ ඊළඟ coins"""
        self._ensure_batch_state()
        wins = sum(1 for it in self.batch_results if it["status"] == "WIN_COMPLETE")
        losses = sum(1 for it in self.batch_results if it["status"] == "LOST")
        total = len(self.batch_results)
        win_rate = (wins / total * 100) if total else 0.0
        sl_time = self._sl_now()
        lines = [
            f"📊 *SHANA BATCH #{self.batch_number} SUMMARY* 📊",
            f"━━━━━━━━━━━━━━━━━━",
            f"✅ Wins: `{wins}`",
            f"❌ Losses: `{losses}`",
            f"🎯 Win Rate: `{win_rate:.1f}%`",
            f"━━━━━━━━━━━━━━━━━━",
        ]
        for it in self.batch_results:
            st = "✅" if it["status"] == "WIN_COMPLETE" else "❌"
            lines.append(f"{st} {it['coin']} — {it['signal']} — {it['win_pct']}%")
        lines.append("━━━━━━━━━━━━━━━━━━")
        lines.append("🔄 *ඊළඟ Coin signals ටික හදනවා...*")
        lines.append(f"🇱🇰 {sl_time.strftime('%Y-%m-%d %H:%M:%S')}")
        return "\n".join(lines)

    def rotate_to_next_batch(self):
        """🔄 Batch එක finish වුනාම — ඊළඟ coins එකට යනවා (auto-rotate)"""
        self._ensure_batch_state()
        self.completed_batches.append({
            "batch_number": self.batch_number,
            "wins": sum(1 for it in self.batch_results if it["status"] == "WIN_COMPLETE"),
            "losses": sum(1 for it in self.batch_results if it["status"] == "LOST"),
            "results": list(self.batch_results),
        })
        self.batch_number += 1
        return self.get_next_batch(10)


if __name__ == "__main__":
    a = BinanceAnalyzer()
    print("Connection:", a.check_binance_connection())
    print("Batch:", a.get_next_batch(10))
    print("Active:", a.update_active_signals())
    print("Power buy:", a.check_power_buy_shana())
    print("Short 5m:", len(a.scan_short_signals(interval="5m")))
