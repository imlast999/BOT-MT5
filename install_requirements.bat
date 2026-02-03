@echo off
echo ========================================
echo   📦 INSTALADOR DE DEPENDENCIAS v2.0
echo ========================================
echo.

REM Verificar que Python está disponible
echo 🔍 Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ERROR: Python no encontrado. 
    echo    Descarga Python desde: https://python.org
    echo    Asegúrate de añadirlo al PATH durante la instalación
    pause
    exit /b 1
)

python --version
echo ✅ Python encontrado
echo.

REM Verificar pip
echo 🔍 Verificando pip...
pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ERROR: pip no encontrado
    echo    Reinstala Python con pip incluido
    pause
    exit /b 1
)
echo ✅ pip encontrado
echo.

echo 📦 INSTALANDO DEPENDENCIAS PRINCIPALES...
echo ========================================

REM Dependencias básicas del bot
echo 📥 Instalando dependencias básicas...
pip install discord.py python-dotenv pandas numpy matplotlib plotly

REM Dependencias para MT5
echo 📥 Instalando MetaTrader5...
pip install MetaTrader5

REM Dependencias para dashboard
echo 📥 Instalando Flask para dashboard...
pip install flask

REM Dependencias adicionales
echo 📥 Instalando dependencias adicionales...
pip install requests sqlite3

echo.
echo ✅ INSTALACIÓN COMPLETADA
echo ========================================

echo 🔍 VERIFICANDO INSTALACIÓN...
echo.

REM Verificar cada paquete
python -c "import discord; print('✅ discord.py')" 2>nul || echo "❌ discord.py"
python -c "import pandas; print('✅ pandas')" 2>nul || echo "❌ pandas"
python -c "import numpy; print('✅ numpy')" 2>nul || echo "❌ numpy"
python -c "import matplotlib; print('✅ matplotlib')" 2>nul || echo "❌ matplotlib"
python -c "import plotly; print('✅ plotly')" 2>nul || echo "❌ plotly"
python -c "import flask; print('✅ flask')" 2>nul || echo "❌ flask"
python -c "import MetaTrader5; print('✅ MetaTrader5')" 2>nul || echo "❌ MetaTrader5"

echo.
echo 💡 CONFIGURACIÓN ADICIONAL NECESARIA:
echo ========================================
echo.
echo 1. 📁 Crea archivo .env con:
echo    DISCORD_TOKEN=tu_token_aqui
echo    AUTHORIZED_USER_ID=tu_user_id
echo    MT5_LOGIN=tu_login
echo    MT5_PASSWORD=tu_password
echo    MT5_SERVER=tu_servidor
echo.
echo 2. 🤖 Configura tu bot de Discord:
echo    - Ve a https://discord.com/developers/applications
echo    - Crea una nueva aplicación
echo    - Ve a "Bot" y crea un bot
echo    - Copia el token al archivo .env
echo.
echo 3. 📊 Instala MetaTrader 5:
echo    - Descarga desde: https://www.metatrader5.com
echo    - Configura tu cuenta demo/real
echo    - Anota login, password y servidor
echo.
echo 4. 🚀 Ejecuta el bot:
echo    start_bot.bat
echo.

pause