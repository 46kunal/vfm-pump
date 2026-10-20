"""Local gateway baseline: simulator telemetry over a read-only HTTP API."""

import argparse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit

from vfm.config import load
from vfm.runtime import messages


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "dashboard"


class TelemetryStore:
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


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, body, mime, status=200):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/api/telemetry":
                try:
                    raw = parse_qs(parsed.query).get("limit", ["120"])[0]
                    limit = int(raw)
                    if not 1 <= limit <= store.capacity:
                        raise ValueError
                except ValueError:
                    self.reply(b'{"error":"limit must be between 1 and 300"}',
                               "application/json; charset=utf-8", 400)
                    return
                body = json.dumps({"schema_version": 1, "items": store.recent(limit)},
                                  allow_nan=False).encode("utf-8")
                self.reply(body, "application/json; charset=utf-8")
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
            self.reply(b'{"error":"not found"}', "application/json; charset=utf-8", 404)

    return Handler


def start_simulator(store, stop, seed=0):
    dt = load()["dt"]

    def run():
        for message in messages(steps=None, seed=seed):
            if stop.is_set():
                break
            store.add(message)
            if stop.wait(dt):
                break

    worker = threading.Thread(target=run, name="simulator", daemon=True)
    worker.start()
    return worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    store = TelemetryStore()
    stop = threading.Event()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store))
    worker = start_simulator(store, stop, args.seed)
    print(f"Virtual flow meter: http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=2)


if __name__ == "__main__":
    main()
