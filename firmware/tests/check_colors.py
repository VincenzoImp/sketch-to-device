#!/usr/bin/env python3
"""Check real native parsing, contrast and navigation; no display or hardware claim."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from runtime.validation import ValidationError, parse_app


def main():
    cjson = ROOT / ".tools/esp-idf-v5.5.5/components/json/cJSON"
    original = json.loads((ROOT / "contracts/fixtures/tap-sprint.json").read_text())
    cases = [(original, True)]
    for value in ("#000000", "#FFFFFF", "#ff69b4", "#aBcD09", None, True, 0, {}, [],
                  "#123", "#12345678", "#12345g", "123456", " #123456", "#123456\n",
                  "#１２３４５６", "#123456\0ignored", "#-12345"):
        candidate = copy.deepcopy(original)
        candidate["screens"][0]["widgets"][-1]["background_color"] = value
        cases.append((candidate, value in ("#000000", "#FFFFFF", "#ff69b4", "#aBcD09")))
    for screen in range(len(original["screens"])):
        for index, widget in enumerate(original["screens"][screen]["widgets"]):
            if widget["type"] != "button":
                candidate = copy.deepcopy(original)
                candidate["screens"][screen]["widgets"][index]["background_color"] = "#FF69B4"
                cases.append((candidate, False))
    focus = json.loads((ROOT / "contracts/fixtures/focus-timer.json").read_text())
    cases.append((copy.deepcopy(focus), True))
    for screen in focus["screens"]:
        for widget in screen["widgets"]:
            if widget["type"] == "toggle":
                widget["background_color"] = "#FF69B4"
    cases.append((focus, False))
    cycle = copy.deepcopy(original)
    cycle.update(app_id="color_cycle", name="Hello World", initial_screen="pink", state={})
    names, colors = ("pink", "blue", "green"), ("#FF69B4", "#164ead", "#80FF80")
    cycle["screens"] = [{"id": name, "title": "Hello World", "widgets": [{
        "id": name + "_button", "type": "button", "text": "Change color", "background_color": colors[i],
        "on_press": [{"type": "navigate", "screen_id": names[(i + 1) % 3]}]}]}
        for i, name in enumerate(names)]
    cases.append((cycle, True))
    with tempfile.TemporaryDirectory(prefix="sketch-colors-") as temporary:
        folder = Path(temporary)
        common = ["clang", "-std=c11", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                  "-I" + str(cjson), "-I" + str(ROOT / "firmware/main")]
        subprocess.run(common + ["-Wno-deprecated-declarations", "-c", str(cjson / "cJSON.c"),
                                 "-o", str(folder / "cjson.o")], check=True)
        for name, source in (("parse", "core_test.c"), ("cycle", "color_test.c")):
            subprocess.run(common + ["-Wall", "-Wextra", "-Werror", str(ROOT / "firmware/tests" / source),
                                     str(ROOT / "firmware/main/app_spec.c"), str(folder / "cjson.o"),
                                     "-o", str(folder / name)], check=True)
        path = folder / "candidate.json"
        for number, (candidate, expected) in enumerate(cases):
            raw = json.dumps(candidate, separators=(",", ":")).encode()
            path.write_bytes(raw)
            try:
                parse_app(raw)
                host = True
            except ValidationError:
                host = False
            native = subprocess.run([str(folder / "parse"), "--validate", str(path)],
                                    capture_output=True, timeout=3)
            assert native.returncode in (0, 1) and not native.stderr, "Native crash or sanitizer failure"
            assert host == expected == (native.returncode == 0), "Color case {} disagrees".format(number)
        path.write_text(json.dumps(cycle))
        subprocess.run([str(folder / "cycle"), str(path)], check=True, timeout=3)
    print("PASS: {} explicit native/host color cases under ASan/UBSan".format(len(cases)))


if __name__ == "__main__":
    main()
