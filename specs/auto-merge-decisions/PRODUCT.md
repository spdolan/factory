# Auto-merge: the owner's decisions

## Summary

Record the owner's six decisions on the risk-gated auto-merge design (`docs/auto-merge.md`, #24), and fold two gaps found while deciding into that design, before anything is built. The consumers are whoever builds the feature (the design is their contract), repositories that will opt in, and the owner, who reads the doc as the agreed design.

## Behavior

These are the properties the agreed design, and so the eventual build, must have.

1. Auto-merge is opt-in per repository and per class, and starts in shadow mode: the gate decides and records, and a human still merges.
2. The first classes in the test repository are `dependency-patch` and `docs`.
3. The gate never lets a PR merge without a human when the PR changes a file under `FACTORY.md`'s Protected paths **or** its Human-only areas. A `docs` PR touching outreach, verification or review records always waits for a human.
4. `dependency-patch` is refused while the repository's `auto_merge.required_checks` is empty. The gate merges only when every check named there is required by the default branch's ruleset and passed on the PR's head. In the test repository, that means the replay of stored reports its `FACTORY.md` requires for dependency changes.
5. `factory/merge-gate` is a required check on every PR, a human's included. A push after the review leaves the new head without the status, so it can't merge until the gate runs on it.
6. On a private repository without GitHub Pro, the feature refuses to run. The owner upgrades the test repository's account to Pro before the first build runs there.
7. A class leaves preview after 20 shadow decisions in a row that match the owner's, then 10 real auto-merges with no revert. A false positive (the gate would merge where the owner wouldn't) restarts that class's count. A false negative doesn't.
8. When the default branch breaks after an auto-merge, the factory opens a revert PR and pauses all auto-merges. It never merges the revert itself.
9. The design names no consumer repository; `scripts/check-references.sh` passes.
