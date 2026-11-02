# Setting up a repository

Install the factory files into the repository (see the [README](../README.md#install-into-a-repository)), then give its workflows credentials and settings with the factory's CLI, [`scripts/factory`](../scripts/factory). The manual steps below do the same thing.

## 1. Create the tokens

These can't be created by API, so they are always manual.

### FACTORY_GITHUB_TOKEN

One fine-grained personal access token covers every repository the factory runs in.

1. Go to GitHub → Settings → Developer settings → Fine-grained tokens → **Generate new token**.
2. **Name:** `factory`. **Expiration:** the longest your account allows. Put a reminder on your calendar a week before it expires.
3. **Resource owner:** your account or organization. **Repository access:** only select repositories: each repository the factory runs in, and add new ones as you install them. Never include the factory itself: agents hold this token, and every repository runs the factory's code.
4. **Repository permissions:**

   | Permission | Access | Why |
   |---|---|---|
   | Contents | Read and write | push agent branches; `repository_dispatch` to consumers |
   | Issues | Read and write | comments and labels |
   | Pull requests | Read and write | open PRs |
   | Actions | Read and write | dispatch the next stage |
   | Metadata | Read | required |

   Leave **Workflows** off, so agents can't push changes to `.github/workflows/`.
5. Copy the token.

Actions run with this token are attributed to you. Unlike `GITHUB_TOKEN`, it triggers CI and review on agent PRs.

### Claude credentials

Use one of these:

- `claude setup-token` creates a `CLAUDE_CODE_OAUTH_TOKEN` that bills to your Claude subscription.
- An `ANTHROPIC_API_KEY` from the Console bills to your API account. Set a workspace spend limit there.

## 2. Apply the settings

### With the factory CLI (recommended)

Each repository declares on its own side that it uses the factory, and the factory's CLI finds and configures repositories by that declaration. The factory itself lists none of them. On GitHub the declaration is the `factory` repository topic.

From inside the consuming repository:

```bash
~/code/factory/scripts/factory doctor          # report what's missing
~/code/factory/scripts/factory doctor --fix    # add the topic, labels and Actions settings
```

`doctor --fix` adds the `factory` topic, creates any missing labels (from `templates/labels.txt`), and sets Actions to a read-only default token that may create and approve pull requests. It reports the secrets but can't set them, because it never sees their values. Add `--protect-default-branch` to also require a pull request and block force pushes on the default branch. Rulesets on private repositories need GitHub Pro or higher.

Then set the secrets on every repository that has the topic, from anywhere:

```bash
export FACTORY_GITHUB_TOKEN='<the fine-grained token>'
export CLAUDE_CODE_OAUTH_TOKEN='<from claude setup-token>'
~/code/factory/scripts/factory rotate-secrets --dry-run   # list where they would go
~/code/factory/scripts/factory rotate-secrets
```

It sets only the secrets you exported, pipes each value to `gh` (never on a command line), writes nothing to disk, and lists every repository it updated. A repository missing from that list lacks the topic. To rotate a token, export the new value and run it again.

Per-repository settings such as `FACTORY_AUTONOMY` or `FACTORY_MODEL_TRIAGE` are optional repository variables, set with `gh variable set` (below). In 0.2 they move into each repository's `.github/factory/config.yml`.

### By hand

For each repository:

```bash
gh repo edit <owner>/<repo> --add-topic factory
```

```bash
gh secret set FACTORY_GITHUB_TOKEN --repo <owner>/<repo>
```

```bash
gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo <owner>/<repo>
```

```bash
gh variable set FACTORY_MODEL_TRIAGE --repo <owner>/<repo> --body claude-haiku-5-5
```

```bash
~/code/factory/scripts/install-factory.sh --create-labels
```

Also turn on **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests**. `factory doctor --fix` sets this for you.

### Protecting the factory

Every consuming repository runs the factory's code with its own secrets, so protect the factory too. From inside the factory:

```bash
scripts/factory protect
```

It creates (or updates) two rulesets. On `main`, changes go only through a pull request, with no force pushes or deletion. On `v*` tags, only GitHub Actions (the release workflow) may create, move or delete them. There is no admin bypass, because local agent sessions run with your login. Never add the factory to `FACTORY_GITHUB_TOKEN`'s repositories, and never give it the `factory` topic.

## 3. Library releases

Add this job to the library's `release-please.yml`, after the publish job. Releases created with `GITHUB_TOKEN` don't trigger other workflows, so the call must come from the release-please workflow itself.

```yaml
  notify-consumers:
    needs: [release-please, publish-ts]
    if: needs.release-please.outputs.ts_release_created == 'true'
    uses: ./.github/workflows/factory-notify-consumers.yml
    with:
      tag: ${{ needs.release-please.outputs.ts_tag }}
      package: "@<owner>/<library>"
    secrets: inherit
```

Then list the consumers under `## Consumers` in the library's `FACTORY.md`. Each consumer's `factory-dependency-bump.yml` bumps the pin for a non-breaking release, or opens an issue for a human when the release notes contain `BREAKING CHANGE`.
