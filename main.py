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

# Global variables
analyzer = BinanceAnalyzer()
bot = Bot(token=TELEGRAM_BOT_TOKEN)
user_coins = set(COINS)  # default all coins
signal_history = []

# =========== ටෙලිග්‍රෑම් කමාන්ඩ්ස් ===========

async def start(update, context):
    """බොට් ස්ටාර්ට් කරන විට පෙන්වන මෙනුව"""
    keyboard = [
        [InlineKeyboardButton("📊 Live Prices", callback_data='prices')],
        [InlineKeyboardButton("🎯 Best Coin Now", callback_data='best_coin')],
        [InlineKeyboardButton("📈 Short Signals", callback_data='short_signals')],
        [InlineKeyboardButton("📉 Long Signals", callback_data='long_signals')],
        [InlineKeyboardButton("⚙️ Select Coins", callback_data='select_coins')],
        [InlineKeyboardButton("🔄 Auto Signal ON/OFF", callback_data='toggle_auto')],
        [InlineKeyboardButton("📋 Stats", callback_data='stats')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 *SHANA Signal Bot*\n\n"
        "බයිනැන්ස් ලයිව් මාර්කට් ඇනලයිසිස්\n"
        "විනාඩි 2කට වරක් Auto Signals\n\n"
        "✅ උපදෙස: 100% guarantee නැහැ — Risk Management අනිවාර්යයෙන් පාවිච්චි කරන්න!",
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

async def show_prices(query):
    """ලයිව් ප්‍රයිස් පෙන්වන්න"""
    msg = "📊 *ලයිව් ප්‍රයිස්සෙස්*\n\n"
    
    for coin in list(user_coins)[:10]:  # max 10 coins show
        try:
            ticker = analyzer.client.get_symbol_ticker(symbol=coin)
            price = float(ticker['price'])
            
            # 24h change
            klines = analyzer.get_klines(coin, "1d", 2)
            if klines is not None:
                change = ((price - klines['close'].iloc[-2]) / klines['close'].iloc[-2]) * 100
                emoji = "🟢" if change > 0 else "🔴"
                msg += f"{emoji} *{coin}*: `${price:.4f}` ({change:+.2f}%)\n"
            else:
                msg += f"💠 *{coin}*: `${price:.4f}`\n"
        except Exception as e:
            msg += f"❌ {coin}: Error\n"
    
    keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data='refresh_prices')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=reply_markup)

async def show_best_coin(query):
    """හොඳම කොයින් එක හොයලා පෙන්වන්න"""
    msg = "🔍 *හොඳම කොයින් සොයමින්...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')
    
    results = []
    for coin in user_coins:
        # Short signal check
        short_sig = analyzer.find_short_signal(coin)
        if short_sig:
            results.append(('SHORT', short_sig))
            
        # Long signal check
        long_sig = analyzer.find_long_signal(coin)
        if long_sig:
            results.append(('LONG', long_sig))
    
    if not results:
        await query.edit_message_text(
            "😴 දැනට හොඳ signal එකක් නැහැ.\n\n"
            "විනාඩි 2කින් නැවත උත්සහ කරන්න.",
            parse_mode='Markdown'
        )
        return
    
    # Sort by confidence
    results.sort(key=lambda x: x[1]['confidence'], reverse=True)
    
    msg = "🏆 *Top Signals:*\n\n"
    for i, (sig_type, sig) in enumerate(results[:5]):
        emoji = "🔴" if sig_type == "SHORT" else "🟢"
        msg += f"{emoji} *{sig['symbol']}* — {sig_type}\n"
        msg += f"   Entry: `${sig['entry']:.4f}`\n"
        msg += f"   TP: `${sig['take_profit_1']:.4f}` | SL: `${sig['stop_loss']:.4f}`\n"
        msg += f"   Confidence: {sig['confidence']}% | RSI: {sig['rsi']:.1f}\n"
        msg += f"   📌 {', '.join(sig['reasons'][:2])}\n\n"
    
    msg += "_⚠️ 100% guarantee නැහැ. Risk management පාවිච්චි කරන්න._"
    
    await query.edit_message_text(msg, parse_mode='Markdown')

async def show_short_signals(query):
    """SHORT සිග්නල්ස් පෙන්වන්න"""
    msg = "🔍 *SHORT Signals සොයමින්...*\n\n"
    await query.edit_message_text(msg, parse_mode='Markdown')
    
    signals = []
    for coin in user_coins:
        sig = analyzer.find_short_signal(coin)
        if sig:
            signals.append(sig)
    
    if not signals:
        await query.edit_message_text(
            "✅ දැනට SHORT signal එකක් නැහැ.\n"
            "විනාඩි 2කින් නැවත උත්සහ කරන්න.",
            parse_mode='Markdown'
        )
        return
    
    signals.sort(key=lambda x: x['confidence'], reverse=True)
    
    msg = "🔴 *SHORT Signals Found:* `{}`\n\n".format(len(signals))
    for sig in signals[:5]:
        msg += f"📉 *{sig['symbol']}*\n"
        msg += f"   Entry: `${sig['entry']:.4f}`\n"
        msg += f"   🎯 TP1: `${sig['take_profit_1']:.4f}`\n"
        msg += f"   🎯 TP2: `${sig['take_profit_2']:.4f}`\n"
        msg += f"   🛑 SL: `${sig['stop_loss']:.4f}`\n"
        msg += f"   ⚡ Confidence: {sig['confidence']}%\n"
        msg += f"   📌 {', '.join(sig['reasons'][:3])}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data='short_signals')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=reply_markup)

async def auto_signal_loop():
    """සෑම විනාඩි 2කට වරක් Auto Signal check"""
    while True:
        try:
            logger.info("🔄 Auto signal check running...")
            
            for coin in list(user_coins):
                # SHORT check
                short_sig = analyzer.find_short_signal(coin)
                if short_sig and short_sig['confidence'] >= 50:
                    signal_history.append(short_sig)
                    
                    msg = (
                        f"🚨 *SHORT SIGNAL* 🚨\n\n"
                        f"📉 *{short_sig['symbol']}*\n"
                        f"💰 Entry: `${short_sig['entry']:.4f}`\n"
                        f"🎯 TP1: `${short_sig['take_profit_1']:.4f}`\n"
                        f"🎯 TP2: `${short_sig['take_profit_2']:.4f}`\n"
                        f"🛑 SL: `${short_sig['stop_loss']:.4f}`\n"
                        f"⚡ Confidence: {short_sig['confidence']}%\n"
                        f"📊 RSI: {short_sig['rsi']:.1f}\n"
                        f"📌 {', '.join(short_sig['reasons'][:3])}\n\n"
                        f"⏰ {short_sig['timestamp']}"
                    )
                    
                    await bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=msg,
                        parse_mode='Markdown'
                    )
                
                # LONG check
                long_sig = analyzer.find_long_signal(coin)
                if long_sig and long_sig['confidence'] >= 40:
                    signal_history.append(long_sig)
                    
                    msg = (
                        f"🟢 *LONG SIGNAL* 🟢\n\n"
                        f"📈 *{long_sig['symbol']}*\n"
                        f"💰 Entry: `${long_sig['entry']:.4f}`\n"
                        f"🎯 TP1: `${long_sig['take_profit_1']:.4f}`\n"
                        f"🎯 TP2: `${long_sig['take_profit_2']:.4f}`\n"
                        f"🛑 SL: `${long_sig['stop_loss']:.4f}`\n"
                        f"⚡ Confidence: {long_sig['confidence']}%\n"
                        f"📊 RSI: {long_sig['rsi']:.1f}\n"
                        f"📌 {', '.join(long_sig['reasons'][:3])}\n\n"
                        f"⏰ {long_sig['timestamp']}"
                    )
                    
                    await bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=msg,
                        parse_mode='Markdown'
                    )
            
            # Keep only last 100 signals
            if len(signal_history) > 100:
                signal_history[:] = signal_history[-100:]
                
        except Exception as e:
            logger.error(f"Auto signal error: {e}")
            
        await asyncio.sleep(ANALYSIS_INTERVAL)  # විනාඩි 2

# =========== Main ===========
def main():
    """බොට් ප්‍රධාන function එක"""
    
    # Application හදන්න
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Auto signal loop එක background එකේ start කරන්න
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(auto_signal_loop())
    
    # Bot start
    logger.info("🤖 SHANA Signal Bot started!")
    app.run_polling(allowed_updates=['message', 'callback_query'])

if __name__ == "__main__":
    main()
