# 🤖 BOT MT5 - Sistema de Trading Automatizado

Bot de trading automatizado para MetaTrader 5 con integración Discord, análisis técnico avanzado y sistema de backtesting completo.

## 📋 Tabla de Contenidos

- [Características Principales](#-características-principales)
- [Instalación y Configuración](#-instalación-y-configuración)
- [Estrategias de Trading](#-estrategias-de-trading)
- [Sistema de Auto-Ejecución](#-sistema-de-auto-ejecución)
- [Dashboard y Monitoreo](#-dashboard-y-monitoreo)
- [Comandos Discord](#-comandos-discord)
- [Configuración Avanzada](#-configuración-avanzada)
- [Backtesting](#-backtesting)
- [Solución de Problemas](#-solución-de-problemas)

---

## 🚀 Características Principales

### **Trading Automatizado**
- ✄1�7 **Auto-ejecución** de señales con confirmación
- ✄1�7 **Gestión de riesgo** automática (0.5% por trade)
- ✄1�7 **Stop Loss y Take Profit** dinámicos
- ✄1�7 **Trailing Stops** inteligentes
- ✄1�7 **Límites por período** (5 trades cada 12 horas)

### **Análisis Técnico**
- ✄1�7 **3 Estrategias optimizadas**: EURUSD, XAUUSD, BTCEUR
- ✄1�7 **Indicadores múltiples**: EMAs, RSI, ATR, Momentum
- ✄1�7 **Filtros anti-duplicados** inteligentes
- ✄1�7 **Análisis multi-timeframe** (H1 principal, M15 precisión)

### **Monitoreo y Control**
- ✄1�7 **Dashboard live** con métricas en tiempo real
- ✄1�7 **Integración Discord** completa
- ✄1�7 **Sistema de logging** detallado
- ✄1�7 **Tracking de señales rechazadas**
- ✄1�7 **Backtest automático** con estadísticas

---

## 🛠 Instalación y Configuración

### **Requisitos Previos**
```bash
# Python 3.8+
# MetaTrader 5 instalado
# Cuenta Discord Bot
```

### **1. Instalación de Dependencias**
```bash
pip install -r requirements.txt
```

### **2. Configuración de Variables de Entorno**
Copiar `.env.example` a `.env` y configurar:

```env
# Discord
DISCORD_TOKEN=tu_token_aqui
GUILD_ID=tu_servidor_id
AUTHORIZED_USER_ID=tu_user_id

# Trading
AUTOSIGNALS=1
AUTO_EXECUTE_SIGNALS=1
AUTO_EXECUTE_CONFIDENCE=LOW
MAX_TRADES_PER_DAY=20

# Símbolos monitoreados
AUTOSIGNAL_SYMBOLS=EURUSD,XAUUSD,BTCEUR
```

### **3. Configuración MT5**
1. Abrir MetaTrader 5
2. **Habilitar AutoTrading** (botón verde en toolbar)
3. Permitir trading automatizado en configuración
4. Verificar conexión con broker

### **4. Iniciar el Bot**
```bash
python bot.py
```

---

## 📈 Estrategias de Trading

### **EURUSD Simple**
```
SETUP: Breakout de rango (15 períodos)
CONFIRMACIONES:
- RSI entre 10-90 (ultra permisivo)
- Precio fuera del rango reciente
GESTIÓN:
- SL: ATR × 1.5
- TP: SL × 1.5 (R:R 1.5)
- Máx: 10 trades/día
```

### **XAUUSD Simple**
```
SETUP: Reversión en niveles psicológicos
CONFIRMACIONES:
- Precio cerca de nivel redondo (±20$)
- Mecha significativa (>20%)
GESTIÓN:
- SL: 10$ fijo
- TP: 20$ fijo (R:R 2.0)
- Máx: 8 trades/día
```

### **BTCEUR Mejorado**
```
SETUP: Momentum EMA con filtro de tendencia
CONFIRMACIONES:
- EMA12 vs EMA26 (señal)
- EMA50 (filtro de tendencia principal)
- RSI en rango óptimo (45-75 BUY, 25-55 SELL)
- Momentum significativo (>1%)
GESTIÓN:
- SL: ATR × 2.0
- TP: SL × 1.5 (R:R 1.5)
- Máx: 12 trades/día
```

---

## 🤖 Sistema de Auto-Ejecución

### **Configuración Actual**
```json
{
  "enabled": true,
  "confidence_filter": "LOW",
  "max_trades_per_period": 5,
  "period_reset_times": ["00:00", "12:00"],
  "duplicate_prevention": true,
  "backtest_mode": true
}
```

### **Límites de Seguridad**
- **5 trades máximo cada 12 horas** (total entre todos los pares)
- **Reinicio automático** a las 00:00 y 12:00 UTC
- **Prevención de duplicados** con tolerancia por símbolo:
  - EURUSD: 10 pips
  - XAUUSD: 5 dólares
  - BTCEUR: 100 EUR

### **Flujo de Auto-Ejecución**
1. **Detección** de señal cada 90 segundos
2. **Verificación** anti-duplicados
3. **Verificación** límites por período
4. **Ejecución inmediata** (modo backtest)
5. **Registro** en dashboard y logs

---

## 📊 Dashboard y Monitoreo

### **Dashboard Live**
- **Archivo**: `live_dashboard.html`
- **Actualización**: Cada 5 minutos
- **Métricas**: Balance, trades, equity curve, estadísticas

### **Datos Mostrados**
- ✄1�7 **Balance actual** y evolución
- ✄1�7 **Trades ejecutados** por sesión
- ✄1�7 **Estadísticas de rendimiento**
- ✄1�7 **Señales rechazadas** y razones
- ✄1�7 **Estado del período** actual

### **Logs del Sistema**
- **Archivo**: `logs.txt`
- **Nivel**: INFO (todos los eventos importantes)
- **Rotación**: Automática por tamaño
- **Formato**: JSON estructurado + mensajes legibles

---

## 💬 Comandos Discord

### **Comandos de Trading**
```
/autosignals          - Ver estado del escaneo automático
/period_status        - Estado del período actual (5 trades/12h)
/rejection_stats      - Estadísticas de señales rechazadas
/comprehensive_stats  - Estadísticas completas del bot
```

### **Comandos de Control**
```
/auto_execution       - Configurar auto-ejecución
/debug_signals [PAR]  - Debug detallado de estrategia
/balance             - Ver balance actual MT5
/positions           - Ver posiciones abiertas
```

### **Comandos de Análisis**
```
/chart [PAR]         - Generar gráfico técnico
/backtest_summary    - Resumen de backtest
/live_dashboard      - Estado del dashboard live
```

---

## ⚙️ Configuración Avanzada

### **Archivo Principal: `rules_config.json`**

#### **Configuración por Par**
```json
{
  "EURUSD": {
    "strategy": "eurusd_simple",
    "enabled": true,
    "risk_per_trade": 0.5,
    "max_daily_trades": 10,
    "min_rr_ratio": 1.5
  }
}
```

#### **Configuración Global**
```json
{
  "GLOBAL_SETTINGS": {
    "max_total_risk": 3.0,
    "max_daily_trades_all": 20,
    "max_simultaneous_positions": 5,
    "drawdown_limit": 25.0
  }
}
```

#### **Auto-Ejecución**
```json
{
  "auto_execution": {
    "enabled": true,
    "max_trades_per_period": 5,
    "duplicate_check_minutes": 60,
    "backtest_mode": true
  }
}
```

### **Filtros Avanzados**
Los filtros avanzados están **desactivados** para permitir testing de estrategias básicas:
```json
{
  "advanced_filters": {
    "enabled": false,
    "note": "Desactivado para testing de estrategias simplificadas"
  }
}
```

---

## 📈 Backtesting

### **Sistema Automático**
- **Tracking**: Todas las señales y ejecuciones
- **Base de datos**: `bot_state.db` (SQLite)
- **Métricas**: Win rate, drawdown, profit factor
- **Exportación**: JSON y dashboard HTML

### **Comandos de Backtest**
```bash
# Ver estadísticas
/backtest_summary

# Dashboard completo
Abrir: backtest_dashboard.html
```

### **Métricas Calculadas**
- ✄1�7 **Total de señales** generadas y ejecutadas
- ✄1�7 **Win rate** por estrategia y global
- ✄1�7 **Profit factor** y expectativa
- ✄1�7 **Drawdown máximo** y actual
- ✄1�7 **Distribución temporal** de trades

---

## 🔧 Solución de Problemas

### **Problemas Comunes**

#### **1. Bot no ejecuta órdenes**
```
Verificar:
✄1�7 AutoTrading habilitado en MT5 (botón verde)
✄1�7 Conexión a broker activa
✄1�7 Saldo suficiente en cuenta
✄1�7 Variable AUTO_EXECUTE_SIGNALS=1
```

#### **2. No se generan señales**
```
Verificar:
✄1�7 AUTOSIGNALS=1 en .env
✄1�7 Pares en AUTOSIGNAL_SYMBOLS
✄1�7 Estrategias habilitadas en rules_config.json
✄1�7 No se alcanzó límite de período (5 trades/12h)
```

#### **3. Señales duplicadas**
```
Sistema anti-duplicados activo:
✄1�7 Tolerancia por símbolo configurada
✄1�7 Ventana de 60 minutos
✄1�7 Logs muestran "SEÑAL DUPLICADA DETECTADA"
```

#### **4. Dashboard no actualiza**
```
Verificar:
✄1�7 Archivo live_dashboard.html existe
✄1�7 Permisos de escritura en directorio
✄1�7 Dashboard loop iniciado en logs
```

### **Logs de Diagnóstico**
```bash
# Ver logs en tiempo real
tail -f logs.txt

# Buscar errores específicos
grep "ERROR" logs.txt

# Ver señales rechazadas
grep "SIGNAL REJECTED" logs.txt
```

### **Reinicio Limpio**
```bash
# Parar bot
Ctrl+C

# Limpiar logs (opcional)
> logs.txt

# Reiniciar
python bot.py
```

---

## 📁 Estructura del Proyecto

### **Archivos Principales**
```
bot.py                    # Bot principal Discord + MT5
signals.py               # Estrategias de trading
rules_config.json        # Configuración de estrategias
mt5_client.py           # Cliente MetaTrader 5
live_dashboard.py       # Dashboard en tiempo real
```

### **Sistemas Auxiliares**
```
risk_manager.py         # Gestión de riesgo
backtest_tracker.py     # Sistema de backtesting
rejected_signals_tracker.py  # Tracking de rechazos
trailing_stops.py       # Trailing stops automáticos
market_opening_system.py     # Alertas de mercado
```

### **Utilidades**
```
charts.py              # Generación de gráficos
secrets_store.py       # Gestión segura de credenciales
user_management.py     # Gestión de usuarios Discord
commercial_commands.py # Comandos comerciales
```

### **Configuración**
```
.env                   # Variables de entorno
requirements.txt       # Dependencias Python
rules_config.json     # Configuración de trading
bot_state.db          # Base de datos SQLite
```

---

## 🎯 Estado Actual del Sistema

### **✄1�7 Funcionalidades Operativas**
- **Auto-ejecución** configurada y funcionando
- **3 estrategias** optimizadas y probadas
- **Sistema anti-duplicados** implementado
- **Límites por período** (5 trades/12h) activos
- **Dashboard live** con métricas reales
- **Logging completo** para debugging
- **Backtest automático** registrando todo

### **🔧 Configuración Actual**
- **Modo**: Backtest automatizado
- **Riesgo**: 0.5% por trade
- **Límites**: 5 trades cada 12 horas (total)
- **Pares**: EURUSD, XAUUSD, BTCEUR
- **Filtros**: Básicos (avanzados desactivados)

### **📊 Rendimiento Esperado**
- **Trades/día**: 5-10 (distribuidos equitativamente)
- **Win rate objetivo**: 60%+
- **Drawdown máximo**: <10%
- **Distribución**: Balanceada entre los 3 pares

---

## 📞 Soporte y Mantenimiento

### **Monitoreo Recomendado**
1. **Dashboard live** cada pocas horas
2. **Comando `/period_status`** para verificar límites
3. **Logs** para identificar problemas
4. **Balance MT5** para confirmar ejecuciones

### **Mantenimiento Periódico**
- **Semanal**: Revisar estadísticas de backtest
- **Mensual**: Optimizar parámetros según resultados
- **Trimestral**: Evaluar nuevas estrategias

### **Actualizaciones**
- Estrategias se pueden modificar en `signals.py`
- Configuración en `rules_config.json`
- Límites y filtros en tiempo real vía Discord

---

**🚀 El sistema está completamente operativo y listo para backtesting automatizado de largo plazo.**