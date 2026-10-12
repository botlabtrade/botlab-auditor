"""Sandbox runner: the ONLY place where uploaded strategy code is executed.

It runs as a separate, throw-away Python process (inside a locked-down Docker container in
production, or a plain subprocess in local/dev mode) and is deliberately standalone: stdlib +
pandas + numpy + honest_backtest, no imports from the rest of this repository.

    python runner.py --mode signals|lookahead --input IN --work WORK --out OUT

* IN   (read-only)  strategy.py and ohlcv/*.csv supplied by the host
* WORK (scratch)    the only directory the strategy may write to
* OUT  (host-owned) result.json + events.jsonl, opened BEFORE untrusted code is loaded

Layer 1 of containment lives here: a Python audit hook (PEP 578) that refuses process spawning,
network access, native code (ctypes), heap introspection and any file write/delete outside WORK,
and records every refusal as a JSON line. Audit hooks are a tripwire, not a security boundary, so
in production layer 2 (the Docker container: no network, read-only root, no capabilities, pid /
memory / CPU limits, wall-clock kill) is what actually holds. See the README for the full picture.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import threading
import time
import traceback

import numpy as np          # noqa: F401  (imported before the hook so its lazy loads are trusted)
import pandas as pd
from honest_backtest.lookahead import lookahead_analysis, sample_indices

MAX_STDOUT = 4000

PROCESS_EVENTS = {
    "os.system", "subprocess.Popen", "os.exec", "os.spawn", "os.posix_spawn", "os.fork",
    "os.forkpty", "os.startfile", "os.kill", "os.killpg", "pty.spawn",
    "_winapi.CreateNamedPipe", "_winapi.CreateFile", "_winapi.OpenProcess", "_winapi.TerminateProcess",
}
NETWORK_PREFIXES = ("socket.", "urllib.Request", "http.client.", "ftplib.", "smtplib.", "poplib.",
                    "imaplib.", "telnetlib.", "webbrowser.")
NATIVE_PREFIXES = ("ctypes.", "cffi.")
INTROSPECTION_EVENTS = {"gc.get_objects", "gc.get_referrers", "gc.get_referents",
                        "object.__delattr__", "sys.remote_exec"}
BLOCKED_IMPORTS = {"ctypes", "_ctypes", "cffi", "_posixsubprocess", "_winapi", "multiprocessing",
                   "_multiprocessing", "mmap", "pty"}
FS_MUTATE = {"os.remove", "os.rmdir", "os.rename", "os.replace", "os.mkdir", "os.makedirs",
             "os.chmod", "os.chown", "os.link", "os.symlink", "os.truncate", "os.utime",
             "os.setxattr", "os.removexattr", "os.unlink", "shutil.copyfile"}


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


class Sandbox:
    """Holds the policy and the event log. One instance is installed as a sys audit hook."""

    def __init__(self, work: str, events_fh, allowed_read):
        self.work = _norm(work)
        self.events_fh = events_fh
        self.allowed_read = [_norm(p) for p in allowed_read if p]
        self.local = threading.local()
        self.active = False
        self.count = 0

    def log(self, event: str, detail: str) -> None:
        self.count += 1
        rec = dict(ts=round(time.time(), 3), event=event, detail=str(detail)[:300], action="blocked")
        self.events_fh.write(json.dumps(rec) + "\n")
        self.events_fh.flush()

    def _inside_work(self, path) -> bool:
        try:
            p = _norm(os.fspath(path))
        except Exception:
            return False
        return p == self.work or p.startswith(self.work + os.sep)

    def _write_mode(self, mode) -> bool:
        return isinstance(mode, str) and any(c in mode for c in ("w", "a", "x", "+"))

    def hook(self, event: str, args) -> None:
        # Never police our own machinery or anything before the strategy is loaded.
        if not self.active or getattr(self.local, "trusted", False):
            return
        try:
            self._check(event, args)
        except PermissionError:
            raise
        except Exception:
            return

    def _check(self, event: str, args) -> None:
        if event in PROCESS_EVENTS:
            self._deny(event, "tried to start a process / run a shell command", args)
        if event.startswith(NETWORK_PREFIXES):
            self._deny(event, "tried to use the network", args)
        if event.startswith(NATIVE_PREFIXES):
            self._deny(event, "tried to load native code (ctypes/cffi)", args)
        if event in INTROSPECTION_EVENTS:
            self._deny(event, "tried to introspect/modify the interpreter", args)
        if event == "import" and args and args[0] in BLOCKED_IMPORTS:
            self._deny(event, f"tried to import a blocked module: {args[0]}", args)
        if event in FS_MUTATE:
            target = args[0] if args else None
            if not self._inside_work(target):
                self._deny(event, f"tried to modify the filesystem outside the sandbox: {target}", args)
        if event == "open" and len(args) >= 2 and self._write_mode(args[1]):
            if not self._inside_work(args[0]):
                self._deny(event, f"tried to write a file outside the sandbox: {args[0]}", args)

    def _deny(self, event: str, why: str, args) -> None:
        detail = why
        try:
            if args:
                detail = f"{why} [{args[0]!r}]"
        except Exception:
            pass
        self.log(event, detail)
        raise PermissionError(f"sandbox blocked {event}: {why}")


def _run_trusted(sb: Sandbox, fn, *a, **k):
    sb.local.trusted = True
    try:
        return fn(*a, **k)
    finally:
        sb.local.trusted = False


def load_strategy(sb: Sandbox, path: str):
    """Import the strategy module under the audit hook and return its ``signals`` callable."""
    import importlib.util
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    spec = importlib.util.spec_from_loader("user_strategy", loader=None)
    mod = importlib.util.module_from_spec(spec)
    code = compile(src, "user_strategy.py", "exec")
    exec(code, mod.__dict__)                       # module top-level runs here, under the hook
    fn = getattr(mod, "signals", None)
    if not callable(fn):
        raise ValueError("strategy file must define signals(df) -> pandas.Series of +1/-1/0")
    return fn


def coerce_signals(raw, n: int):
    s = pd.Series(raw)
    if len(s) != n:
        raise ValueError(f"signals returned {len(s)} values for {n} bars")
    s = pd.to_numeric(s, errors="coerce").fillna(0.0)
    s = np.sign(np.clip(s, -1, 1)).astype(int)     # force into {-1, 0, +1}
    return s.tolist()


def watchdog(seconds: float):
    """Hard wall-clock kill: the infinite-loop demo cannot outlive this."""
    def _kill():
        time.sleep(seconds)
        os.write(2, b"sandbox: wall-clock timeout, killing strategy\n")
        os._exit(7)
    t = threading.Thread(target=_kill, daemon=True)
    t.start()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("signals", "lookahead"), default="signals")
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=float(os.environ.get("SANDBOX_TIMEOUT", "20")))
    ap.add_argument("--max-bars", type=int, default=int(os.environ.get("SANDBOX_MAX_BARS", "20000")))
    a = ap.parse_args()

    os.makedirs(a.work, exist_ok=True)
    events_path = os.path.join(a.out, "events.jsonl")
    result_path = os.path.join(a.out, "result.json")
    events_fh = open(events_path, "w", encoding="utf-8")
    strategy_path = os.path.join(a.input, "strategy.py")
    data_dir = os.path.join(a.input, "ohlcv")

    sb = Sandbox(a.work, events_fh, allowed_read=[a.input, a.work])
    sys.addaudithook(sb.hook)

    # Try to cap memory/CPU on POSIX (Docker enforces this for real; best-effort elsewhere).
    try:
        import resource
        mem = int(os.environ.get("SANDBOX_MEM_MB", "512")) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (int(a.timeout) + 2, int(a.timeout) + 2))
    except Exception:
        pass

    watchdog(a.timeout)
    result = {"mode": a.mode, "ok": False, "blocked_events": 0}
    try:
        frames = {}
        for p in sorted(glob.glob(os.path.join(data_dir, "*.csv"))):
            frames[os.path.splitext(os.path.basename(p))[0]] = pd.read_csv(p)
        if not frames:
            raise FileNotFoundError("no OHLCV data provided to the sandbox")

        sb.active = True
        fn = load_strategy(sb, strategy_path)

        if a.mode == "lookahead":
            sym, df = next(iter(frames.items()))
            if len(df) > a.max_bars:
                df = df.iloc[: a.max_bars].reset_index(drop=True)
            idx = _run_trusted(sb, sample_indices, 200, len(df), 25, 11)

            def wrapped(d):
                return fn(d.reset_index(drop=True))
            la = lookahead_analysis(wrapped, df, idx)
            result.update(ok=True, symbol=sym, lookahead=la)
        else:
            out = {}
            for sym, df in frames.items():
                if len(df) > a.max_bars:
                    df = df.iloc[: a.max_bars].reset_index(drop=True)
                raw = fn(df)
                out[sym] = coerce_signals(raw, len(df))
            result.update(ok=True, signals=out)
    except PermissionError as e:
        result.update(ok=False, error="sandbox_block", message=str(e))
    except SystemExit:
        raise
    except BaseException as e:                      # strategy crashed, bad signals, OOM, etc.
        result.update(ok=False, error=type(e).__name__,
                      message=str(e)[:500], trace=traceback.format_exc()[-MAX_STDOUT:])
    finally:
        sb.active = False
        result["blocked_events"] = sb.count
        events_fh.close()
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
