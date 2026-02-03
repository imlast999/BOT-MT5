"""
Signals Dispatcher - Versión Refactorizada

Este archivo ahora actúa SOLO como dispatcher de estrategias.
Toda la lógica compleja se ha movido a:
- core/engine.py (orquestación)
- core/scoring.py (scoring)
- core/filters.py (filtros)
- strategies/ (estrategias específicas)
"""

import logging
from typing import Dict, Optional, Tuple
import pandas as pd

# Imports del core refactorizado
from core.engine import get_trading_engine
from strategies.eurusd import create_eurusd_strategy
from strategies.xauusd import create_xauusd_strategy  # Asumiendo que existe
from strategies.btceur import create_btceur_strategy  # Asumiendo que existe

logger = logging.getLogger(__name__)

# Registry de estrategias disponibles
STRATEGY_REGISTRY = {
    'ema50_200': lambda: create_eurusd_strategy(advanced=False),
    'eurusd': lambda: create_eurusd_strategy(advanced=False),
    'eurusd_advanced': lambda: create_eurusd_strategy(advanced=True),
    'xauusd': lambda: create_xauusd_strategy(),
    'xauusd_advanced': lambda: create_xauusd_strategy(advanced=True),
    'btceur': lambda: create_btceur_strategy(),
    'btcusdt': lambda: create_btceur_strategy(),  # Alias
    
    # Estrategias genéricas (fallback)
    'rsi': lambda: create_eurusd_strategy(advanced=False),  # Usar EURUSD como fallback
    'macd': lambda: create_eurusd_strategy(advanced=False),  # Usar EURUSD como fallback
}

def detect_signal(df: pd.DataFrame, strategy: str = 'ema50_200', config: dict = None) -> Tuple[Optional[Dict], pd.DataFrame]:
    """
    Dispatcher principal de detección de señales
    
    Args:
        df: DataFrame con datos OHLCV
        strategy: Nombre de la estrategia a usar
        config: Configuración específica (opcional)
        
    Returns:
        (signal_dict or None, df_with_indicators)
    """
    try:
        # Validar datos básicos
        if df is None or len(df) < 10:
            logger.debug(f"Datos insuficientes para {strategy}: {len(df) if df is not None else 0} velas")
            return None, df
        
        # Obtener estrategia del registry
        strategy_name = (strategy or 'ema50_200').lower()
        strategy_factory = STRATEGY_REGISTRY.get(strategy_name)
        
        if strategy_factory is None:
            # Fallback a estrategia por defecto
            logger.warning(f"Estrategia {strategy_name} no encontrada, usando EURUSD por defecto")
            strategy_factory = STRATEGY_REGISTRY['eurusd']
        
        # Crear instancia de la estrategia
        strategy_instance = strategy_factory()
        
        # Detectar señal usando la estrategia
        df_with_indicators = strategy_instance.add_indicators(df, config)
        signal = strategy_instance.detect_setup(df_with_indicators, config)
        
        if signal:
            logger.debug(f"Señal detectada con {strategy_name}: {signal['type']} {signal.get('symbol', 'UNKNOWN')}")
        else:
            logger.debug(f"No hay señal con {strategy_name}")
        
        return signal, df_with_indicators
        
    except Exception as e:
        logger.error(f"Error en detect_signal con estrategia {strategy}: {e}")
        return None, df

def detect_signal_advanced(df: pd.DataFrame, strategy: str = 'ema50_200', 
                          config: dict = None, current_balance: float = 5000.0, 
                          symbol: str = 'EURUSD') -> Tuple[Optional[Dict], pd.DataFrame, Dict]:
    """
    Versión avanzada que usa el trading engine completo
    
    Args:
        df: DataFrame con datos OHLCV
        strategy: Nombre de la estrategia
        config: Configuración específica
        current_balance: Balance actual (para cálculos de riesgo)
        symbol: Símbolo del instrumento
        
    Returns:
        (signal_dict or None, df_with_indicators, evaluation_info)
    """
    try:
        # Usar el trading engine para evaluación completa
        trading_engine = get_trading_engine()
        
        # Evaluar señal con pipeline completo
        result = trading_engine.evaluate_signal(df, symbol, strategy, config)
        
        # Extraer información para compatibilidad
        if result.signal:
            evaluation_info = {
                'approved': result.should_show,
                'strategy_used': strategy,
                'confidence': result.confidence,
                'score': result.score,
                'should_show': result.should_show,
                'can_auto_execute': result.should_execute,
                'rejection_reason': result.rejection_reason,
                'details': result.details
            }
            
            return result.signal, df, evaluation_info
        else:
            evaluation_info = {
                'approved': False,
                'strategy_used': strategy,
                'confidence': 'NONE',
                'score': 0.0,
                'should_show': False,
                'can_auto_execute': False,
                'rejection_reason': result.rejection_reason,
                'details': result.details
            }
            
            return None, df, evaluation_info
            
    except Exception as e:
        logger.error(f"Error en detect_signal_advanced: {e}")
        return None, df, {'error': str(e), 'approved': False}

def get_available_strategies() -> Dict[str, str]:
    """
    Obtiene lista de estrategias disponibles
    
    Returns:
        Dict con nombre -> descripción de estrategias
    """
    return {
        'ema50_200': 'EMA 50/200 Crossover (EURUSD)',
        'eurusd': 'EURUSD Breakout Strategy',
        'eurusd_advanced': 'EURUSD Advanced Multi-Timeframe',
        'xauusd': 'XAUUSD Reversal Strategy',
        'xauusd_advanced': 'XAUUSD Advanced Ultra-Selective',
        'btceur': 'BTCEUR Momentum Strategy',
        'rsi': 'RSI Reversal (Generic)',
        'macd': 'MACD Crossover (Generic)'
    }

def register_strategy(name: str, strategy_factory):
    """
    Registra una nueva estrategia
    
    Args:
        name: Nombre de la estrategia
        strategy_factory: Factory function que retorna instancia de estrategia
    """
    STRATEGY_REGISTRY[name.lower()] = strategy_factory
    logger.info(f"Estrategia {name} registrada exitosamente")

# Funciones de compatibilidad con el código existente
def _detect_signal_wrapper(df: pd.DataFrame, symbol: str = None):
    """
    Wrapper de compatibilidad para el código existente en bot.py
    
    Esta función mantiene la interfaz original pero usa el nuevo sistema.
    """
    try:
        # Determinar estrategia basada en símbolo
        sym = (symbol or 'EURUSD').upper()
        
        if sym == 'EURUSD':
            strategy = 'eurusd_advanced'
        elif sym == 'XAUUSD':
            strategy = 'xauusd_advanced'
        elif sym in ['BTCEUR', 'BTCUSDT']:
            strategy = 'btceur'
        else:
            strategy = 'ema50_200'  # Fallback
        
        # Usar detect_signal_advanced para evaluación completa
        signal, df_processed, evaluation_info = detect_signal_advanced(
            df, strategy=strategy, symbol=sym
        )
        
        return signal, df_processed, evaluation_info
        
    except Exception as e:
        logger.error(f"Error en _detect_signal_wrapper para {symbol}: {e}")
        return None, df, {'approved': False, 'reason': f'Error: {str(e)}'}

# Mantener compatibilidad con imports existentes
SYMBOL = "EURUSD"  # Para compatibilidad

# Funciones auxiliares que pueden estar siendo usadas
def _rsi(series: pd.Series, period: int = 14):
    """RSI calculation for compatibility"""
    delta = series.diff()
    up = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    down = -delta.clip(upper=0).ewm(alpha=1/period, adjust=False).mean()
    rs = up / down.replace(0, pd.np.nan)
    return 100 - (100 / (1 + rs))

def _atr(df: pd.DataFrame, period: int = 14):
    """ATR calculation for compatibility"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()

# Log de inicialización
logger.info(f"Signals dispatcher inicializado con {len(STRATEGY_REGISTRY)} estrategias disponibles")