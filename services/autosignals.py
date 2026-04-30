"""
Servicio de Auto-Señales

Maneja el loop automático de detección y envío de señales.
Consolidado desde bot.py para reducir el tamaño del archivo principal.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import discord

logger = logging.getLogger(__name__)

class AutoSignalsService:
    """Servicio para manejo de señales automáticas"""
    
    def __init__(self, bot, state, config):
        self.bot = bot
        self.state = state
        self.config = config
        self.scan_count = 0
        # Cooldown por símbolo: guarda el timestamp de la última señal enviada
        # Evita spam cuando el mercado está en tendencia fuerte
        self._last_signal_time: dict = {}   # {symbol: datetime}
        self._cooldown_minutes = 60         # mínimo 60 min entre señales del mismo par
        
    async def find_signals_channel(self) -> Optional[discord.TextChannel]:
        """Encuentra el canal de señales"""
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.name == self.config['SIGNALS_CHANNEL_NAME']:
                    return channel
        return None
    
    async def start_auto_signal_loop(self):
        """Inicia el loop principal de auto-señales"""
        await self.bot.wait_until_ready()

        from services.logging import log_event
        from core.circuit_breaker import get_circuit_breaker

        self._circuit_breaker = get_circuit_breaker()
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5  # pausa el loop tras 5 errores seguidos

        log_event(
            f'Auto-signal loop iniciado '
            f'(AUTOSIGNALS={self.state.autosignals}, '
            f'AUTO_EXECUTE={self.config["AUTO_EXECUTE_SIGNALS"]})'
        )

        while True:
            try:
                if self.state.autosignals and not self.config['KILL_SWITCH']:
                    # Verificar circuit breaker antes de escanear
                    can_trade, cb_reason = self._circuit_breaker.can_trade()
                    if not can_trade:
                        if self.scan_count % 30 == 0:
                            log_event(f"⏸️ Circuit breaker activo: {cb_reason}", "WARNING", "AUTOSIGNAL")
                    else:
                        await self._scan_symbols()

                self._consecutive_errors = 0  # reset en cada iteración exitosa
                await asyncio.sleep(self.config['AUTOSIGNAL_INTERVAL'])

            except asyncio.CancelledError:
                log_event("Auto-signal loop cancelado", "WARNING", "AUTOSIGNAL")
                break
            except Exception as e:
                self._consecutive_errors += 1
                logger.error(f"Error en auto-signal loop (intento {self._consecutive_errors}): {e}")

                if self._consecutive_errors >= self._max_consecutive_errors:
                    log_event(
                        f"❌ Auto-signal loop: {self._consecutive_errors} errores consecutivos. "
                        f"Pausando 5 minutos.",
                        "ERROR", "AUTOSIGNAL"
                    )
                    await asyncio.sleep(300)
                    self._consecutive_errors = 0
                else:
                    await asyncio.sleep(30)
    
    async def _scan_symbols(self):
        """Escanea todos los símbolos configurados"""
        from services.logging import log_event

        self.scan_count += 1
        if self.scan_count % 10 == 1:
            log_event(f"Checking {len(self.config['AUTOSIGNAL_SYMBOLS'])} pairs...", "INFO", "AUTOSIGNAL")

        channel = await self.find_signals_channel()
        if channel is None:
            # Notificar cada 50 escaneos para no spamear logs
            if self.scan_count % 50 == 1:
                log_event(
                    f"⚠️ Canal #{self.config['SIGNALS_CHANNEL_NAME']} no encontrado. "
                    f"Las señales no se enviarán hasta que el canal exista.",
                    "WARNING", "AUTOSIGNAL"
                )
            return

        signals_found = 0
        for symbol in self.config['AUTOSIGNAL_SYMBOLS']:
            try:
                signal_sent = await self._process_symbol(symbol, channel)
                if signal_sent:
                    signals_found += 1
            except Exception as e:
                logger.error(f"Error procesando símbolo {symbol}: {e}", exc_info=True)

        if self.scan_count % 30 == 0:
            await self._log_periodic_stats()
    
    async def _process_symbol(self, symbol: str, channel: discord.TextChannel) -> bool:
        """Procesa un símbolo individual"""
        try:
            from services.logging import log_event
            from core import get_trading_engine
            
            # Obtener engine de trading
            engine = get_trading_engine()
            if not engine:
                if self.scan_count % 100 == 1:
                    log_event("Trading engine not available", "WARNING", "AUTOSIGNAL")
                return False
            
            # Obtener datos de mercado
            # 210 velas mínimo para que EMA200 esté disponible en todas las estrategias
            try:
                df = await engine.get_market_data(symbol, timeframe='H1', count=250)
                if df is None or len(df) == 0:
                    return False
                if len(df) < 210:
                    if self.scan_count % 20 == 1:
                        log_event(f"⚠️ {symbol}: solo {len(df)} velas disponibles (mínimo 210)", "WARNING", "AUTOSIGNAL")
                    return False
            except Exception as e:
                if self.scan_count % 50 == 1:
                    log_event(f"Error getting market data for {symbol}: {e}", "WARNING", "AUTOSIGNAL")
                return False
            
            # Evaluar señal usando el ENGINE COMPLETO (no directamente la estrategia)
            try:
                # Obtener configuración del símbolo
                import json
                import os
                rules_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'rules_config.json')
                
                try:
                    with open(rules_config_path, 'r') as f:
                        rules = json.load(f)
                    symbol_config = rules.get(symbol, {})
                    strategy_name = symbol_config.get('strategy', 'ema50_200')
                except Exception:
                    strategy_name = 'ema50_200'
                
                # Usar el engine completo (mismo pipeline que replay)
                result = engine.evaluate_signal(
                    df, 
                    symbol, 
                    strategy_name,
                    symbol_config,
                    skip_duplicate_filter=False  # En producción SÍ usar filtro de duplicados
                )
                
                # Si no hay señal o no debe mostrarse, salir
                if not result.signal or not result.should_show:
                    return False
                
                signal = result.signal
                confidence = result.confidence
                score = result.score
                
                # FILTRO DE CONFIANZA: Rechazar señales LOW
                if confidence in ['LOW', 'VERY_LOW']:
                    if self.scan_count % 20 == 1:
                        log_event(f"{symbol} signal rejected: LOW confidence", "INFO", "AUTOSIGNAL")
                    return False

                # COOLDOWN POR SÍMBOLO: evitar spam del mismo par
                now = datetime.now(timezone.utc)
                last_sent = self._last_signal_time.get(symbol)
                if last_sent is not None:
                    elapsed_min = (now - last_sent).total_seconds() / 60
                    if elapsed_min < self._cooldown_minutes:
                        remaining = int(self._cooldown_minutes - elapsed_min)
                        if self.scan_count % 20 == 1:
                            log_event(
                                f"⏳ {symbol}: cooldown activo, {remaining} min restantes",
                                "INFO", "AUTOSIGNAL"
                            )
                        return False
                
            except Exception as e:
                if self.scan_count % 50 == 1:
                    log_event(f"Error evaluating signal for {symbol}: {e}", "WARNING", "AUTOSIGNAL")
                return False
            
            # Señal aprobada - enviar al canal
            try:
                # Formatear mensaje de señal
                signal_type = signal.get('type', 'BUY').upper()
                entry = signal.get('entry', 0)
                sl = signal.get('sl', 0)
                tp = signal.get('tp', 0)
                
                # Determinar si es auto-aprobada (HIGH o VERY_HIGH)
                auto_approved = confidence in ['HIGH', 'VERY_HIGH']
                
                # Crear embed de señal
                embed_color = 0x00ff00 if signal_type == 'BUY' else 0xff0000
                if auto_approved:
                    embed_color = 0xFFD700  # Dorado para señales auto-aprobadas
                
                embed = discord.Embed(
                    title=f"{'⭐ ' if auto_approved else ''}🎯 {signal_type} {symbol}",
                    description="✅ AUTO-APROBADA" if auto_approved else "⏳ Requiere aprobación manual",
                    color=embed_color,
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(name="📈 Entry", value=f"{entry:.5f}", inline=True)
                embed.add_field(name="🛡️ Stop Loss", value=f"{sl:.5f}", inline=True)
                embed.add_field(name="🎯 Take Profit", value=f"{tp:.5f}", inline=True)
                embed.add_field(name="⭐ Confidence", value=confidence, inline=True)
                embed.add_field(name="📊 Score", value=f"{score:.2f}", inline=True)
                
                # Calcular R:R ratio
                risk = abs(entry - sl)
                reward = abs(tp - entry)
                rr_ratio = reward / risk if risk > 0 else 0
                embed.add_field(name="⚖️ R:R Ratio", value=f"1:{rr_ratio:.2f}", inline=True)
                
                if auto_approved:
                    embed.set_footer(text="Auto-Signal System | AUTO-APROBADA ✅")
                else:
                    embed.set_footer(text="Auto-Signal System | Requiere aprobación manual")
                
                # Generar gráfico con la señal
                chart_file = None
                try:
                    from charts import generate_chart
                    chart_filename = generate_chart(df, symbol=symbol, signal=signal)
                    if chart_filename:
                        chart_file = discord.File(chart_filename, filename=f"{symbol}_signal.png")
                        embed.set_image(url=f"attachment://{symbol}_signal.png")
                except Exception as chart_error:
                    logger.warning(f"Error generando gráfico para {symbol}: {chart_error}")
                
                # Enviar señal con gráfico
                if chart_file:
                    await channel.send(embed=embed, file=chart_file)
                    # Limpiar archivo temporal
                    try:
                        import os
                        os.remove(chart_filename)
                    except Exception:
                        pass
                else:
                    await channel.send(embed=embed)
                
                # Log señal enviada
                approval_status = "AUTO-APROBADA ✅" if auto_approved else "MANUAL ⏳"
                log_event(
                    f"🎯 AUTO-SIGNAL: {signal_type} {symbol} @ {entry:.5f} "
                    f"(SL: {sl:.5f}, TP: {tp:.5f}, Conf: {confidence}) [{approval_status}]",
                    "INFO", "AUTOSIGNAL"
                )
                
                # Registro de actividad por símbolo (métricas dashboard)
                try:
                    from core import record_signal
                    record_signal(symbol.upper())
                except Exception:
                    pass

                # Actualizar cooldown — evitar spam del mismo par
                self._last_signal_time[symbol] = datetime.now(timezone.utc)
                
                # Actualizar dashboard
                try:
                    from services.dashboard import get_dashboard_service
                    get_dashboard_service().add_signal_event(
                        symbol=symbol,
                        strategy=strategy_name,
                        signal_type=signal_type,
                        confidence=confidence,
                        score=score,
                        shown=True,
                        executed=False,
                        entry=float(entry) if entry else None,
                        sl=float(sl) if sl else None,
                        tp=float(tp) if tp else None,
                    )
                except Exception as dash_err:
                    logger.debug(f"Dashboard update error: {dash_err}")
                
                return True
                
            except Exception as e:
                log_event(f"Error sending signal for {symbol}: {e}", "ERROR", "AUTOSIGNAL")
                return False
                
        except Exception as e:
            log_event(f"Unexpected error processing {symbol}: {e}", "ERROR", "AUTOSIGNAL")
            return False
    
    async def _log_periodic_stats(self):
        """Log de estadísticas periódicas"""
        from services.logging import log_event
        from core import get_filters_system
        
        try:
            # Obtener estadísticas del filtro de duplicados
            filters_system = get_filters_system()
            filter_stats = filters_system.get_stats()
            
            # Calcular tiempo de sesión (evitar naive vs aware)
            from services.logging import get_intelligent_logger
            logger_instance = get_intelligent_logger()
            session_start = getattr(logger_instance, 'last_dump', None) or datetime.now(timezone.utc)
            if session_start.tzinfo is None:
                session_start = session_start.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            session_duration = (now_utc - session_start).total_seconds() / 3600
            
            log_event(
                f"📊 STATS: {filter_stats.get('total_signals', 0)} señales evaluadas, "
                f"{filter_stats.get('shown_signals', 0)} mostradas, "
                f"sesión: {session_duration:.1f}h",
                "INFO", "AUTOSIGNAL"
            )
            
        except Exception as e:
            logger.error(f"Error en estadísticas periódicas: {e}")

def create_autosignals_service(bot, state, config):
    """Factory para crear el servicio de auto-señales"""
    return AutoSignalsService(bot, state, config)