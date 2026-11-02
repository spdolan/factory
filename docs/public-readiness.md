# Before making the factory public

A checklist for the day the factory goes public, if it does ([rollout.md §11](rollout.md#11-public-or-private)). Nothing here is needed while it stays private. Each item says what it touches and how much it matters: **must** before flipping visibility, **should** soon after, **nice** when convenient.

Going public is one click (Settings → General → Change visibility) and undoing it doesn't unpublish anything: forks, clones and caches keep whatever was visible. So the history and secrets items come first.

## 1. What the git history exposes

The current tree names no other repository (`scripts/check-references.sh` enforces it), but the history does. Checked 2026-11-02 over every commit on every branch:

| Item | Where | Priority |
|---|---|---|
| **No secrets in history.** A pattern scan for GitHub and Anthropic token shapes over `git log -p --all` found nothing. Terraform state (which held secrets in plain text) was gitignored and never committed. Re-run the scan right before flipping: `git log -p --all \| grep -cE 'gh[pous]_[A-Za-z0-9]{30,}\|sk-ant-'` must print `0`. | whole history | must |
| **Old `infra/live/`** (removed in `e3da1ca`) holds a Terragrunt file per repository with its name, autonomy, model and effort settings and a comment on why. `git show e3da1ca^:infra/live/` shows them. | history | must: decide |
| **Commit messages name repositories and issues**, for example `<owner>/<library>#22` and `feat(infra): triage <two repositories> on Haiku`. About 15 commits. | history | must: decide |
| **Your personal email on 4 early commits** (`b0aeb4d`, `9c27ea5`, `9477d59`, `822ec24`); the rest use the GitHub noreply address. | history | must: decide |
| **11 stale remote branches** from merged PRs (`fix/local-*`, `feat/local-runner`, …). They add nothing the history doesn't already show, but they clutter the branch list. Delete them after confirming each PR is merged, and turn on "Automatically delete head branches". | branches, Settings → General | should |

**Deciding the history.** Three ways, from least to most work:

1. **Publish as is.** Repository names and settings of private projects become visible, and the email. Links to PRs 1–11 keep working. The decision log currently recommends this.
2. **Rewrite history** with `git filter-repo` (mailmap for the email, `--path infra --invert-paths` for the infra, `--replace-message` for names in messages), then force-push. PR links survive but point at commits that no longer exist in the branch; every clone has to be re-cloned; the `v0.1.0` tag must not exist yet, or it has to be re-cut.
3. **Fresh public copy.** A new public repository from a squashed snapshot of `main` (one commit, or one per release), the private one archived. Nothing leaks, PR links are lost, and `install-factory.sh`'s recorded `factory@<sha>` in each consumer's `.claude/factory.lock` no longer resolves until the next install.

Whichever it is, do it before the first release tag exists, because the tag ruleset (once set) stops anyone from moving `v*` tags, including you.

## 2. Docs and comments that assume private or read as internal notes

| Item | File | Priority |
|---|---|---|
| "Status: proposal, third draft. Phase 0 is in progress." and the Migration section's "On the branch now" read as a work log. Replace with the state at release time, or move the phase plan to an issue. | `docs/rollout.md` (top, Migration) | should |
| "Commit af9f982 shows why" is fine, but "Tested on 2026-11-02 with a throwaway reusable workflow…" and the open-questions table are internal notes. Keep the results, drop the diary. | `docs/rollout.md` (Open questions) | should |
| References to "the pilot notes" and "the decision log" (a private Claude doc) can't be followed by a reader. Removed from §11 and open question 6 on this branch; grep for any that return. | `docs/rollout.md` | must |
| `docs/setup.md` says "your account or organization" and "Never include the factory itself": written for one owner. Fine as is; say once at the top that the reader is the owner of the repositories. | `docs/setup.md` | nice |
| `docs/local-runner.md` is written for one Mac ("your Mac", `~/factory-work`, `scutil`). Say it is macOS-only and a single-user setup. | `docs/local-runner.md` | nice |
| `README.md` says "about five repositories" nowhere, but the design docs assume a solo developer with a handful of repositories. Say so in the README's first paragraph, so nobody expects an org-scale tool. | `README.md` | should |
| `scripts/factory` header: "Every command works through your own `gh` login" is right. `protect`'s "local agent sessions run with your login" assumes the local runner; fine. | `scripts/factory` | nice |
| `templates/github/workflows/*.yml` comments mention `FACTORY_GITHUB_TOKEN` being "attributed to you". Fine. | — | — |

## 3. Stale or contradictory docs

| Item | File | Priority |
|---|---|---|
| `rollout.md` §9 said fork PRs run CI "which uses no secrets"; `ci.yml` passes `FACTORY_PRIVATE_NAMES`. Fixed on this branch; keep them in step. | `docs/rollout.md` §9, `.github/workflows/ci.yml` | done |
| `rollout.md` open question 6 named a repository. Fixed on this branch. | `docs/rollout.md` | done |
| `scripts/factory doctor` reports a missing `FACTORY_READ_TOKEN` on every consumer while the factory is private, but nothing in 0.1 fetches the factory at run time, so it isn't needed until 0.2. Either downgrade it to a note until the reusable workflows land, or say in the message that it is for 0.2. If the factory goes public, the check disappears. | `scripts/factory` (doctor), `docs/setup.md` §1 | should |
| `docs/setup.md` §1 "FACTORY_READ_TOKEN": "Runs fetch the factory's skills, scripts and configuration" describes 0.2, not today. Mark it as such. | `docs/setup.md` | should |
| `README.md` "Versions" and `release.yml` describe moving line tags "which repositories will call once the reusable workflows land". Keep the tense honest after 0.2 ships. | `README.md`, `.github/workflows/release.yml` | nice |
| `architecture.md` and `pipeline.md` are labelled proposals. When 0.2 ships, relabel or fold into the README. | `docs/architecture.md`, `docs/pipeline.md` | nice |
| `templates/repo/FACTORY.md` Consumers section asks for `owner/repo` lines: fine, that is the consumer's own file, not the factory's. | — | — |

## 4. Files a public repository usually has

| Item | File | Priority |
|---|---|---|
| **SECURITY.md**: how to report a problem privately (GitHub's private vulnerability reporting, Settings → Code security, is free on public repositories; turn it on), what is in scope (the workflows run with consumers' secrets), and that there is no bug bounty. | `SECURITY.md` | done |
| **CONTRIBUTING.md**: conventional PR titles (the CI check explains the types), the no-references rule, how to run the lints locally (`shellcheck scripts/*.sh scripts/factory`, `actionlint`, `scripts/check-references.sh`), and that fork PRs run only the linters. Keep it short. | `CONTRIBUTING.md` | done |
| **Issue and PR templates**: one issue template is enough. A PR template that reminds about the title class (`fix` / `feat` behind a flag / `feat!` with a `MIGRATION.md` entry). | `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` | nice |
| **CODEOWNERS**: `* @<owner>` so review requests go to you, and so a future "require code owner review" rule has something to point at. | `.github/CODEOWNERS` | nice |
| **CHANGELOG.md**: release-please creates it on the first release; nothing to do unless you want a hand-written entry for 0.1.0. | `CHANGELOG.md` | — |
| **LICENSE and NOTICE.md** already exist and are correct for a derivative of MIT work. Check that the copyright line in `LICENSE` is the one you want public. | `LICENSE` | must: check |
| **Dependabot for Actions**: `.github/dependabot.yml` with `package-ecosystem: github-actions` keeps `claude-code-action`, `release-please-action` and `actions/checkout` current, in the factory and (through the templates' pins) in consumers. | `.github/dependabot.yml` | should |

## 5. CI behavior for fork pull requests

Public means strangers can open PRs. Today's CI is already fork-safe, but it needs two settings and one doc line:

| Item | File / setting | Priority |
|---|---|---|
| `ci.yml` and `pr-title.yml` run on `pull_request`, not `pull_request_target`, with no write permissions (`pr-title.yml` has `permissions: {}`; `ci.yml` inherits the repository default, which is read-only). Keep it that way; `ci.yml` sets `permissions: contents: read` so it doesn't depend on the repository setting. | `.github/workflows/ci.yml` | done |
| The no-references check reads `secrets.FACTORY_PRIVATE_NAMES`, which is empty on fork PRs, so a fork PR could add a private name that only the post-merge run on `main` catches. Acceptable; say so in `CONTRIBUTING.md`. | `scripts/check-references.sh`, `CONTRIBUTING.md` | nice |
| **Require approval for first-time contributors** (Settings → Actions → General → Fork pull request workflows) so CI minutes aren't spent on drive-by PRs. The default for public repositories is "first-time contributors", which is fine; confirm it. | Settings → Actions | must: check |
| `release.yml` runs on `push` to `main` only and the `rollback` input is `workflow_dispatch` only; forks can't reach either. | — | — |
| The release PR is opened with `GITHUB_TOKEN`, so neither CI nor the title check runs on it. Don't make either a required check on `main`, or release PRs can never merge; if you want them, run release-please with a token of your own (a fine-grained PAT with Contents and Pull requests on the factory only). | `.github/workflows/release.yml`, ruleset on `main` | should |

## 6. Settings to set

| Item | Where | Priority |
|---|---|---|
| **`FACTORY_PRIVATE_NAMES` secret** on the factory: the bare names of your private repositories (comma-separated), so `check-references.sh` catches them even without `owner/` in front. Checked 2026-11-02: not set. Names that are ordinary words match everywhere; pick distinctive ones. Set it before going public, and re-run CI on `main` once. | Settings → Secrets → Actions | must |
| **Squash merges only, PR title as the commit message.** Today merge commits and rebase merges are still allowed and the squash title is "commit or PR title", so a one-commit PR's commit message, not its checked title, becomes what release-please reads. Set `squash_merge_commit_title=PR_TITLE` and turn off the other two merge methods. | Settings → General → Pull Requests (`gh repo edit --enable-merge-commit=false --enable-rebase-merge=false --squash-merge-commit-title PR_TITLE`) | must |
| **Allow GitHub Actions to create and approve pull requests** on the factory. Checked 2026-11-02: off. release-please can't open the release PR without it. | Settings → Actions → General | must |
| **Rulesets** on `main` and `v*` tags (`scripts/factory protect`). Done 2026-11-02, but the GitHub Actions app can't be a bypass actor on a personal account, so the tag ruleset has no bypass and blocks releases until a GitHub App (or other actor) is set up ([rollout.md](rollout.md) open question 4). `protect` still sends the invalid actor and needs updating. | `scripts/factory protect`, `.github/workflows/release.yml` | must |
| **Private vulnerability reporting** on, **Discussions** off unless wanted, **Wiki** off, **Projects** off: fewer surfaces to moderate. | Settings → General | should |
| **Topics and description** on the factory itself so the repository page explains itself. Never give the factory the `factory` topic: `rotate-secrets` skips its own repository, but a second checkout with a different origin would not. | Settings → General | nice |
| **Branch deletion on merge** on, to stop the stale-branch list growing. | Settings → General | nice |

## 7. Other things found while reviewing

| Item | File | Priority |
|---|---|---|
| `scripts/factory protect` and `doctor --protect-default-branch --fix` call the rulesets API and die on the 403 a Free private repository returns, halfway through (`set -e`), with `gh`'s raw error. Catch the 403 and print the Pro-or-public message. | `scripts/factory` | should |
| `scripts/factory doctor` printed `cannot iterate over: null` on every repository without topics (jq on a null `repositoryTopics`). Fixed on this branch. | `scripts/factory` | done |
| `scripts/factory` finds the factory's own `owner/name` from the `origin` remote. A fork or a mirror with another origin would protect the wrong repository or stop skipping the factory in `rotate-secrets`. Accept `--repo` everywhere (protect has it; doctor and rotate-secrets don't) or document the assumption. | `scripts/factory` | nice |
| `release-please-config.json` uses `release-type: simple`, which also tries to bump a `version.txt` if one exists. There is none, which is fine; the first release PR should be checked for the version it proposes (0.1.0). | `release-please-config.json` | nice |
| `templates/github/workflows/*.yml` pin `anthropics/claude-code-action@v1.0.245` by tag, not SHA. A public repository that tells others to copy these should pin by SHA with a version comment, like `release.yml` does. | `templates/github/workflows/` | should |
| `README.md` says the factory is "a port of warpdotdev-demos/cloud-factory-demo"; `NOTICE.md` records the upstream commits. Keep both current when skills change. | `README.md`, `NOTICE.md` | — |
