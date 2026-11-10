#!/usr/bin/env python3
"""Keep the agent job's skills through claude-code-action's config restore (docs/pipeline.md).

  agent_skills.py keep --to DIR --settings FILE   copy .claude/skills/ to DIR, outside the checkout,
                                                  and write the agent step's settings to FILE
  agent_skills.py restore --from DIR              put back any file under .claude/skills/ that's gone

On a pull request, claude-code-action deletes .claude/ and checks out only the files the base
branch tracks there, before Claude Code starts. The skills the agent job copied in are untracked
(ignored), so they're deleted with it, unless the repository happens to commit them. FILE holds a
user-level SessionStart hook (the action merges it into ~/.claude/settings.json, which the restore
doesn't touch) that runs `restore`: after the restore and before the agent's first turn.

`restore` only adds what is missing. A file the base branch put back stays as it is, and so does
anything else in .claude/. It never writes through a link that leads out of .claude/skills/.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FactoryError, main_guard  # noqa: E402

SKILLS = Path(".claude", "skills")


def project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def keep(root: Path, to: Path) -> int:
    """Copy root/.claude/skills to `to` (replacing it). Returns the number of skills."""
    src = root / SKILLS
    if not src.is_dir():
        raise FactoryError(f"no {SKILLS}/ in {root}: the job has no skills to keep")
    if to.exists():
        shutil.rmtree(to)
    shutil.copytree(src, to, symlinks=True)
    return sum(1 for d in to.iterdir() if (d / "SKILL.md").is_file())


def hook_settings(snapshot: Path) -> dict:
    script = Path(__file__).resolve()
    command = f"python3 {shlex.quote(str(script))} restore --from {shlex.quote(str(snapshot.resolve()))}"
    return {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": command}]}]}}


def restore(root: Path, snapshot: Path) -> list[str]:
    """Copy into root/.claude/skills every file or link in `snapshot` that is missing there."""
    if not snapshot.is_dir():
        raise FactoryError(f"no skills kept at {snapshot}")
    dest_root = root / SKILLS
    base = root.resolve() / SKILLS
    # resolve() follows every link on the way, including ones in parts that don't exist yet.
    if dest_root.resolve() != base:
        raise FactoryError(f"{SKILLS} leads out of the checkout; not writing there")
    added: list[str] = []
    for dirpath, dirnames, filenames in os.walk(snapshot):
        rel_dir = Path(dirpath).relative_to(snapshot)
        entries = list(filenames)
        # os.walk lists links to directories with the directories; copy them as links, don't descend.
        for name in list(dirnames):
            if (Path(dirpath) / name).is_symlink():
                dirnames.remove(name)
                entries.append(name)
        for name in sorted(entries):
            rel = rel_dir / name
            dest = dest_root / rel
            if dest.exists() or dest.is_symlink():
                continue
            parent = dest.parent.resolve()
            if parent != base and base not in parent.parents:
                raise FactoryError(f"{SKILLS / rel_dir} leads out of {SKILLS}/; not writing there")
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = Path(dirpath) / name
            if src.is_symlink():
                os.symlink(os.readlink(src), dest)
            else:
                shutil.copy2(src, dest)
            added.append(str(SKILLS / rel))
    return added


def check_skill(root: Path, skill: str) -> None:
    """Fail clearly when the stage's skill isn't in the checkout (after the agent step)."""
    if not skill:
        return
    path = SKILLS / skill / "SKILL.md"
    if not (root / path).is_file():
        raise FactoryError(
            f"{path} is missing after the agent step, so the agent ran without its skill. On a pull "
            "request claude-code-action replaces .claude/ with the base branch's tracked files; the "
            "agent step's SessionStart hook (runner/agent_skills.py restore) should have put the "
            "skills back. Its output is in the session transcript.")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keep")
    k.add_argument("--to", required=True)
    k.add_argument("--settings", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--from", dest="src", required=True)
    args = ap.parse_args()
    root = project_root()

    if args.cmd == "keep":
        n = keep(root, Path(args.to))
        Path(args.settings).write_text(json.dumps(hook_settings(Path(args.to)), indent=2) + "\n")
        print(f"kept {n} skill(s) for the agent step")
        return 0

    added = restore(root, Path(args.src))
    if added:
        skills = sorted({Path(p).parts[2] for p in added})
        # SessionStart output reaches the agent's context, so it says only what happened.
        print(f"factory: put back {len(skills)} skill(s) under {SKILLS}/ that the pull request "
              f"config restore removed: {', '.join(skills)}")
    return 0


if __name__ == "__main__":
    main_guard(main)
