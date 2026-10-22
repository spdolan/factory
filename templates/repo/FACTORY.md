# Factory

How the factory's agents (triage, spec, implementation, review, verify-behavior) work in this repository. Agents read this file, so keep it short and literal. Delete any section that doesn't apply.

## Validation commands

Run these in this order. Implementation runs them before opening a PR.

```sh
# e.g. bun install && bun run typecheck && bun test
```

Commands that need local-only resources (a local database, private data) and so can't run in CI:

- `…`: needs …

## Protected paths

Agents may not change these without an approved spec and the `invariant-risk` label. Triage routes work that touches them to `ready-to-spec`, and those issues use the risk model (Opus by default).

- `…`

## Human-only

Areas where agents never advance work on their own, even small changes. Triage marks such issues `factory:awaiting-approval`. Examples: auth, data deletion, anything that publishes findings.

- `…`

## Consumers

Repositories that depend on this one, one per line in exactly this form. Breaking changes need `!` in the PR title and a note in the PR. When this repository releases, `factory-notify-consumers.yml` tells each consumer: non-breaking releases are bumped by an agent, and breaking ones open an issue for a human.

- `owner/repo`: uses …

## App

How verify-behavior starts the app. Omit this section for libraries and pipelines.

- Install: `…`
- Start: `…` (runs in the background)
- URL: `http://localhost:…`
- Seed or fixtures: `…`

## Review notes

Repository-specific review guidance that doesn't belong in AGENTS.md. Longer guidance goes in `.claude/skills/review-pr-local/SKILL.md`.
