"""
Backtest Runner - Validación histórica de estrategias

Ejecuta el replay engine sobre datos históricos reales de MT5
y genera un reporte detallado con métricas de rendimiento.

Uso:
    python backtest_runner.py                                        # Modo interactivo
    python backtest_runner.py --symbol EURUSD --bars 1000            # Directo
    python backtest_runner.py --symbol EURUSD --strategy eurusd_advanced --bars 2000
    python backtest_runner.py --all --bars 500                       # Los 3 pares
    python backtest_runner.py --all --bars 3000 --save               # Guarda CSV

Estrategias disponibles:
    eurusd_simple, eurusd_advanced
    xauusd_simple, xauusd_reversal, xauusd_momentum
    btceur_simple

Requisitos:
    - MT5 instalado y corriendo
    - Credenciales en .env (MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)
    - pip install -r requirements.txt
"""

import sys
import os
import argparse
import time
from datetime import datetime, timezone
from typing import List, Optional

# Añadir directorio raíz al path (el script está en tests/, la raíz está un nivel arriba)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─────────────────────────────────────────────────────────────────────────────
# Configuración de logging (antes de cualquier import del proyecto)
# ─────────────────────────────────────────────────────────────────────────────
import logging

logging.basicConfig(
    level=logging.WARNING,  # Solo warnings y errores en consola
    format='%(levelname)s | %(name)s | %(message)s'
)

# Silenciar loggers ruidosos del proyecto durante el backtest
for noisy in ['core.engine', 'core.scoring', 'strategies.eurusd',
              'strategies.xauusd', 'strategies.btceur_new',
              'signals', 'mt5_client']:
    logging.getLogger(noisy).setLevel(logging.ERROR)

logger = logging.getLogger('backtest_runner')
logger.setLevel(logging.INFO)


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

SYMBOLS = ['EURUSD', 'XAUUSD', 'BTCEUR']

# Estrategias disponibles por símbolo
STRATEGIES_BY_SYMBOL = {
    'EURUSD': ['eurusd_simple', 'eurusd_advanced', 'eurusd_mtf', 'eurusd_asian_breakout'],
    'XAUUSD': ['xauusd_simple', 'xauusd_reversal', 'xauusd_momentum', 'xauusd_psychological'],
    'BTCEUR': ['btceur_simple', 'btc_trend_pullback_v1', 'btceur_weekly_breakout'],
}

# Todas las estrategias válidas (para validación de argumento CLI)
ALL_STRATEGIES = [s for strategies in STRATEGIES_BY_SYMBOL.values() for s in strategies]

# Timeframe por estrategia (las MTF usan H4)
TIMEFRAME_BY_STRATEGY = {
    'eurusd_mtf':            'H4',
    'btc_trend_pullback_v1': 'H1',  # usa H1 para entrada, resamplea H4 internamente
}
DEFAULT_TIMEFRAME = 'H1'

# Estrategia por defecto por símbolo
DEFAULT_STRATEGY = {
    'EURUSD': 'eurusd_simple',
    'XAUUSD': 'xauusd_simple',
    'BTCEUR': 'btceur_simple',
}

# Referencia de pip para mostrar resultados legibles
PIP_SIZE = {
    'EURUSD': 0.0001,
    'XAUUSD': 0.1,     # 1 pip = $0.1 en precio estándar (~3300); el broker multiplica el precio pero los pips son relativos
    'BTCEUR': 1.0,
}

# Umbrales mínimos para considerar una estrategia "con edge"
MIN_WINRATE    = 50.0   # %
MIN_SIGNALS    = 10     # señales mínimas para que el resultado sea estadísticamente relevante
MIN_RR         = 1.5    # R:R promedio mínimo
MIN_PROFIT_FACTOR = 1.2 # profit factor mínimo


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de presentación
# ─────────────────────────────────────────────────────────────────────────────

def _sep(char='─', width=65):
    return char * width

def _header(title: str):
    print()
    print(_sep('═'))
    print(f"  {title}")
    print(_sep('═'))

def _section(title: str):
    print()
    print(_sep())
    print(f"  {title}")
    print(_sep())

def _ok(msg):   print(f"  ✅  {msg}")
def _warn(msg): print(f"  ⚠️   {msg}")
def _fail(msg): print(f"  ❌  {msg}")
def _info(msg): print(f"  ℹ️   {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Inicialización MT5
# ─────────────────────────────────────────────────────────────────────────────

def init_mt5() -> bool:
    """Inicializa MT5 con credenciales del .env"""
    try:
        from dotenv import load_dotenv
        load_dotenv()

        import MetaTrader5 as mt5

        login    = os.getenv('MT5_LOGIN', '').strip()
        password = os.getenv('MT5_PASSWORD', '').strip()
        server   = os.getenv('MT5_SERVER', '').strip()

        if login and password and server:
            # Credenciales explícitas en .env
            ok = mt5.initialize(login=int(login), password=password, server=server)
        else:
            # Sin credenciales: conectar a la sesión ya abierta en MT5
            # MT5 debe estar abierto y logueado manualmente
            ok = mt5.initialize()
            if not ok:
                error = mt5.last_error()
                print(f"\n  ❌  No se pudo conectar a MT5: {error}")
                print()
                print("  Causas posibles:")
                print("  1. MT5 no está abierto o no está logueado")
                print("  2. Las credenciales no están en .env")
                print()
                print("  Solución: añade estas líneas a tu .env:")
                print("    MT5_LOGIN=tu_numero_de_cuenta")
                print("    MT5_PASSWORD=tu_contraseña")
                print("    MT5_SERVER=nombre_del_servidor  (ej: ICMarkets-Demo)")
                print()
                print("  El servidor y número de cuenta los ves en MT5 →")
                print("  esquina inferior derecha, o en Archivo → Abrir cuenta")
                return False

        if not ok:
            error = mt5.last_error()
            print(f"\n  ❌  No se pudo conectar a MT5 con credenciales: {error}")
            print()
            print("  Verifica que MT5_LOGIN, MT5_PASSWORD y MT5_SERVER en .env son correctos.")
            return False

        info = mt5.account_info()
        if info:
            print(f"\n  ✅  MT5 conectado → cuenta {info.login} | {info.server} | balance {info.balance:.2f} {info.currency}")
        else:
            print("  ✅  MT5 conectado (sin info de cuenta)")

        return True

    except ImportError:
        print("\n  ❌  MetaTrader5 no instalado. Ejecuta: pip install MetaTrader5")
        return False
    except Exception as e:
        print(f"\n  ❌  Error inicializando MT5: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo de métricas adicionales
# ─────────────────────────────────────────────────────────────────────────────

def compute_extra_metrics(signals) -> dict:
    """
    Calcula profit factor, max drawdown y distribución de resultados
    a partir de la lista de ReplaySignal.
    """
    wins   = [s for s in signals if s.result == 'WIN']
    losses = [s for s in signals if s.result == 'LOSS']

    gross_profit = sum(s.profit_pips or 0 for s in wins)
    gross_loss   = abs(sum(s.profit_pips or 0 for s in losses))

    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

    # Max drawdown en pips (secuencia de pérdidas consecutivas)
    equity = 0.0
    peak   = 0.0
    max_dd = 0.0
    for s in signals:
        if s.result in ('WIN', 'LOSS'):
            equity += (s.profit_pips or 0)
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

    # Racha máxima de pérdidas consecutivas
    max_loss_streak = 0
    current_streak  = 0
    for s in signals:
        if s.result == 'LOSS':
            current_streak += 1
            max_loss_streak = max(max_loss_streak, current_streak)
        elif s.result == 'WIN':
            current_streak = 0

    # Distribución por confianza
    conf_dist: dict = {}
    for s in signals:
        conf_dist[s.confidence] = conf_dist.get(s.confidence, 0) + 1

    return {
        'gross_profit_pips': gross_profit,
        'gross_loss_pips':   gross_loss,
        'profit_factor':     profit_factor,
        'max_drawdown_pips': max_dd,
        'max_loss_streak':   max_loss_streak,
        'confidence_dist':   conf_dist,
        'wins':  len(wins),
        'losses': len(losses),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Ejecución de un backtest individual
# ─────────────────────────────────────────────────────────────────────────────

def run_single_backtest(symbol: str, bars: int, strategy: str = None,
                        verbose: bool = False) -> Optional[dict]:
    """
    Ejecuta el replay engine para un símbolo y devuelve un dict con resultados.
    Retorna None si hay error.
    """
    if strategy is None:
        strategy = DEFAULT_STRATEGY.get(symbol, 'eurusd_simple')

    pip_size  = PIP_SIZE.get(symbol, 0.0001)
    timeframe = TIMEFRAME_BY_STRATEGY.get(strategy, DEFAULT_TIMEFRAME)

    print(f"\n  ⏳  Analizando {symbol} ({bars} velas {timeframe}, estrategia: {strategy})...")

    try:
        from core.replay_engine import ReplayEngine

        if strategy == 'eurusd_mtf':
            lookback = 1300
            forward  = 300
        elif strategy == 'btc_trend_pullback_v1':
            lookback = 900
            forward  = 120
        elif strategy == 'btceur_weekly_breakout':
            # Necesita ~5 semanas de histórico para calcular rango semanal anterior
            lookback = 900
            forward  = 300   # trades semanales pueden durar días
        elif strategy in ('eurusd_asian_breakout', 'xauusd_psychological'):
            lookback = 210
            forward  = 120
        else:
            lookback = 210
            forward  = 120

        engine = ReplayEngine(lookback_window=lookback, max_forward_bars=forward)
        t0 = time.time()

        stats = engine.run_replay(
            symbol=symbol,
            bars=bars,
            strategy=strategy,
            timeframe=timeframe,
            skip_duplicate_filter=True,
        )

        elapsed = time.time() - t0
        signals = engine.get_signals()

        if stats.signals_final == 0:
            _warn(f"{symbol}: 0 señales generadas en {bars} velas {timeframe}. "
                  "Revisa la conexión MT5 o los parámetros de la estrategia.")
            return None

        extra = compute_extra_metrics(signals)

        return {
            'symbol':          symbol,
            'strategy':        strategy,
            'timeframe':       timeframe,
            'bars_analyzed':   stats.bars_analyzed,
            'signals_final':   stats.signals_final,
            'buy_signals':     stats.buy_signals,
            'sell_signals':    stats.sell_signals,
            'tp_hits':         stats.tp_hits,
            'sl_hits':         stats.sl_hits,
            'pending':         stats.pending,
            'winrate':         stats.winrate,
            'avg_rr':          stats.avg_rr,
            'total_pips':      stats.total_pips,
            'pip_size':        pip_size,
            'elapsed':         elapsed,
            'signals':         signals,
            **extra,
        }

    except Exception as e:
        logger.error(f"Error en backtest de {symbol}: {e}", exc_info=True)
        _fail(f"{symbol}: Error durante el backtest → {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Impresión de resultados
# ─────────────────────────────────────────────────────────────────────────────

def print_result(r: dict, verbose: bool = False):
    """Imprime el resultado de un backtest de forma legible."""
    sym      = r['symbol']

    _section(f"RESULTADOS: {sym}  [estrategia: {r['strategy']}]")

    closed = r['tp_hits'] + r['sl_hits']

    print(f"  Velas analizadas : {r['bars_analyzed']:>6}")
    print(f"  Señales totales  : {r['signals_final']:>6}  (BUY: {r['buy_signals']} | SELL: {r['sell_signals']})")
    print(f"  Cerradas         : {closed:>6}  (TP: {r['tp_hits']} | SL: {r['sl_hits']} | Pendientes: {r['pending']})")
    print()

    # Winrate
    wr = r['winrate']
    wr_str = f"{wr:.1f}%"
    if wr >= MIN_WINRATE:
        _ok(f"Winrate          : {wr_str}")
    else:
        _fail(f"Winrate          : {wr_str}  (mínimo recomendado: {MIN_WINRATE}%)")

    # R:R promedio
    avg_rr = r['avg_rr']
    rr_str = f"{avg_rr:.2f}"
    if avg_rr >= MIN_RR:
        _ok(f"R:R promedio     : {rr_str}")
    else:
        _warn(f"R:R promedio     : {rr_str}  (mínimo recomendado: {MIN_RR})")

    # Profit factor
    pf = r['profit_factor']
    pf_str = f"{pf:.2f}" if pf != float('inf') else "∞ (sin pérdidas)"
    if pf >= MIN_PROFIT_FACTOR:
        _ok(f"Profit factor    : {pf_str}")
    else:
        _fail(f"Profit factor    : {pf_str}  (mínimo recomendado: {MIN_PROFIT_FACTOR})")

    # Pips totales
    total_pips = r['total_pips']
    pips_str = f"{total_pips:+.1f} pips"
    if total_pips > 0:
        _ok(f"Pips netos       : {pips_str}")
    else:
        _fail(f"Pips netos       : {pips_str}")

    # Max drawdown
    _info(f"Max drawdown     : {r['max_drawdown_pips']:.1f} pips")
    _info(f"Racha pérdidas   : {r['max_loss_streak']} consecutivas")

    # Distribución de confianza
    if r['confidence_dist']:
        conf_str = "  |  ".join(f"{k}: {v}" for k, v in sorted(r['confidence_dist'].items()))
        _info(f"Confianza dist.  : {conf_str}")

    # Señales insuficientes
    if r['signals_final'] < MIN_SIGNALS:
        _warn(f"Solo {r['signals_final']} señales cerradas. Aumenta --bars para resultados más fiables.")

    print(f"\n  ⏱️   Tiempo de ejecución: {r['elapsed']:.1f}s")

    # Detalle de señales (solo en modo verbose)
    if verbose and r['signals']:
        print()
        print("  DETALLE DE SEÑALES:")
        print(f"  {'#':>3}  {'Fecha':>20}  {'Tipo':>4}  {'Entry':>10}  {'SL':>10}  {'TP':>10}  {'Resultado':>8}  {'Pips':>8}  {'Conf':>12}")
        print("  " + "─" * 95)
        for i, s in enumerate(r['signals'], 1):
            ts = s.timestamp.strftime('%Y-%m-%d %H:%M') if s.timestamp else '─'
            pips = f"{s.profit_pips:+.1f}" if s.profit_pips is not None else "─"
            result = s.result or 'PENDING'
            print(f"  {i:>3}  {ts:>20}  {s.signal_type:>4}  {s.entry:>10.5f}  "
                  f"{s.sl:>10.5f}  {s.tp:>10.5f}  {result:>8}  {pips:>8}  {s.confidence:>12}")


# ─────────────────────────────────────────────────────────────────────────────
# Resumen comparativo multi-símbolo
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(results: List[dict]):
    """Imprime tabla comparativa de todos los símbolos."""
    if len(results) < 2:
        return

    _header("RESUMEN COMPARATIVO")

    print(f"  {'Símbolo':>8}  {'Señales':>8}  {'Winrate':>8}  {'R:R':>6}  {'PF':>6}  {'Pips':>8}  {'Veredicto':>12}")
    print("  " + "─" * 70)

    for r in results:
        sym    = r['symbol']
        sigs   = r['signals_final']
        wr     = f"{r['winrate']:.1f}%"
        rr     = f"{r['avg_rr']:.2f}"
        pf     = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float('inf') else "∞"
        pips   = f"{r['total_pips']:+.1f}"

        has_edge = (
            r['winrate'] >= MIN_WINRATE and
            r['avg_rr'] >= MIN_RR and
            r['profit_factor'] >= MIN_PROFIT_FACTOR and
            r['total_pips'] > 0 and
            sigs >= MIN_SIGNALS
        )
        verdict = "✅ CON EDGE" if has_edge else "❌ SIN EDGE"

        print(f"  {sym:>8}  {sigs:>8}  {wr:>8}  {rr:>6}  {pf:>6}  {pips:>8}  {verdict:>12}")

    print()
    print("  Criterios de edge: winrate ≥ 50% | R:R ≥ 1.5 | PF ≥ 1.2 | pips > 0 | señales ≥ 10")


# ─────────────────────────────────────────────────────────────────────────────
# Recomendaciones automáticas
# ─────────────────────────────────────────────────────────────────────────────

def print_recommendations(results: List[dict]):
    """Genera recomendaciones basadas en los resultados."""
    _header("RECOMENDACIONES")

    for r in results:
        sym = r['symbol']
        print(f"\n  {sym}:")

        issues = []
        goods  = []

        if r['signals_final'] < MIN_SIGNALS:
            issues.append(f"Pocas señales ({r['signals_final']}). Aumenta --bars o revisa los filtros de la estrategia.")

        if r['winrate'] < MIN_WINRATE:
            issues.append(f"Winrate bajo ({r['winrate']:.1f}%). Considera ajustar los umbrales de RSI o EMA.")

        if r['avg_rr'] < MIN_RR:
            issues.append(f"R:R bajo ({r['avg_rr']:.2f}). Aumenta tp_atr_multiplier o reduce sl_atr_multiplier en la estrategia.")

        if r['profit_factor'] < MIN_PROFIT_FACTOR:
            issues.append(f"Profit factor bajo ({r['profit_factor']:.2f}). La estrategia pierde más de lo que gana.")

        if r['max_loss_streak'] >= 5:
            issues.append(f"Racha de {r['max_loss_streak']} pérdidas consecutivas. Revisa el filtro de tendencia.")

        if r['total_pips'] > 0 and r['winrate'] >= MIN_WINRATE:
            goods.append("Estrategia rentable en el período analizado.")

        if r['avg_rr'] >= 2.0:
            goods.append(f"Excelente R:R promedio ({r['avg_rr']:.2f}).")

        if r['profit_factor'] >= 1.5:
            goods.append(f"Buen profit factor ({r['profit_factor']:.2f}).")

        for g in goods:
            _ok(g)
        for i in issues:
            _warn(i)

        if not issues and not goods:
            _info("Resultados dentro de parámetros normales.")


# ─────────────────────────────────────────────────────────────────────────────
# Guardado de resultados en CSV
# ─────────────────────────────────────────────────────────────────────────────

def save_results_csv(results: List[dict], bars: int):
    """Guarda señales detalladas en CSV para análisis posterior."""
    try:
        import csv
        from pathlib import Path

        Path('backtest_results').mkdir(exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = f'backtest_results/backtest_{ts}_{bars}bars.csv'

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'symbol', 'timestamp', 'signal_type', 'entry', 'sl', 'tp',
                'confidence', 'score', 'result', 'exit_price', 'profit_pips', 'bar_index'
            ])
            for r in results:
                for s in r.get('signals', []):
                    writer.writerow([
                        r['symbol'],
                        s.timestamp.isoformat() if s.timestamp else '',
                        s.signal_type,
                        s.entry,
                        s.sl,
                        s.tp,
                        s.confidence,
                        s.score,
                        s.result or 'PENDING',
                        s.exit_price or '',
                        s.profit_pips or '',
                        s.bar_index,
                    ])

        print(f"\n  💾  Resultados guardados en: {filepath}")

    except Exception as e:
        _warn(f"No se pudo guardar CSV: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description='Backtest Runner - Valida estrategias sobre datos históricos de MT5',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Estrategias disponibles:
  EURUSD : eurusd_simple, eurusd_advanced
  XAUUSD : xauusd_simple, xauusd_reversal, xauusd_momentum
  BTCEUR : btceur_simple

Ejemplos:
  python backtest_runner.py                                         # Modo interactivo
  python backtest_runner.py --symbol EURUSD --bars 1000
  python backtest_runner.py --symbol EURUSD --strategy eurusd_advanced --bars 2000
  python backtest_runner.py --all --bars 1000
  python backtest_runner.py --all --bars 3000 --save
        """
    )
    parser.add_argument('--symbol',   type=str, choices=SYMBOLS,
                        help='Símbolo a analizar')
    parser.add_argument('--strategy', type=str, choices=ALL_STRATEGIES,
                        help='Estrategia a usar (default: la simple del símbolo)')
    parser.add_argument('--all',      action='store_true',
                        help='Analizar todos los pares con su estrategia por defecto')
    parser.add_argument('--bars',     type=int,
                        help='Número de velas H1 a analizar')
    parser.add_argument('--verbose',  action='store_true',
                        help='Mostrar detalle de cada señal')
    parser.add_argument('--save',     action='store_true',
                        help='Guardar resultados en CSV')
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# Modo interactivo
# ─────────────────────────────────────────────────────────────────────────────

def _ask(prompt: str, default: str = None) -> str:
    """Pregunta al usuario con un default opcional."""
    if default:
        full_prompt = f"  {prompt} [{default}]: "
    else:
        full_prompt = f"  {prompt}: "
    answer = input(full_prompt).strip()
    return answer if answer else (default or '')

def interactive_mode() -> dict:
    """Modo interactivo: pregunta símbolo, estrategia y velas."""
    print()
    print("  Modo interactivo — responde las preguntas o pulsa Enter para el valor por defecto.")
    print()

    # ── Símbolo ──────────────────────────────────────────────────────────────
    print(f"  Pares disponibles: {', '.join(SYMBOLS)} | ALL")
    raw_sym = _ask("Par a analizar", "EURUSD").upper()

    run_all = raw_sym == 'ALL'
    if run_all:
        symbols = SYMBOLS
        strategy = None  # cada par usa su default
    else:
        if raw_sym not in SYMBOLS:
            print(f"\n  ⚠️   '{raw_sym}' no reconocido, usando EURUSD.")
            raw_sym = 'EURUSD'
        symbols = [raw_sym]

        # ── Estrategia ───────────────────────────────────────────────────────
        available = STRATEGIES_BY_SYMBOL[raw_sym]
        default_strat = DEFAULT_STRATEGY[raw_sym]
        print()
        print(f"  Estrategias para {raw_sym}: {', '.join(available)}")
        raw_strat = _ask("Estrategia", default_strat).lower()
        if raw_strat not in available:
            print(f"  ⚠️   '{raw_strat}' no reconocida, usando {default_strat}.")
            raw_strat = default_strat
        strategy = raw_strat

    # ── Velas ────────────────────────────────────────────────────────────────
    print()
    print("  Referencia: 168 velas ≈ 1 semana | 720 ≈ 1 mes | 2160 ≈ 3 meses | 4320 ≈ 6 meses")
    raw_bars = _ask("Número de velas H1", "1000")
    try:
        bars = int(raw_bars)
        if bars < 50:
            print("  ⚠️   Mínimo 50 velas. Usando 50.")
            bars = 50
        if bars > 10000:
            print("  ⚠️   Máximo 10000 velas. Usando 10000.")
            bars = 10000
    except ValueError:
        print("  ⚠️   Valor inválido, usando 1000.")
        bars = 1000

    # ── Opciones extra ───────────────────────────────────────────────────────
    print()
    verbose_raw = _ask("Mostrar detalle de cada señal? (s/N)", "N").lower()
    verbose = verbose_raw in ('s', 'si', 'sí', 'y', 'yes')

    save_raw = _ask("Guardar resultados en CSV? (s/N)", "N").lower()
    save = save_raw in ('s', 'si', 'sí', 'y', 'yes')

    print()
    return {
        'symbols':   symbols,
        'strategy':  strategy,
        'bars':      bars,
        'verbose':   verbose,
        'save':      save,
        'run_all':   run_all,
    }


def main():
    args = parse_args()

    # ── Decidir si modo interactivo o CLI directo ─────────────────────────────
    # Modo interactivo: ningún argumento relevante fue pasado
    no_args_given = (
        args.symbol is None and
        not args.all and
        args.bars is None and
        args.strategy is None
    )

    if no_args_given:
        _header("BACKTEST RUNNER — Validación Histórica de Estrategias")
        cfg = interactive_mode()
        symbols_to_run = cfg['symbols']
        strategy_override = cfg['strategy']   # None si --all
        bars    = cfg['bars']
        verbose = cfg['verbose']
        save    = cfg['save']
    else:
        # Modo CLI: usar argumentos con defaults
        symbols_to_run   = SYMBOLS if args.all else [args.symbol or 'EURUSD']
        strategy_override = args.strategy   # None = usar default por símbolo
        bars    = args.bars or 500
        verbose = args.verbose
        save    = args.save

        _header("BACKTEST RUNNER — Validación Histórica de Estrategias")

    print(f"  Fecha      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    tf_display = TIMEFRAME_BY_STRATEGY.get(strategy_override or '', DEFAULT_TIMEFRAME) if not (args.all if not no_args_given else cfg.get('run_all')) else 'H1/H4'
    print(f"  Velas      : {bars}  (~{bars // 168} semanas aprox.)")
    print(f"  Símbolos   : {', '.join(symbols_to_run)}")
    if strategy_override:
        print(f"  Estrategia : {strategy_override}")
    else:
        strats = [f"{s}→{DEFAULT_STRATEGY[s]}" for s in symbols_to_run]
        print(f"  Estrategia : {', '.join(strats)}")
    print(f"  Verbose    : {'Sí' if verbose else 'No'}")

    # Conectar MT5
    if not init_mt5():
        sys.exit(1)

    # Ejecutar backtests
    results = []
    for sym in symbols_to_run:
        # Si hay override de estrategia, validar que sea compatible con el símbolo
        strat = strategy_override
        if strat and strat not in STRATEGIES_BY_SYMBOL.get(sym, []):
            _warn(f"Estrategia '{strat}' no es válida para {sym}. "
                  f"Usando default: {DEFAULT_STRATEGY[sym]}")
            strat = None

        r = run_single_backtest(sym, bars, strategy=strat, verbose=verbose)
        if r:
            print_result(r, verbose=verbose)
            results.append(r)

    if not results:
        print("\n  ❌  No se obtuvieron resultados. Revisa la conexión MT5.")
        sys.exit(1)

    if len(results) > 1:
        print_summary(results)

    print_recommendations(results)

    if save:
        save_results_csv(results, bars)

    has_any_edge = any(
        r['winrate'] >= MIN_WINRATE and
        r['avg_rr'] >= MIN_RR and
        r['total_pips'] > 0
        for r in results
    )

    print()
    if has_any_edge:
        print("  ✅  Al menos una estrategia muestra edge en el período analizado.")
    else:
        print("  ⚠️   Ninguna estrategia muestra edge claro. Considera ajustar parámetros antes de operar en real.")
    print()

    sys.exit(0 if has_any_edge else 1)


if __name__ == '__main__':
    main()
