# The docker sandbox backend

`sandbox/__init__.py` picks a backend automatically: `docker` when the `docker` CLI is on PATH,
otherwise `local`. Override with `SANDBOX_BACKEND=docker` or `SANDBOX_BACKEND=local`.

## Build

From the repository root (the context must include `sandbox/runner.py`):

```bash
docker build -f sandbox/Dockerfile -t botlab-sandbox:latest .
```

The image name can be changed with `SANDBOX_IMAGE`.

## What the host does with it

For every audit step the host creates a throw-away directory with three sub-directories, copies the
uploaded `strategy.py` and the OHLCV CSVs into `input/`, and then runs:

```
docker run --rm --network none --read-only \
  --tmpfs /work:rw,size=64m,noexec,nosuid \
  --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 64 --memory 512m --cpus 1.0 \
  -v <input>:/input:ro -v <out>:/out \
  botlab-sandbox:latest --mode signals --input /input --work /work --out /out --timeout 20
```

so the image must not set its own entrypoint arguments beyond `runner.py`. It does not: the
`ENTRYPOINT` is `python /app/runner.py` and the host supplies every flag.

Two results come back through `/out`: `result.json` (signals, or the error that stopped the run) and
`events.jsonl` (one JSON line per refused action). Both files are created by the runner **before**
the untrusted module is loaded, so a strategy that crashes or is killed still leaves a record.

## Layers

| Layer | Enforced by | Covers |
|---|---|---|
| 1. audit hook | `runner.py` (PEP 578) | process launch, network, ctypes, interpreter introspection, writes outside the scratch directory - and logs each refusal with a human-readable reason |
| 2. container | the `docker run` flags above | the hook being bypassed at all: no network namespace, read-only root, no capabilities, non-root uid, pid / memory / CPU caps |
| 3. wall clock | watchdog thread in `runner.py` + host `subprocess` timeout | a strategy that never returns |

The audit hook is a tripwire with a readable explanation, not a security boundary. Layer 2 is the
boundary. Run the `local` backend only on a development machine.

## Verification status

The image definition in this repository has **not** been built or run on the development machine
used to write it, because Docker is not installed there; the `local` backend was used for all
testing. Build and run it on the Vultr VM (`deploy/install.sh` installs Docker and builds the
image) before trusting the docker path.
