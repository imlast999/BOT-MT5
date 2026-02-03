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
        # Esta función contendría toda la lógica de procesamiento de símbolos
        # que actualmente está en _auto_signal_loop
        
        # Por ahora, retornamos False para evitar errores
        # La implementación completa se haría en una segunda fase
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
            session_duration = (datetime.now(timezone.utc) - self.bot.start_time).total_seconds() / 3600
            
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