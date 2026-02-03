"""
Core Trading System

Sistema consolidado de trading que integra:
- Engine de orquestación principal
- Sistema de scoring flexible
- Filtros consolidados
- Gestión de riesgo

Reemplaza la fragmentación anterior y proporciona una API unificada.
"""

from .engine import (
    TradingEngine, 
    SignalContext, 
    SignalResult,
    BotState,
    get_trading_engine,
    get_current_period_start
)

from .scoring import (
    FlexibleScoring,
    ConfirmationRule,
    ScoringResult,
    get_scoring_system
)

from .filters import (
    ConsolidatedFilters,
    FilterResult,
    get_filters_system
)

from .risk import (
    RiskManager,
    RiskParameters,
    RiskAssessment,
    get_risk_manager,
    create_risk_manager
)

# Instancias globales para compatibilidad
trading_engine = get_trading_engine()
scoring_system = get_scoring_system()
filters_system = get_filters_system()
risk_manager = get_risk_manager()

__all__ = [
    # Engine
    'TradingEngine',
    'SignalContext', 
    'SignalResult',
    'BotState',
    'get_trading_engine',
    'trading_engine',
    
    # Scoring
    'FlexibleScoring',
    'ConfirmationRule',
    'ScoringResult',
    'get_scoring_system',
    'scoring_system',
    
    # Filters
    'ConsolidatedFilters',
    'FilterResult',
    'get_filters_system',
    'filters_system',
    
    # Risk
    'RiskManager',
    'RiskParameters',
    'RiskAssessment',
    'get_risk_manager',
    'create_risk_manager',
    'risk_manager',
    
    # Utilities
    'get_current_period_start'
]