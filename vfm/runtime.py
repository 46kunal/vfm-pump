"""Finite simulation telemetry starter. Run with python -m vfm.runtime."""
import argparse
from itertools import count
import json
import math
from pathlib import Path
import sys
import uuid

from .config import load
from .fastloop import FastLoop
from .sim import SimHAL
from .supervisor import ScriptedOperator, Supervisor


def finite_or_none(value):
    return float(value) if value is not None and math.isfinite(value) else None


def telemetry(estimate, supervisor, device_id, boot_id, sequence):
    return {
        "schema_version": 1,
        "device_id": device_id,
        "boot_id": boot_id,
        "sequence": sequence,
        "source": "simulation",
        "t_s": float(estimate["t"]),
        "model_version": supervisor.model_changes,
        "flow_l_min": finite_or_none(estimate["Q"]),
        "sigma_l_min": finite_or_none(estimate["sigma"]),
        "head_flow_l_min": finite_or_none(estimate["Q_h"]),
        "power_flow_l_min": finite_or_none(estimate["Q_p"]),
        "confidence": estimate["conf"],
        "valid": bool(estimate["valid"]),
        "state": supervisor.state.name,
        "mode": supervisor.mode,
    }


def messages(steps=20, seed=0, device_id="sim-pump-01"):
    cfg = load()
    hal = SimHAL(cfg, seed=seed)
    fast = FastLoop(cfg)
    # No external command handling yet; this starter never approves updates.
    operator = ScriptedOperator(sweep="reject", update="reject")
    supervisor = Supervisor(cfg, fast, hal, operator, mode="manual")
    boot_id = str(uuid.uuid4())
    for sequence in count() if steps is None else range(steps):
        sample = hal.read_sensors()
        estimate = fast.update(sample)
        supervisor.tick(sample, estimate)
        yield telemetry(estimate, supervisor, device_id, boot_id, sequence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be positive")
    stream = sys.stdout
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        stream = args.output.open("w", encoding="utf-8")
    try:
        for message in messages(args.steps, args.seed):
            stream.write(json.dumps(message, allow_nan=False) + "\n")
    finally:
        if args.output:
            stream.close()


if __name__ == "__main__":
    main()
