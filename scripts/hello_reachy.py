"""4-second visible motion test: look around + antenna wiggle.
Usage: uv run python scripts/hello_reachy.py
"""

import time
import numpy as np
from scipy.spatial.transform import Rotation

from core import create_robot


def pose(roll=0.0, pitch=0.0, yaw=0.0) -> np.ndarray:
    mat = np.eye(4)
    mat[:3, :3] = Rotation.from_euler("xyz", [roll, pitch, yaw], degrees=True).as_matrix()
    return mat


with create_robot() as robot:
    robot.wake_up()

    # Look left
    robot.goto_target(head=pose(yaw=30), duration=0.5)
    time.sleep(0.4)

    # Look right
    robot.goto_target(head=pose(yaw=-30), duration=0.5)
    time.sleep(0.4)

    # Nod down
    robot.goto_target(head=pose(pitch=-20), duration=0.4)
    time.sleep(0.3)

    # Nod up
    robot.goto_target(head=pose(pitch=20), duration=0.4)
    time.sleep(0.3)

    # Antenna wiggle
    robot.goto_target(antennas=[0.8, -0.8], duration=0.3)
    time.sleep(0.3)
    robot.goto_target(antennas=[-0.8, 0.8], duration=0.3)
    time.sleep(0.3)

    # Back to neutral
    robot.goto_target(head=pose(), antennas=[0.0, 0.0], duration=0.5)
    time.sleep(0.6)

    print("Done!")
