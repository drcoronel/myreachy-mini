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

## 01.07.2026 (Uke 27) — Robot mic array integration + config fixes

### Goal
Switch conversation audio input from laptop mic (sounddevice) to the robot's onboard ReSpeaker XVF3800 mic array via the SDK's WebRTC audio stream.

### Why the laptop mic failed
- `sounddevice` opened the MacBook mic at 16kHz — it captured audio but levels were extremely low (peak 0.006 on ±1.0 scale)
- Silero VAD never triggered (max probability 0.02) — the conversation loop hung at "Listening..." indefinitely
- The robot's mic array is purpose-built for far-field speech capture and already streams over WebRTC

### `MicCapture` rewrite (`services/audio/mic.py`)
- Replaced `sounddevice.InputStream` with `robot.media.get_audio_sample()` (SDK media manager)
- Audio arrives as stereo float32 `(N, 2)` at 16kHz via WebRTC (Opus-decoded to F32LE)
- Downmix to mono via `sample.mean(axis=1)`, buffer into 512-sample windows for Silero VAD
- Key detail: `get_audio_sample()` returns variable-length chunks — must drain **all** complete 512-sample windows per poll (`while` not `if`) to avoid lag
- `start_recording()` / `stop_recording()` bracket each utterance capture
- Constructor now takes `media_manager` parameter instead of creating its own audio source

### pydantic-settings `extra="ignore"` fix
- `core/config.py` `Settings` rejected `CONV_*` env vars from `.env` → added `extra="ignore"`
- `apps/conversation/config.py` `ConversationSettings` rejected `REACHY_*` vars → same fix
- Root cause: multiple `BaseSettings` classes sharing one `.env` file each see all vars; pydantic's default is `extra="forbid"`

### Status
- WIP — not yet tested end-to-end (WebRTC stream was slow to negotiate during testing)
- Next: test robot mic capture, add skip-camera flag for voice-only mode

### Key files changed
- `services/audio/mic.py` — rewritten for robot mic array
- `apps/conversation/main.py` — passes `robot.media` to `MicCapture`
- `core/config.py` — `extra="ignore"`
- `apps/conversation/config.py` — `extra="ignore"`

---

## 12.06.2026 (Uke 24) — Conversation app: voice pipeline + personality system

### Goal
Build a full voice conversation loop: mic → STT → LLM → TTS, running concurrently with the face tracker so Reachy looks at whoever it's talking to.

### Voice pipeline (`apps/conversation/`)
- `MicCapture` — captures utterances using **Silero VAD** (replaced RMS energy threshold)
  - Fixed 512-sample windows at 16kHz, `speech_threshold=0.5`, `silence_ms=1200`
  - VAD prevents mid-sentence cutoffs; RMS was fooled by pauses and background noise
- `STTService` — **faster-whisper large-v3-turbo** (upgraded from `base`)
  - Pinned `language="en"` + `condition_on_previous_text=True` for Hispanic-accented English
  - `vad_filter=False` — Silero VAD already handled upstream, no double-filtering
- `OllamaProvider` — `llama3.2:3b` via local Ollama
- `TTSService` — Kokoro `af_heart` voice, 24kHz output via sounddevice

### Personality system (`config/personalities.yaml` + `apps/conversation/personality.py`)
- Four personalities defined in YAML: `friendly`, `curious`, `professional`, `playful`
- `load_personality(name)` reads YAML and returns the prompt string; defaults to `"friendly"`
- `ConversationApp` accepts `personality=` kwarg — swappable without touching pipeline code

### `_build_messages()` — context window design
```python
[
    Message(role="system", content=f"{personality} {grounding}"),
    *self._history[-6:],   # last 3 turns, bounded
    Message(role="user", content=user_text),
]
```
- Grounding: `"You are currently looking at someone."` / `"You cannot currently see anyone."` based on `track_mode`
- History window fixed at 6 messages (3 turns) — suits llama3.2:3b's 4k context

### Simulator support (`core/robot.py`)
- `create_robot(sim=True)` — skips `_ReachyMiniNetwork` and WebRTC patches, uses `localhost_only`
- `REACHY_SIM=1` env var in `apps/conversation/main.py` switches mode without code changes
- Run: `reachy-mini-daemon --mockup-sim` + `REACHY_SIM=1 uv run python -m apps.conversation.main`

### Logging added to all services
All services (`mic`, `stt`, `tts`, `ollama`) now emit structured INFO logs — pipeline stage is visible from module name via `logging.getLogger(__name__)`.

### Config (`apps/conversation/config.py`)
All tunable values centralised in `ConversationSettings` (pydantic-settings, `CONV_` prefix):
- `CONV_LLM_MODEL`, `CONV_STT_MODEL`, `CONV_STT_LANGUAGE`, `CONV_TTS_VOICE`
- `CONV_VAD_THRESHOLD`, `CONV_VAD_SILENCE_MS`
- `CONV_PERSONALITY`, `CONV_SIM`

Override at runtime with env vars or add to `.env` — no code changes needed.
`.env.example` updated with all `CONV_` variables and defaults.

### Key files
- `apps/conversation/main.py` — conversation loop, all values from settings
- `apps/conversation/config.py` — pydantic-settings config (`CONV_` prefix)
- `apps/conversation/personality.py` — YAML loader
- `config/personalities.yaml` — personality definitions
- `services/audio/mic.py` — Silero VAD capture
- `services/audio/stt.py` — faster-whisper large-v3-turbo
- `services/audio/tts.py` — Kokoro TTS
- `core/robot.py` — `create_robot(sim=True)` support

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
