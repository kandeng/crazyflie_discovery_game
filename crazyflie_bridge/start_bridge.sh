#!/bin/bash
# Crazyflie Bridge Launcher
# Starts the video stream proxy and WebSocket motion control bridge.
#
# Usage:
#   ./start_bridge.sh
#   ./start_bridge.sh --cf-uri radio://0/80/2M/E7E7E7E7E7

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate the crazyflie conda environment
eval "$(conda shell.bash hook)"
conda activate crazyflie

echo "[Launcher] Starting Crazyflie Bridge..."
echo "[Launcher] Video proxy: http://localhost:8082/stream"
echo "[Launcher] WebSocket:   ws://localhost:8765"

# Start video stream proxy in background
python "$SCRIPT_DIR/video_stream_proxy.py" &
VIDEO_PID=$!

# Start WebSocket motion control bridge (foreground)
python "$SCRIPT_DIR/motion_control_ws.py" "$@"

# Cleanup on exit
kill $VIDEO_PID 2>/dev/null
wait
