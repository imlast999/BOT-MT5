# 🤖 Trading Bot MT5 + Discord - Sistema Simplificado v2.0

Bot de trading automatizado que conecta MetaTrader 5 con Discord. **Rediseñado para ser simple, rentable y generar señales reales.**

## 🎯 FILOSOFÍA DEL BOT

**El bot es una herramienta de análisis, no un casino.**

✅ **Lo que HACE:**
- Propone trades basados en análisis técnico
- Requiere confirmación humana para ejecutar
- Genera 8-12 señales/día con calidad
- Usa sistema de scoring flexible (no perfección imposible)

❌ **Lo que NO HACE:**
- Auto-ejecutar sin confirmación
- Garantizar ganancias
- Operar 24/7 sin control
- Generar señales perfectas todo el tiempo

## 🚀 SISTEMA SIMPLIFICADO v2.0

### **Mejoras Implementadas:**
- ✅ **1 setup + máximo 2 confirmaciones** (no más lógica AND estricta)
- ✅ **Sistema de scoring flexible** (66% mínimo en vez de 100%)
- ✅ **Max trades realistas**: 12/día total (4+3+5)
- ✅ **R:R mínimo 1.5**, preferible 2.0
- ✅ **Estrategias market-logic** específicas por activo
- ✅ **Logs detallados** de por qué se rechazan señales
- ✅ **Gestión de riesgo normalizada** por % de cuenta

### **Estrategias por Activo:**

#### 🇪🇺 **EURUSD** - Breakout + Pullback + Sesión
- **Setup**: Breakout de rango 15 períodos
- **Confirmaciones**: RSI neutral (40-60) + Sesión activa
- **Gestión**: SL ATR×1.5, TP SL×2.0, Max 4/día

#### 🥇 **XAUUSD** - Fakeouts + Rejection + Liquidez  
- **Setup**: Precio cerca de nivel psicológico (±10$)
- **Confirmaciones**: Mecha >30% + Sesión liquidez
- **Gestión**: SL $8, TP $16, Max 3/día

#### ₿ **BTCEUR** - Momentum + Tendencia + Expansión
- **Setup**: EMA12 vs EMA26 con separación
- **Confirmaciones**: EMA50 filtro + ATR expansión
- **Gestión**: SL ATR×2.0, TP SL×1.8, Max 5/día

## 🎮 Comandos Discord

### Comandos Básicos
- `/signal [symbol]` - Generar señal manual
- `/chart [symbol]` - Mostrar gráfico técnico  
- `/positions` - Ver posiciones abiertas
- `/balance` - Consultar balance
- `/status` - Estado del sistema simplificado

### Gestión de Señales
- `/autosignals on/off` - Activar/desactivar automáticas
- `/signal_status` - Ver contadores y límites diarios
- `/reset_counts` - Resetear contadores (admin)

### Sistema Simplificado
- `/system_info` - Info del sistema simplificado
- `/scoring_test [symbol]` - Probar scoring en tiempo real
- `/strategy_details [symbol]` - Detalles de estrategia

## 📋 Configuración Rápida

### **1. Variables de Entorno (.env)**
```bash
# Discord
DISCORD_TOKEN=tu_token_discord
AUTHORIZED_USER_ID=tu_user_id

# MT5
MT5_LOGIN=tu_cuenta
MT5_PASSWORD=tu_password
MT5_SERVER=tu_servidor

# Sistema Simplificado
SIMPLIFIED_SYSTEM=1
MAX_TRADES_PER_DAY=12
AUTOSIGNALS=1
AUTOSIGNAL_SYMBOLS=EURUSD,XAUUSD,BTCEUR
```

### **2. Configuración de Estrategias (rules_config_simplified.json)**
```json
{
  "EURUSD": {
    "strategy": "eurusd_simple",
    "max_daily_trades": 4,
    "min_score": 0.66,
    "min_rr_ratio": 1.5
  },
  "XAUUSD": {
    "strategy": "xauusd_simple", 
    "max_daily_trades": 3,
    "min_score": 0.60,
    "min_rr_ratio": 2.0
  },
  "BTCEUR": {
    "strategy": "btceur_simple",
    "max_daily_trades": 5,
    "min_score": 0.65,
    "min_rr_ratio": 1.5
  }
}
```

## 🧮 Sistema de Scoring

### **Cómo Funciona:**
1. **Setup Principal** (obligatorio): 50% del score
2. **Confirmaciones** (1-2): 50% del score
3. **Score Mínimo**: 66% para aprobar señal

### **Ejemplo EURUSD:**
- ✅ Setup: Breakout detectado (50%)
- ✅ Confirmación 1: RSI neutral (25%)
- ❌ Confirmación 2: Fuera de sesión (0%)
- **Score Final**: 75% ✅ (>66% → Señal aprobada)

### **Ventajas vs Sistema Anterior:**
- ❌ **Antes**: Todas las condiciones AND (0% si falla una)
- ✅ **Ahora**: Sistema flexible (puede fallar 1 confirmación)

## 📊 Gestión de Riesgo

### **Límites Diarios Realistas:**
- **EURUSD**: 4 trades/día máximo
- **XAUUSD**: 3 trades/día máximo  
- **BTCEUR**: 5 trades/día máximo
- **TOTAL**: 12 trades/día máximo

### **Gestión por Trade:**
- **Riesgo**: 0.5-1.0% de la cuenta por trade
- **R:R Mínimo**: 1.5 (preferible 2.0)
- **SL Dinámico**: Basado en ATR o niveles fijos
- **TP Objetivo**: 2x el riesgo mínimo

## 🔍 Logs y Debugging

### **Logs Mejorados:**
```
[14:23:15] 🎯 SEÑAL GENERADA: EURUSD BUY - Sistema: simplified
   Explicación: EURUSD Simple: Breakout BUY + Score 0.75 + R:R 2.1
   Confianza: MEDIUM-HIGH
   R:R: 2.1

[14:25:30] ❌ XAUUSD RECHAZADO: Score insuficiente: 0.58 < 0.60
   Score: Setup 0.50 + Confirmaciones 0.08 = 0.58
   Confirmaciones: 0/2 (Mecha: 15% < 30%, Sesión: Fuera de horario)
```

### **Información de Rechazo:**
- Razón específica del rechazo
- Score obtenido vs requerido
- Detalles de cada confirmación
- Sugerencias de mejora

## 🚀 Instalación

### **1. Clonar Repositorio**
```bash
git clone https://github.com/tu-repo/trading-bot-mt5
cd trading-bot-mt5
```

### **2. Instalar Dependencias**
```bash
pip install -r requirements.txt
```

### **3. Configurar Variables**
```bash
cp .env.example .env
# Editar .env con tus credenciales
```

### **4. Ejecutar Bot**
```bash
python bot.py
```

## 🔧 Migración desde Sistema Anterior

### **Para Activar Sistema Simplificado:**
1. Añadir `SIMPLIFIED_SYSTEM=1` en `.env`
2. Copiar `rules_config_simplified.json` como configuración
3. Reiniciar el bot
4. Verificar con `/system_info`

### **Compatibilidad:**
- ✅ Mantiene compatibilidad con comandos existentes
- ✅ Fallback automático al sistema original si falla
- ✅ Misma integración con MT5 y Discord
- ✅ Dashboard y logs funcionan igual

## 📈 Rendimiento Esperado

### **Frecuencia de Señales:**
- **Objetivo**: 8-12 señales/día total
- **Distribución**: EURUSD (3-4), XAUUSD (2-3), BTCEUR (3-5)
- **Calidad**: Mínimo 66% de score, R:R ≥1.5

### **Mejoras vs Sistema Anterior:**
- 🔥 **+300% más señales** (de 2-3/día a 8-12/día)
- 🎯 **Mejor calidad** (scoring vs AND estricto)
- ⚡ **Menos rechazos** por filtros excesivos
- 📊 **Logs más útiles** para debugging

## 🛠 Solución de Problemas

### **Pocas Señales:**
```bash
# Verificar configuración
/system_info

# Ver contadores actuales
/signal_status

# Probar scoring en tiempo real
/scoring_test EURUSD
```

### **Señales Rechazadas:**
- Revisar logs detallados
- Verificar score mínimo en configuración
- Ajustar `min_score` si es necesario (0.50-0.70)

### **Errores Comunes:**
- **"Sin datos suficientes"**: Verificar conexión MT5
- **"Límite diario alcanzado"**: Normal, esperar reset diario
- **"Score insuficiente"**: Ajustar configuración o esperar mejor setup

## 📞 Soporte

### **Logs Importantes:**
- `logs/logs_YYYY-MM-DD_HH-MM-SS.txt` - Log completo
- Buscar líneas con `🎯 SEÑAL` o `❌ RECHAZADO`

### **Comandos de Debug:**
- `/system_info` - Estado del sistema
- `/signal_status` - Contadores y límites
- `/scoring_test [symbol]` - Test de scoring en vivo

---

## 🎯 Próximas Mejoras

### **En Desarrollo:**
- [ ] Optimización automática de thresholds
- [ ] Backtesting del sistema simplificado
- [ ] Alertas de mercado inteligentes
- [ ] Dashboard específico para scoring
- [ ] Análisis de correlación entre señales

### **Sugerencias de Uso:**
1. **Empezar conservador**: min_score = 0.70
2. **Monitorear logs** las primeras semanas
3. **Ajustar gradualmente** según rendimiento
4. **Usar /scoring_test** para entender el sistema
5. **Revisar contadores diarios** con `/signal_status`

---

**🎯 El objetivo es generar señales reales y útiles, no perfección imposible.**