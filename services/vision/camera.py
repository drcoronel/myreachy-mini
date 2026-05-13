"""OpenCV-based camera capture, works with local webcam or Reachy's camera stream."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

import cv2
import numpy as np


class CameraCapture:
    def __init__(self, source: int | str = 0) -> None:
        self._source = source
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self._source)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera source: {self._source}")

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "CameraCapture":
        self.open()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def read_frame(self) -> np.ndarray:
        if self._cap is None:
            raise RuntimeError("Camera not opened.")
        ok, frame = self._cap.read()
        if not ok:
            raise RuntimeError("Failed to read frame.")
        return frame

    async def stream_frames(self, fps: float = 10) -> AsyncIterator[np.ndarray]:
        interval = 1.0 / fps
        while True:
            frame = await asyncio.to_thread(self.read_frame)
            yield frame
            await asyncio.sleep(interval)
