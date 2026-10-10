"""Exercise incremental publication against real temporary Git repositories."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from scripts import checkpoint_github as checkpoint
from scripts import publish_github as publication
from tests import test_publish_github


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.harness = test_publish_github.PublicationTests()
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.root = self.harness.root
        self.initial = self.harness.publish()
        self.message = "Record physical app verification"

    def publish(self):
        with patch.object(publication, "command", side_effect=self.harness.command):
            return checkpoint.checkpoint(self.root, publication.audit(self.root), self.message, self.initial)

    def test_preserves_history_and_publishes_exact_audited_new_tree(self):
        (self.root / "README.md").write_text("Verified physical app\n")
        head = self.publish()
        self.assertNotEqual(head, self.initial)
        history = self.harness.real_command(["git", "rev-list", "main"], self.root).stdout.decode().splitlines()
        self.assertEqual(history, [head, self.initial])
        remote = self.harness.real_command(["git", "--git-dir=" + str(self.harness.bare), "rev-parse", "main"], self.root)
        self.assertEqual(remote.stdout.decode().strip(), head)
        self.assertEqual(self.publish(), head)  # No empty checkpoint.

    def test_failed_push_can_retry_without_duplicate_commit(self):
        (self.root / "README.md").write_text("Reviewed update\n")
        def interrupted(argv, root, allow_failure=False):
            if "push" in argv:
                raise publication.PublishError("command_failed")
            return self.harness.command(argv, root, allow_failure)
        with patch.object(publication, "command", side_effect=interrupted):
            with self.assertRaises(publication.PublishError):
                checkpoint.checkpoint(self.root, publication.audit(self.root), self.message, self.initial)
        head = self.harness.real_command(["git", "rev-parse", "HEAD"], self.root).stdout.decode().strip()
        self.assertEqual(self.publish(), head)

    def test_private_staged_file_blocks_commit_and_push(self):
        self.harness.real_command(["git", "add", ".env"], self.root)
        self.harness.calls.clear()
        with self.assertRaisesRegex(publication.PublishError, "tracked_files_need_review"):
            self.publish()
        self.assertFalse(any("push" in call or "commit" in call for call in self.harness.calls))

    def test_pending_commit_with_private_identity_is_not_published(self):
        (self.root / "README.md").write_text("Reviewed tree, unreviewed identity\n")
        self.harness.real_command(["git", "add", "README.md"], self.root)
        self.harness.real_command(["git", "-c", "user.name=Private Name", "-c", "user.email=private@example.invalid",
                                   "commit", "-m", self.message], self.root)
        self.harness.calls.clear()
        with self.assertRaisesRegex(publication.PublishError, "unapproved_commit_metadata"):
            self.publish()
        self.assertFalse(any("push" in call for call in self.harness.calls))

    def test_unseen_remote_change_and_extra_local_history_stop(self):
        self.harness.refs = ["a" * 40 + "\trefs/heads/main"]
        with self.assertRaisesRegex(publication.PublishError, "remote_history_not_approved"):
            self.publish()
        self.harness.refs = None
        for index in range(2):
            (self.root / "README.md").write_text("Update " + str(index))
            self.harness.real_command(["git", "add", "README.md"], self.root)
            self.harness.real_command(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "Local change"], self.root)
        with self.assertRaisesRegex(publication.PublishError, "local_history_needs_review"):
            self.publish()

    def test_readonly_default_and_invalid_message(self):
        with patch.object(checkpoint, "ROOT", self.root), patch.object(publication, "command") as command:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(checkpoint.main([]), 0)
            self.assertFalse(json.loads(output.getvalue())["published"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(checkpoint.main(["--publish", "--message", "bad\nmessage"]), 1)
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
