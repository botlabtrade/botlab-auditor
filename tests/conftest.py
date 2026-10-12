"""Shared test setup: run from the repository root and always with the offline planner.

The demo verdicts must be deterministic, so the tests force the local sandbox backend and make sure
no inference key leaks in from the environment.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.pop("LLM_API_KEY", None)
os.environ["SANDBOX_BACKEND"] = "local"
