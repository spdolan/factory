# Dependency updates: tech spec

Product spec: [PRODUCT.md](PRODUCT.md). Issue: #42, with the owner's addendum making the contract tool-neutral.

## Context

- **`dependency-bump`** (`pipeline.yaml`) runs on `repository_dispatch: factory-dependency-release`, which another repository's `notify-consumers` sends, or on dispatch. A non-breaking release runs the `dependency-bump` skill on the `fast` tier: an agent edits the pins, the lockfile and the version comments, and the apply job's `open-pr` turns its patch into a PR. A breaking release runs no agent. `when.breaking` swaps in `open-breaking-issue` (`runner/apply.py`).
- **Bots allowed through review are hard-coded**: `allowed_bots` in `.github/workflows/stage.yml` and `templates/github/workflows/factory-review.yml`.
- **Nothing recognizes a dependency PR.** Only `open-breaking-issue` writes a `chore(deps)!:` title.
- **`updates:` in `config.yml` means factory updates** (`updates.check`, `updates.advance`; `validate_config` in `runner/plan.py`, `docs/rollout.md` §6.2). The updater choice therefore takes a new top-level key, `dependencies`.
- **The issue asked for four open questions to be checked before a spec was written.** They were checked against primary sources on 2026-11-10. Each answer is in the section it affects:

| Question | Answer, in short | Section |
|---|---|---|
| (a) Can an app installation token or `FACTORY_READ_TOKEN` read a private npm package another repository owns? | Neither, as far as the docs go. The run's `GITHUB_TOKEN` can, once the package grants the repository Read under Manage Actions access. | [Tokens](#5-tokens) |
| (b) Does Renovate move uv git pins to a release tag's commit? | No. A `rev` pin is digest-updated to the default branch's HEAD. Use a regex manager plus a `uv lock` post-upgrade task (unverified end to end), or keep `agent`. | [uv git pins](#6-uv-git-pins) |
| (c) Actions minutes per run, and caching? | A few minutes per run at $0.006 a minute on private repositories, rounded up per job. A repository cache isn't worth it yet. | [Cost](#cost) |
| (d) Migration, and `feat` or `feat!`? | `feat:` behind a flag. The stub arrives with `factory install`/`update`. A repository drops `ignoreDeps` in the same PR that switches it to `renovate`. | [Rollout and migration](#rollout-and-migration) |

Quoted sources are listed in [Sources](#sources).

## Proposed changes

### 1. `config.yml`: the `dependencies` key

```yaml
dependencies:
  updater: agent        # renovate | dependabot | agent (default agent)
  bots: []              # extra bot logins for allowed_bots (its own PR)
```

- `validate_config` adds `dependencies` to the known top-level keys.
  - `dependencies.updater` must be one of the three values.
  - `dependencies.bots` must be a list of logins matching `^[A-Za-z0-9-]+(\[bot\])?$`.
  - Any other key under `dependencies` is a problem.
- `templates/repo/config.yml` documents the key, commented out like the others.
- **Resolution.** The plan resolves the updater, and the job summary shows where it came from:
  - flag off: `agent`, with a warning if the file says otherwise;
  - flag on: the file's value, else `agent`.

`dependencies.bots` is the parent change's: it feeds `allowed_bots` in `stage.yml` and `factory-review.yml`, with the defaults `renovate[bot]`, `dependabot[bot]` and the factory's own app. That change lands in a separate PR. This spec only keeps the key name consistent with it.

### 2. The flag

```yaml
dependency-updater:
  summary: dependencies.updater chooses who bumps a dependency (renovate | dependabot | agent); the weekly Renovate run, scoped Renovate runs for internal releases, and review instructions for dependency PRs.
  stages: [dependency-bump, dependency-updates, review]
  state: preview
  added: <release>
  cost: with updater renovate, a few Actions minutes per Renovate run (weekly, and once per internal release) and no model calls for non-breaking bumps; otherwise one plan job a week
```

### 3. The factory's Renovate workflow

The new reusable workflow is `.github/workflows/renovate.yml` (`on: workflow_call`). Its inputs are the same as `stage.yml`'s: `stage`, `params` (JSON) and `dry_run`. The secrets are `stage.yml`'s plus two new optional ones, `FACTORY_APP_CLIENT_ID` and `FACTORY_APP_PRIVATE_KEY`. It has two jobs.

1. **`plan`** (read-only). It finds the factory commit from the OIDC token and checks the factory out at it, as `stage.yml` does. It then runs a new subcommand, `plan.py updater-plan`, which reads `config.yml` from the default branch and `features.yaml`, and outputs:
   - `run`: true only when the flag is on and the updater is `renovate`;
   - `package` and `source_repo`: validated with the same patterns as `stage_params` uses for `dependency-bump`, and empty for a full run;
   - the generated Renovate global config (below).
2. **`renovate`** (`if: run`). Its permissions are `contents: read` and `packages: read`.
   - It mints an installation token with `actions/create-github-app-token`, pinned by SHA as `release.yml` does, when `FACTORY_APP_CLIENT_ID` is set. Otherwise it uses `FACTORY_GITHUB_TOKEN`. With neither, it fails and says which secrets to set. It never falls back to `GITHUB_TOKEN`: PRs opened with `GITHUB_TOKEN` don't trigger CI ("With the exception of `workflow_dispatch` and `repository_dispatch`, other `GITHUB_TOKEN`-triggered events do not create workflow runs at all").
   - It runs `renovatebot/github-action`, pinned by commit SHA with the version in a comment, and passes an exact `renovate-version` (the action's README: "We recommend you pin the version of Renovate to a full version or a full checksum"). At build time, pin the newest of each that is at least three days old, the policy's wait for third-party packages. On 2026-11-10 the newest were action v46.3.13 (2026-11-09) and Renovate 44.227.1 (2026-11-10). The two version numbers are independent.

**The global config the plan job writes for every run:**

| Setting | Value | Why |
|---|---|---|
| `platform` | `github` | |
| `repositories` | `[<this repository>]` | A run never touches another repository. |
| `onboarding` | `false` | |
| `requireConfig` | `required` | A repository without a Renovate config gets no PRs. |
| `gitAuthor` and `platformCommit` | the app's bot identity, and `enabled` | With an app token. |
| `allowedCommands` | `["^uv lock --upgrade-package [A-Za-z0-9_.-]+$"]` | §6. |
| `hostRules` | `npm.pkg.github.com` with `hostType: npm` and the run's `GITHUB_TOKEN` | §5. |
| `dryRun` | `lookup` | Only when `dry_run`. |

**A scoped run** (a `package` was given) adds `force` settings that win over the repository's config:
- `packageRules`:
  - disable every dependency;
  - re-enable the one whose package name or dependency name is `package`, or whose package name is `source_repo`;
  - for it, set `minimumReleaseAge: null` and `schedule: ["at any time"]`.
- `pruneStaleBranches: false`. Without it, Renovate would treat every other open Renovate branch as no longer wanted, because the run disabled those dependencies, and auto-close it.
- The run must also leave the repository's Dependency Dashboard as it found it. Which setting does that is unverified, and the build settles it with a dry run first (Testing).

**Concurrency:** `factory-dependency-updates-<package or all>`, without cancelling. The group is keyed by package because GitHub keeps only one pending run per concurrency group. Two internal releases close together would otherwise lose the first scoped run.

### 4. The stub, and `dependency-bump` as a deterministic job

**A new stage in `pipeline.yaml`** gives the weekly run a stub:

```yaml
dependency-updates:
  summary: Run the factory's pinned Renovate, weekly for every dependency or scoped to one package.
  item: none
  workflow: renovate.yml            # new field; default stage.yml
  feature: dependency-updater
  triggers:
    - { event: schedule, cron: "17 6 * * 1" }
    - event: dispatch
      inputs:
        package: { description: "Limit the run to this package (empty: every dependency)", required: false }
        source_repo: { description: "The package's source repository, if it is pinned by git", required: false }
  agent: none
  output: { kind: none }
  apply: []
  concurrency: { key: "inputs.package || 'all'", cancel: false }
  permissions: {}
```

- **Rendering.** `stub_body` renders `uses: <factory>/.github/workflows/<workflow>@<ref>` from the new `workflow` field.
- **Finding the ref.** `stub_ref` in `scripts/factory`, and the doctor check that every stub calls one ref, match any `.github/workflows/*.yml@` instead of only `stage.yml@`. `check-stubs` hashes the body as before.
- **Effect on repositories.** `factory install` and `factory update` render the stub with the rest, so every repository gets it. With the flag off, or an updater other than `renovate`, a scheduled run is one plan job that exits.

**`dependency-bump` gets two new `when` conditions**, `renovate` and `dependabot`. They are true when the resolved updater has that value, and they are added to `CONDITIONS` in `plan.py`. `when` overrides apply in order with later ones winning, so `breaking` goes last and wins whatever the updater:

```yaml
when:
  renovate:   { agent: none, apply: [dispatch-updater] }
  dependabot: { agent: none, apply: [] }
  breaking:   { agent: none, apply: [open-breaking-issue] }
```

- **`dispatch-updater`** is a new apply operation, added to the plan's list of known operations. It runs `gh workflow run factory-dependency-updates.yml -f package=… -f source_repo=…` on the default branch with the apply job's token. The stage already has `actions: write`, and a `workflow_dispatch` made with `GITHUB_TOKEN` does start a run.
- **`dependabot`, with an empty `apply`,** writes only the job summary line from PRODUCT.md invariant 2. The plan's validation must accept an empty `apply` here.
- **`agent`** has no condition: it is today's stage, unchanged.
- **Configuration overrides.** A repository's `stages.dependency-bump.when.renovate` override is validated like the existing conditions.

### 5. Tokens

**Writing (PRs, branches, workflow files).**
- **The app.** A GitHub App the owner controls, installed on the consuming repository and on any private repository it pins by git (§6).
  - Permissions: those Renovate's GitHub platform docs list for an app, plus **Workflows: write**, so that action pin updates can be pushed. The build copies the exact list from those docs.
  - Secrets: `FACTORY_APP_CLIENT_ID` and `FACTORY_APP_PRIVATE_KEY` join `SECRETS` in `plan.py` (so every stub passes them) and the secret list in `scripts/factory rotate-secrets`.
  - Its `<slug>[bot]` login is "the factory's own app" in the default `allowed_bots`.
- **The fallback.** `FACTORY_GITHUB_TOKEN`, which is fine-grained. It also needs **Workflows: read and write** on the repository, or Renovate can't push changes under `.github/workflows/`. PRs opened with it are authored by the owner.

**Reading private GitHub Packages (open question a).**
- **`FACTORY_READ_TOKEN` can't do it.**
  - It is a fine-grained PAT, and GitHub lists "Using fine-grained personal access token to access Packages" among the gaps fine-grained tokens still have. No changelog entry closing that gap was found (unverified after March 2025).
  - It is also scoped to the factory alone, and `docs/rollout.md` keeps it to the checkout step. Widening it would break that rule.
- **An app installation token isn't relied on.**
  - The packages permission docs say GitHub Packages "only supports authentication using a personal access token (classic)" for registries outside the granular-permission list, and nothing documents installation tokens for `npm.pkg.github.com`.
  - Renovate's GitHub platform docs say package-registry credentials from the platform token are experimental, and that "users reported it is not working correctly with app tokens".
  - Unverified either way.
- **A classic PAT with `read:packages` works** ("A personal access token (classic) with at least `read:packages` scope to install packages"). It isn't chosen: it is long-lived and reads every package the owner can.
- **Chosen: the run's `GITHUB_TOKEN`** (`packages: read`) in a `hostRules` entry for `npm.pkg.github.com`. This is how today's agent job already reads packages (`GITHUB_PACKAGES_TOKEN`).
  - The token's "permissions are limited to the repository that contains your workflow", and "only workflows running in repositories that are given read permission on that package can download the package".
  - So the package's settings must add the consuming repository under **Manage Actions access** with **Read**. This "is different than connecting your package to a repository".
  - A package linked to its source repository "inherits the access permissions (but not the visibility)" of that repository. Inheritance does not reach a different repository's workflow token, so the explicit grant is needed even when both repositories have the same owner.
  - Whether the package-settings UI is the same for a personal account as for an organization is unverified. The docs describe both without saying they differ.
- **The explicit host rule replaces the one Renovate would provision itself.** Renovate "will automatically provision hostRules for both `ghcr.io` (containers) and `*.pkg.github.com`" from the platform token, and that would be the app token.

### 6. uv git pins (open question b)

**Renovate's `pep621` manager does read `[tool.uv.sources]`** (`lib/modules/manager/pep621/processors/uv.ts`, using `applyGitSource` in `lib/modules/manager/util.ts`):

| Source | Datasource | Behavior |
|---|---|---|
| `git` + `tag` | `github-tags` (or `git-tags`) | Updated like a version, and `uv.lock` is regenerated (`uv lock --upgrade-package`). |
| `git` + `rev` | `git-refs` | Only `currentDigest` is set. The lookup returns the hash of `HEAD` when there is no `newValue` (`lib/modules/datasource/git-refs/base.ts`). The pin would follow the default branch, unreleased commits included, never a tag. |
| `git` + `branch` | | Skipped. |

So Renovate can't do natively what the skill does today: move `rev` to the commit of the newest release tag. Instead:

1. **The repository's Renovate config turns off the native update for these pins**: a `packageRules` entry with `matchDepTypes: ["uvSources"]`, `matchDatasources: ["git-refs"]` and `enabled: false`. Otherwise Renovate opens PRs to HEAD.
2. **A regex custom manager reads the pin and a trailing comment that names the full tag**:

   ```toml
   somelib = { git = "https://github.com/<owner>/somelib", rev = "<sha>" }  # py-v0.3.0
   ```

   - Captures: `depName`, `packageName` (from the URL), `currentDigest` (the `rev`) and `currentValue` (the tag).
   - Datasource: `github-tags`, which returns each tag's commit as `newDigest`.
   - Versioning: a regex that keeps the tag's prefix, such as `regex:^(?<compatibility>.+-)?v(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)$`.
   - `autoReplaceStringTemplate` writes both `{{{newDigest}}}` and `{{{newValue}}}`.
   - The code paths exist (`lib/workers/repository/update/branch/auto-replace.ts` replaces the digest and the value). The whole config is unverified until a dry run.
3. **`uv.lock` comes from a post-upgrade task.** Custom managers export no `updateArtifacts`, so Renovate leaves the lock stale. The repository's config adds `postUpgradeTasks` with `uv lock --upgrade-package {{{depName}}}`. The factory's global config allows exactly that command (§3).
   - Unverified: whether `uv` is available to post-upgrade tasks in the pinned Renovate image, and whether the task gets git credentials for a private source.
   - For the credentials, Renovate turns host rules into `GIT_CONFIG_*` `insteadOf` variables for its own `uv lock` (`lib/util/git/auth.ts`). The platform token covers `https://github.com/`, so the app must be installed on the source repository.
   - The build tests this in the test repository first. Until it passes, a repository with uv git pins keeps `updater: agent`, which handles them today.

The regex manager and the `packageRules` belong to the repository's Renovate config, under the policy outside the factory. The factory provides the allowed command and the credentials. Renovate also has a `mise` manager (`lib/modules/manager/mise`), so `mise.toml` is covered, which Dependabot doesn't do.

### 7. Recognizing a dependency PR

- `runner/common.py` gets `is_dependency_pr(title, labels)`. It is true when the title matches `^chore\(deps\)!?: ` or the labels include `dependencies`. The author is never an input.
- With the flag on, the review plan adds `Dependency PR: yes` to the prompt when the rule matches. `skills/review-pr/features/dependency-updater.md` tells the reviewer to check four things:
  - the diff changes only manifests, lockfiles, version comments and workflow pins, and anything else is `⚠️ [IMPORTANT]`;
  - the release notes are linked or summarized;
  - a breaking update has `!`;
  - nothing in it touches a Protected path without the usual spec.

### 8. Documentation

- **`docs/setup.md`, "Dependency updates":** the three values; the app and its permissions; the Manage Actions access grant for private packages; and the switch steps under Rollout.
- **`docs/rollout.md` §11:** the "Dependabot bumps of pinned versions: unverified" row stays as it is, since this spec doesn't test it.
- **`README.md`:** one line under settings pointing to `dependencies`.

## Cost

Open question c. These are GitHub's numbers for private repositories. Public repositories are free: "Standard GitHub-hosted runners in public repositories" are listed as free usage that does not reduce the included amount.

- Linux 2-core costs $0.006 a minute, and "GitHub rounds the minutes and partial minutes each job uses up to the nearest whole minute".
- Included usage is $12 a month on GitHub Free and $18 on Pro, "expressed as a monetary amount, not a fixed number of minutes". That is about 2,000 and 3,000 Linux minutes; the arithmetic is ours.
- **A run is estimated at one plan minute plus two to four Renovate minutes**: pulling the image, cloning, lookups, and any lockfile regeneration. This is an estimate, not a measurement; no primary source states a typical run time. With four weekly runs and about four internal releases a month, that is about 30 minutes, under $0.20 a month per private repository. Today's agent job can take up to 30 minutes per release, plus a model run.
- **A repository not on `renovate` pays one plan minute a week** for the stub that exits, about $0.03 a month.
- **Repository cache: not now.**
  - What it does: `repositoryCache: enabled` keeps "a JSON file cache per-repository to speed up extractions", inside `cacheDir` "beside the existing file-based package cache".
  - What persisting it would take: the action's README restores `/tmp/renovate/cache/renovate/repository` with `actions/cache` and needs `sudo chown -R 12021:0 /tmp/renovate/`, because restored files are owned by the runner.
  - Why not: for repositories this small it would add a restore step, a save step and an ownership fix to save seconds of extraction. Scoped and full runs would also share one cache.
  - Revisit if a measured run goes over five minutes. The first runs' job timings are the measurement.

## Rollout and migration

Open question d.

**Class: `feat:`, behind `dependency-updater`.**
- Nothing a repository provides or relies on is removed or renamed: the `dependency-bump` stage, its triggers, inputs and job IDs, the skill, and the labels all stay.
- Additive pieces:
  - a new optional `config.yml` key, as `sessions` was added under `feat(archive)` (#27);
  - two new optional secrets;
  - a new stage and stub, which `docs/rollout.md` §6 lists under `feat` ("a new stage").
- The addendum reaches the same conclusion: keeping the skill as the `agent` value makes this smaller than a `feat!:`.
- A reviewer who reads "the `config.yml` schema" in §6 as covering additions should raise it on the PR. Nothing here forces a repository to change anything.
- **A later `feat!:`** would make `renovate` the default or remove the skill. Neither is proposed.

**What each repository gets on `factory update`:** the new stub and the flag in its `factory:update` issue (§6.2), with no `MIGRATION.md` step.

**Switching a repository to `renovate`, in order:**

1. If the hosted Renovate app is installed on the repository, remove it. Otherwise two Renovates race.
2. Set `FACTORY_APP_CLIENT_ID` and `FACTORY_APP_PRIVATE_KEY` (`factory rotate-secrets`), or give `FACTORY_GITHUB_TOKEN` Workflows: read and write.
3. Add the repository under Manage Actions access (Read) on each private package it installs.
4. **In one PR**, which reaches the default branch in one merge, since `config.yml` is read from there:
   - set `features.on: [dependency-updater]` and `dependencies.updater: renovate`;
   - in the Renovate config, replace `ignoreDeps` for internal packages with `packageRules`, as the policy describes: no grouping, `minimumReleaseAge: null` for internal packages, `chore(deps)` titles, `!` for breaking updates;
   - add the uv rules from §6 if the repository has git pins.
   
   Dropping `ignoreDeps` before the updater switches would let Renovate and the agent both bump the same release.
5. Run `factory-dependency-updates.yml` with `dry_run` and read the log before the first real run.

**`factory doctor` reports:**
- `updater: renovate` with neither app secrets nor `FACTORY_GITHUB_TOKEN`;
- `updater: renovate` and no Renovate config file (`renovate.json`, `.github/renovate.json`, `renovate.json5`, `.renovaterc*`);
- `dependencies.updater` set while the flag is off.

## Testing and validation

| PRODUCT invariant | Check |
|---|---|
| 1 | `test_plan.py`: `validate_config` accepts the three values, and rejects others and unknown `dependencies.*` keys. `updates.dependencies` is still an unknown key. |
| 2, 3 | Golden plans for `dependency-bump`: `renovate`, `dependabot` and `agent`, each with `breaking` false and true. A breaking plan is `open-breaking-issue` in all three. |
| 2 (`renovate`) | `test_apply`-style test: `dispatch-updater` calls `gh workflow run factory-dependency-updates.yml` with the package and source repository, and nothing else. |
| 4 | `actionlint` on `renovate.yml`. The action is pinned by SHA and `renovate-version` is exact (a CI grep, like the existing pin checks). |
| 5 | `updater-plan` test: the token step fails without app secrets or `FACTORY_GITHUB_TOKEN`. No step passes `github.token` to the action as its token. |
| 6 | Test repository: a dry run lists the private package's versions with the `GITHUB_TOKEN` host rule and the Manage Actions access grant, and fails without the grant. |
| 7 | `test_plan.py`: `is_dependency_pr` is true for `chore(deps): …`, `chore(deps)!: …` and the `dependencies` label, and false for a `chore(deps)` look-alike (`chore(depsx):`) and for a bot-authored `feat:` PR. |
| 8 | In the parent's separate PR. |
| 9 | Golden plans with the flag off: `updater: renovate` plans as `agent` with a warning. `updater-plan` returns `run: false`. The review prompt has no dependency line. |
| 10 | The golden plan for `dependency-bump` with no `dependencies` key is unchanged. The rendered stub diff adds only the new stub and the two optional secrets. |
| 11 | `scripts/check-references.sh` passes. |
| §3 scoped run | Test repository with two open Renovate PRs: a scoped dry run, then a real one, closes neither, leaves the dashboard as it was, and opens only the scoped package's PR. Settle the dashboard setting here before merging. |
| §6 uv pins | Test repository with a uv git pin to a private source: one run moves `rev` to the newest tag's commit, updates the comment and regenerates `uv.lock`. If it fails, the uv workaround stays unbuilt and those repositories keep `agent`. |

## Unverified

These were not confirmed from a primary source, and the build settles them as the Testing rows say:

- Whether a GitHub App installation token can read `npm.pkg.github.com`. The spec doesn't rely on it.
- Whether fine-grained PATs gained Packages support after March 2025.
- Whether the package-settings grant is identical on a personal account.
- Which setting keeps a scoped run from rewriting the Dependency Dashboard.
- The uv regex manager end to end, `uv` in post-upgrade tasks, and git credentials there.
- Typical run time and image size.

## Follow-ups

- **Diagnosing a dependency PR whose CI failed** (the issue's item 4). It uses `is_dependency_pr`. It needs a trigger on CI completion, and neither obvious one fits a generated stub:
  - `check_suite` doesn't fire for Actions ("this event does not trigger workflows if the check suite was created by GitHub Actions");
  - `workflow_run` filters on the names of the workflows to watch, which differ per repository, and runs only from the default branch's file. Both points are unverified: that part of the page was read only as a summary, and whether `workflows:` takes wildcards wasn't settled.
  
  It needs its own spec.
- **The `dependabot` value's tracking-issue comment** on the expected wait, which the addendum left optional.
- **A Dependabot asset under the policy**, when a repository needs one.
- **Keeping the factory's own pins current** (the action, Renovate, `create-github-app-token`) by running this workflow on the factory.

## Sources

Fetched 2026-11-10.

- GitHub, fine-grained token gaps: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- GitHub, packages permissions: https://docs.github.com/en/packages/learn-github-packages/about-permissions-for-github-packages
- GitHub, npm registry: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry
- GitHub, packages in Actions: https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions
- GitHub, package access control: https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility
- GitHub, events (`GITHUB_TOKEN` note, `check_suite`, `workflow_run`): https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- GitHub, Actions billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions and https://docs.github.com/en/billing/reference/actions-runner-pricing
- Renovate, private packages and the GitHub platform: https://docs.renovatebot.com/getting-started/private-packages/ and https://docs.renovatebot.com/modules/platform/github/
- Renovate, self-hosted configuration (`repositoryCache`, `cacheDir`, `allowedCommands`): https://docs.renovatebot.com/self-hosted-configuration/
- Renovate source, `main`: `lib/modules/manager/pep621/processors/uv.ts`, `lib/modules/manager/util.ts`, `lib/modules/datasource/git-refs/base.ts`, `lib/modules/manager/custom/regex/`, `lib/workers/repository/update/branch/auto-replace.ts`, `lib/util/git/auth.ts`, `lib/modules/manager/mise/`
- The action: https://github.com/renovatebot/github-action (README, releases)
