"""
Sistema de reglas avanzado para el bot de trading MT5
Incluye gestión de riesgo, filtros de mercado y reglas de entrada/salida
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

@dataclass
class MarketCondition:
    """Condiciones del mercado para filtrar señales"""
    volatility_high: bool = False
    volatility_low: bool = False
    trending: bool = False
    ranging: bool = False
    news_time: bool = False
    session_active: bool = True

@dataclass
class RiskParameters:
    """Parámetros de gestión de riesgo"""
    max_risk_per_trade: float = 0.5  # % del balance
    max_daily_risk: float = 2.0      # % del balance total por día
    max_drawdown: float = 10.0       # % máximo de drawdown
    risk_reward_min: float = 1.5     # Ratio mínimo R:R
    max_correlation: float = 0.7     # Correlación máxima entre posiciones
    max_positions: int = 3           # Máximo de posiciones simultáneas

@dataclass
class TradingSession:
    """Sesiones de trading activas"""
    london_open: Tuple[int, int] = (8, 17)    # 8:00 - 17:00 GMT
    new_york_open: Tuple[int, int] = (13, 22) # 13:00 - 22:00 GMT
    tokyo_open: Tuple[int, int] = (0, 9)      # 00:00 - 09:00 GMT
    overlap_london_ny: Tuple[int, int] = (13, 17)  # Mejor liquidez

class AdvancedRiskManager:
    """Gestor de riesgo avanzado"""
    
    def __init__(self, risk_params: RiskParameters):
        self.risk_params = risk_params
        self.daily_risk_used = 0.0
        self.current_drawdown = 0.0
        self.open_positions = []
        
    def can_take_trade(self, signal: dict, account_balance: float) -> Tuple[bool, str]:
        """Determina si se puede tomar un trade basado en las reglas de riesgo"""
        
        # Calcular riesgo del trade
        entry = float(signal.get('entry', 0))
        sl = float(signal.get('sl', 0))
        risk_amount = abs(entry - sl) * account_balance * (self.risk_params.max_risk_per_trade / 100)
        
        # Verificar riesgo diario
        if self.daily_risk_used + risk_amount > account_balance * (self.risk_params.max_daily_risk / 100):
            return False, "Límite de riesgo diario excedido"
            
        # Verificar drawdown máximo
        if self.current_drawdown > self.risk_params.max_drawdown:
            return False, f"Drawdown máximo excedido: {self.current_drawdown:.1f}%"
            
        # Verificar ratio R:R
        tp = float(signal.get('tp', entry))
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk > 0 and reward / risk < self.risk_params.risk_reward_min:
            return False, f"R:R insuficiente: {reward/risk:.2f} < {self.risk_params.risk_reward_min}"
            
        # Verificar máximo de posiciones
        if len(self.open_positions) >= self.risk_params.max_positions:
            return False, "Máximo de posiciones simultáneas alcanzado"
            
        return True, "Trade aprobado"
    
    def calculate_position_size(self, signal: dict, account_balance: float) -> float:
        """Calcula el tamaño de posición óptimo"""
        entry = float(signal.get('entry', 0))
        sl = float(signal.get('sl', 0))
        
        if entry == sl:
            return 0.0
            
        # Riesgo en pips/puntos
        risk_points = abs(entry - sl)
        
        # Cantidad a arriesgar
        risk_amount = account_balance * (self.risk_params.max_risk_per_trade / 100)
        
        # Calcular lot size (simplificado - necesita info del símbolo)
        # Esto debería ajustarse según el valor del pip del símbolo
        pip_value = 10  # Valor aproximado para EURUSD
        lot_size = risk_amount / (risk_points * pip_value * 100000)
        
        return round(lot_size, 2)

class MarketAnalyzer:
    """Analizador de condiciones de mercado"""
    
    @staticmethod
    def analyze_volatility(df: pd.DataFrame, period: int = 20) -> Tuple[bool, bool]:
        """Analiza si la volatilidad está alta o baja"""
        if len(df) < period:
            return False, False
            
        # Calcular ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        true_range = np.maximum(high_low, np.maximum(high_close, low_close))
        atr = true_range.rolling(period).mean()
        
        current_atr = atr.iloc[-1]
        avg_atr = atr.rolling(period * 2).mean().iloc[-1]
        
        volatility_high = current_atr > avg_atr * 1.5
        volatility_low = current_atr < avg_atr * 0.7
        
        return volatility_high, volatility_low
    
    @staticmethod
    def detect_trend_or_range(df: pd.DataFrame, period: int = 50) -> Tuple[bool, bool]:
        """Detecta si el mercado está en tendencia o rango"""
        if len(df) < period:
            return False, False
            
        # Usar ADX para detectar tendencia
        high = df['high']
        low = df['low']
        close = df['close']
        
        # Calcular ADX simplificado
        up_move = high.diff()
        down_move = -low.diff()
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.rolling(14).mean()
        plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / atr)
        
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx = dx.rolling(14).mean().iloc[-1]
        
        trending = adx > 25
        ranging = adx < 20
        
        return trending, ranging
    
    @staticmethod
    def is_news_time() -> bool:
        """Verifica si estamos en horario de noticias importantes"""
        now = datetime.now(timezone.utc)
        hour = now.hour
        minute = now.minute
        
        # Horarios típicos de noticias importantes (GMT)
        news_times = [
            (8, 30),   # EUR news
            (12, 30),  # GBP news  
            (13, 30),  # USD news
            (15, 30),  # USD news
        ]
        
        for news_hour, news_minute in news_times:
            if abs(hour - news_hour) == 0 and abs(minute - news_minute) <= 30:
                return True
                
        return False
    
    @staticmethod
    def is_active_session(symbol: str) -> bool:
        """Verifica si estamos en una sesión activa para el símbolo"""
        now = datetime.now(timezone.utc)
        hour = now.hour
        
        # Sesiones por símbolo
        if symbol.startswith('EUR') or symbol.startswith('GBP'):
            # Sesión europea
            return 7 <= hour <= 17
        elif symbol.startswith('USD'):
            # Sesión americana o overlap
            return 12 <= hour <= 22
        elif symbol.startswith('JPY') or symbol.startswith('AUD'):
            # Sesión asiática
            return 22 <= hour <= 24 or 0 <= hour <= 8
        elif symbol == 'XAUUSD':
            # Oro - activo en múltiples sesiones
            return 7 <= hour <= 22
        
        return True  # Por defecto, permitir

class AdvancedSignalFilter:
    """Filtro avanzado de señales"""
    
    def __init__(self, risk_manager: AdvancedRiskManager):
        self.risk_manager = risk_manager
        self.market_analyzer = MarketAnalyzer()
        
    def should_take_signal(self, signal: dict, df: pd.DataFrame, account_balance: float) -> Tuple[bool, str]:
        """Determina si se debe tomar una señal basado en múltiples filtros"""
        
        symbol = signal.get('symbol', '')
        
        # 1. Verificar gestión de riesgo
        can_trade, risk_msg = self.risk_manager.can_take_trade(signal, account_balance)
        if not can_trade:
            return False, f"Riesgo: {risk_msg}"
        
        # 2. Verificar sesión activa
        if not self.market_analyzer.is_active_session(symbol):
            return False, "Sesión inactiva para este símbolo"
        
        # 3. Verificar horario de noticias
        if self.market_analyzer.is_news_time():
            return False, "Horario de noticias - evitar trades"
        
        # 4. Analizar volatilidad
        vol_high, vol_low = self.market_analyzer.analyze_volatility(df)
        if vol_high:
            return False, "Volatilidad demasiado alta"
        if vol_low and symbol != 'XAUUSD':  # El oro puede tradear con baja volatilidad
            return False, "Volatilidad demasiado baja"
        
        # 5. Verificar condiciones de tendencia/rango
        trending, ranging = self.market_analyzer.detect_trend_or_range(df)
        
        # Para estrategias de tendencia, necesitamos mercado trending
        strategy = signal.get('strategy', '')
        if 'ema' in strategy.lower() and not trending:
            return False, "Mercado en rango - estrategia de tendencia no recomendada"
        
        # Para estrategias de reversión, necesitamos mercado ranging
        if 'rsi' in strategy.lower() and trending:
            return False, "Mercado en tendencia - estrategia de reversión no recomendada"
        
        # 6. Verificar calidad de la señal
        quality_score = self._calculate_signal_quality(signal, df)
        if quality_score < 0.6:  # Umbral mínimo de calidad
            return False, f"Calidad de señal insuficiente: {quality_score:.2f}"
        
        return True, f"Señal aprobada (calidad: {quality_score:.2f})"
    
    def _calculate_signal_quality(self, signal: dict, df: pd.DataFrame) -> float:
        """Calcula un score de calidad de la señal (0-1)"""
        score = 0.0
        
        # Factor 1: Ratio R:R (peso: 30%)
        entry = float(signal.get('entry', 0))
        sl = float(signal.get('sl', 0))
        tp = float(signal.get('tp', entry))
        
        if sl != entry:
            rr_ratio = abs(tp - entry) / abs(entry - sl)
            score += min(rr_ratio / 3.0, 0.3)  # Máximo 0.3 puntos
        
        # Factor 2: Confluencia de indicadores (peso: 25%)
        confluence_score = self._check_confluence(signal, df)
        score += confluence_score * 0.25
        
        # Factor 3: Posición respecto a niveles clave (peso: 20%)
        level_score = self._check_key_levels(signal, df)
        score += level_score * 0.20
        
        # Factor 4: Momentum (peso: 15%)
        momentum_score = self._check_momentum(signal, df)
        score += momentum_score * 0.15
        
        # Factor 5: Volumen/Actividad (peso: 10%)
        volume_score = self._check_volume(df)
        score += volume_score * 0.10
        
        return min(score, 1.0)
    
    def _check_confluence(self, signal: dict, df: pd.DataFrame) -> float:
        """Verifica confluencia de múltiples indicadores"""
        if len(df) < 50:
            return 0.5
            
        confluence_count = 0
        total_checks = 0
        
        # EMA confluence
        if 'ema50' in df.columns and 'ema200' in df.columns:
            ema50 = df['ema50'].iloc[-1]
            ema200 = df['ema200'].iloc[-1]
            price = df['close'].iloc[-1]
            
            signal_type = signal.get('type', '')
            if signal_type == 'BUY' and price > ema50 > ema200:
                confluence_count += 1
            elif signal_type == 'SELL' and price < ema50 < ema200:
                confluence_count += 1
            total_checks += 1
        
        # RSI confluence
        if 'rsi' in df.columns:
            rsi = df['rsi'].iloc[-1]
            signal_type = signal.get('type', '')
            
            if signal_type == 'BUY' and 30 <= rsi <= 50:
                confluence_count += 1
            elif signal_type == 'SELL' and 50 <= rsi <= 70:
                confluence_count += 1
            total_checks += 1
        
        return confluence_count / max(total_checks, 1)
    
    def _check_key_levels(self, signal: dict, df: pd.DataFrame) -> float:
        """Verifica proximidad a niveles clave de soporte/resistencia"""
        if len(df) < 20:
            return 0.5
            
        price = float(signal.get('entry', 0))
        
        # Calcular niveles de soporte y resistencia recientes
        recent_highs = df['high'].rolling(20).max()
        recent_lows = df['low'].rolling(20).min()
        
        resistance = recent_highs.iloc[-1]
        support = recent_lows.iloc[-1]
        
        # Verificar si estamos cerca de niveles clave
        signal_type = signal.get('type', '')
        
        if signal_type == 'BUY':
            # Para compras, mejor si estamos cerca del soporte
            distance_to_support = abs(price - support) / price
            return max(0, 1 - distance_to_support * 100)  # Mejor score si más cerca del soporte
        else:
            # Para ventas, mejor si estamos cerca de la resistencia
            distance_to_resistance = abs(price - resistance) / price
            return max(0, 1 - distance_to_resistance * 100)
    
    def _check_momentum(self, signal: dict, df: pd.DataFrame) -> float:
        """Verifica el momentum del mercado"""
        if len(df) < 10:
            return 0.5
            
        # Calcular momentum simple basado en las últimas velas
        recent_closes = df['close'].tail(5)
        momentum = (recent_closes.iloc[-1] - recent_closes.iloc[0]) / recent_closes.iloc[0]
        
        signal_type = signal.get('type', '')
        
        if signal_type == 'BUY' and momentum > 0:
            return min(abs(momentum) * 100, 1.0)
        elif signal_type == 'SELL' and momentum < 0:
            return min(abs(momentum) * 100, 1.0)
        else:
            return 0.3  # Momentum contrario a la señal
    
    def _check_volume(self, df: pd.DataFrame) -> float:
        """Verifica el volumen/actividad (simplificado)"""
        # En MT5, el volumen tick puede no estar siempre disponible
        # Usar el rango de las velas como proxy de actividad
        if len(df) < 10:
            return 0.5
            
        recent_ranges = (df['high'] - df['low']).tail(5)
        avg_range = recent_ranges.mean()
        current_range = recent_ranges.iloc[-1]
        
        # Score basado en si el rango actual es mayor al promedio
        return min(current_range / avg_range, 1.0) if avg_range > 0 else 0.5

# Funciones de utilidad para integrar con el bot existente
def create_advanced_filter(max_risk_per_trade: float = 0.5) -> AdvancedSignalFilter:
    """Crea un filtro avanzado con parámetros por defecto"""
    risk_params = RiskParameters(max_risk_per_trade=max_risk_per_trade)
    risk_manager = AdvancedRiskManager(risk_params)
    return AdvancedSignalFilter(risk_manager)

def should_execute_signal(signal: dict, df: pd.DataFrame, account_balance: float, 
                         signal_filter: AdvancedSignalFilter = None) -> Tuple[bool, str]:
    """Función principal para determinar si ejecutar una señal"""
    if signal_filter is None:
        signal_filter = create_advanced_filter()
    
    return signal_filter.should_take_signal(signal, df, account_balance)