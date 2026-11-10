# Auto-merge enforcement modes: tech spec

Product spec: [PRODUCT.md](PRODUCT.md).

## Context

- **What the agreed design assumed** (`docs/auto-merge.md`, #24 and #29): the host enforces required checks. It relies on GitHub's auto-merge, which waits for required checks, and on a required `factory/merge-gate` status to close the push-after-review race.
- **What the account allows:** rollout.md open question 6 records that it's on GitHub Free, where rulesets and branch protection on a private repository return 403. The test repository is private, so the design needed GitHub Pro (decision 4).
- **What the host offers without a paid plan:** GitHub's REST endpoint for merging a pull request (`PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge`) takes `sha`, "SHA that pull request head must match to allow merge", and refuses a mismatch. Check runs for a commit are listed by `GET /repos/{owner}/{repo}/commits/{ref}/check-runs`. Both work on GitHub Free.

## Proposed changes

Documentation only.

1. **`docs/auto-merge.md`:**
   - **Status line:** names the two modes.
   - **"What decides a merge":** the two mode-dependent rows (required checks, `required_checks`) say what each mode verifies.
   - **New "Two enforcement modes" section:**
     - `auto_merge.enforcement`, with no default;
     - `host` (the previous steps, unchanged);
     - `factory`: the `factory:auto-merge-candidate` label, a `merge-gate` stage on `workflow_run` with a timeout fallback, re-checking every check run on the reviewed head, and a merge through the API with `sha`;
     - "What each mode guarantees".
   - **"Closing the race":** `factory` mode is covered by the `sha` merge. The rest of the section is scoped to `host` mode, and review's apply also removes the candidate label on a new push.
   - **Config example:** `enforcement`.
   - **What it changes:** the `merge-gate` stage and candidate label, `enforcement` validation, the `merge-with-sha` op, and `doctor`'s per-mode checks.
   - **Rollout step 0:** the test repository on `factory` mode, no Pro.
   - **Prerequisites:** Pro only for `host` mode; "Allow auto-merge" only for `host`.
   - **Open questions 5–6:** `workflow_run` timing and the fallback timeout, and the `sha` refusal when the base branch is merged into the PR.
   - **Decisions 3–4:** scoped and amended, with the original answer kept.
2. **`README.md`:** a "Who enforces a rule: your version-control host, or the factory" section after "Who advances an issue" (invariants 9–10).
3. **`docs/rollout.md` §9:** a sub-bullet marking rulesets as host-enforced, pointing to the README and auto-merge.md (invariant 11).

## Testing and validation

| Invariant | Check |
|---|---|
| 1–3 | auto-merge.md, "Two enforcement modes": `enforcement` has no default; `host` steps unchanged from #29; `factory` needs no ruleset. |
| 4–8 | Same section's `factory` steps (when, checks, merge), and "Closing the race". |
| 9–10 | README section present, with both kinds, GitHub as the example, and the named examples. |
| 11 | auto-merge.md "What each mode guarantees"; rollout.md §9 sub-bullet; the `#two-enforcement-modes` anchor matches the heading. |
| 12–13 | Decisions 3–4 and Rollout step 0 as described. |
| 14 | `scripts/check-references.sh` passes. |
| — | Factory CI (`check`, conventional title) passes. No code, golden plan or stub changes. |

## Risks and mitigations

- **`factory` mode is weaker than `host` mode,** with no backstop for a bug in the gate. The design says so where the mode is chosen and in the README, the mode is never chosen by default, and the gate fails closed (invariants 1, 5) and is table-tested.
- **The fallback timeout** could merge later than CI finishes. That costs only speed, never safety: the merge still re-checks every check and the head SHA.

## Follow-ups

- Open questions 5–6, answered in the test repository during shadow mode.
- Building auto-merge, `factory` mode first, as its own spec'd work.
