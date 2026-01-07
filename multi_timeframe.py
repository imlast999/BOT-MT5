"""
Sistema de análisis multi-timeframe para entradas más precisas
H1 para señal principal, M15 para entrada exacta
"""

import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class MultiTimeframeAnalyzer:
    """Analizador de múltiples timeframes para entradas precisas"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        
    def get_precise_entry(self, symbol: str, h1_signal: dict) -> Tuple[Optional[dict], str]:
        """
        Obtiene entrada precisa usando M15 basado en señal H1
        Retorna: (precise_signal, reason)
        """
        try:
            # Obtener datos M15
            m15_data = self.get_m15_data(symbol)
            if m15_data is None or len(m15_data) < 50:
                return None, "Datos M15 insuficientes"
            
            # Calcular indicadores M15
            m15_with_indicators = self.calculate_m15_indicators(m15_data)
            
            # Buscar entrada precisa
            precise_entry = self.find_precise_entry_point(m15_with_indicators, h1_signal)
            
            if precise_entry:
                return precise_entry, "Entrada precisa encontrada en M15"
            else:
                return None, "No se encontró entrada precisa en M15"
                
        except Exception as e:
            logger.exception(f"Error en get_precise_entry: {e}")
            return None, f"Error: {e}"
    
    def get_m15_data(self, symbol: str, candles: int = 100) -> Optional[pd.DataFrame]:
        """Obtiene datos M15 del símbolo"""
        try:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, candles)
            if rates is None or len(rates) == 0:
                return None
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df
            
        except Exception as e:
            logger.exception(f"Error obteniendo datos M15 para {symbol}: {e}")
            return None
    
    def calculate_m15_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula indicadores técnicos para M15"""
        try:
            df = df.copy()
            
            # EMAs rápidas para M15
            df['ema8'] = df['close'].ewm(span=8).mean()
            df['ema21'] = df['close'].ewm(span=21).mean()
            df['ema50'] = df['close'].ewm(span=50).mean()
            
            # RSI
            delta = df['close'].diff()
            up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
            down = -delta.clip(upper=0).ewm(alpha=1/14, adjust=False).mean()
            rs = up / down.replace(0, np.nan)
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # MACD rápido
            ema12 = df['close'].ewm(span=12).mean()
            ema26 = df['close'].ewm(span=26).mean()
            df['macd'] = ema12 - ema26
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_hist'] = df['macd'] - df['macd_signal']
            
            # Bollinger Bands
            df['bb_middle'] = df['close'].rolling(20).mean()
            bb_std = df['close'].rolling(20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
            
            # ATR para volatilidad
            df['atr'] = (df['high'] - df['low']).rolling(14).mean()
            
            return df
            
        except Exception as e:
            logger.exception(f"Error calculando indicadores M15: {e}")
            return df
    
    def find_precise_entry_point(self, df: pd.DataFrame, h1_signal: dict) -> Optional[dict]:
        """Encuentra punto de entrada preciso en M15"""
        try:
            if len(df) < 10:
                return None
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            signal_type = h1_signal['type']
            symbol = h1_signal['symbol']
            
            # Precio actual
            current_price = float(last['close'])
            
            # Verificar confluencias M15
            confluences = self.check_m15_confluences(df, signal_type)
            
            if confluences['score'] < 3:  # Mínimo 3 confluencias
                return None
            
            # Calcular SL y TP más precisos
            precise_sl, precise_tp = self.calculate_precise_levels(df, signal_type, current_price)
            
            # Crear señal precisa
            precise_signal = {
                'symbol': symbol,
                'type': signal_type,
                'entry': current_price,
                'sl': precise_sl,
                'tp': precise_tp,
                'timeframe': 'M15',
                'explanation': f"Entrada precisa M15: {confluences['reasons']}",
                'confidence': 'HIGH' if confluences['score'] >= 4 else 'MEDIUM',
                'strategy': f"{h1_signal.get('strategy', 'unknown')}_m15",
                'h1_signal_id': h1_signal.get('id'),
                'confluences': confluences,
                'expires': datetime.now(timezone.utc) + timedelta(minutes=15)
            }
            
            return precise_signal
            
        except Exception as e:
            logger.exception(f"Error encontrando entrada precisa: {e}")
            return None
    
    def check_m15_confluences(self, df: pd.DataFrame, signal_type: str) -> Dict:
        """Verifica confluencias en M15"""
        try:
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            confluences = {
                'score': 0,
                'reasons': [],
                'details': {}
            }
            
            # 1. Confluencia EMA
            if signal_type == 'BUY':
                if last['ema8'] > last['ema21'] > last['ema50']:
                    confluences['score'] += 1
                    confluences['reasons'].append("EMAs alcistas")
            else:
                if last['ema8'] < last['ema21'] < last['ema50']:
                    confluences['score'] += 1
                    confluences['reasons'].append("EMAs bajistas")
            
            # 2. Confluencia RSI
            rsi = last['rsi']
            if signal_type == 'BUY' and 40 <= rsi <= 65:
                confluences['score'] += 1
                confluences['reasons'].append(f"RSI favorable ({rsi:.1f})")
            elif signal_type == 'SELL' and 35 <= rsi <= 60:
                confluences['score'] += 1
                confluences['reasons'].append(f"RSI favorable ({rsi:.1f})")
            
            # 3. Confluencia MACD
            if signal_type == 'BUY' and last['macd_hist'] > 0 and last['macd_hist'] > prev['macd_hist']:
                confluences['score'] += 1
                confluences['reasons'].append("MACD alcista")
            elif signal_type == 'SELL' and last['macd_hist'] < 0 and last['macd_hist'] < prev['macd_hist']:
                confluences['score'] += 1
                confluences['reasons'].append("MACD bajista")
            
            # 4. Confluencia de vela
            candle_body = abs(last['close'] - last['open'])
            candle_range = last['high'] - last['low']
            body_ratio = candle_body / candle_range if candle_range > 0 else 0
            
            if body_ratio > 0.6:  # Vela fuerte
                if (signal_type == 'BUY' and last['close'] > last['open']) or \
                   (signal_type == 'SELL' and last['close'] < last['open']):
                    confluences['score'] += 1
                    confluences['reasons'].append("Vela fuerte")
            
            # 5. Confluencia Bollinger Bands
            if signal_type == 'BUY' and last['close'] > last['bb_middle']:
                confluences['score'] += 1
                confluences['reasons'].append("Por encima BB middle")
            elif signal_type == 'SELL' and last['close'] < last['bb_middle']:
                confluences['score'] += 1
                confluences['reasons'].append("Por debajo BB middle")
            
            # 6. Confluencia de momentum (precio vs EMAs)
            if signal_type == 'BUY' and last['close'] > last['ema8']:
                confluences['score'] += 1
                confluences['reasons'].append("Momentum alcista")
            elif signal_type == 'SELL' and last['close'] < last['ema8']:
                confluences['score'] += 1
                confluences['reasons'].append("Momentum bajista")
            
            confluences['details'] = {
                'rsi': rsi,
                'macd_hist': last['macd_hist'],
                'body_ratio': body_ratio,
                'bb_position': 'above' if last['close'] > last['bb_middle'] else 'below'
            }
            
            return confluences
            
        except Exception as e:
            logger.exception(f"Error verificando confluencias M15: {e}")
            return {'score': 0, 'reasons': [], 'details': {}}
    
    def calculate_precise_levels(self, df: pd.DataFrame, signal_type: str, entry_price: float) -> Tuple[float, float]:
        """Calcula SL y TP más precisos basados en M15"""
        try:
            last = df.iloc[-1]
            atr = last['atr']
            
            # SL más ajustado basado en estructura M15
            if signal_type == 'BUY':
                # SL debajo del mínimo reciente o EMA21
                recent_low = df['low'].rolling(10).min().iloc[-1]
                ema21_level = last['ema21']
                sl_level = min(recent_low, ema21_level)
                
                # Asegurar distancia mínima
                min_sl_distance = atr * 0.5
                sl = min(sl_level, entry_price - min_sl_distance)
                
                # TP basado en R:R y resistencias
                sl_distance = entry_price - sl
                tp = entry_price + (sl_distance * 2.5)  # R:R 1:2.5
                
            else:  # SELL
                # SL encima del máximo reciente o EMA21
                recent_high = df['high'].rolling(10).max().iloc[-1]
                ema21_level = last['ema21']
                sl_level = max(recent_high, ema21_level)
                
                # Asegurar distancia mínima
                min_sl_distance = atr * 0.5
                sl = max(sl_level, entry_price + min_sl_distance)
                
                # TP basado en R:R y soportes
                sl_distance = sl - entry_price
                tp = entry_price - (sl_distance * 2.5)  # R:R 1:2.5
            
            return sl, tp
            
        except Exception as e:
            logger.exception(f"Error calculando niveles precisos: {e}")
            # Fallback a niveles básicos
            atr_fallback = 0.0020  # Fallback ATR
            if signal_type == 'BUY':
                return entry_price - atr_fallback, entry_price + (atr_fallback * 2)
            else:
                return entry_price + atr_fallback, entry_price - (atr_fallback * 2)
    
    def validate_m15_entry(self, symbol: str, signal_type: str) -> Tuple[bool, str]:
        """Valida si es buen momento para entrar basado en M15"""
        try:
            df = self.get_m15_data(symbol, 50)
            if df is None:
                return False, "No hay datos M15"
            
            df = self.calculate_m15_indicators(df)
            last = df.iloc[-1]
            
            # Verificar que no estemos en extremos
            rsi = last['rsi']
            if signal_type == 'BUY' and rsi > 75:
                return False, f"RSI muy alto en M15: {rsi:.1f}"
            elif signal_type == 'SELL' and rsi < 25:
                return False, f"RSI muy bajo en M15: {rsi:.1f}"
            
            # Verificar que tengamos momentum
            if 'macd_hist' in df.columns:
                macd_hist = last['macd_hist']
                if signal_type == 'BUY' and macd_hist < 0:
                    return False, "MACD negativo en M15"
                elif signal_type == 'SELL' and macd_hist > 0:
                    return False, "MACD positivo en M15"
            
            return True, "M15 favorable para entrada"
            
        except Exception as e:
            logger.exception(f"Error validando entrada M15: {e}")
            return True, f"Error validando M15: {e}"  # Permitir por defecto


def create_multi_timeframe_analyzer(config: dict = None) -> MultiTimeframeAnalyzer:
    """Factory function para crear el analizador multi-timeframe"""
    return MultiTimeframeAnalyzer(config)