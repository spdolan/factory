# Contributing

This is a small, personal project: one maintainer and a handful of repositories that run it. Issues and pull requests are welcome, but expect slow replies and a bias towards keeping things simple.

## Before opening a pull request

- **Open an issue first** for anything bigger than a fix, so the change can be classed before it is written.
- **Title the PR as a conventional commit.** Squash merges use the title as the commit message, and release-please reads it to pick the next version. `fix:` brings behavior back to what is documented. `feat:` is anything a repository could notice (a new write, tool, instruction, cost or default) and ships behind a flag. `feat!:` changes what a repository provides or relies on and needs a migration note. Details: [docs/rollout.md](docs/rollout.md#6-new-behavior-classes-flags-and-update-issues).
- **Name no other repository.** The factory depends on nothing; repositories depend on it. CI fails on `owner/repo` references that aren't the factory itself.
- **Run the checks locally.** They are the same ones CI runs:

  ```bash
  shellcheck scripts/*.sh scripts/factory templates/repo/materialize.sh templates/repo/sync-skills.sh
  ```

  ```bash
  actionlint templates/github/workflows/*.yml .github/workflows/*.yml
  ```

  ```bash
  scripts/check-references.sh
  ```

  ```bash
  python3 -m unittest discover -s runner/tests
  ```

  The runner tests need PyYAML. On a machine without it, run `uv run --no-project --with pyyaml python3 -m unittest discover -s runner/tests`. Each stage has a golden plan under `runner/tests/golden`. Run the tests with `UPDATE_GOLDEN=1` to regenerate them after changing `pipeline.yaml`, `features.yaml`, a prompt or the interpreter. The diff of the golden plans is the behavior change, so review it before you commit.

## What CI runs on your pull request

Only the linters and smoke tests, with a read-only token and no secrets. Nothing in this repository runs an agent on a pull request from a fork. The first pull request from a new contributor waits for a maintainer to approve the workflow run.

## Skills and workflows

- Skills live in `skills/<name>/SKILL.md` with `name:` and `description:` frontmatter; CI checks both.
- The stages live in `pipeline.yaml`, `stages/<stage>/prompt.md` and the reusable workflow `.github/workflows/stage.yml`, which repositories call at a release line. Keep them generic: no owner, repository or package names. `templates/github/workflows/` is the 0.1 copy mode, copied into repositories on install; change it only for a fix 0.1 repositories still need.
- Parts of this repository are derived from MIT-licensed work; see [NOTICE.md](NOTICE.md) and keep it current if you bring more in.
