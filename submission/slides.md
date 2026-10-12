---
title: "BOTLAB Auditor - Blast Radius Zero"
subtitle: "Vultr Agent Rush, November 2026"
---

# 1. BOTLAB Auditor

## An agent that runs a stranger's trading strategy, finds the lie in its backtest, and cannot be hurt by the code it runs.

- Vultr Cloud Compute VM + Vultr Serverless Inference
- MIT licensed - `github.com/botlabtrade/botlab-auditor`
- Challenge: **Blast Radius Zero: Safe Agent Execution on Vultr**

---

# 2. Two problems, one shape

**Almost every backtest is a lie - and the lie is boring.**

| The mistake | How it looks |
|---|---|
| Look-ahead | a signal reads a bar that had not closed |
| Overfitting | the best of 50 variants, shown as if it were the first |
| Ignored costs | returns quoted before fees, slippage, funding |
| Too few trades | 30 trades called evidence |

**To audit code, you must run it.** The reviewer's machine becomes the target.

> An agent that audits strategies *must* execute hostile input by design.
> That is Blast Radius Zero - in a place where containment has commercial value.

---

# 3. What the agent does

1. **Inspect** the upload - no execution
2. **Run it in the sandbox** - host never imports it; gets back `+1 / -1 / 0` per bar
3. **Replay honestly** - signal on bar *t*'s close fills at bar *t+1*'s **open**
4. **Hunt look-ahead** - re-run on truncated history, compare every signal
5. **Subtract costs** - fees, slippage, funding, before any statistic
6. **Deflate the Sharpe** - for the number of variants tried (PSR / DSR / MinTRL)
7. **Score six gates** -> plain-English verdict

**Look-ahead and containment veto the gate result.**

---

# 4. Four demos, four verdicts the tests pin

| Demo | Variants | Verdict |
|---|---|---|
| Honest trend-follower | 3 | `WATCH` - sound, not enough evidence yet |
| Overfit curve-fit | 50 | `NOT_READY` - Deflated Sharpe prices in the 50 trials |
| Look-ahead peeker | 50 | `REJECTED_LOOKAHEAD` |
| Malicious upload | 1 | `REJECTED_UNSAFE` - 12 blocked, 0 trades |

### The one that makes the point

The peeker **passed all six statistical gates**.
Gate status would have been `READY_FOR_MICRO_LIVE`.
The look-ahead veto is the only thing standing between it and real money.

---

# 5. Containment: three layers, honestly ranked

```
 host  ->  sandbox/__init__.py  ->  docker run  ->  runner.py + audit hook
                                 trust boundary
```

| Layer | Enforced by | Trusted? |
|---|---|---|
| 1. PEP 578 audit hook | `runner.py` - refuses shell, process, network, ctypes, writes outside scratch; logs every refusal with its reason | a **tripwire that explains itself**, not a boundary |
| 2. container | `--network none --read-only --user 65534 --cap-drop ALL --pids-limit 64 --memory 512m --cpus 1` | **this is the boundary** |
| 3. clock | watchdog `os._exit(7)` + host timeout + pid/memory caps | kills the infinite loop three ways |

**The design choice that beats all three:** the sandbox returns **data, not behaviour**.
Integers cross the boundary. The backtest runs on the host from those integers. No path back.

---

# 6. Vultr, end to end

- **Cloud Compute VM (Ubuntu 24.04)** - Caddy -> HTTPS on `<ip>.sslip.io` (no domain to buy) ->
  uvicorn/FastAPI on localhost as a systemd service -> Docker, one throw-away sandbox per audit step.
  `sudo bash deploy/install.sh` does all of it.
- **Serverless Inference** - the agent's reasoning: a tool-use loop against
  `api.vultrinference.com/v1`, `llama-3.3-70b-instruct`. The model sees **compact metrics only** -
  never the uploaded file.
- **Containment does not depend on the model behaving.** The tools decide what runs; the model only
  decides which tool to call next.
- **No key, still works** - a deterministic offline planner calls the same seven tools in the same
  order. Graceful degradation, and reproducible tests.

---

# 7. Business value

**Who pays for this**

- **Prop desks and funds** - a mandatory, mechanical pre-allocation review instead of a senior
  quant's afternoon
- **Copy-trading and strategy marketplaces** - vet a seller's strategy *and* their uploaded code,
  without trusting either
- **Bot vendors** (our own case) - every strategy must clear the gates before it sees a customer's
  capital
- **Anyone running an agent on third-party code** - the sandbox is the reusable part

**Why now:** agents that execute user-supplied code are shipping everywhere, and "we read it first"
does not scale. The reusable asset here is the containment pattern; trading is the setting where its
value is easiest to price.

---

# 8. Honest limitations - and the ask

**Limitations we state on the site, not in the footnotes**

- The audit hook is a tripwire; only the container is a boundary. Not a gVisor-grade claim.
- Demo data is synthetic - it demonstrates the method, not a market judgement.
- A statistical audit cannot prove a strategy works; it catches specific named failures.
  `WATCH` = "nothing caught, not enough evidence yet".
- Runs are in-memory; look-ahead detection is empirical; trade-log audits trust your R values.

**Built before:** `honest_backtest` (gates, PSR/DSR, look-ahead primitives) at
`github.com/botlabtrade/botlab-oss`, and the threshold research at `botlab.org.uk`.
**Built during:** the sandbox, the agent and its seven tools, the API and UI, the demos, the
installer, the tests.

> A passing audit is a reason to forward-test small. Never a promise of profit.
