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
                
                # Iniciar servidor web
                self._start_web_server()
                
                logger.info("Dashboard service started successfully")
                
        except Exception as e:
            logger.error(f"Error starting dashboard service: {e}")
            self.is_running = False
    
    def _start_web_server(self):
        """Inicia el servidor web del dashboard"""
        try:
            # Check if dashboard is disabled via environment variable
            if os.getenv('DISABLE_DASHBOARD', '0') == '1':
                logger.info("Dashboard disabled via DISABLE_DASHBOARD environment variable")
                return
            
            import threading
            from http.server import HTTPServer, BaseHTTPRequestHandler
            import json
            
            dashboard_service = self
            
            class DashboardHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    try:
                        if self.path == '/' or self.path == '/dashboard':
                            # Servir HTML del dashboard
                            html_content = dashboard_service.get_dashboard_html()
                            self.send_response(200)
                            self.send_header('Content-type', 'text/html; charset=utf-8')
                            self.end_headers()
                            self.wfile.write(html_content.encode('utf-8'))
                            
                        elif self.path == '/api/metrics':
                            # API JSON de métricas
                            metrics = dashboard_service.get_current_metrics()
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(json.dumps(metrics, indent=2).encode('utf-8'))
                            
                        elif self.path.startswith('/api/history'):
                            # API de historial
                            history = dashboard_service.get_signal_history(hours=24)
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(json.dumps(history, indent=2).encode('utf-8'))
                            
                        else:
                            # 404 para otras rutas
                            self.send_response(404)
                            self.send_header('Content-type', 'text/html')
                            self.end_headers()
                            self.wfile.write(b'<html><body><h1>404 Not Found</h1></body></html>')
                            
                    except Exception as e:
                        logger.error(f"Error handling web request: {e}")
                        self.send_response(500)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        self.wfile.write(f'<html><body><h1>500 Error</h1><p>{str(e)}</p></body></html>'.encode('utf-8'))
                
                def log_message(self, format, *args):
                    # Suprimir logs de HTTP server para reducir ruido
                    pass
            
            # Configurar servidor
            port = int(os.getenv('DASHBOARD_PORT', '8080'))
            server_address = ('', port)
            
            def run_server():
                try:
                    httpd = HTTPServer(server_address, DashboardHandler)
                    logger.info(f"Dashboard web server started on http://localhost:{port}")
                    httpd.serve_forever()
                except Exception as e:
                    logger.error(f"Error running web server: {e}")
            
            # Iniciar servidor en hilo separado
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            
        except Exception as e:
            logger.error(f"Error starting web server: {e}")
    
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
            # Return safe default metrics structure instead of just error
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'uptime_seconds': 0,
                'uptime_formatted': '0s',
                'system_status': 'ERROR',
                
                # Métricas de señales
                'signals': {
                    'today': 0,
                    'shown': 0,
                    'executed': 0,
                    'rejected': 0,
                    'show_rate': 0.0,
                    'execution_rate': 0.0,
                    'last_signal_time': None
                },
                
                # Métricas por símbolo
                'symbols': {
                    'activity': {},
                    'performance': {}
                },
                
                # Distribución de confianza
                'confidence_distribution': {},
                
                # Métricas de trading
                'trading': {
                    'positions_open': 0,
                    'total_profit': 0.0,
                    'win_rate': 0.0
                },
                
                'error': str(e)
            }
    
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
            # Get metrics with error handling
            try:
                metrics = self.get_current_metrics()
            except Exception as e:
                logger.error(f"Error getting metrics: {e}")
                return "<html><body><h1>Dashboard Error</h1><p>Error getting metrics: " + str(e) + "</p></body></html>"
            
            # Build HTML using string concatenation to avoid f-string formatting issues
            html = """<!DOCTYPE html>
<html>
<head>
    <title>Trading Bot Dashboard</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; }
        .metric { display: inline-block; margin: 10px 20px 10px 0; }
        .metric-value { font-size: 24px; font-weight: bold; color: #2196F3; }
        .metric-label { font-size: 12px; color: #666; }
    </style>
    <script>
        setTimeout(function() { location.reload(); }, 30000);
    </script>
</head>
<body>
    <div class="container">
        <h1>🤖 Trading Bot Dashboard</h1>
        
        <div class="card">
            <h2>📊 Estado del Sistema</h2>
            <div class="metric">
                <div class="metric-value">""" + str(metrics.get('system_status', 'UNKNOWN')) + """</div>
                <div class="metric-label">Estado</div>
            </div>
            <div class="metric">
                <div class="metric-value">""" + str(metrics.get('uptime_formatted', '0s')) + """</div>
                <div class="metric-label">Tiempo Activo</div>
            </div>
        </div>
        
        <div class="card">
            <h2>🎯 Métricas de Señales</h2>
            <div class="metric">
                <div class="metric-value">""" + str(metrics.get('signals', {}).get('today', 0)) + """</div>
                <div class="metric-label">Señales Hoy</div>
            </div>
            <div class="metric">
                <div class="metric-value">""" + str(metrics.get('signals', {}).get('shown', 0)) + """</div>
                <div class="metric-label">Mostradas</div>
            </div>
            <div class="metric">
                <div class="metric-value">""" + str(metrics.get('signals', {}).get('executed', 0)) + """</div>
                <div class="metric-label">Ejecutadas</div>
            </div>
        </div>
        
        <div class="card">
            <h2>💹 Métricas de Trading</h2>
            <div class="metric">
                <div class="metric-value">""" + str(metrics.get('trading', {}).get('positions_open', 0)) + """</div>
                <div class="metric-label">Posiciones Abiertas</div>
            </div>
            <div class="metric">
                <div class="metric-value">""" + "{:.2f}".format(metrics.get('trading', {}).get('total_profit', 0.0)) + """ EUR</div>
                <div class="metric-label">Profit Total</div>
            </div>
        </div>
        
        <div class="card">
            <p>Actualizado: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
            <p>Auto-refresh cada 30 segundos</p>
        </div>
    </div>
</body>
</html>"""
            
            return html
            
        except Exception as e:
            logger.error(f"Error generating dashboard HTML: {e}")
            # Return a very simple error page using string concatenation
            return ("<html><body><h1>Dashboard Error</h1><p>Error: " + 
                   str(e) + "</p><p>Time: " + str(datetime.now()) + "</p></body></html>")
    
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