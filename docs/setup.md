# Setting up a repository

Install the factory files into the repository (see the [README](../README.md#install-into-a-repository)), then give its workflows credentials and settings. The settings are managed with Terragrunt and the factory's generic module, [`infra/modules/factory-repo`](../infra/modules/factory-repo), from an ops repository of your own. The manual steps below do the same thing.

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

### With Terragrunt (recommended)

The factory names no repository, so the list of repositories lives in an ops repository you own (private is fine), for example `<owner>/fleet`:

```
fleet/live/
  root.hcl                 # provider, local state, shared inputs, module source
  <repo>/terragrunt.hcl    # one per repository: include root.hcl, set repository and overrides
  factory/terragrunt.hcl   # optional: protect the factory (protect_default_branch, protect_release_tags)
```

`root.hcl` pulls the module from the factory at a release tag:

```hcl
terraform {
  source = "git::https://github.com/<owner>/factory.git//infra/modules/factory-repo?ref=v0.1.0"
}
```

Its `inputs` hold the shared defaults (variables, labels, and secrets read from the environment with `get_env`). Each `<repo>/terragrunt.hcl` includes it with `merge_strategy = "deep"` and sets `repository` plus whatever differs.

```bash
brew install terragrunt
```

```bash
export GITHUB_TOKEN="$(gh auth token)"
export FACTORY_GITHUB_TOKEN='<the fine-grained token>'
export CLAUDE_CODE_OAUTH_TOKEN='<from claude setup-token>'
cd ~/code/fleet/live && terragrunt run --all plan
```

Then run the same command with `apply` in place of `plan`. To add a repository, copy a directory and change `repository`.

Keep state local and gitignored (for example under `live/.state/`). It contains the secret values in plain text, so don't copy it anywhere unencrypted. A secret whose environment variable isn't set is left alone, so you can change variables without having the tokens on hand.

To rotate the token, export the new value and apply again.

### By hand

For each repository:

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

Also turn on **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests**. Terragrunt manages this setting for you.

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
