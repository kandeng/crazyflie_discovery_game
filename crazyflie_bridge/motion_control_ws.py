#!/usr/bin/env python3
"""
Crazyflie WebSocket Bridge

Runs a WebSocket server that accepts commands from a PWA frontend,
forwards them to a Crazyflie drone, and streams telemetry back.

Usage:
    python3 motion_control_ws.py
    python3 motion_control_ws.py --cf-uri radio://0/80/2M/E7E7E7E7E7 --port 8765
"""

import argparse
import asyncio
import json
import os
import queue
import signal
import sys
import threading
import time
import warnings
from contextlib import contextmanager

# Suppress cflib deprecation / firmware-version warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander

try:
    import websockets
except ImportError:
    print("Error: 'websockets' library not installed. Run: pip install websockets")
    sys.exit(1)


class CrazyflieBridge:
    """
    WebSocket server bridge for Crazyflie drone control.

    - WebSocket server accepts connections from PWA clients
    - Crazyflie connection + MotionCommander runs on a dedicated thread
    - Telemetry flows:  Crazyflie callbacks -> asyncio queue -> WebSocket clients
    - Commands flow:    WebSocket clients -> thread-safe queue -> MotionCommander
    """

    def __init__(self, cf_uri, port=8765, telemetry_hz=10):
        self.cf_uri = cf_uri
        self.port = port
        self.telemetry_period_ms = int(1000 / telemetry_hz)

        # Cross-thread communication
        self._command_queue = queue.Queue()
        self._telemetry_queue = asyncio.Queue(maxsize=100)

        self._loop = None
        self._running = True
        self._cf_thread = None
        self._motion_commander = None
        self._scf = None
        self._clients = set()

        # Current height tracked from telemetry (thread-safe via GIL for float)
        self._current_z = 0.0

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _suppress_stderr():
        """Context manager that temporarily silences stderr (for cflib noise)."""
        @contextmanager
        def _cm():
            old_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
            try:
                yield
            finally:
                sys.stderr.close()
                sys.stderr = old_stderr
        return _cm()

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def start(self):
        """Initialize CRTP drivers and spin up the Crazyflie worker thread."""
        cflib.crtp.init_drivers()
        self._cf_thread = threading.Thread(target=self._cf_worker, daemon=False)
        self._cf_thread.start()

    async def run(self):
        """Start the WebSocket server and telemetry broadcaster."""
        self._loop = asyncio.get_event_loop()
        await asyncio.sleep(2)

        async with websockets.serve(self._ws_handler, "0.0.0.0", self.port):
            print(f"[Bridge] WebSocket server running on ws://0.0.0.0:{self.port}")
            await self._broadcast_telemetry()

    def stop(self):
        """Signal all loops to exit."""
        self._running = False

    def join(self, timeout=10):
        """Wait for the Crazyflie worker thread to finish (e.g. after landing)."""
        if self._cf_thread and self._cf_thread.is_alive():
            self._cf_thread.join(timeout=timeout)

    # ------------------------------------------------------------------ #
    #  WebSocket Server Handler
    # ------------------------------------------------------------------ #

    async def _ws_handler(self, websocket):
        """Handle a single WebSocket client connection."""
        self._clients.add(websocket)
        remote = websocket.remote_address
        print(f"[Bridge] Client connected: {remote}")
        try:
            async for message in websocket:
                try:
                    cmd = json.loads(message)
                    action = cmd.get("action")
                    if action:
                        self._command_queue.put_nowait(cmd)
                except json.JSONDecodeError:
                    pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            print(f"[Bridge] Client disconnected: {remote}")

    async def _broadcast_telemetry(self):
        """Continuously read from telemetry queue and broadcast to all clients."""
        while self._running:
            try:
                telem = self._telemetry_queue.get_nowait()
                msg = json.dumps(telem)
                dead = set()
                for ws in self._clients:
                    try:
                        await ws.send(msg)
                    except websockets.exceptions.ConnectionClosed:
                        dead.add(ws)
                self._clients -= dead
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.01)

    # ------------------------------------------------------------------ #
    #  Crazyflie Worker Thread
    # ------------------------------------------------------------------ #

    def _cf_worker(self):
        """Background thread: owns the Crazyflie connection and MotionCommander."""
        while self._running:
            try:
                with SyncCrazyflie(self.cf_uri, cf=Crazyflie(rw_cache='./cache')) as scf:
                    self._scf = scf
                    print(f"[Bridge] Crazyflie connected: {self.cf_uri}")

                    self._setup_logging(scf.cf)
                    # Try new supervisor arming first (firmware v12+), fallback to legacy
                    try:
                        scf.cf.supervisor.send_arming_request(True)
                    except (AttributeError, Exception):
                        scf.cf.platform.send_arming_request(True)
                    time.sleep(1.0)

                    with self._suppress_stderr():
                        mc = MotionCommander(scf, default_height=0.5)
                    with mc:
                        self._motion_commander = mc
                        print("[Bridge] MotionCommander ready. Waiting for commands...")

                        while self._running:
                            try:
                                cmd = self._command_queue.get_nowait()
                                self._dispatch_command(cmd)
                            except queue.Empty:
                                pass
                            time.sleep(0.01)

                        # Ctrl-C / shutdown — land the drone before exiting
                        print("[Bridge] Landing drone...")
                        try:
                            self._gentle_land()
                        except Exception as e:
                            print(f"[Bridge] Land failed: {e}")
                        time.sleep(0.5)

            except Exception as e:
                print(f"[Bridge] Crazyflie error: {e}")
                self._motion_commander = None
                self._scf = None
                if self._running:
                    time.sleep(2)

    def _setup_logging(self, cf):
        """Register log blocks for position, attitude, and battery."""
        with self._suppress_stderr():
            log_pos = LogConfig(name='Position', period_in_ms=self.telemetry_period_ms)
            log_pos.add_variable('stateEstimate.x', 'float')
            log_pos.add_variable('stateEstimate.y', 'float')
            log_pos.add_variable('stateEstimate.z', 'float')
            cf.log.add_config(log_pos)
            log_pos.data_received_cb.add_callback(self._on_position)
            log_pos.start()

            log_stab = LogConfig(name='Stabilizer', period_in_ms=self.telemetry_period_ms)
            log_stab.add_variable('stabilizer.roll', 'float')
            log_stab.add_variable('stabilizer.pitch', 'float')
            log_stab.add_variable('stabilizer.yaw', 'float')
            cf.log.add_config(log_stab)
            log_stab.data_received_cb.add_callback(self._on_attitude)
            log_stab.start()

            log_batt = LogConfig(name='Battery', period_in_ms=1000)
            log_batt.add_variable('pm.vbat', 'FP16')
            cf.log.add_config(log_batt)
            log_batt.data_received_cb.add_callback(self._on_battery)
            log_batt.start()

    # ------------------------------------------------------------------ #
    #  Telemetry callbacks (Crazyflie thread -> asyncio queue)
    # ------------------------------------------------------------------ #

    def _on_position(self, timestamp, data, logconf):
        z = data.get('stateEstimate.z', data.get('kalman.stateZ', 0))
        self._current_z = z
        self._enqueue_telemetry("position", timestamp, {
            "x": data.get('stateEstimate.x', data.get('kalman.stateX', 0)),
            "y": data.get('stateEstimate.y', data.get('kalman.stateY', 0)),
            "z": z
        })

    def _on_attitude(self, timestamp, data, logconf):
        self._enqueue_telemetry("attitude", timestamp, {
            "roll": data.get('stabilizer.roll', 0),
            "pitch": data.get('stabilizer.pitch', 0),
            "yaw": data.get('stabilizer.yaw', 0)
        })

    def _on_battery(self, timestamp, data, logconf):
        self._enqueue_telemetry("battery", timestamp, {
            "voltage": data.get('pm.vbat', 0)
        })

    def _enqueue_telemetry(self, category, timestamp, payload):
        """Marshal telemetry from Crazyflie callbacks into the asyncio queue."""
        if self._loop is None or not self._loop.is_running():
            return

        telem = {
            "type": "telemetry",
            "category": category,
            "timestamp": timestamp,
            "data": payload
        }

        async def _put():
            try:
                self._telemetry_queue.put_nowait(telem)
            except asyncio.QueueFull:
                pass  # Drop if back-pressured

        asyncio.run_coroutine_threadsafe(_put(), self._loop)

    # ------------------------------------------------------------------ #
    #  Descent speed limiting & gentle landing
    # ------------------------------------------------------------------ #

    def _clamp_descent(self, vz):
        """
        Scale down the descent speed when the drone is below 0.5 m.

        Returns a negative (downward) velocity whose magnitude is reduced
        proportionally to the current height:
          - At 0.5 m or above:  full requested speed
          - At 0.25 m:          ~half speed
          - At 0.10 m:          ~20 % speed  (minimum 0.03 m/s)
        """
        z = max(self._current_z, 0.0)
        threshold = 0.5          # metres – start slowing below this
        min_speed = 0.03         # m/s – never slower than this (avoids stall)

        if z >= threshold:
            return vz            # above threshold, full speed

        scale = max(z / threshold, min_speed / abs(vz) if vz != 0 else 0)
        return vz * scale

    def _gentle_land(self):
        """
        Land the drone with a slow, controlled descent instead of the
        default MotionCommander.land() which can be abrupt.

        Strategy: descend at progressively slower speeds as height decreases,
        then stop motors once effectively on the ground.
        """
        mc = self._motion_commander
        if mc is None:
            return

        print("[Bridge] Gentle landing...")

        # Phase 1: descend to ~0.15 m at a moderate speed
        while self._current_z > 0.15:
            speed = max(0.05, min(0.2, self._current_z * 0.4))
            mc.start_linear_motion(0, 0, -speed, 0)
            time.sleep(0.05)

        # Phase 2: very slow final descent
        while self._current_z > 0.04:
            mc.start_linear_motion(0, 0, -0.03, 0)
            time.sleep(0.05)

        # Phase 3: cut motors
        mc.stop()
        # Send zero thrust to let it settle
        if self._scf:
            self._scf.cf.commander.send_stop_setpoint()
        time.sleep(0.3)
        print("[Bridge] Landed.")

    # ------------------------------------------------------------------ #
    #  Command dispatch (Crazyflie thread)
    # ------------------------------------------------------------------ #

    def _dispatch_command(self, cmd):
        """Execute a high-level motion command on the drone."""
        if self._motion_commander is None:
            print("[Bridge] Command dropped: MotionCommander not ready")
            return

        action = cmd.get("action")
        print(f"[Bridge] CMD >> {action}  {cmd}")

        try:
            if action == "takeoff":
                self._motion_commander.take_off(height=cmd.get("height", 0.5))
            elif action == "land":
                self._gentle_land()
            elif action == "stop":
                self._motion_commander.stop()
            elif action == "move":
                vx = cmd.get("vx") or 0
                vy = cmd.get("vy") or 0
                vz = cmd.get("vz") or 0
                yawrate = cmd.get("yawrate") or 0
                # Clamp downward speed when close to ground
                if vz < 0:
                    vz = self._clamp_descent(vz)
                self._motion_commander.start_linear_motion(vx, vy, vz, yawrate)
            elif action == "up":
                self._motion_commander.up(cmd.get("distance", 0.2))
            elif action == "down":
                self._motion_commander.down(cmd.get("distance", 0.2),
                                            velocity=self._clamp_descent(-0.2))
            elif action == "forward":
                self._motion_commander.forward(cmd.get("distance", 0.2))
            elif action == "back":
                self._motion_commander.back(cmd.get("distance", 0.2))
            elif action == "left":
                self._motion_commander.left(cmd.get("distance", 0.2))
            elif action == "right":
                self._motion_commander.right(cmd.get("distance", 0.2))
            else:
                print(f"[Bridge] Unknown action: {action}")
        except Exception as e:
            print(f"[Bridge] Command failed: {e}")


# ---------------------------------------------------------------------- #
#  Entry point
# ---------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Crazyflie WebSocket Bridge")
    parser.add_argument("--cf-uri", default="radio://0/80/2M/E7E7E7E7E7",
                        help="Crazyflie URI (default: radio://0/80/2M/E7E7E7E7E7)")
    parser.add_argument("--port", type=int, default=8765,
                        help="WebSocket server port (default: 8765)")
    parser.add_argument("--telemetry-hz", type=int, default=10,
                        help="Telemetry publish rate in Hz (default: 10)")
    args = parser.parse_args()

    bridge = CrazyflieBridge(
        cf_uri=args.cf_uri,
        port=args.port,
        telemetry_hz=args.telemetry_hz
    )

    bridge.start()

    def handle_signal(sig, frame):
        print("\n[Bridge] Shutting down...")
        bridge.stop()
        bridge.join(timeout=10)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        print("\n[Bridge] Shutting down...")
        bridge.stop()
        bridge.join(timeout=10)


if __name__ == "__main__":
    main()
