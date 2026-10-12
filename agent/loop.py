"""The auditor agent: a tool-use loop over an OpenAI-compatible chat-completions endpoint.

Configured entirely by environment variables:

    LLM_BASE_URL   default https://api.vultrinference.com/v1   (Vultr Serverless Inference)
    LLM_API_KEY    the Vultr Serverless Inference key (NEVER committed; owner pastes it into .env)
    LLM_MODEL      default llama-3.3-70b-instruct

If no key is set, a deterministic planner runs the SAME tools in a fixed, sensible order and writes a
templated plain-English verdict, so the demo works fully offline. Either way, only compact summaries
(metrics, counts, a few example rows) are ever sent to the LLM - never the uploaded files themselves.

The loop is a generator: it yields trace events (plan / tool_call / tool_result / message / done) so
the web UI can stream the agent thinking live.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Dict, Iterator, List, Optional

from .tools import TOOLS, AuditState

DEFAULT_BASE_URL = "https://api.vultrinference.com/v1"
DEFAULT_MODEL = "llama-3.3-70b-instruct"
MAX_ITERS = 10
MAX_TOKENS = 900

SYSTEM_PROMPT = """You are the BOTLAB Auditor, a careful quant risk reviewer. You audit a trading
strategy or a trade log and decide whether it is worth a small, monitored live test - or whether its
great-looking backtest is an illusion from look-ahead bias, overfitting, ignored costs, or luck.

You act ONLY by calling tools. The user's strategy code is executed for you inside a locked-down
sandbox (you never see or run it directly). Work in this order, adapting if a step reveals a problem:
1. inspect_inputs  2. run_strategy_in_sandbox (if a strategy was uploaded)  3. lookahead_audit
4. apply_costs  5. compute_stats  6. run_gates  7. write_report (your final plain-English verdict).

Key judgement:
- A sandbox block is a SAFETY WIN, not a failure. Note what was blocked and keep going.
- DSR (Deflated Sharpe) corrects the Sharpe for how many variants were tried. If PSR looks great but
  DSR is low, that is overfitting - say so plainly.
- Look-ahead mismatches mean the result is fiction, regardless of how good the numbers are.
- Be honest and concrete. A passing audit is a reason to forward-test small, never a promise of profit.
When you call write_report, put a 4-8 sentence verdict a non-quant can understand in 'verdict'."""

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "inspect_inputs", "description": "Summarise the uploaded strategy and/or trade log.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "run_strategy_in_sandbox",
        "description": "Execute the uploaded strategy inside the sandbox and get its signals/trades. "
                       "Reports any actions the sandbox blocked.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "lookahead_audit",
        "description": "Re-run the strategy on truncated history in the sandbox to detect look-ahead bias.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "apply_costs", "description": "Report the fee/slippage/funding drag on returns.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "compute_stats",
        "description": "Compute Sharpe, PSR, and the Deflated Sharpe Ratio (using number of trials).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "run_gates", "description": "Score the trades against the six readiness gates G1-G6.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "write_report",
        "description": "Write the final plain-English verdict. Call this last.",
        "parameters": {"type": "object",
                       "properties": {"verdict": {"type": "string",
                                                  "description": "4-8 sentence plain-English verdict"}},
                       "required": ["verdict"]}}},
]


def llm_configured() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


def _call_tool(name: str, state: AuditState, args: dict):
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    if name == "write_report":
        return fn(state, args.get("verdict", ""))
    return fn(state)


# --------------------------------------------------------------------------------- LLM transport
def _chat(messages: List[dict], tools: List[dict]) -> dict:
    base = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    key = os.environ.get("LLM_API_KEY", "")
    body = json.dumps({"model": model, "messages": messages, "tools": tools,
                       "tool_choice": "auto", "temperature": 0.2, "max_tokens": MAX_TOKENS}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def run_llm_agent(state: AuditState) -> Iterator[dict]:
    yield {"type": "plan", "text": f"LLM agent (model {os.environ.get('LLM_MODEL', DEFAULT_MODEL)} "
                                   "on Vultr Serverless Inference). Planning the audit..."}
    user = ("Audit this submission. "
            f"A strategy file was {'provided' if state.strategy_src else 'NOT provided'}; "
            f"a trade log was {'provided' if state.trade_csv else 'NOT provided'}; "
            f"the author says they tried {state.n_trials} variant(s). Begin.")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
    for _ in range(MAX_ITERS):
        try:
            resp = _chat(messages, TOOL_SCHEMAS)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            yield {"type": "message", "text": f"LLM endpoint unavailable ({e}); switching to the "
                                              "deterministic offline planner."}
            yield from run_offline_agent(state, _already_started=True)
            return
        msg = resp["choices"][0]["message"]
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            if msg.get("content"):
                yield {"type": "message", "text": msg["content"]}
            continue
        done = False
        for call in calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_call", "tool": name, "args": args}
            result = _call_tool(name, state, args)
            yield {"type": "tool_result", "tool": name, "result": result}
            messages.append({"role": "tool", "tool_call_id": call.get("id", name),
                             "content": json.dumps(result)[:4000]})
            if name == "write_report":
                yield {"type": "done", "report": result}
                done = True
        if done:
            return
    yield {"type": "message", "text": "Reached the iteration cap; finalising with the gate report."}
    yield from _finalize(state)


# ------------------------------------------------------------------------------ offline planner
def run_offline_agent(state: AuditState, _already_started: bool = False) -> Iterator[dict]:
    if not _already_started:
        yield {"type": "plan",
               "text": "Deterministic offline planner (no LLM key set). Running the standard audit: "
                       "inspect -> sandbox run -> look-ahead -> costs -> stats -> gates -> verdict."}
    order = ["inspect_inputs", "run_strategy_in_sandbox", "lookahead_audit",
             "apply_costs", "compute_stats", "run_gates"]
    if not state.strategy_src:
        order = ["inspect_inputs", "apply_costs", "compute_stats", "run_gates"]
    for name in order:
        yield {"type": "tool_call", "tool": name, "args": {}}
        result = _call_tool(name, state, {})
        yield {"type": "tool_result", "tool": name, "result": result}
    yield from _finalize(state)


def _finalize(state: AuditState) -> Iterator[dict]:
    verdict = _template_verdict(state)
    yield {"type": "tool_call", "tool": "write_report", "args": {"verdict": verdict}}
    result = TOOLS["write_report"](state, verdict)
    yield {"type": "tool_result", "tool": "write_report", "result": result}
    yield {"type": "done", "report": result}


def _template_verdict(state: AuditState) -> str:
    rep = state.report
    s = state.stats
    blocks = state.sandbox_events
    parts: List[str] = []
    if blocks:
        kinds = sorted({e.get("event", "") for e in blocks})
        parts.append(f"The uploaded code tried {len(blocks)} unsafe action(s) and the sandbox blocked "
                     f"every one ({', '.join(kinds)}); the host was never at risk and the audit "
                     "continued.")
    if state.lookahead and state.lookahead.get("mismatch", 0) > 0:
        parts.append(f"LOOK-AHEAD BIAS: the signal changed on {state.lookahead['mismatch']} of the "
                     f"{state.lookahead.get('n')} bars checked when future data was hidden, so the "
                     "backtest is not reproducible live and its numbers cannot be trusted.")
    if s:
        dsr_v = s.get("dsr")
        psr_v = s.get("psr0")
        if psr_v is not None and dsr_v is not None:
            if psr_v >= 0.95 and dsr_v < 0.5:
                parts.append(f"Overfitting: PSR looks strong ({psr_v:.2f}) but after deflating for the "
                             f"{s['n_trials']} variant(s) tried, the Deflated Sharpe is only "
                             f"{dsr_v:.2f} - most of the edge is explained by luck across trials.")
            else:
                parts.append(f"Significance: PSR(0)={psr_v:.2f}, DSR={dsr_v:.2f} after "
                             f"{s['n_trials']} trial(s); mean {s['mean_r']:+.3f}R over {s['n']} trades, "
                             f"win rate {s['win_rate']:.0f}%.")
    if rep is not None:
        if rep.status == "READY_FOR_MICRO_LIVE":
            parts.append("All six readiness gates pass. This is a reason to run a small, closely "
                         "monitored forward test - not a promise of profit.")
        elif rep.status == "WATCH":
            parts.append(f"Status WATCH: significance and recent performance hold, but these gates do "
                         f"not yet pass: {', '.join(rep.failed)}. Keep collecting trades before risking money.")
        else:
            parts.append(f"Status NOT_READY: failed gates {', '.join(rep.failed)}. Do not trade this live.")
    if not parts:
        parts.append("Not enough information to reach a verdict; check that a trade log or a working "
                     "strategy was provided.")
    return " ".join(parts)


def run_agent(state: AuditState) -> Iterator[dict]:
    if llm_configured():
        yield from run_llm_agent(state)
    else:
        yield from run_offline_agent(state)
