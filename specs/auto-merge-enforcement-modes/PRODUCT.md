# Auto-merge enforcement modes, and host- vs factory-enforced guarantees

## Summary

Auto-merge's design (`docs/auto-merge.md`) gains a second way to enforce its gate, so a repository without required checks can use it. That includes the test repository: private, on GitHub Free. The docs also state, for the factory as a whole, the difference between rules the version-control host enforces and rules the factory enforces. Nothing is built.

The consumers are whoever builds auto-merge (the design is their contract), repositories choosing a mode, and anyone reading the README to learn what the factory does and doesn't guarantee.

## Behavior

### Choosing a mode

1. A repository that turns auto-merge on names `auto_merge.enforcement` as `host` or `factory`. There is no default and no silent fallback: an unset value, or a mode the repository can't support, makes `doctor` report it and the gate refuse to merge.
2. **`host` mode** is the earlier design, unchanged:
   - the host's ruleset or branch protection requires checks, including `factory/merge-gate`;
   - the factory sets that status and enables the host's auto-merge.

   On GitHub it needs a public repository, or Pro or Team for a private one.
3. **`factory` mode** needs no host-side required checks. It works on a private GitHub Free repository.

### What `factory` mode does

4. The factory merges a candidate PR itself, only after re-checking at merge time that:
   - the head is the commit both reviews approved;
   - every check run on that commit has completed and succeeded;
   - every check named in `required_checks` is among them;
   - the rest of the gate still passes.
5. A pending, missing or failed check never counts as passed; the PR waits or stays with a human.
6. The merge names the reviewed head commit, and the host refuses it if the PR's head has moved. A push after the review can't be merged; the new head waits for its own review.
7. The merge is made with the token that triggers the default branch's workflows, as in `host` mode.
8. In `factory` mode, nothing is required on the host, so people's PRs don't wait on `factory/merge-gate`.

### What each kind of rule guarantees (README and docs)

9. The README has a section that separates the two kinds of guarantee, with GitHub as the worked example and other hosts mentioned:
   - **Host-enforced** rules bind every change, by anyone, and hold even if the factory has a bug.
   - **Factory-enforced** rules bind only what the factory does, have no host-side backstop, and therefore fail closed, are tested, and start behind a preview flag or in shadow mode.
10. The README names examples of each kind:
    - **host-enforced:** the release-tag ruleset, and the default-branch ruleset from `doctor`;
    - **factory-enforced:** triage's autonomy rules, the Protected-paths and Human-only gates, the read-only agent job, and auto-merge's `factory` mode.
11. `docs/auto-merge.md` states what each mode guarantees in those terms. `docs/rollout.md` §9 marks rulesets as host-enforced and points to the README section.

### The decisions record

12. Decision 4 is amended, with the original answer kept: the test repository uses `factory` mode on GitHub Free; Pro is optional. Decision 3 (the required `factory/merge-gate`) applies to `host` mode.
13. Rollout step 0 no longer requires Pro for the test repository. It requires `enforcement: factory` and the replay check in `required_checks`.
14. The docs name no consumer repository; `scripts/check-references.sh` passes.
