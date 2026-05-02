@echo off
echo ========================================
echo    🤖 BOT MT5 - SISTEMA INTEGRADO v2.0
echo ========================================
echo.

REM Configuración
set PYTHON_CMD=python
set BOT_SCRIPT=bot.py
set DASHBOARD_PORT=5000
set LOG_DIR=logs

REM Crear directorio de logs si no existe
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Verificar que Python está disponible
echo 🔍 Verificando Python...
%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ERROR: Python no encontrado. Instala Python y añádelo al PATH.
    pause
    exit /b 1
)
echo ✅ Python encontrado

REM Verificar que los archivos del bot existen
echo 🔍 Verificando archivos del bot...
if not exist "%BOT_SCRIPT%" (
    echo ❌ ERROR: %BOT_SCRIPT% no encontrado
    pause
    exit /b 1
)
echo ✅ Archivos del bot encontrados

REM Instalar dependencias automáticamente
echo 🔍 Instalando dependencias...
if exist "requirements.txt" (
    %PYTHON_CMD% -m pip install -r requirements.txt >nul 2>&1
    if errorlevel 1 (
        echo ⚠️  Algunas dependencias pueden faltar - continuando...
    ) else (
        echo ✅ Dependencias instaladas correctamente
    )
) else (
    echo ⚠️  requirements.txt no encontrado - continuando...
)

REM Verificar archivo .env
echo 🔍 Verificando configuración...
if not exist ".env" (
    echo ⚠️  ADVERTENCIA: Archivo .env no encontrado
    echo    Crea .env con DISCORD_TOKEN y otras configuraciones
    echo.
)

REM Obtener IP local para acceso móvil
echo 🌐 Obteniendo IP local...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    for /f "tokens=1" %%b in ("%%a") do set LOCAL_IP=%%b
)
if "%LOCAL_IP%"=="" set LOCAL_IP=localhost

echo ✅ IP local detectada: %LOCAL_IP%
echo.

REM Mostrar información de acceso
echo 📱 INFORMACIÓN DE ACCESO:
echo    � Servidor Web: http://localhost:%DASHBOARD_PORT%
echo    📱 Móvil:        http://%LOCAL_IP%:%DASHBOARD_PORT%
echo    📁 Archivo HTML: live_dashboard.html (tema oscuro integrado)
echo.
echo 🎯 MEJORAS INTEGRADAS:
echo    ✅ Sistema de scoring flexible en signals.py
echo    ✅ Logging inteligente en bot.py
echo    ✅ Dashboard con tema oscuro en live_dashboard.py
echo    ✅ Estrategias optimizadas integradas
echo.
echo 💡 ESTADO: Sistema integrado con servidor web
echo    ✅ Logger definido antes de imports
echo    ✅ Línea corrupta en bot.py arreglada
echo    ✅ Indentación en signals.py corregida
echo    ✅ Servidor web Flask integrado para dashboard
echo    🌐 Dashboard disponible en http://localhost:5000
echo.

echo.
echo 🚀 INICIANDO BOT MT5 CON SISTEMA INTEGRADO...
echo ========================================
echo.

REM Crear timestamp para logs
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "YY=%dt:~2,2%" & set "YYYY=%dt:~0,4%" & set "MM=%dt:~4,2%" & set "DD=%dt:~6,2%"
set "HH=%dt:~8,2%" & set "Min=%dt:~10,2%" & set "Sec=%dt:~12,2%"
set "timestamp=%YYYY%-%MM%-%DD%_%HH%-%Min%-%Sec%"

echo 🤖 Iniciando bot principal con dashboard integrado...
echo    📝 Los logs se guardarán automáticamente
echo    📊 Dashboard se iniciará automáticamente
echo    🌐 Servidor web en http://localhost:5000
echo    ⏹️  Presiona Ctrl+C para detener
echo.

REM Ejecutar bot — sin pipe para evitar bloqueos de buffer
@echo off
setlocal
set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"

REM Lanzar Python directamente, sin echo| pipe que puede bloquear el event loop
%PYTHON_CMD% -u %BOT_SCRIPT%

endlocal

REM Si llegamos aquí, el bot se cerró
echo.
echo ========================================
echo � BOT DETENIDO
echo ========================================
echo.

REM Mostrar información de logs
if exist "logs\logs_%timestamp%.txt" (
    echo 📝 Log guardado en: logs\logs_%timestamp%.txt
) else (
    echo 📝 Busca el archivo de log más reciente en la carpeta 'logs'
)

echo.
echo 💡 CONSEJOS:
echo    - Revisa los logs para diagnosticar problemas
echo    - Verifica la configuración en .env
echo    - Asegúrate de que MT5 esté ejecutándose
echo    - Comprueba la conexión a Discord
echo    - El dashboard se genera automáticamente + servidor web
echo.

REM Auto-close after 3 seconds instead of pause to avoid Ctrl+C prompt
echo ⏳ Cerrando en 3 segundos...
timeout /t 3 /nobreak >nul 2>&1