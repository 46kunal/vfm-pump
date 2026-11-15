"""Local gateway: real ESP32 sensor readings over HTTP, shown on the dashboard.

Nothing here generates data. The ESP32 (directly or through tools/serial_bridge.py)
posts readings to /api/hardware/..., and the dashboard reads them back.
"""

import argparse
from collections import deque
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit

from gateway.hardware import HardwareStore, ReadingError, UnknownSensor, SENSORS


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "dashboard"
MAX_BODY = 4096
JSON = "application/json; charset=utf-8"


class TelemetryStore:
    """Estimated-flow telemetry v1. Stays empty until a calibrated estimator feeds it."""

    def __init__(self, capacity=300):
        self.capacity = capacity
        self._items = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def add(self, message):
        with self._lock:
            self._items.append(message)

    def recent(self, limit=120):
        with self._lock:
            return list(self._items)[-limit:]


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


def make_handler(store, hardware=None, token=None):
    hardware = hardware if hardware is not None else HardwareStore()

    class Handler(BaseHTTPRequestHandler):
        def reply(self, body, mime, status=200):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def reply_json(self, payload, status=200):
            self.reply(json.dumps(payload, allow_nan=False).encode("utf-8"), JSON, status)

        def error(self, status, message):
            self.reply_json({"error": message}, status)

        def limit(self, parsed, maximum):
            try:
                limit = int(parse_qs(parsed.query).get("limit", ["120"])[0])
                if not 1 <= limit <= maximum:
                    raise ValueError
            except ValueError:
                self.error(400, f"limit must be between 1 and {maximum}")
                return None
            return limit

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/api/telemetry":
                limit = self.limit(parsed, store.capacity)
                if limit is not None:
                    self.reply_json({"schema_version": 1, "items": store.recent(limit)})
                return
            if parsed.path == "/api/hardware/latest":
                self.reply_json(hardware.snapshot())
                return
            if parsed.path == "/api/hardware/history":
                sensor = parse_qs(parsed.query).get("sensor", [""])[0]
                limit = self.limit(parsed, hardware.history_capacity)
                if limit is None:
                    return
                try:
                    items = hardware.history(sensor, limit)
                except UnknownSensor:
                    self.error(400, "sensor must be one of: " + ", ".join(SENSORS))
                    return
                self.reply_json({"sensor": sensor, "items": items})
                return
            assets = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            }
            if parsed.path in assets:
                filename, mime = assets[parsed.path]
                self.reply((WEB / filename).read_bytes(), mime)
                return
            self.error(404, "not found")

        def do_POST(self):
            prefix = "/api/hardware/"
            path = urlsplit(self.path).path
            if not path.startswith(prefix):
                self.error(404, "not found")
                return
            if token and not hmac.compare_digest(self.headers.get("X-VFM-Token", ""), token):
                self.error(401, "missing or wrong X-VFM-Token")
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self.error(411, "Content-Length required")
                return
            if length <= 0:
                self.error(400, "empty body")
                return
            if length > MAX_BODY:
                self.error(413, f"body larger than {MAX_BODY} bytes")
                return
            try:
                payload = json.loads(self.rfile.read(length), parse_constant=_reject_constant)
            except ValueError as problem:
                self.error(400, f"invalid JSON: {problem}")
                return
            name = path[len(prefix):]
            readings = payload if name == "sample" else {name: payload}
            try:
                received = hardware.update_many(readings)
            except UnknownSensor as problem:
                self.error(404, str(problem))
            except ReadingError as problem:
                self.error(400, str(problem))
            else:
                self.reply_json({"ok": True, "received": received})

        def log_message(self, fmt, *args):
            if self.command != "POST":
                super().log_message(fmt, *args)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1",
                        help="use 0.0.0.0 only if the ESP32 posts over Wi-Fi")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default=None,
                        help="require this X-VFM-Token header on every POST")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port),
                                 make_handler(TelemetryStore(), HardwareStore(), args.token))
    print(f"Virtual flow meter: http://{args.host}:{server.server_port}", flush=True)
    print("Waiting for ESP32 readings: POST /api/hardware/<sensor> or /api/hardware/sample",
          flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
