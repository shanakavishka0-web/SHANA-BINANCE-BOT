import pandas as pd
import numpy as np
import ta
from binance.client import Client
from binance.exceptions import BinanceAPIException
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BinanceAnalyzer:
    def __init__(self, api_key, secret_key):
        self.client = Client(api_key, secret_key)
        
    def get_klines(self, symbol, interval="1m", limit=100):
        """බයිනැන්ස් එකෙන් ලයිව් ක්ලයින් ඩේටා ගන්න"""
        try:
            klines = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
            ])
            
            # නියම data types වලට හරවන්න
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
            
        except BinanceAPIException as e:
            logger.error(f"API Error for {symbol}: {e}")
            return None
            
    def calculate_indicators(self, df):
        """ටෙක්නිකල් ඉන්ඩිකේටර්ස් ගණනය කරන්න"""
        
        # SMA (Simple Moving Average)
        df['sma_7'] = ta.trend.sma_indicator(df['close'], window=7)
        df['sma_25'] = ta.trend.sma_indicator(df['close'], window=25)
        df['sma_99'] = ta.trend.sma_indicator(df['close'], window=99)
        
        # EMA (Exponential Moving Average)
        df['ema_12'] = ta.trend.ema_indicator(df['close'], window=12)
        df['ema_26'] = ta.trend.ema_indicator(df['close'], window=26)
        
        # RSI (Relative Strength Index)
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        
        # MACD
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = df['bb_upper'] - df['bb_lower']
        
        # Volume Analysis
        df['volume_sma_20'] = ta.trend.sma_indicator(df['volume'], window=20)
        df['volume_ratio'] = df['volume'] / df['volume_sma_20']
        
        # Stochastic RSI
        stoch = ta.momentum.StochRSIIndicator(df['close'], window=14, smooth1=3, smooth2=3)
        df['stoch_k'] = stoch.stochrsi_k()
        df['stoch_d'] = stoch.stochrsi_d()
        
        # ATR (Average True Range) - volatility measure
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        
        # Support & Resistance (සරලව)
        df['resistance'] = df['high'].rolling(window=20).max()
        df['support'] = df['low'].rolling(window=20).min()
        
        # Price Action
        df['body'] = abs(df['close'] - df['open'])
        df['upper_wick'] = df['high'] - df[['close', 'open']].max(axis=1)
        df['lower_wick'] = df[['close', 'open']].min(axis=1) - df['low']
        df['is_bullish'] = df['close'] > df['open']
        
        return df
    
    def find_short_signal(self, symbol):
        """SHORT සිග්නල් හොයන්න (Bearish setup)"""
        
        df = self.get_klines(symbol, "1m", 100)
        if df is None or len(df) < 50:
            return None
            
        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        signals = []
        confidence = 0
        
        # ---- Condition 1: RSI Overbought (>70) ----
        if latest['rsi'] > RSI_OVERBOUGHT:
            signals.append(f"RSI Overbought: {latest['rsi']:.1f}")
            confidence += 20
            
        # ---- Condition 2: Price below EMA 12 & 26 (Bearish cross) ----
        if latest['close'] < latest['ema_12'] and prev['close'] >= prev['ema_12']:
            signals.append("Price broke below EMA-12")
            confidence += 15
            
        if latest['close'] < latest['ema_26']:
            signals.append("Price below EMA-26")
            confidence += 10
            
        # ---- Condition 3: MACD Bearish Crossover ----
        if latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            signals.append("MACD Bearish Crossover")
            confidence += 20
            
        # ---- Condition 4: Price hit upper Bollinger Band ----
        if latest['close'] >= latest['bb_upper'] * 0.98:
            signals.append("Near Upper Bollinger Band")
            confidence += 10
            
        # ---- Condition 5: Volume spike confirmation ----
        if latest['volume_ratio'] > VOLUME_THRESHOLD and not latest['is_bullish']:
            signals.append(f"High Volume Sell: {latest['volume_ratio']:.1f}x")
            confidence += 15
            
        # ---- Condition 6: Bearish candlestick pattern (Doji/Hammer top) ----
        if latest['upper_wick'] > latest['body'] * 2 and not latest['is_bullish']:
            signals.append("Bearish rejection wick")
            confidence += 10
            
        # ---- Condition 7: Stochastic RSI overbought ----
        if latest['stoch_k'] > 80 and latest['stoch_d'] > 80:
            signals.append("StochRSI Overbought")
            confidence += 10
            
        # ---- Condition 8: Price near resistance ----
        if latest['close'] >= latest['resistance'] * 0.98:
            signals.append("Near Resistance level")
            confidence += 10
            
        # ---- Condition 9: Bearish engulfing pattern ----
        if (not latest['is_bullish'] and prev['is_bullish'] and 
            latest['close'] < prev['open'] and latest['open'] > prev['close']):
            signals.append("Bearish Engulfing")
            confidence += 15
        
        # අවම වශයෙන් කන්ඩිෂන් 4ක් හම්බුනොත් සහ confidence 50+ නම්
        if len(signals) >= 4 and confidence >= 50:
            # Take Profit & Stop Loss levels (ATR basis)
            atr = latest['atr']
            entry_price = latest['close']
            
            return {
                'symbol': symbol,
                'signal': 'SHORT',
                'entry': entry_price,
                'take_profit_1': entry_price - (atr * 1.5),  # TP1
                'take_profit_2': entry_price - (atr * 3.0),  # TP2
                'stop_loss': entry_price + (atr * 2.0),      # SL
                'confidence': confidence,
                'strength': len(signals),
                'reasons': signals,
                'rsi': latest['rsi'],
                'volume_ratio': latest['volume_ratio'],
                'timestamp': datetime.now().isoformat()
            }
            
        return None

    def find_long_signal(self, symbol):
        """LONG සිග්නල් හොයන්න (Bullish setup)"""
        
        df = self.get_klines(symbol, "1m", 100)
        if df is None or len(df) < 50:
            return None
            
        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        signals = []
        confidence = 0
        
        # Condition 1: RSI Oversold
        if latest['rsi'] < RSI_OVERSOLD:
            signals.append(f"RSI Oversold: {latest['rsi']:.1f}")
            confidence += 20
            
        # Condition 2: Price above EMA 12
        if latest['close'] > latest['ema_12'] and prev['close'] <= prev['ema_12']:
            signals.append("Price broke above EMA-12")
            confidence += 15
            
        # Condition 3: MACD Bullish Crossover
        if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            signals.append("MACD Bullish Crossover")
            confidence += 20
            
        # Condition 4: Price near lower Bollinger Band
        if latest['close'] <= latest['bb_lower'] * 1.02:
            signals.append("Near Lower Bollinger Band")
            confidence += 10
            
        # Condition 5: Volume spike up
        if latest['volume_ratio'] > VOLUME_THRESHOLD and latest['is_bullish']:
            signals.append(f"High Volume Buy: {latest['volume_ratio']:.1f}x")
            confidence += 15
            
        if len(signals) >= 3 and confidence >= 40:
            atr = latest['atr']
            entry_price = latest['close']
            
            return {
                'symbol': symbol,
                'signal': 'LONG',
                'entry': entry_price,
                'take_profit_1': entry_price + (atr * 1.5),
                'take_profit_2': entry_price + (atr * 3.0),
                'stop_loss': entry_price - (atr * 2.0),
                'confidence': confidence,
                'strength': len(signals),
                'reasons': signals,
                'rsi': latest['rsi'],
                'volume_ratio': latest['volume_ratio'],
                'timestamp': datetime.now().isoformat()
            }
            
        return None
