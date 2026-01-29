"""
Sistema de Confianza para Señales de Trading
Implementa el sistema de puntos para clasificar señales por calidad
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class ConfidenceSystem:
    """Sistema de confianza basado en puntos para clasificar señales"""
    
    def __init__(self):
        self.confidence_mapping = {
            0: "LOW",
            1: "MEDIUM", 
            2: "MEDIUM-HIGH",
            3: "HIGH"
        }
    
    def calculate_confidence(self, signal: Dict[str, Any], df: pd.DataFrame, symbol: str) -> Tuple[str, int, Dict[str, Any]]:
        """
        Calcula la confianza de una señal basada en el símbolo
        
        Returns:
            Tuple[confidence_level, score, details]
        """
        try:
            if symbol.upper() == "EURUSD":
                return self._calculate_eurusd_confidence(signal, df)
            elif symbol.upper() == "XAUUSD":
                return self._calculate_xauusd_confidence(signal, df)
            elif symbol.upper() == "BTCEUR":
                return self._calculate_btceur_confidence(signal, df)
            else:
                # Símbolo no configurado, usar confianza básica
                return "MEDIUM", 1, {"reason": "Symbol not configured for confidence scoring"}
                
        except Exception as e:
            logger.error(f"Error calculating confidence for {symbol}: {e}")
            return "LOW", 0, {"error": str(e)}
    
    def _calculate_eurusd_confidence(self, signal: Dict[str, Any], df: pd.DataFrame) -> Tuple[str, int, Dict[str, Any]]:
        """
        EURUSD - Confianza después del breakout
        Factores:
        1. Distancia del breakout
        2. Pendiente EMA50  
        3. Fuerza RSI
        """
        score = 0
        details = {}
        
        try:
            close = df['close'].iloc[-1]
            
            # Factor 1: Distancia del breakout
            if 'atr' in df.columns and len(df) > 20:
                atr = df['atr'].iloc[-1]
                # Calcular rango reciente (últimas 20 velas)
                recent_high = df['high'].tail(20).max()
                recent_low = df['low'].tail(20).min()
                range_high = recent_high
                
                dist = abs(close - range_high) / atr if atr > 0 else 0
                if dist > 0.5:
                    score += 1
                    details['breakout_distance'] = f"Good distance: {dist:.2f}"
                else:
                    details['breakout_distance'] = f"Weak distance: {dist:.2f}"
            
            # Factor 2: Pendiente EMA50
            if 'ema_50' in df.columns and len(df) > 3:
                ema50_current = df['ema_50'].iloc[-1]
                ema50_prev = df['ema_50'].iloc[-4]  # 3 períodos atrás
                slope = ema50_current - ema50_prev
                
                # Threshold dinámico basado en ATR
                threshold = df['atr'].iloc[-1] * 0.1 if 'atr' in df.columns else 0.0001
                
                if abs(slope) > threshold:
                    score += 1
                    details['ema50_slope'] = f"Strong slope: {slope:.5f}"
                else:
                    details['ema50_slope'] = f"Weak slope: {slope:.5f}"
            
            # Factor 3: Fuerza RSI
            if 'rsi' in df.columns:
                rsi = df['rsi'].iloc[-1]
                rsi_strength = abs(rsi - 50)
                
                if rsi_strength > 10:
                    score += 1
                    details['rsi_strength'] = f"Strong RSI: {rsi:.1f} (strength: {rsi_strength:.1f})"
                else:
                    details['rsi_strength'] = f"Weak RSI: {rsi:.1f} (strength: {rsi_strength:.1f})"
            
        except Exception as e:
            details['error'] = str(e)
        
        confidence = self.confidence_mapping.get(score, "LOW")
        return confidence, score, details
    
    def _calculate_xauusd_confidence(self, signal: Dict[str, Any], df: pd.DataFrame) -> Tuple[str, int, Dict[str, Any]]:
        """
        XAUUSD - Confianza después de reversión
        Factores:
        1. Precisión del nivel
        2. Tamaño de mecha
        3. Rango relativo
        """
        score = 0
        details = {}
        
        try:
            # Datos de la última vela
            last_candle = df.iloc[-1]
            close = last_candle['close']
            high = last_candle['high']
            low = last_candle['low']
            open_price = last_candle['open']
            
            # Factor 1: Precisión del nivel (usar niveles de soporte/resistencia recientes)
            recent_highs = df['high'].tail(20)
            recent_lows = df['low'].tail(20)
            
            # Encontrar nivel más cercano
            resistance_level = recent_highs.max()
            support_level = recent_lows.min()
            
            closest_level = resistance_level if abs(close - resistance_level) < abs(close - support_level) else support_level
            level_distance = abs(close - closest_level)
            
            if level_distance < 5.0:  # 5 puntos para XAUUSD
                score += 1
                details['level_precision'] = f"Close to level: {level_distance:.1f} points"
            else:
                details['level_precision'] = f"Far from level: {level_distance:.1f} points"
            
            # Factor 2: Tamaño de mecha
            candle_range = high - low
            if candle_range > 0:
                if signal.get('type') == 'SELL':
                    # Para SELL, mecha superior importante
                    upper_wick = high - max(open_price, close)
                    wick_ratio = upper_wick / candle_range
                else:
                    # Para BUY, mecha inferior importante  
                    lower_wick = min(open_price, close) - low
                    wick_ratio = lower_wick / candle_range
                
                if wick_ratio > 0.45:
                    score += 1
                    details['wick_strength'] = f"Strong wick: {wick_ratio:.2f}"
                else:
                    details['wick_strength'] = f"Weak wick: {wick_ratio:.2f}"
            
            # Factor 3: Rango relativo
            if 'atr' in df.columns:
                atr = df['atr'].iloc[-1]
                range_ratio = candle_range / atr if atr > 0 else 0
                
                if range_ratio > 1.0:
                    score += 1
                    details['range_strength'] = f"Strong range: {range_ratio:.2f}x ATR"
                else:
                    details['range_strength'] = f"Weak range: {range_ratio:.2f}x ATR"
            
        except Exception as e:
            details['error'] = str(e)
        
        confidence = self.confidence_mapping.get(score, "LOW")
        return confidence, score, details
    
    def _calculate_btceur_confidence(self, signal: Dict[str, Any], df: pd.DataFrame) -> Tuple[str, int, Dict[str, Any]]:
        """
        BTCEUR - Confianza después del cruce EMA
        Factores:
        1. Separación EMAs
        2. Fuerza RSI
        3. Volatilidad
        """
        score = 0
        details = {}
        
        try:
            close = df['close'].iloc[-1]
            
            # Factor 1: Separación EMAs
            if 'ema_12' in df.columns and 'ema_26' in df.columns and 'atr' in df.columns:
                ema12 = df['ema_12'].iloc[-1]
                ema26 = df['ema_26'].iloc[-1]
                atr = df['atr'].iloc[-1]
                
                ema_separation = abs(ema12 - ema26) / atr if atr > 0 else 0
                
                if ema_separation > 0.3:
                    score += 1
                    details['ema_separation'] = f"Good separation: {ema_separation:.2f}x ATR"
                else:
                    details['ema_separation'] = f"Weak separation: {ema_separation:.2f}x ATR"
            
            # Factor 2: Fuerza RSI
            if 'rsi' in df.columns:
                rsi = df['rsi'].iloc[-1]
                rsi_strength = abs(rsi - 50)
                
                if rsi_strength > 12:
                    score += 1
                    details['rsi_strength'] = f"Strong RSI: {rsi:.1f} (strength: {rsi_strength:.1f})"
                else:
                    details['rsi_strength'] = f"Weak RSI: {rsi:.1f} (strength: {rsi_strength:.1f})"
            
            # Factor 3: Volatilidad
            if 'atr' in df.columns:
                atr = df['atr'].iloc[-1]
                volatility_ratio = atr / close if close > 0 else 0
                
                if volatility_ratio > 0.002:  # 0.2%
                    score += 1
                    details['volatility'] = f"High volatility: {volatility_ratio:.4f}"
                else:
                    details['volatility'] = f"Low volatility: {volatility_ratio:.4f}"
            
        except Exception as e:
            details['error'] = str(e)
        
        confidence = self.confidence_mapping.get(score, "LOW")
        return confidence, score, details
    
    def should_show_signal(self, confidence: str) -> bool:
        """
        Determina si una señal debe mostrarse en Discord
        Solo MEDIUM-HIGH y HIGH se muestran
        """
        return confidence in ["MEDIUM-HIGH", "HIGH"]
    
    def should_auto_execute(self, confidence: str, auto_execute_enabled: bool) -> bool:
        """
        Determina si una señal debe auto-ejecutarse
        Solo HIGH puede auto-ejecutarse
        """
        return confidence == "HIGH" and auto_execute_enabled

# Instancia global
confidence_system = ConfidenceSystem()