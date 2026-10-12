"""Sandbox interface: one function, two interchangeable backends.

``run_in_sandbox(strategy_src, data_dir, mode)`` executes untrusted strategy code in isolation and
returns ``(result_dict, events_list)``. The strategy code is never imported into the host process.

Backend is chosen by the ``SANDBOX_BACKEND`` env var (``local`` or ``docker``); it defaults to
``docker`` when the docker CLI is on PATH, otherwise ``local`` (the Windows/dev fallback).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "runner.py")
DOCKER_IMAGE = os.environ.get("SANDBOX_IMAGE", "botlab-sandbox:latest")
TIMEOUT = float(os.environ.get("SANDBOX_TIMEOUT", "20"))


def default_backend() -> str:
    env = os.environ.get("SANDBOX_BACKEND")
    if env:
        return env
    return "docker" if shutil.which("docker") else "local"


def run_in_sandbox(strategy_src: str, data_dir: str, mode: str = "signals",
                   backend: str | None = None) -> Tuple[dict, List[dict]]:
    backend = backend or default_backend()
    root = tempfile.mkdtemp(prefix=f"sbx_{uuid.uuid4().hex[:8]}_")
    in_dir, work_dir, out_dir = (os.path.join(root, d) for d in ("input", "work", "out"))
    for d in (in_dir, work_dir, out_dir):
        os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(in_dir, "ohlcv"), exist_ok=True)
    with open(os.path.join(in_dir, "strategy.py"), "w", encoding="utf-8") as f:
        f.write(strategy_src)
    for name in os.listdir(data_dir):
        if name.endswith(".csv"):
            shutil.copy(os.path.join(data_dir, name), os.path.join(in_dir, "ohlcv", name))

    try:
        if backend == "docker":
            _run_docker(in_dir, work_dir, out_dir, mode)
        else:
            _run_local(in_dir, work_dir, out_dir, mode)
        result = _read_json(os.path.join(out_dir, "result.json"))
        events = _read_jsonl(os.path.join(out_dir, "events.jsonl"))
        result["backend"] = backend
        return result, events
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _honest_backtest_root() -> str:
    """Directory that contains the honest_backtest package, so a clean subprocess can import it
    even when it is only installed in the user site (which -I/-s would hide)."""
    try:
        import honest_backtest
        return os.path.dirname(os.path.dirname(os.path.abspath(honest_backtest.__file__)))
    except Exception:
        return REPO


def _run_local(in_dir: str, work_dir: str, out_dir: str, mode: str) -> None:
    # Local/dev fallback: the audit hook inside the runner is the containment layer here, so we do
    # NOT use -I (it would hide a user-site editable install of honest_backtest). We still launch a
    # separate process with a minimal environment so the strategy never touches the host interpreter.
    cmd = [sys.executable, RUNNER, "--mode", mode, "--input", in_dir,
           "--work", work_dir, "--out", out_dir, "--timeout", str(TIMEOUT)]
    env = {k: v for k, v in os.environ.items()
           if k in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP",
                    "SANDBOX_MEM_MB", "SANDBOX_MAX_BARS", "SANDBOX_TIMEOUT")}
    env["PYTHONPATH"] = os.pathsep.join([_honest_backtest_root(), REPO])
    try:
        p = subprocess.run(cmd, timeout=TIMEOUT + 15, capture_output=True, env=env, cwd=work_dir)
        if p.returncode == 7:                      # watchdog wall-clock kill inside the runner
            _ensure_timeout_result(out_dir)
    except subprocess.TimeoutExpired:
        _ensure_timeout_result(out_dir)
    if not os.path.exists(os.path.join(out_dir, "result.json")):
        _ensure_timeout_result(out_dir)


def _run_docker(in_dir: str, work_dir: str, out_dir: str, mode: str) -> None:
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--tmpfs", "/work:rw,size=64m,noexec,nosuid",
        "--user", "65534:65534",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "64",
        "--memory", os.environ.get("SANDBOX_MEM_MB", "512") + "m",
        "--cpus", os.environ.get("SANDBOX_CPUS", "1.0"),
        "-v", f"{in_dir}:/input:ro",
        "-v", f"{out_dir}:/out",
        DOCKER_IMAGE,
        "--mode", mode, "--input", "/input", "--work", "/work", "--out", "/out",
        "--timeout", str(TIMEOUT),
    ]
    try:
        p = subprocess.run(cmd, timeout=TIMEOUT + 25, capture_output=True)
        if p.returncode in (7, 137, 139):          # watchdog kill / OOM-kill / SIGSEGV
            _ensure_timeout_result(out_dir)
    except subprocess.TimeoutExpired:
        _ensure_timeout_result(out_dir)
    if not os.path.exists(os.path.join(out_dir, "result.json")):
        _ensure_timeout_result(out_dir)


def _ensure_timeout_result(out_dir: str) -> None:
    rp = os.path.join(out_dir, "result.json")
    if not os.path.exists(rp):
        with open(rp, "w", encoding="utf-8") as f:
            json.dump({"ok": False, "error": "timeout",
                       "message": "strategy exceeded the wall-clock limit and was killed",
                       "blocked_events": 0}, f)
    ep = os.path.join(out_dir, "events.jsonl")
    with open(ep, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": 0, "event": "wall_clock_timeout",
                            "detail": "strategy ran too long and was killed by the sandbox",
                            "action": "blocked"}) + "\n")


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {"ok": False, "error": "no_result", "message": "sandbox produced no result",
                "blocked_events": 0}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out
