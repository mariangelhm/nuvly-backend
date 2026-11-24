"""Collect operational evidence without exposing credentials or application data."""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, help="Configuration file; defaults to the backend .env")
    parser.add_argument("--exercise-database", help="Explicit opt-in: creates fixtures in a new nuvly_validation_* DB")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from app.core.config import Settings
    from app.operations.staging_validation import (
        connect,
        exercise_isolated_database,
        read_only_report,
        validate_isolated_target,
    )

    client = None
    try:
        settings = Settings(_env_file=args.env_file if args.env_file is not None else root / ".env")
        if args.exercise_database:
            validate_isolated_target(settings, args.exercise_database)
            client = connect(settings)
            report = exercise_isolated_database(settings, client, args.exercise_database)
        else:
            report = read_only_report(settings)
    except Exception as error:
        # Avoid writing str(error), traceback, URI, tokens or customer documents.
        report = {"phaseComplete": False, "checks": {}, "errorType": type(error).__name__}
    finally:
        if client is not None:
            client.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report.get("checks") and all(check["status"] == "passed" for check in report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
