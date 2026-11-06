"""Shared helpers for the factory's runner: loading pipeline.yaml, features.yaml and config.yml."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parent.parent


class FactoryError(Exception):
    """A problem the caller should see as one line, without a traceback."""


def load_yaml_text(text: str, where: str = "YAML"):
    try:
        import yaml  # PyYAML: preinstalled or installed by prepare; `uv run --with pyyaml` locally
    except ImportError as exc:  # pragma: no cover - depends on the machine
        raise FactoryError(
            "needs PyYAML: `python3 -m pip install pyyaml`, or run through `uv run --with pyyaml`"
        ) from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise FactoryError(f"{where} is not valid YAML: {exc}") from exc


def load_yaml(path: Path | str):
    path = Path(path)
    return load_yaml_text(path.read_text(encoding="utf-8"), str(path))


def load_pipeline(root: Path | str | None = None) -> dict:
    return load_yaml(Path(root or FACTORY_ROOT) / "pipeline.yaml")


def load_features(root: Path | str | None = None) -> dict:
    return load_yaml(Path(root or FACTORY_ROOT) / "features.yaml") or {}


def label_roles(pipeline: dict) -> dict:
    """Every label the pipeline knows, by role, as {"states": [...], "markers": [...], ...}."""
    return {
        "states": list(pipeline["states"]),
        "markers": list(pipeline["markers"]),
        "gate": dict(pipeline["gate"]),
        "kinds": dict(pipeline.get("kinds", {})),
        "runtime_labels": dict(pipeline.get("runtime_labels", {})),
    }


def gh(*args: str, input_text: str | None = None, token: str | None = None, check: bool = True) -> str:
    """Run the GitHub CLI and return stdout. `token` overrides GH_TOKEN for this call."""
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    proc = subprocess.run(
        ["gh", *args], input=input_text, capture_output=True, text=True, env=env
    )
    if check and proc.returncode != 0:
        raise FactoryError(f"gh {' '.join(args[:3])}…: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def gh_json(*args: str, token: str | None = None):
    out = gh(*args, token=token)
    return json.loads(out) if out.strip() else None


def main_guard(fn):
    """Run a CLI entry point, printing FactoryError as one line."""
    try:
        sys.exit(fn() or 0)
    except FactoryError as exc:
        print(f"factory: {exc}", file=sys.stderr)
        sys.exit(1)
