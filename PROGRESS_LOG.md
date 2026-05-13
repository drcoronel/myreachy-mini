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
