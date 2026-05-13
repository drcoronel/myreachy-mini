"""MJPEG camera stream — serves annotated frames when tracking, raw when not."""

import asyncio

import cv2
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from dashboard.backend.state import state

router = APIRouter()


async def _mjpeg_generator():
    while True:
        frame = state.annotated_frame if state.tracking else state.latest_frame
        if frame is None:
            await asyncio.sleep(0.05)
            continue
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
        await asyncio.sleep(1 / 15)  # 15 fps stream


@router.get("/stream")
async def camera_stream():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/status")
async def camera_status():
    return JSONResponse({
        "robot_ready": state.robot_ready,
        "has_frame": state.latest_frame is not None,
    })
