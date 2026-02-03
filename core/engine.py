"""
Core Trading Engine - Orquestador principal de señales

Este módulo consolida toda la lógica de detección, scoring, confianza y filtros
en un solo lugar, eliminando la fragmentación del código anterior.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import pandas as pd

logger = logging.getLogger(__name__)

def get_current_period_start() -> datetime:
    """Obtiene el inicio del período actual (00:00 o 12:00 UTC)"""
    now = datetime.now(timezone.utc)
    if now.hour < 12:
        # Período 00:00-12:00
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # Período 12:00-24:00
        return now.replace(hour=12, minute=0, second=0, microsecond=0)

@dataclass
class BotState:
    """Estado global del bot consolidado"""
    pending_signals: Dict[int, dict] = field(default_factory=dict)
    trades_today: int = 0
    trades_current_period: int = 0  # Trades en el período actual (12h)
    current_period_start: datetime = field(default_factory=get_current_period_start)
    mt5_credentials: Dict[str, Any] = field(default_factory=dict)
    autosignals: bool = field(default_factory=lambda: os.getenv('AUTOSIGNALS', '0') == '1')
    last_auto_sent: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SignalContext:
    """Contexto completo de una señal para evaluación"""
    symbol: str
    strategy: str
    raw_signal: Dict
    dataframe: pd.DataFrame
    market_conditions: Dict
    risk_info: Dict

@dataclass
class SignalResult:
    """Resultado final de evaluación de señal"""
    signal: Optional[Dict]
    should_show: bool
    should_execute: bool
    confidence: str
    score: float
    rejection_reason: Optional[str]
    details: Dict

class TradingEngine:
    """
    Motor principal de trading que orquesta:
    1. Detección de señales
    2. Scoring y confianza
    3. Filtros y validaciones
    4. Decisión final
    """
    
    def __init__(self):
        self.scoring_system = FlexibleScoring()
        self.confidence_system = ConfidenceSystem()
        self.duplicate_filter = DuplicateFilter()
        
        # Estadísticas internas para logging inteligente
        self.stats = defaultdict(int)
        self.rejection_reasons = defaultdict(int)
        self.last_dump = datetime.now()
    
    def evaluate_signal(self, df: pd.DataFrame, symbol: str, strategy: str = 'ema50_200', 
                       config: Dict = None) -> SignalResult:
        """
        Evaluación completa de señal con pipeline integrado:
        1. Detectar setup básico
        2. Calcular scoring y confianza  
        3. Aplicar filtros
        4. Decisión final
        """
        try:
            # 1. Detectar señal básica
            from signals import detect_signal
            raw_signal, df_with_indicators = detect_signal(df, strategy, config)
            
            if not raw_signal:
                return self._create_rejection_result(
                    symbol, strategy, "No setup básico detectado"
                )
            
            # Asegurar símbolo correcto
            raw_signal['symbol'] = symbol
            
            # 2. Crear contexto para evaluación
            context = SignalContext(
                symbol=symbol,
                strategy=strategy,
                raw_signal=raw_signal,
                dataframe=df_with_indicators,
                market_conditions=self._analyze_market_conditions(df_with_indicators),
                risk_info={}
            )
            
            # 3. Calcular scoring y confianza
            scoring_result = self.scoring_system.evaluate_signal_context(context)
            confidence_result = self.confidence_system.calculate_confidence_context(context)
            
            # 4. Verificar filtro de duplicados
            is_duplicate, duplicate_reason = self.duplicate_filter.is_duplicate(raw_signal, symbol)
            if is_duplicate:
                return self._create_rejection_result(
                    symbol, strategy, f"Duplicado: {duplicate_reason}"
                )
            
            # 5. Decisión final
            should_show = scoring_result.should_show and confidence_result.should_show
            should_execute = should_show and confidence_result.should_execute
            
            # 6. Crear señal final enriquecida
            if should_show:
                final_signal = self._enrich_signal(
                    raw_signal, scoring_result, confidence_result, context
                )
                
                # Actualizar estadísticas
                self.stats['signals_shown'] += 1
                
                return SignalResult(
                    signal=final_signal,
                    should_show=True,
                    should_execute=should_execute,
                    confidence=confidence_result.confidence_level,
                    score=scoring_result.final_score,
                    rejection_reason=None,
                    details={
                        'scoring': scoring_result.details,
                        'confidence': confidence_result.details,
                        'market_conditions': context.market_conditions
                    }
                )
            else:
                # Señal rechazada por scoring/confianza
                reason = "Score insuficiente" if not scoring_result.should_show else "Confianza insuficiente"
                return self._create_rejection_result(symbol, strategy, reason)
                
        except Exception as e:
            logger.error(f"Error evaluando señal {symbol}: {e}")
            return self._create_rejection_result(symbol, strategy, f"Error: {str(e)}")
    
    def _analyze_market_conditions(self, df: pd.DataFrame) -> Dict:
        """Analiza condiciones generales del mercado"""
        try:
            last = df.iloc[-1]
            
            # Volatilidad (ATR)
            if 'atr' in df.columns:
                atr_current = last['atr']
                atr_mean = df['atr'].tail(20).mean()
                volatility_ratio = atr_current / atr_mean if atr_mean > 0 else 1.0
            else:
                volatility_ratio = 1.0
            
            # Tendencia (EMA200 si existe)
            trend_direction = 'NEUTRAL'
            if 'ema200' in df.columns:
                price = last['close']
                ema200 = last['ema200']
                if price > ema200 * 1.001:
                    trend_direction = 'BULLISH'
                elif price < ema200 * 0.999:
                    trend_direction = 'BEARISH'
            
            return {
                'volatility_ratio': volatility_ratio,
                'trend_direction': trend_direction,
                'price': float(last['close']),
                'volume_available': 'volume' in df.columns
            }
            
        except Exception as e:
            logger.warning(f"Error analizando condiciones de mercado: {e}")
            return {'error': str(e)}
    
    def _enrich_signal(self, raw_signal: Dict, scoring_result, confidence_result, context: SignalContext) -> Dict:
        """Enriquece la señal con información de scoring y confianza"""
        enriched = raw_signal.copy()
        
        # Información de scoring
        enriched['confidence'] = confidence_result.confidence_level
        enriched['confidence_score'] = confidence_result.confidence_score
        enriched['score'] = scoring_result.final_score
        
        # Detalles para debugging
        enriched['scoring_details'] = scoring_result.details
        enriched['confidence_details'] = confidence_result.details
        enriched['market_conditions'] = context.market_conditions
        
        # Metadatos
        enriched['strategy_used'] = context.strategy
        enriched['evaluation_time'] = datetime.now(timezone.utc).isoformat()
        
        return enriched
    
    def _create_rejection_result(self, symbol: str, strategy: str, reason: str) -> SignalResult:
        """Crea resultado de rechazo con estadísticas"""
        self.stats['signals_rejected'] += 1
        self.rejection_reasons[reason] += 1
        
        return SignalResult(
            signal=None,
            should_show=False,
            should_execute=False,
            confidence='NONE',
            score=0.0,
            rejection_reason=reason,
            details={'symbol': symbol, 'strategy': strategy, 'reason': reason}
        )
    
    def get_statistics(self) -> Dict:
        """Obtiene estadísticas del engine"""
        total_evaluated = self.stats['signals_shown'] + self.stats['signals_rejected']
        
        return {
            'total_evaluated': total_evaluated,
            'signals_shown': self.stats['signals_shown'],
            'signals_rejected': self.stats['signals_rejected'],
            'show_rate': (self.stats['signals_shown'] / total_evaluated * 100) if total_evaluated > 0 else 0,
            'top_rejection_reasons': dict(sorted(self.rejection_reasons.items(), key=lambda x: x[1], reverse=True)[:5])
        }


# ============================================================================
# SISTEMA DE SCORING INTEGRADO (consolidado de signals.py)
# ============================================================================

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
    """Sistema de scoring flexible consolidado"""
    
    def __init__(self):
        # Configuración por símbolo
        self.symbol_config = {
            'EURUSD': {'min_score': 0.60, 'show_threshold': 0.50, 'setup_weight': 0.4},
            'XAUUSD': {'min_score': 0.65, 'show_threshold': 0.60, 'setup_weight': 0.5},
            'BTCEUR': {'min_score': 0.55, 'show_threshold': 0.45, 'setup_weight': 0.4}
        }
    
    def evaluate_signal_context(self, context: SignalContext) -> ScoringResult:
        """Evalúa señal usando contexto completo"""
        symbol = context.symbol
        signal = context.raw_signal
        df = context.dataframe
        
        # Extraer confirmaciones del contexto de la señal
        confirmations = self._extract_confirmations_from_signal(signal, df, symbol)
        
        return self.evaluate_signal(symbol, True, confirmations)
    
    def evaluate_signal(self, symbol: str, setup_valid: bool, 
                       confirmations: List[Tuple[bool, ConfirmationRule]]) -> ScoringResult:
        """Evalúa una señal usando scoring flexible"""
        
        config = self.symbol_config.get(symbol, self.symbol_config['EURUSD'])
        
        if not setup_valid:
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
    
    def _extract_confirmations_from_signal(self, signal: Dict, df: pd.DataFrame, symbol: str) -> List[Tuple[bool, ConfirmationRule]]:
        """Extrae confirmaciones básicas de una señal"""
        confirmations = []
        
        try:
            last = df.iloc[-1]
            
            # Confirmación 1: RSI en rango operativo
            if 'rsi' in df.columns:
                rsi = last['rsi']
                rsi_ok = 30 <= rsi <= 70
                confirmations.append((rsi_ok, ConfirmationRule(
                    "RSI_RANGE", 1.0, f"RSI en rango: {rsi:.1f}"
                )))
            
            # Confirmación 2: ATR adecuado
            if 'atr' in df.columns:
                atr_current = last['atr']
                atr_mean = df['atr'].tail(20).mean()
                atr_ok = atr_current > atr_mean * 0.8
                confirmations.append((atr_ok, ConfirmationRule(
                    "ATR_ADEQUATE", 0.8, f"ATR: {atr_current:.5f} vs {atr_mean:.5f}"
                )))
            
            # Confirmación 3: Dirección de vela
            direction = signal.get('type', 'BUY')
            candle_body = last['close'] - last['open']
            if direction == 'BUY':
                candle_ok = candle_body > 0
            else:
                candle_ok = candle_body < 0
            
            confirmations.append((candle_ok, ConfirmationRule(
                "CANDLE_DIRECTION", 0.6, f"Vela en dirección {direction}"
            )))
            
        except Exception as e:
            logger.warning(f"Error extrayendo confirmaciones: {e}")
        
        return confirmations


# ============================================================================
# SISTEMA DE CONFIANZA INTEGRADO (consolidado de confidence_system.py)
# ============================================================================

@dataclass
class ConfidenceResult:
    """Resultado del sistema de confianza"""
    confidence_level: str
    confidence_score: float
    should_show: bool
    should_execute: bool
    details: Dict

class ConfidenceSystem:
    """Sistema de confianza consolidado"""
    
    def __init__(self):
        self.confidence_thresholds = {
            'VERY_HIGH': 0.85,
            'HIGH': 0.70,
            'MEDIUM-HIGH': 0.60,
            'MEDIUM': 0.50,
            'LOW': 0.30
        }
    
    def calculate_confidence_context(self, context: SignalContext) -> ConfidenceResult:
        """Calcula confianza usando contexto completo"""
        signal = context.raw_signal
        df = context.dataframe
        symbol = context.symbol
        
        # Factores de confianza
        factors = self._calculate_confidence_factors(signal, df, symbol)
        
        # Score ponderado
        confidence_score = sum(factors.values()) / len(factors)
        
        # Determinar nivel
        confidence_level = self._score_to_level(confidence_score)
        
        # Decisiones
        should_show = confidence_score >= 0.40  # Umbral más bajo para mostrar
        should_execute = confidence_score >= 0.65  # Umbral alto para ejecución
        
        return ConfidenceResult(
            confidence_level=confidence_level,
            confidence_score=confidence_score,
            should_show=should_show,
            should_execute=should_execute,
            details={
                'factors': factors,
                'symbol': symbol,
                'thresholds': {
                    'show': 0.40,
                    'execute': 0.65
                }
            }
        )
    
    def _calculate_confidence_factors(self, signal: Dict, df: pd.DataFrame, symbol: str) -> Dict[str, float]:
        """Calcula factores individuales de confianza"""
        factors = {}
        
        try:
            last = df.iloc[-1]
            
            # Factor 1: Calidad del setup (basado en score si existe)
            setup_score = signal.get('score', 0.5)
            factors['setup_quality'] = min(1.0, setup_score)
            
            # Factor 2: Condiciones de mercado
            if 'atr' in df.columns:
                atr_current = last['atr']
                atr_mean = df['atr'].tail(20).mean()
                volatility_factor = min(1.0, atr_current / atr_mean) if atr_mean > 0 else 0.5
                factors['market_volatility'] = volatility_factor
            else:
                factors['market_volatility'] = 0.5
            
            # Factor 3: Fortaleza de la señal (basado en indicadores)
            signal_strength = 0.5
            if 'rsi' in df.columns:
                rsi = last['rsi']
                # RSI extremo = mayor confianza
                if rsi < 30 or rsi > 70:
                    signal_strength = 0.8
                elif 35 <= rsi <= 65:
                    signal_strength = 0.6
            factors['signal_strength'] = signal_strength
            
            # Factor 4: Consistencia temporal
            factors['temporal_consistency'] = 0.7  # Placeholder - podría analizar velas anteriores
            
        except Exception as e:
            logger.warning(f"Error calculando factores de confianza: {e}")
            # Factores por defecto en caso de error
            factors = {
                'setup_quality': 0.5,
                'market_volatility': 0.5,
                'signal_strength': 0.5,
                'temporal_consistency': 0.5
            }
        
        return factors
    
    def _score_to_level(self, score: float) -> str:
        """Convierte score numérico a nivel de confianza"""
        for level, threshold in self.confidence_thresholds.items():
            if score >= threshold:
                return level
        return 'VERY_LOW'


# ============================================================================
# FILTRO DE DUPLICADOS INTEGRADO (consolidado de duplicate_filter.py)
# ============================================================================

class DuplicateFilter:
    """Filtro de duplicados consolidado"""
    
    def __init__(self):
        self.recent_signals = {}  # symbol -> list of recent signals
        self.max_history = 10
        self.time_window_minutes = 30
    
    def is_duplicate(self, signal: Dict, symbol: str) -> Tuple[bool, str]:
        """Verifica si una señal es duplicada"""
        try:
            current_time = datetime.now(timezone.utc)
            
            # Limpiar señales antiguas
            self._cleanup_old_signals(symbol, current_time)
            
            # Obtener señales recientes para este símbolo
            recent = self.recent_signals.get(symbol, [])
            
            # Verificar duplicados
            for recent_signal in recent:
                if self._signals_are_similar(signal, recent_signal['signal']):
                    time_diff = (current_time - recent_signal['timestamp']).total_seconds() / 60
                    return True, f"Similar signal {time_diff:.1f}min ago"
            
            # Agregar señal actual al historial
            if symbol not in self.recent_signals:
                self.recent_signals[symbol] = []
            
            self.recent_signals[symbol].append({
                'signal': signal.copy(),
                'timestamp': current_time
            })
            
            # Mantener solo las más recientes
            if len(self.recent_signals[symbol]) > self.max_history:
                self.recent_signals[symbol] = self.recent_signals[symbol][-self.max_history:]
            
            return False, "Not duplicate"
            
        except Exception as e:
            logger.warning(f"Error verificando duplicados: {e}")
            return False, f"Error: {str(e)}"
    
    def _cleanup_old_signals(self, symbol: str, current_time: datetime):
        """Limpia señales antiguas fuera de la ventana de tiempo"""
        if symbol not in self.recent_signals:
            return
        
        cutoff_time = current_time - timedelta(minutes=self.time_window_minutes)
        self.recent_signals[symbol] = [
            s for s in self.recent_signals[symbol] 
            if s['timestamp'] > cutoff_time
        ]
    
    def _signals_are_similar(self, signal1: Dict, signal2: Dict) -> bool:
        """Compara si dos señales son similares"""
        try:
            # Mismo tipo de operación
            if signal1.get('type') != signal2.get('type'):
                return False
            
            # Precios similares (tolerancia de 5 pips)
            entry1 = float(signal1.get('entry', 0))
            entry2 = float(signal2.get('entry', 0))
            
            # Tolerancia dinámica basada en el precio
            tolerance = entry1 * 0.0005  # 0.05% del precio
            
            if abs(entry1 - entry2) > tolerance:
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"Error comparando señales: {e}")
            return False


# ============================================================================
# INSTANCIA GLOBAL DEL ENGINE
# ============================================================================

# Crear instancia global del engine
trading_engine = TradingEngine()

def get_trading_engine() -> TradingEngine:
    """Obtiene la instancia global del trading engine"""
    return trading_engine