"""
Face tracking background service using InsightFace SCRFD + Kalman filter.

Model: buffalo_sc (small+fast, ~50 MB, downloaded from HF Hub on first run)

Control strategy:
  Kalman filter with constant-velocity model tracks [x, y, vx, vy].
  - On detection: fuse measurement into filter state (update step)
  - On miss:      propagate forward using velocity (predict step)
  Head controller reads the filter's smooth estimate, not raw detections.

Loss recovery (3-phase):
  1. Grace  (~1.5s): pure Kalman prediction, no decay
  2. Search (~4s):   Kalman prediction + velocity decay — head sweeps in the
                     direction the face was last heading, then slows to a stop
  3. Lost:           tracker reset, head holds position until next detection

P-controller:
  Each step, read current head yaw/pitch and nudge by KP * pixel_error.
  Incremental — no look_at_image calibration dependency.
"""

from __future__ import annotations

import asyncio
import logging

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from scipy.spatial.transform import Rotation

logger = logging.getLogger(__name__)

# --- Head P-controller ---
KP_YAW = 0.03
KP_PITCH = 0.03
MAX_YAW = 60.0
MAX_PITCH = 35.0
YAW_SIGN = -1
PITCH_SIGN = 1

# --- Body P-controller ---
# Slow rotation in world coordinates so the face stays in frame even after
# the head reaches its yaw limit. Body gain is much lower than head gain
# so it only kicks in for sustained large offsets.
KP_BODY = 0.002        # radians per pixel
MAX_BODY_YAW = 2.5     # rad (~143°, within ±160° SDK limit)
BODY_DEAD_ZONE_PX = 40 # body only moves when error exceeds this
BODY_YAW_SIGN = 1      # independent of YAW_SIGN — flip if body goes wrong way

DEAD_ZONE_PX = 20
MAX_GRACE_FRAMES = 15   # pure-predict frames before entering search (~1.5s)
SEARCH_FRAMES = 40      # search frames after grace expires (~4s)
SEARCH_VEL_DECAY = 0.88 # velocity multiplier per frame during search


# ---------------------------------------------------------------------------
# Kalman filter — 2D constant-velocity model
# State: [x, y, vx, vy]
# ---------------------------------------------------------------------------

class KalmanFaceTracker:
    def __init__(self, dt: float = 0.1):
        self.F = np.array([           # state transition (constant velocity)
            [1, 0, dt, 0],
            [0, 1,  0, dt],
            [0, 0,  1,  0],
            [0, 0,  0,  1],
        ], dtype=float)

        self.H = np.array([           # measurement: observe x, y only
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=float)

        self.Q = np.diag([100., 100., 50., 50.])    # process noise
        self.R = np.diag([50., 50.])                 # measurement noise

        self._x: np.ndarray | None = None            # state [x, y, vx, vy]
        self._P = np.eye(4) * 500.0                  # state covariance

    @property
    def initialized(self) -> bool:
        return self._x is not None

    def init(self, x: float, y: float) -> None:
        self._x = np.array([x, y, 0.0, 0.0])
        self._P = np.eye(4) * 500.0

    def predict(self) -> np.ndarray:
        """Propagate state forward one step. Returns estimated [x, y]."""
        self._x = self.F @ self._x
        self._P = self.F @ self._P @ self.F.T + self.Q
        return self._x[:2].copy()

    def update(self, x: float, y: float) -> np.ndarray:
        """Fuse a new detection into the state. Returns estimated [x, y]."""
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
    logger.info("Loading InsightFace buffalo_sc (downloads from HF Hub on first run)...")
    app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(320, 320))
    logger.info("InsightFace detector ready")
    return app


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run(state) -> None:
    detector = await asyncio.to_thread(_load_detector)
    tracker = KalmanFaceTracker(dt=0.1)
    grace_remaining = 0
    search_remaining = 0
    current_body_yaw = 0.0   # radians, accumulated from start of session

    logger.info("Face tracker started")

    while state.tracking:
        frame = await asyncio.to_thread(state.robot.media.get_frame)
        if frame is None:
            await asyncio.sleep(0.05)
            continue

        h, w = frame.shape[:2]
        cx0, cy0 = w // 2, h // 2

        faces = await asyncio.to_thread(detector.get, frame)
        annotated = frame.copy()

        if len(faces) > 0:
            face = max(faces, key=lambda f: f.det_score)
            x1, y1, x2, y2 = face.bbox.astype(int)
            raw_cx, raw_cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            grace_remaining = MAX_GRACE_FRAMES
            search_remaining = SEARCH_FRAMES

            est = tracker.update(raw_cx, raw_cy)

            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 0), 2)
            cv2.putText(annotated, f"{face.det_score:.2f}",
                        (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1)
            if face.kps is not None:
                for kp in face.kps.astype(int):
                    cv2.circle(annotated, tuple(kp), 3, (0, 180, 255), -1)
        else:
            grace_remaining -= 1
            if tracker.initialized and grace_remaining > 0:
                # Phase 1 — grace: pure Kalman prediction
                est = tracker.predict()
            elif tracker.initialized and search_remaining > 0:
                # Phase 2 — search: sweep in last-known direction with decay
                tracker.decay_velocity(SEARCH_VEL_DECAY)
                est = tracker.predict()
                search_remaining -= 1
            else:
                # Phase 3 — lost: reset and wait for next detection
                tracker.reset()
                est = None

        # Draw Kalman estimate
        if est is not None:
            cv2.circle(annotated, (int(est[0]), int(est[1])), 8, (0, 220, 255), 2)
            vx, vy = tracker.velocity
            cv2.arrowedLine(
                annotated,
                (int(est[0]), int(est[1])),
                (int(est[0] + vx * 3), int(est[1] + vy * 3)),
                (0, 180, 255), 2, tipLength=0.3,
            )

        # Head + body control
        if est is not None:
            dx, dy = est[0] - cx0, est[1] - cy0
            if abs(dx) > DEAD_ZONE_PX or abs(dy) > DEAD_ZONE_PX:
                current_pose = await asyncio.to_thread(state.robot.get_current_head_pose)
                current_pitch, current_yaw = _extract_pitch_yaw(current_pose)

                # Head: fast fine correction
                new_yaw = float(np.clip(
                    current_yaw + YAW_SIGN * dx * KP_YAW, -MAX_YAW, MAX_YAW
                ))
                new_pitch = float(np.clip(
                    current_pitch + PITCH_SIGN * dy * KP_PITCH, -MAX_PITCH, MAX_PITCH
                ))

                # Body: slow world-coordinate rotation, kicks in for large offsets
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

        cv2.drawMarker(annotated, (cx0, cy0), (200, 100, 0), cv2.MARKER_CROSS, 20, 1)
        if est is not None:
            if grace_remaining > 0:
                mode = "tracking"
            elif search_remaining > 0:
                mode = f"searching ({search_remaining})"
            else:
                mode = "tracking"
            status = (f"{mode}  v=({tracker.velocity[0]:+.0f},{tracker.velocity[1]:+.0f})"
                      f"  body={np.degrees(current_body_yaw):+.1f}°")
        else:
            status = "lost"
        cv2.putText(annotated, status, (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        state.latest_frame = frame
        state.annotated_frame = annotated

        await asyncio.sleep(0.1)

    logger.info("Face tracker stopped")
