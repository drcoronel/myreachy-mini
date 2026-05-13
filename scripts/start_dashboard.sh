#!/usr/bin/env bash
# Start AI services backend (port 8001) and Vite frontend (port 5173) in parallel.
# Robot control goes directly to reachy-mini.local:8000 — no backend needed for that.
set -e

echo "Starting AI services backend (port 8001)..."
uv run uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 8001 --reload &
BACKEND_PID=$!

echo "Starting Vite frontend (port 5173)..."
cd dashboard/frontend && npm run dev &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
