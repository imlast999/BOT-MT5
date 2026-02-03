"""
GUÍA DE MIGRACIÓN AL SISTEMA MEJORADO v2.0
Ayuda a integrar las mejoras en el bot existente

🎯 PASOS DE MIGRACIÓN:
1. Verificar dependencias
2. Integrar sistemas mejorados
3. Actualizar configuración
4. Modificar bot.py
5. Probar funcionamiento

🔧 CAMBIOS NECESARIOS:
- Importar sistemas mejorados en bot.py
- Reemplazar _detect_signal_wrapper
- Integrar dashboard oscuro
- Actualizar logging
"""

import os
import json
import shutil
from datetime import datetime
from typing import List, Dict, Tuple

class MigrationGuide:
    """Guía de migración al sistema mejorado"""
    
    def __init__(self):
        self.backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.required_files = [
            'scoring_system.py',
            'intelligent_logging.py', 
            'improved_strategies.py',
            'dark_dashboard.py',
            'bot_integration_improved.py',
            'rules_config_improved.json',
            'start_bot.bat'
        ]
        
        self.migration_steps = []
    
    def check_dependencies(self) -> Dict:
        """Verificar dependencias necesarias"""
        print("🔍 VERIFICANDO DEPENDENCIAS...")
        
        dependencies = {
            'python_packages': ['flask', 'plotly', 'pandas', 'numpy'],
            'bot_files': ['bot.py', 'signals.py', 'mt5_client.py'],
            'config_files': ['.env', 'rules_config.json'],
            'new_files': self.required_files
        }
        
        status = {
            'python_packages': {},
            'bot_files': {},
            'config_files': {},
            'new_files': {}
        }
        
        # Verificar paquetes Python
        for package in dependencies['python_packages']:
            try:
                __import__(package)
                status['python_packages'][package] = True
                print(f"✅ {package}")
            except ImportError:
                status['python_packages'][package] = False
                print(f"❌ {package} - Instalar con: pip install {package}")
        
        # Verificar archivos del bot
        for file in dependencies['bot_files']:
            exists = os.path.exists(file)
            status['bot_files'][file] = exists
            print(f"{'✅' if exists else '❌'} {file}")
        
        # Verificar archivos de configuración
        for file in dependencies['config_files']:
            exists = os.path.exists(file)
            status['config_files'][file] = exists
            print(f"{'✅' if exists else '⚠️'} {file}")
        
        # Verificar nuevos archivos
        for file in dependencies['new_files']:
            exists = os.path.exists(file)
            status['new_files'][file] = exists
            print(f"{'✅' if exists else '❌'} {file}")
        
        return status
    
    def create_backup(self) -> bool:
        """Crear backup de archivos importantes"""
        print(f"\n💾 CREANDO BACKUP EN: {self.backup_dir}")
        
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            
            # Archivos a respaldar
            backup_files = [
                'bot.py',
                'signals.py', 
                'rules_config.json',
                'live_dashboard.py',
                '.env'
            ]
            
            for file in backup_files:
                if os.path.exists(file):
                    shutil.copy2(file, self.backup_dir)
                    print(f"✅ Respaldado: {file}")
            
            print(f"✅ Backup completado en: {self.backup_dir}")
            return True
            
        except Exception as e:
            print(f"❌ Error creando backup: {e}")
            return False
    
    def generate_bot_integration_code(self) -> str:
        """Generar código de integración para bot.py"""
        
        integration_code = '''
# ======================
# INTEGRACIÓN SISTEMA MEJORADO v2.0
# ======================

# Importar sistemas mejorados
try:
    from bot_integration_improved import (
        detect_signal_with_improvements,
        execute_signal_with_improvements,
        start_improved_systems,
        stop_improved_systems,
        get_improved_session_summary,
        get_system_health
    )
    IMPROVED_SYSTEM_AVAILABLE = True
    print("✅ Sistema mejorado cargado correctamente")
except ImportError as e:
    print(f"⚠️ Sistema mejorado no disponible: {e}")
    IMPROVED_SYSTEM_AVAILABLE = False

# Reemplazar función de detección de señales
def _detect_signal_wrapper_improved(df, symbol: str | None = None):
    """
    Wrapper mejorado que usa el sistema de scoring flexible
    """
    sym = (symbol or SYMBOL or '').upper()
    
    if IMPROVED_SYSTEM_AVAILABLE:
        try:
            # Usar sistema mejorado
            signal, df_processed, analysis = detect_signal_with_improvements(df, sym)
            
            if signal:
                # Convertir a formato esperado por el bot original
                risk_info = {
                    'approved': True,
                    'strategy_used': signal.get('strategy', 'improved'),
                    'confidence': signal.get('confidence', 'MEDIUM'),
                    'confidence_score': signal.get('score', 0.0),
                    'should_show': True,
                    'can_auto_execute': signal.get('confidence') == 'HIGH'
                }
                return signal, df_processed, risk_info
            else:
                # Señal rechazada
                risk_info = {
                    'approved': False,
                    'reason': analysis.get('reason', 'Señal rechazada por sistema mejorado'),
                    'scoring_details': analysis.get('scoring_result', {})
                }
                return None, df, risk_info
                
        except Exception as e:
            print(f"❌ Error en sistema mejorado: {e}")
            # Fallback al sistema original
            pass
    
    # Fallback al sistema original si el mejorado no está disponible
    return _detect_signal_wrapper_original(df, sym)

# Guardar función original como fallback
_detect_signal_wrapper_original = _detect_signal_wrapper
# Reemplazar con versión mejorada
_detect_signal_wrapper = _detect_signal_wrapper_improved

# Modificar evento on_ready para iniciar sistemas mejorados
@bot.event
async def on_ready_improved():
    """Evento on_ready mejorado con sistemas integrados"""
    
    # Ejecutar on_ready original
    await on_ready_original()
    
    # Iniciar sistemas mejorados
    if IMPROVED_SYSTEM_AVAILABLE:
        try:
            start_improved_systems()
            log_event("✅ Sistemas mejorados iniciados correctamente")
        except Exception as e:
            log_event(f"❌ Error iniciando sistemas mejorados: {e}", "ERROR")

# Guardar evento original
on_ready_original = bot.event(on_ready)
# Reemplazar con versión mejorada
bot.remove_listener(on_ready_original)
bot.event(on_ready_improved)

# Añadir comando para estado del sistema mejorado
@bot.tree.command(name="system_health")
async def slash_system_health(interaction: discord.Interaction):
    """Muestra el estado de salud del sistema mejorado"""
    if interaction.user.id != AUTHORIZED_USER_ID:
        await interaction.response.send_message("⛔ No autorizado", ephemeral=True)
        return
    
    if not IMPROVED_SYSTEM_AVAILABLE:
        await interaction.response.send_message("❌ Sistema mejorado no disponible", ephemeral=True)
        return
    
    try:
        health = get_system_health()
        summary = get_improved_session_summary()
        
        embed = discord.Embed(
            title="🏥 Estado del Sistema Mejorado",
            color=0x00ff00 if health['overall_status'] == 'EXCELLENT' else 0xff9900,
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📊 Estado General",
            value=f"**Status:** {health['overall_status']}\\n"
                  f"**Sistemas:** {health['systems_available']}/{health['systems_total']}\\n"
                  f"**Uptime:** {health['uptime_hours']:.1f}h",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Señales de Sesión",
            value=f"**Generadas:** {summary['signals_generated']}\\n"
                  f"**Mostradas:** {summary['signals_shown']}\\n"
                  f"**Ejecutadas:** {summary['signals_executed']}",
            inline=True
        )
        
        embed.add_field(
            name="📈 Tasas de Éxito",
            value=f"**Show Rate:** {summary['show_rate']:.1f}%\\n"
                  f"**Execution Rate:** {summary['execution_rate']:.1f}%",
            inline=True
        )
        
        # Estado de sistemas individuales
        systems_status = "\\n".join([
            f"{'✅' if status else '❌'} {system.title()}"
            for system, status in health['systems_status'].items()
        ])
        
        embed.add_field(
            name="🔧 Sistemas Individuales",
            value=systems_status,
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Error obteniendo estado: {e}", ephemeral=True)

# Modificar cierre del bot para detener sistemas mejorados
def shutdown_improved_systems():
    """Detener sistemas mejorados al cerrar el bot"""
    if IMPROVED_SYSTEM_AVAILABLE:
        try:
            stop_improved_systems()
            print("✅ Sistemas mejorados detenidos correctamente")
        except Exception as e:
            print(f"❌ Error deteniendo sistemas mejorados: {e}")

# Añadir al finally del main
# En la sección finally de bot.py, añadir:
# shutdown_improved_systems()
'''
        
        return integration_code
    
    def update_bot_file(self) -> bool:
        """Actualizar bot.py con integración mejorada"""
        print("\n🔧 ACTUALIZANDO bot.py...")
        
        try:
            # Leer bot.py actual
            with open('bot.py', 'r', encoding='utf-8') as f:
                bot_content = f.read()
            
            # Generar código de integración
            integration_code = self.generate_bot_integration_code()
            
            # Buscar punto de inserción (después de imports)
            import_end = bot_content.find('# ======================')
            if import_end == -1:
                import_end = bot_content.find('load_dotenv()')
            
            if import_end != -1:
                # Insertar código de integración
                new_content = (
                    bot_content[:import_end] + 
                    integration_code + 
                    "\n\n" + 
                    bot_content[import_end:]
                )
                
                # Escribir archivo actualizado
                with open('bot_improved.py', 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                print("✅ bot_improved.py creado con integración mejorada")
                print("⚠️ Revisa el archivo antes de reemplazar bot.py original")
                return True
            else:
                print("❌ No se pudo encontrar punto de inserción en bot.py")
                return False
                
        except Exception as e:
            print(f"❌ Error actualizando bot.py: {e}")
            return False
    
    def create_migration_summary(self) -> Dict:
        """Crear resumen de migración"""
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'backup_created': os.path.exists(self.backup_dir),
            'backup_location': self.backup_dir,
            'files_status': {},
            'next_steps': [],
            'warnings': []
        }
        
        # Verificar archivos nuevos
        for file in self.required_files:
            summary['files_status'][file] = os.path.exists(file)
        
        # Próximos pasos
        summary['next_steps'] = [
            "1. Revisar bot_improved.py generado",
            "2. Instalar dependencias faltantes (pip install flask plotly)",
            "3. Copiar configuración de .env a rules_config_improved.json",
            "4. Probar con: python bot_integration_improved.py",
            "5. Si todo funciona, reemplazar bot.py con bot_improved.py",
            "6. Ejecutar: start_bot.bat"
        ]
        
        # Advertencias
        if not all(summary['files_status'].values()):
            summary['warnings'].append("Algunos archivos del sistema mejorado no están disponibles")
        
        if not os.path.exists('.env'):
            summary['warnings'].append("Archivo .env no encontrado - configurar variables de entorno")
        
        return summary
    
    def run_migration(self) -> bool:
        """Ejecutar migración completa"""
        print("🚀 INICIANDO MIGRACIÓN AL SISTEMA MEJORADO v2.0")
        print("=" * 60)
        
        # Paso 1: Verificar dependencias
        deps_status = self.check_dependencies()
        
        # Paso 2: Crear backup
        if not self.create_backup():
            print("❌ Error creando backup - Migración abortada")
            return False
        
        # Paso 3: Actualizar bot.py
        if not self.update_bot_file():
            print("⚠️ No se pudo actualizar bot.py automáticamente")
        
        # Paso 4: Crear resumen
        summary = self.create_migration_summary()
        
        # Guardar resumen
        with open('migration_summary.json', 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print("\n" + "=" * 60)
        print("📋 RESUMEN DE MIGRACIÓN")
        print("=" * 60)
        
        print(f"✅ Backup creado en: {summary['backup_location']}")
        
        print("\n📁 Estado de archivos nuevos:")
        for file, exists in summary['files_status'].items():
            print(f"{'✅' if exists else '❌'} {file}")
        
        if summary['warnings']:
            print("\n⚠️ Advertencias:")
            for warning in summary['warnings']:
                print(f"   - {warning}")
        
        print("\n📝 Próximos pasos:")
        for step in summary['next_steps']:
            print(f"   {step}")
        
        print(f"\n📄 Resumen completo guardado en: migration_summary.json")
        
        return True

def run_migration_wizard():
    """Ejecutar asistente de migración"""
    print("🧙‍♂️ ASISTENTE DE MIGRACIÓN AL SISTEMA MEJORADO v2.0")
    print("=" * 60)
    
    migration = MigrationGuide()
    
    # Confirmar migración
    print("\n¿Deseas continuar con la migración? (s/N)")
    response = input().lower()
    
    if response not in ['s', 'y', 'yes', 'sí']:
        print("Migración cancelada")
        return False
    
    # Ejecutar migración
    success = migration.run_migration()
    
    if success:
        print("\n🎉 MIGRACIÓN COMPLETADA")
        print("Revisa los archivos generados y sigue los próximos pasos")
    else:
        print("\n❌ MIGRACIÓN FALLIDA")
        print("Revisa los errores y vuelve a intentar")
    
    return success

if __name__ == "__main__":
    run_migration_wizard()