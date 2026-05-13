# Reachy Mini — Claude Code Guide

## What this repo is

Experiments and applications for a **Reachy Mini wireless** desktop robot (Pollen Robotics).
The repo is a flat Python + TypeScript monorepo managed with **uv** for Python and **npm/Vite** for the frontend dashboard.

## Layout

```
reachy-mini/
├── core/               # Low-level SDK wrapper + config (ReachyMini, settings)
├── services/
│   ├── llm/            # LLM/VLM providers — shared base class + Gemini + Ollama impls
│   ├── vision/         # Camera capture (OpenCV) + frame utilities
│   ├── motion/         # High-level motion helpers (to be built out)
│   └── audio/          # TTS/STT (to be built out)
├── apps/               # Standalone demo apps — each has a main.py entry point
│   ├── face_tracker/
│   ├── conversation/
│   └── gesture_demo/
├── dashboard/
│   ├── backend/        # FastAPI server (REST + WebSocket)
│   └── frontend/       # Vite + React (TypeScript)
├── config/             # YAML config files for apps
└── scripts/            # Utility scripts (connect check, start dashboard)
```

## Python environment (uv)

```bash
# Install deps and create venv
uv sync

# Run a script
uv run python scripts/connect_check.py
uv run python -m apps.face_tracker.main

# Run the backend
uv run uvicorn dashboard.backend.main:app --reload

# Add a dependency
uv add <package>

# Dev tools
uv run ruff check .
uv run mypy .
uv run pytest
```

Python version is pinned in `.python-version` (3.11).

## Frontend (dashboard)

```bash
cd dashboard/frontend
npm install
npm run dev        # dev server on :5173, proxies /api and /ws to :8000
npm run build      # production build → dist/
npm run typecheck
```

Start both together: `./scripts/start_dashboard.sh`

## Robot connection

- Set `REACHY_HOST` in `.env` (default: `reachy.local`)
- Verify connectivity: `uv run python scripts/connect_check.py`
- The `ReachyMini` class in `core/robot.py` is a context manager around `reachy2-sdk`

## AI providers

**Gemini** — set `GOOGLE_API_KEY` in `.env`, use `GeminiProvider` from `services/llm`.

**Ollama** — set `OLLAMA_HOST` and `OLLAMA_DEFAULT_MODEL`. Default model is `llava:13b` (VLM-capable). Use `OllamaProvider`.

Both implement `LLMProvider` (base class in `services/llm/base.py`), so they are interchangeable.

## Adding a new app

1. Create `apps/<name>/` with `__init__.py` and `main.py`
2. Entry point: `async def run() -> None` called via `asyncio.run(run())`
3. Import from `core` and `services` — don't duplicate connection/config logic
4. Add a YAML config to `config/` if the app needs tunable parameters

## Adding a new service

1. Create `services/<name>/` with `__init__.py`
2. Expose a clean public API through `__init__.py`
3. Keep I/O async where possible (`async def`, `asyncio.to_thread` for blocking calls)

## Dashboard backend conventions

- Routers live in `dashboard/backend/routers/` and are registered in `main.py`
- The global `robot_instance` in `main.py` is the live `ReachyMini` object
- Routers import it with `from dashboard.backend.main import robot_instance`
- Offline mode: the server starts even if Reachy is unreachable — endpoints return 503

## Code style

- Line length 100, ruff for linting/formatting, mypy for type checking (non-strict)
- No comments unless the WHY is non-obvious
- Async everywhere that touches I/O; use `asyncio.to_thread` for blocking SDK calls

## Environment variables

Copy `.env.example` → `.env`. Never commit `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `REACHY_HOST` | `reachy.local` | Robot IP or mDNS hostname |
| `GOOGLE_API_KEY` | — | Gemini API key |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server |
| `OLLAMA_DEFAULT_MODEL` | `llava:13b` | Default VLM |
| `DASHBOARD_PORT` | `8000` | FastAPI listen port |
