"""
Gestor de riesgo integrado para el bot de trading MT5
Se integra con el sistema existente para mejorar la gestión de riesgo
"""

import json
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

@dataclass
class TradeRecord:
    """Registro de un trade"""
    timestamp: datetime
    symbol: str
    trade_type: str
    entry_price: float
    sl_price: float
    tp_price: float
    lot_size: float
    result: Optional[str] = None  # 'win', 'loss', 'pending'
    pnl: Optional[float] = None
    risk_amount: Optional[float] = None

class EnhancedRiskManager:
    """Gestor de riesgo mejorado que se integra con el bot existente"""
    
    def __init__(self, db_path: str = 'bot_state.db', rules_config_path: str = 'rules_config.json'):
        self.db_path = db_path
        self.rules_config_path = rules_config_path
        self.init_risk_db()
        self.load_rules_config()
        
    def init_risk_db(self):
        """Inicializa las tablas de gestión de riesgo"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Tabla de trades
        c.execute('''CREATE TABLE IF NOT EXISTS trades_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            entry_price REAL NOT NULL,
            sl_price REAL NOT NULL,
            tp_price REAL NOT NULL,
            lot_size REAL NOT NULL,
            result TEXT,
            pnl REAL,
            risk_amount REAL,
            strategy TEXT
        )''')
        
        # Tabla de métricas diarias
        c.execute('''CREATE TABLE IF NOT EXISTS daily_metrics (
            date TEXT PRIMARY KEY,
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            losing_trades INTEGER DEFAULT 0,
            total_pnl REAL DEFAULT 0.0,
            max_drawdown REAL DEFAULT 0.0,
            risk_used REAL DEFAULT 0.0
        )''')
        
        # Tabla de configuración de riesgo
        c.execute('''CREATE TABLE IF NOT EXISTS risk_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )''')
        
        conn.commit()
        conn.close()
        
    def load_rules_config(self):
        """Carga la configuración de reglas"""
        try:
            with open(self.rules_config_path, 'r', encoding='utf-8') as f:
                self.rules_config = json.load(f)
        except Exception as e:
            logger.error(f"Error cargando configuración de reglas: {e}")
            self.rules_config = {}
    
    def can_take_trade(self, signal: dict, account_balance: float) -> Tuple[bool, str, dict]:
        """
        Determina si se puede tomar un trade basado en reglas avanzadas
        Retorna: (puede_tomar, razón, info_adicional)
        """
        symbol = signal.get('symbol', '').upper()
        
        # Obtener configuración del símbolo
        symbol_config = self.rules_config.get(symbol, {})
        global_config = self.rules_config.get('GLOBAL_SETTINGS', {})
        
        if not symbol_config.get('enabled', True):
            return False, f"Trading deshabilitado para {symbol}", {}
        
        # 1. Verificar límites diarios
        today = datetime.now(timezone.utc).date().isoformat()
        daily_stats = self.get_daily_stats(today)
        
        # Límite de trades diarios por símbolo
        max_daily_symbol = symbol_config.get('max_daily_trades', 3)
        symbol_trades_today = self.get_symbol_trades_today(symbol, today)
        if symbol_trades_today >= max_daily_symbol:
            return False, f"Límite diario de trades para {symbol} alcanzado ({symbol_trades_today}/{max_daily_symbol})", {}
        
        # Límite total de trades diarios
        max_daily_total = global_config.get('max_daily_trades_all', 5)
        if daily_stats['total_trades'] >= max_daily_total:
            return False, f"Límite diario total de trades alcanzado ({daily_stats['total_trades']}/{max_daily_total})", {}
        
        # 2. Verificar riesgo
        risk_check = self.check_risk_limits(signal, account_balance, symbol_config, global_config)
        if not risk_check['can_trade']:
            return False, risk_check['reason'], risk_check
        
        # 3. Verificar drawdown
        current_drawdown = self.calculate_current_drawdown(account_balance)
        max_drawdown = global_config.get('drawdown_limit', 10.0)
        if current_drawdown > max_drawdown:
            return False, f"Drawdown máximo excedido: {current_drawdown:.1f}% > {max_drawdown}%", {}
        
        # 4. Verificar correlación con posiciones abiertas
        correlation_check = self.check_correlation(symbol)
        if not correlation_check['can_trade']:
            return False, correlation_check['reason'], correlation_check
        
        # 5. Verificar ratio R:R
        rr_ratio = self.calculate_rr_ratio(signal)
        min_rr = symbol_config.get('min_rr_ratio', 1.5)
        if rr_ratio < min_rr:
            return False, f"R:R insuficiente: {rr_ratio:.2f} < {min_rr}", {'rr_ratio': rr_ratio}
        
        # 6. Verificar sesión activa
        if not self.is_active_session(symbol, symbol_config):
            return False, "Fuera de sesión activa para este símbolo", {}
        
        # 7. Verificar horario de noticias
        if symbol_config.get('avoid_news', True) and self.is_news_time(symbol, global_config):
            return False, "Horario de noticias - evitando trades", {}
        
        # Calcular información adicional
        suggested_lot = self.calculate_optimal_lot_size(signal, account_balance, symbol_config)
        
        info = {
            'suggested_lot': suggested_lot,
            'risk_amount': risk_check.get('risk_amount', 0),
            'rr_ratio': rr_ratio,
            'daily_trades_used': daily_stats['total_trades'],
            'symbol_trades_today': symbol_trades_today,
            'current_drawdown': current_drawdown
        }
        
        return True, "Trade aprobado por gestión de riesgo", info
    
    def check_risk_limits(self, signal: dict, account_balance: float, symbol_config: dict, global_config: dict) -> dict:
        """Verifica los límites de riesgo"""
        entry = float(signal.get('entry', 0))
        sl = float(signal.get('sl', 0))
        
        if entry == sl:
            return {'can_trade': False, 'reason': 'SL igual a entrada'}
        
        # Riesgo por trade
        risk_per_trade = symbol_config.get('risk_per_trade', 0.5) / 100
        risk_amount = account_balance * risk_per_trade
        
        # Verificar riesgo total usado hoy
        today = datetime.now(timezone.utc).date().isoformat()
        daily_stats = self.get_daily_stats(today)
        max_total_risk = global_config.get('max_total_risk', 2.0) / 100
        max_risk_amount = account_balance * max_total_risk
        
        if daily_stats['risk_used'] + risk_amount > max_risk_amount:
            return {
                'can_trade': False,
                'reason': f"Riesgo diario máximo excedido: {daily_stats['risk_used'] + risk_amount:.2f} > {max_risk_amount:.2f}",
                'risk_used_today': daily_stats['risk_used'],
                'max_risk_today': max_risk_amount
            }
        
        # Verificar si estamos en racha perdedora
        recent_performance = self.get_recent_performance()
        risk_multiplier = self.get_risk_multiplier(recent_performance, global_config)
        adjusted_risk_amount = risk_amount * risk_multiplier
        
        return {
            'can_trade': True,
            'reason': 'Riesgo dentro de límites',
            'risk_amount': adjusted_risk_amount,
            'risk_multiplier': risk_multiplier,
            'base_risk': risk_amount
        }
    
    def check_correlation(self, symbol: str) -> dict:
        """Verifica correlación con posiciones abiertas"""
        try:
            positions = mt5.positions_get()
            if not positions:
                return {'can_trade': True, 'reason': 'Sin posiciones abiertas'}
            
            # Matriz de correlación simplificada (debería ser más sofisticada)
            correlations = {
                'EURUSD': ['XAUUSD'],  # Correlación baja entre EUR y oro
                'XAUUSD': ['EURUSD'],  # Oro puede correlacionar inversamente con USD
                'BTCEUR': [],  # Crypto generalmente no correlacionado con forex
                'XAUUSD': [],  # Oro generalmente no correlacionado
            }
            
            correlated_symbols = correlations.get(symbol, [])
            max_correlation = self.rules_config.get('GLOBAL_SETTINGS', {}).get('correlation_limit', 0.7)
            
            for pos in positions:
                pos_symbol = pos.symbol
                if pos_symbol in correlated_symbols:
                    return {
                        'can_trade': False,
                        'reason': f'Posición correlacionada abierta: {pos_symbol}',
                        'correlated_position': pos_symbol
                    }
            
            return {'can_trade': True, 'reason': 'Sin correlaciones problemáticas'}
            
        except Exception as e:
            logger.error(f"Error verificando correlación: {e}")
            return {'can_trade': True, 'reason': 'Error en verificación de correlación'}
    
    def calculate_rr_ratio(self, signal: dict) -> float:
        """Calcula el ratio riesgo:recompensa"""
        entry = float(signal.get('entry', 0))
        sl = float(signal.get('sl', 0))
        tp = float(signal.get('tp', entry))
        
        if entry == sl:
            return 0.0
        
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        
        return reward / risk if risk > 0 else 0.0
    
    def is_active_session(self, symbol: str, symbol_config: dict) -> bool:
        """Verifica si estamos en una sesión activa"""
        active_sessions = symbol_config.get('active_sessions', ['all'])
        if 'all' in active_sessions:
            return True
        
        now = datetime.now(timezone.utc)
        hour = now.hour
        
        global_config = self.rules_config.get('GLOBAL_SETTINGS', {})
        session_definitions = global_config.get('session_definitions', {
            'tokyo': {'start': 0, 'end': 9},
            'london': {'start': 8, 'end': 17},
            'newyork': {'start': 13, 'end': 22},
            'overlap': {'start': 13, 'end': 17}
        })
        
        for session_name in active_sessions:
            session = session_definitions.get(session_name, {})
            start_hour = session.get('start', 0)
            end_hour = session.get('end', 23)
            
            if start_hour <= hour <= end_hour:
                return True
        
        return False
    
    def is_news_time(self, symbol: str, global_config: dict) -> bool:
        """Verifica si estamos en horario de noticias"""
        high_impact_pairs = global_config.get('high_impact_news_pairs', [])
        if symbol not in high_impact_pairs:
            return False
        
        now = datetime.now(timezone.utc)
        hour = now.hour
        minute = now.minute
        
        # Horarios típicos de noticias importantes (GMT)
        news_times = [
            (8, 30),   # EUR news
            (12, 30),  # GBP news  
            (13, 30),  # USD news
            (15, 30),  # USD news
        ]
        
        blackout_minutes = global_config.get('news_blackout_minutes', 30)
        
        for news_hour, news_minute in news_times:
            news_time = datetime.now(timezone.utc).replace(hour=news_hour, minute=news_minute)
            current_time = datetime.now(timezone.utc)
            
            time_diff = abs((current_time - news_time).total_seconds() / 60)
            if time_diff <= blackout_minutes:
                return True
        
        return False
    
    def calculate_optimal_lot_size(self, signal: dict, account_balance: float, symbol_config: dict) -> float:
        """Calcula el tamaño de lote óptimo"""
        try:
            symbol = signal.get('symbol', '')
            entry = float(signal.get('entry', 0))
            sl = float(signal.get('sl', 0))
            
            if entry == sl:
                return 0.0
            
            # Obtener información del símbolo
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return 0.01  # Valor por defecto
            
            # Riesgo por trade ajustado
            risk_per_trade = symbol_config.get('risk_per_trade', 0.5) / 100
            recent_performance = self.get_recent_performance()
            global_config = self.rules_config.get('GLOBAL_SETTINGS', {})
            risk_multiplier = self.get_risk_multiplier(recent_performance, global_config)
            
            risk_amount = account_balance * risk_per_trade * risk_multiplier
            
            # Calcular lot size
            risk_points = abs(entry - sl)
            point_value = symbol_info.point
            contract_size = getattr(symbol_info, 'trade_contract_size', 100000)
            
            # Valor por punto
            pip_value = contract_size * point_value
            
            # Lot size
            lot_size = risk_amount / (risk_points * pip_value) if risk_points > 0 else 0.01
            
            # Ajustar a los límites del símbolo
            vol_min = getattr(symbol_info, 'volume_min', 0.01)
            vol_max = getattr(symbol_info, 'volume_max', 100.0)
            vol_step = getattr(symbol_info, 'volume_step', 0.01)
            
            # Redondear al step más cercano
            steps = round(lot_size / vol_step)
            lot_size = max(vol_min, min(vol_max, steps * vol_step))
            
            return lot_size
            
        except Exception as e:
            logger.error(f"Error calculando lot size: {e}")
            return 0.01
    
    def get_risk_multiplier(self, recent_performance: dict, global_config: dict) -> float:
        """Calcula el multiplicador de riesgo basado en performance reciente"""
        risk_scaling = global_config.get('risk_scaling', {})
        
        winning_streak = recent_performance.get('winning_streak', 0)
        losing_streak = recent_performance.get('losing_streak', 0)
        
        if losing_streak >= 3:
            return risk_scaling.get('losing_streak_3', 0.5)
        elif losing_streak >= 2:
            return risk_scaling.get('losing_streak_2', 0.8)
        elif winning_streak >= 5:
            return risk_scaling.get('winning_streak_5', 1.5)
        elif winning_streak >= 3:
            return risk_scaling.get('winning_streak_3', 1.2)
        
        return 1.0  # Multiplicador normal
    
    def record_trade(self, signal: dict, lot_size: float, strategy: str = '') -> int:
        """Registra un trade en la base de datos"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        trade_record = TradeRecord(
            timestamp=datetime.now(timezone.utc),
            symbol=signal.get('symbol', ''),
            trade_type=signal.get('type', ''),
            entry_price=float(signal.get('entry', 0)),
            sl_price=float(signal.get('sl', 0)),
            tp_price=float(signal.get('tp', 0)),
            lot_size=lot_size,
            result='pending'
        )
        
        c.execute('''INSERT INTO trades_history 
                     (timestamp, symbol, trade_type, entry_price, sl_price, tp_price, lot_size, result, strategy)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (trade_record.timestamp.isoformat(), trade_record.symbol, trade_record.trade_type,
                   trade_record.entry_price, trade_record.sl_price, trade_record.tp_price,
                   trade_record.lot_size, trade_record.result, strategy))
        
        trade_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Actualizar métricas diarias
        self.update_daily_metrics()
        
        return trade_id
    
    def get_daily_stats(self, date: str) -> dict:
        """Obtiene estadísticas del día"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('SELECT * FROM daily_metrics WHERE date = ?', (date,))
        row = c.fetchone()
        
        if row:
            return {
                'total_trades': row[1],
                'winning_trades': row[2],
                'losing_trades': row[3],
                'total_pnl': row[4],
                'max_drawdown': row[5],
                'risk_used': row[6]
            }
        else:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0.0,
                'max_drawdown': 0.0,
                'risk_used': 0.0
            }
    
    def get_symbol_trades_today(self, symbol: str, date: str) -> int:
        """Obtiene el número de trades del símbolo hoy"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''SELECT COUNT(*) FROM trades_history 
                     WHERE symbol = ? AND date(timestamp) = ?''', (symbol, date))
        
        count = c.fetchone()[0]
        conn.close()
        
        return count
    
    def get_recent_performance(self, days: int = 7) -> dict:
        """Obtiene la performance reciente"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        c.execute('''SELECT result FROM trades_history 
                     WHERE timestamp > ? AND result IS NOT NULL 
                     ORDER BY timestamp DESC LIMIT 10''', (cutoff_date,))
        
        results = [row[0] for row in c.fetchall()]
        conn.close()
        
        if not results:
            return {'winning_streak': 0, 'losing_streak': 0, 'win_rate': 0.0}
        
        # Calcular rachas
        winning_streak = 0
        losing_streak = 0
        
        for result in results:
            if result == 'win':
                winning_streak += 1
                break
            elif result == 'loss':
                losing_streak += 1
            else:
                break
        
        wins = results.count('win')
        win_rate = wins / len(results) if results else 0.0
        
        return {
            'winning_streak': winning_streak,
            'losing_streak': losing_streak,
            'win_rate': win_rate,
            'total_trades': len(results)
        }
    
    def calculate_current_drawdown(self, current_balance: float) -> float:
        """Calcula el drawdown actual"""
        # Esto debería calcularse basado en el balance máximo histórico
        # Por simplicidad, retornamos 0 por ahora
        return 0.0
    
    def update_daily_metrics(self):
        """Actualiza las métricas diarias"""
        today = datetime.now(timezone.utc).date().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Contar trades del día
        c.execute('''SELECT COUNT(*), 
                            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END),
                            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END),
                            SUM(COALESCE(pnl, 0)),
                            SUM(COALESCE(risk_amount, 0))
                     FROM trades_history 
                     WHERE date(timestamp) = ?''', (today,))
        
        row = c.fetchone()
        total_trades, winning_trades, losing_trades, total_pnl, risk_used = row
        
        c.execute('''INSERT OR REPLACE INTO daily_metrics 
                     (date, total_trades, winning_trades, losing_trades, total_pnl, risk_used)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (today, total_trades or 0, winning_trades or 0, losing_trades or 0, 
                   total_pnl or 0.0, risk_used or 0.0))
        
        conn.commit()
        conn.close()
    
    def get_performance_report(self, days: int = 30) -> dict:
        """Genera un reporte de performance"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        c.execute('''SELECT COUNT(*) as total_trades,
                            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                            SUM(COALESCE(pnl, 0)) as total_pnl,
                            AVG(CASE WHEN result = 'win' THEN pnl END) as avg_win,
                            AVG(CASE WHEN result = 'loss' THEN pnl END) as avg_loss
                     FROM trades_history 
                     WHERE timestamp > ?''', (cutoff_date,))
        
        row = c.fetchone()
        conn.close()
        
        if not row or row[0] == 0:
            return {'error': 'No hay datos suficientes'}
        
        total_trades, wins, losses, total_pnl, avg_win, avg_loss = row
        
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (avg_win * wins) / abs(avg_loss * losses) if avg_loss and losses > 0 else 0
        
        return {
            'period_days': days,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'avg_win': round(avg_win or 0, 2),
            'avg_loss': round(avg_loss or 0, 2),
            'profit_factor': round(profit_factor, 2)
        }

# Función de utilidad para integrar con el bot existente
def create_risk_manager(db_path: str = 'bot_state.db') -> EnhancedRiskManager:
    """Crea una instancia del gestor de riesgo"""
    return EnhancedRiskManager(db_path)