---
name: dependency-bump
description: Bump this repository's pin on an internal dependency to a new non-breaking release, update the lockfile, run the repository's validation commands, and open a PR. Use when the dependency-bump workflow runs after an internal library releases, or when asked to bump an internal package to a released version.
---

# Dependency bump

Move one dependency to one released version, prove nothing broke, and open a PR. The workflow has already decided the release isn't breaking. If you find out otherwise, stop and say so.

## Inputs (from the prompt)

- Package name, source repository, release tag, and version
- The release notes URL

## Workflow

1. **Find every pin.** Search the manifests for the package name and the source repository:
   - npm/bun: `package.json` (`"@scope/name": "x.y.z"`, an exact pin) and the lockfile (`bun.lock`, `package-lock.json`)
   - Python/uv: `pyproject.toml` (a version, or `git = "https://github.com/<source>", rev = "<sha>"`) and `uv.lock`
   - Any other manifest the repository uses

   If there is no pin, stop and report that this repository doesn't depend on the package.
2. **Update the pins.**
   - A version pin becomes the exact new version. Keep exact pins exact.
   - A git pin moves to the release's commit: `git ls-remote https://github.com/<source> refs/tags/<tag>` (use the `^{}` line for an annotated tag). Keep the existing pin style and comments, and update any comment that names the old version.
   - Regenerate the lockfile with the repository's tool (`bun install`, `uv lock`, `npm install --package-lock-only`). Don't upgrade anything else.
3. **Validate.** Run the validation commands in `FACTORY.md`, or what the README and CI document. Skip the ones `FACTORY.md` marks as needing local-only resources, and list them in the PR.
4. **Read the release notes** (the URL from the prompt, or `gh release view <tag> --repo <source>`) for deprecations or behavior changes this repository should know about.
5. **Open the PR.**
   - Branch: `deps/<package-slug>-<version>`
   - Commit: `chore(deps): bump <package> to <version>`, ending with `Co-Authored-By: Claude <Model> <Version> <noreply@anthropic.com>`, naming the model you are running as (the prompt gives its ID; `claude-haiku-5-5` is Haiku 5.5)
   - `gh pr create` with the same title. The body should cover: the release link, each pin changed (old → new), each validation command and its result, the skipped local-only checks, and relevant notes from the release.
   - If any validation failed, open the PR with `--draft` and put the failing command and the key error lines (no secrets) at the top of the body. Don't try to adapt this repository's code to the new version. That is a human decision, and the draft PR is the hand-off.

## Guardrails

- Change only the pins, lockfiles, and version comments for this one package.
- If the pinned version is already the new version or newer, stop without opening a PR.
- If the release turns out to be breaking (removed APIs, compile errors pointing to changed signatures), still open a draft PR, and title it `chore(deps)!: …` so it is obvious.
- Never push to the default branch or merge.
