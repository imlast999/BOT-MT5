from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict

# Configurar logger primero
logger = logging.getLogger(__name__)

# Importar nuevos sistemas avanzados
try:
    from trading_filters import ConsolidatedTradingFilter
    from multi_timeframe import create_multi_timeframe_analyzer
    ADVANCED_SYSTEMS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Sistemas avanzados no disponibles: {e}")
    ADVANCED_SYSTEMS_AVAILABLE = False

SYMBOL = "EURUSD"

# ======================
# SISTEMA DE SCORING FLEXIBLE INTEGRADO
# ======================

@dataclass
class ConfirmationRule:
    """Regla de confirmación con peso y descripción"""
    name: str
    weight: float = 1.0
    description: str = ""
    critical: bool = False

@dataclass
class ScoringResult:
    """Resultado del sistema de scoring"""
    setup_valid: bool
    confirmations_passed: int
    confirmations_total: int
    final_score: float
    confidence_level: str
    should_show: bool
    details: Dict
    failed_confirmations: List[str]

class FlexibleScoring:
    """Sistema de scoring flexible integrado en signals.py"""
    
    def __init__(self):
        # Thresholds por símbolo
        self.symbol_config = {
            'EURUSD': {'min_score': 0.60, 'show_threshold': 0.50, 'setup_weight': 0.4},
            'XAUUSD': {'min_score': 0.65, 'show_threshold': 0.60, 'setup_weight': 0.5},
            'BTCEUR': {'min_score': 0.55, 'show_threshold': 0.45, 'setup_weight': 0.4}
        }
        
        # Contadores internos para logging inteligente
        self.stats = defaultdict(int)
        self.rejection_reasons = defaultdict(int)
        self.failed_rules = defaultdict(int)
        self.last_dump = datetime.now()
    
    def evaluate_signal(self, symbol: str, setup_valid: bool, 
                       confirmations: List[Tuple[bool, ConfirmationRule]]) -> ScoringResult:
        """Evalúa una señal usando scoring flexible"""
        
        config = self.symbol_config.get(symbol, self.symbol_config['EURUSD'])
        
        # Actualizar estadísticas internas
        self.stats['signals_evaluated'] += 1
        
        if not setup_valid:
            self.stats['signals_rejected'] += 1
            self.rejection_reasons['setup_invalid'] += 1
            return ScoringResult(
                setup_valid=False, confirmations_passed=0, confirmations_total=len(confirmations),
                final_score=0.0, confidence_level='NONE', should_show=False,
                details={'reason': 'Setup principal no válido'}, failed_confirmations=['SETUP_INVALID']
            )
        
        # Evaluar confirmaciones
        passed_confirmations = []
        failed_confirmations = []
        total_weight = sum(rule.weight for _, rule in confirmations)
        passed_weight = sum(rule.weight for result, rule in confirmations if result)
        
        for result, rule in confirmations:
            if result:
                passed_confirmations.append(rule.name)
            else:
                failed_confirmations.append(rule.name)
                self.failed_rules[rule.name] += 1
        
        # Score ponderado
        weighted_score = passed_weight / total_weight if total_weight > 0 else 0.0
        
        # Score final (setup + confirmaciones)
        setup_weight = config.get('setup_weight', 0.5)
        final_score = (setup_weight * 1.0) + ((1 - setup_weight) * weighted_score)
        
        # Determinar confianza
        if final_score >= 0.75:
            confidence = 'HIGH'
        elif final_score >= 0.65:
            confidence = 'MEDIUM-HIGH'
        elif final_score >= 0.50:
            confidence = 'MEDIUM'
        else:
            confidence = 'LOW'
        
        # Determinar si mostrar
        show_threshold = config.get('show_threshold', 0.50)
        should_show = final_score >= show_threshold
        
        if should_show:
            self.stats['signals_shown'] += 1
        else:
            self.stats['signals_rejected'] += 1
            self.rejection_reasons['score_insufficient'] += 1
        
        # Volcado periódico de estadísticas (cada 15 minutos)
        if (datetime.now() - self.last_dump).total_seconds() > 900:  # 15 minutos
            self._dump_stats()
        
        return ScoringResult(
            setup_valid=setup_valid,
            confirmations_passed=len(passed_confirmations),
            confirmations_total=len(confirmations),
            final_score=final_score,
            confidence_level=confidence,
            should_show=should_show,
            details={
                'symbol': symbol,
                'passed_confirmations': passed_confirmations,
                'failed_confirmations': failed_confirmations,
                'weighted_score': weighted_score,
                'show_threshold': show_threshold
            },
            failed_confirmations=failed_confirmations
        )
    
    def _dump_stats(self):
        """Volcado inteligente de estadísticas agregadas"""
        duration = (datetime.now() - self.last_dump).total_seconds() / 60
        
        # Log solo resumen importante
        if self.stats['signals_evaluated'] > 0:
            show_rate = (self.stats['signals_shown'] / self.stats['signals_evaluated']) * 100
            logger.info(f"📊 RESUMEN {duration:.0f}min: {self.stats['signals_evaluated']} evaluadas, "
                       f"{self.stats['signals_shown']} mostradas ({show_rate:.1f}%), "
                       f"{self.stats['signals_rejected']} rechazadas")
            
            # Top 3 razones de rechazo
            if self.rejection_reasons:
                top_rejections = sorted(self.rejection_reasons.items(), key=lambda x: x[1], reverse=True)[:3]
                rejection_summary = ", ".join([f"{reason}({count})" for reason, count in top_rejections])
                logger.info(f"Top rechazos: {rejection_summary}")
        
        # Reset contadores
        self.stats.clear()
        self.rejection_reasons.clear()
        self.failed_rules.clear()
        self.last_dump = datetime.now()
    
    def create_confirmation_rule(self, name: str, weight: float = 1.0, 
                               description: str = "", critical: bool = False) -> ConfirmationRule:
        """Helper para crear reglas de confirmación"""
        return ConfirmationRule(name=name, weight=weight, description=description, critical=critical)

# Instancia global del sistema de scoring
flexible_scoring = FlexibleScoring()

# simple registry for pluggable rules
RULES = {}

# Instancias globales de sistemas avanzados (si están disponibles)
if ADVANCED_SYSTEMS_AVAILABLE:
    advanced_filter_system = ConsolidatedTradingFilter()
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
    """Estrategia EMA mejorada con sistema de scoring flexible"""
    cfg = config or {}
    df = df.copy()
    
    # Verificar datos suficientes
    if len(df) < 200:
        return None, df
    
    # Indicadores
    span_fast = int(cfg.get('ema_fast', 50))
    span_slow = int(cfg.get('ema_slow', 200))
    df[f'ema{span_fast}'] = df['close'].ewm(span=span_fast).mean()
    df[f'ema{span_slow}'] = df['close'].ewm(span=span_slow).mean()
    df['rsi'] = _rsi(df['close'], 14)
    df['atr'] = _atr(df, 14)

    last = df.iloc[-1]
    price = float(last['close'])
    atr_current = last['atr']
    atr_mean = df['atr'].tail(20).mean()
    
    # 🎯 SETUP PRINCIPAL: Cruce EMA (menos exigente)
    ema_fast = last[f'ema{span_fast}']
    ema_slow = last[f'ema{span_slow}']
    
    # Breakout de 15 períodos (más flexible)
    df['high_15'] = df['high'].rolling(15).max()
    df['low_15'] = df['low'].rolling(15).min()
    
    breakout_up = price > last['high_15'] and ema_fast > ema_slow
    breakout_down = price < last['low_15'] and ema_fast < ema_slow
    setup_valid = breakout_up or breakout_down
    
    if not setup_valid:
        return None, df
    
    # ✅ CONFIRMACIONES CON SCORING FLEXIBLE
    confirmations = []
    
    # Confirmación 1: RSI en zona operativa (MÁS AMPLIO: 35-75)
    rsi_ok = 35 <= last['rsi'] <= 75
    confirmations.append((rsi_ok, flexible_scoring.create_confirmation_rule(
        "RSI_OPERATIVE", 1.0, f"RSI operativo (35-75): {last['rsi']:.1f}"
    )))
    
    # Confirmación 2: ATR por encima de media (volatilidad)
    atr_high = atr_current > atr_mean * 0.9  # Menos exigente
    confirmations.append((atr_high, flexible_scoring.create_confirmation_rule(
        "ATR_HIGH", 0.8, f"ATR alto: {atr_current:.5f} vs {atr_mean:.5f}"
    )))
    
    # Confirmación 3: No retroceso fuerte
    if breakout_up:
        recent_high = df['high'].tail(10).max()
        no_pullback = price >= recent_high * 0.998  # Tolerancia 0.2%
        direction = 'BUY'
    else:
        recent_low = df['low'].tail(10).min()
        no_pullback = price <= recent_low * 1.002  # Tolerancia 0.2%
        direction = 'SELL'
    
    confirmations.append((no_pullback, flexible_scoring.create_confirmation_rule(
        "NO_PULLBACK", 0.6, f"Sin retroceso fuerte para {direction}"
    )))
    
    # 🧮 EVALUACIÓN CON SCORING
    symbol = df.get('symbol', SYMBOL)
    scoring_result = flexible_scoring.evaluate_signal(symbol, setup_valid, confirmations)
    
    if not scoring_result.should_show:
        return None, df
    
    # 📈 GENERAR SEÑAL
    expires_minutes = int(cfg.get('expires_minutes', 30))
    sl_distance = atr_current * 1.2  # Más conservador
    tp_distance = sl_distance * 2.0  # R:R = 2.0
    
    if direction == 'BUY':
        sl = price - sl_distance
        tp = price + tp_distance
    else:
        sl = price + sl_distance
        tp = price - tp_distance
    
    sig = {
        'symbol': symbol,
        'type': direction,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'timeframe': cfg.get('timeframe', 'H1'),
        'explanation': f'EMA Mejorado: {direction} + Score {scoring_result.final_score:.2f} + R:R {tp_distance/sl_distance:.1f}',
        'expires': datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        'confidence': scoring_result.confidence_level,
        'score': scoring_result.final_score,
        'scoring_details': scoring_result.details
    }
    
    # Log solo señales importantes (HIGH/MEDIUM-HIGH)
    if scoring_result.confidence_level in ['HIGH', 'MEDIUM-HIGH']:
        logger.info(f"🎯 {symbol} {direction} señal generada | Score: {scoring_result.final_score:.2f} | Confidence: {scoring_result.confidence_level}")
    
    return sig, df

    return None, df


@register_rule('rsi')
def _rsi_strategy(df: pd.DataFrame, config: dict | None = None):
    """Estrategia RSI mejorada con sistema de scoring flexible"""
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
    df['atr'] = _atr(df, 14)

    last = rsi.iloc[-1]
    price = float(df['close'].iloc[-1])
    atr_current = df['atr'].iloc[-1]
    
    # 🎯 SETUP PRINCIPAL: RSI en zona extrema
    setup_valid = last < lower or last > upper
    
    if not setup_valid:
        return None, df
    
    # Determinar dirección
    if last < lower:
        direction = 'BUY'
        sl_distance = float(cfg.get('sl_distance', atr_current * 1.5))
        tp_distance = float(cfg.get('tp_distance', atr_current * 2.0))
    else:
        direction = 'SELL'
        sl_distance = float(cfg.get('sl_distance', atr_current * 1.5))
        tp_distance = float(cfg.get('tp_distance', atr_current * 2.0))
    
    # ✅ CONFIRMACIONES CON SCORING FLEXIBLE
    confirmations = []
    
    # Confirmación 1: RSI muy extremo (más confianza)
    rsi_extreme = last < 25 or last > 75
    confirmations.append((rsi_extreme, flexible_scoring.create_confirmation_rule(
        "RSI_EXTREME", 1.2, f"RSI muy extremo: {last:.1f}"
    )))
    
    # Confirmación 2: ATR adecuado (volatilidad)
    atr_mean = df['atr'].tail(20).mean()
    atr_ok = atr_current > atr_mean * 0.8
    confirmations.append((atr_ok, flexible_scoring.create_confirmation_rule(
        "ATR_ADEQUATE", 0.8, f"ATR adecuado: {atr_current:.5f}"
    )))
    
    # Confirmación 3: Vela de reversión
    last_candle = df.iloc[-1]
    if direction == 'BUY':
        reversal_candle = last_candle['close'] > last_candle['open']
    else:
        reversal_candle = last_candle['close'] < last_candle['open']
    
    confirmations.append((reversal_candle, flexible_scoring.create_confirmation_rule(
        "REVERSAL_CANDLE", 0.6, f"Vela de reversión para {direction}"
    )))
    
    # 🧮 EVALUACIÓN CON SCORING
    symbol = df.get('symbol', SYMBOL)
    scoring_result = flexible_scoring.evaluate_signal(symbol, setup_valid, confirmations)
    
    if not scoring_result.should_show:
        return None, df
    
    # 📈 GENERAR SEÑAL
    if direction == 'BUY':
        sl = price - sl_distance
        tp = price + tp_distance
    else:
        sl = price + sl_distance
        tp = price - tp_distance
    
    sig = {
        'symbol': symbol,
        'type': direction,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'timeframe': cfg.get('timeframe', 'H1'),
        'explanation': f'RSI Mejorado: {direction} RSI {last:.1f} + Score {scoring_result.final_score:.2f}',
        'expires': datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        'confidence': scoring_result.confidence_level,
        'score': scoring_result.final_score,
        'scoring_details': scoring_result.details
    }
    
    # Log solo señales importantes
    if scoring_result.confidence_level in ['HIGH', 'MEDIUM-HIGH']:
        logger.info(f"🎯 {symbol} {direction} RSI señal generada | Score: {scoring_result.final_score:.2f} | Confidence: {scoring_result.confidence_level}")
    
    return sig, df


@register_rule('macd')
def _macd_strategy(df: pd.DataFrame, config: dict | None = None):
    """Estrategia MACD mejorada con sistema de scoring flexible"""
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
    df['atr'] = _atr(df, 14)

    # 🎯 SETUP PRINCIPAL: Cruce del histograma MACD
    setup_valid = False
    direction = None
    
    if len(hist) >= 2:
        if hist.iloc[-2] < 0 and hist.iloc[-1] > 0:
            setup_valid = True
            direction = 'BUY'
        elif hist.iloc[-2] > 0 and hist.iloc[-1] < 0:
            setup_valid = True
            direction = 'SELL'
    
    if not setup_valid:
        return None, df
    
    price = float(df['close'].iloc[-1])
    atr_current = df['atr'].iloc[-1]
    
    # ✅ CONFIRMACIONES CON SCORING FLEXIBLE
    confirmations = []
    
    # Confirmación 1: Magnitud del histograma
    hist_magnitude = abs(hist.iloc[-1])
    hist_strong = hist_magnitude > abs(hist.tail(10).mean())
    confirmations.append((hist_strong, flexible_scoring.create_confirmation_rule(
        "HIST_MAGNITUDE", 1.0, f"Histograma fuerte: {hist_magnitude:.6f}"
    )))
    
    # Confirmación 2: MACD por encima/debajo de cero
    if direction == 'BUY':
        macd_position_ok = macd.iloc[-1] > -abs(macd.tail(20).std())
    else:
        macd_position_ok = macd.iloc[-1] < abs(macd.tail(20).std())
    
    confirmations.append((macd_position_ok, flexible_scoring.create_confirmation_rule(
        "MACD_POSITION", 0.8, f"MACD en posición favorable para {direction}"
    )))
    
    # Confirmación 3: Volatilidad adecuada
    atr_mean = df['atr'].tail(20).mean()
    atr_ok = atr_current > atr_mean * 0.7
    confirmations.append((atr_ok, flexible_scoring.create_confirmation_rule(
        "ATR_ADEQUATE", 0.6, f"ATR adecuado: {atr_current:.5f}"
    )))
    
    # 🧮 EVALUACIÓN CON SCORING
    symbol = df.get('symbol', SYMBOL)
    scoring_result = flexible_scoring.evaluate_signal(symbol, setup_valid, confirmations)
    
    if not scoring_result.should_show:
        return None, df
    
    # 📈 GENERAR SEÑAL
    sl_distance = float(cfg.get('sl_distance', atr_current * 1.5))
    tp_distance = float(cfg.get('tp_distance', atr_current * 2.0))
    
    if direction == 'BUY':
        sl = price - sl_distance
        tp = price + tp_distance
    else:
        sl = price + sl_distance
        tp = price - tp_distance
    
    sigd = {
        'symbol': symbol,
        'type': direction,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'timeframe': cfg.get('timeframe', 'H1'),
        'explanation': f'MACD Mejorado: {direction} histograma cruce + Score {scoring_result.final_score:.2f}',
        'expires': datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        'confidence': scoring_result.confidence_level,
        'score': scoring_result.final_score,
        'scoring_details': scoring_result.details
    }
    
    # Log solo señales importantes
    if scoring_result.confidence_level in ['HIGH', 'MEDIUM-HIGH']:
        logger.info(f"🎯 {symbol} {direction} MACD señal generada | Score: {scoring_result.final_score:.2f} | Confidence: {scoring_result.confidence_level}")
    
    return sigd, df


def detect_signal_advanced(df: pd.DataFrame, strategy: str = 'ema50_200', config: dict | None = None, current_balance: float = 5000.0, symbol: str = 'EURUSD'):
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
            # Obtener balance de la cuenta
            try:
                import MetaTrader5 as mt5
                account_info = mt5.account_info()
                account_balance = account_info.balance if account_info else 10000.0  # Default fallback
            except Exception:
                account_balance = 10000.0  # Default fallback
            
            filter_passed, filter_reason, filter_info = advanced_filter_system.apply_all_filters(
                df_with_indicators, basic_signal, account_balance
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


def _atr(df: pd.DataFrame, period: int = 14):
    """
    Calcula el Average True Range (ATR)
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    # True Range calculation
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    
    return atr


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
    Estrategia EURUSD OPTIMIZADA: Menos estricta, más oportunidades
    
    MEJORAS IMPLEMENTADAS:
    - Breakout menos exigente (15 períodos en vez de 20)
    - RSI más amplio (40-60 en vez de 50)
    - Filtros más flexibles para generar más señales
    - Mejor distribución de confianza
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
    df['atr'] = _atr(df, 14)
    
    # Breakout de 15 períodos (menos exigente)
    df['high_15'] = df['high'].rolling(15).max()
    df['low_15'] = df['low'].rolling(15).min()
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    atr_current = last['atr']
    
    # 🔹 SEÑAL DE COMPRA: Breakout alcista RELAJADO
    if (price > last['high_15'] and  # Breakout alcista de 15 períodos (menos exigente)
        last['ema50'] > last['ema200']):  # Solo EMA50 > EMA200 (tendencia alcista)
        
        # RSI más flexible: 40-80 (antes era >50)
        rsi_ok = 40 <= last['rsi'] <= 80
        
        if rsi_ok:
            # Calcular niveles
            sl_distance = atr_current * 1.2  # SL más ajustado
            tp_distance = sl_distance * 2.0
            
            # Determinar confianza basada en múltiples factores
            confidence_score = 0
            
            # Factor 1: Fuerza del RSI
            if 50 <= last['rsi'] <= 70:
                confidence_score += 1
            
            # Factor 2: Separación EMAs
            ema_separation = (last['ema50'] - last['ema200']) / atr_current
            if ema_separation > 0.5:
                confidence_score += 1
                
            # Factor 3: Momentum del breakout
            breakout_strength = (price - last['high_15']) / atr_current
            if breakout_strength > 0.3:
                confidence_score += 1
            
            # Mapear score a confianza
            if confidence_score >= 2:
                confidence = 'HIGH'
            elif confidence_score == 1:
                confidence = 'MEDIUM-HIGH'
            else:
                confidence = 'MEDIUM'
            
            signal = {
                'symbol': 'EURUSD',
                'type': 'BUY',
                'entry': price,
                'sl': price - sl_distance,
                'tp': price + tp_distance,
                'explanation': f'EURUSD RELAXED: Breakout alcista 15P + EMA50>EMA200 + RSI {last["rsi"]:.1f} (Score: {confidence_score})',
                'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 45))),
                'confidence': confidence,
                'strategy': 'eurusd_advanced'
            }
            
            logger.info(f"EURUSD BUY signal generated: RSI {last['rsi']:.1f}, Confidence {confidence} (Score: {confidence_score})")
            return signal, df
    
    # 🔹 SEÑAL DE VENTA: Breakout bajista RELAJADO
    if (price < last['low_15'] and  # Breakout bajista de 15 períodos (menos exigente)
        last['ema50'] < last['ema200']):  # Solo EMA50 < EMA200 (tendencia bajista)
        
        # RSI más flexible: 20-60 (antes era <50)
        rsi_ok = 20 <= last['rsi'] <= 60
        
        if rsi_ok:
            # Calcular niveles
            sl_distance = atr_current * 1.2  # SL más ajustado
            tp_distance = sl_distance * 2.0
            
            # Determinar confianza basada en múltiples factores
            confidence_score = 0
            
            # Factor 1: Fuerza del RSI
            if 30 <= last['rsi'] <= 50:
                confidence_score += 1
            
            # Factor 2: Separación EMAs
            ema_separation = (last['ema200'] - last['ema50']) / atr_current
            if ema_separation > 0.5:
                confidence_score += 1
                
            # Factor 3: Momentum del breakout
            breakout_strength = (last['low_15'] - price) / atr_current
            if breakout_strength > 0.3:
                confidence_score += 1
            
            # Mapear score a confianza
            if confidence_score >= 2:
                confidence = 'HIGH'
            elif confidence_score == 1:
                confidence = 'MEDIUM-HIGH'
            else:
                confidence = 'MEDIUM'
            
            signal = {
                'symbol': 'EURUSD',
                'type': 'SELL',
                'entry': price,
                'sl': price + sl_distance,
                'tp': price - tp_distance,
                'explanation': f'EURUSD RELAXED: Breakout bajista 15P + EMA50<EMA200 + RSI {last["rsi"]:.1f} (Score: {confidence_score})',
                'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 45))),
                'confidence': confidence,
                'strategy': 'eurusd_advanced'
            }
            
            logger.info(f"EURUSD SELL signal generated: RSI {last['rsi']:.1f}, Confidence {confidence} (Score: {confidence_score})")
            return signal, df
    
    # Si no hay breakout, intentar señales de continuación de tendencia
    # 🔹 SEÑAL DE CONTINUACIÓN ALCISTA (menos exigente)
    if (last['ema50'] > last['ema200'] and  # Tendencia alcista
        price > last['ema50'] and  # Precio por encima de EMA50
        45 <= last['rsi'] <= 65):  # RSI neutral-alcista
        
        # Verificar que no estemos en sobrecompra extrema
        recent_high = df['high'].tail(10).max()
        if price < recent_high * 1.002:  # No más del 0.2% por encima del máximo reciente
            
            sl_distance = atr_current * 1.0
            tp_distance = sl_distance * 1.5
            
            signal = {
                'symbol': 'EURUSD',
                'type': 'BUY',
                'entry': price,
                'sl': price - sl_distance,
                'tp': price + tp_distance,
                'explanation': f'EURUSD CONTINUATION: Tendencia alcista + RSI {last["rsi"]:.1f}',
                'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 30))),
                'confidence': 'MEDIUM',
                'strategy': 'eurusd_advanced'
            }
            
            logger.info(f"EURUSD BUY continuation signal: RSI {last['rsi']:.1f}")
            return signal, df
    
    # 🔹 SEÑAL DE CONTINUACIÓN BAJISTA (menos exigente)
    if (last['ema50'] < last['ema200'] and  # Tendencia bajista
        price < last['ema50'] and  # Precio por debajo de EMA50
        35 <= last['rsi'] <= 55):  # RSI neutral-bajista
        
        # Verificar que no estemos en sobreventa extrema
        recent_low = df['low'].tail(10).min()
        if price > recent_low * 0.998:  # No más del 0.2% por debajo del mínimo reciente
            
            sl_distance = atr_current * 1.0
            tp_distance = sl_distance * 1.5
            
            signal = {
                'symbol': 'EURUSD',
                'type': 'SELL',
                'entry': price,
                'sl': price + sl_distance,
                'tp': price - tp_distance,
                'explanation': f'EURUSD CONTINUATION: Tendencia bajista + RSI {last["rsi"]:.1f}',
                'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 30))),
                'confidence': 'MEDIUM',
                'strategy': 'eurusd_advanced'
            }
            
            logger.info(f"EURUSD SELL continuation signal: RSI {last['rsi']:.1f}")
            return signal, df
    
    logger.debug("EURUSD: No valid setup found")
    return None, df


@register_rule('xauusd_advanced')
def xauusd_advanced_strategy(df: pd.DataFrame, config: dict | None = None):
    """
    Estrategia XAUUSD ULTRA-SELECTIVA v2.0: Máxima reducción de ruido
    
    NUEVAS MEJORAS IMPLEMENTADAS:
    - Wick ratio mínimo 50% (más estricto)
    - Distancia al nivel ±3$ (ultra estricto)
    - ATR mínimo más exigente
    - Filtro de sesión mejorado
    - Filtro de rango lateral más estricto
    - Sistema de zonas inteligente
    - Cooldown integrado con duplicate_filter
    """
    cfg = config or {}
    df = df.copy()
    
    # Verificar datos suficientes
    if len(df) < 200:
        logger.debug("XAUUSD rejected: Insufficient data")
        return None, df
    
    # 🕐 FILTRO DE SESIÓN: Solo Londres + NY overlap (13-17 GMT) - MÁS ESTRICTO
    current_hour = datetime.now(timezone.utc).hour
    overlap_session = 13 <= current_hour <= 17  # Solo overlap Londres-NY
    
    if not overlap_session:
        logger.debug(f"XAUUSD rejected: Outside overlap session (hour: {current_hour})")
        return None, df
    
    # Indicadores requeridos
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()
    df['atr'] = _atr(df, 14)
    df['rsi'] = _rsi(df['close'], 14)  # Añadir RSI para filtro adicional
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    atr_current = last['atr']
    atr_mean = df['atr'].tail(20).mean()
    rsi_current = last['rsi']
    
    # 🧩 FILTRO 1: VOLATILIDAD ULTRA-ESTRICTA
    candle_range = last['high'] - last['low']
    if candle_range < 15.0:  # MÁS ESTRICTO: 15 puntos mínimo
        logger.debug(f"XAUUSD rejected: Low volatility candle ({candle_range:.1f} < 15.0)")
        return None, df
    
    # 🧩 FILTRO 2: ATR ULTRA-EXIGENTE
    if atr_current < atr_mean * 1.0:  # ATR debe ser igual o mayor al promedio
        logger.debug(f"XAUUSD rejected: Low volatility regime (ATR: {atr_current:.1f} < {atr_mean:.1f})")
        return None, df
    
    # 🧩 FILTRO 3: EVITAR MERCADO LATERAL ULTRA-ESTRICTO
    ema_separation = abs(last['ema50'] - last['ema200'])
    if ema_separation < atr_current * 0.8:  # EMAs mucho más separadas requeridas
        logger.debug(f"XAUUSD rejected: Sideways market (EMA separation: {ema_separation:.1f} < {atr_current*0.8:.1f})")
        return None, df
    
    # 🧩 FILTRO 4: DESPLAZAMIENTO REAL ULTRA-EXIGENTE
    price_move = abs(price - prev['close'])
    if price_move < atr_current * 0.5:  # Movimiento mínimo más exigente
        logger.debug(f"XAUUSD rejected: No real price displacement ({price_move:.1f} < {atr_current*0.5:.1f})")
        return None, df
    
    # 🧩 FILTRO 5: RSI NO EXTREMO (evitar sobrecompra/sobreventa)
    if rsi_current < 25 or rsi_current > 75:
        logger.debug(f"XAUUSD rejected: RSI too extreme ({rsi_current:.1f})")
        return None, df
    
    # Niveles psicológicos dinámicos - ULTRA-SELECTIVOS
    closest_level = round(price / 25) * 25  # Niveles cada 25 puntos
    distance_to_level = abs(price - closest_level)
    
    # 🧩 FILTRO 6: PROXIMIDAD ULTRA-ULTRA-ESTRICTA A NIVELES
    # Solo operar si estamos EXTREMADAMENTE cerca del nivel (máximo 3 puntos)
    if distance_to_level > 3.0:
        logger.debug(f"XAUUSD rejected: Too far from psychological level ({distance_to_level:.1f} > 3.0)")
        return None, df
    
    # 🧩 FILTRO 7: VERIFICAR QUE NO ESTAMOS EN RANGO MUERTO
    recent_high = df['high'].tail(20).max()
    recent_low = df['low'].tail(20).min()
    recent_range = recent_high - recent_low
    
    if recent_range < atr_current * 10:  # Rango reciente debe ser significativo
        logger.debug(f"XAUUSD rejected: Dead range market ({recent_range:.1f} < {atr_current*10:.1f})")
        return None, df
    
    # Calcular tamaño de mecha
    candle_range = last['high'] - last['low']
    upper_wick = last['high'] - max(last['open'], last['close'])
    lower_wick = min(last['open'], last['close']) - last['low']
    upper_wick_pct = (upper_wick / candle_range) * 100 if candle_range > 0 else 0
    lower_wick_pct = (lower_wick / candle_range) * 100 if candle_range > 0 else 0
    
    # 🧩 SEÑAL DE COMPRA: Reversión alcista ULTRA-ULTRA-SELECTIVA
    if (distance_to_level <= 3.0 and  # ±3$ del nivel psicológico (ULTRA estricto)
        price < closest_level and  # Precio por debajo del nivel
        last['ema50'] > last['ema200'] and  # Tendencia alcista
        lower_wick_pct >= 50 and  # Mecha inferior ≥50% (ULTRA estricto)
        last['close'] > last['open'] and  # Vela alcista
        candle_range >= 15.0 and  # Vela con rango mínimo de 15 puntos
        30 <= rsi_current <= 70):  # RSI en rango operativo
        
        # Niveles fijos para oro - MÁS CONSERVADORES
        sl_distance = 8.0   # SL más ajustado
        tp_distance = 16.0  # TP más conservador (2:1 ratio)
        
        # Determinar confianza de forma ULTRA-ESTRICTA
        confidence_score = 0
        
        # Factor 1: Proximidad extrema al nivel
        if distance_to_level <= 2.0:
            confidence_score += 1
            
        # Factor 2: Mecha ultra fuerte
        if lower_wick_pct >= 60:
            confidence_score += 1
            
        # Factor 3: Volatilidad muy alta
        if atr_current > atr_mean * 1.3:
            confidence_score += 1
            
        # Factor 4: RSI en zona óptima
        if 40 <= rsi_current <= 60:
            confidence_score += 1
        
        # Mapear score a confianza - MÁS ESTRICTO
        if confidence_score >= 3:
            confidence = 'HIGH'
        elif confidence_score >= 2:
            confidence = 'MEDIUM-HIGH'
        else:
            confidence = 'MEDIUM'
        
        signal = {
            'symbol': 'XAUUSD',
            'type': 'BUY',
            'entry': price,
            'sl': price - sl_distance,
            'tp': price + tp_distance,
            'zone': f"XAUUSD_{closest_level:.0f}",  # Añadir zona
            'explanation': f'XAUUSD ULTRA-SELECT v2: Reversión alcista ${distance_to_level:.1f} del nivel ${closest_level}, mecha {lower_wick_pct:.1f}%, ATR {atr_current:.1f}, RSI {rsi_current:.1f} (Score: {confidence_score})',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 60))),
            'confidence': confidence,
            'strategy': 'xauusd_advanced_v2'
        }
        
        logger.info(f"🟢 XAUUSD BUY ULTRA-SELECT v2: Level distance {distance_to_level:.1f}, Wick {lower_wick_pct:.1f}%, RSI {rsi_current:.1f}, Confidence {confidence} (Score: {confidence_score})")
        return signal, df
    
    # 🧩 SEÑAL DE VENTA: Reversión bajista ULTRA-ULTRA-SELECTIVA
    if (distance_to_level <= 3.0 and  # ±3$ del nivel psicológico (ULTRA estricto)
        price > closest_level and  # Precio por encima del nivel
        last['ema50'] < last['ema200'] and  # Tendencia bajista
        upper_wick_pct >= 50 and  # Mecha superior ≥50% (ULTRA estricto)
        last['close'] < last['open'] and  # Vela bajista
        candle_range >= 15.0 and  # Vela con rango mínimo de 15 puntos
        30 <= rsi_current <= 70):  # RSI en rango operativo
        
        # Niveles fijos para oro - MÁS CONSERVADORES
        sl_distance = 8.0   # SL más ajustado
        tp_distance = 16.0  # TP más conservador (2:1 ratio)
        
        # Determinar confianza de forma ULTRA-ESTRICTA
        confidence_score = 0
        
        # Factor 1: Proximidad extrema al nivel
        if distance_to_level <= 2.0:
            confidence_score += 1
            
        # Factor 2: Mecha ultra fuerte
        if upper_wick_pct >= 60:
            confidence_score += 1
            
        # Factor 3: Volatilidad muy alta
        if atr_current > atr_mean * 1.3:
            confidence_score += 1
            
        # Factor 4: RSI en zona óptima
        if 40 <= rsi_current <= 60:
            confidence_score += 1
        
        # Mapear score a confianza - MÁS ESTRICTO
        if confidence_score >= 3:
            confidence = 'HIGH'
        elif confidence_score >= 2:
            confidence = 'MEDIUM-HIGH'
        else:
            confidence = 'MEDIUM'
        
        signal = {
            'symbol': 'XAUUSD',
            'type': 'SELL',
            'entry': price,
            'sl': price + sl_distance,
            'tp': price - tp_distance,
            'zone': f"XAUUSD_{closest_level:.0f}",  # Añadir zona
            'explanation': f'XAUUSD ULTRA-SELECT v2: Reversión bajista ${distance_to_level:.1f} del nivel ${closest_level}, mecha {upper_wick_pct:.1f}%, ATR {atr_current:.1f}, RSI {rsi_current:.1f} (Score: {confidence_score})',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 60))),
            'confidence': confidence,
            'strategy': 'xauusd_advanced_v2'
        }
        
        logger.info(f"🔴 XAUUSD SELL ULTRA-SELECT v2: Level distance {distance_to_level:.1f}, Wick {upper_wick_pct:.1f}%, RSI {rsi_current:.1f}, Confidence {confidence} (Score: {confidence_score})")
        return signal, df
    
    # Si llegamos aquí, no hay señal válida
    logger.debug("XAUUSD v2: No valid setup found after ultra-strict filters")
    return None, df


@register_rule('btceur_advanced')
def btceur_advanced_strategy(df: pd.DataFrame, config: dict | None = None):
    """
    Estrategia BTCEUR OPTIMIZADA: Más flexible, menos conservador
    
    MEJORAS IMPLEMENTADAS:
    - Cruces EMA con menor separación mínima
    - RSI menos restrictivo (35-65 en vez de 50)
    - Momentum no tan alto como requisito
    - ATR mínimo reducido
    - Mejor distribución de confianza
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
    df['atr'] = _atr(df, 14)
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    atr_current = last['atr']
    
    # 🔹 SEÑAL DE COMPRA: EMA12 > EMA26 RELAJADO
    if (last['ema12'] > last['ema26'] and  # EMA12 > EMA26 (momentum tendencial)
        last['ema12'] > last['ema50']):  # Filtro de estructura: EMA12 > EMA50
        
        # RSI más flexible: 35-75 (antes era >50)
        rsi_ok = 35 <= last['rsi'] <= 75
        
        if rsi_ok:
            # Verificar que no esté en lateral RELAJADO (EMA50 menos plana)
            ema50_slope = (last['ema50'] - df['ema50'].iloc[-5]) / 5
            lateral_threshold = 0.00005  # Más permisivo (antes 0.0001)
            
            if abs(ema50_slope) >= lateral_threshold:  # No está completamente lateral
                
                # ATR mínimo REDUCIDO (menos restrictivo)
                atr_min = 30  # Reducido de 50 a 30
                
                if atr_current >= atr_min:
                    
                    # Determinar confianza basada en múltiples factores
                    confidence_score = 0
                    
                    # Factor 1: Fuerza del RSI
                    if 50 <= last['rsi'] <= 70:
                        confidence_score += 1
                    
                    # Factor 2: Separación EMAs (momentum)
                    ema_separation = (last['ema12'] - last['ema26']) / atr_current
                    if ema_separation > 0.3:  # Separación significativa
                        confidence_score += 1
                        
                    # Factor 3: Pendiente EMA50 (tendencia)
                    if ema50_slope > 0.0001:  # Tendencia alcista clara
                        confidence_score += 1
                        
                    # Factor 4: ATR alto (volatilidad)
                    atr_mean = df['atr'].tail(20).mean()
                    if atr_current > atr_mean * 1.1:
                        confidence_score += 1
                    
                    # Mapear score a confianza
                    if confidence_score >= 3:
                        confidence = 'HIGH'
                    elif confidence_score == 2:
                        confidence = 'MEDIUM-HIGH'
                    elif confidence_score == 1:
                        confidence = 'MEDIUM'
                    else:
                        confidence = 'MEDIUM'  # Mínimo MEDIUM para BTCEUR
                    
                    # Calcular niveles más conservadores
                    sl_distance = atr_current * 2.0  # Reducido de 2.5 a 2.0
                    tp_distance = sl_distance * 2.0  # Reducido de 2.5 a 2.0
                    
                    signal = {
                        'symbol': 'BTCEUR',
                        'type': 'BUY',
                        'entry': price,
                        'sl': price - sl_distance,
                        'tp': price + tp_distance,
                        'explanation': f'BTCEUR RELAXED: EMA12>EMA26+EMA50 + RSI {last["rsi"]:.1f} + ATR {atr_current:.0f} (Score: {confidence_score})',
                        'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 90))),
                        'confidence': confidence,
                        'strategy': 'btceur_advanced'
                    }
                    
                    logger.info(f"BTCEUR BUY signal generated: RSI {last['rsi']:.1f}, Confidence {confidence} (Score: {confidence_score})")
                    return signal, df
    
    # 🔹 SEÑAL DE VENTA: EMA12 < EMA26 RELAJADO
    if (last['ema12'] < last['ema26'] and  # EMA12 < EMA26 (momentum tendencial bajista)
        last['ema12'] < last['ema50']):  # Filtro de estructura: EMA12 < EMA50
        
        # RSI más flexible: 25-65 (antes era <50)
        rsi_ok = 25 <= last['rsi'] <= 65
        
        if rsi_ok:
            # Verificar que no esté en lateral RELAJADO (EMA50 menos plana)
            ema50_slope = (last['ema50'] - df['ema50'].iloc[-5]) / 5
            lateral_threshold = 0.00005  # Más permisivo (antes 0.0001)
            
            if abs(ema50_slope) >= lateral_threshold:  # No está completamente lateral
                
                # ATR mínimo REDUCIDO (menos restrictivo)
                atr_min = 30  # Reducido de 50 a 30
                
                if atr_current >= atr_min:
                    
                    # Determinar confianza basada en múltiples factores
                    confidence_score = 0
                    
                    # Factor 1: Fuerza del RSI
                    if 30 <= last['rsi'] <= 50:
                        confidence_score += 1
                    
                    # Factor 2: Separación EMAs (momentum)
                    ema_separation = (last['ema26'] - last['ema12']) / atr_current
                    if ema_separation > 0.3:  # Separación significativa
                        confidence_score += 1
                        
                    # Factor 3: Pendiente EMA50 (tendencia)
                    if ema50_slope < -0.0001:  # Tendencia bajista clara
                        confidence_score += 1
                        
                    # Factor 4: ATR alto (volatilidad)
                    atr_mean = df['atr'].tail(20).mean()
                    if atr_current > atr_mean * 1.1:
                        confidence_score += 1
                    
                    # Mapear score a confianza
                    if confidence_score >= 3:
                        confidence = 'HIGH'
                    elif confidence_score == 2:
                        confidence = 'MEDIUM-HIGH'
                    elif confidence_score == 1:
                        confidence = 'MEDIUM'
                    else:
                        confidence = 'MEDIUM'  # Mínimo MEDIUM para BTCEUR
                    
                    # Calcular niveles más conservadores
                    sl_distance = atr_current * 2.0  # Reducido de 2.5 a 2.0
                    tp_distance = sl_distance * 2.0  # Reducido de 2.5 a 2.0
                    
                    signal = {
                        'symbol': 'BTCEUR',
                        'type': 'SELL',
                        'entry': price,
                        'sl': price + sl_distance,
                        'tp': price - tp_distance,
                        'explanation': f'BTCEUR RELAXED: EMA12<EMA26+EMA50 + RSI {last["rsi"]:.1f} + ATR {atr_current:.0f} (Score: {confidence_score})',
                        'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 90))),
                        'confidence': confidence,
                        'strategy': 'btceur_advanced'
                    }
                    
                    logger.info(f"BTCEUR SELL signal generated: RSI {last['rsi']:.1f}, Confidence {confidence} (Score: {confidence_score})")
                    return signal, df
    
    # Si no hay cruce claro, intentar señales de momentum
    # 🔹 SEÑAL DE MOMENTUM ALCISTA (nueva)
    if (last['ema12'] > last['ema50'] and  # Precio por encima de EMA50
        last['ema50'] > last['ema200'] if 'ema200' in df.columns else True and  # Tendencia general alcista
        50 <= last['rsi'] <= 70):  # RSI en zona de fuerza
        
        # Verificar momentum reciente
        price_change = (price - df['close'].iloc[-5]) / df['close'].iloc[-5]
        if price_change > 0.01:  # Al menos 1% de movimiento en 5 períodos
            
            sl_distance = atr_current * 1.5
            tp_distance = sl_distance * 1.5
            
            signal = {
                'symbol': 'BTCEUR',
                'type': 'BUY',
                'entry': price,
                'sl': price - sl_distance,
                'tp': price + tp_distance,
                'explanation': f'BTCEUR MOMENTUM: Tendencia alcista + RSI {last["rsi"]:.1f} + Momentum {price_change*100:.1f}%',
                'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 60))),
                'confidence': 'MEDIUM',
                'strategy': 'btceur_advanced'
            }
            
            logger.info(f"BTCEUR BUY momentum signal: RSI {last['rsi']:.1f}, Momentum {price_change*100:.1f}%")
            return signal, df
    
    # 🔹 SEÑAL DE MOMENTUM BAJISTA (nueva)
    if (last['ema12'] < last['ema50'] and  # Precio por debajo de EMA50
        last['ema50'] < last['ema200'] if 'ema200' in df.columns else True and  # Tendencia general bajista
        30 <= last['rsi'] <= 50):  # RSI en zona de debilidad
        
        # Verificar momentum reciente
        price_change = (price - df['close'].iloc[-5]) / df['close'].iloc[-5]
        if price_change < -0.01:  # Al menos -1% de movimiento en 5 períodos
            
            sl_distance = atr_current * 1.5
            tp_distance = sl_distance * 1.5
            
            signal = {
                'symbol': 'BTCEUR',
                'type': 'SELL',
                'entry': price,
                'sl': price + sl_distance,
                'tp': price - tp_distance,
                'explanation': f'BTCEUR MOMENTUM: Tendencia bajista + RSI {last["rsi"]:.1f} + Momentum {price_change*100:.1f}%',
                'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 60))),
                'confidence': 'MEDIUM',
                'strategy': 'btceur_advanced'
            }
            
            logger.info(f"BTCEUR SELL momentum signal: RSI {last['rsi']:.1f}, Momentum {price_change*100:.1f}%")
            return signal, df
    
    logger.debug("BTCEUR: No valid setup found")
    return None, df
