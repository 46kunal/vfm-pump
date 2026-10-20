"""Check feature-branch file scope; this is a workflow aid, not access control."""
import argparse
import fnmatch
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")


def changed_paths(base):
    ancestor = git("merge-base", base, "HEAD").strip()
    # Compare the ancestor to the working tree: committed, staged and unstaged.
    tracked = git("diff", "--no-renames", "--name-only", "-z", ancestor)
    untracked = git("ls-files", "--others", "--exclude-standard", "-z")
    return sorted(set(filter(None, (tracked + untracked).split("\0"))))


def outside_scope(paths, role, ownership):
    patterns = ownership[role]
    return [path for path in paths
            if not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=["a", "b", "c", "d"])
    parser.add_argument("--base", required=True, help="Fetched base ref, e.g. origin/main")
    args = parser.parse_args()
    ownership = json.loads((ROOT / "team/ownership.json").read_text())
    try:
        paths = changed_paths(args.base)
    except subprocess.CalledProcessError:
        parser.exit(2, "Cannot resolve Git base. Fetch the target branch and retry.\n")
    violations = outside_scope(paths, args.role, ownership)
    if violations:
        print("Shared or other-role paths require a separate integration PR:")
        print("\n".join(f"  {path}" for path in violations))
        return 1
    print(f"Role {args.role.upper()}: {len(paths)} changed paths are within scope.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
