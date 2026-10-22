---
name: validate-against-specs
description: Check a branch's changes against its PRODUCT.md and TECH.md without asking questions, and produce a short mismatch report. Use after implementing a spec'd issue, before opening the PR, or when asked whether an implementation matches its spec. Non-interactive, so it works in CI.
---

# Validate against specs

Compare the current branch's diff with the specs for the issue, and report material mismatches. This is the non-interactive counterpart of Warp's `validate-changes-match-specs`: it never stops to ask, and the caller decides what to fix.

## Inputs

- The spec directory, usually `specs/gh-<n>*/`, containing `PRODUCT.md` and `TECH.md`, and possibly `PRIOR_ART.md`
- The diff: `git diff $(git merge-base HEAD origin/<default-branch>)...HEAD`, or the working-tree diff before committing

## Workflow

1. Read PRODUCT.md and extract every numbered Behavior invariant. Read TECH.md and extract the commitments in Proposed changes (modules, APIs, data flow) and in Testing and validation (each test or check promised).
2. If PRIOR_ART.md has a **Claim**, add it as an invariant. The distinguishing case must be implemented and tested.
3. For each item, find the evidence in the diff or the nearby code:
   - **met**: the code implements it, and a test or validation step covers it
   - **untested**: implemented, but the promised test is missing
   - **missing**: not implemented
   - **contradicted**: implemented differently from the spec
   - **n/a**: deferred, with a stated reason in the spec or issue
4. Look for scope creep: changes in the diff that no spec item explains.

## Report

Return this block. The caller pastes it into the PR body.

```markdown
### Spec alignment
- Specs: `specs/<slug>/PRODUCT.md`, `TECH.md`
- Result: aligned | aligned with gaps | not aligned
- Invariants: N met · N untested · N missing · N contradicted · N n/a

| Item | Status | Evidence or gap |
|---|---|---|
| P3: empty state shows … | untested | no test covers the empty list |

Unexplained changes: none | list
Spec issues (the spec looks wrong, not the code): none | list
```

Include only rows that are not `met`, plus one line saying how many were met.

## Rules

- Report material mismatches only. No style commentary.
- If an item is `missing` or `contradicted` because of the implementation, say so plainly. The caller fixes it.
- If the spec is what's wrong (stale or impossible), list it under Spec issues and don't count it against the code.
- Don't edit files. This skill only reports.
