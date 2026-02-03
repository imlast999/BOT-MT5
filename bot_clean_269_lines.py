"""
Bot MT5 - Versión Limpia y Refactorizada

Este archivo contiene SOLO la orquestación principal del bot.
Toda la lógica compleja se ha movido a módulos especializados:
- core/ (engine, scoring, filters, risk)
- services/ (logging, execution, dashboard, database, commands, autosignals)
- strategies/ (eurusd, xauusd, btceur)
"""

import os
import logging
import asyncio

# Parche para compatibilidad con Python 3.13
import audioop_patch

# Configurar matplotlib para evitar problemas de threading
import matplotlib
matplotlib.use('Agg')

import discord
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timezone

# ============================================================================
# IMPORTS CONSOLIDADOS - ARQUITECTURA LIMPIA
# ============================================================================

# Core system
from core import BotState, get_current_period_start

# Services
from services import (
    log_event, log_signal_evaluation, log_command,
    start_enhanced_dashboard, stop_enhanced_dashboard,
    load_db_state, save_autosignals_state,
    create_commands_service, create_autosignals_service
)

# Signals dispatcher
from signals import _detect_signal_wrapper

# Módulos específicos mantenidos
from mt5_client import initialize as mt5_initialize
import MetaTrader5 as mt5

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Configurar logging básico
logging.basicConfig(
    level=logging.WARNING,
    format='{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}'
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
AUTHORIZED_USER_ID = int(os.getenv('AUTHORIZED_USER_ID', '739198540177473667'))
SIGNALS_CHANNEL_NAME = "signals"
TIMEFRAME = mt5.TIMEFRAME_H1
SYMBOL = "EURUSD"
CANDLES = 100

# Límites de seguridad
MAX_TRADES_PER_DAY = int(os.getenv('MAX_TRADES_PER_DAY', '3'))
MAX_TRADES_PER_PERIOD = int(os.getenv('MAX_TRADES_PER_PERIOD', '5'))
KILL_SWITCH = os.getenv('KILL_SWITCH', '0') == '1'

# Auto-ejecución
AUTO_EXECUTE_SIGNALS = os.getenv('AUTO_EXECUTE_SIGNALS', '0') == '1'
AUTO_EXECUTE_CONFIDENCE = os.getenv('AUTO_EXECUTE_CONFIDENCE', 'HIGH')

# Auto-señales
AUTOSIGNAL_INTERVAL = int(os.getenv('AUTOSIGNAL_INTERVAL', '20'))
AUTOSIGNAL_SYMBOLS = [s.strip().upper() for s in os.getenv('AUTOSIGNAL_SYMBOLS', SYMBOL).split(',') if s.strip()]

# ============================================================================
# ESTADO GLOBAL Y CONFIGURACIÓN
# ============================================================================

# Estado del bot usando el core system
state = BotState()

# Configuración para servicios
config = {
    'AUTHORIZED_USER_ID': AUTHORIZED_USER_ID,
    'SIGNALS_CHANNEL_NAME': SIGNALS_CHANNEL_NAME,
    'TIMEFRAME': TIMEFRAME,
    'SYMBOL': SYMBOL,
    'CANDLES': CANDLES,
    'MAX_TRADES_PER_DAY': MAX_TRADES_PER_DAY,
    'MAX_TRADES_PER_PERIOD': MAX_TRADES_PER_PERIOD,
    'KILL_SWITCH': KILL_SWITCH,
    'AUTO_EXECUTE_SIGNALS': AUTO_EXECUTE_SIGNALS,
    'AUTO_EXECUTE_CONFIDENCE': AUTO_EXECUTE_CONFIDENCE,
    'AUTOSIGNAL_INTERVAL': AUTOSIGNAL_INTERVAL,
    'AUTOSIGNAL_SYMBOLS': AUTOSIGNAL_SYMBOLS
}

# ============================================================================
# BOT DISCORD
# ============================================================================

intents = discord.Intents.default()
intents.message_content = False
bot = commands.Bot(command_prefix="/", intents=intents)

# Servicios
commands_service = None
autosignals_service = None

# ============================================================================
# FUNCIONES AUXILIARES BÁSICAS
# ============================================================================

def is_new_period() -> bool:
    """Verifica si estamos en un nuevo período de 12 horas"""
    current_period_start = get_current_period_start()
    return current_period_start > state.current_period_start

def reset_period_if_needed():
    """Resetea el contador de trades si estamos en un nuevo período"""
    if is_new_period():
        old_count = state.trades_current_period
        state.trades_current_period = 0
        state.current_period_start = get_current_period_start()
        
        period_name = "00:00-12:00" if state.current_period_start.hour == 0 else "12:00-24:00"
        log_event(f"🔄 NUEVO PERÍODO: {period_name} UTC | Trades resetados: {old_count} → 0", "INFO", "PERIOD")

def get_period_status() -> dict:
    """Obtiene el estado actual del período"""
    reset_period_if_needed()
    
    period_name = "00:00-12:00" if state.current_period_start.hour == 0 else "12:00-24:00"
    next_reset = state.current_period_start + timedelta(hours=12)
    time_until_reset = next_reset - datetime.now(timezone.utc)
    
    return {
        'current_period': period_name,
        'trades_current_period': state.trades_current_period,
        'max_trades_per_period': MAX_TRADES_PER_PERIOD,
        'trades_remaining': max(0, MAX_TRADES_PER_PERIOD - state.trades_current_period),
        'next_reset': next_reset,
        'time_until_reset': time_until_reset,
        'period_full': state.trades_current_period >= MAX_TRADES_PER_PERIOD
    }

# ============================================================================
# EVENTOS DEL BOT
# ============================================================================

@bot.event
async def on_ready():
    global commands_service, autosignals_service
    
    bot.start_time = datetime.now(timezone.utc)
    log_event(f"Conectado como {bot.user}")
    
    # Sincronizar comandos slash
    try:
        await bot.tree.sync()
        log_event("Comandos sincronizados correctamente")
    except Exception as e:
        log_event(f"Error sincronizando comandos: {e}", "ERROR")
    
    # Cargar estado de la base de datos
    try:
        load_db_state(state)
        log_event(f'Estado cargado: AUTOSIGNALS={state.autosignals}')
    except Exception as e:
        log_event(f"Error cargando estado: {e}", "ERROR")
    
    # Inicializar servicios
    commands_service = create_commands_service(bot, state, config)
    autosignals_service = create_autosignals_service(bot, state, config)
    
    # Iniciar dashboard
    try:
        start_enhanced_dashboard()
        log_event("Dashboard iniciado correctamente")
    except Exception as e:
        log_event(f"Error iniciando dashboard: {e}", "ERROR")
    
    # Iniciar loop de auto-señales
    bot.loop.create_task(autosignals_service.start_auto_signal_loop())
    
    log_event("Bot completamente inicializado y listo")

# ============================================================================
# COMANDOS BÁSICOS (los complejos están en services/commands.py)
# ============================================================================

@bot.command()
async def signal(ctx, symbol: str = None):
    """Comando de señal - delegado al servicio"""
    await commands_service.handle_signal_command(ctx, symbol)

@bot.command()
async def accept(ctx, signal_id: int):
    """Comando de aceptar - delegado al servicio"""
    await commands_service.handle_accept_command(ctx, signal_id)

@bot.command()
async def reject(ctx, signal_id: int):
    """Comando de rechazar - delegado al servicio"""
    await commands_service.handle_reject_command(ctx, signal_id)

@bot.command()
async def chart(ctx):
    """Comando de gráfico - delegado al servicio"""
    await commands_service.handle_chart_command(ctx)

# ============================================================================
# COMANDOS SLASH BÁSICOS
# ============================================================================

@bot.tree.command(name="status")
async def slash_status(interaction: discord.Interaction):
    """Muestra estado básico del bot"""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return
    
    period_status = get_period_status()
    uptime = datetime.now(timezone.utc) - bot.start_time if hasattr(bot, 'start_time') else timedelta(0)
    
    embed = discord.Embed(
        title="🤖 Estado del Bot",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📊 Trades",
        value=f"Hoy: {state.trades_today}/{MAX_TRADES_PER_DAY}\n"
              f"Período: {state.trades_current_period}/{MAX_TRADES_PER_PERIOD}\n"
              f"Período actual: {period_status['current_period']}",
        inline=True
    )
    
    embed.add_field(
        name="🔄 Sistema",
        value=f"Uptime: {str(uptime).split('.')[0]}\n"
              f"Auto-señales: {'✅' if state.autosignals else '❌'}\n"
              f"Kill switch: {'🔴' if KILL_SWITCH else '🟢'}",
        inline=True
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="autosignals")
async def slash_autosignals(interaction: discord.Interaction, enabled: bool):
    """Activa/desactiva auto-señales"""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return
    
    state.autosignals = enabled
    save_autosignals_state(enabled)
    
    status = "activadas" if enabled else "desactivadas"
    await interaction.response.send_message(f"🔄 Auto-señales {status}", ephemeral=True)

# ============================================================================
# MANEJO DE ERRORES Y LIMPIEZA
# ============================================================================

@bot.event
async def on_error(event, *args, **kwargs):
    """Manejo global de errores"""
    log_event(f"Error en evento {event}: {args}", "ERROR")

async def cleanup():
    """Limpieza al cerrar el bot"""
    log_event("Bot cerrándose - Limpiando recursos...")
    
    try:
        stop_enhanced_dashboard()
        log_event("Dashboard detenido")
    except:
        pass
    
    try:
        from mt5_client import shutdown as mt5_shutdown
        mt5_shutdown()
        log_event("MT5 desconectado")
    except:
        pass
    
    log_event("Bot cerrado completamente")

# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        log_event("Bot detenido por usuario")
    except Exception as e:
        log_event(f"Error fatal: {e}", "ERROR")
    finally:
        asyncio.run(cleanup())