# 📊 Guía del Sistema de Backtesting

## Descripción

El sistema de backtesting registra automáticamente todas las señales generadas por el bot y permite analizar el rendimiento histórico. Es similar al reporte de FundedEA pero adaptado a nuestro bot de Discord.

## Características

### ✅ Registro Automático
- **Todas las señales** se registran automáticamente cuando se generan
- **Estado de señales** se actualiza cuando se aceptan/rechazan
- **Resultados** se pueden registrar manualmente o automáticamente

### 📈 Estadísticas Disponibles
- Win Rate por período
- P&L total y promedio
- Rendimiento por símbolo (EURUSD, XAUUSD, BTCEUR)
- Rendimiento por estrategia
- Factor de beneficio
- Duración promedio de operaciones

### 📊 Reportes
- **Estadísticas rápidas** en Discord
- **Reporte HTML completo** similar al de FundedEA
- **Exportación CSV** para análisis externo

## Comandos Disponibles

### `backtest_stats [días]`
Muestra estadísticas rápidas en Discord
```
backtest_stats 7    # Últimos 7 días
backtest_stats 30   # Último mes
```

### `backtest_report [días]`
Genera reporte HTML completo
```
backtest_report 30  # Reporte del último mes
```

### `close_signal [id] [resultado] [p&l] [precio_cierre]`
Simula el cierre de una señal (para testing)
```
close_signal 1 WIN 25.50 1.0850
close_signal 2 LOSS -15.00 1.0820
close_signal 3 BREAKEVEN 0 1.0835
```

## Flujo de Trabajo Recomendado

### 1. **Configuración Inicial**
- El sistema está ya integrado y funcionando
- No requiere configuración adicional

### 2. **Uso Diario**
- Deja el bot funcionando con autoseñales activadas
- Acepta/rechaza señales normalmente
- El sistema registra todo automáticamente

### 3. **Análisis Semanal**
```
backtest_stats 7
```
- Revisa win rate semanal
- Identifica qué símbolos funcionan mejor
- Ajusta estrategias si es necesario

### 4. **Análisis Mensual**
```
backtest_report 30
```
- Genera reporte completo
- Analiza tendencias a largo plazo
- Compara con meses anteriores

## Interpretación de Resultados

### 🎯 Win Rate
- **>60%**: Excelente rendimiento
- **50-60%**: Buen rendimiento
- **40-50%**: Rendimiento aceptable
- **<40%**: Requiere optimización

### 💰 Factor de Beneficio
- **>2.0**: Excelente
- **1.5-2.0**: Bueno
- **1.2-1.5**: Aceptable
- **<1.2**: Requiere mejoras

### 📊 Por Símbolo
- Identifica qué pares funcionan mejor
- Ajusta configuraciones específicas
- Considera desactivar pares problemáticos

## Archivos del Sistema

### `backtest_tracker.py`
Clase principal del sistema de backtesting

### `backtest_data.json`
Base de datos de todas las señales (se crea automáticamente)

### Reportes Generados
- `backtest_report_YYYYMMDD_HHMMSS.html`
- `backtest_export_YYYYMMDD_HHMMSS.csv`

## Ejemplo de Uso Completo

### Día 1: Configuración
```
# El bot ya está configurado, solo asegúrate de que esté funcionando
/status
```

### Días 2-7: Operación Normal
```
# Deja el bot funcionando
# Acepta/rechaza señales normalmente
/accept 1
/reject 2
```

### Día 8: Análisis Semanal
```
backtest_stats 7
```

### Día 30: Análisis Mensual
```
backtest_report 30
```

## Simulación de Resultados (Para Testing)

Si quieres probar el sistema sin esperar resultados reales:

```
# Simula algunas operaciones cerradas
close_signal 1 WIN 25.50 1.0850
close_signal 2 WIN 18.75 2650.00
close_signal 3 LOSS -12.30 1.0820
close_signal 4 WIN 31.20 95500.00

# Luego revisa las estadísticas
backtest_stats 1
```

## Ventajas vs FundedEA

### ✅ Nuestro Sistema
- **Integrado** con Discord
- **Tiempo real** - no necesita esperar
- **Personalizable** para nuestras estrategias
- **Gratuito** y bajo nuestro control

### 📊 Similar a FundedEA
- **Formato de reporte** similar
- **Estadísticas completas**
- **Análisis por símbolo**
- **Historial detallado**

## Próximas Mejoras

1. **Auto-cierre** basado en MT5
2. **Alertas** de rendimiento
3. **Comparación** entre períodos
4. **Gráficos** de equity curve
5. **Integración** con MT5 para P&L real

---

**¡El sistema está listo para usar! Solo deja el bot funcionando y empezará a registrar todas las señales automáticamente.**