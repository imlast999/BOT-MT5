"""
Trading Strategies Module

Provides access to all trading strategies and strategy management functions.
"""

import logging
from .base import BaseStrategy

logger = logging.getLogger(__name__)
from .eurusd import EURUSDStrategy
from .xauusd import XAUUSDStrategy

# Import BTCEUR desde la implementación oficial (btceur_new.py)
# Este es ahora el ÚNICO origen de la estrategia BTCEUR en el sistema.
try:
    from .btceur_new import BTCEURStrategy
    BTCEUR_AVAILABLE = True
except ImportError as e:
    print(f"Warning: BTCEURStrategy not available: {e}")
    BTCEURStrategy = None
    BTCEUR_AVAILABLE = False

# Strategy registry
STRATEGY_REGISTRY = {
    'EURUSD': EURUSDStrategy,
    'XAUUSD': XAUUSDStrategy,
}

# Add BTCEUR only if available
if BTCEUR_AVAILABLE:
    STRATEGY_REGISTRY['BTCEUR'] = BTCEURStrategy

def get_strategy(symbol: str):
    """
    Get strategy instance for a given symbol
    
    Args:
        symbol: Trading symbol (e.g., 'EURUSD', 'XAUUSD', 'BTCEUR')
        
    Returns:
        Strategy instance or None if not found
    """
    symbol_upper = symbol.upper()
    strategy_class = STRATEGY_REGISTRY.get(symbol_upper)

    # Estrategia registrada correctamente
    if strategy_class:
        return strategy_class()

    # PROTECCIÓN BTCEUR: nunca hacer fallback silencioso a EURUSD
    if symbol_upper == 'BTCEUR':
        err_msg = "Estrategia no disponible (BTCEUR no registrado o import fallido)."
        logger.error("[CRITICAL][BTCEUR] %s", err_msg)
        try:
            from core import set_btceur_health
            set_btceur_health(status="ERROR", last_error=err_msg)
        except Exception:
            pass
        return None
    
    # Fallback genérico a EURUSD solo para otros símbolos
    if symbol_upper != 'EURUSD':
        print(f"Warning: Strategy for {symbol} not found, using EURUSD as fallback")
        return EURUSDStrategy()
    
    return None

def get_available_symbols():
    """Get list of symbols with available strategies"""
    return list(STRATEGY_REGISTRY.keys())

def register_strategy(symbol: str, strategy_class):
    """Register a new strategy for a symbol"""
    STRATEGY_REGISTRY[symbol.upper()] = strategy_class

__all__ = [
    'BaseStrategy',
    'EURUSDStrategy', 
    'XAUUSDStrategy',
    'get_strategy',
    'get_available_symbols',
    'register_strategy',
    'STRATEGY_REGISTRY'
]

# Add BTCEURStrategy to exports only if available
if BTCEUR_AVAILABLE:
    __all__.append('BTCEURStrategy')