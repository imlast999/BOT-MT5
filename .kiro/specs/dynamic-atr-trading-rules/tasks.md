# Plan de Implementación: Reglas de Trading Dinámicas Basadas en ATR

## Resumen

Este plan de implementación transforma el bot de trading semi-automático existente de cálculos fijos basados en pips a reglas dinámicas basadas en ATR. El enfoque se centra en mejorar los componentes existentes en lugar de reconstruir, manteniendo la arquitectura actual mientras se añade funcionalidad adaptativa de ATR y puntuación de confianza simplificada.

## Tareas

- [x] 1. Mejorar cálculos de ATR y funciones utilitarias
  - Extender cálculos de ATR existentes en `signals.py` con funciones de medición relativa
  - Añadir utilidades de normalización ATR para fuerza de breakout y separación EMA
  - Crear funciones de umbral ATR específicas por activo
  - _Requisitos: 1.1, 1.2, 2.4, 2.5, 4.4_

- [x] 1.1 Escribir test de propiedades para cálculos relativos de ATR
  - **Propiedad 2: Clasificación de Fuerza Relativa ATR**
  - **Valida: Requisitos 1.1, 1.2, 2.4, 2.5, 4.4**

- [x] 2. Actualizar estrategia EURUSD con reglas dinámicas basadas en ATR
  - Modificar `eurusd_simple_strategy()` para usar cálculos de breakout relativos a ATR
  - Actualizar lógica de separación EMA para usar normalización ATR
  - Implementar puntuación RSI optimizada para señales buy/sell (55-70 buy, 30-45 sell)
  - Actualizar cálculos de stop loss y take profit (ATR×1.5, SL×2.0)
  - _Requisitos: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.4, 2.5_

- [x] 2.1 Escribir test de propiedades para gestión de riesgo ATR de EURUSD
  - **Propiedad 1: Gestión de Riesgo Basada en ATR (porción EURUSD)**
  - **Valida: Requisitos 1.3, 1.4**

- [x] 2.2 Escribir test de propiedades para puntuación RSI de EURUSD
  - **Propiedad 3: Optimización de Puntuación RSI**
  - **Valida: Requisitos 2.1, 2.2**

- [x] 3. Actualizar estrategia XAUUSD con niveles dinámicos y filtrado de sesión
  - Modificar `xauusd_simple_strategy()` para usar generación de niveles dinámicos (round(price/50)*50)
  - Implementar clasificación de distancia (≤5$ fuerte, ≤8$ medio, ≤10$ débil)
  - Añadir filtrado de sesión Londres/NY (8-17 GMT, 13-22 GMT)
  - Mantener cantidades fijas en dólares para SL (12$) y TP (24$)
  - _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7_

- [x] 3.1 Escribir test de propiedades para generación de niveles dinámicos XAUUSD
  - **Propiedad 5: Generación de Niveles Dinámicos**
  - **Valida: Requisitos 3.1, 3.2**

- [x] 3.2 Escribir test de propiedades para filtrado de sesión XAUUSD
  - **Propiedad 6: Filtrado de Sesión**
  - **Valida: Requisitos 3.3**

- [x] 3.3 Escribir test de propiedades para gestión de dólares fijos XAUUSD
  - **Propiedad 4: Gestión de Dólares Fijos XAUUSD**
  - **Valida: Requisitos 3.4, 3.5**

- [x] 4. Actualizar estrategia BTCEUR con análisis de pendiente EMA
  - Modificar `btceur_simple_strategy()` para calcular pendiente EMA50 (actual - actual-3)
  - Implementar lógica de dirección de señal basada en pendiente (positiva→buy, negativa→sell)
  - Actualizar separaciones para usar mediciones relativas a ATR
  - Actualizar cálculos de stop loss y take profit (ATR×2.5 para ambos)
  - Establecer expiración de señal a 180-240 minutos
  - _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 4.1 Escribir test de propiedades para análisis de momentum BTCEUR
  - **Propiedad 7: Análisis de Momentum BTCEUR**
  - **Valida: Requisitos 4.1, 4.2, 4.3**

- [x] 4.2 Escribir test de propiedades para gestión de riesgo ATR de BTCEUR
  - **Propiedad 1: Gestión de Riesgo Basada en ATR (porción BTCEUR)**
  - **Valida: Requisitos 1.5, 1.6**

- [x] 5. Checkpoint - Asegurar que todas las pruebas de estrategia pasen
  - Asegurar que todas las pruebas pasen, preguntar al usuario si surgen dudas.

- [x] 6. Simplificar sistema de puntuación de confianza
  - Modificar funciones de cálculo de confianza existentes para usar exactamente 4 factores (2 estructurales, 1 calidad, 1 contexto)
  - Eliminar lógica AND compleja que requiere puntuaciones perfectas
  - Actualizar `_calculate_eurusd_confidence()`, `_calculate_xauusd_confidence()`, `_calculate_btceur_confidence()`
  - Asegurar que solo se usen niveles HIGH/MEDIUM_HIGH/MEDIUM/LOW_MEDIUM/LOW
  - _Requisitos: 5.1, 5.2, 5.3, 5.5_

- [x] 6.1 Escribir test de propiedades para cálculo de confianza simplificado
  - **Propiedad 9: Cálculo de Confianza Simplificado**
  - **Valida: Requisitos 5.1, 5.2, 5.5**

- [ ] 7. Actualizar lógica de ejecución para automatización basada en confianza
  - Modificar `_auto_execute_signal()` y funciones relacionadas en `bot.py`
  - Implementar HIGH→auto-ejecutar, MEDIUM_HIGH→confirmación manual, MEDIUM/LOW→solo log
  - Actualizar lógica de visualización de señales para mostrar solo señales MEDIUM_HIGH con botones de confirmación
  - Asegurar integración adecuada con sistema de auto-ejecución existente
  - _Requisitos: 6.1, 6.2, 6.3, 6.5_

- [ ] 7.1 Escribir test de propiedades para lógica de ejecución basada en confianza
  - **Propiedad 10: Lógica de Ejecución Basada en Confianza**
  - **Valida: Requisitos 6.1, 6.2, 6.3**

- [ ] 8. Mejorar sistema de logging de señales rechazadas
  - Extender `rejected_signals_tracker.py` para capturar datos completos de señales
  - Añadir logging estructurado para todas las señales independientemente del nivel de confianza
  - Incluir valores ATR, fuerza de breakout, ratios de separación en datos loggeados
  - Asegurar que las razones de rechazo estén categorizadas apropiadamente (weak_breakout, low_atr, flat_ema)
  - Actualizar formato de logging para incluir todos los campos requeridos
  - _Requisitos: 6.4, 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 8.1 Escribir test de propiedades para logging completo de señales
  - **Propiedad 11: Logging Completo de Señales**
  - **Valida: Requisitos 6.4, 7.1, 7.2, 7.3, 7.4, 7.5**

- [ ] 9. Actualizar gestión de configuración para parámetros dinámicos
  - Modificar `rules_config.json` para incluir nuevos multiplicadores ATR y umbrales
  - Añadir recarga en caliente de configuración para parámetros ATR, pesos de confianza, límites de trading
  - Actualizar configuraciones específicas por activo con nuevos parámetros dinámicos
  - Asegurar que filtros de sesión y tiempos de expiración sean configurables
  - _Requisitos: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 9.1 Escribir test de propiedades para parámetros dirigidos por configuración
  - **Propiedad 12: Parámetros Dirigidos por Configuración**
  - **Valida: Requisitos 8.1, 8.2, 8.3, 8.4, 8.5**

- [ ] 10. Implementar aplicación de límites de trading
  - Actualizar seguimiento de posiciones para aplicar límites específicos por activo (EURUSD: 4, XAUUSD: 3, BTCEUR: 4)
  - Modificar procesamiento de señales para verificar límites de trades concurrentes antes de la ejecución
  - Integrar con sistema de conteo de trades existente en `bot.py`
  - _Requisitos: 2.3, 3.6, 4.6_

- [ ] 10.1 Escribir test de propiedades para aplicación de límites de trading
  - **Propiedad 8: Aplicación de Límites de Trading**
  - **Valida: Requisitos 2.3, 3.6, 4.6**

- [ ] 11. Añadir expiración de señales y validación de mechas
  - Implementar expiración de señales BTCEUR (180-240 minutos) en generación de señales
  - Añadir validación de mechas XAUUSD (≥30% del rango de vela) a señales de reversión
  - Actualizar estructuras de datos de señales para incluir metadatos de expiración y validación
  - _Requisitos: 4.5, 3.7_

- [ ] 11.1 Escribir test de propiedades para gestión de expiración de señales
  - **Propiedad 13: Gestión de Expiración de Señales**
  - **Valida: Requisitos 4.5**

- [ ] 11.2 Escribir test de propiedades para validación de mechas
  - **Propiedad 14: Validación de Mechas para Reversiones**
  - **Valida: Requisitos 3.7**

- [ ] 12. Integración y testing
  - Conectar todos los componentes mejorados
  - Actualizar `_detect_signal_wrapper()` para usar nuevas estrategias basadas en ATR
  - Asegurar integración adecuada con conexión MT5 existente y colocación de órdenes
  - Probar generación de señales de extremo a extremo, puntuación de confianza y lógica de ejecución
  - _Requisitos: Integración de todos los requisitos_

- [ ] 12.1 Escribir tests de integración para procesamiento de señales de extremo a extremo
  - Probar flujo completo de señales desde datos de mercado hasta decisión de ejecución
  - Verificar interacción adecuada entre todos los componentes mejorados

- [ ] 13. Checkpoint final - Asegurar que todas las pruebas pasen
  - Asegurar que todas las pruebas pasen, preguntar al usuario si surgen dudas.

## Notas

- Todas las tareas son requeridas para implementación completa desde el inicio
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints aseguran validación incremental
- Los tests de propiedades validan propiedades de corrección universales
- Los tests unitarios validan ejemplos específicos y casos límite
- La implementación se basa en la arquitectura existente en lugar de reconstruir desde cero
- Todos los cálculos ATR mantienen compatibilidad hacia atrás con estructuras de señales existentes
- Los cambios de configuración son recargables en caliente sin reinicio del sistema
- El logging completo permite análisis y optimización post-implementación