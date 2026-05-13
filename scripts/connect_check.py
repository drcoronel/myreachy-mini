"""Quick connectivity check — run before any app to confirm Reachy is reachable.
Usage: uv run python scripts/connect_check.py
"""

from core import ReachyMini

try:
    with ReachyMini() as r:
        print(f"Connected to Reachy at {r._host}")
        print("SDK:", r.sdk)
except Exception as e:
    print(f"Connection failed: {e}")
