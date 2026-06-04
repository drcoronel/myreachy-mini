# Reachy Mini — Claude Code Guide

## Agent behavior

### Always be a teacher

Unless the user explicitly requests otherwise:
- Explain concepts as you go — why a choice was made, not just what was done
- Encourage questions ("Let me know if you'd like more detail on any of this")
- Don't assume prior knowledge of the SDK, robotics, or async Python
- When something is non-obvious (DOA conventions, frame semantics, motor modes), explain it inline

### Check agents.local.md first

**Before doing anything**, read `agents.local.md` — it contains robot type, connection details, and setup status for this session.

### Write plan.md before implementing

For any non-trivial feature:
1. Create `plan.md` in the relevant app directory
2. Write your understanding of what the user wants
3. List the technical approach and open questions
4. Wait for confirmation before coding

---

## What this repo is

Experiments and applications for a **Reachy Mini wireless** desktop robot (Pollen Robotics).
Flat Python monorepo managed with **uv**, plus a TypeScript/Vite dashboard.

> **Always read `agents.local.md` first** — it contains robot type, connection details, and setup status.

## Layout

```
reachy-mini/
├── core/               # Config (pydantic-settings) + create_robot() factory
├── services/
│   ├── llm/            # LLM/VLM providers — shared base + Gemini + Ollama impls
│   ├── vision/         # Camera capture (OpenCV) + frame utilities
│   ├── motion/         # High-level motion helpers
│   └── audio/          # DOA client + TTS/STT
├── apps/               # Standalone demo apps — each has a main.py entry point
│   ├── face_tracker/
│   ├── conversation/
│   └── gesture_demo/
├── dashboard/
│   ├── backend/        # FastAPI on :8001 — AI/LLM services only
│   └── frontend/       # Vite + React — proxies /daemon/* to the robot daemon
├── config/             # YAML config files for apps
├── scripts/            # Utility scripts
├── LEARNINGS.md        # Hard-won engineering notes
└── PROGRESS_LOG.md     # Session-by-session build log
```

## Python environment (uv)

```bash
uv sync                                         # install/update deps
uv run python scripts/connect_check.py         # verify robot connection
uv run python -m apps.face_tracker.main        # run an app
uv run uvicorn dashboard.backend.main:app --reload --port 8001
uv add <package>                               # add a dependency
uv run ruff check . && uv run mypy .           # lint + typecheck
uv run pytest
```

Python version pinned in `.python-version` (3.11).

> **Note:** `reachy-mini` SDK is installed via `uv pip install "reachy-mini"` (not listed in
> pyproject.toml — the project is named `reachy-mini-experiments` to avoid a naming conflict).

## Robot connection

The robot runs a **daemon** at `reachy-mini.local:8000`:
- REST API at `/api` (interactive docs at `/docs`)
- WebSocket at `/ws/sdk` (used internally by the Python SDK)

Use `core.create_robot()` — never instantiate `ReachyMini` directly:

```python
from core import create_robot

with create_robot() as robot:
    robot.wake_up()
    robot.goto_target(head=pose, duration=1.0)
```

Host/port read from `.env` (`REACHY_HOST`, `REACHY_PORT`). `create_robot()` forces
`connection_mode="network"` and patches WebRTC signaling to use the hostname instead of
the daemon's hotspot IP.

## SDK quick reference

```python
from reachy_mini import ReachyMini
import numpy as np

with ReachyMini() as robot:
    robot.wake_up()                              # required before any motor commands

    # Smooth gesture (≥ 0.5s, interpolated)
    robot.goto_target(head=np.eye(4), duration=1.0)

    # Real-time control loop (10Hz+, immediate)
    robot.set_target(head=pose_matrix)           # 4x4 numpy array, world-frame absolute
    robot.set_target(antennas=[0.0, 0.0])        # [right_rad, left_rad]
    robot.set_target(body_yaw=0.3)               # radians

    # Look at a pixel in the camera frame
    robot.look_at_image(u=cx, v=cy, duration=0)

    # Look at a 3D point in world frame
    robot.look_at_world(x=0.5, y=0.0, z=0.3, duration=0)

    # DOA → head direction (from sound_doa.py reference)
    p_head = np.array([np.sin(doa_angle), np.cos(doa_angle), 0.0])
    p_world = robot.get_current_head_pose()[:3, :3] @ p_head
    robot.look_at_world(p_world[0], p_world[1], p_world[2], duration=0)

    # Motor modes
    robot.set_motor_mode("gravity_compensation")  # "enabled" | "disabled" | "gravity_compensation"

    # Recorded emotions
    from reachy_mini.motion.recorded_move import RecordedMoves
    moves = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
    robot.play_move(moves.get("happy"), initial_goto_duration=1.0)

    robot.goto_sleep()

    # Release camera to OpenCV before capturing frames
    robot.release_media()
    # ... use CameraCapture here ...
    robot.acquire_media()
```

### goto_target vs set_target

| Method | Use when |
|--------|----------|
| `goto_target()` | **Default** — smooth interpolation, ≥ 0.5s gestures, one-shot moves |
| `set_target()` | Real-time reactive loop (tracking, games) at 10Hz+ |

Never mix both in the same control flow. One loop owns `set_target`; everything else queues
to it. See `.claude/skills/motion-philosophy.md`.

### Motor names

`body_rotation`, `stewart_1` through `stewart_6`, `right_antenna`, `left_antenna`

### Interpolation methods

`minjerk` (default), `linear`, `ease_in_out`, `cartoon`

## Safety limits

| Joint | Range |
|-------|-------|
| Head pitch / roll | ±40° |
| Head yaw | ±180° |
| Body yaw | ±160° |
| Head yaw − body yaw delta | max ±65° |

SDK clamps values automatically. The yaw delta limit is easy to violate when rotating the
body without also adjusting the head — always send head + body_yaw together when orienting.

## Hardware (wireless variant)

| Component | Description |
|-----------|-------------|
| Head | 6 DOF: x, y, z, roll, pitch, yaw (Stewart platform) |
| Body | Rotation around vertical axis (`body_yaw`) |
| Antennas | 2 motors; also usable as physical buttons (threshold ~0.3 rad) |
| Camera | WebRTC stream via GStreamer on the onboard CM4 |
| Mic array | Seeed ReSpeaker XVF3800 — DOA exposed at `/api/state/doa` |

**Platform note:** the CM4 is memory/CPU constrained. Keep compute (InsightFace, LLM
inference) on the laptop. The robot is a pure IO device in this repo.

## REST API quick reference

Daemon at `http://reachy-mini.local:8000/api`. Interactive docs at `/docs`.

```
GET  /api/state/full          # full robot state (joints, motors, sensors)
GET  /api/state/doa           # {"angle": float_rad, "speech_detected": bool}
POST /api/move/goto           # smooth interpolated move
POST /api/move/set_target     # immediate raw target
WS   ws://reachy-mini.local:8000/api/state/ws/full   # streaming state
```

See `.claude/skills/rest-api.md` for full endpoint list and examples.

## Dashboard

- **Robot control**: direct to daemon at `reachy-mini.local:8000/api` — Vite proxies `/daemon/*`
- **AI services**: FastAPI on `:8001` handles LLM calls, vision, DOA — Vite proxies `/api/ai/*`

```bash
./scripts/start_dashboard.sh    # both servers in parallel
```

## Frontend

```bash
cd dashboard/frontend
npm install
npm run dev        # :5173, proxies /daemon → daemon, /api/ai → :8001
npm run build
npm run typecheck
```

## AI providers

**Gemini** — `GOOGLE_API_KEY` in `.env`, use `GeminiProvider` from `services/llm`.

**Ollama** — `OLLAMA_HOST` + `OLLAMA_DEFAULT_MODEL`, use `OllamaProvider`.

Both implement `LLMProvider` and are swappable.

## Adding a new app

1. Create `apps/<name>/` with `__init__.py` and `main.py`
2. Entry point: `async def run() -> None` called via `asyncio.run(run())`
3. Use `create_robot()` from `core` — never hardcode connection details
4. Call `robot.wake_up()` before any control loop
5. For real-time loops, use `set_target()` at 10Hz in a single dedicated loop
6. Call `robot.release_media()` before opening the camera with OpenCV

## Code style

- Line length 100, ruff for linting/formatting, mypy for type checking (non-strict)
- No comments unless the WHY is non-obvious
- Async where it touches I/O; `asyncio.to_thread` for blocking SDK calls
- Catch `BaseException` (not `Exception`) in background pollers — `CancelledError` is a `BaseException`

## Environment variables

Copy `.env.example` → `.env`. Never commit `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `REACHY_HOST` | `reachy-mini.local` | Robot daemon hostname |
| `REACHY_PORT` | `8000` | Robot daemon port |
| `GOOGLE_API_KEY` | — | Gemini API key |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server |
| `OLLAMA_DEFAULT_MODEL` | `llava:13b` | Default VLM |
| `DASHBOARD_PORT` | `8001` | AI services backend port |

## Skills reference

Detailed guides in `.claude/skills/` (mirrored from upstream SDK):

| Skill | When to use |
|-------|-------------|
| `motion-philosophy.md` | Choosing between `goto_target` and `set_target` |
| `control-loops.md` | Building real-time reactive apps (tracking, games) |
| `safe-torque.md` | Enabling/disabling motors without jerky motion |
| `ai-integration.md` | Building LLM-powered apps, queue-based tool calls |
| `symbolic-motion.md` | Defining motion mathematically (dances, rhythms) |
| `interaction-patterns.md` | Antennas as buttons, head as controller |
| `debugging.md` | App crashes, connectivity issues, basic checks |
| `testing-apps.md` | Testing checklist, simulation limitations |
| `rest-api.md` | Full HTTP/WebSocket API reference |
| `deep-dive-docs.md` | When to read full SDK source |

Also read `LEARNINGS.md` for hard-won lessons specific to this repo.
