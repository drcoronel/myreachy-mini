import asyncio

from fastapi import APIRouter, HTTPException

from dashboard.backend import services
from dashboard.backend.state import state

router = APIRouter()


@router.post("/start")
async def start_tracker():
    if not state.robot_ready:
        raise HTTPException(503, "Robot not ready yet — wait for WebRTC stream")
    if state.tracking:
        return {"ok": True, "message": "already running"}
    state.tracking = True
    state.tracker_task = asyncio.create_task(services.face_tracker.run(state))
    return {"ok": True}


@router.post("/stop")
async def stop_tracker():
    state.tracking = False
    if state.tracker_task:
        state.tracker_task.cancel()
        state.tracker_task = None
    return {"ok": True}


@router.get("/status")
async def tracker_status():
    return {"tracking": state.tracking, "robot_ready": state.robot_ready}
