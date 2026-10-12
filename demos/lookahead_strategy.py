"""Demo 4 - a strategy that peeks into the future (look-ahead bias).

It "predicts" the next bar with ``shift(-1)``: the backtest is spectacular, live trading is
impossible. The look-ahead audit recomputes the signal on truncated history and catches it.
"""
import numpy as np
import pandas as pd


def signals(df: pd.DataFrame) -> pd.Series:
    nxt = df["close"].shift(-1)                      # <- tomorrow's price, unknowable today
    sig = np.where(nxt > df["close"], 1, -1)
    return pd.Series(sig, index=df.index)
