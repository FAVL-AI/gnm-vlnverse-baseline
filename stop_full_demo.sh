#!/usr/bin/env bash

echo "Stopping FleetSafe demo processes..."

pkill -9 -f "uvicorn" 2>/dev/null || true
pkill -9 -f "run_supervisor_demo_isaac.py" 2>/dev/null || true
pkill -9 -f "next dev" 2>/dev/null || true
pkill -9 -f "next-server" 2>/dev/null || true
pkill -9 -f "turbopack" 2>/dev/null || true
pkill -9 -f "node.*next" 2>/dev/null || true
pkill -9 -f "kit" 2>/dev/null || true

if command -v lsof >/dev/null 2>&1; then
    lsof -ti:3000 | xargs -r kill -9 2>/dev/null || true
    lsof -ti:3001 | xargs -r kill -9 2>/dev/null || true
    lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true
fi

echo "✅ Stopped."
