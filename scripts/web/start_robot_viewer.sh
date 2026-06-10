#!/bin/bash
# Start Fleet-Safe Robot Web Viewer
# Usage: ./scripts/web/start_robot_viewer.sh [--port 8080] [--ros2]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_DIR="$REPO_ROOT/web/robot_web_viewer"

PORT=8080
ROS2=false

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --port) PORT="$2"; shift 2 ;;
        --ros2) ROS2=true; shift ;;
        *) shift ;;
    esac
done

echo "=== Fleet-Safe Robot Web Viewer ==="
echo "URL: http://localhost:$PORT"

# ROS2 sourcing (optional)
if [ "$ROS2" = true ] && [ -f /opt/ros/humble/setup.bash ]; then
    source /opt/ros/humble/setup.bash
    echo "ROS2 Humble sourced"
fi

# Activate conda env
if command -v conda &>/dev/null; then
    source ~/miniforge3/etc/profile.d/conda.sh 2>/dev/null || true
    conda activate isaac 2>/dev/null || conda activate base 2>/dev/null || true
fi

export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

# Install deps if needed
"${CONDA_PREFIX:-$HOME/miniforge3/envs/isaac}/bin/python" -c "import fastapi, uvicorn" 2>/dev/null || pip install fastapi uvicorn websockets

# Start viewer
cd "$APP_DIR"
"${CONDA_PREFIX:-$HOME/miniforge3/envs/isaac}/bin/python" app.py --host 0.0.0.0 --port "$PORT"
