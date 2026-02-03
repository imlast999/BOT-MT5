"""
Sistema de Resumen de Sesión Automático
Genera resúmenes automáticos de la sesión de trading con métricas detalladas
"""

import sqlite3
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class SessionSummarySystem:
    """Sistema para generar resúmenes automáticos de sesión"""
    
    def __init__(self, db_path: str = "bot_state.db"):
        self.db_path = db_path
        self.session_start = datetime.now(timezone.utc)
        self.session_id = self.session_start.strftime('%Y%m%d_%H%M%S')
        self.symbols = ['EURUSD', 'XAUUSD', 'BTCEUR']
        self.confidence_levels = ['LOW', 'MEDIUM', 'MEDIUM-HIGH', 'HIGH']
        
        # Contadores de sesión
        self.session_stats = {
            'signals_generated': 0,
            'signals_shown': 0,
            'signals_executed': 0,
            'duplicates_filtered': 0,
            'by_symbol': {symbol: {'total': 0, 'shown': 0, 'executed': 0, 'filtered': 0} for symbol in self.symbols},
            'by_confidence': {level: 0 for level in self.confidence_levels},
            'trades_won': 0,
            'trades_lost': 0,
            'total_pnl': 0.0
        }
    
    def log_session_event(self, message: str, level: str = "INFO"):
        """Log personalizado para eventos de sesión"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        console_msg = f"[{timestamp}] 📊 SESSION: {message}"
        print(console_msg)
        
        if level.upper() == "ERROR":
            logger.error(f"SESSION: {message}")
        elif level.upper() == "WARNING":
            logger.warning(f"SESSION: {message}")
        else:
            logger.info(f"SESSION: {message}")
    
    def update_signal_stats(self, symbol: str, confidence: str, shown: bool = False, executed: bool = False, filtered: bool = False):
        """Actualizar estadísticas de señales en tiempo real"""
        try:
            # Estadísticas globales
            self.session_stats['signals_generated'] += 1
            
            if shown:
                self.session_stats['signals_shown'] += 1
            if executed:
                self.session_stats['signals_executed'] += 1
            if filtered:
                self.session_stats['duplicates_filtered'] += 1
            
            # Por símbolo
            if symbol in self.session_stats['by_symbol']:
                self.session_stats['by_symbol'][symbol]['total'] += 1
                if shown:
                    self.session_stats['by_symbol'][symbol]['shown'] += 1
                if executed:
                    self.session_stats['by_symbol'][symbol]['executed'] += 1
                if filtered:
                    self.session_stats['by_symbol'][symbol]['filtered'] += 1
            
            # Por confianza
            if confidence in self.session_stats['by_confidence']:
                self.session_stats['by_confidence'][confidence] += 1
                
        except Exception as e:
            logger.error(f"Error updating signal stats: {e}")
    
    def update_trade_result(self, symbol: str, pnl: float, won: bool):
        """Actualizar resultado de trade"""
        try:
            if won:
                self.session_stats['trades_won'] += 1
            else:
                self.session_stats['trades_lost'] += 1
            
            self.session_stats['total_pnl'] += pnl
            
        except Exception as e:
            logger.error(f"Error updating trade result: {e}")
    
    def get_session_duration(self) -> timedelta:
        """Obtener duración de la sesión actual"""
        return datetime.now(timezone.utc) - self.session_start
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas de la base de datos"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Estadísticas de señales desde el inicio de la sesión
            session_start_str = self.session_start.isoformat()
            
            # Señales por símbolo desde el inicio de sesión
            c.execute('''
                SELECT symbol, confidence_level, status, executed, rejected, COUNT(*) as count
                FROM enhanced_signals 
                WHERE created_at >= ?
                GROUP BY symbol, confidence_level, status, executed, rejected
            ''', (session_start_str,))
            
            db_stats = {
                'total_signals': 0,
                'by_symbol': {symbol: {'total': 0, 'high': 0, 'medium_high': 0, 'executed': 0} for symbol in self.symbols},
                'by_confidence': {level: 0 for level in self.confidence_levels},
                'executed_count': 0,
                'rejected_count': 0
            }
            
            for row in c.fetchall():
                symbol, confidence, status, executed, rejected, count = row
                
                db_stats['total_signals'] += count
                
                if symbol in db_stats['by_symbol']:
                    db_stats['by_symbol'][symbol]['total'] += count
                    if confidence == 'HIGH':
                        db_stats['by_symbol'][symbol]['high'] += count
                    elif confidence == 'MEDIUM-HIGH':
                        db_stats['by_symbol'][symbol]['medium_high'] += count
                    if executed:
                        db_stats['by_symbol'][symbol]['executed'] += count
                
                if confidence in db_stats['by_confidence']:
                    db_stats['by_confidence'][confidence] += count
                
                if executed:
                    db_stats['executed_count'] += count
                if rejected:
                    db_stats['rejected_count'] += count
            
            conn.close()
            return db_stats
            
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {}
    
    def generate_session_summary(self, include_db_stats: bool = True) -> str:
        """Generar resumen completo de la sesión"""
        try:
            duration = self.get_session_duration()
            hours = duration.total_seconds() / 3600
            
            # Obtener estadísticas de la base de datos si está disponible
            db_stats = self.get_database_stats() if include_db_stats else {}
            
            # Usar estadísticas de DB si están disponibles, sino usar contadores internos
            total_signals = db_stats.get('total_signals', self.session_stats['signals_generated'])
            
            summary = f"""
╔══════════════════════════════════════════════════════════════╗
║                    📊 RESUMEN DE SESIÓN                      ║
╠══════════════════════════════════════════════════════════════╣
║ 🕐 Sesión: {self.session_id}                                 
║ ⏱️  Duración: {hours:.1f} horas ({duration.total_seconds()/60:.0f} minutos)
║ 📅 Inicio: {self.session_start.strftime('%Y-%m-%d %H:%M:%S UTC')}
║ 📅 Fin: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
╠══════════════════════════════════════════════════════════════╣
║                        🎯 SEÑALES                            ║
╠══════════════════════════════════════════════════════════════╣
║ 📊 Total Generadas: {total_signals:>3}                                    
║ 👁️  Mostradas (MH+H): {db_stats.get('by_confidence', {}).get('MEDIUM-HIGH', 0) + db_stats.get('by_confidence', {}).get('HIGH', 0):>3}                                  
║ ⚡ Ejecutadas: {db_stats.get('executed_count', self.session_stats['signals_executed']):>3}                                        
║ 🔄 Duplicados Filtrados: {self.session_stats['duplicates_filtered']:>3}                       
╠══════════════════════════════════════════════════════════════╣
║                    📈 POR SÍMBOLO                            ║
╠══════════════════════════════════════════════════════════════╣"""
            
            # Estadísticas por símbolo
            for symbol in self.symbols:
                if include_db_stats and symbol in db_stats['by_symbol']:
                    symbol_data = db_stats['by_symbol'][symbol]
                    total = symbol_data['total']
                    high = symbol_data['high']
                    medium_high = symbol_data['medium_high']
                    executed = symbol_data['executed']
                else:
                    symbol_data = self.session_stats['by_symbol'][symbol]
                    total = symbol_data['total']
                    high = 0  # No disponible en contadores internos
                    medium_high = 0
                    executed = symbol_data['executed']
                
                quality_signals = high + medium_high
                quality_rate = (quality_signals / total * 100) if total > 0 else 0
                
                summary += f"""
║ 🔸 {symbol:<8} Total: {total:>3} | Calidad: {quality_signals:>2} ({quality_rate:>4.1f}%) | Ejecutadas: {executed:>2}"""
            
            # Distribución por confianza
            summary += f"""
╠══════════════════════════════════════════════════════════════╣
║                  🧠 DISTRIBUCIÓN CONFIANZA                   ║
╠══════════════════════════════════════════════════════════════╣"""
            
            for level in ['HIGH', 'MEDIUM-HIGH', 'MEDIUM', 'LOW']:
                if include_db_stats:
                    count = db_stats.get('by_confidence', {}).get(level, 0)
                else:
                    count = self.session_stats['by_confidence'][level]
                
                percentage = (count / total_signals * 100) if total_signals > 0 else 0
                
                # Emojis por nivel
                emoji = {'HIGH': '🎯', 'MEDIUM-HIGH': '⚡', 'MEDIUM': '📈', 'LOW': '📉'}[level]
                
                summary += f"""
║ {emoji} {level:<11} {count:>3} señales ({percentage:>5.1f}%)"""
            
            # Estadísticas de trading
            total_trades = self.session_stats['trades_won'] + self.session_stats['trades_lost']
            win_rate = (self.session_stats['trades_won'] / total_trades * 100) if total_trades > 0 else 0
            
            summary += f"""
╠══════════════════════════════════════════════════════════════╣
║                      💰 TRADING                              ║
╠══════════════════════════════════════════════════════════════╣
║ 📊 Trades Totales: {total_trades:>3}                                      
║ ✅ Ganadores: {self.session_stats['trades_won']:>3} | ❌ Perdedores: {self.session_stats['trades_lost']:>3}                    
║ 📈 Win Rate: {win_rate:>5.1f}%                                        
║ 💵 P&L Total: {self.session_stats['total_pnl']:>+7.2f} EUR                              
╠══════════════════════════════════════════════════════════════╣
║                     ⚙️ RENDIMIENTO                           ║
╠══════════════════════════════════════════════════════════════╣
║ 🔄 Señales/Hora: {(total_signals / hours):>5.1f}                                   
║ ⚡ Ejecución Rate: {(db_stats.get('executed_count', 0) / total_signals * 100) if total_signals > 0 else 0:>4.1f}%                                
║ 🎯 Calidad Rate: {((db_stats.get('by_confidence', {}).get('MEDIUM-HIGH', 0) + db_stats.get('by_confidence', {}).get('HIGH', 0)) / total_signals * 100) if total_signals > 0 else 0:>4.1f}%                                 
╚══════════════════════════════════════════════════════════════╝
            """
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Error generating session summary: {e}")
            return f"❌ Error generando resumen de sesión: {e}"
    
    def log_session_summary(self):
        """Loggear resumen de sesión"""
        try:
            summary = self.generate_session_summary()
            self.log_session_event("Generando resumen de sesión...")
            
            # Log línea por línea para mejor formato
            for line in summary.split('\n'):
                if line.strip():
                    print(line)
            
            self.log_session_event("Resumen de sesión completado")
            
        except Exception as e:
            self.log_session_event(f"Error logging session summary: {e}", "ERROR")
    
    def save_session_summary(self, filepath: Optional[str] = None):
        """Guardar resumen de sesión en archivo"""
        try:
            if filepath is None:
                filepath = f"session_summary_{self.session_id}.txt"
            
            summary = self.generate_session_summary()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(summary)
            
            self.log_session_event(f"Resumen guardado en: {filepath}")
            return filepath
            
        except Exception as e:
            self.log_session_event(f"Error saving session summary: {e}", "ERROR")
            return None

# Instancia global
session_summary = SessionSummarySystem()