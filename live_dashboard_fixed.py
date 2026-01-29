"""
Dashboard Inteligente Mejorado para Bot MT5 - Versión Corregida
Integra sistema de confianza, filtros avanzados y análisis por símbolo
"""

import json
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import sqlite3
import threading
import time
from typing import Dict, List, Any, Optional

# Importar MT5 de forma segura
try:
    import MetaTrader5 as mt5
    from mt5_client import initialize as mt5_initialize
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

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

class EnhancedLiveDashboard:
    """Dashboard inteligente con sistema de confianza y filtros avanzados"""
    
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
        
        # Niveles de confianza
        self.confidence_levels = ['LOW', 'MEDIUM', 'MEDIUM-HIGH', 'HIGH']
        self.confidence_colors = {
            'LOW': '#ff4444',
            'MEDIUM': '#ffaa00', 
            'MEDIUM-HIGH': '#00ccff',
            'HIGH': '#00ff88'
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
                rejected BOOLEAN DEFAULT 0,
                rejection_reason TEXT,
                pnl REAL DEFAULT 0,
                lot_size REAL DEFAULT 0.01,
                mt5_ticket INTEGER,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                close_price REAL
            )
        ''')
        
        # Tabla de métricas por símbolo
        c.execute('''
            CREATE TABLE IF NOT EXISTS symbol_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                total_signals INTEGER DEFAULT 0,
                high_confidence_signals INTEGER DEFAULT 0,
                medium_high_signals INTEGER DEFAULT 0,
                medium_signals INTEGER DEFAULT 0,
                low_signals INTEGER DEFAULT 0,
                executed_signals INTEGER DEFAULT 0,
                win_trades INTEGER DEFAULT 0,
                loss_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                execution_rate REAL DEFAULT 0,
                avg_confidence_score REAL DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def reset_session_data(self):
        """Limpiar datos de sesión anterior"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            # Obtener balance inicial real de MT5 si está disponible
            initial_balance = 5000.0
            if MT5_AVAILABLE:
                try:
                    mt5_initialize()
                    account_info = mt5.account_info()
                    if account_info:
                        initial_balance = account_info.balance
                except Exception:
                    pass
            
            # Inicializar métricas por símbolo
            for symbol in self.symbols:
                c.execute('''
                    INSERT OR REPLACE INTO symbol_metrics 
                    (session_id, symbol, timestamp) 
                    VALUES (?, ?, ?)
                ''', (self.session_id, symbol, datetime.now().isoformat()))
            
            conn.commit()
            dashboard_logger.log(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Dashboard mejorado iniciado: {self.session_id}")
            dashboard_logger.log(f"[{datetime.now().strftime('%H:%M:%S')}] 💰 Balance inicial: {initial_balance} EUR")
            
        except Exception as e:
            dashboard_logger.log(f"Error inicializando sesión mejorada: {e}")
        finally:
            conn.close()
    
    def add_signal_with_confidence(self, signal_data: Dict):
        """Añadir señal con información de confianza completa"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            c.execute('''
                INSERT INTO enhanced_signals 
                (session_id, timestamp, symbol, strategy, direction, price, sl_price, tp_price,
                 confidence_level, confidence_score, confidence_details, status, executed, 
                 lot_size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.session_id,
                signal_data.get('timestamp', datetime.now().isoformat()),
                signal_data.get('symbol', 'EURUSD'),
                signal_data.get('strategy', 'unknown'),
                signal_data.get('direction', 'BUY'),
                signal_data.get('price', 0.0),
                signal_data.get('sl_price', 0.0),
                signal_data.get('tp_price', 0.0),
                signal_data.get('confidence_level', 'MEDIUM'),
                signal_data.get('confidence_score', 1),
                json.dumps(signal_data.get('confidence_details', {})),
                signal_data.get('status', 'PROPOSED'),
                signal_data.get('executed', False),
                signal_data.get('lot_size', 0.01),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            
            # Actualizar métricas del símbolo
            self.update_symbol_metrics(signal_data.get('symbol', 'EURUSD'))
            
            dashboard_logger.log(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Señal con confianza añadida: {signal_data.get('symbol')} [{signal_data.get('confidence_level')}]")
            
        except Exception as e:
            dashboard_logger.log(f"Error añadiendo señal con confianza: {e}")
        finally:
            conn.close()
    
    def update_symbol_metrics(self, symbol: str):
        """Actualizar métricas específicas por símbolo"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            # Obtener estadísticas del símbolo
            c.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN confidence_level = 'HIGH' THEN 1 ELSE 0 END) as high,
                    SUM(CASE WHEN confidence_level = 'MEDIUM-HIGH' THEN 1 ELSE 0 END) as medium_high,
                    SUM(CASE WHEN confidence_level = 'MEDIUM' THEN 1 ELSE 0 END) as medium,
                    SUM(CASE WHEN confidence_level = 'LOW' THEN 1 ELSE 0 END) as low,
                    SUM(CASE WHEN executed = 1 THEN 1 ELSE 0 END) as executed,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                    SUM(pnl) as total_pnl,
                    AVG(confidence_score) as avg_score
                FROM enhanced_signals 
                WHERE session_id = ? AND symbol = ?
            ''', (self.session_id, symbol))
            
            stats = c.fetchone()
            if stats:
                total = stats[0] or 0
                executed = stats[5] or 0
                wins = stats[6] or 0
                losses = stats[7] or 0
                
                win_rate = (wins / (wins + losses)) * 100 if (wins + losses) > 0 else 0
                execution_rate = (executed / total) * 100 if total > 0 else 0
                
                c.execute('''
                    UPDATE symbol_metrics 
                    SET total_signals = ?, high_confidence_signals = ?, 
                        medium_high_signals = ?, medium_signals = ?, low_signals = ?,
                        executed_signals = ?, win_trades = ?, loss_trades = ?,
                        total_pnl = ?, win_rate = ?, execution_rate = ?,
                        avg_confidence_score = ?, timestamp = ?
                    WHERE session_id = ? AND symbol = ?
                ''', (
                    stats[0], stats[1], stats[2], stats[3], stats[4],
                    stats[5], stats[6], stats[7], stats[8] or 0,
                    win_rate, execution_rate, stats[9] or 0,
                    datetime.now().isoformat(), self.session_id, symbol
                ))
                
                conn.commit()
            
        except Exception as e:
            dashboard_logger.log(f"Error actualizando métricas de {symbol}: {e}")
        finally:
            conn.close()
    
    def get_signals_with_filters(self, symbol_filter: str = 'ALL', 
                                confidence_filter: str = 'ALL', 
                                status_filter: str = 'ALL',
                                limit: int = 50) -> List[Dict]:
        """Obtener señales con filtros aplicados"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Construir query con filtros
        where_conditions = ['session_id = ?']
        params = [self.session_id]
        
        if symbol_filter != 'ALL':
            where_conditions.append('symbol = ?')
            params.append(symbol_filter)
        
        if confidence_filter != 'ALL':
            where_conditions.append('confidence_level = ?')
            params.append(confidence_filter)
        
        if status_filter == 'EXECUTED':
            where_conditions.append('executed = 1')
        elif status_filter == 'PROPOSED':
            where_conditions.append('executed = 0 AND rejected = 0')
        elif status_filter == 'REJECTED':
            where_conditions.append('rejected = 1')
        
        where_clause = ' AND '.join(where_conditions)
        
        c.execute(f'''
            SELECT timestamp, symbol, strategy, direction, price, confidence_level,
                   confidence_score, status, executed, rejected, pnl, lot_size
            FROM enhanced_signals 
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        ''', params + [limit])
        
        signals = []
        for row in c.fetchall():
            signals.append({
                'timestamp': row[0],
                'symbol': row[1],
                'strategy': row[2],
                'direction': row[3],
                'price': row[4],
                'confidence_level': row[5],
                'confidence_score': row[6],
                'status': row[7],
                'executed': bool(row[8]),
                'rejected': bool(row[9]),
                'pnl': row[10] or 0.0,
                'lot_size': row[11] or 0.01
            })
        
        conn.close()
        return signals
    
    def get_symbol_statistics(self, symbol: str = 'ALL') -> Dict[str, Any]:
        """Obtener estadísticas detalladas por símbolo"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        if symbol == 'ALL':
            # Estadísticas globales
            c.execute('''
                SELECT symbol, total_signals, high_confidence_signals, medium_high_signals,
                       medium_signals, low_signals, executed_signals, win_trades, loss_trades,
                       total_pnl, win_rate, execution_rate, avg_confidence_score
                FROM symbol_metrics 
                WHERE session_id = ?
            ''', (self.session_id,))
            
            stats_by_symbol = {}
            for row in c.fetchall():
                stats_by_symbol[row[0]] = {
                    'total_signals': row[1] or 0,
                    'high_confidence': row[2] or 0,
                    'medium_high_confidence': row[3] or 0,
                    'medium_confidence': row[4] or 0,
                    'low_confidence': row[5] or 0,
                    'executed_signals': row[6] or 0,
                    'win_trades': row[7] or 0,
                    'loss_trades': row[8] or 0,
                    'total_pnl': row[9] or 0.0,
                    'win_rate': row[10] or 0.0,
                    'execution_rate': row[11] or 0.0,
                    'avg_confidence_score': row[12] or 0.0
                }
            
            conn.close()
            return stats_by_symbol
        else:
            # Estadísticas de un símbolo específico
            c.execute('''
                SELECT total_signals, high_confidence_signals, medium_high_signals,
                       medium_signals, low_signals, executed_signals, win_trades, loss_trades,
                       total_pnl, win_rate, execution_rate, avg_confidence_score
                FROM symbol_metrics 
                WHERE session_id = ? AND symbol = ?
            ''', (self.session_id, symbol))
            
            row = c.fetchone()
            conn.close()
            
            if row:
                return {
                    'total_signals': row[0] or 0,
                    'high_confidence': row[1] or 0,
                    'medium_high_confidence': row[2] or 0,
                    'medium_confidence': row[3] or 0,
                    'low_confidence': row[4] or 0,
                    'executed_signals': row[5] or 0,
                    'win_trades': row[6] or 0,
                    'loss_trades': row[7] or 0,
                    'total_pnl': row[8] or 0.0,
                    'win_rate': row[9] or 0.0,
                    'execution_rate': row[10] or 0.0,
                    'avg_confidence_score': row[11] or 0.0
                }
            
            return {}
    
    def get_confidence_distribution(self) -> Dict[str, int]:
        """Obtener distribución de señales por nivel de confianza"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            SELECT confidence_level, COUNT(*) 
            FROM enhanced_signals 
            WHERE session_id = ?
            GROUP BY confidence_level
        ''', (self.session_id,))
        
        distribution = {level: 0 for level in self.confidence_levels}
        for row in c.fetchall():
            distribution[row[0]] = row[1]
        
        conn.close()
        return distribution
    
    def generate_enhanced_dashboard_html(self, symbol_filter: str = 'ALL', 
                                       confidence_filter: str = 'ALL',
                                       status_filter: str = 'ALL') -> str:
        """Generar HTML del dashboard mejorado con filtros"""
        
        # Obtener datos con filtros aplicados
        filtered_signals = self.get_signals_with_filters(symbol_filter, confidence_filter, status_filter)
        stats_by_symbol = self.get_symbol_statistics('ALL')
        confidence_distribution = self.get_confidence_distribution()
        
        # Calcular estadísticas globales
        total_signals = sum(confidence_distribution.values())
        high_signals = confidence_distribution.get('HIGH', 0)
        medium_high_signals = confidence_distribution.get('MEDIUM-HIGH', 0)
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Bot MT5 - Dashboard Inteligente (Sesión: {self.session_id})</title>
            <meta http-equiv="refresh" content="300">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
                    color: #ffffff;
                    min-height: 100vh;
                }}
                
                .header {{
                    background: rgba(0, 0, 0, 0.4);
                    padding: 15px 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    border-bottom: 2px solid #00ff88;
                    backdrop-filter: blur(10px);
                }}
                
                .header h1 {{
                    font-size: 1.8em;
                    background: linear-gradient(45deg, #00ff88, #00ccff);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }}
                
                .filters-section {{
                    background: rgba(255, 255, 255, 0.05);
                    padding: 20px;
                    display: flex;
                    gap: 20px;
                    align-items: center;
                    flex-wrap: wrap;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }}
                
                .filter-group {{
                    display: flex;
                    flex-direction: column;
                    gap: 5px;
                }}
                
                .filter-group label {{
                    font-size: 0.9em;
                    color: rgba(255, 255, 255, 0.8);
                    font-weight: bold;
                }}
                
                .filter-select {{
                    padding: 8px 12px;
                    background: rgba(255, 255, 255, 0.1);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    color: white;
                    border-radius: 5px;
                    cursor: pointer;
                }}
                
                .confidence-badge {{
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 0.8em;
                    font-weight: bold;
                    text-transform: uppercase;
                }}
                
                .confidence-HIGH {{ background: #00ff88; color: #000; }}
                .confidence-MEDIUM-HIGH {{ background: #00ccff; color: #000; }}
                .confidence-MEDIUM {{ background: #ffaa00; color: #000; }}
                .confidence-LOW {{ background: #ff4444; color: #fff; }}
                
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    padding: 20px;
                    max-width: 1400px;
                    margin: 0 auto;
                }}
                
                .stat-card {{
                    background: rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    padding: 20px;
                    text-align: center;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(10px);
                    transition: transform 0.3s;
                }}
                
                .stat-card:hover {{
                    transform: translateY(-2px);
                }}
                
                .stat-card h3 {{
                    color: #00ff88;
                    margin-bottom: 8px;
                    font-size: 0.8em;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                
                .stat-card .value {{
                    font-size: 1.8em;
                    font-weight: bold;
                    margin-bottom: 5px;
                }}
                
                .symbol-cards {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 20px;
                    padding: 20px;
                    max-width: 1400px;
                    margin: 0 auto;
                }}
                
                .symbol-card {{
                    background: rgba(255, 255, 255, 0.08);
                    border-radius: 15px;
                    padding: 20px;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }}
                
                .symbol-card h3 {{
                    color: #00ff88;
                    margin-bottom: 15px;
                    font-size: 1.2em;
                    text-align: center;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                    padding-bottom: 10px;
                }}
                
                .symbol-metrics {{
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 10px;
                    margin-bottom: 15px;
                }}
                
                .metric-item {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 5px 0;
                    font-size: 0.9em;
                }}
                
                .metric-value {{
                    font-weight: bold;
                    color: #00ccff;
                }}
                
                .confidence-breakdown {{
                    display: flex;
                    gap: 5px;
                    margin-top: 10px;
                }}
                
                .confidence-mini-badge {{
                    flex: 1;
                    text-align: center;
                    padding: 5px 2px;
                    border-radius: 3px;
                    font-size: 0.7em;
                    font-weight: bold;
                }}
                
                .signals-table {{
                    background: rgba(255, 255, 255, 0.05);
                    border-radius: 15px;
                    padding: 20px;
                    margin: 20px auto;
                    max-width: 1400px;
                }}
                
                .signals-table table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 15px;
                }}
                
                .signals-table th,
                .signals-table td {{
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }}
                
                .signals-table th {{
                    background: rgba(0, 255, 136, 0.2);
                    color: #00ff88;
                    font-weight: bold;
                    text-transform: uppercase;
                    font-size: 0.9em;
                }}
                
                .status-executed {{ color: #00ff88; }}
                .status-proposed {{ color: #ffaa00; }}
                .status-rejected {{ color: #ff4444; }}
                
                .positive {{ color: #00ff88; }}
                .negative {{ color: #ff4444; }}
                .neutral {{ color: #ffaa00; }}
                
                .section-title {{
                    text-align: center;
                    font-size: 1.5em;
                    margin: 30px 0 20px 0;
                    color: #00ff88;
                    text-transform: uppercase;
                    letter-spacing: 2px;
                }}
                
                .live-indicator {{
                    display: inline-block;
                    width: 8px;
                    height: 8px;
                    background: #00ff88;
                    border-radius: 50%;
                    animation: pulse 2s infinite;
                    margin-right: 5px;
                }}
                
                @keyframes pulse {{
                    0% {{ opacity: 1; }}
                    50% {{ opacity: 0.5; }}
                    100% {{ opacity: 1; }}
                }}
                
                @media (max-width: 768px) {{
                    .stats-grid, .symbol-cards {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .filters-section {{
                        flex-direction: column;
                        align-items: stretch;
                    }}
                    
                    .filter-group {{
                        width: 100%;
                    }}
                }}
            </style>
            <script>
                // Auto-refresh
                let refreshCountdown = 300;
                function updateCountdown() {{
                    const minutes = Math.floor(refreshCountdown / 60);
                    const seconds = refreshCountdown % 60;
                    document.getElementById('refresh-countdown').textContent = 
                        `${{minutes}}:${{seconds.toString().padStart(2, '0')}}`;
                    
                    if (refreshCountdown <= 0) {{
                        location.reload();
                    }} else {{
                        refreshCountdown--;
                    }}
                }}
                setInterval(updateCountdown, 1000);
            </script>
        </head>
        <body>
            <div class="header">
                <div>
                    <h1><span class="live-indicator"></span>Dashboard Inteligente MT5</h1>
                    <div style="font-size: 0.8em; color: rgba(255, 255, 255, 0.7); margin-top: 5px;">
                        Sesión: {self.session_id} • Sistema de Confianza Activo
                    </div>
                </div>
                <div style="text-align: right;">
                    <div>Próxima actualización: <span id="refresh-countdown">5:00</span></div>
                    <div style="font-size: 0.8em; margin-top: 5px;">
                        Señales totales: {total_signals} • HIGH: {high_signals} • MEDIUM-HIGH: {medium_high_signals}
                    </div>
                </div>
            </div>
            
            <div class="filters-section">
                <div class="filter-group">
                    <label>📊 Símbolo:</label>
                    <select class="filter-select">
                        <option value="ALL">Todos</option>
                        <option value="EURUSD">EURUSD</option>
                        <option value="XAUUSD">XAUUSD</option>
                        <option value="BTCEUR">BTCEUR</option>
                    </select>
                </div>
                
                <div class="filter-group">
                    <label>🧠 Confianza:</label>
                    <select class="filter-select">
                        <option value="ALL">Todas</option>
                        <option value="HIGH">HIGH</option>
                        <option value="MEDIUM-HIGH">MEDIUM-HIGH</option>
                        <option value="MEDIUM">MEDIUM</option>
                        <option value="LOW">LOW</option>
                    </select>
                </div>
                
                <div class="filter-group">
                    <label>⚡ Estado:</label>
                    <select class="filter-select">
                        <option value="ALL">Todos</option>
                        <option value="EXECUTED">Ejecutadas</option>
                        <option value="PROPOSED">Propuestas</option>
                        <option value="REJECTED">Rechazadas</option>
                    </select>
                </div>
            </div>
            
            <div class="section-title">📊 Resumen Global de Confianza</div>
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>🎯 Señales HIGH</h3>
                    <div class="value positive">{confidence_distribution.get('HIGH', 0)}</div>
                    <small>Auto-ejecutables</small>
                </div>
                
                <div class="stat-card">
                    <h3>⚡ Señales MEDIUM-HIGH</h3>
                    <div class="value neutral">{confidence_distribution.get('MEDIUM-HIGH', 0)}</div>
                    <small>Mostradas en Discord</small>
                </div>
                
                <div class="stat-card">
                    <h3>📈 Señales MEDIUM</h3>
                    <div class="value neutral">{confidence_distribution.get('MEDIUM', 0)}</div>
                    <small>Solo logueadas</small>
                </div>
                
                <div class="stat-card">
                    <h3>📉 Señales LOW</h3>
                    <div class="value negative">{confidence_distribution.get('LOW', 0)}</div>
                    <small>Filtradas</small>
                </div>
            </div>
            
            <div class="section-title">💎 Análisis por Símbolo</div>
            <div class="symbol-cards">
        """
        
        # Generar cards por símbolo
        for symbol in self.symbols:
            symbol_stats = stats_by_symbol.get(symbol, {})
            total_sym_signals = symbol_stats.get('total_signals', 0)
            
            html_content += f"""
                <div class="symbol-card">
                    <h3>{symbol}</h3>
                    <div class="symbol-metrics">
                        <div class="metric-item">
                            <span>Total Señales:</span>
                            <span class="metric-value">{total_sym_signals}</span>
                        </div>
                        <div class="metric-item">
                            <span>Win Rate:</span>
                            <span class="metric-value {'positive' if symbol_stats.get('win_rate', 0) >= 50 else 'negative'}">{symbol_stats.get('win_rate', 0):.1f}%</span>
                        </div>
                        <div class="metric-item">
                            <span>P&L:</span>
                            <span class="metric-value {'positive' if symbol_stats.get('total_pnl', 0) > 0 else 'negative'}">{symbol_stats.get('total_pnl', 0):.2f} EUR</span>
                        </div>
                        <div class="metric-item">
                            <span>Ejecución:</span>
                            <span class="metric-value">{symbol_stats.get('execution_rate', 0):.1f}%</span>
                        </div>
                    </div>
                    <div class="confidence-breakdown">
                        <div class="confidence-mini-badge confidence-HIGH">
                            H: {symbol_stats.get('high_confidence', 0)}
                        </div>
                        <div class="confidence-mini-badge confidence-MEDIUM-HIGH">
                            MH: {symbol_stats.get('medium_high_confidence', 0)}
                        </div>
                        <div class="confidence-mini-badge confidence-MEDIUM">
                            M: {symbol_stats.get('medium_confidence', 0)}
                        </div>
                        <div class="confidence-mini-badge confidence-LOW">
                            L: {symbol_stats.get('low_confidence', 0)}
                        </div>
                    </div>
                </div>
            """
        
        html_content += f"""
            </div>
            
            <div class="signals-table">
                <h3>📋 Señales Filtradas ({len(filtered_signals)} resultados)</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Hora</th>
                            <th>Símbolo</th>
                            <th>Estrategia</th>
                            <th>Dirección</th>
                            <th>Precio</th>
                            <th>Confianza</th>
                            <th>Score</th>
                            <th>Estado</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        # Añadir filas de señales filtradas
        for signal in filtered_signals[:50]:  # Limitar a 50 para rendimiento
            timestamp = datetime.fromisoformat(signal['timestamp']).strftime('%H:%M:%S')
            confidence_class = f"confidence-{signal['confidence_level']}"
            
            if signal['executed']:
                status = "EJECUTADA"
                status_class = "status-executed"
            elif signal['rejected']:
                status = "RECHAZADA"
                status_class = "status-rejected"
            else:
                status = "PROPUESTA"
                status_class = "status-proposed"
            
            pnl_class = "positive" if signal['pnl'] > 0 else "negative" if signal['pnl'] < 0 else "neutral"
            
            html_content += f"""
                        <tr>
                            <td>{timestamp}</td>
                            <td><strong>{signal['symbol']}</strong></td>
                            <td>{signal['strategy']}</td>
                            <td>{signal['direction']}</td>
                            <td>{signal['price']:.5f}</td>
                            <td><span class="confidence-badge {confidence_class}">{signal['confidence_level']}</span></td>
                            <td>{signal['confidence_score']}/3</td>
                            <td class="{status_class}">{status}</td>
                            <td class="{pnl_class}">{signal['pnl']:.2f} EUR</td>
                        </tr>
            """
        
        if not filtered_signals:
            html_content += """
                        <tr>
                            <td colspan="9" style="text-align: center; color: rgba(255,255,255,0.6);">
                                No hay señales que coincidan con los filtros aplicados
                            </td>
                        </tr>
            """
        
        html_content += f"""
                    </tbody>
                </table>
            </div>
            
            <div style="text-align: center; padding: 30px 20px; color: rgba(255, 255, 255, 0.6); border-top: 1px solid rgba(255, 255, 255, 0.1); margin-top: 40px;">
                <p>🤖 Bot MT5 Dashboard Inteligente - Sistema de Confianza Integrado</p>
                <p>Última actualización: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                <p>Sesión: {self.session_id} • Filtros: Símbolo={symbol_filter}, Confianza={confidence_filter}, Estado={status_filter}</p>
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    def update_enhanced_dashboard(self, symbol_filter: str = 'ALL', 
                                confidence_filter: str = 'ALL',
                                status_filter: str = 'ALL'):
        """Actualizar dashboard mejorado"""
        try:
            html_content = self.generate_enhanced_dashboard_html(symbol_filter, confidence_filter, status_filter)
            
            with open(self.dashboard_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            dashboard_logger.log(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Dashboard inteligente actualizado: {self.dashboard_path}")
            
        except Exception as e:
            dashboard_logger.log(f"Error actualizando dashboard inteligente: {e}")
    
    def start_auto_update(self):
        """Iniciar actualización automática del dashboard mejorado"""
        if self.is_running:
            return
        
        self.is_running = True
        
        def update_loop():
            while self.is_running:
                self.update_enhanced_dashboard()
                time.sleep(self.update_interval)
        
        self.update_thread = threading.Thread(target=update_loop, daemon=True)
        self.update_thread.start()
        
        dashboard_logger.log(f"🚀 Dashboard inteligente iniciado - Actualización cada {self.update_interval//60} minutos")
        dashboard_logger.log(f"📁 Archivo: {os.path.abspath(self.dashboard_path)}")
        dashboard_logger.log(f"🔄 Sesión: {self.session_id} - Sistema de confianza integrado")
    
    def stop_auto_update(self):
        """Detener actualización automática"""
        self.is_running = False
        if self.update_thread:
            self.update_thread.join(timeout=1)
        dashboard_logger.log(f"⏹️ Dashboard inteligente detenido - Sesión: {self.session_id}")

# Instancia global del dashboard mejorado
enhanced_dashboard = EnhancedLiveDashboard()

def start_enhanced_dashboard():
    """Iniciar dashboard inteligente (llamar desde bot.py)"""
    enhanced_dashboard.start_auto_update()

def stop_enhanced_dashboard():
    """Detener dashboard inteligente"""
    enhanced_dashboard.stop_auto_update()

def add_signal_to_enhanced_dashboard(signal_data: Dict):
    """Añadir señal con confianza al dashboard (llamar desde bot.py)"""
    enhanced_dashboard.add_signal_with_confidence(signal_data)

if __name__ == "__main__":
    # Test del dashboard inteligente
    enhanced_dashboard.update_enhanced_dashboard()
    dashboard_logger.log("Dashboard inteligente generado para testing")