import asyncio
import logging
import os
import traceback
from datetime import datetime
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
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


# ============ WELCOME ============
async def start(update, context):
    try:
        if os.path.exists(WELCOME_IMAGE):
            with open(WELCOME_IMAGE, 'rb') as photo:
                await update.message.reply_photo(photo=photo)
        elif WELCOME_IMAGE.startswith('http://') or WELCOME_IMAGE.startswith('https://'):
            await update.message.reply_photo(photo=WELCOME_IMAGE)
    except Exception as e:
        logger.warning(f"Welcome image not available: {e}")

    welcome_text = (
        "🌟 *Welcome to SHANA Signal Bot* 🌟\n\n"
        "🤖 *Powered by Binance*\n"
        "📊 *Real-time Cryptocurrency Analysis*\n\n"
        "🔹 Live Price Tracking — හැම coin එකම 🟢\n"
        "🔹 Smart Trading Signals — Timeframe 5m/20m/50m/1h/2h ⏰\n"
        "🔹 Signal Tracking — WIN/LOSS 100% Track 🏆\n"
        "🔹 Live WIN% — Progress bar එක්ක 🎯\n\n"
        "👇 *Click Menu to get started*"
    )

    keyboard = [[InlineKeyboardButton("📋 MENU", callback_data='menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


# ============ MAIN MENU ============
async def show_menu(query):
    keyboard = [
        [InlineKeyboardButton("🕹️ LIVE PRICE — හැම Coin එකම", callback_data='prices')],
        [InlineKeyboardButton("🟢 NOW GOOD COIN", callback_data='best_coin')],
        [InlineKeyboardButton("💀 BINANCE SHANA SIGNALS", callback_data='shana_signals_menu')],
        [InlineKeyboardButton("📊 STATS — WIN/LOSS Track", callback_data='stats')],
        [InlineKeyboardButton("🔄 Recall Signals", callback_data='recall_signals')],
        [InlineKeyboardButton("⬅️ BACK", callback_data='back_to_welcome')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "📋 *MAIN MENU*\n\n"
        "👇 *Choose an option below:*",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def back_to_welcome(query):
    welcome_text = (
        "🌟 *Welcome to SHANA Signal Bot* 🌟\n\n"
        "🤖 *Powered by Binance*\n"
        "📊 *Real-time Cryptocurrency Analysis*\n\n"
        "🔹 Live Price Tracking — හැම coin එකම 🟢\n"
        "🔹 Smart Trading Signals — Timeframe 5m/20m/50m/1h/2h ⏰\n"
        "🔹 Signal Tracking — WIN/LOSS 100% Track 🏆\n"
        "🔹 Live WIN% — Progress bar එක්ක 🎯\n\n"
        "👇 *Click Menu to get started*"
    )

    keyboard = [[InlineKeyboardButton("📋 MENU", callback_data='menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


# ====================================================================
# 💀 BINANCE SHANA SIGNALS — TIMEFRAME SUB-MENU
# ====================================================================
async def show_shana_signals_menu(query):
    """💀 BINANCE SHANA SIGNALS — බටන් ටික පෙන්වන්න"""
    keyboard = [
        [InlineKeyboardButton("⏰ 5 Minute", callback_data='shana_scan_5m')],
        [InlineKeyboardButton("⏰ 20 MINUTE", callback_data='shana_scan_20m')],
        [InlineKeyboardButton("⏰ 50 MINUTE", callback_data='shana_scan_50m')],
        [InlineKeyboardButton("⏰ 1 HOURS", callback_data='shana_scan_1h')],
        [InlineKeyboardButton("⏰ 2 HOURS", callback_data='shana_scan_2h')],
        [InlineKeyboardButton("⬅️ BACK", callback_data='menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = (
        "💀 *BINANCE SHANA SIGNALS* 💀\n\n"
        "👇 *Timeframe එකක් තෝරන්න:*\n\n"
        "⏰ *5 Minute* — ඉක්මන් signals\n"
        "⏰ *20 MINUTE* — Medium signals\n"
        "⏰ *50 MINUTE* — Swing signals\n"
        "⏰ *1 HOURS* — Hourly signals\n"
        "⏰ *2 HOURS* — Long signals\n\n"
        "📊 *හැම signal එකක්ම TRACK වෙනවා — DELETE වෙන්නේ නැහැ!*\n"
        "🏆 *WIN/LOSS 100% Track කරනවා*"
    )

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def show_shana_timeframe_scan(query, context, tf_label, tf_key):
    """Timeframe එකක් scan කරලා coins list එක පෙන්වන්න"""
    msg = f"🔍 *{tf_label} — SHORT signals සොයමින්...*\n\n"
    msg += "⏳ *සියලුම coins scan වෙමින්...*\n"
    msg += "_මේකට තත්පර 10-15ක් ගතවෙනවා._"
    await query.edit_message_text(msg, parse_mode='Markdown')

    try:
        top_coins = analyzer.get_top_short_coins_timeframe(limit=20, timeframe=tf_key)
    except Exception as e:
        logger.error(f"Scan error {tf_key}: {e}")
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='shana_signals_menu')]]
        await query.edit_message_text(
            f"❌ *Scan error:* `{str(e)[:50]}`\n\n_නැවත try කරන්න._",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if not top_coins:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='shana_signals_menu')]]
        await query.edit_message_text(
            f"✅ *{tf_label} — දැනට SHORT potential ඇති coins නැහැ*\n\n"
            "Market bullish/neutral trend එකේ. වෙන timeframe එකක් try කරන්න.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    context.chat_data['shana_coins'] = top_coins
    context.chat_data['shana_timeframe'] = tf_key
    context.chat_data['shana_tf_label'] = tf_label

    msg = f"💀 *BINANCE SHANA SIGNALS — {tf_label}* 💀\n\n"
    msg += f"📊 *SHORT coins {len(top_coins)}ක් හමුවුනා*\n"
    msg += "👇 *Coin එකක් click කරන්න — Signal Generate + Live WIN%:*\n\n"

    keyboard = []
    for coin_data in top_coins[:15]:
        score = coin_data['score']
        score_bar = generate_colored_bar(min(score, 100), 6)
        reasons = ', '.join(coin_data['reasons'][:2]) if coin_data.get('reasons') else ''
        change = coin_data.get('change_24h', 0)
        change_emoji = "🟢" if change >= 0 else "🔴"

        coin_clean = coin_data['symbol'].replace('/', '')
        keyboard.append([
            InlineKeyboardButton(
                f"{'📉' if score >= 50 else '📊'} {coin_data['symbol']}  {score_bar}  {score}%  |  {change_emoji}{change:+.1f}%  |  {reasons}",
                callback_data=f'shana_coin_{tf_key}_{coin_clean}'
            )
        ])

    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data=f'shana_scan_{tf_key}')])
    keyboard.append([InlineKeyboardButton("⬅️ BACK", callback_data='shana_signals_menu')])

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_shana_coin_analysis(query, context, tf_key, coin_clean):
    """Coin එකක් click කරහම — Signal generate + Live WIN% + Entry/TP1/TP2/SL"""
    # Find full symbol
    full_symbol = coin_clean
    if '/' not in full_symbol:
        for c in COINS:
            if c.replace('/', '') == coin_clean:
                full_symbol = c
                break
        else:
            for c in user_coins:
                if c.replace('/', '') == coin_clean:
                    full_symbol = c
                    break

    # Get timeframe label
    tf_label = "5m"
    for label, key in TIMEFRAMES:
        if key == tf_key:
            tf_label = label
            break

    msg = f"🔍 *[{tf_label}] Analyzing {full_symbol}...*\n\n"
    msg += "⏳ *Signal generate වෙමින්...*"
    await query.edit_message_text(msg, parse_mode='Markdown')

    # ===== GENERATE SIGNAL =====
    signal = analyzer.generate_short_signal_from_scan_timeframe(full_symbol, tf_key)

    # ===== GET LIVE TRACKING =====
    live_data = analyzer.get_live_signal_percentage(full_symbol, 'SHORT')

    # ===== QUICK ANALYSIS =====
    quick = analyzer.analyze_coin_for_short_timeframe(full_symbol, tf_key)

    # ===== BUILD DISPLAY =====
    msg = f"💀 *BINANCE SHANA SIGNALS — {tf_label}* 💀\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🪙 *{full_symbol}*\n\n"

    if signal:
        # Confidence stars
        conf = signal['confidence']
        if conf >= 85:
            stars = "⭐⭐⭐⭐⭐"
        elif conf >= 75:
            stars = "⭐⭐⭐⭐"
        elif conf >= 65:
            stars = "⭐⭐⭐"
        elif conf >= 50:
            stars = "⭐⭐"
        else:
            stars = "⭐"

        msg += (
            f"━━━ *SIGNAL DETAILS* ━━━\n"
            f"📥 *Entry:* `{signal['entry']:.8f}`\n"
            f"🎯 *TP1:* `{signal['take_profit_1']:.8f}`\n"
            f"🎯 *TP2:* `{signal['take_profit_2']:.8f}`\n"
            f"🛑 *SL:* `{signal['stop_loss']:.8f}`\n"
            f"⚡ *Confidence:* `{conf}%` {stars}\n"
            f"📊 *Filters:* `{signal.get('strict_filters', 0)}/5`\n\n"
        )

        if signal.get('reasons'):
            msg += f"📌 *Reasons:*\n"
            for i, r in enumerate(signal['reasons'][:5]):
                msg += f"  {i+1}. {r}\n"
            msg += "\n"
    else:
        msg += "_❌ Signal generate කරන්න තරම් conditions නැහැ._\n\n"

    if quick:
        msg += (
            f"━━━ *QUICK ANALYSIS* ━━━\n"
            f"📊 *Score:* `{quick['score']}/100`\n"
            f"📉 *RSI:* `{quick['rsi']:.1f}`\n"
            f"📊 *24h Change:* `{quick.get('change_24h', 0):+.2f}%`\n\n"
        )

    # ===== LIVE WIN/LOSS TRACKING — 100% =====
    if live_data:
        if live_data['status'] == 'WIN':
            status_emoji = "🏆"
            status_text = "WIN ✅ (TP Hit!)"
            status_color = "🟢"
        elif live_data['status'] == 'LOST':
            status_emoji = "💀"
            status_text = "LOST ❌ (SL Hit!)"
            status_color = "🔴"
        elif live_data['status'] == 'ACTIVE':
            status_emoji = "⏳"
            status_text = "ACTIVE 🟡"
            status_color = "🟡"
        else:
            status_emoji = "⏸️"
            status_text = live_data['status']
            status_color = "⚪"

        bar = generate_colored_bar(live_data['win_percentage'], 10)
        price_emoji = "🟢" if live_data['current_price'] < live_data['entry'] else "🔴"

        # Calculate direction
        if live_data['signal'] == 'SHORT':
            direction_percent = round(((live_data['entry'] - live_data['current_price']) / live_data['entry']) * 100, 2)
            tp_percent = round(abs((live_data['entry'] - live_data['tp1']) / live_data['entry']) * 100, 2)
            sl_percent = round(abs((live_data['entry'] - live_data['sl']) / live_data['entry']) * 100, 2)
        else:
            direction_percent = round(((live_data['current_price'] - live_data['entry']) / live_data['entry']) * 100, 2)
            tp_percent = round(abs((live_data['tp1'] - live_data['entry']) / live_data['entry']) * 100, 2)
            sl_percent = round(abs((live_data['sl'] - live_data['entry']) / live_data['entry']) * 100, 2)

        msg += (
            f"━━━━ *LIVE TRACKING* ━━━━\n"
            f"{status_emoji} *Status:* {status_text} {status_color}\n"
            f"📊 *WIN Progress:* `{live_data['win_percentage']:.1f}%`\n"
            f"`{bar}`\n"
            f"{price_emoji} *Current:* `{live_data['current_price']:.8f}`\n"
            f"📥 *Entry:* `{live_data['entry']:.8f}`\n"
            f"📊 *Direction:* `{direction_percent:+.2f}%`\n"
            f"🎯 *TP1:* `{live_data['tp1']:.8f}`  ({tp_percent:.1f}%)\n"
            f"🛑 *SL:* `{live_data['sl']:.8f}`  ({sl_percent:.1f}%)\n"
        )

        # Direction analysis
        if live_data['signal'] == 'SHORT':
            if live_data['current_price'] < live_data['entry']:
                progress_to_tp = round(abs(live_data['current_price'] - live_data['entry']) / abs(live_data['entry'] - live_data['tp1']) * 100, 1)
                msg += f"\n📉 *Price dropping...* ✅ ({progress_to_tp:.0f}% to TP)"
            elif live_data['current_price'] > live_data['entry']:
                progress_to_sl = round(abs(live_data['current_price'] - live_data['entry']) / abs(live_data['entry'] - live_data['sl']) * 100, 1)
                msg += f"\n📈 *Price rising...* ⚠️ ({progress_to_sl:.0f}% to SL)"
            else:
                msg += f"\n⏸️ *Price at entry...*"
    else:
        msg += "━━━━ *LIVE TRACKING* ━━━━\n"
        msg += "📊 *No active signal to track*\n"
        if signal:
            msg += "_✅ Signal sent — tracking started! Refresh කරන්න._\n"
        else:
            msg += "_❌ Signal generate කරන්න බැරි උනා._\n"

    # Live price
    ticker = analyzer.get_ticker(full_symbol)
    if ticker:
        change = ticker['percentage']
        emoji = "🟢" if float(change) > 0 else "🔴"
        msg += f"\n📊 *24h Change:* {emoji} `{change:+.2f}%`"
        msg += f"\n💵 *Price:* `${ticker['last']:.8f}`"
        msg += f"\n📊 *Volume:* `${ticker['quoteVolume']:.2f}`"

    msg += f"\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    msg += "\n_⚠️ 100% නිවැරදි නැහැ. Risk management use කරන්න._"

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data=f'shana_coin_{tf_key}_{coin_clean}')],
        [InlineKeyboardButton("📊 Signal Journey", callback_data=f'shana_journey_{tf_key}_{coin_clean}')],
        [InlineKeyboardButton("⬅️ BACK", callback_data=f'shana_scan_{tf_key}')]
    ]

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_shana_signal_journey(query, context, tf_key, coin_clean):
    """Signal journey එක පෙන්වන්න — හැම level එකම"""
    full_symbol = coin_clean
    if '/' not in full_symbol:
        for c in COINS:
            if c.replace('/', '') == coin_clean:
                full_symbol = c
                break
        else:
            for c in user_coins:
                if c.replace('/', '') == coin_clean:
                    full_symbol = c
                    break

    # Find the signal key for this coin
    signal_key = None
    for key in list(analyzer.signal_tracker.keys()):
        if full_symbol in key and 'SHORT' in key:
            signal_key = key
            break

    if not signal_key:
        # Try to find any signal for this symbol
        for key in list(analyzer.signal_tracker.keys()):
            sig = analyzer.signal_tracker[key]
            if sig.get('symbol') == full_symbol:
                signal_key = key
                break

    if not signal_key:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data=f'shana_coin_{tf_key}_{coin_clean}')]]
        await query.edit_message_text(
            f"❌ *{full_symbol} සඳහා signal track කරලා නැහැ*\n\n"
            "මුලින් Signal Generate කරන්න.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    journey = analyzer.get_signal_journey(signal_key)

    if not journey:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data=f'shana_coin_{tf_key}_{coin_clean}')]]
        await query.edit_message_text(
            "❌ *Signal journey එක load කරන්න බැරි උනා*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    display = analyzer.format_signal_journey_display(journey)
    if not display:
        display = f"❌ Format error"

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data=f'shana_journey_{tf_key}_{coin_clean}')],
        [InlineKeyboardButton("⬅️ BACK", callback_data=f'shana_coin_{tf_key}_{coin_clean}')]
    ]

    await query.edit_message_text(
        f"`{display}`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ====================================================================
# 🟢 NOW GOOD COIN
# ====================================================================
async def show_best_coin(query):
    msg = "🔍 *හොඳම SHORT coins සොයමින්...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')

    try:
        top_coins = analyzer.get_top_short_coins(limit=5)
    except Exception as e:
        logger.error(f"Best coin error: {e}")
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            f"❌ *Error:* `{str(e)[:50]}`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if not top_coins:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "😴 *දැනට trade එකට හොඳ SHORT coin එකක් නැහැ*\n\n"
            "Market range එකේ. විනාඩි 2කින් try කරන්න.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    msg = "🏆 *NOW GOOD SHORT COINS* 🏆\n\n"
    for i, coin_data in enumerate(top_coins):
        score_bar = generate_colored_bar(min(coin_data['score'], 100), 8)
        reasons = ', '.join(coin_data['reasons'][:3]) if coin_data.get('reasons') else 'Analysis in progress'
        change = coin_data.get('change_24h', 0)
        change_emoji = "🟢" if change >= 0 else "🔴"
        msg += (
            f"{i+1}. *{coin_data['symbol']}*\n"
            f"   Score: `{score_bar}` `{coin_data['score']}%`\n"
            f"   📉 RSI: `{coin_data['rsi']:.1f}` | 24h: {change_emoji} `{change:+.2f}%`\n"
            f"   📌 {reasons}\n\n"
        )
    msg += "_⚠️ 100% නිවැරදි නැහැ!_"

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data='best_coin')],
        [InlineKeyboardButton("⬅️ BACK", callback_data='menu')]
    ]

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ====================================================================
# 🕹️ LIVE PRICE — හැම Coin එකම
# ====================================================================
async def show_prices(query):
    msg = "🟢 *LIVE PRICE — හැම Coin එකම* 🟢\n\n"
    msg += "⏳ *Prices loading...*"
    await query.edit_message_text(msg, parse_mode='Markdown')

    try:
        prices = analyzer.get_all_live_prices()
    except Exception as e:
        logger.error(f"Prices error: {e}")
        keyboard = [[InlineKeyboardButton("🔄 Try Again", callback_data='prices')],
                    [InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            f"❌ *Error loading prices:* `{str(e)[:50]}`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if not prices:
        keyboard = [[InlineKeyboardButton("🔄 Try Again", callback_data='prices'),
                     InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "❌ *Price data නැහැ*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Build nice table
    lines = [
        "╔════════════════════════════════════════════════════╗",
        "║        🟢 LIVE PRICE — ALL 50 COINS 🟢            ║",
        "╠════════════════════════════════════════════════════╣",
        "║  #  │  Coin       │  Price       │  24h%    │ Vol ║",
        "╠════════════════════════════════════════════════════╣"
    ]

    for i, p in enumerate(prices, 1):
        sym = p['symbol'].replace('/USDT', '')
        price = p['price']
        chg = p['change_24h']
        vol = p.get('volume_24h', 0)

        # 24h change emoji
        if chg > 0:
            arrow = "🟢"
        elif chg < 0:
            arrow = "🔴"
        else:
            arrow = "⚪"

        # Volume format
        if vol > 1_000_000_000:
            vol_str = f"${vol/1e9:.1f}B"
        elif vol > 1_000_000:
            vol_str = f"${vol/1e6:.1f}M"
        elif vol > 1_000:
            vol_str = f"${vol/1e3:.1f}K"
        else:
            vol_str = f"${vol:.0f}"

        # Price format
        if price >= 100:
            price_str = f"${price:.2f}"
        elif price >= 1:
            price_str = f"${price:.4f}"
        elif price >= 0.01:
            price_str = f"${price:.6f}"
        else:
            price_str = f"${price:.8f}"

        lines.append(f"║  {i:2d}  │  {sym:<8s}  │  {price_str:<12s}  │  {arrow} {chg:>+6.2f}%  │  {vol_str:<8s}  ║")

    lines.append("╚════════════════════════════════════════════════════╝")
    lines.append(f"🔄 Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    msg = "```\n" + "\n".join(lines) + "\n```"

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data='prices')],
        [InlineKeyboardButton("⬅️ BACK", callback_data='menu')]
    ]

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ====================================================================
# 📊 STATS — WIN/LOSS Track
# ====================================================================
async def show_stats(query):
    msg = "📊 *STATS loading...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')

    try:
        analyzer.update_active_signals()
        stats = analyzer.get_enhanced_stats()
    except Exception as e:
        logger.error(f"Stats error: {e}")
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            f"❌ *Stats error:* `{str(e)[:50]}`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if stats['total_signals'] == 0:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "📊 *තාම signal track කරලා නැහැ*\n\n"
            "💀 BINANCE SHANA SIGNALS button එකෙන් signal generate කරන්න.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Build display
    win_rate_display = f"{stats['win_rate']:.1f}%" if stats['win_rate'] > 0 else "0.0%"
    loss_rate_display = f"{stats['loss_rate']:.1f}%" if stats['loss_rate'] > 0 else "0.0%"

    # Win rate emoji
    if stats['win_rate'] >= 80:
        wr_emoji = "🏆🔥"
    elif stats['win_rate'] >= 60:
        wr_emoji = "✅👍"
    elif stats['win_rate'] >= 40:
        wr_emoji = "📊🤷"
    else:
        wr_emoji = "💀👎"

    lines = [
        "╔══════════════════════════════════════╗",
        "║    📊 BINANCE SHANA STATS 📊         ║",
        "╠══════════════════════════════════════╣",
        f"║  📈 Total Signals  : {stats['total_signals']:<4d}              ║",
        f"║  🏆 Wins           : {stats['total_wins']:<4d}  🟢🟢🟢         ║",
        f"║  💀 Losses         : {stats['total_losses']:<4d}  🔴🔴🔴         ║",
        f"║  ⏳ Active         : {stats['active_signals']:<4d}  🟡🟡🟡         ║",
        f"║  ⌛ Expired        : {stats['expired_signals']:<4d}                  ║",
        "╠══════════════════════════════════════╣",
        f"║  📊 Win Rate       : {win_rate_display:<6s}  {wr_emoji:<7s}      ║",
        f"║  📊 Loss Rate      : {loss_rate_display:<6s}                  ║",
        "╠══════════════════════════════════════╣"
    ]

    # Best signal
    if stats.get('best_signal'):
        best = stats['best_signal']
        lines.append(f"║  🏆 BEST SIGNAL:                           ║")
        lines.append(f"║     {best['symbol']} — {best['signal']} — Conf: {best['confidence']}%   ║")
        lines.append(f"║     Entry: {best['entry']:.8f}        ║")
        lines.append(f"║     TP Hit: {best['tp1']:.8f}                 ║")

    # Worst signal
    if stats.get('worst_signal'):
        worst = stats['worst_signal']
        lines.append(f"║  💀 WORST SIGNAL:                          ║")
        lines.append(f"║     {worst['symbol']} — {worst['signal']} — Conf: {worst['confidence']}%   ║")
        lines.append(f"║     Entry: {worst['entry']:.8f}        ║")
        lines.append(f"║     SL Hit: {worst['sl']:.8f}                  ║")

    # Per coin breakdown
    if stats.get('by_symbol'):
        lines.append(f"╠══════════════════════════════════════╣")
        lines.append(f"║  📊 PER COIN BREAKDOWN:               ║")
        sorted_symbols = sorted(
            stats['by_symbol'].items(),
            key=lambda x: x[1]['wins'] / (x[1]['wins'] + x[1]['losses'] + 0.01) if (x[1]['wins'] + x[1]['losses']) > 0 else 0,
            reverse=True
        )
        for sym, data in sorted_symbols[:10]:
            completed = data['wins'] + data['losses']
            wr = round((data['wins'] / completed) * 100, 1) if completed > 0 else 0
            sym_short = sym.replace('/USDT', '')
            wr_ico = "🏆" if wr >= 80 else "✅" if wr >= 60 else "📊" if wr >= 40 else "💀"
            lines.append(f"║  {wr_ico} {sym_short:<8s}  W:{data['wins']:<2d}  L:{data['losses']:<2d}  A:{data['active']:<2d}  WR:{wr:>5.1f}%  ║")

    lines.append("╚══════════════════════════════════════╝")
    lines.append(f"🔄 Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    msg = "```\n" + "\n".join(lines) + "\n```"

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data='stats')],
        [InlineKeyboardButton("📋 Signal Recall List", callback_data='recall_signals')],
        [InlineKeyboardButton("⬅️ BACK", callback_data='menu')]
    ]

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ====================================================================
# 🔄 Recall Signals — කවදාවත් DELETE වෙන්නේ නැහැ
# ====================================================================
async def show_recall_signals(query, page=0):
    """Track කරපු signals list එක — DELETE වෙන්නේ නැහැ!"""
    try:
        signals_list = analyzer.get_signal_recall_list(limit=50)
    except Exception as e:
        logger.error(f"Recall error: {e}")
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            f"❌ *Recall error:* `{str(e)[:50]}`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if not signals_list:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "📋 *තාම signal track කරලා නැහැ*\n\n"
            "💀 BINANCE SHANA SIGNALS button එකෙන් signal generate කරන්න.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    total = len(signals_list)
    total_pages = (total + 9) // 10
    page = max(0, min(page, total_pages - 1))
    start_idx = page * 10
    end_idx = min(start_idx + 10, total)
    page_signals = signals_list[start_idx:end_idx]

    msg = f"📋 *SIGNAL RECALL LIST* — {total} signals\n"
    msg += f"_කවදාවත් DELETE වෙන්නේ නැහැ — හැමෝම ඉතුරු වෙනවා!_\n\n"

    for i, sig in enumerate(page_signals, start_idx + 1):
        status_emoji = "🏆" if sig['status'] == 'WIN' else "💀" if sig['status'] == 'LOST' else "⏳" if sig['status'] == 'ACTIVE' else "⏸️"
        msg += (
            f"{i}. {status_emoji} *{sig['symbol']}* — {sig['signal']}\n"
            f"   Conf: {sig['confidence']}% | WIN%: {sig['win_percentage']:.1f}% | Status: {sig['status']}\n"
            f"   Entry: {sig['entry']:.8f}\n"
            f"   🆔 `{sig['key'][:40]}...`\n\n"
        )

    # Navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f'recall_page_{page-1}'))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f'recall_page_{page+1}'))

    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("⬅️ BACK", callback_data='menu')])

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ====================================================================
# BUTTON HANDLER — හැම callback එකම
# ====================================================================
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    try:
        # ===== MAIN MENU =====
        if query.data == 'menu':
            await show_menu(query)

        elif query.data == 'back_to_welcome':
            await back_to_welcome(query)

        # ===== 💀 BINANCE SHANA SIGNALS =====
        elif query.data == 'shana_signals_menu':
            await show_shana_signals_menu(query)

        elif query.data.startswith('shana_scan_'):
            tf_map = {
                'shana_scan_5m': ('5 Minute', '5m'),
                'shana_scan_20m': ('20 MINUTE', '20m'),
                'shana_scan_50m': ('50 MINUTE', '50m'),
                'shana_scan_1h': ('1 HOURS', '1h'),
                'shana_scan_2h': ('2 HOURS', '2h'),
            }
            if query.data in tf_map:
                tf_label, tf_key = tf_map[query.data]
                await show_shana_timeframe_scan(query, context, tf_label, tf_key)

        elif query.data.startswith('shana_coin_'):
            # Format: shana_coin_{tf_key}_{coin_clean}
            parts = query.data.split('_', 3)  # ['shana', 'coin', '5m', 'BTCUSDT']
            if len(parts) == 4:
                _, _, tf_key, coin_clean = parts
                await show_shana_coin_analysis(query, context, tf_key, coin_clean)

        elif query.data.startswith('shana_journey_'):
            parts = query.data.split('_', 3)
            if len(parts) == 4:
                _, _, tf_key, coin_clean = parts
                await show_shana_signal_journey(query, context, tf_key, coin_clean)

        # ===== 🟢 NOW GOOD COIN =====
        elif query.data == 'best_coin':
            await show_best_coin(query)

        # ===== 🕹️ LIVE PRICE =====
        elif query.data == 'prices':
            await show_prices(query)

        # ===== 📊 STATS =====
        elif query.data == 'stats':
            await show_stats(query)

        # ===== 🔄 RECALL SIGNALS =====
        elif query.data == 'recall_signals':
            await show_recall_signals(query, 0)

        elif query.data.startswith('recall_page_'):
            try:
                page = int(query.data.split('_')[2])
                await show_recall_signals(query, page)
            except:
                await show_recall_signals(query, 0)

        # ===== ORIGINAL BUTTONS (keep working) =====
        elif query.data == 'refresh_prices':
            await show_prices(query)

        elif query.data == 'refresh_signals':
            # Original short signals
            await show_short_signals_original(query)

        elif query.data == 'short_signals':
            await show_short_signals_original(query)

        elif query.data == 'long_signals':
            await show_long_signals_original(query)

        elif query.data == 'select_coins':
            await show_coin_selector(query)

        elif query.data == 'toggle_auto':
            await toggle_auto_signal(query)

        elif query.data.startswith('coin_'):
            coin = query.data.replace('coin_', '')
            await toggle_coin(query, coin)

        else:
            logger.warning(f"Unknown callback: {query.data}")
            keyboard = [[InlineKeyboardButton("📋 MENU", callback_data='menu')]]
            await query.edit_message_text(
                "⚠️ *Unknown option* — කරුණාකර MENU එකෙන් තෝරන්න.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    except Exception as e:
        logger.error(f"Button handler error: {e}\n{traceback.format_exc()}")
        try:
            keyboard = [[InlineKeyboardButton("📋 MENU", callback_data='menu')]]
            await query.edit_message_text(
                f"❌ *Error:* `{str(e)[:80]}`\n\n_කරුණාකර MENU එකෙන් නැවත try කරන්න._",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass


# ====================================================================
# ORIGINAL HANDLERS — වෙනස් කරලා නැහැ, තියෙන විදියටම
# ====================================================================
async def show_short_signals_original(query):
    """Original SHORT signals — unchanged"""
    msg = "🔍 *SHORT Signals සොයමින්...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')
    signals = []
    for coin in list(user_coins)[:10]:
        try:
            sig = analyzer.find_short_signal(coin)
            if sig:
                signals.append(sig)
            await asyncio.sleep(0.1)
        except:
            continue
    if not signals:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "✅ *දැනට SHORT signal නැහැ*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    signals.sort(key=lambda x: x['confidence'], reverse=True)
    msg = f"🔴 *SHORT Signals — {len(signals)} found*\n\n"
    for sig in signals[:5]:
        msg += (
            f"📉 *{sig['symbol']}*\n"
            f"   Entry: `${sig['entry']:.4f}`\n"
            f"   TP1: `${sig['take_profit_1']:.4f}` | TP2: `${sig['take_profit_2']:.4f}`\n"
            f"   SL: `${sig['stop_loss']:.4f}`\n"
            f"   Confidence: {sig['confidence']}%\n"
            f"   RSI: {sig['rsi']:.1f}\n"
            f"   📌 {', '.join(sig['reasons'][:3])}\n\n"
        )
    keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data='refresh_signals'),
                 InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def show_long_signals_original(query):
    """Original LONG signals — unchanged"""
    msg = "🔍 *LONG Signals සොයමින්...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')
    signals = []
    for coin in list(user_coins)[:10]:
        try:
            sig = analyzer.find_long_signal(coin)
            if sig:
                signals.append(sig)
            await asyncio.sleep(0.1)
        except:
            continue
    if not signals:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "✅ *දැනට LONG signal නැහැ*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    signals.sort(key=lambda x: x['confidence'], reverse=True)
    msg = f"🟢 *LONG Signals — {len(signals)} found*\n\n"
    for sig in signals[:5]:
        msg += (
            f"📈 *{sig['symbol']}*\n"
            f"   Entry: `${sig['entry']:.4f}`\n"
            f"   TP1: `${sig['take_profit_1']:.4f}` | SL: `${sig['stop_loss']:.4f}`\n"
            f"   Confidence: {sig['confidence']}%\n"
            f"   RSI: {sig['rsi']:.1f}\n"
            f"   📌 {', '.join(sig['reasons'][:3])}\n\n"
        )
    keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def show_coin_selector(query):
    """Original coin selector — unchanged"""
    keyboard = []
    row = []
    for i, coin in enumerate(COINS):
        emoji = "✅" if coin in user_coins else "❌"
        row.append(InlineKeyboardButton(f"{emoji} {coin}", callback_data=f'coin_{coin}'))
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ BACK", callback_data='menu')])
    await query.edit_message_text(
        "⚙️ *Select Coins to Monitor*\n\nClick to enable/disable:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def toggle_coin(query, coin_name):
    """Original toggle coin — unchanged"""
    if coin_name in user_coins:
        user_coins.remove(coin_name)
    else:
        user_coins.add(coin_name)
    await show_coin_selector(query)


async def toggle_auto_signal(query):
    """Original toggle auto signal — unchanged"""
    global auto_signal_running
    auto_signal_running = not auto_signal_running
    status = "🟢 ON" if auto_signal_running else "🔴 OFF"
    keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
    await query.edit_message_text(
        f"🔄 *Auto Signal: {status}*\n\n"
        "විනාඩි 2කට වරක් signals check වෙනවා.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ====================================================================
# AUTO SIGNAL LOOP — 24/7 කිසිම SLEEP එකක් නැතුව
# ====================================================================
async def auto_signal_loop():
    """24/7 Auto signal — errors handle කරලා continue වෙනවා"""
    global signal_history
    consecutive_errors = 0
    check_count = 0

    while True:
        try:
            if auto_signal_running:
                check_count += 1
                logger.info(f"🔄 Auto signal check #{check_count}...")

                # Update active signals first
                try:
                    updated = analyzer.update_active_signals()
                    if updated > 0:
                        logger.info(f"📊 Updated {updated} active signals")
                except Exception as e:
                    logger.warning(f"Update active signals error: {e}")

                # Check for WIN signals — POWER BUY SHANA
                try:
                    power_signals = analyzer.check_power_buy_shana()
                    for ps in power_signals:
                        try:
                            await bot.send_message(
                                TELEGRAM_CHAT_ID,
                                ps['message'],
                                parse_mode='Markdown'
                            )
                            logger.info(f"💀🔥 POWER BUY SHANA: {ps['symbol']}")
                        except Exception as e:
                            logger.warning(f"Power buy send error: {e}")
                except Exception as e:
                    logger.warning(f"Power buy check error: {e}")

                # Check for new signals (original auto signal)
                for coin in list(user_coins):
                    try:
                        short = analyzer.find_short_signal(coin)
                        if short and short['confidence'] >= 50:
                            signal_history.append(short)
                            msg = (
                                f"🚨 *SHORT SIGNAL* 🚨\n\n"
                                f"📉 *{short['symbol']}*\n"
                                f"💰 Entry: `${short['entry']:.4f}`\n"
                                f"🎯 TP1: `${short['take_profit_1']:.4f}`\n"
                                f"🛑 SL: `${short['stop_loss']:.4f}`\n"
                                f"⚡ Confidence: {short['confidence']}%\n"
                                f"📌 {', '.join(short['reasons'][:3])}\n\n"
                                f"⏰ {short['timestamp']}"
                            )
                            try:
                                await bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode='Markdown')
                            except:
                                pass

                        long = analyzer.find_long_signal(coin)
                        if long and long['confidence'] >= 40:
                            signal_history.append(long)
                            msg = (
                                f"🟢 *LONG SIGNAL* 🟢\n\n"
                                f"📈 *{long['symbol']}*\n"
                                f"💰 Entry: `${long['entry']:.4f}`\n"
                                f"🎯 TP1: `${long['take_profit_1']:.4f}`\n"
                                f"🛑 SL: `${long['stop_loss']:.4f}`\n"
                                f"⚡ Confidence: {long['confidence']}%\n"
                                f"📌 {', '.join(long['reasons'][:3])}\n\n"
                                f"⏰ {long['timestamp']}"
                            )
                            try:
                                await bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode='Markdown')
                            except:
                                pass
                    except Exception as e:
                        logger.warning(f"Error checking {coin}: {e}")
                        continue

                # Keep signal history manageable
                if len(signal_history) > 200:
                    signal_history = signal_history[-200:]

                consecutive_errors = 0
            else:
                logger.info("⏸️ Auto signal paused")

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Auto signal loop error ({consecutive_errors}): {e}")

            # If too many errors, wait longer
            if consecutive_errors > 5:
                logger.error("🔥 Too many consecutive errors! Waiting 60s...")
                await asyncio.sleep(60)
                consecutive_errors = 0
                continue

        # Wait ANALYSIS_INTERVAL seconds between checks
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
        await asyncio.sleep(1800)  # Every 30 minutes


# ====================================================================
# MAIN
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

    # Run polling with error handling
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
    import time  # for restart delay
    main()
