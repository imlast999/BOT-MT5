import os
import logging
import signal
import sys

# Add signal handler for graceful shutdown
def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\n🛑 Señal de interrupción recibida. Cerrando bot...")
    sys.exit(0)

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Parche para compatibilidad con Python 3.13
import audioop_patch

# Configurar matplotlib para evitar problemas de threading
import matplotlib
matplotlib.use('Agg')  # Usar backend sin GUI

import discord
import asyncio
import sqlite3
import json
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from math import floor

# Configurar logging ANTES de los imports opcionales
logging.basicConfig(
    level=logging.WARNING,  # Cambiar a WARNING para reducir ruido
    format='{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}'
)
logger = logging.getLogger(__name__)

# ============================================================================
# IMPORTS CONSOLIDADOS - NUEVA ARQUITECTURA
# ============================================================================

# Core system (consolidado)
from core import (
    trading_engine, 
    get_current_period_start, 
    BotState,
    get_risk_manager,
    get_filters_system
)

# Services (consolidado)
from services import (
    log_event, 
    log_signal_evaluation, 
    log_command,
    execution_service,
    dashboard_service,
    start_enhanced_dashboard,
    stop_enhanced_dashboard,
    add_signal_to_enhanced_dashboard,
    update_dashboard_stats
)

# Import intelligent logger to access current_log_file
from services.logging import get_intelligent_logger

# Signals dispatcher (simplificado)
from signals import _detect_signal_wrapper

# Módulos específicos que se mantienen
from mt5_client import initialize as mt5_initialize, get_candles, shutdown as mt5_shutdown, login as mt5_login, place_order
from charts import generate_chart
from secrets_store import save_credentials, load_credentials, clear_credentials
from backtest_tracker import backtest_tracker
import MetaTrader5 as mt5
from position_manager import list_positions, close_position

# ============================================================================
# SISTEMAS OPCIONALES (mantenidos por compatibilidad)
# ============================================================================

# Importar sistema de apertura de mercados
try:
    from market_opening_system import create_market_opening_system
    market_opening_system = create_market_opening_system()
    MARKET_OPENING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Sistema de apertura de mercados no disponible: {e}")
    market_opening_system = None
    MARKET_OPENING_AVAILABLE = False

# Importar sistema de trailing stops
try:
    from trailing_stops import get_trailing_manager
    trailing_manager = get_trailing_manager()
    TRAILING_STOPS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Sistema de trailing stops no disponible: {e}")
    trailing_manager = None
    TRAILING_STOPS_AVAILABLE = False

# Importar sistema de reconexión
try:
    from reconnection_system import reconnection_system
    RECONNECTION_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Sistema de reconexión no disponible: {e}")
    reconnection_system = None
    RECONNECTION_AVAILABLE = False

# Importar sistema de resumen de sesión
try:
    from session_summary import session_summary
    SESSION_SUMMARY_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Sistema de resumen de sesión no disponible: {e}")
    session_summary = None
    SESSION_SUMMARY_AVAILABLE = False

# ======================
# CONFIGURACIÓN
# ======================

AUTHORIZED_USER_ID = int(os.getenv('AUTHORIZED_USER_ID', '739198540177473667'))
SIGNALS_CHANNEL_NAME = "signals"         # configurable
TIMEFRAME = mt5.TIMEFRAME_H1
SYMBOL = "EURUSD"
CANDLES = 100

# safety / limits
MAX_TRADES_PER_DAY = int(os.getenv('MAX_TRADES_PER_DAY', '3'))
MAX_TRADES_PER_PERIOD = int(os.getenv('MAX_TRADES_PER_PERIOD', '5'))  # 5 trades cada 12 horas
KILL_SWITCH = os.getenv('KILL_SWITCH', '0') == '1'

# auto-execution settings
AUTO_EXECUTE_SIGNALS = os.getenv('AUTO_EXECUTE_SIGNALS', '0') == '1'
AUTO_EXECUTE_CONFIDENCE = os.getenv('AUTO_EXECUTE_CONFIDENCE', 'HIGH')  # FIXED: HIGH instead of LOW

# ============================================================================
# ESTADO GLOBAL CONSOLIDADO
# ============================================================================

# Usar BotState consolidado del core
state = BotState()

# Configurar loggers específicos
mt5_logger = logging.getLogger('mt5_client')
mt5_logger.setLevel(logging.ERROR)  # Solo errores de MT5

signals_logger = logging.getLogger('signals')
signals_logger.setLevel(logging.INFO)  # Mantener info de señales


# ======================
# FUNCIONES DE PERÍODO (12 HORAS)
# ======================

# get_current_period_start ya está importado desde core

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
    reset_period_if_needed()  # Verificar si necesitamos resetear
    
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


# ======================
# DECORADOR PARA LOGGING DE COMANDOS
# ======================

def log_discord_command(func):
    """Decorador para loggear automáticamente comandos Discord"""
    import functools
    
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        # Obtener nombre del comando
        command_name = func.__name__.replace('slash_', '')
        
        # Construir argumentos para el log
        args_str = ' '.join(str(arg) for arg in args if arg)
        kwargs_str = ' '.join(f"{k}={v}" for k, v in kwargs.items() if v)
        full_args = f"{args_str} {kwargs_str}".strip()
        
        # Log inicial del comando
        log_event(f"🎮 COMMAND: /{command_name} {full_args} | User: {interaction.user.id} ({interaction.user.display_name})")
        
        try:
            # Ejecutar el comando original
            result = await func(interaction, *args, **kwargs)
            
            # Log de éxito (solo si no hubo excepción)
            log_event(f"✅ COMMAND SUCCESS: /{command_name} {full_args}")
            return result
            
        except Exception as e:
            # Log de error
            log_event(f"❌ COMMAND ERROR: /{command_name} {full_args} | Error: {e}")
            
            # Re-lanzar la excepción para que Discord la maneje
            raise
    
    return wrapper


# ======================
# LOGGING SYSTEM
# ======================

# Usar el logger inteligente consolidado de services
from services.logging import get_intelligent_logger
bot_logger = get_intelligent_logger()

# ensure we also write a simple log file for quicker debugging
# Sistema de logging ahora manejado por services/logging.py

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
# Use slash commands to avoid the Message Content privileged intent
intents.message_content = False
bot = commands.Bot(command_prefix="/", intents=intents)

# Optional: fast command registration to a test guild to avoid global sync delay
GUILD_ID = os.getenv('GUILD_ID')

# runtime state encapsulated in a single object to avoid globals
from dataclasses import dataclass, field
from typing import Dict, Any

# Global variables for session tracking
bot_start_time = None

# Usar BotState del core system
from core import BotState

state = BotState()

AUTOSIGNAL_INTERVAL = int(os.getenv('AUTOSIGNAL_INTERVAL', '20'))  # seconds between scans
AUTOSIGNAL_SYMBOLS = [s.strip().upper() for s in os.getenv('AUTOSIGNAL_SYMBOLS', SYMBOL).split(',') if s.strip()]
# AUTOSIGNAL_TOLERANCE_PIPS used to detect duplicates
AUTOSIGNAL_TOLERANCE_PIPS = float(os.getenv('AUTOSIGNAL_TOLERANCE_PIPS', '1.0'))
DB_PATH = os.path.join(os.path.dirname(__file__), 'bot_state.db')
# default strategy name (can be overridden via .env)
DEFAULT_STRATEGY = os.getenv('DEFAULT_STRATEGY', 'ema50_200')
# default autosignal symbols: EURUSD and XAUUSD; BTCEUR can be added via env
if not AUTOSIGNAL_SYMBOLS or AUTOSIGNAL_SYMBOLS == ['']:
    AUTOSIGNAL_SYMBOLS = ['EURUSD', 'XAUUSD']  # Removed BTCEUR due to strategy issues

# parse per-symbol rules from env, format: EURUSD:ema,XAUUSD:macd
_rules_raw = os.getenv('AUTOSIGNAL_RULES', '')
AUTOSIGNAL_RULES = {}
if _rules_raw:
    for part in _rules_raw.split(','):
        if ':' in part:
            s, r = part.split(':', 1)
            AUTOSIGNAL_RULES[s.strip().upper()] = r.strip().lower()

# Optional per-symbol strategy config file (JSON). Keys should be symbol uppercased.
RULES_CONFIG_PATH = os.getenv('RULES_CONFIG_PATH', os.path.join(os.path.dirname(__file__), 'rules_config.json'))
RULES_CONFIG = {}
try:
    if os.path.exists(RULES_CONFIG_PATH):
        with open(RULES_CONFIG_PATH, 'r', encoding='utf-8') as f:
            rc = json.load(f)
            # normalize keys to upper
            for k, v in rc.items():
                try:
                    RULES_CONFIG[k.strip().upper()] = dict(v or {})
                except Exception:
                    RULES_CONFIG[k.strip().upper()] = {}
except Exception:
    logger.exception('Failed to load rules config from %s', RULES_CONFIG_PATH)

# Inicializar gestores después de cargar configuración
risk_manager = None
advanced_filter = None

def init_risk_managers():
    """Inicializa los gestores de riesgo después de cargar la configuración"""
    global risk_manager, advanced_filter
    try:
        from core import get_risk_manager, get_filters_system
        risk_manager = get_risk_manager()
        advanced_filter = get_filters_system()
        logger.info("Gestores de riesgo inicializados correctamente")
    except Exception as e:
        logger.error(f"Error inicializando gestores de riesgo: {e}")
        # Crear gestores dummy para evitar errores
        risk_manager = None
        advanced_filter = None


# Funciones de base de datos ahora están en services/database.py
# Importar funciones de compatibilidad
from services import (
    init_db, load_db_state, save_autosignals_state, 
    save_last_auto_sent, save_trades_today, reset_trades_today
)

# Funciones get_symbol_tolerance y signals_similar ahora están en core/filters.py

# ======================
# UTILIDADES MT5
# ======================

def connect_mt5():
    try:
        return mt5_initialize()
    except Exception as e:
        logger.exception("MT5 connection failed")
        raise

# ======================
# GRÁFICOS
# ======================

# Use `generate_chart` imported from `charts` module above.

# ======================
# LÓGICA DE SEÑALES (EJEMPLO)
# ======================

# _detect_signal_wrapper ya está importado desde signals.py - función eliminada para evitar duplicación
def compute_suggested_lot(signal, risk_pct: float = None):
    """Compute a suggested lot size given a signal dict.

    Uses MT5 account balance and symbol info. This is an approximation and
    should be reviewed by the user before executing.
    Returns (lot, risk_amount, rr_ratio) or (None, None, None) on failure.
    """
    try:
        mt5_initialize()
    except Exception as e:
        logger.error(f"MT5 initialization failed in compute_suggested_lot: {e}")
        return None, None, None

    try:
        acc = mt5.account_info()
        if acc is None:
            logger.error("No account info available in compute_suggested_lot")
            return None, None, None
        
        balance = float(acc.balance)
        
        # Ensure symbol is a string
        symbol = signal.get('symbol')
        if hasattr(symbol, 'iloc'):  # Es una Serie de pandas
            symbol = str(symbol.iloc[0]) if len(symbol) > 0 else 'EURUSD'
        elif not isinstance(symbol, str):
            symbol = str(symbol)
        
        logger.debug(f"Computing lot for symbol: {symbol}")
        
        si = mt5.symbol_info(symbol)
        if si is None:
            logger.error(f"No symbol info for {symbol} in compute_suggested_lot")
            return None, None, None

        # default risk percent from env if not provided
        if risk_pct is None:
            try:
                risk_pct = float(os.getenv('MT5_RISK_PCT', '0.5'))
            except Exception:
                risk_pct = 0.5

        risk_amount = balance * (risk_pct / 100.0)

        entry = float(signal['entry'])
        sl = float(signal['sl'])
        
        # point value and contract size
        point = si.point
        contract = getattr(si, 'trade_contract_size', getattr(si, 'lot_size', 100000))

        # compute SL in pips (in points)
        sl_points = abs(entry - sl) / point if point and point != 0 else None
        if not sl_points or sl_points <= 0:
            logger.error(f"Invalid SL points calculation: {sl_points}")
            return None, None, None

        # approximate pip value per lot in account currency
        pip_value_per_lot = contract * point
        # risk per lot = sl_points * pip_value_per_lot
        risk_per_lot = sl_points * pip_value_per_lot
        if risk_per_lot <= 0:
            logger.error(f"Invalid risk per lot calculation: {risk_per_lot}")
            return None, None, None

        raw_lot = risk_amount / risk_per_lot

        # clamp to symbol min/max and step
        vol_min = getattr(si, 'volume_min', 0.01)
        vol_max = getattr(si, 'volume_max', 100.0)
        vol_step = getattr(si, 'volume_step', 0.01)

        # round down to nearest step
        steps = floor(raw_lot / vol_step)
        lot = max(vol_min, min(vol_max, steps * vol_step)) if steps > 0 else vol_min

        # risk/reward ratio approx
        tp = float(signal.get('tp', entry))
        rr = abs((tp - entry) / (entry - sl)) if (entry - sl) != 0 else None

        logger.debug(f"Computed lot: {lot}, risk_amount: {risk_amount}, rr: {rr}")
        return lot, risk_amount, rr
        
    except Exception as e:
        logger.error(f"Error in compute_suggested_lot: {e}")
        return None, None, None

# Load persisted credentials if available
loaded = load_credentials()
if loaded:
    state.mt5_credentials.update(loaded)

# ======================
# BOT EVENTS
# ======================

@bot.event
async def on_ready():
    global bot_start_time
    bot_start_time = datetime.now(timezone.utc)  # Track bot start time for session metrics
    
    log_event(f"Conectado como {bot.user}")
    
    # Inicializar gestores de riesgo
    init_risk_managers()
    log_event("Gestores de riesgo inicializados correctamente")
    
    # Sync application commands (slash commands). If GUILD_ID is set, sync only to that guild for fast registration.
    try:
        if GUILD_ID:
            guild_obj = discord.Object(id=int(GUILD_ID))
            # Attempt to copy any existing global commands to the guild (fast dev iteration)
            try:
                await bot.tree.copy_global_to(guild=guild_obj)
                log_event("Comandos globales copiados al servidor")
            except Exception:
                pass

            await bot.tree.sync(guild=guild_obj)
            log_event(f"Comandos sincronizados al servidor {GUILD_ID}")
        else:
            await bot.tree.sync()
            log_event("Comandos sincronizados globalmente")
    except Exception:
        log_event("Error sincronizando comandos slash", "ERROR")
        logger.exception("Failed to sync slash commands")
    
    # load persisted autosignals state and last sent info
    try:
        load_db_state(state)
        log_event(f'Estado cargado: AUTOSIGNALS={state.autosignals}')
    except Exception:
        log_event("Error cargando estado de la base de datos", "ERROR")
        logger.exception('Failed to load DB state')
    
    # start autosignal background task using services
    try:
        from services.autosignals import create_autosignals_service
        autosignals_service = create_autosignals_service(bot, state, {
            'AUTOSIGNAL_SYMBOLS': AUTOSIGNAL_SYMBOLS,
            'AUTOSIGNAL_INTERVAL': AUTOSIGNAL_INTERVAL,
            'SIGNALS_CHANNEL_NAME': SIGNALS_CHANNEL_NAME,
            'MAX_TRADES_PER_DAY': MAX_TRADES_PER_DAY,
            'MAX_TRADES_PER_PERIOD': MAX_TRADES_PER_PERIOD,
            'KILL_SWITCH': KILL_SWITCH,
            'AUTO_EXECUTE_SIGNALS': AUTO_EXECUTE_SIGNALS
        })
        bot.loop.create_task(autosignals_service.start_auto_signal_loop())
        log_event("Servicio de autosignals iniciado")
    except Exception as e:
        log_event(f"Error iniciando servicio de autosignals: {e}", "ERROR")
        logger.exception("Failed to start autosignals service")
    
    # start trailing stops background task
    if TRAILING_STOPS_AVAILABLE:
        bot.loop.create_task(_trailing_stops_loop_simple())
        log_event("Sistema de trailing stops iniciado")
    
    # start market opening alerts background task
    if MARKET_OPENING_AVAILABLE:
        bot.loop.create_task(_market_opening_loop_simple())
        log_event("Sistema de alertas de apertura iniciado")
    
    # start enhanced dashboard
    try:
        start_enhanced_dashboard()
        log_event("Dashboard inteligente iniciado - Sistema de confianza integrado")
    except Exception as e:
        log_event(f"Error iniciando dashboard inteligente: {e}", "ERROR")
        logger.exception("Failed to start enhanced dashboard")
    
    # start reconnection system - DISABLED temporarily due to freezing issues
    if RECONNECTION_AVAILABLE and False:  # Disabled
        try:
            # Configurar callbacks
            async def on_mt5_reconnect():
                log_event("🔄 MT5 reconectado exitosamente")
            
            async def on_discord_reconnect():
                log_event("🔄 Discord reconectado exitosamente")
            
            async def on_connection_lost(service):
                log_event(f"⚠️ Conexión perdida: {service}", "WARNING")
            
            reconnection_system.set_callbacks(
                mt5_reconnect=on_mt5_reconnect,
                discord_reconnect=on_discord_reconnect,
                connection_lost=on_connection_lost
            )
            
            # Iniciar watchdog
            bot.loop.create_task(reconnection_system.watchdog_loop(bot, state.mt5_credentials))
            log_event("Sistema de reconexión automática iniciado")
        except Exception as e:
            log_event(f"Error iniciando sistema de reconexión: {e}", "ERROR")
            logger.exception("Failed to start reconnection system")
    else:
        log_event("Sistema de reconexión DESHABILITADO temporalmente", "WARNING")
    
    # Print helpful invite URL for adding the bot with application commands scope
    try:
        app_id = bot.application_id or bot.user.id
        invite_url = f"https://discord.com/oauth2/authorize?client_id={app_id}&scope=bot%20applications.commands&permissions=8"
        logger.info(f"Invite URL: {invite_url}")
        log_event("URL de invitación generada correctamente")
    except Exception:
        log_event("Error generando URL de invitación", "WARNING")
        logger.debug("Could not build invite URL")
    
    # Log configuración importante
    log_event(f"AUTO_EXECUTE_SIGNALS: {AUTO_EXECUTE_SIGNALS}")
    log_event(f"AUTO_EXECUTE_CONFIDENCE: {AUTO_EXECUTE_CONFIDENCE}")
    log_event(f"AUTOSIGNAL_INTERVAL: {AUTOSIGNAL_INTERVAL} segundos")
    log_event(f"Símbolos monitoreados: {AUTOSIGNAL_SYMBOLS}")
    
    # Log estado de módulos opcionales
    if TRAILING_STOPS_AVAILABLE:
        log_event("Módulo trailing stops: DISPONIBLE")
    else:
        log_event("Módulo trailing stops: NO DISPONIBLE", "WARNING")
    
    if MARKET_OPENING_AVAILABLE:
        log_event("Módulo market opening: DISPONIBLE")
    else:
        log_event("Módulo market opening: NO DISPONIBLE", "WARNING")
    
    if RECONNECTION_AVAILABLE:
        log_event("Módulo reconexión: DISPONIBLE")
    else:
        log_event("Módulo reconexión: NO DISPONIBLE", "WARNING")
    
    if SESSION_SUMMARY_AVAILABLE:
        log_event("Módulo resumen de sesión: DISPONIBLE")
    else:
        log_event("Módulo resumen de sesión: NO DISPONIBLE", "WARNING")
    
    log_event("Bot completamente inicializado y listo para operar")
    
    # Mostrar información del archivo de log
    intelligent_logger = get_intelligent_logger()
    current_log_file = intelligent_logger.current_log_file
    if current_log_file:
        log_filename = os.path.basename(current_log_file)
        log_event(f"📝 Archivo de log: {log_filename}")
        log_event(f"📁 Ruta completa: {current_log_file}")


# Simplified background loops for compatibility
async def _trailing_stops_loop_simple():
    """Simplified trailing stops loop"""
    await bot.wait_until_ready()
    logger.info('Trailing stops loop started')
    
    while True:
        try:
            if TRAILING_STOPS_AVAILABLE and trailing_manager:
                trailing_manager.update_all_trailing_stops()
            await asyncio.sleep(30)
        except Exception:
            logger.exception('Trailing stops loop crashed; retrying in 60s')
            await asyncio.sleep(60)


async def _market_opening_loop_simple():
    """Simplified market opening loop"""
    await bot.wait_until_ready()
    logger.info('Market opening alerts loop started')
    
    while True:
        try:
            if MARKET_OPENING_AVAILABLE and market_opening_system:
                # Basic market opening monitoring
                pass
            await asyncio.sleep(300)
        except Exception:
            logger.exception('Market opening loop crashed; retrying in 10 minutes')
            await asyncio.sleep(600)

# ======================
# COMANDOS
# ======================

@bot.command()
async def signal(ctx, symbol: str = None):
    if ctx.author.id != AUTHORIZED_USER_ID:
        await ctx.send("⛔ No autorizado")
        return

    if KILL_SWITCH:
        await ctx.send("⛔ Kill switch activado. No se generan señales.")
        return

    # allow overriding the symbol from the command: `/signal BTCUSDT` or `!signal BTCUSDT`
    sym = (symbol or SYMBOL).upper()
    try:
        connect_mt5()
        df = get_candles(sym, TIMEFRAME, CANDLES)
    except Exception as e:
        await ctx.send(f"❌ Error conectando a MT5: {e}")
        return

    signal, df = _detect_signal_wrapper(df, symbol=sym)

    if not signal:
        await ctx.send("❌ No hay señal válida")
        return

    signal_id = max(state.pending_signals.keys(), default=0) + 1
    state.pending_signals[signal_id] = signal

    try:
        # Asegurar que el símbolo sea un string
        chart_symbol = signal.get('symbol', SYMBOL)
        if hasattr(chart_symbol, 'iloc'):
            chart_symbol = str(chart_symbol.iloc[0]) if len(chart_symbol) > 0 else SYMBOL
        elif not isinstance(chart_symbol, str):
            chart_symbol = str(chart_symbol)
        
        logger.debug(f"Generating chart for symbol: {chart_symbol}")
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
            os.remove(chart)
        except Exception:
            pass
    else:
        await ctx.send(text)

@bot.command()
async def accept(ctx, signal_id: int):
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    # trades counter moved into `state`

    signal = state.pending_signals.get(signal_id)
    if not signal:
        await ctx.send("❌ Señal no encontrada")
        return

    if datetime.now(timezone.utc) > signal.get("expires", datetime.now(timezone.utc)):
        await ctx.send("⌛ Señal expirada")
        # BACKTEST TRACKING: Marcar como expirada
        if 'backtest_id' in signal:
            try:
                backtest_tracker.update_signal_status(signal['backtest_id'], "REJECTED", 
                                                    result="EXPIRED", notes="Señal expirada")
            except Exception as e:
                logger.error(f"Error actualizando backtest (expirada): {e}")
        del state.pending_signals[signal_id]
        return

    # Verificar límites antes de aceptar
    reset_period_if_needed()  # Verificar si necesitamos resetear período
    
    if state.trades_today >= MAX_TRADES_PER_DAY:
        await ctx.send("⛔ Límite de trades diarios alcanzado")
        # BACKTEST TRACKING: Marcar como rechazada por límite
        if 'backtest_id' in signal:
            try:
                backtest_tracker.update_signal_status(signal['backtest_id'], "REJECTED", 
                                                    result="LIMIT_REACHED", notes="Límite diario alcanzado")
            except Exception as e:
                logger.error(f"Error actualizando backtest (límite): {e}")
        del state.pending_signals[signal_id]
        return
    
    if state.trades_current_period >= MAX_TRADES_PER_PERIOD:
        period_status = get_period_status()
        await ctx.send(f"⛔ Límite de período alcanzado ({state.trades_current_period}/{MAX_TRADES_PER_PERIOD})\n"
                      f"📅 Período actual: {period_status['current_period']} UTC\n"
                      f"⏰ Próximo reinicio: {period_status['time_until_reset'].total_seconds()/3600:.1f}h")
        # BACKTEST TRACKING: Marcar como rechazada por límite de período
        if 'backtest_id' in signal:
            try:
                backtest_tracker.update_signal_status(signal['backtest_id'], "REJECTED", 
                                                    result="PERIOD_LIMIT", notes="Límite de período alcanzado")
            except Exception as e:
                logger.error(f"Error actualizando backtest (período): {e}")
        del state.pending_signals[signal_id]
        return
    # Incrementar contadores y persistir
    state.trades_today += 1
    state.trades_current_period += 1
    try:
        save_trades_today(state.trades_today)
    except Exception:
        logger.exception('Failed to save trades_today')

    # BACKTEST TRACKING: Marcar como aceptada
    if 'backtest_id' in signal:
        try:
            backtest_tracker.update_signal_status(signal['backtest_id'], "ACCEPTED", 
                                                notes="Señal aceptada manualmente")
        except Exception as e:
            logger.error(f"Error actualizando backtest (aceptada): {e}")

    # Aquí solo confirmamos; ejecución automática vendrá más tarde y solo tras confirmación adicional
    await ctx.send(f"✅ Señal {signal_id} aceptada (lista para ejecución/manual). Trades hoy: {state.trades_today}/{MAX_TRADES_PER_DAY}")
    del state.pending_signals[signal_id]

@bot.command()
async def reject(ctx, signal_id: int):
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    if signal_id in state.pending_signals:
        signal = state.pending_signals[signal_id]
        # BACKTEST TRACKING: Marcar como rechazada
        if 'backtest_id' in signal:
            try:
                backtest_tracker.update_signal_status(signal['backtest_id'], "REJECTED", 
                                                    result="USER_REJECTED", notes="Señal rechazada manualmente")
            except Exception as e:
                logger.error(f"Error actualizando backtest (rechazada): {e}")
        del state.pending_signals[signal_id]
        await ctx.send(f"❌ Señal {signal_id} rechazada")

@bot.command()
async def close_signal(ctx, backtest_id: int, result: str, profit_loss: float = 0.0, close_price: float = 0.0):
    """Simula el cierre de una señal para testing del backtesting (WIN/LOSS/BREAKEVEN)"""
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    
    if result.upper() not in ['WIN', 'LOSS', 'BREAKEVEN']:
        await ctx.send("❌ Resultado debe ser WIN, LOSS o BREAKEVEN")
        return
    
    try:
        success = backtest_tracker.update_signal_status(
            backtest_id, 
            "CLOSED", 
            result=result.upper(),
            profit_loss=profit_loss,
            close_price=close_price,
            notes=f"Cerrada manualmente para testing"
        )
        
        if success:
            await ctx.send(f"✅ Señal {backtest_id} cerrada: {result.upper()} | P&L: {profit_loss} EUR")
        else:
            await ctx.send(f"❌ No se encontró la señal {backtest_id}")
            
    except Exception as e:
        await ctx.send(f"❌ Error cerrando señal: {e}")

# Backtest stats command moved to services/commands.py

# Backtest report command moved to services/commands.py

@bot.command()
async def chart(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    try:
        connect_mt5()
        df = get_candles(SYMBOL, TIMEFRAME, CANDLES)
    except Exception as e:
        await ctx.send(f"❌ Error obteniendo datos: {e}")
        return

    try:
        filename = generate_chart(df)
        await ctx.send("📊 Gráfico actual", file=discord.File(filename))
    except Exception as e:
        await ctx.send(f"❌ Error generando gráfico: {e}")


# ======================
# Slash commands (app commands)
# ======================

# Large slash commands moved to services/commands.py


async def _find_signals_channel():
    # find first channel matching SIGNALS_CHANNEL_NAME across guilds
    for g in bot.guilds:
        for ch in g.text_channels:
            if ch.name == SIGNALS_CHANNEL_NAME:
                return ch
    return None


# Auto-signal loop moved to services/autosignals.py


@bot.tree.command(name="status")
async def slash_status(interaction: discord.Interaction):
    """Muestra estado del bot, aplicación y sincronización de comandos."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    app_id = bot.application_id or bot.user.id
    in_guild = False
    guild_info = "(no GUILD_ID configured)"
    if GUILD_ID:
        try:
            gid = int(GUILD_ID)
            guild = bot.get_guild(gid)
            in_guild = guild is not None
            guild_info = f"Guild ID configured: {gid}. Bot is in guild: {in_guild}"
        except Exception:
            guild_info = f"Configured GUILD_ID is invalid: {GUILD_ID}"

    # fetch registered commands for the guild if possible
    cmds = []
    try:
        if GUILD_ID and in_guild:
            cmds = await bot.tree.fetch_commands(guild=discord.Object(id=int(GUILD_ID)))
        else:
            cmds = await bot.tree.fetch_commands()
    except Exception:
        cmds = []

    cmd_names = ", ".join([c.name for c in cmds]) if cmds else "(no commands found or fetch failed)"

    lines = [
        f"Application ID: {app_id}",
        guild_info,
        f"Registered commands: {cmd_names}",
        "\nIf the commands are not visible in the server, ensure the bot was invited with the `applications.commands` scope using the invite URL printed in the bot logs."
    ]

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="logs_info")
async def slash_logs_info(interaction: discord.Interaction):
    """Muestra información del archivo de logs actual (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    intelligent_logger = get_intelligent_logger()
    current_log_file = intelligent_logger.current_log_file
    if current_log_file and os.path.exists(current_log_file):
        # Obtener información del archivo
        file_size = os.path.getsize(current_log_file)
        file_size_mb = file_size / (1024 * 1024)
        
        # Obtener timestamp de creación del archivo
        creation_time = datetime.fromtimestamp(os.path.getctime(current_log_file))
        
        # Contar líneas del archivo
        try:
            with open(current_log_file, 'r', encoding='utf-8') as f:
                line_count = sum(1 for _ in f)
        except Exception:
            line_count = "Error contando líneas"
        
        lines = [
            "📝 **INFORMACIÓN DEL ARCHIVO DE LOGS**",
            "",
            f"📁 **Archivo:** `{os.path.basename(current_log_file)}`",
            f"📂 **Ruta:** `{current_log_file}`",
            f"📊 **Tamaño:** {file_size_mb:.2f} MB ({file_size:,} bytes)",
            f"📄 **Líneas:** {line_count:,}" if isinstance(line_count, int) else f"📄 **Líneas:** {line_count}",
            f"🕐 **Creado:** {creation_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"⏱️ **Duración:** {datetime.now() - creation_time}",
            "",
            "💡 **Nota:** Este archivo contiene TODA la salida de la terminal del bot."
        ]
        
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
    else:
        await interaction.response.send_message("❌ No se encontró información del archivo de logs actual", ephemeral=True)


@bot.tree.command(name="positions")
async def slash_positions(interaction: discord.Interaction):
    """Lista posiciones abiertas (solo usuario autorizado)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    try:
        connect_mt5()
        pos = list_positions()
        if not pos:
            await interaction.followup.send("(Sin posiciones abiertas)", ephemeral=True)
            return
        lines = [f"Tickets abiertos: {len(pos)}"]
        for p in pos:
            lines.append(f"- #{p['ticket']} {p['symbol']} {p['type']} vol={p['volume']} open={p['price_open']:.5f} profit={p['profit']:.2f}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error obteniendo posiciones: {e}")


@bot.tree.command(name="close_position")
@discord.app_commands.describe(ticket="Ticket de la posición a cerrar (número)")
async def slash_close_position(interaction: discord.Interaction, ticket: int):
    """Cierra una posición por ticket (solo usuario autorizado)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    try:
        connect_mt5()
        res = close_position(ticket)
        await interaction.followup.send(f"✅ Close request submitted: {res}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error cerrando posición: {e}", ephemeral=True)


@bot.tree.command(name="close_positions_ui")
async def slash_close_positions_ui(interaction: discord.Interaction):
    """Muestra un desplegable con posiciones abiertas y permite cerrar una (solo autorizado)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    try:
        connect_mt5()
        pos = list_positions()
        if not pos:
            await interaction.followup.send("(Sin posiciones abiertas)", ephemeral=True)
            return

        # Build select options
        options = []
        for p in pos:
            label = f"#{p['ticket']} {p['symbol']} {p['type']} vol={p['volume']}"
            desc = f"open={p['price_open']:.5f} profit={p['profit']:.2f}"
            options.append(discord.SelectOption(label=label, description=desc, value=str(p['ticket'])))

        class PositionSelect(discord.ui.Select):
            def __init__(self, opts):
                super().__init__(placeholder='Selecciona una posición a cerrar...', min_values=1, max_values=1, options=opts)

            async def callback(self, select_interaction: discord.Interaction):
                if select_interaction.user.id != AUTHORIZED_USER_ID:
                    await select_interaction.response.send_message('⛔ No autorizado', ephemeral=True)
                    return
                ticket = int(self.values[0])

                # confirmation view
                class ConfirmCloseView(discord.ui.View):
                    def __init__(self, ticket):
                        super().__init__(timeout=60)
                        self.ticket = ticket

                    @discord.ui.button(label='Confirmar cierre', style=discord.ButtonStyle.danger)
                    async def confirm(self, button_inter: discord.Interaction, btn: discord.ui.Button):
                        if button_inter.user.id != AUTHORIZED_USER_ID:
                            await button_inter.response.send_message('⛔ No autorizado', ephemeral=True)
                            return
                        await button_inter.response.defer(thinking=True)
                        try:
                            res = close_position(self.ticket)
                            await button_inter.followup.send(f'✅ Close request submitted: {res}', ephemeral=True)
                        except Exception as e:
                            await button_inter.followup.send(f'❌ Error cerrando posición: {e}', ephemeral=True)

                    @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary)
                    async def cancel(self, button_inter: discord.Interaction, btn: discord.ui.Button):
                        await button_inter.response.send_message('Operación cancelada', ephemeral=True)

                await select_interaction.response.send_message(f'¿Cerrar posición #{ticket}?', view=ConfirmCloseView(ticket), ephemeral=True)

        view = discord.ui.View()
        view.add_item(PositionSelect(options))
        await interaction.followup.send('Selecciona la posición a cerrar:', view=view, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error mostrando posiciones: {e}", ephemeral=True)


@bot.tree.command(name="signal")
@discord.app_commands.describe(symbol="Símbolo/activo (ej: EURUSD, BTCUSDT). Si se omite usa DEFAULT_STRATEGY simbolo por defecto en .env")
@log_discord_command
async def slash_signal(interaction: discord.Interaction, symbol: str = ''):
    """Detecta una señal usando MT5 y publica la propuesta (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    if KILL_SWITCH:
        await interaction.response.send_message("⛔ Kill switch activado. No se generan señales.", ephemeral=True)
        return

    # defer only if the interaction hasn't been responded to yet
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True)

    sym = (symbol or SYMBOL).upper()
    try:
        connect_mt5()
        df = get_candles(sym, TIMEFRAME, CANDLES)
    except Exception as e:
        await interaction.followup.send(f"❌ Error conectando a MT5: {e}")
        return

    signal, df, risk_info = _detect_signal_wrapper(df, symbol=sym)
    if not signal:
        rejection_reason = risk_info.get('reason', 'No hay señal válida')
        await interaction.followup.send(f"❌ {rejection_reason}")
        return

    signal_id = max(state.pending_signals.keys(), default=0) + 1
    state.pending_signals[signal_id] = signal

    # compute suggested lot and risk/reward
    lot, risk_amount, rr = compute_suggested_lot(signal)
    lot_text = f"Sugerido: {lot:.2f} lot" if lot else "Sugerido: N/A"
    risk_text = f"Riesgo aprox: {risk_amount:.2f} ({os.getenv('MT5_RISK_PCT','0.5')}%)" if risk_amount else "Riesgo aprox: N/A"
    rr_text = f"RR ≈ {rr:.2f}" if rr else "RR: N/A"

    def _fmt(v, nd=5):
        try:
            return f"{float(v):.{nd}f}"
        except Exception:
            return "N/A"

    entry_s = _fmt(signal.get('entry'))
    sl_s = _fmt(signal.get('sl'))
    tp_s = _fmt(signal.get('tp'))

    text = (
        f"🟡 **SEÑAL DETECTADA** (ID {signal_id})\n"
        f"Activo: {signal.get('symbol')}\n"
        f"Tipo: {signal.get('type')}\n"
        f"Entrada: {entry_s}\n"
        f"SL: {sl_s}\n"
        f"TP: {tp_s}\n"
        f"{lot_text} | {risk_text} | {rr_text}\n"
        f"⏱ Válida por 1 minuto\n"
        f"Explicación: {signal.get('explanation','-')}\n\n"
        "Decide:"
    )

    # Buttons view
    class SignalView(discord.ui.View):
        def __init__(self, sid):
            super().__init__(timeout=60)
            self.sid = sid

        @discord.ui.button(label='Aceptar', style=discord.ButtonStyle.success)
        async def accept_button(self, interaction_btn: discord.Interaction, button: discord.ui.Button):
            if interaction_btn.user.id != AUTHORIZED_USER_ID:
                await interaction_btn.response.send_message('⛔ No autorizado', ephemeral=True)
                return
            sig = state.pending_signals.get(self.sid)
            if not sig:
                await interaction_btn.response.send_message('❌ Señal no encontrada o ya procesada', ephemeral=True)
                return
            if datetime.now(timezone.utc) > sig.get('expires', datetime.now(timezone.utc)):
                del state.pending_signals[self.sid]
                await interaction_btn.response.send_message('⌛ Señal expirada', ephemeral=True)
                return

            # Show execution choices: Ejecutar ahora / Personalizar / Cancelar
            class ExecModal(discord.ui.Modal, title='Ejecutar señal - Personalizar'):
                lot = discord.ui.TextInput(label='Lot (ej: 0.01)', required=False, style=discord.TextStyle.short, placeholder='Dejar vacío para usar % de riesgo')
                risk_pct = discord.ui.TextInput(label='Riesgo % (ej: 0.5)', required=False, style=discord.TextStyle.short, placeholder='Porcentaje de balance a arriesgar')

                def __init__(self, sid):
                    super().__init__()
                    self.sid = sid

                async def on_submit(self, interaction_modal: discord.Interaction):
                    # perform execution with custom params
                    s = state.pending_signals.get(self.sid)
                    if not s:
                        await interaction_modal.response.send_message('❌ Señal no encontrada', ephemeral=True)
                        return
                    # determine lot
                    lot_val = None
                    try:
                        if self.risk_pct.value:
                            rp = float(self.risk_pct.value)
                            lot_val, _, _ = compute_suggested_lot(s, risk_pct=rp)
                        elif self.lot.value:
                            lot_val = float(self.lot.value)
                    except Exception as e:
                        await interaction_modal.response.send_message(f'❌ Parámetros inválidos: {e}', ephemeral=True)
                        return

                    if not lot_val:
                        await interaction_modal.response.send_message('❌ No se pudo calcular un lot válido', ephemeral=True)
                        return

                    # place order
                    try:
                        # Asegurar que el símbolo sea un string válido
                        symbol_str = s.get('symbol', 'EURUSD')
                        if hasattr(symbol_str, 'iloc'):
                            symbol_str = str(symbol_str.iloc[0]) if len(symbol_str) > 0 else 'EURUSD'
                        elif not isinstance(symbol_str, str):
                            symbol_str = str(symbol_str)
                        
                        logger.debug(f"Ejecutando orden: {symbol_str} {s.get('type')} {lot_val}")
                        res = place_order(symbol_str, s['type'], lot_val, price=s.get('entry'), sl=s.get('sl'), tp=s.get('tp'))
                        # increment trades_today and remove pending
                        state.trades_today += 1
                        try:
                            save_trades_today(state.trades_today)
                        except Exception:
                            logger.exception('Failed to save trades_today')
                        if self.sid in state.pending_signals:
                            del state.pending_signals[self.sid]
                        await interaction_modal.response.send_message(f'✅ Orden ejecutada: {res}', ephemeral=True)
                    except Exception as e:
                        await interaction_modal.response.send_message(f'❌ Error ejecutando orden: {e}', ephemeral=True)

            class ExecView(discord.ui.View):
                def __init__(self, sid):
                    super().__init__(timeout=60)
                    self.sid = sid

                @discord.ui.button(label='Ejecutar ahora', style=discord.ButtonStyle.success)
                async def execute_now(self, interaction_exec: discord.Interaction, button: discord.ui.Button):
                    if interaction_exec.user.id != AUTHORIZED_USER_ID:
                        await interaction_exec.response.send_message('⛔ No autorizado', ephemeral=True)
                        return
                    s = state.pending_signals.get(self.sid)
                    if not s:
                        await interaction_exec.response.send_message('❌ Señal no encontrada', ephemeral=True)
                        return
                    # compute default risk per type env override
                    type_key = s.get('type','').upper()
                    env_key = f'MT5_RISK_{type_key}'
                    try:
                        rp = float(os.getenv(env_key, os.getenv('MT5_RISK_PCT', '0.5')))
                    except Exception:
                        rp = 0.5
                    lot_val, _, _ = compute_suggested_lot(s, risk_pct=rp)
                    if not lot_val:
                        await interaction_exec.response.send_message('❌ No se pudo calcular lot sugerido', ephemeral=True)
                        return
                    try:
                        # Asegurar que el símbolo sea un string válido
                        symbol_str = s.get('symbol', 'EURUSD')
                        if hasattr(symbol_str, 'iloc'):
                            symbol_str = str(symbol_str.iloc[0]) if len(symbol_str) > 0 else 'EURUSD'
                        elif not isinstance(symbol_str, str):
                            symbol_str = str(symbol_str)
                        
                        logger.debug(f"Ejecutando orden automática: {symbol_str} {s.get('type')} {lot_val}")
                        res = place_order(symbol_str, s['type'], lot_val, price=s.get('entry'), sl=s.get('sl'), tp=s.get('tp'))
                        state.trades_today += 1
                        try:
                            save_trades_today(state.trades_today)
                        except Exception:
                            logger.exception('Failed to save trades_today')
                        if self.sid in state.pending_signals:
                            del state.pending_signals[self.sid]
                        await interaction_exec.response.send_message(f'✅ Orden ejecutada: {res}', ephemeral=True)
                    except Exception as e:
                        await interaction_exec.response.send_message(f'❌ Error ejecutando orden: {e}', ephemeral=True)

                @discord.ui.button(label='Personalizar', style=discord.ButtonStyle.primary)
                async def customize(self, interaction_exec: discord.Interaction, button: discord.ui.Button):
                    if interaction_exec.user.id != AUTHORIZED_USER_ID:
                        await interaction_exec.response.send_message('⛔ No autorizado', ephemeral=True)
                        return
                    await interaction_exec.response.send_modal(ExecModal(self.sid))

                @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary)
                async def cancel(self, interaction_exec: discord.Interaction, button: discord.ui.Button):
                    await interaction_exec.response.send_message('Acción cancelada. La señal permanece pendiente.', ephemeral=True)

            await interaction_btn.response.send_message('Selecciona acción: ejecutar ahora, personalizar lotaje o cancelar.', view=ExecView(self.sid), ephemeral=True)

        @discord.ui.button(label='Rechazar', style=discord.ButtonStyle.danger)
        async def reject_button(self, interaction_btn: discord.Interaction, button: discord.ui.Button):
            if interaction_btn.user.id != AUTHORIZED_USER_ID:
                await interaction_btn.response.send_message('⛔ No autorizado', ephemeral=True)
                return
            if self.sid in state.pending_signals:
                del state.pending_signals[self.sid]
                await interaction_btn.response.send_message(f'❌ Señal {self.sid} rechazada', ephemeral=True)
            else:
                await interaction_btn.response.send_message('❌ Señal no encontrada', ephemeral=True)

    view = SignalView(signal_id)

    try:
        # Asegurar que el símbolo sea un string
        chart_symbol = signal.get('symbol', SYMBOL)
        if hasattr(chart_symbol, 'iloc'):
            chart_symbol = str(chart_symbol.iloc[0]) if len(chart_symbol) > 0 else SYMBOL
        elif not isinstance(chart_symbol, str):
            chart_symbol = str(chart_symbol)
        
        logger.debug(f"Generating slash signal chart for symbol: {chart_symbol}")
        chart_file = generate_chart(df, symbol=chart_symbol, signal=signal)
    except Exception as e:
        logger.error(f"Slash signal chart generation failed: {e}")
        chart_file = None

    if chart_file:
        await interaction.followup.send(text, file=discord.File(chart_file), view=view)
        try:
            os.remove(chart_file)
        except Exception:
            pass
    else:
        await interaction.followup.send(text, view=view)


@bot.tree.command(name="chart")
@discord.app_commands.describe(symbol="Símbolo/activo (ej: EURUSD, XAUUSD, BTCEUR)", timeframe="Timeframe (M1,M5,M15,M30,H1,H4,D1)", candles="Número de velas a mostrar")
async def slash_chart(interaction: discord.Interaction, symbol: str = 'EURUSD', timeframe: str = 'H1', candles: int = 100):
    """Genera un gráfico PNG con las últimas velas (solo admin)."""
    # Log del comando ejecutado
    log_event(f"🎮 COMMAND: /chart {symbol} {timeframe} {candles} | User: {interaction.user.id} ({interaction.user.display_name})")
    
    if interaction.user.id != AUTHORIZED_USER_ID:
        log_event(f"❌ COMMAND REJECTED: /chart | User: {interaction.user.id} | Reason: No autorizado")
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    symbol = symbol.upper()
    # restrict charts to symbols that have rules (only show charts for these pairs)
    ALLOWED = ['EURUSD','XAUUSD','BTCEUR']
    if symbol not in ALLOWED:
        log_event(f"❌ COMMAND REJECTED: /chart | Symbol: {symbol} | Reason: Símbolo no soportado")
        await interaction.response.send_message(f"Símbolo no soportado o no disponible: {symbol}", ephemeral=True)
        return

    TF_MAP = {
        'M1': mt5.TIMEFRAME_M1,
        'M5': mt5.TIMEFRAME_M5,
        'M15': mt5.TIMEFRAME_M15,
        'M30': mt5.TIMEFRAME_M30,
        'H1': mt5.TIMEFRAME_H1,
        'H4': mt5.TIMEFRAME_H4,
        'D1': mt5.TIMEFRAME_D1,
    }

    tf = TF_MAP.get(timeframe.upper())
    if tf is None:
        await interaction.response.send_message(f"Timeframe no reconocido: {timeframe}", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    try:
        connect_mt5()
        df = get_candles(symbol, tf, candles)
    except Exception as e:
        await interaction.followup.send(f"❌ Error obteniendo datos: {e}")
        return

    try:
        filename = generate_chart(df, symbol=symbol, title=f"{symbol} {timeframe}")
        await interaction.followup.send("📊 Gráfico actual", file=discord.File(filename))
        log_event(f"✅ COMMAND SUCCESS: /chart {symbol} {timeframe} | Chart generated and sent")
        # remove file after sending to avoid stale reuse
        try:
            import os
            os.remove(filename)
        except Exception:
            pass
    except Exception as e:
        log_event(f"❌ COMMAND ERROR: /chart {symbol} {timeframe} | Error: {e}")
        await interaction.followup.send(f"❌ Error generando gráfico: {e}")


@bot.tree.command(name="scan")
@discord.app_commands.describe(symbols="Lista de símbolos separados por comas (opcional)", strategy="Estrategia a usar (ema,rsi,macd)")
async def slash_scan(interaction: discord.Interaction, symbols: str = '', strategy: str = 'ema'):
    """Escanea varios símbolos (limitado) y reporta señales encontradas."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    try:
        connect_mt5()
    except Exception as e:
        await interaction.followup.send(f"❌ Error conectando a MT5: {e}")
        return

    # Build symbol list
    if symbols:
        sym_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    else:
        # try to fetch a small set from MT5 (visible symbols)
        try:
            all_syms = mt5.symbols_get()
            sym_list = [s.name for s in all_syms if getattr(s, 'visible', False)][:10]
        except Exception:
            sym_list = ['EURUSD','XAUUSD','BTCEUR']

    results = []
    for s in sym_list[:10]:
        try:
            df = get_candles(s, TIMEFRAME, CANDLES)
            cfg = RULES_CONFIG.get(s.upper(), {}) or {}
            strat_used = cfg.get('strategy') or strategy
            sig, _ = detect_signal(df, strategy=strat_used, config=cfg)
            if sig:
                results.append((s, sig.get('type'), sig.get('entry')))
        except Exception:
            continue

    if not results:
        await interaction.followup.send('🔎 No se encontraron señales en el conjunto escaneado.')
    else:
        lines = ['🔎 Señales encontradas:']
        for s, t, e in results:
            lines.append(f"- {s}: {t} @ {e}")
        await interaction.followup.send('\n'.join(lines))


# Large autosignals command moved to services/commands.py


@bot.tree.command(name="set_mt5_credentials")
async def slash_set_mt5_credentials(interaction: discord.Interaction):
    """Abre un modal para introducir credenciales MT5 (slash)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    # show the same modal class used for the text command
    await interaction.response.send_modal(MT5CredentialsModal())


# Pairs config command moved to services/commands.py


# Market overview command moved to services/commands.py


@bot.tree.command(name="set_strategy")
@discord.app_commands.describe(
    symbol="Símbolo (EURUSD, XAUUSD, BTCEUR)",
    strategy="Estrategia disponible"
)
@discord.app_commands.choices(
    symbol=[
        discord.app_commands.Choice(name="🇪🇺 EURUSD", value="EURUSD"),
        discord.app_commands.Choice(name="🥇 XAUUSD", value="XAUUSD"),
        discord.app_commands.Choice(name="₿ BTCEUR", value="BTCEUR")
    ],
    strategy=[
        discord.app_commands.Choice(name="EURUSD Avanzada", value="eurusd_advanced"),
        discord.app_commands.Choice(name="XAUUSD Avanzada", value="xauusd_advanced"),
        discord.app_commands.Choice(name="BTCEUR Avanzada", value="btceur_advanced"),
        discord.app_commands.Choice(name="Breakout Confirmación", value="breakout_confirmation"),
        discord.app_commands.Choice(name="Reversión Media", value="mean_reversion"),
        discord.app_commands.Choice(name="EMA 50/200", value="ema50_200")
    ]
)
async def slash_set_strategy(interaction: discord.Interaction, symbol: str, strategy: str):
    """Cambia la estrategia para un símbolo específico (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    symbol = symbol.upper()
    strategy = strategy.lower()
    
    # Verificar que es uno de los pares principales
    main_pairs = ['EURUSD', 'XAUUSD', 'BTCEUR']
    if symbol not in main_pairs:
        await interaction.response.send_message(
            f"❌ Solo se pueden configurar los pares principales: {', '.join(main_pairs)}", 
            ephemeral=True
        )
        return
    
    # Actualizar configuración
    if symbol not in RULES_CONFIG:
        RULES_CONFIG[symbol] = {}
    
    old_strategy = RULES_CONFIG[symbol].get('strategy', 'N/A')
    RULES_CONFIG[symbol]['strategy'] = strategy
    
    # Guardar en archivo
    try:
        with open(RULES_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(RULES_CONFIG, f, indent=2, ensure_ascii=False)
        
        embed = discord.Embed(
            title="✅ Estrategia Actualizada",
            description=f"Configuración cambiada para **{symbol}**",
            color=0x00ff00
        )
        
        emoji = {"EURUSD": "🇪🇺", "XAUUSD": "🥇", "BTCEUR": "₿"}.get(symbol, "📈")
        
        embed.add_field(
            name=f"{emoji} **{symbol}**",
            value=(
                f"**Estrategia anterior:** `{old_strategy}`\n"
                f"**Nueva estrategia:** `{strategy}`\n"
                f"**Estado:** {'🟢 Activo' if RULES_CONFIG[symbol].get('enabled', False) else '🔴 Inactivo'}"
            ),
            inline=False
        )
        
        embed.set_footer(text="Los cambios se aplicarán en la próxima señal automática")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Error guardando configuración: {e}", ephemeral=True)


@bot.tree.command(name="strategy_performance")
@discord.app_commands.describe(days="Días para analizar (por defecto: 7)")
async def slash_strategy_performance(interaction: discord.Interaction, days: int = 7):
    """Muestra performance por estrategia (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    if risk_manager is None:
        await interaction.followup.send("❌ Gestor de riesgo no disponible")
        return
    
    try:
        # Obtener trades por estrategia
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        conn = sqlite3.connect(risk_manager.db_path)
        c = conn.cursor()
        
        c.execute('''SELECT strategy, COUNT(*) as total_trades,
                            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                            SUM(COALESCE(pnl, 0)) as total_pnl,
                            AVG(CASE WHEN result = 'win' THEN pnl END) as avg_win,
                            AVG(CASE WHEN result = 'loss' THEN pnl END) as avg_loss
                     FROM trades_history 
                     WHERE timestamp > ? AND strategy IS NOT NULL
                     GROUP BY strategy''', (cutoff_date,))
        
        results = c.fetchall()
        conn.close()
        
        if not results:
            await interaction.followup.send("❌ No hay datos de estrategias en el período seleccionado")
            return
        
        lines = [f"📊 **PERFORMANCE POR ESTRATEGIA ({days} días)**", ""]
        
        for row in results:
            strategy, total, wins, losses, pnl, avg_win, avg_loss = row
            win_rate = (wins / total * 100) if total > 0 else 0
            
            lines.extend([
                f"🎯 **{strategy.upper()}**",
                f"• Trades: {total} | Ganadores: {wins} | Perdedores: {losses}",
                f"• Tasa acierto: {win_rate:.1f}%",
                f"• PnL total: {pnl:.2f}",
                f"• Ganancia promedio: {avg_win:.2f}" if avg_win else "• Ganancia promedio: N/A",
                f"• Pérdida promedio: {avg_loss:.2f}" if avg_loss else "• Pérdida promedio: N/A",
                ""
            ])
        
        await interaction.followup.send("\n".join(lines))
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error obteniendo performance: {e}")


# Demo stats command moved to services/commands.py


@bot.tree.command(name="force_autosignal")
@discord.app_commands.describe(symbol="Símbolo para forzar señal automática (por defecto: EURUSD)")
async def slash_force_autosignal(interaction: discord.Interaction, symbol: str = 'EURUSD'):
    """Fuerza la generación de una señal automática para pruebas (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    try:
        # Buscar canal de señales
        ch = await _find_signals_channel()
        if ch is None:
            await interaction.followup.send(f"❌ No se encontró el canal '{SIGNALS_CHANNEL_NAME}'. Créalo primero.")
            return
        
        # Obtener datos y generar señal
        connect_mt5()
        df = get_candles(symbol.upper(), TIMEFRAME, CANDLES)
        
        # Usar la misma lógica que el auto-signal loop
        cfg = RULES_CONFIG.get(symbol.upper(), {}) or {}
        strat = cfg.get('strategy', 'ema50_200')
        
        sig, df2, risk_info = _detect_signal_wrapper(df, symbol=symbol.upper())
        
        if sig:
            # Crear ID de señal
            sid = max(state.pending_signals.keys(), default=0) + 1
            state.pending_signals[sid] = sig
            
            # Crear mensaje
            text = (
                f"🔧 **SEÑAL FORZADA** (ID {sid})\n"
                f"Activo: {sig['symbol']}\n"
                f"Tipo: {sig['type']}\n"
                f"Entrada: {sig['entry']:.5f}\n"
                f"SL: {sig['sl']:.5f}\n"
                f"TP: {sig['tp']:.5f}\n"
                f"Explicación: {sig.get('explanation','-')}\n"
                f"(Usa `/accept {sid}` para procesar)\n\n"
                f"**Información de Riesgo:**\n"
            )
            
            # Añadir información de riesgo si está disponible
            if risk_info and 'suggested_lot' in risk_info:
                text += f"Lot sugerido: {risk_info['suggested_lot']:.2f}\n"
            if risk_info and 'rr_ratio' in risk_info:
                text += f"R:R: {risk_info['rr_ratio']:.2f}\n"
            
            # Generar gráfico
            try:
                # Asegurar que el símbolo sea un string
                chart_symbol = sig.get('symbol', symbol.upper())
                if hasattr(chart_symbol, 'iloc'):
                    chart_symbol = str(chart_symbol.iloc[0]) if len(chart_symbol) > 0 else symbol.upper()
                elif not isinstance(chart_symbol, str):
                    chart_symbol = str(chart_symbol)
                
                logger.debug(f"Generating force autosignal chart for symbol: {chart_symbol}")
                chart = generate_chart(df2, symbol=chart_symbol, signal=sig)
                await ch.send(text, file=discord.File(chart))
                await interaction.followup.send(f"✅ Señal forzada enviada al canal #{ch.name}")
                
                # Limpiar archivo
                try:
                    os.remove(chart)
                except Exception:
                    pass
                    
            except Exception as chart_error:
                logger.error(f"Force autosignal chart generation failed: {chart_error}")
                await ch.send(text)
                await interaction.followup.send(f"✅ Señal enviada (sin gráfico): {chart_error}")
                
        else:
            reason = risk_info.get('reason', 'No hay señal válida') if risk_info else 'No hay señal válida'
            await interaction.followup.send(f"❌ No se pudo generar señal: {reason}")
            
    except Exception as e:
        await interaction.followup.send(f"❌ Error forzando señal: {e}")


@bot.tree.command(name="test_fallback")
@discord.app_commands.describe(symbol="Símbolo para probar el sistema de fallback")
@discord.app_commands.choices(symbol=[
    discord.app_commands.Choice(name="🇪🇺 EURUSD", value="EURUSD"),
    discord.app_commands.Choice(name="🥇 XAUUSD", value="XAUUSD"),
    discord.app_commands.Choice(name="₿ BTCEUR", value="BTCEUR")
])
async def slash_test_fallback(interaction: discord.Interaction, symbol: str = 'EURUSD'):
    """Prueba el sistema de fallback de estrategias (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    try:
        bot_logger.command_used(interaction.user.id, f"test_fallback {symbol}")
        
        # Obtener datos
        connect_mt5()
        df = get_candles(symbol.upper(), TIMEFRAME, CANDLES)
        
        # Test del sistema de fallback
        sig, df_result, risk_info = _detect_signal_wrapper(df, symbol=symbol.upper())
        
        embed = discord.Embed(
            title=f"🧪 Test Sistema Fallback: {symbol}",
            description="Resultado del sistema de estrategias en cascada",
            color=0x00ff88 if sig else 0xff4444
        )
        
        # Información de la estrategia usada
        strategy_used = risk_info.get('strategy_used', 'N/A')
        is_fallback = risk_info.get('is_fallback', False)
        is_emergency = risk_info.get('is_emergency', False)
        
        if is_emergency:
            strategy_label = f"🚨 {strategy_used} (EMERGENCY)"
            color = 0xff9500
        elif is_fallback:
            strategy_label = f"🔄 {strategy_used} (FALLBACK)"
            color = 0xffff00
        elif sig:
            strategy_label = f"✅ {strategy_used} (PRINCIPAL)"
            color = 0x00ff88
        else:
            strategy_label = "❌ NINGUNA"
            color = 0xff4444
        
        embed.color = color
        
        embed.add_field(
            name="🎯 **Resultado**",
            value=(
                f"**Estado:** {'✅ SEÑAL GENERADA' if sig else '❌ SIN SEÑAL'}\n"
                f"**Estrategia:** {strategy_label}\n"
                f"**Confianza:** {sig.get('confidence', 'N/A') if sig else 'N/A'}"
            ),
            inline=False
        )
        
        if sig:
            # Formatear precio según símbolo
            if symbol == 'XAUUSD':
                entry_str = f"{sig['entry']:.2f}"
                sl_str = f"{sig['sl']:.2f}"
                tp_str = f"{sig['tp']:.2f}"
            elif symbol == 'BTCEUR':
                entry_str = f"{sig['entry']:.0f}"
                sl_str = f"{sig['sl']:.0f}"
                tp_str = f"{sig['tp']:.0f}"
            else:  # EURUSD
                entry_str = f"{sig['entry']:.5f}"
                sl_str = f"{sig['sl']:.5f}"
                tp_str = f"{sig['tp']:.5f}"
            
            embed.add_field(
                name="📊 **Detalles de la Señal**",
                value=(
                    f"**Tipo:** {sig.get('type', 'N/A')}\n"
                    f"**Entrada:** {entry_str}\n"
                    f"**Stop Loss:** {sl_str}\n"
                    f"**Take Profit:** {tp_str}\n"
                    f"**Explicación:** {sig.get('explanation', 'N/A')[:100]}..."
                ),
                inline=False
            )
            
            # Test de cálculo de lot
            try:
                lot, risk_amount, rr = compute_suggested_lot(sig)
                if lot:
                    embed.add_field(
                        name="💰 **Cálculo de Riesgo**",
                        value=(
                            f"**Lot sugerido:** {lot:.2f}\n"
                            f"**Riesgo:** ${risk_amount:.2f}\n"
                            f"**R:R:** {rr:.2f}" if rr else "**R:R:** N/A"
                        ),
                        inline=True
                    )
                else:
                    embed.add_field(
                        name="💰 **Cálculo de Riesgo**",
                        value="❌ Error calculando lot",
                        inline=True
                    )
            except Exception as lot_error:
                embed.add_field(
                    name="💰 **Cálculo de Riesgo**",
                    value=f"❌ Error: {str(lot_error)[:50]}",
                    inline=True
                )
        
        # Información del sistema de fallback
        if 'strategies_tried' in risk_info:
            strategies_tried = risk_info['strategies_tried']
            embed.add_field(
                name="🔄 **Estrategias Probadas**",
                value="\n".join([f"• {s}" for s in strategies_tried]),
                inline=True
            )
        
        if not sig and 'reason' in risk_info:
            embed.add_field(
                name="❌ **Razón del Rechazo**",
                value=risk_info['reason'][:200],
                inline=False
            )
        
        # Test de generación de gráfico
        try:
            # Asegurar que el símbolo sea un string
            chart_symbol = sig.get('symbol', symbol.upper()) if sig else symbol.upper()
            if hasattr(chart_symbol, 'iloc'):
                chart_symbol = str(chart_symbol.iloc[0]) if len(chart_symbol) > 0 else symbol.upper()
            elif not isinstance(chart_symbol, str):
                chart_symbol = str(chart_symbol)
            
            chart_file = generate_chart(df_result, symbol=chart_symbol, signal=sig)
            embed.set_footer(text="✅ Gráfico generado correctamente")
            
            await interaction.followup.send(embed=embed, file=discord.File(chart_file))
            
            # Limpiar archivo
            try:
                os.remove(chart_file)
            except Exception:
                pass
                
        except Exception as chart_error:
            embed.set_footer(text=f"❌ Error generando gráfico: {str(chart_error)[:100]}")
            await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error en test de fallback: {e}")


@bot.tree.command(name="debug_signals")
@discord.app_commands.describe(symbol="Símbolo para debug (EURUSD, XAUUSD, BTCEUR)")
@discord.app_commands.choices(symbol=[
    discord.app_commands.Choice(name="🇪🇺 EURUSD", value="EURUSD"),
    discord.app_commands.Choice(name="🥇 XAUUSD", value="XAUUSD"),
    discord.app_commands.Choice(name="₿ BTCEUR", value="BTCEUR")
])
async def slash_debug_signals(interaction: discord.Interaction, symbol: str = 'EURUSD'):
    """Debug detallado del sistema de señales para ver por qué no se generan (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        bot_logger.command_used(interaction.user.id, f"debug_signals {symbol}", False)
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    try:
        bot_logger.command_used(interaction.user.id, f"debug_signals {symbol}")
        
        # Obtener datos
        connect_mt5()
        df = get_candles(symbol, TIMEFRAME, CANDLES)
        
        # Test señal básica
        cfg = RULES_CONFIG.get(symbol.upper(), {}) or {}
        strat = cfg.get('strategy', 'ema50_200')
        
        basic_signal, df_with_indicators = detect_signal(df, strategy=strat, config=cfg)
        
        # Test señal avanzada
        advanced_signal, df2, advanced_info = detect_signal_advanced(
            df, 
            strategy=strat, 
            config=cfg, 
            current_balance=5000.0
        )
        
        embed = discord.Embed(
            title=f"🔍 Debug de Señales: {symbol}",
            description="Análisis detallado del sistema de detección",
            color=0xff9500
        )
        
        # Formatear precio según símbolo
        if symbol == 'XAUUSD':
            current_price_str = f"{df['close'].iloc[-1]:.2f}"
        elif symbol == 'BTCEUR':
            current_price_str = f"{df['close'].iloc[-1]:.0f}"
        else:  # EURUSD
            current_price_str = f"{df['close'].iloc[-1]:.5f}"
        
        # Información básica
        embed.add_field(
            name="📊 **Datos Básicos**",
            value=(
                f"**Símbolo:** {symbol}\n"
                f"**Estrategia:** {strat}\n"
                f"**Velas:** {len(df)}\n"
                f"**Precio actual:** {current_price_str}"
            ),
            inline=True
        )
        
        # Señal básica
        embed.add_field(
            name="🎯 **Señal Básica**",
            value=(
                f"**Estado:** {'✅ DETECTADA' if basic_signal else '❌ NO DETECTADA'}\n"
                f"**Tipo:** {basic_signal.get('type', 'N/A') if basic_signal else 'N/A'}\n"
                f"**Explicación:** {basic_signal.get('explanation', 'Sin señal')[:50] if basic_signal else 'Sin señal'}..."
            ),
            inline=True
        )
        
        # Sistemas avanzados
        systems_available = advanced_info.get('systems_available', False)
        embed.add_field(
            name="🔧 **Sistemas Avanzados**",
            value=(
                f"**Disponibles:** {'✅ SÍ' if systems_available else '❌ NO'}\n"
                f"**Filtros:** {'✅ ACTIVOS' if advanced_info.get('advanced_filters', False) else '❌ INACTIVOS'}\n"
                f"**M15:** {'✅ ACTIVO' if advanced_info.get('m15_validation', False) else '❌ INACTIVO'}"
            ),
            inline=True
        )
        
        # Resultado final
        embed.add_field(
            name="🎯 **Resultado Final**",
            value=(
                f"**Señal Avanzada:** {'✅ APROBADA' if advanced_signal else '❌ RECHAZADA'}\n"
                f"**Confianza:** {advanced_signal.get('confidence', 'N/A') if advanced_signal else 'N/A'}\n"
                f"**Razón rechazo:** {advanced_info.get('reason', 'N/A') if not advanced_signal else 'N/A'}"
            ),
            inline=False
        )
        
        # Información detallada de filtros
        if 'filter_info' in advanced_info and advanced_info['filter_info']:
            filter_details = []
            filter_info = advanced_info['filter_info']
            
            if 'confluence' in filter_info:
                conf = filter_info['confluence']
                filter_details.append(f"**Confluencias:** {conf.get('score', 0)}/3 - {conf.get('passed', False)}")
            
            if 'session' in filter_info:
                sess = filter_info['session']
                filter_details.append(f"**Sesión:** {sess.get('passed', False)} - {sess.get('reason', 'N/A')[:30]}")
            
            if 'drawdown' in filter_info:
                dd = filter_info['drawdown']
                filter_details.append(f"**Drawdown:** {dd.get('passed', False)} - {dd.get('reason', 'N/A')[:30]}")
            
            if filter_details:
                embed.add_field(
                    name="🔍 **Detalles de Filtros**",
                    value="\n".join(filter_details),
                    inline=False
                )
        
        # Configuración actual
        embed.add_field(
            name="⚙️ **Configuración**",
            value=(
                f"**Min Confluencias:** {cfg.get('min_confirmations', 'N/A')}\n"
                f"**Filtros Sesión:** {cfg.get('use_session_filters', 'N/A')}\n"
                f"**Filtros Volatilidad:** {cfg.get('use_volatility_filters', 'N/A')}\n"
                f"**Habilitado:** {cfg.get('enabled', True)}"
            ),
            inline=True
        )
        
        # Sugerencias
        suggestions = []
        if not basic_signal:
            suggestions.append("• No hay condiciones básicas para señal")
        if not systems_available:
            suggestions.append("• Sistemas avanzados no disponibles")
        if advanced_info.get('reason'):
            suggestions.append(f"• {advanced_info['reason'][:60]}")
        
        if suggestions:
            embed.add_field(
                name="💡 **Diagnóstico**",
                value="\n".join(suggestions),
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
        bot_logger.command_used(interaction.user.id, f"debug_signals {symbol}")
        
    except Exception as e:
        bot_logger.command_used(interaction.user.id, f"debug_signals {symbol}", False)
        await interaction.followup.send(f"❌ Error en debug: {e}")


@bot.tree.command(name="test_signal")
@discord.app_commands.describe(symbol="Símbolo para probar (por defecto: EURUSD)")
async def slash_test_signal(interaction: discord.Interaction, symbol: str = 'EURUSD'):
    """Genera una señal de prueba para verificar el sistema (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    try:
        from mt5_client import get_candles
        import MetaTrader5 as mt5
        
        # Obtener datos
        df = get_candles(symbol.upper(), mt5.TIMEFRAME_H1, 100)
        
        # Detectar señal
        signal, df_with_indicators, risk_info = _detect_signal_wrapper(df, symbol=symbol.upper())
        
        if signal:
            # Generar gráfico
            try:
                # Asegurar que el símbolo sea un string
                chart_symbol = signal.get('symbol', symbol.upper())
                if hasattr(chart_symbol, 'iloc'):
                    chart_symbol = str(chart_symbol.iloc[0]) if len(chart_symbol) > 0 else symbol.upper()
                elif not isinstance(chart_symbol, str):
                    chart_symbol = str(chart_symbol)
                
                logger.debug(f"Generating test signal chart for symbol: {chart_symbol}")
                chart_file = generate_chart(df_with_indicators, symbol=chart_symbol, signal=signal)
                
                # Información de la señal
                text = (
                    f"🧪 **SEÑAL DE PRUEBA**\n"
                    f"Activo: {signal['symbol']}\n"
                    f"Tipo: {signal['type']}\n"
                    f"Entrada: {signal['entry']:.5f}\n"
                    f"SL: {signal['sl']:.5f}\n"
                    f"TP: {signal['tp']:.5f}\n"
                    f"Explicación: {signal.get('explanation', '-')}\n"
                )
                
                # Añadir información de riesgo si está disponible
                if risk_info:
                    if 'suggested_lot' in risk_info:
                        text += f"Lot sugerido: {risk_info['suggested_lot']:.2f}\n"
                    if 'rr_ratio' in risk_info:
                        text += f"R:R: {risk_info['rr_ratio']:.2f}\n"
                
                if chart_file:
                    await interaction.followup.send(text, file=discord.File(chart_file))
                    try:
                        import os
                        os.remove(chart_file)
                    except Exception:
                        pass
                else:
                    await interaction.followup.send(text)
                    
            except Exception as e:
                await interaction.followup.send(f"✅ Señal detectada pero error en gráfico: {e}\n{text}")
        else:
            reason = risk_info.get('reason', 'No hay señal válida') if risk_info else 'No hay señal válida'
            await interaction.followup.send(f"❌ {reason}")
            
    except Exception as e:
        await interaction.followup.send(f"❌ Error generando señal de prueba: {e}")



@bot.tree.command(name="mt5_login")
async def slash_mt5_login(interaction: discord.Interaction):
    """Intenta iniciar sesión en MT5 con las credenciales guardadas en memoria (slash)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    if not state.mt5_credentials.get('login'):
        await interaction.response.send_message("No hay credenciales guardadas. Usa `/set_mt5_credentials` primero.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    try:
        connect_mt5()
        ok = mt5.login(state.mt5_credentials.get('login'), state.mt5_credentials.get('password'), server=state.mt5_credentials.get('server'))
        if ok:
            await interaction.followup.send("✅ Conectado y logueado en MT5.")
        else:
            await interaction.followup.send(f"❌ Login falló: {mt5.last_error()}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error al loguear en MT5: {e}")


@bot.tree.command(name="accept")
@log_discord_command
async def slash_accept(interaction: discord.Interaction, signal_id: int):
    """Aceptar una señal pendiente por ID (slash)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    log_event(f"Usuario intentando aceptar señal ID: {signal_id}")

    signal = state.pending_signals.get(signal_id)
    if not signal:
        log_event(f"❌ Señal {signal_id} no encontrada", "WARNING")
        await interaction.followup.send("❌ Señal no encontrada")
        return

    if datetime.now(timezone.utc) > signal.get("expires", datetime.now(timezone.utc)):
        del state.pending_signals[signal_id]
        log_event(f"⌛ Señal {signal_id} expirada y eliminada", "WARNING")
        await interaction.followup.send("⌛ Señal expirada")
        return

    # Present execution options similar to the button flow
    class ExecModal(discord.ui.Modal, title='Ejecutar señal - Personalizar'):
        lot = discord.ui.TextInput(label='Lot (ej: 0.01)', required=False, style=discord.TextStyle.short, placeholder='Dejar vacío para usar % de riesgo')
        risk_pct = discord.ui.TextInput(label='Riesgo % (ej: 0.5)', required=False, style=discord.TextStyle.short, placeholder='Porcentaje de balance a arriesgar')

        def __init__(self, sid):
            super().__init__()
            self.sid = sid

        async def on_submit(self, interaction_modal: discord.Interaction):
            s = state.pending_signals.get(self.sid)
            if not s:
                await interaction_modal.response.send_message('❌ Señal no encontrada', ephemeral=True)
                return
            lot_val = None
            try:
                if self.risk_pct.value:
                    rp = float(self.risk_pct.value)
                    lot_val, _, _ = compute_suggested_lot(s, risk_pct=rp)
                elif self.lot.value:
                    lot_val = float(self.lot.value)
            except Exception as e:
                await interaction_modal.response.send_message(f'❌ Parámetros inválidos: {e}', ephemeral=True)
                return

            if not lot_val:
                await interaction_modal.response.send_message('❌ No se pudo calcular un lot válido', ephemeral=True)
                return

            try:
                # Asegurar que el símbolo sea un string válido
                symbol_str = s.get('symbol', 'EURUSD')
                if hasattr(symbol_str, 'iloc'):
                    symbol_str = str(symbol_str.iloc[0]) if len(symbol_str) > 0 else 'EURUSD'
                elif not isinstance(symbol_str, str):
                    symbol_str = str(symbol_str)
                
                logger.debug(f"Ejecutando orden modal: {symbol_str} {s.get('type')} {lot_val}")
                log_event(f"🎯 EXECUTING ORDER: {symbol_str} {s.get('type')} {lot_val} lots (Modal)")
                res = place_order(symbol_str, s['type'], lot_val, price=s.get('entry'), sl=s.get('sl'), tp=s.get('tp'))
                state.trades_today += 1
                try:
                    save_trades_today(state.trades_today)
                except Exception:
                    logger.exception('Failed to save trades_today')
                if self.sid in state.pending_signals:
                    del state.pending_signals[self.sid]
                log_event(f"✅ ORDER EXECUTED: {res}")
                await interaction_modal.response.send_message(f'✅ Orden ejecutada: {res}', ephemeral=True)
            except Exception as e:
                log_event(f"❌ ORDER FAILED: {e}", "ERROR")
                await interaction_modal.response.send_message(f'❌ Error ejecutando orden: {e}', ephemeral=True)

    class ExecView(discord.ui.View):
        def __init__(self, sid):
            super().__init__(timeout=60)
            self.sid = sid

        @discord.ui.button(label='Ejecutar ahora', style=discord.ButtonStyle.success)
        async def execute_now(self, interaction_exec: discord.Interaction, button: discord.ui.Button):
            if interaction_exec.user.id != AUTHORIZED_USER_ID:
                await interaction_exec.response.send_message('⛔ No autorizado', ephemeral=True)
                return
            s = state.pending_signals.get(self.sid)
            if not s:
                await interaction_exec.response.send_message('❌ Señal no encontrada', ephemeral=True)
                return
            type_key = s.get('type','').upper()
            env_key = f'MT5_RISK_{type_key}'
            try:
                rp = float(os.getenv(env_key, os.getenv('MT5_RISK_PCT', '0.5')))
            except Exception:
                rp = 0.5
            lot_val, _, _ = compute_suggested_lot(s, risk_pct=rp)
            if not lot_val:
                await interaction_exec.response.send_message('❌ No se pudo calcular lot sugerido', ephemeral=True)
                return
            try:
                # Asegurar que el símbolo sea un string válido
                symbol_str = s.get('symbol', 'EURUSD')
                if hasattr(symbol_str, 'iloc'):
                    symbol_str = str(symbol_str.iloc[0]) if len(symbol_str) > 0 else 'EURUSD'
                elif not isinstance(symbol_str, str):
                    symbol_str = str(symbol_str)
                
                logger.debug(f"Ejecutando orden directa: {symbol_str} {s.get('type')} {lot_val}")
                log_event(f"🎯 EXECUTING ORDER: {symbol_str} {s.get('type')} {lot_val} lots (Direct)")
                res = place_order(symbol_str, s['type'], lot_val, price=s.get('entry'), sl=s.get('sl'), tp=s.get('tp'))
                state.trades_today += 1
                try:
                    save_trades_today(state.trades_today)
                except Exception:
                    logger.exception('Failed to save trades_today')
                if self.sid in state.pending_signals:
                    del state.pending_signals[self.sid]
                log_event(f"✅ ORDER EXECUTED: {res}")
                await interaction_exec.response.send_message(f'✅ Orden ejecutada: {res}', ephemeral=True)
            except Exception as e:
                log_event(f"❌ ORDER FAILED: {e}", "ERROR")
                await interaction_exec.response.send_message(f'❌ Error ejecutando orden: {e}', ephemeral=True)

        @discord.ui.button(label='Personalizar', style=discord.ButtonStyle.primary)
        async def customize(self, interaction_exec: discord.Interaction, button: discord.ui.Button):
            if interaction_exec.user.id != AUTHORIZED_USER_ID:
                await interaction_exec.response.send_message('⛔ No autorizado', ephemeral=True)
                return
            await interaction_exec.response.send_modal(ExecModal(self.sid))

        @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction_exec: discord.Interaction, button: discord.ui.Button):
            await interaction_exec.response.send_message('Acción cancelada. La señal permanece pendiente.', ephemeral=True)

    await interaction.followup.send('Selecciona acción: ejecutar ahora, personalizar lotaje o cancelar.', view=ExecView(signal_id), ephemeral=True)


@bot.tree.command(name="reject")
@log_discord_command
async def slash_reject(interaction: discord.Interaction, signal_id: int):
    """Rechaza una señal pendiente por ID (slash)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    if signal_id in state.pending_signals:
        signal = state.pending_signals[signal_id]
        del state.pending_signals[signal_id]
        log_event(f"❌ SIGNAL REJECTED: ID {signal_id} ({signal.get('symbol', 'N/A')} {signal.get('type', 'N/A')})")
        await interaction.response.send_message(f"❌ Señal {signal_id} rechazada")
    else:
        log_event(f"❌ Intento de rechazar señal inexistente: ID {signal_id}", "WARNING")
        await interaction.response.send_message("❌ Señal no encontrada")


@bot.tree.command(name="performance")
@discord.app_commands.describe(days="Número de días para el reporte (por defecto: 30)")
async def slash_performance(interaction: discord.Interaction, days: int = 30):
    """Muestra un reporte de performance del bot (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    if risk_manager is None:
        await interaction.followup.send("❌ Gestor de riesgo no disponible")
        return
    
    try:
        report = risk_manager.get_performance_report(days)
        
        if 'error' in report:
            await interaction.followup.send(f"❌ {report['error']}")
            return
        
        # Formatear el reporte
        lines = [
            f"📊 **REPORTE DE PERFORMANCE ({days} días)**",
            f"",
            f"🔢 **Estadísticas Generales:**",
            f"• Total de trades: {report['total_trades']}",
            f"• Trades ganadores: {report['wins']}",
            f"• Trades perdedores: {report['losses']}",
            f"• Tasa de acierto: {report['win_rate']}%",
            f"",
            f"💰 **Resultados Financieros:**",
            f"• PnL total: {report['total_pnl']}",
            f"• Ganancia promedio: {report['avg_win']}",
            f"• Pérdida promedio: {report['avg_loss']}",
            f"• Factor de beneficio: {report['profit_factor']}",
            f"",
            f"📈 **Análisis:**"
        ]
        
        # Añadir análisis cualitativo
        if report['win_rate'] >= 60:
            lines.append("✅ Excelente tasa de acierto")
        elif report['win_rate'] >= 50:
            lines.append("🟡 Tasa de acierto aceptable")
        else:
            lines.append("🔴 Tasa de acierto baja - revisar estrategias")
        
        if report['profit_factor'] >= 1.5:
            lines.append("✅ Buen factor de beneficio")
        elif report['profit_factor'] >= 1.0:
            lines.append("🟡 Factor de beneficio marginal")
        else:
            lines.append("🔴 Factor de beneficio negativo")
        
        await interaction.followup.send("\n".join(lines))
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error generando reporte: {e}")


# Trailing status command moved to services/commands.py


# Risk status command moved to services/commands.py


# ----------------------
# MT5 credential helpers (Modal)
# ----------------------
from discord import ui


class MT5CredentialsModal(ui.Modal, title="MT5 Credentials"):
    login = ui.TextInput(label="Login (numeric)", style=discord.TextStyle.short, placeholder="123456", required=True)
    password = ui.TextInput(label="Password", style=discord.TextStyle.short, required=True)
    server = ui.TextInput(label="Server", style=discord.TextStyle.short, placeholder="BrokerServer", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            state.mt5_credentials['login'] = int(self.login.value)
        except Exception:
            state.mt5_credentials['login'] = self.login.value
        state.mt5_credentials['password'] = self.password.value
        state.mt5_credentials['server'] = self.server.value
        # try to persist encrypted
        ok = save_credentials(state.mt5_credentials)
        if ok:
            await interaction.response.send_message("Credenciales MT5 almacenadas y cifradas en disco. Usa `mt5_login` para intentar iniciar sesión.", ephemeral=True)
        else:
            await interaction.response.send_message("Credenciales almacenadas en memoria (no cifradas). Define MT5_MASTER_KEY en .env para cifrarlas en disco.", ephemeral=True)


@bot.command()
async def set_mt5_credentials(ctx):
    """Abre un modal para introducir credenciales MT5. Sólo usuario autorizado."""
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    await ctx.send_modal(MT5CredentialsModal())


@bot.command()
async def mt5_login(ctx):
    """Intenta iniciar sesión en MT5 con las credenciales guardadas en memoria."""
    if ctx.author.id != AUTHORIZED_USER_ID:
        return

    if not state.mt5_credentials.get('login'):
        await ctx.send("No hay credenciales guardadas. Usa `set_mt5_credentials` primero.")
        return

    try:
        connect_mt5()
        ok = mt5_login(state.mt5_credentials.get('login'), state.mt5_credentials.get('password'), state.mt5_credentials.get('server'))
        if ok:
            await ctx.send("✅ Conectado y logueado en MT5.")
        else:
            # mt5.last_error might be available
            err = None
            try:
                import MetaTrader5 as _mt5
                err = _mt5.last_error()
            except Exception:
                pass
            await ctx.send(f"❌ Login falló: {err}")
    except Exception as e:
        await ctx.send(f"❌ Error al loguear en MT5: {e}")

# Background loops moved to services/autosignals.py


# Next opening command moved to services/commands.py


# Pre-market analysis command moved to services/commands.py


# Opening alerts command moved to services/commands.py


# Period status command moved to services/commands.py


# Backtest summary command moved to services/commands.py


# Cooldown status command moved to services/commands.py


# Live dashboard command moved to services/commands.py


# ======================
# START
# ======================

if __name__ == '__main__':
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN no encontrado en el entorno. Añade .env con DISCORD_TOKEN=")
        raise SystemExit("DISCORD_TOKEN missing")

    try:
        bot.run(DISCORD_TOKEN)
    except discord.errors.PrivilegedIntentsRequired as exc:
        logger.error("Privileged intents required: %s", exc)
        logger.error("Enable the required privileged intents (Message Content) in the Discord Developer Portal for your application: https://discord.com/developers/applications")
        logger.error("Or remove/avoid using `message_content` intent by migrating commands to application (slash) commands.")
        print("ERROR: Privileged intents required. See logs for details.")
        raise
    except Exception:
        logger.exception("Unhandled exception while running bot")
        raise
    finally:
        # ensure MT5 is shutdown when process exits
        log_event("Bot cerrándose - Limpiando recursos...")
        try:
            stop_enhanced_dashboard()
            log_event("Dashboard inteligente detenido")
        except Exception:
            pass
        try:
            mt5_shutdown()
            log_event("MT5 desconectado")
        except Exception:
            pass
        
        # Información final del archivo de log
        intelligent_logger = get_intelligent_logger()
        current_log_file = intelligent_logger.current_log_file
        if current_log_file and os.path.exists(current_log_file):
            file_size = os.path.getsize(current_log_file)
            file_size_mb = file_size / (1024 * 1024)
            log_event(f"📝 Log final guardado: {os.path.basename(current_log_file)} ({file_size_mb:.2f} MB)")
        
        log_event("Bot cerrado completamente")
        print("=" * 60)
        print(f"📝 Sesión completa guardada en: {os.path.basename(current_log_file) if current_log_file else 'archivo desconocido'}")
        print("=" * 60)
