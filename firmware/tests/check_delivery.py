"""Exercise actual delivery C logic with synthetic storage/transport boundaries."""
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CJSON = ROOT / ".tools/esp-idf-v5.5.5/components/json/cJSON"
with tempfile.TemporaryDirectory(prefix="sketch-delivery-") as directory:
    work = Path(directory)
    source = (ROOT / "firmware/main/app_delivery.c").read_text()
    for name in re.findall(r'#include "([^"]+)"', source):
        if name in ("app_delivery.h", "app_ui.h", "cJSON.h"):
            continue
        stub = work / name
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text("/* Synthetic host boundary; never used by firmware builds. */\n")
    shared = ["clang", "-std=c11", "-g", "-fsanitize=address,undefined", "-I" + str(work),
              "-I" + str(CJSON), "-I" + str(ROOT / "firmware/main")]
    subprocess.run(shared + ["-Wno-deprecated-declarations", "-c", str(CJSON / "cJSON.c"), "-o", str(work / "json.o")], check=True)
    subprocess.run(shared + ["-Wall", "-Wextra", "-Werror", "-Wno-deprecated-declarations",
                   str(ROOT / "firmware/tests/delivery_test.c"), str(ROOT / "firmware/main/app_spec.c"),
                   str(work / "json.o"), "-o", str(work / "delivery")], check=True)
    subprocess.run([str(work / "delivery"), str(ROOT / "contracts/fixtures/tap-sprint.json"),
                    str(ROOT / "contracts/fixtures/focus-timer.json")], check=True)
