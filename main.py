import asyncio
import logging
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


# ============ HANDLERS ============

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("📊 Live Prices", callback_data='prices')],
        [InlineKeyboardButton("🎯 Best Coin Now", callback_data='best_coin')],
        [InlineKeyboardButton("🔴 Short Signals", callback_data='short_signals')],
        [InlineKeyboardButton("🟢 Long Signals", callback_data='long_signals')],
        [InlineKeyboardButton("⚙️ Select Coins", callback_data='select_coins')],
        [InlineKeyboardButton("🔄 Auto Signal", callback_data='toggle_auto')],
        [InlineKeyboardButton("📋 Stats", callback_data='stats')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🤖 *SHANA Signal Bot* 🚀\n\n"
        "📊 *Binance Live Analysis*\n"
        "⏱ විනාඩි 2ට වරක් Auto Signals\n"
        f"📈 Monitoring {len(user_coins)} coins\n\n"
        "⚠️ *Risk Warning:* 100% guarantee නැහැ!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == 'prices':
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

    keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data='refresh_prices')]]
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
        await query.edit_message_text(
            "😴 *දැනට signal එකක් නැහැ*\n\n"
            "Market range එකේ. විනාඩි 2කින් try කරන්න.",
            parse_mode='Markdown'
        )
        return

    results.sort(key=lambda x: x[1]['confidence'], reverse=True)
    msg = "🏆 *Top Signals (Binance)*\n\n"
    for sig_type, sig in results[:5]:
        msg += (
            f"{sig_type} *{sig['symbol']}*\n"
            f"   Entry: `${sig['entry']:.4f}`\n"
            f"   TP1: `${sig['take_profit_1']:.4f}` | SL: `${sig['stop_loss']:.4f}`\n"
            f"   Confidence: {sig['confidence']}% | RSI: {sig['rsi']:.1f}\n"
            f"   📌 {', '.join(sig['reasons'][:2])}\n\n"
        )
    msg += "_⚠️ 100% නිවැරදි නැහැ!_"
    await query.edit_message_text(msg, parse_mode='Markdown')


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
    msg = (
        f"📋 *Bot Statistics*\n\n"
        f"📊 Exchange: *Binance*\n"
        f"👀 Coins: *{len(user_coins)}*\n"
        f"🔄 Auto Signal: {'ON' if auto_signal_running else 'OFF'}\n"
        f"📈 Total Signals: *{len(signal_history)}*\n"
        f"⏰ Last Check: *{datetime.now().strftime('%H:%M:%S')}*\n"
    )
    await query.edit_message_text(msg, parse_mode='Markdown')


async def auto_signal_loop():
    """Background auto signal check"""
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
