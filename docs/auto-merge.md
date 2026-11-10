# Risk-gated auto-merge

Status: design agreed. The owner's decisions (2026-11-10) are recorded at the end and folded into the design below. Nothing is built yet. It reverses "every stage ends in a review a human merges" ([README](../README.md)) for repositories that opt in. It ships behind a preview flag ([rollout.md §6.1](rollout.md#61-flags)) and is tried in the test repository first, in shadow mode, once the prerequisites in Rollout step 0 are in place. It works in two enforcement modes (below): `host`, where the version-control host enforces required checks, and `factory`, where the factory enforces them for its own merges. `factory` is for hosts or plans without required checks, such as a private repository on GitHub Free.

## The problem

Every factory PR waits for a human to merge it, including a patch-level dependency bump with green CI and a typo fix in the docs. Small, low-risk work goes through triage, implement and review without you, but then waits on a click. As more repositories adopt the factory, that click becomes the bottleneck, and approving PRs nobody read teaches people to approve without reading.

## What the phase 1 runs showed

The factory's agents can't be the ones who decide a merge. Three things from the phase 1 runs in the test repository:

- **Triage stated something false.** Its comment on one issue said a related issue wasn't open, but it was. The state and size it chose were reasonable; the reasoning it showed wasn't checked against anything.
- **A review missed what the PR said.** Implement's PR body reported a failing test. The review ran on the fast tier (the `small_change` rule) and didn't mention it.
- **Agents misreport their own work.** Implement and spec runs said "nothing pushed" above PRs the apply job had already opened (fixed in the prompts, but it shows how much a self-report is worth).

So the design rule: **an agent can veto a merge but never allow one.** The merge happens only when facts the factory measures itself, and the repository's required CI, all say yes.

## Design

### What decides a merge

A PR merges without a human only when every check below passes. The apply job evaluates all of them in one pure function, `decide_merge`, from data it fetches itself, and writes the result and each reason to the run summary.

| Check | Source | Why |
|---|---|---|
| The repository turned the feature on and lists the PR's class (below) | `config.yml`, `features.yaml` | Opt-in, per class |
| `FACTORY_AUTO_MERGE` isn't `off`, and no issue labeled `factory:auto-merge-paused` is open | repository variable, tracker | Kill switches: one for you, one the factory sets itself |
| Fewer than `daily_cap` PRs labeled `factory:auto-merged` merged in the last 24 hours | GitHub search | Limits the blast radius of a bad release |
| The PR was opened by the factory's apply job, from a branch it pushed, and every commit on it came from that push | the PR, the run that opened it | No human or outside commits slip in |
| Its issue was opened by an owner or collaborator, and has no comments from anyone else | tracker | Prompt injection through the issue reaches implement |
| Triage sized the issue `small`, gave it `factory:agent`, and added no marker (`invariant-risk` or any `never_if` label) | labels | The existing autonomy rules, reused |
| The diff, measured by apply: at most `max_lines` changed lines, no file under Protected paths **or Human-only** in `FACTORY.md`, nothing under `.github/`, no lockfile or manifest unless the class allows it, no deleted files, no binary files | `git diff --numstat` on the bundle | Size and blast radius are measured, not estimated. Human-only areas (outreach, verification, reviews) are often Markdown, so `docs` would otherwise reach them |
| The review stage's `review.json` for the current head has verdict `APPROVE` and no `critical` or `important` findings | the review artifact, not the GitHub review | Published approvals fall back to `COMMENT` on most repositories, so the artifact is the source |
| A second, independent review (below) also approves | the merge-review artifact | One reviewer missed a failing test in phase 1 |
| `host` mode: the default branch has a ruleset or branch protection that requires checks, including `factory/merge-gate`. `factory` mode: every check run on the head commit has completed, and every one succeeded | `GET /repos/{repo}/rules/branches/{branch}`, or the head's check runs | Without required checks, GitHub's auto-merge merges at once. In `factory` mode, nothing merges while a check is pending or failed |
| Every check named in `auto_merge.required_checks` is present and passed on the head, and in `host` mode also required by the ruleset | the head's check runs, the ruleset | A repository's own gates, such as a replay of stored outputs that its `FACTORY.md` requires for dependency changes, must hold before anything merges. A named check that hasn't reported counts as not passed |

An agent's own risk call can only lower eligibility: implement and both reviews may report `merge: "no"` with a reason, which fails the gate. Nothing an agent writes can pass it.

When every check passes, apply acts according to the repository's enforcement mode (next section). If any check fails, apply writes why in the summary and leaves the PR for a human, as today.

### Two enforcement modes

The gate decides; something then has to stop a merge that the gate didn't allow. A repository chooses who does that with `auto_merge.enforcement`. There is no default and no fallback: a repository that turns the feature on names its mode, and `doctor` and the gate refuse a mode the repository can't support.

**`host`: the version-control host enforces it.** The repository's ruleset or branch protection requires checks, including `factory/merge-gate`. On GitHub that needs a public repository, or GitHub Pro or Team for a private one. When every check passes, apply:

1. sets the commit status `factory/merge-gate` to `success` on the reviewed head commit,
2. adds `factory:auto-merged` to the PR,
3. enables GitHub's auto-merge (squash) with `FACTORY_GITHUB_TOKEN`, so the push to the default branch triggers its workflows (a merge by `GITHUB_TOKEN` would trigger none, including post-merge CI and release-please).

GitHub then merges once the required checks pass.

**`factory`: the factory enforces it, for its own merges.** For hosts or plans without required checks, such as a private repository on GitHub Free. Nothing is required on the host, so the factory does what the host would have done, at the moment it merges:

1. **When:** `merge-review`'s apply records the reviewed head commit and adds `factory:auto-merge-candidate`. A new stage, `merge-gate`, runs when the repository's CI finishes on a PR with that label (`workflow_run`, as `auto-merge-watch` does), and once more after a timeout if it never fires (open question 5).
2. **Checks:** `merge-gate` lists every check run on the head commit. It merges only if:
   - the head is still the reviewed commit;
   - every check run has completed and succeeded;
   - every check in `required_checks` is among them;
   - `decide_merge` still passes.
   
   A pending, missing or failed check means "not yet" or "no", never "yes".
3. **The merge:** it merges through the API with the head commit's SHA (GitHub: `PUT /repos/{repo}/pulls/{n}/merge` with `sha`, squash). The host refuses the merge if the PR's head has moved, so a push after the review can't be merged. `merge-gate` then waits for the next review instead. It merges with `FACTORY_GITHUB_TOKEN`, for the same reason as above, and adds `factory:auto-merged`.

**What each mode guarantees.** In `host` mode, the rule binds every merge on the repository, a person's included, and holds even if the factory has a bug. In `factory` mode, the rule binds only the merges the factory makes. People can merge what they like, as they can today, and a bug in the gate has no host-side backstop. That's why `factory` mode fails closed on anything missing or pending, why `decide_merge` is table-tested, and why every class starts in shadow mode. The README describes the same distinction for the factory as a whole.

### Closing the race between a push and the merge

In `factory` mode, the merge call carries the reviewed head commit's SHA, so the host refuses it if the head has moved (above). The rest of this section is about `host` mode.

A push after the review would leave auto-merge enabled on a head nobody reviewed. `factory/merge-gate` is set per commit, so a new head has no status and can't merge until the gate runs again on it. That only works if the ruleset requires `factory/merge-gate`, which means every PR, including a human's, needs it. To keep human PRs mergeable, apply sets `factory/merge-gate` to `success` on every reviewed head, with the description "reviewed, not eligible for auto-merge" when the gate failed, and only the eligible ones get auto-merge enabled. The cost: every PR waits for the review stage before it can merge, unless the owner bypasses the ruleset. Release-please PRs, which review skips, need the status too, so review sets it when it skips one. The review stub gains `statuses: write`. (Decision 3.)

A new push also reruns review, which would set `success` on the new head while auto-merge is still enabled from the old one. So review's apply, before anything else, disables auto-merge and removes `factory:auto-merged` on any PR that has them. Only `merge-review` enables auto-merge, and only on the head it reviewed. In `factory` mode, the same step removes `factory:auto-merge-candidate`, so `merge-gate` waits for the new head's review.

### Classes

A repository opts into classes, from least to most risky. Each class narrows which files and stages may produce the PR.

| Class | Produced by | Files allowed | Also needs |
|---|---|---|---|
| `dependency-patch` | dependency-bump | the manifest and lockfile only | a semver patch release, not breaking, and `required_checks` naming the repository's own checks for dependency changes (the gate refuses the class while the list is empty) |
| `docs` | implement | Markdown outside Protected paths and Human-only areas | |
| `small-fix` | implement | anything the general checks allow | a `fix:` title |
| `small-feature` | implement | anything the general checks allow | a `feat:` title, `max_lines` halved |

Spec PRs are never auto-merged: a specs PR is the point where a human agrees to what gets built.

```yaml
# .github/factory/config.yml
features: { on: [auto-merge] }
auto_merge:
  classes: [dependency-patch, docs]
  max_lines: 100
  daily_cap: 3
  mode: shadow          # shadow | on
  enforcement: factory   # host | factory; no default (Two enforcement modes)
  required_checks: [replay]   # checks the head must pass, and in host mode the ruleset must require (names are the repository's own)
```

### The second review

For a PR that passes every other check, review's apply dispatches a new stage, `merge-review`. It runs on the deep tier, from the trusted base like review, and sees only the diff, the issue, `FACTORY.md` and the CI results. It doesn't see the first review. Its prompt asks it to find the reason not to merge: behavior the issue didn't ask for, tests that don't test the change, a failing or skipped check, anything a Protected path depends on. It outputs `{merge: yes|no, reasons}`; `merge-review`'s apply runs `decide_merge` and the steps above.

The `small_change` rule that sends small PRs to the fast tier doesn't apply to merge candidates: both reviews run at least on the balanced tier.

### Shadow mode

`mode: shadow` runs everything except the merge: the gate decides, posts its decision in the summary (and in `host` mode sets `factory/merge-gate`), and a human merges as today. That gives a record of what the factory would have merged before it merges anything. The flag stays in preview until shadow mode has agreed with the owner's own decisions on enough PRs (decision 5), counted per class:

- **The gate would merge a PR the owner wouldn't** (a false positive): the count for that class restarts at zero.
- **The gate declines a PR the owner merges** (a false negative): a missed chance, not a risk. It doesn't reset the count, but the gate is reviewed if it happens often.

### When the default branch breaks

A new stage, `auto-merge-watch`, runs when the repository's CI finishes on the default branch. If that run failed and the commit came from a PR labeled `factory:auto-merged`, apply:

1. opens a revert PR (a human merges it; reverts aren't auto-merged),
2. opens an issue labeled `factory:auto-merge-paused` that links the failing run, which stops every further auto-merge until a human closes it,
3. comments on the original issue and PR.

The stub needs the name of the repository's CI workflow for its `workflow_run` trigger. It comes from `config.yml` (`auto_merge.ci_workflow`), which `factory install` reads when it renders the stub.

## What it changes

- `features.yaml`: the `auto-merge` flag, preview, with a cost note (one deep-tier run per candidate PR).
- `pipeline.yaml`: the stages `merge-review`, `merge-gate` (`factory` mode) and `auto-merge-watch`; labels `factory:auto-merged`, `factory:auto-merge-candidate` and `factory:auto-merge-paused`; the variable `FACTORY_AUTO_MERGE`.
- `runner/plan.py`: the `auto_merge` config schema and validation, including `enforcement` (required, `host` or `factory`) and `required_checks` (refusing `dependency-patch` while it's empty).
- `runner/apply.py`: `decide_merge` (pure, table-tested like `decide_route`) and the ops `gate-merge`, `merge-with-sha` (`factory` mode), `dispatch-merge-review` and `revert-merge`. It reads both Protected paths and Human-only from `FACTORY.md`, the head's check runs, and in `host` mode the ruleset's required checks.
- `stages/merge-review/prompt.md` and its schema; the review and patch schemas gain an optional `merge: no` veto.
- `scripts/factory doctor`: checks that the enforcement mode is supported. For `host`: the ruleset requires `factory/merge-gate` and every check in `required_checks`, and the repository allows auto-merge. For `factory`: the `merge-gate` stub is installed. In both modes, `FACTORY_GITHUB_TOKEN` must have Contents and Pull requests: write.
- Docs: README, pipeline.md, architecture.md, setup.md.

New stubs (`merge-review` and `auto-merge-watch`, plus `merge-gate` in `factory` mode) mean a stub change in each repository that wants the feature, which arrives through `factory update`. A repository without them never auto-merges, so the feature can ship in a 0.2.x patch behind the flag.

## Rollout

0. **Prerequisites, before any build runs in the test repository.** The test repository is private on GitHub Free, so it uses `enforcement: factory` (decision 4, amended). No Pro and no ruleset are needed. Its `required_checks` lists the repository's own dependency check (its stored-output replay) before `dependency-patch` is turned on. `host` mode is tried later, in a repository that has required checks.
1. Build it with `mode: shadow` only. Test repository: `classes: [dependency-patch, docs]`.
2. Compare shadow decisions with the owner's merges. Fix the gate until they agree.
3. Turn on `mode: on` in the test repository for `dependency-patch` and `docs`. Break the default branch on purpose once to see the revert path work.
4. Add `small-fix` in the test repository.
5. Move the flag to default. It stays inert in every repository that lists no classes.

## Prerequisites and limits

- **`host` mode needs required checks**, from a ruleset or branch protection, which on a private repository needs GitHub Pro (rollout.md open question 6). On a private repository without Pro, `host` mode refuses. **`factory` mode needs neither** (Two enforcement modes).
- **PRs opened with `GITHUB_TOKEN` never qualify.** When `FACTORY_GITHUB_TOKEN` can't open a PR, apply falls back to `GITHUB_TOKEN`, and no CI runs on that PR. Its required checks never pass, so it can't auto-merge. This fails closed, as it should.
- **Settings → General → "Allow auto-merge"** must be on in `host` mode. Only the owner sets it. `factory` mode merges through the API and doesn't use it.

## Open questions

Each to be tested in the test repository before it's relied on:

1. Does a commit status set by `GITHUB_TOKEN` satisfy a ruleset's required check?
2. Does auto-merge enabled with a fine-grained PAT merge as that PAT's owner, so the push triggers workflows?
3. Does `workflow_run` fire for a CI run that a PAT-triggered merge started, and can its `workflows:` list come from config without making the stub repository-specific in a way `check-stubs` rejects?
4. Does GitHub keep auto-merge enabled after a new push to the PR? (The `factory/merge-gate` status makes the answer not matter for safety, but it decides whether the gate has to re-enable it.)
5. `factory` mode: does `workflow_run` fire for a PR's CI promptly enough to drive `merge-gate`, and what timeout should the fallback run use?
6. `factory` mode: does the merge endpoint refuse a stale `sha` with 409 in every case, including when the PR was updated by merging the base branch into it?

## Decisions (owner, 2026-11-10)

1. **Accept the reversal: yes.** Opted-in repositories, in the classes they list, merge without a human. Start in shadow mode.
2. **First classes in the test repository: `dependency-patch` and `docs`.** Two gaps found while deciding are now in the design:
   - **Human-only areas.** The gate also excludes FACTORY.md's Human-only areas, not only Protected paths, so `docs` can't reach outreach, verification or review records.
   - **Required checks.** `dependency-patch` needs `required_checks` to name the repository's own gate for dependency changes (in the test repository, the replay of stored reports), and that check must be required by the ruleset.
3. **`factory/merge-gate` is a required check on every PR: yes, in `host` mode.** It closes the push-after-review race without relying on open question 4. Every PR waits for the review stage, about 2–3 minutes in recent runs, unless the owner bypasses the ruleset. In `factory` mode, nothing is required on the host, and the SHA-guarded merge closes the race.
4. **Private repositories: `factory` mode on GitHub Free; Pro optional.** Amended the same day. First decided as "upgrade to GitHub Pro", because the test repository is private and can't require checks without it. Then changed to add `factory` mode, which needs no plan upgrade, at the cost of the host-side backstop described in "What each mode guarantees". Upgrading later, and switching a repository to `host`, stays open.
5. **The bar to leave preview, per class: 20 shadow decisions in a row that match the owner's, then 10 real auto-merges with no revert.** A false positive (the gate would merge, the owner wouldn't) resets the count; a false negative doesn't (Shadow mode, above).
6. **Pause, don't revert automatically.** On a broken default branch, the factory opens the revert PR and pauses all auto-merges, and a human merges the revert.
