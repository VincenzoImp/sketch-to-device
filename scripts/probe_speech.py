#!/usr/bin/env python3
"""Compare two fixed Gradium profiles on one frozen recording; never generate or install."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT))
from backend.generator import _convert, requirements_for
from backend.providers import ERROR_MESSAGES, ProviderError, STT_CONFIGS, STT_PATHS, load_keys, parse_transcript, request, wav_duration
from backend.server import save_private
from scripts.probe_providers import SafeParser
from scripts.replay_generation import ReplayError, frozen_input


def compare(directory, output):
    """Keep identical decoded audio for both requests and private raw transcripts."""
    started = time.monotonic()
    deadline = started + 90
    _, snapshots = frozen_input(directory)
    recordings = [(mime, raw) for mime, raw in snapshots if not mime.startswith("image/")]
    if len(recordings) != 1:
        raise ReplayError("speech_comparison_needs_one_recording")
    mime, raw = recordings[0]
    wav, _ = _convert(raw, mime, deadline)
    if wav is None:
        raise ReplayError("speech_comparison_needs_one_recording")
    wav_duration(wav)
    keys = load_keys(ROOT / ".env")
    result = {"result": "compared", "audio_sha256": hashlib.sha256(wav).hexdigest(), "profiles": [],
              "accuracy_verified": False, "production_changed": False, "device_installed": False}
    transcripts = []
    for profile in ("default", "runtime_context"):
        began = time.monotonic()
        # Two calls at most, each capped at 30 seconds within the shared 90-second budget.
        response = request("gradium", keys["gradium"], STT_PATHS[profile], wav, "audio/wav",
                           min(deadline, began + 30), 131072)
        transcript = parse_transcript(response)
        words = set(re.findall(r"[a-z]+", transcript.lower()))
        observation = {"profile": profile, "elapsed_ms": round((time.monotonic() - began) * 1000),
                       "characters": len(transcript),
                       "runtime_words": sorted(words & {"tap", "timer", "countdown", "score", "button", "toggle"})}
        try:
            observation["requirements"] = requirements_for(transcript)
        except ProviderError:
            # An unrepresentable recognized request is evidence, not an ASR failure.
            observation["requirements_error"] = "outside_runtime_limits"
        result["profiles"].append(observation)
        transcripts.append({"profile": profile, "configuration": STT_CONFIGS[profile], "transcript": transcript})
    result["observed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    save_private(output / "speech-comparison.json", {"summary": result, "transcripts": transcripts})
    return result


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--last-failed", action="store_true")
    args = parser.parse_args(argv)
    if not (args.live and args.last_failed):
        print(json.dumps({"result": "live_not_requested", "requests_sent": 0}))
        return 0
    try:
        result = compare(ROOT / "private/service", ROOT / "private/provider")
    except Exception as exc:
        code = getattr(exc, "code", None)
        allowed = set(ERROR_MESSAGES) | {"speech_comparison_needs_one_recording", "generation_busy",
                                         "replay_no_failed_job", "replay_input_invalid"}
        result = {"result": "failed", "code": code if type(code) is str and code in allowed else "speech",
                  "production_changed": False, "device_installed": False}
    print(json.dumps(result))
    return 0 if result["result"] == "compared" else 1


if __name__ == "__main__":
    raise SystemExit(main())
