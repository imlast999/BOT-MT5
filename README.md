# 🤖 BOT MT5 — Trading Automatizado con Discord

Bot de trading para MetaTrader 5 con integración Discord, backtesting histórico y paper trading.

---

## Inicio rápido

```bash
pip install -r requirements.txt
python bot.py
```

Requiere MT5 abierto y credenciales en `.env`.

---

## Estructura del proyecto

```
bot.py                    # Punto de entrada — bot Discord + MT5
signals.py                # Dispatcher de estrategias
rules_config.json         # Configuración de pares y riesgo
mt5_client.py             # Cliente MetaTrader 5
charts.py                 # Generación de gráficos
secrets_store.py          # Credenciales cifradas
position_manager.py       # Gestión de posiciones MT5
backtest_tracker.py       # Tracking de señales

core/
  engine.py               # Motor principal de señales
  scoring.py              # Sistema de scoring y confianza
  risk.py                 # Gestión de riesgo y lot sizing
  filters.py              # Filtros de duplicados y cooldown
  replay_engine.py        # Motor de backtesting histórico
  circuit_breaker.py      # Circuit breaker y risk scaling

services/
  autosignals.py          # Loop de escaneo automático
  dashboard.py            # Dashboard web (puerto 8080)
  execution.py            # Ejecución de órdenes MT5
  logging.py              # Sistema de logging inteligente
  database.py             # Persistencia SQLite
  commands.py             # Comandos Discord adicionales

strategies/
  base.py                 # Clase base con indicadores comunes
  eurusd.py               # Estrategia EURUSD (activa)
  xauusd.py               # Estrategia XAUUSD (activa)
  btceur_new.py           # Estrategia BTCEUR baseline (activa)
  btc_trend_pullback_v1.py  # Estrategia BTCEUR alternativa
  eurusd_mtf.py           # EURUSD multi-timeframe (experimental)

tests/
  backtest_runner.py      # Script de backtesting CLI
  test_replay.py          # Tests del replay engine

logs/                     # Logs por sesión (rotación automática)
backtest_results/         # CSVs de resultados de backtest
```

---

## Configuración (.env)

```env
# Discord
DISCORD_TOKEN=...
GUILD_ID=...
AUTHORIZED_USER_ID=...

# MT5
MT5_LOGIN=...
MT5_PASSWORD=...
MT5_SERVER=...

# Trading
AUTOSIGNALS=1
AUTOSIGNAL_INTERVAL=90
AUTOSIGNAL_SYMBOLS=EURUSD,XAUUSD,BTCEUR

# Auto-ejecución — DESACTIVADA para paper trading
AUTO_EXECUTE_SIGNALS=0
AUTO_EXECUTE_CONFIDENCE=HIGH

# Riesgo
MT5_RISK_PCT=0.5
MAX_TRADES_PER_PERIOD=5
```

---

## Estrategias activas

Las estrategias están validadas con backtest histórico (~7 meses de datos H1).
Configuración en `rules_config.json`.

### EURUSD — `eurusd_simple`

Tendencia confirmada + retroceso a EMA20.

| Parámetro | Valor |
|---|---|
| Timeframe | H1 |
| Filtro tendencia | EMA20 > EMA50, precio > EMA200 |
| Entrada | Retroceso a EMA20 (≤ 0.3%) |
| RSI | 38–62 |
| SL | 2.0× ATR |
| TP | 4.0× ATR |
| R:R | 2.0 |
| Riesgo/trade | 0.75% |
| **Profit factor** | **1.28** (3000 velas H1) |

### XAUUSD — `xauusd_simple`

Momentum en tendencia con filtro EMA200.

| Parámetro | Valor |
|---|---|
| Timeframe | H1 |
| Filtro tendencia | EMA20 > EMA50, precio > EMA200 |
| Entrada | RSI > 55 (BUY) / RSI < 45 (SELL) + ATR > media |
| SL | 2.0× ATR |
| TP | 5.0× ATR |
| R:R | 2.5 |
| Riesgo/trade | 0.60% |
| **Profit factor** | **1.28** (5000 velas H1) |

### BTCEUR — `btceur_simple` (baseline recomendado)

Tendencia EMA + MACD + volatilidad.

| Parámetro | Valor |
|---|---|
| Timeframe | H1 |
| Filtro tendencia | EMA20 > EMA50, precio > EMA200 |
| Entrada | MACD histogram en dirección + ATR > media |
| SL | 2.0× ATR |
| TP | 3.0× ATR |
| R:R | 1.5 |
| Riesgo/trade | 0.50% |
| **Profit factor** | **1.30** (5000 velas H1) |

### BTCEUR — `btc_trend_pullback_v1` (alternativa)

Trend following H4 + pullback a EMA20 H1.

| Parámetro | Valor |
|---|---|
| Timeframes | H4 (tendencia) + H1 (entrada) |
| Filtro H4 | EMA50 > EMA200, precio > EMA50 |
| Entrada H1 | Pullback a EMA20 (≤ 1.2%) + RSI 45–60 |
| SL | 1.5× ATR H1 |
| TP | 4.5× ATR H1 |
| R:R | 3.0 |
| Riesgo/trade | 0.50% |
| **Profit factor** | **1.20** (3000 velas H1) |

Para activar: cambiar en `rules_config.json` → `"strategy": "btc_trend_pullback_v1"`

---

## Backtesting

```bash
# Modo interactivo (pregunta par, estrategia y velas)
python tests/backtest_runner.py

# Directo
python tests/backtest_runner.py --symbol EURUSD --bars 3000
python tests/backtest_runner.py --symbol XAUUSD --strategy xauusd_simple --bars 5000
python tests/backtest_runner.py --symbol BTCEUR --strategy btc_trend_pullback_v1 --bars 3000
python tests/backtest_runner.py --all --bars 3000 --save

# Estrategias disponibles por par
# EURUSD : eurusd_simple, eurusd_advanced, eurusd_mtf
# XAUUSD : xauusd_simple, xauusd_reversal, xauusd_momentum
# BTCEUR : btceur_simple, btc_trend_pullback_v1
```

Los resultados se guardan en `backtest_results/` como CSV.

---

## Dashboard

Accesible en `http://localhost:8080` mientras el bot está corriendo.

Muestra: estado del sistema, señales del día, circuit breaker, pares monitoreados, historial de señales (48h).

---

## Circuit Breaker y Risk Scaling

Implementado en `core/circuit_breaker.py`. Se activa automáticamente:

| Situación | Acción |
|---|---|
| 2 pérdidas seguidas | Riesgo × 0.8 |
| 3 pérdidas seguidas | Riesgo × 0.5 |
| 4 pérdidas seguidas | **Pausa 24h** |
| 3 wins seguidos | Riesgo × 1.4 |
| 5 wins seguidos | Riesgo × 1.8 |

---

## Comandos Discord principales

```
/autosignals on|off|status   — Control del escaneo automático
/signal [EURUSD]             — Señal manual de un par
/positions                   — Posiciones abiertas en MT5
/close_position [ticket]     — Cerrar posición
/replay EURUSD 1000          — Backtest rápido desde Discord
/logs_info                   — Archivo de log actual
```

---

## Notas para paper trading

- `AUTO_EXECUTE_SIGNALS=0` — el bot solo envía señales a Discord, no ejecuta
- Cooldown de 60 minutos por par — máximo 1 señal/hora por símbolo
- Límite de 5 trades por período de 12h (global)
- Los logs se guardan en `logs/` con rotación automática por sesión
