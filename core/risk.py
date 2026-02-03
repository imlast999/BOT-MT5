"""
Sistema de Gestión de Riesgo Consolidado

Consolida toda la lógica de gestión de riesgo que estaba fragmentada
en risk_manager.py y otros archivos.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass
from math import floor
import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

@dataclass
class RiskParameters:
    """Parámetros de riesgo para una operación"""
    suggested_lot: float
    risk_amount: float
    rr_ratio: float
    max_loss: float
    expected_profit: float
    risk_pct: float

@dataclass
class RiskAssessment:
    """Evaluación completa de riesgo"""
    approved: bool
    reason: str
    parameters: Optional[RiskParameters]
    warnings: list
    details: Dict

class RiskManager:
    """
    Gestor de riesgo consolidado que maneja:
    - Cálculo de tamaño de posición
    - Evaluación de R:R ratio
    - Límites de riesgo por operación
    - Gestión de drawdown
    """
    
    def __init__(self):
        # Configuración de riesgo desde variables de entorno
        self.default_risk_pct = float(os.getenv('MT5_RISK_PCT', '0.5'))
        self.max_risk_pct = float(os.getenv('MAX_RISK_PCT', '2.0'))
        self.min_rr_ratio = float(os.getenv('MIN_RR_RATIO', '1.5'))
        self.max_lot_size = float(os.getenv('MAX_LOT_SIZE', '1.0'))
        self.min_lot_size = float(os.getenv('MIN_LOT_SIZE', '0.01'))
        
        # Configuración específica por símbolo
        self.symbol_config = {
            'EURUSD': {
                'max_risk_pct': 1.0,
                'preferred_rr': 2.0,
                'max_lot': 0.5,
                'point_value_multiplier': 1.0
            },
            'XAUUSD': {
                'max_risk_pct': 0.8,  # Más conservador para oro
                'preferred_rr': 2.5,
                'max_lot': 0.3,
                'point_value_multiplier': 1.0
            },
            'BTCEUR': {
                'max_risk_pct': 1.5,  # Más agresivo para crypto
                'preferred_rr': 1.8,
                'max_lot': 0.2,
                'point_value_multiplier': 1.0
            }
        }
    
    def assess_signal_risk(self, signal: Dict, current_balance: float = None) -> RiskAssessment:
        """
        Evaluación completa de riesgo para una señal
        
        Args:
            signal: Diccionario con datos de la señal
            current_balance: Balance actual de la cuenta
            
        Returns:
            RiskAssessment con evaluación completa
        """
        try:
            # Obtener balance actual si no se proporciona
            if current_balance is None:
                current_balance = self._get_account_balance()
            
            if current_balance <= 0:
                return RiskAssessment(
                    approved=False,
                    reason="Invalid account balance",
                    parameters=None,
                    warnings=[],
                    details={'balance': current_balance}
                )
            
            # Extraer datos de la señal
            symbol = signal.get('symbol', 'EURUSD')
            entry = float(signal.get('entry', 0))
            sl = float(signal.get('sl', 0))
            tp = float(signal.get('tp', 0))
            
            if entry == 0 or sl == 0:
                return RiskAssessment(
                    approved=False,
                    reason="Invalid entry or SL price",
                    parameters=None,
                    warnings=[],
                    details={'entry': entry, 'sl': sl}
                )
            
            # Calcular parámetros de riesgo
            risk_params = self._calculate_risk_parameters(
                symbol, entry, sl, tp, current_balance
            )
            
            if risk_params is None:
                return RiskAssessment(
                    approved=False,
                    reason="Could not calculate risk parameters",
                    parameters=None,
                    warnings=[],
                    details={'symbol': symbol}
                )
            
            # Evaluar si el riesgo es aceptable
            warnings = []
            approved = True
            reason = "Risk assessment passed"
            
            # Verificar R:R ratio
            if risk_params.rr_ratio < self.min_rr_ratio:
                approved = False
                reason = f"Poor R:R ratio ({risk_params.rr_ratio:.2f} < {self.min_rr_ratio})"
            
            # Verificar porcentaje de riesgo
            symbol_config = self.symbol_config.get(symbol, {})
            max_risk_for_symbol = symbol_config.get('max_risk_pct', self.max_risk_pct)
            
            if risk_params.risk_pct > max_risk_for_symbol:
                approved = False
                reason = f"Risk too high ({risk_params.risk_pct:.2f}% > {max_risk_for_symbol}%)"
            
            # Verificar tamaño de lote
            if risk_params.suggested_lot > self.max_lot_size:
                warnings.append(f"Lot size capped at {self.max_lot_size}")
                risk_params.suggested_lot = self.max_lot_size
            
            if risk_params.suggested_lot < self.min_lot_size:
                warnings.append(f"Lot size increased to minimum {self.min_lot_size}")
                risk_params.suggested_lot = self.min_lot_size
            
            # Advertencias adicionales
            if risk_params.rr_ratio < 2.0:
                warnings.append("R:R ratio below 2.0 - consider better entry/exit")
            
            if risk_params.risk_pct > 1.0:
                warnings.append("Risk above 1% - high risk trade")
            
            return RiskAssessment(
                approved=approved,
                reason=reason,
                parameters=risk_params,
                warnings=warnings,
                details={
                    'symbol': symbol,
                    'balance': current_balance,
                    'symbol_config': symbol_config,
                    'calculation_time': datetime.now(timezone.utc).isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error en evaluación de riesgo: {e}")
            return RiskAssessment(
                approved=False,
                reason=f"Risk assessment error: {str(e)}",
                parameters=None,
                warnings=[],
                details={'error': str(e)}
            )
    
    def _calculate_risk_parameters(self, symbol: str, entry: float, sl: float, 
                                 tp: float, balance: float) -> Optional[RiskParameters]:
        """Calcula parámetros de riesgo para una operación"""
        try:
            # Obtener información del símbolo
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.error(f"No symbol info for {symbol}")
                return None
            
            # Configuración específica del símbolo
            symbol_config = self.symbol_config.get(symbol, {})
            risk_pct = symbol_config.get('max_risk_pct', self.default_risk_pct)
            
            # Calcular riesgo en puntos
            risk_points = abs(entry - sl)
            reward_points = abs(tp - entry) if tp != 0 else 0
            
            # Calcular R:R ratio
            rr_ratio = reward_points / risk_points if risk_points > 0 else 0
            
            # Información del símbolo
            point = symbol_info.point
            contract_size = getattr(symbol_info, 'trade_contract_size', 
                                  getattr(symbol_info, 'lot_size', 100000))
            
            # Calcular valor por punto
            point_value = contract_size * point
            
            # Calcular tamaño de lote basado en riesgo
            risk_amount = balance * (risk_pct / 100.0)
            risk_per_lot = risk_points * point_value
            
            if risk_per_lot <= 0:
                logger.error(f"Invalid risk per lot: {risk_per_lot}")
                return None
            
            raw_lot = risk_amount / risk_per_lot
            
            # Ajustar a los límites del símbolo
            vol_min = getattr(symbol_info, 'volume_min', 0.01)
            vol_max = getattr(symbol_info, 'volume_max', 100.0)
            vol_step = getattr(symbol_info, 'volume_step', 0.01)
            
            # Redondear al step más cercano
            steps = floor(raw_lot / vol_step)
            suggested_lot = max(vol_min, min(vol_max, steps * vol_step)) if steps > 0 else vol_min
            
            # Calcular valores finales
            actual_risk_amount = suggested_lot * risk_per_lot
            actual_risk_pct = (actual_risk_amount / balance) * 100
            expected_profit = suggested_lot * reward_points * point_value
            
            return RiskParameters(
                suggested_lot=suggested_lot,
                risk_amount=actual_risk_amount,
                rr_ratio=rr_ratio,
                max_loss=actual_risk_amount,
                expected_profit=expected_profit,
                risk_pct=actual_risk_pct
            )
            
        except Exception as e:
            logger.error(f"Error calculando parámetros de riesgo: {e}")
            return None
    
    def _get_account_balance(self) -> float:
        """Obtiene el balance actual de la cuenta MT5"""
        try:
            account_info = mt5.account_info()
            if account_info is None:
                logger.warning("No account info available, using default balance")
                return 10000.0  # Balance por defecto
            
            return float(account_info.balance)
            
        except Exception as e:
            logger.error(f"Error obteniendo balance de cuenta: {e}")
            return 10000.0  # Balance por defecto en caso de error
    
    def calculate_position_size(self, symbol: str, entry: float, sl: float, 
                              risk_pct: float = None) -> Tuple[float, float, float]:
        """
        Calcula el tamaño de posición óptimo
        
        Returns:
            (lot_size, risk_amount, rr_ratio)
        """
        try:
            balance = self._get_account_balance()
            
            # Crear señal temporal para usar assess_signal_risk
            temp_signal = {
                'symbol': symbol,
                'entry': entry,
                'sl': sl,
                'tp': entry + (2 * abs(entry - sl))  # Asumir R:R 2:1 por defecto
            }
            
            assessment = self.assess_signal_risk(temp_signal, balance)
            
            if assessment.approved and assessment.parameters:
                return (
                    assessment.parameters.suggested_lot,
                    assessment.parameters.risk_amount,
                    assessment.parameters.rr_ratio
                )
            else:
                logger.warning(f"Risk assessment failed: {assessment.reason}")
                return 0.01, 0.0, 0.0  # Valores mínimos seguros
                
        except Exception as e:
            logger.error(f"Error calculando tamaño de posición: {e}")
            return 0.01, 0.0, 0.0
    
    def get_risk_statistics(self) -> Dict:
        """Obtiene estadísticas del gestor de riesgo"""
        try:
            balance = self._get_account_balance()
            
            return {
                'current_balance': balance,
                'default_risk_pct': self.default_risk_pct,
                'max_risk_pct': self.max_risk_pct,
                'min_rr_ratio': self.min_rr_ratio,
                'max_lot_size': self.max_lot_size,
                'min_lot_size': self.min_lot_size,
                'symbol_configs': self.symbol_config,
                'risk_per_symbol': {
                    symbol: {
                        'max_risk_amount': balance * (config.get('max_risk_pct', self.max_risk_pct) / 100),
                        'max_lot': config.get('max_lot', self.max_lot_size)
                    }
                    for symbol, config in self.symbol_config.items()
                }
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas de riesgo: {e}")
            return {'error': str(e)}

# Instancia global del gestor de riesgo
risk_manager = RiskManager()

def get_risk_manager() -> RiskManager:
    """Obtiene la instancia global del gestor de riesgo"""
    return risk_manager

def create_risk_manager() -> RiskManager:
    """Crea una nueva instancia del gestor de riesgo (compatibilidad)"""
    return RiskManager()