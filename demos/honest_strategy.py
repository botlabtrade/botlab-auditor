"""Demo 1 - an honest trend-follower.

Long when the 12-bar EMA is more than 0.2 % above the 96-bar EMA, short when it is more than 0.2 %
below, flat in between. Uses only past and current bars. One idea, one parameter set, tried once.
"""
import numpy as np
import pandas as pd


def signals(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    fast = close.ewm(span=12, adjust=False).mean()
    slow = close.ewm(span=96, adjust=False).mean()
    gap = (fast - slow) / slow
    sig = np.where(gap > 0.002, 1, np.where(gap < -0.002, -1, 0))
    return pd.Series(sig, index=df.index)
