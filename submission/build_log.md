# Build log

This project is judged on work done during the Vultr *Agent Rush* build window (3-8 November 2026).
The honest position: a working prototype existed on 12 October 2026 and the commit history shows
it. This file records what is planned for the window and what actually happened, dated, so a judge
can check any claim against the commits.

## Before the window (12 October 2026)

Prototype: sandbox runner and audit-hook policy, seven audit tools, host-side replay engine, the
tool-use loop with an offline fallback, the FastAPI app and single-page UI, four demo strategies,
synthetic data, 14 tests. Container image and VM installer written but **never executed**: the
development machine had neither Docker nor Linux.

## Planned for the window

| # | Work | Why it matters to the challenge |
|---|---|---|
| 1 | Bring up the Docker backend for real: build the runner image, run all four demos through it, record the container's own refusals | The challenge is containment. Until the container runs, only the in-process audit hook is proven. |
| 2 | Deploy on a Vultr VM: installer run end to end, systemd service, HTTPS, public demo URL | Required: backend on Vultr, public demo. |
| 3 | Wire Vultr Serverless Inference and compare the LLM planner against the offline planner on all four demos | Required: Vultr Serverless Inference. Also tests whether the agent reaches the same verdicts when a model, not a fixed script, chooses the tools. |
| 4 | Adversarial pass: new containment cases (symlink escape, fork bomb, memory bomb, slow network read, writing to the output file the host reads back) with a test for each | Judges reward containment that holds under pressure, not one happy-path demo. |
| 5 | Container hardening proven by test: `--network none`, read-only root, dropped capabilities, pid/memory/CPU caps, no-new-privileges | Turns claims in the README into checks that run. |
| 6 | Load and failure behaviour: concurrent audits, a killed container mid-run, a malformed upload | Reliability is a judged criterion. |
| 7 | Record the demo video against the deployed instance | Required: containment moment on camera. |

## What actually happened

Filled in during the window, newest last. Each entry: date, what changed, the commit.

<!-- 3 Nov: -->
