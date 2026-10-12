# lablab.ai submission listing

## Title (60 characters max)

```
BOTLAB Auditor: Blast-Radius-Zero Trading Strategy Audit
```

(55 characters.)

Alternatives, both within the limit:

- `BOTLAB Auditor - audits hostile strategy code safely` (52)
- `Blast Radius Zero: the backtest auditor agent` (45)

## Short description (255 characters max)

```
An agent that runs a stranger's trading strategy, finds the lie in its backtest, and cannot be hurt by the code it runs. Look-ahead, overfitting and cost checks, with hostile uploads contained in a sandbox. Vultr VM + Vultr Serverless Inference. MIT.
```

(249 characters.)

## Long description

**The problem is two problems that turn out to be one.**

Almost every trading backtest is a lie, and the lie is boring: a signal that quietly reads a bar
that had not closed yet; the best of fifty variants presented as if it were the first; returns
quoted before fees, slippage and funding; thirty trades treated as evidence. Reviewing a strategy by
hand means reading the code, re-deriving the statistics, and remembering which of those four to
check. Most people skip at least two.

And to audit a strategy you have to run it - which means running a stranger's arbitrary code on your
machine. An agent that audits strategies is therefore an agent that must execute hostile input by
design. That is exactly the Blast Radius Zero problem, in a setting where containment has obvious
commercial value.

**What BOTLAB Auditor does.** Upload a strategy `.py` (a `signals(df)` function) and/or a trade-log
`.csv`, say how many variants you tried, and the agent inspects the upload without executing it;
runs the strategy inside a locked-down sandbox and gets back nothing but a list of `+1 / -1 / 0` per
bar; replays those signals on the host with honest execution rules (a signal computed on bar *t*'s
close fills at bar *t+1*'s **open**, never the same bar); hunts look-ahead bias by re-running the
strategy on truncated history and comparing every signal; subtracts fees, slippage and funding
before any statistic is computed; deflates the Sharpe ratio for the number of trials, which is how
"the best of 50 variants" stops looking like skill; scores six readiness gates; and writes a verdict
a non-quant can act on. Look-ahead and containment **veto** the gate result.

**Four demos on the front page, each with a verdict it is supposed to earn.** An honest EMA
trend-follower gets `WATCH` - nothing wrong, just not enough trades to risk money. An overfit
curve-fit (the best of 50 variants: EMA 20/80, only on Wednesdays and Saturdays at 19:00, held
exactly 36 bars) gets `NOT_READY` once the Deflated Sharpe prices in the 50 trials. A strategy that
peeks at next bar's close gets `REJECTED_LOOKAHEAD` - and this is the one that makes the point,
because it **passed all six statistical gates**. Its gate status would have been
`READY_FOR_MICRO_LIVE`. The look-ahead veto is the only thing between it and real money.

**And then the containment moment.** The fourth demo is not a strategy at all. It runs
`os.system("rm -rf /")`, spawns `curl`, opens a socket to an exfiltration host, plants a persistence
file outside its scratch directory, deletes the evidence, and then spins forever to burn the CPU.
The UI fills with twelve red rows - each naming the action and the rule that refused it - the
infinite loop is killed by the wall-clock watchdog, zero trades are produced, and the audit **does
not crash**: it treats containment as a finding, reports it, and still reaches a verdict of
`REJECTED_UNSAFE`.

**How containment works, ranked by how much we trust it.** Layer one is a PEP 578 audit hook inside
the runner process that refuses process spawning and shell calls, every networking entry point,
native code, interpreter introspection, a blocklist of imports, and any file write or delete outside
one scratch directory - logging each refusal with a human-readable reason. We call that a tripwire
that explains itself, not a security boundary. Layer two is the boundary: the runner executes in a
container with no network namespace, a read-only root filesystem, a 64 MB `noexec` tmpfs as the only
writable path, uid 65534, all capabilities dropped, `no-new-privileges`, 64 pids, 512 MB, one CPU.
Layer three is the clock - a watchdog thread, a host timeout and hard resource caps. The design
choice that matters more than all three: **the sandbox returns data, not behaviour.** Integers cross
the trust boundary; the backtest, the cost model and the statistics all run on the host from those
integers. There is no code path by which uploaded code influences the host beyond those numbers. The
result files are opened before untrusted code is loaded, so a strategy that crashes, OOMs or is
killed still leaves a complete record.

**How it uses Vultr.** A Vultr Cloud Compute VM (Ubuntu 24.04) runs everything: Caddy terminating
HTTPS on an `sslip.io` hostname derived from the VM's own IP, so no domain purchase is needed;
uvicorn/FastAPI on localhost as a systemd service; Docker running one throw-away sandbox container
per audit step. `sudo bash deploy/install.sh` sets all of that up in a single command, and the
deployment guide is written for a non-technical owner with every step as a literal command to paste.
Vultr Serverless Inference is the agent's reasoning: a tool-use loop against the OpenAI-compatible
endpoint with `llama-3.3-70b-instruct`, where the model picks the tools and writes the final verdict
but only ever sees compact summaries - counts, metrics, a couple of example rows - never the
uploaded file. Containment does not depend on the model behaving: the tools decide what runs, the
model only decides which tool to call next. With no key configured, a deterministic offline planner
calls the same seven tools in the same order, so the demo degrades gracefully and the test suite is
reproducible.

**Honest limitations, stated on the site rather than in a footnote.** The audit hook is a tripwire,
not a boundary - only the container is one, and it is only as good as the host kernel and Docker
configuration; this is not a gVisor-grade isolation claim. The local (no-Docker) backend has no
boundary at all and exists only so the project runs on a laptop. The demo data is synthetic: it
demonstrates the method, not a judgement about a real market. A statistical audit cannot prove a
strategy works, only catch specific named failures - `WATCH` means "nothing caught, not enough
evidence yet", and `READY_FOR_MICRO_LIVE` means "worth a small, closely monitored forward test",
never a promise of profit.

**Built before the hackathon:** `honest_backtest`, our open-source gate, cost and statistics library
(`github.com/botlabtrade/botlab-oss`), which supplies the six readiness gates, the cost model,
PSR / DSR / minimum-track-record statistics and the look-ahead primitives - plus the threshold
research published at `botlab.org.uk`. **Built during the hackathon:** everything in this
repository - the sandbox (runner, audit-hook policy, two backends, container image), the agent and
its seven audit tools, the host-side replay engine with next-bar-open fills, the FastAPI service and
its SSE trace stream, the single-page UI with the live sandbox-events panel, the four demo
strategies, the synthetic data generator, the Vultr installer and owner's guide, and the test suite
that pins all four demo verdicts.

MIT licensed. A passing audit is a reason to forward-test small - never a promise of profit.

## Tags

```
agent-safety, sandboxing, blast-radius-zero, vultr-serverless-inference, vultr,
fastapi, python, docker, algorithmic-trading, backtesting, quantitative-finance,
look-ahead-bias, overfitting, deflated-sharpe-ratio, risk-management,
untrusted-code-execution, server-sent-events, open-source, mit-license
```

## Links to provide on the submission form

| Field | Value |
|---|---|
| GitHub repository | `https://github.com/botlabtrade/botlab-auditor` |
| Public demo URL | the `https://<ip-with-dashes>.sslip.io` address printed by `deploy/install.sh` |
| Demo video | the recording made from `submission/video_script.md` (under 3 minutes) |
| Cover image | `submission/cover.png` (1280x720) |
| Licence | MIT (`LICENSE` in the repository root) |
| Challenge | Blast Radius Zero: Safe Agent Execution on Vultr |

## Judging-criteria crib sheet

- **Application of technology** - Vultr VM *and* Vultr Serverless Inference both load-bearing; a
  real two-layer sandbox with a data-only trust boundary; one-command deploy.
- **Presentation** - four demos with pre-stated expected verdicts, a live agent trace, and a
  containment moment you can watch happen in red.
- **Business value** - prop desks, copy-trading marketplaces, bot vendors; the containment pattern
  is reusable by anyone running an agent over third-party code.
- **Originality** - the veto design (a strategy that passes every statistical gate and is still
  rejected) and treating containment events as audit findings rather than as crashes.
