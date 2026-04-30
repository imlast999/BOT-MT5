"""
Market Replay Engine - Sistema de Backtesting Rápido

Este módulo permite simular miles de velas históricas y ejecutar
las estrategias del bot sobre ellas para validar el comportamiento
sin esperar días de mercado real.

IMPORTANTE: Reutiliza el mismo pipeline de producción:
- Estrategias actuales
- Engine actual
- Scoring actual
- Filtros actuales (excepto duplicados en modo diagnóstico)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd

logger = logging.getLogger(__name__)

@dataclass
class ReplaySignal:
    """Señal detectada durante el replay"""
    timestamp: datetime
    symbol: str
    signal_type: str  # BUY/SELL
    entry: float
    sl: float
    tp: float
    confidence: str
    score: float
    bar_index: int
    
    # Resultado de simulación TP/SL
    result: Optional[str] = None  # WIN/LOSS/PENDING
    exit_price: Optional[float] = None
    exit_bar: Optional[int] = None
    profit_pips: Optional[float] = None

@dataclass
class ReplayStatistics:
    """Estadísticas del replay"""
    bars_analyzed: int = 0
    setups_detected: int = 0
    signals_final: int = 0
    buy_signals: int = 0
    sell_signals: int = 0
    tp_hits: int = 0
    sl_hits: int = 0
    pending: int = 0
    winrate: float = 0.0
    avg_rr: float = 0.0
    total_pips: float = 0.0
    execution_time: float = 0.0

class ReplayEngine:
    """
    Motor de replay que ejecuta estrategias sobre datos históricos
    
    Características:
    - Reutiliza el pipeline completo de producción
    - Simula TP/SL para calcular winrate
    - Genera estadísticas detalladas
    - Modo diagnóstico (sin filtro de duplicados)
    """
    
    def __init__(self, lookback_window: int = 100, max_forward_bars: int = 120):
        """
        Args:
            lookback_window: Número de velas a usar para análisis de indicadores
            max_forward_bars: Máximo de velas a revisar hacia adelante para TP/SL
        """
        self.lookback_window = lookback_window
        self.max_forward_bars = max_forward_bars
        self.signals: List[ReplaySignal] = []
        
    def run_replay(self, symbol: str, bars: int, strategy: str = None,
                   config: Dict = None, skip_duplicate_filter: bool = True,
                   timeframe: str = 'H1') -> ReplayStatistics:
        """
        Ejecuta replay sobre datos históricos
        
        Args:
            symbol: Símbolo a analizar (EURUSD, XAUUSD, BTCEUR)
            bars: Número de velas históricas a analizar
            strategy: Estrategia a usar (None = auto-detectar por símbolo)
            config: Configuración específica (opcional)
            skip_duplicate_filter: Si True, omite filtro de duplicados (recomendado para replay)
            
        Returns:
            ReplayStatistics con resultados completos
        """
        import time
        from mt5_client import get_candles, initialize as mt5_initialize
        import MetaTrader5 as mt5
        from core.engine import get_trading_engine
        
        start_time = time.time()
        
        try:
            # Inicializar MT5
            mt5_initialize()
            
            # Obtener datos históricos (necesitamos lookback + bars)
            total_bars_needed = self.lookback_window + bars
            logger.info(f"Cargando {total_bars_needed} velas para {symbol}...")

            # Mapear timeframe string a constante MT5
            tf_map = {
                'H1': mt5.TIMEFRAME_H1,
                'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1,
                'M15': mt5.TIMEFRAME_M15,
                'M5': mt5.TIMEFRAME_M5,
            }
            mt5_timeframe = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_H1)

            df_full = get_candles(symbol, mt5_timeframe, total_bars_needed)
            
            if df_full is None or len(df_full) < self.lookback_window + 10:
                logger.error(f"Datos insuficientes para {symbol}: {len(df_full) if df_full is not None else 0} velas")
                return ReplayStatistics()
            
            logger.info(f"Datos cargados: {len(df_full)} velas")
            
            # Auto-detectar estrategia si no se especifica
            if strategy is None:
                strategy = self._auto_detect_strategy(symbol)
            
            logger.info(f"Usando estrategia: {strategy}")
            
            # Obtener engine
            engine = get_trading_engine()
            
            # Estadísticas
            stats = ReplayStatistics()
            self.signals = []
            
            # Recorrer velas una a una
            bars_to_analyze = min(bars, len(df_full) - self.lookback_window)
            logger.info(f"Analizando {bars_to_analyze} velas...")
            
            for i in range(self.lookback_window, self.lookback_window + bars_to_analyze):
                # Crear ventana de análisis (últimas lookback_window velas)
                window = df_full.iloc[i - self.lookback_window:i].copy()
                
                # Evaluar señal usando el engine completo (pasar current_index para cooldown)
                result = engine.evaluate_signal(
                    window, 
                    symbol, 
                    strategy, 
                    config,
                    skip_duplicate_filter=skip_duplicate_filter,
                    current_index=i  # Pasar índice para cooldown
                )
                
                stats.bars_analyzed += 1
                
                # Contar setups: cualquier señal detectada (antes de filtros de scoring/confianza)
                # Un setup se detectó si hay raw_signal, independientemente de si pasa scoring
                if result.signal is not None:
                    # Si hay señal final, definitivamente hubo setup
                    stats.setups_detected += 1
                elif result.rejection_reason and result.rejection_reason not in [
                    "No setup básico detectado",
                    "Símbolo desactivado en configuración dinámica"
                ]:
                    # Si fue rechazado por scoring/confianza, también hubo setup
                    stats.setups_detected += 1
                
                # Si hay señal final (pasó scoring y confianza)
                if result.signal and result.should_show:
                    stats.signals_final += 1
                    
                    signal_type = result.signal.get('type', 'BUY')
                    if signal_type == 'BUY':
                        stats.buy_signals += 1
                    else:
                        stats.sell_signals += 1
                    
                    # Crear registro de señal
                    replay_signal = ReplaySignal(
                        timestamp=df_full.iloc[i]['time'] if 'time' in df_full.columns else datetime.now(timezone.utc),
                        symbol=symbol,
                        signal_type=signal_type,
                        entry=float(result.signal.get('entry', 0)),
                        sl=float(result.signal.get('sl', 0)),
                        tp=float(result.signal.get('tp', 0)),
                        confidence=result.confidence,
                        score=result.score,
                        bar_index=i
                    )
                    
                    # Simular TP/SL en velas futuras
                    self._simulate_tp_sl(replay_signal, df_full, i)
                    
                    self.signals.append(replay_signal)
                    
                    # Actualizar estadísticas de resultados
                    if replay_signal.result == 'WIN':
                        stats.tp_hits += 1
                        stats.total_pips += replay_signal.profit_pips or 0
                    elif replay_signal.result == 'LOSS':
                        stats.sl_hits += 1
                        stats.total_pips += replay_signal.profit_pips or 0
                    else:
                        stats.pending += 1
            
            # Calcular métricas finales
            closed_trades = stats.tp_hits + stats.sl_hits
            if closed_trades > 0:
                stats.winrate = (stats.tp_hits / closed_trades) * 100
            
            # Calcular R:R promedio
            if stats.signals_final > 0:
                total_rr = 0
                for sig in self.signals:
                    risk = abs(sig.entry - sig.sl)
                    reward = abs(sig.tp - sig.entry)
                    if risk > 0:
                        total_rr += reward / risk
                stats.avg_rr = total_rr / stats.signals_final
            
            stats.execution_time = time.time() - start_time
            
            logger.info(f"Replay completado: {stats.signals_final} señales en {stats.execution_time:.2f}s")
            
            return stats
            
        except Exception as e:
            logger.error(f"Error en replay: {e}", exc_info=True)
            stats = ReplayStatistics()
            stats.execution_time = time.time() - start_time
            return stats
    
    def _auto_detect_strategy(self, symbol: str) -> str:
        """Auto-detecta estrategia basada en símbolo"""
        symbol_upper = symbol.upper()
        
        if symbol_upper == 'EURUSD':
            return 'eurusd_simple'
        elif symbol_upper == 'XAUUSD':
            return 'xauusd_simple'
        elif symbol_upper in ['BTCEUR', 'BTCUSDT']:
            return 'btceur_simple'
        else:
            return 'ema50_200'
    
    def _get_pip_size(self, symbol: str) -> float:
        """
        Obtiene el tamaño de pip correcto según el símbolo
        
        Args:
            symbol: Símbolo del instrumento
            
        Returns:
            Tamaño de pip para el símbolo
        """
        symbol_upper = symbol.upper()
        
        if symbol_upper == 'EURUSD':
            return 0.0001  # 1 pip = 0.0001
        elif symbol_upper == 'XAUUSD':
            return 0.1  # 1 pip = 0.1 en precio estándar
        elif symbol_upper in ['BTCEUR', 'BTCUSDT']:
            return 1.0  # 1 pip = 1.0
        else:
            # Default para pares Forex
            return 0.0001
    
    def _simulate_tp_sl(self, signal: ReplaySignal, df_full: pd.DataFrame, start_index: int):
        """
        Simula el resultado de una señal avanzando velas hasta TP o SL
        
        Args:
            signal: Señal a simular
            df_full: DataFrame completo con todas las velas
            start_index: Índice de la vela donde se generó la señal
        """
        try:
            # Obtener tamaño de pip correcto para el símbolo
            pip_size = self._get_pip_size(signal.symbol)
            
            # Máximo de velas a revisar hacia adelante
            # H1: 120 velas = ~5 días | H4: 300 velas = ~50 días (swing trading)
            max_forward_bars = self.max_forward_bars
            
            for i in range(start_index + 1, min(start_index + max_forward_bars, len(df_full))):
                bar = df_full.iloc[i]
                high = float(bar['high'])
                low = float(bar['low'])
                
                if signal.signal_type == 'BUY':
                    # Verificar TP (precio sube)
                    if high >= signal.tp:
                        signal.result = 'WIN'
                        signal.exit_price = signal.tp
                        signal.exit_bar = i
                        # Calcular pips correctamente según el símbolo
                        signal.profit_pips = (signal.tp - signal.entry) / pip_size
                        return
                    
                    # Verificar SL (precio baja)
                    if low <= signal.sl:
                        signal.result = 'LOSS'
                        signal.exit_price = signal.sl
                        signal.exit_bar = i
                        # Calcular pips correctamente (negativo para pérdida)
                        signal.profit_pips = (signal.sl - signal.entry) / pip_size
                        return
                
                else:  # SELL
                    # Verificar TP (precio baja)
                    if low <= signal.tp:
                        signal.result = 'WIN'
                        signal.exit_price = signal.tp
                        signal.exit_bar = i
                        # Calcular pips correctamente según el símbolo
                        signal.profit_pips = (signal.entry - signal.tp) / pip_size
                        return
                    
                    # Verificar SL (precio sube)
                    if high >= signal.sl:
                        signal.result = 'LOSS'
                        signal.exit_price = signal.sl
                        signal.exit_bar = i
                        # Calcular pips correctamente (negativo para pérdida)
                        signal.profit_pips = (signal.entry - signal.sl) / pip_size
                        return
            
            # Si llegamos aquí, la señal sigue pendiente
            signal.result = 'PENDING'
            signal.exit_price = None
            signal.exit_bar = None
            signal.profit_pips = 0.0
            
        except Exception as e:
            logger.warning(f"Error simulando TP/SL: {e}")
            signal.result = 'ERROR'
    
    def get_signals(self) -> List[ReplaySignal]:
        """Obtiene lista de señales detectadas durante el replay"""
        return self.signals
    
    def get_detailed_report(self) -> str:
        """Genera reporte detallado en formato texto"""
        if not self.signals:
            return "No hay señales para reportar"
        
        lines = []
        lines.append("=" * 60)
        lines.append("REPORTE DETALLADO DE SEÑALES")
        lines.append("=" * 60)
        lines.append("")
        
        for i, sig in enumerate(self.signals, 1):
            lines.append(f"Señal #{i}")
            lines.append(f"  Timestamp: {sig.timestamp}")
            lines.append(f"  Tipo: {sig.signal_type}")
            lines.append(f"  Entry: {sig.entry:.5f}")
            lines.append(f"  SL: {sig.sl:.5f}")
            lines.append(f"  TP: {sig.tp:.5f}")
            lines.append(f"  Confianza: {sig.confidence} (Score: {sig.score:.2f})")
            lines.append(f"  Resultado: {sig.result or 'PENDING'}")
            if sig.exit_price:
                lines.append(f"  Exit: {sig.exit_price:.5f} (Bar {sig.exit_bar})")
                lines.append(f"  Profit: {sig.profit_pips:.1f} pips")
            lines.append("")
        
        return "\n".join(lines)


# Instancia global del replay engine
_replay_engine = None

def get_replay_engine(lookback_window: int = 100) -> ReplayEngine:
    """Obtiene instancia del replay engine"""
    global _replay_engine
    if _replay_engine is None:
        _replay_engine = ReplayEngine(lookback_window)
    return _replay_engine
