#!/usr/bin/env python3
"""
MJPEG Multi-Client Proxy for ESP32-S3-AI-Deck

Fetches a single MJPEG stream from the ESP32-Crazyflie and re-broadcasts it
to multiple HTTP clients simultaneously.

Usage:
    python3 video_stream_proxy.py
    python3 video_stream_proxy.py --upstream http://192.168.0.109/stream --port 8082

Endpoints:
    http://localhost:PORT/stream    — Continuous MJPEG stream (for <img> tags)
    http://localhost:PORT/snapshot  — Single JPEG frame (for polling)
"""

import argparse
import os
import threading
import http.server
import socketserver
import urllib.request
import time

CRAZYFLIE_IP = os.environ.get("CRAZYFLIE_IP", "192.168.0.106")
UPSTREAM_URL = f"http://{CRAZYFLIE_IP}/stream"
PROXY_PORT = 8082

_latest_frame = None
_frame_lock = threading.Lock()
_running = True


def fetch_stream(upstream_url):
    """Background thread: continuously fetch MJPEG frames from the ESP32."""
    global _latest_frame, _running

    # Build an opener that bypasses system HTTP proxies (they can cause 502s
    # when hitting local / non-routable addresses like the ESP32 AP).
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    while _running:
        try:
            req = urllib.request.Request(
                upstream_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "*/*",
                },
            )
            with opener.open(req, timeout=10) as resp:
                print(f"[Proxy] Connected to upstream: {upstream_url}")
                buffer = bytearray()
                while _running:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    buffer.extend(chunk)

                    # Extract JPEG frames by scanning for SOI/EOI markers
                    while True:
                        soi = buffer.find(b"\xff\xd8")
                        if soi < 0:
                            break
                        eoi = buffer.find(b"\xff\xd9", soi + 2)
                        if eoi < 0:
                            break
                        frame = bytes(buffer[soi : eoi + 2])
                        with _frame_lock:
                            _latest_frame = frame
                        # Trim processed data, keep remainder for next frame
                        buffer = bytearray(buffer[eoi + 2 :])
        except Exception as e:
            print(f"[Proxy] Stream error: {e}")
            time.sleep(2)


class MJPEGHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/stream", "/stream/"):
            self._serve_mjpeg_stream()
        elif self.path in ("/snapshot", "/snapshot/"):
            self._serve_snapshot()
        else:
            self.send_error(404)

    def _serve_mjpeg_stream(self):
        """Serve a continuous MJPEG stream to the client."""
        self.send_response(200)
        self.send_header(
            "Content-Type", "multipart/x-mixed-replace; boundary=--frameboundary"
        )
        self.send_header(
            "Cache-Control",
            "no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0",
        )
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "-1")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            while _running:
                with _frame_lock:
                    frame = _latest_frame
                if frame:
                    self.wfile.write(b"--frameboundary\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n".encode())
                    self.wfile.write(b"\r\n")
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                time.sleep(0.033)  # ~30 fps cap
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_snapshot(self):
        """Serve the latest single JPEG frame."""
        with _frame_lock:
            frame = _latest_frame
        if frame:
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(frame)
        else:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"No frame available yet")

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Handle each client in a separate thread."""
    daemon_threads = True
    allow_reuse_address = True


def main():
    global _running, UPSTREAM_URL, PROXY_PORT

    parser = argparse.ArgumentParser(
        description="MJPEG Multi-Client Proxy for ESP32-S3-AI-Deck"
    )
    parser.add_argument(
        "--upstream",
        default=UPSTREAM_URL,
        help=f"Upstream ESP32 MJPEG URL (default: {UPSTREAM_URL})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=PROXY_PORT,
        help=f"Local proxy port (default: {PROXY_PORT})",
    )
    args = parser.parse_args()

    fetcher = threading.Thread(
        target=fetch_stream, args=(args.upstream,), daemon=True
    )
    fetcher.start()

    with ThreadedHTTPServer(("", args.port), MJPEGHandler) as httpd:
        print(f"[Proxy] MJPEG proxy running on http://localhost:{args.port}/stream")
        print(f"[Proxy] Snapshot: http://localhost:{args.port}/snapshot")
        print(f"[Proxy] Upstream: {args.upstream}")
        print("[Proxy] Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Proxy] Shutting down...")
            _running = False


if __name__ == "__main__":
    main()
