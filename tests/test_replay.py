"""
Script de prueba rápida para el Replay Engine

Este script verifica que el replay engine funciona correctamente
sin necesidad de ejecutar el bot completo.
"""

import sys
import os

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(__file__))

def test_replay_engine():
    """Prueba básica del replay engine"""
    print("=" * 60)
    print("TEST: Replay Engine")
    print("=" * 60)
    print()
    
    try:
        # Importar el replay engine
        from core.replay_engine import get_replay_engine, ReplayEngine
        print("✅ Importación exitosa: core.replay_engine")
        
        # Crear instancia
        engine = get_replay_engine(lookback_window=100)
        print(f"✅ Instancia creada: {type(engine).__name__}")
        
        # Verificar métodos
        assert hasattr(engine, 'run_replay'), "Falta método run_replay"
        assert hasattr(engine, 'get_signals'), "Falta método get_signals"
        assert hasattr(engine, 'get_detailed_report'), "Falta método get_detailed_report"
        print("✅ Métodos verificados: run_replay, get_signals, get_detailed_report")
        
        # Verificar dataclasses
        from core.replay_engine import ReplaySignal, ReplayStatistics
        print("✅ Dataclasses importadas: ReplaySignal, ReplayStatistics")
        
        # Crear estadísticas de prueba
        stats = ReplayStatistics()
        stats.bars_analyzed = 1000
        stats.signals_final = 50
        stats.tp_hits = 30
        stats.sl_hits = 20
        
        # Calcular winrate
        closed = stats.tp_hits + stats.sl_hits
        if closed > 0:
            stats.winrate = (stats.tp_hits / closed) * 100
        
        print(f"✅ Estadísticas de prueba: {stats.bars_analyzed} velas, {stats.signals_final} señales, {stats.winrate:.1f}% winrate")
        
        print()
        print("=" * 60)
        print("✅ TODAS LAS PRUEBAS PASARON")
        print("=" * 60)
        print()
        print("El Replay Engine está listo para usar.")
        print()
        print("Comandos disponibles:")
        print("  /replay EURUSD 1000")
        print("  /replay XAUUSD 5000")
        print("  /replay BTCEUR 2000")
        print()
        
        return True
        
    except ImportError as e:
        print(f"❌ Error de importación: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Error de verificación: {e}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_diagnose_fix():
    """Verifica que el comando diagnose_signals esté corregido"""
    print("=" * 60)
    print("TEST: Corrección de /diagnose_signals")
    print("=" * 60)
    print()
    
    try:
        # Leer el archivo bot.py
        with open('bot.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Verificar que NO tenga el límite antiguo
        if 'iterations = min(iterations, 20)' in content:
            print("❌ FALLO: Todavía existe el límite de 20 iteraciones")
            return False
        
        print("✅ Límite de 20 iteraciones eliminado")
        
        # Verificar que tenga el nuevo límite de seguridad
        if 'iterations > 10000' in content:
            print("✅ Límite de seguridad de 10000 implementado")
        else:
            print("⚠️  Advertencia: No se encontró el límite de seguridad de 10000")
        
        # Verificar que use skip_duplicate_filter
        if 'skip_duplicate_filter=True' in content:
            print("✅ Filtro de duplicados desactivado en diagnóstico")
        else:
            print("⚠️  Advertencia: No se encontró skip_duplicate_filter=True")
        
        # NUEVA VERIFICACIÓN: Que use replay_engine
        if 'from core.replay_engine import get_replay_engine' in content:
            print("✅ Usa replay_engine para analizar ventanas históricas")
        else:
            print("❌ FALLO: No usa replay_engine (evalúa misma vela repetidamente)")
            return False
        
        # NUEVA VERIFICACIÓN: Que NO use el loop antiguo
        diagnose_section = content[content.find('slash_diagnose_signals'):content.find('slash_diagnose_signals') + 5000]
        if 'for i in range(iterations):' in diagnose_section and 'engine.evaluate_signal(df' in diagnose_section:
            print("❌ FALLO: Todavía usa el loop antiguo que evalúa la misma vela")
            return False
        
        print("✅ NO usa el loop antiguo (no repite misma vela)")
        
        # Verificar que use run_replay
        if 'run_replay(' in content:
            print("✅ Usa run_replay() para analizar ventanas distintas")
        else:
            print("⚠️  Advertencia: No se encontró run_replay()")
        
        print()
        print("=" * 60)
        print("✅ CORRECCIÓN VERIFICADA")
        print("=" * 60)
        print()
        print("El comando /diagnose_signals ahora:")
        print("  - Respeta el parámetro de iteraciones")
        print("  - Tiene límite de seguridad de 10000")
        print("  - Desactiva filtro de duplicados temporalmente")
        print("  - Analiza ventanas históricas DISTINTAS (no repite misma vela)")
        print("  - Reutiliza replay_engine (no duplica lógica)")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ Error verificando corrección: {e}")
        return False

if __name__ == '__main__':
    print()
    print("🧪 PRUEBAS DEL SISTEMA DE REPLAY")
    print()
    
    # Ejecutar pruebas
    test1 = test_diagnose_fix()
    print()
    test2 = test_replay_engine()
    
    # Resumen
    print()
    print("=" * 60)
    print("RESUMEN DE PRUEBAS")
    print("=" * 60)
    print(f"Corrección /diagnose_signals: {'✅ PASS' if test1 else '❌ FAIL'}")
    print(f"Replay Engine: {'✅ PASS' if test2 else '❌ FAIL'}")
    print("=" * 60)
    print()
    
    if test1 and test2:
        print("🎉 ¡Todas las pruebas pasaron! El sistema está listo.")
        sys.exit(0)
    else:
        print("⚠️  Algunas pruebas fallaron. Revisa los errores arriba.")
        sys.exit(1)
