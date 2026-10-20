import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

from gateway.app import TelemetryStore, make_handler
from vfm.runtime import messages


def test_bounded_store_and_telemetry_api():
    store = TelemetryStore(capacity=3)
    rows = list(messages(5))
    for row in rows:
        store.add(row)
    assert store.recent() == rows[-3:]
    assert store.recent(2) == rows[-2:]

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/telemetry?limit=2") as response:
            payload = json.load(response)
        assert payload == {"schema_version": 1, "items": rows[-2:]}
        with urlopen(base + "/") as response:
            assert b"Pump overview" in response.read()
        with urlopen(base + "/app.js") as response:
            assert b"/api/telemetry" in response.read()
        with urlopen(base + "/styles.css") as response:
            assert response.status == 200
        try:
            urlopen(base + "/api/telemetry?limit=0")
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("invalid limit accepted")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
