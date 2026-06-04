# Progress Log

---

## 13.05.2026 (Uke 20) — Initial build: repo setup → face tracker with loss recovery

### Repo & SDK setup
- Created flat Python + TypeScript monorepo, managed with **uv** + **npm/Vite**
- Switched from `reachy2-sdk` (wrong SDK, gRPC-based) to `reachy-mini` (HTTP/WebSocket daemon SDK)
- Naming conflict: project was called `reachy-mini` in pyproject.toml, clashing with the pip package name → renamed to `reachy-mini-experiments`
- `reachy-mini` SDK must be installed with `uv pip install "reachy-mini"` separately — not listed in pyproject.toml because of the name collision. Running `uv sync` alone won't install it
- `core/robot.py` replaced custom wrapper with thin `create_robot()` factory; SDK connects in `__init__`, there is no `.connect()` call
- Silenced `reachy_mini.media.audio_control_utils` logger — always errors over WiFi (no USB audio device), not a real issue

### Dashboard architecture
- FastAPI backend on `:8001` for AI/LLM services only (`dashboard/backend/`)
- Vite frontend on `:5173` proxies `/api/ai/*` → `:8001`, `/daemon/*` → `reachy-mini.local:8000`
- Robot control goes directly to the daemon — no backend proxy needed for that
- `state.py` holds shared mutable state (robot handle, latest frame, tracking flag, task handle)
- Routers: `camera.py` (MJPEG stream at `/api/ai/camera/stream`), `tracker.py` (start/stop/status)
- Backend lifespan starts `_robot_connect()` as a background task; polls `robot.media.get_frame()` up to 30s for WebRTC negotiation

### Face tracker — evolution
Started with OpenCV Haar cascade on the laptop webcam → `apps/face_tracker/main.py`. Replaced with:

1. **InsightFace `buffalo_sc`** (SCRFD model, ~50 MB, downloads from HF Hub on first run)  
   - Much better detection quality than Haar  
   - `FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])`, det_size 320×320  
   - `dashboard/backend/services/face_tracker.py`

2. **Robot camera** via `robot.media.get_frame()` (WebRTC → BGR numpy array)  
   - `cv2.imshow` removed entirely — macOS camera permissions block it and there's no display server on the robot  
   - Frames streamed to the frontend via MJPEG over FastAPI

3. **Incremental angle P-controller** — replaced `look_at_image()` because it always returned the neutral pose (WebRTC stream resolution ≠ robot calibration assumption)  
   - Each frame: read `get_current_head_pose()`, decompose to pitch/yaw, nudge by `KP * pixel_error`  
   - `KP_YAW = KP_PITCH = 0.03`, `DEAD_ZONE_PX = 20`  
   - Direction signs needed tuning: `YAW_SIGN = -1`, `PITCH_SIGN = 1` (pitch was initially set to -1, caused head to dive away from face — corrected this session)

4. **Body yaw controller** — when `|dx| > BODY_DEAD_ZONE_PX (40px)`, accumulate `current_body_yaw` in world coordinates so Reachy can rotate toward someone who walked out of frame  
   - `KP_BODY = 0.002`, `BODY_YAW_SIGN = 1` (independent from head sign)  
   - Body was rotating too fast at first — sign was wrong, then gain was reduced

5. **Kalman filter** (`KalmanFaceTracker`, constant-velocity model `[x, y, vx, vy]`)  
   - Replaced EMA smoothing  
   - Velocity process noise `Q` had components at 500 initially — built up phantom velocity and drove body motion even when person was stationary → reduced to `[100, 100, 50, 50]`  
   - Controller reads Kalman estimate, not raw bbox centroid

6. **3-phase loss recovery** (added end of session):  
   - **Grace** (~1.5s, 15 frames): pure Kalman prediction  
   - **Search** (~4s, 40 frames): Kalman predict + velocity decay (`SEARCH_VEL_DECAY = 0.88`) — head sweeps in last-known direction, gradually slows  
   - **Lost**: tracker reset, head holds position  
   - Dashboard overlay shows `tracking` / `searching (N)` / `lost`

### Key files
- `dashboard/backend/services/face_tracker.py` — main tracker logic, all constants at top
- `dashboard/backend/routers/camera.py` — MJPEG stream
- `dashboard/backend/routers/tracker.py` — start/stop REST endpoints
- `dashboard/backend/state.py` — shared state
- `dashboard/frontend/src/App.tsx` — polls status, renders stream, Start/Stop button
- `scripts/hello_reachy.py` — motion smoke test (look left/right, nod, antenna wiggle)

---

## 04.06.2026 (Uke 23) — Speech direction detection + orientation state machine

### Goal
When no face is tracked, listen for speech → detect speaker direction via mic array DOA → rotate toward speaker → activate face tracking when face enters frame.

### Hardware
Seeed Studio ReSpeaker XMOS XVF3800 4-mic array attached to the robot. DOA is computed onboard by the XVF3800 chip — no custom signal processing needed. The daemon exposes the result at `/api/state/doa` returning `{"angle": float_rad, "speech_detected": bool}`.

### State machine (added to face_tracker.py)
```
LISTENING → (speech detected) → ORIENTING → (face found) → TRACKING
TRACKING → (face lost, grace+search exhausted) → LISTENING
ORIENTING → (timeout, no face) → LISTENING
```
- `track_mode` field added to `AppState` for dashboard visibility

### DOA client (`services/audio/direction.py`)
Polls `/api/state/doa` at 20Hz via `asyncio.create_task` background coroutine.
Uses synchronous `requests.get()` via `asyncio.to_thread` — `httpx.AsyncClient` raised
`CancelledError` (a `BaseException`) and silently killed the poller.

**Speech latch pattern:** `speech_detected=True` lasts only ~200ms but the main loop runs at
~10Hz. Poller sets latch True and never clears it; main loop clears after reading.

### SDK connection fixes (`core/robot.py`)
Two issues discovered connecting over home network (not hotspot):

1. **`connection_mode="auto"`** picks `localhost_only` on macOS → force `"network"`
2. **WebRTC signaling host**: daemon reports `wlan_ip=10.42.0.1` (hotspot IP, unreachable from home) → subclass `_ReachyMiniNetwork` overrides `_configure_mediamanager` to use `signalling_host=self.host` (`reachy-mini.local`) instead

`_VideoOnlyMediaManager` subclass added to set audio transceivers INACTIVE so GStreamer
doesn't claim the XVF3800 mic array exclusively (leaving the DOA pipeline free).

### DOA angle convention (non-obvious)
**0 rad = left, π/2 rad = front, π rad = right** — not the common "0 = forward" convention.
`DOA_FORWARD_RAD = math.pi / 2` to convert to delta from center:
```python
doa_delta = angle - math.pi / 2
```
Filter noise with `abs(doa_delta) > DOA_MIN_ORIENT_DELTA_RAD (20°)` — do NOT filter
`angle == 0.0` because 0 rad is a valid reading when the speaker is 90° to one side.

### Head orientation during ORIENTING (critical fix)
`set_target(head=...)` takes **world-frame absolute** pose. Commanding `_build_pose(0, 0)`
while rotating body caused the neck to counter-rotate, keeping the camera fixed — the body
rotated but the FOV didn't change.

Fix: use `look_at_world` with the canonical DOA projection from `examples/sound_doa.py`:
```python
p_head = np.array([math.sin(doa_angle), math.cos(doa_angle), 0.0])
T_head = robot.get_current_head_pose()
p_world = T_head[:3, :3] @ p_head
robot.look_at_world(p_world[0], p_world[1], p_world[2], duration=0)
```
Body rotation (`set_target(body_yaw=...)`) is applied separately in the same frame.

### Stability tuning
- Reduced `KP_YAW` 0.05→0.03, `KP_PITCH` 0.05→0.02
- Added `MAX_HEAD_STEP_DEG = 4.0` per-frame clamp on head corrections
- Increased `DEAD_ZONE_PX` 20→30, `BODY_DEAD_ZONE_PX` 40→80
- `current_body_yaw` reset to `0.0` on every LISTENING re-entry to prevent drift

### Other fixes
- `robot.wake_up()` must be called after camera ready — without it, motor commands are silently ignored
- `except BaseException` required in background pollers to catch `CancelledError`

### Key files changed this session
- `apps/face_tracker/main.py` — added `wake_up()` call
- `dashboard/backend/services/face_tracker.py` — state machine, DOA integration, orientation logic
- `dashboard/backend/state.py` — added `track_mode` field
- `core/robot.py` — `_ReachyMiniNetwork`, `_VideoOnlyMediaManager`, `create_robot()` fixes
- `services/audio/direction.py` — new DOA client
- `LEARNINGS.md` — engineering notes (new file)
