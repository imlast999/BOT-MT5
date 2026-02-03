"""
Servicio de Base de Datos

Maneja todas las operaciones de base de datos del bot.
Consolidado desde bot.py para reducir el tamaño del archivo principal.
"""

import sqlite3
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class DatabaseService:
    """Servicio para operaciones de base de datos"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inicializa la base de datos"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS autosignals(state INTEGER)')
        c.execute('CREATE TABLE IF NOT EXISTS last_auto_sent(symbol TEXT PRIMARY KEY, time TEXT, type TEXT, entry REAL, sl REAL, tp REAL)')
        c.execute("CREATE TABLE IF NOT EXISTS trades_counter(date TEXT PRIMARY KEY, count INTEGER)")
        conn.commit()
        conn.close()
    
    def load_state(self, state_obj) -> None:
        """Carga el estado desde la base de datos"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Cargar autosignals state
        c.execute('SELECT state FROM autosignals LIMIT 1')
        r = c.fetchone()
        if r is not None:
            state_obj.autosignals = bool(r[0])
        
        # Cargar trades_today para hoy (UTC)
        today = datetime.now(timezone.utc).date().isoformat()
        c.execute('SELECT count FROM trades_counter WHERE date=?', (today,))
        tr = c.fetchone()
        if tr is not None:
            state_obj.trades_today = int(tr[0])
        else:
            state_obj.trades_today = 0
        
        # Cargar last_auto_sent
        c.execute('SELECT symbol,time,type,entry,sl,tp FROM last_auto_sent')
        rows = c.fetchall()
        for sym, time_s, t, entry, sl, tp in rows:
            try:
                time_dt = datetime.fromisoformat(time_s)
            except Exception:
                time_dt = datetime.now(timezone.utc)
            state_obj.last_auto_sent[sym] = {'time': time_dt, 'sig': (t, entry, sl, tp)}
        
        conn.close()
    
    def save_autosignals_state(self, value: bool) -> None:
        """Guarda el estado de autosignals"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('DELETE FROM autosignals')
        c.execute('INSERT INTO autosignals(state) VALUES(?)', (1 if value else 0,))
        conn.commit()
        conn.close()
    
    def save_last_auto_sent(self, symbol: str, time_dt: datetime, sig_tuple: Tuple) -> None:
        """Guarda la última señal automática enviada"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO last_auto_sent(symbol,time,type,entry,sl,tp) VALUES(?,?,?,?,?,?)',
                  (symbol, time_dt.isoformat(), sig_tuple[0], float(sig_tuple[1]), float(sig_tuple[2]), float(sig_tuple[3])))
        conn.commit()
        conn.close()
    
    def save_trades_today(self, count: int) -> None:
        """Guarda el contador de trades de hoy"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        today = datetime.now(timezone.utc).date().isoformat()
        c.execute('INSERT OR REPLACE INTO trades_counter(date,count) VALUES(?,?)', (today, count))
        conn.commit()
        conn.close()
    
    def reset_trades_today(self) -> None:
        """Resetea el contador de trades de hoy"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        today = datetime.now(timezone.utc).date().isoformat()
        c.execute('INSERT OR REPLACE INTO trades_counter(date,count) VALUES(?,?)', (today, 0))
        conn.commit()
        conn.close()

# Instancia global del servicio de base de datos
_db_service = None

def get_database_service(db_path: str = None) -> DatabaseService:
    """Obtiene la instancia global del servicio de base de datos"""
    global _db_service
    if _db_service is None:
        if db_path is None:
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bot_state.db')
        _db_service = DatabaseService(db_path)
    return _db_service

# Funciones de conveniencia para compatibilidad
def init_db():
    """Función de compatibilidad"""
    get_database_service().init_db()

def load_db_state(state_obj):
    """Función de compatibilidad"""
    get_database_service().load_state(state_obj)

def save_autosignals_state(value: bool):
    """Función de compatibilidad"""
    get_database_service().save_autosignals_state(value)

def save_last_auto_sent(symbol: str, time_dt: datetime, sig_tuple: Tuple):
    """Función de compatibilidad"""
    get_database_service().save_last_auto_sent(symbol, time_dt, sig_tuple)

def save_trades_today(count: int):
    """Función de compatibilidad"""
    get_database_service().save_trades_today(count)

def reset_trades_today():
    """Función de compatibilidad"""
    get_database_service().reset_trades_today()