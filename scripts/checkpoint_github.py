#!/usr/bin/env python3
"""Publish one audited follow-up commit, preserving existing public history.

Default is read-only. --publish requires a short English commit message. Only
allowlisted files are staged, current private values are scanned, and main is
pushed without force. An interrupted push may be retried with identical source.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import publish_github as publication

ROOT = Path(__file__).resolve().parents[1]
INITIAL = "8826f2edb8ab662cc2e524e4867661832c8d04cd"


def checkpoint(root, snapshot, message, initial=INITIAL):
    git, error = publication.git, publication.PublishError
    if (root / ".git").is_symlink() or not (root / ".git").is_dir():
        raise error("unexpected_git_directory")
    if Path(git(root, "rev-parse", "--show-toplevel").stdout.decode().strip()).resolve() != root.resolve():
        raise error("unexpected_git_root")
    if git(root, "symbolic-ref", "--short", "HEAD").stdout.strip() != b"main":
        raise error("unexpected_git_branch")
    if git(root, "remote", "get-url", "--all", "origin").stdout.decode().strip() != publication.URL + ".git":
        raise error("unexpected_git_remote")
    if publication.remote(root) is None:
        raise error("public_repository_missing")
    refs = publication.remote_refs(root)
    main = [line.split("\t")[0] for line in refs if line.endswith("\trefs/heads/main")]
    if len(main) != 1 or not re.fullmatch(r"[a-f0-9]{40}", main[0]):
        raise error("remote_history_not_approved")
    remote_head = main[0]
    head = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    profile = json.loads(publication.command(["gh", "api", "user"], root).stdout)
    if not isinstance(profile, dict) or profile.get("login") != "VincenzoImp" or type(profile.get("id")) is not int or profile["id"] <= 0:
        raise error("github_account_mismatch")
    identity = str(profile["id"]) + "+VincenzoImp@users.noreply.github.com"
    if git(root, "merge-base", "--is-ancestor", initial, remote_head, allow_failure=True).returncode:
        raise error("remote_history_not_approved")
    # Never push unrelated local history, merges or an unseen intermediate tree.
    retry = head != remote_head
    if retry:
        parents = git(root, "rev-list", "--parents", "-n", "1", head).stdout.decode().split()
        if parents != [head, remote_head]:
            raise error("local_history_needs_review")
        publication.verify_entries(root, git(root, "ls-tree", "-r", "-z", head).stdout, snapshot)
        if git(root, "log", "-1", "--format=%B").stdout.decode().strip() != message:
            raise error("retry_message_mismatch")
    # Existing index entries must not introduce private paths, even accidentally.
    tracked = git(root, "ls-files", "-z").stdout.decode().split("\0")
    if any(name and name not in snapshot for name in tracked):
        raise error("tracked_files_need_review")
    if publication.audit(root) != snapshot:
        raise error("source_changed_during_publication")
    if not retry:
        git(root, "add", "--", *sorted(snapshot))
        publication.verify_entries(root, git(root, "ls-files", "--stage", "-z").stdout, snapshot, index=True)
        changed = git(root, "diff", "--cached", "--quiet", allow_failure=True).returncode
        if changed not in (0, 1):
            raise error("index_comparison_failed")
        if changed:
            git(root, "-c", "user.name=VincenzoImp", "-c", "user.email=" + identity,
                "-c", "commit.gpgsign=false", "commit", "-m", message)
            head = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    if head != remote_head:
        headers = git(root, "cat-file", "commit", head).stdout.decode().split("\n\n", 1)[0].splitlines()
        if (len(headers) != 4 or not headers[0].startswith("tree ") or headers[1] != "parent " + remote_head
                or any(not re.fullmatch(kind + " VincenzoImp <" + re.escape(identity) + r"> \d+ [+-]\d{4}", line)
                       for kind, line in zip(("author", "committer"), headers[2:]))):
            raise error("unapproved_commit_metadata")
    publication.verify_entries(root, git(root, "ls-tree", "-r", "-z", head).stdout, snapshot)
    if publication.audit(root) != snapshot:
        raise error("source_changed_during_publication")
    # A racing remote update is rejected by the normal non-force push.
    git(root, "push", "--no-verify", "--no-follow-tags", publication.URL + ".git", head + ":refs/heads/main")
    if head + "\trefs/heads/main" not in publication.remote_refs(root) or publication.remote(root) is None:
        raise error("publication_unverified")
    return head


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--message", default="Update reviewed prototype")
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .,:()/_-]{2,95}", args.message):
            raise publication.PublishError("invalid_commit_message")
        snapshot = publication.audit(ROOT)
        if not args.publish:
            print(json.dumps({"result": "audit_passed", "files": len(snapshot), "published": False}))
            return 0
        directory = ROOT / "private/publication"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(directory / "checkpoint.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as log:
            publication.LOG = log
            sha = checkpoint(ROOT, snapshot, args.message)
        print(json.dumps({"result": "published", "url": publication.URL, "commit": sha, "files": len(snapshot)}))
        return 0
    except (publication.PublishError, OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"result": str(exc) if isinstance(exc, publication.PublishError) else "publication_failed", "published": False}))
        return 1
    finally:
        publication.LOG = None


if __name__ == "__main__":
    raise SystemExit(main())
