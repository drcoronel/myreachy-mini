from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class MoveHeadRequest(BaseModel):
    pan: float = 0.0    # degrees
    tilt: float = 0.0
    roll: float = 0.0


@router.get("/status")
async def get_status():
    from dashboard.backend.main import robot_instance
    return {"connected": robot_instance is not None and robot_instance.is_connected}


@router.post("/head/move")
async def move_head(req: MoveHeadRequest):
    from dashboard.backend.main import robot_instance
    if not robot_instance or not robot_instance.is_connected:
        raise HTTPException(503, "Robot not connected")
    robot_instance.sdk.head.rotate_to(pan=req.pan, tilt=req.tilt, roll=req.roll)
    return {"ok": True}


@router.post("/head/reset")
async def reset_head():
    from dashboard.backend.main import robot_instance
    if not robot_instance or not robot_instance.is_connected:
        raise HTTPException(503, "Robot not connected")
    robot_instance.sdk.head.rotate_to(pan=0, tilt=0, roll=0)
    return {"ok": True}
