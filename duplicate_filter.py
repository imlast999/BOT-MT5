"""
Sistema de Filtrado de Señales Duplicadas MEJORADO
Maneja la detección y prevención de señales duplicadas con lógica inteligente
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
import logging
import MetaTrader5 as mt5

# Importar el nuevo sistema de cooldown
try:
    from signal_cooldown_manager import signal_cooldown_manager
    COOLDOWN_MANAGER_AVAILABLE = True
except ImportError:
    COOLDOWN_MANAGER_AVAILABLE = False
    signal_cooldown_manager = None

logger = logging.getLogger(__name__)

class DuplicateFilter:
    """Sistema inteligente para filtrar señales duplicadas"""
    
    def __init__(self):
        self.last_signals = {}  # {symbol: {'time': datetime, 'fingerprint': tuple, 'confidence': str, 'price': float, 'zone': str}}
        self.symbol_tolerances = self._load_symbol_tolerances()
        self.symbol_cooldowns = self._load_symbol_cooldowns()
        self.zone_cooldowns = self._load_zone_cooldowns()
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
        """Carga los cooldowns específicos por símbolo - REBALANCEADOS PARA MENOS SPAM"""
        from dotenv import load_dotenv
        load_dotenv()
        
        # Cooldowns específicos por símbolo (en segundos) - MÁS SELECTIVOS
        cooldowns = {
            'EURUSD': int(os.getenv('EURUSD_COOLDOWN', '600')),    # 10 minutos - MÁS SELECTIVO
            'XAUUSD': int(os.getenv('XAUUSD_COOLDOWN', '1200')),   # 20 minutos - ULTRA SELECTIVO
            'BTCEUR': int(os.getenv('BTCEUR_COOLDOWN', '600'))     # 10 minutos - MÁS SELECTIVO
        }
        
        return cooldowns
    
    def _load_zone_cooldowns(self) -> Dict[str, Dict[str, int]]:
        """Carga cooldowns específicos por zona y dirección"""
        return {
            'EURUSD': {
                'BUY': int(os.getenv('EURUSD_BUY_ZONE_COOLDOWN', '900')),   # 15 min por zona BUY
                'SELL': int(os.getenv('EURUSD_SELL_ZONE_COOLDOWN', '900'))  # 15 min por zona SELL
            },
            'XAUUSD': {
                'BUY': int(os.getenv('XAUUSD_BUY_ZONE_COOLDOWN', '1800')),  # 30 min por zona BUY
                'SELL': int(os.getenv('XAUUSD_SELL_ZONE_COOLDOWN', '1800')) # 30 min por zona SELL
            },
            'BTCEUR': {
                'BUY': int(os.getenv('BTCEUR_BUY_ZONE_COOLDOWN', '900')),   # 15 min por zona BUY
                'SELL': int(os.getenv('BTCEUR_SELL_ZONE_COOLDOWN', '900'))  # 15 min por zona SELL
            }
        }
    
    def get_symbol_tolerance(self, symbol: str) -> float:
        """Obtiene la tolerancia para un símbolo específico"""
        return self.symbol_tolerances.get(symbol.upper(), 1.0)
    
    def get_symbol_cooldown(self, symbol: str) -> int:
        """Obtiene el cooldown específico para un símbolo"""
        return self.symbol_cooldowns.get(symbol.upper(), self.base_interval)
    
    def get_zone_cooldown(self, symbol: str, direction: str) -> int:
        """Obtiene el cooldown específico para una zona y dirección"""
        symbol_zones = self.zone_cooldowns.get(symbol.upper(), {})
        return symbol_zones.get(direction.upper(), 900)  # Default 15 min
    
    def calculate_zone(self, symbol: str, price: float) -> str:
        """Calcula la zona lógica de una señal"""
        symbol = symbol.upper()
        
        if symbol == 'XAUUSD':
            # Zonas cada 25 puntos para oro (más granular)
            zone_level = round(price / 25) * 25
            return f"XAUUSD_{zone_level:.0f}"
            
        elif symbol == 'EURUSD':
            # Zonas cada 25 pips para EUR/USD
            zone_level = round(price / 0.0025) * 0.0025
            return f"EURUSD_{zone_level:.4f}"
            
        elif symbol == 'BTCEUR':
            # Zonas cada 500 puntos para BTC
            zone_level = round(price / 500) * 500
            return f"BTCEUR_{zone_level:.0f}"
            
        else:
            # Zona genérica
            return f"{symbol}_{price:.5f}"
    
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
        MEJORADO: Más selectivo para XAUUSD, considera zona además de precio
        """
        symbol = symbol.upper()
        
        if symbol not in self.last_signals:
            return True, None
        
        current_price = float(signal.get('entry', 0))
        current_zone = self.calculate_zone(symbol, current_price)
        current_direction = signal.get('type', '').upper()
        
        last_data = self.last_signals[symbol]
        last_price = last_data.get('price', 0)
        last_zone = last_data.get('zone', '')
        last_direction = last_data.get('direction', '')
        
        if last_price == 0:
            return True, None
        
        # Si es la misma zona y misma dirección, aplicar cooldown estricto
        if current_zone == last_zone and current_direction == last_direction:
            return False, f"Same zone + direction: {current_zone} {current_direction}"
        
        # Calcular distancia mínima requerida según el símbolo - MÁS SELECTIVO
        if symbol == 'XAUUSD':
            # Para XAUUSD: Mínimo 30 puntos de movimiento (MÁS SELECTIVO)
            min_distance = 30.0
            price_diff = abs(current_price - last_price)
            
            if price_diff < min_distance:
                return False, f"Insufficient price movement: {price_diff:.1f} < {min_distance} points"
                
        elif symbol == 'EURUSD':
            # Para EURUSD: Mínimo 10 pips (MÁS SELECTIVO)
            min_distance = 0.0010
            price_diff = abs(current_price - last_price)
            
            if price_diff < min_distance:
                return False, f"Insufficient price movement: {price_diff*10000:.1f} < {min_distance*10000} pips"
                
        elif symbol == 'BTCEUR':
            # Para BTCEUR: Mínimo 300 puntos (MÁS SELECTIVO)
            min_distance = 300.0
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
        Verifica si una señal es duplicada con lógica ULTRA-INTELIGENTE
        
        NUEVA LÓGICA:
        1. Usa el sistema de cooldown inteligente si está disponible
        2. Verifica cooldown general del símbolo
        3. Verifica cooldown específico por dirección
        4. Verifica cooldown por zona
        5. Verifica movimiento de precio suficiente
        6. Verifica similitud de señales
        
        Returns:
            Tuple[is_duplicate, reason]
        """
        now = datetime.now(timezone.utc)
        symbol = symbol.upper()
        direction = signal.get('type', '').upper()
        
        # 1. USAR SISTEMA DE COOLDOWN INTELIGENTE SI ESTÁ DISPONIBLE
        if COOLDOWN_MANAGER_AVAILABLE and signal_cooldown_manager:
            can_signal, block_reason = signal_cooldown_manager.can_signal(signal, symbol)
            if not can_signal:
                return True, f"🚫 COOLDOWN MANAGER: {block_reason}"
        
        # 2. VERIFICAR COOLDOWN GENERAL DEL SÍMBOLO (FALLBACK)
        symbol_cooldown = self.get_symbol_cooldown(symbol)
        
        if symbol in self.last_signals:
            last_signal_data = self.last_signals[symbol]
            last_time = last_signal_data['time']
            time_since_last = (now - last_time).total_seconds()
            
            # Cooldown básico específico por símbolo
            if time_since_last < symbol_cooldown:
                return True, f"🚫 SYMBOL COOLDOWN: {symbol} - {time_since_last:.0f}s < {symbol_cooldown}s"
        
        # 3. VERIFICAR COOLDOWN ESPECÍFICO POR DIRECCIÓN
        direction_cooldown = self.get_zone_cooldown(symbol, direction)
        
        if symbol in self.last_signals:
            last_direction = self.last_signals[symbol].get('direction', '')
            if direction == last_direction:
                time_since_last = (now - self.last_signals[symbol]['time']).total_seconds()
                if time_since_last < direction_cooldown:
                    return True, f"🚫 DIRECTION COOLDOWN: {symbol} {direction} - {time_since_last:.0f}s < {direction_cooldown}s"
        
        # 4. VERIFICAR MOVIMIENTO DE PRECIO SUFICIENTE (INCLUYE ZONA)
        has_movement, movement_reason = self.has_sufficient_price_movement(signal, symbol)
        if not has_movement:
            return True, f"🚫 INSUFFICIENT MOVEMENT: {movement_reason}"
        
        # 5. VERIFICAR SIMILITUD DE SEÑALES (LÓGICA EXISTENTE MEJORADA)
        if symbol in self.last_signals:
            last_fingerprint = self.last_signals[symbol]['fingerprint']
            
            if self.signals_similar(signal, last_fingerprint, symbol):
                time_since_last = (now - self.last_signals[symbol]['time']).total_seconds()
                
                # Cooldown extendido para señales similares - ULTRA LARGO para XAUUSD
                if symbol == 'XAUUSD':
                    extended_cooldown = symbol_cooldown * 3  # 60 minutos para XAUUSD
                else:
                    extended_cooldown = symbol_cooldown * 2  # Otros símbolos
                
                if time_since_last < extended_cooldown:
                    tolerance = self.get_symbol_tolerance(symbol)
                    return True, f"🚫 SIMILAR SIGNAL: {symbol} within {tolerance} tolerance - {time_since_last:.0f}s < {extended_cooldown}s"
        
        return False, None
    
    def register_signal(self, signal: Dict[str, Any], symbol: str, confidence: str):
        """Registra una señal para futuras comparaciones con información completa"""
        now = datetime.now(timezone.utc)
        symbol = symbol.upper()
        direction = signal.get('type', '').upper()
        
        fingerprint = self.create_signal_fingerprint(signal)
        current_price = float(signal.get('entry', 0))
        current_zone = self.calculate_zone(symbol, current_price)
        
        self.last_signals[symbol] = {
            'time': now,
            'fingerprint': fingerprint,
            'confidence': confidence,
            'price': current_price,
            'zone': current_zone,
            'direction': direction  # Añadir dirección para análisis
        }
        
        # Registrar también en el sistema de cooldown inteligente si está disponible
        if COOLDOWN_MANAGER_AVAILABLE and signal_cooldown_manager:
            signal_cooldown_manager.register_signal(signal, symbol, confidence)
        
        logger.info(f"📝 SIGNAL REGISTERED: {symbol} {direction} @ {current_price} in {current_zone} [{confidence}]")
        logger.debug(f"Signal fingerprint: {fingerprint}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del filtro con información mejorada y detallada"""
        stats = {
            'symbols_tracked': len(self.last_signals),
            'tolerances': self.symbol_tolerances,
            'cooldowns': self.symbol_cooldowns,
            'zone_cooldowns': self.zone_cooldowns,
            'base_interval': self.base_interval,
            'cooldown_manager_available': COOLDOWN_MANAGER_AVAILABLE
        }
        
        # Estadísticas por símbolo
        for symbol, data in self.last_signals.items():
            time_since = (datetime.now(timezone.utc) - data['time']).total_seconds()
            cooldown = self.get_symbol_cooldown(symbol)
            direction_cooldown = self.get_zone_cooldown(symbol, data.get('direction', 'BUY'))
            
            stats[f'{symbol}_last_signal'] = {
                'time_since': f"{time_since:.0f}s ago",
                'confidence': data['confidence'],
                'direction': data.get('direction', 'unknown'),
                'zone': data.get('zone', 'unknown'),
                'price': data.get('price', 0),
                'symbol_cooldown': f"{cooldown}s",
                'direction_cooldown': f"{direction_cooldown}s",
                'cooldown_remaining': f"{max(0, cooldown - time_since):.0f}s"
            }
        
        # Estadísticas del sistema de cooldown inteligente si está disponible
        if COOLDOWN_MANAGER_AVAILABLE and signal_cooldown_manager:
            stats['cooldown_manager_stats'] = signal_cooldown_manager.get_stats()
        
        return stats

# Instancia global
duplicate_filter = DuplicateFilter()