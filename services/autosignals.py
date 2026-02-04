"""
Servicio de Auto-Señales

Maneja el loop automático de detección y envío de señales.
Consolidado desde bot.py para reducir el tamaño del archivo principal.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import discord

logger = logging.getLogger(__name__)

class AutoSignalsService:
    """Servicio para manejo de señales automáticas"""
    
    def __init__(self, bot, state, config):
        self.bot = bot
        self.state = state
        self.config = config
        self.scan_count = 0
        
    async def find_signals_channel(self) -> Optional[discord.TextChannel]:
        """Encuentra el canal de señales"""
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.name == self.config['SIGNALS_CHANNEL_NAME']:
                    return channel
        return None
    
    async def start_auto_signal_loop(self):
        """Inicia el loop principal de auto-señales"""
        await self.bot.wait_until_ready()
        
        from services.logging import log_event
        log_event(f'Auto-signal loop iniciado (AUTOSIGNALS={self.state.autosignals}, AUTO_EXECUTE={self.config["AUTO_EXECUTE_SIGNALS"]})')
        
        while True:
            try:
                if self.state.autosignals and not self.config['KILL_SWITCH']:
                    await self._scan_symbols()
                
                # Esperar antes del próximo escaneo
                await asyncio.sleep(self.config['AUTOSIGNAL_INTERVAL'])
                
            except Exception as e:
                logger.error(f"Error en auto-signal loop: {e}")
                await asyncio.sleep(30)  # Esperar más tiempo si hay error
    
    async def _scan_symbols(self):
        """Escanea todos los símbolos configurados"""
        from services.logging import log_event
        
        self.scan_count += 1
        if self.scan_count % 10 == 1:  # Log cada 10 escaneos
            log_event(f"Checking {len(self.config['AUTOSIGNAL_SYMBOLS'])} pairs...", "INFO", "AUTOSIGNAL")
        
        channel = await self.find_signals_channel()
        if channel is None:
            if self.scan_count % 50 == 1:  # Log error cada 50 escaneos
                log_event('Canal #signals no encontrado para autosignals', "WARNING")
            return
        
        signals_found = 0
        for symbol in self.config['AUTOSIGNAL_SYMBOLS']:
            try:
                signal_sent = await self._process_symbol(symbol, channel)
                if signal_sent:
                    signals_found += 1
            except Exception as e:
                logger.error(f"Error procesando símbolo {symbol}: {e}")
        
        # Log estadísticas periódicas
        if self.scan_count % 30 == 0:  # Cada 30 escaneos
            await self._log_periodic_stats()
    
    async def _process_symbol(self, symbol: str, channel: discord.TextChannel) -> bool:
        """Procesa un símbolo individual"""
        try:
            from services.logging import log_event
            from core import get_engine
            from strategies import get_strategy
            
            # Obtener estrategia para el símbolo
            strategy = get_strategy(symbol)
            if not strategy:
                if self.scan_count % 100 == 1:  # Log error ocasionalmente
                    log_event(f"No strategy found for {symbol}", "WARNING", "AUTOSIGNAL")
                return False
            
            # Obtener engine de trading
            engine = get_engine()
            if not engine:
                if self.scan_count % 100 == 1:
                    log_event("Trading engine not available", "WARNING", "AUTOSIGNAL")
                return False
            
            # Obtener datos de mercado
            try:
                df = await engine.get_market_data(symbol, timeframe='H1', count=100)
                if df is None or len(df) == 0:
                    return False
            except Exception as e:
                if self.scan_count % 50 == 1:  # Log error ocasionalmente
                    log_event(f"Error getting market data for {symbol}: {e}", "WARNING", "AUTOSIGNAL")
                return False
            
            # Evaluar señal usando la estrategia
            try:
                signal_result = strategy.evaluate_signal(df)
                if not signal_result or not signal_result.get('signal_found'):
                    return False
                
                signal = signal_result['signal']
                confidence = signal_result.get('confidence', 'MEDIUM')
                score = signal_result.get('score', 0.0)
                
            except Exception as e:
                if self.scan_count % 50 == 1:
                    log_event(f"Error evaluating signal for {symbol}: {e}", "WARNING", "AUTOSIGNAL")
                return False
            
            # Aplicar filtros
            try:
                from core import get_filters_system
                filters_system = get_filters_system()
                
                passed, reason, details = filters_system.apply_all_filters(df, signal)
                if not passed:
                    # Log rechazo ocasionalmente para debugging
                    if self.scan_count % 20 == 1:
                        log_event(f"{symbol} signal rejected: {reason}", "INFO", "AUTOSIGNAL")
                    return False
                
            except Exception as e:
                log_event(f"Error applying filters for {symbol}: {e}", "WARNING", "AUTOSIGNAL")
                return False
            
            # Señal aprobada - enviar al canal
            try:
                # Formatear mensaje de señal
                signal_type = signal.get('type', 'BUY').upper()
                entry = signal.get('entry', 0)
                sl = signal.get('sl', 0)
                tp = signal.get('tp', 0)
                
                # Crear embed de señal
                embed = discord.Embed(
                    title=f"🎯 {signal_type} {symbol}",
                    color=0x00ff00 if signal_type == 'BUY' else 0xff0000,
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(name="📈 Entry", value=f"{entry:.5f}", inline=True)
                embed.add_field(name="🛡️ Stop Loss", value=f"{sl:.5f}", inline=True)
                embed.add_field(name="🎯 Take Profit", value=f"{tp:.5f}", inline=True)
                embed.add_field(name="⭐ Confidence", value=confidence, inline=True)
                embed.add_field(name="📊 Score", value=f"{score:.2f}", inline=True)
                embed.add_field(name="🤖 Strategy", value=strategy.__class__.__name__, inline=True)
                
                # Calcular R:R ratio
                risk = abs(entry - sl)
                reward = abs(tp - entry)
                rr_ratio = reward / risk if risk > 0 else 0
                embed.add_field(name="⚖️ R:R Ratio", value=f"1:{rr_ratio:.2f}", inline=True)
                
                embed.set_footer(text="Auto-Signal System")
                
                # Enviar señal
                await channel.send(embed=embed)
                
                # Log señal enviada
                log_event(
                    f"🎯 AUTO-SIGNAL: {signal_type} {symbol} @ {entry:.5f} "
                    f"(SL: {sl:.5f}, TP: {tp:.5f}, Conf: {confidence})",
                    "INFO", "AUTOSIGNAL"
                )
                
                # Actualizar contadores de filtros
                filters_system.increment_trade_counters(symbol)
                
                # Actualizar dashboard si está disponible
                try:
                    from services.dashboard import get_dashboard_service
                    dashboard = get_dashboard_service()
                    dashboard.add_signal_event(
                        symbol=symbol,
                        strategy=strategy.__class__.__name__,
                        signal_type=signal_type,
                        confidence=confidence,
                        score=score,
                        shown=True,
                        executed=False  # Por ahora no ejecutamos automáticamente
                    )
                except Exception as e:
                    # Dashboard no crítico, continuar
                    pass
                
                return True
                
            except Exception as e:
                log_event(f"Error sending signal for {symbol}: {e}", "ERROR", "AUTOSIGNAL")
                return False
                
        except Exception as e:
            log_event(f"Unexpected error processing {symbol}: {e}", "ERROR", "AUTOSIGNAL")
            return False
    
    async def _log_periodic_stats(self):
        """Log de estadísticas periódicas"""
        from services.logging import log_event
        from core import get_filters_system
        
        try:
            # Obtener estadísticas del filtro de duplicados
            filters_system = get_filters_system()
            filter_stats = filters_system.get_stats()
            
            # Calcular tiempo de sesión
            # Use intelligent logger's start time instead of bot.start_time
            from services.logging import get_intelligent_logger
            logger_instance = get_intelligent_logger()
            session_start = getattr(logger_instance, 'last_dump', datetime.now(timezone.utc))
            session_duration = (datetime.now(timezone.utc) - session_start).total_seconds() / 3600
            
            log_event(
                f"📊 STATS: {filter_stats.get('total_signals', 0)} señales evaluadas, "
                f"{filter_stats.get('shown_signals', 0)} mostradas, "
                f"sesión: {session_duration:.1f}h",
                "INFO", "AUTOSIGNAL"
            )
            
        except Exception as e:
            logger.error(f"Error en estadísticas periódicas: {e}")

def create_autosignals_service(bot, state, config):
    """Factory para crear el servicio de auto-señales"""
    return AutoSignalsService(bot, state, config)