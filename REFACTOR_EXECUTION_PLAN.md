# 🧩 PLAN DE REFACTOR - EJECUCIÓN INMEDIATA

## 🎯 OBJETIVO
Consolidar y refactorizar el proyecto para reducir fragmentación y mejorar mantenibilidad.

## 📋 ESTADO ACTUAL DETECTADO

### Problemas Identificados:
- **bot.py**: 4500+ líneas, mezcla orquestación, comandos, lógica de negocio, logging, etc.
- **signals.py**: 1500+ líneas, mezcla detección, scoring, estrategias, filtros
- **Fragmentación**: Muchos archivos nuevos creados (confidence_system.py, duplicate_filter.py, etc.)
- **Duplicación**: Lógica repetida entre archivos
- **Responsabilidades mezcladas**: Un archivo hace muchas cosas

### Estructura Actual:
```
/core (parcialmente implementado)
/strategies (parcialmente implementado)  
/services (vacío)
bot.py (god file)
signals.py (god file)
+ 20+ archivos auxiliares fragmentados
```

## 🗂️ NUEVA ESTRUCTURA PROPUESTA

```
/core/
  ├── engine.py          # Orquestador principal
  ├── scoring.py         # Sistema de scoring integrado
  ├── risk.py           # Gestión de riesgo
  ├── filters.py        # Filtros consolidados
  └── __init__.py

/strategies/
  ├── base.py           # Clase base para estrategias
  ├── eurusd.py         # Estrategia EURUSD limpia
  ├── xauusd.py         # Estrategia XAUUSD limpia
  ├── btceur.py         # Estrategia BTCEUR limpia
  └── __init__.py

/services/
  ├── execution.py      # Ejecución de trades
  ├── logging.py        # Sistema de logging inteligente
  ├── dashboard.py      # Dashboard y métricas
  └── __init__.py

bot.py                  # Solo orquestador Discord + comandos
signals.py              # Solo dispatcher de estrategias
```

## 🔄 PASOS DE EJECUCIÓN

### FASE 1: Crear Core Engine
1. ✅ Mover lógica de orquestación a `/core/engine.py`
2. ✅ Integrar sistema de scoring en `/core/scoring.py`
3. ✅ Consolidar filtros en `/core/filters.py`
4. ✅ Mover gestión de riesgo a `/core/risk.py`

### FASE 2: Limpiar Estrategias
1. ✅ Refactorizar estrategias existentes
2. ✅ Mover lógica específica de cada par a su archivo
3. ✅ Eliminar duplicación entre estrategias

### FASE 3: Crear Services
1. ✅ Mover logging inteligente a `/services/logging.py`
2. ✅ Consolidar dashboard en `/services/dashboard.py`
3. ✅ Crear servicio de ejecución en `/services/execution.py`

### FASE 4: Simplificar Archivos Principales
1. ✅ Reducir bot.py a solo comandos Discord + orquestación
2. ✅ Reducir signals.py a solo dispatcher
3. ✅ Eliminar archivos fragmentados innecesarios

### FASE 5: Integración y Testing
1. ✅ Actualizar imports en todos los archivos
2. ✅ Verificar que todo funciona
3. ✅ Eliminar archivos obsoletos

## 🛡️ PRINCIPIOS APLICADOS

- **Una responsabilidad por archivo**
- **Integración en lugar de fragmentación**
- **Reutilización de código existente**
- **Mantenimiento de funcionalidad actual**
- **Reducción de complejidad**

## 📊 RESULTADO ESPERADO

- **bot.py**: ~500 líneas (solo comandos + orquestación)
- **signals.py**: ~200 líneas (solo dispatcher)
- **Archivos core**: Responsabilidades claras y separadas
- **Estrategias**: Limpias y enfocadas solo en detección
- **Services**: Servicios reutilizables y modulares

---

**INICIO DE EJECUCIÓN**: Ahora
**TIEMPO ESTIMADO**: 30-45 minutos
**PRIORIDAD**: CRÍTICA - Estabilidad del proyecto