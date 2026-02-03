"""
Services Package

Servicios consolidados del bot de trading que proporcionan:
- Logging inteligente
- Ejecución de trades
- Dashboard y métricas
- Funcionalidades transversales

Reemplaza la fragmentación anterior de funcionalidades dispersas.
"""

from .logging import (
    IntelligentLogger,
    get_intelligent_logger,
    log_event,
    log_signal_evaluation,
    log_command,
    log_trading
)

from .execution import (
    ExecutionService,
    ExecutionResult,
    PositionInfo,
    get_execution_service
)

from .dashboard import (
    DashboardService,
    DashboardMetrics,
    SignalEvent,
    get_dashboard_service,
    start_enhanced_dashboard,
    stop_enhanced_dashboard,
    add_signal_to_enhanced_dashboard,
    update_dashboard_stats
)

# Instancias globales para compatibilidad
intelligent_logger = get_intelligent_logger()
execution_service = get_execution_service()
dashboard_service = get_dashboard_service()

__all__ = [
    # Logging
    'IntelligentLogger',
    'get_intelligent_logger',
    'intelligent_logger',
    'log_event',
    'log_signal_evaluation',
    'log_command',
    'log_trading',
    
    # Execution
    'ExecutionService',
    'ExecutionResult',
    'PositionInfo',
    'get_execution_service',
    'execution_service',
    
    # Dashboard
    'DashboardService',
    'DashboardMetrics',
    'SignalEvent',
    'get_dashboard_service',
    'dashboard_service',
    'start_enhanced_dashboard',
    'stop_enhanced_dashboard',
    'add_signal_to_enhanced_dashboard',
    'update_dashboard_stats'
]