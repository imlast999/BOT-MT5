"""
Servicio de Comandos Discord

Maneja los comandos más complejos de Discord.
Consolidado desde bot.py para reducir el tamaño del archivo principal.
"""

import discord
from discord.ext import commands
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class CommandsService:
    """Servicio para comandos Discord complejos"""
    
    def __init__(self, bot, state, config):
        self.bot = bot
        self.state = state
        self.config = config
    
    async def handle_signal_command(self, ctx, symbol: str = None):
        """Maneja el comando de señal"""
        if ctx.author.id != self.config['AUTHORIZED_USER_ID']:
            await ctx.send("⛔ No autorizado")
            return

        if self.config['KILL_SWITCH']:
            await ctx.send("⛔ Kill switch activado. No se generan señales.")
            return

        # Importar funciones necesarias
        from mt5_client import get_candles
        from signals import _detect_signal_wrapper
        from charts import generate_chart
        
        sym = (symbol or self.config['SYMBOL']).upper()
        try:
            from mt5_client import initialize as mt5_initialize
            mt5_initialize()
            df = get_candles(sym, self.config['TIMEFRAME'], self.config['CANDLES'])
        except Exception as e:
            await ctx.send(f"❌ Error conectando a MT5: {e}")
            return

        signal, df = _detect_signal_wrapper(df, symbol=sym)

        if not signal:
            await ctx.send("❌ No hay señal válida")
            return

        signal_id = max(self.state.pending_signals.keys(), default=0) + 1
        self.state.pending_signals[signal_id] = signal

        try:
            chart_symbol = signal.get('symbol', self.config['SYMBOL'])
            if hasattr(chart_symbol, 'iloc'):
                chart_symbol = str(chart_symbol.iloc[0]) if len(chart_symbol) > 0 else self.config['SYMBOL']
            elif not isinstance(chart_symbol, str):
                chart_symbol = str(chart_symbol)
            
            chart = generate_chart(df, symbol=chart_symbol, signal=signal)
        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
            chart = None

        text = (
            f"🟡 **SEÑAL DETECTADA** (ID {signal_id})\n"
            f"Activo: {signal['symbol']}\n"
            f"Tipo: {signal['type']}\n"
            f"Entrada: {signal['entry']:.5f}\n"
            f"SL: {signal['sl']:.5f}\n"
            f"TP: {signal['tp']:.5f}\n"
            f"⏱ Válida por 1 minuto\n"
            f"Explicación: {signal.get('explanation','-')}\n\n"
            "Comandos:\n"
            f"`/accept {signal_id}`\n"
            f"`/reject {signal_id}`\n"
        )

        if chart:
            await ctx.send(text, file=discord.File(chart))
            try:
                import os
                os.remove(chart)
            except Exception:
                pass
        else:
            await ctx.send(text)
    
    async def handle_accept_command(self, ctx, signal_id: int):
        """Maneja el comando de aceptar señal"""
        if ctx.author.id != self.config['AUTHORIZED_USER_ID']:
            return

        signal = self.state.pending_signals.get(signal_id)
        if not signal:
            await ctx.send("❌ Señal no encontrada")
            return

        if datetime.now(timezone.utc) > signal.get("expires", datetime.now(timezone.utc)):
            await ctx.send("⌛ Señal expirada")
            del self.state.pending_signals[signal_id]
            return

        # Verificar límites
        from bot import reset_period_if_needed, get_period_status
        reset_period_if_needed()
        
        if self.state.trades_today >= self.config['MAX_TRADES_PER_DAY']:
            await ctx.send("⛔ Límite de trades diarios alcanzado")
            del self.state.pending_signals[signal_id]
            return
        
        if self.state.trades_current_period >= self.config['MAX_TRADES_PER_PERIOD']:
            period_status = get_period_status()
            await ctx.send(f"⛔ Límite de período alcanzado ({self.state.trades_current_period}/{self.config['MAX_TRADES_PER_PERIOD']})\n"
                          f"📅 Período actual: {period_status['current_period']} UTC\n"
                          f"⏰ Próximo reinicio: {period_status['time_until_reset'].total_seconds()/3600:.1f}h")
            del self.state.pending_signals[signal_id]
            return

        # Incrementar contadores
        self.state.trades_today += 1
        self.state.trades_current_period += 1
        
        # Guardar en base de datos
        from services.database import save_trades_today
        save_trades_today(self.state.trades_today)

        await ctx.send(f"✅ Señal {signal_id} aceptada (lista para ejecución/manual). Trades hoy: {self.state.trades_today}/{self.config['MAX_TRADES_PER_DAY']}")
        del self.state.pending_signals[signal_id]
    
    async def handle_reject_command(self, ctx, signal_id: int):
        """Maneja el comando de rechazar señal"""
        if ctx.author.id != self.config['AUTHORIZED_USER_ID']:
            return
            
        if signal_id in self.state.pending_signals:
            del self.state.pending_signals[signal_id]
            await ctx.send(f"❌ Señal {signal_id} rechazada")
    
    async def handle_chart_command(self, ctx):
        """Maneja el comando de gráfico"""
        if ctx.author.id != self.config['AUTHORIZED_USER_ID']:
            return
            
        try:
            from mt5_client import initialize as mt5_initialize, get_candles
            from charts import generate_chart
            
            mt5_initialize()
            df = get_candles(self.config['SYMBOL'], self.config['TIMEFRAME'], self.config['CANDLES'])
        except Exception as e:
            await ctx.send(f"❌ Error obteniendo datos: {e}")
            return

        try:
            filename = generate_chart(df)
            await ctx.send("📊 Gráfico actual", file=discord.File(filename))
        except Exception as e:
            await ctx.send(f"❌ Error generando gráfico: {e}")

def create_commands_service(bot, state, config):
    """Factory para crear el servicio de comandos"""
    return CommandsService(bot, state, config)