import asyncio
import logging
import os
import time
from datetime import datetime
import requests
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from config import *
from analyzer import BinanceAnalyzer

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ GLOBAL ============
analyzer = BinanceAnalyzer()
bot = Bot(token=TELEGRAM_BOT_TOKEN)
user_coins = set(COINS)
signal_history = []
auto_signal_running = True

# ============ WELCOME IMAGE ============
WELCOME_IMAGE = "welcome.jpg"

# ============ TIMEFRAME LIST ============
TIMEFRAMES = [
    ("5 Minute", "5m"),
    ("20 MINUTE", "20m"),
    ("50 MINUTE", "50m"),
    ("1 HOURS", "1h"),
    ("2 HOURS", "2h"),
]

# ============ OWNER AUTHORIZATION ============
# ඔයාගේ Telegram User ID එක දාන්න (අනිත් අයට use කරන්න බැරි වෙයි)
# @userinfobot ගිහින් /start කරලා ID එක ගන්න
OWNER_ID = 0  # <-- මෙතන ඔයාගේ Telegram User ID එක දාන්න!

# Webhook settings for UptimeRobot / Railway
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
WEBHOOK_PORT = int(os.environ.get("PORT", 8443))
WEBHOOK_LISTEN = "0.0.0.0"

# ============ SESSION STATE (menu navigation) ============
sessions = {}  # chat_id -> {"scan": [...], "idx": 0, "tf": "5m"}

# ============ Progress Bar ============
def generate_progress_bar(percentage, length=10):
    filled = int(min(percentage, 100) / 100 * length)
    return '█' * filled + '░' * (length - filled)

def generate_colored_bar(percentage, length=10):
    """Color-coded progress bar"""
    filled = int(min(percentage, 100) / 100 * length)
    bar = ''
    for i in range(length):
        if i < filled:
            if percentage >= 80:
                bar += '🟢'
            elif percentage >= 50:
                bar += '🟡'
            elif percentage >= 30:
                bar += '🟠'
            else:
                bar += '🔴'
        else:
            bar += '⚪'
    return bar

# ============ AUTHORIZATION CHECK ============
def is_owner(update):
    """Check if the user is the owner"""
    if OWNER_ID == 0:
        return True
    user = update.effective_user
    return user is not None and user.id == OWNER_ID

# ============================================================
# 🆕 NEW: WELCOME + MENU SYSTEM
# ============================================================
WELCOME_TEXT = (
    "🎯 *WELCOME TO SHANA SIGNALS BOT* 🎯\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🤖 *SHANA × BINANCE* Live Trading Signals\n"
    "📈 24/7 Auto Analysis — කිසිම වෙලාවක නවතින්නේ නෑ\n"
    "🕹️ පහල *MENU* එකෙන් තෝරගන්න 👇\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🇱🇰 Sri Lanka Time (Asia/Colombo)"
)

def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕹️ LIVE PRICE", callback_data="menu_live")],
        [InlineKeyboardButton("🟢 NOW GOOD COIN", callback_data="menu_good")],
        [InlineKeyboardButton("♻️ POWER BUY SHANA", callback_data="menu_powerbuy")],
        [InlineKeyboardButton("🔴 SHORT SIGNALS 5 MINUTE", callback_data="menu_short")],
        [InlineKeyboardButton("📊 STATS", callback_data="menu_stats")],
        [InlineKeyboardButton("BACK ⬅️", callback_data="menu_back")],
    ])

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("BACK ⬅️", callback_data="menu_back")]])

async def start(update: Update, context):
    if not is_owner(update):
        await update.message.reply_text("⛔ Access Denied! මේ Bot එක Private. Owner ID එක set කරලා තියෙන්න ඕන.")
        return
    if os.path.exists(WELCOME_IMAGE):
        with open(WELCOME_IMAGE, "rb") as f:
            await update.message.reply_photo(photo=f, caption=WELCOME_TEXT,
                                             parse_mode="Markdown", reply_markup=menu_keyboard())
    else:
        await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown",
                                        reply_markup=menu_keyboard())

async def back_to_menu(chat_id, message_id=None):
    if os.path.exists(WELCOME_IMAGE):
        with open(WELCOME_IMAGE, "rb") as f:
            await bot.send_photo(chat_id=chat_id, photo=f, caption=WELCOME_TEXT,
                                 parse_mode="Markdown", reply_markup=menu_keyboard())
    else:
        await bot.send_message(chat_id, WELCOME_TEXT, parse_mode="Markdown",
                               reply_markup=menu_keyboard())

# ============ 🕹️ LIVE PRICE ============
async def live_prices(chat_id, message_id=None):
    lines = ["🕹️ *LIVE COIN PRICES* 🕹️", "━━━━━━━━━━━━━━━━━━"]
    try:
        data = analyzer.get_live_prices(list(user_coins))
    except Exception as e:
        lines.append(f"❌ Error: {e}")
        data = {}
    if not data:
        lines.append("😴 දැන් data නෑ. REFRESH කරලා බලන්න.")
    for c in sorted(data):
        t = data[c]
        arrow = "🟢" if t["change"] >= 0 else "🔴"
        lines.append(
            f"{arrow} *{c}*\n"
            f"     💰 Price: `{t['price']:,.4f}`\n"
            f"     📈 Change: {'+' if t['change'] >= 0 else ''}{t['change']:.2f}%"
        )
    lines.append("━━━━━━━━━━━━━━━━━━")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 REFRESH", callback_data="live_refresh")],
        [InlineKeyboardButton("BACK ⬅️", callback_data="menu_back")],
    ])
    text = "\n".join(lines)
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                                        parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

# ============ 🟢 NOW GOOD COIN ============
async def show_good_coin(chat_id, message_id=None):
    lines = ["🟢 *NOW GOOD COIN — BEST PICKS* 🟢", "━━━━━━━━━━━━━━━━━━"]
    try:
        scores = analyzer.score_coins(list(user_coins), "5m")
    except Exception as e:
        scores = []
        lines.append(f"❌ Error: {e}")
    if not scores:
        lines.append("😴 දැන් data නෑ. ටිකකින් REFRESH කරන්න.")
    for i, s in enumerate(scores[:5], 1):
        lines.append(
            f"{i}. *{s['coin']}* — `{s['score']}%`\n"
            f"    {generate_colored_bar(s['score'])}\n"
            f"    RSI: `{s['rsi']}` | Price: `{s['price']:,.4f}`"
        )
    lines.append("━━━━━━━━━━━━━━━━━━")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 REFRESH", callback_data="good_refresh")],
        [InlineKeyboardButton("BACK ⬅️", callback_data="menu_back")],
    ])
    text = "\n".join(lines)
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                                        parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

# ============ ♻️ POWER BUY SHANA ============
async def show_power_buy(chat_id, message_id=None):
    lines = ["♻️ *POWER BUY SHANA* ♻️", "━━━━━━━━━━━━━━━━━━"]
    try:
        signals = analyzer.check_power_buy_shana(list(user_coins))
    except Exception as e:
        signals = []
        lines.append(f"❌ Error: {e}")
    if not signals:
        lines.append("😴 දැන් Power Buy signal නෑ. (RSI < 25 coins නෑ)")
    for sig in signals:
        lines.append(
            f"🟢 *{sig['coin']}* — BUY\n"
            f"    Entry: `{sig['entry']:,.4f}` | Confidence: `{sig.get('confidence', 0)}%`"
        )
    lines.append("━━━━━━━━━━━━━━━━━━")
    kb = back_kb()
    text = "\n".join(lines)
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                                        parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

# ============ 🔴 SHORT SIGNALS (timeframe select) ============
async def short_timeframe_menu(chat_id, message_id=None):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ 5 MINUTES", callback_data="tf_5m")],
        [InlineKeyboardButton("⏰ 1 HOUR", callback_data="tf_1h")],
        [InlineKeyboardButton("⏰ 2 HOURS", callback_data="tf_2h")],
        [InlineKeyboardButton("⏰ 24 HOURS", callback_data="tf_1d")],
        [InlineKeyboardButton("BACK ⬅️", callback_data="menu_back")],
    ])
    text = ("🔴 *SHORT SIGNALS* — Timeframe එකක් තෝරන්න 👇\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⏰ 5 = විනාඩි 5\n"
            "⏰ 1h = පැය 1\n"
            "⏰ 2h = පැය 2\n"
            "⏰ 24h = පැය 24\n"
            "━━━━━━━━━━━━━━━━━━")
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                                        parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

async def run_short_scan(chat_id, tf, message_id=None, next_idx=False):
    sess = sessions.setdefault(chat_id, {})
    if not next_idx or "scan" not in sess or sess.get("tf") != tf:
        sess["tf"] = tf
        sess["scan"] = analyzer.scan_short_signals(list(user_coins), tf)
        sess["idx"] = 0
    scan = sess["scan"]
    kb_empty = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 REFRESH", callback_data="short_refresh")],
        [InlineKeyboardButton("BACK ⬅️", callback_data="menu_back")],
    ])
    if not scan:
        text = "😴 දැන් මේ timeframe එකට SHORT signal නෑ.\nටික වෙලාවකින් REFRESH කරලා බලන්න."
        if message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                                            parse_mode="Markdown", reply_markup=kb_empty)
            except Exception:
                await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb_empty)
        else:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb_empty)
        return
    idx = sess["idx"]
    if idx >= len(scan):
        idx = 0
        sess["idx"] = 0
    sig = scan[idx]
    try:
        price = analyzer.get_price(sig["coin"])
    except Exception:
        price = sig["entry"]
    # Live WIN / LOST progress
    if sig["signal"] == "SELL":
        if price <= sig["tp"]:
            status, pct = "WIN_COMPLETE", 100.0
        elif price >= sig["sl"]:
            status, pct = "LOST", 0.0
        else:
            pct = max(0.0, min(100.0, (sig["entry"] - price) / (sig["entry"] - sig["tp"]) * 100))
            status = "ACTIVE"
    else:
        if price >= sig["tp"]:
            status, pct = "WIN_COMPLETE", 100.0
        elif price <= sig["sl"]:
            status, pct = "LOST", 0.0
        else:
            pct = max(0.0, min(100.0, (price - sig["entry"]) / (sig["tp"] - sig["entry"]) * 100))
            status = "ACTIVE"
    if status == "WIN_COMPLETE":
        result = "🟢🟢🟢🟢🟢 *WIN!* 🎉\nසුබ පැතුම්! Binance trade එක check කරලා බලන්න 😘❤️"
    elif status == "LOST":
        result = "🔴🔴🔴🔴🔴 *LOST!* 😭\nNext Signals එකෙන් cover කරගමු.....!"
    else:
        result = f"⏳ *Live Progress:* `{pct:.1f}%`\n{generate_colored_bar(pct)}"
    text = (
        f"{sig.get('message', '')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 *Live Price:* `{price:,.4f}`\n"
        f"{result}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"`{idx + 1}/{len(scan)}` signals | ⏰ {sig.get('timestamp', '')}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 UPDATE WIN/LOST", callback_data="short_refresh"),
         InlineKeyboardButton("NEXT SIGNALS ➡️", callback_data="short_next")],
        [InlineKeyboardButton("BACK ⬅️", callback_data="menu_back")],
    ])
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                                        parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

# ============ 📊 STATS / LIVE SIGNALS WIN-LOST ============
async def show_stats(chat_id, message_id=None):
    tracker = analyzer.signal_tracker
    wins = sum(1 for s in tracker.values() if s.get("status") == "WIN_COMPLETE")
    losses = sum(1 for s in tracker.values() if s.get("status") == "LOST")
    active = sum(1 for s in tracker.values() if s.get("status") == "ACTIVE")
    total = wins + losses
    rate = (wins / total * 100) if total else 0.0
    lines = ["📊 *STATS — LIVE SIGNALS WIN/LOST* 📊", "━━━━━━━━━━━━━━━━━━"]
    if not tracker:
        lines.append("😴 තාම signals නෑ.")
    for coin, s in tracker.items():
        st = ("🟢 *WIN*" if s.get("status") == "WIN_COMPLETE"
              else "🔴 *LOST*" if s.get("status") == "LOST" else "⏳ ACTIVE")
        pct = s.get("win_pct", 0)
        lines.append(f"{st} `{coin}` — `{pct:.1f}%`")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"✅ Wins: `{wins}` | ❌ Losses: `{losses}` | ⏳ Active: `{active}`")
    lines.append(f"🎯 *Win Rate: `{rate:.1f}%`*")
    kb = back_kb()
    text = "\n".join(lines)
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                                        parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

# ============ BUTTON HANDLER (NEW menu routing) ============
async def button_handler(update: Update, context):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    data = q.data
    mid = q.message.message_id

    if data == "menu_live":
        await live_prices(chat_id)
    elif data == "live_refresh":
        await live_prices(chat_id, mid)
    elif data == "menu_good":
        await show_good_coin(chat_id, mid)
    elif data == "good_refresh":
        await show_good_coin(chat_id, mid)
    elif data == "menu_powerbuy":
        await show_power_buy(chat_id, mid)
    elif data == "menu_short":
        await short_timeframe_menu(chat_id, mid)
    elif data.startswith("tf_"):
        await run_short_scan(chat_id, data[3:], mid)
    elif data == "short_refresh":
        await run_short_scan(chat_id, sessions.get(chat_id, {}).get("tf", "5m"), mid)
    elif data == "short_next":
        sess = sessions.setdefault(chat_id, {})
        sess["idx"] = sess.get("idx", 0) + 1
        await run_short_scan(chat_id, sess.get("tf", "5m"), mid, next_idx=True)
    elif data == "menu_stats":
        await show_stats(chat_id, mid)
    elif data == "menu_back":
        await back_to_menu(chat_id)

# ====================================================================
# AUTO SIGNAL LOOP — 24/7 Power Buy + Long signals
# ====================================================================
async def auto_signal_loop():
    """Every ANALYSIS_INTERVAL — analyze all coins & send signals"""
    global auto_signal_running, signal_history
    consecutive_errors = 0
    while True:
        try:
            if auto_signal_running:
                signals = analyzer.check_power_buy_shana(list(user_coins))
                if not signals:
                    long = analyzer.find_long_signal()
                    if long:
                        signals = [long]
                for sig in signals:
                    msg = sig.get("message") or (
                        f"🟢 *BUY SIGNAL — {sig['coin']}*\n"
                        f"Entry: `{sig['entry']:.4f}` | TP: `{sig['tp']:.4f}` | SL: `{sig['sl']:.4f}`"
                    )
                    try:
                        await bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")
                        signal_history.append(sig)
                    except Exception:
                        pass
                try:
                    analyzer.update_active_signals()
                except Exception as e:
                    logger.warning(f"update_active_signals error: {e}")

                if len(signal_history) > 200:
                    signal_history = signal_history[-200:]

                consecutive_errors = 0
            else:
                logger.info("⏸️ Auto signal paused")

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Auto signal loop error ({consecutive_errors}): {e}")

            if consecutive_errors > 5:
                logger.error("🔥 Too many consecutive errors! Waiting 60s...")
                await asyncio.sleep(60)
                consecutive_errors = 0
                continue

        await asyncio.sleep(ANALYSIS_INTERVAL)

# ====================================================================
# HEALTH CHECK — Bot එක 24/7 ජීවත් වෙනවාද කියලා check කරන්න
# ====================================================================
async def health_check():
    """Every 30 minutes, log that bot is still alive"""
    while True:
        try:
            total_signals = len(analyzer.signal_tracker)
            active_count = sum(1 for s in analyzer.signal_tracker.values() if s.get('status') == 'ACTIVE')
            logger.info(f"💚 Bot HEALTHY — Tracked: {total_signals} signals, Active: {active_count}, Coins: {len(user_coins)}")
        except Exception as e:
            logger.warning(f"Health check error: {e}")
        await asyncio.sleep(1800)

# ====================================================================
# WEBHOOK MODE FOR RAILWAY / UPTIMEROBOT
# ====================================================================
async def webhook_mode(app):
    """Webhook mode — Railway / Render / UptimeRobot සඳහා"""
    if not WEBHOOK_URL:
        logger.info("⚠️ WEBHOOK_URL environment variable එක set කරලා නැහැ. Polling mode use කරන්න.")
        return False

    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await app.bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook set to: {webhook_url}")

        await app.start()
        app.updater.start_polling()

        await app.start_webhook(
            listen=WEBHOOK_LISTEN,
            port=WEBHOOK_PORT,
            url_path="webhook",
        )
        logger.info(f"🌐 Webhook listening on {WEBHOOK_LISTEN}:{WEBHOOK_PORT}")
        return True
    except Exception as e:
        logger.error(f"❌ Webhook setup error: {e}")
        return False

# ====================================================================
# MAIN — Polling + Webhook dual mode
# ====================================================================
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Start background tasks
    loop.create_task(auto_signal_loop())
    loop.create_task(health_check())

    logger.info("🤖💀 BINANCE SHANA SIGNALS BOT STARTED!")
    logger.info(f"📊 Monitoring {len(user_coins)} coins")
    logger.info(f"⏰ Analysis interval: {ANALYSIS_INTERVAL}s")
    logger.info(f"📝 Signal tracker: {len(analyzer.signal_tracker)} signals loaded")

    if OWNER_ID != 0:
        logger.info(f"🔒 Bot is PRIVATE — Owner ID: {OWNER_ID}")
    else:
        logger.warning("⚠️ OWNER_ID set කරලා නැහැ! @userinfobot ගිහින් /start කරලා ID එක ගන්න.")

    try:
        loop.run_until_complete(webhook_mode(app))
        loop.run_forever()
    except Exception as e:
        logger.warning(f"Webhook failed ({e}), falling back to polling mode...")

    while True:
        try:
            app.run_polling(
                allowed_updates=['message', 'callback_query'],
                drop_pending_updates=True,
                timeout=30
            )
        except Exception as e:
            logger.error(f"🔥 Polling crashed: {e}")
            logger.info("🔄 Restarting in 5 seconds...")
            time.sleep(5)
            continue

if __name__ == "__main__":
    main()
