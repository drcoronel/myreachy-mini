"""Shared mutable state for the dashboard backend."""

from __future__ import annotations

import asyncio  # noqa: F401 — needed for Optional[asyncio.Task] annotation
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from reachy_mini import ReachyMini


class AppState:
    robot: ReachyMini | None = None
    robot_ready: bool = False          # True once WebRTC media stream is up
    latest_frame: np.ndarray | None = None    # raw camera frame
    annotated_frame: np.ndarray | None = None # frame with face overlay
    tracking: bool = False
    tracker_task: asyncio.Task | None = None
    track_mode: str = "listening"      # "listening" | "orienting" | "tracking"


state = AppState()
