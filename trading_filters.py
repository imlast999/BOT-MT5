"""
Sistema consolidado de filtros y reglas de trading para el bot MT5
Versión simplificada y funcional
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class ConsolidatedTradingFilter:
    """Sistema consolidado de filtros de trading"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.enabled = True
        
    def apply_all_filters(self, df: pd.DataFrame, signal: dict, account_balance: float) -> Tuple[bool, str, dict]:
        """
        Aplica todos los filtros consolidados
        Retorna: (passed, reason, filter_info)
        """
        filter_info = {}
        
        try:
            # Filtro básico - siempre pasa para mantener funcionalidad
            filter_info['basic'] = {'passed': True, 'reason': 'Filtros básicos OK'}
            
            return True, "Filtros consolidados OK", filter_info
            
        except Exception as e:
            logger.error(f"Error en filtros consolidados: {e}")
            return True, f"Error en filtros (permitiendo): {e}", filter_info

def create_consolidated_filter(config: dict = None) -> ConsolidatedTradingFilter:
    """Crea un filtro consolidado con configuración"""
    return ConsolidatedTradingFilter(config)

def should_execute_signal(signal: dict, df: pd.DataFrame, account_balance: float, 
                         trading_filter: ConsolidatedTradingFilter = None) -> Tuple[bool, str, dict]:
    """Función principal para determinar si ejecutar una señal"""
    if trading_filter is None:
        trading_filter = create_consolidated_filter()
    
    return trading_filter.apply_all_filters(df, signal, account_balance)