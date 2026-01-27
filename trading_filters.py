"""
Sistema consolidado de filtros y reglas de trading para el bot MT5
Combina gestión de riesgo, filtros de mercado, confluencias y sesiones
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging
import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

@dataclass
class RiskParameters:
    """Parámetros de gestión de riesgo"""
    max_risk_per_trade: float = 0.5  # % del balance
    max_daily_risk: float = 2.0      # % del balance total por día
    max_drawdown: float = 10.0       # % máximo de drawdown
    risk_reward_min: float = 1.5     # Ratio mínimo R:R
    max_correlation: float = 0.7     # Correlación máxima entre posiciones
    max_positions: int = 3           # Máximo de posiciones simultáneas

class ConsolidatedTradingFilter:
    """Sistema consolidado de filtros de trading"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.risk_params = RiskParameters()
        self.daily_risk_used = 0.0
        self.current_drawdown = 0.0
        self.open_positions = []
        self.consecutive_losses = 0
        
        # Sesiones optimizadas por símbolo
        self.session_filters = {
            'EURUSD': [(8, 22)],   # Londres + NY
            'XAUUSD': [(8, 22)],   # Londres + NY  
            'BTCEUR': [(0, 24)]    # 24h pero filtrar domingos
        }
    
    def apply_all_filters(self, df: pd.DataFrame, signal: dict, account_balance: float) -> Tuple[bool, str, dict]:
        """
        Aplica todos los filtros consolidados
        Retorna: (passed, reason, filter_info)
        """
        filter_info = {}
        symbol = signal.get('symbol', '')
        signal_type = signal.get('type', '')
        
        try:
            # 1. Filtro de gestión de riesgo (CRÍTICO)
            risk_passed, risk_reason = self._risk_management_filter(signal, account_balance)
            filter_info['risk'] = {'passed': risk_passed, 'reason': risk_reason}
            if not risk_passed:
                return False, f"❌ Riesgo: {risk_reason}", filter_info
            
            # 2. Filtro de sesión
            session_passed, session_reason = self._session_filter(symbol)
            filter_info['session'] = {'passed': session_passed, 'reason': session_reason}
            if not session_passed:
                return False, f"❌ {session_reason}", filter_info
            
            # 3. Filtro de confluencias
            confluence_passed, confluence_reason, confluence_score = self._confluence_filter(df, signal)
            filter_info['confluence'] = {
                'passed': confluence_passed, 
                'reason': confluence_reason, 
                'score': confluence_score
            }
            if not confluence_passed:
                return False, f"❌ {confluence_reason}", filter_info
            
            # 4. Filtro de volatilidad
            volatility_passed, volatility_reason = self._volatility_filter(df, symbol)
            filter_info['volatility'] = {'passed': volatility_passed, 'reason': volatility_reason}
            if not volatility_passed:
                return False, f"❌ {volatility_reason}", filter_info
            
            # 5. Filtro de correlación
            correlation_passed, correlation_reason = self._correlation_filter(symbol, signal_type)
            filter_info['correlation'] = {'passed': correlation_passed, 'reason': correlation_reason}
            if not correlation_passed:
                return False, f"❌ {correlation_reason}", filter_info
            
            # 6. Filtro de drawdown dinámico
            drawdown_passed, drawdown_reason, risk_multiplier = self._drawdown_filter(account_balance)
            filter_info['drawdown'] = {
                'passed': drawdown_passed, 
                'reason': drawdown_reason, 
                'risk_multiplier': risk_multiplier
            }
            if not drawdown_passed:
                return False, f"❌ {drawdown_reason}", filter_info
            
            # Ajustar riesgo si es necesario
            if risk_multiplier < 1.0:
                signal['risk_multiplier'] = risk_multiplier
                signal['adjusted_risk'] = True
            
            # ✅ Todos los filtros pasados
            success_reasons = [
                f"✅ {risk_reason}",
                f"✅ {session_reason}", 
                f"✅ {confluence_reason}",
                f"✅ {volatility_reason}",
                f"✅ {correlation_reason}",
                f"✅ {drawdown_reason}"
            ]
            
            return True, " | ".join(success_reasons), filter_info
            
        except Exception as e:
            logger.exception(f"Error en apply_all_filters: {e}")
            return False, f"❌ Error en filtros: {e}", filter_info
    
    def _risk_management_filter(self, signal: dict, account_balance: float) -> Tuple[bool, str]:
        """Filtro de gestión de riesgo"""
        try:
            entry = float(signal.get('entry', 0))
            sl = float(signal.get('sl', 0))
            tp = float(signal.get('tp', entry))
            
            if entry == sl:
                return False, "SL igual a entrada"
            
            # Verificar ratio R:R
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            if risk > 0:
                rr_ratio = reward / risk
                if rr_ratio < self.risk_params.risk_reward_min:
                    return False, f"R:R insuficiente: {rr_ratio:.2f} < {self.risk_params.risk_reward_min}"
            
            # Verificar riesgo diario
            risk_amount = risk * account_balance * (self.risk_params.max_risk_per_trade / 100)
            if self.daily_risk_used + risk_amount > account_balance * (self.risk_params.max_daily_risk / 100):
                return False, "Límite de riesgo diario excedido"
            
            # Verificar máximo de posiciones
            if len(self.open_positions) >= self.risk_params.max_positions:
                return False, "Máximo de posiciones simultáneas alcanzado"
            
            return True, f"Gestión de riesgo OK (R:R: {rr_ratio:.2f})"
            
        except Exception as e:
            return False, f"Error en gestión de riesgo: {e}"
    
    def _session_filter(self, symbol: str) -> Tuple[bool, str]:
        """Filtro de sesiones óptimas"""
        try:
            now = datetime.now(timezone.utc)
            hour = now.hour
            weekday = now.weekday()  # 0=Monday, 6=Sunday
            
            # No tradear domingos para forex
            if weekday == 6 and symbol != 'BTCEUR':
                return False, "Domingo - Mercado forex cerrado"
            
            # Sesiones por símbolo
            if symbol in ['EURUSD', 'XAUUSD']:
                if 8 <= hour < 22:  # Londres + NY
                    session_name = self._get_session_name(hour)
                    return True, f"Sesión activa: {session_name}"
            elif symbol == 'BTCEUR':
                if weekday == 6 and hour > 20:  # Domingo tarde
                    return False, "Domingo tarde - Baja liquidez crypto"
                return True, "Crypto 24/7"
            
            # Para otros símbolos
            if 6 <= hour < 23:
                session_name = self._get_session_name(hour)
                return True, f"Sesión extendida: {session_name}"
            
            return False, f"Fuera de horario (hora: {hour})"
            
        except Exception as e:
            return True, f"Error en sesión (permitiendo): {e}"
    
    def _confluence_filter(self, df: pd.DataFrame, signal: dict) -> Tuple[bool, str, int]:
        """Filtro de confluencias múltiples"""
        try:
            confirmations = 0
            reasons = []
            available_indicators = 0
            
            if len(df) < 2:
                return False, "Datos insuficientes", 0
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 1. Confirmación EMA (Tendencia)
            if 'ema20' in df.columns and 'ema50' in df.columns:
                available_indicators += 1
                if signal['type'] == 'BUY' and last['ema20'] > last['ema50']:
                    confirmations += 1
                    reasons.append("EMA alcista")
                elif signal['type'] == 'SELL' and last['ema20'] < last['ema50']:
                    confirmations += 1
                    reasons.append("EMA bajista")
            
            # 2. Confirmación RSI
            if 'rsi' in df.columns:
                available_indicators += 1
                rsi = last['rsi']
                if signal['type'] == 'BUY' and 30 <= rsi <= 70:
                    confirmations += 1
                    reasons.append(f"RSI favorable ({rsi:.1f})")
                elif signal['type'] == 'SELL' and 30 <= rsi <= 70:
                    confirmations += 1
                    reasons.append(f"RSI favorable ({rsi:.1f})")
            
            # 3. Confirmación de vela direccional
            available_indicators += 1
            candle_body = abs(last['close'] - last['open'])
            prev_body = abs(prev['close'] - prev['open'])
            if candle_body > prev_body * 0.8:
                if (signal['type'] == 'BUY' and last['close'] > last['open']) or \
                   (signal['type'] == 'SELL' and last['close'] < last['open']):
                    confirmations += 1
                    reasons.append("Vela direccional")
            
            # 4. Confirmación de sesión
            available_indicators += 1
            if self._is_optimal_session(signal['symbol']):
                confirmations += 1
                reasons.append("Sesión óptima")
            
            # 5. Confirmación R:R
            available_indicators += 1
            rr_ratio = signal.get('rr_ratio', 0)
            if rr_ratio >= 2.0:
                confirmations += 1
                reasons.append(f"R:R favorable ({rr_ratio:.1f})")
            
            # Lógica de aprobación
            if available_indicators == 0:
                return False, "Sin indicadores disponibles", 0
            
            min_confirmations = max(2, available_indicators // 2)  # Al menos 50%
            passed = confirmations >= min_confirmations
            
            reason = f"Confluencias: {confirmations}/{available_indicators} - " + ", ".join(reasons)
            return passed, reason, confirmations
            
        except Exception as e:
            logger.exception(f"Error en confluence_filter: {e}")
            return False, f"Error en confluencias: {e}", 0
    
    def _volatility_filter(self, df: pd.DataFrame, symbol: str) -> Tuple[bool, str]:
        """Filtro de volatilidad extrema"""
        try:
            if len(df) < 20:
                return True, "Datos insuficientes (permitiendo)"
            
            # Calcular ATR
            atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
            atr_avg = (df['high'] - df['low']).rolling(50).mean().iloc[-1]
            
            if atr_avg <= 0:
                return True, "ATR inválido (permitiendo)"
            
            volatility_ratio = atr / atr_avg
            
            # Límites por símbolo
            limits = {
                'EURUSD': {'min': 0.3, 'max': 4.0},
                'XAUUSD': {'min': 0.2, 'max': 5.0},
                'BTCEUR': {'min': 0.2, 'max': 6.0}
            }
            
            symbol_limits = limits.get(symbol, {'min': 0.2, 'max': 4.0})
            
            if volatility_ratio < symbol_limits['min']:
                return False, f"Volatilidad muy baja: {volatility_ratio:.2f}"
            elif volatility_ratio > symbol_limits['max']:
                return False, f"Volatilidad muy alta: {volatility_ratio:.2f}"
            
            return True, f"Volatilidad OK: {volatility_ratio:.2f}"
            
        except Exception as e:
            return True, f"Error volatilidad (permitiendo): {e}"
    
    def _correlation_filter(self, symbol: str, signal_type: str) -> Tuple[bool, str]:
        """Filtro de correlación entre pares"""
        try:
            positions = mt5.positions_get()
            if not positions:
                return True, "Sin posiciones abiertas"
            
            # Límite de posiciones por símbolo
            symbol_positions = [pos for pos in positions if pos.symbol == symbol]
            max_per_symbol = self.config.get('max_positions_per_symbol', 2)
            
            if len(symbol_positions) >= max_per_symbol:
                return False, f"Máximo {max_per_symbol} posiciones en {symbol}"
            
            return True, f"Correlación OK - {len(positions)} posiciones totales"
            
        except Exception as e:
            return True, f"Error correlación: {e}"
    
    def _drawdown_filter(self, current_balance: float) -> Tuple[bool, str, float]:
        """Filtro de drawdown dinámico"""
        try:
            initial_balance = self.config.get('initial_balance', 5000.0)
            current_drawdown = max(0, (initial_balance - current_balance) / initial_balance * 100)
            
            if current_drawdown > 15:
                return False, f"Drawdown crítico: {current_drawdown:.1f}%", 0.0
            elif current_drawdown > 10:
                return True, f"Drawdown alto: {current_drawdown:.1f}% - Riesgo reducido", 0.3
            elif current_drawdown > 5:
                return True, f"Drawdown moderado: {current_drawdown:.1f}% - Riesgo reducido", 0.6
            else:
                return True, f"Drawdown bajo: {current_drawdown:.1f}%", 1.0
                
        except Exception as e:
            return True, f"Error drawdown: {e}", 1.0
    
    def _get_session_name(self, hour: int) -> str:
        """Obtiene el nombre de la sesión"""
        if 0 <= hour < 9:
            return "Tokio"
        elif 8 <= hour < 17:
            return "Londres"
        elif 13 <= hour < 22:
            return "Overlap Londres-NY" if 13 <= hour < 17 else "Nueva York"
        else:
            return "Fuera de sesiones"
    
    def _is_optimal_session(self, symbol: str) -> bool:
        """Verifica si estamos en sesión óptima"""
        passed, _ = self._session_filter(symbol)
        return passed
    
    def calculate_position_size(self, signal: dict, account_balance: float) -> float:
        """Calcula el tamaño de posición óptimo"""
        try:
            entry = float(signal.get('entry', 0))
            sl = float(signal.get('sl', 0))
            
            if entry == sl:
                return 0.0
            
            risk_points = abs(entry - sl)
            risk_amount = account_balance * (self.risk_params.max_risk_per_trade / 100)
            
            # Ajustar por multiplicador de riesgo si existe
            risk_multiplier = signal.get('risk_multiplier', 1.0)
            risk_amount *= risk_multiplier
            
            # Valor del pip aproximado (simplificado)
            pip_values = {
                'EURUSD': 10,
                'XAUUSD': 1,
                'BTCEUR': 0.1
            }
            
            symbol = signal.get('symbol', 'EURUSD')
            pip_value = pip_values.get(symbol, 10)
            
            lot_size = risk_amount / (risk_points * pip_value * 100000)
            return round(max(0.01, lot_size), 2)
            
        except Exception as e:
            logger.exception(f"Error calculando position size: {e}")
            return 0.01

# Funciones de utilidad
def create_consolidated_filter(config: dict = None) -> ConsolidatedTradingFilter:
    """Crea un filtro consolidado con configuración"""
    return ConsolidatedTradingFilter(config)

def should_execute_signal(signal: dict, df: pd.DataFrame, account_balance: float, 
                         trading_filter: ConsolidatedTradingFilter = None) -> Tuple[bool, str, dict]:
    """Función principal para determinar si ejecutar una señal"""
    if trading_filter is None:
        trading_filter = create_consolidated_filter()
    
    return trading_filter.apply_all_filters(df, signal, account_balance)