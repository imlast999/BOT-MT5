#!/usr/bin/env python3
"""
Script de configuración inicial para el sistema de reglas de trading avanzado
Ejecutar una vez después de instalar el sistema
"""

import os
import json
import sqlite3
from datetime import datetime, timezone

def setup_database():
    """Configura la base de datos con las tablas necesarias"""
    print("🔧 Configurando base de datos...")
    
    db_path = 'bot_state.db'
    conn = sqlite3.connect(db_path)
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
    print("✅ Base de datos configurada")

def create_backup_config():
    """Crea backup de la configuración actual"""
    print("💾 Creando backup de configuración...")
    
    if os.path.exists('rules_config.json'):
        backup_name = f'rules_config_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        os.rename('rules_config.json', backup_name)
        print(f"✅ Backup creado: {backup_name}")

def validate_config():
    """Valida la configuración actual"""
    print("🔍 Validando configuración...")
    
    try:
        with open('rules_config.json', 'r') as f:
            config = json.load(f)
        
        # Verificar símbolos requeridos
        required_symbols = ['EURUSD', 'GLOBAL_SETTINGS']
        for symbol in required_symbols:
            if symbol not in config:
                print(f"⚠️  Advertencia: {symbol} no encontrado en configuración")
        
        # Verificar configuración global
        global_settings = config.get('GLOBAL_SETTINGS', {})
        required_global = ['max_total_risk', 'max_daily_trades_all', 'drawdown_limit']
        for setting in required_global:
            if setting not in global_settings:
                print(f"⚠️  Advertencia: {setting} no encontrado en GLOBAL_SETTINGS")
        
        print("✅ Configuración validada")
        
    except Exception as e:
        print(f"❌ Error validando configuración: {e}")

def setup_environment():
    """Configura variables de entorno adicionales"""
    print("🌍 Configurando variables de entorno...")
    
    env_additions = [
        "# Configuración del sistema de reglas avanzado",
        "ADVANCED_FILTERS=1",
        "CONSERVATIVE_MODE=0",
        "DEFAULT_RISK_PCT=0.5",
        "RISK_SCALING_ENABLED=1",
        ""
    ]
    
    # Leer .env actual
    env_content = []
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            env_content = f.readlines()
    
    # Verificar si ya están las configuraciones
    has_advanced_config = any('ADVANCED_FILTERS' in line for line in env_content)
    
    if not has_advanced_config:
        with open('.env', 'a') as f:
            f.write('\n'.join(env_additions))
        print("✅ Variables de entorno añadidas a .env")
    else:
        print("✅ Variables de entorno ya configuradas")

def create_example_strategies():
    """Crea ejemplos de estrategias personalizadas"""
    print("📝 Creando ejemplos de estrategias...")
    
    example_strategy = '''"""
Ejemplo de estrategia personalizada
Copia este archivo y modifica según tus necesidades
"""

from signals import register_rule
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

@register_rule('mi_estrategia_personalizada')
def mi_estrategia(df: pd.DataFrame, config: dict = None):
    """
    Estrategia personalizada de ejemplo
    
    Combina:
    - EMA 21 y EMA 50 para tendencia
    - RSI para momentum
    - Volumen para confirmación
    """
    cfg = config or {}
    
    # Parámetros configurables
    ema_fast = int(cfg.get('ema_fast', 21))
    ema_slow = int(cfg.get('ema_slow', 50))
    rsi_period = int(cfg.get('rsi_period', 14))
    rsi_oversold = float(cfg.get('rsi_oversold', 30))
    rsi_overbought = float(cfg.get('rsi_overbought', 70))
    
    df = df.copy()
    
    # Calcular indicadores
    df['ema_fast'] = df['close'].ewm(span=ema_fast).mean()
    df['ema_slow'] = df['close'].ewm(span=ema_slow).mean()
    
    # RSI
    delta = df['close'].diff()
    up = delta.clip(lower=0).ewm(alpha=1/rsi_period, adjust=False).mean()
    down = -delta.clip(upper=0).ewm(alpha=1/rsi_period, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Condiciones de entrada
    last = df.iloc[-1]
    price = float(last['close'])
    
    # Señal de compra: EMA rápida > EMA lenta y RSI sobreventa
    if (last['ema_fast'] > last['ema_slow'] and 
        last['rsi'] < rsi_oversold and
        last['rsi'] > 25):  # No demasiado sobreventa
        
        signal = {
            'symbol': df.get('symbol', 'EURUSD'),
            'type': 'BUY',
            'entry': price,
            'sl': price - float(cfg.get('sl_distance', 0.0020)),
            'tp': price + float(cfg.get('tp_distance', 0.0040)),
            'explanation': f'EMA crossover + RSI oversold ({last["rsi"]:.1f})',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 15)))
        }
        return signal, df
    
    # Señal de venta: EMA rápida < EMA lenta y RSI sobrecompra
    if (last['ema_fast'] < last['ema_slow'] and 
        last['rsi'] > rsi_overbought and
        last['rsi'] < 75):  # No demasiado sobrecompra
        
        signal = {
            'symbol': df.get('symbol', 'EURUSD'),
            'type': 'SELL',
            'entry': price,
            'sl': price + float(cfg.get('sl_distance', 0.0020)),
            'tp': price - float(cfg.get('tp_distance', 0.0040)),
            'explanation': f'EMA crossover + RSI overbought ({last["rsi"]:.1f})',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=int(cfg.get('expires_minutes', 15)))
        }
        return signal, df
    
    return None, df
'''
    
    with open('example_custom_strategy.py', 'w') as f:
        f.write(example_strategy)
    
    print("✅ Ejemplo de estrategia creado: example_custom_strategy.py")

def show_next_steps():
    """Muestra los próximos pasos"""
    print("\n🎉 ¡Configuración completada!")
    print("\n📋 Próximos pasos:")
    print("1. Revisa y ajusta rules_config.json según tus preferencias")
    print("2. Configura tu .env con los tokens de Discord y MT5")
    print("3. Ejecuta el bot en modo demo primero: python bot.py")
    print("4. Usa /risk_status para verificar la configuración")
    print("5. Usa /performance para monitorear resultados")
    print("\n📚 Documentación:")
    print("- Lee TRADING_RULES_GUIDE.md para entender el sistema")
    print("- Revisa example_custom_strategy.py para crear tus propias estrategias")
    print("\n⚠️  Importante:")
    print("- Siempre prueba en demo antes de usar dinero real")
    print("- Comienza con riesgo bajo (0.3% por trade)")
    print("- Monitorea el performance regularmente")

def main():
    """Función principal de configuración"""
    print("🚀 Configurando sistema de reglas de trading avanzado...")
    print("=" * 60)
    
    try:
        setup_database()
        create_backup_config()
        validate_config()
        setup_environment()
        create_example_strategies()
        show_next_steps()
        
    except Exception as e:
        print(f"❌ Error durante la configuración: {e}")
        print("Por favor, revisa los errores y ejecuta el script nuevamente")

if __name__ == "__main__":
    main()