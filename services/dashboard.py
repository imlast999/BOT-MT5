"""Servicio de Dashboard Consolidado"""

import logging
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
import threading
import time

try:
    from core import active_symbols
except Exception:
    active_symbols = {}

try:
    from core.engine import symbol_health
except Exception:
    symbol_health = {}

logger = logging.getLogger(__name__)


@dataclass
class DashboardMetrics:
    signals_today: int = 0
    signals_shown: int = 0
    signals_executed: int = 0
    signals_rejected: int = 0
    symbol_activity: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    symbol_performance: Dict[str, Dict] = field(default_factory=dict)
    confidence_distribution: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    positions_open: int = 0
    total_profit: float = 0.0
    win_rate: float = 0.0
    uptime_seconds: int = 0
    last_signal_time: Optional[datetime] = None
    system_status: str = "RUNNING"


@dataclass
class SignalEvent:
    timestamp: datetime
    symbol: str
    strategy: str
    signal_type: str
    confidence: str
    score: float
    shown: bool
    executed: bool
    rejection_reason: Optional[str] = None
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None


class DashboardService:

    def __init__(self):
        self.start_time = datetime.now(timezone.utc)
        self.metrics = DashboardMetrics()
        self.signal_history = deque(maxlen=2000)
        self.performance_history = deque(maxlen=200)
        self.last_mt5_update: Optional[datetime] = None
        self.dashboard_config = {
            'update_interval': int(os.getenv('DASHBOARD_UPDATE_INTERVAL', '30')),
            'history_retention_hours': int(os.getenv('DASHBOARD_HISTORY_HOURS', '168')),
            'enable_persistence': os.getenv('DASHBOARD_PERSISTENCE', '1') == '1',
            'data_file': os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dashboard_data.json')
        }
        self.is_running = False
        self.update_thread = None
        self.lock = threading.Lock()
        if self.dashboard_config['enable_persistence']:
            self._load_persisted_data()

    def start(self):
        try:
            with self.lock:
                if self.is_running:
                    return
                self.is_running = True
                self.start_time = datetime.now(timezone.utc)
                self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
                self.update_thread.start()
                self._start_web_server()
                logger.info("Dashboard service started")
        except Exception as e:
            logger.error(f"Error starting dashboard: {e}")
            self.is_running = False

    def _start_web_server(self):
        try:
            if os.getenv('DISABLE_DASHBOARD', '0') == '1':
                return
            from http.server import HTTPServer, BaseHTTPRequestHandler
            dashboard_service = self

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    try:
                        if self.path in ('/', '/dashboard'):
                            body = dashboard_service.get_dashboard_html().encode('utf-8')
                            self.send_response(200)
                            self.send_header('Content-type', 'text/html; charset=utf-8')
                            self.end_headers()
                            self.wfile.write(body)
                        elif self.path == '/api/metrics':
                            body = json.dumps(dashboard_service.get_current_metrics(), indent=2).encode('utf-8')
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(body)
                        elif self.path.startswith('/api/history'):
                            body = json.dumps(dashboard_service.get_signal_history(hours=168), indent=2).encode('utf-8')
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(body)
                        elif self.path == '/api/export':
                            csv = dashboard_service.export_signals_csv().encode('utf-8')
                            fname = f"signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                            self.send_response(200)
                            self.send_header('Content-type', 'text/csv; charset=utf-8')
                            self.send_header('Content-Disposition', f'attachment; filename="{fname}"')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(csv)
                        else:
                            self.send_response(404)
                            self.end_headers()
                    except Exception as e:
                        logger.error(f"Dashboard request error: {e}")
                        self.send_response(500)
                        self.end_headers()

                def log_message(self, *args):
                    pass

            port = int(os.getenv('DASHBOARD_PORT', '8080'))

            def run():
                try:
                    HTTPServer(('', port), Handler).serve_forever()
                except Exception as e:
                    logger.error(f"Dashboard server error: {e}")

            threading.Thread(target=run, daemon=True).start()
            logger.info(f"Dashboard on http://localhost:{port}")
        except Exception as e:
            logger.error(f"Error starting web server: {e}")

    def stop(self):
        try:
            with self.lock:
                if not self.is_running:
                    return
                self.is_running = False
                if self.dashboard_config['enable_persistence']:
                    self._save_persisted_data()
        except Exception as e:
            logger.error(f"Error stopping dashboard: {e}")

    def add_signal_event(self, symbol: str, strategy: str, signal_type: str,
                         confidence: str, score: float, shown: bool,
                         executed: bool = False, rejection_reason: str = None,
                         entry: float = None, sl: float = None, tp: float = None):
        try:
            with self.lock:
                event = SignalEvent(
                    timestamp=datetime.now(timezone.utc),
                    symbol=symbol, strategy=strategy, signal_type=signal_type,
                    confidence=confidence, score=score, shown=shown,
                    executed=executed, rejection_reason=rejection_reason,
                    entry=entry, sl=sl, tp=tp,
                )
                self.signal_history.append(event)
                self._update_signal_metrics(event)
                self.metrics.last_signal_time = event.timestamp
        except Exception as e:
            logger.error(f"Error adding signal event: {e}")

    def update_trading_metrics(self, positions_open: int, total_profit: float, win_rate: float):
        try:
            with self.lock:
                self.metrics.positions_open = positions_open
                self.metrics.total_profit = total_profit
                self.metrics.win_rate = win_rate
                self.performance_history.append({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'positions_open': positions_open,
                    'total_profit': total_profit,
                    'win_rate': win_rate,
                    'signals_today': self.metrics.signals_today,
                })
        except Exception as e:
            logger.error(f"Error updating trading metrics: {e}")

    def get_current_metrics(self) -> Dict:
        try:
            with self.lock:
                uptime = datetime.now(timezone.utc) - self.start_time
                self.metrics.uptime_seconds = int(uptime.total_seconds())
                return {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'uptime_seconds': self.metrics.uptime_seconds,
                    'uptime_formatted': self._format_uptime(uptime),
                    'system_status': self.metrics.system_status,
                    'signals': {
                        'today': self.metrics.signals_today,
                        'shown': self.metrics.signals_shown,
                        'executed': self.metrics.signals_executed,
                        'rejected': self.metrics.signals_rejected,
                        'show_rate': (self.metrics.signals_shown / self.metrics.signals_today * 100) if self.metrics.signals_today > 0 else 0,
                        'last_signal_time': self.metrics.last_signal_time.isoformat() if self.metrics.last_signal_time else None,
                    },
                    'symbols': {
                        'activity': dict(self.metrics.symbol_activity),
                        'performance': self.metrics.symbol_performance,
                        'active': dict(active_symbols or {}),
                    },
                    'confidence_distribution': dict(self.metrics.confidence_distribution),
                    'trading': {
                        'positions_open': self.metrics.positions_open,
                        'total_profit': self.metrics.total_profit,
                        'win_rate': self.metrics.win_rate,
                    },
                }
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return {'error': str(e), 'system_status': 'ERROR',
                    'signals': {'today':0,'shown':0,'executed':0,'rejected':0,'show_rate':0,'last_signal_time':None},
                    'symbols': {'activity':{},'performance':{},'active':{}},
                    'confidence_distribution': {},
                    'trading': {'positions_open':0,'total_profit':0.0,'win_rate':0.0},
                    'uptime_formatted': '0s', 'uptime_seconds': 0,
                    'timestamp': datetime.now(timezone.utc).isoformat()}

    def get_signal_history(self, hours: int = 168, symbol: str = None) -> List[Dict]:
        try:
            with self.lock:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                result = []
                for ev in self.signal_history:
                    if ev.timestamp < cutoff:
                        continue
                    if symbol and ev.symbol != symbol:
                        continue
                    result.append({
                        'timestamp': ev.timestamp.isoformat(),
                        'symbol': ev.symbol, 'strategy': ev.strategy,
                        'signal_type': ev.signal_type, 'confidence': ev.confidence,
                        'score': ev.score, 'shown': ev.shown, 'executed': ev.executed,
                        'rejection_reason': ev.rejection_reason,
                        'entry': ev.entry, 'sl': ev.sl, 'tp': ev.tp,
                    })
                return result
        except Exception as e:
            logger.error(f"Error getting signal history: {e}")
            return []

    def export_signals_csv(self) -> str:
        try:
            lines = ['timestamp,symbol,direction,confidence,entry,sl,tp,rr,status,shown']
            for ev in self.get_signal_history(hours=168):
                entry = ev.get('entry'); sl = ev.get('sl'); tp = ev.get('tp')
                rr = ''
                if entry and sl and tp and abs(entry - sl) > 0:
                    rr = f"{abs(tp-entry)/abs(entry-sl):.2f}"
                status = self._get_signal_status_dict(ev)
                lines.append(
                    f"{ev['timestamp'][:16]},{ev['symbol']},{ev['signal_type']},"
                    f"{ev['confidence']},{entry or ''},{sl or ''},{tp or ''},"
                    f"{rr},{status},{'yes' if ev['shown'] else 'no'}"
                )
            return '\n'.join(lines)
        except Exception as e:
            logger.error(f"Error exporting CSV: {e}")
            return "error,generating,csv"

    def _get_signal_status_dict(self, ev: dict) -> str:
        try:
            import MetaTrader5 as mt5
            entry = ev.get('entry'); sl = ev.get('sl'); tp = ev.get('tp')
            sym = ev.get('symbol', ''); stype = ev.get('signal_type', 'BUY')
            if not (entry and sl and tp):
                return 'pending'
            tick = mt5.symbol_info_tick(sym)
            if not tick:
                return 'pending'
            price = (tick.bid + tick.ask) / 2
            if stype == 'BUY':
                return 'win' if price >= tp else 'loss' if price <= sl else 'open'
            else:
                return 'win' if price <= tp else 'loss' if price >= sl else 'open'
        except Exception:
            return 'pending'

    def get_dashboard_html(self) -> str:
        try:
            metrics   = self.get_current_metrics()
            history   = self.get_signal_history(hours=168)
            cb_status = {}
            try:
                from core.circuit_breaker import get_circuit_breaker
                cb_status = get_circuit_breaker().get_status()
            except Exception:
                pass

            # Precios actuales MT5
            current_prices: dict = {}
            try:
                import MetaTrader5 as mt5
                for sym in ('EURUSD', 'XAUUSD', 'BTCEUR'):
                    tick = mt5.symbol_info_tick(sym)
                    if tick:
                        current_prices[sym] = (tick.bid + tick.ask) / 2
                self.last_mt5_update = datetime.now(timezone.utc)
            except Exception:
                pass

            def sig_status(ev):
                entry = ev.get('entry'); sl = ev.get('sl'); tp = ev.get('tp')
                sym = ev.get('symbol', ''); stype = ev.get('signal_type', 'BUY')
                price = current_prices.get(sym)
                if not (entry and sl and tp and price):
                    return 'pending'
                if stype == 'BUY':
                    return 'win' if price >= tp else 'loss' if price <= sl else 'open'
                else:
                    return 'win' if price <= tp else 'loss' if price >= sl else 'open'

            # Equity simulada
            risk_pct = 0.0075
            balance = 5000.0
            try:
                import MetaTrader5 as mt5
                info = mt5.account_info()
                if info:
                    balance = float(info.balance)
            except Exception:
                pass

            equity = balance; wins_n = losses_n = open_n = 0; eq_pts = [balance]
            for ev in history:
                st = sig_status(ev)
                entry = ev.get('entry'); sl = ev.get('sl'); tp = ev.get('tp')
                if st == 'win':
                    wins_n += 1
                    rr = abs(tp-entry)/abs(entry-sl) if entry and sl and tp and abs(entry-sl)>0 else 1
                    equity += equity * risk_pct * rr
                elif st == 'loss':
                    losses_n += 1; equity -= equity * risk_pct
                elif st == 'open':
                    open_n += 1
                eq_pts.append(equity)

            eq_change = equity - balance
            eq_pct    = eq_change / balance * 100 if balance > 0 else 0
            eq_color  = '#3fb950' if eq_change >= 0 else '#f85149'
            closed    = wins_n + losses_n
            wr_pct    = wins_n / closed * 100 if closed > 0 else 0
            wr_color  = '#3fb950' if wr_pct >= 50 else '#d29922' if wr_pct >= 40 else '#f85149'

            if len(eq_pts) > 1:
                mn = min(eq_pts); mx = max(eq_pts); rng = mx - mn if mx != mn else 1
                W = 120; H = 30
                pts = " ".join(f"{int(i/(len(eq_pts)-1)*W)},{int(H-(v-mn)/rng*H)}" for i,v in enumerate(eq_pts))
                sparkline = (f'<svg width="{W}" height="{H}" style="vertical-align:middle;margin-left:8px">'
                             f'<polyline points="{pts}" fill="none" stroke="{eq_color}" stroke-width="1.5"/></svg>')
            else:
                sparkline = ''

            if self.last_mt5_update:
                d = (datetime.now(timezone.utc) - self.last_mt5_update).total_seconds()
                mt5_ind = '🟢 Conectado' if d < 120 else f'🟡 {int(d//60)}m sin datos' if d < 300 else f'🔴 {int(d//60)}m sin datos'
                mt5_col = '#3fb950' if d < 120 else '#d29922' if d < 300 else '#f85149'
            else:
                mt5_ind = '— Sin datos'; mt5_col = '#8b949e'

            status_map = {
                'win':     '<span style="color:#3fb950;font-weight:600">WIN ✅</span>',
                'loss':    '<span style="color:#f85149;font-weight:600">LOSS ❌</span>',
                'open':    '<span style="color:#d29922">OPEN ⏳</span>',
                'pending': '<span style="color:#8b949e">—</span>',
            }

            recent_rows = ""
            for ev in reversed(history[-50:]):
                ts = ev['timestamp'][:16].replace('T', ' ')
                sym = ev['symbol']; stype = ev['signal_type']; conf = ev['confidence']
                shown = "✅" if ev['shown'] else "—"
                cc = {'HIGH':'conf-high','VERY_HIGH':'conf-high','MEDIUM-HIGH':'conf-med-high','MEDIUM':'conf-med'}.get(conf,'conf-low')
                dc = 'dir-buy' if stype == 'BUY' else 'dir-sell'
                entry = ev.get('entry'); sl = ev.get('sl'); tp = ev.get('tp')
                if sym == 'EURUSD':   fmt = lambda v: f"{v:.5f}" if v is not None else "—"
                elif sym == 'XAUUSD': fmt = lambda v: f"{v:.2f}"  if v is not None else "—"
                else:                 fmt = lambda v: f"{v:.0f}"   if v is not None else "—"
                rr_str = (f"{abs(tp-entry)/abs(entry-sl):.1f}" if entry and sl and tp and abs(entry-sl)>0 else "—")
                st_html = status_map.get(sig_status(ev), status_map['pending'])
                recent_rows += (f'<tr><td>{ts}</td><td class="sym">{sym}</td>'
                                 f'<td class="{dc}">{stype}</td><td class="{cc}">{conf}</td>'
                                 f'<td>{fmt(entry)}</td><td style="color:var(--red)">{fmt(sl)}</td>'
                                 f'<td style="color:var(--green)">{fmt(tp)}</td>'
                                 f'<td>{rr_str}</td><td>{st_html}</td><td>{shown}</td></tr>\n')
            if not recent_rows:
                recent_rows = '<tr><td colspan="10" class="empty">Sin señales registradas aún</td></tr>'

            sig = metrics.get('signals', {}); trd = metrics.get('trading', {})
            sp  = metrics.get('symbols', {}).get('performance', {})
            s_today = sig.get('today', 0); s_shown = sig.get('shown', 0)
            s_rate  = f"{sig.get('show_rate',0):.0f}%"
            pos_open = trd.get('positions_open', 0); t_profit = trd.get('total_profit', 0.0)
            p_color = '#3fb950' if t_profit >= 0 else '#f85149'
            uptime  = metrics.get('uptime_formatted', '—'); sys_st = metrics.get('system_status', 'RUNNING')
            ls = sig.get('last_signal_time', ''); ls_fmt = ls[:16].replace('T',' ') if ls else '—'
            cb_ok = cb_status.get('can_trade', True); cb_l = cb_status.get('consecutive_losses', 0)
            cb_w  = cb_status.get('consecutive_wins', 0); cb_m = cb_status.get('risk_multiplier', 1.0)
            cb_lbl = 'ACTIVO' if cb_ok else 'PAUSADO'; cb_rsn = cb_status.get('reason', '')

            def sym_row(sym):
                perf = sp.get(sym, {}); tot = perf.get('total_signals',0); shw = perf.get('shown_signals',0)
                avg  = perf.get('avg_confidence_score', 0.0)
                h = (symbol_health or {}).get(sym, {}); lt = h.get('last_signal_time')
                nu = datetime.now(timezone.utc)
                if lt:
                    t = lt if lt.tzinfo else lt.replace(tzinfo=timezone.utc)
                    d = (nu-t).total_seconds()
                    ltxt = "<1 min" if d<60 else f"{int(d//60)}m" if d<3600 else f"{int(d//3600)}h {int((d%3600)//60)}m"
                    inact = d > 5400
                else:
                    ltxt = "—"; inact = True
                dot = '🔴' if h.get('status') in ('ERROR','DISABLED') else ('🟡' if inact else '🟢')
                return (f'<tr><td class="sym">{sym}</td><td>{dot}</td>'
                        f'<td>{tot}</td><td>{shw}</td><td>{avg:.2f}</td><td>{ltxt}</td></tr>')

            sym_rows = sym_row('EURUSD') + sym_row('XAUUSD') + sym_row('BTCEUR')
            port = os.getenv('DASHBOARD_PORT', '8080')
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trading Bot — Dashboard</title>
<style>
:root{{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#e6edf3;--muted:#8b949e;--blue:#58a6ff;--green:#3fb950;--yellow:#d29922;--red:#f85149;--purple:#a371f7}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px}}
a{{color:var(--blue);text-decoration:none}}
.page{{max-width:1150px;margin:0 auto;padding:24px 16px}}
.topbar{{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}}
.topbar h1{{font-size:18px;font-weight:600}}.topbar .meta{{font-size:12px;color:var(--muted);text-align:right}}
.grid-4{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.grid-3{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}}
@media(max-width:700px){{.grid-4,.grid-3{{grid-template-columns:repeat(2,1fr)}}.grid-2{{grid-template-columns:1fr}}}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px}}
.card-title{{font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:8px}}
.card-value{{font-size:28px;font-weight:700;line-height:1}}.card-sub{{font-size:12px;color:var(--muted);margin-top:4px}}
.section-title{{font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px}}
table{{width:100%;border-collapse:collapse}}
th{{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);padding:6px 10px;border-bottom:1px solid var(--border);text-align:left}}
td{{padding:7px 10px;border-bottom:1px solid rgba(48,54,61,.5);font-size:12px}}
tr:last-child td{{border-bottom:none}}tr:hover td{{background:rgba(88,166,255,.04)}}
.empty{{color:var(--muted);text-align:center;padding:20px}}
.sym{{font-weight:600;color:var(--blue)}}.dir-buy{{color:var(--green);font-weight:600}}.dir-sell{{color:var(--red);font-weight:600}}
.conf-high{{color:var(--green)}}.conf-med-high{{color:var(--blue)}}.conf-med{{color:var(--yellow)}}.conf-low{{color:var(--red)}}
.cb-bar{{display:flex;align-items:center;gap:16px;flex-wrap:wrap}}
.cb-pill{{padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}}
.cb-ok{{background:rgba(63,185,80,.15);color:var(--green)}}.cb-stop{{background:rgba(248,81,73,.15);color:var(--red)}}
.cb-stat{{font-size:12px;color:var(--muted)}}.cb-stat span{{color:var(--text);font-weight:600}}
.export-btn{{background:var(--blue);color:#0d1117;border:none;padding:5px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}}
.footer{{margin-top:24px;font-size:11px;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px}}
.dot-live{{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--green);margin-right:5px;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
</style></head>
<body><div class="page">

<div class="topbar">
  <h1>🤖 Trading Bot <span style="color:var(--muted);font-weight:400">/ Dashboard</span></h1>
  <div class="meta">
    <div><span class="dot-live"></span>En vivo · actualiza cada 30s</div>
    <div>{now_str}</div>
    <div style="color:{mt5_col}">{mt5_ind}</div>
  </div>
</div>

<div class="grid-4">
  <div class="card"><div class="card-title">Estado</div><div class="card-value" style="font-size:18px;color:var(--green)">{sys_st}</div><div class="card-sub">Uptime: {uptime}</div></div>
  <div class="card"><div class="card-title">Señales (sesión)</div><div class="card-value" style="color:var(--blue)">{s_today}</div><div class="card-sub">Mostradas: {s_shown} ({s_rate})</div></div>
  <div class="card"><div class="card-title">Posiciones abiertas</div><div class="card-value" style="color:var(--purple)">{pos_open}</div><div class="card-sub">Última señal: {ls_fmt}</div></div>
  <div class="card"><div class="card-title">Profit total</div><div class="card-value" style="color:{p_color}">{t_profit:+.2f} €</div><div class="card-sub">Paper trading activo</div></div>
</div>

<div class="grid-3">
  <div class="card">
    <div class="card-title">Equity simulada (paper)</div>
    <div style="display:flex;align-items:center">
      <span class="card-value" style="color:{eq_color}">{equity:,.0f} €</span>{sparkline}
    </div>
    <div class="card-sub">{eq_change:+.2f} € ({eq_pct:+.1f}%) vs balance inicial</div>
  </div>
  <div class="card">
    <div class="card-title">Winrate paper trading</div>
    <div class="card-value" style="color:{wr_color}">{wr_pct:.0f}%</div>
    <div class="card-sub">✅ {wins_n} wins · ❌ {losses_n} losses · ⏳ {open_n} abiertas</div>
  </div>
  <div class="card">
    <div class="card-title">Exportar señales (7 días)</div>
    <div style="margin-top:8px"><a href="/api/export" class="export-btn" download>⬇ Descargar CSV</a></div>
    <div class="card-sub" style="margin-top:8px">{len(history)} señales en historial</div>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <div class="section-title">Circuit Breaker</div>
    <div class="cb-bar" style="margin-bottom:12px">
      <span class="cb-pill {'cb-ok' if cb_ok else 'cb-stop'}">{cb_lbl}</span>
      {'<span style="color:var(--red);font-size:11px">' + cb_rsn + '</span>' if not cb_ok else ''}
    </div>
    <div class="cb-bar">
      <div class="cb-stat">Pérdidas: <span style="color:{'var(--red)' if cb_l>0 else 'var(--text)'}">{cb_l}</span></div>
      <div class="cb-stat">Wins: <span style="color:{'var(--green)' if cb_w>0 else 'var(--text)'}">{cb_w}</span></div>
      <div class="cb-stat">Riesgo ×<span style="color:{'var(--yellow)' if cb_m!=1.0 else 'var(--text)'}">{cb_m:.1f}</span></div>
    </div>
  </div>
  <div class="card">
    <div class="section-title">Pares monitoreados</div>
    <table><thead><tr><th>Par</th><th></th><th>Total</th><th>Mostradas</th><th>Score avg</th><th>Última</th></tr></thead>
    <tbody>{sym_rows}</tbody></table>
  </div>
</div>

<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
    <div class="section-title" style="margin-bottom:0">Señales recientes (últimas 7 días · últimas 50)</div>
    <a href="/api/export" class="export-btn" download>⬇ CSV</a>
  </div>
  <table>
    <thead><tr><th>Hora</th><th>Par</th><th>Dir</th><th>Confianza</th><th>Entry</th><th style="color:var(--red)">SL</th><th style="color:var(--green)">TP</th><th>R:R</th><th>Estado</th><th>Enviada</th></tr></thead>
    <tbody>{recent_rows}</tbody>
  </table>
</div>

<div class="footer">
  <span>Puerto: <a href="http://localhost:{port}">:{port}</a> · <a href="/api/metrics">API JSON</a> · <a href="/api/export">Export CSV</a></span>
  <span>Auto-execute: OFF · Solo señales Discord</span>
</div>
</div>
<script>setTimeout(()=>location.reload(),30000);</script>
</body></html>"""

        except Exception as e:
            logger.error(f"Error generating dashboard HTML: {e}")
            return (f"<html><body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:40px'>"
                    f"<h2>Dashboard Error</h2><pre>{e}</pre></body></html>")

    def _update_signal_metrics(self, event: SignalEvent):
        self.metrics.signals_today += 1
        self.metrics.symbol_activity[event.symbol] += 1
        self.metrics.confidence_distribution[event.confidence] += 1
        if event.shown:
            self.metrics.signals_shown += 1
        else:
            self.metrics.signals_rejected += 1
        if event.executed:
            self.metrics.signals_executed += 1
        if event.symbol not in self.metrics.symbol_performance:
            self.metrics.symbol_performance[event.symbol] = {
                'total_signals': 0, 'shown_signals': 0,
                'executed_signals': 0, 'avg_confidence_score': 0.0,
            }
        sp = self.metrics.symbol_performance[event.symbol]
        sp['total_signals'] += 1
        if event.shown:    sp['shown_signals'] += 1
        if event.executed: sp['executed_signals'] += 1
        total = sp['total_signals']
        sp['avg_confidence_score'] = ((sp['avg_confidence_score'] * (total-1)) + event.score) / total

    def _update_loop(self):
        while self.is_running:
            try:
                self._cleanup_old_data()
                if self.dashboard_config['enable_persistence']:
                    self._save_persisted_data()
                time.sleep(self.dashboard_config['update_interval'])
            except Exception as e:
                logger.error(f"Dashboard update loop error: {e}")
                time.sleep(5)

    def _cleanup_old_data(self):
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.dashboard_config['history_retention_hours'])
            while self.signal_history and self.signal_history[0].timestamp < cutoff:
                self.signal_history.popleft()
            while self.performance_history:
                t = datetime.fromisoformat(self.performance_history[0]['timestamp'].replace('Z', '+00:00'))
                if t < cutoff:
                    self.performance_history.popleft()
                else:
                    break
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    def _format_uptime(self, uptime: timedelta) -> str:
        s = int(uptime.total_seconds())
        h, r = divmod(s, 3600); m, sec = divmod(r, 60)
        return f"{h}h {m}m" if h > 0 else f"{m}m {sec}s" if m > 0 else f"{sec}s"

    def _save_persisted_data(self):
        try:
            history_serialized = [
                {'timestamp': ev.timestamp.isoformat(), 'symbol': ev.symbol,
                 'strategy': ev.strategy, 'signal_type': ev.signal_type,
                 'confidence': ev.confidence, 'score': ev.score,
                 'shown': ev.shown, 'executed': ev.executed,
                 'rejection_reason': ev.rejection_reason,
                 'entry': ev.entry, 'sl': ev.sl, 'tp': ev.tp}
                for ev in self.signal_history
            ]
            data = {
                'metrics': {
                    'signals_today': self.metrics.signals_today,
                    'signals_shown': self.metrics.signals_shown,
                    'signals_executed': self.metrics.signals_executed,
                    'signals_rejected': self.metrics.signals_rejected,
                    'symbol_activity': dict(self.metrics.symbol_activity),
                    'symbol_performance': self.metrics.symbol_performance,
                    'confidence_distribution': dict(self.metrics.confidence_distribution),
                },
                'signal_history': history_serialized,
                'last_save': datetime.now(timezone.utc).isoformat(),
            }
            with open(self.dashboard_config['data_file'], 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving data: {e}")

    def _load_persisted_data(self):
        try:
            if not os.path.exists(self.dashboard_config['data_file']):
                return
            with open(self.dashboard_config['data_file'], 'r', encoding='utf-8') as f:
                data = json.load(f)
            last_save = datetime.fromisoformat(data.get('last_save', '2000-01-01T00:00:00+00:00'))
            if datetime.now(timezone.utc) - last_save > timedelta(hours=168):
                logger.info("Dashboard data too old, starting fresh")
                return
            m = data.get('metrics', {})
            self.metrics.signals_today    = m.get('signals_today', 0)
            self.metrics.signals_shown    = m.get('signals_shown', 0)
            self.metrics.signals_executed = m.get('signals_executed', 0)
            self.metrics.signals_rejected = m.get('signals_rejected', 0)
            for sym, cnt in m.get('symbol_activity', {}).items():
                self.metrics.symbol_activity[sym] = cnt
            self.metrics.symbol_performance = m.get('symbol_performance', {})
            for conf, cnt in m.get('confidence_distribution', {}).items():
                self.metrics.confidence_distribution[conf] = cnt
            cutoff = datetime.now(timezone.utc) - timedelta(hours=168)
            for ev_data in data.get('signal_history', []):
                try:
                    ts = datetime.fromisoformat(ev_data['timestamp'])
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                    self.signal_history.append(SignalEvent(
                        timestamp=ts, symbol=ev_data.get('symbol',''),
                        strategy=ev_data.get('strategy',''), signal_type=ev_data.get('signal_type',''),
                        confidence=ev_data.get('confidence',''), score=float(ev_data.get('score',0)),
                        shown=bool(ev_data.get('shown',False)), executed=bool(ev_data.get('executed',False)),
                        rejection_reason=ev_data.get('rejection_reason'),
                        entry=ev_data.get('entry'), sl=ev_data.get('sl'), tp=ev_data.get('tp'),
                    ))
                except Exception:
                    pass
            logger.info(f"Dashboard loaded: {len(self.signal_history)} signals")
        except Exception as e:
            logger.error(f"Error loading data: {e}")


# ── Instancia global ──────────────────────────────────────────────────────────

dashboard_service = DashboardService()


def get_dashboard_service() -> DashboardService:
    return dashboard_service

def start_enhanced_dashboard():
    dashboard_service.start()

def stop_enhanced_dashboard():
    dashboard_service.stop()

def add_signal_to_enhanced_dashboard(symbol: str, strategy: str, signal_type: str,
                                     confidence: str, score: float, shown: bool, **kwargs):
    dashboard_service.add_signal_event(
        symbol, strategy, signal_type, confidence, score, shown,
        entry=kwargs.get('entry'), sl=kwargs.get('sl'), tp=kwargs.get('tp'),
        **{k: v for k, v in kwargs.items() if k not in ('entry', 'sl', 'tp')}
    )

def update_dashboard_stats(positions_open: int = 0, total_profit: float = 0.0, win_rate: float = 0.0):
    dashboard_service.update_trading_metrics(positions_open, total_profit, win_rate)
