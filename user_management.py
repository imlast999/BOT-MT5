"""
Sistema de gestión de usuarios para comercialización del bot
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

class SubscriptionTier(Enum):
    BASIC = "basic"
    PREMIUM = "premium" 
    VIP = "vip"

@dataclass
class UserConfig:
    user_id: int
    subscription: SubscriptionTier
    allowed_pairs: List[str]
    allowed_strategies: List[str]
    max_daily_trades: int
    risk_per_trade: float
    consolidated_filters: bool
    expires_at: datetime
    
class UserManager:
    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self.init_db()
        
    def init_db(self):
        """Inicializar base de datos de usuarios"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                subscription TEXT NOT NULL,
                allowed_pairs TEXT NOT NULL,
                allowed_strategies TEXT NOT NULL,
                max_daily_trades INTEGER NOT NULL,
                risk_per_trade REAL NOT NULL,
                consolidated_filters BOOLEAN NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_active TEXT
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER,
                date TEXT,
                trades_count INTEGER,
                profit_loss REAL,
                win_rate REAL,
                PRIMARY KEY (user_id, date)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_subscription_config(self, tier: SubscriptionTier) -> Dict:
        """Obtener configuración por nivel de suscripción"""
        configs = {
            SubscriptionTier.BASIC: {
                'pairs': ['EURUSD'],
                'strategies': ['ema50_200', 'rsi_divergence'],
                'max_daily_trades': 3,
                'risk_per_trade': 0.5,
                'consolidated_filters': False,
                'price_monthly': 29
            },
            SubscriptionTier.PREMIUM: {
                'pairs': ['EURUSD', 'XAUUSD', 'BTCEUR'],
                'strategies': ['all'],
                'max_daily_trades': 15,
                'risk_per_trade': 0.5,
                'consolidated_filters': True,
                'price_monthly': 79
            },
            SubscriptionTier.VIP: {
                'pairs': ['all'],
                'strategies': ['all'],
                'max_daily_trades': 999,
                'risk_per_trade': 1.0,
                'consolidated_filters': True,
                'price_monthly': 199
            }
        }
        return configs[tier]
    
    def create_user(self, user_id: int, subscription: SubscriptionTier, months: int = 1) -> UserConfig:
        """Crear nuevo usuario con suscripción"""
        config = self.get_subscription_config(subscription)
        expires_at = datetime.now() + timedelta(days=30 * months)
        
        user_config = UserConfig(
            user_id=user_id,
            subscription=subscription,
            allowed_pairs=config['pairs'],
            allowed_strategies=config['strategies'],
            max_daily_trades=config['max_daily_trades'],
            risk_per_trade=config['risk_per_trade'],
            consolidated_filters=config['consolidated_filters'],
            expires_at=expires_at
        )
        
        # Guardar en DB
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, subscription, allowed_pairs, allowed_strategies, 
             max_daily_trades, risk_per_trade, consolidated_filters, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            subscription.value,
            json.dumps(config['pairs']),
            json.dumps(config['strategies']),
            config['max_daily_trades'],
            config['risk_per_trade'],
            config['consolidated_filters'],
            expires_at.isoformat(),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return user_config
    
    def get_user_config(self, user_id: int) -> Optional[UserConfig]:
        """Obtener configuración de usuario"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            return None
            
        return UserConfig(
            user_id=row[0],
            subscription=SubscriptionTier(row[1]),
            allowed_pairs=json.loads(row[2]),
            allowed_strategies=json.loads(row[3]),
            max_daily_trades=row[4],
            risk_per_trade=row[5],
            consolidated_filters=bool(row[6]),
            expires_at=datetime.fromisoformat(row[7])
        )
    
    def is_user_authorized(self, user_id: int, pair: str = None, strategy: str = None) -> bool:
        """Verificar si usuario está autorizado para usar funcionalidad"""
        config = self.get_user_config(user_id)
        
        if not config:
            return False
            
        # Verificar expiración
        if datetime.now() > config.expires_at:
            return False
            
        # Verificar par
        if pair and 'all' not in config.allowed_pairs and pair not in config.allowed_pairs:
            return False
            
        # Verificar estrategia
        if strategy and 'all' not in config.allowed_strategies and strategy not in config.allowed_strategies:
            return False
            
        return True
    
    def get_daily_trades_count(self, user_id: int, date: str = None) -> int:
        """Obtener número de trades del día"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
            
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('SELECT trades_count FROM user_stats WHERE user_id = ? AND date = ?', 
                 (user_id, date))
        row = c.fetchone()
        conn.close()
        
        return row[0] if row else 0
    
    def can_trade_today(self, user_id: int) -> bool:
        """Verificar si usuario puede hacer más trades hoy"""
        config = self.get_user_config(user_id)
        if not config:
            return False
            
        daily_count = self.get_daily_trades_count(user_id)
        return daily_count < config.max_daily_trades

# Instancia global
user_manager = UserManager()

def create_trial_user(user_id: int) -> UserConfig:
    """Crear usuario de prueba (7 días gratis)"""
    return user_manager.create_user(user_id, SubscriptionTier.PREMIUM, months=0.25)  # 7 días

def check_user_access(user_id: int, pair: str = None, strategy: str = None) -> bool:
    """Verificar acceso de usuario (para usar en comandos)"""
    return user_manager.is_user_authorized(user_id, pair, strategy)