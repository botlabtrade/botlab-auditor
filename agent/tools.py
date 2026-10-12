"""The audit tools the agent can call. Each is a small, pure-ish function over the audit state.

The tools never send anything to the network. ``run_strategy_in_sandbox`` is the only tool that
executes untrusted code, and it does so through the sandbox interface, never in this process.
Only compact summaries (counts, metrics, a few example rows) ever leave a tool - never whole files.
"""
from __future__ import annotations

import io
import math
from typing import Any, Dict, List, Optional

import pandas as pd
from honest_backtest import CostModel, GateConfig, Trade, evaluate, format_report
from honest_backtest.stats import dsr, min_track_record_dsr, psr

from . import engine
from .engine import DATA_DIR
from sandbox import run_in_sandbox


class AuditState:
    """Everything the tools read and write during one audit."""

    def __init__(self, strategy_src: Optional[str], trade_csv: Optional[str], n_trials: int):
        self.strategy_src = strategy_src
        self.trade_csv = trade_csv
        self.n_trials = max(int(n_trials), 1)
        self.data_dir = DATA_DIR
        self.sandbox_events: List[dict] = []
        self.trades: List[engine.SimTrade] = []     # from the sandboxed strategy
        self.csv_trades: List[Trade] = []           # from an uploaded trade log
        self.lookahead: Optional[dict] = None
        self.stats: Dict[str, Any] = {}
        self.report = None
        self.source = None                          # "strategy" or "trade_log"

    def gate_trades(self) -> List[Trade]:
        if self.source == "strategy":
            return [Trade(t.net_r, t.symbol, t.side, t.exit_time) for t in self.trades]
        return self.csv_trades


# ---------------------------------------------------------------------------- tool implementations
def inspect_inputs(state: AuditState) -> dict:
    out = {"has_strategy": bool(state.strategy_src), "has_trade_log": bool(state.trade_csv),
           "n_trials": state.n_trials}
    if state.strategy_src:
        src = state.strategy_src
        out["strategy_lines"] = src.count("\n") + 1
        out["defines_signals"] = "def signals(" in src
        flags = []
        for pat, msg in (("shift(-", "uses shift(-k): possible look-ahead"),
                         ("os.system", "calls os.system"), ("subprocess", "imports/uses subprocess"),
                         ("socket", "uses socket"), ("eval(", "uses eval"),
                         ("exec(", "uses exec"), ("open(", "opens files")):
            if pat in src:
                flags.append(msg)
        out["static_flags"] = flags
    if state.trade_csv:
        try:
            df = pd.read_csv(io.StringIO(state.trade_csv))
            out["trade_log_rows"] = int(len(df))
            out["trade_log_columns"] = [str(c) for c in df.columns][:12]
        except Exception as e:
            out["trade_log_error"] = str(e)[:200]
    return out


def run_strategy_in_sandbox(state: AuditState) -> dict:
    if not state.strategy_src:
        return {"ran": False, "reason": "no strategy file uploaded"}
    result, events = run_in_sandbox(state.strategy_src, state.data_dir, mode="signals")
    state.sandbox_events += events
    summary = {"ran": result.get("ok", False), "backend": result.get("backend"),
               "blocked_events": result.get("blocked_events", len(events)),
               "blocked": [{"event": e.get("event"), "detail": e.get("detail")} for e in events]}
    if not result.get("ok"):
        summary.update(contained=bool(events) or result.get("error") in ("timeout", "sandbox_block"),
                       error=result.get("error"), message=result.get("message"))
        return summary
    # Replay the sandbox's signals into trades on the host (strategy code does NOT run here).
    data = engine.load_ohlcv(state.data_dir)
    trades: List[engine.SimTrade] = []
    for sym, sig in result.get("signals", {}).items():
        if sym in data:
            trades += engine.signals_to_trades(data[sym], sig, sym)
    engine.apply_costs(trades)
    state.trades = trades
    state.source = "strategy"
    gross = [t.gross_r for t in trades]
    summary.update(n_trades=len(trades), symbols=len(result.get("signals", {})),
                   mean_gross_r=round(sum(gross) / len(gross), 4) if gross else None)
    return summary


def lookahead_audit(state: AuditState) -> dict:
    if not state.strategy_src:
        return {"checked": False, "reason": "no strategy file to audit"}
    result, events = run_in_sandbox(state.strategy_src, state.data_dir, mode="lookahead")
    state.sandbox_events += events
    if not result.get("ok"):
        return {"checked": False, "contained": bool(events), "error": result.get("error"),
                "message": result.get("message"), "blocked_events": result.get("blocked_events", 0)}
    la = result.get("lookahead", {})
    state.lookahead = la
    mism = la.get("mismatch", 0)
    ex = la.get("examples", [])[:2]
    return {"checked": True, "bars_sampled": la.get("n"), "mismatches": mism,
            "has_lookahead": mism > 0,
            "verdict": ("LOOK-AHEAD DETECTED: the signal changes when future bars are hidden"
                        if mism > 0 else "clean: signal is identical on truncated history"),
            "examples": [{"bar": e.get("i"), "full": e.get("full"), "truncated": e.get("incremental")}
                         for e in ex]}


def _load_csv_trades(state: AuditState) -> None:
    if state.csv_trades or not state.trade_csv:
        return
    import csv as _csv
    from honest_backtest.loaders import _pick, _float
    rows = list(_csv.DictReader(io.StringIO(state.trade_csv)))
    cm = CostModel()
    out: List[Trade] = []
    for row in rows:
        r = _float(_pick(row, "r"))
        side = _pick(row, "side")
        if r is None:
            e, x, s = (_float(_pick(row, k)) for k in ("entry", "exit", "stop"))
            if None in (e, x, s) or not side:
                continue
            r = cm.r_multiple(side, e, x, s, _float(_pick(row, "hold_hours")))
            if r is None:
                continue
        out.append(Trade(r=r, symbol=_pick(row, "symbol"), side=(side or "").lower() or None,
                         closed=_pick(row, "closed")))
    state.csv_trades = out


def compute_stats(state: AuditState) -> dict:
    if state.source != "strategy" and state.trade_csv:
        _load_csv_trades(state)
        state.source = "trade_log"
    rs = [t.r for t in state.gate_trades()]
    if len(rs) < 2:
        return {"ok": False, "reason": "need at least 2 trades to compute statistics"}
    p0 = psr(rs, 0.0)
    d, sr0 = dsr(rs, state.n_trials)
    sr = (sum(rs) / len(rs)) / (pd.Series(rs).std(ddof=1) or float("nan"))
    mtrl = min_track_record_dsr(sr, state.n_trials)
    state.stats = {"n": len(rs), "mean_r": round(sum(rs) / len(rs), 4),
                   "win_rate": round(sum(1 for x in rs if x > 0) / len(rs) * 100, 1),
                   "sharpe_per_trade": round(sr, 4),
                   "psr0": round(p0, 4) if p0 is not None else None,
                   "dsr": round(d, 4) if d is not None else None,
                   "sr0_luck": round(sr0, 4) if sr0 is not None else None,
                   "n_trials": state.n_trials,
                   "min_trl_dsr": None if not math.isfinite(mtrl) else int(math.ceil(mtrl))}
    return {"ok": True, **state.stats}


def apply_costs(state: AuditState) -> dict:
    cm = CostModel()
    if state.source == "strategy":
        gross = [t.gross_r for t in state.trades]
        net = [t.net_r for t in state.trades]
        if not gross:
            return {"ok": False, "reason": "no trades"}
        g, n = sum(gross) / len(gross), sum(x for x in net if x is not None) / len(net)
        return {"ok": True, "applied": True, "model": vars(cm),
                "mean_gross_r": round(g, 4), "mean_net_r": round(n, 4),
                "cost_drag_r": round(g - n, 4),
                "note": "fees + slippage + funding already subtracted from every R used in the gates"}
    return {"ok": True, "applied": False,
            "note": "trade log supplied R directly; assuming it is already net of costs (verify this!)",
            "model": vars(cm)}


def run_gates(state: AuditState) -> dict:
    trades = state.gate_trades()
    if len(trades) < 2:
        return {"ok": False, "reason": "need at least 2 trades"}
    rep = evaluate(trades, n_trials=state.n_trials, config=GateConfig())
    state.report = rep
    gates = {g: {"pass": rep.gates[g].ok, "why": rep.gates[g].why} for g in rep.gates}
    return {"ok": True, "status": rep.status, "failed": rep.failed, "gates": gates,
            "n": rep.n, "mean_r": round(rep.mean_r, 4) if rep.mean_r is not None else None}


def overall_status(state: AuditState) -> tuple:
    """The headline verdict. Gates alone are not enough: a strategy that peeks at future bars can
    pass every statistical gate, so look-ahead and containment veto the gate result."""
    gate_status = state.report.status if state.report is not None else "UNKNOWN"
    la = state.lookahead or {}
    if la.get("mismatch", 0) > 0:
        return ("REJECTED_LOOKAHEAD",
                "the signal changes when future bars are hidden, so the backtest is not reproducible")
    if state.strategy_src and not state.trades and state.sandbox_events:
        return ("REJECTED_UNSAFE",
                "the uploaded code was contained before it produced any result")
    return (gate_status, None)


def write_report(state: AuditState, verdict_text: str) -> dict:
    rep = state.report
    text = format_report(rep) if rep is not None else "no gate report available"
    status, override = overall_status(state)
    return {"ok": True, "verdict": verdict_text, "gate_report": text,
            "status": status, "gate_status": rep.status if rep else "UNKNOWN",
            "override_reason": override,
            "sandbox_blocked_events": len(state.sandbox_events)}


TOOLS = {
    "inspect_inputs": inspect_inputs,
    "run_strategy_in_sandbox": run_strategy_in_sandbox,
    "lookahead_audit": lookahead_audit,
    "compute_stats": compute_stats,
    "apply_costs": apply_costs,
    "run_gates": run_gates,
    "write_report": write_report,
}
