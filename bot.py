import os
import logging
import discord
import asyncio
import sqlite3
import json
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from math import floor

# local modules
from mt5_client import initialize as mt5_initialize, get_candles, shutdown as mt5_shutdown, login as mt5_login, place_order
from signals import detect_signal, detect_signal_advanced
from charts import generate_chart
from secrets_store import save_credentials, load_credentials, clear_credentials
from risk_manager import create_risk_manager
from trading_rules import create_advanced_filter, should_execute_signal
from backtest_tracker import backtest_tracker
import MetaTrader5 as mt5
from position_manager import list_positions, close_position
from live_dashboard import start_live_dashboard, stop_live_dashboard, update_dashboard_stats

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
KILL_SWITCH = os.getenv('KILL_SWITCH', '0') == '1'

# structured-ish logging for easier parsing
logging.basicConfig(
    level=logging.WARNING,  # Cambiar a WARNING para reducir ruido
    format='{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}'
)
logger = logging.getLogger(__name__)

# Configurar loggers específicos
mt5_logger = logging.getLogger('mt5_client')
mt5_logger.setLevel(logging.ERROR)  # Solo errores de MT5

signals_logger = logging.getLogger('signals')
signals_logger.setLevel(logging.INFO)  # Mantener info de señales

# Logger personalizado para eventos importantes
def log_event(message: str, level: str = "INFO", component: str = "BOT"):
    """
    Logger personalizado para eventos importantes del bot.
    Ahora que capturamos toda la salida, solo necesitamos hacer print()
    """
    timestamp = datetime.now().strftime('%H:%M:%S')
    
    # Formato para consola (que se capturará automáticamente en el archivo)
    console_msg = f"[{timestamp}] 🤖 {component}: {message}"
    
    # Solo hacer print - el sistema TeeOutput se encarga del resto
    print(console_msg)
    
    # También usar el logger estándar para mantener compatibilidad
    if level.upper() == "ERROR":
        logger.error(f"{component}: {message}")
    elif level.upper() == "WARNING":
        logger.warning(f"{component}: {message}")
    else:
        logger.info(f"{component}: {message}")
class BotEventLogger:
    """Logger personalizado para eventos importantes del bot"""
    
    @staticmethod
    def command_used(user_id: int, command: str, success: bool = True):
        status = "✅ SUCCESS" if success else "❌ ERROR"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎮 COMMAND: /{command} | User: {user_id} | {status}")
    
    @staticmethod
    def signal_generated(symbol: str, signal_type: str, confidence: str = "MEDIUM"):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎯 NEW SIGNAL: {symbol} {signal_type} | Confidence: {confidence}")
    
    @staticmethod
    def signal_rejected(symbol: str, reason: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ SIGNAL REJECTED: {symbol} | Reason: {reason[:50]}")
    
    @staticmethod
    def autosignal_scan():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 AUTOSIGNAL SCAN: Checking {len(AUTOSIGNAL_SYMBOLS)} pairs...")
    
    @staticmethod
    def market_opening_alert(market: str, alert_type: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚨 MARKET ALERT: {market} {alert_type}")
    
    @staticmethod
    def bot_status(message: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🤖 BOT: {message}")

bot_logger = BotEventLogger()

# ensure we also write a simple log file for quicker debugging
def ensure_log_file(log_path: str | None = None, clear_on_start: bool = True):
    """
    Crear un nuevo archivo de log con timestamp único cada vez que se inicia el bot
    """
    from datetime import datetime
    import sys
    
    # Crear nombre de archivo con timestamp
    if log_path is None:
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        log_path = os.path.join(os.path.dirname(__file__), f'logs_{timestamp}.txt')
    
    try:
        # Crear archivo con header inicial
        with open(log_path, 'w', encoding='utf-8') as f:
            startup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"=== BOT STARTED: {startup_time} ===\n")
            f.write(f"=== LOG FILE: {os.path.basename(log_path)} ===\n")
            f.write("=" * 60 + "\n\n")
        
        # Configurar logging para capturar TODO
        class TeeOutput:
            """Clase para duplicar la salida a archivo y consola"""
            def __init__(self, file_path, original_stream):
                self.file_path = file_path
                self.original_stream = original_stream
                self.terminal = original_stream
                
            def write(self, message):
                # Escribir a la terminal original
                self.terminal.write(message)
                self.terminal.flush()
                
                # Escribir al archivo de log
                try:
                    with open(self.file_path, 'a', encoding='utf-8') as f:
                        # Agregar timestamp a cada línea si no es solo un salto de línea
                        if message.strip():
                            timestamp = datetime.now().strftime('%H:%M:%S')
                            f.write(f"[{timestamp}] {message}")
                        else:
                            f.write(message)
                        f.flush()
                except Exception:
                    pass  # No queremos que el logging cause errores
                    
            def flush(self):
                self.terminal.flush()
        
        # Redirigir stdout y stderr para capturar TODO
        sys.stdout = TeeOutput(log_path, sys.stdout)
        sys.stderr = TeeOutput(log_path, sys.stderr)
        
        # También configurar el handler de logging para el archivo
        fh_exists = any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == os.path.abspath(log_path) for h in logging.getLogger().handlers)
        if not fh_exists:
            fh = logging.FileHandler(log_path, encoding='utf-8')
            fh.setLevel(logging.INFO)
            fmt = logging.Formatter('[%(asctime)s] %(levelname)s - %(name)s: %(message)s', datefmt='%H:%M:%S')
            fh.setFormatter(fmt)
            logging.getLogger().addHandler(fh)
        
        # Guardar la ruta del archivo actual para referencia
        global current_log_file
        current_log_file = log_path
        
        print(f"📝 Sistema de logging iniciado: {os.path.basename(log_path)}")
        
    except Exception as e:
        print(f'❌ Error configurando sistema de logging: {e}')
        logger.exception('Failed to ensure log file %s', log_path)

# Immediately ensure logs.txt exists so errors are captured to disk
current_log_file = None  # Variable global para el archivo de log actual
ensure_log_file()

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


@dataclass
class BotState:
    pending_signals: Dict[int, dict] = field(default_factory=dict)
    trades_today: int = 0
    mt5_credentials: Dict[str, Any] = field(default_factory=dict)
    autosignals: bool = os.getenv('AUTOSIGNALS', '0') == '1'
    last_auto_sent: Dict[str, Any] = field(default_factory=dict)


state = BotState()

AUTOSIGNAL_INTERVAL = int(os.getenv('AUTOSIGNAL_INTERVAL', '20'))  # seconds between scans
AUTOSIGNAL_SYMBOLS = [s.strip().upper() for s in os.getenv('AUTOSIGNAL_SYMBOLS', SYMBOL).split(',') if s.strip()]
# AUTOSIGNAL_TOLERANCE_PIPS used to detect duplicates
AUTOSIGNAL_TOLERANCE_PIPS = float(os.getenv('AUTOSIGNAL_TOLERANCE_PIPS', '1.0'))
DB_PATH = os.path.join(os.path.dirname(__file__), 'bot_state.db')
# default strategy name (can be overridden via .env)
DEFAULT_STRATEGY = os.getenv('DEFAULT_STRATEGY', 'ema50_200')
# default autosignal symbols: EURUSD and XAUUSD; BTCUSDT can be added via env
if not AUTOSIGNAL_SYMBOLS or AUTOSIGNAL_SYMBOLS == ['']:
    AUTOSIGNAL_SYMBOLS = ['EURUSD', 'XAUUSD']

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
        risk_manager = create_risk_manager()
        advanced_filter = create_advanced_filter()
        logger.info("Gestores de riesgo inicializados correctamente")
    except Exception as e:
        logger.error(f"Error inicializando gestores de riesgo: {e}")
        # Crear gestores dummy para evitar errores
        risk_manager = None
        advanced_filter = None


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS autosignals(state INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS last_auto_sent(symbol TEXT PRIMARY KEY, time TEXT, type TEXT, entry REAL, sl REAL, tp REAL)')
    conn.commit()
    conn.close()


def load_db_state():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT state FROM autosignals LIMIT 1')
    r = c.fetchone()
    if r is not None:
        state.autosignals = bool(r[0])
    # load trades_today for today (UTC)
    c.execute("CREATE TABLE IF NOT EXISTS trades_counter(date TEXT PRIMARY KEY, count INTEGER)")
    today = datetime.now(timezone.utc).date().isoformat()
    c.execute('SELECT count FROM trades_counter WHERE date=?', (today,))
    tr = c.fetchone()
    if tr is not None:
        state.trades_today = int(tr[0])
    else:
        state.trades_today = 0
    c.execute('SELECT symbol,time,type,entry,sl,tp FROM last_auto_sent')
    rows = c.fetchall()
    for sym, time_s, t, entry, sl, tp in rows:
        try:
            time_dt = datetime.fromisoformat(time_s)
        except Exception:
            time_dt = datetime.now(timezone.utc)
        state.last_auto_sent[sym] = {'time': time_dt, 'sig': (t, entry, sl, tp)}
    conn.close()


def save_autosignals_state(val: bool):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM autosignals')
    c.execute('INSERT INTO autosignals(state) VALUES(?)', (1 if val else 0,))
    conn.commit()
    conn.close()
    state.autosignals = bool(val)


def save_last_auto_sent(sym: str, time_dt: datetime, sig_tuple):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO last_auto_sent(symbol,time,type,entry,sl,tp) VALUES(?,?,?,?,?,?)',
              (sym, time_dt.isoformat(), sig_tuple[0], float(sig_tuple[1]), float(sig_tuple[2]), float(sig_tuple[3])))
    conn.commit()
    conn.close()
    state.last_auto_sent[sym] = {'time': time_dt, 'sig': sig_tuple}


def save_trades_today():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS trades_counter(date TEXT PRIMARY KEY, count INTEGER)")
    today = datetime.now(timezone.utc).date().isoformat()
    c.execute('INSERT OR REPLACE INTO trades_counter(date,count) VALUES(?,?)', (today, int(state.trades_today)))
    conn.commit()
    conn.close()


def reset_trades_today():
    state.trades_today = 0
    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        today = datetime.now(timezone.utc).date().isoformat()
        c.execute('INSERT OR REPLACE INTO trades_counter(date,count) VALUES(?,?)', (today, 0))
        conn.commit()
        conn.close()
    except Exception:
        logger.exception('Failed to reset trades counter in DB')


def signals_similar(sig_a, sig_b_tuple, tol_pips: float, symbol: str) -> bool:
    """Compare signal dict `sig_a` to stored tuple (type, entry, sl, tp) using a pip tolerance."""
    if not sig_b_tuple:
        return False
    try:
        si = mt5.symbol_info(symbol)
        point = float(getattr(si, 'point', 0.0001)) if si is not None else 0.0001
    except Exception:
        point = 0.0001

    type_a = sig_a.get('type')
    type_b = sig_b_tuple[0]
    if type_a != type_b:
        return False

    entry_a = float(sig_a.get('entry', 0))
    sl_a = float(sig_a.get('sl', 0))
    tp_a = float(sig_a.get('tp', 0))
    entry_b = float(sig_b_tuple[1])
    sl_b = float(sig_b_tuple[2])
    tp_b = float(sig_b_tuple[3])

    tol = tol_pips * point
    if abs(entry_a - entry_b) > tol:
        return False
    if abs(sl_a - sl_b) > tol:
        return False
    if abs(tp_a - tp_b) > tol:
        return False
    return True

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

def _detect_signal_wrapper(df, symbol: str | None = None):
    """Wrapper que selects per-symbol strategy/config y calls detect_signal_advanced con filtros avanzados.
    Incluye sistema de fallback para estrategias más simples cuando las avanzadas fallan.

    Returns (signal_dict or None, df_with_indicators, risk_info).
    """
    sym = (symbol or SYMBOL or '').upper()
    # choose strategy: rules config override -> env var -> default
    env_strategy = os.getenv('AUTOSIGNAL_RULE', os.getenv('DEFAULT_STRATEGY', 'ema50_200'))
    cfg = RULES_CONFIG.get(sym, {}) or {}
    strategy = cfg.get('strategy') or env_strategy
    
    # Obtener configuración global
    global_cfg = RULES_CONFIG.get('GLOBAL_SETTINGS', {})
    confidence_filter = global_cfg.get('notification_settings', {}).get('signal_confidence_filter', 'MEDIUM')
    
    try:
        # Obtener balance actual para filtros de drawdown
        current_balance = 5000.0  # Default demo balance
        try:
            mt5_initialize()
            account_info = mt5.account_info()
            if account_info:
                current_balance = account_info.balance
        except Exception:
            logger.warning("No se pudo obtener balance de MT5, usando balance por defecto")
        
        # 1. Intentar estrategia principal (avanzada)
        sig, df2, advanced_info = detect_signal_advanced(
            df, 
            strategy=strategy, 
            config=cfg, 
            current_balance=current_balance
        )
        
        if sig:
            # Verificar si la confianza cumple el filtro
            signal_confidence = sig.get('confidence', 'LOW')
            if confidence_filter == 'HIGH' and signal_confidence not in ['HIGH']:
                return None, df2, {
                    'rejected': True,
                    'reason': f'Confianza {signal_confidence} no cumple filtro {confidence_filter}',
                    'advanced_info': advanced_info
                }
            elif confidence_filter == 'MEDIUM' and signal_confidence not in ['HIGH', 'MEDIUM']:
                return None, df2, {
                    'rejected': True,
                    'reason': f'Confianza {signal_confidence} no cumple filtro {confidence_filter}',
                    'advanced_info': advanced_info
                }
            
            # Estrategia principal funcionó y cumple filtros
            return sig, df2, {
                'approved': True,
                'strategy_used': strategy,
                'confidence': sig.get('confidence', 'MEDIUM'),
                'advanced_info': advanced_info
            }
        
        # 2. Si no hay señal y está habilitado fallback, intentar estrategia simple
        use_fallback = cfg.get('use_fallback', False)
        fallback_strategy = cfg.get('fallback_strategy', 'ema50_200')
        
        if use_fallback and fallback_strategy and confidence_filter != 'HIGH':
            # Solo usar fallback si no se requiere confianza HIGH
            fallback_sig, fallback_df = detect_signal(df, strategy=fallback_strategy, config=cfg)
            
            if fallback_sig:
                # Verificar R:R mínimo para fallback
                min_rr = cfg.get('min_rr_ratio', 2.0)
                entry = float(fallback_sig.get('entry', 0))
                sl = float(fallback_sig.get('sl', 0))
                tp = float(fallback_sig.get('tp', 0))
                
                if entry != 0 and sl != 0 and tp != 0:
                    rr_ratio = abs((tp - entry) / (entry - sl)) if (entry - sl) != 0 else 0
                    if rr_ratio < min_rr:
                        return None, df2, {
                            'rejected': True,
                            'reason': f'R:R fallback {rr_ratio:.2f} < mínimo {min_rr}',
                            'advanced_info': advanced_info
                        }
                
                # Añadir información de que es fallback
                fallback_sig['strategy'] = f"{fallback_strategy}_fallback"
                fallback_sig['confidence'] = 'MEDIUM'  # Siempre medium para fallback
                fallback_sig['explanation'] = f"Fallback: {fallback_sig.get('explanation', '')}"
                
                return fallback_sig, fallback_df, {
                    'approved': True,
                    'strategy_used': fallback_strategy,
                    'is_fallback': True,
                    'confidence': 'MEDIUM',
                    'original_strategy': strategy,
                    'fallback_reason': advanced_info.get('reason', 'Estrategia principal no generó señal')
                }
        
        # 3. DESHABILITADO: No usar estrategia de emergencia para evitar spam
        # El emergency fallback está deshabilitado en la configuración
        
        # 4. No se pudo generar ninguna señal
        return None, df2, {
            'rejected': True,
            'reason': advanced_info.get('reason', 'No hay señal básica válida'),
            'advanced_info': advanced_info,
            'strategies_tried': [strategy, fallback_strategy] if use_fallback else [strategy]
        }
        
    except Exception:
        logger.exception('Error in _detect_signal_wrapper for %s', sym)
        return None, df, {'error': 'Error en wrapper de señales'}


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
        load_db_state()
        log_event(f'Estado cargado: AUTOSIGNALS={state.autosignals}')
    except Exception:
        log_event("Error cargando estado de la base de datos", "ERROR")
        logger.exception('Failed to load DB state')
    
    # start autosignal background task
    bot.loop.create_task(_auto_signal_loop())
    
    # start trailing stops background task
    if TRAILING_STOPS_AVAILABLE:
        bot.loop.create_task(_trailing_stops_loop())
        log_event("Sistema de trailing stops iniciado")
    
    # start market opening alerts background task
    if MARKET_OPENING_AVAILABLE:
        bot.loop.create_task(_market_opening_loop())
        log_event("Sistema de alertas de apertura iniciado")
    
    # start live dashboard
    try:
        start_live_dashboard()
        log_event("Dashboard live iniciado - Actualización cada 5 minutos")
    except Exception as e:
        log_event(f"Error iniciando dashboard live: {e}", "ERROR")
        logger.exception("Failed to start live dashboard")
    
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
    
    log_event("Bot completamente inicializado y listo para operar")
    
    # Mostrar información del archivo de log
    if current_log_file:
        log_filename = os.path.basename(current_log_file)
        log_event(f"📝 Archivo de log: {log_filename}")
        log_event(f"📁 Ruta completa: {current_log_file}")

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
    # Incrementar contador y persistir
    state.trades_today += 1
    try:
        save_trades_today()
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

@bot.command()
async def backtest_stats(ctx, days: int = 7):
    """Muestra estadísticas de backtesting de los últimos N días"""
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    
    try:
        stats = backtest_tracker.get_statistics(days)
        
        if "error" in stats:
            await ctx.send(f"❌ {stats['error']}")
            return
        
        embed = discord.Embed(
            title=f"📊 Estadísticas de Backtesting - Últimos {days} días",
            color=0x00ff00 if stats['total_pnl'] > 0 else 0xff0000,
            timestamp=datetime.now()
        )
        
        # Estadísticas generales
        embed.add_field(
            name="📈 Resumen General",
            value=f"**Total Señales:** {stats['total_signals']}\n"
                  f"**Cerradas:** {stats['closed_signals']}\n"
                  f"**Pendientes:** {stats['pending_signals']}\n"
                  f"**Win Rate:** {stats['win_rate']}%",
            inline=True
        )
        
        embed.add_field(
            name="💰 P&L",
            value=f"**Total:** {stats['total_pnl']} EUR\n"
                  f"**Ganancia Prom:** {stats['average_win']} EUR\n"
                  f"**Pérdida Prom:** {stats['average_loss']} EUR\n"
                  f"**Factor Beneficio:** {stats['profit_factor']}",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Resultados",
            value=f"**Ganadoras:** {stats['wins']}\n"
                  f"**Perdedoras:** {stats['losses']}\n"
                  f"**Breakeven:** {stats['breakevens']}",
            inline=True
        )
        
        # Por símbolo
        if stats['symbols']:
            symbol_text = ""
            for symbol, data in stats['symbols'].items():
                symbol_text += f"**{symbol}:** {data['win_rate']:.1f}% ({data['wins']}/{data['total_signals']}) | {data['total_pnl']:.2f} EUR\n"
            embed.add_field(name="📊 Por Símbolo", value=symbol_text[:1024], inline=False)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error generando estadísticas: {e}")

@bot.command()
async def backtest_report(ctx, days: int = 30):
    """Genera un reporte HTML de backtesting"""
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    
    try:
        html_content = backtest_tracker.generate_html_report(days)
        
        # Guardar el reporte en un archivo temporal
        filename = f"backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        await ctx.send(
            f"📊 **Reporte de Backtesting generado**\n"
            f"Período: Últimos {days} días\n"
            f"Archivo: `{filename}`",
            file=discord.File(filename)
        )
        
        # Limpiar archivo temporal
        try:
            os.remove(filename)
        except:
            pass
            
    except Exception as e:
        await ctx.send(f"❌ Error generando reporte: {e}")

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

@bot.tree.command(name="help")
async def slash_help(interaction: discord.Interaction):
    """Muestra comandos disponibles y guía de uso (solo administrador)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    embed = discord.Embed(
        title="🤖 Bot MT5 - Guía de Comandos",
        description="Sistema de trading automatizado para EURUSD, XAUUSD y BTCEUR",
        color=0x00ff88
    )
    
    # Comandos principales
    embed.add_field(
        name="🎯 **Comandos de Trading**",
        value=(
            "`/signal [símbolo]` - Detecta señal con filtros avanzados\n"
            "`/test_signal [símbolo]` - Genera señal de prueba\n"
            "`/force_autosignal [símbolo]` - Fuerza señal automática\n"
            "`/chart [símbolo]` - Genera gráfico profesional\n"
            "`/accept [id]` - Acepta señal pendiente\n"
            "`/reject [id]` - Rechaza señal pendiente"
        ),
        inline=False
    )
    
    # Comandos de gestión
    embed.add_field(
        name="📊 **Comandos de Análisis**",
        value=(
            "`/demo_stats` - Estadísticas de cuenta demo\n"
            "`/performance [días]` - Reporte de performance\n"
            "`/strategy_performance [días]` - Performance por estrategia\n"
            "`/risk_status` - Estado de gestión de riesgo\n"
            "`/positions` - Lista posiciones abiertas\n"
            "`/market_overview` - Resumen del mercado actual\n"
            "`/next_opening` - Próxima apertura de mercado\n"
            "`/pre_market_analysis [símbolo]` - Análisis pre-mercado"
        ),
        inline=False
    )
    
    # Comandos de backtesting
    embed.add_field(
        name="📈 **Comandos de Backtesting**",
        value=(
            "`backtest_stats [días]` - Estadísticas de señales\n"
            "`backtest_report [días]` - Reporte HTML completo\n"
            "\n*Rastrea todas las señales generadas y sus resultados*"
        ),
        inline=False
    )
    
    # Comandos de configuración
    embed.add_field(
        name="⚙️ **Comandos de Configuración**",
        value=(
            "`/autosignals [on/off]` - Control señales automáticas\n"
            "`/set_strategy [símbolo] [estrategia]` - Cambiar estrategia\n"
            "`/set_mt5_credentials` - Configurar MT5\n"
            "`/mt5_login` - Conectar a MT5\n"
            "`/status` - Estado general del bot"
        ),
        inline=False
    )
    
    # Información adicional
    embed.add_field(
        name="💡 **Sugerencias de Uso**",
        value=(
            "• Usa `/demo_stats` para monitorear progreso diario\n"
            "• Revisa `/strategy_performance 7` semanalmente\n"
            "• Prueba `/test_signal EURUSD` para ver el sistema\n"
            "• Configura MT5 con `/set_mt5_credentials` primero\n"
            "• Crea canal `#signals` para señales automáticas\n"
            "• Usa `/next_opening` para anticipar aperturas\n"
            "• Revisa `/pre_market_analysis` antes de sesiones"
        ),
        inline=False
    )
    
    # Pares principales
    embed.add_field(
        name="📈 **Pares Principales**",
        value=(
            "🇪🇺 **EURUSD** - Breakout de consolidación\n"
            "🥇 **XAUUSD** - Reversión en niveles clave\n"
            "₿ **BTCEUR** - Momentum crypto\n"
            "\n*Cada par usa estrategia específica optimizada*"
        ),
        inline=False
    )
    
    embed.set_footer(text="Bot MT5 v2.0 | Modo Demo Agresivo | 3 Pares Principales")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def _find_signals_channel():
    # find first channel matching SIGNALS_CHANNEL_NAME across guilds
    for g in bot.guilds:
        for ch in g.text_channels:
            if ch.name == SIGNALS_CHANNEL_NAME:
                return ch
    return None


async def _auto_signal_loop():
    await bot.wait_until_ready()
    log_event(f'Auto-signal loop iniciado (AUTOSIGNALS={state.autosignals}, AUTO_EXECUTE={AUTO_EXECUTE_SIGNALS})')
    
    scan_count = 0
    while True:
        try:
            if state.autosignals and not KILL_SWITCH:
                scan_count += 1
                if scan_count % 10 == 1:  # Log cada 10 escaneos (cada ~3 minutos)
                    log_event(f"🔍 AUTOSIGNAL SCAN: Checking {len(AUTOSIGNAL_SYMBOLS)} pairs...")
                
                ch = await _find_signals_channel()
                if ch is None:
                    if scan_count % 50 == 1:  # Log error cada 50 escaneos
                        log_event('Canal #signals no encontrado para autosignals', "WARNING")
                else:
                    signals_found = 0
                    for sym in AUTOSIGNAL_SYMBOLS:
                        # throttle per symbol and avoid reposting identical signals
                        now = datetime.now(timezone.utc)
                        last = state.last_auto_sent.get(sym)
                        if last:
                            last_time = last.get('time')
                            last_sig = last.get('sig')
                        else:
                            last_time = None
                            last_sig = None
                        # small throttle to avoid tight loops
                        if last_time and (now - last_time) < timedelta(seconds=AUTOSIGNAL_INTERVAL * 1):
                            continue
                        try:
                            connect_mt5()
                            df = get_candles(sym, TIMEFRAME, CANDLES)
                            # choose per-symbol strategy if configured
                            strat = AUTOSIGNAL_RULES.get(sym, 'ema')
                            # pick per-symbol config if available
                            # prefer explicit strategy in per-symbol config if present
                            cfg = RULES_CONFIG.get(sym.upper(), {}) or {}
                            strat = cfg.get('strategy') or strat
                            sig, df2, risk_info = _detect_signal_wrapper(df, symbol=sym)
                            if sig:
                                signals_found += 1
                                # fingerprint the signal by type and raw prices
                                fingerprint = (sig.get('type'), float(sig.get('entry', 0)), float(sig.get('sl', 0)), float(sig.get('tp', 0)))
                                # if identical (within tolerance in pips) to last sent and within longer cooldown, skip
                                if last_sig and signals_similar(sig, last_sig, AUTOSIGNAL_TOLERANCE_PIPS, sym) and last_time and (now - last_time) < timedelta(seconds=AUTOSIGNAL_INTERVAL * 10):
                                    logger.debug('Skipping duplicate auto-signal for %s (recent identical within tolerance)', sym)
                                    # update last sent time to avoid tight loops
                                    save_last_auto_sent(sym, now, last_sig)
                                    state.last_auto_sent[sym] = {'time': now, 'sig': last_sig}
                                    continue

                                sid = max(state.pending_signals.keys(), default=0) + 1
                                state.pending_signals[sid] = sig
                                
                                # BACKTEST TRACKING: Registrar nueva señal
                                try:
                                    signal_data = {
                                        "symbol": sig.get('symbol', sym),
                                        "direction": sig.get('type'),
                                        "entry_price": sig.get('entry'),
                                        "stop_loss": sig.get('sl'),
                                        "take_profit": sig.get('tp'),
                                        "confidence": sig.get('confidence', 'MEDIUM'),
                                        "strategy": strategy_used,
                                        "risk_reward": sig.get('rr_ratio', 0),
                                        "lot_size": sig.get('lot_size', 0),
                                        "notes": f"Autoseñal - {'Fallback' if is_fallback else 'Principal'} - {'Emergency' if is_emergency else 'Normal'}"
                                    }
                                    backtest_id = backtest_tracker.add_signal(signal_data)
                                    # Asociar el ID de backtest con el ID de señal del bot
                                    sig['backtest_id'] = backtest_id
                                    state.pending_signals[sid] = sig
                                except Exception as e:
                                    logger.error(f"Error registrando señal en backtest: {e}")
                                
                                # Log nueva señal con información de estrategia
                                confidence = sig.get('confidence', 'MEDIUM')
                                strategy_used = risk_info.get('strategy_used', 'unknown')
                                is_fallback = risk_info.get('is_fallback', False)
                                is_emergency = risk_info.get('is_emergency', False)
                                
                                if is_emergency:
                                    strategy_label = f"{strategy_used} (EMERGENCY)"
                                elif is_fallback:
                                    strategy_label = f"{strategy_used} (FALLBACK)"
                                else:
                                    strategy_label = strategy_used
                                
                                log_event(f"✅ SIGNAL GENERATED: {sym} [{strategy_label}] {sig.get('type')} @ {sig.get('entry'):.5f} | Confidence: {confidence}")
                                
                                text = (
                                    f"🎯 **SEÑAL AUTOMÁTICA** (ID {sid})\n"
                                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                    f"📊 **{sig['symbol']}** | Estrategia: `{sig.get('strategy', 'N/A')}`\n"
                                    f"🔄 **{sig['type']}** | Confianza: `{sig.get('confidence', 'MEDIUM')}`\n"
                                    f"\n📈 **Niveles de Trading:**\n"
                                    f"• **Entrada:** `{sig['entry']:.5f}`\n"
                                    f"• **Stop Loss:** `{sig['sl']:.5f}`\n"
                                    f"• **Take Profit:** `{sig['tp']:.5f}`\n"
                                    f"\n💡 **Análisis:** {sig.get('explanation','-')}\n"
                                    f"\n⏱️ **Válida por:** {sig.get('expires', datetime.now(timezone.utc) + timedelta(minutes=30)).strftime('%H:%M')} GMT\n"
                                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🎮 **Comandos:** `/accept {sid}` | `/reject {sid}`"
                                )
                                try:
                                    # Asegurar que el símbolo sea un string
                                    chart_symbol = sig.get('symbol', sym)
                                    if hasattr(chart_symbol, 'iloc'):
                                        chart_symbol = str(chart_symbol.iloc[0]) if len(chart_symbol) > 0 else sym
                                    elif not isinstance(chart_symbol, str):
                                        chart_symbol = str(chart_symbol)
                                    
                                    logger.debug(f"Generating autosignal chart for symbol: {chart_symbol}")
                                    chart = generate_chart(df2, symbol=chart_symbol, signal=sig)
                                except Exception as e:
                                    logger.error(f"Autosignal chart generation failed: {e}")
                                    chart = None
                                if chart:
                                    await ch.send(text, file=discord.File(chart))
                                    try:
                                        os.remove(chart)
                                    except Exception:
                                        pass
                                else:
                                    await ch.send(text)
                                # record now and fingerprint (persist)
                                save_last_auto_sent(sym, now, fingerprint)
                                state.last_auto_sent[sym] = {'time': now, 'sig': fingerprint}
                            else:
                                # Log señal rechazada
                                reason = risk_info.get('reason', 'No hay señal básica válida') if risk_info else 'Sin información de riesgo'
                                log_event(f"❌ SIGNAL REJECTED: {sym} | Reason: {reason}")
                        except Exception:
                            log_event(f"❌ ERROR scanning {sym}", "ERROR")
                            logger.exception('Error scanning symbol %s', sym)
                    
                    # Log resumen cada cierto tiempo
                    if scan_count % 30 == 0:  # Cada 30 escaneos (~10 minutos)
                        log_event(f"Escaneo #{scan_count}: {signals_found} señales encontradas")
            
            await asyncio.sleep(AUTOSIGNAL_INTERVAL)
        except Exception:
            logger.exception('Auto-signal loop crashed; retrying in 30s')
            await asyncio.sleep(30)


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
                            save_trades_today()
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
                            save_trades_today()
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
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    symbol = symbol.upper()
    # restrict charts to symbols that have rules (only show charts for these pairs)
    ALLOWED = ['EURUSD','XAUUSD','BTCEUR']
    if symbol not in ALLOWED:
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
        # remove file after sending to avoid stale reuse
        try:
            import os
            os.remove(filename)
        except Exception:
            pass
    except Exception as e:
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


@bot.tree.command(name="autosignals")
async def slash_autosignals(interaction: discord.Interaction):
    """Muestra estado detallado de las señales automáticas con controles."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    # Mostrar estado detallado con botones de control
    embed = discord.Embed(
        title="🤖 Estado de Autosignals",
        description=f"Sistema: {'🟢 **ACTIVO**' if state.autosignals else '🔴 **INACTIVO**'}",
        color=0x00ff00 if state.autosignals else 0xff0000
    )
    
    # Configuración actual
    embed.add_field(
        name="⚙️ Configuración",
        value=(
            f"• **Intervalo:** {AUTOSIGNAL_INTERVAL}s\n"
            f"• **Símbolos:** {len(AUTOSIGNAL_SYMBOLS)} pares\n"
            f"• **Tolerancia:** {AUTOSIGNAL_TOLERANCE_PIPS} pips"
        ),
        inline=True
    )
    
    # Verificar canal
    ch = await _find_signals_channel()
    channel_status = f"#{ch.name} ✅" if ch else f"❌ '{SIGNALS_CHANNEL_NAME}' no encontrado"
    
    # Verificar MT5
    try:
        from mt5_client import initialize as mt5_initialize
        mt5_ok = mt5_initialize()
        mt5_status = "✅ Conectado" if mt5_ok else "❌ Desconectado"
    except Exception:
        mt5_status = "❌ Error"
    
    embed.add_field(
        name="🔗 Conexiones",
        value=(
            f"• **Canal:** {channel_status}\n"
            f"• **MT5:** {mt5_status}\n"
            f"• **Filtros:** {'✅ Activos' if os.getenv('ADVANCED_FILTERS') == '1' else '❌ Inactivos'}"
        ),
        inline=True
    )
    
    # Estrategias por símbolo
    strategies_info = []
    for symbol in AUTOSIGNAL_SYMBOLS:
        cfg = RULES_CONFIG.get(symbol.upper(), {})
        strategy = cfg.get('strategy', 'N/A')
        enabled = "✅" if cfg.get('enabled', False) else "❌"
        strategies_info.append(f"{enabled} **{symbol}:** `{strategy}`")
    
    embed.add_field(
        name="📊 Estrategias por Par",
        value="\n".join(strategies_info),
        inline=False
    )
    
    # Estadísticas recientes
    if risk_manager:
        try:
            recent_perf = risk_manager.get_recent_performance(1)  # Último día
            embed.add_field(
                name="📈 Últimas 24h",
                value=(
                    f"• **Trades:** {recent_perf.get('total_trades', 0)}\n"
                    f"• **Tasa acierto:** {recent_perf.get('win_rate', 0)*100:.1f}%\n"
                    f"• **Racha actual:** {recent_perf.get('winning_streak', 0)}W / {recent_perf.get('losing_streak', 0)}L"
                ),
                inline=True
            )
        except Exception:
            pass
    
    # Crear botones de control
    class AutosignalsControlView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)  # 5 minutos de timeout
        
        @discord.ui.button(
            label='🟢 Activar' if not state.autosignals else '🔴 Desactivar',
            style=discord.ButtonStyle.success if not state.autosignals else discord.ButtonStyle.danger,
            emoji='▶️' if not state.autosignals else '⏹️'
        )
        async def toggle_autosignals(self, interaction_btn: discord.Interaction, button: discord.ui.Button):
            if interaction_btn.user.id != AUTHORIZED_USER_ID:
                await interaction_btn.response.send_message('⛔ No autorizado', ephemeral=True)
                return
            
            # Cambiar estado
            new_state = not state.autosignals
            state.autosignals = new_state
            
            log_event(f"🔄 AUTOSIGNALS {'ACTIVADAS' if new_state else 'DESACTIVADAS'} por usuario")
            
            try:
                save_autosignals_state(new_state)
            except Exception:
                log_event("❌ Error guardando estado de autosignals", "ERROR")
                logger.exception('Failed to save autosignals state')
            
            # Actualizar embed
            new_embed = discord.Embed(
                title="🤖 Estado de Autosignals",
                description=f"Sistema: {'🟢 **ACTIVO**' if new_state else '🔴 **INACTIVO**'}",
                color=0x00ff00 if new_state else 0xff0000
            )
            
            # Configuración actual
            new_embed.add_field(
                name="⚙️ Configuración",
                value=(
                    f"• **Intervalo:** {AUTOSIGNAL_INTERVAL}s\n"
                    f"• **Símbolos:** {len(AUTOSIGNAL_SYMBOLS)} pares\n"
                    f"• **Tolerancia:** {AUTOSIGNAL_TOLERANCE_PIPS} pips"
                ),
                inline=True
            )
            
            new_embed.add_field(
                name="🔗 Conexiones",
                value=(
                    f"• **Canal:** {channel_status}\n"
                    f"• **MT5:** {mt5_status}\n"
                    f"• **Filtros:** {'✅ Activos' if os.getenv('ADVANCED_FILTERS') == '1' else '❌ Inactivos'}"
                ),
                inline=True
            )
            
            new_embed.add_field(
                name="📊 Estrategias por Par",
                value="\n".join(strategies_info),
                inline=False
            )
            
            # Actualizar botón
            button.label = '🟢 Activar' if not new_state else '🔴 Desactivar'
            button.style = discord.ButtonStyle.success if not new_state else discord.ButtonStyle.danger
            button.emoji = '▶️' if not new_state else '⏹️'
            
            status_msg = "✅ **Autosignals ACTIVADAS**" if new_state else "🔴 **Autosignals DESACTIVADAS**"
            new_embed.set_footer(text=f"{status_msg} | Actualizado")
            
            await interaction_btn.response.edit_message(embed=new_embed, view=self)
        
        @discord.ui.button(
            label='🔄 Actualizar',
            style=discord.ButtonStyle.secondary,
            emoji='🔄'
        )
        async def refresh_status(self, interaction_btn: discord.Interaction, button: discord.ui.Button):
            if interaction_btn.user.id != AUTHORIZED_USER_ID:
                await interaction_btn.response.send_message('⛔ No autorizado', ephemeral=True)
                return
            
            # Recrear el embed con datos actualizados
            await interaction_btn.response.send_message("🔄 Estado actualizado", ephemeral=True)
    
    embed.set_footer(text="Usa los botones para controlar las autosignals")
    
    view = AutosignalsControlView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="set_mt5_credentials")
async def slash_set_mt5_credentials(interaction: discord.Interaction):
    """Abre un modal para introducir credenciales MT5 (slash)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    # show the same modal class used for the text command
    await interaction.response.send_modal(MT5CredentialsModal())


@bot.tree.command(name="pairs_config")
async def slash_pairs_config(interaction: discord.Interaction):
    """Muestra la configuración actual de los pares principales (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    embed = discord.Embed(
        title="📊 Configuración de Pares Principales",
        description="Estrategias y parámetros optimizados para cada par",
        color=0x0099ff
    )
    
    main_pairs = ['EURUSD', 'XAUUSD', 'BTCEUR']
    
    for symbol in main_pairs:
        cfg = RULES_CONFIG.get(symbol, {})
        
        if not cfg:
            continue
            
        status = "🟢 Activo" if cfg.get('enabled', False) else "🔴 Inactivo"
        strategy = cfg.get('strategy', 'N/A')
        risk = cfg.get('risk_per_trade', 0)
        max_trades = cfg.get('max_daily_trades', 0)
        rr_ratio = cfg.get('min_rr_ratio', 0)
        
        # Emojis por par
        emoji = {"EURUSD": "🇪🇺", "XAUUSD": "🥇", "BTCEUR": "₿"}.get(symbol, "📈")
        
        embed.add_field(
            name=f"{emoji} **{symbol}**",
            value=(
                f"**Estado:** {status}\n"
                f"**Estrategia:** `{strategy}`\n"
                f"**Riesgo:** {risk}% por trade\n"
                f"**Trades/día:** {max_trades} máximo\n"
                f"**R:R mínimo:** 1:{rr_ratio}\n"
                f"**Descripción:** {cfg.get('description', 'N/A')}"
            ),
            inline=True
        )
    
    # Configuración global
    global_cfg = RULES_CONFIG.get('GLOBAL_SETTINGS', {})
    embed.add_field(
        name="🌐 **Configuración Global**",
        value=(
            f"**Riesgo total diario:** {global_cfg.get('max_total_risk', 0)}%\n"
            f"**Trades totales/día:** {global_cfg.get('max_daily_trades_all', 0)}\n"
            f"**Posiciones simultáneas:** {global_cfg.get('max_simultaneous_positions', 0)}\n"
            f"**Límite drawdown:** {global_cfg.get('drawdown_limit', 0)}%"
        ),
        inline=False
    )
    
    embed.set_footer(text="Usa '/set_strategy [par] [estrategia]' para cambiar configuración")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="market_overview")
async def slash_market_overview(interaction: discord.Interaction):
    """Muestra un resumen del estado actual del mercado para los 3 pares (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    try:
        embed = discord.Embed(
            title="🌍 Resumen del Mercado",
            description="Estado actual de los 3 pares principales",
            color=0x00ff88
        )
        
        main_pairs = ['EURUSD', 'XAUUSD', 'BTCEUR']
        
        for symbol in main_pairs:
            try:
                # Obtener datos actuales
                connect_mt5()
                df = get_candles(symbol, TIMEFRAME, 50)
                
                if len(df) < 10:
                    continue
                
                # Calcular indicadores básicos
                current_price = df['close'].iloc[-1]
                prev_price = df['close'].iloc[-2]
                change = current_price - prev_price
                change_pct = (change / prev_price) * 100
                
                # EMAs básicas
                ema20 = df['close'].ewm(span=20).mean().iloc[-1]
                ema50 = df['close'].ewm(span=50).mean().iloc[-1]
                
                # Tendencia
                if current_price > ema20 > ema50:
                    trend = "📈 Alcista"
                elif current_price < ema20 < ema50:
                    trend = "📉 Bajista"
                else:
                    trend = "➡️ Lateral"
                
                # Volatilidad
                atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
                volatility = "Alta" if atr > df['close'].std() else "Normal"
                
                # Emoji por par
                emoji = {"EURUSD": "🇪🇺", "XAUUSD": "🥇", "BTCEUR": "₿"}.get(symbol, "📈")
                
                # Formatear precio según el símbolo
                if symbol == 'XAUUSD':
                    price_str = f"{current_price:.2f}"
                    change_str = f"{change:+.2f}"
                elif symbol == 'BTCEUR':
                    price_str = f"{current_price:.0f}"
                    change_str = f"{change:+.0f}"
                else:  # EURUSD
                    price_str = f"{current_price:.5f}"
                    change_str = f"{change:+.5f}"
                
                embed.add_field(
                    name=f"{emoji} **{symbol}**",
                    value=(
                        f"**Precio:** {price_str}\n"
                        f"**Cambio:** {change_str} ({change_pct:+.2f}%)\n"
                        f"**Tendencia:** {trend}\n"
                        f"**Volatilidad:** {volatility}"
                    ),
                    inline=True
                )
                
            except Exception as e:
                embed.add_field(
                    name=f"❌ **{symbol}**",
                    value=f"Error obteniendo datos: {str(e)[:50]}...",
                    inline=True
                )
        
        # Información de sesión actual
        now_utc = datetime.now(timezone.utc)
        now_spain = now_utc.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=1)))  # España GMT+1
        hour_utc = now_utc.hour
        
        if 0 <= hour_utc <= 9:
            session = "🌅 Sesión Asiática (Tokio)"
        elif 8 <= hour_utc <= 17:
            session = "🌍 Sesión Europea (Londres)"
        elif 13 <= hour_utc <= 22:
            session = "🌎 Sesión Americana (Nueva York)"
        else:
            session = "🌙 Fuera de sesiones principales"
        
        if 13 <= hour_utc <= 17:
            session += " | 🔥 **OVERLAP LONDRES-NY**"
        
        embed.add_field(
            name="🕐 **Sesión Actual**",
            value=(
                f"{session}\n"
                f"**Hora GMT:** {now_utc.strftime('%H:%M')}\n"
                f"**Hora España:** {now_spain.strftime('%H:%M')} (GMT+1)"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Actualizado: {now_utc.strftime('%Y-%m-%d %H:%M')} GMT | {now_spain.strftime('%H:%M')} España")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error obteniendo resumen del mercado: {e}")


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


@bot.tree.command(name="demo_stats")
async def slash_demo_stats(interaction: discord.Interaction):
    """Muestra estadísticas específicas del modo demo (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    try:
        # Obtener balance actual
        mt5_initialize()
        account_info = mt5.account_info()
        if not account_info:
            await interaction.followup.send("❌ No se pudo conectar a MT5")
            return
        
        balance = account_info.balance
        equity = account_info.equity
        margin = account_info.margin
        free_margin = account_info.margin_free
        
        # Calcular estadísticas
        initial_balance = 5000.0  # Balance inicial demo
        total_pnl = balance - initial_balance
        pnl_percentage = (total_pnl / initial_balance) * 100
        
        # Obtener posiciones abiertas
        positions = mt5.positions_get()
        open_positions = len(positions) if positions else 0
        
        # Calcular PnL de posiciones abiertas
        open_pnl = sum(pos.profit for pos in positions) if positions else 0
        
        lines = [
            f"💰 **ESTADÍSTICAS CUENTA DEMO**",
            f"",
            f"💵 **Balance y Equity:**",
            f"• Balance inicial: ${initial_balance:,.2f}",
            f"• Balance actual: ${balance:,.2f}",
            f"• Equity: ${equity:,.2f}",
            f"• PnL total: ${total_pnl:,.2f} ({pnl_percentage:+.2f}%)",
            f"",
            f"📊 **Margen:**",
            f"• Margen usado: ${margin:,.2f}",
            f"• Margen libre: ${free_margin:,.2f}",
            f"• Nivel de margen: {(equity/margin*100):.1f}%" if margin > 0 else "• Nivel de margen: N/A",
            f"",
            f"🎯 **Posiciones:**",
            f"• Posiciones abiertas: {open_positions}",
            f"• PnL posiciones abiertas: ${open_pnl:,.2f}",
            f"",
            f"⚙️ **Configuración Actual:**",
            f"• Modo: {'🟢 DEMO AGRESIVO' if os.getenv('DEMO_MODE') == '1' else '🔴 CONSERVADOR'}",
            f"• Riesgo por trade: {os.getenv('DEFAULT_RISK_PCT', '1.0')}%",
            f"• Trades máximos/día: {os.getenv('MAX_TRADES_PER_DAY', '12')}",
            f"• Intervalo autosignals: {os.getenv('AUTOSIGNAL_INTERVAL', '30')}s"
        ]
        
        # Añadir análisis de performance
        if pnl_percentage > 5:
            lines.append("🎉 **¡Excelente performance!**")
        elif pnl_percentage > 0:
            lines.append("✅ **Performance positiva**")
        elif pnl_percentage > -5:
            lines.append("🟡 **Performance neutral**")
        else:
            lines.append("🔴 **Revisar estrategias**")
        
        await interaction.followup.send("\n".join(lines))
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error obteniendo estadísticas: {e}")


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
                    save_trades_today()
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
                    save_trades_today()
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


@bot.tree.command(name="trailing_status")
async def slash_trailing_status(interaction: discord.Interaction):
    """Muestra el estado de los trailing stops (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    if not TRAILING_STOPS_AVAILABLE or not trailing_manager:
        await interaction.followup.send("❌ Sistema de trailing stops no disponible")
        return
    
    try:
        status = trailing_manager.get_trailing_status()
        
        if status['active_trails'] == 0:
            await interaction.followup.send("📊 **Trailing Stops**\n\nNo hay posiciones con trailing stops activos")
            return
        
        embed = discord.Embed(
            title="📊 Estado de Trailing Stops",
            description=f"**{status['active_trails']} posiciones** con trailing stops activos",
            color=0x00ff88
        )
        
        for pos_info in status['positions']:
            ticket = pos_info['ticket']
            symbol = pos_info['symbol']
            
            status_text = []
            if pos_info['breakeven_moved']:
                status_text.append("✅ Breakeven")
            if pos_info['trailing_active']:
                status_text.append("🔄 Trailing")
            if pos_info['partial_closed']:
                status_text.append("📉 Parcial")
            
            status_str = " | ".join(status_text) if status_text else "⏳ Esperando"
            
            embed.add_field(
                name=f"🎯 **{symbol}** (#{ticket})",
                value=(
                    f"**Estado:** {status_str}\n"
                    f"**Max Profit:** {pos_info['highest_profit']*100:.1f}%"
                ),
                inline=True
            )
        
        embed.set_footer(text="Los trailing stops se actualizan cada 30 segundos")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error obteniendo estado de trailing stops: {e}")


@bot.tree.command(name="risk_status")
async def slash_risk_status(interaction: discord.Interaction):
    """Muestra el estado actual de la gestión de riesgo (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    if risk_manager is None:
        await interaction.followup.send("❌ Gestor de riesgo no disponible")
        return
    
    try:
        # Obtener balance de la cuenta
        mt5_initialize()
        account_info = mt5.account_info()
        if not account_info:
            await interaction.followup.send("❌ No se pudo obtener información de la cuenta MT5")
            return
        
        balance = account_info.balance
        
        # Obtener estadísticas del día
        today = datetime.now(timezone.utc).date().isoformat()
        daily_stats = risk_manager.get_daily_stats(today)
        
        # Obtener performance reciente
        recent_perf = risk_manager.get_recent_performance()
        
        # Obtener posiciones abiertas
        positions = mt5.positions_get()
        open_positions = len(positions) if positions else 0
        
        lines = [
            f"🛡️ **ESTADO DE GESTIÓN DE RIESGO**",
            f"",
            f"💰 **Cuenta:**",
            f"• Balance: {balance:.2f}",
            f"• Posiciones abiertas: {open_positions}",
            f"",
            f"📅 **Hoy ({today}):**",
            f"• Trades realizados: {daily_stats['total_trades']}",
            f"• Trades ganadores: {daily_stats['winning_trades']}",
            f"• Trades perdedores: {daily_stats['losing_trades']}",
            f"• PnL del día: {daily_stats['total_pnl']:.2f}",
            f"• Riesgo usado: {daily_stats['risk_used']:.2f}",
            f"",
            f"📊 **Performance Reciente:**",
            f"• Racha ganadora: {recent_perf['winning_streak']}",
            f"• Racha perdedora: {recent_perf['losing_streak']}",
            f"• Tasa de acierto: {recent_perf['win_rate']*100:.1f}%",
            f"",
            f"⚙️ **Límites Configurados:**"
        ]
        
        # Obtener configuración global
        global_config = risk_manager.rules_config.get('GLOBAL_SETTINGS', {})
        lines.extend([
            f"• Riesgo máximo diario: {global_config.get('max_total_risk', 1.5)}%",
            f"• Trades máximos por día: {global_config.get('max_daily_trades_all', 5)}",
            f"• Posiciones máximas: {global_config.get('max_simultaneous_positions', 3)}",
            f"• Límite de drawdown: {global_config.get('drawdown_limit', 8.0)}%"
        ])
        
        await interaction.followup.send("\n".join(lines))
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error obteniendo estado de riesgo: {e}")


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

async def _trailing_stops_loop():
    """Loop en background para actualizar trailing stops"""
    await bot.wait_until_ready()
    logger.info('Trailing stops loop started')
    
    while True:
        try:
            if TRAILING_STOPS_AVAILABLE and trailing_manager:
                trailing_manager.update_all_trailing_stops()
            await asyncio.sleep(30)  # Actualizar cada 30 segundos
        except Exception:
            logger.exception('Trailing stops loop crashed; retrying in 60s')
            await asyncio.sleep(60)


async def _market_opening_loop():
    """Loop en background para monitorear aperturas de mercado"""
    await bot.wait_until_ready()
    logger.info('Market opening alerts loop started')
    
    last_alert_sent = {}  # Para evitar spam de alertas
    
    while True:
        try:
            if MARKET_OPENING_AVAILABLE and market_opening_system:
                # Obtener próxima apertura
                market, opening_time, minutes_until = market_opening_system.get_next_market_opening()
                
                if market and opening_time:
                    # Verificar si debe enviar alerta
                    should_alert, alert_type = market_opening_system.should_send_alert(market, minutes_until)
                    
                    if should_alert:
                        # Evitar spam - solo una alerta por tipo por mercado por día
                        alert_key = f"{market}_{alert_type}_{opening_time.date()}"
                        
                        if alert_key not in last_alert_sent:
                            # Buscar canal de señales
                            ch = await _find_signals_channel()
                            
                            if ch:
                                # Generar estrategias para pares principales de este mercado
                                market_info = market_opening_system.market_sessions.get(market, {})
                                main_pairs = market_info.get('main_pairs', [])
                                
                                strategies = []
                                for symbol in main_pairs:
                                    try:
                                        strategy = market_opening_system.generate_opening_strategy(symbol, market)
                                        if 'error' not in strategy:
                                            strategies.append(strategy)
                                    except Exception as e:
                                        logger.exception(f"Error generating strategy for {symbol}: {e}")
                                
                                # Formatear y enviar alerta
                                alert_message = market_opening_system.format_opening_alert(market, alert_type, strategies)
                                
                                try:
                                    await ch.send(alert_message)
                                    last_alert_sent[alert_key] = datetime.now(timezone.utc)
                                    bot_logger.market_opening_alert(market, alert_type)
                                except Exception as e:
                                    logger.exception(f"Error sending market opening alert: {e}")
            
            # Verificar cada 5 minutos
            await asyncio.sleep(300)
            
        except Exception:
            logger.exception('Market opening loop crashed; retrying in 10 minutes')
            await asyncio.sleep(600)


@bot.tree.command(name="next_opening")
async def slash_next_opening(interaction: discord.Interaction):
    """Muestra información sobre la próxima apertura de mercado (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    if not MARKET_OPENING_AVAILABLE:
        await interaction.followup.send("❌ Sistema de apertura de mercados no disponible")
        return
    
    try:
        market, opening_time, minutes_until = market_opening_system.get_next_market_opening()
        
        if not market:
            await interaction.followup.send("❌ No se pudo determinar la próxima apertura")
            return
        
        now_utc = datetime.now(timezone.utc)
        now_spain = now_utc + timedelta(hours=1)
        
        # Información del mercado
        market_info = market_opening_system.market_sessions.get(market, {})
        main_pairs = market_info.get('main_pairs', [])
        
        embed = discord.Embed(
            title=f"⏰ Próxima Apertura: {market}",
            description=f"Información sobre la siguiente sesión de trading",
            color=0xff9500
        )
        
        # Tiempo hasta apertura
        if minutes_until > 60:
            hours = minutes_until // 60
            mins = minutes_until % 60
            time_str = f"{hours}h {mins}m"
        else:
            time_str = f"{minutes_until}m"
        
        embed.add_field(
            name="🕐 **Tiempo hasta Apertura**",
            value=(
                f"**{time_str}**\n"
                f"Apertura: {opening_time.strftime('%H:%M')} GMT\n"
                f"España: {(opening_time + timedelta(hours=1)).strftime('%H:%M')}"
            ),
            inline=True
        )
        
        # Pares principales
        if main_pairs:
            pairs_text = "\n".join([
                f"{'🇪🇺' if p == 'EURUSD' else '🥇' if p == 'XAUUSD' else '₿'} {p}" 
                for p in main_pairs
            ])
            embed.add_field(
                name="📊 **Pares Principales**",
                value=pairs_text,
                inline=True
            )
        
        # Estado actual
        if minutes_until <= 30:
            status = "🔥 **INMINENTE**"
            color = 0xff0000
        elif minutes_until <= 120:
            status = "⚡ **PRÓXIMA**"
            color = 0xff9500
        else:
            status = "⏳ **LEJANA**"
            color = 0x00ff88
        
        embed.color = color
        embed.add_field(
            name="📈 **Estado**",
            value=status,
            inline=True
        )
        
        # Consejos
        if minutes_until <= 60:
            embed.add_field(
                name="💡 **Preparación**",
                value=(
                    "• Revisa análisis pre-mercado\n"
                    "• Prepara niveles clave\n"
                    "• Configura alertas\n"
                    "• Mantente atento a noticias"
                ),
                inline=False
            )
        
        embed.set_footer(text=f"Actualizado: {now_spain.strftime('%H:%M')} España")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error obteniendo información de apertura: {e}")


@bot.tree.command(name="pre_market_analysis")
@discord.app_commands.describe(symbol="Símbolo para análisis pre-mercado (EURUSD, XAUUSD, BTCEUR)")
@discord.app_commands.choices(symbol=[
    discord.app_commands.Choice(name="🇪🇺 EURUSD", value="EURUSD"),
    discord.app_commands.Choice(name="🥇 XAUUSD", value="XAUUSD"),
    discord.app_commands.Choice(name="₿ BTCEUR", value="BTCEUR")
])
async def slash_pre_market_analysis(interaction: discord.Interaction, symbol: str = 'EURUSD'):
    """Análisis pre-mercado detallado para anticipar movimientos de apertura (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    
    if not MARKET_OPENING_AVAILABLE:
        await interaction.followup.send("❌ Sistema de análisis pre-mercado no disponible")
        return
    
    try:
        # Obtener análisis pre-mercado
        analysis = market_opening_system.analyze_pre_market_conditions(symbol)
        
        if 'error' in analysis:
            await interaction.followup.send(f"❌ Error en análisis: {analysis['error']}")
            return
        
        # Generar estrategia
        market = 'LONDON' if symbol in ['EURUSD', 'XAUUSD'] else 'CRYPTO'
        strategy = market_opening_system.generate_opening_strategy(symbol, market)
        
        emoji = {"EURUSD": "🇪🇺", "XAUUSD": "🥇", "BTCEUR": "₿"}.get(symbol, "📈")
        
        embed = discord.Embed(
            title=f"{emoji} Análisis Pre-Mercado: {symbol}",
            description="Condiciones actuales y estrategia para apertura",
            color=0x00ff88
        )
        
        # Formatear precio según símbolo
        if symbol == 'XAUUSD':
            price_str = f"{analysis['last_close']:.2f}"
            range_str = f"{analysis['range_size']:.2f}"
        elif symbol == 'BTCEUR':
            price_str = f"{analysis['last_close']:.0f}"
            range_str = f"{analysis['range_size']:.0f}"
        else:  # EURUSD
            price_str = f"{analysis['last_close']:.5f}"
            range_str = f"{analysis['range_size']:.5f}"
        
        # Condiciones actuales
        embed.add_field(
            name="📊 **Condiciones Actuales**",
            value=(
                f"**Precio:** {price_str}\n"
                f"**Momentum:** {analysis['momentum']}\n"
                f"**Volatilidad:** {analysis['volatility']:.2f}%\n"
                f"**Rango 8h:** {range_str}"
            ),
            inline=True
        )
        
        # Formatear niveles clave
        if symbol == 'XAUUSD':
            resistance_str = f"{analysis['resistance']:.2f}"
            support_str = f"{analysis['support']:.2f}"
        elif symbol == 'BTCEUR':
            resistance_str = f"{analysis['resistance']:.0f}"
            support_str = f"{analysis['support']:.0f}"
        else:  # EURUSD
            resistance_str = f"{analysis['resistance']:.5f}"
            support_str = f"{analysis['support']:.5f}"
        
        # Niveles clave
        embed.add_field(
            name="🎯 **Niveles Clave**",
            value=(
                f"**Resistencia:** {resistance_str}\n"
                f"**Soporte:** {support_str}\n"
                f"**Dist. Resist.:** {analysis['dist_to_resistance']:.2f}%\n"
                f"**Dist. Soporte:** {analysis['dist_to_support']:.2f}%"
            ),
            inline=True
        )
        
        # Potencial de gap
        gap_info = analysis['gap_potential']
        gap_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(gap_info['probability'], "⚪")
        
        embed.add_field(
            name="⚡ **Potencial de Gap**",
            value=(
                f"{gap_emoji} **Probabilidad:** {gap_info['probability']}\n"
                f"📈 **Dirección:** {gap_info['expected_direction']}\n"
                f"📊 **Momentum:** {gap_info['momentum_score']}/3"
            ),
            inline=True
        )
        
        # Estrategias recomendadas
        if 'error' not in strategy and strategy.get('recommendations'):
            strategy_text = []
            for i, rec in enumerate(strategy['recommendations'][:3], 1):  # Máximo 3
                confidence_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(rec['confidence'], "⚪")
                
                if rec['type'] in ['BUY', 'SELL']:
                    strategy_text.append(
                        f"{confidence_emoji} **{rec['type']}**\n"
                        f"• {rec['reason']}\n"
                        f"• Entrada: {rec['entry_zone']}\n"
                    )
                elif rec['type'] == 'GAP_PLAY':
                    strategy_text.append(
                        f"{confidence_emoji} **GAP {rec['direction']}**\n"
                        f"• {rec['reason']}\n"
                    )
                elif rec['type'] == 'BREAKOUT':
                    strategy_text.append(
                        f"{confidence_emoji} **BREAKOUT**\n"
                        f"• {rec['reason']}\n"
                    )
            
            if strategy_text:
                embed.add_field(
                    name="🎯 **Estrategias Recomendadas**",
                    value="\n\n".join(strategy_text),
                    inline=False
                )
        
        # Próxima apertura relevante
        market_name, opening_time, minutes_until = market_opening_system.get_next_market_opening()
        if market_name and minutes_until:
            if minutes_until <= 120:  # Próximas 2 horas
                embed.add_field(
                    name="⏰ **Próxima Apertura Relevante**",
                    value=(
                        f"**{market_name}** en {minutes_until}m\n"
                        f"Apertura: {opening_time.strftime('%H:%M')} GMT"
                    ),
                    inline=True
                )
        
        now_spain = datetime.now(timezone.utc) + timedelta(hours=1)
        embed.set_footer(text=f"Análisis: {now_spain.strftime('%H:%M')} España")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error en análisis pre-mercado: {e}")


@bot.tree.command(name="opening_alerts")
@discord.app_commands.describe(enabled="Activar/desactivar alertas de apertura")
@discord.app_commands.choices(enabled=[
    discord.app_commands.Choice(name="✅ Activar", value="true"),
    discord.app_commands.Choice(name="❌ Desactivar", value="false")
])
async def slash_opening_alerts(interaction: discord.Interaction, enabled: str = None):
    """Configura las alertas automáticas de apertura de mercado (solo admin)."""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return

    if not MARKET_OPENING_AVAILABLE:
        await interaction.response.send_message("❌ Sistema de alertas de apertura no disponible", ephemeral=True)
        return
    
    # Si no se especifica enabled, mostrar estado actual
    if enabled is None:
        embed = discord.Embed(
            title="🚨 Estado de Alertas de Apertura",
            description="Configuración actual del sistema de alertas",
            color=0x00ff88
        )
        
        embed.add_field(
            name="📊 **Sistema**",
            value=f"{'🟢 ACTIVO' if MARKET_OPENING_AVAILABLE else '🔴 INACTIVO'}",
            inline=True
        )
        
        # Próximas alertas
        market, opening_time, minutes_until = market_opening_system.get_next_market_opening()
        if market:
            should_alert, alert_type = market_opening_system.should_send_alert(market, minutes_until)
            
            embed.add_field(
                name="⏰ **Próxima Alerta**",
                value=(
                    f"**Mercado:** {market}\n"
                    f"**Tipo:** {alert_type or 'Ninguna próxima'}\n"
                    f"**En:** {minutes_until}m"
                ),
                inline=True
            )
        
        embed.add_field(
            name="🔔 **Tipos de Alerta**",
            value=(
                "• **Pre-Market:** 30m antes\n"
                "• **Opening:** 15m antes\n"
                "• **Post-Opening:** 15m después"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Configurar alertas (por ahora solo mostrar confirmación)
    is_enabled = enabled.lower() == 'true'
    
    embed = discord.Embed(
        title="✅ Alertas de Apertura Configuradas",
        description=f"Las alertas han sido {'activadas' if is_enabled else 'desactivadas'}",
        color=0x00ff00 if is_enabled else 0xff0000
    )
    
    if is_enabled:
        embed.add_field(
            name="🔔 **Alertas Activas**",
            value=(
                "• Pre-Market (30m antes)\n"
                "• Apertura Inminente (15m antes)\n"
                "• Post-Apertura (15m después)\n"
                "\nSe enviarán al canal #signals"
            ),
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


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
            stop_live_dashboard()
            log_event("Dashboard live detenido")
        except Exception:
            pass
        try:
            mt5_shutdown()
            log_event("MT5 desconectado")
        except Exception:
            pass
        
        # Información final del archivo de log
        if current_log_file and os.path.exists(current_log_file):
            file_size = os.path.getsize(current_log_file)
            file_size_mb = file_size / (1024 * 1024)
            log_event(f"📝 Log final guardado: {os.path.basename(current_log_file)} ({file_size_mb:.2f} MB)")
        
        log_event("Bot cerrado completamente")
        print("=" * 60)
        print(f"📝 Sesión completa guardada en: {os.path.basename(current_log_file) if current_log_file else 'archivo desconocido'}")
        print("=" * 60)
