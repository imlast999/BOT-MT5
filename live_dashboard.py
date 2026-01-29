"""
Dashboard en tiempo real que se actualiza automáticamente
Muestra datos reales del bot con actualización cada 5 minutos
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
from typing import Dict, List, Any
import MetaTrader5 as mt5
from mt5_client import initialize as mt5_initialize

# Importar el tracker de señales rechazadas
try:
    from rejected_signals_tracker import rejected_signals_tracker
    REJECTION_TRACKING_AVAILABLE = True
except ImportError:
    REJECTION_TRACKING_AVAILABLE = False
    rejected_signals_tracker = None

class DashboardLogger:
    """Logger para el dashboard que escribe tanto a consola como a archivo"""
    
    def __init__(self):
        self.log_file = os.path.join(os.path.dirname(__file__), 'logs.txt')
    
    def log(self, message: str):
        """Escribir mensaje tanto a consola como a archivo"""
        print(message)  # Mostrar en consola
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message + '\n')
        except Exception:
            pass  # No fallar si no se puede escribir al archivo

dashboard_logger = DashboardLogger()

class LiveDashboard:
    def __init__(self):
        self.db_path = "bot_state.db"
        self.dashboard_path = "live_dashboard.html"
        self.update_interval = 300  # 5 minutos en segundos
        self.bot_start_time = datetime.now()
        self.session_id = self.bot_start_time.strftime('%Y%m%d_%H%M%S')
        self.is_running = False
        self.update_thread = None
        
        # Crear tablas para datos reales de la sesión
        self.init_session_db()
        
        # Limpiar datos de sesión anterior y empezar desde cero
        self.reset_session_data()
    
    def init_session_db(self):
        """Inicializar base de datos para datos reales de la sesión actual"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Tabla para trades reales de la sesión actual
        c.execute('''
            CREATE TABLE IF NOT EXISTS session_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                pair TEXT NOT NULL,
                strategy TEXT NOT NULL,
                type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                sl_price REAL NOT NULL,
                tp_price REAL NOT NULL,
                lot_size REAL NOT NULL,
                pnl REAL DEFAULT 0,
                status TEXT DEFAULT 'OPEN',
                mt5_ticket INTEGER,
                confidence TEXT,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                close_price REAL
            )
        ''')
        
        # Tabla para estadísticas de la sesión actual
        c.execute('''
            CREATE TABLE IF NOT EXISTS session_stats (
                session_id TEXT PRIMARY KEY,
                start_time TEXT NOT NULL,
                end_time TEXT,
                total_signals_generated INTEGER DEFAULT 0,
                total_signals_executed INTEGER DEFAULT 0,
                total_scans INTEGER DEFAULT 0,
                initial_balance REAL DEFAULT 5000.0,
                current_balance REAL DEFAULT 5000.0,
                peak_balance REAL DEFAULT 5000.0,
                max_drawdown REAL DEFAULT 0.0,
                total_pnl REAL DEFAULT 0.0,
                win_trades INTEGER DEFAULT 0,
                loss_trades INTEGER DEFAULT 0,
                last_update TEXT NOT NULL
            )
        ''')
        
        # Tabla para snapshots de balance cada 5 minutos
        c.execute('''
            CREATE TABLE IF NOT EXISTS balance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                balance REAL NOT NULL,
                equity REAL NOT NULL,
                margin REAL DEFAULT 0,
                free_margin REAL DEFAULT 0,
                profit REAL DEFAULT 0,
                open_positions INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def reset_session_data(self):
        """Limpiar datos de sesión anterior y empezar desde cero"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Insertar nueva sesión con datos iniciales en cero
        try:
            # Obtener balance inicial real de MT5
            initial_balance = 5000.0
            try:
                import MetaTrader5 as mt5
                from mt5_client import initialize as mt5_initialize
                mt5_initialize()
                account_info = mt5.account_info()
                if account_info:
                    initial_balance = account_info.balance
            except Exception:
                pass
            
            c.execute('''
                INSERT OR REPLACE INTO session_stats 
                (session_id, start_time, initial_balance, current_balance, peak_balance, last_update) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                self.session_id, 
                self.bot_start_time.isoformat(), 
                initial_balance,
                initial_balance,
                initial_balance,
                datetime.now().isoformat()
            ))
            
            # Crear primer snapshot de balance
            c.execute('''
                INSERT INTO balance_snapshots 
                (session_id, timestamp, balance, equity) 
                VALUES (?, ?, ?, ?)
            ''', (
                self.session_id,
                self.bot_start_time.isoformat(),
                initial_balance,
                initial_balance
            ))
            
            conn.commit()
            dashboard_logger.log(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Nueva sesión iniciada: {self.session_id}")
            dashboard_logger.log(f"[{datetime.now().strftime('%H:%M:%S')}] 💰 Balance inicial: {initial_balance} EUR")
            
        except Exception as e:
            dashboard_logger.log(f"Error inicializando sesión: {e}")
        finally:
            conn.close()
    
    def get_bot_uptime(self) -> Dict[str, Any]:
        """Obtener tiempo de funcionamiento del bot de la sesión actual"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            SELECT start_time, total_scans, total_signals_generated, total_signals_executed 
            FROM session_stats WHERE session_id = ?
        ''', (self.session_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            start_time = datetime.fromisoformat(row[0])
            uptime = datetime.now() - start_time
            
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            return {
                'uptime_str': f"{days}d {hours}h {minutes}m",
                'uptime_seconds': uptime.total_seconds(),
                'total_scans': row[1] or 0,
                'total_signals': row[2] or 0,
                'total_executed': row[3] or 0,
                'start_time': start_time,
                'session_id': self.session_id
            }
        
        return {
            'uptime_str': "0d 0h 0m",
            'uptime_seconds': 0,
            'total_scans': 0,
            'total_signals': 0,
            'total_executed': 0,
            'start_time': self.bot_start_time,
            'session_id': self.session_id
        }
    
    def get_mt5_account_info(self) -> Dict[str, Any]:
        """Obtener información real de la cuenta MT5"""
        try:
            mt5_initialize()
            account_info = mt5.account_info()
            
            if account_info:
                return {
                    'balance': account_info.balance,
                    'equity': account_info.equity,
                    'margin': account_info.margin,
                    'free_margin': account_info.margin_free,
                    'profit': account_info.profit,
                    'currency': account_info.currency
                }
        except Exception as e:
            print(f"Error obteniendo info MT5: {e}")
        
        # Datos por defecto si MT5 no está disponible
        return {
            'balance': 5000.0,
            'equity': 5000.0,
            'margin': 0.0,
            'free_margin': 5000.0,
            'profit': 0.0,
            'currency': 'USD'
        }
    
    def get_open_positions(self) -> List[Dict]:
        """Obtener posiciones abiertas reales de MT5"""
        try:
            mt5_initialize()
            positions = mt5.positions_get()
            
            if positions:
                return [{
                    'ticket': pos.ticket,
                    'symbol': pos.symbol,
                    'type': 'BUY' if pos.type == 0 else 'SELL',
                    'volume': pos.volume,
                    'price_open': pos.price_open,
                    'sl': pos.sl,
                    'tp': pos.tp,
                    'profit': pos.profit,
                    'time': datetime.fromtimestamp(pos.time)
                } for pos in positions]
        except Exception as e:
            print(f"Error obteniendo posiciones: {e}")
        
        return []
    
    def get_session_trades(self) -> List[Dict]:
        """Obtener trades reales de la sesión actual"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            SELECT timestamp, pair, strategy, type, pnl, status, confidence, lot_size, mt5_ticket
            FROM session_trades 
            WHERE session_id = ?
            ORDER BY timestamp DESC
        ''', (self.session_id,))
        
        trades = []
        for row in c.fetchall():
            trades.append({
                'timestamp': row[0],
                'pair': row[1],
                'strategy': row[2],
                'type': row[3],
                'pnl': row[4] or 0.0,
                'status': row[5],
                'confidence': row[6] or 'MEDIUM',
                'lot_size': row[7] or 0.01,
                'mt5_ticket': row[8]
            })
        
        conn.close()
        return trades
    
    def add_session_trade(self, trade_data: Dict):
        """Añadir un trade real a la sesión actual"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            c.execute('''
                INSERT INTO session_trades 
                (session_id, timestamp, pair, strategy, type, entry_price, sl_price, tp_price, 
                 lot_size, pnl, status, mt5_ticket, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.session_id,
                trade_data.get('timestamp', datetime.now().isoformat()),
                trade_data.get('pair', 'EURUSD'),
                trade_data.get('strategy', 'unknown'),
                trade_data.get('type', 'BUY'),
                trade_data.get('entry_price', 0.0),
                trade_data.get('sl_price', 0.0),
                trade_data.get('tp_price', 0.0),
                trade_data.get('lot_size', 0.01),
                trade_data.get('pnl', 0.0),
                trade_data.get('status', 'OPEN'),
                trade_data.get('mt5_ticket'),
                trade_data.get('confidence', 'MEDIUM'),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            dashboard_logger.log(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Trade añadido a sesión: {trade_data.get('pair')} {trade_data.get('type')}")
            
        except Exception as e:
            dashboard_logger.log(f"Error añadiendo trade a sesión: {e}")
        finally:
            conn.close()
    
    def update_trade_result(self, mt5_ticket: int, pnl: float, status: str = 'CLOSED'):
        """Actualizar resultado de un trade cuando se cierra"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            c.execute('''
                UPDATE session_trades 
                SET pnl = ?, status = ?, closed_at = ?
                WHERE mt5_ticket = ? AND session_id = ?
            ''', (pnl, status, datetime.now().isoformat(), mt5_ticket, self.session_id))
            
            conn.commit()
            
            if c.rowcount > 0:
                dashboard_logger.log(f"[{datetime.now().strftime('%H:%M:%S')}] 💰 Trade actualizado: Ticket {mt5_ticket}, P&L: {pnl}")
                # Actualizar estadísticas de la sesión
                self.update_session_stats()
            
        except Exception as e:
            dashboard_logger.log(f"Error actualizando trade: {e}")
        finally:
            conn.close()
    
    def update_session_stats(self):
        """Actualizar estadísticas de la sesión actual"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            # Obtener balance actual de MT5
            current_balance = 5000.0
            current_equity = 5000.0
            try:
                import MetaTrader5 as mt5
                from mt5_client import initialize as mt5_initialize
                mt5_initialize()
                account_info = mt5.account_info()
                if account_info:
                    current_balance = account_info.balance
                    current_equity = account_info.equity
            except Exception:
                pass
            
            # Calcular estadísticas de trades de la sesión
            c.execute('''
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                    SUM(pnl) as total_pnl,
                    MAX(pnl) as best_trade,
                    MIN(pnl) as worst_trade
                FROM session_trades 
                WHERE session_id = ? AND status = 'CLOSED'
            ''', (self.session_id,))
            
            trade_stats = c.fetchone()
            total_trades = trade_stats[0] or 0
            wins = trade_stats[1] or 0
            losses = trade_stats[2] or 0
            total_pnl = trade_stats[3] or 0.0
            
            # Obtener balance inicial
            c.execute('SELECT initial_balance FROM session_stats WHERE session_id = ?', (self.session_id,))
            initial_balance = c.fetchone()[0] or 5000.0
            
            # Calcular drawdown
            peak_balance = max(current_balance, initial_balance)
            drawdown = ((peak_balance - current_balance) / peak_balance) * 100 if peak_balance > 0 else 0
            
            # Actualizar estadísticas
            c.execute('''
                UPDATE session_stats 
                SET current_balance = ?, peak_balance = ?, max_drawdown = ?, 
                    total_pnl = ?, win_trades = ?, loss_trades = ?, last_update = ?
                WHERE session_id = ?
            ''', (
                current_balance, peak_balance, drawdown, total_pnl, 
                wins, losses, datetime.now().isoformat(), self.session_id
            ))
            
            # Crear snapshot de balance
            c.execute('''
                INSERT INTO balance_snapshots 
                (session_id, timestamp, balance, equity) 
                VALUES (?, ?, ?, ?)
            ''', (self.session_id, datetime.now().isoformat(), current_balance, current_equity))
            
            conn.commit()
            
        except Exception as e:
            dashboard_logger.log(f"Error actualizando estadísticas de sesión: {e}")
        finally:
            conn.close()
    
    def get_balance_history(self) -> List[Dict]:
        """Obtener historial de balance de la sesión actual"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            SELECT timestamp, balance, equity 
            FROM balance_snapshots 
            WHERE session_id = ?
            ORDER BY timestamp ASC
        ''', (self.session_id,))
        
        history = []
        for row in c.fetchall():
            history.append({
                'timestamp': row[0],
                'balance': row[1],
                'equity': row[2]
            })
        
        conn.close()
        return history
    
    def calculate_statistics(self, trades: List[Dict]) -> Dict[str, Any]:
        """Calcular estadísticas de trading de la sesión actual"""
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'roi': 0,
                'max_drawdown': 0,
                'profit_factor': 0,
                'gross_profit': 0,
                'gross_loss': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'best_trade': 0,
                'worst_trade': 0
            }
        
        # Usar datos reales de la sesión
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Obtener estadísticas de la sesión
        c.execute('''
            SELECT 
                initial_balance, current_balance, total_pnl, max_drawdown,
                win_trades, loss_trades
            FROM session_stats 
            WHERE session_id = ?
        ''', (self.session_id,))
        
        session_data = c.fetchone()
        if not session_data:
            conn.close()
            return self.calculate_statistics([])  # Recursión con lista vacía
        
        initial_balance = session_data[0] or 5000.0
        current_balance = session_data[1] or 5000.0
        total_pnl = session_data[2] or 0.0
        max_drawdown = session_data[3] or 0.0
        win_trades = session_data[4] or 0
        loss_trades = session_data[5] or 0
        
        # Calcular métricas adicionales de trades
        c.execute('''
            SELECT 
                SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) as gross_profit,
                SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) as gross_loss,
                AVG(CASE WHEN pnl > 0 THEN pnl ELSE NULL END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN pnl ELSE NULL END) as avg_loss,
                MAX(pnl) as best_trade,
                MIN(pnl) as worst_trade
            FROM session_trades 
            WHERE session_id = ? AND status = 'CLOSED'
        ''', (self.session_id,))
        
        trade_metrics = c.fetchone()
        conn.close()
        
        gross_profit = trade_metrics[0] or 0.0
        gross_loss = trade_metrics[1] or 0.0
        avg_win = trade_metrics[2] or 0.0
        avg_loss = trade_metrics[3] or 0.0
        best_trade = trade_metrics[4] or 0.0
        worst_trade = trade_metrics[5] or 0.0
        
        # Calcular métricas finales
        total_trades = win_trades + loss_trades
        win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
        roi = (total_pnl / initial_balance) * 100 if initial_balance > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'roi': roi,
            'max_drawdown': max_drawdown,
            'profit_factor': profit_factor,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'initial_balance': initial_balance,
            'current_balance': current_balance
        }
    
    def generate_equity_curve_chart(self, trades: List[Dict], timeframe: str = '1D') -> str:
        """Generar gráfico de curva de equity con datos reales de la sesión"""
        balance_history = self.get_balance_history()
        
        if not balance_history:
            return "<div style='text-align: center; color: #888; padding: 50px;'>No hay datos de balance disponibles para esta sesión</div>"
        
        # Convertir a DataFrame
        df = pd.DataFrame(balance_history)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        # Resample según timeframe si hay suficientes datos
        if len(df) > 1:
            df_indexed = df.set_index('timestamp')
            if timeframe == '1H' and len(df) > 12:
                df_resampled = df_indexed.resample('1H')[['balance', 'equity']].last().dropna()
            elif timeframe == '4H' and len(df) > 6:
                df_resampled = df_indexed.resample('4H')[['balance', 'equity']].last().dropna()
            elif timeframe == '1D':
                df_resampled = df_indexed.resample('1D')[['balance', 'equity']].last().dropna()
            elif timeframe == '1W':
                df_resampled = df_indexed.resample('1W')[['balance', 'equity']].last().dropna()
            else:
                df_resampled = df_indexed[['balance', 'equity']]
        else:
            df_resampled = df.set_index('timestamp')[['balance', 'equity']]
        
        fig = go.Figure()
        
        # Línea de balance
        fig.add_trace(go.Scatter(
            x=df_resampled.index,
            y=df_resampled['balance'],
            mode='lines+markers',
            name='Balance',
            line=dict(color='#00ff88', width=2),
            marker=dict(size=4)
        ))
        
        # Línea de equity
        fig.add_trace(go.Scatter(
            x=df_resampled.index,
            y=df_resampled['equity'],
            mode='lines+markers',
            name='Equity',
            line=dict(color='#00ccff', width=2, dash='dot'),
            marker=dict(size=4)
        ))
        
        # Línea de balance inicial
        if len(df_resampled) > 0:
            initial_balance = df_resampled['balance'].iloc[0]
            fig.add_hline(y=initial_balance, line_dash="dash", line_color="rgba(255,255,255,0.3)",
                         annotation_text=f"Balance Inicial: {initial_balance:.2f}")
        
        fig.update_layout(
            title=f"Curva de Equity - Sesión Actual ({timeframe})",
            xaxis_title="Tiempo",
            yaxis_title="Balance (EUR)",
            template="plotly_dark",
            height=400,
            showlegend=True,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01
            )
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="equity-curve")
    
    def get_rejection_statistics(self) -> Dict:
        """Obtener estadísticas de señales rechazadas para el dashboard"""
        if not REJECTION_TRACKING_AVAILABLE or not rejected_signals_tracker:
            return {
                'available': False,
                'total_rejections': 0,
                'by_symbol': {},
                'by_category': {},
                'recent_rejections': []
            }
        
        try:
            # Obtener estadísticas de las últimas 24 horas (sin filtrar por session_id para mostrar todos los rechazos)
            stats = rejected_signals_tracker.get_rejection_stats(hours_back=24, session_id=None)
            
            # Obtener rechazos recientes
            recent = rejected_signals_tracker.get_recent_rejections(limit=10)
            
            return {
                'available': True,
                'total_rejections': stats.get('total_rejections', 0),
                'by_symbol': stats.get('by_symbol', {}),
                'by_category': stats.get('by_category', {}),
                'by_strategy': stats.get('by_strategy', {}),
                'by_hour': stats.get('by_hour', {}),
                'recent_rejections': recent
            }
        except Exception as e:
            self.logger.error(f"Error obteniendo estadísticas de rechazos: {e}")
            return {
                'available': False,
                'total_rejections': 0,
                'by_symbol': {},
                'by_category': {},
                'recent_rejections': []
            }

    def generate_dashboard_html(self, timeframe: str = '1D') -> str:
        """Generar HTML completo del dashboard con datos reales de la sesión"""
        # Obtener datos reales de la sesión actual
        uptime_info = self.get_bot_uptime()
        account_info = self.get_mt5_account_info()
        positions = self.get_open_positions()
        trades = self.get_session_trades()
        stats = self.calculate_statistics(trades)
        rejection_stats = self.get_rejection_statistics()
        
        # Generar gráficos con datos reales
        equity_chart = self.generate_equity_curve_chart(trades, timeframe)
        
        # Balance final real
        final_balance = stats.get('current_balance', account_info['balance'])
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Bot MT5 - Dashboard Live (Sesión: {uptime_info['session_id']})</title>
            <meta http-equiv="refresh" content="300"> <!-- Auto-refresh cada 5 minutos -->
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
                
                .session-info {{
                    font-size: 0.8em;
                    color: rgba(255, 255, 255, 0.7);
                    margin-top: 5px;
                }}
                
                .status-info {{
                    display: flex;
                    gap: 20px;
                    font-size: 0.9em;
                }}
                
                .status-item {{
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                }}
                
                .status-value {{
                    font-weight: bold;
                    color: #00ff88;
                }}
                
                .controls {{
                    padding: 15px 20px;
                    background: rgba(255, 255, 255, 0.05);
                    display: flex;
                    gap: 10px;
                    align-items: center;
                }}
                
                .timeframe-btn {{
                    padding: 8px 15px;
                    background: rgba(255, 255, 255, 0.1);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    color: white;
                    border-radius: 5px;
                    cursor: pointer;
                    transition: all 0.3s;
                }}
                
                .timeframe-btn:hover,
                .timeframe-btn.active {{
                    background: #00ff88;
                    color: #000;
                }}
                
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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
                
                .rejection-breakdown {{
                    display: flex;
                    flex-direction: column;
                    gap: 4px;
                    font-size: 0.9em;
                }}
                
                .rejection-item {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 2px 0;
                }}
                
                .rejection-item .count {{
                    background: rgba(255, 0, 0, 0.2);
                    color: #ff6b6b;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 0.8em;
                }}
                
                .rejection-reason {{
                    font-size: 0.85em;
                    color: rgba(255, 255, 255, 0.8);
                }}
                
                .category-tag {{
                    background: rgba(255, 165, 0, 0.2);
                    color: #ffa500;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-size: 0.75em;
                    text-transform: uppercase;
                }}
                
                .table-container {{
                    margin-top: 20px;
                    background: rgba(255, 255, 255, 0.05);
                    border-radius: 12px;
                    padding: 15px;
                }}
                
                .data-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                }}
                
                .data-table th,
                .data-table td {{
                    padding: 8px 12px;
                    text-align: left;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }}
                
                .data-table th {{
                    background: rgba(0, 255, 136, 0.1);
                    color: #00ff88;
                    font-weight: bold;
                    font-size: 0.9em;
                }}
                
                .data-table td {{
                    font-size: 0.85em;
                }}
                
                .stat-card .value {{
                    font-size: 1.8em;
                    font-weight: bold;
                    margin-bottom: 5px;
                }}
                
                .positive {{ color: #00ff88; }}
                .negative {{ color: #ff4444; }}
                .neutral {{ color: #ffaa00; }}
                
                .charts-container {{
                    max-width: 1400px;
                    margin: 0 auto;
                    padding: 0 20px;
                }}
                
                .chart-section {{
                    background: rgba(255, 255, 255, 0.05);
                    border-radius: 15px;
                    margin-bottom: 20px;
                    padding: 20px;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }}
                
                .positions-table {{
                    background: rgba(255, 255, 255, 0.05);
                    border-radius: 15px;
                    padding: 20px;
                    margin: 20px auto;
                    max-width: 1400px;
                }}
                
                .positions-table table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 15px;
                }}
                
                .positions-table th,
                .positions-table td {{
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }}
                
                .positions-table th {{
                    background: rgba(0, 255, 136, 0.2);
                    color: #00ff88;
                    font-weight: bold;
                    text-transform: uppercase;
                    font-size: 0.9em;
                }}
                
                .footer {{
                    text-align: center;
                    padding: 30px 20px;
                    color: rgba(255, 255, 255, 0.6);
                    border-top: 1px solid rgba(255, 255, 255, 0.1);
                    margin-top: 40px;
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
                
                .session-badge {{
                    background: rgba(0, 255, 136, 0.2);
                    color: #00ff88;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 0.7em;
                    margin-left: 10px;
                }}
                
                @keyframes pulse {{
                    0% {{ opacity: 1; }}
                    50% {{ opacity: 0.5; }}
                    100% {{ opacity: 1; }}
                }}
                
                @media (max-width: 768px) {{
                    .stats-grid {{
                        grid-template-columns: repeat(2, 1fr);
                    }}
                    
                    .header {{
                        flex-direction: column;
                        gap: 10px;
                    }}
                    
                    .status-info {{
                        flex-wrap: wrap;
                        justify-content: center;
                    }}
                }}
            </style>
            <script>
                // Auto-refresh con indicador visual
                let refreshCountdown = 300; // 5 minutos
                
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
                
                // Actualizar cada segundo
                setInterval(updateCountdown, 1000);
                
                // Función para cambiar timeframe (placeholder)
                function changeTimeframe(tf) {{
                    // En una implementación real, esto recargaría con el nuevo timeframe
                    document.querySelectorAll('.timeframe-btn').forEach(btn => btn.classList.remove('active'));
                    event.target.classList.add('active');
                    // Aquí iría la lógica para recargar con nuevo timeframe
                }}
            </script>
        </head>
        <body>
            <div class="header">
                <div>
                    <h1><span class="live-indicator"></span>Bot MT5 Trading - LIVE</h1>
                    <div class="session-info">
                        Sesión actual: {uptime_info['session_id']} 
                        <span class="session-badge">DATOS REALES</span>
                    </div>
                    <small>Actualización automática cada 5 minutos</small>
                </div>
                <div class="status-info">
                    <div class="status-item">
                        <span>Tiempo Activo</span>
                        <span class="status-value">{uptime_info['uptime_str']}</span>
                    </div>
                    <div class="status-item">
                        <span>Scans Totales</span>
                        <span class="status-value">{uptime_info['total_scans']:,}</span>
                    </div>
                    <div class="status-item">
                        <span>Señales Generadas</span>
                        <span class="status-value">{uptime_info['total_signals']:,}</span>
                    </div>
                    <div class="status-item">
                        <span>Próxima Actualización</span>
                        <span class="status-value" id="refresh-countdown">5:00</span>
                    </div>
                </div>
            </div>
            
            <div class="controls">
                <span>Timeframe:</span>
                <button class="timeframe-btn" onclick="changeTimeframe('1H')">1H</button>
                <button class="timeframe-btn" onclick="changeTimeframe('4H')">4H</button>
                <button class="timeframe-btn active" onclick="changeTimeframe('1D')">1D</button>
                <button class="timeframe-btn" onclick="changeTimeframe('1W')">1W</button>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>📊 Total Trades</h3>
                    <div class="value">{stats['total_trades']}</div>
                    <small>Sesión actual</small>
                </div>
                
                <div class="stat-card">
                    <h3>🎯 Win Rate</h3>
                    <div class="value {'positive' if stats['win_rate'] >= 50 else 'negative'}">{stats['win_rate']:.1f}%</div>
                    <small>Trades cerrados</small>
                </div>
                
                <div class="stat-card">
                    <h3>💰 ROI Sesión</h3>
                    <div class="value {'positive' if stats['roi'] > 0 else 'negative'}">{stats['roi']:.2f}%</div>
                    <small>Desde inicio</small>
                </div>
                
                <div class="stat-card">
                    <h3>📈 P&L Total</h3>
                    <div class="value {'positive' if stats['total_pnl'] > 0 else 'negative'}">{stats['total_pnl']:.2f} EUR</div>
                    <small>Sesión actual</small>
                </div>
                
                <div class="stat-card">
                    <h3>📉 Max Drawdown</h3>
                    <div class="value negative">{stats['max_drawdown']:.2f}%</div>
                    <small>Pico a valle</small>
                </div>
                
                <div class="stat-card">
                    <h3>⚡ Balance Actual</h3>
                    <div class="value {'positive' if final_balance >= stats.get('initial_balance', 5000) else 'negative'}">{final_balance:.2f} EUR</div>
                    <small>MT5 en tiempo real</small>
                </div>
                
                <div class="stat-card">
                    <h3>💎 Equity</h3>
                    <div class="value {'positive' if account_info['equity'] >= account_info['balance'] else 'negative'}">{account_info['equity']:.2f} EUR</div>
                    <small>Incluye posiciones</small>
                </div>
                
                <div class="stat-card">
                    <h3>🔥 Profit Factor</h3>
                    <div class="value {'positive' if stats['profit_factor'] > 1 else 'negative'}">{stats['profit_factor']:.2f}</div>
                    <small>Ganancia/Pérdida</small>
                </div>
            </div>
            
            <!-- Estadísticas de Señales Rechazadas -->
            <div class="section">
                <h2>🚫 Análisis de Señales Rechazadas</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3>🚫 Total Rechazadas</h3>
                        <div class="value negative">{rejection_stats['total_rejections']}</div>
                        <small>Últimas 24h</small>
                    </div>
                    
                    <div class="stat-card">
                        <h3>📊 Por Símbolo</h3>
                        <div class="rejection-breakdown">
                            {''.join([f'<div class="rejection-item"><span>{symbol}</span><span class="count">{count}</span></div>' 
                                     for symbol, count in list(rejection_stats['by_symbol'].items())[:3]])}
                        </div>
                        <small>Top 3 símbolos</small>
                    </div>
                    
                    <div class="stat-card">
                        <h3>🔍 Por Categoría</h3>
                        <div class="rejection-breakdown">
                            {''.join([f'<div class="rejection-item"><span>{category.replace("_", " ")}</span><span class="count">{count}</span></div>' 
                                     for category, count in list(rejection_stats['by_category'].items())[:3]])}
                        </div>
                        <small>Top 3 razones</small>
                    </div>
                    
                    <div class="stat-card">
                        <h3>⚙️ Por Estrategia</h3>
                        <div class="rejection-breakdown">
                            {''.join([f'<div class="rejection-item"><span>{strategy}</span><span class="count">{count}</span></div>' 
                                     for strategy, count in list(rejection_stats['by_strategy'].items())[:3]])}
                        </div>
                        <small>Top 3 estrategias</small>
                    </div>
                </div>
                
                <!-- Tabla de Rechazos Recientes -->
                <div class="table-container">
                    <h3>📋 Rechazos Recientes</h3>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Hora</th>
                                <th>Símbolo</th>
                                <th>Estrategia</th>
                                <th>Razón del Rechazo</th>
                                <th>Categoría</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join([f'''
                            <tr>
                                <td>{datetime.fromisoformat(rejection['timestamp'].replace('Z', '+00:00')).strftime('%H:%M:%S')}</td>
                                <td><span class="symbol">{rejection['symbol']}</span></td>
                                <td>{rejection['strategy']}</td>
                                <td class="rejection-reason">{rejection['rejection_reason'][:50]}{'...' if len(rejection['rejection_reason']) > 50 else ''}</td>
                                <td><span class="category-tag">{rejection['rejection_category'].replace('_', ' ')}</span></td>
                            </tr>
                            ''' for rejection in rejection_stats['recent_rejections'][:10]])}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <div class="charts-container">
                <div class="chart-section">
                    {equity_chart}
                </div>
            </div>
            
            <div class="positions-table">
                <h3>📊 Posiciones Abiertas ({len(positions)})</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Ticket</th>
                            <th>Par</th>
                            <th>Tipo</th>
                            <th>Volumen</th>
                            <th>Precio</th>
                            <th>SL</th>
                            <th>TP</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        # Añadir posiciones abiertas
        if positions:
            for pos in positions:
                pnl_class = "positive" if pos['profit'] > 0 else "negative" if pos['profit'] < 0 else "neutral"
                html_content += f"""
                        <tr>
                            <td>{pos['ticket']}</td>
                            <td><strong>{pos['symbol']}</strong></td>
                            <td>{pos['type']}</td>
                            <td>{pos['volume']}</td>
                            <td>{pos['price_open']:.5f}</td>
                            <td>{f"{pos['sl']:.5f}" if pos['sl'] > 0 else '-'}</td>
                            <td>{f"{pos['tp']:.5f}" if pos['tp'] > 0 else '-'}</td>
                            <td class="{pnl_class}">{pos['profit']:.2f} EUR</td>
                        </tr>
                """
        else:
            html_content += """
                        <tr>
                            <td colspan="8" style="text-align: center; color: rgba(255,255,255,0.6);">
                                No hay posiciones abiertas en esta sesión
                            </td>
                        </tr>
            """
        
        html_content += f"""
                    </tbody>
                </table>
            </div>
            
            <div class="footer">
                <p>🤖 Bot MT5 Trading System - Dashboard Live (Sesión: {uptime_info['session_id']})</p>
                <p>Última actualización: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                <p>Datos reales desde MT5 • Sesión iniciada: {uptime_info['start_time'].strftime('%d/%m/%Y %H:%M:%S')}</p>
                <p>Balance inicial: {stats.get('initial_balance', 5000):.2f} EUR • Auto-refresh cada 5 minutos</p>
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    def update_dashboard(self):
        """Actualizar dashboard con datos frescos de la sesión actual"""
        try:
            # Actualizar estadísticas de la sesión antes de generar HTML
            self.update_session_stats()
            
            html_content = self.generate_dashboard_html()
            
            with open(self.dashboard_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            dashboard_logger.log(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Dashboard actualizado: {self.dashboard_path} (Sesión: {self.session_id})")
            
        except Exception as e:
            dashboard_logger.log(f"Error actualizando dashboard: {e}")
    
    def update_bot_stats(self, scans_increment: int = 1, signals_increment: int = 0):
        """Actualizar estadísticas del bot para la sesión actual"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            c.execute('''
                UPDATE session_stats 
                SET total_scans = total_scans + ?, 
                    total_signals_generated = total_signals_generated + ?,
                    last_update = ?
                WHERE session_id = ?
            ''', (scans_increment, signals_increment, datetime.now().isoformat(), self.session_id))
            
            conn.commit()
            
            if signals_increment > 0:
                dashboard_logger.log(f"[{datetime.now().strftime('%H:%M:%S')}] 📈 Stats actualizadas: +{scans_increment} scans, +{signals_increment} señales")
            
        except Exception as e:
            dashboard_logger.log(f"Error actualizando stats del bot: {e}")
        finally:
            conn.close()
    
    def start_auto_update(self):
        """Iniciar actualización automática en hilo separado"""
        if self.is_running:
            return
        
        self.is_running = True
        
        def update_loop():
            while self.is_running:
                self.update_dashboard()
                time.sleep(self.update_interval)
        
        self.update_thread = threading.Thread(target=update_loop, daemon=True)
        self.update_thread.start()
        
        dashboard_logger.log(f"🚀 Dashboard live iniciado - Actualización cada {self.update_interval//60} minutos")
        dashboard_logger.log(f"📁 Archivo: {os.path.abspath(self.dashboard_path)}")
        dashboard_logger.log(f"🔄 Sesión: {self.session_id} - Datos reales desde cero")
    
    def stop_auto_update(self):
        """Detener actualización automática"""
        self.is_running = False
        if self.update_thread:
            self.update_thread.join(timeout=1)
        dashboard_logger.log(f"⏹️ Dashboard live detenido - Sesión: {self.session_id}")
    
    def get_combined_historical_data(self, days: int = 30) -> Dict[str, Any]:
        """Combinar datos de la sesión actual con datos históricos de backtesting"""
        try:
            # Obtener datos de la sesión actual
            session_trades = self.get_session_trades()
            session_stats = self.calculate_statistics(session_trades)
            
            # Intentar obtener datos históricos del sistema de backtesting
            historical_data = {}
            try:
                from backtest_tracker import backtest_tracker
                historical_stats = backtest_tracker.get_statistics(days)
                historical_data = {
                    'historical_trades': historical_stats.get('total_signals', 0),
                    'historical_win_rate': historical_stats.get('win_rate', 0),
                    'historical_pnl': historical_stats.get('total_pnl', 0),
                    'historical_available': True
                }
            except Exception:
                historical_data = {'historical_available': False}
            
            return {
                'session_data': session_stats,
                'historical_data': historical_data,
                'combined_available': historical_data.get('historical_available', False)
            }
            
        except Exception as e:
            dashboard_logger.log(f"Error obteniendo datos combinados: {e}")
            return {'session_data': {}, 'historical_data': {}, 'combined_available': False}

# Instancia global
live_dashboard = LiveDashboard()

def start_live_dashboard():
    """Iniciar dashboard live (llamar desde bot.py)"""
    live_dashboard.start_auto_update()

def stop_live_dashboard():
    """Detener dashboard live"""
    live_dashboard.stop_auto_update()

def update_dashboard_stats(scans: int = 1, signals: int = 0):
    """Actualizar stats desde el bot"""
    live_dashboard.update_bot_stats(scans, signals)

if __name__ == "__main__":
    # Test del dashboard live
    live_dashboard.update_dashboard()
    dashboard_logger.log("Dashboard generado para testing")