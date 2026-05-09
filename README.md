# Crazyflie Discovery Game

A Progressive Web App (PWA) that lets you pilot a physical [Crazyflie](https://www.bitcraze.io/products/crazyflie-2-1/) drone in real time while viewing its live camera feed directly in your browser. The drone streams video from an onboard ESP32-S3 AI-Deck camera, and the app overlays real-time telemetry (position, attitude, battery) on top of the video viewport.

## Objective

Control the flying motion of a Crazyflie nano-drone, retrieve the live MJPEG video stream captured by its ESP32-S3 AI-Deck camera, and display it within a mobile-friendly PWA interface — all from your phone or desktop browser.

---

## Getting Started

### Prerequisites

| Component | Version / Notes |
|-----------|----------------|
| Node.js | v18+ |
| Python | 3.10+ (via conda) |
| Conda env | Named `crazyflie` |
| Crazyradio PA | USB radio dongle plugged in |
| Crazyflie 2.1 | With AI-Deck (ESP32-S3 camera) |

### Clone the Repository

```bash
git clone <repo-url> crazyflie_discovery_game
cd crazyflie_discovery_game
```

### Install Frontend Dependencies

```bash
npm install
```

### Install Backend (Bridge) Dependencies

```bash
conda activate crazyflie
pip install -r crazyflie_bridge/requirements.txt
```

### Build the Frontend

```bash
npm run build
```

The production bundle is output to the `dist/` directory.

### Start the System

**1. Start the Crazyflie Bridge** (video proxy + WebSocket motion server):

```bash
cd crazyflie_bridge
./start_bridge.sh
```

You can optionally pass a custom Crazyflie radio URI:

```bash
./start_bridge.sh --cf-uri radio://0/80/2M/E7E7E7E7E7
```

This launches two services:
- **Video proxy** — `http://localhost:8082/stream`
- **WebSocket bridge** — `ws://localhost:8765`

**2. Start the Frontend Dev Server** (or serve the built `dist/` folder):

```bash
npm run dev
```

The app is available at `http://localhost:5175`.

---

## Using the PWA App

### Flight Controls

The app uses a touch-friendly virtual joystick overlay:

| Gesture | Effect |
|---------|--------|
| Drag left/right | Lateral movement (vy) |
| Drag up/down | Forward/backward movement (vx) |
| Height gesture | Ascend / descend (vz) |
| Rotate gesture | Yaw rotation |
| Release | Stop (hover in place) |

Additional buttons in the top-left corner:

- **Takeoff** — Arms the drone and lifts off to 0.5 m.
- **Land** — Initiates a controlled landing sequence.

### Connection Status

A badge in the top-right corner shows the current WebSocket connection state:

- Green — **Connected** to bridge
- Yellow — **Connecting…** (attempting reconnection)
- Red — **Disconnected**

The app reconnects automatically with exponential backoff (max 10 s delay).

---

## Main Display Area

The main viewport occupies the upper portion of the screen and contains:

### Live Video Feed

The full-bleed background displays the MJPEG video stream from the ESP32-S3 AI-Deck camera mounted on the Crazyflie. States:

- **Loading** — Spinner shown while waiting for the first video frame.
- **Connected** — Live camera feed fills the viewport.
- **Error** — "No Video Signal" message with a Retry button and the bridge URL for troubleshooting.

### Telemetry Overlay

A semi-transparent panel at the bottom of the viewport displays real-time drone data in a fixed-width font:

| Field | Description |
|-------|-------------|
| X, Y, Z | Position in world frame (meters) |
| R, P, Yaw | Roll, Pitch, Yaw angles (degrees) |
| Bat | Battery voltage (V) |
| WS | WebSocket link status indicator |

Telemetry is streamed at 10 Hz for position/attitude and 1 Hz for battery.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       PWA Frontend (React)                       │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ VideoStream│  │TelemetryOverlay│ │ Joystick + Buttons     │  │
│  └─────┬──────┘  └──────┬───────┘  └───────────┬────────────┘  │
│        │                 │                      │               │
│   HTTP GET          Receives JSON          Sends JSON           │
│   (MJPEG)           (telemetry)            (commands)           │
└────────┼─────────────────┼──────────────────────┼───────────────┘
         │                 │                      │
         ▼                 │                      ▼
┌─────────────────┐        │         ┌────────────────────────────┐
│ Video Proxy     │        │         │  WebSocket Bridge          │
│ :8082/stream    │        │         │  :8765                     │
│                 │        │         │                            │
│ Fetches MJPEG   │        │         │  ┌──────────────────────┐  │
│ from ESP32 cam  │        │         │  │ Command Queue        │  │
│ Rebroadcasts to │        │         │  │ (WS → Crazyflie)     │  │
│ multiple clients│        │         │  └──────────┬───────────┘  │
└────────┬────────┘        │         │             │              │
         │                 │         │  ┌──────────▼───────────┐  │
         │                 │         │  │ MotionCommander      │  │
         │                 │         │  │ (takeoff/land/move)  │  │
         │                 │         │  └──────────────────────┘  │
         │                 │         │                            │
         │                 │         │  ┌──────────────────────┐  │
         │                 └─────────┼──│ Telemetry Queue      │  │
         │                           │  │ (Crazyflie → WS)     │  │
         │                           │  └──────────────────────┘  │
         │                           └────────────────────────────┘
         │                                        │
         ▼                                        ▼
┌─────────────────┐                  ┌────────────────────────────┐
│ ESP32-S3        │                  │ Crazyflie 2.1              │
│ AI-Deck Camera  │                  │ (via Crazyradio PA)        │
└─────────────────┘                  └────────────────────────────┘
```

### Internal Workflow

1. **Startup** — `start_bridge.sh` activates the `crazyflie` conda environment, launches the MJPEG video proxy in the background, then starts the WebSocket bridge in the foreground.

2. **Video pipeline** — The video proxy connects to the ESP32-S3 AI-Deck at its IP address, continuously reads the MJPEG stream, extracts individual JPEG frames (SOI/EOI markers), and serves them to any number of browser clients over HTTP multipart.

3. **Control pipeline** — The user's joystick gestures in the PWA are mapped to velocity commands (`vx`, `vy`, `vz`, `yawrate`) and serialized as JSON over the WebSocket. The bridge queues commands in a thread-safe queue and a dedicated Crazyflie worker thread dispatches them through the `MotionCommander` API.

4. **Telemetry pipeline** — The Crazyflie worker thread registers log blocks for position (`stateEstimate.x/y/z`), attitude (`stabilizer.roll/pitch/yaw`), and battery (`pm.vbat`). Callbacks enqueue telemetry messages into an asyncio queue, which are then broadcast to all connected WebSocket clients in real time. The frontend hook updates React state, and the `TelemetryOverlay` component re-renders with the latest values.

5. **Resilience** — Both the WebSocket connection (frontend) and the Crazyflie radio link (backend) implement automatic reconnection with exponential backoff, ensuring the system recovers gracefully from transient failures.
