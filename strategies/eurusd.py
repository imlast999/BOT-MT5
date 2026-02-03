"""
EURUSD Strategy - Estrategia específica para EURUSD

Estrategia optimizada para el par EUR/USD basada en:
- Breakout de consolidación con EMAs
- Filtros de tendencia y momentum
- Gestión de riesgo conservadora
"""

from typing import Dict, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import logging

from .base import BaseStrategy

logger = logging.getLogger(__name__)

class EURUSDStrategy(BaseStrategy):
    """
    Estrategia EURUSD: Breakout de consolidación con confirmaciones múltiples
    
    Setup Principal:
    - Breakout de rango de 15 períodos
    - EMA50 > EMA200 para BUY, EMA50 < EMA200 para SELL
    
    Confirmaciones:
    - RSI en zona operativa (35-75)
    - ATR por encima de media (volatilidad)
    - Sin retroceso fuerte después del breakout
    """
    
    def __init__(self):
        super().__init__("EURUSD_Breakout")
    
    def _get_default_config(self) -> Dict:
        return {
            'ema_fast': 50,
            'ema_slow': 200,
            'breakout_periods': 15,
            'rsi_period': 14,
            'rsi_min': 35,
            'rsi_max': 75,
            'atr_period': 14,
            'atr_multiplier': 0.9,
            'sl_atr_multiplier': 1.2,
            'tp_atr_multiplier': 2.4,  # R:R = 2.0
            'expires_minutes': 30,
            'pullback_tolerance': 0.002  # 0.2%
        }
    
    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        """Añade indicadores específicos para EURUSD"""
        # EMAs para filtro de tendencia
        df['ema50'] = self._ema(df['close'], config['ema_fast'])
        df['ema200'] = self._ema(df['close'], config['ema_slow'])
        
        # Rangos para breakout
        df['high_15'] = df['high'].rolling(config['breakout_periods']).max()
        df['low_15'] = df['low'].rolling(config['breakout_periods']).min()
        
        # Indicadores adicionales ya están en la clase base
        return df
    
    def detect_setup(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict]:
        """
        Detecta setup de breakout EURUSD
        """
        cfg = {**self.default_config, **(config or {})}
        
        # Validar datos
        if not self.validate_data(df) or len(df) < cfg['ema_slow']:
            return None
        
        # Añadir indicadores
        df = self.add_indicators(df, cfg)
        
        # Datos actuales
        last = df.iloc[-1]
        price = float(last['close'])
        ema50 = float(last['ema50'])
        ema200 = float(last['ema200'])
        rsi = float(last['rsi'])
        atr_current = float(last['atr'])
        
        # Calcular ATR medio
        atr_mean = df['atr'].tail(20).mean()
        
        # ========================================================================
        # SETUP PRINCIPAL: Breakout con filtro de tendencia
        # ========================================================================
        
        # Detectar breakout alcista
        breakout_up = (
            price > last['high_15'] and  # Breakout del máximo
            ema50 > ema200  # Tendencia alcista
        )
        
        # Detectar breakout bajista  
        breakout_down = (
            price < last['low_15'] and  # Breakout del mínimo
            ema50 < ema200  # Tendencia bajista
        )
        
        if not (breakout_up or breakout_down):
            return None
        
        # Determinar dirección
        direction = 'BUY' if breakout_up else 'SELL'
        
        # ========================================================================
        # CONFIRMACIONES
        # ========================================================================
        
        confirmations = []
        
        # Confirmación 1: RSI en zona operativa
        rsi_ok = cfg['rsi_min'] <= rsi <= cfg['rsi_max']
        confirmations.append({
            'name': 'RSI_OPERATIVE',
            'passed': rsi_ok,
            'value': rsi,
            'description': f"RSI operativo ({cfg['rsi_min']}-{cfg['rsi_max']}): {rsi:.1f}"
        })
        
        # Confirmación 2: ATR por encima de media (volatilidad)
        atr_high = atr_current > atr_mean * cfg['atr_multiplier']
        confirmations.append({
            'name': 'ATR_HIGH',
            'passed': atr_high,
            'value': atr_current / atr_mean if atr_mean > 0 else 0,
            'description': f"ATR alto: {atr_current:.5f} vs {atr_mean:.5f}"
        })
        
        # Confirmación 3: Sin retroceso fuerte
        if direction == 'BUY':
            recent_high = df['high'].tail(10).max()
            no_pullback = price >= recent_high * (1 - cfg['pullback_tolerance'])
        else:
            recent_low = df['low'].tail(10).min()
            no_pullback = price <= recent_low * (1 + cfg['pullback_tolerance'])
        
        confirmations.append({
            'name': 'NO_PULLBACK',
            'passed': no_pullback,
            'value': 1.0 if no_pullback else 0.0,
            'description': f"Sin retroceso fuerte para {direction}"
        })
        
        # ========================================================================
        # CALCULAR NIVELES
        # ========================================================================
        
        # Distancias basadas en ATR
        sl_distance = atr_current * cfg['sl_atr_multiplier']
        tp_distance = atr_current * cfg['tp_atr_multiplier']
        
        if direction == 'BUY':
            sl = price - sl_distance
            tp = price + tp_distance
        else:
            sl = price + sl_distance
            tp = price - tp_distance
        
        # ========================================================================
        # CALCULAR FORTALEZA DEL SETUP
        # ========================================================================
        
        # Contar confirmaciones pasadas
        passed_confirmations = sum(1 for c in confirmations if c['passed'])
        total_confirmations = len(confirmations)
        
        # Setup strength basado en confirmaciones y separación de EMAs
        ema_separation = abs(ema50 - ema200) / ema200 if ema200 > 0 else 0
        confirmation_ratio = passed_confirmations / total_confirmations
        
        setup_strength = (confirmation_ratio * 0.7) + (min(ema_separation * 100, 1.0) * 0.3)
        
        # ========================================================================
        # CREAR SEÑAL
        # ========================================================================
        
        signal = {
            'type': direction,
            'entry': price,
            'sl': sl,
            'tp': tp,
            'timeframe': 'H1',
            'explanation': f'EURUSD Breakout: {direction} + {passed_confirmations}/{total_confirmations} confirmaciones + R:R {tp_distance/sl_distance:.1f}',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=cfg['expires_minutes']),
            'setup_strength': setup_strength,
            'context': {
                'strategy': 'eurusd_breakout',
                'confirmations': confirmations,
                'market_conditions': {
                    'ema50': ema50,
                    'ema200': ema200,
                    'ema_separation': ema_separation,
                    'rsi': rsi,
                    'atr_current': atr_current,
                    'atr_mean': atr_mean,
                    'volatility_ratio': atr_current / atr_mean if atr_mean > 0 else 1.0
                },
                'risk_reward': tp_distance / sl_distance if sl_distance > 0 else 0,
                'breakout_type': 'high' if breakout_up else 'low',
                'trend_alignment': True  # Siempre True por el filtro EMA
            }
        }
        
        return signal


class EURUSDAdvancedStrategy(BaseStrategy):
    """
    Estrategia EURUSD Avanzada: Versión más sofisticada con múltiples timeframes
    
    Mejoras:
    - Análisis de múltiples timeframes
    - Detección de patrones de velas
    - Filtros de volumen (si disponible)
    - Gestión dinámica de riesgo
    """
    
    def __init__(self):
        super().__init__("EURUSD_Advanced")
    
    def _get_default_config(self) -> Dict:
        return {
            'ema_fast': 21,
            'ema_medium': 50,
            'ema_slow': 200,
            'rsi_period': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'atr_period': 14,
            'bb_period': 20,
            'bb_std': 2.0,
            'min_confirmations': 3,
            'sl_atr_multiplier': 1.5,
            'tp_atr_multiplier': 3.0,
            'expires_minutes': 45
        }
    
    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        """Añade indicadores avanzados para EURUSD"""
        # EMAs múltiples
        df['ema21'] = self._ema(df['close'], config['ema_fast'])
        df['ema50'] = self._ema(df['close'], config['ema_medium'])
        df['ema200'] = self._ema(df['close'], config['ema_slow'])
        
        # MACD
        df['macd'], df['macd_signal'], df['macd_hist'] = self._macd(
            df['close'], config['macd_fast'], config['macd_slow'], config['macd_signal']
        )
        
        # Bollinger Bands
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = self._bollinger_bands(
            df['close'], config['bb_period'], config['bb_std']
        )
        
        # Stochastic
        df['stoch_k'], df['stoch_d'] = self._stochastic(
            df['high'], df['low'], df['close']
        )
        
        return df
    
    def detect_setup(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict]:
        """
        Detecta setup avanzado EURUSD con múltiples confirmaciones
        """
        cfg = {**self.default_config, **(config or {})}
        
        # Validar datos
        if not self.validate_data(df) or len(df) < cfg['ema_slow']:
            return None
        
        # Añadir indicadores
        df = self.add_indicators(df, cfg)
        
        # Datos actuales
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        price = float(last['close'])
        ema21 = float(last['ema21'])
        ema50 = float(last['ema50'])
        ema200 = float(last['ema200'])
        
        # ========================================================================
        # SETUP PRINCIPAL: Alineación de EMAs + Momentum
        # ========================================================================
        
        # Setup alcista: EMAs alineadas + momentum positivo
        bullish_setup = (
            ema21 > ema50 > ema200 and  # EMAs alineadas
            last['macd'] > last['macd_signal'] and  # MACD positivo
            last['macd_hist'] > prev['macd_hist']  # Histograma creciente
        )
        
        # Setup bajista: EMAs alineadas + momentum negativo
        bearish_setup = (
            ema21 < ema50 < ema200 and  # EMAs alineadas
            last['macd'] < last['macd_signal'] and  # MACD negativo
            last['macd_hist'] < prev['macd_hist']  # Histograma decreciente
        )
        
        if not (bullish_setup or bearish_setup):
            return None
        
        direction = 'BUY' if bullish_setup else 'SELL'
        
        # ========================================================================
        # CONFIRMACIONES AVANZADAS
        # ========================================================================
        
        confirmations = []
        
        # Confirmación 1: RSI en zona favorable
        rsi = float(last['rsi'])
        if direction == 'BUY':
            rsi_ok = 40 <= rsi <= 70
        else:
            rsi_ok = 30 <= rsi <= 60
        
        confirmations.append({
            'name': 'RSI_FAVORABLE',
            'passed': rsi_ok,
            'value': rsi,
            'description': f"RSI favorable para {direction}: {rsi:.1f}"
        })
        
        # Confirmación 2: Stochastic alignment
        stoch_k = float(last['stoch_k'])
        stoch_d = float(last['stoch_d'])
        
        if direction == 'BUY':
            stoch_ok = stoch_k > stoch_d and stoch_k < 80
        else:
            stoch_ok = stoch_k < stoch_d and stoch_k > 20
        
        confirmations.append({
            'name': 'STOCHASTIC_ALIGNMENT',
            'passed': stoch_ok,
            'value': stoch_k,
            'description': f"Stochastic alineado para {direction}"
        })
        
        # Confirmación 3: Bollinger Bands position
        bb_position = (price - last['bb_lower']) / (last['bb_upper'] - last['bb_lower'])
        
        if direction == 'BUY':
            bb_ok = 0.2 <= bb_position <= 0.8  # No en extremos
        else:
            bb_ok = 0.2 <= bb_position <= 0.8
        
        confirmations.append({
            'name': 'BB_POSITION',
            'passed': bb_ok,
            'value': bb_position,
            'description': f"Posición en BB: {bb_position:.2f}"
        })
        
        # Confirmación 4: Patrón de velas
        candle_pattern = self._analyze_candle_pattern(df.tail(3), direction)
        confirmations.append({
            'name': 'CANDLE_PATTERN',
            'passed': candle_pattern['valid'],
            'value': candle_pattern['strength'],
            'description': candle_pattern['description']
        })
        
        # Verificar mínimo de confirmaciones
        passed_confirmations = sum(1 for c in confirmations if c['passed'])
        if passed_confirmations < cfg['min_confirmations']:
            return None
        
        # ========================================================================
        # CALCULAR NIVELES CON GESTIÓN DINÁMICA
        # ========================================================================
        
        atr_current = float(last['atr'])
        
        # Ajustar multiplicadores basado en volatilidad
        volatility_factor = min(2.0, max(0.5, atr_current / df['atr'].tail(50).mean()))
        
        sl_distance = atr_current * cfg['sl_atr_multiplier'] * volatility_factor
        tp_distance = atr_current * cfg['tp_atr_multiplier'] * volatility_factor
        
        if direction == 'BUY':
            sl = price - sl_distance
            tp = price + tp_distance
        else:
            sl = price + sl_distance
            tp = price - tp_distance
        
        # ========================================================================
        # CALCULAR FORTALEZA DEL SETUP
        # ========================================================================
        
        confirmation_ratio = passed_confirmations / len(confirmations)
        momentum_strength = abs(last['macd_hist']) / df['macd_hist'].tail(20).std()
        ema_alignment = self._calculate_ema_alignment_strength(ema21, ema50, ema200)
        
        setup_strength = (
            confirmation_ratio * 0.4 +
            min(momentum_strength, 1.0) * 0.3 +
            ema_alignment * 0.3
        )
        
        # ========================================================================
        # CREAR SEÑAL AVANZADA
        # ========================================================================
        
        signal = {
            'type': direction,
            'entry': price,
            'sl': sl,
            'tp': tp,
            'timeframe': 'H1',
            'explanation': f'EURUSD Advanced: {direction} + {passed_confirmations}/{len(confirmations)} confirmaciones + Momentum + EMAs',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=cfg['expires_minutes']),
            'setup_strength': setup_strength,
            'context': {
                'strategy': 'eurusd_advanced',
                'confirmations': confirmations,
                'market_conditions': {
                    'ema_alignment': ema_alignment,
                    'momentum_strength': momentum_strength,
                    'volatility_factor': volatility_factor,
                    'bb_position': bb_position,
                    'macd_histogram': float(last['macd_hist']),
                    'rsi': rsi,
                    'stochastic': {'k': stoch_k, 'd': stoch_d}
                },
                'risk_reward': tp_distance / sl_distance if sl_distance > 0 else 0,
                'advanced_features': True
            }
        }
        
        return signal
    
    def _analyze_candle_pattern(self, candles: pd.DataFrame, direction: str) -> Dict:
        """Analiza patrón de velas para confirmación"""
        try:
            if len(candles) < 3:
                return {'valid': False, 'strength': 0.0, 'description': 'Datos insuficientes'}
            
            last = candles.iloc[-1]
            prev = candles.iloc[-2]
            
            # Análisis básico de momentum de velas
            if direction == 'BUY':
                # Buscar velas alcistas con momentum creciente
                last_bullish = self._is_bullish_candle(last)
                body_size_increasing = self._candle_body_size(last) > self._candle_body_size(prev)
                
                valid = last_bullish and body_size_increasing
                strength = 0.8 if valid else 0.2
                description = f"Patrón alcista: vela {'fuerte' if valid else 'débil'}"
                
            else:
                # Buscar velas bajistas con momentum creciente
                last_bearish = self._is_bearish_candle(last)
                body_size_increasing = self._candle_body_size(last) > self._candle_body_size(prev)
                
                valid = last_bearish and body_size_increasing
                strength = 0.8 if valid else 0.2
                description = f"Patrón bajista: vela {'fuerte' if valid else 'débil'}"
            
            return {
                'valid': valid,
                'strength': strength,
                'description': description
            }
            
        except Exception as e:
            logger.warning(f"Error analizando patrón de velas: {e}")
            return {'valid': False, 'strength': 0.0, 'description': 'Error en análisis'}
    
    def _calculate_ema_alignment_strength(self, ema21: float, ema50: float, ema200: float) -> float:
        """Calcula la fortaleza de la alineación de EMAs"""
        try:
            # Calcular separaciones relativas
            sep_21_50 = abs(ema21 - ema50) / ema50 if ema50 > 0 else 0
            sep_50_200 = abs(ema50 - ema200) / ema200 if ema200 > 0 else 0
            
            # Normalizar y combinar
            strength = min(1.0, (sep_21_50 + sep_50_200) * 50)  # Factor de escala
            
            return strength
            
        except Exception as e:
            logger.warning(f"Error calculando alineación de EMAs: {e}")
            return 0.5


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_eurusd_strategy(advanced: bool = False) -> BaseStrategy:
    """
    Factory function para crear estrategia EURUSD
    
    Args:
        advanced: Si True, usa la estrategia avanzada
        
    Returns:
        Instancia de la estrategia EURUSD
    """
    if advanced:
        return EURUSDAdvancedStrategy()
    else:
        return EURUSDStrategy()