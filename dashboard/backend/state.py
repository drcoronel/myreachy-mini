"""Shared mutable state for the dashboard backend."""

from __future__ import annotations

import asyncio  # noqa: F401 — needed for Optional[asyncio.Task] annotation
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:
    from reachy_mini import ReachyMini


class AppState:
    robot: Optional["ReachyMini"] = None
    robot_ready: bool = False          # True once WebRTC media stream is up
    latest_frame: Optional[np.ndarray] = None    # raw camera frame
    annotated_frame: Optional[np.ndarray] = None # frame with face overlay
    tracking: bool = False
    tracker_task: Optional[asyncio.Task] = None


state = AppState()
