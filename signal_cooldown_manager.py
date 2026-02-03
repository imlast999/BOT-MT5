"""
Sistema de Cooldown Inteligente para Señales
Gestiona cooldowns por símbolo, dirección y zona para evitar spam
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple, Set
import logging
import json

logger = logging.getLogger(__name__)

class SignalCooldownManager:
    """Sistema inteligente de cooldown para señales de trading"""
    
    def __init__(self):
        self.last_signals = {}  # {symbol: {direction: {time, price, zone, confidence}}}
        self.zone_cooldowns = {}  # {symbol: {zone: {direction: time}}}
        self.symbol_cooldowns = self._load_symbol_cooldowns()
        self.direction_cooldowns = self._load_direction_cooldowns()
        self.zone_tolerances = self._load_zone_tolerances()
        
    def _load_symbol_cooldowns(self) -> Dict[str, int]:
        """Cooldowns generales por símbolo (segundos)"""
        return {
            'EURUSD': int(os.getenv('EURUSD_COOLDOWN', '600')),    # 10 min
            'XAUUSD': int(os.getenv('XAUUSD_COOLDOWN', '1200')),   # 20 min - MÁS SELECTIVO
            'BTCEUR': int(os.getenv('BTCEUR_COOLDOWN', '600'))     # 10 min
        }
    
    def _load_direction_cooldowns(self) -> Dict[str, Dict[str, int]]:
        """Cooldowns específicos por dirección (BUY/SELL)"""
        return {
            'EURUSD': {
                'BUY': int(os.getenv('EURUSD_BUY_COOLDOWN', '900')),   # 15 min
                'SELL': int(os.getenv('EURUSD_SELL_COOLDOWN', '900'))  # 15 min
            },
            'XAUUSD': {
                'BUY': int(os.getenv('XAUUSD_BUY_COOLDOWN', '1800')),  # 30 min - MUY SELECTIVO
                'SELL': int(os.getenv('XAUUSD_SELL_COOLDOWN', '1800')) # 30 min - MUY SELECTIVO
            },
            'BTCEUR': {
                'BUY': int(os.getenv('BTCEUR_BUY_COOLDOWN', '900')),   # 15 min
                'SELL': int(os.getenv('BTCEUR_SELL_COOLDOWN', '900'))  # 15 min
            }
        }
    
    def _load_zone_tolerances(self) -> Dict[str, float]:
        """Tolerancias para considerar la misma zona"""
        return {
            'EURUSD': 0.0020,   # 20 pips
            'XAUUSD': 15.0,     # 15 puntos
            'BTCEUR': 500.0     # 500 puntos
        }
    
    def _calculate_zone(self, symbol: str, price: float) -> str:
        """Calcula la zona lógica de una señal"""
        symbol = symbol.upper()
        
        if symbol == 'XAUUSD':
            # Zonas cada 50 puntos para oro
            zone_level = round(price / 50) * 50
            return f"XAUUSD_{zone_level:.0f}"
            
        elif symbol == 'EURUSD':
            # Zonas cada 50 pips para EUR/USD
            zone_level = round(price / 0.0050) * 0.0050
            return f"EURUSD_{zone_level:.4f}"
            
        elif symbol == 'BTCEUR':
            # Zonas cada 1000 puntos para BTC
            zone_level = round(price / 1000) * 1000
            return f"BTCEUR_{zone_level:.0f}"
            
        else:
            # Zona genérica
            return f"{symbol}_{price:.5f}"
    
    def _is_same_zone(self, symbol: str, price1: float, price2: float) -> bool:
        """Verifica si dos precios están en la misma zona"""
        tolerance = self.zone_tolerances.get(symbol.upper(), 0.001)
        return abs(price1 - price2) <= tolerance
    
    def can_signal(self, signal: Dict[str, Any], symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Verifica si una señal puede ser enviada según los cooldowns
        
        Returns:
            Tuple[can_send, block_reason]
        """
        now = datetime.now(timezone.utc)
        symbol = symbol.upper()
        direction = signal.get('type', 'UNKNOWN').upper()
        price = float(signal.get('entry', 0))
        zone = self._calculate_zone(symbol, price)
        
        # 1. Verificar cooldown general del símbolo
        general_cooldown = self.symbol_cooldowns.get(symbol, 600)
        if symbol in self.last_signals:
            for dir_data in self.last_signals[symbol].values():
                last_time = dir_data.get('time')
                if last_time:
                    time_since = (now - last_time).total_seconds()
                    if time_since < general_cooldown:
                        return False, f"Symbol cooldown active: {time_since:.0f}s < {general_cooldown}s"
        
        # 2. Verificar cooldown específico por dirección
        direction_cooldowns = self.direction_cooldowns.get(symbol, {})
        direction_cooldown = direction_cooldowns.get(direction, 900)
        
        if (symbol in self.last_signals and 
            direction in self.last_signals[symbol]):
            
            last_dir_data = self.last_signals[symbol][direction]
            last_time = last_dir_data.get('time')
            
            if last_time:
                time_since = (now - last_time).total_seconds()
                if time_since < direction_cooldown:
                    return False, f"Direction cooldown active: {symbol} {direction} - {time_since:.0f}s < {direction_cooldown}s"
        
        # 3. Verificar cooldown por zona
        if symbol in self.zone_cooldowns and zone in self.zone_cooldowns[symbol]:
            zone_data = self.zone_cooldowns[symbol][zone].get(direction)
            if zone_data:
                time_since = (now - zone_data).total_seconds()
                zone_cooldown = direction_cooldown * 2  # Cooldown de zona es 2x el de dirección
                
                if time_since < zone_cooldown:
                    return False, f"Zone cooldown active: {zone} {direction} - {time_since:.0f}s < {zone_cooldown}s"
        
        # 4. Verificar si es la misma zona que la última señal (independiente de dirección)
        if symbol in self.last_signals:
            for last_direction, dir_data in self.last_signals[symbol].items():
                last_price = dir_data.get('price', 0)
                last_time = dir_data.get('time')
                
                if (last_price > 0 and last_time and 
                    self._is_same_zone(symbol, price, last_price)):
                    
                    time_since = (now - last_time).total_seconds()
                    same_zone_cooldown = direction_cooldown // 2  # Cooldown reducido para misma zona
                    
                    if time_since < same_zone_cooldown:
                        return False, f"Same zone recent activity: {zone} - {time_since:.0f}s < {same_zone_cooldown}s"
        
        return True, None
    
    def register_signal(self, signal: Dict[str, Any], symbol: str, confidence: str):
        """Registra una señal en el sistema de cooldown"""
        now = datetime.now(timezone.utc)
        symbol = symbol.upper()
        direction = signal.get('type', 'UNKNOWN').upper()
        price = float(signal.get('entry', 0))
        zone = self._calculate_zone(symbol, price)
        
        # Inicializar estructuras si no existen
        if symbol not in self.last_signals:
            self.last_signals[symbol] = {}
        
        if symbol not in self.zone_cooldowns:
            self.zone_cooldowns[symbol] = {}
        
        if zone not in self.zone_cooldowns[symbol]:
            self.zone_cooldowns[symbol][zone] = {}
        
        # Registrar señal por dirección
        self.last_signals[symbol][direction] = {
            'time': now,
            'price': price,
            'zone': zone,
            'confidence': confidence
        }
        
        # Registrar cooldown de zona
        self.zone_cooldowns[symbol][zone][direction] = now
        
        logger.info(f"Signal registered: {symbol} {direction} @ {price} in {zone} [{confidence}]")
    
    def get_cooldown_status(self, symbol: str) -> Dict[str, Any]:
        """Obtiene el estado actual de cooldowns para un símbolo"""
        now = datetime.now(timezone.utc)
        symbol = symbol.upper()
        status = {
            'symbol': symbol,
            'general_cooldown': self.symbol_cooldowns.get(symbol, 600),
            'direction_cooldowns': self.direction_cooldowns.get(symbol, {}),
            'last_signals': {},
            'zone_status': {}
        }
        
        # Estado de últimas señales por dirección
        if symbol in self.last_signals:
            for direction, data in self.last_signals[symbol].items():
                last_time = data.get('time')
                if last_time:
                    time_since = (now - last_time).total_seconds()
                    cooldown_remaining = max(0, self.direction_cooldowns.get(symbol, {}).get(direction, 900) - time_since)
                    
                    status['last_signals'][direction] = {
                        'time_since': f"{time_since:.0f}s",
                        'cooldown_remaining': f"{cooldown_remaining:.0f}s",
                        'zone': data.get('zone', 'unknown'),
                        'price': data.get('price', 0),
                        'confidence': data.get('confidence', 'unknown')
                    }
        
        # Estado de zonas
        if symbol in self.zone_cooldowns:
            for zone, directions in self.zone_cooldowns[symbol].items():
                status['zone_status'][zone] = {}
                for direction, zone_time in directions.items():
                    time_since = (now - zone_time).total_seconds()
                    zone_cooldown = self.direction_cooldowns.get(symbol, {}).get(direction, 900) * 2
                    cooldown_remaining = max(0, zone_cooldown - time_since)
                    
                    status['zone_status'][zone][direction] = {
                        'time_since': f"{time_since:.0f}s",
                        'cooldown_remaining': f"{cooldown_remaining:.0f}s"
                    }
        
        return status
    
    def cleanup_old_entries(self, max_age_hours: int = 24):
        """Limpia entradas antiguas para evitar acumulación de memoria"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        
        # Limpiar last_signals
        for symbol in list(self.last_signals.keys()):
            for direction in list(self.last_signals[symbol].keys()):
                last_time = self.last_signals[symbol][direction].get('time')
                if last_time and last_time < cutoff_time:
                    del self.last_signals[symbol][direction]
            
            # Eliminar símbolo si no tiene direcciones
            if not self.last_signals[symbol]:
                del self.last_signals[symbol]
        
        # Limpiar zone_cooldowns
        for symbol in list(self.zone_cooldowns.keys()):
            for zone in list(self.zone_cooldowns[symbol].keys()):
                for direction in list(self.zone_cooldowns[symbol][zone].keys()):
                    zone_time = self.zone_cooldowns[symbol][zone][direction]
                    if zone_time < cutoff_time:
                        del self.zone_cooldowns[symbol][zone][direction]
                
                # Eliminar zona si no tiene direcciones
                if not self.zone_cooldowns[symbol][zone]:
                    del self.zone_cooldowns[symbol][zone]
            
            # Eliminar símbolo si no tiene zonas
            if not self.zone_cooldowns[symbol]:
                del self.zone_cooldowns[symbol]
        
        logger.debug(f"Cleanup completed: removed entries older than {max_age_hours}h")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del sistema de cooldown"""
        stats = {
            'symbols_tracked': len(self.last_signals),
            'zones_tracked': sum(len(zones) for zones in self.zone_cooldowns.values()),
            'symbol_cooldowns': self.symbol_cooldowns,
            'direction_cooldowns': self.direction_cooldowns,
            'zone_tolerances': self.zone_tolerances
        }
        
        # Estadísticas por símbolo
        for symbol in self.last_signals.keys():
            stats[f'{symbol}_status'] = self.get_cooldown_status(symbol)
        
        return stats

# Instancia global
signal_cooldown_manager = SignalCooldownManager()