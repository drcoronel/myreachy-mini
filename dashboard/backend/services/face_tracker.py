"""
Face tracking background service using InsightFace SCRFD + Kalman filter.

State machine:
  LISTENING  — no face tracked; polling daemon DOA for speech direction
  ORIENTING  — speech detected; head snapped toward speaker, scanning for face
  TRACKING   — face found; Kalman + P-controller drives head and body

Loss recovery inside TRACKING (3-phase):
  1. Grace  (~1.5s): pure Kalman prediction, no decay
  2. Search (~4s):   Kalman prediction + velocity decay
  3. Lost:           reset tracker → LISTENING

P-controller:
  Incremental nudge each step: new_angle = current + KP * pixel_error
  No look_at_image calibration dependency.
"""

from __future__ import annotations

import asyncio
import logging
import math
from enum import Enum, auto

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from scipy.spatial.transform import Rotation

from core.config import settings
from services.audio.direction import DaemonDOA

logger = logging.getLogger(__name__)

# --- Head P-controller ---
KP_YAW = 0.03
KP_PITCH = 0.02
MAX_YAW = 60.0
MAX_PITCH = 35.0
YAW_SIGN = -1
PITCH_SIGN = 1
MAX_HEAD_STEP_DEG = 4.0   # clamp max head correction per frame

# --- Body P-controller ---
KP_BODY = 0.002
MAX_BODY_YAW = 2.5
BODY_DEAD_ZONE_PX = 80
BODY_YAW_SIGN = 1

DEAD_ZONE_PX = 30
MAX_GRACE_FRAMES = 15
SEARCH_FRAMES = 40
SEARCH_VEL_DECAY = 0.88

# --- Orientation (DOA → body sweep) ---
ORIENT_MAX_FRAMES = 80          # frames to sweep body toward speaker (~8s)
ORIENT_STEP_RAD = 0.12          # body rotation per frame (~6.9°, ~1.2 rad/s at 10 Hz)
ORIENT_DEAD_RAD = 0.05          # stop stepping when within this of target
ORIENT_ANGLE_SIGN = 1           # flip to -1 if body rotates the wrong way toward speaker
DOA_MIN_ANGLE_CHANGE = 0.05    # rad — ignore repeated readings within this delta
# XVF3800 DOA convention: 0° = some reference direction; adjust so that "speaker directly
# ahead" maps to delta=0. Set to math.radians(90) if straight-ahead reads ~90°.
DOA_FORWARD_RAD = math.pi / 2  # calibrate: DOA angle when speaker is directly in front
DOA_MIN_ORIENT_DELTA_RAD = math.radians(20)  # ignore DOA if speaker is already within 20° of center


class TrackMode(Enum):
    LISTENING = auto()
    ORIENTING = auto()
    TRACKING = auto()


# ---------------------------------------------------------------------------
# Kalman filter — 2D constant-velocity model
# ---------------------------------------------------------------------------

class KalmanFaceTracker:
    def __init__(self, dt: float = 0.1):
        self.F = np.array([
            [1, 0, dt, 0],
            [0, 1,  0, dt],
            [0, 0,  1,  0],
            [0, 0,  0,  1],
        ], dtype=float)
        self.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        self.Q = np.diag([100., 100., 50., 50.])
        self.R = np.diag([50., 50.])
        self._x: np.ndarray | None = None
        self._P = np.eye(4) * 500.0

    @property
    def initialized(self) -> bool:
        return self._x is not None

    def init(self, x: float, y: float) -> None:
        self._x = np.array([x, y, 0.0, 0.0])
        self._P = np.eye(4) * 500.0

    def predict(self) -> np.ndarray:
        self._x = self.F @ self._x
        self._P = self.F @ self._P @ self.F.T + self.Q
        return self._x[:2].copy()

    def update(self, x: float, y: float) -> np.ndarray:
        if not self.initialized:
            self.init(x, y)
            return self._x[:2].copy()
        z = np.array([x, y])
        S = self.H @ self._P @ self.H.T + self.R
        K = self._P @ self.H.T @ np.linalg.inv(S)
        self._x = self._x + K @ (z - self.H @ self._x)
        self._P = (np.eye(4) - K @ self.H) @ self._P
        return self._x[:2].copy()

    def decay_velocity(self, factor: float) -> None:
        if self.initialized:
            self._x[2] *= factor
            self._x[3] *= factor

    def reset(self) -> None:
        self._x = None
        self._P = np.eye(4) * 500.0

    @property
    def velocity(self) -> np.ndarray:
        return self._x[2:4].copy() if self.initialized else np.zeros(2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_pitch_yaw(pose: np.ndarray) -> tuple[float, float]:
    roll, pitch, yaw = Rotation.from_matrix(pose[:3, :3]).as_euler("xyz", degrees=True)
    return pitch, yaw


def _build_pose(pitch: float, yaw: float) -> np.ndarray:
    mat = np.eye(4)
    mat[:3, :3] = Rotation.from_euler("xyz", [0.0, pitch, yaw], degrees=True).as_matrix()
    return mat


def _load_detector() -> FaceAnalysis:
    logger.info("Loading InsightFace buffalo_sc...")
    app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(320, 320))
    logger.info("InsightFace detector ready")
    return app


def _doa_world_point(doa_angle: float, head_pose: np.ndarray) -> tuple[float, float, float]:
    """Convert DOA angle (rad, head frame) to a world-frame look-at point."""
    p_head = np.array([math.sin(doa_angle), math.cos(doa_angle), 0.0])
    p_world = head_pose[:3, :3] @ p_head
    return float(p_world[0]), float(p_world[1]), float(p_world[2])


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def _poll_doa(doa: DaemonDOA, latest: list, stop: asyncio.Event) -> None:
    """Poll DOA at 20 Hz. Latches speech_detected=True until the main loop clears it."""
    logger.info("DOA poller started")
    try:
        tick = 0
        while not stop.is_set():
            angle, speech = await doa.get()
            latest[0] = angle
            if speech:
                logger.info("DOA: speech=True angle=%.1f°",
                            math.degrees(angle) if angle is not None else 0.0)
                latest[1] = True  # latch — only cleared by the main loop after acting on it
            if tick % 40 == 0:  # heartbeat every ~2s
                logger.info("DOA heartbeat: angle=%s speech=%s",
                            f"{math.degrees(angle):.1f}°" if angle is not None else "None",
                            speech)
            tick += 1
            await asyncio.sleep(0.05)
    except BaseException as exc:
        logger.error("DOA poller crashed: %s", exc, exc_info=True)
        raise
    finally:
        logger.info("DOA poller stopped")


async def run(state) -> None:
    detector = await asyncio.to_thread(_load_detector)
    tracker = KalmanFaceTracker(dt=0.1)
    doa = DaemonDOA(host=settings.reachy_host, port=settings.reachy_port)
    await doa.start()

    doa_latest: list = [None, False]   # [angle: float|None, speech_detected: bool]
    doa_stop = asyncio.Event()
    asyncio.create_task(_poll_doa(doa, doa_latest, doa_stop))

    mode = TrackMode.LISTENING
    grace_remaining = 0
    search_remaining = 0
    orient_frames_remaining = 0
    orient_target_body_yaw = 0.0
    orient_doa_angle: float | None = None   # raw DOA angle saved when entering ORIENTING
    last_doa_angle: float | None = None
    current_body_yaw = 0.0

    logger.info("Face tracker started (mode=LISTENING)")

    try:
        while state.tracking:
            frame = await asyncio.to_thread(state.robot.media.get_frame)
            if frame is None:
                await asyncio.sleep(0.05)
                continue

            h, w = frame.shape[:2]
            cx0, cy0 = w // 2, h // 2

            faces = await asyncio.to_thread(detector.get, frame)
            annotated = frame.copy()

            # ----------------------------------------------------------------
            # State machine
            # ----------------------------------------------------------------
            est: np.ndarray | None = None

            if len(faces) > 0:
                face = max(faces, key=lambda f: f.det_score)
                x1, y1, x2, y2 = face.bbox.astype(int)
                raw_cx, raw_cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0

                if mode != TrackMode.TRACKING:
                    logger.info("Face found — switching to TRACKING")
                    mode = TrackMode.TRACKING
                    state.track_mode = "tracking"

                grace_remaining = MAX_GRACE_FRAMES
                search_remaining = SEARCH_FRAMES
                est = tracker.update(raw_cx, raw_cy)

                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 0), 2)
                cv2.putText(annotated, f"{face.det_score:.2f}",
                            (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1)
                if face.kps is not None:
                    for kp in face.kps.astype(int):
                        cv2.circle(annotated, tuple(kp), 3, (0, 180, 255), -1)

            elif mode == TrackMode.TRACKING:
                grace_remaining -= 1
                if tracker.initialized and grace_remaining > 0:
                    est = tracker.predict()
                elif tracker.initialized and search_remaining > 0:
                    tracker.decay_velocity(SEARCH_VEL_DECAY)
                    est = tracker.predict()
                    search_remaining -= 1
                else:
                    tracker.reset()
                    mode = TrackMode.LISTENING
                    state.track_mode = "listening"
                    last_doa_angle = None
                    current_body_yaw = 0.0  # re-sync with robot home position
                    logger.info("Face lost — switching to LISTENING")

            elif mode == TrackMode.LISTENING:
                angle, speech = doa_latest[0], doa_latest[1]
                doa_latest[1] = False  # clear latch
                # Only orient if speaker is meaningfully off-center; small deltas are noise.
                doa_delta = (angle - DOA_FORWARD_RAD) if angle is not None else 0.0
                if speech and angle is not None and abs(doa_delta) > DOA_MIN_ORIENT_DELTA_RAD:
                    logger.info("DOA: angle=%.1f° speech=True", math.degrees(angle))
                    changed = (last_doa_angle is None or
                               abs(angle - last_doa_angle) > DOA_MIN_ANGLE_CHANGE)
                    if changed:
                        logger.info("Speech detected at %.2f rad (%.1f°) — orienting",
                                    angle, math.degrees(angle))
                        logger.info("DOA delta from forward: %.2f rad (%.1f°)",
                                    doa_delta, math.degrees(doa_delta))
                        orient_target_body_yaw = float(np.clip(
                            current_body_yaw + ORIENT_ANGLE_SIGN * doa_delta,
                            -MAX_BODY_YAW, MAX_BODY_YAW
                        ))
                        last_doa_angle = angle
                        mode = TrackMode.ORIENTING
                        state.track_mode = "orienting"
                        orient_frames_remaining = ORIENT_MAX_FRAMES
                        orient_doa_angle = angle
                        logger.info("Orienting body to %.1f°",
                                    math.degrees(orient_target_body_yaw))

            elif mode == TrackMode.ORIENTING:
                orient_frames_remaining -= 1
                if orient_frames_remaining <= 0:
                    logger.info("Orient timed out — back to LISTENING")
                    mode = TrackMode.LISTENING
                    state.track_mode = "listening"
                    last_doa_angle = None
                    orient_doa_angle = None
                    current_body_yaw = 0.0  # re-sync with robot home position
                else:
                    # Sweep body toward speaker
                    delta = orient_target_body_yaw - current_body_yaw
                    if abs(delta) > ORIENT_DEAD_RAD:
                        step = math.copysign(min(abs(delta), ORIENT_STEP_RAD), delta)
                        current_body_yaw = float(np.clip(
                            current_body_yaw + step, -MAX_BODY_YAW, MAX_BODY_YAW
                        ))
                    await asyncio.to_thread(state.robot.set_target, body_yaw=current_body_yaw)

                    # Point head toward speaker using DOA world-frame projection.
                    # Convention: angle=π/2 → forward. p_head=[sin,cos,0] in head frame.
                    if orient_doa_angle is not None:
                        T_head = await asyncio.to_thread(state.robot.get_current_head_pose)
                        p_head = np.array([math.sin(orient_doa_angle),
                                           math.cos(orient_doa_angle), 0.0])
                        p_world = T_head[:3, :3] @ p_head
                        await asyncio.to_thread(
                            state.robot.look_at_world,
                            float(p_world[0]), float(p_world[1]), float(p_world[2]), 0,
                        )

            # ----------------------------------------------------------------
            # Head + body control (TRACKING only)
            # ----------------------------------------------------------------
            if est is not None:
                cv2.circle(annotated, (int(est[0]), int(est[1])), 8, (0, 220, 255), 2)
                vx, vy = tracker.velocity
                cv2.arrowedLine(
                    annotated,
                    (int(est[0]), int(est[1])),
                    (int(est[0] + vx * 3), int(est[1] + vy * 3)),
                    (0, 180, 255), 2, tipLength=0.3,
                )

            if mode == TrackMode.TRACKING and est is not None:
                dx, dy = est[0] - cx0, est[1] - cy0
                if abs(dx) > DEAD_ZONE_PX or abs(dy) > DEAD_ZONE_PX:
                    current_pose = await asyncio.to_thread(state.robot.get_current_head_pose)
                    current_pitch, current_yaw = _extract_pitch_yaw(current_pose)

                    raw_yaw = current_yaw + YAW_SIGN * dx * KP_YAW
                    raw_pitch = current_pitch + PITCH_SIGN * dy * KP_PITCH
                    new_yaw = float(np.clip(
                        current_yaw + np.clip(raw_yaw - current_yaw, -MAX_HEAD_STEP_DEG, MAX_HEAD_STEP_DEG),
                        -MAX_YAW, MAX_YAW
                    ))
                    new_pitch = float(np.clip(
                        current_pitch + np.clip(raw_pitch - current_pitch, -MAX_HEAD_STEP_DEG, MAX_HEAD_STEP_DEG),
                        -MAX_PITCH, MAX_PITCH
                    ))

                    if abs(dx) > BODY_DEAD_ZONE_PX:
                        current_body_yaw = float(np.clip(
                            current_body_yaw + BODY_YAW_SIGN * dx * KP_BODY,
                            -MAX_BODY_YAW, MAX_BODY_YAW,
                        ))

                    await asyncio.to_thread(
                        state.robot.set_target,
                        head=_build_pose(new_pitch, new_yaw),
                        body_yaw=current_body_yaw,
                    )
                    logger.debug(
                        "dx=%+.0f dy=%+.0f → head(y=%+.1f° p=%+.1f°) body=%.2f rad",
                        dx, dy, new_yaw, new_pitch, current_body_yaw,
                    )

            # ----------------------------------------------------------------
            # Overlay
            # ----------------------------------------------------------------
            cv2.drawMarker(annotated, (cx0, cy0), (200, 100, 0), cv2.MARKER_CROSS, 20, 1)

            mode_label = {
                TrackMode.LISTENING: "listening",
                TrackMode.ORIENTING: f"orienting ({orient_frames_remaining})",
                TrackMode.TRACKING: "tracking",
            }[mode]
            if est is not None and mode == TrackMode.TRACKING:
                if grace_remaining > 0:
                    mode_label = "tracking"
                elif search_remaining > 0:
                    mode_label = f"searching ({search_remaining})"
                status = (f"{mode_label}  v=({tracker.velocity[0]:+.0f},{tracker.velocity[1]:+.0f})"
                          f"  body={np.degrees(current_body_yaw):+.1f}°")
            else:
                status = mode_label

            cv2.putText(annotated, status, (8, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

            state.latest_frame = frame
            state.annotated_frame = annotated

            await asyncio.sleep(0.1)

    finally:
        doa_stop.set()
        await doa.stop()
        logger.info("Face tracker stopped")
