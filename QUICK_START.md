# 🚀 Guía de Inicio Rápido - Bot MT5 Mejorado v2.0

## ⚡ **INSTALACIÓN EN 5 MINUTOS**

### **1. Instalar Dependencias**
```bash
# Ejecutar instalador automático
install_requirements.bat
```

### **2. Configurar Variables**
Crear archivo `.env`:
```env
DISCORD_TOKEN=tu_token_de_discord
AUTHORIZED_USER_ID=tu_user_id_discord
MT5_LOGIN=tu_login_mt5
MT5_PASSWORD=tu_password_mt5
MT5_SERVER=tu_servidor_mt5
```

### **3. Iniciar Bot**
```bash
# Un solo comando inicia todo
start_bot.bat
```

¡Listo! El dashboard se abrirá automáticamente en tu navegador.

---

## 📱 **ACCESO DESDE MÓVIL**

### **IP Automática:**
Al iniciar el bot, verás algo como:
```
📱 Acceso móvil: http://192.168.1.100:5000
```

### **Conectar desde tu teléfono:**
1. Conecta tu móvil a la misma WiFi
2. Abre esa URL en tu navegador móvil
3. ¡Dashboard completo en tu teléfono!

---

## 🎯 **COMANDOS PRINCIPALES**

### **Discord:**
- `/signal EURUSD` - Generar señal manual
- `/system_health` - Estado del sistema
- `/demo_stats` - Estadísticas de cuenta
- `/help` - Lista completa de comandos

### **Dashboard:**
- **Local**: http://localhost:5000
- **Móvil**: http://[IP_LOCAL]:5000
- **Auto-refresh**: Cada 5 minutos

---

## 📊 **QUÉ ESPERAR**

### **Frecuencia de Señales:**
- **EURUSD**: 3-4 señales/día
- **XAUUSD**: 2-3 señales/día  
- **BTCEUR**: 3-5 señales/día
- **Total**: 8-12 señales/día

### **Niveles de Confianza:**
- **HIGH**: 1-3/día (señales premium)
- **MEDIUM-HIGH**: 2-4/día (buena calidad)
- **MEDIUM**: 3-5/día (calidad aceptable)

---

## 🔧 **CONFIGURACIÓN RÁPIDA**

### **Ajustar Frecuencia:**
Editar `rules_config_improved.json`:
```json
{
  "EURUSD": {
    "min_score": 0.60,        // Bajar = más señales
    "show_threshold": 0.50    // Bajar = más señales mostradas
  }
}
```

### **Cambiar Símbolos:**
```json
{
  "GBPUSD": {
    "enabled": true,          // Habilitar nuevo símbolo
    "strategy": "eurusd_improved"
  }
}
```

---

## 🛠️ **SOLUCIÓN DE PROBLEMAS**

### **❌ No aparecen señales:**
1. Verificar que MT5 esté conectado
2. Comprobar que los símbolos estén habilitados
3. Revisar thresholds en configuración

### **❌ Dashboard no carga:**
1. Verificar que el puerto 5000 esté libre
2. Comprobar firewall/antivirus
3. Probar con IP local en vez de localhost

### **❌ Bot no se conecta a Discord:**
1. Verificar token en .env
2. Comprobar permisos del bot
3. Revisar que el bot esté en el servidor

---

## 📈 **MONITOREO**

### **Dashboard Oscuro:**
- **Métricas en tiempo real**
- **Gráficos interactivos**
- **Análisis de rechazos**
- **Actividad por hora**

### **Logs Inteligentes:**
- **Sin ruido** de rechazos individuales
- **Métricas agregadas** cada 15 minutos
- **Solo eventos importantes**

### **Archivos de Log:**
- `logs/logs_YYYY-MM-DD_HH-MM-SS.txt` - Log completo
- `intelligent_metrics.json` - Métricas agregadas

---

## 🎯 **MEJORES PRÁCTICAS**

### **Configuración Inicial:**
1. **Empezar conservador**: Usar thresholds altos (0.70+)
2. **Monitorear 1 semana**: Revisar frecuencia y calidad
3. **Ajustar gradualmente**: Bajar thresholds si es necesario

### **Uso Diario:**
1. **Revisar dashboard** cada mañana
2. **Monitorear señales HIGH** durante el día
3. **Revisar métricas** cada noche

### **Optimización:**
1. **Analizar rechazos** en dashboard
2. **Ajustar reglas** que fallan mucho
3. **Optimizar thresholds** por símbolo

---

## 🚀 **PRÓXIMOS PASOS**

### **Una vez funcionando:**
1. **Configurar alertas** push móviles
2. **Añadir más símbolos** según necesidad
3. **Optimizar thresholds** basado en resultados
4. **Explorar backtesting** automático

### **Personalización Avanzada:**
1. **Crear estrategias** personalizadas
2. **Ajustar pesos** de confirmaciones
3. **Implementar filtros** adicionales
4. **Integrar APIs** externas

---

## 📞 **SOPORTE RÁPIDO**

### **Comandos de Diagnóstico:**
```bash
# Estado del sistema
python -c "from bot_integration_improved import get_system_health; print(get_system_health())"

# Test de estrategias
python improved_strategies.py

# Test de dashboard
python dark_dashboard.py
```

### **Archivos Importantes:**
- `bot.py` - Bot principal
- `rules_config_improved.json` - Configuración
- `.env` - Variables de entorno
- `start_bot.bat` - Script de arranque

---

**🎯 ¡En 5 minutos tendrás un bot de trading profesional funcionando!**

**📱 Dashboard oscuro + Acceso móvil + Señales inteligentes + Logs sin ruido**