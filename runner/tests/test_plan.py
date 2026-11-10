"""Tests for runner/plan.py and runner/apply.py's decisions.

Golden files: runner/tests/golden/<case>.json is each case's resolved plan, and
golden/stubs/ the rendered stubs. After an intended change, regenerate them with
  UPDATE_GOLDEN=1 python3 -m unittest discover -s runner/tests
and review the diff: it is the change in behavior.
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apply  # noqa: E402
import plan  # noqa: E402
from common import FactoryError, load_features, load_pipeline  # noqa: E402

GOLDEN = Path(__file__).parent / "golden"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"

BASE = {
    "repository": "acme/app", "server_url": "https://github.com", "run_id": "99",
    "factory": {"repo": "acme/factory", "sha": "a" * 40, "ref": "refs/tags/v0.2", "release": "v0.2.0"},
    "tags": {"v0.2": "a" * 40, "v0.2.0": "a" * 40},
    "config": {"features": {"off": ["spec-auto-advance", "skill-sources", "session-archive", "dependency-bots"]}},
}
PR = {"number": 3, "labels": [], "state": "open", "draft": False, "head_ref": "feat/x",
      "base_sha": "1" * 40, "head_sha": "2" * 40, "changed_lines": 120}

CASES = {
    "triage": dict(stage="triage", event_name="issues",
                   event={"action": "opened", "issue": {"number": 7, "author_association": "OWNER"}},
                   item={"number": 7, "labels": []}),
    "triage-outsider": dict(stage="triage", event_name="issues",
                            event={"action": "opened", "issue": {"number": 7, "author_association": "NONE"}},
                            item={"number": 7, "labels": []}),
    "spec-approved-risk": dict(stage="spec", event_name="issues", event={"action": "labeled", "label": {"name": "factory:approved"}},
                               item={"number": 7, "labels": ["ready-to-spec", "invariant-risk", "factory:approved"]}),
    "spec-local-label": dict(stage="spec", event_name="issues", event={"action": "labeled", "label": {"name": "factory:local"}},
                             item={"number": 7, "labels": ["ready-to-spec", "factory:local"]}),
    "implement-autonomous-verify": dict(stage="implement", event_name="workflow_dispatch", params={"issue_number": 7},
                                        item={"number": 7, "labels": ["ready-to-implement", "factory:agent"]},
                                        config={"verify": True, "features": {"off": ["spec-auto-advance", "skill-sources", "session-archive", "dependency-bots"]}}),
    "implement-config-local": dict(stage="implement", event_name="issues", event={"action": "labeled", "label": {"name": "ready-to-implement"}},
                                   item={"number": 8, "labels": ["ready-to-implement"]},
                                   config={"stages": {"implement": {"runtime": "local"}}, "features": {"off": ["spec-auto-advance", "skill-sources", "session-archive", "dependency-bots"]}}),
    "implement-wrong-label": dict(stage="implement", event_name="issues", event={"action": "labeled", "label": {"name": "factory:approved"}},
                                  item={"number": 8, "labels": ["ready-to-spec", "factory:approved"]}),
    "review-small": dict(stage="review", event_name="pull_request_target", event={"action": "opened"}, item=PR),
    "review-large-vars": dict(stage="review", event_name="workflow_dispatch", params={"pr_number": 3},
                              item=dict(PR, changed_lines=900), variables={"FACTORY_MODEL_REVIEW": "deep", "FACTORY_EFFORT_REVIEW": "high"}),
    "review-draft": dict(stage="review", event_name="pull_request_target", event={"action": "synchronize"}, item=dict(PR, draft=True)),
    "review-release-please": dict(stage="review", event_name="pull_request_target", event={"action": "opened"},
                                  item=dict(PR, head_ref="release-please--branches--main")),
    "bet-intake": dict(stage="bet-intake", event_name="workflow_dispatch", params={}, files={"bets.md": True}),
    "bet-intake-no-bets": dict(stage="bet-intake", event_name="workflow_dispatch", params={}, files={"bets.md": False}),
    "improve-review": dict(stage="improve-review", event_name="schedule"),
    "dependency-bump": dict(stage="dependency-bump", event_name="repository_dispatch",
                            event={"action": "factory-dependency-release",
                                   "client_payload": {"source_repo": "acme/lib", "package": "@acme/lib", "tag": "ts-v0.3.0", "breaking": False}}),
    "dependency-bump-breaking": dict(stage="dependency-bump", event_name="workflow_dispatch",
                                     params={"source_repo": "acme/lib", "package": "@acme/lib", "tag": "ts-v1.0.0", "breaking": True}),
    "notify-consumers": dict(stage="notify-consumers", event_name="push", params={"tag": "ts-v0.3.0", "package": "@acme/lib"}),
    "review-archive": dict(stage="review", event_name="pull_request_target", event={"action": "opened"}, item=PR, private=True,
                           config={"features": {"on": ["session-archive"], "off": ["spec-auto-advance"]},
                                   "sessions": {"archive": "acme/factory-sessions"}}),
    "update-newer-line": dict(stage="triage", event_name="workflow_dispatch", params={"issue_number": 7}, item={"number": 7, "labels": []},
                              tags={"v0.2": "a" * 40, "v0.2.0": "a" * 40, "v0.3": "b" * 40, "v0.3.0": "b" * 40}),
}


def ctx(case):
    c = copy.deepcopy(BASE)
    c.update(copy.deepcopy(CASES[case]))
    return c


class Golden(unittest.TestCase):
    def test_each_case_matches_its_golden_plan(self):
        for case in CASES:
            with self.subTest(case=case):
                got = json.dumps(plan.resolve(ctx(case)), indent=2, sort_keys=True) + "\n"
                path = GOLDEN / f"{case}.json"
                if UPDATE:
                    path.write_text(got)
                self.assertEqual(path.read_text(), got, f"{case}: plan changed; see the module docstring")

    def test_stubs_match_their_goldens(self):
        pipeline = load_pipeline()
        for name in pipeline["stages"]:
            with self.subTest(stage=name):
                got = plan.stub_text(pipeline, name, "acme/factory", "v0.2")
                path = GOLDEN / "stubs" / f"factory-{name}.yml"
                if UPDATE:
                    path.parent.mkdir(exist_ok=True)
                    path.write_text(got)
                self.assertEqual(path.read_text(), got)


class Resolution(unittest.TestCase):
    def test_runs_and_skips(self):
        want = {"triage": True, "triage-outsider": False, "implement-wrong-label": False, "review-draft": False,
                "review-release-please": False, "bet-intake-no-bets": False, "notify-consumers": True}
        for case, run in want.items():
            with self.subTest(case=case):
                self.assertEqual(plan.resolve(ctx(case))["run"], run)

    def test_model_tiers_and_conditions(self):
        self.assertEqual(plan.resolve(ctx("triage"))["agent"]["model"], "claude-haiku-5-5")
        p = plan.resolve(ctx("spec-approved-risk"))
        self.assertEqual((p["agent"]["model"], p["agent"]["effort"]), ("claude-opus-5-5", "high"))
        self.assertEqual(plan.resolve(ctx("implement-autonomous-verify"))["agent"]["model"], "claude-haiku-5-5")
        self.assertEqual(plan.resolve(ctx("review-small"))["agent"]["model"], "claude-haiku-5-5")
        p = plan.resolve(ctx("review-large-vars"))
        self.assertEqual((p["agent"]["model"], p["agent"]["effort"]), ("claude-opus-5-5", "high"))
        self.assertEqual(p["sources"]["agent.tier"], "variable")

    def test_risk_beats_autonomous(self):
        c = ctx("implement-autonomous-verify")
        c["item"]["labels"].append("invariant-risk")
        p = plan.resolve(c)
        self.assertEqual(p["agent"]["model"], "claude-opus-5-5")
        self.assertEqual(p["conditions"], ["autonomous", "risk"])

    def test_variable_beats_config_beats_default(self):
        c = ctx("implement-autonomous-verify")
        c["config"]["stages"] = {"implement": {"when": {"autonomous": {"tier": "balanced"}}}}
        self.assertEqual(plan.resolve(c)["agent"]["model"], "claude-sonnet-5-5")
        c["variables"] = {"FACTORY_MODEL_IMPLEMENT_AGENT": "claude-opus-5-5"}
        self.assertEqual(plan.resolve(c)["agent"]["model"], "claude-opus-5-5")
        c["config"]["tiers"] = {"fast": "claude-sonnet-5-5"}
        c["variables"] = {}
        c["config"]["stages"] = {}
        self.assertEqual(plan.resolve(c)["agent"]["model"], "claude-sonnet-5-5")

    def test_runtime_label_and_config(self):
        self.assertEqual(plan.resolve(ctx("spec-local-label"))["runtime"], "local")
        p = plan.resolve(ctx("implement-config-local"))
        self.assertEqual(p["runtime"], "local")
        self.assertEqual(p["apply"], [])
        self.assertNotIn("mcp__playwright", p["agent"]["allowed_tools"])

    def test_verify_attaches_the_browser(self):
        p = plan.resolve(ctx("implement-autonomous-verify"))
        self.assertIn("mcp__playwright", p["agent"]["allowed_tools"])
        self.assertIn("--mcp-config .claude/skills/verify-behavior/playwright-mcp.json", p["claude_args"])
        c = ctx("implement-autonomous-verify")
        c["config"]["verify"] = False
        self.assertNotIn("mcp__playwright", plan.resolve(c)["agent"]["allowed_tools"])

    def test_breaking_release_has_no_agent(self):
        p = plan.resolve(ctx("dependency-bump-breaking"))
        self.assertIsNone(p["agent"])
        self.assertEqual(p["apply"][0], "open-breaking-issue")
        self.assertEqual(p["params"]["version"], "1.0.0")

    def test_bad_params_are_refused(self):
        c = ctx("dependency-bump-breaking")
        c["params"]["package"] = "x; rm -rf /"
        with self.assertRaises(FactoryError):
            plan.resolve(c)

    def test_dispatch_without_state_fails(self):
        c = ctx("implement-autonomous-verify")
        c["item"]["labels"] = []
        with self.assertRaises(FactoryError):
            plan.resolve(c)

    def test_triage_all_authors_variable(self):
        c = ctx("triage-outsider")
        c["variables"] = {"FACTORY_TRIAGE_ALL": "true"}
        self.assertTrue(plan.resolve(c)["run"])

    def test_disabled_stage(self):
        c = ctx("triage")
        c["config"]["stages"] = {"triage": {"enabled": False}}
        self.assertFalse(plan.resolve(c)["run"])

    def test_every_prompt_renders_without_unknown_placeholders(self):
        for case in CASES:
            p = plan.resolve(ctx(case))
            self.assertNotIn("{{", p["prompt"], case)

    def test_unknown_placeholder_fails(self):
        with self.assertRaises(FactoryError):
            plan.render_prompt("hi {{nope}}", {}, "t")


class Flags(unittest.TestCase):
    FEATURES = {"a": {"summary": "A.", "state": "preview"}, "b": {"summary": "B.", "state": "default"}}

    def flags(self, cfg=None, variables=None):
        pipeline = load_pipeline()
        settings, _ = plan.layered(pipeline, cfg, variables or {})
        return plan.resolve_flags(self.FEATURES, settings, variables or {})

    def test_defaults(self):
        on, _, undecided = self.flags()
        self.assertEqual(on, {"a": False, "b": True})
        self.assertEqual(undecided, ["a", "b"])

    def test_preview_all_and_opt_out(self):
        on, _, undecided = self.flags({"features": {"preview": "all", "off": ["b"]}})
        self.assertEqual(on, {"a": True, "b": False})
        self.assertEqual(undecided, ["a"])

    def test_variable_wins(self):
        on, why, _ = self.flags({"features": {"on": ["a"]}}, {"FACTORY_FEATURES_OFF": "a"})
        self.assertFalse(on["a"])
        self.assertEqual(why["a"], "variable FACTORY_FEATURES_OFF")

    def test_yaml_booleans_for_on_and_off(self):
        on, _, _ = self.flags({"features": {True: ["a"], False: ["b"]}})
        self.assertEqual(on, {"a": True, "b": False})

    def test_spec_auto_advance_gates_the_medium_spec_rule(self):
        c = ctx("triage")
        rules = plan.resolve(c)["autonomy"]["rules"]
        self.assertFalse(any(r.get("feature") for r in rules))
        c["config"] = {}
        rules = plan.resolve(c)["autonomy"]["rules"]
        self.assertTrue(any(r.get("feature") == "spec-auto-advance" for r in rules))

    def test_shipped_flags_are_well_formed(self):
        for flag, spec in load_features().items():
            self.assertEqual(set(spec) >= {"summary", "stages", "state", "added", "cost"}, True, flag)
            self.assertIn(spec["state"], ("preview", "default"), flag)


class Updates(unittest.TestCase):
    def test_newer_line_opens_an_issue(self):
        p = plan.resolve(ctx("update-newer-line"))
        self.assertTrue(p["update"]["needed"])
        self.assertEqual(p["update"]["newer_line"], "v0.3")
        self.assertIn("open-update-issue", p["apply"])
        self.assertRegex(p["update"]["body"], r"<!-- factory:update [0-9a-f]{12} -->")

    def test_nothing_pending(self):
        p = plan.resolve(ctx("triage"))
        self.assertFalse(p["update"]["needed"])
        self.assertNotIn("open-update-issue", p["apply"])

    def test_undecided_flag_on_main(self):
        c = ctx("triage")
        c["config"] = {"features": {"preview": "all"}}
        c["factory"]["ref"] = "refs/heads/main"
        u = plan.resolve(c)["update"]
        self.assertEqual((u["needed"], u["newer_line"], u["pending"]), (True, None, ["spec-auto-advance", "skill-sources", "session-archive", "dependency-bots"]))
        self.assertIn("(preview, on now through features.preview)", u["body"])

    def test_preview_flag_wording_follows_features_preview(self):
        feats = {"p": {"summary": "s", "stages": [], "state": "preview", "added": "0.2.0", "cost": ""},
                 "d": {"summary": "s", "stages": [], "state": "default", "added": "0.2.0", "cost": ""}}
        fac = {"factory": {"ref": "refs/heads/main", "sha": "a" * 40, "repo": "acme/factory"}}
        for preview, want in (([], "(preview, off until you opt in)"), ("all", "(preview, on now through features.preview)"),
                              (["p"], "(preview, on now through features.preview)")):
            with self.subTest(preview=preview):
                body = plan.update_check(fac, {"features": {"preview": preview}}, feats, ["p", "d"])["body"]
                self.assertIn(want, body)
                self.assertIn("`d` (default, on now)", body)

    def test_check_false(self):
        c = ctx("update-newer-line")
        c["config"]["updates"] = {"check": False}
        self.assertFalse(plan.resolve(c)["update"]["needed"])


class Sessions(unittest.TestCase):
    def sessions(self, archive="acme/factory-sessions", on=True, private=True, **over):
        c = ctx("review-small")
        c["private"] = private
        c["config"] = {"features": {"on" if on else "off": ["session-archive"], "off": ["spec-auto-advance"]} if on else
                       {"off": ["spec-auto-advance", "session-archive"]}}
        if archive:
            c["config"]["sessions"] = {"archive": archive}
        c.update(over)
        return plan.resolve(c)["sessions"]

    def test_kept_when_flag_on_and_archive_named(self):
        self.assertEqual(self.sessions(), {"archive": "acme/factory-sessions", "reason": "config.yml sessions.archive",
                                           "encrypt": False})

    def test_public_repository_encrypts(self):
        self.assertTrue(self.sessions(private=False)["encrypt"])

    def test_not_kept(self):
        for kw, why in ((dict(on=False), "flag session-archive is off"),
                        (dict(archive=""), "names no sessions.archive"),
                        (dict(archive="acme/app"), "repository itself"),
                        (dict(archive="other/sessions"), "isn't owned by acme")):
            with self.subTest(**kw):
                s = self.sessions(**kw)
                self.assertEqual((s["archive"], s["encrypt"]), ("", False))
                self.assertIn(why, s["reason"])

    def test_local_runtime_keeps_its_own(self):
        c = ctx("spec-local-label")
        c["config"] = {"features": {"on": ["session-archive"], "off": ["spec-auto-advance"]}, "sessions": {"archive": "acme/s"}}
        self.assertIn("local runtime", plan.resolve(c)["sessions"]["reason"])

    def test_archive_must_be_a_repository(self):
        problems, _ = plan.validate_config({"sessions": {"archive": "not a repo"}}, load_pipeline(), load_features())
        self.assertIn("sessions.archive must be a repository, owner/name", problems)
        problems, _ = plan.validate_config({"sessions": {"keep": True}}, load_pipeline(), load_features())
        self.assertIn("unknown key 'sessions.keep'", problems)


class Config(unittest.TestCase):
    def check(self, cfg):
        return plan.validate_config(cfg, load_pipeline(), load_features())

    def test_template_is_valid(self):
        from common import load_yaml
        problems, warnings = self.check(load_yaml(Path(__file__).resolve().parents[2] / "templates/repo/config.yml"))
        self.assertEqual((problems, warnings), ([], []))

    def test_problems(self):
        problems, _ = self.check({"autonomy": "yolo", "stages": {"triage": {"runtime": "local"}, "nope": {}}, "colour": 1})
        self.assertEqual(len(problems), 4, problems)

    def test_autonomy_off_as_yaml_boolean(self):
        self.assertEqual(self.check({"autonomy": False}), ([], []))

    def test_unknown_flag_is_a_warning(self):
        self.assertEqual(self.check({"features": {"off": ["gone"]}})[1], ["features.off: no flag 'gone' in this factory version"])


class Bots(unittest.TestCase):
    def bots(self, config=None, flag=False):
        c = ctx("review-small")
        c["config"] = copy.deepcopy(config or {})
        c["config"].setdefault("features", {})["on" if flag else "off"] = ["dependency-bots"]
        p = plan.resolve(c)
        return p["allowed_bots"].split(","), p["sources"]["allowed_bots"]

    def test_default_list(self):
        self.assertEqual(self.bots(), (["github-actions", "github-actions[bot]", "claude[bot]", "dependabot[bot]"],
                                       "pipeline.yaml"))

    def test_flag_adds_renovate(self):
        bots, why = self.bots(flag=True)
        self.assertEqual(bots[-1], "renovate[bot]")
        self.assertEqual(why, "pipeline.yaml, flag dependency-bots")

    def test_config_adds_without_duplicates(self):
        bots, why = self.bots({"dependencies": {"bots": ["my-app[bot]", "dependabot[bot]"]}})
        self.assertEqual(bots[-2:], ["dependabot[bot]", "my-app[bot]"])
        self.assertEqual(bots.count("dependabot[bot]"), 1)
        self.assertEqual(why, "pipeline.yaml, config.yml dependencies.bots")

    def test_config_is_checked(self):
        check = lambda cfg: plan.validate_config(cfg, load_pipeline(), load_features())[0]  # noqa: E731
        self.assertEqual(check({"dependencies": {"bots": ["my-app[bot]", "a-user"]}}), [])
        bad = "dependencies.bots must be a list of GitHub account names, e.g. my-app[bot]"
        for v in (["*"], "my-app[bot]", ["a b"], [1]):
            self.assertEqual(check({"dependencies": {"bots": v}}), [bad], v)
        self.assertEqual(check({"dependencies": {"updater": "renovate"}}), ["unknown key 'dependencies.updater'"])


class Stubs(unittest.TestCase):
    def test_check_stubs(self):
        pipeline = load_pipeline()
        with tempfile.TemporaryDirectory() as d:
            for name in pipeline["stages"]:
                Path(d, f"factory-{name}.yml").write_text(plan.stub_text(pipeline, name, "acme/factory", "v0.2"))
            self.assertTrue(plan.check_stubs(Path(d))[1])
            f = Path(d, "factory-triage.yml")
            f.write_text(f.read_text().replace("cancel-in-progress: true", "cancel-in-progress: false"))
            lines, ok = plan.check_stubs(Path(d))
            self.assertFalse(ok)
            self.assertTrue(any(x.startswith("edited") for x in lines))

    def test_stub_names_only_the_factory(self):
        text = plan.stub_text(load_pipeline(), "review", "acme/factory", "v0.2")
        self.assertIn("uses: acme/factory/.github/workflows/stage.yml@v0.2", text)
        self.assertIn("id-token: write", text)
        self.assertIn("pull-requests: write", text)

    def test_bad_ref_refused(self):
        with self.assertRaises(FactoryError):
            plan.stub_text(load_pipeline(), "review", "acme/factory", "v0.2; rm")


class Route(unittest.TestCase):
    def route(self, result, labels=(), cfg=None):
        c = ctx("triage")
        c["config"] = cfg if cfg is not None else {}
        p = plan.resolve(c)
        base = {"state": "ready-to-implement", "size": "small", "risk_labels": [], "autonomy": "agent"}
        base.update(result)
        return apply.decide_route(p, base, list(labels), load_pipeline())

    def test_small_implement_goes_to_an_agent(self):
        self.assertEqual(self.route({}), {"advance": "agent", "risky": False, "next_stage": "implement"})

    def test_medium_spec_needs_the_flag(self):
        self.assertEqual(self.route({"state": "ready-to-spec", "size": "medium"})["advance"], "agent")
        off = self.route({"state": "ready-to-spec", "size": "medium"}, cfg={"features": {"off": ["spec-auto-advance"]}})
        self.assertEqual(off["advance"], "human")

    def test_risk_and_policy_off(self):
        self.assertEqual(self.route({"risk_labels": ["invariant-risk"]})["advance"], "human")
        self.assertEqual(self.route({}, labels=["invariant-risk"])["advance"], "human")
        self.assertEqual(self.route({}, cfg={"autonomy": "off"})["advance"], "human")
        self.assertEqual(self.route({"autonomy": "human"})["advance"], "human")

    def test_needs_info_has_no_next_stage(self):
        self.assertEqual(self.route({"state": "needs-info"})["advance"], "none")

    def test_patch_problems(self):
        self.assertTrue(apply.patch_problems([".github/workflows/ci.yml"], None))
        self.assertTrue(apply.patch_problems(["src/a.ts"], [".claude/skills/review-pr-local/"]))
        self.assertEqual(apply.patch_problems([".claude/skills/review-pr-local/SKILL.md"], [".claude/skills/review-pr-local/"]), [])

    def test_create_labels_and_consumers(self):
        self.assertEqual(apply.item_labels_for_create(["factory:proposed", "bet:b-1", "ready-to-implement", "evil"], load_pipeline()),
                         ["factory:proposed", "bet:b-1"])
        md = "# x\n## Consumers\n- `acme/web`: uses it\n- owner/repo\n## Other\n- `acme/no`\n"
        self.assertEqual(apply.consumers(md), ["acme/web"])

    def test_free_branch(self):
        self.assertEqual(apply.free_branch("fix/a", set(), "7"), "fix/a")
        self.assertEqual(apply.free_branch("fix/a", {"fix/a"}, "7"), "fix/a-run7")
        self.assertEqual(apply.free_branch("fix/a", {"fix/a", "fix/a-run7"}, "7"), "fix/a-run7-2")

    def test_triage_comment(self):
        r = {"state": "ready-to-spec", "size": "medium", "comment": "Line one.\\nLine two.", "autonomy_reason": "Why.", "bet": None}
        body = apply.triage_comment(r, {"advance": "human"}, "https://run", "factory:approved")
        self.assertIn("Line one.\nLine two.", body)
        self.assertIn("Add the `factory:approved` label to start.", body)
        self.assertIn("bet `none`", body)


class ToolsNote(unittest.TestCase):
    def test_limited_shell_lists_the_commands(self):
        note = plan.tools_note(["Read", "Write", "Bash(python3 validate.py:*)"])
        self.assertIn("`Read`, `Write`", note)
        self.assertIn("`python3 validate.py`", note)
        self.assertIn("no `&&`", note)

    def test_no_shell_and_full_shell(self):
        self.assertIn("There is no shell.", plan.tools_note(["Read", "Glob", "Grep"]))
        self.assertEqual(plan.tools_note(["Bash", "Read"]), "")

    def test_review_prompt_carries_it(self):
        p = plan.resolve(ctx("review-small"))
        self.assertIn("validate_review_json.py`", p["prompt"].split("Your tools in this run:")[1])


if __name__ == "__main__":
    unittest.main()
