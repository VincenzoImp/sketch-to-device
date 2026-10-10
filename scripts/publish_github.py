#!/usr/bin/env python3
"""Audit by default; --publish creates/pushes only the audited initial snapshot.

Retries require the same single initial commit. Later repository updates need a
separate reviewed workflow. No force push, global Git configuration, or private
file staging is performed. Raw command failures stay in a mode-600 private log.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import check_context

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "VincenzoImp/sketch-to-device"
URL = "https://github.com/" + REPOSITORY
COMMIT_MESSAGE = "Publish audited Sketch-to-Device prototype"
LOG = None


class PublishError(Exception):
    pass


def command(argv, root, allow_failure=False):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    try:
        result = subprocess.run(argv, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        raise PublishError("command_unavailable_or_timeout") from None
    if LOG:
        LOG.write(result.stdout + result.stderr)
        LOG.flush()
    if result.returncode and not allow_failure:
        raise PublishError("command_failed")
    return result


def git(root, *args, allow_failure=False):
    return command(["git", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=",
                    "-c", "credential.helper=!gh auth git-credential", *args], root, allow_failure)


def audit(root):
    root = root.resolve()
    check_context.ROOT = root
    files = check_context.public_files()
    if check_context.validate(files):
        raise PublishError("public_audit_failed")
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in files}


def verify_entries(root, raw, snapshot, index=False):
    actual = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        fields, name = entry.split(b"\t", 1)
        mode, kind, revision = fields.decode().split()
        if index:
            kind, revision = revision, kind
        name = name.decode("utf-8")
        if mode not in {"100644", "100755"} or kind != ("0" if index else "blob") or name not in snapshot:
            raise PublishError("unapproved_git_content")
        if git(root, "cat-file", "blob", revision).stdout != snapshot[name]:
            raise PublishError("git_snapshot_changed")
        actual[name] = revision
    if set(actual) != set(snapshot):
        raise PublishError("git_snapshot_incomplete")


def verify_history(root, snapshot, identity):
    head = git(root, "rev-parse", "--verify", "HEAD", allow_failure=True)
    if head.returncode:
        if git(root, "rev-list", "--all").stdout.strip():
            raise PublishError("unexpected_git_history")
        return None
    sha = head.stdout.decode().strip()
    commits = git(root, "rev-list", "--all", "HEAD").stdout.decode().splitlines()
    if commits != [sha] or git(root, "log", "-1", "--format=%B").stdout.decode().strip() != COMMIT_MESSAGE:
        raise PublishError("unexpected_git_history")
    headers = git(root, "cat-file", "commit", sha).stdout.decode().split("\n\n", 1)[0].splitlines()
    if len(headers) != 3 or not headers[0].startswith("tree ") or any(
            not re.fullmatch(kind + " VincenzoImp <" + re.escape(identity) + r"> \d+ [+-]\d{4}", line)
            for kind, line in zip(("author", "committer"), headers[1:])):
        raise PublishError("unapproved_commit_metadata")
    verify_entries(root, git(root, "ls-tree", "-r", "-z", "HEAD").stdout, snapshot)
    return sha


def remote(root):
    result = command(["gh", "api", "repos/" + REPOSITORY], root, allow_failure=True)
    try:
        data = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise PublishError("remote_state_unknown") from None
    if not isinstance(data, dict):
        raise PublishError("remote_state_unknown")
    if result.returncode and str(data.get("status")) == "404":
        return None
    if result.returncode or data.get("full_name") != REPOSITORY or data.get("private") is not False or data.get("fork") or data.get("archived"):
        raise PublishError("remote_state_not_approved")
    return data


def remote_refs(root):
    return git(root, "ls-remote", "--refs", URL + ".git").stdout.decode().splitlines()


def publish(root, snapshot):
    profile = json.loads(command(["gh", "api", "user"], root).stdout)
    if not isinstance(profile, dict) or profile.get("login") != "VincenzoImp" or type(profile.get("id")) is not int or profile["id"] <= 0:
        raise PublishError("github_account_mismatch")
    identity = f"{profile['id']}+VincenzoImp@users.noreply.github.com"
    git_dir = root / ".git"
    if git_dir.is_symlink() or (git_dir.exists() and not git_dir.is_dir()):
        raise PublishError("unexpected_git_directory")
    if not git_dir.exists():
        git(root, "init", "-b", "main")
    if Path(git(root, "rev-parse", "--show-toplevel").stdout.decode().strip()).resolve() != root.resolve():
        raise PublishError("unexpected_git_root")
    if git(root, "symbolic-ref", "--short", "HEAD").stdout.strip() != b"main":
        raise PublishError("unexpected_git_branch")
    names = git(root, "remote").stdout.decode().splitlines()
    if names and (names != ["origin"] or git(root, "remote", "get-url", "--all", "origin").stdout.decode().strip() != URL + ".git"):
        raise PublishError("unexpected_git_remote")
    sha = verify_history(root, snapshot, identity)
    git(root, "add", "--", *sorted(snapshot))
    verify_entries(root, git(root, "ls-files", "--stage", "-z").stdout, snapshot, index=True)
    if sha is None:
        git(root, "-c", "user.name=VincenzoImp", "-c", "user.email=" + identity,
            "-c", "commit.gpgsign=false", "commit", "-m", COMMIT_MESSAGE)
        sha = verify_history(root, snapshot, identity)
    # Validate the actual index and history, then recheck current source bytes.
    verify_entries(root, git(root, "ls-files", "--stage", "-z").stdout, snapshot, index=True)
    if audit(root) != snapshot:
        raise PublishError("source_changed_during_publication")
    existing = remote(root)
    expected = [sha + "\trefs/heads/main"]
    if existing is not None and remote_refs(root) not in ([], expected):
        raise PublishError("remote_history_not_approved")
    if existing is None:
        command(["gh", "api", "--method", "POST", "user/repos", "-f", "name=sketch-to-device",
                 "-F", "private=false", "-f", "description=Prompt-to-device interactive app prototype"], root)
        if remote(root) is None:
            raise PublishError("remote_creation_unverified")
    if not names:
        git(root, "remote", "add", "origin", URL + ".git")
    git(root, "push", "--no-verify", "--no-follow-tags", URL + ".git", sha + ":refs/heads/main")
    if remote_refs(root) != expected or remote(root) is None:
        raise PublishError("publication_unverified")
    return sha


def main(argv=None):
    global LOG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="create/push the audited initial public snapshot")
    args = parser.parse_args(argv)
    try:
        snapshot = audit(ROOT)
        if not args.publish:
            print(json.dumps({"result": "audit_passed", "files": len(snapshot), "published": False}))
            return 0
        directory = ROOT / "private" / "publication"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(directory / "publish.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as LOG:
            sha = publish(ROOT, snapshot)
        LOG = None
        print(json.dumps({"result": "published", "url": URL, "commit": sha, "files": len(snapshot)}))
        return 0
    except (PublishError, OSError, ValueError, UnicodeError) as exc:
        LOG = None
        code = str(exc) if isinstance(exc, PublishError) else "publication_failed"
        print(json.dumps({"result": code, "published": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
