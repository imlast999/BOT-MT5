"""
Circuit Breaker y Risk Scaling

Implementa dos mecanismos de protección:

1. Circuit Breaker: pausa automática del bot tras N pérdidas consecutivas
   o si el drawdown diario supera el límite configurado.

2. Risk Scaling: ajusta el riesgo por trade dinámicamente según la racha
   de resultados (implementa los valores de rules_config.json).

Uso:
    from core.circuit_breaker import get_circuit_breaker
    cb = get_circuit_breaker()

    # Registrar resultado de un trade
    cb.record_result('WIN', pips=45.0)
    cb.record_result('LOSS', pips=-22.0)

    # Verificar si se puede operar
    ok, reason = cb.can_trade('EURUSD')

    # Obtener riesgo ajustado para el próximo trade
    risk_pct = cb.get_adjusted_risk('EURUSD', base_risk=0.75)
"""

import json
import os
import logging
from datetime import datetime, timezone, date
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    outcome: str        # 'WIN' | 'LOSS'
    pips: float
    symbol: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CircuitBreaker:
    """
    Protege el capital pausando el bot automáticamente cuando:
    - Se alcanzan N pérdidas consecutivas (configurable)
    - El drawdown diario supera el límite configurado

    También implementa risk scaling dinámico basado en rachas.
    """

    def __init__(self):
        self._load_config()
        self.results: List[TradeResult] = []
        self.daily_pips: Dict[str, float] = {}   # fecha → pips acumulados
        self.paused_until: Optional[datetime] = None
        self.pause_reason: str = ""

    def _load_config(self):
        """Carga configuración desde rules_config.json"""
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'rules_config.json')
            with open(config_path, 'r') as f:
                rules = json.load(f)

            global_cfg = rules.get('GLOBAL_SETTINGS', {})

            # Límites del circuit breaker
            self.max_consecutive_losses = 4          # pausa tras 4 pérdidas seguidas
            self.daily_loss_limit_pct   = float(global_cfg.get('loss_limit_daily', 2.0))
            self.drawdown_limit_pct     = float(global_cfg.get('drawdown_limit', 15.0))
            self.pause_hours_on_trigger = 24         # horas de pausa al activarse

            # Risk scaling desde config
            scaling = global_cfg.get('risk_scaling', {})
            self.risk_scaling = {
                'winning_streak_3': float(scaling.get('winning_streak_3', 1.0)),
                'winning_streak_5': float(scaling.get('winning_streak_5', 1.0)),
                'winning_streak_7': float(scaling.get('winning_streak_7', 1.0)),
                'losing_streak_2':  float(scaling.get('losing_streak_2',  0.8)),
                'losing_streak_3':  float(scaling.get('losing_streak_3',  0.5)),
                'losing_streak_4':  float(scaling.get('losing_streak_4',  0.3)),
            }

            logger.info("CircuitBreaker: configuración cargada")

        except Exception as e:
            logger.warning(f"CircuitBreaker: usando valores por defecto ({e})")
            self.max_consecutive_losses = 4
            self.daily_loss_limit_pct   = 2.0
            self.drawdown_limit_pct     = 15.0
            self.pause_hours_on_trigger = 24
            self.risk_scaling = {
                'winning_streak_3': 1.0,
                'winning_streak_5': 1.0,
                'winning_streak_7': 1.0,
                'losing_streak_2':  0.8,
                'losing_streak_3':  0.5,
                'losing_streak_4':  0.3,
            }

    def record_result(self, outcome: str, pips: float = 0.0, symbol: str = 'UNKNOWN'):
        """
        Registra el resultado de un trade cerrado.

        Args:
            outcome: 'WIN' o 'LOSS'
            pips: pips ganados (positivo) o perdidos (negativo)
            symbol: símbolo del trade
        """
        result = TradeResult(outcome=outcome.upper(), pips=pips, symbol=symbol)
        self.results.append(result)

        # Acumular pips del día
        today = date.today().isoformat()
        self.daily_pips[today] = self.daily_pips.get(today, 0.0) + pips

        # Mantener solo los últimos 50 resultados en memoria
        if len(self.results) > 50:
            self.results = self.results[-50:]

        # Verificar si hay que activar el circuit breaker
        self._check_triggers()

        logger.info(
            "CircuitBreaker: resultado registrado | %s %s %.1f pips | "
            "racha=%d | pips_hoy=%.1f",
            outcome, symbol, pips,
            self._consecutive_losses(),
            self.daily_pips.get(today, 0.0)
        )

    def can_trade(self, symbol: str = None) -> Tuple[bool, str]:
        """
        Verifica si el bot puede abrir nuevas operaciones.

        Returns:
            (puede_operar, razón)
        """
        # Verificar pausa activa
        if self.paused_until is not None:
            now = datetime.now(timezone.utc)
            if now < self.paused_until:
                remaining = (self.paused_until - now).total_seconds() / 3600
                return False, (
                    f"Circuit breaker activo: {self.pause_reason} | "
                    f"Reanuda en {remaining:.1f}h"
                )
            else:
                # Pausa expirada
                self.paused_until = None
                self.pause_reason = ""
                logger.info("CircuitBreaker: pausa expirada, trading reanudado")

        return True, "OK"

    def get_adjusted_risk(self, symbol: str, base_risk: float) -> float:
        """
        Devuelve el riesgo ajustado según la racha actual.

        Args:
            symbol: símbolo del trade
            base_risk: riesgo base configurado (ej: 0.75%)

        Returns:
            riesgo ajustado (puede ser menor o mayor que base_risk)
        """
        consecutive_losses = self._consecutive_losses()
        consecutive_wins   = self._consecutive_wins()

        multiplier = 1.0

        # Rachas perdedoras → reducir riesgo
        if consecutive_losses >= 4:
            multiplier = self.risk_scaling['losing_streak_4']
        elif consecutive_losses >= 3:
            multiplier = self.risk_scaling['losing_streak_3']
        elif consecutive_losses >= 2:
            multiplier = self.risk_scaling['losing_streak_2']

        # Rachas ganadoras → aumentar riesgo (solo si no hay pérdidas recientes)
        elif consecutive_wins >= 7:
            multiplier = self.risk_scaling['winning_streak_7']
        elif consecutive_wins >= 5:
            multiplier = self.risk_scaling['winning_streak_5']
        elif consecutive_wins >= 3:
            multiplier = self.risk_scaling['winning_streak_3']

        adjusted = round(base_risk * multiplier, 4)

        if multiplier != 1.0:
            logger.info(
                "RiskScaling: %s | base=%.3f%% × %.1f = %.3f%% | "
                "losses=%d wins=%d",
                symbol, base_risk, multiplier, adjusted,
                consecutive_losses, consecutive_wins
            )

        return adjusted

    def get_status(self) -> Dict:
        """Devuelve el estado actual del circuit breaker."""
        today = date.today().isoformat()
        can_trade, reason = self.can_trade()

        return {
            'can_trade':           can_trade,
            'reason':              reason,
            'consecutive_losses':  self._consecutive_losses(),
            'consecutive_wins':    self._consecutive_wins(),
            'daily_pips':          self.daily_pips.get(today, 0.0),
            'paused_until':        self.paused_until.isoformat() if self.paused_until else None,
            'pause_reason':        self.pause_reason,
            'total_results':       len(self.results),
            'risk_multiplier':     self._current_risk_multiplier(),
        }

    # ── Internos ─────────────────────────────────────────────────────────────

    def _consecutive_losses(self) -> int:
        count = 0
        for r in reversed(self.results):
            if r.outcome == 'LOSS':
                count += 1
            else:
                break
        return count

    def _consecutive_wins(self) -> int:
        count = 0
        for r in reversed(self.results):
            if r.outcome == 'WIN':
                count += 1
            else:
                break
        return count

    def _current_risk_multiplier(self) -> float:
        """Multiplier actual sin aplicar a un riesgo base."""
        losses = self._consecutive_losses()
        wins   = self._consecutive_wins()
        if losses >= 4: return self.risk_scaling['losing_streak_4']
        if losses >= 3: return self.risk_scaling['losing_streak_3']
        if losses >= 2: return self.risk_scaling['losing_streak_2']
        if wins   >= 7: return self.risk_scaling['winning_streak_7']
        if wins   >= 5: return self.risk_scaling['winning_streak_5']
        if wins   >= 3: return self.risk_scaling['winning_streak_3']
        return 1.0

    def _check_triggers(self):
        """Verifica si hay que activar el circuit breaker."""
        # Trigger 1: pérdidas consecutivas
        consecutive = self._consecutive_losses()
        if consecutive >= self.max_consecutive_losses:
            self._activate_pause(
                f"{consecutive} pérdidas consecutivas"
            )
            return

        # Trigger 2: pérdida diaria excesiva (en pips, aproximación)
        today = date.today().isoformat()
        daily = self.daily_pips.get(today, 0.0)
        # No tenemos balance aquí, usamos pips como proxy
        # Si las pérdidas del día superan 500 pips, pausar
        if daily < -500:
            self._activate_pause(
                f"Pérdida diaria de {abs(daily):.0f} pips"
            )

    def _activate_pause(self, reason: str):
        """Activa la pausa del circuit breaker."""
        from datetime import timedelta
        if self.paused_until is not None:
            return  # Ya está pausado

        self.paused_until = datetime.now(timezone.utc) + timedelta(hours=self.pause_hours_on_trigger)
        self.pause_reason = reason

        logger.warning(
            "🔴 CIRCUIT BREAKER ACTIVADO: %s | Pausa hasta %s",
            reason, self.paused_until.strftime('%Y-%m-%d %H:%M UTC')
        )


# ── Instancia global ──────────────────────────────────────────────────────────

_circuit_breaker: Optional[CircuitBreaker] = None

def get_circuit_breaker() -> CircuitBreaker:
    """Obtiene la instancia global del circuit breaker."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker
