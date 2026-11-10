# Auto-merge decisions: tech spec

Product spec: [PRODUCT.md](PRODUCT.md).

## Context

`docs/auto-merge.md` (#24, merged 2026-11-10 as `3c14be1`) proposes risk-gated auto-merge and ends with six decisions for the owner. The owner agreed to the recommendations made in the session that reviewed it. Reading the design against the test repository turned up two gaps:

- **The diff check excludes Protected paths only.** `FACTORY.md` also has Human-only areas, such as outreach drafts, verification records and expert review notes. In the test repository these are Markdown, which the `docs` class allows.
- **The gate trusts "required CI passed".** The test repository's `FACTORY.md` requires a replay of every stored report for dependency changes. That replay runs in its own workflow, which isn't necessarily a required check.

## Proposed changes

Documentation only; nothing is built.

1. **`docs/auto-merge.md`:**
   - **Status line:** design agreed; decisions dated.
   - **"What decides a merge":**
     - the diff row excludes Human-only as well as Protected paths (PRODUCT.md invariant 3);
     - a new row requires every check in `auto_merge.required_checks` to be required by the ruleset and passed on the head (invariant 4).
   - **Classes:**
     - `dependency-patch` needs a non-empty `required_checks`;
     - `docs` excludes Human-only areas;
     - the config example shows `required_checks`.
   - **Shadow mode:** the leave-preview bar counts per class. A false positive restarts the count; a false negative doesn't (invariant 7).
   - **Rollout:** new step 0. Before any build runs in the test repository: GitHub Pro, a ruleset that requires `factory/merge-gate`, and the replay check listed in `required_checks` (invariants 4–6).
   - **Prerequisites:** Pro is the decided path.
   - **What it changes:** `plan.py` validates `required_checks`; `decide_merge` reads Human-only and the ruleset's required checks; `doctor` checks them.
   - **"Decisions for the owner" becomes "Decisions (owner, 2026-11-10)"**, with each answer.
2. **`docs/rollout.md`:** the link to auto-merge.md says "agreed 2026-11-10, not built".

## Testing and validation

| Invariant | Check |
|---|---|
| 1–8 | Each appears in `docs/auto-merge.md`: 1, 2, 5, 6 and 8 in the Decisions section and Rollout step 0; 3 in the diff row and the `docs` class; 4 in the `required_checks` row and the `dependency-patch` class; 7 in Shadow mode. The diff shows nothing else changed. |
| 9 | `scripts/check-references.sh` passes; the doc says "the test repository" and names none. |
| — | CI (`check`, conventional title) passes. No code, golden plan or stub changes. |

## Follow-ups

- The build itself, as its own spec'd work, starting from Rollout step 0.
