"""
Standalone face tracker (no dashboard).
For the dashboard-integrated version run: scripts/start_dashboard.sh

Run: uv run python -m apps.face_tracker.main
Press Ctrl+C to quit.
"""

import asyncio
import logging

from core import create_robot
from dashboard.backend.services.face_tracker import run as run_tracker
from dashboard.backend.state import AppState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    local_state = AppState()

    with create_robot() as robot:
        local_state.robot = robot

        logger.info("Waiting for camera stream (WebRTC negotiation ~15s)...")
        for i in range(60):
            frame = await asyncio.to_thread(robot.media.get_frame)
            if frame is not None:
                local_state.robot_ready = True
                h, w = frame.shape[:2]
                logger.info("Camera ready: %dx%d — starting tracker", w, h)
                break
            if i % 5 == 0:
                logger.info("Still waiting... (%ds)", i)
            await asyncio.sleep(0.5)

        if not local_state.robot_ready:
            logger.error("Camera stream did not start within 30s")
            return

        robot.wake_up()
        local_state.tracking = True
        try:
            await run_tracker(local_state)
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
