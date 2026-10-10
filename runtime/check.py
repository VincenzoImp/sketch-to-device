"""CLI for exact-byte validation and optional headless scenario execution."""

import argparse
import json
import sys

from .reference import ReferenceRuntime
from .scenarios import run_scenario
from .validation import LIMITS, ValidationError, package_report


def _read(path):
    with open(path, "rb") as source:
        return source.read(LIMITS["max_app_bytes"] + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package")
    parser.add_argument("--scenario")
    args = parser.parse_args()
    try:
        raw = _read(args.package)
        report = package_report(raw)
        if args.scenario:
            report["scenario"] = run_scenario(ReferenceRuntime(raw), _read(args.scenario))
    except ValidationError as error:
        print(json.dumps({"valid": False, "error": error.as_dict()}))
        return 1
    except (OSError, ValueError, AssertionError) as error:
        print(json.dumps({"valid": False, "error": {"code": type(error).__name__, "message": str(error)}}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
