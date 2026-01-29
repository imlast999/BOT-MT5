"""
Sistema de Filtrado de Señales Duplicadas
Maneja la detección y prevención de señales duplicadas
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
import logging
import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

class DuplicateFilter:
    """Sistema para filtrar señales duplicadas"""
    
    def __init__(self):
        self.last_signals = {}  # {symbol: {'time': datetime, 'fingerprint': tuple, 'confidence': str, 'price': float}}
        self.symbol_tolerances = self._load_symbol_tolerances()
        self.symbol_cooldowns = self._load_symbol_cooldowns()
        self.base_interval = int(os.getenv('AUTOSIGNAL_INTERVAL', '90'))
    
    def _load_symbol_tolerances(self) -> Dict[str, float]:
        """Carga las tolerancias específicas por símbolo"""
        from dotenv import load_dotenv
        load_dotenv()  # Asegurar que las variables estén cargadas
        
        default_tolerance = float(os.getenv('AUTOSIGNAL_TOLERANCE_PIPS', '1.0'))
        
        tolerances = {}
        symbols = ['EURUSD', 'XAUUSD', 'BTCEUR', 'GBPUSD', 'USDJPY']
        
        for symbol in symbols:
            tolerance_key = f"{symbol}_TOLERANCE_PIPS"
            tolerances[symbol] = float(os.getenv(tolerance_key, default_tolerance))
        
        return tolerances
    
    def _load_symbol_cooldowns(self) -> Dict[str, int]:
        """Carga los cooldowns específicos por símbolo"""
        from dotenv import load_dotenv
        load_dotenv()
        
        # Cooldowns específicos por símbolo (en segundos)
        cooldowns = {
            'EURUSD': int(os.getenv('EURUSD_COOLDOWN', '90')),    # 1.5 minutos
            'XAUUSD': int(os.getenv('XAUUSD_COOLDOWN', '300')),   # 5 minutos - MÁS SELECTIVO
            'BTCEUR': int(os.getenv('BTCEUR_COOLDOWN', '180'))    # 3 minutos
        }
        
        return cooldowns
    
    def get_symbol_tolerance(self, symbol: str) -> float:
        """Obtiene la tolerancia para un símbolo específico"""
        return self.symbol_tolerances.get(symbol.upper(), 1.0)
    
    def get_symbol_cooldown(self, symbol: str) -> int:
        """Obtiene el cooldown específico para un símbolo"""
        return self.symbol_cooldowns.get(symbol.upper(), self.base_interval)
    
    def create_signal_fingerprint(self, signal: Dict[str, Any]) -> Tuple:
        """Crea una huella digital de la señal para comparación"""
        return (
            signal.get('type'),
            float(signal.get('entry', 0)),
            float(signal.get('sl', 0)),
            float(signal.get('tp', 0))
        )
    
    def has_sufficient_price_movement(self, signal: Dict[str, Any], symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Verifica si hay suficiente movimiento de precio desde la última señal
        Especialmente importante para XAUUSD para evitar micro-movimientos
        """
        symbol = symbol.upper()
        
        if symbol not in self.last_signals:
            return True, None
        
        current_price = float(signal.get('entry', 0))
        last_price = self.last_signals[symbol].get('price', 0)
        
        if last_price == 0:
            return True, None
        
        # Calcular distancia mínima requerida según el símbolo
        if symbol == 'XAUUSD':
            # Para XAUUSD: Mínimo 15 puntos de movimiento (más selectivo)
            min_distance = 15.0
            price_diff = abs(current_price - last_price)
            
            if price_diff < min_distance:
                return False, f"Insufficient price movement: {price_diff:.1f} < {min_distance} points"
                
        elif symbol == 'EURUSD':
            # Para EURUSD: Mínimo 8 pips
            min_distance = 0.0008
            price_diff = abs(current_price - last_price)
            
            if price_diff < min_distance:
                return False, f"Insufficient price movement: {price_diff*10000:.1f} < {min_distance*10000} pips"
                
        elif symbol == 'BTCEUR':
            # Para BTCEUR: Mínimo 200 puntos
            min_distance = 200.0
            price_diff = abs(current_price - last_price)
            
            if price_diff < min_distance:
                return False, f"Insufficient price movement: {price_diff:.0f} < {min_distance} points"
        
        return True, None
    
    def signals_similar(self, signal: Dict[str, Any], last_fingerprint: Tuple, symbol: str) -> bool:
        """
        Compara si dos señales son similares dentro de la tolerancia
        """
        if not last_fingerprint:
            return False
        
        try:
            # Obtener información del símbolo para calcular el point
            si = mt5.symbol_info(symbol)
            point = float(getattr(si, 'point', 0.0001)) if si is not None else 0.0001
        except Exception:
            # Valores por defecto según el tipo de símbolo
            if 'XAU' in symbol.upper() or 'GOLD' in symbol.upper():
                point = 0.01  # Para oro
            elif 'BTC' in symbol.upper():
                point = 1.0   # Para Bitcoin
            else:
                point = 0.0001  # Para forex
        
        # Obtener tolerancia específica del símbolo
        tolerance_pips = self.get_symbol_tolerance(symbol)
        tolerance_value = tolerance_pips * point
        
        # Crear fingerprint de la señal actual
        current_fingerprint = self.create_signal_fingerprint(signal)
        
        # Comparar tipo
        if current_fingerprint[0] != last_fingerprint[0]:
            logger.debug(f"Signal types differ: {current_fingerprint[0]} vs {last_fingerprint[0]}")
            return False
        
        # Comparar precios con tolerancia
        entry_diff = abs(current_fingerprint[1] - last_fingerprint[1])
        sl_diff = abs(current_fingerprint[2] - last_fingerprint[2])
        tp_diff = abs(current_fingerprint[3] - last_fingerprint[3])
        
        logger.debug(f"Comparing {symbol}: entry_diff={entry_diff:.5f}, tolerance={tolerance_value:.5f}")
        
        # Si cualquier precio difiere más que la tolerancia, no es duplicado
        if entry_diff > tolerance_value or sl_diff > tolerance_value or tp_diff > tolerance_value:
            return False
        
        return True
    
    def is_duplicate(self, signal: Dict[str, Any], symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Verifica si una señal es duplicada con lógica mejorada para XAUUSD
        
        Returns:
            Tuple[is_duplicate, reason]
        """
        now = datetime.now(timezone.utc)
        symbol = symbol.upper()
        
        # 1. Verificar cooldown específico del símbolo
        symbol_cooldown = self.get_symbol_cooldown(symbol)
        
        if symbol in self.last_signals:
            last_signal_data = self.last_signals[symbol]
            last_time = last_signal_data['time']
            time_since_last = (now - last_time).total_seconds()
            
            # Cooldown básico específico por símbolo
            if time_since_last < symbol_cooldown:
                return True, f"Cooldown active: {time_since_last:.0f}s < {symbol_cooldown}s"
        
        # 2. Verificar movimiento de precio suficiente
        has_movement, movement_reason = self.has_sufficient_price_movement(signal, symbol)
        if not has_movement:
            return True, movement_reason
        
        # 3. Verificar similitud de señales (lógica existente mejorada)
        if symbol in self.last_signals:
            last_fingerprint = self.last_signals[symbol]['fingerprint']
            
            if self.signals_similar(signal, last_fingerprint, symbol):
                # Cooldown extendido para señales similares - más largo para XAUUSD
                if symbol == 'XAUUSD':
                    extended_cooldown = symbol_cooldown * 8  # 40 minutos para XAUUSD
                else:
                    extended_cooldown = symbol_cooldown * 4  # Otros símbolos
                
                if time_since_last < extended_cooldown:
                    tolerance = self.get_symbol_tolerance(symbol)
                    return True, f"Similar signal within {tolerance} pips (last: {time_since_last:.0f}s ago, need: {extended_cooldown}s)"
        
        return False, None
    
    def register_signal(self, signal: Dict[str, Any], symbol: str, confidence: str):
        """Registra una señal para futuras comparaciones con precio incluido"""
        now = datetime.now(timezone.utc)
        symbol = symbol.upper()
        
        fingerprint = self.create_signal_fingerprint(signal)
        current_price = float(signal.get('entry', 0))
        
        self.last_signals[symbol] = {
            'time': now,
            'fingerprint': fingerprint,
            'confidence': confidence,
            'price': current_price,  # Añadir precio para verificar movimiento
            'type': signal.get('type', 'UNKNOWN')  # Añadir tipo para análisis
        }
        
        logger.debug(f"Registered signal for {symbol}: {fingerprint} at price {current_price}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del filtro con información mejorada"""
        stats = {
            'symbols_tracked': len(self.last_signals),
            'tolerances': self.symbol_tolerances,
            'cooldowns': self.symbol_cooldowns,
            'base_interval': self.base_interval
        }
        
        for symbol, data in self.last_signals.items():
            time_since = (datetime.now(timezone.utc) - data['time']).total_seconds()
            cooldown = self.get_symbol_cooldown(symbol)
            stats[f'{symbol}_last_signal'] = f"{time_since:.0f}s ago ({data['confidence']}) - Cooldown: {cooldown}s"
        
        return stats

# Instancia global
duplicate_filter = DuplicateFilter()