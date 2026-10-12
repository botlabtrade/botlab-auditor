"""HTTP layer: the stream always ends with a done event, and oversized uploads are refused."""
import io
import json

from fastapi.testclient import TestClient

from app.main import MAX_UPLOAD_BYTES, app

client = TestClient(app)

TRADE_CSV = "symbol,side,r\n" + "".join(
    f"ALPHAUSDT,{'long' if i % 2 else 'short'},{(0.4 if i % 3 else -0.5):.2f}\n" for i in range(40))


def _sse_events(run_id):
    """Read the SSE stream and return the decoded events."""
    out = []
    with client.stream("GET", f"/api/audit/{run_id}/stream") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
                if out[-1].get("type") == "done":
                    break
    return out


def test_index_and_health():
    assert client.get("/").status_code == 200
    h = client.get("/api/health").json()
    assert h["ok"] is True
    assert set(h["demos"]) == {"honest", "overfit", "lookahead", "malicious"}


def test_demo_endpoint_serves_the_four_demos():
    for name in ("honest", "overfit", "lookahead", "malicious"):
        d = client.get(f"/api/demo/{name}").json()
        assert "def signals(" in d["source"]
        assert d["expected"]
    assert client.get("/api/demo/nope").status_code == 404


def test_stream_ends_with_a_done_event():
    r = client.post("/api/audit",
                    files={"trade_log": ("trades.csv", TRADE_CSV, "text/csv")},
                    data={"n_trials": "5"})
    assert r.status_code == 200
    body = r.json()
    events = _sse_events(body["id"])
    assert events[-1]["type"] == "done"
    assert events[-1]["report"]["status"]
    assert any(e["type"] == "tool_call" for e in events)


def test_oversized_upload_is_rejected():
    big = "# padding\n" * (MAX_UPLOAD_BYTES // 5)
    assert len(big.encode()) > MAX_UPLOAD_BYTES
    r = client.post("/api/audit", files={"strategy": ("big.py", big, "text/x-python")},
                    data={"n_trials": "1"})
    assert r.status_code == 413
    assert "KB" in r.json()["detail"]


def test_empty_submission_is_rejected():
    assert client.post("/api/audit", data={"n_trials": "1"}).status_code == 400


def test_unknown_run_id_is_404():
    assert client.get("/api/audit/deadbeef/stream").status_code == 404
