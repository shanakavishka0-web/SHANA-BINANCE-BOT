def calculate_indicators(self, df):
        """ටෙක්නිකල් ඉන්ඩිකේටර්ස් — 100% FULL ANALYSIS"""
        # ===== TREND INDICATORS =====
        df['sma_7'] = ta.trend.sma_indicator(df['close'], window=7)
        df['sma_25'] = ta.trend.sma_indicator(df['close'], window=25)
        df['sma_50'] = ta.trend.sma_indicator(df['close'], window=50)
        df['sma_99'] = ta.trend.sma_indicator(df['close'], window=99)
        df['sma_200'] = ta.trend.sma_indicator(df['close'], window=200)
        df['ema_5'] = ta.trend.ema_indicator(df['close'], window=5)
        df['ema_12'] = ta.trend.ema_indicator(df['close'], window=12)
        df['ema_26'] = ta.trend.ema_indicator(df['close'], window=26)
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=50)
        df['ema_200'] = ta.trend.ema_indicator(df['close'], window=200)
        
        # ===== MOMENTUM INDICATORS =====
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        df['rsi_6'] = ta.momentum.rsi(df['close'], window=6)  # Fast RSI
        
        # Williams %R
        df['williams_r'] = ta.momentum.williams_r(df['high'], df['low'], df['close'], lbp=14)
        
        # Awesome Oscillator
        df['ao'] = ta.momentum.awesome_oscillator(df['high'], df['low'], window1=5, window2=34)
        
        # KAMA (Kaufman's Adaptive Moving Average)
        df['kama'] = ta.momentum.kama(df['close'], window=30, pow1=2, pow2=30)
        
        # ROC (Rate of Change)
        df['roc'] = ta.momentum.roc(df['close'], window=12)
        
        # TSV / MFI (Money Flow Index)
        df['mfi'] = ta.volume.money_flow_index(df['high'], df['low'], df['close'], df['volume'], window=14)
        
        # Ease of Movement
        df['eom'] = ta.volume.ease_of_movement(df['high'], df['low'], df['volume'], window=14)
        
        # ===== MACD (FULL) =====
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        # MACD Extra
        df['macd_histogram'] = df['macd_diff']
        
        # ===== BOLLINGER BANDS (3 LEVELS) =====
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle'] * 100
        df['bb_percent'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower']) * 100
        
        # Bollinger Bands 1.5 deviation (tighter)
        bb_15 = ta.volatility.BollingerBands(df['close'], window=20, window_dev=1.5)
        df['bb_upper_15'] = bb_15.bollinger_hband()
        df['bb_lower_15'] = bb_15.bollinger_lband()
        
        # ===== VOLUME INDICATORS =====
        df['volume_sma_5'] = ta.trend.sma_indicator(df['volume'], window=5)
        df['volume_sma_10'] = ta.trend.sma_indicator(df['volume'], window=10)
        df['volume_sma_20'] = ta.trend.sma_indicator(df['volume'], window=20)
        df['volume_ratio_5'] = df['volume'] / df['volume_sma_5']
        df['volume_ratio_10'] = df['volume'] / df['volume_sma_10']
        df['volume_ratio_20'] = df['volume'] / df['volume_sma_20']
        
        # OBV (On-Balance Volume)
        df['obv'] = ta.volume.on_balance_volume(df['close'], df['volume'])
        df['obv_sma'] = ta.trend.sma_indicator(df['obv'], window=20)
        df['obv_divergence'] = df['obv'] - df['obv_sma']
        
        # Volume Price Trend
        df['vpt'] = ta.volume.volume_price_trend(df['close'], df['volume'])
        
        # ===== STOCHASTIC (FULL) =====
        stoch = ta.momentum.StochRSIIndicator(df['close'], window=14, smooth1=3, smooth2=3)
        df['stoch_k'] = stoch.stochrsi_k()
        df['stoch_d'] = stoch.stochrsi_d()
        
        # Regular Stochastic
        df['stoch_k_reg'] = ta.momentum.stoch(df['high'], df['low'], df['close'], window=14, smooth_window=3)
        df['stoch_d_reg'] = ta.momentum.stoch_signal(df['high'], df['low'], df['close'], window=14, smooth_window=3)
        
        # ===== VOLATILITY =====
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['atr_percent'] = df['atr'] / df['close'] * 100
        
        # Keltner Channels
        df['kc_middle'] = ta.trend.ema_indicator(df['close'], window=20)
        df['kc_upper'] = df['kc_middle'] + (df['atr'] * 1.5)
        df['kc_lower'] = df['kc_middle'] - (df['atr'] * 1.5)
        
        # ===== PATTERN / PRICE ACTION =====
        df['resistance'] = df['high'].rolling(window=20).max()
        df['support'] = df['low'].rolling(window=20).min()
        df['resistance_50'] = df['high'].rolling(window=50).max()  # Stronger resistance
        df['support_50'] = df['low'].rolling(window=50).min()      # Stronger support
        
        # Candlestick body/wick analysis
        df['body'] = abs(df['close'] - df['open'])
        df['upper_wick'] = df['high'] - df[['close', 'open']].max(axis=1)
        df['lower_wick'] = df[['close', 'open']].min(axis=1) - df['low']
        df['body_percent'] = df['body'] / (df['high'] - df['low']) * 100
        df['upper_wick_percent'] = df['upper_wick'] / (df['high'] - df['low']) * 100
        df['lower_wick_percent'] = df['lower_wick'] / (df['high'] - df['low']) * 100
        
        df['is_bullish'] = df['close'] > df['open']
        df['is_bearish'] = df['close'] < df['open']
        df['is_doji'] = df['body'] < ((df['high'] - df['low']) * 0.1)
        
        # ===== TREND STRENGTH =====
        # ADX
        df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
        df['plus_di'] = ta.trend.adx_pos(df['high'], df['low'], df['close'], window=14)
        df['minus_di'] = ta.trend.adx_neg(df['high'], df['low'], df['close'], window=14)
        
        # ===== FIXED: AROON (high, low, close ඔක්කොම pass කරන්න ඕනේ!) =====
        df['aroon_up'] = ta.trend.aroon_up(df['high'], df['low'], df['close'], window=25)
        df['aroon_down'] = ta.trend.aroon_down(df['high'], df['low'], df['close'], window=25)
        
        # Ichimoku Cloud
        df['ichimoku_a'] = ta.trend.ichimoku_a(df['high'], df['low'], window1=9, window2=26)
        df['ichimoku_b'] = ta.trend.ichimoku_b(df['high'], df['low'], window2=26, window3=52)
        
        # PSAR
        df['psar'] = ta.trend.psar_indicator(df['high'], df['low'], df['close'], step=0.02, max_step=0.2)
        
        # ===== DIVERGENCE DETECTION =====
        df['price_higher_high'] = (df['high'] > df['high'].shift(1)) & (df['high'].shift(1) > df['high'].shift(2))
        df['price_lower_low'] = (df['low'] < df['low'].shift(1)) & (df['low'].shift(1) < df['low'].shift(2))
        df['rsi_higher_high'] = (df['rsi'] > df['rsi'].shift(1)) & (df['rsi'].shift(1) > df['rsi'].shift(2))
        df['rsi_lower_low'] = (df['rsi'] < df['rsi'].shift(1)) & (df['rsi'].shift(1) < df['rsi'].shift(2))
        
        # Bearish divergence: price higher high, RSI lower high
        df['bearish_div_rsi'] = df['price_higher_high'] & ~df['rsi_higher_high']
        
        return df
