"""FastAPI dashboard backend — robot status, camera stream, control endpoints."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core import ReachyMini, settings
from dashboard.backend.routers import robot, vision

logger = logging.getLogger(__name__)

robot_instance: ReachyMini | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global robot_instance
    robot_instance = ReachyMini()
    try:
        robot_instance.connect()
    except Exception:
        logger.warning("Reachy not reachable — running in offline mode")
    yield
    if robot_instance:
        robot_instance.disconnect()


app = FastAPI(title="Reachy Mini Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(robot.router, prefix="/api/robot", tags=["robot"])
app.include_router(vision.router, prefix="/api/vision", tags=["vision"])


@app.websocket("/ws/status")
async def status_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            connected = robot_instance is not None and robot_instance.is_connected
            await websocket.send_json({"connected": connected})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
