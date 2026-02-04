"""
Trading Strategies Module

Provides access to all trading strategies and strategy management functions.
"""

from .base import BaseStrategy
from .eurusd import EURUSDStrategy
from .xauusd import XAUUSDStrategy

# Import BTCEUR conditionally to avoid startup issues
try:
    from .btceur import BTCEURStrategy
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
    strategy_class = STRATEGY_REGISTRY.get(symbol.upper())
    if strategy_class:
        return strategy_class()
    
    # Fallback to EURUSD if symbol not found
    if symbol.upper() != 'EURUSD':
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