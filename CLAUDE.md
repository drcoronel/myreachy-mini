# Reachy Mini — Claude Code Guide

## What this repo is

Experiments and applications for a **Reachy Mini wireless** desktop robot (Pollen Robotics).
Flat Python + TypeScript monorepo managed with **uv** for Python and **npm/Vite** for the frontend dashboard.

> See `agents.local.md` for robot type, connection details, and setup status.

## Robot reference

Before implementing features, read the upstream SDK agent guide for hardware capabilities,
API patterns, and constraints:
https://github.com/pollen-robotics/reachy_mini/blob/main/AGENTS.md

Or as a shorter inline note inside the existing "What this repo is" block:

> For hardware capabilities and SDK patterns, see the upstream guide:
> https://github.com/pollen-robotics/reachy_mini/blob/main/AGENTS.md

## Layout

```
reachy-mini/
├── core/               # Config (pydantic-settings) + create_robot() factory
├── services/
│   ├── llm/            # LLM/VLM providers — shared base + Gemini + Ollama impls
│   ├── vision/         # Camera capture (OpenCV) + frame utilities
│   ├── motion/         # High-level motion helpers (to be built out)
│   └── audio/          # TTS/STT (to be built out)
├── apps/               # Standalone demo apps — each has a main.py entry point
│   ├── face_tracker/
│   ├── conversation/
│   └── gesture_demo/
├── dashboard/
│   ├── backend/        # FastAPI on :8001 — AI/LLM services only
│   └── frontend/       # Vite + React — proxies /daemon/* to the robot daemon
├── config/             # YAML config files for apps
└── scripts/            # Utility scripts
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

The robot runs a **daemon** at `reachy-mini.local:8000` that exposes:
- REST API at `/api` (interactive docs at `/docs`)
- WebSocket at `/ws/sdk` (used internally by the Python SDK)

Use `core.create_robot()` to get a configured `ReachyMini` instance:

```python
from core import create_robot

with create_robot() as robot:
    robot.goto_target(head=pose, duration=1.0)
```

Host/port read from `.env` (`REACHY_HOST`, `REACHY_PORT`).

## SDK quick reference

```python
from reachy_mini import ReachyMini
import numpy as np

with ReachyMini() as robot:
    # Smooth gesture (≥ 0.5s)
    robot.goto_target(head=np.eye(4), duration=1.0)

    # Real-time control loop (10Hz+)
    robot.set_target(head=pose_matrix)          # 4x4 numpy array
    robot.set_target(antennas=[0.0, 0.0])       # [right_rad, left_rad]
    robot.set_target(body_yaw=0.3)              # radians

    # Look at pixel in camera frame (great for tracking)
    robot.look_at_image(u=cx, v=cy, duration=0)

    # Look at 3D point in robot frame
    robot.look_at_world(x=0.5, y=0.0, z=0.3, duration=1.0)

    # Antennas / body / misc
    robot.wake_up()
    robot.goto_sleep()

    # Release camera to OpenCV before capturing frames
    robot.release_media()
    # ... use CameraCapture here ...
    robot.acquire_media()
```

**Safety limits:** head pitch/roll ±40°, head yaw ±180°, body yaw ±160°. SDK clamps automatically.

## Dashboard

- **Robot control**: goes directly to the daemon at `reachy-mini.local:8000/api` — the Vite dev server proxies `/daemon/*` there. No custom backend needed for robot control.
- **AI services**: our FastAPI on `:8001` handles LLM calls, vision AI, etc. Vite proxies `/api/ai/*` there.

```bash
./scripts/start_dashboard.sh    # both servers in parallel
```

## Frontend (dashboard)

```bash
cd dashboard/frontend
npm install
npm run dev        # :5173, proxies /daemon → daemon, /api/ai → :8001
npm run build
npm run typecheck
```

## AI providers

**Gemini** — `GOOGLE_API_KEY` in `.env`, use `GeminiProvider` from `services/llm`.

**Ollama** — `OLLAMA_HOST` + `OLLAMA_DEFAULT_MODEL`, use `OllamaProvider`. Both implement `LLMProvider` and are swappable.

## Adding a new app

1. Create `apps/<name>/` with `__init__.py` and `main.py`
2. Entry point: `async def run() -> None` called via `asyncio.run(run())`
3. Use `create_robot()` from `core` — don't hardcode connection details
4. For real-time control loops, use `set_target()` at 10Hz; for one-shot gestures, use `goto_target()`
5. Call `robot.release_media()` before opening the camera with OpenCV

## Code style

- Line length 100, ruff for linting/formatting, mypy for type checking (non-strict)
- No comments unless the WHY is non-obvious
- Async where it touches I/O; `asyncio.to_thread` for blocking SDK calls

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
