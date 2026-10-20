import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ownership_check", ROOT / "tools/check_ownership.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
OWNERSHIP = json.loads((ROOT / "team/ownership.json").read_text())


def test_owned_nested_paths_and_shared_files():
    assert checker.outside_scope(
        ["gateway/app.py", "tests/gateway/test_storage.py"], "c", OWNERSHIP
    ) == []
    assert checker.outside_scope(
        ["vfm/fastloop.py", "contracts/telemetry.schema.json", "config.json"],
        "c", OWNERSHIP,
    ) == ["vfm/fastloop.py", "contracts/telemetry.schema.json", "config.json"]
    assert checker.outside_scope(["gateway/app.py"], "d", OWNERSHIP)
    assert checker.outside_scope(["gateway/src/mqtt.py"], "c", OWNERSHIP) == []
    assert checker.outside_scope(["vfm/runtime.py"], "c", OWNERSHIP)


def test_git_scope_includes_committed_working_and_untracked(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path)
    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / "base.txt").write_text("base")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD").decode().strip()
    (tmp_path / "committed.txt").write_text("feature")
    git("add", ".")
    git("commit", "-qm", "feature")
    (tmp_path / "base.txt").write_text("edited")
    (tmp_path / "untracked.txt").write_text("untracked")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    assert checker.changed_paths(base) == ["base.txt", "committed.txt", "untracked.txt"]
