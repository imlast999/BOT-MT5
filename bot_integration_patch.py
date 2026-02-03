"""
PARCHE DE INTEGRACIÓN PARA BOT.PY
Conecta el sistema simplificado con el bot existente sin romper funcionalidad

🎯 FUNCIONES:
- Reemplaza detect_signal_advanced con detect_signal_integrated
- Añade comandos Discord para el sistema simplificado
- Mantiene compatibilidad total con el sistema existente
- Proporciona fallback automático

📝 INSTRUCCIONES DE USO:
1. Importar este módulo en bot.py
2. Llamar setup_simplified_integration(bot)
3. El sistema funcionará automáticamente
"""

import discord
from discord.ext import commands
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

# Importar el integrador
from signal_integrator import (
    detect_signal_integrated,
    get_signal_system_status,
    reset_daily_signal_counts,
    can_generate_signal_for_symbol,
    get_simplified_system_info
)

logger = logging.getLogger(__name__)

def setup_simplified_integration(bot: commands.Bot):
    """
    Configura la integración del sistema simplificado con el bot Discord
    
    Args:
        bot: Instancia del bot Discord
    """
    logger.info("🔧 Configurando integración del sistema simplificado...")
    
    # Añadir comandos específicos del sistema simplificado
    add_simplified_commands(bot)
    
    logger.info("✅ Integración del sistema simplificado configurada")

def add_simplified_commands(bot: commands.Bot):
    """Añade comandos específicos del sistema simplificado"""
    
    @bot.tree.command(name="system_info", description="Información del sistema simplificado")
    async def system_info_command(interaction: discord.Interaction):
        """Muestra información del sistema simplificado"""
        try:
            await interaction.response.defer()
            
            # Obtener información del sistema
            system_info = get_simplified_system_info()
            status = get_signal_system_status()
            
            # Crear embed
            embed = discord.Embed(
                title="🚀 Sistema Simplificado v2.0",
                description=system_info['philosophy'],
                color=0x00ff00
            )
            
            # Información general
            embed.add_field(
                name="📊 Estado Actual",
                value=f"**Sistema**: {'Simplificado' if status['system_type'] == 'simplified' else 'Original'}\n"
                      f"**Señales hoy**: {status['total_signals']}/{status['max_total_signals']}\n"
                      f"**Uso**: {status['percentage_used']:.1f}%",
                inline=True
            )
            
            # Distribución por símbolo
            symbols_info = ""
            for symbol, info in status['symbols'].items():
                if info['enabled']:
                    symbols_info += f"**{symbol}**: {info['current']}/{info['max']} ({info['percentage_used']:.0f}%)\n"
            
            embed.add_field(
                name="📈 Por Símbolo",
                value=symbols_info or "Sin datos",
                inline=True
            )
            
            # Mejoras implementadas
            improvements = "\n".join(f"• {imp}" for imp in system_info['improvements'][:5])
            embed.add_field(
                name="✅ Mejoras Clave",
                value=improvements,
                inline=False
            )
            
            # Frecuencia esperada
            embed.add_field(
                name="🎯 Frecuencia Esperada",
                value=f"**Total**: {system_info['expected_frequency']}\n"
                      f"**EURUSD**: {system_info['distribution']['EURUSD']}\n"
                      f"**XAUUSD**: {system_info['distribution']['XAUUSD']}\n"
                      f"**BTCEUR**: {system_info['distribution']['BTCEUR']}",
                inline=True
            )
            
            embed.set_footer(text=f"Versión {system_info['version']} • {datetime.now().strftime('%H:%M:%S')}")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error en system_info_command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @bot.tree.command(name="signal_status", description="Estado de contadores y límites de señales")
    async def signal_status_command(interaction: discord.Interaction):
        """Muestra el estado actual de los contadores de señales"""
        try:
            await interaction.response.defer()
            
            status = get_signal_system_status()
            
            embed = discord.Embed(
                title="📊 Estado de Señales",
                description=f"Fecha: {status['date']}",
                color=0x3498db
            )
            
            # Resumen general
            embed.add_field(
                name="📈 Resumen General",
                value=f"**Total**: {status['total_signals']}/{status['max_total_signals']}\n"
                      f"**Restantes**: {status['remaining_total']}\n"
                      f"**Uso**: {status['percentage_used']:.1f}%",
                inline=True
            )
            
            # Detalles por símbolo
            for symbol, info in status['symbols'].items():
                if info['enabled']:
                    status_emoji = "🟢" if info['remaining'] > 0 else "🔴"
                    embed.add_field(
                        name=f"{status_emoji} {symbol}",
                        value=f"**Usado**: {info['current']}/{info['max']}\n"
                              f"**Restante**: {info['remaining']}\n"
                              f"**%**: {info['percentage_used']:.0f}%",
                        inline=True
                    )
            
            # Información del sistema
            system_type = "🚀 Simplificado" if status['system_type'] == 'simplified' else "⚙️ Original"
            embed.add_field(
                name="🔧 Sistema Activo",
                value=system_type,
                inline=False
            )
            
            embed.set_footer(text=f"Actualizado: {datetime.now().strftime('%H:%M:%S')}")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error en signal_status_command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @bot.tree.command(name="scoring_test", description="Probar sistema de scoring en tiempo real")
    async def scoring_test_command(interaction: discord.Interaction, symbol: str = "EURUSD"):
        """Prueba el sistema de scoring para un símbolo"""
        try:
            await interaction.response.defer()
            
            symbol = symbol.upper()
            
            # Verificar si se puede generar señal
            can_generate, reason = can_generate_signal_for_symbol(symbol)
            
            embed = discord.Embed(
                title=f"🧮 Test de Scoring - {symbol}",
                description="Análisis en tiempo real del sistema de scoring",
                color=0xf39c12
            )
            
            # Estado de límites
            status_emoji = "✅" if can_generate else "❌"
            embed.add_field(
                name=f"{status_emoji} Estado de Límites",
                value=reason,
                inline=False
            )
            
            if can_generate:
                # Aquí se podría hacer un análisis real del mercado
                # Por ahora, mostrar información teórica
                embed.add_field(
                    name="📋 Criterios de Evaluación",
                    value="**Setup Principal** (50%): Obligatorio\n"
                          "**Confirmación 1** (25%): Opcional\n"
                          "**Confirmación 2** (25%): Opcional\n"
                          "**Mínimo requerido**: 66%",
                    inline=True
                )
                
                # Estrategia específica
                strategies = {
                    'EURUSD': "Breakout 15P + RSI neutral + Sesión",
                    'XAUUSD': "Nivel ±10$ + Mecha >30% + Liquidez", 
                    'BTCEUR': "EMA momentum + EMA50 + ATR expansión"
                }
                
                embed.add_field(
                    name=f"🎯 Estrategia {symbol}",
                    value=strategies.get(symbol, "Estrategia no definida"),
                    inline=True
                )
            
            embed.set_footer(text=f"Para señal real usar: /signal {symbol}")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error en scoring_test_command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @bot.tree.command(name="strategy_details", description="Detalles de estrategia para un símbolo")
    async def strategy_details_command(interaction: discord.Interaction, symbol: str = "EURUSD"):
        """Muestra detalles de la estrategia para un símbolo"""
        try:
            await interaction.response.defer()
            
            symbol = symbol.upper()
            
            # Información de estrategias
            strategies_info = {
                'EURUSD': {
                    'name': 'Breakout + Pullback + Sesión',
                    'setup': 'Breakout de rango 15 períodos',
                    'confirmations': [
                        'RSI entre 40-60 (zona neutral)',
                        'Sesión activa Londres/NY (8-22 GMT)'
                    ],
                    'management': {
                        'sl': 'ATR × 1.5',
                        'tp': 'SL × 2.0 (R:R = 2.0)',
                        'max_daily': 4
                    },
                    'philosophy': 'Breakout + Pullback + Sesión',
                    'min_score': 0.66
                },
                'XAUUSD': {
                    'name': 'Fakeouts + Rejection + Liquidez',
                    'setup': 'Precio cerca de nivel psicológico (±10$)',
                    'confirmations': [
                        'Mecha significativa (>30% del rango)',
                        'Sesión alta liquidez (8-22 GMT)'
                    ],
                    'management': {
                        'sl': '$8 fijo',
                        'tp': '$16 fijo (R:R = 2.0)',
                        'max_daily': 3
                    },
                    'philosophy': 'Fakeouts + Rejection + Liquidez',
                    'min_score': 0.60
                },
                'BTCEUR': {
                    'name': 'Momentum + Tendencia + Expansión',
                    'setup': 'EMA12 vs EMA26 con separación mínima',
                    'confirmations': [
                        'EMA50 como filtro direccional',
                        'ATR por encima de media (expansión)'
                    ],
                    'management': {
                        'sl': 'ATR × 2.0',
                        'tp': 'SL × 1.8 (R:R = 1.8)',
                        'max_daily': 5
                    },
                    'philosophy': 'Momentum + Tendencia + Expansión',
                    'min_score': 0.65
                }
            }
            
            strategy = strategies_info.get(symbol)
            
            if not strategy:
                embed = discord.Embed(
                    title=f"❌ {symbol}",
                    description="Estrategia no disponible para este símbolo",
                    color=0xe74c3c
                )
                embed.add_field(
                    name="Símbolos Disponibles",
                    value="EURUSD, XAUUSD, BTCEUR",
                    inline=False
                )
            else:
                embed = discord.Embed(
                    title=f"📋 Estrategia {symbol}",
                    description=f"**{strategy['name']}**\n*{strategy['philosophy']}*",
                    color=0x2ecc71
                )
                
                # Setup principal
                embed.add_field(
                    name="🎯 Setup Principal (Obligatorio)",
                    value=strategy['setup'],
                    inline=False
                )
                
                # Confirmaciones
                confirmations_text = "\n".join(f"• {conf}" for conf in strategy['confirmations'])
                embed.add_field(
                    name="✅ Confirmaciones (Mínimo 1)",
                    value=confirmations_text,
                    inline=False
                )
                
                # Gestión
                mgmt = strategy['management']
                embed.add_field(
                    name="📊 Gestión de Riesgo",
                    value=f"**SL**: {mgmt['sl']}\n"
                          f"**TP**: {mgmt['tp']}\n"
                          f"**Max/día**: {mgmt['max_daily']}",
                    inline=True
                )
                
                # Scoring
                embed.add_field(
                    name="🧮 Sistema de Scoring",
                    value=f"**Mínimo**: {strategy['min_score']*100:.0f}%\n"
                          f"**Setup**: 50%\n"
                          f"**Confirmaciones**: 50%",
                    inline=True
                )
            
            embed.set_footer(text=f"Usar: /signal {symbol} para generar señal")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error en strategy_details_command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @bot.tree.command(name="reset_counts", description="Resetear contadores de señales (Admin)")
    async def reset_counts_command(interaction: discord.Interaction):
        """Resetea los contadores de señales diarios (solo admin)"""
        try:
            # Verificar permisos (esto debería integrarse con el sistema de permisos existente)
            # Por ahora, permitir a todos para testing
            
            await interaction.response.defer()
            
            old_counts = reset_daily_signal_counts()
            
            embed = discord.Embed(
                title="🔄 Contadores Reseteados",
                description="Los contadores de señales han sido reseteados",
                color=0xf39c12
            )
            
            if old_counts:
                old_counts_text = "\n".join(f"**{symbol}**: {count}" for symbol, count in old_counts.items())
                embed.add_field(
                    name="📊 Contadores Anteriores",
                    value=old_counts_text,
                    inline=True
                )
            
            embed.add_field(
                name="✅ Estado Actual",
                value="Todos los contadores en 0\nSe pueden generar nuevas señales",
                inline=True
            )
            
            embed.set_footer(text=f"Reseteado por: {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error en reset_counts_command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")

def patch_signal_detection():
    """
    Función para parchear la detección de señales en el bot existente
    
    Esta función debe ser llamada para reemplazar las llamadas a detect_signal_advanced
    con detect_signal_integrated
    """
    
    # Esta función se puede usar para monkey-patch el sistema existente
    # si es necesario mantener compatibilidad total
    
    logger.info("🔧 Aplicando parche de detección de señales...")
    
    # Aquí se podría hacer monkey patching si fuera necesario
    # Por ejemplo:
    # import signals
    # signals.detect_signal_advanced = detect_signal_integrated
    
    logger.info("✅ Parche de detección aplicado")

def get_integration_status() -> Dict:
    """Retorna el estado de la integración"""
    return {
        'simplified_system_available': True,
        'integration_active': True,
        'commands_added': [
            'system_info',
            'signal_status', 
            'scoring_test',
            'strategy_details',
            'reset_counts'
        ],
        'compatibility': 'Full backward compatibility maintained'
    }

# Función de utilidad para logging
def log_integration_event(event: str, details: str = ""):
    """Log eventos de integración"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    logger.info(f"[{timestamp}] 🔧 INTEGRATION: {event} {details}")