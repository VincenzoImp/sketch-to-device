"""Real temporary Git repositories with synthetic GitHub boundaries; no network."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import publish_github as publication


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in publication.check_context.ROOT_FILES:
            (self.root / name).write_text("Synthetic public source\n")
        (self.root / ".env").write_text("API_KEY=synthetic_private_value_only\n")
        self.old_audit_root = publication.check_context.ROOT
        self.addCleanup(setattr, publication.check_context, "ROOT", self.old_audit_root)
        self.real_command = publication.command
        self.exists, self.refs, self.calls = False, None, []
        self.bare = self.root / ".remote-fixture.git"
        self.real_command(["git", "init", "--bare", str(self.bare)], self.root)

    def command(self, argv, root, allow_failure=False):
        self.calls.append(argv)
        if argv[:3] == ["gh", "api", "user"]:
            return subprocess.CompletedProcess(argv, 0, b'{"login":"VincenzoImp","id":123}', b"")
        if argv[:3] == ["gh", "api", "repos/" + publication.REPOSITORY]:
            data = {"full_name": publication.REPOSITORY, "private": False, "fork": False, "archived": False} if self.exists else {"status": "404"}
            return subprocess.CompletedProcess(argv, 0 if self.exists else 1, json.dumps(data).encode(), b"")
        if argv[:4] == ["gh", "api", "--method", "POST"]:
            self.exists = True
            return subprocess.CompletedProcess(argv, 0, b"{}", b"")
        if "ls-remote" in argv and self.refs is not None:
            return subprocess.CompletedProcess(argv, 0, "\n".join(self.refs).encode(), b"")
        if "push" in argv or "ls-remote" in argv:
            argv = [str(self.bare) if part == publication.URL + ".git" else part for part in argv]
        return self.real_command(argv, root, allow_failure)

    def publish(self):
        with patch.object(publication, "command", side_effect=self.command):
            return publication.publish(self.root, publication.audit(self.root))

    def test_default_audits_without_git_or_github_mutation(self):
        with patch.object(publication, "ROOT", self.root), patch.object(publication, "command") as command, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(publication.main([]), 0)
        command.assert_not_called()
        self.assertFalse((self.root / ".git").exists())
        self.assertFalse((self.root / "private").exists())
        self.assertFalse(json.loads(output.getvalue())["published"])

    def test_real_index_commit_and_retry_contain_only_exact_audited_sources(self):
        sha = self.publish()
        self.assertEqual(self.publish(), sha)
        tracked = self.real_command(["git", "ls-files"], self.root).stdout.decode().splitlines()
        self.assertEqual(set(tracked), set(publication.check_context.ROOT_FILES))
        self.assertNotIn(".env", tracked)
        self.assertEqual(self.real_command(["git", "rev-list", "--all"], self.root).stdout.decode().splitlines(), [sha])
        self.assertEqual(self.real_command(["git", "--git-dir=" + str(self.bare), "rev-parse", "main"], self.root).stdout.decode().strip(), sha)
        self.assertEqual(sum(call[:4] == ["gh", "api", "--method", "POST"] for call in self.calls), 1)
        for call in self.calls:
            self.assertNotIn("--force", call)
            self.assertNotIn("--global", call)
            if "add" in call:
                self.assertNotIn(".", call)

    def test_private_index_entry_blocks_before_remote_write(self):
        self.real_command(["git", "init", "-b", "main"], self.root)
        self.real_command(["git", "add", ".env"], self.root)
        with self.assertRaises(publication.PublishError) as caught:
            self.publish()
        self.assertEqual(str(caught.exception), "unapproved_git_content")
        self.assertFalse(self.exists)
        self.assertFalse(any("push" in call for call in self.calls))

    def test_different_existing_remote_is_not_overwritten(self):
        self.exists, self.refs = True, ["a" * 40 + "\trefs/heads/main"]
        with self.assertRaises(publication.PublishError) as caught:
            self.publish()
        self.assertEqual(str(caught.exception), "remote_history_not_approved")
        self.assertFalse(any("push" in call for call in self.calls))

    def test_changed_snapshot_or_additional_history_requires_new_review(self):
        self.publish()
        (self.root / "README.md").write_text("Changed public source\n")
        with self.assertRaises(publication.PublishError) as caught:
            self.publish()
        self.assertEqual(str(caught.exception), "git_snapshot_changed")
        self.real_command(["git", "add", "README.md"], self.root)
        self.real_command(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "Unexpected later commit"], self.root)
        with self.assertRaises(publication.PublishError) as caught:
            self.publish()
        self.assertEqual(str(caught.exception), "unexpected_git_history")

    def test_known_private_value_fails_without_echo(self):
        (self.root / "README.md").write_text("synthetic_private_value_only\n")
        with patch.object(publication, "ROOT", self.root), patch.object(publication, "command") as command, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(publication.main(["--publish"]), 1)
        command.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["result"], "public_audit_failed")
        self.assertNotIn("synthetic_private_value_only", output.getvalue())

    def test_cli_publication_verifies_real_local_push_and_private_log_mode(self):
        with patch.object(publication, "ROOT", self.root), patch.object(publication, "command", side_effect=self.command), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(publication.main(["--publish"]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["result"], "published")
        self.assertEqual(report["url"], publication.URL)
        self.assertEqual((self.root / "private/publication/publish.log").stat().st_mode & 0o777, 0o600)
        self.assertNotIn("synthetic_private_value_only", output.getvalue())


if __name__ == "__main__":
    unittest.main()
