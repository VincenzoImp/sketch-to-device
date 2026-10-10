#!/usr/bin/env python3
"""Execute SDK examples with the actual reference runtime; no hardware claim."""

import hashlib
import json
from pathlib import Path
import sys

SDK = Path(__file__).resolve().parent
sys.path.insert(0, str(SDK.parent))
from runtime.reference import ReferenceRuntime
from runtime.scenarios import run_scenario


def run(name):
    if name not in {"counter", "settings", "timer", "colors"}:
        raise ValueError("Unknown SDK example")
    raw = (SDK / "examples" / (name + ".json")).read_bytes()
    scenario = (SDK / "scenarios" / (name + ".json")).read_bytes()
    result = run_scenario(ReferenceRuntime(raw), scenario)
    return {"example": name, "sha256": hashlib.sha256(raw).hexdigest(),
            "checkpoints": result["checkpoints"], "evidence": "reference_runtime_only"}


if __name__ == "__main__":
    names = sys.argv[1:] or ["counter", "settings", "timer", "colors"]
    for example in names:
        print(json.dumps(run(example)))
