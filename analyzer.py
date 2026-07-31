# ============================================================
    # 💀 SHANA BATCH ENGINE v2 — 10 COIN ROTATION | 1h ONLY | LIVE WIN/LOST
    # ============================================================

@staticmethod
def _sl_now():
    """Lk Sri Lanka current date & time - 100% accurate (Asia/Colombo)"""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Colombo"))
    except Exception:
        return datetime.now() + timedelta(hours=5, minutes=30)
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

    def _ensure_batch_state(self):
        if not hasattr(self, 'signal_queue') or self.signal_queue is None:
            self.signal_queue = list(COINS)
            self.active_batch = []
            self.batch_results = []
            self.batch_number = 1
            self.completed_batches = []

    def check_binance_connection(self):
        """🔌 Binance API + Secret Key 100% connection check (binance.com)"""
        status = {'connected': False, 'ping': False, 'time': False,
                  'account': False, 'message': ''}
        try:
            ping = self._make_request("/api/v3/ping")
            status['ping'] = ping == {}
            srv_time = self._make_request("/api/v3/time")
            status['time'] = bool(srv_time and 'serverTime' in srv_time)
            import os
            api_key = os.getenv("BINANCE_API_KEY", "")
            secret = os.getenv("BINANCE_SECRET_KEY", "")
            if api_key and secret:
                try:
                    import hmac, hashlib
                    ts = int(time.time() * 1000)
                    query = f"timestamp={ts}"
                    sig = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
                    url = f"{self.base_url}/api/v3/account?{query}&signature={sig}"
                    resp = requests.get(url, headers={"X-MBX-APIKEY": api_key}, timeout=10)
                    status['account'] = resp.status_code == 200
                    if not status['account']:
                        status['message'] = f"Account check HTTP {resp.status_code} — API key permissions/whitelist බලන්න"
                except Exception as e:
                    status['message'] = f"Signed request error: {e}"
            else:
                status['message'] = "BINANCE_API_KEY/SECRET .env එකේ set කරලා නැහැ (public analysis වැඩ කරනවා)"
            status['connected'] = status['ping'] and status['time']
            logger.info(f"Binance connection: {status}")
        except Exception as e:
            status['message'] = str(e)
            logger.error(f"check_binance_connection error: {e}")
        return status

    def get_next_batch(self, batch_size=10):
        """🔄 Next 10 coins (rotating queue) — 1h analysis only"""
        self._ensure_batch_state()
        if not self.signal_queue:
            self.signal_queue = list(COINS)
        batch = self.signal_queue[:batch_size]
        self.signal_queue = self.signal_queue[batch_size:] + batch
        self.active_batch = batch
        self.batch_results = []
        self.batch_number += 1
        logger.info(f"🔄 Batch #{self.batch_number} coins: {batch}")
        return batch

    def analyze_batch_1h(self, batch_size=10):
        """🧠 FULL 50-method aggregate analysis on 1h chart → signals for 10 coins"""
        self._ensure_batch_state()
        coins = self.get_next_batch(batch_size)
        signals = []
        for coin in coins:
            try:
                result = self.analyze_all_50(coin, '1h')
                if not result or result.get('signal') not in ('BUY', 'SELL') or not result.get('entry'):
                    result = self._quick_short_analysis(coin, '1h')
                if not result or result.get('signal') not in ('BUY', 'SELL') or not result.get('entry'):
                    result = self._force_signal(coin, '1h')
                result = self._normalize_signal_dict(result)
                if result and result.get('signal') in ('BUY', 'SELL') and result.get('entry'):
                    result['batch_number'] = self.batch_number
                    result['message'] = self.build_signal_message(result)
                    item = {
                        'coin': coin,
                        'signal': result['signal'],
                        'status': 'ACTIVE',
                        'win_pct': 0.0,
                        'entry': result['entry'],
                        'tp1': result['tp1'],
                        'tp2': result['tp2'],
                        'sl': result['sl'],
                        'confidence': result.get('confidence', 0),
                        'method': result.get('method', 'Aggregate 50'),
                        'message': result['message'],
                        'tp1_msg_sent': False,
                        'tp2_msg_sent': False,
                        'sl_msg_sent': False,
                        'batch_number': self.batch_number
                    }
                    self.batch_results.append(item)
                    signals.append(result)
            except Exception as e:
                logger.warning(f"analyze_batch_1h error {coin}: {e}")
        return signals

    def _force_signal(self, coin, interval='1h'):
        """NEUTRAL result එකක් වුනාමත් signal එකක් ලැබෙන්න — RSI/EMA bias අනුව"""
        try:
            ohlcv = self._load_ohlcv(coin, interval, 100)
            ticker = self.get_ticker(coin)
            if not ohlcv or not ticker:
                return None
            closes = ohlcv['close']
            rsi = self._calc_rsi(closes, 14)[-1]
            ema_fast = self._calc_ema(closes, 8)[-1]
            ema_slow = self._calc_ema(closes, 21)[-1]
            entry = ticker['last']
            if closes[-1] > ema_fast and ema_fast > ema_slow:
                signal = 'BUY'
                conf = min(60.0, 45 + (50 - rsi) * 0.4)
            else:
                signal = 'SELL'
                conf = min(60.0, 45 + (rsi - 50) * 0.4)
            atr = (max(ohlcv['high'][-14:]) - min(ohlcv['low'][-14:])) / 2
            if atr <= 0:
                atr = entry * 0.005
            if signal == 'BUY':
                tp1, tp2, tp3, sl = entry + atr, entry + atr * 1.5, entry + atr * 2.2, entry - atr * 0.8
            else:
                tp1, tp2, tp3, sl = entry - atr, entry - atr * 1.5, entry - atr * 2.2, entry + atr * 0.8
            return {
                'symbol': coin, 'interval': interval, 'signal': signal,
                'confidence': round(conf, 1), 'entry': round(entry, 8),
                'tp1': round(tp1, 8), 'tp2': round(tp2, 8), 'tp3': round(tp3, 8),
                'sl': round(sl, 8), 'rr_ratio': 1.25,
                'win_percentage': 50.0, 'method': f'ForceBalance ({signal})',
                'summary': {'total': 2, 'buy': 1 if signal == 'BUY' else 0,
                            'sell': 1 if signal == 'SELL' else 0, 'neutral': 0,
                            'avg_confidence': round(conf, 1),
                            'bias': 0.1 if signal == 'BUY' else -0.1},
                'top_methods': [{'method': 'RSI+EMA Balance', 'confidence': round(conf, 1)}],
                'timestamp': str(datetime.now()), 'all_results_count': 2
            }
        except Exception as e:
            logger.warning(f"_force_signal error {coin}: {e}")
            return None

    def build_signal_message(self, result):
        """🤖 Signal message — 1h chart, entry/TP1/TP2/SL, SL time"""
        sl_time = self._sl_now()
        coin = result.get('symbol', '???')
        signal = result.get('signal', 'NEUTRAL')
        sig_txt = "🟢 BUY / LONG" if signal == 'BUY' else "🔴 SELL / SHORT"
        conf = result.get('confidence', 0)
        live = self.get_ticker(coin)
        live_price = live['last'] if live else result.get('entry', 0)
        return (
            f"💀 *POWER BUY BINANCE SHANA* 💀\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Signal එක: {sig_txt}\n"
            f"⏰ Timeframe: *1h Chart*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 Coin: *{coin}*\n"
            f"💰 Entry: `{self._fmt_price(result.get('entry'))}`\n"
            f"🎯 TP 1: `{self._fmt_price(result.get('tp1'))}`\n"
            f"🎯 TP 2: `{self._fmt_price(result.get('tp2'))}`\n"
            f"🛑 STOP LOSS: `{self._fmt_price(result.get('sl'))}`\n"
            f"⚡ Confidence: `{conf}%`\n"
            f"📊 Method: `{result.get('method', 'Aggregate 50')}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📈 Live Price (1h): `{self._fmt_price(live_price)}`\n"
            f"🇱🇰 {sl_time.strftime('%Y-%m-%d %H:%M:%S')} ({sl_time.strftime('%A')})"
        )

    def build_win_message(self, item, tp_level=1):
        """✅ WIN message — original signal එක mention කරලා"""
        sl_time = self._sl_now()
        live = self.get_ticker(item['coin'])
        live_price = live['last'] if live else item['entry']
        target = item['tp1'] if tp_level == 1 else item['tp2']
        return (
            f"✅✅✅✅✅✅✅✅✅✅\n"
            f"_POWER BUY SHANA SIGNAL_\n\n"
            f"📊 *WIN 100% SUCCESS* 🎉\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 Coin: *{item['coin']}*\n"
            f"Signal: {'🟢 BUY / LONG' if item['signal'] == 'BUY' else '🔴 SELL / SHORT'}\n"
            f"🎯 *TP {tp_level} HIT!* 🚀\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Entry: `{self._fmt_price(item['entry'])}`\n"
            f"🎯 Target: `{self._fmt_price(target)}`\n"
            f"📈 Live Price (1h): `{self._fmt_price(live_price)}`\n"
            f"📊 Progress: {self._progress_bar(100)} 100.0%\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🇱🇰 {sl_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def build_lost_message(self, item):
        """❌ LOST message — SL hit"""
        sl_time = self._sl_now()
        live = self.get_ticker(item['coin'])
        live_price = live['last'] if live else item['entry']
        return (
            f"❌❌❌❌❌❌❌❌❌❌\n"
            f"_POWER BUY SHANA SIGNAL_\n\n"
            f"📊 *LOST 0% — SL HIT* 💀\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 Coin: *{item['coin']}*\n"
            f"Signal: {'🟢 BUY / LONG' if item['signal'] == 'BUY' else '🔴 SELL / SHORT'}\n"
            f"🛑 *STOP LOSS HIT*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Entry: `{self._fmt_price(item['entry'])}`\n"
            f"🛑 SL: `{self._fmt_price(item['sl'])}`\n"
            f"📈 Live Price (1h): `{self._fmt_price(live_price)}`\n"
            f"📊 Progress: {self._progress_bar(0)} 0.0%\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🇱🇰 {sl_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def build_pending_message(self, coin, dots=4):
        """🟢 PENDING animation message"""
        sl_time = self._sl_now()
        return f"🟢 PENDING{'●' * dots}  |  `{coin}` — 1h Full-50 Analysis...\n🇱🇰 {sl_time.strftime('%H:%M:%S')}"

    def get_live_status_message(self, item):
        """📡 Live win% — Binance chart එක වගේ auto-refresh වෙන progress"""
        live = self.get_ticker(item['coin'])
        current = live['last'] if live else item['entry']
        entry = float(item['entry'] or 0)
        tp1 = float(item['tp1'] or 0)
        tp2 = float(item['tp2'] or 0)
        sl = float(item['sl'] or 0)
        signal = item.get('signal', 'BUY')
        if signal == 'BUY':
            dist = abs(tp1 - entry) if tp1 != entry else 0
            pct = min(100.0, abs(current - entry) / dist * 100) if dist > 0 else 0.0
            arrow = "🟢" if current > entry else "🔴"
        else:
            dist = abs(entry - tp1) if tp1 != entry else 0
            pct = min(100.0, abs(entry - current) / dist * 100) if dist > 0 else 0.0
            arrow = "🟢" if current < entry else "🔴"
        pct = round(pct, 1)
        bar = self._progress_bar(pct)
        sl_time = self._sl_now()
        return (
            f"{arrow} *{item['coin']}* — Live 1h Status\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📈 Live Price: `{self._fmt_price(current)}`\n"
            f"💰 Entry: `{self._fmt_price(entry)}`\n"
            f"🎯 TP1: `{self._fmt_price(tp1)}`\n"
            f"🎯 TP2: `{self._fmt_price(tp2)}`\n"
            f"🛑 SL: `{self._fmt_price(sl)}`\n"
            f"📊 {bar} {pct}%\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🇱🇰 {sl_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def check_signal_results(self):
        """🔍 Live price check → TP1 WIN / TP2 WIN / SL LOST messages"""
        self._ensure_batch_state()
        updates = []
        for item in self.batch_results:
            if item['status'] in ('WIN_COMPLETE', 'LOST'):
                continue
            try:
                live = self.get_ticker(item['coin'])
                if not live:
                    continue
                current = float(live['last'])
                tp1 = float(item['tp1'] or 0)
                tp2 = float(item['tp2'] or 0)
                sl = float(item['sl'] or 0)
                signal = item['signal']

                # 🎯 TP1 — price එක TP1 ට ටිකක් වැඩි/අඩු වුනාම WIN msg
                if not item['tp1_msg_sent']:
                    hit = (signal == 'BUY' and current >= tp1 * 1.0005) or \
                          (signal == 'SELL' and current <= tp1 * 0.9995)
                    if hit:
                        item['tp1_msg_sent'] = True
                        item['win_pct'] = 100.0
                        updates.append({'type': 'WIN1', 'item': item,
                                        'message': self.build_win_message(item, 1)})

                # 🎯 TP2 — TP1 දිනපු ගමන් විතරක් check වෙනවා
                elif not item['tp2_msg_sent']:
                    hit = (signal == 'BUY' and current >= tp2 * 1.0005) or \
                          (signal == 'SELL' and current <= tp2 * 0.9995)
                    if hit:
                        item['tp2_msg_sent'] = True
                        item['status'] = 'WIN_COMPLETE'
                        item['win_pct'] = 100.0
                        updates.append({'type': 'WIN2', 'item': item,
                                        'message': self.build_win_message(item, 2)})

                # 🛑 SL — LOST msg
                if not item['sl_msg_sent']:
                    hit = (signal == 'BUY' and current <= sl * 0.9995) or \
                          (signal == 'SELL' and current >= sl * 1
                           def check_signal_results(self):
        """🔍 Live price check → TP1 WIN / TP2 WIN / SL LOST messages"""
        self._ensure_batch_state()
        updates = []
        for item in self.batch_results:
            if item['status'] in ('WIN_COMPLETE', 'LOST'):
                continue
            try:
                live = self.get_ticker(item['coin'])
                if not live:
                    continue
                current = float(live['last'])
                tp1 = float(item['tp1'] or 0)
                tp2 = float(item['tp2'] or 0)
                sl = float(item['sl'] or 0)
                signal = item['signal']

                # 🎯 TP1 — price එක TP1 ට ටිකක් වැඩි/අඩු වුනාම WIN msg
                if not item['tp1_msg_sent']:
                    hit = (signal == 'BUY' and current >= tp1 * 1.0005) or \
                          (signal == 'SELL' and current <= tp1 * 0.9995)
                    if hit:
                        item['tp1_msg_sent'] = True
                        item['win_pct'] = 100.0
                        updates.append({'type': 'WIN1', 'item': item,
                                        'message': self.build_win_message(item, 1)})

                # 🎯 TP2 — TP1 දිනපු ගමන් විතරක් check වෙනවා
                elif not item['tp2_msg_sent']:
                    hit = (signal == 'BUY' and current >= tp2 * 1.0005) or \
                          (signal == 'SELL' and current <= tp2 * 0.9995)
                    if hit:
                        item['tp2_msg_sent'] = True
                        item['status'] = 'WIN_COMPLETE'
                        item['win_pct'] = 100.0
                        updates.append({'type': 'WIN2', 'item': item,
                                        'message': self.build_win_message(item, 2)})

                # 🛑 SL — LOST msg (TP1 දිනන්න කලින් SL hit වුනොත්)
                if not item['sl_msg_sent']:
                    hit = (signal == 'BUY' and current <= sl * 0.9995) or \
                          (signal == 'SELL' and current >= sl * 1.0005)
                    if hit:
                        item['sl_msg_sent'] = True
                        item['status'] = 'LOST'
                        item['win_pct'] = 0.0
                        updates.append({'type': 'LOST', 'item': item,
                                        'message': self.build_lost_message(item)})

                # 📡 ACTIVE නම් live progress update
                if item['status'] not in ('WIN_COMPLETE', 'LOST'):
                    if signal == 'BUY':
                        dist = abs(tp1 - float(item['entry'])) if tp1 != float(item['entry']) else 0
                        pct = min(100.0, abs(current - float(item['entry'])) / dist * 100) if dist > 0 else 0.0
                    else:
                        dist = abs(float(item['entry']) - tp1) if tp1 != float(item['entry']) else 0
                        pct = min(100.0, abs(float(item['entry']) - current) / dist * 100) if dist > 0 else 0.0
                    item['win_pct'] = round(pct, 1)
            except Exception as e:
                logger.warning(f"check_signal_results error {item['coin']}: {e}")
                continue
        return updates
        def is_batch_finished(self):
        """Batch එකේ 10 coins ඔක්කොම WIN_COMPLETE/LOST වුනාද?"""
        self._ensure_batch_state()
        if not self.batch_results:
            return False
        return all(item['status'] in ('WIN_COMPLETE', 'LOST') for item in self.batch_results)

    def build_batch_summary_message(self):
        """📊 Batch එකේ WIN/LOST ගාන + ප්‍රතිශත — පස්සේ ඊළඟ 10 coins"""
        self._ensure_batch_state()
        wins = sum(1 for it in self.batch_results if it['status'] == 'WIN_COMPLETE')
        losses = sum(1 for it in self.batch_results if it['status'] == 'LOST')
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
            st = "✅" if it['status'] == 'WIN_COMPLETE' else "❌"
            lines.append(f"{st} {it['coin']} — {it['signal']} — {it['win_pct']}%")
        lines.append(f"━━━━━━━━━━━━━━━━━━")
        lines.append(f"🔄 *ඊළඟ Coin 10 signals ටික හදනවා...*")
        lines.append(f"🇱🇰 {sl_time.strftime('%Y-%m-%d %H:%M:%S')}")
        return '\n'.join(lines)

    def rotate_to_next_batch(self):
        """🔄 Batch එක finish වුනාම — ඊළඟ 10 coins එකට යනවා (auto-rotate)"""
        self._ensure_batch_state()
        self.completed_batches.append({
            'batch_number': self.batch_number,
            'wins': sum(1 for it in self.batch_results if it['status'] == 'WIN_COMPLETE'),
            'losses': sum(1 for it in self.batch_results if it['status'] == 'LOST'),
            'results': list(self.batch_results)
        })
        return self.get_next_batch(10)
