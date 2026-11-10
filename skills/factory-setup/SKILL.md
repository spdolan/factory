---
name: factory-setup
description: Install the factory in a repository, move a repository from 0.1 copy mode to the stubs, or update it to a newer release line, then fill in FACTORY.md and config.yml and check the result with factory doctor. Drives the factory's own CLI (install, update, doctor) and hands every secret, token and repository setting to the human. Use when asked to "set up the factory", "install the factory here", "migrate to 0.2", "update the factory", "why isn't the factory running here?", or when factory doctor reports problems.
disable-model-invocation: true
---

# Factory setup

Get a repository to a state where `factory doctor` reports nothing but the secrets a human still has to set, on a branch, as one reviewable PR. The CLI does the mechanical work. This skill decides which command to run, drafts the files the CLI only templates (`FACTORY.md`, `config.yml`), and keeps every credential and setting change with the human.

It is invoked by a person, never by a factory stage. It runs in an interactive session at the root of the repository being set up, with a local checkout of the factory.

## Before anything

1. **Find the factory checkout.** `FACTORY_DIR` if set, otherwise `~/code/factory`; ask if neither exists. Update it (`git -C "$FACTORY_DIR" pull --ff-only`) and read its version from `.release-please-manifest.json`. The commands below are `"$FACTORY_DIR/scripts/factory" …`; the docs are `"$FACTORY_DIR/docs/setup.md"` and `"$FACTORY_DIR/MIGRATION.md"`. Read `docs/setup.md` before the first install in a session.
2. **Refuse to run in the factory itself.** If the current repository has `pipeline.yaml` and `scripts/factory`, stop. The factory must never get the `factory` topic or be in `FACTORY_GITHUB_TOKEN`'s repositories.
3. **Work on a branch from a clean tree.** If the tree is dirty, ask. Create `chore/factory-setup` (or `chore/factory-v0.N` for an update).
4. **Check the login.** `gh auth status` must show the account that owns the repository. Everything runs through that login.

## 1. Detect the state

Run `factory doctor` (read-only without `--fix`) and look at the files:

| What you find | State | Mode |
|---|---|---|
| No `factory-*.yml`, no `.github/factory/` | not installed | **install** |
| `factory-*.yml` copies and `.claude/factory.lock`, no `.github/factory/config.yml` | 0.1 copy mode | **migrate** |
| Stubs calling `stage.yml@vX` and `config.yml` | installed | **update** if the factory has a newer line than `vX`, or doctor reports stale stubs; otherwise **check** |

Read the ref the stubs call (`grep -h 'stage.yml@' .github/workflows/factory-*.yml`). Tell the user the state, the ref, and the mode you propose, and wait for a yes.

## 2. Decide with the user

Ask only what the repository can't tell you:

- **Ref.** The line tag of the checkout's version (`v0.N`), which is the default. `--ref main` is only for the factory's test repository.
- **Autonomy.** `standard` (triage decides), `small` (agents advance only small issues) or `off` (humans advance everything). Suggest `small` for a repository's first weeks.
- **Library or application.** A library that other repositories pin needs the release job and a Consumers list (step 6).
- **Local runtime.** Whether spec and implement should run as sessions on the user's machine (`stages.<stage>.runtime: local`) or in Actions (default).

## 3. Run the CLI

Always `--dry-run` first and show the user what it will write or remove.

- **install:** `factory install [--ref REF] --dry-run`, then without `--dry-run`.
- **migrate:** the same command; it also removes the 0.1 copies that still match the lock. Then follow the 0.1 → 0.2 entry in `MIGRATION.md` step by step. For step 2, list every file the install kept (a local edit makes it the repository's fork) and ask, per file, whether to keep the fork or delete it and take the factory's version. For step 3, read `gh variable list` and propose the `config.yml` key for each `FACTORY_*` variable from the table there. Moving a value into `config.yml` is a file edit. Deleting the variable is a setting change: list the `gh variable delete` commands for the user, or run them only after a yes for each.
- **update:** `factory update --to v0.N --dry-run`, then without it. It prints the `MIGRATION.md` entries between the two lines: follow each one, in order, and say which ones you did and which need the user.
- **check:** nothing to render. Go to step 7.

Never edit a stub by hand. If one is wrong, fix the input (`config.yml`, the ref) and run `factory update` again.

## 4. Fill in FACTORY.md

Agents read it on every run, so it must be short, literal and true. Draft each section from evidence, mark anything you inferred, and have the user confirm **Protected paths** and **Human-only** (those are their judgement, not yours).

- **Validation commands:** what CI runs, in order (read `.github/workflows/`, `mise.toml` tasks, `package.json` scripts, the README). Run each one once to confirm it works from a clean checkout. List commands that need local-only resources (a local database, private data) separately.
- **Protected paths:** always `.github/factory/config.yml` and `.github/workflows/`. Then propose what the code shows: migrations, schemas and generated code, public API surfaces, auth, anything an `AGENTS.md` calls an invariant.
- **Human-only:** propose auth, secrets, data deletion, billing, anything that publishes. Ask.
- **Consumers, App, Review notes:** fill them in if they apply, otherwise delete the section. The App section is what verify-behavior uses to start the app; take the commands from the README or `docker-compose.yml`, and test them.

Leave `vision.md` and `bets.md` as templates unless the user wants to write them now (the `bet` skill does that).

## 5. Set config.yml

The installer writes every key commented out at its default. Uncomment only what the user chose in step 2, and leave the rest as comments so the defaults stay visible.

**Flags.** Read `"$FACTORY_DIR/features.yaml"`. For each flag, give the user its summary, state and cost, and record their decision under `features.on` or `features.off`. A flag left undecided is listed in the repository's first `factory:update` issue, so deciding now keeps that issue empty.

Run `factory doctor` again; it validates the file.

## 6. Libraries only

If other repositories pin this one:

- Add the `notify-consumers` job to the release-please workflow, after the publish job, as in step 3 of `docs/setup.md`, with the permissions in step 6 of the 0.1 → 0.2 entry of `MIGRATION.md` and `secrets: inherit`.
- List each consumer under **Consumers** in `FACTORY.md`, in exactly the form the template shows.

## 7. Settings and secrets: hand them over

`factory doctor` reports what's missing. Group the remaining items into what you may do after a yes and what only the user can do.

**After the user says yes:** `factory doctor --fix` adds the `factory` topic, creates missing labels and sets the Actions permissions (read-only default token; Actions may create and approve PRs). `--protect-default-branch` also creates a ruleset requiring a pull request; on a private repository that needs GitHub Pro. Say what each will change before running it.

**Only the user** (you never see, handle, print or store a secret value):

- **`FACTORY_GITHUB_TOKEN`:** a fine-grained token (`docs/setup.md` §1). If one exists, the user must still **add this repository to its repository access** in GitHub's token settings; this is the step most often missed, and agent PRs then fail to trigger CI. Permissions: Contents, Issues, Pull requests, Actions read and write; Workflows off.
- **Claude credential:** `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or `ANTHROPIC_API_KEY`.
- **`FACTORY_READ_TOKEN`** only while the factory is private; **`FACTORY_SKILLS_TOKEN`** only if `.agents/skills.lock` names a private source.

Give the commands to run in their own shell, values exported there and never pasted into the session:

```bash
export FACTORY_GITHUB_TOKEN='…'  CLAUDE_CODE_OAUTH_TOKEN='…'
"$FACTORY_DIR/scripts/factory" rotate-secrets --dry-run
"$FACTORY_DIR/scripts/factory" rotate-secrets
```

`rotate-secrets` only reaches repositories with the `factory` topic, so the topic must be set first. It skips a secret a repository already has, so it never overwrites another repository's secrets. If the user means to replace a token (expired, or the wrong one), give `rotate-secrets --force NAME` for that secret instead.

## 8. Verify and hand off

1. `factory doctor`: everything `ok` except secrets the user hasn't set yet, which you list.
2. `actionlint .github/workflows/factory-*.yml` if actionlint is installed.
3. Commit with a conventional message: `ci: install the factory at v0.N`, `ci: move the factory from 0.1 to v0.N` or `ci: update the factory to v0.N`, ending with the `Co-Authored-By` line for the model you are running as. Ask before pushing and opening the PR; its title is the commit message.
4. For a migrate: required checks are renamed to `<stage> / <job>` (for example `review / agent`). If a ruleset requires the old names, tell the user which to rename.
5. After the merge and the secrets: suggest a smoke test. The user opens a small, real issue, and triage should label it within a few minutes; the run's summary shows the factory commit, model and flags it resolved. Don't open the issue yourself unless asked.

Report: the mode, the ref, each file changed, the flag decisions, what doctor still reports, and the user's remaining steps as a numbered list.

## Guardrails

- Never handle secret values, put them on a command line, or write them to a file.
- Never change repository settings, rulesets, variables or secrets without a yes for that change. Never add the factory itself to anything.
- Never edit `.github/workflows/factory-*.yml`, `.github/factory/materialize.sh`, the `.gitignore` block or the SessionStart hook by hand; the CLI renders them.
- Never push to the default branch or merge.
- If a command fails, show its output and stop; don't work around the CLI.
