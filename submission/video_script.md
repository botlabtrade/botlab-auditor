# Demo video script - BOTLAB Auditor

**Target length: 2 min 50 s (hard cap 3 min).** Screen recording of the live site, one voice-over,
no music under the narration. Record at 1920x1080, 30 fps. Mouse movements slow and deliberate.

Record the browser at ~90 % zoom so the verdict card and the Sandbox events panel are both visible
without scrolling.

---

## Scene 1 - The claim (0:00-0:20)

**Screen:** the site's hero section, then the upload card. Nothing clicked yet.

**Voice-over:**
> Every trading backtest looks good. That is what a backtest is for. This agent runs a stranger's
> strategy, finds the lie in its numbers, and cannot be hurt by the code it runs. It is on a Vultr
> VM, and it thinks with Vultr Serverless Inference.

**On-screen text (lower third):** `BOTLAB Auditor - Blast Radius Zero`

---

## Scene 2 - An honest strategy (0:20-0:50)

**Screen:** click the **Honest trend-follower** demo button; the source appears. Set variants to 3
(it auto-fills). Click **Run the audit**. The agent trace fills in live.

**Voice-over:**
> Start with an honest one. EMA crossover, past bars only, one parameter set. Watch the trace: the
> agent plans, runs the code in a sandbox, re-runs it on truncated history to check for look-ahead,
> subtracts fees and slippage, deflates the Sharpe ratio, scores six readiness gates.

**Screen:** verdict card lands on **WATCH**.

**Voice-over:**
> Verdict: WATCH. Nothing wrong - just not enough trades yet to risk money. An auditor that only
> ever says no is useless.

---

## Scene 3 - The expensive lie (0:50-1:25)

**Screen:** click **Look-ahead peeker**. Pause one second on the source so `shift(-1)` is readable;
zoom in on that line if the editor allows. Run the audit.

**Voice-over:**
> Now the expensive mistake. This one reads next bar's close. One character of code, and a backtest
> that prints money.

**Screen:** the trace reaches `lookahead_audit`; the result shows mismatches. The verdict card
lands on **REJECTED_LOOKAHEAD**, with the line *"gate status would have been
READY_FOR_MICRO_LIVE"* visible.

**Voice-over:**
> And here is why this matters. It passed every statistical gate. Sharpe, deflated Sharpe, costs,
> drawdown - all six. A naive review would have green-lit it. The agent re-ran the strategy with
> the future hidden, the signal changed, and that single fact vetoes the entire gate result.

**On-screen text:** `passed all 6 gates -> still rejected`

---

## Scene 4 - THE CONTAINMENT MOMENT (1:25-2:20)

**Screen:** click **Malicious upload**. Scroll the source panel slowly through the five attacks so
each is legible: `os.system("rm -rf /")`, `subprocess.Popen(["curl", ...])`,
`socket.create_connection` to an exfiltration host, writing `pwned.txt` outside the scratch
directory, deleting it again - then the `while True: pass` at the bottom.

**Voice-over:**
> This is not a strategy. It wipes the disk, spawns curl, opens a socket to an exfiltration server,
> plants a persistence file outside its directory, deletes the evidence, then spins forever to burn
> the CPU. This is what an auditing agent has to survive, because to audit code you have to run it.

**Screen:** click **Run the audit**. Hold the shot on the **Sandbox events** panel as the red rows
appear one after another. Do not cut away. Let the viewer count them.

**Voice-over:**
> Twelve actions. Twelve refusals. Each row names the call and the rule that stopped it: no shell,
> no process spawning, no network, writes confined to one scratch directory. The infinite loop is
> killed by the wall-clock watchdog.

**Screen:** zoom on one red row (the `socket.` one) so the rule text is readable, then pan to the
verdict card: **REJECTED_UNSAFE**, zero trades.

**Voice-over:**
> Nothing left the container. The host was never at risk. And notice the audit did not crash - it
> treated containment as a finding, reported it, and still reached a verdict.

**On-screen text:** `12 blocked - 0 trades - host untouched`

---

## Scene 5 - How it is contained (2:20-2:40)

**Screen:** scroll to the "How containment works" section on the page; optionally cut to the ASCII
architecture diagram in the README for three seconds.

**Voice-over:**
> Two layers. A Python audit hook that refuses and logs, inside a container with no network, a
> read-only filesystem, no capabilities, a non-root user, and hard pid, memory and CPU caps. And
> the part that matters most: the sandbox only ever returns numbers - plus one and minus one per
> bar. The backtest runs on the host from those numbers. There is no path back.

---

## Scene 6 - Close (2:40-2:50)

**Screen:** back to the top of the page, the public URL visible in the address bar.

**Voice-over:**
> On a Vultr VM, reasoning on Vultr Serverless Inference, MIT licensed, the whole thing deploys with
> one command. BOTLAB Auditor - blast radius zero.

**On-screen text:** the public URL and `github.com/botlabtrade/botlab-auditor`

---

## Recording checklist

- [ ] `.env` is **not** on screen at any point, and the browser has no extensions sidebar showing.
- [ ] The address bar shows the HTTPS `sslip.io` URL, not `localhost`.
- [ ] `GET /api/health` reports `vultr-serverless` before recording, so the trace is genuinely
      LLM-driven.
- [ ] Run each demo once before recording so the warm-up time does not appear in the take.
- [ ] Scene 4 is one unbroken shot of the Sandbox events panel - that is the shot the challenge
      asks for.
- [ ] Total under 3:00. If over, trim Scene 2, never Scene 4.
