"""
Sistema de filtros avanzados para el bot de trading MT5
Incluye confluencias, sesiones, drawdown dinámico y correlación
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional
import logging
import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

class AdvancedFilterSystem:
    """Sistema completo de filtros avanzados"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.daily_drawdown = 0.0
        self.consecutive_losses = 0
        self.open_positions = {}
        self.session_filters = {
            'EURUSD': [(13, 17)],  # Solo overlap Londres-NY
            'XAUUSD': [(8, 17)],   # Solo sesión Londres
            'BTCEUR': [(0, 24)]    # 24h pero filtrar domingos
        }
        
    def confluence_filter(self, df: pd.DataFrame, signal: dict) -> Tuple[bool, str, int]:
        """
        Sistema de confluencias - Múltiples confirmaciones
        Retorna: (passed, reason, confluence_score)
        """
        confirmations = 0
        reasons = []
        
        try:
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 1. Confirmación EMA (Tendencia)
            if 'ema20' in df.columns and 'ema50' in df.columns:
                if signal['type'] == 'BUY' and last['ema20'] > last['ema50']:
                    confirmations += 1
                    reasons.append("EMA alcista")
                elif signal['type'] == 'SELL' and last['ema20'] < last['ema50']:
                    confirmations += 1
                    reasons.append("EMA bajista")
            
            # 2. Confirmación RSI (Momentum)
            if 'rsi' in df.columns:
                rsi = last['rsi']
                if signal['type'] == 'BUY' and 30 <= rsi <= 70:
                    confirmations += 1
                    reasons.append(f"RSI favorable ({rsi:.1f})")
                elif signal['type'] == 'SELL' and 30 <= rsi <= 70:
                    confirmations += 1
                    reasons.append(f"RSI favorable ({rsi:.1f})")
            
            # 3. Confirmación de Volumen
            if 'tick_volume' in df.columns:
                avg_volume = df['tick_volume'].rolling(20).mean().iloc[-1]
                current_volume = last['tick_volume']
                if current_volume > avg_volume * 1.2:
                    confirmations += 1
                    reasons.append("Volumen alto")
            
            # 4. Confirmación de Vela
            candle_body = abs(last['close'] - last['open'])
            prev_body = abs(prev['close'] - prev['open'])
            if candle_body > prev_body * 1.2:
                if (signal['type'] == 'BUY' and last['close'] > last['open']) or \
                   (signal['type'] == 'SELL' and last['close'] < last['open']):
                    confirmations += 1
                    reasons.append("Vela fuerte")
            
            # 5. Confirmación de Sesión
            if self.is_optimal_session(signal['symbol']):
                confirmations += 1
                reasons.append("Sesión óptima")
            
            # 6. Confirmación ADX (Fuerza de tendencia)
            if 'adx' in df.columns and not pd.isna(last['adx']):
                if last['adx'] > 25:
                    confirmations += 1
                    reasons.append(f"ADX fuerte ({last['adx']:.1f})")
            
            # Requerir mínimo 4 confirmaciones para señales de alta calidad
            min_confirmations = self.config.get('min_confirmations', 4)
            passed = confirmations >= min_confirmations
            
            reason = f"Confluencias: {confirmations}/{min_confirmations} - " + ", ".join(reasons)
            
            return passed, reason, confirmations
            
        except Exception as e:
            logger.exception(f"Error en confluence_filter: {e}")
            return False, f"Error en confluencias: {e}", 0
    
    def session_filter(self, symbol: str) -> Tuple[bool, str]:
        """Filtro de sesiones óptimas por símbolo"""
        try:
            now = datetime.now(timezone.utc)
            hour = now.hour
            weekday = now.weekday()  # 0=Monday, 6=Sunday
            
            # No tradear domingos para forex
            if weekday == 6 and symbol != 'BTCEUR':
                return False, "Domingo - Mercado cerrado"
            
            # Verificar sesiones óptimas
            optimal_sessions = self.session_filters.get(symbol, [(0, 24)])
            
            for start_hour, end_hour in optimal_sessions:
                if start_hour <= hour < end_hour:
                    session_name = self.get_session_name(hour)
                    return True, f"Sesión óptima: {session_name}"
            
            return False, f"Fuera de sesión óptima (hora: {hour})"
            
        except Exception as e:
            logger.exception(f"Error en session_filter: {e}")
            return False, f"Error en sesión: {e}"
    
    def drawdown_filter(self, signal: dict, current_balance: float) -> Tuple[bool, str, float]:
        """Filtro de drawdown dinámico"""
        try:
            # Calcular drawdown actual (simplificado)
            initial_balance = self.config.get('initial_balance', 5000.0)
            current_drawdown = max(0, (initial_balance - current_balance) / initial_balance * 100)
            
            # Límites dinámicos
            if current_drawdown > 15:
                return False, f"Drawdown crítico: {current_drawdown:.1f}%", 0.0
            elif current_drawdown > 10:
                risk_multiplier = 0.3  # Reducir riesgo 70%
                return True, f"Drawdown alto: {current_drawdown:.1f}% - Riesgo reducido", risk_multiplier
            elif current_drawdown > 5:
                risk_multiplier = 0.6  # Reducir riesgo 40%
                return True, f"Drawdown moderado: {current_drawdown:.1f}% - Riesgo reducido", risk_multiplier
            else:
                risk_multiplier = 1.0  # Riesgo normal
                return True, f"Drawdown bajo: {current_drawdown:.1f}%", risk_multiplier
                
        except Exception as e:
            logger.exception(f"Error en drawdown_filter: {e}")
            return True, f"Error en drawdown: {e}", 1.0
    
    def correlation_filter(self, symbol: str, signal_type: str) -> Tuple[bool, str]:
        """Filtro de correlación entre pares"""
        try:
            # Obtener posiciones abiertas
            positions = mt5.positions_get()
            if not positions:
                return True, "Sin posiciones abiertas"
            
            open_symbols = [pos.symbol for pos in positions]
            
            # Reglas de correlación
            correlations = {
                'EURUSD': ['XAUUSD'],  # EUR y oro pueden correlacionar inversamente
                'XAUUSD': ['EURUSD'],  # Oro y EUR
                'BTCEUR': []           # Crypto independiente
            }
            
            # Verificar correlaciones
            correlated_symbols = correlations.get(symbol, [])
            for corr_symbol in correlated_symbols:
                if corr_symbol in open_symbols:
                    # Permitir solo si son direcciones opuestas (diversificación)
                    existing_pos = next((pos for pos in positions if pos.symbol == corr_symbol), None)
                    if existing_pos:
                        existing_type = 'BUY' if existing_pos.type == 0 else 'SELL'
                        if existing_type == signal_type:
                            return False, f"Correlación: Ya hay {existing_type} en {corr_symbol}"
            
            # Límite de posiciones por símbolo
            symbol_positions = [pos for pos in positions if pos.symbol == symbol]
            max_positions_per_symbol = self.config.get('max_positions_per_symbol', 2)
            
            if len(symbol_positions) >= max_positions_per_symbol:
                return False, f"Máximo {max_positions_per_symbol} posiciones en {symbol}"
            
            return True, f"Correlación OK - {len(open_symbols)} posiciones abiertas"
            
        except Exception as e:
            logger.exception(f"Error en correlation_filter: {e}")
            return True, f"Error en correlación: {e}"
    
    def volatility_filter(self, df: pd.DataFrame, symbol: str) -> Tuple[bool, str]:
        """Filtro de volatilidad extrema"""
        try:
            if len(df) < 20:
                return True, "Datos insuficientes para volatilidad"
            
            # Calcular ATR
            atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
            atr_avg = (df['high'] - df['low']).rolling(50).mean().iloc[-1]
            
            volatility_ratio = atr / atr_avg if atr_avg > 0 else 1.0
            
            # Límites por símbolo
            limits = {
                'EURUSD': {'min': 0.5, 'max': 3.0},
                'XAUUSD': {'min': 0.3, 'max': 4.0},
                'BTCEUR': {'min': 0.2, 'max': 5.0}
            }
            
            symbol_limits = limits.get(symbol, {'min': 0.3, 'max': 3.0})
            
            if volatility_ratio < symbol_limits['min']:
                return False, f"Volatilidad muy baja: {volatility_ratio:.2f}"
            elif volatility_ratio > symbol_limits['max']:
                return False, f"Volatilidad extrema: {volatility_ratio:.2f}"
            else:
                return True, f"Volatilidad normal: {volatility_ratio:.2f}"
                
        except Exception as e:
            logger.exception(f"Error en volatility_filter: {e}")
            return True, f"Error en volatilidad: {e}"
    
    def is_optimal_session(self, symbol: str) -> bool:
        """Verifica si estamos en sesión óptima"""
        passed, _ = self.session_filter(symbol)
        return passed
    
    def get_session_name(self, hour: int) -> str:
        """Obtiene el nombre de la sesión actual"""
        if 0 <= hour < 9:
            return "Tokio"
        elif 8 <= hour < 17:
            return "Londres"
        elif 13 <= hour < 22:
            if 13 <= hour < 17:
                return "Overlap Londres-NY"
            else:
                return "Nueva York"
        else:
            return "Fuera de sesiones"
    
    def apply_all_filters(self, df: pd.DataFrame, signal: dict, current_balance: float) -> Tuple[bool, str, dict]:
        """
        Aplica todos los filtros avanzados
        Retorna: (passed, reason, filter_info)
        """
        filter_info = {}
        
        try:
            symbol = signal.get('symbol', '')
            signal_type = signal.get('type', '')
            
            # 1. Filtro de confluencias (CRÍTICO)
            confluence_passed, confluence_reason, confluence_score = self.confluence_filter(df, signal)
            filter_info['confluence'] = {
                'passed': confluence_passed,
                'reason': confluence_reason,
                'score': confluence_score
            }
            
            if not confluence_passed:
                return False, f"❌ {confluence_reason}", filter_info
            
            # 2. Filtro de sesión
            session_passed, session_reason = self.session_filter(symbol)
            filter_info['session'] = {
                'passed': session_passed,
                'reason': session_reason
            }
            
            if not session_passed:
                return False, f"❌ {session_reason}", filter_info
            
            # 3. Filtro de drawdown
            drawdown_passed, drawdown_reason, risk_multiplier = self.drawdown_filter(signal, current_balance)
            filter_info['drawdown'] = {
                'passed': drawdown_passed,
                'reason': drawdown_reason,
                'risk_multiplier': risk_multiplier
            }
            
            if not drawdown_passed:
                return False, f"❌ {drawdown_reason}", filter_info
            
            # 4. Filtro de correlación
            correlation_passed, correlation_reason = self.correlation_filter(symbol, signal_type)
            filter_info['correlation'] = {
                'passed': correlation_passed,
                'reason': correlation_reason
            }
            
            if not correlation_passed:
                return False, f"❌ {correlation_reason}", filter_info
            
            # 5. Filtro de volatilidad
            volatility_passed, volatility_reason = self.volatility_filter(df, symbol)
            filter_info['volatility'] = {
                'passed': volatility_passed,
                'reason': volatility_reason
            }
            
            if not volatility_passed:
                return False, f"❌ {volatility_reason}", filter_info
            
            # ✅ Todos los filtros pasados
            success_reasons = [
                f"✅ {confluence_reason}",
                f"✅ {session_reason}",
                f"✅ {drawdown_reason}",
                f"✅ {correlation_reason}",
                f"✅ {volatility_reason}"
            ]
            
            # Añadir información de riesgo ajustado
            if risk_multiplier < 1.0:
                signal['risk_multiplier'] = risk_multiplier
                signal['adjusted_risk'] = True
            
            return True, " | ".join(success_reasons), filter_info
            
        except Exception as e:
            logger.exception(f"Error en apply_all_filters: {e}")
            return False, f"❌ Error en filtros: {e}", filter_info


def create_advanced_filter_system(config: dict = None) -> AdvancedFilterSystem:
    """Factory function para crear el sistema de filtros"""
    return AdvancedFilterSystem(config)