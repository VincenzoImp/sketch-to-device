#!/usr/bin/env python3
"""Check current public project files and export an allowlisted snapshot.

This checks an explicit source allowlist. It does not certify unlisted files,
Git history, every possible secret, provider connectivity, or physical
device behavior. Secret checks cover known signatures and current local values.
"""

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = ("README.md", "AGENTS.md", ".gitignore", ".env.example")
SOURCE_SUFFIXES = {".md", ".json", ".py", ".sh", ".html", ".css", ".js", ".swift", ".c", ".h", ".yml", ".csv", ".lock", ".cmake", ".txt"}
SOURCE_NAMES = {"sdkconfig.defaults", "Kconfig.projbuild", ".gitignore"}
EXCLUDED_PARTS = {"managed_components", "build", ".git", "__pycache__", ".tools", "private"}
SOURCE_DIRS = ("contracts", "runtime", "backend", "companion", "firmware", "tests", "scripts", "agent-sdk")
SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\bAQ\.[0-9A-Za-z_-]{32,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def public_files():
    """Select current context and implemented source, excluding private data."""
    files = [ROOT / name for name in ROOT_FILES]
    files.extend(sorted((ROOT / "docs").rglob("*.md")))
    for directory in SOURCE_DIRS:
        files.extend(sorted(path for path in (ROOT / directory).rglob("*")
                            if (path.suffix in SOURCE_SUFFIXES or path.name in SOURCE_NAMES)
                            and not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)))
    return files


def validate(files):
    """Return non-sensitive diagnostics for missing links or leaked secrets."""
    errors = []
    selected = {path.relative_to(ROOT).as_posix() for path in files}
    document_paths = {path.resolve() for path in files if path.suffix == ".md"}
    links_by_document = {path: set() for path in document_paths}
    private_values = []
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and ("KEY" in key or "TOKEN" in key or "PASSWORD" in key):
                value = value.strip().strip("\"'")
                if value:
                    private_values.append(value)
    # Provisioned device/session credentials live outside .env as well.
    config = ROOT / "firmware/sdkconfig.private"
    if config.exists():
        for line in config.read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"CONFIG_SKETCH_WIFI_SSID", "CONFIG_SKETCH_WIFI_PASSWORD", "CONFIG_SKETCH_DEVICE_TOKEN"}:
                try:
                    decoded = json.loads(value)
                except ValueError:
                    errors.append("Private device configuration could not be inspected (value omitted)")
                    continue
                if isinstance(decoded, str) and decoded:
                    private_values.extend({decoded, value[1:-1]})
    config = ROOT / "private/service/demo-config.json"
    if config.exists():
        try:
            data = json.loads(config.read_text())
            for key in ("session_token", "device_token"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    private_values.append(value)
        except (ValueError, AttributeError):
            errors.append("Private service configuration could not be inspected (value omitted)")
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if path.is_symlink() or not path.is_file():
            errors.append(f"{relative}: missing file or disallowed symlink")
            continue
        if ROOT not in path.resolve().parents:
            errors.append(f"{relative}: file resolves outside project")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError:
            errors.append(f"{relative}: public source must be UTF-8")
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            errors.append(f"{relative}: possible credential signature (value omitted)")
        if any(value in content for value in private_values):
            errors.append(f"{relative}: contains a private environment value (omitted)")
        if path.suffix != ".md":
            continue
        for target in LINK.findall(content):
            target = target.strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / unquote(target)).resolve()
            if ROOT not in resolved.parents:
                errors.append(f"{relative}: local link leaves project")
                continue
            if resolved.relative_to(ROOT).as_posix() not in selected:
                errors.append(f"{relative}: local link is missing from public allowlist (target omitted)")
            elif resolved in document_paths:
                links_by_document[path.resolve()].add(resolved)
    pending = [ROOT / "AGENTS.md", ROOT / "README.md"]
    reachable = set()
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending.extend(links_by_document.get(current, set()) - reachable)
    for orphan in sorted(document_paths - reachable):
        errors.append(f"{orphan.relative_to(ROOT)}: not reachable from AGENTS.md or README.md")
    return errors


def main():
    """Run the audit and export only after all checks pass."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true", help="write artifacts/context-public.tar.gz")
    args = parser.parse_args()
    files = public_files()
    errors = validate(files)
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print(f"PASS: {len(files)} public files; relative links, document reachability and credential checks passed.")
    print("Original PDFs, .env, uploads, Git metadata and account files are excluded.")
    if args.export:
        target = ROOT / "artifacts" / "context-public.tar.gz"
        target.parent.mkdir(exist_ok=True)
        with tarfile.open(target, "w:gz") as archive:
            for path in files:
                archive.add(path, arcname="sketch-to-device/" + path.relative_to(ROOT).as_posix(), recursive=False)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        target.with_suffix(target.suffix + ".sha256").write_text(digest + "  " + target.name + "\n")
        print(f"Exported {target.relative_to(ROOT)}; SHA-256 {digest}")


if __name__ == "__main__":
    main()
