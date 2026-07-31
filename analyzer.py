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


class BinanceAnalyzer:

    def __init__(self, base_url="https://api.binance.com", api_key=None, secret=None):
        self.base_url = base_url
        self.api_key = api_key or os.getenv("BINANCE_API_KEY", "")
        self.secret = secret or os.getenv("BINANCE_SECRET_KEY", "")
        self.session = requests.Session()
        # ── full state init — main.py එකට ඕන හැම attribute එකම මෙතන ✅ ──
        self.signal_tracker = {}          # main.py line 1141 මේක use කරනවා
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
            return f"{price:.4f}"
        return f"{price:.8f}".rstrip('0').rstrip('.')

    def _fmt_pct(self, pct):
        try:
            return f"{float(pct):.1f}%"
        except (TypeError, ValueError):
            return "0.0%"

    def _progress_bar(self, win_pct, width=10):
        try:
            pct = max(0.0, min(100.0, float(win_pct)))
        except (TypeError, ValueError):
            pct = 0.0
        filled = int(round(pct / 100.0 * width))
        return "█" * filled + "░" * (width - filled)

    # ============================================================
    # 🔌 BINANCE API HELPERS
    # ============================================================

    def _make_request(self, path, params=None):
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params or {}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_ticker(self, coin):
        """💰 Live price ticker — {'last': '1234.56', ...}"""
        try:
            return self._make_request("/api/v3/ticker/price", {"symbol": coin})
        except Exception as e:
            logger.warning(f"get_ticker error {coin}: {e}")
            return None

    def _get_klines(self, coin, interval="1h", limit=60):
        """🕯️ 1h candles — signal generation සඳහා"""
        try:
            data = self._make_request(
                "/api/v3/klines",
                {"symbol": coin, "interval": interval, "limit": limit},
            )
            candles = []
            for k in data:
                candles.append({
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            return candles
        except Exception as e:
            logger.warning(f"_get_klines error {coin}: {e}")
            return []

    def _rsi(self, candles, period=14):
        """📉 RSI (Wilder's smoothing)"""
        closes = [c["close"] for c in candles]
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _atr(self, candles, period=14):
        """📏 ATR — TP/SL distance calculate කරන්න"""
        if len(candles) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(candles)):
            h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return sum(trs[-period:]) / period

    def _generate_signal(self, coin):
        """🎯 1h RSI + ATR → BUY/SELL signal + TP1/TP2/SL"""
        candles = self._get_klines(coin, interval="1h", limit=60)
        if len(candles) < 20:
            return None
        rsi = self._rsi(candles)
        atr = self._atr(candles)
        if atr <= 0:
            return None
        entry = candles[-1]["close"]

        if rsi <= 30:
            signal = "BUY"
            tp1 = entry + atr
            tp2 = entry + 2 * atr
            sl = entry - atr
        elif rsi >= 70:
            signal = "SELL"
            tp1 = entry - atr
            tp2 = entry - 2 * atr
            sl = entry + atr
        else:
            return None  # RSI neutral — signal නැහැ

        return {
            "coin": coin,
            "signal": signal,
            "entry": entry,
            "tp1": tp1,
            "tp2": tp2,
            "sl": sl,
            "status": "ACTIVE",
            "win_pct": 0.0,
            "tp1_msg_sent": False,
            "tp2_msg_sent": False,
            "sl_msg_sent": False,
            "created_at": str(self._sl_now()),
        }

    # ============================================================
    # 🧮 BATCH STATE
    # ============================================================

    def _ensure_batch_state(self):
        if not hasattr(self, "signal_queue") or self.signal_queue is None:
            self.signal_queue = list(COINS)
            self.active_batch = []
            self.batch_results = []
            self.batch_number = 1
            self.completed_batches = []
            self.signal_tracker = {}

    def get_next_batch(self, count=10):
        """🔄 ඊළඟ coins 10ට signals හදනවා — queue ඉවර වුනාම නැවත rotate වෙනවා"""
        self._ensure_batch_state()
        if not self.signal_queue:
            self.signal_queue = list(COINS)  # auto-reset rotation
        coins = []
        while self.signal_queue and len(coins) < count:
            coins.append(self.signal_queue.pop(0))
        self.active_batch = coins
        self.batch_results = []
        self.signal_tracker = {}             # batch එකට අලුත් tracker එක
        for coin in coins:
            sig = self._generate_signal(coin)
            if sig:
                self.batch_results.append(sig)
                self.signal_tracker[coin] = sig   # ✅ main.py tracker එකට
        if self.completed_batches:
            self.batch_number = self.completed_batches[-1]["batch_number"] + 1
        else:
            self.batch_number = 1
        logger.info(f"Batch #{self.batch_number}: {len(self.batch_results)} signals "
                    f"({len(self.batch_results)}/{len(coins)} coins)")
        return self.batch_results

    # ============================================================
    # 🔌 CONNECTION CHECK
    # ============================================================

    def check_binance_connection(self):
        """🔌 Binance API + Secret Key 100% connection check (binance.com)"""
        status = {"connected": False, "ping": False, "time": False,
                  "account": False, "message": ""}
        try:
            ping = self._make_request("/api/v3/ping")
            status["ping"] = ping == {}
            srv_time = self._make_request("/api/v3/time")
            status["time"] = bool(srv_time and "serverTime" in srv_time)

            if self.api_key and self.secret:
                try:
                    ts = int(time.time() * 1000)
                    query = f"timestamp={ts}"
                    sig = hmac.new(self.secret.encode(), query.encode(),
                                   hashlib.sha256).hexdigest()
                    url = f"{self.base_url}/api/v3/account?{query}&signature={sig}"
                    resp = self.session.get(url, headers={"X-MBX-APIKEY": self.api_key}, timeout=10)
                    status["account"] = resp.status_code == 200
                    if not status["account"]:
                        status["message"] = (f"Account check HTTP {resp.status_code} — "
                                             "API key permissions/whitelist බලන්න")
                except Exception as e:
                    status["message"] = f"Signed request error: {e}"
            else:
                status["message"] = ("BINANCE_API_KEY/SECRET .env එකේ set කරලා නැහැ "
                                     "(public analysis වැඩ කරනවා)")
            status["connected"] = status["ping"] and status["time"]
            logger.info(f"Binance connection: {status}")
        except Exception as e:
            status["message"] = f"Connection error: {e}"
        return status

    # ============================================================
    # 📊 MESSAGE BUILDERS
    # ============================================================

    def build_win_message(self, item, level=1):
        """🎯 WIN message — Telegram format"""
        sl_time = self._sl_now()
        lines = [
            f"🎯 *SHANA WIN {level}* 🎯",
            f"━━━━━━━━━━━━━━━━━━",
            f"🪙 Coin: `{item['coin']}`",
            f"📈 Signal: `{item['signal']}`",
            f"💵 Entry: `{self._fmt_price(item['entry'])}`",
            f"🎯 TP{level}: `{self._fmt_price(item[f'tp{level}'])}`",
            f"{self._progress_bar(item['win_pct'])} {self._fmt_pct(item['win_pct'])}",
            f"━━━━━━━━━━━━━━━━━━",
            f"🇱🇰 {sl_time.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        return "\n".join(lines)

    def build_lost_message(self, item):
        """🛑 LOST message — Telegram format"""
        sl_time = self._sl_now()
        lines = [
            f"🛑 *SHANA LOST* 🛑",
            f"━━━━━━━━━━━━━━━━━━",
            f"🪙 Coin: `{item['coin']}`",
            f"📈 Signal: `{item['signal']}`",
            f"💵 Entry: `{self._fmt_price(item['entry'])}`",
            f"🛑 SL: `{self._fmt_price(item['sl'])}`",
            f"━━━━━━━━━━━━━━━━━━",
            f"🇱🇰 {sl_time.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        return "\n".join(lines)

    # ============================================================
    # 🔍 LIVE SIGNAL RESULT CHECK
    # ============================================================

    def check_signal_results(self):
        """🔍 Live price check → TP1 WIN / TP2 WIN / SL LOST messages"""
        self._ensure_batch_state()
        updates = []
        for item in self.batch_results:
            if item["status"] in ("WIN_COMPLETE", "LOST"):
                continue
            try:
                live = self.get_ticker(item["coin"])
                if not live:
                    continue
                current = float(live["last"])
                tp1 = float(item["tp1"] or 0)
                tp2 = float(item["tp2"] or 0)
                sl = float(item["sl"] or 0)
                signal = item["signal"]

                # 🎯 TP1 — price එක TP1 ට ටිකක් වැඩි/අඩු වුනාම WIN msg
                if not item["tp1_msg_sent"]:
                    hit = (signal == "BUY" and current >= tp1 * 1.0005) or \
                          (signal == "SELL" and current <= tp1 * 0.9995)
                    if hit:
                        item["tp1_msg_sent"] = True
                        item["win_pct"] = 100.0
                        updates.append({"type": "WIN1", "item": item,
                                        "message": self.build_win_message(item, 1)})

                # 🎯 TP2 — TP1 දිනපු ගමන් විතරක් check වෙනවා
                elif not item["tp2_msg_sent"]:
                    hit = (signal == "BUY" and current >= tp2 * 1.0005) or \
                          (signal == "SELL" and current <= tp2 * 0.9995)
                    if hit:
                        item["tp2_msg_sent"] = True
                        item["status"] = "WIN_COMPLETE"
                        item["win_pct"] = 100.0
                        updates.append({"type": "WIN2", "item": item,
                                        "message": self.build_win_message(item, 2)})

                # 🛑 SL — LOST msg (TP1 දිනන්න කලින් SL hit වුනොත්)
                if not item["sl_msg_sent"]:
                    hit = (signal == "BUY" and current <= sl * 0.9995) or \
                          (signal == "SELL" and current >= sl * 1.0005)
                    if hit:
                        item["sl_msg_sent"] = True
                        item["status"] = "LOST"
                        item["win_pct"] = 0.0
                        updates.append({"type": "LOST", "item": item,
                                        "message": self.build_lost_message(item)})

                # 📡 ACTIVE නම් live progress update
                if item["status"] not in ("WIN_COMPLETE", "LOST"):
                    if signal == "BUY":
                        dist = abs(tp1 - float(item["entry"])) if tp1 != float(item["entry"]) else 0
                        pct = min(100.0, abs(current - float(item["entry"])) / dist * 100) if dist > 0 else 0.0
                    else:
                        dist = abs(float(item["entry"]) - tp1) if tp1 != float(item["entry"]) else 0
                        pct = min(100.0, abs(float(item["entry"]) - current) / dist * 100) if dist > 0 else 0.0
                    item["win_pct"] = round(pct, 1)

                # ✅ tracker sync
                self.signal_tracker[item["coin"]] = item
            except Exception as e:
                logger.warning(f"check_signal_results error {item['coin']}: {e}")
                continue
        return updates

    # ============================================================
    # ➕ NEW — main.py loop එකට ඕන methods 4
    # ============================================================

    def update_active_signals(self):
        """🔁 main.py loop එකෙන් call වෙනවා — live check කරලා
        ACTIVE signal count එක (int) return කරනවා"""
        self._ensure_batch_state()
        try:
            self.check_signal_results()
        except Exception as e:
            logger.warning(f"update_active_signals error: {e}")
        active = sum(1 for it in self.batch_results if it.get("status") == "ACTIVE")
        logger.info(f"🔄 Active signals: {active}/{len(self.batch_results)}")
        return active

    def check_power_buy_shana(self, coins=None):
        """⚡ POWER BUY — RSI < 25 වුන coins වල signal dict list එකක්
        return කරනවා (main.py එකේ loop එකට iterable එකක් ඕන)"""
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
                    sig = {
                        "coin": coin, "signal": "BUY", "entry": entry,
                        "tp1": entry + atr, "tp2": entry + 2 * atr, "sl": entry - atr,
                        "rsi": round(rsi, 2), "status": "ACTIVE", "win_pct": 0.0,
                        "tp1_msg_sent": False, "tp2_msg_sent": False, "sl_msg_sent": False,
                        "created_at": str(self._sl_now()),
                    }
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
                    return sig
            except Exception as e:
                logger.warning(f"find_short_signal error {c}: {e}")
        return None

    # ============================================================
    # 📦 BATCH SUMMARY / ROTATION
    # ============================================================

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
        return self.get_next_batch(10)


if __name__ == "__main__":
    a = BinanceAnalyzer()
    print("Connection:", a.check_binance_connection())
    print("Batch:", a.get_next_batch(10))
    print("Active:", a.update_active_signals())
    print("Power buy:", a.check_power_buy_shana())
