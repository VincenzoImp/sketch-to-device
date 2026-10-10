#!/usr/bin/env python3
"""Fetch and test an isolated QuickJS-NG dependency; never flash a device.

Without flags this only inspects local status. --fetch downloads public source
from the official registry, verifies its component hash and records exact pins.
No provider/device credentials or running firmware configuration are read.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / ".tools/quickjs-probe"
SOURCE = BASE / "quickjs-ng"
PIN = BASE / "source-pin.json"
VERSION = "0.14.0"
COMMIT = "0d0b99456ce9112f4ac4838927ba837949359f9b"
METADATA_URL = "https://components.espressif.com/api/components/espressif/quickjs-ng"
ARCHIVE_URL = ("https://components.espressif.com/api/downloads/?"
               "object_id=68c9c504-e08b-4545-a117-4222f2d80ee4&object_type=component")
IDF_PYTHON = ROOT / ".tools/espressif/python_env/idf5.5_py3.9_env/bin/python"
MAX_ARCHIVE = 2 * 1024 * 1024
MAX_EXPANDED = 12 * 1024 * 1024


class ProbeError(Exception):
    """A fixed non-sensitive failure code."""


def allowed_url(url):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname is not None
            and (parsed.hostname == "espressif.com"
                 or parsed.hostname.endswith(".espressif.com"))
            and parsed.port in (None, 443) and not parsed.username
            and not parsed.password and not parsed.fragment)


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise ProbeError("non_official_redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, limit, deadline):
    if not allowed_url(url):
        raise ProbeError("non_official_url")
    # Ignore ambient proxy credentials; only public HTTPS source is requested.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), OfficialRedirect())
    chunks, total = [], 0
    with opener.open(url, timeout=min(15, max(0.1, deadline - time.monotonic()))) as response:
        if response.status != 200 or not allowed_url(response.geturl()):
            raise ProbeError("download_response_invalid")
        while True:
            if time.monotonic() >= deadline:
                raise ProbeError("download_timeout")
            data = response.read1(min(65536, limit + 1 - total))
            if not data:
                return b"".join(chunks)
            total += len(data)
            if total > limit:
                raise ProbeError("download_size_limit")
            chunks.append(data)


def registry_hash(data):
    try:
        document = json.loads(data)
        if document["namespace"] != "espressif" or document["name"] != "quickjs-ng":
            raise ValueError()
        matches = [item for item in document["versions"] if item["version"] == VERSION]
        if len(matches) != 1 or matches[0].get("yanked_at"):
            raise ValueError()
        digest = matches[0]["component_hash"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError()
        return digest
    except (ValueError, KeyError, TypeError):
        raise ProbeError("registry_metadata_invalid") from None


def extract_archive(data, target):
    """Extract regular files only into a fresh private directory."""
    seen, expanded = set(), 0
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        entries = archive.infolist()
        if not entries or len(entries) > 2000:
            raise ProbeError("archive_entry_limit")
        for item in entries:
            name = item.filename
            parts = PurePosixPath(name).parts
            mode = item.external_attr >> 16
            if (not name or "\\" in name or "\x00" in name
                    or name.startswith("/") or any(p in ("..", ".") for p in parts)
                    or ":" in name or name.casefold() in seen
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))
                    or item.flag_bits & 1):
                raise ProbeError("unsafe_archive_entry")
            seen.add(name.casefold())
            expanded += item.file_size
            if expanded > MAX_EXPANDED or item.file_size > 4 * 1024 * 1024:
                raise ProbeError("archive_expansion_limit")
            path = target.joinpath(*parts)
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as output:
                    os.chmod(path, 0o600)
                    output.write(archive.read(item))
    except (zipfile.BadZipFile, OSError, RuntimeError):
        raise ProbeError("archive_invalid") from None


def component_hash(path):
    # Use the installed official algorithm, including its canonical exclusions.
    code = '''import sys
from pathlib import Path
import yaml
from idf_component_tools.hash_tools.calculate import hash_dir
def require(ok, code):
    if not ok:
        print(code)
        raise SystemExit(1)
p = Path(sys.argv[1])
require(not any(f.is_symlink() for f in p.rglob('*')), 'source_symlink')
require((p/'idf_component.yml').is_file(), 'manifest_missing')
m = yaml.safe_load((p/'idf_component.yml').read_text())
require(isinstance(m, dict), 'manifest_invalid')
require(m.get('version') == '0.14.0', 'manifest_version')
require(m.get('dependencies') == {'idf': '>=5.4'}, 'manifest_dependencies')
require(m.get('repository') in ('https://github.com/espressif/esp-iot-solution.git',
        'git://github.com/espressif/esp-iot-solution.git'), 'manifest_repository')
require(m.get('repository_info') == {'commit_sha': '0d0b99456ce9112f4ac4838927ba837949359f9b',
        'path': 'components/quickjs-ng'}, 'manifest_source_pin')
require((p/'quickjs-ng/quickjs.c').is_file(), 'engine_c_missing')
require((p/'quickjs-ng/quickjs.h').is_file(), 'engine_h_missing')
print(hash_dir(p))
'''
    try:
        result = subprocess.run([str(IDF_PYTHON), "-c", code, str(path)],
                                capture_output=True, timeout=15, check=False)
        digest = result.stdout.decode().strip()
        if result.returncode:
            allowed = {"source_symlink", "manifest_missing", "manifest_invalid", "manifest_version",
                       "manifest_dependencies", "manifest_repository", "manifest_source_pin",
                       "engine_c_missing", "engine_h_missing"}
            if digest in allowed:
                raise ProbeError("component_" + digest)
            raise ProbeError("component_validation_failed")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError()
        return digest
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ProbeError("component_validation_failed") from None


def status():
    if not SOURCE.exists() and not PIN.exists():
        return {"status": "dependency_absent", "version": VERSION}
    try:
        if SOURCE.is_symlink() or PIN.is_symlink():
            raise ValueError()
        pin = json.loads(PIN.read_text())
        if (pin["version"] != VERSION or pin["registry_source_commit"] != COMMIT
                or component_hash(SOURCE) != pin["component_hash"]):
            raise ValueError()
        return {"status": "dependency_verified", "version": VERSION,
                "component_hash": pin["component_hash"], "archive_sha256": pin["archive_sha256"]}
    except (OSError, ValueError, KeyError, TypeError):
        raise ProbeError("existing_dependency_changed") from None


def fetch():
    if SOURCE.exists() or PIN.exists():
        return status()
    if BASE.is_symlink():
        raise ProbeError("unsafe_dependency_directory")
    BASE.mkdir(parents=True, exist_ok=True)
    def expired(_signum, _frame):
        raise ProbeError("download_timeout")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 45)
    try:
        deadline = time.monotonic() + 40
        cached = BASE / "download.zip"
        cached_pin = BASE / "download-pin.json"
        if cached.exists() or cached_pin.exists():
            if (cached.is_symlink() or cached_pin.is_symlink() or not cached.is_file()
                    or not cached_pin.is_file() or cached.stat().st_size > MAX_ARCHIVE
                    or cached_pin.stat().st_size > 4096):
                raise ProbeError("cached_download_changed")
            cache = json.loads(cached_pin.read_text())
            data = cached.read_bytes()
            digest = cache["component_hash"]
            if (not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or len(data) > MAX_ARCHIVE
                    or hashlib.sha256(data).hexdigest() != cache["archive_sha256"]):
                raise ProbeError("cached_download_changed")
        else:
            digest = registry_hash(download(METADATA_URL, 512 * 1024, deadline))
            data = download(ARCHIVE_URL, MAX_ARCHIVE, deadline)
            # Public source retained for diagnosis; never executed before validation.
            for path, value in ((cached, data), (cached_pin, json.dumps({
                    "component_hash": digest, "archive_sha256": hashlib.sha256(data).hexdigest()
            }).encode())):
                with path.open("xb") as output:
                    os.chmod(path, 0o600)
                    output.write(value)
        with tempfile.TemporaryDirectory(prefix="source-", dir=BASE) as temporary:
            extracted = Path(temporary) / "quickjs-ng"
            extracted.mkdir()
            extract_archive(data, extracted)
            # The registry's fixed download endpoint wraps this component in one
            # quickjs-ng directory. Storage archives may already have a flat root.
            if not (extracted / "idf_component.yml").is_file():
                children = list(extracted.iterdir())
                if len(children) == 1 and children[0].name == "quickjs-ng" and children[0].is_dir():
                    extracted = children[0]
            if component_hash(extracted) != digest:
                raise ProbeError("registry_hash_mismatch")
            pin = {"version": VERSION, "component_hash": digest,
                   "archive_sha256": hashlib.sha256(data).hexdigest(), "archive_size": len(data),
                   "registry_source_commit": COMMIT,
                   "source_commit_evidence": "registry_hash_and_archive_repository_info"}
            # All checks precede installation. An interrupted pin write fails closed.
            extracted.rename(SOURCE)
            with PIN.open("x") as output:
                os.chmod(PIN, 0o600)
                json.dump(pin, output, indent=2)
                output.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ProbeError("download_unavailable") from error
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    return status()


def run_logged(command, log_name, timeout):
    path = BASE / log_name
    with path.open("w") as log:
        os.chmod(path, 0o600)
        try:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise ProbeError("probe_process_unavailable_or_timeout") from None
    if result.returncode:
        raise ProbeError("probe_process_failed")
    return path


def host():
    if status()["status"] != "dependency_verified":
        raise ProbeError("fetch_required")
    source = SOURCE / "quickjs-ng"
    probe = ROOT / "firmware/probes/quickjs/probe.c"
    binary = BASE / "host-probe"
    flags = ["clang", "-std=c11", "-O1", "-g", "-D_GNU_SOURCE", "-funsigned-char",
             "-fno-omit-frame-pointer", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
             "-I", str(source)]
    run_logged(flags + ["-Wall", "-Wextra", "-Werror", "-c", str(probe),
                       "-o", str(BASE / "probe.o")], "host-own-build.log", 30)
    run_logged(flags + [str(source / name) for name in
                       ("dtoa.c", "libregexp.c", "libunicode.c", "quickjs.c")]
               + [str(BASE / "probe.o"), "-lm", "-pthread", "-o", str(binary)],
               "host-engine-build.log", 120)
    path = run_logged([str(binary)], "host-run.log", 20)
    try:
        result = json.loads(path.read_text())
        if result["status"] != "engine_checks_passed" or result["residual_bytes"] != 0:
            raise ValueError()
    except (ValueError, KeyError):
        raise ProbeError("host_result_invalid") from None
    result["platform"] = "native_host_asan_ubsan"
    return result


def target_result():
    """Report only an actual matching target build, without rebuilding it."""
    header = BASE / "target-build/config/sdkconfig.h"
    required = ('#define CONFIG_IDF_TARGET "esp32p4"',
                '#define CONFIG_IDF_INIT_VERSION "5.5.5"',
                '#define CONFIG_ESP32P4_REV_MIN_FULL 300',
                '#define CONFIG_ESPTOOLPY_FLASHSIZE_16MB 1')
    try:
        lines = header.read_text().splitlines()
    except OSError:
        raise ProbeError("target_configuration_missing") from None
    if not all(line in lines for line in required):
        raise ProbeError("target_configuration_mismatch")
    binary = BASE / "target-build/quickjs_feasibility.bin"
    if not binary.is_file():
        raise ProbeError("target_binary_missing")
    data = binary.read_bytes()
    return {"status": "target_cross_build_passed", "platform": "esp32p4_rev3",
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "physical_execution": False, "flashed": False}


def target():
    if status()["status"] != "dependency_verified":
        raise ProbeError("fetch_required")
    run_logged(["bash", str(ROOT / "firmware/probes/quickjs/build.sh")], "target-build.log", 240)
    return target_result()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="download and verify public engine source")
    parser.add_argument("--host", action="store_true", help="compile and run actual native engine checks")
    parser.add_argument("--target", action="store_true", help="cross-build isolated P4rev3 probe; never flash")
    args = parser.parse_args()
    try:
        result = fetch() if args.fetch else status()
        if args.host:
            result = host()
        if args.target:
            result = target()
    except ProbeError as error:
        print(json.dumps({"status": "failed", "error_code": str(error)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
