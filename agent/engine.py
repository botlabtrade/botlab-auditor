"""Host-side backtest engine: turns the +1/-1/0 signals produced INSIDE the sandbox into trades.

The user's code never runs here. This module only receives a list of integers per symbol from the
sandbox and replays them against the same OHLCV data with honest execution rules:

* a signal computed on bar t's close is executed at bar t+1's OPEN (no same-bar fills);
* one unit of risk = RISK_ATR (5) x ATR(14) at the signal bar, as a fraction of price (floor 0.2 %);
* gross R = side x (exit / entry - 1) / risk;  net R subtracts fees, slippage and funding using
  :class:`honest_backtest.CostModel`.
"""
from __future__ import annotations

import glob
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from honest_backtest import CostModel

RISK_ATR = 5.0   # one unit of risk = 5 x ATR(14) (a typical trend-follower stop)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ohlcv")


@dataclass
class SimTrade:
    symbol: str
    side: str
    entry_time: str
    exit_time: str
    entry: float
    exit: float
    risk_frac: float
    hold_hours: float
    gross_r: float
    net_r: Optional[float] = None


def load_ohlcv(data_dir: str = DATA_DIR) -> Dict[str, pd.DataFrame]:
    out = {}
    for p in sorted(glob.glob(os.path.join(data_dir, "*.csv"))):
        out[os.path.splitext(os.path.basename(p))[0]] = pd.read_csv(p)
    if not out:
        raise FileNotFoundError(f"no OHLCV csv files in {data_dir} (run python data/make_data.py)")
    return out


def atr(df: pd.DataFrame, n: int = 14) -> np.ndarray:
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n, min_periods=1).mean().to_numpy()   # trailing only


def signals_to_trades(df: pd.DataFrame, sig: Sequence[int], symbol: str) -> List[SimTrade]:
    sig = np.asarray(sig, dtype=int)
    if len(sig) != len(df):
        raise ValueError(f"{symbol}: {len(sig)} signals for {len(df)} bars")
    o, c = df["open"].to_numpy(float), df["close"].to_numpy(float)
    ts = df["timestamp"].astype(str).to_numpy()
    a = atr(df)
    trades: List[SimTrade] = []
    pos, entry_i, entry_px, risk = 0, -1, 0.0, 0.0

    def close_at(i: int) -> None:
        exit_px = o[i]
        side = "long" if pos > 0 else "short"
        gross = pos * (exit_px / entry_px - 1.0) / risk
        trades.append(SimTrade(symbol, side, ts[entry_i], ts[i], float(entry_px), float(exit_px),
                               float(risk), float(i - entry_i), float(gross)))

    for t in range(len(df) - 1):            # decision on bar t close -> fill at bar t+1 open
        want = int(sig[t])
        if want == pos:
            continue
        if pos != 0:
            close_at(t + 1)
        pos = want
        if pos != 0:
            entry_i, entry_px = t + 1, o[t + 1]
            risk = max(RISK_ATR * a[t] / c[t], 0.002)
    if pos != 0:                            # mark the last open trade at the final close
        exit_px, side = c[-1], ("long" if pos > 0 else "short")
        trades.append(SimTrade(symbol, side, ts[entry_i], ts[-1], float(entry_px), float(exit_px),
                               float(risk), float(len(df) - 1 - entry_i),
                               float(pos * (exit_px / entry_px - 1.0) / risk)))
    return trades


def apply_costs(trades: List[SimTrade], cm: CostModel = CostModel()) -> List[SimTrade]:
    for t in trades:
        t.net_r = cm.net_return(t.side, t.entry, t.exit, t.hold_hours) / t.risk_frac
    return trades


def trades_to_dicts(trades: List[SimTrade]) -> List[dict]:
    return [asdict(t) for t in trades]
