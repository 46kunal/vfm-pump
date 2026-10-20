"""Lead-owned compatibility tests spanning device, gateway and UI."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from jsonschema import Draft202012Validator

from vfm.runtime import messages, telemetry

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/telemetry.schema.json").read_text())


def test_fixture_and_runtime_share_contract():
    Draft202012Validator.check_schema(SCHEMA)
    validator = Draft202012Validator(SCHEMA)
    validator.validate(json.loads((ROOT / "contracts/examples/telemetry.json").read_text()))
    output = list(messages(50))
    assert len({message["boot_id"] for message in output}) == 1
    assert [message["sequence"] for message in output] == list(range(50))
    assert all(a["t_s"] < b["t_s"] for a, b in zip(output, output[1:]))
    for message in output:
        validator.validate(message)
        json.dumps(message, allow_nan=False)
        assert message["source"] == "simulation"
        assert message["mode"] == "manual"
        assert message["model_version"] == 0


def test_invalid_path_values_are_json_null():
    estimate = dict(t=1, Q=float("nan"), sigma=float("inf"),
                    Q_h=float("-inf"), Q_p=4, conf="low", valid=False)
    supervisor = SimpleNamespace(model_changes=0, state=SimpleNamespace(name="MONITOR"),
                                 mode="manual")
    output = telemetry(estimate, supervisor, "test", "boot", 0)
    assert output["flow_l_min"] is None
    assert output["sigma_l_min"] is None
    assert output["head_flow_l_min"] is None
    assert output["power_flow_l_min"] == 4
    Draft202012Validator(SCHEMA).validate(output)
    json.dumps(output, allow_nan=False)


def test_runtime_cli_emits_parseable_messages():
    result = subprocess.run(
        [sys.executable, "-m", "vfm.runtime", "--steps", "3"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    output = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(output) == 3
    for message in output:
        Draft202012Validator(SCHEMA).validate(message)
