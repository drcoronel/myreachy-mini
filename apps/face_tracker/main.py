"""
Face tracker: detects a face with OpenCV and steers Reachy's head toward it.
Run: uv run python -m apps.face_tracker.main
"""

import asyncio
import logging

import cv2

from core import ReachyMini
from services.vision import CameraCapture

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRAME_W, FRAME_H = 640, 480
DEAD_ZONE = 30  # pixels — ignore small offsets


async def run() -> None:
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    with ReachyMini() as robot, CameraCapture(0) as cam:
        logger.info("Face tracker running — press Ctrl+C to stop")
        async for frame in cam.stream_frames(fps=10):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))

            if len(faces) == 0:
                continue

            x, y, w, h = faces[0]
            cx, cy = x + w // 2, y + h // 2
            dx, dy = cx - FRAME_W // 2, cy - FRAME_H // 2

            if abs(dx) < DEAD_ZONE and abs(dy) < DEAD_ZONE:
                continue

            pan_delta = -dx * 0.05
            tilt_delta = dy * 0.05
            robot.sdk.head.rotate_by(pan=pan_delta, tilt=tilt_delta)
            await asyncio.sleep(0.05)


if __name__ == "__main__":
    asyncio.run(run())
