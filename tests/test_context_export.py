"""Exercise the public snapshot CLI on synthetic project trees."""

import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_context.py"


class ContextExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="context-audit-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "scripts").mkdir()
        (self.root / "docs").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts/check_context.py")
        self.public = {
            "README.md": "[Spec](docs/spec.md)\n",
            "AGENTS.md": "[Overview](README.md)\n",
            ".gitignore": ".env\n/*.pdf\nartifacts/\n",
            ".env.example": "EXAMPLE_KEY=\n",
            "docs/spec.md": "# Public specification\n",
        }
        for name, content in self.public.items():
            (self.root / name).write_text(content)
        self.secret = "synthetic-private-" + "z" * 20
        (self.root / ".env").write_text(
            "SERVICE_KEY=" + self.secret + "\nWIFI_PASSWORD=DemoOnly9!\nEMPTY_TOKEN=\n")
        (self.root / "private.pdf").write_bytes(b"private fixture only")

    def run_check(self, valid, export=False, private_values=()):
        result = subprocess.run(
            [sys.executable, "scripts/check_context.py"] + (["--export"] if export else []),
            cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0 if valid else 1)
        for value in private_values:
            self.assertNotIn(value, result.stdout + result.stderr)
        return result

    def test_export_exact_members_and_bytes(self):
        self.run_check(True, export=True)
        with tarfile.open(self.root / "artifacts/context-public.tar.gz") as archive:
            members = archive.getmembers()
            expected = set(self.public) | {"scripts/check_context.py"}
            actual = {member.name.removeprefix("sketch-to-device/") for member in members}
            self.assertEqual(actual, expected)
            for member in members:
                self.assertTrue(member.isfile())
                original = self.root / member.name.removeprefix("sketch-to-device/")
                self.assertEqual(archive.extractfile(member).read(), original.read_bytes())

    def test_bad_content_is_rejected_without_secret_echo(self):
        signature = "gsk_" + "x" * 32
        cases = [
            ("missing link", "[Missing](absent.md)", ()),
            ("signature", signature, (signature,)),
            ("configured value", self.secret, (self.secret,)),
            ("short password", "DemoOnly9!", ("DemoOnly9!",)),
            ("secret link", "[Missing](<" + self.secret + ">)", (self.secret,)),
        ]
        for label, content, private_values in cases:
            with self.subTest(label=label):
                (self.root / "README.md").write_text(self.public["README.md"] + content)
                self.run_check(False, private_values=private_values)
        (self.root / "README.md").write_text(self.public["README.md"])
        self.run_check(True)

    def test_orphan_document(self):
        (self.root / "docs/orphan.md").write_text("# Unlinked\n")
        self.run_check(False)

    def test_symlink(self):
        path = self.root / "docs/spec.md"
        path.unlink()
        path.symlink_to(self.root / "private.pdf")
        self.run_check(False)

    def test_invalid_utf8_source(self):
        (self.root / "scripts/bad.py").write_bytes(b"\xff")
        self.run_check(False)


if __name__ == "__main__":
    unittest.main()
