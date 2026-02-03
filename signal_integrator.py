"""
INTEGRADOR DEL SISTEMA DE SEÑALES SIMPLIFICADO
Conecta las nuevas estrategias simplificadas con el bot existente

🎯 FUNCIONES:
- Integra sistema simplificado con el existente
- Mantiene compatibilidad con bot.py
- Añade logs mejorados y tracking
- Gestiona cooldowns y duplicados
- Proporciona fallback al sistema original
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple, Any
import pandas as pd

# Importar sistemas
from signals_simplified import detect_simplified_signal, get_simplified_strategies_info, log_rejection_details
from signals import detect_signal_advanced, detect_signal  # Sistema original
from duplicate_filter import duplicate_filter
from confidence_system import confidence_system

logger = logging.getLogger(__name__)

class SignalIntegrator:
    """Integrador principal del sistema de señales"""
    
    def __init__(self, config_path: str = 'rules_config_simplified.json'):
        self.config_path = config_path
        self.config = self.load_config()
        self.use_simplified = self.config.get('GLOBAL_SETTINGS', {}).get('simplified_system', True)
        self.daily_counts = {}  # Contador de señales por símbolo
        self.last_reset_date = datetime.now(timezone.utc).date()
        
        logger.info(f"🔧 SignalIntegrator iniciado - Sistema simplificado: {self.use_simplified}")
    
    def load_config(self) -> Dict:
        """Carga la configuración del sistema"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"✅ Configuración cargada desde {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"❌ Error cargando configuración: {e}")
            # Configuración por defecto
            return {
                'GLOBAL_SETTINGS': {
                    'simplified_system': True,
                    'max_total_daily_trades': 12
                },
                'EURUSD': {'max_daily_trades': 4, 'enabled': True},
                'XAUUSD': {'max_daily_trades': 3, 'enabled': True},
                'BTCEUR': {'max_daily_trades': 5, 'enabled': True}
            }
    
    def reset_daily_counts_if_needed(self):
        """Resetea contadores diarios si es un nuevo día"""
        current_date = datetime.now(timezone.utc).date()
        if current_date != self.last_reset_date:
            old_counts = self.daily_counts.copy()
            self.daily_counts = {}
            self.last_reset_date = current_date
            logger.info(f"🔄 Contadores diarios reseteados: {old_counts} → {{}}")
    
    def can_generate_signal(self, symbol: str) -> Tuple[bool, str]:
        """Verifica si se puede generar una señal para el símbolo"""
        self.reset_daily_counts_if_needed()
        
        symbol_config = self.config.get(symbol, {})
        global_config = self.config.get('GLOBAL_SETTINGS', {})
        
        # Verificar si el símbolo está habilitado
        if not symbol_config.get('enabled', True):
            return False, f"{symbol} deshabilitado en configuración"
        
        # Verificar límite por símbolo
        max_daily_symbol = symbol_config.get('max_daily_trades', 5)
        current_count_symbol = self.daily_counts.get(symbol, 0)
        
        if current_count_symbol >= max_daily_symbol:
            return False, f"Límite diario {symbol} alcanzado: {current_count_symbol}/{max_daily_symbol}"
        
        # Verificar límite total
        max_total_daily = global_config.get('max_total_daily_trades', 12)
        total_count = sum(self.daily_counts.values())
        
        if total_count >= max_total_daily:
            return False, f"Límite total diario alcanzado: {total_count}/{max_total_daily}"
        
        return True, "OK"
    
    def increment_signal_count(self, symbol: str):
        """Incrementa el contador de señales para el símbolo"""
        self.daily_counts[symbol] = self.daily_counts.get(symbol, 0) + 1
        total = sum(self.daily_counts.values())
        logger.info(f"📊 Contador actualizado: {symbol} = {self.daily_counts[symbol]}, Total = {total}")
    
    def detect_signal_integrated(self, df: pd.DataFrame, symbol: str, 
                               force_original: bool = False) -> Tuple[Optional[Dict], pd.DataFrame, Dict]:
        """
        Función principal integrada de detección de señales
        
        Args:
            df: DataFrame con datos OHLC
            symbol: Símbolo a analizar
            force_original: Forzar uso del sistema original
        
        Returns:
            (signal_dict or None, df_with_indicators, analysis_info)
        """
        symbol = symbol.upper()
        
        # Verificar si se puede generar señal
        can_generate, reason = self.can_generate_signal(symbol)
        if not can_generate:
            return None, df, {
                'rejected': True,
                'reason': reason,
                'daily_counts': self.daily_counts.copy(),
                'system': 'limit_check'
            }
        
        # Decidir qué sistema usar
        use_simplified = self.use_simplified and not force_original
        
        if use_simplified:
            # Usar sistema simplificado
            signal, df_processed, analysis = self._detect_simplified_with_fallback(df, symbol)
        else:
            # Usar sistema original
            signal, df_processed, analysis = self._detect_original_system(df, symbol)
        
        # Si se generó una señal válida
        if signal and analysis.get('approved', True):
            # Verificar duplicados
            if self._is_duplicate_signal(signal, symbol):
                return None, df_processed, {
                    'rejected': True,
                    'reason': 'Señal duplicada detectada',
                    'original_signal': signal,
                    'system': 'duplicate_filter'
                }
            
            # Incrementar contador
            self.increment_signal_count(symbol)
            
            # Añadir metadata
            signal['system_used'] = 'simplified' if use_simplified else 'original'
            signal['daily_count'] = self.daily_counts.get(symbol, 0)
            signal['total_daily_count'] = sum(self.daily_counts.values())
            
            # Log de éxito
            logger.info(f"🎯 SEÑAL GENERADA: {symbol} {signal['type']} - Sistema: {signal['system_used']}")
            logger.info(f"   Explicación: {signal.get('explanation', 'N/A')}")
            logger.info(f"   Confianza: {signal.get('confidence', 'N/A')}")
            logger.info(f"   R:R: {signal.get('rr_ratio', 'N/A')}")
        
        # Log de rechazo si aplica
        if analysis.get('rejected'):
            log_rejection_details(symbol, analysis)
        
        return signal, df_processed, analysis
    
    def _detect_simplified_with_fallback(self, df: pd.DataFrame, symbol: str) -> Tuple[Optional[Dict], pd.DataFrame, Dict]:
        """Detecta señal con sistema simplificado y fallback al original"""
        try:
            # Intentar sistema simplificado
            signal, df_processed, analysis = detect_simplified_signal(df, symbol, self.config.get(symbol, {}))
            
            if signal:
                analysis['system'] = 'simplified'
                return signal, df_processed, analysis
            
            # Si no hay señal, intentar fallback al sistema original
            logger.debug(f"🔄 {symbol}: Sin señal simplificada, intentando fallback...")
            
            fallback_signal, fallback_df, fallback_analysis = self._detect_original_system(df, symbol)
            
            if fallback_signal:
                # Marcar como fallback
                fallback_signal['system_used'] = 'original_fallback'
                fallback_analysis['system'] = 'original_fallback'
                logger.info(f"🔄 {symbol}: Usando fallback al sistema original")
                return fallback_signal, fallback_df, fallback_analysis
            
            # No hay señal en ningún sistema
            analysis['system'] = 'simplified_no_fallback'
            analysis['fallback_attempted'] = True
            return None, df_processed, analysis
            
        except Exception as e:
            logger.error(f"❌ Error en sistema simplificado para {symbol}: {e}")
            # Fallback de emergencia al sistema original
            return self._detect_original_system(df, symbol)
    
    def _detect_original_system(self, df: pd.DataFrame, symbol: str) -> Tuple[Optional[Dict], pd.DataFrame, Dict]:
        """Detecta señal usando el sistema original"""
        try:
            # Usar detect_signal_advanced si está disponible
            signal, df_processed, analysis = detect_signal_advanced(
                df, strategy='ema50_200', config=None, current_balance=5000.0, symbol=symbol
            )
            
            if signal:
                analysis['system'] = 'original_advanced'
                return signal, df_processed, analysis
            
            # Fallback a detect_signal básico
            basic_signal, basic_df = detect_signal(df, strategy='rsi')
            
            if basic_signal:
                # Crear análisis básico
                analysis = {
                    'approved': True,
                    'system': 'original_basic',
                    'confidence': basic_signal.get('confidence', 'MEDIUM')
                }
                return basic_signal, basic_df, analysis
            
            return None, df, {'rejected': True, 'reason': 'Sin señal en sistema original', 'system': 'original'}
            
        except Exception as e:
            logger.error(f"❌ Error en sistema original para {symbol}: {e}")
            return None, df, {'rejected': True, 'reason': f'Error: {str(e)}', 'system': 'original_error'}
    
    def _is_duplicate_signal(self, signal: Dict, symbol: str) -> bool:
        """Verifica si la señal es duplicada usando el sistema existente"""
        try:
            # Usar el duplicate_filter existente si está disponible
            if hasattr(duplicate_filter, 'is_duplicate'):
                return duplicate_filter.is_duplicate(signal, symbol)
            
            # Implementación básica de detección de duplicados
            # (esto debería integrarse con el sistema existente)
            return False
            
        except Exception as e:
            logger.error(f"Error verificando duplicados: {e}")
            return False
    
    def get_status_report(self) -> Dict:
        """Genera un reporte del estado actual del sistema"""
        self.reset_daily_counts_if_needed()
        
        total_signals = sum(self.daily_counts.values())
        max_total = self.config.get('GLOBAL_SETTINGS', {}).get('max_total_daily_trades', 12)
        
        symbol_status = {}
        for symbol in ['EURUSD', 'XAUUSD', 'BTCEUR']:
            symbol_config = self.config.get(symbol, {})
            current_count = self.daily_counts.get(symbol, 0)
            max_count = symbol_config.get('max_daily_trades', 5)
            
            symbol_status[symbol] = {
                'current': current_count,
                'max': max_count,
                'remaining': max(0, max_count - current_count),
                'enabled': symbol_config.get('enabled', True),
                'percentage_used': (current_count / max_count * 100) if max_count > 0 else 0
            }
        
        return {
            'date': datetime.now(timezone.utc).date().isoformat(),
            'system_type': 'simplified' if self.use_simplified else 'original',
            'total_signals': total_signals,
            'max_total_signals': max_total,
            'remaining_total': max(0, max_total - total_signals),
            'percentage_used': (total_signals / max_total * 100) if max_total > 0 else 0,
            'symbols': symbol_status,
            'config_loaded': bool(self.config),
            'strategies_info': get_simplified_strategies_info() if self.use_simplified else {}
        }
    
    def force_reset_counts(self):
        """Fuerza el reset de contadores (para testing/admin)"""
        old_counts = self.daily_counts.copy()
        self.daily_counts = {}
        logger.warning(f"🔄 RESET FORZADO de contadores: {old_counts} → {{}}")
        return old_counts

# ======================
# FUNCIONES DE INTEGRACIÓN PARA BOT.PY
# ======================

# Instancia global del integrador
_signal_integrator = None

def get_signal_integrator() -> SignalIntegrator:
    """Obtiene la instancia global del integrador"""
    global _signal_integrator
    if _signal_integrator is None:
        _signal_integrator = SignalIntegrator()
    return _signal_integrator

def detect_signal_integrated(df: pd.DataFrame, symbol: str, force_original: bool = False) -> Tuple[Optional[Dict], pd.DataFrame, Dict]:
    """
    Función principal para usar desde bot.py
    Reemplaza las llamadas a detect_signal_advanced
    """
    integrator = get_signal_integrator()
    return integrator.detect_signal_integrated(df, symbol, force_original)

def get_signal_system_status() -> Dict:
    """Obtiene el estado del sistema de señales"""
    integrator = get_signal_integrator()
    return integrator.get_status_report()

def reset_daily_signal_counts():
    """Resetea los contadores diarios (para comandos admin)"""
    integrator = get_signal_integrator()
    return integrator.force_reset_counts()

def can_generate_signal_for_symbol(symbol: str) -> Tuple[bool, str]:
    """Verifica si se puede generar una señal para un símbolo"""
    integrator = get_signal_integrator()
    return integrator.can_generate_signal(symbol)

# ======================
# FUNCIONES DE UTILIDAD
# ======================

def log_signal_performance(signal: Dict, result: str, pnl: float = None):
    """Log del rendimiento de una señal (para tracking futuro)"""
    try:
        performance_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'symbol': signal.get('symbol'),
            'type': signal.get('type'),
            'system': signal.get('system_used'),
            'confidence': signal.get('confidence'),
            'score': signal.get('score'),
            'rr_ratio': signal.get('rr_ratio'),
            'result': result,  # 'win', 'loss', 'pending'
            'pnl': pnl
        }
        
        logger.info(f"📈 PERFORMANCE: {performance_data}")
        
        # Aquí se podría integrar con un sistema de tracking más sofisticado
        
    except Exception as e:
        logger.error(f"Error logging performance: {e}")

def get_simplified_system_info() -> Dict:
    """Información sobre el sistema simplificado"""
    return {
        'version': '2.0',
        'philosophy': 'Sistema de scoring flexible - No AND estricto',
        'improvements': [
            '✅ 1 setup + máximo 2 confirmaciones',
            '✅ Sistema de scoring en vez de AND estricto', 
            '✅ Max trades realistas: 12/día total',
            '✅ R:R mínimo 1.5, preferible 2.0',
            '✅ Estrategias market-logic específicas',
            '✅ Logs detallados de rechazo',
            '✅ Gestión de riesgo normalizada'
        ],
        'strategies': get_simplified_strategies_info(),
        'expected_frequency': '8-12 señales/día total',
        'distribution': {
            'EURUSD': '3-4 señales/día',
            'XAUUSD': '2-3 señales/día',
            'BTCEUR': '3-5 señales/día'
        }
    }