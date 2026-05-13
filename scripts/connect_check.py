"""Quick connectivity check — run before any app to confirm Reachy is reachable.
Usage: uv run python scripts/connect_check.py
"""

from reachy_mini import ReachyMini
from core.config import settings

print(f"Connecting to {settings.reachy_host}:{settings.reachy_port} ...")

try:
    with ReachyMini(host=settings.reachy_host, port=settings.reachy_port) as robot:
        print("Connected!")
        pose = robot.get_current_head_pose()
        print(f"Head pose:\n{pose}")
        joints, antennas = robot.get_current_joint_positions()
        print(f"Antenna positions (rad): right={antennas[0]:.2f}, left={antennas[1]:.2f}")
except Exception as e:
    print(f"Connection failed: {e}")
