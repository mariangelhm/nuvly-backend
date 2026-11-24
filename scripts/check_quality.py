"""Run the same read-only quality gates locally and in CI."""

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", action="store_true", help="Also run the offline regression suite")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    commands = [
        [sys.executable, "-m", "ruff", "check", "app", "scripts", "tests"],
        [sys.executable, "-m", "ruff", "format", "--check", "app", "scripts", "tests"],
        [sys.executable, "-m", "mypy"],
    ]
    if args.tests:
        commands.append([sys.executable, "-B", "scripts/test_offline.py"])
    for command in commands:
        print("Running:", " ".join(command[1:]), flush=True)
        result = subprocess.run(command, cwd=root, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
