"""Tests for runner/agent_skills.py and the skill check in runner/agent_output.py.

The agent job copies the skills into .claude/skills/, untracked. On a pull request,
claude-code-action then deletes .claude/ and checks out the base branch's tracked files there
(restoreConfigFromBase). These tests do the same to a scratch repository and run the SessionStart
hook the agent step is given.

Run: python3 -m unittest discover -s runner/tests
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNNER))
import agent_skills  # noqa: E402
from common import FactoryError  # noqa: E402

SETTINGS = '{"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "bash hook.sh"}]}]}}\n'
PLAN = {"stage": "review", "agent": {"skill": "review-pr"}, "output": {"kind": "file", "file": "review.json"}}


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class AgentSkillsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "repo"
        self.temp = self.tmp / "runner-temp"
        self.temp.mkdir()
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")

    def commit_base(self, tracked: dict[str, str]) -> None:
        """The default branch: .claude/settings.json plus `tracked`; factory skills are ignored."""
        write(self.root / ".gitignore", ".claude/skills/review-pr/\n.claude/skills/triage/\n.factory/\n")
        write(self.root / ".claude/settings.json", SETTINGS)
        for rel, text in tracked.items():
            write(self.root / rel, text)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")

    def materialize(self) -> None:
        """What the job's Skills and plan and Add skill sources steps leave behind."""
        skills = self.root / ".claude/skills"
        write(skills / "review-pr/SKILL.md", "---\nname: review-pr\n---\nfactory review-pr\n")
        write(skills / "review-pr/scripts/validate_review_json.py", "print('ok')\n")
        write(skills / "triage/SKILL.md", "---\nname: triage\n---\n")
        write(skills / "novelty-audit/SKILL.md", "---\nname: novelty-audit\n---\n")
        write(skills / "novelty-audit/.gitignore", "# agent-skills: synced\n*\n")

    def action_restore(self) -> None:
        """claude-code-action's restoreConfigFromBase: delete .claude, check out the base's tracked files."""
        shutil.rmtree(self.root / ".claude")
        subprocess.run(["git", "-C", str(self.root), "checkout", "main", "--", ".claude"], capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "reset", "-q", "--", ".claude"], capture_output=True)

    def keep(self, count: int = 3) -> dict:
        settings = self.temp / "factory-agent-settings.json"
        out = subprocess.run(
            [sys.executable, str(RUNNER / "agent_skills.py"), "keep", "--to", str(self.temp / "factory-agent-skills"),
             "--settings", str(settings)], cwd=self.root, check=True, capture_output=True, text=True).stdout
        self.assertIn(f"kept {count} skill(s)", out)
        return json.loads(settings.read_text())

    def run_hook(self, settings: dict) -> subprocess.CompletedProcess:
        """Run the SessionStart hook as Claude Code does: through a shell, in the project directory."""
        (hook,) = settings["hooks"]["SessionStart"][0]["hooks"]
        self.assertEqual(hook["type"], "command")
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        return subprocess.run(["bash", "-c", hook["command"]], cwd=self.root, env=env, capture_output=True, text=True)

    def collect(self) -> subprocess.CompletedProcess:
        plan = self.temp / "plan.json"
        plan.write_text(json.dumps(PLAN))
        write(self.root / "review.json", "{}")
        write(self.root / "pr_diff.txt", "")
        env = {**os.environ, "FACTORY_INPUTS": str(self.temp / "inputs")}
        return subprocess.run(
            [sys.executable, str(RUNNER / "agent_output.py"), "--plan", str(plan), "--base", "HEAD",
             "--out", str(self.temp / "result")], cwd=self.root, env=env, capture_output=True, text=True)

    def test_no_tracked_skills_loses_them_and_the_hook_puts_them_back(self):
        self.commit_base({})
        self.materialize()
        settings = self.keep()
        self.action_restore()
        # The bug: with nothing tracked under .claude/skills/, the restore leaves no skills at all.
        self.assertFalse((self.root / ".claude/skills").exists())
        self.assertEqual((self.root / ".claude/settings.json").read_text(), SETTINGS)
        failed = self.collect()
        self.assertEqual(failed.returncode, 1)
        self.assertIn(".claude/skills/review-pr/SKILL.md is missing after the agent step", failed.stderr)
        self.assertNotIn("Traceback", failed.stderr)

        proc = self.run_hook(settings)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("put back 3 skill(s)", proc.stdout)
        self.assertIn("novelty-audit, review-pr, triage", proc.stdout)
        self.assertTrue((self.root / ".claude/skills/review-pr/scripts/validate_review_json.py").is_file())
        self.assertEqual((self.root / ".claude/skills/novelty-audit/.gitignore").read_text(), "# agent-skills: synced\n*\n")
        # Still untracked and ignored: nothing reaches the agent's commits.
        self.assertEqual(git(self.root, "status", "--porcelain", "--", ".claude"), "")

        ok = self.collect()
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("collected review.json", ok.stdout)

        # Run again (SessionStart also fires on resume and compact): nothing to do, nothing printed.
        again = self.run_hook(settings)
        self.assertEqual((again.returncode, again.stdout), (0, ""))

    def test_tracked_skill_stays_as_the_base_branch_has_it(self):
        self.commit_base({".claude/skills/onboard/SKILL.md": "---\nname: onboard\n---\nbase\n"})
        self.materialize()
        write(self.root / ".claude/skills/onboard/SKILL.md", "---\nname: onboard\n---\nedited\n")
        settings = self.keep(4)
        self.action_restore()
        self.assertFalse((self.root / ".claude/skills/review-pr").exists())
        proc = self.run_hook(settings)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("onboard", proc.stdout)
        self.assertIn("base", (self.root / ".claude/skills/onboard/SKILL.md").read_text())
        self.assertTrue((self.root / ".claude/skills/review-pr/SKILL.md").is_file())

    def test_no_restore_means_nothing_to_do(self):
        self.commit_base({})
        self.materialize()
        settings = self.keep()
        proc = self.run_hook(settings)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_does_not_write_through_a_link_out_of_the_skills(self):
        self.commit_base({})
        self.materialize()
        self.keep()
        self.action_restore()
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.root / ".claude/skills").mkdir(parents=True)
        os.symlink(outside, self.root / ".claude/skills/review-pr")
        with self.assertRaises(FactoryError):
            agent_skills.restore(self.root, self.temp / "factory-agent-skills")
        self.assertEqual(list(outside.iterdir()), [])

        shutil.rmtree(self.root / ".claude/skills")
        os.symlink(outside, self.root / ".claude/skills")
        with self.assertRaises(FactoryError):
            agent_skills.restore(self.root, self.temp / "factory-agent-skills")
        self.assertEqual(list(outside.iterdir()), [])

    def test_keep_needs_skills(self):
        with self.assertRaises(FactoryError):
            agent_skills.keep(self.root, self.temp / "kept")

    def test_check_skill(self):
        agent_skills.check_skill(self.root, "")
        with self.assertRaisesRegex(FactoryError, "ran without its skill"):
            agent_skills.check_skill(self.root, "review-pr")
        write(self.root / ".claude/skills/review-pr/SKILL.md", "x")
        agent_skills.check_skill(self.root, "review-pr")


class WorkflowTest(unittest.TestCase):
    """stage.yml keeps the skills and hands the hook to the action."""

    def test_agent_job_wires_the_hook(self):
        import yaml

        wf = yaml.safe_load((RUNNER.parent / ".github/workflows/stage.yml").read_text())
        steps = wf["jobs"]["agent"]["steps"]
        names = [s.get("name") for s in steps]
        keep = steps[names.index("Keep the skills for the agent")]
        claude = steps[names.index("Claude Code")]
        self.assertLess(names.index("Add skill sources"), names.index("Keep the skills for the agent"))
        self.assertLess(names.index("Keep the skills for the agent"), names.index("Claude Code"))
        self.assertIn("agent_skills.py keep", keep["run"])
        self.assertIn('"$RUNNER_TEMP/factory-agent-settings.json"', keep["run"])
        self.assertEqual(claude["with"]["settings"], "${{ runner.temp }}/factory-agent-settings.json")
        self.assertEqual(keep.get("if"), claude.get("if"))


if __name__ == "__main__":
    unittest.main()
