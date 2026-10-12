"""The four demo strategies must keep earning the four verdicts the project claims they earn."""
import os

import pytest

from agent.loop import run_agent
from agent.tools import AuditState

DEMOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demos")


def audit(demo_file, n_trials):
    with open(os.path.join(DEMOS, demo_file), "r", encoding="utf-8") as f:
        src = f.read()
    state = AuditState(src, None, n_trials)
    events = list(run_agent(state))
    done = [e for e in events if e["type"] == "done"]
    assert done, "the agent never produced a done event"
    return state, done[-1]["report"], events


@pytest.mark.parametrize("demo_file,n_trials,expected", [
    ("honest_strategy.py", 3, "WATCH"),
    ("overfit_strategy.py", 50, "NOT_READY"),
    ("lookahead_strategy.py", 50, "REJECTED_LOOKAHEAD"),
    ("malicious_strategy.py", 1, "REJECTED_UNSAFE"),
])
def test_demo_verdict(demo_file, n_trials, expected):
    state, report, _ = audit(demo_file, n_trials)
    assert report["status"] == expected


def test_lookahead_is_a_veto_not_a_gate_failure():
    """The peeking strategy passes the statistical gates; look-ahead is what rejects it."""
    state, report, _ = audit("lookahead_strategy.py", 50)
    assert report["status"] == "REJECTED_LOOKAHEAD"
    assert report["gate_status"] == "READY_FOR_MICRO_LIVE"
    assert state.lookahead["mismatch"] > 0
    assert report["override_reason"]


def test_malicious_upload_is_contained_and_produces_no_trades():
    state, report, events = audit("malicious_strategy.py", 1)
    assert report["status"] == "REJECTED_UNSAFE"
    assert state.trades == []
    assert report["sandbox_blocked_events"] == 12
    kinds = {e["event"] for e in state.sandbox_events}
    assert "os.system" in kinds                       # shell
    assert any(k.startswith("socket.") for k in kinds)  # network
    assert "wall_clock_timeout" in kinds              # the infinite loop
    sandbox_results = [e for e in events
                       if e["type"] == "tool_result" and e["tool"] == "run_strategy_in_sandbox"]
    assert sandbox_results and sandbox_results[0]["result"]["contained"] is True


def test_honest_strategy_has_no_lookahead_and_no_blocks():
    state, report, _ = audit("honest_strategy.py", 3)
    assert state.lookahead["mismatch"] == 0
    assert state.sandbox_events == []
    assert len(state.trades) > 0


def test_overfit_is_caught_by_the_deflated_sharpe():
    """Same strategy, honest trial count vs. the 50 variants actually tried."""
    _, report_50, _ = audit("overfit_strategy.py", 50)
    assert report_50["status"] == "NOT_READY"
    assert "G2" in report_50["gate_report"] or report_50["verdict"]
