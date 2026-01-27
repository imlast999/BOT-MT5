"""
Sistema de tracking de señales rechazadas para análisis y mejora del bot
"""

import sqlite3
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

def _serialize_for_json(obj):
    """Convierte objetos datetime a string para JSON"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    else:
        return obj

class RejectedSignalsTracker:
    """Rastrea y analiza señales rechazadas para mejorar el sistema"""
    
    def __init__(self, db_path: str = 'bot_state.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inicializa la tabla de señales rechazadas"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rejected_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy TEXT,
                    rejection_reason TEXT NOT NULL,
                    rejection_category TEXT,
                    signal_data TEXT,
                    market_conditions TEXT,
                    session_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Crear índices para consultas rápidas
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_rejected_symbol ON rejected_signals(symbol)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_rejected_timestamp ON rejected_signals(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_rejected_category ON rejected_signals(rejection_category)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_rejected_session ON rejected_signals(session_id)')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error inicializando DB de señales rechazadas: {e}")
    
    def add_rejected_signal(self, 
                          symbol: str, 
                          strategy: str, 
                          rejection_reason: str,
                          signal_data: Dict = None,
                          market_conditions: Dict = None,
                          session_id: str = None) -> int:
        """
        Registra una señal rechazada
        
        Args:
            symbol: Símbolo del activo (EURUSD, XAUUSD, etc.)
            strategy: Estrategia que se intentó usar
            rejection_reason: Razón específica del rechazo
            signal_data: Datos de la señal que se intentó generar
            market_conditions: Condiciones del mercado en el momento
            session_id: ID de la sesión actual del bot
            
        Returns:
            ID del registro creado
        """
        try:
            # Categorizar el tipo de rechazo
            rejection_category = self._categorize_rejection(rejection_reason)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO rejected_signals 
                (timestamp, symbol, strategy, rejection_reason, rejection_category, 
                 signal_data, market_conditions, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(timezone.utc).isoformat(),
                symbol,
                strategy,
                rejection_reason,
                rejection_category,
                json.dumps(_serialize_for_json(signal_data)) if signal_data else None,
                json.dumps(_serialize_for_json(market_conditions)) if market_conditions else None,
                session_id
            ))
            
            rejected_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            logger.debug(f"Señal rechazada registrada: {symbol} - {rejection_reason}")
            return rejected_id
            
        except Exception as e:
            logger.error(f"Error registrando señal rechazada: {e}")
            return -1
    
    def _categorize_rejection(self, reason: str) -> str:
        """Categoriza el tipo de rechazo para análisis"""
        reason_lower = reason.lower()
        
        if 'no hay señal básica' in reason_lower or 'no signal' in reason_lower:
            return 'NO_BASIC_SIGNAL'
        elif 'confluencia' in reason_lower or 'confluence' in reason_lower:
            return 'CONFLUENCE_FAILED'
        elif 'sesión' in reason_lower or 'session' in reason_lower:
            return 'SESSION_FILTER'
        elif 'rsi' in reason_lower:
            return 'RSI_FILTER'
        elif 'volatilidad' in reason_lower or 'volatility' in reason_lower:
            return 'VOLATILITY_FILTER'
        elif 'drawdown' in reason_lower:
            return 'DRAWDOWN_FILTER'
        elif 'correlación' in reason_lower or 'correlation' in reason_lower:
            return 'CORRELATION_FILTER'
        elif 'confianza' in reason_lower or 'confidence' in reason_lower:
            return 'CONFIDENCE_FILTER'
        elif 'r:r' in reason_lower or 'risk reward' in reason_lower:
            return 'RR_FILTER'
        else:
            return 'OTHER'
    
    def get_rejection_stats(self, 
                          symbol: str = None, 
                          hours_back: int = 24,
                          session_id: str = None) -> Dict:
        """
        Obtiene estadísticas de señales rechazadas
        
        Args:
            symbol: Filtrar por símbolo específico
            hours_back: Horas hacia atrás para el análisis
            session_id: Filtrar por sesión específica
            
        Returns:
            Diccionario con estadísticas detalladas
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Construir query base
            where_conditions = []
            params = []
            
            if symbol:
                where_conditions.append("symbol = ?")
                params.append(symbol)
            
            if session_id:
                where_conditions.append("session_id = ?")
                params.append(session_id)
            
            if hours_back:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
                where_conditions.append("timestamp >= ?")
                params.append(cutoff_time.isoformat())
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            # Total de rechazos
            cursor.execute(f"SELECT COUNT(*) FROM rejected_signals WHERE {where_clause}", params)
            total_rejections = cursor.fetchone()[0]
            
            # Rechazos por símbolo
            cursor.execute(f"""
                SELECT symbol, COUNT(*) as count 
                FROM rejected_signals 
                WHERE {where_clause}
                GROUP BY symbol 
                ORDER BY count DESC
            """, params)
            by_symbol = dict(cursor.fetchall())
            
            # Rechazos por categoría
            cursor.execute(f"""
                SELECT rejection_category, COUNT(*) as count 
                FROM rejected_signals 
                WHERE {where_clause}
                GROUP BY rejection_category 
                ORDER BY count DESC
            """, params)
            by_category = dict(cursor.fetchall())
            
            # Rechazos por estrategia
            cursor.execute(f"""
                SELECT strategy, COUNT(*) as count 
                FROM rejected_signals 
                WHERE {where_clause}
                GROUP BY strategy 
                ORDER BY count DESC
            """, params)
            by_strategy = dict(cursor.fetchall())
            
            # Rechazos por hora
            cursor.execute(f"""
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count 
                FROM rejected_signals 
                WHERE {where_clause}
                GROUP BY hour 
                ORDER BY hour
            """, params)
            by_hour = dict(cursor.fetchall())
            
            conn.close()
            
            return {
                'total_rejections': total_rejections,
                'by_symbol': by_symbol,
                'by_category': by_category,
                'by_strategy': by_strategy,
                'by_hour': by_hour,
                'analysis_period_hours': hours_back,
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas de rechazos: {e}")
            return {}
    
    def get_recent_rejections(self, limit: int = 50, symbol: str = None) -> List[Dict]:
        """Obtiene las señales rechazadas más recientes"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            where_clause = "WHERE symbol = ?" if symbol else ""
            params = [symbol] if symbol else []
            
            cursor.execute(f"""
                SELECT timestamp, symbol, strategy, rejection_reason, 
                       rejection_category, signal_data, market_conditions
                FROM rejected_signals 
                {where_clause}
                ORDER BY timestamp DESC 
                LIMIT ?
            """, params + [limit])
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'timestamp': row[0],
                    'symbol': row[1],
                    'strategy': row[2],
                    'rejection_reason': row[3],
                    'rejection_category': row[4],
                    'signal_data': json.loads(row[5]) if row[5] else None,
                    'market_conditions': json.loads(row[6]) if row[6] else None
                })
            
            conn.close()
            return results
            
        except Exception as e:
            logger.error(f"Error obteniendo rechazos recientes: {e}")
            return []
    
    def get_rejection_trends(self, days_back: int = 7) -> Dict:
        """Analiza tendencias de rechazos por día"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = datetime.now(timezone.utc).replace(day=datetime.now(timezone.utc).day - days_back)
            
            cursor.execute("""
                SELECT DATE(timestamp) as date, 
                       COUNT(*) as total_rejections,
                       COUNT(DISTINCT symbol) as symbols_affected
                FROM rejected_signals 
                WHERE timestamp >= ?
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
            """, (cutoff_date.isoformat(),))
            
            daily_trends = []
            for row in cursor.fetchall():
                daily_trends.append({
                    'date': row[0],
                    'total_rejections': row[1],
                    'symbols_affected': row[2]
                })
            
            conn.close()
            
            return {
                'daily_trends': daily_trends,
                'analysis_period_days': days_back,
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analizando tendencias de rechazos: {e}")
            return {}

# Instancia global
rejected_signals_tracker = RejectedSignalsTracker()