"""
BTCEUR Strategy - Estrategia básica para Bitcoin EUR
"""

from typing import Dict, Optional
import pandas as pd
from .base import BaseStrategy

class BTCEURStrategy(BaseStrategy):
    """Estrategia básica BTCEUR"""
    
    def __init__(self):
        super().__init__("BTCEUR_Basic")
    
    def _get_default_config(self) -> Dict:
        return {
            'rsi_period': 14,
            'min_candles': 50
        }
    
    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        """Añade indicadores específicos de BTCEUR"""
        # Para BTCEUR, solo necesitamos RSI adicional
        df['rsi'] = self._rsi(df['close'], config.get('rsi_period', 14))
        return df
    
    def detect_setup(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict]:
        """Detecta setup básico"""
        if len(df) < 50:
            return None
        
        # Setup básico - solo para testing
        last = df.iloc[-1]
        rsi = float(last['rsi'])
        
        if rsi < 30:  # Oversold
            return {
                'symbol': 'BTCEUR',
                'type': 'BUY',
                'entry': float(last['close']),
                'sl': float(last['close']) * 0.98,
                'tp': float(last['close']) * 1.04,
                'confidence': 'LOW',
                'explanation': 'BTCEUR BUY: RSI oversold',
                'strategy': 'btceur_basic'
            }
        elif rsi > 70:  # Overbought
            return {
                'symbol': 'BTCEUR',
                'type': 'SELL',
                'entry': float(last['close']),
                'sl': float(last['close']) * 1.02,
                'tp': float(last['close']) * 0.96,
                'confidence': 'LOW',
                'explanation': 'BTCEUR SELL: RSI overbought',
                'strategy': 'btceur_basic'
            }
        
        return None

def create_btceur_strategy() -> 'BTCEURStrategy':
    """Factory function para crear estrategia BTCEUR"""
    return BTCEURStrategy()