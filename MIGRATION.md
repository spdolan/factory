# Migration

What a consuming repository does to move from one minor line to the next. Each entry is written so a person or an agent can follow it step by step. `factory update --to vX.Y` prints the entries between two versions.

## 0.1 → 0.2

0.2 replaces the copied workflows and skills with one generated stub per stage. Each stub calls the factory's reusable workflow, `stage.yml`, at a release line (`@v0.2`). Settings move from repository variables into `.github/factory/config.yml`, and agents no longer hold a write token.

### Before you start

- Use a factory checkout at 0.2.0 or later (`git -C ~/code/factory pull`).
- If the factory is private, the repository needs `FACTORY_READ_TOKEN` (`factory rotate-secrets`), and the factory needs Actions access for your repositories (`factory protect`). A public factory needs neither.

### Steps

1. **Install the stubs.** From the repository root, on a new branch:

   ```bash
   ~/code/factory/scripts/factory install
   ```

   It calls `@v0.2` by default; the test repository uses `--ref main`. It does this:
   - writes `.github/workflows/factory-<stage>.yml` for every stage
   - removes the 0.1 copies that still match `.claude/factory.lock`, including `factory-local.yml`, then the lock itself
   - adds a `.gitignore` block for `.factory/` and the factory's skill directories
   - adds a SessionStart hook to `.claude/settings.json` that fetches the pinned skills
   - adds `.github/factory/materialize.sh` and `.github/factory/config.yml`

   `--dry-run` shows the changes first.
2. **Check what it kept.** A skill or workflow you changed since the last install is kept, and the install says so. A kept skill is now your repository's own fork, and the factory leaves it alone. Delete it to take the factory's version. A kept workflow blocks its stub: delete it, then run `factory update`.
3. **Move settings into `config.yml`.** This is optional, since variables still work and take precedence over the file. Delete each variable once it's moved, or it keeps overriding the file.

   | 0.1 variable | `config.yml` key |
   |---|---|
   | `FACTORY_AUTONOMY` | `autonomy` |
   | `FACTORY_VERIFY` | `verify` |
   | `FACTORY_MODEL_<STAGE>` | `stages.<stage>.tier` (a tier, `fast`/`balanced`/`deep`, or a model ID) |
   | `FACTORY_EFFORT_<STAGE>` | `stages.<stage>.effort` |
   | `FACTORY_MODEL_IMPLEMENT_AGENT` | `stages.implement.when.autonomous.tier` |
   | `FACTORY_MODEL_RISK` | `stages.<stage>.when.risk.tier` (spec, implement) |
   | `FACTORY_MODEL_REVIEW_SMALL` | `stages.review.when.small_change.tier` |
   | `FACTORY_REVIEW_SMALL_LINES` | `stages.review.small_change_lines` |
   | `FACTORY_MODEL_BET`, `_IMPROVE`, `_BUMP` (and `FACTORY_EFFORT_*`) | `stages.bet-intake`, `stages.improve-review`, `stages.dependency-bump` |
   | `FACTORY_LOCAL_SETTING_SOURCES` | `runtimes.local.setting_sources` |
   | `FACTORY_WORK_DIR` | `runtimes.local.work_dir` |

   `FACTORY_TRIAGE_ALL` stays a variable: the stub reads it before a run starts.
4. **Protect `config.yml`.** List `.github/factory/config.yml` under **Protected paths** in `FACTORY.md`. It is read from the default branch, so a PR can't change the settings its own review uses.
5. **Decide on flags.** `spec-auto-advance` is on by default: agents may start the spec stage for medium `ready-to-spec` issues, as in 0.1. To have a human approve those instead, add `features: {off: [spec-auto-advance]}`. The first run opens a `factory:update` issue that lists every flag you haven't put under `features.on` or `features.off`.
6. **Libraries only: the release job's permissions.** The job in your release-please workflow that calls `factory-notify-consumers.yml` needs these permissions, because the stub's ceiling can't exceed its caller's. Keep `secrets: inherit`.

   ```yaml
   permissions:
     contents: read
     issues: write
     pull-requests: read
     packages: read
     id-token: write
   ```
7. **Required checks.** Check names become `<stage> / <job>`, for example `review / agent` and `review / apply`. Rename any check a ruleset requires.
8. **Commit, open the PR, and merge it.** `factory doctor` should report the stubs and `config.yml` as ok. After the merge, the first session in a clone fetches the skills into `.claude/skills/`, which is now gitignored.

### What behaves differently

- **Agents have no write token.** Spec, implement, improve-review and dependency-bump commit locally. A separate apply job pushes the branch and opens the PR, with `FACTORY_GITHUB_TOKEN` when it is set. The apply job refuses any agent change under `.github/workflows/`.
- **No "started" or progress comments** from Actions runs. The final comment links the run. Local sessions still post them.
- **One state at a time.** Setting a state removes the other state labels. A specs PR moves its issue from `ready-to-spec` to `spec-ready-for-review`.
- **Bet intake** drafts its issues as structured output. The apply job creates them and dispatches triage.
- **Local sessions** are the `local` runtime of spec and implement. The `factory:local` label still picks it per issue, and `stages.<stage>.runtime: local` picks it for every issue. The session gets its skills from the SessionStart hook, so the self-hosted machine needs to reach the factory, and needs your `gh` login if the factory is private.
- **Review** has a 30-minute timeout. 0.1's review job had none.
- **A new label,** `factory:update`. It is created on first use, or by `factory doctor --fix`.
- **Every run's summary** shows the factory commit, the resolved model, tools and prompt, where each value came from, the flags that are on, and any pending update.

### Rolling back

Revert the install commit. That restores the 0.1 copies and the lock.
