"""Tests for runner/tracker.py. gh is replaced by a fake, so nothing reaches GitHub."""

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tracker  # noqa: E402
from common import FactoryError  # noqa: E402


class FakeGh:
    """Records each gh call; answers with `replies`, keyed by the first two arguments."""

    def __init__(self):
        self.replies = {}
        self.calls = []

    def __call__(self, *args, input_text=None, token=None, check=True):
        self.calls.append(list(args))
        return self.replies.get(" ".join(args[:2]), "")

    def ops(self, key):
        return [c for c in self.calls if " ".join(c[:2]) == key]


def pairs(call):
    """The --flag value pairs of a gh call, in order."""
    return [(call[i], call[i + 1]) for i in range(len(call) - 1) if call[i].startswith("--")
            and not call[i + 1].startswith("--")]


class TrackerTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("GITHUB_REPOSITORY", None)
        self.fake = FakeGh()
        patch = mock.patch.object(tracker, "gh", self.fake)
        patch.start()
        self.addCleanup(patch.stop)

    def view(self, *label_names, **extra):
        data = {"number": 5, "title": "Fix the tracker writes", "body": "",
                "url": "https://example.test/issues/5", "labels": [{"name": n} for n in label_names]}
        data.update(extra)
        self.fake.replies["issue view"] = json.dumps(data)

    def test_unknown_labels_rejected_without_calling_gh(self):
        for call in (
            lambda: tracker.add_marker(5, "bogus"),
            lambda: tracker.set_state(5, "bogus"),
            lambda: tracker.set_state(5, "maintenance"),  # a kind, not a state
            lambda: tracker.gate(5, "bogus"),
            lambda: tracker.create("t", "body.md", labels=["bogus"]),
            lambda: tracker.create("t", "body.md", labels=["bet:Not_Valid"]),
            lambda: tracker.create("t", "body.md", state="maintenance"),
        ):
            with self.subTest():
                with self.assertRaises(FactoryError):
                    call()
        self.assertEqual(self.fake.calls, [])

    def test_bet_label_accepted_on_create(self):
        self.fake.replies["issue create"] = "https://github.com/o/r/issues/7\n"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tracker.create("Bet work", "body.md", labels=["bet:checkout-2"]), 7)
        create = self.fake.ops("issue create")[0]
        self.assertIn(("--label", "bet:checkout-2"), pairs(create))
        label = self.fake.ops("label create")[0]
        self.assertNotIn("--color", label)  # not in templates/labels.txt, so no colour

    def test_set_state_removes_the_other_states(self):
        self.view("needs-info", "invariant-risk")
        tracker.set_state(5, "ready-to-implement")
        edits = self.fake.ops("issue edit")
        self.assertEqual(len(edits), 1)
        # Only the state the issue has is removed; the marker stays.
        self.assertEqual(pairs(edits[0]), [("--add-label", "ready-to-implement"),
                                           ("--remove-label", "needs-info")])

    def test_set_state_does_nothing_when_already_set(self):
        self.view("ready-to-spec")
        tracker.set_state(5, "ready-to-spec")
        self.assertEqual(self.fake.ops("issue edit"), [])

    def test_gate_agent_awaiting_clear(self):
        self.view("factory:awaiting-approval", "factory:approved")
        tracker.gate(5, "agent")
        self.assertEqual(pairs(self.fake.ops("issue edit")[-1]),
                         [("--add-label", "factory:agent"),
                          ("--remove-label", "factory:awaiting-approval")])

        self.fake.calls.clear()
        self.view("factory:agent", "factory:approved")
        tracker.gate(5, "clear")
        self.assertEqual(pairs(self.fake.ops("issue edit")[-1]), [("--remove-label", "factory:agent")])

        self.fake.calls.clear()
        self.view("factory:agent", "factory:approved")
        tracker.gate(5, "awaiting")
        self.assertEqual(pairs(self.fake.ops("issue edit")[-1]),
                         [("--add-label", "factory:awaiting-approval"), ("--remove-label", "factory:agent")])

    def test_get_derives_state_markers_and_gate(self):
        self.view("ready-to-spec", "invariant-risk", "factory:agent", "maintenance",
                  author={"login": "sean"}, authorAssociation="OWNER",
                  comments=[{"author": {"login": "bot"}, "body": "hi", "createdAt": "2026-01-01T00:00:00Z"}])
        item = tracker.get(5)
        self.assertEqual(item["state"], "ready-to-spec")
        self.assertEqual(item["markers"], ["invariant-risk"])
        self.assertEqual(item["gate"], "agent")
        self.assertEqual(item["labels"], ["ready-to-spec", "invariant-risk", "factory:agent", "maintenance"])
        self.assertEqual(item["author"], "sean")
        self.assertEqual(item["author_association"], "OWNER")
        self.assertEqual(item["comments"], [{"author": "bot", "body": "hi", "created_at": "2026-01-01T00:00:00Z"}])

    def test_get_with_no_state_or_gate(self):
        self.view()
        item = tracker.get(5)
        self.assertIsNone(item["state"])
        self.assertIsNone(item["gate"])
        self.assertEqual(item["markers"], [])

    def test_create_parses_the_number(self):
        self.fake.replies["issue create"] = "https://github.com/o/r/issues/42\n"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            number = tracker.create("Title", "body.md", state="ready-to-spec", labels=["factory:proposed"])
        self.assertEqual(number, 42)
        self.assertEqual(out.getvalue().strip(), "42")
        create = self.fake.ops("issue create")[0]
        self.assertEqual(pairs(create)[-2:], [("--label", "ready-to-spec"), ("--label", "factory:proposed")])

    def test_create_fails_when_no_number_is_printed(self):
        self.fake.replies["issue create"] = "something unexpected\n"
        with self.assertRaises(FactoryError):
            tracker.create("Title", "body.md")

    def test_related_drops_the_item_itself(self):
        self.view(title="Tracker writes fail on labels")
        self.fake.replies["issue list"] = json.dumps([
            {"number": 5, "title": "Tracker writes fail on labels", "labels": []},
            {"number": 9, "title": "Label writes race", "labels": [{"name": "maintenance"}]},
        ])
        self.assertEqual(tracker.related(5), [{"number": 9, "title": "Label writes race", "labels": ["maintenance"]}])
        search = self.fake.ops("issue list")[0]
        self.assertIn("in:title", search[search.index("--search") + 1])

    def test_repo_is_passed_when_github_repository_is_set(self):
        os.environ["GITHUB_REPOSITORY"] = "owner/factory"
        self.view("ready-to-spec")
        tracker.set_state(5, "ready-to-implement")
        for call in self.fake.calls:
            self.assertEqual(call[call.index("--repo") + 1], "owner/factory", call)

    def test_no_repo_flag_when_github_repository_is_unset(self):
        self.view()
        tracker.add_marker(5, "invariant-risk")
        for call in self.fake.calls:
            self.assertNotIn("--repo", call)


if __name__ == "__main__":
    unittest.main()
