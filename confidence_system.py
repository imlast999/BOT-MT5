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
        EURUSD - Confianza después del breakout (RECALIBRADO para más señales)
        Factores:
        1. Distancia del breakout (menos estricto)
        2. Pendiente EMA50 (más flexible)
        3. Fuerza RSI (rango ampliado)
        """
        score = 0
        details = {}
        
        try:
            close = df['close'].iloc[-1]
            
            # Factor 1: Distancia del breakout (MENOS ESTRICTO)
            if 'atr' in df.columns and len(df) > 15:  # Reducido de 20 a 15
                atr = df['atr'].iloc[-1]
                # Calcular rango reciente (últimas 15 velas)
                recent_high = df['high'].tail(15).max()
                recent_low = df['low'].tail(15).min()
                range_high = recent_high
                
                dist = abs(close - range_high) / atr if atr > 0 else 0
                if dist > 0.3:  # Reducido de 0.5 a 0.3
                    score += 1
                    details['breakout_distance'] = f"Good distance: {dist:.2f}"
                else:
                    details['breakout_distance'] = f"Weak distance: {dist:.2f}"
            
            # Factor 2: Pendiente EMA50 (MÁS FLEXIBLE)
            if 'ema_50' in df.columns and len(df) > 2:  # Reducido de 3 a 2
                ema50_current = df['ema_50'].iloc[-1]
                ema50_prev = df['ema_50'].iloc[-3]  # 2 períodos atrás
                slope = ema50_current - ema50_prev
                
                # Threshold más flexible
                threshold = df['atr'].iloc[-1] * 0.05 if 'atr' in df.columns else 0.00005  # Reducido de 0.1 a 0.05
                
                if abs(slope) > threshold:
                    score += 1
                    details['ema50_slope'] = f"Strong slope: {slope:.5f}"
                else:
                    details['ema50_slope'] = f"Weak slope: {slope:.5f}"
            
            # Factor 3: Fuerza RSI (RANGO AMPLIADO)
            if 'rsi' in df.columns:
                rsi = df['rsi'].iloc[-1]
                rsi_strength = abs(rsi - 50)
                
                if rsi_strength > 5:  # Reducido de 10 a 5
                    score += 1
                    details['rsi_strength'] = f"Strong RSI: {rsi:.1f} (strength: {rsi_strength:.1f})"
                else:
                    details['rsi_strength'] = f"Weak RSI: {rsi:.1f} (strength: {rsi_strength:.1f})"
            
            # BONUS: Factor adicional para momentum
            if len(df) > 5:
                recent_closes = df['close'].tail(5)
                momentum = (recent_closes.iloc[-1] - recent_closes.iloc[0]) / recent_closes.iloc[0]
                
                if abs(momentum) > 0.0005:  # 0.05% de movimiento
                    score += 1
                    details['momentum_bonus'] = f"Good momentum: {momentum*100:.3f}%"
                else:
                    details['momentum_bonus'] = f"Weak momentum: {momentum*100:.3f}%"
            
        except Exception as e:
            details['error'] = str(e)
        
        # Recalibrar mapping para distribución más realista
        if score >= 3:
            confidence = "HIGH"
        elif score >= 2:
            confidence = "MEDIUM-HIGH"
        elif score >= 1:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        return confidence, score, details
    
    def _calculate_xauusd_confidence(self, signal: Dict[str, Any], df: pd.DataFrame) -> Tuple[str, int, Dict[str, Any]]:
        """
        XAUUSD - Confianza ULTRA-RECALIBRADA para máxima selectividad
        Factores:
        1. Precisión del nivel (ULTRA-ESTRICTO - 2$ máximo)
        2. Tamaño de mecha (ULTRA-EXIGENTE - 60% mínimo)
        3. Rango relativo (MÁS EXIGENTE)
        4. Sesión de trading (SOLO OVERLAP)
        5. RSI en zona óptima (NUEVO)
        6. Volatilidad extrema (NUEVO)
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
            
            # Factor 1: Precisión del nivel (ULTRA-ESTRICTO - 2$ máximo)
            recent_highs = df['high'].tail(20)
            recent_lows = df['low'].tail(20)
            
            # Encontrar nivel más cercano (niveles cada 25 puntos)
            closest_level = round(close / 25) * 25
            level_distance = abs(close - closest_level)
            
            if level_distance < 2.0:  # ULTRA-ESTRICTO: 2 puntos máximo
                score += 2  # Doble puntuación por ser ultra-preciso
                details['level_precision'] = f"Ultra-close to level: {level_distance:.1f} points"
            elif level_distance < 3.0:
                score += 1
                details['level_precision'] = f"Close to level: {level_distance:.1f} points"
            else:
                details['level_precision'] = f"Far from level: {level_distance:.1f} points"
            
            # Factor 2: Tamaño de mecha (ULTRA-EXIGENTE - 60% mínimo para HIGH)
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
                
                if wick_ratio > 0.60:  # ULTRA-EXIGENTE: 60% para máxima puntuación
                    score += 2
                    details['wick_strength'] = f"Ultra-strong wick: {wick_ratio:.2f}"
                elif wick_ratio > 0.50:  # 50% para puntuación media
                    score += 1
                    details['wick_strength'] = f"Strong wick: {wick_ratio:.2f}"
                else:
                    details['wick_strength'] = f"Weak wick: {wick_ratio:.2f}"
            
            # Factor 3: Rango relativo (MÁS EXIGENTE)
            if 'atr' in df.columns:
                atr = df['atr'].iloc[-1]
                range_ratio = candle_range / atr if atr > 0 else 0
                
                if range_ratio > 1.5:  # ULTRA-EXIGENTE: 1.5x ATR
                    score += 2
                    details['range_strength'] = f"Ultra-strong range: {range_ratio:.2f}x ATR"
                elif range_ratio > 1.2:
                    score += 1
                    details['range_strength'] = f"Strong range: {range_ratio:.2f}x ATR"
                else:
                    details['range_strength'] = f"Weak range: {range_ratio:.2f}x ATR"
            
            # Factor 4: Filtro de sesión (SOLO OVERLAP Londres-NY)
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            hour = now.hour
            
            # Solo overlap: 13-17 UTC
            is_overlap = 13 <= hour <= 17
            
            if is_overlap:
                score += 1
                details['session_filter'] = f"Perfect session: OVERLAP (hour {hour})"
            else:
                details['session_filter'] = f"Poor session: outside overlap (hour {hour})"
            
            # Factor 5: NUEVO - RSI en zona óptima (evitar extremos)
            if 'rsi' in df.columns:
                rsi = df['rsi'].iloc[-1]
                
                if 40 <= rsi <= 60:  # Zona óptima
                    score += 1
                    details['rsi_zone'] = f"Optimal RSI: {rsi:.1f}"
                elif 30 <= rsi <= 70:  # Zona aceptable
                    details['rsi_zone'] = f"Acceptable RSI: {rsi:.1f}"
                else:
                    details['rsi_zone'] = f"Extreme RSI: {rsi:.1f}"
            
            # Factor 6: NUEVO - Volatilidad extrema
            if 'atr' in df.columns:
                atr_current = df['atr'].iloc[-1]
                atr_mean = df['atr'].tail(20).mean()
                volatility_ratio = atr_current / atr_mean if atr_mean > 0 else 1
                
                if volatility_ratio > 1.3:  # Volatilidad 30% superior al promedio
                    score += 1
                    details['volatility_boost'] = f"High volatility: {volatility_ratio:.2f}x avg"
                else:
                    details['volatility_boost'] = f"Normal volatility: {volatility_ratio:.2f}x avg"
            
        except Exception as e:
            details['error'] = str(e)
        
        # Recalibrar mapping para ser ULTRA-ULTRA-SELECTIVO
        # Máximo posible: 9 puntos (2+2+2+1+1+1)
        if score >= 7:  # Necesita 7/9 puntos para HIGH (77%)
            confidence = "HIGH"
        elif score >= 5:  # Necesita 5/9 puntos para MEDIUM-HIGH (55%)
            confidence = "MEDIUM-HIGH"
        elif score >= 3:  # Necesita 3/9 puntos para MEDIUM (33%)
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        return confidence, score, details
    
    def _calculate_btceur_confidence(self, signal: Dict[str, Any], df: pd.DataFrame) -> Tuple[str, int, Dict[str, Any]]:
        """
        BTCEUR - Confianza después del cruce EMA (MÁS FLEXIBLE para más señales)
        Factores:
        1. Separación EMAs (menos estricto)
        2. Fuerza RSI (rango ampliado)
        3. Volatilidad (menos exigente)
        4. Momentum adicional (nuevo)
        """
        score = 0
        details = {}
        
        try:
            close = df['close'].iloc[-1]
            
            # Factor 1: Separación EMAs (MENOS ESTRICTO)
            if 'ema_12' in df.columns and 'ema_26' in df.columns and 'atr' in df.columns:
                ema12 = df['ema_12'].iloc[-1]
                ema26 = df['ema_26'].iloc[-1]
                atr = df['atr'].iloc[-1]
                
                ema_separation = abs(ema12 - ema26) / atr if atr > 0 else 0
                
                if ema_separation > 0.15:  # Reducido de 0.3 a 0.15
                    score += 1
                    details['ema_separation'] = f"Good separation: {ema_separation:.2f}x ATR"
                else:
                    details['ema_separation'] = f"Weak separation: {ema_separation:.2f}x ATR"
            
            # Factor 2: Fuerza RSI (RANGO AMPLIADO)
            if 'rsi' in df.columns:
                rsi = df['rsi'].iloc[-1]
                rsi_strength = abs(rsi - 50)
                
                if rsi_strength > 8:  # Reducido de 12 a 8
                    score += 1
                    details['rsi_strength'] = f"Strong RSI: {rsi:.1f} (strength: {rsi_strength:.1f})"
                else:
                    details['rsi_strength'] = f"Weak RSI: {rsi:.1f} (strength: {rsi_strength:.1f})"
            
            # Factor 3: Volatilidad (MENOS EXIGENTE)
            if 'atr' in df.columns:
                atr = df['atr'].iloc[-1]
                volatility_ratio = atr / close if close > 0 else 0
                
                if volatility_ratio > 0.001:  # Reducido de 0.002 a 0.001 (0.1%)
                    score += 1
                    details['volatility'] = f"High volatility: {volatility_ratio:.4f}"
                else:
                    details['volatility'] = f"Low volatility: {volatility_ratio:.4f}"
            
            # Factor 4: NUEVO - Momentum de precio
            if len(df) > 10:
                recent_closes = df['close'].tail(10)
                price_momentum = (recent_closes.iloc[-1] - recent_closes.iloc[0]) / recent_closes.iloc[0]
                
                if abs(price_momentum) > 0.005:  # 0.5% de movimiento
                    score += 1
                    details['price_momentum'] = f"Good momentum: {price_momentum*100:.2f}%"
                else:
                    details['price_momentum'] = f"Weak momentum: {price_momentum*100:.2f}%"
            
            # Factor 5: NUEVO - Volumen relativo (si disponible)
            if 'volume' in df.columns and len(df) > 20:
                current_volume = df['volume'].iloc[-1]
                avg_volume = df['volume'].tail(20).mean()
                
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                
                if volume_ratio > 1.2:  # 20% más volumen que promedio
                    score += 1
                    details['volume_strength'] = f"High volume: {volume_ratio:.2f}x avg"
                else:
                    details['volume_strength'] = f"Normal volume: {volume_ratio:.2f}x avg"
            
        except Exception as e:
            details['error'] = str(e)
        
        # Recalibrar mapping para distribución más realista
        if score >= 4:
            confidence = "HIGH"
        elif score >= 3:
            confidence = "MEDIUM-HIGH"
        elif score >= 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
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