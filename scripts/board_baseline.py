#!/usr/bin/env python3
"""Back up the confirmed P4 and flash a vendor baseline or configured runtime.

No operation without an explicit action. Flashing requires a complete 16 MB
backup with its recorded SHA-256. Runtime flashing first builds the private
configuration; initial app storage setup requires --initialize-app-storage.
Output contains no raw serial contents or credentials.
"""

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from identify_board import IDF_PYTHON, parse_output
from probe_hardware import serial_candidates

ROOT = Path(__file__).absolute().parent.parent
BACKUP = ROOT / "private/board-baseline"
BUILD = ROOT / ".tools/waveshare-p4-35/examples/esp-idf/08_lvgl_demo_v9/build-rev3_x"
RUNTIME_BUILD = ROOT / "firmware/build"
SIZE = 16 * 1024 * 1024


def run(port, arguments, label, timeout):
    command = [str(IDF_PYTHON), "-u", "-I", "-m", "esptool", "--chip", "esp32p4",
               "--port", port, "--baud", "460800"] + arguments
    log = BACKUP / (label + ".log")
    descriptor = os.open(str(log), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        try:
            result = subprocess.run(command, cwd=str(BUILD), stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            # Preserve esptool's progress even when the wrapper deadline expires.
            raise RuntimeError(label + "_timeout") from None
    if result.returncode:
        raise RuntimeError(label + "_failed")
    return log.read_text(errors="replace")


def measure_read(port):
    probe = BACKUP / "read-probe.bin"
    if probe.is_symlink():
        raise RuntimeError("invalid_read_probe_path")
    descriptor = os.open(str(probe), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.close(descriptor)
    started = time.monotonic()
    run(port, ["read_flash", "0", "65536", str(probe)], "read-probe", 60)
    elapsed = time.monotonic() - started
    if probe.stat().st_size != 65536:
        raise RuntimeError("read_probe_size_mismatch")
    # Include connection overhead: conservative when projecting a small sample.
    # At 460800 baud a 16 MiB UART transfer alone needs at least 364 seconds.
    budget = min(1800, max(600, int(elapsed * (SIZE / 65536) * 1.5 + 60)))
    print(json.dumps({"stage": "flash_read_verified", "probe_bytes": 65536,
                      "elapsed_seconds": round(elapsed, 2), "backup_timeout_seconds": budget}), flush=True)
    return budget


def baseline(flash=False, runtime=False, initialize_apps=False):
    ports = serial_candidates()
    if len(ports) != 1:
        raise RuntimeError("unique_serial_required")
    if not IDF_PYTHON.is_file() or not BUILD.is_dir():
        raise RuntimeError("idf_and_vendor_build_required")
    BACKUP.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = parse_output(run(ports[0], ["--no-stub", "flash_id"], "identity", 30), 0)
    if (identity.get("chip_model"), identity.get("silicon_revision"), identity.get("flash_size")) != ("ESP32-P4", "3.2", "16MB"):
        raise RuntimeError("expected_board_and_flash_not_confirmed")
    backup, metadata = BACKUP / "original-flash.bin", BACKUP / "backup.json"
    if backup.exists() != metadata.exists():
        raise RuntimeError("incomplete_backup_requires_inspection")
    if not backup.exists():
        partial = BACKUP / "original-flash.partial.bin"
        if partial.exists():
            if partial.is_symlink() or not partial.is_file() or partial.stat().st_size:
                raise RuntimeError("partial_backup_requires_inspection")
            # Earlier esptool timeouts left this precreated empty placeholder.
            partial.unlink()
        budget = measure_read(ports[0])
        # The loader runs in RAM; this command reads flash, never erases/writes it.
        descriptor = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        print(json.dumps({"stage": "reading_original_flash"}), flush=True)
        run(ports[0], ["read_flash", "0", str(SIZE), str(partial)], "backup", budget)
        if partial.stat().st_size != SIZE:
            raise RuntimeError("backup_size_mismatch")
        digest = hashlib.sha256(partial.read_bytes()).hexdigest()
        partial.rename(backup)
        descriptor = os.open(str(metadata), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"size_bytes": SIZE, "sha256": digest, "identity": identity}, stream)
    evidence = json.loads(metadata.read_text())
    if backup.stat().st_size != SIZE or hashlib.sha256(backup.read_bytes()).hexdigest() != evidence.get("sha256"):
        raise RuntimeError("backup_integrity_failed")
    result = {"backup_verified": True, "flash_written": False, "size_bytes": SIZE}
    if flash:
        build = RUNTIME_BUILD if runtime else BUILD
        config = json.loads((build / "flasher_args.json").read_text())
        expected = {"0x2000": "bootloader/bootloader.bin", "0x10000": "partition_table/partition-table.bin", "0x20000": "lvgl_demo_v9.bin"}
        if runtime:
            expected["0x20000"] = "sketch_to_device.bin"
        if config.get("flash_files") != expected:
            raise RuntimeError("unexpected_flash_layout")
        arguments = ["write_flash", "--flash_mode", "dio", "--flash_size", "16MB", "--flash_freq", "80m"]
        images = {}
        for address, name in expected.items():
            image = build / name
            limit = {"0x2000": 0x10000, "0x10000": 0x11000,
                     "0x20000": 0x420000 if runtime else 0x820000}[address]
            if (not image.is_file() or image.is_symlink() or not image.stat().st_size or
                    int(address, 16) + image.stat().st_size > limit):
                raise RuntimeError("invalid_vendor_image")
            images[name] = hashlib.sha256(image.read_bytes()).hexdigest()
            arguments.extend([address, str(image)])
        if runtime:
            # Inspect the actual built partition binary, not a source declaration.
            parsed = subprocess.run([str(IDF_PYTHON), "-I", str(ROOT / ".tools/esp-idf-v5.5.5/components/partition_table/gen_esp32part.py"),
                                     "--offset", "0x10000", "--flash-size", "16MB",
                                     str(build / "partition_table/partition-table.bin")], capture_output=True,
                                    text=True, timeout=15, check=True)
            rows = list(csv.reader(line for line in parsed.stdout.splitlines() if line and not line.startswith("#")))
            wanted = [["nvs", "data", "nvs", "0x11000", "24K", ""],
                      ["phy_init", "data", "phy", "0x17000", "4K", ""],
                      ["factory", "app", "factory", "0x20000", "4M", ""],
                      ["apps", "data", "nvs", "0x420000", "512K", ""]]
            if [[field.strip() for field in row] for row in rows] != wanted:
                raise RuntimeError("unexpected_runtime_partition_table")
            marker = BACKUP / "apps-initialized.json"
            if marker.exists():
                if json.loads(marker.read_text()).get("original_backup_sha256") != evidence["sha256"]:
                    raise RuntimeError("apps_initialization_identity_mismatch")
            elif initialize_apps:
                print(json.dumps({"stage": "initializing_app_storage", "backup_verified": True}), flush=True)
                run(ports[0], ["erase_region", "0x420000", "0x80000"], "apps-initialize", 60)
                descriptor = os.open(str(marker), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as stream:
                    json.dump({"original_backup_sha256": evidence["sha256"]}, stream)
            else:
                raise RuntimeError("first_runtime_flash_requires_app_storage_initialization")
        print(json.dumps({"stage": "flashing_runtime" if runtime else "flashing_vendor_display_example", "backup_verified": True}), flush=True)
        run(ports[0], arguments, "flash", 180)
        result.update(flash_written=True, image_hashes=images,
                      next_check="Observe the display and test touch; flashing alone is not a peripheral test.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--backup", action="store_true")
    group.add_argument("--flash-vendor", action="store_true")
    group.add_argument("--flash-runtime", action="store_true")
    parser.add_argument("--initialize-app-storage", action="store_true",
                        help="Initialize only the new runtime data partition once, after verified original backup")
    args = parser.parse_args()
    if args.initialize_app_storage and not args.flash_runtime:
        parser.error("--initialize-app-storage requires --flash-runtime")
    if not args.backup and not args.flash_vendor and not args.flash_runtime:
        print(json.dumps({"status": "not_requested"}))
        return 0
    try:
        if args.flash_runtime:
            if not (ROOT / "firmware/sdkconfig.private").is_file():
                raise RuntimeError("private_device_configuration_required")
            print(json.dumps({"stage": "building_configured_runtime"}), flush=True)
            completed = subprocess.run(["/bin/bash", str(ROOT / "firmware/build.sh")], cwd=str(ROOT), timeout=900, check=False)
            if completed.returncode:
                raise RuntimeError("runtime_build_failed")
        print(json.dumps(baseline(args.flash_vendor or args.flash_runtime, args.flash_runtime, args.initialize_app_storage), indent=2))
        return 0
    except subprocess.TimeoutExpired:
        error = "serial_command_timeout"
    except RuntimeError as exc:
        error = str(exc)
    except Exception:
        error = "baseline_operation_failed"
    print(json.dumps({"error": error, "result": "failed"}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
