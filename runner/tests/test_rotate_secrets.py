"""Tests for `scripts/factory rotate-secrets`. gh is a stub on PATH, so nothing reaches GitHub.

The stub answers `gh repo list` and `gh secret list` from files, logs every call's arguments to
calls.log, and writes the value piped to `gh secret set` to set.log as "NAME REPO VALUE". The values are fake.

Run: python3 -m unittest discover -s runner/tests
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2] / "scripts" / "factory"

STUB = r'''#!/usr/bin/env bash
echo "$*" >> "$STUB_DIR/calls.log"
case "$1 $2" in
  "auth status") exit 0 ;;
  "api user") echo me ;;
  "repo list") cat "$STUB_DIR/repos" ;;
  "secret list")
    repo="$4"
    if grep -qxF -- "$repo" "$STUB_DIR/unlistable" 2>/dev/null; then exit 1; fi
    cat "$STUB_DIR/secrets/${repo//\//__}" 2>/dev/null || true ;;
  "secret set") echo "$3 $5 $(cat)" >> "$STUB_DIR/set.log" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
'''

EXPORTED = {"FACTORY_GITHUB_TOKEN": "fake-github", "CLAUDE_CODE_OAUTH_TOKEN": "fake-claude"}


class RotateSecretsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / "bin").mkdir()
        (self.dir / "secrets").mkdir()
        gh = self.dir / "bin" / "gh"
        gh.write_text(STUB)
        gh.chmod(0o755)
        # me/old already has both; me/partial has the GitHub token only; me/new has nothing.
        self.have("me/old", "FACTORY_GITHUB_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
        self.have("me/partial", "FACTORY_GITHUB_TOKEN")
        self.have("me/new")
        (self.dir / "repos").write_text("me/old\nme/new\nme/partial\nme/factory\n")

    def have(self, repo, *names):
        (self.dir / "secrets" / repo.replace("/", "__")).write_text("".join(n + "\n" for n in names))

    def run_cli(self, *args, env=None):
        env = {"PATH": f"{self.dir / 'bin'}:{os.environ['PATH']}", "HOME": str(self.dir),
               "STUB_DIR": str(self.dir), "FACTORY_REPO": "me/factory", **(EXPORTED if env is None else env)}
        return subprocess.run([str(FACTORY), "rotate-secrets", *args], env=env, text=True,
                              capture_output=True, check=False)

    def sets(self):
        log = self.dir / "set.log"
        return sorted(log.read_text().splitlines()) if log.exists() else []

    def calls(self, prefix):
        log = self.dir / "calls.log"
        return [c for c in log.read_text().splitlines() if c.startswith(prefix)] if log.exists() else []

    def test_default_sets_only_missing_secrets(self):
        out = self.run_cli()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.sets(), sorted([
            "FACTORY_GITHUB_TOKEN me/new fake-github",
            "CLAUDE_CODE_OAUTH_TOKEN me/new fake-claude",
            "CLAUDE_CODE_OAUTH_TOKEN me/partial fake-claude",
        ]))
        self.assertIn("skip     FACTORY_GITHUB_TOKEN on me/old (already set; use --force to rotate)", out.stdout)
        self.assertIn("set      CLAUDE_CODE_OAUTH_TOKEN on me/partial", out.stdout)
        self.assertIn("skip     me/factory (the factory itself", out.stdout)
        self.assertIn("3 repositories (2 changed, 1 unchanged): set 3, rotated 0, skipped 3.", out.stdout)
        self.assertIn("3 secret(s) were already set and left alone. To rotate", out.stdout)

    def test_lists_each_repository_once_and_never_the_factory(self):
        self.run_cli()
        self.assertEqual(sorted(self.calls("secret list")), sorted(
            f"secret list --repo me/{r} --json name -q .[].name" for r in ("old", "new", "partial")))

    def test_second_run_with_the_same_exports_sets_nothing(self):
        self.have("me/new", "FACTORY_GITHUB_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
        self.have("me/partial", "FACTORY_GITHUB_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
        out = self.run_cli()
        self.assertEqual(self.sets(), [])
        self.assertIn("(0 changed, 3 unchanged): set 0, rotated 0, skipped 6.", out.stdout)

    def test_values_are_piped_never_on_a_command_line(self):
        self.run_cli()
        self.assertTrue(self.sets())
        self.assertNotIn("fake-", (self.dir / "calls.log").read_text())

    def test_force_sets_everywhere(self):
        out = self.run_cli("--force")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(len(self.sets()), 6)
        self.assertIn("rotate   FACTORY_GITHUB_TOKEN on me/old", out.stdout)
        self.assertIn("set      CLAUDE_CODE_OAUTH_TOKEN on me/new", out.stdout)
        self.assertIn("set 3, rotated 3, skipped 0.", out.stdout)
        self.assertNotIn("left alone", out.stdout)

    def test_force_with_names_rotates_only_those(self):
        out = self.run_cli("--force", "CLAUDE_CODE_OAUTH_TOKEN")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.sets(), sorted([
            "CLAUDE_CODE_OAUTH_TOKEN me/old fake-claude",      # rotated
            "CLAUDE_CODE_OAUTH_TOKEN me/new fake-claude",      # missing
            "CLAUDE_CODE_OAUTH_TOKEN me/partial fake-claude",  # missing
            "FACTORY_GITHUB_TOKEN me/new fake-github",         # missing, so still set
        ]))
        self.assertIn("skip     FACTORY_GITHUB_TOKEN on me/old", out.stdout)
        self.assertIn("rotate   CLAUDE_CODE_OAUTH_TOKEN on me/old", out.stdout)
        self.assertIn("set 3, rotated 1, skipped 2.", out.stdout)

    def test_force_accepts_a_comma_list_and_options_after_it(self):
        out = self.run_cli("--force", "FACTORY_GITHUB_TOKEN,CLAUDE_CODE_OAUTH_TOKEN", "--dry-run")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("would rotate 3", out.stdout)
        self.assertEqual(self.sets(), [])

    def test_force_name_must_be_a_known_exported_secret(self):
        bad = self.run_cli("--force", "NOPE")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("not one of", bad.stderr)
        unset = self.run_cli("--force", "FACTORY_READ_TOKEN")
        self.assertNotEqual(unset.returncode, 0)
        self.assertIn("not exported", unset.stderr)
        self.assertEqual(self.sets(), [])

    def test_dry_run_reports_each_secret_and_sets_nothing(self):
        out = self.run_cli("--dry-run")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.sets(), [])
        self.assertEqual(self.calls("secret set"), [])
        lines = out.stdout.splitlines()
        self.assertIn("would set FACTORY_GITHUB_TOKEN on me/new", lines)
        self.assertIn("would set CLAUDE_CODE_OAUTH_TOKEN on me/partial", lines)
        self.assertIn("would skip FACTORY_GITHUB_TOKEN on me/old (already set; use --force to rotate)", lines)
        self.assertIn("3 repositories (2 with a change, 1 unchanged): would set 3, would rotate 0, "
                      "would skip 3 (dry run: nothing changed).", out.stdout)
        self.assertIn("3 secret(s) are already set and would be left alone.", out.stdout)

    def test_dry_run_with_force_says_would_rotate(self):
        out = self.run_cli("--force", "--dry-run")
        self.assertEqual(self.sets(), [])
        self.assertIn("would rotate FACTORY_GITHUB_TOKEN on me/old", out.stdout)
        self.assertIn("would set CLAUDE_CODE_OAUTH_TOKEN on me/new", out.stdout)
        self.assertIn("would set 3, would rotate 3, would skip 0 (dry run", out.stdout)

    def test_a_repository_whose_secrets_cant_be_listed_is_left_alone_and_fails_the_run(self):
        (self.dir / "unlistable").write_text("me/new\n")
        out = self.run_cli()
        self.assertEqual(out.returncode, 1)
        self.assertIn("can't list the secrets of me/new", out.stderr)
        self.assertEqual(self.sets(), ["CLAUDE_CODE_OAUTH_TOKEN me/partial fake-claude"])
        self.assertIn("1 failed", out.stdout)

    def test_needs_an_exported_secret(self):
        out = self.run_cli(env={})
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("export at least one", out.stderr)


if __name__ == "__main__":
    unittest.main()
