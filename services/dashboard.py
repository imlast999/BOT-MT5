"""
Servicio de Dashboard Consolidado

Consolida toda la funcionalidad de dashboard que estaba fragmentada en:
- live_dashboard.py
- Funciones de dashboard en bot.py
- Métricas dispersas en otros archivos
"""

import logging
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
import threading
import time

logger = logging.getLogger(__name__)

@dataclass
class DashboardMetrics:
    """Métricas consolidadas del dashboard"""
    # Métricas de señales
    signals_today: int = 0
    signals_shown: int = 0
    signals_executed: int = 0
    signals_rejected: int = 0
    
    # Métricas por símbolo
    symbol_activity: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    symbol_performance: Dict[str, Dict] = field(default_factory=dict)
    
    # Métricas de confianza
    confidence_distribution: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Métricas de trading
    positions_open: int = 0
    total_profit: float = 0.0
    win_rate: float = 0.0
    
    # Métricas de sistema
    uptime_seconds: int = 0
    last_signal_time: Optional[datetime] = None
    system_status: str = "RUNNING"

@dataclass
class SignalEvent:
    """Evento de señal para el dashboard"""
    timestamp: datetime
    symbol: str
    strategy: str
    signal_type: str
    confidence: str
    score: float
    shown: bool
    executed: bool
    rejection_reason: Optional[str] = None

class DashboardService:
    """
    Servicio consolidado de dashboard que proporciona:
    - Métricas en tiempo real
    - Historial de señales
    - Estadísticas de performance
    - API para frontend
    - Persistencia de datos
    """
    
    def __init__(self):
        self.start_time = datetime.now(timezone.utc)
        self.metrics = DashboardMetrics()
        
        # Historial de eventos (buffer circular)
        self.signal_history = deque(maxlen=1000)
        self.performance_history = deque(maxlen=100)  # Últimas 100 métricas de performance
        
        # Configuración
        self.dashboard_config = {
            'update_interval': int(os.getenv('DASHBOARD_UPDATE_INTERVAL', '30')),  # segundos
            'history_retention_hours': int(os.getenv('DASHBOARD_HISTORY_HOURS', '24')),
            'enable_persistence': os.getenv('DASHBOARD_PERSISTENCE', '1') == '1',
            'data_file': os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dashboard_data.json')
        }
        
        # Estado del dashboard
        self.is_running = False
        self.update_thread = None
        self.lock = threading.Lock()
        
        # Cargar datos persistidos
        if self.dashboard_config['enable_persistence']:
            self._load_persisted_data()
    
    def start(self):
        """Inicia el servicio de dashboard"""
        try:
            with self.lock:
                if self.is_running:
                    logger.warning("Dashboard service already running")
                    return
                
                self.is_running = True
                self.start_time = datetime.now(timezone.utc)
                
                # Iniciar hilo de actualización
                self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
                self.update_thread.start()
                
                logger.info("Dashboard service started successfully")
                
        except Exception as e:
            logger.error(f"Error starting dashboard service: {e}")
            self.is_running = False
    
    def stop(self):
        """Detiene el servicio de dashboard"""
        try:
            with self.lock:
                if not self.is_running:
                    return
                
                self.is_running = False
                
                # Guardar datos antes de cerrar
                if self.dashboard_config['enable_persistence']:
                    self._save_persisted_data()
                
                logger.info("Dashboard service stopped")
                
        except Exception as e:
            logger.error(f"Error stopping dashboard service: {e}")
    
    def add_signal_event(self, symbol: str, strategy: str, signal_type: str,
                        confidence: str, score: float, shown: bool, 
                        executed: bool = False, rejection_reason: str = None):
        """
        Añade un evento de señal al dashboard
        
        Args:
            symbol: Símbolo del instrumento
            strategy: Estrategia utilizada
            signal_type: Tipo de señal (BUY/SELL)
            confidence: Nivel de confianza
            score: Score numérico
            shown: Si la señal fue mostrada
            executed: Si la señal fue ejecutada
            rejection_reason: Razón de rechazo si aplica
        """
        try:
            with self.lock:
                # Crear evento
                event = SignalEvent(
                    timestamp=datetime.now(timezone.utc),
                    symbol=symbol,
                    strategy=strategy,
                    signal_type=signal_type,
                    confidence=confidence,
                    score=score,
                    shown=shown,
                    executed=executed,
                    rejection_reason=rejection_reason
                )
                
                # Añadir al historial
                self.signal_history.append(event)
                
                # Actualizar métricas
                self._update_signal_metrics(event)
                
                # Actualizar tiempo de última señal
                self.metrics.last_signal_time = event.timestamp
                
        except Exception as e:
            logger.error(f"Error adding signal event: {e}")
    
    def update_trading_metrics(self, positions_open: int, total_profit: float, 
                             win_rate: float):
        """
        Actualiza métricas de trading
        
        Args:
            positions_open: Número de posiciones abiertas
            total_profit: Profit total
            win_rate: Tasa de ganancia (%)
        """
        try:
            with self.lock:
                self.metrics.positions_open = positions_open
                self.metrics.total_profit = total_profit
                self.metrics.win_rate = win_rate
                
                # Añadir al historial de performance
                performance_snapshot = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'positions_open': positions_open,
                    'total_profit': total_profit,
                    'win_rate': win_rate,
                    'signals_today': self.metrics.signals_today
                }
                
                self.performance_history.append(performance_snapshot)
                
        except Exception as e:
            logger.error(f"Error updating trading metrics: {e}")
    
    def get_current_metrics(self) -> Dict:
        """Obtiene métricas actuales del dashboard"""
        try:
            with self.lock:
                # Calcular uptime
                uptime = datetime.now(timezone.utc) - self.start_time
                self.metrics.uptime_seconds = int(uptime.total_seconds())
                
                return {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'uptime_seconds': self.metrics.uptime_seconds,
                    'uptime_formatted': self._format_uptime(uptime),
                    'system_status': self.metrics.system_status,
                    
                    # Métricas de señales
                    'signals': {
                        'today': self.metrics.signals_today,
                        'shown': self.metrics.signals_shown,
                        'executed': self.metrics.signals_executed,
                        'rejected': self.metrics.signals_rejected,
                        'show_rate': (self.metrics.signals_shown / self.metrics.signals_today * 100) if self.metrics.signals_today > 0 else 0,
                        'execution_rate': (self.metrics.signals_executed / self.metrics.signals_shown * 100) if self.metrics.signals_shown > 0 else 0,
                        'last_signal_time': self.metrics.last_signal_time.isoformat() if self.metrics.last_signal_time else None
                    },
                    
                    # Métricas por símbolo
                    'symbols': {
                        'activity': dict(self.metrics.symbol_activity),
                        'performance': self.metrics.symbol_performance
                    },
                    
                    # Distribución de confianza
                    'confidence_distribution': dict(self.metrics.confidence_distribution),
                    
                    # Métricas de trading
                    'trading': {
                        'positions_open': self.metrics.positions_open,
                        'total_profit': self.metrics.total_profit,
                        'win_rate': self.metrics.win_rate
                    }
                }
                
        except Exception as e:
            logger.error(f"Error getting current metrics: {e}")
            return {'error': str(e)}
    
    def get_signal_history(self, hours: int = 24, symbol: str = None) -> List[Dict]:
        """
        Obtiene historial de señales
        
        Args:
            hours: Horas hacia atrás a incluir
            symbol: Filtrar por símbolo específico (opcional)
            
        Returns:
            Lista de eventos de señales
        """
        try:
            with self.lock:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
                
                filtered_events = []
                for event in self.signal_history:
                    # Filtrar por tiempo
                    if event.timestamp < cutoff_time:
                        continue
                    
                    # Filtrar por símbolo si se especifica
                    if symbol and event.symbol != symbol:
                        continue
                    
                    filtered_events.append({
                        'timestamp': event.timestamp.isoformat(),
                        'symbol': event.symbol,
                        'strategy': event.strategy,
                        'signal_type': event.signal_type,
                        'confidence': event.confidence,
                        'score': event.score,
                        'shown': event.shown,
                        'executed': event.executed,
                        'rejection_reason': event.rejection_reason
                    })
                
                return filtered_events
                
        except Exception as e:
            logger.error(f"Error getting signal history: {e}")
            return []
    
    def get_performance_history(self, hours: int = 24) -> List[Dict]:
        """
        Obtiene historial de performance
        
        Args:
            hours: Horas hacia atrás a incluir
            
        Returns:
            Lista de snapshots de performance
        """
        try:
            with self.lock:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
                
                filtered_performance = []
                for snapshot in self.performance_history:
                    snapshot_time = datetime.fromisoformat(snapshot['timestamp'].replace('Z', '+00:00'))
                    if snapshot_time >= cutoff_time:
                        filtered_performance.append(snapshot)
                
                return filtered_performance
                
        except Exception as e:
            logger.error(f"Error getting performance history: {e}")
            return []
    
    def get_dashboard_html(self) -> str:
        """
        Genera HTML del dashboard para visualización web
        
        Returns:
            HTML string del dashboard
        """
        try:
            metrics = self.get_current_metrics()
            signal_history = self.get_signal_history(hours=6)  # Últimas 6 horas
            
            html_template = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Trading Bot Dashboard</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
                    .container { max-width: 1200px; margin: 0 auto; }
                    .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                    .metric { display: inline-block; margin: 10px 20px 10px 0; }
                    .metric-value { font-size: 24px; font-weight: bold; color: #2196F3; }
                    .metric-label { font-size: 12px; color: #666; }
                    .status-running { color: #4CAF50; }
                    .status-error { color: #F44336; }
                    .signal-item { padding: 8px; margin: 4px 0; border-left: 4px solid #ddd; background: #f9f9f9; }
                    .signal-buy { border-left-color: #4CAF50; }
                    .signal-sell { border-left-color: #F44336; }
                    .confidence-high { color: #4CAF50; font-weight: bold; }
                    .confidence-medium { color: #FF9800; }
                    .confidence-low { color: #F44336; }
                    .refresh-info { text-align: center; color: #666; font-size: 12px; margin-top: 20px; }
                </style>
                <script>
                    setTimeout(function() { location.reload(); }, 30000); // Auto-refresh cada 30s
                </script>
            </head>
            <body>
                <div class="container">
                    <h1>🤖 Trading Bot Dashboard</h1>
                    
                    <div class="card">
                        <h2>📊 Estado del Sistema</h2>
                        <div class="metric">
                            <div class="metric-value status-running">{system_status}</div>
                            <div class="metric-label">Estado</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{uptime_formatted}</div>
                            <div class="metric-label">Tiempo Activo</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{last_signal}</div>
                            <div class="metric-label">Última Señal</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>🎯 Métricas de Señales</h2>
                        <div class="metric">
                            <div class="metric-value">{signals_today}</div>
                            <div class="metric-label">Señales Hoy</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{signals_shown}</div>
                            <div class="metric-label">Mostradas</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{signals_executed}</div>
                            <div class="metric-label">Ejecutadas</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{show_rate:.1f}%</div>
                            <div class="metric-label">Tasa Mostradas</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{execution_rate:.1f}%</div>
                            <div class="metric-label">Tasa Ejecución</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>💹 Métricas de Trading</h2>
                        <div class="metric">
                            <div class="metric-value">{positions_open}</div>
                            <div class="metric-label">Posiciones Abiertas</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{total_profit:.2f} EUR</div>
                            <div class="metric-label">Profit Total</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{win_rate:.1f}%</div>
                            <div class="metric-label">Win Rate</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>📈 Actividad por Símbolo</h2>
                        {symbol_activity}
                    </div>
                    
                    <div class="card">
                        <h2>🕐 Historial de Señales (Últimas 6h)</h2>
                        {signal_history_html}
                    </div>
                    
                    <div class="refresh-info">
                        Actualizado: {timestamp}<br>
                        Auto-refresh cada 30 segundos
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Formatear datos para el template
            last_signal = "Nunca" if not metrics['signals']['last_signal_time'] else \
                         datetime.fromisoformat(metrics['signals']['last_signal_time'].replace('Z', '+00:00')).strftime('%H:%M:%S')
            
            # Generar HTML de actividad por símbolo
            symbol_activity_html = ""
            for symbol, count in metrics['symbols']['activity'].items():
                symbol_activity_html += f'<div class="metric"><div class="metric-value">{count}</div><div class="metric-label">{symbol}</div></div>'
            
            # Generar HTML de historial de señales
            signal_history_html = ""
            for signal in signal_history[-20:]:  # Últimas 20 señales
                css_class = f"signal-item signal-{signal['signal_type'].lower()}"
                confidence_class = f"confidence-{signal['confidence'].lower().replace('-', '')}"
                
                time_str = datetime.fromisoformat(signal['timestamp'].replace('Z', '+00:00')).strftime('%H:%M:%S')
                status = "✅ Ejecutada" if signal['executed'] else ("👁️ Mostrada" if signal['shown'] else f"❌ {signal['rejection_reason']}")
                
                signal_history_html += f"""
                <div class="{css_class}">
                    <strong>{time_str}</strong> - {signal['symbol']} {signal['signal_type']} 
                    (<span class="{confidence_class}">{signal['confidence']}</span>) - {status}
                </div>
                """
            
            # Rellenar template
            html = html_template.format(
                system_status=metrics['system_status'],
                uptime_formatted=metrics['uptime_formatted'],
                last_signal=last_signal,
                signals_today=metrics['signals']['today'],
                signals_shown=metrics['signals']['shown'],
                signals_executed=metrics['signals']['executed'],
                show_rate=metrics['signals']['show_rate'],
                execution_rate=metrics['signals']['execution_rate'],
                positions_open=metrics['trading']['positions_open'],
                total_profit=metrics['trading']['total_profit'],
                win_rate=metrics['trading']['win_rate'],
                symbol_activity=symbol_activity_html,
                signal_history_html=signal_history_html,
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            return html
            
        except Exception as e:
            logger.error(f"Error generating dashboard HTML: {e}")
            return f"<html><body><h1>Dashboard Error</h1><p>{str(e)}</p></body></html>"
    
    def _update_signal_metrics(self, event: SignalEvent):
        """Actualiza métricas basadas en un evento de señal"""
        self.metrics.signals_today += 1
        self.metrics.symbol_activity[event.symbol] += 1
        self.metrics.confidence_distribution[event.confidence] += 1
        
        if event.shown:
            self.metrics.signals_shown += 1
        else:
            self.metrics.signals_rejected += 1
        
        if event.executed:
            self.metrics.signals_executed += 1
        
        # Actualizar performance por símbolo
        if event.symbol not in self.metrics.symbol_performance:
            self.metrics.symbol_performance[event.symbol] = {
                'total_signals': 0,
                'shown_signals': 0,
                'executed_signals': 0,
                'avg_confidence_score': 0.0
            }
        
        symbol_perf = self.metrics.symbol_performance[event.symbol]
        symbol_perf['total_signals'] += 1
        
        if event.shown:
            symbol_perf['shown_signals'] += 1
        
        if event.executed:
            symbol_perf['executed_signals'] += 1
        
        # Actualizar score promedio (simple)
        current_avg = symbol_perf['avg_confidence_score']
        total = symbol_perf['total_signals']
        symbol_perf['avg_confidence_score'] = ((current_avg * (total - 1)) + event.score) / total
    
    def _update_loop(self):
        """Loop principal de actualización del dashboard"""
        while self.is_running:
            try:
                # Limpiar datos antiguos
                self._cleanup_old_data()
                
                # Guardar datos si está habilitado
                if self.dashboard_config['enable_persistence']:
                    self._save_persisted_data()
                
                # Esperar hasta la próxima actualización
                time.sleep(self.dashboard_config['update_interval'])
                
            except Exception as e:
                logger.error(f"Error in dashboard update loop: {e}")
                time.sleep(5)  # Esperar menos tiempo en caso de error
    
    def _cleanup_old_data(self):
        """Limpia datos antiguos del historial"""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.dashboard_config['history_retention_hours'])
            
            # Limpiar historial de señales
            while self.signal_history and self.signal_history[0].timestamp < cutoff_time:
                self.signal_history.popleft()
            
            # Limpiar historial de performance
            while self.performance_history:
                snapshot_time = datetime.fromisoformat(self.performance_history[0]['timestamp'].replace('Z', '+00:00'))
                if snapshot_time < cutoff_time:
                    self.performance_history.popleft()
                else:
                    break
                    
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
    
    def _format_uptime(self, uptime: timedelta) -> str:
        """Formatea el uptime de manera legible"""
        total_seconds = int(uptime.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def _save_persisted_data(self):
        """Guarda datos en archivo para persistencia"""
        try:
            data = {
                'metrics': {
                    'signals_today': self.metrics.signals_today,
                    'signals_shown': self.metrics.signals_shown,
                    'signals_executed': self.metrics.signals_executed,
                    'signals_rejected': self.metrics.signals_rejected,
                    'symbol_activity': dict(self.metrics.symbol_activity),
                    'symbol_performance': self.metrics.symbol_performance,
                    'confidence_distribution': dict(self.metrics.confidence_distribution)
                },
                'last_save': datetime.now(timezone.utc).isoformat()
            }
            
            with open(self.dashboard_config['data_file'], 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error saving persisted data: {e}")
    
    def _load_persisted_data(self):
        """Carga datos persistidos desde archivo"""
        try:
            if not os.path.exists(self.dashboard_config['data_file']):
                return
            
            with open(self.dashboard_config['data_file'], 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Verificar que los datos no sean muy antiguos (más de 24 horas)
            last_save = datetime.fromisoformat(data.get('last_save', '2000-01-01T00:00:00+00:00'))
            if datetime.now(timezone.utc) - last_save > timedelta(hours=24):
                logger.info("Persisted data too old, starting fresh")
                return
            
            # Cargar métricas
            metrics_data = data.get('metrics', {})
            self.metrics.signals_today = metrics_data.get('signals_today', 0)
            self.metrics.signals_shown = metrics_data.get('signals_shown', 0)
            self.metrics.signals_executed = metrics_data.get('signals_executed', 0)
            self.metrics.signals_rejected = metrics_data.get('signals_rejected', 0)
            
            # Cargar actividad por símbolo
            for symbol, count in metrics_data.get('symbol_activity', {}).items():
                self.metrics.symbol_activity[symbol] = count
            
            # Cargar performance por símbolo
            self.metrics.symbol_performance = metrics_data.get('symbol_performance', {})
            
            # Cargar distribución de confianza
            for confidence, count in metrics_data.get('confidence_distribution', {}).items():
                self.metrics.confidence_distribution[confidence] = count
            
            logger.info("Persisted dashboard data loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading persisted data: {e}")

# Instancia global del servicio de dashboard
dashboard_service = DashboardService()

def get_dashboard_service() -> DashboardService:
    """Obtiene la instancia global del servicio de dashboard"""
    return dashboard_service

# Funciones de conveniencia para compatibilidad
def start_enhanced_dashboard():
    """Inicia el dashboard mejorado"""
    dashboard_service.start()

def stop_enhanced_dashboard():
    """Detiene el dashboard mejorado"""
    dashboard_service.stop()

def add_signal_to_enhanced_dashboard(symbol: str, strategy: str, signal_type: str, 
                                   confidence: str, score: float, shown: bool, **kwargs):
    """Añade señal al dashboard mejorado"""
    dashboard_service.add_signal_event(symbol, strategy, signal_type, confidence, score, shown, **kwargs)

def update_dashboard_stats(positions_open: int = 0, total_profit: float = 0.0, win_rate: float = 0.0):
    """Actualiza estadísticas del dashboard"""
    dashboard_service.update_trading_metrics(positions_open, total_profit, win_rate)