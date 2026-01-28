#!/usr/bin/env python3
"""
Script para limpiar archivos de log antiguos
Mantiene solo los logs de los últimos N días
"""

import os
import glob
import sys
from datetime import datetime, timedelta

def cleanup_old_logs(days_to_keep=7):
    """
    Eliminar archivos de log más antiguos que el número especificado de días
    
    Args:
        days_to_keep (int): Número de días de logs a mantener (default: 7)
    """
    print(f"🧹 Limpiando archivos de log más antiguos que {days_to_keep} días...")
    
    # Buscar todos los archivos de log en la carpeta logs/
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        print("📁 Carpeta logs/ no encontrada")
        return 0
    
    log_files = glob.glob(os.path.join(logs_dir, "logs_*.txt"))
    
    if not log_files:
        print("📝 No se encontraron archivos de log para limpiar")
        return 0
    
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    deleted_count = 0
    kept_count = 0
    total_size_deleted = 0
    
    print(f"📅 Fecha límite: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Archivos encontrados: {len(log_files)}")
    print()
    
    for log_file in sorted(log_files):
        try:
            # Obtener la fecha de modificación del archivo
            file_mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
            file_size = os.path.getsize(log_file)
            file_size_mb = file_size / (1024 * 1024)
            
            if file_mtime < cutoff_date:
                # Archivo antiguo - eliminar
                os.remove(log_file)
                deleted_count += 1
                total_size_deleted += file_size
                print(f"🗑️  ELIMINADO: {log_file} ({file_size_mb:.2f} MB) - {file_mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                # Archivo reciente - mantener
                kept_count += 1
                print(f"✅ MANTENIDO: {log_file} ({file_size_mb:.2f} MB) - {file_mtime.strftime('%Y-%m-%d %H:%M:%S')}")
                
        except Exception as e:
            print(f"❌ Error procesando {log_file}: {e}")
    
    total_size_deleted_mb = total_size_deleted / (1024 * 1024)
    
    print()
    print("=" * 60)
    print(f"📊 RESUMEN DE LIMPIEZA:")
    print(f"   🗑️  Archivos eliminados: {deleted_count}")
    print(f"   ✅ Archivos mantenidos: {kept_count}")
    print(f"   💾 Espacio liberado: {total_size_deleted_mb:.2f} MB")
    print("=" * 60)
    
    return deleted_count

def list_log_files():
    """Listar todos los archivos de log disponibles"""
    print("📝 ARCHIVOS DE LOG DISPONIBLES:")
    print("=" * 60)
    
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        print("📁 Carpeta logs/ no encontrada")
        return
    
    log_files = glob.glob(os.path.join(logs_dir, "logs_*.txt"))
    
    if not log_files:
        print("📝 No se encontraron archivos de log")
        return
    
    total_size = 0
    
    for log_file in sorted(log_files, reverse=True):  # Más recientes primero
        try:
            file_mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
            file_size = os.path.getsize(log_file)
            file_size_mb = file_size / (1024 * 1024)
            total_size += file_size
            
            # Calcular edad del archivo
            age = datetime.now() - file_mtime
            if age.days > 0:
                age_str = f"{age.days} días"
            elif age.seconds > 3600:
                age_str = f"{age.seconds // 3600} horas"
            else:
                age_str = f"{age.seconds // 60} minutos"
            
            print(f"📄 {log_file}")
            print(f"   📅 Fecha: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')} ({age_str})")
            print(f"   📊 Tamaño: {file_size_mb:.2f} MB")
            print()
            
        except Exception as e:
            print(f"❌ Error leyendo {log_file}: {e}")
    
    total_size_mb = total_size / (1024 * 1024)
    print(f"💾 Tamaño total: {total_size_mb:.2f} MB ({len(log_files)} archivos)")

def main():
    """Función principal"""
    if len(sys.argv) > 1:
        if sys.argv[1] == "list":
            list_log_files()
            return 0
        elif sys.argv[1] == "help":
            print("🧹 SCRIPT DE LIMPIEZA DE LOGS")
            print("=" * 40)
            print("Uso:")
            print("  python cleanup_logs.py [días]  - Limpiar logs más antiguos que N días (default: 7)")
            print("  python cleanup_logs.py list   - Listar todos los archivos de log")
            print("  python cleanup_logs.py help   - Mostrar esta ayuda")
            print()
            print("Ejemplos:")
            print("  python cleanup_logs.py        - Limpiar logs más antiguos que 7 días")
            print("  python cleanup_logs.py 3      - Limpiar logs más antiguos que 3 días")
            print("  python cleanup_logs.py 30     - Limpiar logs más antiguos que 30 días")
            return 0
        else:
            try:
                days = int(sys.argv[1])
                if days < 1:
                    print("❌ Error: El número de días debe ser mayor que 0")
                    return 1
                cleanup_old_logs(days)
                return 0
            except ValueError:
                print("❌ Error: Argumento inválido. Use 'help' para ver las opciones.")
                return 1
    else:
        # Comportamiento por defecto: limpiar logs más antiguos que 7 días
        cleanup_old_logs(7)
        return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)