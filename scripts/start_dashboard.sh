#!/usr/bin/env bash
# Start backend and frontend dev servers in parallel.
set -e

echo "Starting FastAPI backend..."
uv run uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

echo "Starting Vite frontend..."
cd dashboard/frontend && npm run dev &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
