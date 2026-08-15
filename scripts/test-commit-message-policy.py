#!/usr/bin/env python3
"""Regression tests for the dependency-free commit message policy."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate-commit-message.py"


def run_validator(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


class CommitMessagePolicyTests(unittest.TestCase):
    def test_accepts_supported_conventional_subjects(self) -> None:
        for subject in (
            "feat(team): add overview and focused conversation",
            "fix(local-agent): isolate binding state",
            "docs(workflow): explain release rollback",
            "ci(delivery): validate pull request subjects",
        ):
            with self.subTest(subject=subject):
                self.assertEqual(run_validator("--subject", subject).returncode, 0)

    def test_rejects_missing_type_scope_and_overlong_subject(self) -> None:
        invalid = "ship everything"
        overlong = "feat(platform): " + "x" * 90
        result = run_validator("--subject", invalid, "--subject", overlong)
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected '<type>(<scope>): <summary>'", result.stderr)
        self.assertIn("maximum is 88", result.stderr)

    def test_fixup_is_local_only(self) -> None:
        subject = "fixup! feat(team): add overview and focused conversation"
        self.assertEqual(run_validator("--subject", subject).returncode, 1)
        self.assertEqual(
            run_validator("--subject", subject, "--allow-fixup").returncode,
            0,
        )

    def test_reads_first_non_comment_line_from_message_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            message = Path(temp_dir) / "COMMIT_EDITMSG"
            message.write_text(
                "# template comment\n\nfeat(provider): enforce model allowlist\n\nWhy: keep routing exact.\n"
            )
            self.assertEqual(
                run_validator("--message-file", str(message)).returncode,
                0,
            )

    def test_stdin_validates_each_subject(self) -> None:
        result = run_validator(
            "--stdin",
            stdin=(
                "feat(team): add overview\n"
                "WIP desktop changes\n"
            ),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("commit 2", result.stderr)


if __name__ == "__main__":
    unittest.main()
