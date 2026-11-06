"""The factory's work tracker: the only code that talks to GitHub Issues.

    python3 runner/tracker.py <command> …      (scripts/factory tracker <command> …)

Label names come from pipeline.yaml. Write commands accept only the labels it declares,
plus bet:<id> for create. Every gh call gets --repo $GITHUB_REPOSITORY when it is set.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re

from common import FACTORY_ROOT, FactoryError, gh, label_roles, load_pipeline, main_guard

ROLES = label_roles(load_pipeline())
STATES = ROLES["states"]
MARKERS = ROLES["markers"]
GATE = ROLES["gate"]  # {"awaiting": ..., "approved": ..., "agent": ...}
GATE_ORDER = ("awaiting", "approved", "agent")
BET_LABEL = re.compile(r"bet:[a-z0-9-]+")
STOP_WORDS = {"that", "this", "with", "from", "into", "when", "should", "have", "will", "after", "before", "issue"}


def _declared() -> set[str]:
    return (set(STATES) | set(MARKERS) | set(GATE.values())
            | set(ROLES["kinds"].values()) | set(ROLES["runtime_labels"]))


def _check_label(name: str, allow_bet: bool = False) -> None:
    if name in _declared() or (allow_bet and BET_LABEL.fullmatch(name)):
        return
    raise FactoryError(f"unknown label {name!r}: pipeline.yaml does not declare it")


def _check_state(state: str) -> None:
    if state not in STATES:
        raise FactoryError(f"unknown state {state!r}; states are {', '.join(STATES)}")


@functools.lru_cache(maxsize=None)
def _label_specs() -> dict[str, tuple[str, str]]:
    """name -> (color, description) from templates/labels.txt (name|color|description)."""
    specs = {}
    for line in (FACTORY_ROOT / "templates" / "labels.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            name, color, description = line.split("|", 2)
            specs[name] = (color, description)
    return specs


def _gh(*args: str) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    return gh(*args, *(["--repo", repo] if repo else []))


def _json(*args: str):
    out = _gh(*args)
    return json.loads(out) if out.strip() else None


def _names(item: dict) -> list[str]:
    return [label["name"] for label in item.get("labels") or []]


def _labels_of(n: int) -> list[str]:
    return _names(_json("issue", "view", str(n), "--json", "labels"))


def _ensure_label(name: str) -> None:
    args = ["label", "create", name, "--force"]
    if name in _label_specs():
        color, description = _label_specs()[name]
        args += ["--color", color, "--description", description]
    _gh(*args)


def _edit_labels(n: int, add=(), remove=()) -> None:
    if not add and not remove:
        return
    args = ["issue", "edit", str(n)]
    for name in add:
        _ensure_label(name)
        args += ["--add-label", name]
    for name in remove:
        args += ["--remove-label", name]
    _gh(*args)


def get(n: int) -> dict:
    data = _json("issue", "view", str(n), "--json",
                 "number,title,body,url,author,authorAssociation,labels,comments")
    names = _names(data)
    return {
        "number": data["number"],
        "title": data["title"],
        "body": data.get("body") or "",
        "url": data["url"],
        "author": (data.get("author") or {}).get("login"),
        "author_association": data.get("authorAssociation"),
        "labels": names,
        "state": next((s for s in STATES if s in names), None),
        "markers": [m for m in MARKERS if m in names],
        "gate": next((g for g in GATE_ORDER if GATE[g] in names), None),
        "comments": [{"author": (c.get("author") or {}).get("login"), "body": c.get("body") or "",
                      "created_at": c.get("createdAt")} for c in data.get("comments") or []],
    }


def related(n: int) -> list[dict]:
    title = _json("issue", "view", str(n), "--json", "title")["title"]
    words = sorted({w for w in re.findall(r"[a-z0-9]+", title.lower())
                    if len(w) > 3 and w not in STOP_WORDS}, key=lambda w: (-len(w), w))[:4]
    if not words:
        return []
    rows = _json("issue", "list", "--state", "open", "--search", " ".join(words) + " in:title",
                 "--limit", "21", "--json", "number,title,labels") or []
    found = [{"number": r["number"], "title": r["title"], "labels": _names(r)}
             for r in rows if r["number"] != int(n)]
    return found[:20]


def list_items(label: str | None = None, state: str = "open", limit: int = 100) -> list[dict]:
    if state not in ("open", "closed", "all"):
        raise FactoryError(f"state must be open, closed or all, not {state!r}")
    args = ["issue", "list", "--state", state, "--limit", str(limit), "--json", "number,title,labels"]
    if label:
        args += ["--label", label]
    rows = _json(*args) or []
    return [{"number": r["number"], "title": r["title"], "labels": _names(r)} for r in rows]


def set_state(n: int, state: str) -> None:
    _check_state(state)
    current = _labels_of(n)
    _edit_labels(n, add=[] if state in current else [state],
                 remove=[s for s in STATES if s != state and s in current])


def add_marker(n: int, marker: str) -> None:
    if marker not in MARKERS:
        raise FactoryError(f"unknown marker {marker!r}; markers are {', '.join(MARKERS)}")
    _edit_labels(n, add=[marker])


def gate(n: int, value: str) -> None:
    if value not in ("awaiting", "agent", "clear", "started"):
        raise FactoryError(f"gate must be awaiting, agent, clear or started, not {value!r}")
    wanted = [] if value in ("clear", "started") else [GATE[value]]
    current = _labels_of(n)
    # approved is never removed here; `started` (a stage began) removes only awaiting
    others = [GATE["awaiting"]] if value == "started" else [GATE["awaiting"], GATE["agent"]]
    _edit_labels(n, add=[w for w in wanted if w not in current],
                 remove=[o for o in others if o in current and o not in wanted])


def comment(n: int, body_file: str) -> None:
    _gh("issue", "comment", str(n), "--body-file", body_file)


def create(title: str, body_file: str, state: str | None = None, labels=()) -> int:
    names = list(labels)
    if state is not None:
        _check_state(state)
        names.insert(0, state)
    for name in names:
        _check_label(name, allow_bet=True)
    args = ["issue", "create", "--title", title, "--body-file", body_file]
    for name in names:
        _ensure_label(name)
        args += ["--label", name]
    out = _gh(*args)
    match = re.search(r"/issues/(\d+)", out)
    if not match:
        raise FactoryError(f"gh did not print the new issue's URL: {out.strip()!r}")
    number = int(match.group(1))
    print(number)
    return number


def edit(n: int, body_file: str) -> None:
    _gh("issue", "edit", str(n), "--body-file", body_file)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factory tracker", description="Read and write the work tracker.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("get", help="an issue as JSON").add_argument("number", type=int)
    sub.add_parser("related", help="open issues that may be neighbours").add_argument("number", type=int)
    p = sub.add_parser("list", help="issues as JSON")
    p.add_argument("--label")
    p.add_argument("--state", default="open", choices=["open", "closed", "all"])
    p.add_argument("--limit", type=int, default=100)
    p = sub.add_parser("set-state", help="set the readiness state")
    p.add_argument("number", type=int)
    p.add_argument("state")
    p = sub.add_parser("add-marker", help="add a marker label")
    p.add_argument("number", type=int)
    p.add_argument("marker")
    p = sub.add_parser("gate", help="set the gate label")
    p.add_argument("number", type=int)
    p.add_argument("value", choices=["awaiting", "agent", "clear", "started"])
    p = sub.add_parser("comment", help="post a file as a comment")
    p.add_argument("number", type=int)
    p.add_argument("file")
    p = sub.add_parser("create", help="create an issue and print its number")
    p.add_argument("title")
    p.add_argument("body_file")
    p.add_argument("--state")
    p.add_argument("--label", action="append")
    p = sub.add_parser("edit", help="replace the issue body with a file")
    p.add_argument("number", type=int)
    p.add_argument("body_file")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "get":
        print(json.dumps(get(args.number), indent=2))
    elif args.command == "related":
        print(json.dumps(related(args.number), indent=2))
    elif args.command == "list":
        print(json.dumps(list_items(args.label, args.state, args.limit), indent=2))
    elif args.command == "set-state":
        set_state(args.number, args.state)
    elif args.command == "add-marker":
        add_marker(args.number, args.marker)
    elif args.command == "gate":
        gate(args.number, args.value)
    elif args.command == "comment":
        comment(args.number, args.file)
    elif args.command == "create":
        create(args.title, args.body_file, args.state, args.label or [])
    elif args.command == "edit":
        edit(args.number, args.body_file)
    return 0


if __name__ == "__main__":
    main_guard(main)
