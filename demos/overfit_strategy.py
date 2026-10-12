"""Demo 2 - an overfit strategy that looks great in a naive backtest.

This is the best of many variants the author tried: EMA 20/80 direction, but only entered on
Wednesdays and Saturdays at 19:00 UTC, then held for exactly 36 bars. Every one of those
specific numbers was picked because it made the backtest look good on THIS data.
Run it with "variants tried = 50" and the Deflated Sharpe Ratio exposes it.
"""
import numpy as np
import pandas as pd

ENTRY_WEEKDAYS = (2, 5)   # Wednesday, Saturday   <- chosen by looking at results
ENTRY_HOURS = (19,)       # 19:00 UTC              <- chosen by looking at results
HOLD_BARS = 36            #                        <- chosen by looking at results


def signals(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    trend = np.where(close.ewm(span=20, adjust=False).mean() > close.ewm(span=80, adjust=False).mean(), 1, -1)
    ts = pd.to_datetime(df["timestamp"])
    can_enter = np.isin(ts.dt.dayofweek, ENTRY_WEEKDAYS) & np.isin(ts.dt.hour, ENTRY_HOURS)
    out = np.zeros(len(df), dtype=int)
    left, cur = 0, 0
    for i in range(len(df)):
        if left > 0:
            out[i], left = cur, left - 1
            continue
        if can_enter[i]:
            cur, left = int(trend[i]), HOLD_BARS - 1
            out[i] = cur
    return pd.Series(out, index=df.index)
