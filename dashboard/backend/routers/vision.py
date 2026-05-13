import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from services.vision import CameraCapture, frame_to_bytes

router = APIRouter()

_camera: CameraCapture | None = None


def get_camera() -> CameraCapture:
    global _camera
    if _camera is None:
        _camera = CameraCapture(source=0)
        _camera.open()
    return _camera


async def _mjpeg_generator():
    cam = get_camera()
    async for frame in cam.stream_frames(fps=15):
        jpg = frame_to_bytes(frame)
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
        )


@router.get("/stream")
async def mjpeg_stream():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
