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

# ===== 🔥 NEW ADDITION 1: OWNER AUTHORIZATION =====
# ඔයාගේ Telegram User ID එක දාන්න (අනිත් අයට bot එක use කරන්න බැරි වෙයි)
# @userinfobot ගිහින් /start කරලා ඔයාගේ ID එක ගන්න
OWNER_ID = 0  # <-- මෙතන ඔයාගේ Telegram User ID එක දාන්න!

# Webhook settings for UptimeRobot
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # Set this for webhook mode
WEBHOOK_PORT = int(os.environ.get("PORT", 8443))
WEBHOOK_LISTEN = "0.0.0.0"


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


# ===== 🔥 NEW ADDITION 2: AUTHORIZATION CHECK =====
def is_owner(update):
    """Check if the user is the owner"""
    if OWNER_ID == 0:
        return True  # No restriction if OWNER_ID not set
    user_id = update.effective_user.id
    return user_id == OWNER_ID


async def owner_only(update, context):
    """Owner authorization wrapper - add this to any handler"""
    if not is_owner(update):
        query = update.callback_query
        if query:
            await query.answer("⛔ මේ bot එක private එකක්! ඔයාට use කරන්න බැහැ.", show_alert=True)
        else:
            await update.message.reply_text("⛔ මේ bot එක private එකක්! ඔයාට use කරන්න බැහැ.")
        return False
    return True


# ============ WELCOME ============
async def start(update, context):
    # 🔥 NEW: Owner check
    if not await owner_only(update, context):
        return
        
    try:
        if os.path.exists(WELCOME_IMAGE):
            with open(WELCOME_IMAGE, 'rb') as photo:
                await update.message.reply_photo(photo=photo)
        elif WELCOME_IMAGE.startswith('http://') or WELCOME_IMAGE.startswith('https://'):
            await update.message.reply_photo(photo=WELCOME_IMAGE)
    except Exception as e:
        logger.warning(f"Welcome image not available: {e}")

    welcome_text = (
        "🌟 *WELCOME to SHANA SHANA * 🌟\n\n"
        "🤖 *Powered by Binance*\n"
        "📊 *Real-time Cryptocurrency Analysis*\n\n"
        "🔹 Live Price Tracking  💸\n"
        "🔹 Smart Trading Signals —  5m/20m/50m/1h/2h ⏰\n"
        "🔹 Signal Tracking — WIN/LOSS 100% Track 🏆\n"
        "🔹 Live WIN% —  🎯\n\n"
        "👇 *Click Menu to get started*"
        " *💀 POWER BUY SHANA 💀*"
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
        [InlineKeyboardButton("🕹️ LIVE PRICE ", callback_data='prices')],
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
        "🌟 *WELCOME to SHANA SHANA * 🌟\n\n"
        "🤖 *Powered by Binance*\n"
        "📊 *Real-time Cryptocurrency Analysis*\n\n"
        "🔹 Live Price Tracking  💸\n"
        "🔹 Smart Trading Signals —  5m/20m/50m/1h/2h ⏰\n"
        "🔹 Signal Tracking — WIN/LOSS 100% Track 🏆\n"
        "🔹 Live WIN% —  🎯\n\n"
        "👇 *Click Menu to get started*"
        " *💀 POWER BUY SHANA 💀*"
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
    """💀 BINANCE SHANA SIGNALS """
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
        "👇 *Time එකක් තෝරන්න:*\n\n"
        "⏰ *5 Minute* — SPEED signals\n"
        "⏰ *20 MINUTE* — Medium signals\n"
        "⏰ *50 MINUTE* — Swing signals\n"
        "⏰ *1 HOURS* — Hourly signals\n"
        "⏰ *2 HOURS* — Long signals\n\n"
        "📊 *හැම signal එකක්ම TRACK වෙනවාැ!*\n"
        "🏆 *WIN/LOSS 100% Track කරනවා*"
    )

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def show_shana_timeframe_scan(query, context, tf_label, tf_key):
    """Timeframe එකක් scan කරලා coins list එක පෙන්වන්න"""
    msg = f"🔍 *{tf_label} — SHORT signals PENDIN...*\n\n"
    msg += "⏳ *All coins scan PENDIN...*\n"
    msg += "_PENDIN TIME  10-15 Wait..._"
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
            f"✅ *{tf_label} — NOW SHORT potential  coins NO*\n\n"
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
        change_emoji = "🟢"
        # ... (progress bar display for each coin)
        sym_clean = coin_data['symbol'].replace('/', '')
        btn_text = f"{coin_data['symbol']} | {score_bar} {score}%"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f'shana_coin_{tf_key}_{sym_clean}')])

    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data=f'shana_scan_{tf_key}')])
    keyboard.append([InlineKeyboardButton("⬅️ BACK", callback_data='shana_signals_menu')])

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_shana_coin_analysis(query, context, tf_key, coin_clean):
    """Coin එකක signal generate කරලා Journey button + WIN% පෙන්වන්න"""
    # ... (existing coin analysis code - unchanged)
    msg = f"🔍 *{coin_clean} signal generate PENDIN...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')

    try:
        signal = analyzer.generate_short_signal_from_scan_timeframe(coin_clean, timeframe=tf_key)
    except Exception as e:
        logger.error(f"Signal gen error {coin_clean}: {e}")
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data=f'shana_scan_{tf_key}')]]
        await query.edit_message_text(
            f"❌ *Signal error:* `{str(e)[:50]}`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if not signal:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data=f'shana_scan_{tf_key}')]]
        await query.edit_message_text(
            f"✅ *{coin_clean} — දැනට SHORT signal නැහැ*\n\n"
            "Market bullish/neutral. වෙන coin එකක් try කරන්න.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # 🔥 NEW: Mark this signal as belonging to this user
    try:
        user_id = query.from_user.id
        analyzer.mark_user_signal(signal, user_id)
    except Exception as e:
        logger.warning(f"Could not mark user signal: {e}")
    # (continues with existing code)

    # Build signal display
    symbol = signal['symbol']
    entry = signal['entry']
    tp1 = signal.get('take_profit_1', signal.get('tp1', 0))
    tp2 = signal.get('take_profit_2', signal.get('tp2', 'N/A'))
    sl = signal.get('stop_loss', signal.get('sl', 0))
    confidence = signal['confidence']
    reasons = signal.get('reasons', [])
    rsi = signal.get('rsi', 50)

    conf_bar = generate_colored_bar(confidence, 6)

    perp = signal.get('perpetual', 0)
    perp_emoji = "🟢" if perp > 0 else ("🔴" if perp < 0 else "⚪")
    perp_str = f"{perp_emoji} Perp: {perp:+.2f}%" if perp != 0 else "⚪ Perp: 0.00%"

    change = signal.get('change_24h', 0)
    chg_emoji = "🟢" if change > 0 else ("🔴" if change < 0 else "⚪")

    rsi_level = "Oversold 🔵" if rsi < 30 else ("Overbought 🔴" if rsi > 70 else "Neutral ⚪")

    volume = signal.get('volume', 0)
    vol_str = f"${volume/1e6:.1f}M" if volume > 1e6 else f"${volume/1e3:.1f}K"

    win_pct = signal.get('win_percentage', 50)
    if win_pct >= 80:
        win_emoji = "🏆🔥"
    elif win_pct >= 60:
        win_emoji = "✅👍"
    elif win_pct >= 40:
        win_emoji = "📊🤷"
    else:
        win_emoji = "💀👎"

    msg = (
        f"💀 *{symbol} — SHORT SIGNAL* 💀\n\n"
        f"💰 *Entry:* `${entry:.8f}`\n"
        f"🎯 *TP1:* `${tp1:.8f}`\n"
        f"{'🎯 *TP2:* `' + str(tp2) + '`' if tp2 != 'N/A' else ''}\n"
        f"🛑 *SL:* `${sl:.8f}`\n\n"
        f"⚡ *Confidence: {confidence}%* {conf_bar}\n"
        f"📊 *RSI:* {rsi:.1f} — {rsi_level}\n"
        f"📈 *24h Change:* {chg_emoji} {change:+.2f}%\n"
        f"{perp_str}\n"
        f"💧 *Volume:* {vol_str}\n\n"
        f"🏆 *Live WIN%: {win_pct:.1f}%* {win_emoji}\n"
    )

    if reasons:
        msg += f"📌 *Reasons:* {', '.join(reasons[:4])}\n\n"

    msg += f"⏰ `{signal['timestamp']}`\n"
    msg += f"🆔 `{signal['key'][:50]}...`\n"

    keyboard = [
        [InlineKeyboardButton("📋 Signal Journey", callback_data=f'shana_journey_{tf_key}_{coin_clean}')],
        [InlineKeyboardButton("⬅️ BACK to coins", callback_data=f'shana_scan_{tf_key}')],
        [InlineKeyboardButton("📋 MENU", callback_data='menu')]
    ]

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_shana_signal_journey(query, context, tf_key, coin_clean):
    """Signal Journey — edit_message_text use කරලා chat එකේ ඉතුරු වෙනවා"""
    msg = f"🔍 *{coin_clean} — Signal Journey loading...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')

    try:
        # 🔥 NEW: Get journey for this specific user
        user_id = query.from_user.id
        journey = analyzer.get_signal_journey(coin_clean, timeframe=tf_key, user_id=user_id)
    except Exception as e:
        journey = analyzer.get_signal_journey(coin_clean, timeframe=tf_key)

    if not journey:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data=f'shana_coin_{tf_key}_{coin_clean}')]]
        await query.edit_message_text(
            f"📋 *{coin_clean} — Signal Journey data නැහැ*\n\n"
            "මේ coin එකට තාම signal track කරලා නැහැ.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Display journey
    lines = [
        f"╔═══ 📋 SIGNAL JOURNEY: {coin_clean} ═══╗",
        f"║  🎯 Timeframe: {tf_key}",
        f"║  🆔 Signal Key: {journey['signal_key'][:40]}...",
        f"║  📊 Status: {'🏆 WIN' if journey['status'] == 'WIN' else '💀 LOST' if journey['status'] == 'LOST' else '⏳ ACTIVE'}",
        f"║  ⚡ Confidence: {journey['confidence']}%",
        f"║  🏆 WIN%: {journey.get('win_percentage', 0):.1f}%",
        f"║",
        f"║  💰 Entry: {journey['entry']:.8f}",
    ]

    if journey.get('tp1'):
        lines.append(f"║  🎯 TP1: {journey['tp1']:.8f}")
    if journey.get('sl'):
        lines.append(f"║  🛑 SL: {journey['sl']:.8f}")

    if journey.get('history'):
        lines.append(f"║")
        lines.append(f"║  📜 Price History:")
        for h in journey['history'][-10:]:
            emoji = "🟢" if h.get('action') == 'WIN' else "🔴" if h.get('action') == 'LOST' else "⚪"
            lines.append(f"║    {emoji} {h.get('time', '')[:16]} — ${h.get('price', 0):.8f}")

    lines.append(f"║")
    lines.append(f"╚═══ {datetime.now().strftime('%Y-%m-%d %H:%M')} ═══╝")

    msg = "```\n" + "\n".join(lines) + "\n```"

    # BACK button goes to coin analysis page (edit_message_text — message stays visible!)
    keyboard = [
        [InlineKeyboardButton("⬅️ BACK to Signal", callback_data=f'shana_coin_{tf_key}_{coin_clean}')],
        [InlineKeyboardButton("📋 MENU", callback_data='menu')]
    ]

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ====================================================================
# 🟢 NOW GOOD COIN
# ====================================================================
async def show_best_coin(query):
    msg = "🔍 *NOW GOOD COIN search PENDIN...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')

    all_scores = []
    for coin in list(user_coins)[:30]:
        try:
            sig = analyzer.find_short_signal(coin)
            if sig and sig.get('confidence', 0) >= 40:
                all_scores.append({
                    'symbol': coin,
                    'signal': 'SHORT',
                    'confidence': sig['confidence'],
                    'rsi': sig.get('rsi', 50),
                    'entry': sig.get('entry', 0),
                    'reasons': sig.get('reasons', [])
                })
        except:
            pass

    if not all_scores:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "✅ *දැනට SHORT signal එකක් නැහැ*\n\n"
            "Market bullish/neutral. පසුව try කරන්න.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    all_scores.sort(key=lambda x: x['confidence'], reverse=True)
    top = all_scores[:5]

    msg = "🟢 *NOW GOOD COIN — TOP RANK* 🟢\n\n"
    for i, item in enumerate(top, 1):
        conf_bar = generate_colored_bar(item['confidence'], 6)
        reasons = ', '.join(item['reasons'][:2]) if item.get('reasons') else ''
        msg += (
            f"{i}. *{item['symbol']}* {conf_bar} {item['confidence']}%\n"
            f"   RSI: {item['rsi']:.1f} | Entry: `${item['entry']:.8f}`\n"
            f"   📌 {reasons}\n\n"
        )

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
# 🕹️ LIVE PRICE
# ====================================================================
async def show_prices(query):
    msg = "🕹️ *LIVE PRICE loading...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')

    try:
        live_prices = analyzer.get_all_live_prices()
    except Exception as e:
        logger.error(f"Live price error: {e}")
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            f"❌ *Price error:* `{str(e)[:50]}`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if not live_prices:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "❌ *ලයිව් price data නැහැ*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    lines = [
        "╔════════════════════════════════════════════════════╗",
        "║  🕹️  BINANCE LIVE PRICES  🕹️                      ║",
        "╠════════════════════════════════════════════════════╣",
        "║  # │ SYMBOL    │ PRICE          │ 24H CHG │ VOL   ║",
        "╠════════════════════════════════════════════════════╣"
    ]

    for i, item in enumerate(live_prices[:20], 1):
        sym = item['symbol'].replace('/USDT', '')
        price = item['price']
        chg = item['change_24h']
        vol = item['volume']
        arrow = "🟢" if chg > 0 else ("🔴" if chg < 0 else "⚪")

        if vol > 1_000_000:
            vol_str = f"${vol/1e6:.1f}M"
        elif vol > 1_000:
            vol_str = f"${vol/1e3:.1f}K"
        else:
            vol_str = f"${vol:.0f}"

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
# 📊 STATS — WIN/LOSS Track (OWNER signals විතරයි!)
# ====================================================================
async def show_stats(query):
    msg = "📊 *STATS loading...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')

    try:
        analyzer.update_active_signals()
        # 🔥 NEW: Use user-specific stats! Owner signals විතරයි ගණන් කරන්නේ
        user_id = query.from_user.id
        stats = analyzer.get_user_stats(user_id=user_id)
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

    if stats.get('best_signal'):
        best = stats['best_signal']
        lines.append(f"║  🏆 BEST SIGNAL:                           ║")
        lines.append(f"║     {best['symbol']} — {best['signal']} — Conf: {best['confidence']}%   ║")
        lines.append(f"║     Entry: {best['entry']:.8f}        ║")
        lines.append(f"║     TP Hit: {best['tp1']:.8f}                 ║")

    if stats.get('worst_signal'):
        worst = stats['worst_signal']
        lines.append(f"║  💀 WORST SIGNAL:                          ║")
        lines.append(f"║     {worst['symbol']} — {worst['signal']} — Conf: {worst['confidence']}%   ║")
        lines.append(f"║     Entry: {worst['entry']:.8f}        ║")
        lines.append(f"║     SL Hit: {worst['sl']:.8f}                  ║")

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
# 🔄 Recall Signals — OWNER signals විතරයි!
# ====================================================================
async def show_recall_signals(query, page=0):
    """Track කරපු signals list එක — Owner signals විතරයි"""
    try:
        # 🔥 NEW: Use user-specific recall! Owner signals විතරයි
        user_id = query.from_user.id
        signals_list = analyzer.get_user_recall_list(user_id=user_id, limit=50)
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

    msg = f"📋 *SIGNAL RECALL LIST* — {total} signals (ඔයාගේ විතරයි)\n"
    msg += f"_කවදාවත් DELETE වෙන්නේ නැහැ — හැමෝම ඉතුරු වෙනවා!_\n\n"

    for i, sig in enumerate(page_signals, start_idx + 1):
        status_emoji = "🏆" if sig['status'] == 'WIN' else "💀" if sig['status'] == 'LOST' else "⏳" if sig['status'] == 'ACTIVE' else "⏸️"
        msg += (
            f"{i}. {status_emoji} *{sig['symbol']}* — {sig['signal']}\n"
            f"   Conf: {sig['confidence']}% | WIN%: {sig['win_percentage']:.1f}% | Status: {sig['status']}\n"
            f"   Entry: {sig['entry']:.8f}\n"
            f"   🆔 `{sig['key'][:40]}...`\n\n"
        )

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
# BUTTON HANDLER — OWNER CHECK එකත් එක්ක
# ====================================================================
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    # 🔥 NEW: Owner check — වෙන කෙනෙක් නම් එපා!
    if not is_owner(update):
        await query.answer("⛔ මේ bot එක private එකක්! ඔයාට use කරන්න බැහැ.", show_alert=True)
        return

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
            parts = query.data.split('_', 3)
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

                try:
                    updated = analyzer.update_active_signals()
                    if updated > 0:
                        logger.info(f"📊 Updated {updated} active signals")
                except Exception as e:
                    logger.warning(f"Update active signals error: {e}")

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


# ===== 🔥 NEW ADDITION 3: WEBHOOK MODE FOR UPTIMEROBOT =====
async def webhook_mode(app):
    """Webhook mode — UptimeRobot / Railway / Render etc. සඳහා"""
    if not WEBHOOK_URL:
        logger.info("⚠️ WEBHOOK_URL environment variable එක set කරලා නැහැ. Polling mode use කරන්න.")
        return False

    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await app.bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook set to: {webhook_url}")

        # Start webhook
        await app.start()
        app.updater.start_polling()  # Keep polling for background tasks

        # Run on specified port
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
    
    # 🔥 NEW: Authorized users info
    if OWNER_ID != 0:
        logger.info(f"🔒 Bot is PRIVATE — Owner ID: {OWNER_ID}")
    else:
        logger.warning("⚠️ OWNER_ID set කරලා නැහැ! @userinfobot ගිහින් /start කරලා ID එක ගන්න.")

    # 🔥 NEW: Try webhook first, fallback to polling
    try:
        loop.run_until_complete(webhook_mode(app))
        # If webhook succeeded, keep running
        loop.run_forever()
    except Exception as e:
        logger.warning(f"Webhook failed ({e}), falling back to polling mode...")

    # Run polling with error handling (fallback)
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
