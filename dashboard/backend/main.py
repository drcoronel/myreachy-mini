"""Dashboard backend — camera stream + face tracker service."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core import create_robot
from dashboard.backend.routers import camera, tracker
from dashboard.backend.state import state

logger = logging.getLogger(__name__)


async def _robot_connect() -> None:
    """Connect to Reachy and warm up the WebRTC camera stream in the background."""
    try:
        # ReachyMini connects to the daemon in __init__ (no separate connect() call)
        state.robot = await asyncio.to_thread(create_robot)
        logger.info("Robot connected — waiting for camera stream...")
    except Exception as exc:
        logger.warning("Robot not reachable: %s — running in offline mode", exc)
        return

    # Poll until the first frame arrives (WebRTC negotiation takes ~15s)
    for i in range(60):
        try:
            frame = await asyncio.to_thread(state.robot.media.get_frame)
        except Exception as exc:
            logger.warning("Error getting frame: %s", exc)
            await asyncio.sleep(0.5)
            continue
        if frame is not None:
            state.latest_frame = frame
            state.robot_ready = True
            h, w = frame.shape[:2]
            logger.info("Camera ready: %dx%d", w, h)
            return
        if i % 5 == 0:
            logger.info("Waiting for WebRTC stream... (%ds)", i)
        await asyncio.sleep(0.5)

    logger.warning("Camera stream did not start within 30s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_robot_connect())
    yield
    state.tracking = False
    if state.tracker_task:
        state.tracker_task.cancel()
    if state.robot:
        await asyncio.to_thread(state.robot.disconnect)


app = FastAPI(title="Reachy Mini Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(camera.router, prefix="/api/ai/camera", tags=["camera"])
app.include_router(tracker.router, prefix="/api/ai/tracker", tags=["tracker"])
