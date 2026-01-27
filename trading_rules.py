"""
Sistema de reglas de trading y filtros avanzados.
Este módulo maneja las reglas de ejecución y validación de señales.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class AdvancedFilter:
    """Filtro avanzado para validar señales antes de la ejecución"""
    
    def __init__(self):
        self.enabled = os.getenv('ADVANCED_FILTERS', '0') == '1'
        self.logger = logging.getLogger(__name__)
        
    def should_execute(self, signal: Dict[str, Any], current_balance: float = 0.0) -> Tuple[bool, str]:
        """
        Determina si una señal debe ejecutarse basado en reglas avanzadas
        
        Args:
            signal: Diccionario con información de la señal
            current_balance: Balance actual de la cuenta
            
        Returns:
            Tuple[bool, str]: (should_execute, reason)
        """
        if not self.enabled:
            return True, "Filtros avanzados desactivados"
        
        try:
            # 1. Verificar información básica de la señal
            if not self._validate_signal_structure(signal):
                return False, "Estructura de señal inválida"
            
            # 2. Verificar horario de trading
            if not self._validate_trading_hours(signal.get('symbol', '')):
                return False, "Fuera de horario de trading"
            
            # 3. Verificar riesgo/recompensa
            if not self._validate_risk_reward(signal):
                return False, "Ratio riesgo/recompensa insuficiente"
            
            # 4. Verificar balance y gestión de riesgo
            if current_balance > 0 and not self._validate_risk_management(signal, current_balance):
                return False, "Gestión de riesgo no cumplida"
            
            return True, "Todos los filtros pasados"
            
        except Exception as e:
            self.logger.error(f"Error en filtros avanzados: {e}")
            return False, f"Error en validación: {str(e)}"
    
    def _validate_signal_structure(self, signal: Dict[str, Any]) -> bool:
        """Valida que la señal tenga la estructura correcta"""
        required_fields = ['symbol', 'type', 'entry', 'sl', 'tp']
        
        for field in required_fields:
            if field not in signal or signal[field] is None:
                return False
        
        # Verificar que los precios sean números válidos
        try:
            float(signal['entry'])
            float(signal['sl'])
            float(signal['tp'])
        except (ValueError, TypeError):
            return False
        
        return True
    
    def _validate_trading_hours(self, symbol: str) -> bool:
        """Valida si estamos en horario de trading para el símbolo"""
        try:
            now = datetime.now(timezone.utc)
            hour = now.hour
            weekday = now.weekday()  # 0=Monday, 6=Sunday
            
            # No operar en fin de semana para Forex
            if symbol in ['EURUSD', 'GBPUSD', 'XAUUSD'] and weekday >= 5:
                return False
            
            # Horarios por símbolo (UTC)
            if symbol in ['EURUSD', 'GBPUSD']:
                # Forex: Domingo 22:00 - Viernes 22:00
                if weekday == 6 and hour < 22:  # Domingo antes de las 22:00
                    return False
                if weekday == 4 and hour >= 22:  # Viernes después de las 22:00
                    return False
                return True
            elif symbol == 'XAUUSD':
                # Oro similar a Forex pero con horarios ligeramente diferentes
                return True
            elif symbol in ['BTCEUR', 'BTCUSD']:
                # Crypto opera 24/7
                return True
            else:
                # Por defecto, permitir trading
                return True
                
        except Exception:
            return True  # En caso de error, no bloquear
    
    def _validate_risk_reward(self, signal: Dict[str, Any]) -> bool:
        """Valida que el ratio riesgo/recompensa sea aceptable"""
        try:
            entry = float(signal['entry'])
            sl = float(signal['sl'])
            tp = float(signal['tp'])
            
            # Calcular distancias
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            
            if risk <= 0:
                return False
            
            # Ratio mínimo de 1.5:1
            rr_ratio = reward / risk
            min_rr = 1.5
            
            return rr_ratio >= min_rr
            
        except (ValueError, TypeError, ZeroDivisionError):
            return False
    
    def _validate_risk_management(self, signal: Dict[str, Any], current_balance: float) -> bool:
        """Valida gestión de riesgo basada en el balance actual"""
        try:
            # Riesgo máximo por trade (por defecto 2%)
            max_risk_pct = float(os.getenv('MAX_RISK_PCT', '2.0'))
            max_risk_amount = current_balance * (max_risk_pct / 100.0)
            
            # Calcular riesgo de la señal (simplificado)
            entry = float(signal['entry'])
            sl = float(signal['sl'])
            risk_points = abs(entry - sl)
            
            # Para una estimación básica, asumimos 1 lote estándar
            # En la práctica, esto debería calcularse con el tamaño de lote real
            estimated_risk = risk_points * 100000  # Aproximación para EURUSD
            
            return estimated_risk <= max_risk_amount
            
        except Exception:
            return True  # En caso de error, no bloquear por gestión de riesgo


def create_advanced_filter():
    """Factory function para crear el filtro avanzado"""
    return AdvancedFilter()


def should_execute_signal(signal: Dict[str, Any], current_balance: float = 0.0) -> Tuple[bool, str]:
    """
    Función de conveniencia para verificar si una señal debe ejecutarse
    
    Args:
        signal: Diccionario con información de la señal
        current_balance: Balance actual de la cuenta
        
    Returns:
        Tuple[bool, str]: (should_execute, reason)
    """
    filter_instance = create_advanced_filter()
    return filter_instance.should_execute(signal, current_balance)


# Instancia global para compatibilidad
advanced_filter = None

def get_advanced_filter():
    """Obtiene la instancia global del filtro avanzado"""
    global advanced_filter
    if advanced_filter is None:
        advanced_filter = create_advanced_filter()
    return advanced_filter