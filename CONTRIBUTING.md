# Contributing

This is a small, personal project: one maintainer and a handful of repositories that run it. Issues and pull requests are welcome, but expect slow replies and a bias towards keeping things simple.

## Before opening a pull request

- **Open an issue first** for anything bigger than a fix, so the change can be classed before it is written.
- **Title the PR as a conventional commit.** Squash merges use the title as the commit message, and release-please reads it to pick the next version. `fix:` brings behavior back to what is documented. `feat:` is anything a repository could notice (a new write, tool, instruction, cost or default) and ships behind a flag. `feat!:` changes what a repository provides or relies on and needs a migration note. Details: [docs/rollout.md](docs/rollout.md#6-new-behavior-classes-flags-and-update-issues).
- **Name no other repository.** The factory depends on nothing; repositories depend on it. CI fails on `owner/repo` references that aren't the factory itself.
- **Run the checks locally.** They are the same ones CI runs:

  ```bash
  shellcheck scripts/*.sh scripts/factory
  ```

  ```bash
  actionlint templates/github/workflows/*.yml .github/workflows/*.yml
  ```

  ```bash
  scripts/check-references.sh
  ```

## What CI runs on your pull request

Only the linters and smoke tests, with a read-only token and no secrets. Nothing in this repository runs an agent on a pull request from a fork. The first pull request from a new contributor waits for a maintainer to approve the workflow run.

## Skills and workflows

- Skills live in `skills/<name>/SKILL.md` with `name:` and `description:` frontmatter; CI checks both.
- Workflow templates in `templates/github/workflows/` are copied into consuming repositories, so a change there reaches every repository on its next install. Keep them generic: no owner, repository or package names.
- Parts of this repository are derived from MIT-licensed work; see [NOTICE.md](NOTICE.md) and keep it current if you bring more in.
