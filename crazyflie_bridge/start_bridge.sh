#!/bin/bash
# Crazyflie Bridge Launcher
# Starts the video stream proxy and WebSocket motion control bridge.
#
# Usage:
#   ./start_bridge.sh
#   ./start_bridge.sh --cf-uri radio://0/80/2M/E7E7E7E7E7
#
# Environment variables:
#   CRAZYFLIE_IP  — IP address of the drone (default: 192.168.0.106)
#
# Example:
#   CRAZYFLIE_IP=192.168.0.110 ./start_bridge.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CRAZYFLIE_IP="${CRAZYFLIE_IP:-192.168.0.106}"

# Activate the crazyflie conda environment
eval "$(conda shell.bash hook)"
conda activate crazyflie

echo "[Launcher] Starting Crazyflie Bridge..."
echo "[Launcher] Drone IP:    $CRAZYFLIE_IP"
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
