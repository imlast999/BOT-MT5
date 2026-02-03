# 🧩 PLAN DE REFACTOR - ARQUITECTURA LIMPIA

## 📊 ANÁLISIS ACTUAL

### Problemas Identificados
- **bot.py**: 4536 líneas (god file)
- **signals.py**: 1820 líneas (mezcla todo)
- **Fragmentación**: Múltiples archivos duplicando lógica
- **Fragilidad**: Cambios pequeños rompen múltiples partes
- **Mantenibilidad**: Difícil de modificar sin riesgo

### Archivos a Consolidar/Eliminar
- `confidence_system.py` → Integrar en core
- `duplicate_filter.py` → Integrar en core  
- `signal_integrator.py` → Eliminar (duplica lógica)
- `signals_simplified.py` → Eliminar (duplica lógica)
- Otros archivos de implementación anterior

## 🏗️ NUEVA ESTRUCTURA

```
/core/
    engine.py       # Orquestador principal de señales
    scoring.py      # Sistema de scoring unificado  
    confidence.py   # Sistema de confianza integrado
    filters.py      # Filtros de trading consolidados
    
/strategies/
    base.py         # Clase base para estrategias
    eurusd.py       # Estrategia específica EURUSD
    xauusd.py       # Estrategia específica XAUUSD
    btceur.py       # Estrategia específica BTCEUR
    
/services/
    execution.py    # Lógica de ejecución de trades
    dashboard.py    # Dashboard y logging inteligente
    session.py      # Gestión de sesión y estadísticas
    
bot.py              # Solo orquestador Discord (~1000 líneas)
signals.py          # Solo detección básica + dispatch (~500 líneas)
```

## 🎯 PRINCIPIOS DE REFACTOR

### ✅ Hacer
- **Una responsabilidad por archivo**
- **Integrar mejoras en archivos existentes**
- **Refactorizar, no duplicar**
- **Mantener funcionalidad durante el proceso**
- **Separar dominio de infraestructura**

### ❌ No Hacer
- **Crear sistemas paralelos**
- **Duplicar lógica existente**
- **Romper funcionalidad actual**
- **Crear archivos gigantes nuevos**

## 📋 FASES DE IMPLEMENTACIÓN

### Fase 1: Core Engine (PRIORIDAD ALTA)
1. Crear `core/engine.py` con lógica principal de señales
2. Mover `_detect_signal_wrapper` y lógica relacionada
3. Integrar sistema de scoring flexible de `signals.py`
4. Consolidar sistema de confianza de `confidence_system.py`
5. Integrar filtro de duplicados de `duplicate_filter.py`

### Fase 2: Estrategias (PRIORIDAD ALTA)  
1. Crear `strategies/base.py` con clase base
2. Extraer `rule_eurusd`, `rule_xauusd`, `rule_btcusdt` a archivos separados
3. Simplificar cada estrategia para que solo detecte oportunidades
4. Eliminar lógica de scoring/confianza de estrategias individuales

### Fase 3: Services (PRIORIDAD MEDIA)
1. Mover dashboard y logging inteligente a `services/dashboard.py`
2. Crear `services/session.py` para gestión de sesión
3. Mover lógica de ejecución a `services/execution.py`

### Fase 4: Limpieza Final (PRIORIDAD MEDIA)
1. Refactor `bot.py` para usar solo core engine
2. Simplificar `signals.py` a dispatch básico
3. Eliminar archivos duplicados
4. Actualizar imports y dependencias

## 🔧 DETALLES TÉCNICOS

### Core Engine Responsibilities
- Orquestar detección de señales
- Aplicar scoring y confianza
- Gestionar filtros y validaciones
- Decidir mostrar/ejecutar señales

### Strategy Responsibilities  
- Detectar setups de mercado
- Calcular niveles (entry, SL, TP)
- Retornar contexto para scoring
- NO gestionar confianza/logging/risk

### Services Responsibilities
- Dashboard: Logging inteligente y visualización
- Session: Estadísticas y límites de trading
- Execution: Lógica de ejecución de trades

### Bot.py Responsibilities
- Comandos Discord únicamente
- Orquestación de alto nivel
- Gestión de estado de Discord
- NO lógica de negocio

## 📈 BENEFICIOS ESPERADOS

1. **Mantenibilidad**: Cada archivo tiene una responsabilidad clara
2. **Testabilidad**: Componentes aislados fáciles de probar
3. **Escalabilidad**: Fácil agregar nuevas estrategias/filtros
4. **Estabilidad**: Cambios localizados, menor riesgo
5. **Claridad**: Código más fácil de entender y modificar

## ⚠️ RIESGOS Y MITIGACIÓN

### Riesgos
- Romper funcionalidad durante refactor
- Introducir bugs en el proceso
- Perder configuraciones existentes

### Mitigación
- Refactor incremental manteniendo funcionalidad
- Probar cada fase antes de continuar
- Mantener archivos originales como backup
- Implementar paso a paso con validación

## 🚀 RESULTADO ESPERADO

Al final del refactor:
- `bot.py`: ~1000 líneas (solo Discord)
- `signals.py`: ~500 líneas (solo dispatch)
- Código modular y mantenible
- Misma funcionalidad, mejor arquitectura
- Base sólida para futuras mejoras