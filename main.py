import asyncio
import logging
import os
from datetime import datetime
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
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


# ============ Progress Bar Helper ============
def generate_progress_bar(percentage, length=10):
    filled = int(min(percentage, 100) / 100 * length)
    return '█' * filled + '░' * (length - filled)


# ============ WELCOME + MENU SYSTEM ============

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
        "🔹 Live Price Tracking\n"
        "🔹 Smart Trading Signals\n"
        "🔹 Market Analysis\n\n"
        "👇 *Click Menu to get started*"
    )

    keyboard = [[InlineKeyboardButton("📋 MENU", callback_data='menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def show_menu(query):
    keyboard = [
        [InlineKeyboardButton("🕹️ LIVE PRICE", callback_data='prices')],
        [InlineKeyboardButton("🟢 NOW GOOD COIN", callback_data='best_coin')],
        [InlineKeyboardButton("🔴 SHORT SIGNALS 5 MINUTE", callback_data='short_signals_5min')],
        [InlineKeyboardButton("📊 STATS", callback_data='stats')],
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
        "🔹 Live Price Tracking\n"
        "🔹 Smart Trading Signals\n"
        "🔹 Market Analysis\n\n"
        "👇 *Click Menu to get started*"
    )

    keyboard = [[InlineKeyboardButton("📋 MENU", callback_data='menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


# ============ SHORT SIGNALS 5 MINUTE — ALL coins list ============
async def show_short_signals_5min(query, context):
    msg = "🔍 *SHORT potential සොයමින්...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')
    
    top_coins = analyzer.get_top_short_coins(limit=25)
    
    if not top_coins:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "✅ *දැනට SHORT potential ඇති coins නැහැ*\n\n"
            "Market bullish/neutral trend එකේ.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    context.chat_data['top_short_coins'] = top_coins
    
    msg = "🔴 *SHORT SIGNALS 5 MINUTE*\n\n"
    msg += "👇 *Coin එකක් click කරන්න full analysis + Live WIN% බලන්න:*\n\n"
    
    keyboard = []
    for coin_data in top_coins[:15]:
        score = coin_data['score']
        score_bar = generate_progress_bar(min(score, 100))
        reasons = ', '.join(coin_data['reasons'][:2]) if coin_data.get('reasons') else ''
        
        coin_clean = coin_data['symbol'].replace('/', '')
        keyboard.append([
            InlineKeyboardButton(
                f"{coin_data['symbol']}  {score_bar}  {score}%  |  {reasons}",
                callback_data=f'shortcoin_{coin_clean}'
            )
        ])
    
    keyboard.append([InlineKeyboardButton("⬅️ BACK", callback_data='menu')])
    
    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============ FIXED: Coin එකක full short analysis + Live WIN% + Signal හැමවිටම ============
async def show_coin_short_analysis(query, context, coin_clean):
    """Show full SHORT analysis + live WIN% + ALWAYS generate signal"""
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
    
    msg = f"🔍 *Analyzing {full_symbol}...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')
    
    # ===== TRY generate_short_signal_from_scan — මේක ALWAYS signal එකක් දෙනවා =====
    signal = analyzer.generate_short_signal_from_scan(full_symbol)
    
    # Get live tracking data
    live_data = analyzer.get_live_signal_percentage(full_symbol, 'SHORT')
    
    quick = analyzer.analyze_coin_for_short(full_symbol)
    
    msg = f"🔴 *SHORT SIGNAL — {full_symbol}*\n\n"
    
    if signal:
        msg += (
            f"━━━ *SIGNAL DETAILS* ━━━\n"
            f"💰 *Entry:* `{signal['entry']:.8f}`\n"
            f"🎯 *TP1:* `{signal['take_profit_1']:.8f}`\n"
            f"🎯 *TP2:* `{signal['take_profit_2']:.8f}`\n"
            f"🛑 *SL:* `{signal['stop_loss']:.8f}`\n"
            f"⚡ *Confidence:* `{signal['confidence']}%`\n"
            f"📊 *Strict Filters:* `{signal.get('strict_filters', 0)}/5`\n\n"
        )
        
        if signal.get('reasons'):
            msg += f"📌 *Reasons:*\n"
            for i, r in enumerate(signal['reasons'][:5]):
                msg += f"  {i+1}. {r}\n"
            msg += "\n"
    
    if quick:
        msg += (
            f"━━━ *QUICK ANALYSIS* ━━━\n"
            f"📊 *Score:* `{quick['score']}%`\n"
            f"📉 *RSI:* `{quick['rsi']:.1f}`\n"
            f"📊 *Volume Ratio:* `{signal.get('volume_ratio', 1.0):.2f}x`\n"
            f"📊 *ADX:* `{signal.get('adx', 0):.1f}`\n\n"
        )
    
    # ===== LIVE WIN/LOSS TRACKING — Percentage + Progress Bar =====
    if live_data:
        if live_data['status'] == 'WIN':
            status_emoji = "🏆"
            status_text = "WIN ✅ (TP Hit!)"
        elif live_data['status'] == 'LOST':
            status_emoji = "💀"
            status_text = "LOST ❌ (SL Hit!)"
        elif live_data['status'] == 'ACTIVE':
            status_emoji = "⏳"
            status_text = "ACTIVE 🟢"
        else:
            status_emoji = "⏸️"
            status_text = live_data['status']
        
        bar = generate_progress_bar(live_data['win_percentage'])
        price_emoji = "🟢" if live_data['current_price'] < live_data['entry'] else "🔴"
        
        msg += (
            f"━━━ *LIVE TRACKING* ━━━\n"
            f"{status_emoji} *Status:* `{status_text}`\n"
            f"📊 *WIN Progress: `{live_data['win_percentage']:.1f}%`*\n"
            f"`{bar}`\n"
            f"{price_emoji} *Current:* `{live_data['current_price']:.8f}`\n"
            f"💰 *Entry:* `{live_data['entry']:.8f}`\n"
            f"🎯 *TP:* `{live_data['tp1']:.8f}` →  {abs(live_data['entry'] - live_data['tp1'])/abs(live_data['entry'] - live_data['sl'])*100:.0f}%\n"
            f"🛑 *SL:* `{live_data['sl']:.8f}`\n"
        )
        
        # Direction arrow
        price_diff = live_data['current_price'] - live_data['entry']
        if live_data['signal'] == 'SHORT':
            if price_diff < 0:
                pct_to_tp = abs(price_diff) / abs(live_data['entry'] - live_data['tp1']) * 100
                msg += f"\n📉 *Price dropping...* TP direction ✅ ({pct_to_tp:.0f}%)"
            elif price_diff > 0:
                pct_to_sl = abs(price_diff) / abs(live_data['entry'] - live_data['sl']) * 100
                msg += f"\n📈 *Price rising...* SL direction ⚠️ ({pct_to_sl:.0f}%)"
            else:
                msg += f"\n⏸️ *Price at entry...*"
    else:
        msg += "━━━ *LIVE TRACKING* ━━━\n"
        msg += "📊 *No active signal to track*\n"
        if signal:
            msg += "_✅ Signal sent — tracking started! Refresh කරන්න._\n"
        else:
            msg += "_Signal generate කරන්න තරම් conditions නැහැ._\n"
    
    # Live price + 24h change
    ticker = analyzer.get_ticker(full_symbol)
    if ticker:
        change = ticker['percentage']
        emoji = "🟢" if float(change) > 0 else "🔴"
        msg += f"\n📊 *24h Change:* {emoji} `{change:+.2f}%`"
        msg += f"\n💵 *Price:* `${ticker['last']:.8f}`"
    
    msg += f"\n\n⏰ {datetime.now().strftime('%H:%M:%S')}"
    msg += "\n_⚠️ 100% නිවැරදි නැහැ!_"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data=f'refresh_{coin_clean}')],
        [InlineKeyboardButton("⬅️ BACK", callback_data='short_signals_5min')]
    ]
    
    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============ NOW GOOD COIN — SHORT coins විතරක් ============
async def show_best_coin(query):
    msg = "🔍 *හොඳම SHORT coins සොයමින්...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')
    
    top_coins = analyzer.get_top_short_coins(limit=5)
    
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
        score_bar = generate_progress_bar(min(coin_data['score'], 100))
        reasons = ', '.join(coin_data['reasons'][:3]) if coin_data.get('reasons') else 'Analysis in progress'
        change = coin_data.get('change_24h', 0)
        change_emoji = "🟢" if change >= 0 else "🔴"
        msg += (
            f"{i+1}. *{coin_data['symbol']}*\n"
            f"   Score: `{score_bar}` `{coin_data['score']}%`\n"
            f"   RSI: `{coin_data['rsi']:.1f}` | 24h: {change_emoji} `{change:+.2f}%`\n"
            f"   📌 {reasons}\n\n"
        )
    msg += "_⚠️ 100% නිවැරදි නැහැ!_"
    
    keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============ Button Handler ============
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == 'menu':
        await show_menu(query)
    
    elif query.data == 'back_to_welcome':
        await back_to_welcome(query)
    
    elif query.data == 'short_signals_5min':
        context.chat_data['signal_page'] = 0
        await show_short_signals_5min(query, context)
    
    elif query.data.startswith('shortcoin_'):
        coin_clean = query.data.replace('shortcoin_', '')
        await show_coin_short_analysis(query, context, coin_clean)
    
    elif query.data.startswith('refresh_'):
        coin_clean = query.data.replace('refresh_', '')
        await show_coin_short_analysis(query, context, coin_clean)
    
    elif query.data == 'next_signal':
        context.chat_data['signal_page'] = context.chat_data.get('signal_page', 0) + 1
        await show_short_signals_5min(query, context)
    
    elif query.data == 'prev_signal':
        context.chat_data['signal_page'] = context.chat_data.get('signal_page', 0) - 1
        await show_short_signals_5min(query, context)
    
    elif query.data == 'prices':
        await show_prices(query)
    
    elif query.data == 'best_coin':
        await show_best_coin(query)
    
    elif query.data == 'short_signals':
        await show_short_signals(query)
    
    elif query.data == 'long_signals':
        await show_long_signals(query)
    
    elif query.data == 'select_coins':
        await show_coin_selector(query)
    
    elif query.data == 'toggle_auto':
        await toggle_auto_signal(query)
    
    elif query.data == 'stats':
        await show_stats(query)
    
    elif query.data.startswith('coin_'):
        coin = query.data.replace('coin_', '')
        await toggle_coin(query, coin)
    
    elif query.data == 'refresh_prices':
        await show_prices(query)
    
    elif query.data == 'refresh_signals':
        await show_short_signals(query)


# ============ UNCHANGED: Existing handlers ============

async def show_prices(query):
    msg = "📊 *Binance Live Prices*\n\n"
    for coin in list(user_coins)[:10]:
        try:
            ticker = analyzer.get_ticker(coin)
            if ticker:
                price = ticker['last']
                change = ticker['percentage']
                emoji = "🟢" if float(change) > 0 else "🔴"
                msg += f"{emoji} *{coin}*: `${price:.4f}` ({change:+.2f}%)\n"
            else:
                msg += f"❌ {coin}: No data\n"
        except:
            msg += f"❌ {coin}: Error\n"
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data='refresh_prices')],
        [InlineKeyboardButton("⬅️ BACK", callback_data='menu')]
    ]
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def show_short_signals(query):
    msg = "🔍 *SHORT Signals සොයමින්...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')
    signals = []
    for coin in user_coins:
        sig = analyzer.find_short_signal(coin)
        if sig:
            signals.append(sig)
        await asyncio.sleep(0.2)
    if not signals:
        await query.edit_message_text(
            "✅ *දැනට SHORT signal නැහැ*\n\n"
            "Market bullish trend එකේ.",
            parse_mode='Markdown'
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
    keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data='refresh_signals')]]
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def show_long_signals(query):
    msg = "🔍 *LONG Signals සොයමින්...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')
    signals = []
    for coin in user_coins:
        sig = analyzer.find_long_signal(coin)
        if sig:
            signals.append(sig)
        await asyncio.sleep(0.2)
    if not signals:
        await query.edit_message_text(
            "✅ *දැනට LONG signal නැහැ*\n\n"
            "Market bearish trend එකේ.",
            parse_mode='Markdown'
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
    await query.edit_message_text(msg, parse_mode='Markdown')


async def show_coin_selector(query):
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
    await query.edit_message_text(
        "⚙️ *Select Coins to Monitor*\n\n"
        "Click to enable/disable:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def toggle_coin(query, coin_name):
    if coin_name in user_coins:
        user_coins.remove(coin_name)
    else:
        user_coins.add(coin_name)
    await show_coin_selector(query)


async def toggle_auto_signal(query):
    global auto_signal_running
    auto_signal_running = not auto_signal_running
    status = "🟢 ON" if auto_signal_running else "🔴 OFF"
    await query.edit_message_text(
        f"🔄 *Auto Signal: {status}*\n\n"
        "විනාඩි 2කට වරක් signals check වෙනවා.",
        parse_mode='Markdown'
    )


async def show_stats(query):
    msg = (
        f"📋 *Bot Statistics*\n\n"
        f"📊 Exchange: *Binance*\n"
        f"👀 Coins: *{len(user_coins)}*\n"
        f"🔄 Auto Signal: {'ON' if auto_signal_running else 'OFF'}\n"
        f"📈 Total Signals: *{len(signal_history)}*\n"
        f"⏰ Last Check: *{datetime.now().strftime('%H:%M:%S')}*\n"
    )
    keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def auto_signal_loop():
    global signal_history
    while True:
        if auto_signal_running:
            try:
                logger.info("🔄 Auto signal checking...")
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
                            await bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode='Markdown')
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
                            await bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode='Markdown')
                    except Exception as e:
                        logger.error(f"Error checking {coin}: {e}")
                        continue
                if len(signal_history) > 100:
                    signal_history = signal_history[-100:]
            except Exception as e:
                logger.error(f"Auto signal loop error: {e}")
        await asyncio.sleep(ANALYSIS_INTERVAL)


# ============ MAIN ============
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(auto_signal_loop())

    logger.info("🤖 SHANA Signal Bot started! (Binance only)")
    app.run_polling(allowed_updates=['message', 'callback_query'])


if __name__ == "__main__":
    main()
