"""
BTCEUR Strategy - Estrategia SIMPLIFICADA para Bitcoin EUR
"""

import logging
from typing import Dict, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from .base import BaseStrategy

logger = logging.getLogger(__name__)


class BTCEURStrategy(BaseStrategy):
    """
    Estrategia BTCEUR SIMPLIFICADA: Tendencia + Volatilidad
    
    Filosofía: Solo 3 condiciones principales
    - Tendencia clara (EMA20 > EMA50)
    - MACD histogram positivo/negativo
    - ATR mayor que media (volatilidad presente)
    
    Sin confirmaciones múltiples, sin filtros de rango estrictos.
    """
    
    def __init__(self):
        super().__init__("BTCEUR_Simple")
    
    def _get_default_config(self) -> Dict:
        return {
            'ema_fast': 20,
            'ema_slow': 50,
            'ema_trend': 200,              # Filtro tendencia mayor
            'ema_min_separation': 0.005,   # 0.5% mínimo entre EMA20/EMA50
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'atr_period': 14,
            'atr_multiplier': 1.0,
            'sl_atr_multiplier': 2.0,
            'tp_atr_multiplier': 3.0,   # R:R 1.5 — óptimo para BTC (movimientos más cortos)
            'expires_minutes': 90,
            'min_candles': 210           # suficiente para EMA200
        }
    
    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df['ema20']  = self._ema(df['close'], config['ema_fast'])
        df['ema50']  = self._ema(df['close'], config['ema_slow'])
        df['ema200'] = self._ema(df['close'], config['ema_trend'])
        df['macd'], df['macd_signal'], df['macd_hist'] = self._macd(
            df['close'], config['macd_fast'], config['macd_slow'], config['macd_signal']
        )
        return df
    
    def detect_setup(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict]:
        """Detecta setup simple de tendencia + volatilidad"""
        cfg = {**self.default_config, **(config or {})}
        
        logger.debug("[BTCEUR] Using strategy: btceur_new (BTCEURStrategy SIMPLIFIED)")
        
        if not self.validate_data(df) or len(df) < cfg['min_candles']:
            logger.debug("[BTCEUR][REJECT] insufficient_data | len=%d | required=%d", 
                        len(df) if df is not None else 0, cfg['min_candles'])
            return None
        
        df = self.add_indicators(df, cfg)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        price       = float(last['close'])
        ema20       = float(last['ema20'])
        ema50       = float(last['ema50'])
        ema200      = float(last['ema200'])
        macd_hist   = float(last['macd_hist'])
        atr_current = float(last['atr'])
        
        # ── 1. Tendencia EMA20 vs EMA50 ──────────────────────────────────────
        bullish_trend = ema20 > ema50
        bearish_trend = ema20 < ema50
        if not (bullish_trend or bearish_trend):
            return None
        direction = 'BUY' if bullish_trend else 'SELL'
        
        # ── 2. Separación mínima (no lateral) ────────────────────────────────
        ema_separation = abs(ema20 - ema50) / ema50 if ema50 > 0 else 0
        if ema_separation < cfg['ema_min_separation']:
            logger.debug("[BTCEUR][REJECT] ema_too_close | sep=%.4f", ema_separation)
            return None
        
        # ── 3. Filtro EMA200 (tendencia mayor) ───────────────────────────────
        if direction == 'BUY' and price < ema200:
            logger.debug("[BTCEUR][REJECT] price_below_ema200_buy")
            return None
        if direction == 'SELL' and price > ema200:
            logger.debug("[BTCEUR][REJECT] price_above_ema200_sell")
            return None
        
        # ── 4. MACD histogram en dirección correcta ───────────────────────────
        macd_ok = macd_hist > 0 if direction == 'BUY' else macd_hist < 0
        if not macd_ok:
            logger.debug("[BTCEUR][REJECT] macd_wrong_direction | hist=%.2f", macd_hist)
            return None
        
        # ── 5. ATR > media (volatilidad) ──────────────────────────────────────
        atr_mean = df['atr'].tail(30).mean()
        if atr_current <= atr_mean * cfg['atr_multiplier']:
            logger.debug("[BTCEUR][REJECT] low_volatility")
            return None
        
        # ── 6. No entrar con 2 velas consecutivas en contra ──────────────────
        last_bearish = float(last['close']) < float(last['open'])
        prev_bearish = float(prev['close']) < float(prev['open'])
        last_bullish = float(last['close']) > float(last['open'])
        prev_bullish = float(prev['close']) > float(prev['open'])
        if direction == 'BUY' and last_bearish and prev_bearish:
            logger.debug("[BTCEUR][REJECT] two_bearish_candles_on_buy")
            return None
        if direction == 'SELL' and last_bullish and prev_bullish:
            logger.debug("[BTCEUR][REJECT] two_bullish_candles_on_sell")
            return None
        
        # ── NIVELES ───────────────────────────────────────────────────────────
        sl_distance = atr_current * cfg['sl_atr_multiplier']
        tp_distance = atr_current * cfg['tp_atr_multiplier']
        
        if direction == 'BUY':
            sl = price - sl_distance
            tp = price + tp_distance
        else:
            sl = price + sl_distance
            tp = price - tp_distance
        
        # ── FORTALEZA ─────────────────────────────────────────────────────────
        macd_std = df['macd_hist'].tail(20).std()
        momentum_strength = min(1.0, abs(macd_hist) / (macd_std + 0.0001))
        ema_strength      = min(1.0, ema_separation * 50)
        setup_strength    = (momentum_strength * 0.5) + (ema_strength * 0.5)
        
        signal = {
            'type': direction,
            'entry': price,
            'sl': sl,
            'tp': tp,
            'timeframe': 'H1',
            'explanation': f'BTCEUR: {direction} | EMA200✓ | sep={ema_separation:.3f} | MACD={macd_hist:.0f}',
            'expires': datetime.now(timezone.utc) + timedelta(minutes=cfg['expires_minutes']),
            'setup_strength': setup_strength,
            'context': {
                'strategy': 'btceur_new',
                'confirmations': [
                    {'name': 'EMA_TREND',  'passed': True, 'value': ema_separation, 'description': f'sep={ema_separation:.3f}'},
                    {'name': 'EMA200',     'passed': True, 'value': 1.0,            'description': 'Precio lado EMA200'},
                    {'name': 'MACD',       'passed': True, 'value': macd_hist,      'description': f'MACD hist={macd_hist:.0f}'},
                    {'name': 'ATR_OK',     'passed': True, 'value': atr_current/atr_mean, 'description': 'Volatilidad ok'},
                ],
                'market_conditions': {
                    'ema20': ema20, 'ema50': ema50, 'ema200': ema200,
                    'ema_separation': ema_separation,
                    'macd_histogram': macd_hist,
                    'atr_current': atr_current,
                    'atr_mean': atr_mean,
                    'volatility_ratio': atr_current / atr_mean if atr_mean > 0 else 1.0
                },
                'risk_reward': tp_distance / sl_distance if sl_distance > 0 else 0,
                'simple_strategy': True
            }
        }
        
        logger.info("[BTCEUR][SIGNAL] type=%s | price=%.0f | macd=%.0f | sep=%.3f | ema200_ok=True",
                   direction, price, macd_hist, ema_separation)
        return signal


def create_btceur_strategy() -> 'BTCEURStrategy':
    """Factory function para crear estrategia BTCEUR"""
    return BTCEURStrategy()
