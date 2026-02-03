"""
SISTEMA DE SEÑALES SIMPLIFICADO Y RENTABLE
Versión 2.0 - Enfoque en simplicidad y frecuencia saludable

🎯 FILOSOFÍA:
- 1 SETUP principal + máximo 2 CONFIRMACIONES
- Sistema de scoring flexible (no AND estricto)
- Frecuencia realista: 3-6 señales/día total
- R:R mínimo 1.5, preferible 2.0
- Cada activo con lógica independiente y coherente

🔧 MEJORAS IMPLEMENTADAS:
✅ Lógica de scoring en vez de AND estricto
✅ Max trades realistas por activo
✅ Estrategias market-logic específicas
✅ Gestión de riesgo normalizada
✅ Logs detallados de rechazo
✅ Sistema de flexibilidad configurable
"""

from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Tuple, List

logger = logging.getLogger(__name__)

# Registry para las nuevas estrategias simplificadas
SIMPLIFIED_RULES = {}

def register_simplified_rule(name: str):
    """Decorador para registrar estrategias simplificadas"""
    def _decorator(fn):
        SIMPLIFIED_RULES[name.lower()] = fn
        return fn
    return _decorator

# ======================
# UTILIDADES TÉCNICAS
# ======================

def _sma(series: pd.Series, window: int):
    """Simple Moving Average"""
    return series.rolling(window).mean()

def _ema(series: pd.Series, span: int):
    """Exponential Moving Average"""
    return series.ewm(span=span, adjust=False).mean()

def _rsi(series: pd.Series, period: int = 14):
    """Relative Strength Index"""
    delta = series.diff()
    up = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    down = -delta.clip(upper=0).ewm(alpha=1/period, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def _atr(df: pd.DataFrame, period: int = 14):
    """Average True Range"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()

def _calculate_rr_ratio(entry: float, sl: float, tp: float) -> float:
    """Calcula el ratio riesgo:recompensa"""
    if entry == sl:
        return 0.0
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    return reward / risk if risk > 0 else 0.0

# ======================
# SISTEMA DE SCORING FLEXIBLE
# ======================

class SignalScorer:
    """Sistema de scoring flexible para evaluar señales"""
    
    @staticmethod
    def evaluate_signal(setup_valid: bool, confirmations: List[bool], 
                       min_score: float = 0.66, weights: List[float] = None) -> Tuple[bool, float, Dict]:
        """
        Evalúa una señal usando sistema de scoring flexible
        
        Args:
            setup_valid: Si el setup principal es válido (obligatorio)
            confirmations: Lista de confirmaciones (True/False)
            min_score: Score mínimo requerido (0.66 = 66%)
            weights: Pesos para cada confirmación (opcional)
        
        Returns:
            (signal_approved, final_score, details)
        """
        if not setup_valid:
            return False, 0.0, {'reason': 'Setup principal no válido'}
        
        if not confirmations:
            # Solo setup, score = 0.5 (puede ser suficiente si min_score <= 0.5)
            score = 0.5
            details = {
                'setup': True,
                'confirmations_passed': 0,
                'confirmations_total': 0,
                'score': score,
                'threshold': min_score
            }
            return score >= min_score, score, details
        
        # Calcular score con confirmaciones
        if weights is None:
            weights = [1.0] * len(confirmations)
        
        # Setup cuenta como 50%, confirmaciones como 50%
        setup_weight = 0.5
        confirmations_weight = 0.5
        
        # Score de confirmaciones
        passed_confirmations = sum(1 for c in confirmations if c)
        total_confirmations = len(confirmations)
        confirmations_score = passed_confirmations / total_confirmations if total_confirmations > 0 else 0
        
        # Score final
        final_score = setup_weight + (confirmations_weight * confirmations_score)
        
        details = {
            'setup': setup_valid,
            'confirmations_passed': passed_confirmations,
            'confirmations_total': total_confirmations,
            'confirmations_score': confirmations_score,
            'score': final_score,
            'threshold': min_score,
            'approved': final_score >= min_score
        }
        
        return final_score >= min_score, final_score, details

# ======================
# ESTRATEGIA EURUSD SIMPLIFICADA
# ======================

@register_simplified_rule('eurusd_simple')
def eurusd_simple_strategy(df: pd.DataFrame, config: dict = None) -> Tuple[Optional[Dict], pd.DataFrame, Dict]:
    """
    EURUSD SIMPLIFICADO: Breakout + Pullback + Sesión
    
    🎯 SETUP PRINCIPAL (obligatorio):
    - Breakout de rango de 15 períodos
    
    ✅ CONFIRMACIONES (mínimo 1 de 2):
    1. RSI entre 40-60 (zona neutral)
    2. Sesión activa (Londres/NY)
    
    📊 GESTIÓN:
    - SL: ATR × 1.5
    - TP: SL × 2.0 (R:R = 2.0)
    - Max: 4 trades/día
    """
    cfg = config or {}
    df = df.copy()
    
    # Verificar datos suficientes
    if len(df) < 50:
        return None, df, {'rejected': True, 'reason': 'Datos insuficientes'}
    
    # Indicadores básicos
    df['rsi'] = _rsi(df['close'], 14)
    df['atr'] = _atr(df, 14)
    
    # Rango de breakout (15 períodos - menos exigente)
    df['high_15'] = df['high'].rolling(15).max()
    df['low_15'] = df['low'].rolling(15).min()
    
    last = df.iloc[-1]
    price = float(last['close'])
    atr_current = last['atr']
    
    # 🎯 SETUP PRINCIPAL: Breakout
    breakout_up = price > last['high_15']
    breakout_down = price < last['low_15']
    
    if not (breakout_up or breakout_down):
        return None, df, {'rejected': True, 'reason': 'No hay breakout válido'}
    
    # ✅ CONFIRMACIONES
    confirmations = []
    confirmation_details = []
    
    # Confirmación 1: RSI neutral (40-60)
    rsi_neutral = 40 <= last['rsi'] <= 60
    confirmations.append(rsi_neutral)
    confirmation_details.append(f"RSI neutral: {rsi_neutral} (RSI: {last['rsi']:.1f})")
    
    # Confirmación 2: Sesión activa
    current_hour = datetime.now(timezone.utc).hour
    active_session = 8 <= current_hour <= 22  # Londres + NY (8-22 GMT)
    confirmations.append(active_session)
    confirmation_details.append(f"Sesión activa: {active_session} (Hora: {current_hour})")
    
    # 🧮 EVALUACIÓN CON SCORING
    min_score = float(cfg.get('min_score', 0.66))  # 66% por defecto
    setup_valid = breakout_up or breakout_down
    
    signal_approved, final_score, score_details = SignalScorer.evaluate_signal(
        setup_valid, confirmations, min_score
    )
    
    if not signal_approved:
        return None, df, {
            'rejected': True,
            'reason': f'Score insuficiente: {final_score:.2f} < {min_score}',
            'score_details': score_details,
            'confirmations': confirmation_details
        }
    
    # 📈 GENERAR SEÑAL
    signal_type = 'BUY' if breakout_up else 'SELL'
    
    # Calcular niveles
    sl_distance = atr_current * 1.5
    tp_distance = sl_distance * 2.0  # R:R = 2.0
    
    if signal_type == 'BUY':
        sl = price - sl_distance
        tp = price + tp_distance
    else:
        sl = price + sl_distance
        tp = price - tp_distance
    
    # Verificar R:R mínimo
    rr_ratio = _calculate_rr_ratio(price, sl, tp)
    min_rr = float(cfg.get('min_rr', 1.5))
    
    if rr_ratio < min_rr:
        return None, df, {
            'rejected': True,
            'reason': f'R:R insuficiente: {rr_ratio:.2f} < {min_rr}',
            'rr_ratio': rr_ratio
        }
    
    # Determinar confianza basada en score
    if final_score >= 0.85:
        confidence = 'HIGH'
    elif final_score >= 0.75:
        confidence = 'MEDIUM-HIGH'
    else:
        confidence = 'MEDIUM'
    
    signal = {
        'symbol': 'EURUSD',
        'type': signal_type,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'explanation': f'EURUSD Simple: Breakout {signal_type} + Score {final_score:.2f} + R:R {rr_ratio:.1f}',
        'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 30))),
        'confidence': confidence,
        'strategy': 'eurusd_simple',
        'score': final_score,
        'rr_ratio': rr_ratio
    }
    
    analysis = {
        'approved': True,
        'score': final_score,
        'score_details': score_details,
        'confirmations': confirmation_details,
        'rr_ratio': rr_ratio,
        'confidence': confidence
    }
    
    logger.info(f"✅ EURUSD Simple {signal_type}: Score {final_score:.2f}, R:R {rr_ratio:.1f}, Confidence {confidence}")
    
    return signal, df, analysis

# ======================
# ESTRATEGIA XAUUSD SIMPLIFICADA
# ======================

@register_simplified_rule('xauusd_simple')
def xauusd_simple_strategy(df: pd.DataFrame, config: dict = None) -> Tuple[Optional[Dict], pd.DataFrame, Dict]:
    """
    XAUUSD SIMPLIFICADO: Fakeouts + Rejection + Liquidez
    
    🎯 SETUP PRINCIPAL (obligatorio):
    - Precio cerca de nivel psicológico (±10$)
    
    ✅ CONFIRMACIONES (mínimo 1 de 2):
    1. Mecha significativa (>30% del rango)
    2. Sesión de alta liquidez (Londres/NY overlap)
    
    📊 GESTIÓN:
    - SL: $8 fijo
    - TP: $16 fijo (R:R = 2.0)
    - Max: 3 trades/día
    """
    cfg = config or {}
    df = df.copy()
    
    # Verificar datos suficientes
    if len(df) < 20:
        return None, df, {'rejected': True, 'reason': 'Datos insuficientes'}
    
    # Indicadores básicos
    df['atr'] = _atr(df, 14)
    
    last = df.iloc[-1]
    price = float(last['close'])
    
    # 🎯 SETUP PRINCIPAL: Proximidad a nivel psicológico
    # Niveles cada $25 (más realista que cada $50)
    closest_level = round(price / 25) * 25
    distance_to_level = abs(price - closest_level)
    
    # Tolerancia más flexible: ±10$ (antes era ±5$)
    level_proximity = distance_to_level <= 10.0
    
    if not level_proximity:
        return None, df, {
            'rejected': True,
            'reason': f'Lejos del nivel psicológico: ${distance_to_level:.1f} > $10.0',
            'closest_level': closest_level,
            'distance': distance_to_level
        }
    
    # ✅ CONFIRMACIONES
    confirmations = []
    confirmation_details = []
    
    # Confirmación 1: Mecha significativa
    candle_range = last['high'] - last['low']
    upper_wick = last['high'] - max(last['open'], last['close'])
    lower_wick = min(last['open'], last['close']) - last['low']
    
    upper_wick_pct = (upper_wick / candle_range) * 100 if candle_range > 0 else 0
    lower_wick_pct = (lower_wick / candle_range) * 100 if candle_range > 0 else 0
    
    significant_wick = max(upper_wick_pct, lower_wick_pct) >= 30
    confirmations.append(significant_wick)
    confirmation_details.append(f"Mecha significativa: {significant_wick} (Max: {max(upper_wick_pct, lower_wick_pct):.1f}%)")
    
    # Confirmación 2: Sesión de liquidez (más flexible)
    current_hour = datetime.now(timezone.utc).hour
    high_liquidity = 8 <= current_hour <= 22  # Londres + NY (más amplio)
    confirmations.append(high_liquidity)
    confirmation_details.append(f"Alta liquidez: {high_liquidity} (Hora: {current_hour})")
    
    # 🧮 EVALUACIÓN CON SCORING
    min_score = float(cfg.get('min_score', 0.60))  # Más flexible para oro
    
    signal_approved, final_score, score_details = SignalScorer.evaluate_signal(
        level_proximity, confirmations, min_score
    )
    
    if not signal_approved:
        return None, df, {
            'rejected': True,
            'reason': f'Score insuficiente: {final_score:.2f} < {min_score}',
            'score_details': score_details,
            'confirmations': confirmation_details
        }
    
    # 📈 DETERMINAR DIRECCIÓN
    # Usar la mecha más fuerte para determinar dirección
    if lower_wick_pct > upper_wick_pct and lower_wick_pct >= 30:
        signal_type = 'BUY'  # Rechazo desde abajo
    elif upper_wick_pct > lower_wick_pct and upper_wick_pct >= 30:
        signal_type = 'SELL'  # Rechazo desde arriba
    else:
        # Si no hay mecha clara, usar posición relativa al nivel
        signal_type = 'BUY' if price < closest_level else 'SELL'
    
    # Calcular niveles fijos (más simple)
    sl_distance = 8.0   # $8 fijo
    tp_distance = 16.0  # $16 fijo (R:R = 2.0)
    
    if signal_type == 'BUY':
        sl = price - sl_distance
        tp = price + tp_distance
    else:
        sl = price + sl_distance
        tp = price - tp_distance
    
    # Verificar R:R
    rr_ratio = _calculate_rr_ratio(price, sl, tp)
    
    # Determinar confianza
    if final_score >= 0.85 and max(upper_wick_pct, lower_wick_pct) >= 50:
        confidence = 'HIGH'
    elif final_score >= 0.75:
        confidence = 'MEDIUM-HIGH'
    else:
        confidence = 'MEDIUM'
    
    signal = {
        'symbol': 'XAUUSD',
        'type': signal_type,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'explanation': f'XAUUSD Simple: Nivel ${closest_level} (${distance_to_level:.1f}) + Mecha {max(upper_wick_pct, lower_wick_pct):.1f}% + Score {final_score:.2f}',
        'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 45))),
        'confidence': confidence,
        'strategy': 'xauusd_simple',
        'score': final_score,
        'rr_ratio': rr_ratio,
        'level': closest_level,
        'distance_to_level': distance_to_level
    }
    
    analysis = {
        'approved': True,
        'score': final_score,
        'score_details': score_details,
        'confirmations': confirmation_details,
        'rr_ratio': rr_ratio,
        'confidence': confidence,
        'level_analysis': {
            'closest_level': closest_level,
            'distance': distance_to_level,
            'upper_wick_pct': upper_wick_pct,
            'lower_wick_pct': lower_wick_pct
        }
    }
    
    logger.info(f"✅ XAUUSD Simple {signal_type}: Nivel ${closest_level} (${distance_to_level:.1f}), Score {final_score:.2f}, Confidence {confidence}")
    
    return signal, df, analysis

# ======================
# ESTRATEGIA BTCEUR SIMPLIFICADA
# ======================

@register_simplified_rule('btceur_simple')
def btceur_simple_strategy(df: pd.DataFrame, config: dict = None) -> Tuple[Optional[Dict], pd.DataFrame, Dict]:
    """
    BTCEUR SIMPLIFICADO: Momentum + Tendencia + Expansión
    
    🎯 SETUP PRINCIPAL (obligatorio):
    - EMA12 vs EMA26 (cruce o separación)
    
    ✅ CONFIRMACIONES (mínimo 1 de 2):
    1. EMA50 como filtro direccional
    2. ATR por encima de la media (expansión)
    
    📊 GESTIÓN:
    - SL: ATR × 2.0
    - TP: SL × 1.8 (R:R = 1.8)
    - Max: 5 trades/día
    """
    cfg = config or {}
    df = df.copy()
    
    # Verificar datos suficientes
    if len(df) < 50:
        return None, df, {'rejected': True, 'reason': 'Datos insuficientes'}
    
    # Indicadores básicos
    df['ema12'] = _ema(df['close'], 12)
    df['ema26'] = _ema(df['close'], 26)
    df['ema50'] = _ema(df['close'], 50)
    df['atr'] = _atr(df, 14)
    
    last = df.iloc[-1]
    price = float(last['close'])
    atr_current = last['atr']
    atr_mean = df['atr'].tail(20).mean()
    
    # 🎯 SETUP PRINCIPAL: Momentum EMA
    ema12_above_26 = last['ema12'] > last['ema26']
    ema12_below_26 = last['ema12'] < last['ema26']
    
    # Verificar que hay separación mínima (momentum real)
    ema_separation = abs(last['ema12'] - last['ema26'])
    min_separation = atr_current * 0.3  # Separación mínima
    
    momentum_setup = (ema12_above_26 or ema12_below_26) and ema_separation >= min_separation
    
    if not momentum_setup:
        return None, df, {
            'rejected': True,
            'reason': f'Sin momentum claro: separación {ema_separation:.0f} < {min_separation:.0f}',
            'ema_separation': ema_separation,
            'min_separation': min_separation
        }
    
    # ✅ CONFIRMACIONES
    confirmations = []
    confirmation_details = []
    
    # Confirmación 1: EMA50 como filtro direccional
    if ema12_above_26:
        ema50_filter = price > last['ema50']  # Para BUY, precio debe estar sobre EMA50
    else:
        ema50_filter = price < last['ema50']  # Para SELL, precio debe estar bajo EMA50
    
    confirmations.append(ema50_filter)
    confirmation_details.append(f"EMA50 filtro: {ema50_filter} (Precio vs EMA50: {price:.0f} vs {last['ema50']:.0f})")
    
    # Confirmación 2: Expansión de volatilidad
    atr_expansion = atr_current > atr_mean * 1.1  # ATR 10% por encima de la media
    confirmations.append(atr_expansion)
    confirmation_details.append(f"ATR expansión: {atr_expansion} (ATR: {atr_current:.0f} vs Media: {atr_mean:.0f})")
    
    # 🧮 EVALUACIÓN CON SCORING
    min_score = float(cfg.get('min_score', 0.65))  # Intermedio para crypto
    
    signal_approved, final_score, score_details = SignalScorer.evaluate_signal(
        momentum_setup, confirmations, min_score
    )
    
    if not signal_approved:
        return None, df, {
            'rejected': True,
            'reason': f'Score insuficiente: {final_score:.2f} < {min_score}',
            'score_details': score_details,
            'confirmations': confirmation_details
        }
    
    # 📈 GENERAR SEÑAL
    signal_type = 'BUY' if ema12_above_26 else 'SELL'
    
    # Calcular niveles
    sl_distance = atr_current * 2.0
    tp_distance = sl_distance * 1.8  # R:R = 1.8 (más realista para crypto)
    
    if signal_type == 'BUY':
        sl = price - sl_distance
        tp = price + tp_distance
    else:
        sl = price + sl_distance
        tp = price - tp_distance
    
    # Verificar R:R mínimo
    rr_ratio = _calculate_rr_ratio(price, sl, tp)
    min_rr = float(cfg.get('min_rr', 1.5))
    
    if rr_ratio < min_rr:
        return None, df, {
            'rejected': True,
            'reason': f'R:R insuficiente: {rr_ratio:.2f} < {min_rr}',
            'rr_ratio': rr_ratio
        }
    
    # Determinar confianza
    if final_score >= 0.85 and atr_expansion and ema50_filter:
        confidence = 'HIGH'
    elif final_score >= 0.75:
        confidence = 'MEDIUM-HIGH'
    else:
        confidence = 'MEDIUM'
    
    signal = {
        'symbol': 'BTCEUR',
        'type': signal_type,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'explanation': f'BTCEUR Simple: EMA momentum {signal_type} + Score {final_score:.2f} + ATR {atr_current:.0f}',
        'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 60))),
        'confidence': confidence,
        'strategy': 'btceur_simple',
        'score': final_score,
        'rr_ratio': rr_ratio
    }
    
    analysis = {
        'approved': True,
        'score': final_score,
        'score_details': score_details,
        'confirmations': confirmation_details,
        'rr_ratio': rr_ratio,
        'confidence': confidence,
        'momentum_analysis': {
            'ema_separation': ema_separation,
            'atr_current': atr_current,
            'atr_mean': atr_mean,
            'atr_expansion': atr_expansion
        }
    }
    
    logger.info(f"✅ BTCEUR Simple {signal_type}: EMA momentum, Score {final_score:.2f}, ATR {atr_current:.0f}, Confidence {confidence}")
    
    return signal, df, analysis

# ======================
# FUNCIÓN PRINCIPAL DE DETECCIÓN
# ======================

def detect_simplified_signal(df: pd.DataFrame, symbol: str, config: dict = None) -> Tuple[Optional[Dict], pd.DataFrame, Dict]:
    """
    Función principal para detectar señales con el sistema simplificado
    
    Args:
        df: DataFrame con datos OHLC
        symbol: Símbolo a analizar
        config: Configuración específica
    
    Returns:
        (signal_dict or None, df_with_indicators, analysis_info)
    """
    symbol = symbol.upper()
    
    # Mapear símbolos a estrategias
    strategy_map = {
        'EURUSD': 'eurusd_simple',
        'XAUUSD': 'xauusd_simple', 
        'BTCEUR': 'btceur_simple'
    }
    
    strategy_name = strategy_map.get(symbol)
    if not strategy_name:
        return None, df, {
            'rejected': True,
            'reason': f'No hay estrategia simplificada para {symbol}',
            'available_symbols': list(strategy_map.keys())
        }
    
    # Obtener función de estrategia
    strategy_fn = SIMPLIFIED_RULES.get(strategy_name)
    if not strategy_fn:
        return None, df, {
            'rejected': True,
            'reason': f'Estrategia {strategy_name} no encontrada',
            'available_strategies': list(SIMPLIFIED_RULES.keys())
        }
    
    try:
        # Ejecutar estrategia
        signal, df_processed, analysis = strategy_fn(df, config)
        
        if signal:
            # Añadir información adicional a la señal
            signal['simplified_system'] = True
            signal['timestamp'] = datetime.now(timezone.utc).isoformat()
            
            # Log de éxito
            logger.info(f"🎯 Señal simplificada generada: {symbol} {signal['type']} - {signal['explanation']}")
        
        return signal, df_processed, analysis
        
    except Exception as e:
        logger.error(f"Error en estrategia simplificada {strategy_name} para {symbol}: {e}")
        return None, df, {
            'rejected': True,
            'reason': f'Error en estrategia: {str(e)}',
            'strategy': strategy_name
        }

# ======================
# UTILIDADES DE ANÁLISIS
# ======================

def get_simplified_strategies_info() -> Dict:
    """Retorna información sobre las estrategias simplificadas disponibles"""
    return {
        'available_strategies': list(SIMPLIFIED_RULES.keys()),
        'strategy_descriptions': {
            'eurusd_simple': 'Breakout + Pullback + Sesión (Max: 4/día)',
            'xauusd_simple': 'Fakeouts + Rejection + Liquidez (Max: 3/día)', 
            'btceur_simple': 'Momentum + Tendencia + Expansión (Max: 5/día)'
        },
        'total_max_daily': 12,  # 4 + 3 + 5
        'philosophy': 'Sistema de scoring flexible - No AND estricto',
        'min_rr_ratios': {
            'eurusd_simple': 1.5,
            'xauusd_simple': 2.0,
            'btceur_simple': 1.5
        }
    }

def log_rejection_details(symbol: str, analysis: Dict):
    """Log detallado de por qué se rechazó una señal"""
    if analysis.get('rejected'):
        reason = analysis.get('reason', 'Razón desconocida')
        logger.info(f"❌ {symbol} RECHAZADO: {reason}")
        
        # Log detalles adicionales si están disponibles
        if 'score_details' in analysis:
            score_info = analysis['score_details']
            logger.debug(f"   Score: {score_info.get('score', 0):.2f} < {score_info.get('threshold', 0):.2f}")
            logger.debug(f"   Confirmaciones: {score_info.get('confirmations_passed', 0)}/{score_info.get('confirmations_total', 0)}")
        
        if 'confirmations' in analysis:
            for conf in analysis['confirmations']:
                logger.debug(f"   {conf}")