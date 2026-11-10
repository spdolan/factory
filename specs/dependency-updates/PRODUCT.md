# Dependency updates: a deterministic updater, with the agent kept for judgement

## Summary

Today the `dependency-bump` stage has a Haiku agent find a pin, set a version, regenerate the lockfile and open a PR. That is arithmetic in prose: it costs a model run per consumer and release, and it isn't reproducible (#42). This spec lets a repository choose who makes the bump:

- **`renovate`**: a factory-owned, pinned, self-hosted Renovate.
- **`dependabot`**: Dependabot, which the factory leaves alone.
- **`agent`**: today's skill.

The factory recognizes dependency PRs by what they say they are, not by which bot opened them.

Renovate is the chosen tool for the owner's repositories. The factory depends on a small contract rather than on Renovate, so a repository on Dependabot, or on neither, fits without a fork. The contract rests on a tool-neutral dependency-update policy (grouping, cadence, release-age waits, `chore(deps)` titles, who merges) that lives outside the factory. This spec doesn't write that policy, and the factory never reads it.

The consumers are repositories that call the factory, the owner who sets them up, and whoever builds this.

## Behavior

1. **A new top-level `config.yml` key, `dependencies`, holds the choice.** It doesn't go under `updates:`, which already means updates to the factory itself (`updates.check`, `updates.advance`).

   ```yaml
   dependencies:
     updater: agent      # renovate | dependabot | agent
     bots: []            # extra bot logins allowed through review (lands separately)
   ```

   `agent` is the default, so a repository that sets nothing behaves as it does today.
2. **What happens when a `factory-dependency-release` arrives** depends on `dependencies.updater`:

   | `updater` | Non-breaking release | Breaking release | Weekly schedule |
   |---|---|---|---|
   | `renovate` | The factory's Renovate workflow runs in this repository, scoped to that one package, with no schedule and no release-age wait. No agent runs. | `open-breaking-issue` | Renovate runs for every dependency, under the repository's own Renovate config |
   | `dependabot` | Nothing. The run's summary says Dependabot's next scheduled run (at best daily) will pick the release up, because Dependabot can't be started through an API. | `open-breaking-issue` | Skips |
   | `agent` | Today's `dependency-bump` skill makes the PR. | `open-breaking-issue` | Skips |

3. **A breaking release always takes `open-breaking-issue`**, whatever the updater: an issue labeled `maintenance` and `invariant-risk`, triaged to a human. The factory never starts a scoped Renovate run for a breaking release.
4. **Every Renovate run in every repository uses the same reviewed versions.** The factory pins the `renovatebot/github-action` version and the Renovate version. A repository can't choose a different version except by calling a different factory release.
5. **Renovate's PRs trigger CI and can update workflow files.** They are opened with an installation token from a GitHub App the owner controls, or with `FACTORY_GITHUB_TOKEN` when no app is set up. They are never opened with `GITHUB_TOKEN`.
6. **Private GitHub Packages are readable without a new long-lived token.** When a repository installs a private npm package from `npm.pkg.github.com`, the package's settings grant that repository Read under **Manage Actions access**. Renovate then reads the package with the run's `GITHUB_TOKEN`. `FACTORY_READ_TOKEN` can't do this (TECH.md, "Tokens").
7. **The factory recognizes a dependency PR by its title or label**: a title starting `chore(deps):` or `chore(deps)!:`, or a `dependencies` label. It never goes by the PR's author. The review stage uses this rule, and every later dependency-specific behavior must use it too.
8. **The bots allowed through review come from `config.yml`.** The defaults are `renovate[bot]`, `dependabot[bot]` and the factory's own app. `dependencies.bots` adds more. This piece lands in its own PR, separately from this spec.
9. **All of this is behind the `dependency-updater` flag.** It starts in `preview`. While the flag is off:
   - `dependencies.updater` is read as `agent`, and the plan warns if it says otherwise;
   - the weekly run does nothing beyond its plan job;
   - the review stage gets no dependency-PR instructions.
10. **Nothing a repository relies on today is removed or renamed.** The `dependency-bump` stage, its triggers and inputs, and the `agent` skill all stay. The change is a `feat:`, not a `feat!:`.
11. **The factory names no other repository.** The specs and the code say "a consumer", "the released repository" and "the policy", and `scripts/check-references.sh` passes.

## Not built here

- **A Dependabot configuration asset.** The `dependabot` value's no-op behavior is all that ships. A `.github/dependabot.yml` mapping of the policy waits until a repository needs one.
- **The agent that diagnoses a dependency PR whose CI failed.** The recognition rule (invariant 7) is defined now so that the agent can use it. Starting the agent needs a trigger on CI completion that a generated stub can't express yet (TECH.md, Follow-ups).
- **Renovate as the default updater.** Changing the default from `agent` would be a changed default, a later `feat` decided on its own.
- **Removing or deprecating the `dependency-bump` skill.** It is the `agent` value.
- **A repository cache between Renovate runs.** It isn't worth it at this size (TECH.md, "Cost").
