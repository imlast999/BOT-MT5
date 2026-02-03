"""
Dashboard Inteligente Consolidado para Bot MT5
Integra sistema de confianza, filtros avanzados, cooldowns y análisis por símbolo
"""

import json
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, timezone
import os
import sqlite3
import threading
import time
from typing import Dict, List, Any, Optional

# Servidor web simple para servir el HTML
try:
    from flask import Flask, send_file
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Flask = None

# Importar plotly de forma segura
try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    go = None
    px = None

# Importar MT5 de forma segura
try:
    import MetaTrader5 as mt5
    from mt5_client import initialize as mt5_initialize
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

# Importar sistemas del bot
try:
    from confidence_system import confidence_system
    CONFIDENCE_SYSTEM_AVAILABLE = True
except ImportError:
    CONFIDENCE_SYSTEM_AVAILABLE = False
    confidence_system = None

try:
    from rejected_signals_tracker import rejected_signals_tracker
    REJECTION_TRACKING_AVAILABLE = True
except ImportError:
    REJECTION_TRACKING_AVAILABLE = False
    rejected_signals_tracker = None

try:
    from duplicate_filter import duplicate_filter
    DUPLICATE_FILTER_AVAILABLE = True
except ImportError:
    DUPLICATE_FILTER_AVAILABLE = False
    duplicate_filter = None

try:
    from signal_cooldown_manager import signal_cooldown_manager
    COOLDOWN_MANAGER_AVAILABLE = True
except ImportError:
    COOLDOWN_MANAGER_AVAILABLE = False
    signal_cooldown_manager = None

class DashboardLogger:
    """Logger mejorado para el dashboard"""
    
    def __init__(self):
        self.log_file = os.path.join(os.path.dirname(__file__), 'logs.txt')
    
    def log(self, message: str):
        """Escribir mensaje tanto a consola como a archivo"""
        print(message)
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message + '\n')
        except Exception:
            pass

dashboard_logger = DashboardLogger()

class ConsolidatedLiveDashboard:
    """Dashboard inteligente consolidado con todas las funcionalidades"""
    
    def __init__(self):
        self.db_path = "bot_state.db"
        self.dashboard_path = "live_dashboard.html"
        self.update_interval = 300  # 5 minutos
        self.bot_start_time = datetime.now()
        self.session_id = self.bot_start_time.strftime('%Y%m%d_%H%M%S')
        self.is_running = False
        self.update_thread = None
        
        # Símbolos monitoreados
        self.symbols = ['EURUSD', 'XAUUSD', 'BTCEUR']
        
        # Colores del tema oscuro integrado
        self.colors = {
            'background': '#0d1117',
            'surface': '#161b22', 
            'surface_light': '#21262d',
            'primary': '#58a6ff',
            'success': '#3fb950',
            'warning': '#d29922',
            'error': '#f85149',
            'text_primary': '#f0f6fc',
            'text_secondary': '#8b949e',
            'border': '#30363d',
            'accent': '#7c3aed'
        }
        
        # Niveles de confianza
        self.confidence_levels = ['LOW', 'MEDIUM', 'MEDIUM-HIGH', 'HIGH']
        self.confidence_colors = {
            'LOW': '#ff4444',
            'MEDIUM': '#ffaa00', 
            'MEDIUM-HIGH': '#00ccff',
            'HIGH': '#00ff88'
        }
        
        # Estadísticas del bot
        self.bot_stats = {
            'scans': 0,
            'signals': 0,
            'last_update': datetime.now()
        }
        
        # Inicializar base de datos mejorada
        self.init_enhanced_db()
        self.reset_session_data()
    
    def init_enhanced_db(self):
        """Inicializar base de datos con tablas mejoradas para sistema de confianza"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Tabla mejorada de señales con sistema de confianza
        c.execute('''
            CREATE TABLE IF NOT EXISTS enhanced_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                direction TEXT NOT NULL,
                price REAL NOT NULL,
                sl_price REAL NOT NULL,
                tp_price REAL NOT NULL,
                confidence_level TEXT NOT NULL,
                confidence_score INTEGER NOT NULL,
                confidence_details TEXT,
                status TEXT DEFAULT 'PROPOSED',
                executed BOOLEAN DEFAULT 0,
                lot_size REAL DEFAULT 0.01,
                zone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de estadísticas de cooldown
        c.execute('''
            CREATE TABLE IF NOT EXISTS cooldown_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                blocked_reason TEXT,
                cooldown_remaining INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def reset_session_data(self):
        """Resetear datos de la sesión actual"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Limpiar datos de sesiones anteriores (mantener solo últimas 24h)
        cutoff_time = (datetime.now() - timedelta(hours=24)).isoformat()
        c.execute('DELETE FROM enhanced_signals WHERE timestamp < ?', (cutoff_time,))
        c.execute('DELETE FROM cooldown_stats WHERE timestamp < ?', (cutoff_time,))
        
        conn.commit()
        conn.close()
        
        dashboard_logger.log(f"🔄 Sesión iniciada: {self.session_id} - Sistema de confianza integrado")
    
    def add_signal_with_confidence(self, signal_data: Dict):
        """Añadir señal con información de confianza al dashboard"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Extraer datos de confianza
            confidence_details = signal_data.get('confidence_details', {})
            confidence_details_json = json.dumps(confidence_details) if confidence_details else '{}'
            
            c.execute('''
                INSERT INTO enhanced_signals (
                    session_id, timestamp, symbol, strategy, direction, price,
                    sl_price, tp_price, confidence_level, confidence_score,
                    confidence_details, status, executed, lot_size, zone
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.session_id,
                signal_data.get('timestamp', datetime.now().isoformat()),
                signal_data.get('symbol', 'UNKNOWN'),
                signal_data.get('strategy', 'unknown'),
                signal_data.get('direction', 'BUY'),
                signal_data.get('price', 0.0),
                signal_data.get('sl_price', 0.0),
                signal_data.get('tp_price', 0.0),
                signal_data.get('confidence_level', 'MEDIUM'),
                signal_data.get('confidence_score', 1),
                confidence_details_json,
                signal_data.get('status', 'PROPOSED'),
                signal_data.get('executed', False),
                signal_data.get('lot_size', 0.01),
                signal_data.get('zone', '')
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            dashboard_logger.log(f"❌ Error añadiendo señal al dashboard: {e}")
    
    def add_cooldown_stat(self, symbol: str, blocked_reason: str, cooldown_remaining: int):
        """Añadir estadística de cooldown bloqueado"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('''
                INSERT INTO cooldown_stats (
                    session_id, timestamp, symbol, blocked_reason, cooldown_remaining
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                self.session_id,
                datetime.now().isoformat(),
                symbol,
                blocked_reason,
                cooldown_remaining
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            dashboard_logger.log(f"❌ Error añadiendo estadística de cooldown: {e}")
    
    def create_simple_chart(self, title: str, message: str):
        """Crear un gráfico simple sin plotly"""
        return {
            'data': [],
            'layout': {
                'title': title,
                'annotations': [{'text': message, 'x': 0.5, 'y': 0.5, 'showarrow': False}]
            }
        }
    
    def get_mt5_data(self):
        """Obtener datos de MT5 de forma segura"""
        if not MT5_AVAILABLE:
            return {
                'balance': 0.0,
                'equity': 0.0,
                'margin': 0.0,
                'free_margin': 0.0,
                'positions': []
            }
        
        try:
            if not mt5.initialize():
                mt5_initialize()
            
            account_info = mt5.account_info()
            if account_info is None:
                return {
                    'balance': 0.0,
                    'equity': 0.0,
                    'margin': 0.0,
                    'free_margin': 0.0,
                    'positions': []
                }
            
            positions = mt5.positions_get()
            positions_list = []
            
            if positions:
                for pos in positions:
                    positions_list.append({
                        'ticket': pos.ticket,
                        'symbol': pos.symbol,
                        'type': 'BUY' if pos.type == 0 else 'SELL',
                        'volume': pos.volume,
                        'price_open': pos.price_open,
                        'price_current': pos.price_current,
                        'profit': pos.profit,
                        'swap': pos.swap,
                        'comment': pos.comment
                    })
            
            return {
                'balance': float(account_info.balance),
                'equity': float(account_info.equity),
                'margin': float(account_info.margin),
                'free_margin': float(account_info.margin_free),
                'positions': positions_list
            }
            
        except Exception as e:
            dashboard_logger.log(f"❌ Error obteniendo datos MT5: {e}")
            return {
                'balance': 0.0,
                'equity': 0.0,
                'margin': 0.0,
                'free_margin': 0.0,
                'positions': []
            }
    
    def get_cooldown_data(self):
        """Obtener datos de cooldown de los sistemas"""
        cooldown_data = {
            'duplicate_filter_available': DUPLICATE_FILTER_AVAILABLE,
            'cooldown_manager_available': COOLDOWN_MANAGER_AVAILABLE,
            'stats': {}
        }
        
        # Datos del duplicate_filter
        if DUPLICATE_FILTER_AVAILABLE and duplicate_filter:
            try:
                filter_stats = duplicate_filter.get_stats()
                cooldown_data['stats']['duplicate_filter'] = filter_stats
            except Exception as e:
                dashboard_logger.log(f"❌ Error obteniendo stats de duplicate_filter: {e}")
        
        # Datos del cooldown_manager
        if COOLDOWN_MANAGER_AVAILABLE and signal_cooldown_manager:
            try:
                manager_stats = signal_cooldown_manager.get_stats()
                cooldown_data['stats']['cooldown_manager'] = manager_stats
            except Exception as e:
                dashboard_logger.log(f"❌ Error obteniendo stats de cooldown_manager: {e}")
        
        return cooldown_data
    
    def create_confidence_chart(self, signals_df):
        """Crear gráfico de distribución de confianza con tema oscuro"""
        if not PLOTLY_AVAILABLE:
            return self.create_simple_chart("Distribución de Confianza", "Plotly no disponible")
        
        if signals_df.empty:
            fig = go.Figure()
            fig.add_annotation(
                text="No hay datos de señales",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(color=self.colors['text_secondary'], size=14)
            )
            fig.update_layout(
                paper_bgcolor=self.colors['surface'],
                plot_bgcolor=self.colors['surface'],
                font=dict(color=self.colors['text_primary'])
            )
            return fig
        
        # Contar señales por nivel de confianza
        confidence_counts = signals_df['confidence_level'].value_counts()
        
        # Colores por confianza con tema oscuro
        confidence_colors = {
            'HIGH': self.colors['success'],
            'MEDIUM-HIGH': self.colors['primary'],
            'MEDIUM': self.colors['warning'],
            'LOW': self.colors['error'],
            'UNKNOWN': self.colors['text_secondary']
        }
        
        colors = [confidence_colors.get(level, self.colors['text_secondary']) for level in confidence_counts.index]
        
        fig = go.Figure(data=[
            go.Bar(
                x=confidence_counts.index,
                y=confidence_counts.values,
                marker_color=colors,
                text=confidence_counts.values,
                textposition='auto',
                textfont=dict(color=self.colors['text_primary'])
            )
        ])
        
        fig.update_layout(
            title=dict(
                text="Distribución de Confianza",
                font=dict(color=self.colors['text_primary'], size=16)
            ),
            xaxis=dict(
                title="Nivel de Confianza",
                color=self.colors['text_primary'],
                gridcolor=self.colors['border']
            ),
            yaxis=dict(
                title="Cantidad de Señales",
                color=self.colors['text_primary'],
                gridcolor=self.colors['border']
            ),
            paper_bgcolor=self.colors['surface'],
            plot_bgcolor=self.colors['surface'],
            font=dict(color=self.colors['text_primary']),
            height=300
        )
        
        return fig
    
    def create_cooldown_chart(self, cooldown_data):
        """Crear gráfico de estado de cooldowns con tema oscuro"""
        fig = go.Figure()
        
        if not cooldown_data.get('duplicate_filter_available', False):
            fig.add_annotation(
                text="Sistema de cooldown no disponible",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(color=self.colors['text_secondary'], size=14)
            )
            fig.update_layout(
                paper_bgcolor=self.colors['surface'],
                plot_bgcolor=self.colors['surface'],
                font=dict(color=self.colors['text_primary'])
            )
            return fig
        
        # Obtener datos de cooldown por símbolo
        filter_stats = cooldown_data.get('stats', {}).get('duplicate_filter', {})
        symbols = ['EURUSD', 'XAUUSD', 'BTCEUR']
        cooldown_remaining = []
        
        for symbol in symbols:
            symbol_key = f'{symbol}_last_signal'
            if symbol_key in filter_stats:
                symbol_data = filter_stats[symbol_key]
                if isinstance(symbol_data, dict):
                    remaining = symbol_data.get('cooldown_remaining', '0s')
                    # Extraer número de segundos
                    remaining_seconds = int(remaining.replace('s', '')) if 's' in remaining else 0
                    cooldown_remaining.append(remaining_seconds)
                else:
                    cooldown_remaining.append(0)
            else:
                cooldown_remaining.append(0)
        
        fig.add_trace(go.Bar(
            x=symbols,
            y=cooldown_remaining,
            marker_color=[self.colors['error'] if x > 0 else self.colors['success'] for x in cooldown_remaining],
            text=[f"{x}s" for x in cooldown_remaining],
            textposition='auto',
            textfont=dict(color=self.colors['text_primary'])
        ))
        
        fig.update_layout(
            title=dict(
                text="Estado de Cooldowns por Símbolo",
                font=dict(color=self.colors['text_primary'], size=16)
            ),
            xaxis=dict(
                title="Símbolo",
                color=self.colors['text_primary'],
                gridcolor=self.colors['border']
            ),
            yaxis=dict(
                title="Cooldown Restante (segundos)",
                color=self.colors['text_primary'],
                gridcolor=self.colors['border']
            ),
            paper_bgcolor=self.colors['surface'],
            plot_bgcolor=self.colors['surface'],
            font=dict(color=self.colors['text_primary']),
            height=300
        )
        
        return fig
    
    def update_enhanced_dashboard(self):
        """Actualizar dashboard con todas las funcionalidades"""
        try:
            # Obtener datos
            mt5_data = self.get_mt5_data()
            cooldown_data = self.get_cooldown_data()
            
            # Obtener señales de la base de datos
            conn = sqlite3.connect(self.db_path)
            signals_df = pd.read_sql_query('''
                SELECT * FROM enhanced_signals 
                WHERE session_id = ? 
                ORDER BY timestamp DESC
            ''', conn, params=(self.session_id,))
            conn.close()
            
            # Crear gráficos
            confidence_chart = self.create_confidence_chart(signals_df)
            cooldown_chart = self.create_cooldown_chart(cooldown_data)
            
            # Crear gráfico de equity con tema oscuro
            equity_fig = go.Figure()
            equity_fig.add_trace(go.Scatter(
                x=[datetime.now()],
                y=[mt5_data['equity']],
                mode='markers+lines',
                name='Equity',
                line=dict(color=self.colors['success']),
                marker=dict(color=self.colors['primary'])
            ))
            equity_fig.update_layout(
                title=dict(
                    text="Curva de Equity",
                    font=dict(color=self.colors['text_primary'], size=16)
                ),
                xaxis=dict(
                    title="Tiempo",
                    color=self.colors['text_primary'],
                    gridcolor=self.colors['border']
                ),
                yaxis=dict(
                    title="Equity (EUR)",
                    color=self.colors['text_primary'],
                    gridcolor=self.colors['border']
                ),
                paper_bgcolor=self.colors['surface'],
                plot_bgcolor=self.colors['surface'],
                font=dict(color=self.colors['text_primary']),
                height=300
            )
            
            # Generar HTML con tema oscuro integrado
            html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 Dashboard MT5 Bot - Sistema Inteligente Oscuro</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: {self.colors['background']};
            color: {self.colors['text_primary']};
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .header {{
            background: linear-gradient(135deg, {self.colors['surface']} 0%, {self.colors['surface_light']} 100%);
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            border: 1px solid {self.colors['border']};
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            font-weight: 300;
            margin-bottom: 10px;
            background: linear-gradient(135deg, {self.colors['primary']} 0%, {self.colors['accent']} 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .header p {{
            color: {self.colors['text_secondary']};
            font-size: 1.1em;
            margin-bottom: 15px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: {self.colors['surface']};
            border: 1px solid {self.colors['border']};
            border-radius: 12px;
            padding: 25px;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}
        
        .stat-card:hover {{
            transform: translateY(-2px);
            border-color: {self.colors['primary']};
            box-shadow: 0 8px 25px rgba(88, 166, 255, 0.15);
        }}
        
        .stat-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, {self.colors['primary']}, {self.colors['accent']});
        }}
        
        .stat-label {{
            color: {self.colors['text_secondary']};
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}
        
        .stat-value {{
            font-size: 2.2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .stat-change {{
            font-size: 0.85em;
            opacity: 0.8;
        }}
        
        .positive {{ color: {self.colors['success']}; }}
        .negative {{ color: {self.colors['error']}; }}
        .neutral {{ color: {self.colors['warning']}; }}
        
        .charts-section {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .chart-container {{
            background: {self.colors['surface']};
            border: 1px solid {self.colors['border']};
            border-radius: 12px;
            padding: 20px;
            overflow: hidden;
        }}
        
        .cooldown-info {{
            background: {self.colors['surface']};
            border: 1px solid {self.colors['border']};
            border-left: 4px solid {self.colors['primary']};
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        
        .cooldown-info h3 {{
            color: {self.colors['primary']};
            margin-bottom: 15px;
        }}
        
        .footer {{
            background: {self.colors['surface']};
            border: 1px solid {self.colors['border']};
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            color: {self.colors['text_secondary']};
        }}
        
        .status-indicator {{
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }}
        
        .status-active {{ background-color: {self.colors['success']}; }}
        .status-inactive {{ background-color: {self.colors['error']}; }}
        
        @media (max-width: 768px) {{
            .container {{ padding: 10px; }}
            .stats-grid {{ grid-template-columns: 1fr; }}
            .charts-section {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Dashboard MT5 Bot</h1>
            <p>Sistema Inteligente con Scoring Flexible y Tema Oscuro</p>
            <p>Sesión: {self.session_id} | Actualizado: {datetime.now().strftime('%H:%M:%S')}</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Balance</div>
                <div class="stat-value positive">{mt5_data['balance']:.2f} €</div>
                <div class="stat-change">
                    <span class="status-indicator {'status-active' if mt5_data['connected'] else 'status-inactive'}"></span>
                    {'Conectado' if mt5_data['connected'] else 'Desconectado'}
                </div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Equity</div>
                <div class="stat-value {'positive' if mt5_data['equity'] >= mt5_data['balance'] else 'negative'}">{mt5_data['equity']:.2f} €</div>
                <div class="stat-change">Margen libre: {mt5_data['free_margin']:.2f} €</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Posiciones Abiertas</div>
                <div class="stat-value neutral">{len(mt5_data['positions'])}</div>
                <div class="stat-change">Señales sesión: {len(signals_df)}</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Sistema Cooldown</div>
                <div class="stat-value">
                    <span class="status-indicator {'status-active' if cooldown_data['cooldown_manager_available'] else 'status-inactive'}"></span>
                    {'Activo' if cooldown_data['cooldown_manager_available'] else 'Inactivo'}
                </div>
                <div class="stat-change">Filtros inteligentes</div>
            </div>
        </div>
        
        <div class="cooldown-info">
            <h3>🔄 Estado del Sistema de Cooldowns</h3>
            <p><strong>Filtro de Duplicados:</strong> {'✅ Activo' if cooldown_data['duplicate_filter_available'] else '❌ No disponible'}</p>
            <p><strong>Gestor de Cooldowns:</strong> {'✅ Activo' if cooldown_data['cooldown_manager_available'] else '❌ No disponible'}</p>
            <p><strong>Configuración XAUUSD:</strong> Ultra-selectivo (20min cooldown, 30min por dirección)</p>
            <p><strong>Última actualización:</strong> {datetime.now().strftime('%H:%M:%S')}</p>
        </div>
        
        <div class="charts-section">
            <div class="chart-container">
                <div id="confidence-chart"></div>
            </div>
            <div class="chart-container">
                <div id="cooldown-chart"></div>
            </div>
            <div class="chart-container">
                <div id="equity-chart"></div>
            </div>
        </div>
        
        <div class="footer">
            <p>🚀 Bot MT5 con Sistema Inteligente de Señales | Actualización automática cada 5 minutos</p>
            <p>Sesión iniciada: {self.bot_start_time.strftime('%Y-%m-%d %H:%M:%S')} | Uptime: {str(datetime.now() - self.bot_start_time).split('.')[0]}</p>
        </div>
    </div>
    
    <script>
        // Configuración de Plotly para tema oscuro
        const plotlyConfig = {{
            displayModeBar: false,
            responsive: true
        }};
        
        // Gráfico de confianza
        var confidenceData = {confidence_chart.to_json()};
        Plotly.newPlot('confidence-chart', confidenceData.data, confidenceData.layout, plotlyConfig);
        
        // Gráfico de cooldowns
        var cooldownData = {cooldown_chart.to_json()};
        Plotly.newPlot('cooldown-chart', cooldownData.data, cooldownData.layout, plotlyConfig);
        
        // Gráfico de equity
        var equityData = {equity_fig.to_json()};
        Plotly.newPlot('equity-chart', equityData.data, equityData.layout, plotlyConfig);
        
        // Auto-refresh cada 5 minutos
        setTimeout(function() {{
            location.reload();
        }}, 300000);
        
        // Botón de refresh manual
        document.addEventListener('DOMContentLoaded', function() {{
            const refreshBtn = document.createElement('button');
            refreshBtn.innerHTML = '🔄 Actualizar';
            refreshBtn.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: {self.colors['primary']};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                z-index: 1000;
                font-size: 14px;
            `;
            refreshBtn.onclick = function() {{
                location.reload();
            }};
            document.body.appendChild(refreshBtn);
        }});
    </script>
</body>
</html>
"""
            
            # Escribir archivo HTML
            with open(self.dashboard_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            dashboard_logger.log(f"📊 Dashboard inteligente actualizado: {self.dashboard_path}")
            
        except Exception as e:
            dashboard_logger.log(f"❌ Error actualizando dashboard: {e}")
    
    def setup_flask_app(self):
        """Configurar aplicación Flask para servidor web"""
        if not FLASK_AVAILABLE:
            dashboard_logger.log("❌ Flask no disponible - servidor web deshabilitado")
            return None
        
        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'dashboard-mt5-bot'
        
        @app.route('/')
        def dashboard_home():
            """Página principal del dashboard"""
            try:
                # Leer el HTML generado
                if os.path.exists(self.dashboard_path):
                    with open(self.dashboard_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    return html_content
                else:
                    return """
                    <html>
                    <head><title>Dashboard MT5 Bot</title></head>
                    <body style="background: #0d1117; color: #f0f6fc; font-family: Arial;">
                        <h1>🤖 Dashboard MT5 Bot</h1>
                        <p>⏳ Dashboard inicializándose...</p>
                        <p>Actualiza la página en unos segundos.</p>
                    </body>
                    </html>
                    """
            except Exception as e:
                return f"""
                <html>
                <head><title>Error - Dashboard MT5</title></head>
                <body style="background: #0d1117; color: #f85149; font-family: Arial;">
                    <h1>❌ Error en Dashboard</h1>
                    <p>Error: {e}</p>
                </body>
                </html>
                """
        
        @app.route('/api/status')
        def api_status():
            """API endpoint para estado del bot"""
            try:
                mt5_data = self.get_mt5_data()
                return jsonify({
                    'status': 'running',
                    'session_id': self.session_id,
                    'uptime': str(datetime.now() - self.bot_start_time).split('.')[0],
                    'balance': mt5_data.get('balance', 0),
                    'equity': mt5_data.get('equity', 0),
                    'positions': len(mt5_data.get('positions', [])),
                    'last_update': datetime.now().isoformat()
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @app.route('/api/refresh')
        def api_refresh():
            """API endpoint para forzar actualización"""
            try:
                self.update_enhanced_dashboard()
                return jsonify({'status': 'refreshed', 'timestamp': datetime.now().isoformat()})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        return app
    
    def start_web_server(self):
        """Iniciar servidor web Flask"""
        if not FLASK_AVAILABLE:
            dashboard_logger.log("⚠️ Flask no disponible - usando solo archivo HTML")
            return False
        
        try:
            self.flask_app = self.setup_flask_app()
            if not self.flask_app:
                return False
            
            def run_server():
                try:
                    self.flask_app.run(
                        host='0.0.0.0',  # Permitir acceso desde red local
                        port=self.web_server_port,
                        debug=False,
                        use_reloader=False,
                        threaded=True
                    )
                except Exception as e:
                    dashboard_logger.log(f"❌ Error en servidor web: {e}")
            
            self.web_server_thread = threading.Thread(target=run_server, daemon=True)
            self.web_server_thread.start()
            
            # Esperar un momento para que el servidor inicie
            time.sleep(2)
            
            dashboard_logger.log(f"🌐 Servidor web iniciado en http://localhost:{self.web_server_port}")
            dashboard_logger.log(f"📱 Acceso móvil: http://192.168.1.64:{self.web_server_port}")
            
            return True
            
        except Exception as e:
            dashboard_logger.log(f"❌ Error iniciando servidor web: {e}")
            return False
    
    def stop_web_server(self):
        """Detener servidor web"""
        if self.web_server_thread and self.web_server_thread.is_alive():
            dashboard_logger.log("⏹️ Deteniendo servidor web...")
            # Flask no tiene un método clean shutdown, pero el thread daemon se cerrará automáticamente
    
    def update_bot_stats(self, scans: int = 1, signals: int = 0):
        """Actualizar estadísticas del bot"""
        self.bot_stats['scans'] += scans
        self.bot_stats['signals'] += signals
        self.bot_stats['last_update'] = datetime.now()
    
    def auto_update_loop(self):
        """Loop de actualización automática"""
        while self.is_running:
            try:
                self.update_enhanced_dashboard()
                time.sleep(self.update_interval)
            except Exception as e:
                dashboard_logger.log(f"❌ Error en loop de actualización: {e}")
                time.sleep(60)  # Esperar 1 minuto antes de reintentar
    
    def start_auto_update(self):
        """Iniciar actualización automática + servidor web"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # Iniciar servidor web
        web_server_started = self.start_web_server()
        
        # Iniciar thread de actualización
        self.update_thread = threading.Thread(target=self.auto_update_loop, daemon=True)
        self.update_thread.start()
        
        # Actualización inicial
        self.update_enhanced_dashboard()
        
        if web_server_started:
            dashboard_logger.log(f"🚀 Dashboard completo iniciado - Servidor web + archivo HTML")
            dashboard_logger.log(f"🌐 Acceso web: http://localhost:5000")
        else:
            dashboard_logger.log(f"🚀 Dashboard iniciado - Solo archivo HTML")
        
        dashboard_logger.log(f"📁 Archivo: {os.path.abspath(self.dashboard_path)}")
        dashboard_logger.log(f"🔄 Sesión: {self.session_id} - Sistema de confianza integrado")
    
    def stop_auto_update(self):
        """Detener actualización automática + servidor web"""
        self.is_running = False
        
        # Detener servidor web
        self.stop_web_server()
        
        # Detener thread de actualización
        if self.update_thread:
            self.update_thread.join(timeout=1)
        
        dashboard_logger.log(f"⏹️ Dashboard completo detenido - Sesión: {self.session_id}")
    
    def start_web_server(self):
        """Iniciar servidor web simple para servir el HTML existente"""
        if not FLASK_AVAILABLE:
            dashboard_logger.log("⚠️ Flask no disponible - solo archivo HTML")
            return False
        
        try:
            app = Flask(__name__)
            
            @app.route('/')
            def dashboard():
                """Servir el archivo HTML del dashboard"""
                if os.path.exists(self.dashboard_path):
                    return send_file(self.dashboard_path)
                else:
                    return "<h1>Dashboard inicializándose...</h1><p>Actualiza en unos segundos</p>"
            
            def run_server():
                app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)
            
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            
            time.sleep(1)  # Esperar que inicie
            dashboard_logger.log("🌐 Servidor web iniciado en http://localhost:5000")
            return True
            
        except Exception as e:
            dashboard_logger.log(f"❌ Error servidor web: {e}")
            return False

# Instancias globales
live_dashboard = ConsolidatedLiveDashboard()
enhanced_dashboard = live_dashboard  # Alias para compatibilidad

# Funciones de compatibilidad con bot.py
def start_live_dashboard():
    """Iniciar dashboard live (llamar desde bot.py)"""
    live_dashboard.start_auto_update()

def stop_live_dashboard():
    """Detener dashboard live"""
    live_dashboard.stop_auto_update()

def update_dashboard_stats(scans: int = 1, signals: int = 0):
    """Actualizar stats desde el bot"""
    live_dashboard.update_bot_stats(scans, signals)

def start_enhanced_dashboard():
    """Iniciar dashboard inteligente (llamar desde bot.py)"""
    live_dashboard.start_auto_update()

def stop_enhanced_dashboard():
    """Detener dashboard inteligente"""
    live_dashboard.stop_auto_update()

def add_signal_to_enhanced_dashboard(signal_data: Dict):
    """Añadir señal con confianza al dashboard (llamar desde bot.py)"""
    live_dashboard.add_signal_with_confidence(signal_data)

if __name__ == "__main__":
    # Test del dashboard consolidado
    live_dashboard.update_enhanced_dashboard()
    dashboard_logger.log("Dashboard consolidado generado para testing")