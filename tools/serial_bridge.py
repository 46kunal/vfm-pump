"""Forward JSON lines from the ESP32's USB serial port to the gateway.

The ESP32 prints one JSON object per line, e.g.
  {"ina219":{"volts":12.3,"amps":0.62},"ds18b20":{"temp_c":24.5},"hx711":{"raw":-566400}}
Each line is posted to /api/hardware/sample. Boot messages and other non-JSON lines
are ignored. Close the Arduino Serial Monitor first: only one program can open the port.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def forward_line(line, base_url, token=None, timeout=2.0):
    """Post one serial line. Returns (status, detail); status is skip, ok or error."""
    line = line.strip()
    if not line.startswith("{"):
        return "skip", line
    try:
        payload = json.loads(line)
    except ValueError:
        return "skip", line
    if not isinstance(payload, dict):
        return "skip", line
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-VFM-Token"] = token
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/hardware/sample",
        data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return "ok", response.read().decode("utf-8")
    except urllib.error.HTTPError as problem:
        return "error", f"gateway rejected the reading ({problem.code}): " + \
            problem.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as problem:
        return "error", f"gateway unreachable: {problem}"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="serial port, e.g. COM13")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--gateway", default="http://127.0.0.1:8765")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()
    try:
        import serial
    except ImportError:
        sys.exit("pyserial is missing. Run: python -m pip install pyserial")

    sent = failed = 0
    while True:
        try:
            with serial.Serial(args.port, args.baud, timeout=2) as port:
                print(f"Reading {args.port} at {args.baud} baud. Press Ctrl+C to stop.", flush=True)
                while True:
                    raw = port.readline().decode("utf-8", "replace")
                    if not raw:
                        continue
                    status, detail = forward_line(raw, args.gateway, args.token)
                    if status == "ok":
                        sent += 1
                        if sent % 20 == 1:
                            print(f"sent {sent} readings", flush=True)
                    elif status == "error":
                        failed += 1
                        print(detail, flush=True)
        except serial.SerialException as problem:
            print(f"Serial port problem: {problem}. Retrying in 3 s...", flush=True)
            time.sleep(3)
        except KeyboardInterrupt:
            print(f"Stopped. Sent {sent}, rejected or failed {failed}.")
            return


if __name__ == "__main__":
    main()
