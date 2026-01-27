"""
Comandos comerciales para el bot - Sistema de suscripciones
"""

import discord
from discord.ext import commands
from user_management import user_manager, SubscriptionTier, create_trial_user
from datetime import datetime

# Estos comandos se pueden añadir al bot.py

@bot.tree.command(name="subscribe")
@discord.app_commands.describe(
    plan="Plan de suscripción",
    months="Meses de suscripción"
)
@discord.app_commands.choices(plan=[
    discord.app_commands.Choice(name="🥉 BASIC - $29/mes", value="basic"),
    discord.app_commands.Choice(name="🥈 PREMIUM - $79/mes", value="premium"),
    discord.app_commands.Choice(name="🥇 VIP - $199/mes", value="vip")
])
async def slash_subscribe(interaction: discord.Interaction, plan: str, months: int = 1):
    """Suscribirse al bot de trading"""
    
    try:
        tier = SubscriptionTier(plan)
        config = user_manager.get_subscription_config(tier)
        
        embed = discord.Embed(
            title=f"💳 Suscripción {plan.upper()}",
            description="Confirma tu suscripción al bot de trading",
            color=0x00ff00
        )
        
        embed.add_field(
            name="📊 **Características**",
            value=(
                f"**Pares:** {', '.join(config['pairs']) if config['pairs'] != ['all'] else 'Todos'}\n"
                f"**Estrategias:** {'Todas' if config['strategies'] == ['all'] else str(len(config['strategies']))}\n"
                f"**Trades/día:** {config['max_daily_trades']}\n"
                f"**Filtros consolidados:** {'✅ Sí' if config['consolidated_filters'] else '❌ No'}"
            ),
            inline=True
        )
        
        total_price = config['price_monthly'] * months
        embed.add_field(
            name="💰 **Precio**",
            value=(
                f"**Mensual:** ${config['price_monthly']}\n"
                f"**Meses:** {months}\n"
                f"**Total:** ${total_price}"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🎁 **Bonus**",
            value=(
                "• Soporte 24/7\n"
                "• Actualizaciones gratuitas\n"
                "• Comunidad VIP\n"
                "• Estadísticas detalladas"
            ),
            inline=False
        )
        
        # Botones de confirmación
        view = SubscriptionView(interaction.user.id, tier, months, total_price)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="trial")
async def slash_trial(interaction: discord.Interaction):
    """Iniciar prueba gratuita de 7 días"""
    
    user_id = interaction.user.id
    
    # Verificar si ya tiene suscripción
    existing_config = user_manager.get_user_config(user_id)
    if existing_config:
        await interaction.response.send_message(
            "❌ Ya tienes una suscripción activa. Usa `/my_subscription` para ver detalles.",
            ephemeral=True
        )
        return
    
    try:
        # Crear usuario de prueba
        config = create_trial_user(user_id)
        
        embed = discord.Embed(
            title="🎉 ¡Prueba Gratuita Activada!",
            description="Tienes 7 días gratis de acceso PREMIUM",
            color=0x00ff00
        )
        
        embed.add_field(
            name="🚀 **Acceso Incluido**",
            value=(
                "• **Pares:** EURUSD, XAUUSD, BTCEUR\n"
                "• **Estrategias:** Todas las avanzadas\n"
                "• **Trades/día:** 15 máximo\n"
                "• **Filtros avanzados:** ✅ Activos"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⏰ **Vencimiento**",
            value=f"**Expira:** {config.expires_at.strftime('%Y-%m-%d %H:%M')}",
            inline=True
        )
        
        embed.add_field(
            name="🎮 **Primeros Pasos**",
            value=(
                "1. Usa `/debug_signals XAUUSD` para probar\n"
                "2. Configura tu MT5 con `/set_mt5_credentials`\n"
                "3. Activa autosignals con `/autosignals`"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Error activando prueba: {e}", ephemeral=True)

@bot.tree.command(name="my_subscription")
async def slash_my_subscription(interaction: discord.Interaction):
    """Ver detalles de tu suscripción"""
    
    user_id = interaction.user.id
    config = user_manager.get_user_config(user_id)
    
    if not config:
        embed = discord.Embed(
            title="❌ Sin Suscripción",
            description="No tienes una suscripción activa",
            color=0xff0000
        )
        
        embed.add_field(
            name="🎁 **Prueba Gratuita**",
            value="Usa `/trial` para 7 días gratis",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Verificar si está expirada
    is_expired = datetime.now() > config.expires_at
    color = 0xff0000 if is_expired else 0x00ff00
    
    embed = discord.Embed(
        title=f"📋 Mi Suscripción - {config.subscription.value.upper()}",
        description="Detalles de tu suscripción actual",
        color=color
    )
    
    embed.add_field(
        name="📊 **Características**",
        value=(
            f"**Pares:** {', '.join(config.allowed_pairs) if config.allowed_pairs != ['all'] else 'Todos'}\n"
            f"**Estrategias:** {'Todas' if config.allowed_strategies == ['all'] else str(len(config.allowed_strategies))}\n"
            f"**Trades/día:** {config.max_daily_trades}\n"
            f"**Riesgo/trade:** {config.risk_per_trade}%\n"
            f"**Filtros consolidados:** {'✅ Sí' if config.consolidated_filters else '❌ No'}"
        ),
        inline=True
    )
    
    embed.add_field(
        name="⏰ **Estado**",
        value=(
            f"**Expira:** {config.expires_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"**Estado:** {'❌ EXPIRADA' if is_expired else '✅ ACTIVA'}\n"
            f"**Trades hoy:** {user_manager.get_daily_trades_count(user_id)}/{config.max_daily_trades}"
        ),
        inline=True
    )
    
    if is_expired:
        embed.add_field(
            name="🔄 **Renovar**",
            value="Usa `/subscribe` para renovar tu suscripción",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

class SubscriptionView(discord.ui.View):
    def __init__(self, user_id: int, tier: SubscriptionTier, months: int, total_price: float):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.tier = tier
        self.months = months
        self.total_price = total_price
    
    @discord.ui.button(label="✅ Confirmar Pago", style=discord.ButtonStyle.green)
    async def confirm_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Aquí integrarías con Stripe, PayPal, etc.
        
        embed = discord.Embed(
            title="💳 Procesando Pago",
            description=f"Redirigiendo a pasarela de pago para ${self.total_price}",
            color=0xffaa00
        )
        
        embed.add_field(
            name="🔗 **Siguiente Paso**",
            value=(
                "1. Completa el pago en la página que se abrirá\n"
                "2. Tu suscripción se activará automáticamente\n"
                "3. Recibirás confirmación por DM"
            ),
            inline=False
        )
        
        # Aquí añadirías el link real de pago
        embed.add_field(
            name="🌐 **Link de Pago**",
            value="[Pagar con Stripe](https://stripe.com/payment-link-example)",
            inline=False
        )
        
        await interaction.response.edit_message(embed=embed, view=None)
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.red)
    async def cancel_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ Suscripción Cancelada",
            description="No se procesó ningún pago",
            color=0xff0000
        )
        
        await interaction.response.edit_message(embed=embed, view=None)