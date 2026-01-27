from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
import logging

# Importar nuevos sistemas avanzados
try:
    from advanced_filters import create_advanced_filter_system
    from multi_timeframe import create_multi_timeframe_analyzer
    ADVANCED_SYSTEMS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Sistemas avanzados no disponibles: {e}")
    ADVANCED_SYSTEMS_AVAILABLE = False

logger = logging.getLogger(__name__)

SYMBOL = "EURUSD"

# simple registry for pluggable rules
RULES = {}

# Instancias globales de sistemas avanzados (si están disponibles)
if ADVANCED_SYSTEMS_AVAILABLE:
    advanced_filter_system = create_advanced_filter_system()
    multi_timeframe_analyzer = create_multi_timeframe_analyzer()
else:
    advanced_filter_system = None
    multi_timeframe_analyzer = None


def register_rule(name: str):
    def _decorator(fn):
        RULES[name.lower()] = fn
        return fn
    return _decorator


@register_rule('ema50_200')
def _ema_strategy(df: pd.DataFrame, config: dict | None = None):
    cfg = config or {}
    expires_minutes = int(cfg.get('expires_minutes', 1))
    span_fast = int(cfg.get('ema_fast', 50))
    span_slow = int(cfg.get('ema_slow', 200))

    df = df.copy()
    df[f'ema{span_fast}'] = df['close'].ewm(span=span_fast).mean()
    df[f'ema{span_slow}'] = df['close'].ewm(span=span_slow).mean()

    last_fast = df[f'ema{span_fast}'].iloc[-1]
    last_slow = df[f'ema{span_slow}'].iloc[-1]
    price = float(df['close'].iloc[-1])

    if last_fast > last_slow:
        sig = {
            'symbol': df.get('symbol', SYMBOL),
            'type': 'BUY',
            'entry': price,
            'sl': price - float(cfg.get('sl_distance', 0.0020)),
            'tp': price + float(cfg.get('tp_distance', 0.0040)),
            'timeframe': None,
            'explanation': f'EMA{span_fast} > EMA{span_slow}',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        }
        logger.debug('EMA rule produced BUY signal: %s', sig)
        return sig, df

    if last_fast < last_slow:
        sig = {
            'symbol': df.get('symbol', SYMBOL),
            'type': 'SELL',
            'entry': price,
            'sl': price + float(cfg.get('sl_distance', 0.0020)),
            'tp': price - float(cfg.get('tp_distance', 0.0040)),
            'timeframe': None,
            'explanation': f'EMA{span_fast} < EMA{span_slow}',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        }
        logger.debug('EMA rule produced SELL signal: %s', sig)
        return sig, df

    return None, df


@register_rule('rsi')
def _rsi_strategy(df: pd.DataFrame, config: dict | None = None):
    cfg = config or {}
    period = int(cfg.get('period', 14))
    lower = float(cfg.get('lower', 30))
    upper = float(cfg.get('upper', 70))
    expires_minutes = int(cfg.get('expires_minutes', 1))

    df = df.copy()
    delta = df['close'].diff()
    up = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    down = -delta.clip(upper=0).ewm(alpha=1/period, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    df['rsi'] = rsi

    last = rsi.iloc[-1]
    price = float(df['close'].iloc[-1])
    if last < lower:
        sig = {
            'symbol': df.get('symbol', SYMBOL),
            'type': 'BUY',
            'entry': price,
            'sl': price - float(cfg.get('sl_distance', 0.0025)),
            'tp': price + float(cfg.get('tp_distance', 0.0050)),
            'timeframe': None,
            'explanation': f'RSI {last:.1f} < {lower}',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        }
        logger.debug('RSI rule produced BUY signal: %s', sig)
        return sig, df
    if last > upper:
        sig = {
            'symbol': df.get('symbol', SYMBOL),
            'type': 'SELL',
            'entry': price,
            'sl': price + float(cfg.get('sl_distance', 0.0025)),
            'tp': price - float(cfg.get('tp_distance', 0.0050)),
            'timeframe': None,
            'explanation': f'RSI {last:.1f} > {upper}',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        }
        logger.debug('RSI rule produced SELL signal: %s', sig)
        return sig, df

    return None, df


@register_rule('macd')
def _macd_strategy(df: pd.DataFrame, config: dict | None = None):
    cfg = config or {}
    fast = int(cfg.get('fast', 12))
    slow = int(cfg.get('slow', 26))
    signal_s = int(cfg.get('signal', 9))
    expires_minutes = int(cfg.get('expires_minutes', 1))

    df = df.copy()
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal_s, adjust=False).mean()
    hist = macd - sig
    df['macd'] = macd
    df['macd_sig'] = sig
    df['macd_hist'] = hist

    # signal when histogram crosses zero
    if hist.iloc[-2] < 0 and hist.iloc[-1] > 0:
        price = float(df['close'].iloc[-1])
        sigd = {
            'symbol': df.get('symbol', SYMBOL),
            'type': 'BUY',
            'entry': price,
            'sl': price - float(cfg.get('sl_distance', 0.0020)),
            'tp': price + float(cfg.get('tp_distance', 0.0040)),
            'timeframe': None,
            'explanation': 'MACD histogram crossed above zero',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        }
        logger.debug('MACD rule produced BUY signal: %s', sigd)
        return sigd, df
    if hist.iloc[-2] > 0 and hist.iloc[-1] < 0:
        price = float(df['close'].iloc[-1])
        sigd = {
            'symbol': df.get('symbol', SYMBOL),
            'type': 'SELL',
            'entry': price,
            'sl': price + float(cfg.get('sl_distance', 0.0020)),
            'tp': price - float(cfg.get('tp_distance', 0.0040)),
            'timeframe': None,
            'explanation': 'MACD histogram crossed below zero',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        }
        logger.debug('MACD rule produced SELL signal: %s', sigd)
        return sigd, df

    return None, df


def detect_signal_advanced(df: pd.DataFrame, strategy: str = 'ema50_200', config: dict | None = None, current_balance: float = 5000.0):
    """
    Versión avanzada de detect_signal con todos los filtros y mejoras
    Returns (signal_dict or None, df_with_indicators, filter_info).
    """
    if df is None or len(df) < 10:
        return None, df, {'error': 'Datos insuficientes'}

    try:
        # 1. Detectar señal básica usando estrategia original
        basic_signal, df_with_indicators = detect_signal(df, strategy, config)
        
        if not basic_signal:
            return None, df_with_indicators, {'basic_signal': False}
        
        # 2. Aplicar filtros avanzados (si están disponibles)
        if ADVANCED_SYSTEMS_AVAILABLE and advanced_filter_system:
            filter_passed, filter_reason, filter_info = advanced_filter_system.apply_all_filters(
                df_with_indicators, basic_signal, current_balance
            )
            
            if not filter_passed:
                logger.info(f"Señal rechazada por filtros avanzados: {filter_reason}")
                return None, df_with_indicators, {
                    'basic_signal': True,
                    'advanced_filters': False,
                    'filter_reason': filter_reason,
                    'filter_info': filter_info
                }
        else:
            # Filtros avanzados no disponibles, usar señal básica
            filter_passed = True
            filter_reason = "Filtros avanzados no disponibles - usando señal básica"
            filter_info = {'warning': 'Advanced filters not available'}
        
        # 3. Validar entrada con M15 (si está disponible)
        symbol = basic_signal.get('symbol', 'EURUSD')
        signal_type = basic_signal.get('type', 'BUY')
        
        if ADVANCED_SYSTEMS_AVAILABLE and multi_timeframe_analyzer:
            m15_valid, m15_reason = multi_timeframe_analyzer.validate_m15_entry(symbol, signal_type)
            
            if not m15_valid:
                logger.info(f"Señal rechazada por análisis M15: {m15_reason}")
                return None, df_with_indicators, {
                    'basic_signal': True,
                    'advanced_filters': filter_passed,
                    'filter_info': filter_info,
                    'm15_validation': False,
                    'm15_reason': m15_reason
                }
        else:
            # M15 no disponible
            m15_valid = True
            m15_reason = "Análisis M15 no disponible - usando señal básica"
        
        # 4. Obtener entrada precisa con M15 (si está habilitado y disponible)
        use_m15_precision = config.get('use_m15_precision', True) if config else True
        
        if ADVANCED_SYSTEMS_AVAILABLE and multi_timeframe_analyzer and use_m15_precision:
            precise_signal, precision_reason = multi_timeframe_analyzer.get_precise_entry(symbol, basic_signal)
            
            if precise_signal:
                # Usar señal precisa
                final_signal = precise_signal
                logger.info(f"Usando entrada precisa M15: {precision_reason}")
            else:
                # Usar señal básica pero con validación M15
                final_signal = basic_signal
                final_signal['m15_precision'] = False
                final_signal['precision_reason'] = precision_reason
                logger.info(f"Usando señal H1 (M15 no disponible): {precision_reason}")
        else:
            final_signal = basic_signal
            final_signal['m15_precision'] = False
            final_signal['precision_reason'] = "M15 precision disabled or not available"
        
        # 5. Añadir información de filtros a la señal
        final_signal['advanced_filters'] = {
            'passed': filter_passed,
            'reason': filter_reason,
            'confluence_score': filter_info.get('confluence', {}).get('score', 0) if isinstance(filter_info, dict) else 0,
            'risk_multiplier': filter_info.get('drawdown', {}).get('risk_multiplier', 1.0) if isinstance(filter_info, dict) else 1.0
        }
        
        final_signal['m15_validation'] = {
            'passed': m15_valid,
            'reason': m15_reason
        }
        
        # 6. Ajustar confianza basada en filtros
        if ADVANCED_SYSTEMS_AVAILABLE:
            confluence_score = filter_info.get('confluence', {}).get('score', 0) if isinstance(filter_info, dict) else 0
            if confluence_score >= 5:
                final_signal['confidence'] = 'VERY_HIGH'
            elif confluence_score >= 4:
                final_signal['confidence'] = 'HIGH'
            else:
                final_signal['confidence'] = 'MEDIUM'
        else:
            final_signal['confidence'] = 'MEDIUM'  # Default cuando no hay filtros avanzados
        
        return final_signal, df_with_indicators, {
            'basic_signal': True,
            'advanced_filters': filter_passed,
            'filter_info': filter_info,
            'm15_validation': m15_valid,
            'm15_reason': m15_reason,
            'final_confidence': final_signal['confidence'],
            'systems_available': ADVANCED_SYSTEMS_AVAILABLE
        }
        
    except Exception as e:
        logger.exception(f'Error in detect_signal_advanced: {e}')
        return None, df, {'error': str(e)}


def detect_signal(df: pd.DataFrame, strategy: str = 'ema50_200', config: dict | None = None):
    """Dispatch to a registered rule. Returns (signal_dict or None, df_with_indicators).

    `strategy` can be the rule name registered via `register_rule`. `config` is a
    dict with strategy-specific parameters.
    """
    if df is None or len(df) < 10:
        return None, df

    strat = (strategy or 'ema50_200').lower()
    fn = RULES.get(strat)
    if fn is None:
        # try simple aliases
        if strat.startswith('ema'):
            fn = RULES.get('ema50_200')
        elif strat.startswith('rsi'):
            fn = RULES.get('rsi')
        elif strat.startswith('macd'):
            fn = RULES.get('macd')

    if fn is None:
        logger.debug('No registered rule found for %s; returning no signal', strat)
        return None, df

    try:
        sig, df2 = fn(df, config=config)
        logger.debug('Rule %s returned signal: %s', strat, bool(sig))
        return sig, df2
    except Exception:
        logger.exception('Error executing strategy %s', strat)
        return None, df


# -----------------------------
# Per-symbol composite rules
# -----------------------------


def _sma(series: pd.Series, window: int):
    return series.rolling(window).mean()


def _ema(series: pd.Series, span: int):
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14):
    delta = series.diff()
    up = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    down = -delta.clip(upper=0).ewm(alpha=1/period, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd_indicators(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return macd, sig, hist


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    # Basic ADX implementation
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    plus_di = 100 * (_sma(pd.Series(plus_dm), period) / atr.replace(0, np.nan))
    minus_di = 100 * (_sma(pd.Series(minus_dm), period) / atr.replace(0, np.nan))
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.rolling(period).mean()
    return adx


@register_rule('eurusd')
def rule_eurusd(df: pd.DataFrame, config: dict | None = None):
    """Composite EURUSD rule: trend filter (EMA200 H1), pullback (EMA20/50), RSI and candle confirmation."""
    cfg = config or {}
    df = df.copy()
    # indicators
    df['ema200'] = _ema(df['close'], int(cfg.get('ema200', 200)))
    df['ema50'] = _ema(df['close'], int(cfg.get('ema50', 50)))
    df['ema20'] = _ema(df['close'], int(cfg.get('ema20', 20)))
    df['rsi'] = _rsi(df['close'], int(cfg.get('rsi_period', 14)))

    last = df.iloc[-1]
    price = float(last['close'])
    ema200 = float(last['ema200'])

    # Trend filter
    if price > ema200:
        allowed = 'BUY'
    elif price < ema200:
        allowed = 'SELL'
    else:
        return None, df

    # Pullback control: price near EMA20 or EMA50
    near20 = abs(price - float(last['ema20'])) <= (float(last['ema20']) * float(cfg.get('pullback_tol_pct', 0.002)))
    near50 = abs(price - float(last['ema50'])) <= (float(last['ema50']) * float(cfg.get('pullback_tol_pct', 0.002)))
    if not (near20 or near50):
        return None, df

    # RSI windows
    r = float(last['rsi'])
    if allowed == 'BUY' and not (float(cfg.get('rsi_buy_low', 40)) <= r <= float(cfg.get('rsi_buy_high', 50))):
        return None, df
    if allowed == 'SELL' and not (float(cfg.get('rsi_sell_low', 50)) <= r <= float(cfg.get('rsi_sell_high', 60))):
        return None, df

    # Simple candle confirmation: last candle body in direction and larger than previous small candle
    if len(df) < 3:
        return None, df
    c1 = df['close'].iloc[-2] - df['open'].iloc[-2]
    c2 = df['close'].iloc[-1] - df['open'].iloc[-1]
    if allowed == 'BUY' and not (c2 > 0 and abs(c2) > abs(c1) * float(cfg.get('candle_body_mult', 0.8))):
        return None, df
    if allowed == 'SELL' and not (c2 < 0 and abs(c2) > abs(c1) * float(cfg.get('candle_body_mult', 0.8))):
        return None, df

    # Estimate SL/TP simple: SL at ema20/50 whichever closer, TP as 1.5R
    sl_distance = float(cfg.get('sl_distance', 0.0020))
    tp_distance = float(cfg.get('tp_distance', 0.0030))
    if allowed == 'BUY':
        sl = price - sl_distance
        tp = price + tp_distance
    else:
        sl = price + sl_distance
        tp = price - tp_distance

    # minimal RR check (1.5R)
    risk = abs(price - sl)
    reward = abs(tp - price)
    if risk == 0 or reward / risk < float(cfg.get('min_rr', 1.5)):
        return None, df

    sig = {
        'symbol': df.get('symbol', 'EURUSD'),
        'type': allowed,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'timeframe': cfg.get('timeframe', 'H1'),
        'explanation': f'EURUSD trend {allowed}, pullback ok, RSI {r:.1f}',
        'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 10)))
    }
    return sig, df


@register_rule('xauusd')
def rule_xauusd(df: pd.DataFrame, config: dict | None = None):
    cfg = config or {}
    df = df.copy()
    # indicators
    macd, macd_sig, macd_hist = _macd_indicators(df['close'], int(cfg.get('fast', 12)), int(cfg.get('slow', 26)), int(cfg.get('signal', 9)))
    df['macd'] = macd
    df['macd_sig'] = macd_sig
    df['macd_hist'] = macd_hist
    df['rsi'] = _rsi(df['close'], int(cfg.get('rsi_period', 14)))

    last = df.iloc[-1]
    price = float(last['close'])

    # Zone check: near previous day high/low
    if 'prev_day_high' in cfg and 'prev_day_low' in cfg:
        pdh = float(cfg['prev_day_high'])
        pdl = float(cfg['prev_day_low'])
        zone_ok = abs(price - pdh) <= float(cfg.get('zone_tol', 2.0)) or abs(price - pdl) <= float(cfg.get('zone_tol', 2.0))
    else:
        # fallback: require price not too far from day's extremes in df
        day_high = df['high'].max()
        day_low = df['low'].min()
        zone_ok = abs(price - day_high) <= (abs(day_high) * 0.005) or abs(price - day_low) <= (abs(day_low) * 0.005)

    if not zone_ok:
        return None, df

    # Momentum: MACD histogram crossing and magnitude
    if len(df) < 3:
        return None, df
    if not (macd_hist.iloc[-2] < 0 and macd_hist.iloc[-1] > 0) and not (macd_hist.iloc[-2] > 0 and macd_hist.iloc[-1] < 0):
        return None, df

    # candle range check
    avg_range = (df['high'] - df['low']).rolling(20).mean().iloc[-1]
    last_range = last['high'] - last['low']
    if last_range < avg_range * float(cfg.get('range_mult', 1.0)):
        return None, df

    r = float(last['rsi'])
    if r > float(cfg.get('rsi_high', 70)) or r < float(cfg.get('rsi_low', 30)):
        return None, df

    # signal type based on macd_hist crossing
    if macd_hist.iloc[-2] < 0 and macd_hist.iloc[-1] > 0:
        typ = 'BUY'
    else:
        typ = 'SELL'

    # SL and TP wider
    sl_dist = float(cfg.get('sl_distance', 0.5))
    tp_dist = float(cfg.get('tp_distance', 1.0))
    if typ == 'BUY':
        sl = price - sl_dist
        tp = price + tp_dist
    else:
        sl = price + sl_dist
        tp = price - tp_dist

    sig = {
        'symbol': df.get('symbol', 'XAUUSD'),
        'type': typ,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'timeframe': cfg.get('timeframe', 'M15'),
        'explanation': f'XAUUSD MACD crossover, range {last_range:.4f}',
        'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 15)))
    }
    return sig, df


@register_rule('btcusdt')
def rule_btcusdt(df: pd.DataFrame, config: dict | None = None):
    cfg = config or {}
    df = df.copy()
    df['ema50'] = _ema(df['close'], int(cfg.get('ema50', 50)))
    df['ema200'] = _ema(df['close'], int(cfg.get('ema200', 200)))
    df['rsi'] = _rsi(df['close'], int(cfg.get('rsi_period', 14)))
    adx = _adx(df['high'], df['low'], df['close'], int(cfg.get('adx_period', 14)))
    df['adx'] = adx

    last = df.iloc[-1]
    price = float(last['close'])

    # Avoid range: ADX or ema separation
    adx_val = float(last['adx']) if not np.isnan(last['adx']) else 0.0
    ema_sep = abs(float(last['ema50']) - float(last['ema200'])) / price
    if not (adx_val >= float(cfg.get('adx_thresh', 20)) or ema_sep > float(cfg.get('ema_sep_thresh', 0.01))):
        return None, df

    # Breakout: price beyond recent swing high/low
    recent_high = df['high'].rolling(20).max().iloc[-2]
    recent_low = df['low'].rolling(20).min().iloc[-2]
    vol = df.get('tick_volume') if 'tick_volume' in df.columns else df.get('volume')
    vol_ma = vol.rolling(20).mean().iloc[-1] if vol is not None else None

    typ = None
    if price > recent_high and (vol_ma is None or float(df['close'].iloc[-1]) and (vol.iloc[-1] > vol_ma)) and float(df['rsi'].iloc[-1]) > 50:
        typ = 'BUY'
    if price < recent_low and (vol_ma is None or float(df['close'].iloc[-1]) and (vol.iloc[-1] > vol_ma)) and float(df['rsi'].iloc[-1]) < 50:
        typ = 'SELL'

    if typ is None:
        return None, df

    # SL at last swing
    if typ == 'BUY':
        sl = recent_low
        tp = None
    else:
        sl = recent_high
        tp = None

    sig = {
        # allow config to override reported symbol (use broker symbol like BTCEUR)
        'symbol': cfg.get('symbol', df.get('symbol', 'BTCEUR')),
        'type': typ,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'timeframe': cfg.get('timeframe', 'H1'),
        'explanation': f'BTC breakout {typ}, ADX {adx_val:.1f}',
        'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 60)))
    }
    return sig, df


@register_rule('breakout_confirmation')
def breakout_confirmation_strategy(df: pd.DataFrame, config: dict | None = None):
    """
    Estrategia de breakout con múltiples confirmaciones
    - Breakout de rango consolidado
    - Volumen aumentado
    - RSI en zona neutral
    - Confirmación con vela siguiente
    """
    cfg = config or {}
    df = df.copy()
    
    # Parámetros configurables
    lookback_period = int(cfg.get('lookback_period', 20))
    volume_multiplier = float(cfg.get('volume_multiplier', 1.5))
    rsi_min = float(cfg.get('rsi_min', 40))
    rsi_max = float(cfg.get('rsi_max', 60))
    min_range_pips = float(cfg.get('min_range_pips', 15))
    
    if len(df) < lookback_period + 5:
        return None, df
    
    # Calcular indicadores
    df['rsi'] = _rsi(df['close'], 14)
    df['atr'] = (df['high'] - df['low']).rolling(14).mean()
    
    # Identificar rango de consolidación
    recent_high = df['high'].rolling(lookback_period).max().iloc[-2]
    recent_low = df['low'].rolling(lookback_period).min().iloc[-2]
    range_size = recent_high - recent_low
    
    # Verificar que el rango sea significativo
    avg_atr = df['atr'].iloc[-5:].mean()
    if range_size < avg_atr * min_range_pips:
        return None, df
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    
    # Verificar volumen (si está disponible)
    volume_ok = True
    if 'tick_volume' in df.columns:
        avg_volume = df['tick_volume'].rolling(20).mean().iloc[-2]
        current_volume = last['tick_volume']
        volume_ok = current_volume > avg_volume * volume_multiplier
    
    # RSI en zona neutral
    rsi_ok = rsi_min <= last['rsi'] <= rsi_max
    
    # Breakout alcista
    if (price > recent_high and 
        last['close'] > last['open'] and  # Vela verde
        volume_ok and rsi_ok and
        last['high'] > prev['high']):  # Nuevo máximo
        
        sl_distance = float(cfg.get('sl_distance', range_size * 0.5))
        tp_distance = float(cfg.get('tp_distance', range_size * 1.5))
        
        signal = {
            'symbol': df.get('symbol', 'EURUSD'),
            'type': 'BUY',
            'entry': price,
            'sl': price - sl_distance,
            'tp': price + tp_distance,
            'explanation': f'Breakout alcista confirmado, rango: {range_size:.5f}',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 30)))
        }
        return signal, df
    
    # Breakout bajista
    if (price < recent_low and 
        last['close'] < last['open'] and  # Vela roja
        volume_ok and rsi_ok and
        last['low'] < prev['low']):  # Nuevo mínimo
        
        sl_distance = float(cfg.get('sl_distance', range_size * 0.5))
        tp_distance = float(cfg.get('tp_distance', range_size * 1.5))
        
        signal = {
            'symbol': df.get('symbol', 'EURUSD'),
            'type': 'SELL',
            'entry': price,
            'sl': price + sl_distance,
            'tp': price - tp_distance,
            'explanation': f'Breakout bajista confirmado, rango: {range_size:.5f}',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 30)))
        }
        return signal, df
    
    return None, df


@register_rule('scalping_ema')
def scalping_ema_strategy(df: pd.DataFrame, config: dict | None = None):
    """
    Estrategia de scalping con EMAs rápidas
    - EMA 8/21 para señales rápidas
    - Confirmación con momentum
    - SL ajustado y TP rápido
    """
    cfg = config or {}
    df = df.copy()
    
    # EMAs rápidas para scalping
    df['ema8'] = df['close'].ewm(span=8).mean()
    df['ema21'] = df['close'].ewm(span=21).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    
    # MACD para momentum
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    if len(df) < 50:
        return None, df
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    
    # Tendencia general (EMA50)
    trend_up = price > last['ema50']
    trend_down = price < last['ema50']
    
    # Señal de compra: EMA8 cruza por encima de EMA21 + momentum positivo
    if (trend_up and 
        last['ema8'] > last['ema21'] and 
        prev['ema8'] <= prev['ema21'] and  # Cruce reciente
        last['macd_hist'] > 0 and
        last['close'] > last['open']):  # Vela verde
        
        sl_distance = float(cfg.get('sl_distance', 0.0008))  # 8 pips
        tp_distance = float(cfg.get('tp_distance', 0.0015))  # 15 pips
        
        signal = {
            'symbol': df.get('symbol', 'EURUSD'),
            'type': 'BUY',
            'entry': price,
            'sl': price - sl_distance,
            'tp': price + tp_distance,
            'explanation': 'Scalping: EMA8/21 cruce alcista + momentum',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 10)))
        }
        return signal, df
    
    # Señal de venta: EMA8 cruza por debajo de EMA21 + momentum negativo
    if (trend_down and 
        last['ema8'] < last['ema21'] and 
        prev['ema8'] >= prev['ema21'] and  # Cruce reciente
        last['macd_hist'] < 0 and
        last['close'] < last['open']):  # Vela roja
        
        sl_distance = float(cfg.get('sl_distance', 0.0008))  # 8 pips
        tp_distance = float(cfg.get('tp_distance', 0.0015))  # 15 pips
        
        signal = {
            'symbol': df.get('symbol', 'EURUSD'),
            'type': 'SELL',
            'entry': price,
            'sl': price + sl_distance,
            'tp': price - tp_distance,
            'explanation': 'Scalping: EMA8/21 cruce bajista + momentum',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 10)))
        }
        return signal, df
    
    return None, df


@register_rule('mean_reversion')
def mean_reversion_strategy(df: pd.DataFrame, config: dict | None = None):
    """
    Estrategia de reversión a la media
    - Precio se aleja mucho de EMAs
    - RSI en extremos
    - Bollinger Bands para confirmación
    """
    cfg = config or {}
    df = df.copy()
    
    # Indicadores
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['rsi'] = _rsi(df['close'], 14)
    
    # Bollinger Bands
    bb_period = int(cfg.get('bb_period', 20))
    bb_std = float(cfg.get('bb_std', 2.0))
    df['bb_middle'] = df['close'].rolling(bb_period).mean()
    bb_std_val = df['close'].rolling(bb_period).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std_val * bb_std)
    df['bb_lower'] = df['bb_middle'] - (bb_std_val * bb_std)
    
    if len(df) < bb_period + 5:
        return None, df
    
    last = df.iloc[-1]
    price = float(last['close'])
    
    # Parámetros
    rsi_oversold = float(cfg.get('rsi_oversold', 25))
    rsi_overbought = float(cfg.get('rsi_overbought', 75))
    
    # Señal de compra: precio cerca del BB inferior + RSI oversold
    if (price <= last['bb_lower'] and 
        last['rsi'] <= rsi_oversold and
        last['close'] > last['open']):  # Vela de reversión
        
        sl_distance = abs(price - last['bb_lower']) * 1.5
        tp_distance = abs(last['bb_middle'] - price) * 0.8
        
        signal = {
            'symbol': df.get('symbol', 'EURUSD'),
            'type': 'BUY',
            'entry': price,
            'sl': price - sl_distance,
            'tp': price + tp_distance,
            'explanation': f'Reversión alcista: RSI {last["rsi"]:.1f}, BB inferior',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 20)))
        }
        return signal, df
    
    # Señal de venta: precio cerca del BB superior + RSI overbought
    if (price >= last['bb_upper'] and 
        last['rsi'] >= rsi_overbought and
        last['close'] < last['open']):  # Vela de reversión
        
        sl_distance = abs(last['bb_upper'] - price) * 1.5
        tp_distance = abs(price - last['bb_middle']) * 0.8
        
        signal = {
            'symbol': df.get('symbol', 'EURUSD'),
            'type': 'SELL',
            'entry': price,
            'sl': price + sl_distance,
            'tp': price - tp_distance,
            'explanation': f'Reversión bajista: RSI {last["rsi"]:.1f}, BB superior',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 20)))
        }
        return signal, df
    
    return None, df


@register_rule('eurusd_advanced')
def eurusd_advanced_strategy(df: pd.DataFrame, config: dict | None = None):
    """
    Estrategia EURUSD: Breakout 20 períodos + EMA50/EMA200 filtro + RSI >50/<50
    Implementación exacta según especificaciones del README
    """
    cfg = config or {}
    df = df.copy()
    
    # Verificar datos suficientes
    if len(df) < 200:
        return None, df
    
    # Indicadores requeridos
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()
    df['rsi'] = _rsi(df['close'], 14)
    
    # Breakout de 20 períodos
    df['high_20'] = df['high'].rolling(20).max()
    df['low_20'] = df['low'].rolling(20).min()
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    
    # Señal de compra: Breakout alcista + filtros
    if (price > last['high_20'] and  # Breakout alcista de 20 períodos
        last['ema50'] > last['ema200'] and  # EMA50 > EMA200 (tendencia alcista)
        last['rsi'] > 50):  # RSI > 50
        
        # Calcular niveles
        atr_value = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
        sl_distance = atr_value * 1.5
        tp_distance = sl_distance * 2.0
        
        signal = {
            'symbol': 'EURUSD',
            'type': 'BUY',
            'entry': price,
            'sl': price - sl_distance,
            'tp': price + tp_distance,
            'explanation': f'EURUSD: Breakout alcista 20P + EMA50>EMA200 + RSI>50 ({last["rsi"]:.1f})',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 45))),
            'confidence': 'HIGH' if last['rsi'] > 60 else 'MEDIUM',
            'strategy': 'eurusd_advanced'
        }
        return signal, df
    
    # Señal de venta: Breakout bajista + filtros
    if (price < last['low_20'] and  # Breakout bajista de 20 períodos
        last['ema50'] < last['ema200'] and  # EMA50 < EMA200 (tendencia bajista)
        last['rsi'] < 50):  # RSI < 50
        
        # Calcular niveles
        atr_value = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
        sl_distance = atr_value * 1.5
        tp_distance = sl_distance * 2.0
        
        signal = {
            'symbol': 'EURUSD',
            'type': 'SELL',
            'entry': price,
            'sl': price + sl_distance,
            'tp': price - tp_distance,
            'explanation': f'EURUSD: Breakout bajista 20P + EMA50<EMA200 + RSI<50 ({last["rsi"]:.1f})',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 45))),
            'confidence': 'HIGH' if last['rsi'] < 40 else 'MEDIUM',
            'strategy': 'eurusd_advanced'
        }
        return signal, df
    
    return None, df


@register_rule('xauusd_advanced')
def xauusd_advanced_strategy(df: pd.DataFrame, config: dict | None = None):
    """
    Estrategia XAUUSD: Reversión psicológica ±8-10$ del nivel + EMA50/EMA200 + Mecha ≥30%
    Implementación exacta según especificaciones del README
    """
    cfg = config or {}
    df = df.copy()
    
    # Verificar datos suficientes
    if len(df) < 200:
        return None, df
    
    # Indicadores requeridos
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()
    
    # Niveles psicológicos del oro (cada $50)
    psychological_levels = cfg.get('psychological_levels', [1900, 1950, 2000, 2050, 2100, 2150])
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    
    # Calcular tamaño de mecha
    candle_range = last['high'] - last['low']
    upper_wick = last['high'] - max(last['open'], last['close'])
    lower_wick = min(last['open'], last['close']) - last['low']
    upper_wick_pct = (upper_wick / candle_range) * 100 if candle_range > 0 else 0
    lower_wick_pct = (lower_wick / candle_range) * 100 if candle_range > 0 else 0
    
    # Encontrar el nivel psicológico más cercano
    closest_level = min(psychological_levels, key=lambda x: abs(price - x))
    distance_to_level = abs(price - closest_level)
    
    # Señal de compra: Reversión alcista cerca de nivel psicológico
    if (distance_to_level <= 10 and  # ±8-10$ del nivel psicológico
        price < closest_level and  # Precio por debajo del nivel (para reversión alcista)
        last['ema50'] > last['ema200'] and  # EMA50 > EMA200 (tendencia alcista)
        lower_wick_pct >= 30 and  # Mecha inferior ≥30%
        last['close'] > last['open']):  # Vela alcista de reversión
        
        # Niveles fijos para oro
        sl_distance = 12.0  # $12 SL
        tp_distance = 24.0  # $24 TP
        
        signal = {
            'symbol': 'XAUUSD',
            'type': 'BUY',
            'entry': price,
            'sl': price - sl_distance,
            'tp': price + tp_distance,
            'explanation': f'XAUUSD: Reversión alcista ${distance_to_level:.1f} del nivel ${closest_level}, mecha {lower_wick_pct:.1f}%',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 60))),
            'confidence': 'HIGH' if distance_to_level <= 5 else 'MEDIUM',
            'strategy': 'xauusd_advanced'
        }
        return signal, df
    
    # Señal de venta: Reversión bajista cerca de nivel psicológico
    if (distance_to_level <= 10 and  # ±8-10$ del nivel psicológico
        price > closest_level and  # Precio por encima del nivel (para reversión bajista)
        last['ema50'] < last['ema200'] and  # EMA50 < EMA200 (tendencia bajista)
        upper_wick_pct >= 30 and  # Mecha superior ≥30%
        last['close'] < last['open']):  # Vela bajista de reversión
        
        # Niveles fijos para oro
        sl_distance = 12.0  # $12 SL
        tp_distance = 24.0  # $24 TP
        
        signal = {
            'symbol': 'XAUUSD',
            'type': 'SELL',
            'entry': price,
            'sl': price + sl_distance,
            'tp': price - tp_distance,
            'explanation': f'XAUUSD: Reversión bajista ${distance_to_level:.1f} del nivel ${closest_level}, mecha {upper_wick_pct:.1f}%',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 60))),
            'confidence': 'HIGH' if distance_to_level <= 5 else 'MEDIUM',
            'strategy': 'xauusd_advanced'
        }
        return signal, df
    
    return None, df


@register_rule('btceur_advanced')
def btceur_advanced_strategy(df: pd.DataFrame, config: dict | None = None):
    """
    Estrategia BTCEUR: EMA12/26 cross + EMA50 filtro + RSI direccional
    Implementación exacta según especificaciones del README
    """
    cfg = config or {}
    df = df.copy()
    
    # Verificar datos suficientes
    if len(df) < 50:
        return None, df
    
    # Indicadores requeridos
    df['ema12'] = df['close'].ewm(span=12).mean()
    df['ema26'] = df['close'].ewm(span=26).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['rsi'] = _rsi(df['close'], 14)
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    
    # Señal de compra: EMA12/26 cross alcista + filtros
    if (last['ema12'] > last['ema26'] and  # Cross alcista EMA12 > EMA26
        prev['ema12'] <= prev['ema26'] and  # Cross reciente
        last['ema12'] > last['ema50'] and  # EMA12 > EMA50 (filtro de tendencia)
        last['rsi'] > 50):  # RSI direccional alcista
        
        # Calcular niveles
        atr_value = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
        sl_distance = atr_value * 2.5
        tp_distance = sl_distance * 2.5
        
        signal = {
            'symbol': 'BTCEUR',
            'type': 'BUY',
            'entry': price,
            'sl': price - sl_distance,
            'tp': price + tp_distance,
            'explanation': f'BTCEUR: Cross alcista EMA12/26 + EMA50 filtro + RSI direccional ({last["rsi"]:.1f})',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 90))),
            'confidence': 'HIGH' if last['rsi'] > 60 else 'MEDIUM',
            'strategy': 'btceur_advanced'
        }
        return signal, df
    
    # Señal de venta: EMA12/26 cross bajista + filtros
    if (last['ema12'] < last['ema26'] and  # Cross bajista EMA12 < EMA26
        prev['ema12'] >= prev['ema26'] and  # Cross reciente
        last['ema12'] < last['ema50'] and  # EMA12 < EMA50 (filtro de tendencia)
        last['rsi'] < 50):  # RSI direccional bajista
        
        # Calcular niveles
        atr_value = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
        sl_distance = atr_value * 2.5
        tp_distance = sl_distance * 2.5
        
        signal = {
            'symbol': 'BTCEUR',
            'type': 'SELL',
            'entry': price,
            'sl': price + sl_distance,
            'tp': price - tp_distance,
            'explanation': f'BTCEUR: Cross bajista EMA12/26 + EMA50 filtro + RSI direccional ({last["rsi"]:.1f})',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 90))),
            'confidence': 'HIGH' if last['rsi'] < 40 else 'MEDIUM',
            'strategy': 'btceur_advanced'
        }
        return signal, df
    
    return None, df
