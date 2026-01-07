# Bot de Trading MT5 con Integración Discord

Un sofisticado bot de trading automatizado que integra MetaTrader 5 con Discord para generación de señales en tiempo real, gestión de riesgo y ejecución de operaciones en múltiples pares de divisas y activos.

## 🚀 Características

### Capacidades de Trading Principales
- **Soporte Multi-Activo**: EURUSD, XAUUSD (Oro), BTCEUR (Bitcoin)
- **Detección Avanzada de Señales**: Múltiples estrategias con sistemas de respaldo
- **Gestión de Riesgo**: Dimensionamiento automático de posiciones, protección de drawdown, filtros de correlación
- **Ejecución en Tiempo Real**: Integración directa con MT5 y gestión de órdenes
- **Gráficos Profesionales**: Gráficos de velas de alta calidad con indicadores técnicos

### Integración con Discord
- **Comandos Slash**: Interfaz moderna de Discord con más de 25 comandos
- **Auto-Señales**: Transmisión automática de señales cada 2 minutos
- **Controles Interactivos**: Aceptar/rechazar señales con botones y modales
- **Monitoreo en Tiempo Real**: Seguimiento de posiciones y estadísticas de rendimiento
- **Alertas de Mercado**: Análisis pre-mercado y notificaciones de sesión

### Sistemas Avanzados
- **Análisis Multi-Timeframe**: Señales H1 con entradas de precisión M15
- **Trailing Stops**: Protección automática de beneficios con gestión de breakeven
- **Alertas de Apertura de Mercado**: Análisis pre-mercado para sesiones de Londres/Nueva York
- **Filtros de Confluencia**: Sistema de confirmación múltiple para calidad de señales
- **Estrategias de Respaldo**: Sistema jerárquico de estrategias para generación consistente de señales

## 📋 Requisitos

### Dependencias de Software
- Python 3.9+
- Terminal MetaTrader 5
- Token de Bot de Discord
- Paquetes de Python requeridos (ver `requirements.txt`)

### Cuenta de Trading
- Cuenta Demo o Real de MT5
- Broker compatible con acceso a EURUSD, XAUUSD, BTCEUR
- Balance mínimo: $1000 (recomendado $5000+ para pruebas demo)

## 🛠️ Instalación

### 1. Clonar Repositorio
```bash
git clone https://github.com/tuusuario/mt5-discord-bot.git
cd mt5-discord-bot
```

### 2. Instalar Dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar Entorno
Crear un archivo `.env` con tus configuraciones:
```env
# Configuración Discord
DISCORD_TOKEN=tu_token_bot_discord
GUILD_ID=tu_id_servidor_discord
AUTHORIZED_USER_ID=tu_id_usuario_discord

# Configuración Trading
AUTOSIGNALS=1
AUTOSIGNAL_INTERVAL=120
AUTOSIGNAL_SYMBOLS=EURUSD,XAUUSD,BTCEUR
MAX_TRADES_PER_DAY=7

# Gestión de Riesgo
DEFAULT_RISK_PCT=1.0
DEMO_MODE=1
```

### 4. Configurar Bot de Discord
1. Crear una aplicación Discord en [Portal de Desarrolladores Discord](https://discord.com/developers/applications)
2. Crear un bot y copiar el token
3. Invitar bot a tu servidor con scope `applications.commands`
4. Crear un canal `#signals` para señales automáticas

### 5. Configurar MT5
1. Instalar e iniciar sesión en MetaTrader 5
2. Habilitar trading algorítmico en Herramientas → Opciones → Asesores Expertos
3. Asegurar que los símbolos EURUSD, XAUUSD, BTCEUR estén disponibles

## 🎮 Uso

### Iniciar el Bot
```bash
python bot.py
```

### Comandos Esenciales

#### Generación de Señales
- `/signal [símbolo]` - Generar señal manual para par específico
- `/force_autosignal [símbolo]` - Forzar generación de señal automática
- `/test_fallback [símbolo]` - Probar sistema de estrategias de respaldo

#### Gestión de Trading
- `/accept [id_señal]` - Aceptar y ejecutar señal pendiente
- `/reject [id_señal]` - Rechazar señal pendiente
- `/positions` - Ver posiciones abiertas
- `/close_position [ticket]` - Cerrar posición específica

#### Análisis de Mercado
- `/market_overview` - Estado actual del mercado para todos los pares
- `/chart [símbolo] [timeframe]` - Generar gráfico profesional
- `/pre_market_analysis [símbolo]` - Análisis de condiciones pre-mercado
- `/next_opening` - Próximo horario de apertura de mercado principal

#### Configuración y Monitoreo
- `/autosignals` - Controlar generación automática de señales
- `/pairs_config` - Ver configuraciones actuales de pares
- `/demo_stats` - Estadísticas de cuenta y rendimiento
- `/strategy_performance [días]` - Rendimiento por estrategia
- `/risk_status` - Estado actual de gestión de riesgo

### Configuración de Estrategias

El bot usa un sistema de configuración sofisticado en `rules_config.json`:

```json
{
  "EURUSD": {
    "strategy": "eurusd_advanced",
    "fallback_strategy": "ema50_200",
    "max_daily_trades": 3,
    "min_rr_ratio": 2.5,
    "risk_per_trade": 1.2
  }
}
```

## 🧠 Estrategias de Trading

### Estrategias Principales
1. **EURUSD Avanzada**: Confirmación de breakout con detección de consolidación
2. **XAUUSD Avanzada**: Reversión a la media en niveles psicológicos
3. **BTCEUR Avanzada**: Trading de crypto basado en momentum

### Sistema de Respaldo
- **Nivel 1**: Estrategias avanzadas principales
- **Nivel 2**: Indicadores técnicos simples (EMA, RSI, MACD)
- **Nivel 3**: Respaldo de emergencia (deshabilitado por defecto para control de calidad)

### Gestión de Riesgo
- **Dimensionamiento de Posición**: Cálculo automático de lotes basado en balance de cuenta
- **Protección de Drawdown**: Límites máximos de pérdida diaria
- **Filtros de Correlación**: Prevenir sobre-exposición a pares correlacionados
- **Filtros de Sesión**: Operar solo durante horas óptimas de mercado

## 📊 Características de Rendimiento

### Monitoreo en Tiempo Real
- Seguimiento de P&L en vivo
- Estadísticas de tasa de acierto
- Comparación de rendimiento de estrategias
- Dashboard de métricas de riesgo

### Análisis Avanzado
- Análisis multi-timeframe
- Sistema de puntuación de confluencia
- Optimización de sesiones de mercado
- Filtrado basado en volatilidad

## 🔧 Archivos de Configuración

### Archivos Principales
- `bot.py` - Bot principal de Discord y manejadores de comandos
- `signals.py` - Detección de señales e implementación de estrategias
- `mt5_client.py` - Integración con MetaTrader 5
- `risk_manager.py` - Gestión de riesgo y dimensionamiento de posiciones
- `charts.py` - Generación de gráficos profesionales

### Módulos Avanzados
- `advanced_filters.py` - Sistemas de confluencia y filtrado
- `trailing_stops.py` - Protección automática de beneficios
- `multi_timeframe.py` - Análisis cross-timeframe
- `market_opening_system.py` - Alertas basadas en sesiones
- `position_manager.py` - Ejecución de operaciones y gestión

### Configuración
- `rules_config.json` - Reglas de trading y parámetros de estrategia
- `.env` - Variables de entorno y datos sensibles
- `requirements.txt` - Dependencias de Python

## 🚨 Descargo de Responsabilidad de Riesgo

**Este software es solo para fines educativos y de investigación. El trading de instrumentos financieros implica un riesgo sustancial de pérdida y no es adecuado para todos los inversores. El rendimiento pasado no garantiza resultados futuros.**

- Siempre prueba primero en cuentas demo
- Nunca arriesgues más de lo que puedes permitirte perder
- Entiende las estrategias antes de usarlas
- Monitorea las posiciones regularmente
- Mantén el terminal MT5 funcionando durante horas de trading

## 🤝 Contribuir

1. Hacer fork del repositorio
2. Crear una rama de característica (`git checkout -b feature/caracteristica-increible`)
3. Hacer commit de tus cambios (`git commit -m 'Agregar característica increíble'`)
4. Push a la rama (`git push origin feature/caracteristica-increible`)
5. Abrir un Pull Request

## 📝 Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para detalles.

## 🆘 Soporte

- **Issues**: Reportar bugs vía GitHub Issues
- **Documentación**: Revisar el comando `/help` en Discord
- **Testing**: Usar `/test_fallback` y `/debug_signals` para resolución de problemas

## 🔄 Historial de Versiones

### v2.0.0 (Actual)
- Sistema multi-estrategia avanzado
- Integración de comandos slash de Discord
- Generación de gráficos profesionales
- Gestión de riesgo integral
- Alertas de apertura de mercado
- Sistema de trailing stops

### v1.0.0
- Generación básica de señales
- Integración MT5
- Comandos simples de Discord

---

**⚠️ Recuerda**: Esta es una herramienta de trading poderosa. Siempre entiende los riesgos involucrados en el trading automatizado y prueba exhaustivamente antes de usar con dinero real.