"""BOTLAB Auditor - web front end.

A thin, stateless-ish HTTP layer over ``agent.loop.run_agent``. It does three things:

* takes an upload (a strategy ``.py`` and/or a trade-log ``.csv``) and starts one audit run;
* streams the agent's trace back to the browser with Server-Sent Events;
* serves the single-page UI and the four demo strategies.

Deliberate non-features: no auth, no cookies, no database, no logging of file contents. Uploads are
capped, runs live in memory with a hard cap, and the uploaded code is only ever executed inside the
sandbox (see ``sandbox/``), never in this process.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from collections import OrderedDict
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent.loop import llm_configured, run_agent
from agent.tools import AuditState

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
STATIC = os.path.join(HERE, "static")
DEMO_DIR = os.path.join(REPO, "demos")

MAX_UPLOAD_BYTES = 256 * 1024          # 256 KB per file: an audit reads code, not data dumps
MAX_RUNS = 40                          # in-memory runs; oldest evicted first
MAX_TRIALS = 100000
POLL_SECONDS = 0.25
STREAM_IDLE_LIMIT = 600                # ~150 s of no new events before the stream gives up

DEMOS = {
    "honest": {
        "file": "honest_strategy.py",
        "title": "Honest trend-follower",
        "blurb": "EMA 12/96 crossover with a 0.2 % band. Past bars only, one parameter set, "
                 "tried once. Expected verdict: WATCH (sound, but not enough trades yet).",
        "n_trials": 3,
        "expected": "WATCH",
    },
    "overfit": {
        "file": "overfit_strategy.py",
        "title": "Overfit curve-fit",
        "blurb": "The best of 50 variants: EMA 20/80, but only on Wednesdays and Saturdays at "
                 "19:00, held exactly 36 bars. Expected verdict: NOT_READY (Deflated Sharpe "
                 "exposes the 50 trials).",
        "n_trials": 50,
        "expected": "NOT_READY",
    },
    "lookahead": {
        "file": "lookahead_strategy.py",
        "title": "Look-ahead peeker",
        "blurb": "Trades on next bar's close via shift(-1). Passes every statistical gate and is "
                 "still worthless. Expected verdict: REJECTED_LOOKAHEAD.",
        "n_trials": 50,
        "expected": "REJECTED_LOOKAHEAD",
    },
    "malicious": {
        "file": "malicious_strategy.py",
        "title": "Malicious upload",
        "blurb": "Not a strategy at all: it tries to run a shell command, spawn a process, open a "
                 "socket, plant and delete files outside its scratch directory, then spin forever. "
                 "Expected verdict: REJECTED_UNSAFE, every action blocked, zero trades.",
        "n_trials": 1,
        "expected": "REJECTED_UNSAFE",
    },
}

app = FastAPI(title="BOTLAB Auditor", docs_url=None, redoc_url=None, openapi_url=None)

_runs: "OrderedDict[str, dict]" = OrderedDict()
_lock = threading.Lock()


# --------------------------------------------------------------------------------- run bookkeeping
def _new_run(state: AuditState) -> str:
    run_id = uuid.uuid4().hex[:16]
    rec = {"id": run_id, "state": state, "events": [], "done": False, "error": None}
    with _lock:
        _runs[run_id] = rec
        while len(_runs) > MAX_RUNS:
            _runs.popitem(last=False)
    threading.Thread(target=_drive, args=(rec,), daemon=True).start()
    return run_id


def _drive(rec: dict) -> None:
    """Consume the agent generator on a worker thread, appending every event to the run record."""
    try:
        for ev in run_agent(rec["state"]):
            rec["events"].append(ev)
    except Exception as exc:                        # never leak a traceback or file contents
        rec["error"] = type(exc).__name__
        rec["events"].append({"type": "message",
                              "text": f"The audit stopped unexpectedly ({type(exc).__name__})."})
        rec["events"].append({"type": "done", "report": {
            "ok": False, "status": "ERROR", "gate_status": "UNKNOWN",
            "verdict": "The audit could not be completed. Please check the uploaded files.",
            "gate_report": "", "override_reason": None, "sandbox_blocked_events": 0}})
    finally:
        rec["done"] = True


async def _read_capped(upload: Optional[UploadFile], label: str) -> Optional[str]:
    if upload is None or not upload.filename:
        return None
    raw = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"{label} is larger than {MAX_UPLOAD_BYTES // 1024} KB")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail=f"{label} must be UTF-8 text")


# ----------------------------------------------------------------------------------------- routes
@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/health")
def health() -> dict:
    from sandbox import default_backend
    return {"ok": True, "sandbox_backend": default_backend(),
            "inference": "vultr-serverless" if llm_configured() else "offline-planner",
            "demos": list(DEMOS)}


@app.get("/api/demo/{name}")
def demo(name: str) -> dict:
    meta = DEMOS.get(name)
    if meta is None:
        raise HTTPException(status_code=404, detail="unknown demo")
    with open(os.path.join(DEMO_DIR, meta["file"]), "r", encoding="utf-8") as f:
        source = f.read()
    return {"name": name, "filename": meta["file"], "title": meta["title"],
            "blurb": meta["blurb"], "n_trials": meta["n_trials"],
            "expected": meta["expected"], "source": source}


@app.post("/api/audit")
async def audit(strategy: UploadFile = File(None), trade_log: UploadFile = File(None),
                demo_name: str = Form(None), n_trials: int = Form(1)) -> JSONResponse:
    strategy_src = await _read_capped(strategy, "The strategy file")
    trade_csv = await _read_capped(trade_log, "The trade log")

    if strategy_src is None and demo_name:
        meta = DEMOS.get(demo_name)
        if meta is None:
            raise HTTPException(status_code=404, detail="unknown demo")
        with open(os.path.join(DEMO_DIR, meta["file"]), "r", encoding="utf-8") as f:
            strategy_src = f.read()

    if strategy_src is None and trade_csv is None:
        raise HTTPException(status_code=400,
                            detail="upload a strategy .py file, a trade-log .csv, or pick a demo")
    try:
        trials = max(1, min(int(n_trials), MAX_TRIALS))
    except (TypeError, ValueError):
        trials = 1

    run_id = _new_run(AuditState(strategy_src, trade_csv, trials))
    return JSONResponse({"id": run_id, "stream": f"/api/audit/{run_id}/stream",
                         "n_trials": trials,
                         "inference": "vultr-serverless" if llm_configured() else "offline-planner"})


@app.get("/api/audit/{run_id}/stream")
async def stream(run_id: str) -> StreamingResponse:
    rec = _runs.get(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="unknown run id")

    async def gen():
        sent, idle = 0, 0
        yield "retry: 5000\n\n"
        while True:
            events = rec["events"]
            if sent < len(events):
                idle = 0
                while sent < len(events):
                    ev = events[sent]
                    sent += 1
                    yield f"data: {json.dumps(ev)}\n\n"
                    if ev.get("type") == "done":
                        return
            else:
                if rec["done"]:
                    yield "data: " + json.dumps({"type": "done", "report": None}) + "\n\n"
                    return
                idle += 1
                if idle > STREAM_IDLE_LIMIT:
                    yield "data: " + json.dumps(
                        {"type": "message", "text": "The audit timed out."}) + "\n\n"
                    yield "data: " + json.dumps({"type": "done", "report": None}) + "\n\n"
                    return
                yield ": keep-alive\n\n"
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
