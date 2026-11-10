#!/usr/bin/env python3
"""Keep one run's transcript and run record in the session archive (docs/memory.md part 1).

claude-code-action writes an execution file, a JSON array of Claude Code messages. This
script redacts it into gzipped JSON lines, builds a small run record, checks that the
archive repository is private and has the same owner as this repository, and pushes both
files with FACTORY_GITHUB_TOKEN through the contents API.

    archive.py redact --plan plan.json --execution FILE --out DIR      # agent job
    archive.py push --plan plan.json --session DIR --result DIR         # archive job
    archive.py push ... --dry-run --out DIR                             # write, don't push

`redact` runs in the agent job, after the agent, so nothing unredacted leaves it. On a
public repository anyone signed in can download a run's artifacts, so the plan asks for
the transcript to be encrypted with FACTORY_ARCHIVE_KEY; without that secret, a public
repository's transcript isn't kept (its run record still is).
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FactoryError, gh, main_guard  # noqa: E402

MAX_STRING = 20_000          # longer strings (usually tool results) keep their head and tail
MAX_ARCHIVE_BYTES = 25 << 20  # a compressed transcript larger than this isn't pushed
SECRET_ENV = re.compile(r"(TOKEN|SECRET|PASSWORD|PRIVATE_KEY|API_KEY|CREDENTIAL)", re.I)
MIN_SECRET = 8

# (kind, pattern). Kinds appear in the run record as counts, never with the matched text.
PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("auth-header", re.compile(r"(?i)(authorization:\s*(?:bearer|basic|token)\s+)[A-Za-z0-9+/=._~-]{8,}")),
    ("url-credentials", re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("aws-key-id", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("slack-token", re.compile(r"xox[abpsr]-[A-Za-z0-9-]{10,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]


def known_secrets(env: dict) -> list[str]:
    """Secret values from the environment, with the encodings git and HTTP put them in."""
    values = {v for k, v in env.items() if SECRET_ENV.search(k) and v and len(v) >= MIN_SECRET}
    out = set(values)
    for v in values:
        for raw in (v, f"x-access-token:{v}"):
            out.add(base64.b64encode(raw.encode()).decode())
    return sorted(out, key=len, reverse=True)  # longest first, so no secret is left half-replaced


class Redactor:
    def __init__(self, secrets: list[str]):
        self.secrets = secrets
        self.counts: dict[str, int] = {}
        self.truncated = 0

    def _count(self, kind: str, n: int = 1):
        if n:
            self.counts[kind] = self.counts.get(kind, 0) + n

    def text(self, s: str) -> str:
        for secret in self.secrets:
            if secret in s:
                self._count("known-secret", s.count(secret))
                s = s.replace(secret, "[REDACTED]")
        for kind, pat in PATTERNS:
            if kind in ("auth-header", "url-credentials"):
                s, n = pat.subn(lambda m: m.group(1) + "[REDACTED]" + ("@" if kind == "url-credentials" else ""), s)
            else:
                s, n = pat.subn(f"[REDACTED:{kind}]", s)
            self._count(kind, n)
        if len(s) > MAX_STRING:
            self.truncated += 1
            head, tail = MAX_STRING * 4 // 5, MAX_STRING // 5
            s = f"{s[:head]}\n[… {len(s) - head - tail} characters cut by the factory …]\n{s[-tail:]}"
        return s

    def value(self, v):
        if isinstance(v, str):
            return self.text(v)
        if isinstance(v, list):
            return [self.value(x) for x in v]
        if isinstance(v, dict):
            return {self.text(k) if isinstance(k, str) else k: self.value(x) for k, x in v.items()}
        return v


def load_messages(raw: str) -> list:
    """The execution file is a JSON array; JSON lines and plain text are accepted too."""
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        pass
    try:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    except json.JSONDecodeError:
        return [{"type": "text", "text": raw}]


def to_jsonl_gz(messages: list) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, filename="") as fh:
        for m in messages:
            fh.write((json.dumps(m, ensure_ascii=False, separators=(",", ":")) + "\n").encode())
    return buf.getvalue()


def session_stats(messages: list) -> dict:
    """Model, turns, cost and duration from Claude Code's init and result messages."""
    out: dict = {}
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("type") == "system" and m.get("subtype") == "init":
            out["model"] = m.get("model", "")
            out["claude_code_version"] = m.get("claude_code_version", "")
        if m.get("type") == "result":
            for k in ("subtype", "is_error", "num_turns", "duration_ms", "total_cost_usd"):
                if k in m:
                    out[k] = m[k]
    out["messages"] = len(messages)
    return out


def short(v, n: int = 300):
    if isinstance(v, str):
        return v if len(v) <= n else v[:n] + "…"
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, list):
        return [short(x, n) for x in v[:20]]
    if isinstance(v, dict):
        return {k: short(x, n) for k, x in list(v.items())[:30]}
    return str(v)[:n]


def agent_result(result_dir: Path | None) -> dict | None:
    """What the agent decided, shortened: result.json for structured and patch output,
    the verdict and finding count of review.json for file output."""
    if not result_dir or not result_dir.is_dir():
        return None
    r = result_dir / "result.json"
    if r.exists():
        return short(json.loads(r.read_text()))
    review = result_dir / "review.json"
    if review.exists():
        data = json.loads(review.read_text())
        return {"verdict": data.get("verdict"), "comments": len(data.get("comments") or [])}
    return None


def run_record(plan: dict, env: dict, stats: dict, result: dict | None, redaction: dict, transcript: str | None) -> dict:
    agent = plan.get("agent") or {}
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    server, repo = env.get("GITHUB_SERVER_URL", "https://github.com"), env.get("GITHUB_REPOSITORY", "")
    return {
        "version": 1,
        "repository": repo,
        "stage": plan.get("stage"),
        "item": plan.get("item") or None,
        "item_kind": plan.get("item_kind"),
        "trigger": plan.get("trigger"),
        "run_id": env.get("GITHUB_RUN_ID"),
        "run_attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "run_url": f"{server}/{repo}/actions/runs/{env.get('GITHUB_RUN_ID', '')}",
        "archived_at": env.get("FACTORY_NOW") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "factory": {k: (plan.get("factory") or {}).get(k) for k in ("repo", "sha", "ref", "release")},
        "plan_hash": hashlib.sha256(canonical.encode()).hexdigest()[:12],
        "tier": agent.get("tier"), "model": agent.get("model"), "effort": agent.get("effort"),
        "conditions": plan.get("conditions") or [],
        "flags_on": sorted(k for k, v in (plan.get("flags") or {}).items() if v),
        "apply_ops": plan.get("apply") or [],
        "jobs": {"agent": env.get("AGENT_RESULT", ""), "apply": env.get("APPLY_RESULT", "")},
        "session": stats,
        "result": result,
        "redaction": redaction,
        "transcript": transcript,
    }


def archive_paths(plan: dict, env: dict) -> tuple[str, str]:
    now = env.get("FACTORY_NOW") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    yyyy, mm = now[:4], now[5:7]
    name = env.get("GITHUB_REPOSITORY", "unknown/unknown").split("/", 1)[1]
    stem = f"{env.get('GITHUB_RUN_ID', '0')}-{env.get('GITHUB_RUN_ATTEMPT', '1')}-{plan.get('stage')}-{plan.get('item') or 'none'}"
    return (f"sessions/{name}/{yyyy}/{mm}/{stem}.jsonl.gz", f"runs/{name}/{yyyy}/{mm}/{stem}.json")


def redact_session(execution: Path | None, env: dict) -> tuple[bytes | None, dict]:
    """(compressed redacted transcript or None, session info: stats and what redaction did)."""
    red = Redactor(known_secrets(env))
    messages = []
    if execution and execution.exists():
        messages = red.value(load_messages(execution.read_text(errors="replace")))
    blob = to_jsonl_gz(messages) if messages else None
    info = {"stats": session_stats(messages), "redaction": {"counts": red.counts, "truncated_strings": red.truncated}}
    if blob is not None and len(blob) > MAX_ARCHIVE_BYTES:
        info["redaction"]["note"] = f"transcript not kept: {len(blob)} compressed bytes is over the {MAX_ARCHIVE_BYTES} limit"
        blob = None
    elif blob is None:
        info["redaction"]["note"] = "no transcript: the agent wrote no execution file"
    return blob, info


def crypt(data: bytes, key: str, decrypt: bool = False) -> bytes:
    """AES-256 with a key from FACTORY_ARCHIVE_KEY, through the runner's openssl."""
    args = ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-pass", "env:FACTORY_ARCHIVE_KEY"]
    if decrypt:
        args.append("-d")
    else:
        args.append("-salt")
    proc = subprocess.run(args, input=data, capture_output=True, env={**os.environ, "FACTORY_ARCHIVE_KEY": key})
    if proc.returncode != 0:
        raise FactoryError(f"openssl {'decryption' if decrypt else 'encryption'} failed: {proc.stderr.decode(errors='replace')[:200]}")
    return proc.stdout


# --- the archive repository --------------------------------------------------------------------

def check_archive(archive: str, repo: str, token: str) -> None:
    """Refuse an archive that isn't private, or that another owner holds."""
    proc = gh("api", f"repos/{archive}", "--jq", "{private: .private, owner: .owner.login}", token=token, check=False)
    try:
        info = json.loads(proc) if proc.strip() else None
    except json.JSONDecodeError:
        info = None
    if not info:
        raise FactoryError(f"FACTORY_GITHUB_TOKEN can't read {archive}. Add it to the token's repositories "
                           "with Contents: read and write (docs/setup.md)")
    if info.get("private") is not True:
        raise FactoryError(f"{archive} isn't private; refusing to keep sessions in it")
    if str(info.get("owner", "")).lower() != repo.split("/")[0].lower():
        raise FactoryError(f"{archive} isn't owned by {repo.split('/')[0]}")


def put_file(archive: str, path: str, data: bytes, message: str, token: str, attempts: int = 4) -> str:
    """Create one file. Returns 'created' or 'exists'. Retries a conflict from a concurrent run."""
    body = json.dumps({"message": message, "content": base64.b64encode(data).decode()})
    error = ""
    for i in range(attempts):
        out = gh("api", "-X", "PUT", f"repos/{archive}/contents/{path}", "--input", "-",
                 input_text=body, token=token, check=False)
        try:
            resp = json.loads(out) if out.strip() else {}
        except json.JSONDecodeError:
            resp = {}
        if (resp.get("content") or {}).get("path") == path:
            return "created"
        error = str(resp.get("message") or out.strip())[:200]
        probe = gh("api", f"repos/{archive}/contents/{path}", "--jq", ".path", token=token, check=False)
        if probe.strip() == path:
            return "exists"  # a rerun of the same attempt, or a retry that landed
        if resp.get("status") in ("401", "403", "404"):
            break  # retrying won't help
        time.sleep(2 * (i + 1))
    raise FactoryError(f"couldn't write {path} to {archive}: {error}")


def summary_lines(archive: str, record: dict, paths: tuple[str, str], pushed: bool) -> list[str]:
    counts = record["redaction"].get("counts") or {}
    red = ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "nothing matched"
    where = f"`{archive}`" if pushed else "not pushed (local files only)"
    lines = ["### Session archive", "", f"- Archive: {where}",
             f"- Transcript: `{paths[0]}`" if record["transcript"] else "- Transcript: none",
             f"- Run record: `{paths[1]}`",
             f"- Redacted: {red}; {record['redaction'].get('truncated_strings', 0)} long strings cut"]
    if record["redaction"].get("note"):
        lines.append(f"- {record['redaction']['note']}")
    return lines


def cmd_redact(args, env: dict) -> int:
    """In the agent job, right after the agent: redact, and encrypt when the plan says so."""
    plan = json.loads(Path(args.plan).read_text())
    sess = plan.get("sessions") or {}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    blob, info = redact_session(Path(args.execution) if args.execution else None, env)
    if blob is not None and sess.get("encrypt"):
        key = env.get("FACTORY_ARCHIVE_KEY", "")
        if key:
            (out / "transcript.jsonl.gz.enc").write_bytes(crypt(blob, key))
        else:
            info["redaction"]["note"] = ("transcript not kept: this repository is public and FACTORY_ARCHIVE_KEY "
                                         "isn't set, so the transcript can't leave the agent job privately")
    elif blob is not None:
        (out / "transcript.jsonl.gz").write_bytes(blob)
    (out / "session.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"session: {info['stats'].get('messages', 0)} messages; redacted {info['redaction']['counts'] or 'nothing'}")
    return 0


def cmd_push(args, env: dict) -> int:
    """In the archive job: build the run record and push both files (or, with --dry-run, write them)."""
    plan = json.loads(Path(args.plan).read_text())
    archive = (plan.get("sessions") or {}).get("archive", "")
    if not archive:
        print(f"session archive: none ({(plan.get('sessions') or {}).get('reason', 'not configured')})")
        return 0
    sdir = Path(args.session) if args.session else None
    info = {"stats": {}, "redaction": {"note": "no session from the agent job"}}
    blob = None
    if sdir and (sdir / "session.json").exists():
        info = json.loads((sdir / "session.json").read_text())
        if (sdir / "transcript.jsonl.gz.enc").exists():
            blob = crypt((sdir / "transcript.jsonl.gz.enc").read_bytes(), env.get("FACTORY_ARCHIVE_KEY", ""), decrypt=True)
        elif (sdir / "transcript.jsonl.gz").exists():
            blob = (sdir / "transcript.jsonl.gz").read_bytes()
    paths = archive_paths(plan, env)
    red = Redactor(known_secrets(env))  # apply's tokens too, for the record's copy of the result
    record = run_record(plan, env, info.get("stats") or {}, red.value(agent_result(Path(args.result) if args.result else None)),
                        info.get("redaction") or {}, paths[0] if blob is not None else None)
    files = [(paths[1], (json.dumps(record, indent=2) + "\n").encode())]
    if blob is not None:
        files.insert(0, (paths[0], blob))

    pushed = False
    if args.dry_run:
        out = Path(args.out or ".factory-io/archive")
        for rel, data in files:
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(data)
    else:
        token = env.get("FACTORY_GITHUB_TOKEN", "")
        if not token:
            raise FactoryError("FACTORY_GITHUB_TOKEN is not set; it is needed to write to the session archive")
        repo = env.get("GITHUB_REPOSITORY", "")
        check_archive(archive, repo, token)
        msg = f"{record['stage']}: {repo} run {record['run_id']}"
        for rel, data in files:
            put_file(archive, rel, data, msg, token)
        pushed = True

    lines = summary_lines(archive, record, paths, pushed)
    print("\n".join(lines))
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("redact", help="redact (and maybe encrypt) the agent's execution file")
    r.add_argument("--plan", required=True)
    r.add_argument("--execution", help="claude-code-action's execution file, if the agent wrote one")
    r.add_argument("--out", required=True)
    p = sub.add_parser("push", help="build the run record and push it with the transcript")
    p.add_argument("--plan", required=True)
    p.add_argument("--session", help="what `redact` wrote")
    p.add_argument("--result", help="the agent's result directory")
    p.add_argument("--dry-run", action="store_true", help="write the files under --out instead of pushing")
    p.add_argument("--out")
    args = ap.parse_args()
    env = dict(os.environ)
    return cmd_redact(args, env) if args.cmd == "redact" else cmd_push(args, env)


if __name__ == "__main__":
    main_guard(main)
