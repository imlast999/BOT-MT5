"""
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
