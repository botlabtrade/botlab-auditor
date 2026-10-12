"""Generate the deterministic synthetic OHLCV data the sandbox feeds to strategies.

No network access is needed (or allowed) inside the sandbox, so the audit runs on this
synthetic market: hourly bars for four made-up symbols, built from a random walk plus a slowly
drifting trend component (so a genuine trend-follower has a small, real edge to find).

Run:  python data/make_data.py      (same seed -> byte-identical files)
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

SEED = 20261103
SYMBOLS = ("ALPHAUSDT", "BRAVOUSDT", "CHARLIEUSDT", "DELTAUSDT", "ECHOUSDT", "FOXTROTUSDT",
           "GOLFUSDT", "HOTELUSDT")
BARS = 3000
DRIFT_SD = float(os.environ.get("DRIFT_SD", "0.00005"))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ohlcv")


def make_symbol(rng: np.random.Generator, start_price: float) -> pd.DataFrame:
    noise = rng.normal(0.0, 0.007, BARS)
    drift = np.zeros(BARS)
    for t in range(1, BARS):
        drift[t] = 0.996 * drift[t - 1] + rng.normal(0.0, DRIFT_SD)
    logret = drift + noise
    close = start_price * np.exp(np.cumsum(logret))
    open_ = np.concatenate([[start_price], close[:-1]])
    wick = np.abs(rng.normal(0.0, 0.003, (2, BARS)))
    high = np.maximum(open_, close) * (1 + wick[0])
    low = np.minimum(open_, close) * (1 - wick[1])
    vol = np.round(rng.lognormal(10, 0.4, BARS), 2)
    ts = pd.date_range("2026-01-01", periods=BARS, freq="h")
    return pd.DataFrame({"timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": open_.round(6),
                         "high": high.round(6), "low": low.round(6), "close": close.round(6),
                         "volume": vol})


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(SEED)
    for i, sym in enumerate(SYMBOLS):
        df = make_symbol(rng, 100.0 * (i + 1))
        df.to_csv(os.path.join(OUT, f"{sym}.csv"), index=False, lineterminator="\n")
        print(sym, len(df), "bars, last close", df["close"].iloc[-1])


if __name__ == "__main__":
    main()
