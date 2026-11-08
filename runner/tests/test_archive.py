"""Tests for runner/archive.py: redaction, the run record, encryption and the archive checks.

Run: python3 -m unittest discover -s runner/tests
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import archive  # noqa: E402
from common import FactoryError  # noqa: E402

TOKEN = "ghs_" + "A" * 36
ENV = {"FACTORY_GITHUB_TOKEN": "s3cret-value-1234", "CLAUDE_CODE_OAUTH_TOKEN": "oauth-value-5678",
       "GITHUB_REPOSITORY": "acme/app", "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
       "GITHUB_SERVER_URL": "https://github.com", "FACTORY_NOW": "2026-11-07T12:00:00Z",
       "AGENT_RESULT": "success", "APPLY_RESULT": "failure", "PATH": os.environ.get("PATH", "")}
PLAN = {"stage": "review", "item": 3, "item_kind": "pr", "trigger": "pull_request_target opened",
        "factory": {"repo": "acme/factory", "sha": "a" * 40, "ref": "main", "release": ""},
        "agent": {"tier": "fast", "model": "claude-haiku-5-5", "effort": "medium"},
        "conditions": ["small_change"], "flags": {"session-archive": True, "spec-auto-advance": False},
        "apply": ["publish-review"], "sessions": {"archive": "acme/factory-sessions", "encrypt": False}}
MESSAGES = [
    {"type": "system", "subtype": "init", "model": "claude-haiku-5-5", "claude_code_version": "2.1.0"},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "env"}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "content":
        f"GH_TOKEN={TOKEN}\nFACTORY=s3cret-value-1234\nkey sk-ant-api03-{'x' * 30}\n"
        "AUTHORIZATION: basic eHgtYWNjZXNzLXRva2VuOmFiYw==\nhttps://user:pw@example.com/repo.git"}]}},
    {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "duration_ms": 9000, "total_cost_usd": 0.12},
]


class Redaction(unittest.TestCase):
    def test_known_secrets_include_their_encodings(self):
        secrets = archive.known_secrets({"FACTORY_GITHUB_TOKEN": "abcdefgh12", "SHORT_TOKEN": "abc", "HOME": "/home/x"})
        self.assertIn("abcdefgh12", secrets)
        self.assertIn(base64.b64encode(b"x-access-token:abcdefgh12").decode(), secrets)
        self.assertNotIn("abc", secrets)
        self.assertNotIn("/home/x", secrets)

    def test_secrets_and_patterns_are_removed_and_counted(self):
        red = archive.Redactor(archive.known_secrets(ENV))
        text = json.dumps(red.value(MESSAGES))
        for leaked in (TOKEN, "s3cret-value-1234", "sk-ant-api03", "eHgtYWNjZXNzLXRva2VuOmFiYw==", "user:pw@"):
            self.assertNotIn(leaked, text)
        self.assertIn("AUTHORIZATION: basic [REDACTED]", text)
        self.assertIn("https://[REDACTED]@example.com", text)
        self.assertEqual(red.counts["known-secret"], 1)
        for kind in ("github-token", "anthropic-key", "auth-header", "url-credentials"):
            self.assertEqual(red.counts[kind], 1, kind)

    def test_long_strings_keep_head_and_tail(self):
        red = archive.Redactor([])
        s = "h" * 30_000 + "TAIL"
        out = red.text(s)
        self.assertLess(len(out), 21_000)
        self.assertTrue(out.startswith("h" * 100) and out.endswith("TAIL"))
        self.assertEqual(red.truncated, 1)

    def test_private_key_blocks(self):
        red = archive.Redactor([])
        out = red.text("a\n-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----\nb")
        self.assertEqual(out, "a\n[REDACTED:private-key]\nb")


class Loading(unittest.TestCase):
    def test_array_lines_and_text(self):
        self.assertEqual(archive.load_messages(json.dumps([{"a": 1}])), [{"a": 1}])
        self.assertEqual(archive.load_messages('{"a": 1}\n{"b": 2}\n'), [{"a": 1}, {"b": 2}])
        self.assertEqual(archive.load_messages("not json\nat all"), [{"type": "text", "text": "not json\nat all"}])
        self.assertEqual(archive.load_messages("  "), [])

    def test_jsonl_gz_is_deterministic(self):
        blob = archive.to_jsonl_gz(MESSAGES)
        self.assertEqual(blob, archive.to_jsonl_gz(MESSAGES))
        lines = gzip.decompress(blob).decode().splitlines()
        self.assertEqual([json.loads(x) for x in lines], MESSAGES)

    def test_session_stats(self):
        s = archive.session_stats(MESSAGES)
        self.assertEqual((s["model"], s["num_turns"], s["total_cost_usd"], s["messages"]), ("claude-haiku-5-5", 3, 0.12, 4))


class Commands(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "plan.json").write_text(json.dumps(PLAN))
        (self.tmp / "exec.json").write_text(json.dumps(MESSAGES))
        (self.tmp / "result").mkdir()
        (self.tmp / "result" / "review.json").write_text(json.dumps({"verdict": "APPROVE", "comments": [{}, {}],
                                                                     "body": f"token {TOKEN}"}))
        self.env = mock.patch.dict(os.environ, ENV, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp)

    def redact(self, plan=PLAN, extra_env=None):
        (self.tmp / "plan.json").write_text(json.dumps(plan))
        env = dict(ENV, **(extra_env or {}))
        args = SimpleNamespace(plan=str(self.tmp / "plan.json"), execution=str(self.tmp / "exec.json"), out=str(self.tmp / "session"))
        archive.cmd_redact(args, env)
        return env

    def push(self, env, dry_run=True):
        args = SimpleNamespace(plan=str(self.tmp / "plan.json"), session=str(self.tmp / "session"),
                               result=str(self.tmp / "result"), dry_run=dry_run, out=str(self.tmp / "out"))
        return archive.cmd_push(args, env)

    def test_private_repository_round_trip(self):
        env = self.redact()
        self.assertTrue((self.tmp / "session" / "transcript.jsonl.gz").exists())
        self.push(env)
        record = json.loads((self.tmp / "out" / "runs/app/2026/11/42-1-review-3.json").read_text())
        self.assertEqual(record["transcript"], "sessions/app/2026/11/42-1-review-3.jsonl.gz")
        self.assertEqual(record["result"], {"verdict": "APPROVE", "comments": 2})
        self.assertEqual(record["jobs"], {"agent": "success", "apply": "failure"})
        self.assertEqual(record["session"]["total_cost_usd"], 0.12)
        self.assertEqual(record["flags_on"], ["session-archive"])
        blob = (self.tmp / "out" / record["transcript"]).read_bytes()
        self.assertNotIn(TOKEN, gzip.decompress(blob).decode())

    @unittest.skipUnless(shutil.which("openssl"), "needs openssl")
    def test_public_repository_encrypts_between_jobs(self):
        env = self.redact(dict(PLAN, sessions={"archive": "acme/factory-sessions", "encrypt": True}),
                          {"FACTORY_ARCHIVE_KEY": "archive-key-123456"})
        enc = self.tmp / "session" / "transcript.jsonl.gz.enc"
        self.assertTrue(enc.exists())
        self.assertFalse((self.tmp / "session" / "transcript.jsonl.gz").exists())
        self.assertNotIn(b'"type"', enc.read_bytes())
        self.push(env)
        record = json.loads((self.tmp / "out" / "runs/app/2026/11/42-1-review-3.json").read_text())
        lines = gzip.decompress((self.tmp / "out" / record["transcript"]).read_bytes()).decode().splitlines()
        self.assertEqual(len(lines), len(MESSAGES))

    def test_public_repository_without_a_key_keeps_only_the_record(self):
        env = self.redact(dict(PLAN, sessions={"archive": "acme/factory-sessions", "encrypt": True}))
        self.assertEqual(sorted(p.name for p in (self.tmp / "session").iterdir()), ["session.json"])
        self.push(env)
        record = json.loads((self.tmp / "out" / "runs/app/2026/11/42-1-review-3.json").read_text())
        self.assertIsNone(record["transcript"])
        self.assertIn("FACTORY_ARCHIVE_KEY", record["redaction"]["note"])

    def test_no_archive_does_nothing(self):
        (self.tmp / "plan.json").write_text(json.dumps(dict(PLAN, sessions={"archive": "", "reason": "flag session-archive is off"})))
        self.assertEqual(self.push(ENV), 0)
        self.assertFalse((self.tmp / "out").exists())

    def test_push_checks_the_archive_first(self):
        env = self.redact()
        with mock.patch.object(archive, "gh", return_value='{"private": false, "owner": "acme"}') as gh:
            with self.assertRaisesRegex(FactoryError, "isn't private"):
                self.push(env, dry_run=False)
            self.assertEqual(gh.call_count, 1)  # nothing was written


class ArchiveRepository(unittest.TestCase):
    def test_check_archive(self):
        cases = [('{"private": true, "owner": "Acme"}', None), ('{"private": false, "owner": "acme"}', "isn't private"),
                 ('{"private": true, "owner": "other"}', "isn't owned by acme"), ("", "can't read")]
        for out, err in cases:
            with self.subTest(out=out), mock.patch.object(archive, "gh", return_value=out):
                if err:
                    with self.assertRaisesRegex(FactoryError, err):
                        archive.check_archive("acme/sessions", "acme/app", "t")
                else:
                    archive.check_archive("acme/sessions", "acme/app", "t")

    def test_put_file_created_exists_and_denied(self):
        ok = json.dumps({"content": {"path": "runs/x.json"}})
        with mock.patch.object(archive, "gh", return_value=ok):
            self.assertEqual(archive.put_file("acme/s", "runs/x.json", b"{}", "m", "t"), "created")
        with mock.patch.object(archive, "gh", side_effect=['{"message": "sha wasn\'t supplied", "status": "422"}', "runs/x.json"]):
            self.assertEqual(archive.put_file("acme/s", "runs/x.json", b"{}", "m", "t"), "exists")
        with mock.patch.object(archive, "gh", side_effect=['{"message": "Resource not accessible", "status": "403"}', ""]), \
                self.assertRaisesRegex(FactoryError, "Resource not accessible"):
            archive.put_file("acme/s", "runs/x.json", b"{}", "m", "t")

    def test_paths(self):
        self.assertEqual(archive.archive_paths(dict(PLAN, item=""), ENV),
                         ("sessions/app/2026/11/42-1-review-none.jsonl.gz", "runs/app/2026/11/42-1-review-none.json"))


if __name__ == "__main__":
    unittest.main()
