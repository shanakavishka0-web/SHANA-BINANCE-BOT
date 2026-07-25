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
# 📌 ඔබගේ Welcome Image එක මෙතන set කරන්න (local file path හෝ URL)
# Example: "welcome.jpg"  (local file)  or  "https://example.com/welcome.jpg"  (URL)
WELCOME_IMAGE = "welcome.jpg"  # ← මෙය ඔබගේ image path/URL එකට වෙනස් කරන්න!


# ============ NEW: WELCOME + MENU SYSTEM ============

async def start(update, context):
    """Welcome message with Image + Menu button"""
    # Welcome image එක send කරන්න (image එක නැත්නම් error නොදී text විතරක් යයි)
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
    """Main Menu List"""
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
    """Back to Welcome message"""
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


# ============ FIXED: SHORT SIGNALS 5 MINUTE (Full Analysis + Live WIN/LOSS %) ============

async def show_short_signals_5min(query, context):
    """🔴 SHORT SIGNALS 5 MINUTE — 100% Full Analysis + Live WIN/LOSS % Tracking"""
    msg = "🔍 *SHORT Signals ඇනලයිසින් කරමින්...*\n\n"
    msg += "⏳ *Please wait... (5 sec)*\n\n"
    msg += "_සියලුම Technical Indicators භාවිතා කරමින් විශ්ලේෂණය කරයි..._"
    
    await query.edit_message_text(msg, parse_mode='Markdown')

    # Step 1: Update all active signal tracking first (WIN/LOSS status update)
    try:
        analyzer.update_active_signals()
    except Exception as e:
        logger.warning(f"Signal tracking update error: {e}")

    # Step 2: Full analysis on all user coins using the enhanced analyzer
    signals = []
    
    for coin in list(user_coins):
        try:
            sig = analyzer.find_short_signal(coin)
            if sig:
                # Get live WIN/LOSS tracking for this signal
                try:
                    live_data = analyzer.get_live_signal_percentage(coin, 'SHORT')
                    if live_data:
                        sig['tracked_status'] = live_data['status']
                        sig['live_win_percentage'] = live_data['win_percentage']
                        sig['current_live_price'] = live_data['current_price']
                    else:
                        sig['tracked_status'] = 'NEW'
                        sig['live_win_percentage'] = 0.0
                        sig['current_live_price'] = sig['entry']
                except:
                    sig['tracked_status'] = 'NEW'
                    sig['live_win_percentage'] = 0.0
                    sig['current_live_price'] = sig['entry']
                
                signals.append(sig)
        except Exception as e:
            logger.error(f"Analysis error {coin}: {e}")
            continue

    if not signals:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "✅ *දැනට SHORT signal නැහැ*\n\n"
            "🔍 Market එකේ ප්‍රමාණවත් bearish signals නැහැ.\n"
            "😴 විනාඩි 2කින් නැවත try කරන්න.\n\n"
            "_💡 Strong bearish reversal pattern එකක් එනතුරු බලා සිටින්න_",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Step 3: Sort by confidence (highest first)
    signals.sort(key=lambda x: x['confidence'], reverse=True)

    # Step 4: Store in chat_data for pagination
    context.chat_data['short_signal_list'] = signals
    page = context.chat_data.get('short_signal_page', 0)
    total = len(signals)

    # Clamp page
    if page < 0:
        page = 0
        context.chat_data['short_signal_page'] = 0
    elif page >= total:
        page = total - 1
        context.chat_data['short_signal_page'] = total - 1

    sig = signals[page]
    
    # Get WIN/LOSS status emoji
    status_emoji = "🟢" if sig.get('tracked_status') == 'WIN' else ("🔴" if sig.get('tracked_status') == 'LOST' else "🟡")
    win_percent = sig.get('live_win_percentage', 0.0)
    
    # Build WIN/LOSS progress bar
    bar_len = 20
    filled = int(win_percent / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    
    # Status text
    if sig.get('tracked_status') == 'WIN':
        status_line = f"\n🏆 *WIN* 🏆\n{bar} `100.0%` ✅ *Take Profit Hit!*"
    elif sig.get('tracked_status') == 'LOST':
        status_line = f"\n💀 *LOST* 💀\n{bar} `0.0%` ❌ *Stop Loss Hit!*"
    elif sig.get('tracked_status') == 'EXPIRED':
        status_line = f"\n⏰ *EXPIRED*\n{bar} `{win_percent}%`"
    else:
        status_line = f"\n📊 *Live WIN Rate:*\n{bar} `{win_percent}%`"

    # Build signal message
    msg = (
        f"🔴 *SHORT SIGNAL* ({page+1}/{total})\n"
        f"{'═'*30}\n\n"
        f"📉 *Coin:* `{sig['symbol']}`\n"
        f"⚡ *Confidence:* `{sig['confidence']}%`\n"
        f"📊 *Accuracy Score:* `{sig.get('accuracy_score', sig['confidence'])}%`\n"
        f"📈 *RSI(14):* `{sig['rsi']:.1f}` | *ADX:* `{sig.get('adx', 0):.0f}`\n"
        f"💰 *MFI:* `{sig.get('mfi', 0):.0f}` | *BB%:* `{sig.get('bb_percent', 0):.1f}%`\n"
        f"🔍 *Signals:* `{sig['strength']}` | *Filters:* `{sig.get('strict_filters', 0)}/5`\n\n"
        f"{'─'*30}\n"
        f"💰 *Entry Price:*\n`{sig['entry']:.8f}`\n\n"
        f"🎯 *Take Profit (TP1):*\n`{sig['take_profit_1']:.8f}`\n\n"
    )
    
    if 'take_profit_2' in sig:
        msg += f"🎯 *Take Profit (TP2):*\n`{sig['take_profit_2']:.8f}`\n\n"
    
    msg += (
        f"🛑 *Stop Loss:*\n`{sig['stop_loss']:.8f}`\n\n"
        f"{'─'*30}\n"
        f"💰 *Current Price:* `{sig.get('current_live_price', sig['entry']):.8f}`\n"
        f"{status_line}\n\n"
        f"{'─'*30}\n"
        f"📌 *Reasons:*\n"
    )
    
    # Show top reasons (max 4)
    for i, reason in enumerate(sig['reasons'][:4]):
        msg += f"  {i+1}. {reason}\n"
    
    if len(sig['reasons']) > 4:
        msg += f"  ... +{len(sig['reasons'])-4} more\n"
    
    msg += f"\n⏰ `{sig.get('timestamp', 'N/A')}`\n"
    msg += "⚠️ _100% නිවැරදි නැහැ! Risk Management භාවිතා කරන්න._"

    # Navigation buttons
    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data='short_prev'))
    if page < total - 1:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data='short_next'))
    if nav_row:
        keyboard.append(nav_row)
    
    # Refresh button to update WIN/LOSS % live
    keyboard.append([InlineKeyboardButton("🔄 Refresh WIN%", callback_data='short_refresh')])
    keyboard.append([InlineKeyboardButton("⬅️ BACK", callback_data='menu')])

    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============ EXISTING HANDLERS (modified only with Back buttons) ============

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == 'menu':
        await show_menu(query)
    elif query.data == 'back_to_welcome':
        await back_to_welcome(query)
    elif query.data == 'short_signals_5min':
        context.chat_data['short_signal_page'] = 0
        await show_short_signals_5min(query, context)
    elif query.data == 'short_next':
        context.chat_data['short_signal_page'] = context.chat_data.get('short_signal_page', 0) + 1
        await show_short_signals_5min(query, context)
    elif query.data == 'short_prev':
        context.chat_data['short_signal_page'] = context.chat_data.get('short_signal_page', 0) - 1
        await show_short_signals_5min(query, context)
    elif query.data == 'short_refresh':
        # Just refresh the current view (update WIN/LOSS % without re-analyzing)
        page = context.chat_data.get('short_signal_page', 0)
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


async def show_prices(query):
    """ලයිව් ප්‍රයිස් — Binance Direct REST"""
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


async def show_best_coin(query):
    """හොඳම signal එක"""
    msg = "🔍 *හොඳම කොයින් සොයමින්...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')

    results = []
    for coin in user_coins:
        short = analyzer.find_short_signal(coin)
        if short:
            results.append(('🔴 SHORT', short))
        long = analyzer.find_long_signal(coin)
        if long:
            results.append(('🟢 LONG', long))
        await asyncio.sleep(0.2)

    if not results:
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
        await query.edit_message_text(
            "😴 *දැනට signal එකක් නැහැ*\n\n"
            "Market range එකේ. විනාඩි 2කින් try කරන්න.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    results.sort(key=lambda x: x[1]['confidence'], reverse=True)
    msg = "🏆 *Top Signals (Binance)*\n\n"
    for sig_type, sig in results[:5]:
        msg += (
            f"{sig_type} *{sig['symbol']}*\n"
            f"   Entry: `${sig['entry']:.4f}`\n"
            f"   TP1: `${sig['take_profit_1']:.4f}` | SL: `${sig['stop_loss']:.4f}`\n"
            f"   Confidence: `{sig['confidence']}%` | RSI: `{sig['rsi']:.1f}`\n"
            f"   📌 {', '.join(sig['reasons'][:2])}\n\n"
        )
    msg += "_⚠️ 100% නිවැරදි නැහැ!_"
    keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def show_short_signals(query):
    """SHORT signals"""
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
    """LONG signals"""
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
    """කොයින් සිලෙක්ටර්"""
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
    """කොයින් එක toggle කරන්න"""
    if coin_name in user_coins:
        user_coins.remove(coin_name)
    else:
        user_coins.add(coin_name)
    await show_coin_selector(query)


async def toggle_auto_signal(query):
    """Auto signal toggle"""
    global auto_signal_running
    auto_signal_running = not auto_signal_running
    status = "🟢 ON" if auto_signal_running else "🔴 OFF"
    await query.edit_message_text(
        f"🔄 *Auto Signal: {status}*\n\n"
        "විනාඩි 2කට වරක් signals check වෙනවා.",
        parse_mode='Markdown'
    )


async def show_stats(query):
    """Statistics"""
    # Get actual win rate from analyzer
    win_data = analyzer.get_signal_win_rate()
    
    msg = (
        f"📋 *Bot Statistics*\n\n"
        f"📊 Exchange: *Binance*\n"
        f"👀 Coins: *{len(user_coins)}*\n"
        f"🔄 Auto Signal: {'ON' if auto_signal_running else 'OFF'}\n"
        f"📈 Total Signals: *{len(signal_history)}*\n"
        f"📊 Tracked Signals: *{win_data['total']}*\n"
        f"🏆 Wins: *{win_data['wins']}* | 💀 Losses: *{win_data['losses']}*\n"
        f"🎯 Win Rate: *{win_data['win_rate']}%*\n"
        f"⏰ Last Check: *{datetime.now().strftime('%H:%M:%S')}*\n"
    )
    keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='menu')]]
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def auto_signal_loop():
    """Background auto signal check"""
    global signal_history

    while True:
        if auto_signal_running:
            try:
                logger.info("🔄 Auto signal checking...")

                # Update all tracked signals first
                try:
                    analyzer.update_active_signals()
                except:
                    pass

                for coin in list(user_coins):
                    try:
                        short = analyzer.find_short_signal(coin)
                        if short and short['confidence'] >= 50:
                            signal_history.append(short)
                            
                            # Get live tracking status
                            live = analyzer.get_live_signal_percentage(coin, 'SHORT')
                            win_status = f" | 🟡 {live['win_percentage']}%" if live else ""
                            
                            msg = (
                                f"🚨 *SHORT SIGNAL* 🚨\n\n"
                                f"📉 *{short['symbol']}*\n"
                                f"💰 Entry: `${short['entry']:.4f}`\n"
                                f"🎯 TP1: `${short['take_profit_1']:.4f}`\n"
                                f"🛑 SL: `${short['stop_loss']:.4f}`\n"
                                f"⚡ Confidence: {short['confidence']}%{win_status}\n"
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
