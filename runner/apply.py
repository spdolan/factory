#!/usr/bin/env python3
"""The apply job: the only code that writes to GitHub, through fixed named operations.

  apply.py --plan PLAN --result DIR [--inputs DIR]

Runs plan["apply"] in order. Each operation accepts only what pipeline.yaml declares:
states, markers and gate labels by name, and patches that leave .github/workflows/ alone.
Issue reads and writes go through runner/tracker.py; PRs, reviews and dispatches use gh.

Tokens: GH_TOKEN is the job's GITHUB_TOKEN (the stub's permission ceiling). WRITE_TOKEN is
FACTORY_GITHUB_TOKEN when set, so pushed branches, PRs and dispatched runs trigger CI.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FactoryError, gh, load_pipeline, main_guard  # noqa: E402

PROTECTED = (".github/workflows/",)
ALLOWED_KINDS = ("proposed", "maintenance")


# --- pure decisions (tested) --------------------------------------------------------------------

def decide_route(plan: dict, result: dict, item_labels: list, pipeline: dict) -> dict:
    """Who advances a triaged issue: {advance: agent|human|none, risky, next_stage}."""
    state, size = result["state"], result["size"]
    auto = plan["autonomy"]
    risky = bool(set(auto["never_if"]) & (set(result.get("risk_labels") or []) | set(item_labels)))
    next_stage = auto["next_stage"].get(state)
    advance = "human" if next_stage else "none"
    if advance == "human" and not risky and result.get("autonomy") == "agent":
        for rule in auto["rules"]:
            states = rule["state"] if isinstance(rule["state"], list) else [rule["state"]]
            if state in states and size in rule["size"]:
                advance = "agent"
                break
    return {"advance": advance, "risky": risky, "next_stage": next_stage}


def triage_comment(result: dict, route: dict, run_url: str, gate_approved: str) -> str:
    body = result["comment"]
    if "\n" not in body:  # models sometimes double-escape line breaks; undo only then
        body = body.replace("\\n", "\n")
    reason = result.get("autonomy_reason", "")
    nxt = {"agent": f"**Next:** an agent continues automatically. {reason}",
           "human": f"**Next:** needs a human. {reason} Add the `{gate_approved}` label to start."}.get(route["advance"], "")
    out = body + (f"\n\n{nxt}" if nxt else "")
    return out + (f"\n\n---\n_Triage: `{result['state']}` · size `{result['size']}` · "
                  f"bet `{result.get('bet') or 'none'}` · [run]({run_url})_\n")


def patch_problems(files: list[str], allowed_prefixes: list[str] | None) -> list[str]:
    problems = [f"{f}: the factory never applies agent changes to {p}" for f in files for p in PROTECTED if f.startswith(p)]
    if allowed_prefixes:
        problems += [f"{f}: this stage may only change {', '.join(allowed_prefixes)}"
                     for f in files if not any(f.startswith(p) for p in allowed_prefixes)]
    return problems


def item_labels_for_create(labels: list, pipeline: dict) -> list:
    """bet-intake: only factory:proposed, maintenance and bet:<id>."""
    ok = {pipeline["kinds"][k] for k in ALLOWED_KINDS}
    return [x for x in dict.fromkeys(labels) if x in ok or re.match(r"^bet:[a-z0-9-]+$", x)]


def consumers(factory_md: str) -> list[str]:
    """Repositories listed under '## Consumers' in FACTORY.md, e.g. "- `owner/repo`: uses …"."""
    out, on = [], False
    for line in factory_md.splitlines():
        if line.startswith("## "):
            on = line.startswith("## Consumers")
        elif on and line.startswith("- "):
            m = re.match(r"^- `?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)`?", line)
            if m and m.group(1) != "owner/repo":
                out.append(m.group(1))
    return out


def free_branch(branch: str, taken: set, run_id: str) -> str:
    """The agent's branch name, or a fresh one when a branch of that name already exists on the remote
    (an earlier run's): apply never force-pushes over it."""
    if branch not in taken:
        return branch
    for suffix in [f"-run{run_id}"] + [f"-run{run_id}-{i}" for i in range(2, 10)]:
        if branch + suffix not in taken:
            return branch + suffix
    raise FactoryError(f"no free branch name near {branch}")


def remote_branches(git: list, url: str, branch: str) -> set:  # pragma: no cover - IO
    proc = subprocess.run([*git, "ls-remote", "--heads", url, f"refs/heads/{branch}*"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise FactoryError(f"can't list branches: {proc.stderr.strip()[-300:]}")
    out = proc.stdout
    return {line.split("refs/heads/", 1)[1] for line in out.splitlines() if "refs/heads/" in line}


# --- operations -------------------------------------------------------------------------------

class Apply:
    def __init__(self, plan: dict, result_dir: Path, inputs_dir: Path | None):
        import tracker
        self.t = tracker
        self.plan, self.pipeline = plan, load_pipeline()
        self.result_dir, self.inputs_dir = result_dir, inputs_dir
        rp = result_dir / "result.json"
        self.result = json.loads(rp.read_text()) if rp.exists() else {}
        self.repo = os.environ["GITHUB_REPOSITORY"]
        self.server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        self.run_url = f"{self.server}/{self.repo}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
        self.write_token = os.environ.get("WRITE_TOKEN") or os.environ.get("GH_TOKEN")
        self.item = int(plan["item"]) if plan.get("item") else None
        self.route = None
        self.pr_url = ""
        self.notes: list[str] = []
        self.pushed = ""
        self.dispatches: list[tuple[str, int]] = []

    def redact(self, text: str) -> str:
        for secret in {self.write_token, os.environ.get("GH_TOKEN"), os.environ.get("FACTORY_GITHUB_TOKEN")} - {None, ""}:
            text = text.replace(secret, "***")
        return text

    def labels(self) -> list:
        return self.t.get(self.item)["labels"] if self.item else []

    def comment_file(self, body: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w") as fh:
            fh.write(body)
        return path

    def dispatch(self, stage: str, issue: int):
        gh("workflow", "run", f"factory-{stage}.yml", "--repo", self.repo, "-f", f"issue_number={issue}", token=self.write_token)
        print(f"dispatched factory-{stage}.yml for #{issue}")

    # triage
    def op_set_state(self):
        if self.plan["output"]["kind"] == "structured":
            state = self.result["state"]
        else:
            state = self.result.get("state")
            if not state:
                return
        if state not in self.plan["output"].get("states", []):
            raise FactoryError(f"state {state!r} isn't one this stage may set")
        self.t.set_state(self.item, state)
        print(f"#{self.item}: state {state}")

    def op_add_markers(self):
        markers = set(self.pipeline["markers"])
        wanted = [m for m in self.result.get("risk_labels") or [] if m in markers]
        if self.decide()["risky"]:
            wanted += [m for m in self.plan["autonomy"]["never_if"] if m not in wanted and m in markers]
        for m in dict.fromkeys(wanted):
            self.t.add_marker(self.item, m)
            print(f"#{self.item}: marker {m}")

    def decide(self):
        if self.route is None:
            self.route = decide_route(self.plan, self.result, self.labels(), self.pipeline)
        return self.route

    def op_route(self):
        r = self.decide()
        self.t.gate(self.item, {"agent": "agent", "human": "awaiting"}.get(r["advance"], "clear"))
        print(f"#{self.item}: advance {r['advance']} (policy {self.plan['autonomy']['policy']})")
        if r["advance"] == "agent":
            self.dispatches.append((r["next_stage"], self.item))

    def op_comment(self):
        if self.plan["output"]["kind"] == "structured":
            body = triage_comment(self.result, self.decide(), self.run_url, self.pipeline["gate"]["approved"])
        else:
            body = self.result.get("comment", "").strip()
            if self.pr_url:
                body += f"\n\n**PR:** {self.pr_url}"
            for note in self.notes:
                body += f"\n\n_{note}_"
            body += f"\n\n_[Run]({self.run_url})_\n"
        if not self.item:
            print(body)
            return
        self.t.comment(self.item, self.comment_file(body))

    def op_clear_gate(self):
        self.t.gate(self.item, "started")

    # patches
    def op_open_pr(self):
        r = self.result
        if r.get("outcome") != "pr":
            print(f"outcome {r.get('outcome')}: no PR")
            return
        branch, base = r["branch"], r["base"]
        default = gh("api", f"repos/{self.repo}", "--jq", ".default_branch").strip()
        if branch == default:
            raise FactoryError("refusing to push the default branch")
        bundle = self.result_dir / "patch.bundle"
        subprocess.run(["git", "bundle", "verify", str(bundle)], check=True, capture_output=True)
        subprocess.run(["git", "fetch", "--quiet", str(bundle), f"refs/heads/{branch}:refs/factory/patch"], check=True)
        files = subprocess.run(["git", "diff", "--name-only", base, "refs/factory/patch"], check=True,
                               capture_output=True, text=True).stdout.split()
        problems = patch_problems(files, self.plan["output"].get("paths"))
        if problems:
            raise FactoryError("refusing the patch:\n  " + "\n  ".join(problems))
        # The token goes in a header, never the URL, so no error message can carry it.
        url = f"{self.server}/{self.repo}.git"
        auth = base64.b64encode(f"x-access-token:{self.write_token}".encode()).decode()
        git = ["git", "-c", f"http.{self.server}/.extraheader=AUTHORIZATION: basic {auth}"]
        branch = free_branch(branch, remote_branches(git, url, branch), os.environ.get("GITHUB_RUN_ID", "0"))
        push = subprocess.run([*git, "push", "--quiet", url, f"refs/factory/patch:refs/heads/{branch}"],
                              capture_output=True, text=True)
        if push.returncode != 0:
            raise FactoryError(f"git push {branch} failed: {push.stderr.strip()[-500:]}")
        self.pushed = branch
        args = ["pr", "create", "--repo", self.repo, "--head", branch, "--base", default, "--title", r["pr_title"],
                "--body-file", self.comment_file(r["pr_body"])]
        if r.get("draft"):
            args.append("--draft")
        try:
            out = gh(*args, token=self.write_token)
        except FactoryError as exc:
            # A FACTORY_GITHUB_TOKEN without Pull requests: write can push but not open the PR. The job's
            # own token can (the stub grants pull-requests: write), but PRs it opens don't start CI or review.
            if self.write_token == os.environ.get("GH_TOKEN") or "not accessible" not in str(exc):
                raise
            out = gh(*args)
            self.notes.append(f"The PR was opened with the run's GITHUB_TOKEN because FACTORY_GITHUB_TOKEN can't open "
                              f"pull requests in {self.repo} (it needs Pull requests: read and write). CI and review "
                              "won't start on it until the next push.")
            print(f"::warning::{self.notes[-1]}")
        self.pr_url = out.strip().splitlines()[-1]
        print(f"opened {self.pr_url} from {branch}")

    # review
    def op_publish_review(self):
        inputs, n = self.inputs_dir, self.item
        cur = json.loads(gh("api", f"repos/{self.repo}/pulls/{n}"))
        for side in ("base", "head"):
            if cur[side]["sha"] != self.plan["pr"][f"{side}_sha"]:
                raise FactoryError(f"PR {side} changed before publication; refusing a stale review")
        subprocess.run(["python3", ".claude/skills/review-pr/scripts/publish_review.py", "--review-json",
                        str(self.result_dir / "review.json"), "--diff", str(inputs / "pr_diff.txt"), "--repo", self.repo,
                        "--pr", str(n), "--commit-id", cur["head"]["sha"]], check=True)

    # bet intake and dependency releases
    def op_create_items(self):
        made = []
        for issue in (self.result.get("issues") or [])[: self.plan["output"].get("max_items", 3)]:
            labels = item_labels_for_create(issue.get("labels") or [], self.pipeline)
            n = self.t.create(issue["title"], self.comment_file(issue["body"]), labels=labels)
            made.append(n)
            self.dispatches.append(("triage", n))
        print(f"created {made}")

    def op_open_breaking_issue(self):
        p = self.plan["params"]
        title = f"chore(deps)!: adopt {p['package']} {p['version']}"
        if any(i["title"] == title for i in self.t.list_items(state="open", limit=200)):
            print("an issue for this release is already open")
            return
        body = (f"{p['package']} {p['version']} is a breaking release: {p['release_url']}\n\nRead the breaking changes in "
                "the release notes and decide how this repository adopts them.\n\n_Opened by the factory's dependency-bump stage._")
        n = self.t.create(title, self.comment_file(body),
                          labels=[self.pipeline["kinds"]["maintenance"], *self.pipeline["autonomy"]["never_if"]])
        self.dispatches.append(("triage", n))

    def op_notify_consumers(self):
        token = os.environ.get("FACTORY_GITHUB_TOKEN")
        if not token:
            raise FactoryError("FACTORY_GITHUB_TOKEN is not set; it is needed to dispatch to other repositories")
        md = Path("FACTORY.md")
        targets = consumers(md.read_text()) if md.exists() else []
        if not targets:
            print("FACTORY.md lists no consumers")
            return
        tag, package = self.plan["params"]["tag"], self.plan["params"]["package"]
        rel = json.loads(gh("release", "view", tag, "--repo", self.repo, "--json", "body,url"))
        sha = gh("api", f"repos/{self.repo}/commits/{tag}", "--jq", ".sha").strip()
        payload = json.dumps({"event_type": "factory-dependency-release", "client_payload": {
            "source_repo": self.repo, "tag": tag, "version": tag.split("-v")[-1], "package": package, "commit": sha,
            "release_url": rel["url"], "breaking": "BREAKING CHANGE" in (rel.get("body") or "")}})
        failed = []
        for c in targets:
            try:
                gh("api", f"repos/{c}/dispatches", "--input", "-", input_text=payload, token=token)
                print(f"notified {c}")
            except FactoryError as exc:
                print(f"::error::could not notify {c} (does FACTORY_GITHUB_TOKEN cover it?): {exc}")
                failed.append(c)
        if failed:
            raise FactoryError(f"{len(failed)} consumer(s) not notified")

    # updates (rollout.md §6.2)
    def op_open_update_issue(self):
        u = self.plan["update"]
        label = self.pipeline["kinds"]["update"]
        digest = re.search(r"<!-- factory:update (\w+) -->", u["body"]).group(1)
        open_items = self.t.list_items(label=label, state="open", limit=5)
        if not open_items:
            n = self.t.create("Factory update available", self.comment_file(u["body"]),
                              labels=[label, self.pipeline["kinds"]["maintenance"]])
            print(f"opened update issue #{n}")
            return
        n = open_items[0]["number"]
        if f"factory:update {digest}" not in self.t.get(n).get("body", ""):
            self.t.edit(n, self.comment_file(u["body"]))
            print(f"updated update issue #{n}")

    def run(self):
        ops = self.plan["apply"]
        for i, op in enumerate(ops):
            print(f"== {op}")
            try:
                getattr(self, "op_" + op.replace("-", "_"))()
            except (FactoryError, subprocess.CalledProcessError) as exc:
                # Still tell the item what happened when a later operation would have reported on it.
                if "comment" in ops[i + 1:] and self.item:
                    self.notes.append(f"The factory couldn't finish `{op}`: {self.redact(str(exc)).splitlines()[0][:300]}"
                                      + (f" The commits are on `{self.pushed}`." if self.pushed else ""))
                    print("== comment (after the failure)")
                    self.op_comment()
                raise
        for stage, n in self.dispatches:
            self.dispatch(stage, n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--inputs")
    a = ap.parse_args()
    Apply(json.loads(Path(a.plan).read_text()), Path(a.result), Path(a.inputs) if a.inputs else None).run()
    return 0


if __name__ == "__main__":
    main_guard(main)
