#!/usr/bin/env python3
"""Collect the agent's output in the agent job, for the apply job (docs/pipeline.md).

  agent_output.py --plan PLAN --base SHA --out DIR   (structured output in $STRUCTURED_OUTPUT)

structured: the JSON becomes DIR/result.json.
file:       review.json is checked (a regular file, at most 4 MiB, a JSON object, valid against
            the diff) and copied to DIR/review.json.
patch:      the JSON becomes DIR/result.json; for outcome `pr`, the commits on its branch since
            SHA become DIR/patch.bundle and the changed paths DIR/files.txt.
Unless the agent was skipped, the stage's skill must still be in .claude/skills/ (agent_skills.py).
Nothing here writes to GitHub. The apply job checks everything again before it does.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_skills import check_skill  # noqa: E402
from common import FactoryError, main_guard  # noqa: E402

BRANCH = re.compile(r"^(?!-)(?!.*\.\.)[A-Za-z0-9._/-]{1,200}$")
PATCH_KEYS = {"outcome": str, "branch": str, "pr_title": str, "pr_body": str, "draft": bool, "comment": str}


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise FactoryError(f"git {' '.join(args[:2])}: {proc.stderr.strip()}")
    return proc.stdout


def check_patch_result(result) -> dict:
    if not isinstance(result, dict):
        raise FactoryError("the agent's result must be a JSON object")
    for key, typ in PATCH_KEYS.items():
        if not isinstance(result.get(key), typ):
            raise FactoryError(f"the agent's result needs '{key}' ({typ.__name__})")
    if result["outcome"] not in ("pr", "none", "blocked"):
        raise FactoryError(f"unknown outcome {result['outcome']!r}")
    if result.get("state") is not None and not isinstance(result["state"], str):
        raise FactoryError("state must be a string or null")
    if result["outcome"] == "pr":
        if not BRANCH.match(result["branch"]):
            raise FactoryError(f"bad branch name {result['branch']!r}")
        if not result["pr_title"].strip():
            raise FactoryError("outcome pr needs a pr_title")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    kind = plan["output"]["kind"]
    raw = os.environ.get("STRUCTURED_OUTPUT", "").strip()
    skipped = Path(os.environ.get("FACTORY_INPUTS", ".factory-io/inputs"), "skip-agent").exists()

    if skipped:
        result = {"outcome": "none", "branch": "", "pr_title": "", "pr_body": "", "draft": False,
                  "comment": "Nothing to learn from in this window; the agent didn't run.", "state": None}
        (out / "result.json").write_text(json.dumps(result))
        print("agent skipped")
        return 0

    check_skill(Path.cwd(), (plan.get("agent") or {}).get("skill", ""))

    if kind == "file":
        source = Path(plan["output"]["file"])
        if not source.exists():
            raise FactoryError(f"the agent did not write {source}")
        st = source.lstat()
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise FactoryError(f"{source} must be a regular file, not a link or special file")
        if st.st_size > 4 * 1024 * 1024:
            raise FactoryError(f"{source} is over 4 MiB")
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise FactoryError(f"{source} must hold a JSON object")
        subprocess.run(["python3", ".claude/skills/review-pr/scripts/validate_review_json.py",
                        "--review-json", str(source), "--diff", "pr_diff.txt"], check=True)
        (out / source.name).write_text(json.dumps(payload))
        print(f"collected {source}")
        return 0

    if not raw:
        raise FactoryError("the agent returned no structured output")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FactoryError(f"the agent's structured output isn't JSON: {exc}") from exc

    if kind == "patch":
        result = check_patch_result(result)
        result["base"] = args.base
        if result["outcome"] == "pr":
            ref = f"refs/heads/{result['branch']}"
            git("rev-parse", "--verify", "--quiet", ref)
            count = int(git("rev-list", "--count", f"{args.base}..{ref}").strip())
            if count == 0:
                raise FactoryError(f"branch {result['branch']} has no commits since {args.base[:12]}")
            git("bundle", "create", str(out / "patch.bundle"), ref, f"^{args.base}")
            files = git("diff", "--name-only", args.base, ref)
            (out / "files.txt").write_text(files)
            print(f"bundled {count} commit(s) on {result['branch']}:\n{files}")
    (out / "result.json").write_text(json.dumps(result))
    print(f"collected {kind} result")
    return 0


if __name__ == "__main__":
    main_guard(main)
