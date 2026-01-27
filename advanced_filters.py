"""
Sistema de filtros avanzados para el bot de trading MT5.
Este módulo proporciona filtros de confluencias, sesiones y validaciones adicionales.
"""

import logging
import pandas as pd
from datetime import datetime, timezone
import MetaTrader5 as mt5
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class AdvancedFilterSystem:
    """Sistema de filtros avanzados para validar señales de trading"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.confluence_weights = {
            'trend_alignment': 0.3,
            'support_resistance': 0.25,
            'momentum': 0.2,
            'volume': 0.15,
            'session_timing': 0.1
        }
    
    def apply_filters(self, signal: Dict[str, Any], df: pd.DataFrame, symbol: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Aplica filtros avanzados a una señal de trading
        
        Returns:
            Tuple[bool, str, Dict]: (passed, reason, filter_info)
        """
        try:
            filter_info = {
                'confluence_score': 0.0,
                'session_valid': False,
                'trend_alignment': False,
                'momentum_confirmation': False,
                'volume_confirmation': False
            }
            
            # 1. Validación de sesión
            session_valid = self._validate_session(symbol)
            filter_info['session_valid'] = session_valid
            
            # 2. Alineación de tendencia
            trend_aligned = self._check_trend_alignment(df, signal)
            filter_info['trend_alignment'] = trend_aligned
            
            # 3. Confirmación de momentum
            momentum_confirmed = self._check_momentum(df, signal)
            filter_info['momentum_confirmation'] = momentum_confirmed
            
            # 4. Confirmación de volumen (si disponible)
            volume_confirmed = self._check_volume(df, symbol)
            filter_info['volume_confirmation'] = volume_confirmed
            
            # 5. Calcular score de confluencia
            confluence_score = self._calculate_confluence_score(filter_info)
            filter_info['confluence_score'] = confluence_score
            
            # Umbral mínimo para aprobar filtros
            min_score = 0.6
            passed = confluence_score >= min_score
            
            reason = f"Confluence score: {confluence_score:.2f} ({'PASS' if passed else 'FAIL'})"
            
            return passed, reason, filter_info
            
        except Exception as e:
            self.logger.error(f"Error en filtros avanzados: {e}")
            return False, f"Error en filtros: {str(e)}", {}
    
    def _validate_session(self, symbol: str) -> bool:
        """Valida si estamos en una sesión de trading activa"""
        try:
            now = datetime.now(timezone.utc)
            hour = now.hour
            
            # Sesiones principales (UTC)
            if symbol in ['EURUSD', 'GBPUSD', 'EURGBP']:
                # Sesión europea: 07:00-16:00 UTC
                # Sesión americana: 13:00-22:00 UTC
                return (7 <= hour <= 16) or (13 <= hour <= 22)
            elif symbol in ['XAUUSD']:
                # Oro es más activo durante sesiones de Londres y NY
                return (8 <= hour <= 17) or (13 <= hour <= 22)
            elif symbol in ['BTCEUR', 'BTCUSD']:
                # Crypto opera 24/7, pero más volumen en horarios tradicionales
                return True
            else:
                # Por defecto, sesiones principales
                return (7 <= hour <= 22)
                
        except Exception:
            return True  # Si hay error, no bloquear por sesión
    
    def _check_trend_alignment(self, df: pd.DataFrame, signal: Dict[str, Any]) -> bool:
        """Verifica alineación con la tendencia principal"""
        try:
            if len(df) < 50:
                return True
            
            # Usar EMAs para determinar tendencia
            if 'ema50' in df.columns and 'ema200' in df.columns:
                current_ema50 = df['ema50'].iloc[-1]
                current_ema200 = df['ema200'].iloc[-1]
                
                # Tendencia alcista si EMA50 > EMA200
                uptrend = current_ema50 > current_ema200
                
                signal_type = signal.get('type', '').upper()
                
                # Verificar alineación
                if signal_type == 'BUY' and uptrend:
                    return True
                elif signal_type == 'SELL' and not uptrend:
                    return True
                else:
                    return False
            
            return True  # Si no hay EMAs, no penalizar
            
        except Exception:
            return True
    
    def _check_momentum(self, df: pd.DataFrame, signal: Dict[str, Any]) -> bool:
        """Verifica confirmación de momentum"""
        try:
            if len(df) < 14:
                return True
            
            # Usar RSI para momentum
            if 'rsi' in df.columns:
                current_rsi = df['rsi'].iloc[-1]
                signal_type = signal.get('type', '').upper()
                
                # Para BUY: RSI no debe estar en sobrecompra extrema
                # Para SELL: RSI no debe estar en sobreventa extrema
                if signal_type == 'BUY' and current_rsi < 75:
                    return True
                elif signal_type == 'SELL' and current_rsi > 25:
                    return True
                else:
                    return False
            
            return True
            
        except Exception:
            return True
    
    def _check_volume(self, df: pd.DataFrame, symbol: str) -> bool:
        """Verifica confirmación de volumen si está disponible"""
        try:
            # Para crypto y algunos pares, el volumen puede estar disponible
            if 'volume' in df.columns and len(df) >= 20:
                recent_volume = df['volume'].iloc[-5:].mean()
                avg_volume = df['volume'].iloc[-20:].mean()
                
                # Volumen reciente debe ser al menos 80% del promedio
                return recent_volume >= (avg_volume * 0.8)
            
            # Si no hay datos de volumen, no penalizar
            return True
            
        except Exception:
            return True
    
    def _calculate_confluence_score(self, filter_info: Dict[str, Any]) -> float:
        """Calcula el score de confluencia basado en los filtros"""
        try:
            score = 0.0
            
            # Sesión válida
            if filter_info.get('session_valid', False):
                score += self.confluence_weights['session_timing']
            
            # Alineación de tendencia
            if filter_info.get('trend_alignment', False):
                score += self.confluence_weights['trend_alignment']
            
            # Confirmación de momentum
            if filter_info.get('momentum_confirmation', False):
                score += self.confluence_weights['momentum']
            
            # Confirmación de volumen
            if filter_info.get('volume_confirmation', False):
                score += self.confluence_weights['volume']
            
            # Bonus por soporte/resistencia (simplificado)
            score += self.confluence_weights['support_resistance'] * 0.8
            
            return min(1.0, score)
            
        except Exception:
            return 0.5  # Score neutral en caso de error


def create_advanced_filter_system():
    """Factory function para crear el sistema de filtros avanzados"""
    return AdvancedFilterSystem()


# Instancia global para compatibilidad
advanced_filter_system = None

def get_advanced_filter_system():
    """Obtiene la instancia global del sistema de filtros"""
    global advanced_filter_system
    if advanced_filter_system is None:
        advanced_filter_system = create_advanced_filter_system()
    return advanced_filter_system