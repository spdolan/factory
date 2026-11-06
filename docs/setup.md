# Setting up a repository

Install the factory's stubs into the repository, then give its workflows credentials and settings with the factory's CLI, [`scripts/factory`](../scripts/factory). The manual steps below do the same thing.

```bash
~/code/factory/scripts/factory install            # stubs call the line tag of your checkout, e.g. @v0.2
~/code/factory/scripts/factory install --ref main # track every merge (the test repository)
```

Run it on a new branch at the repository root. It writes one stub per stage into `.github/workflows/`, `.github/factory/config.yml` and `materialize.sh`, a `.gitignore` block, and a SessionStart hook in `.claude/settings.json` that fetches the pinned skills. It creates `FACTORY.md`, `vision.md` and `bets.md` if they're missing. `--dry-run` shows the changes. A repository still on the 0.1 copies follows [MIGRATION.md](../MIGRATION.md). The 0.1 installer, `scripts/install-factory.sh`, still works.

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

### FACTORY_READ_TOKEN (only while the factory is private)

Runs fetch the factory's skills, scripts and configuration. A public factory needs no token for that. A private one needs a second fine-grained token:

1. **Name:** `factory-read`. **Expiration:** the longest allowed, with a calendar reminder.
2. **Repository access:** only the factory.
3. **Repository permissions:** Contents: Read (Metadata: Read is added automatically). Nothing else.

`factory rotate-secrets` puts it on every consuming repository. Only the checkout step uses it; agents never see it. Also run `scripts/factory protect` in the factory, which sets **Settings → Actions → General → Access** so your other repositories may call its reusable workflows.

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

### Settings: `config.yml`

Per-repository settings live in `.github/factory/config.yml`. `factory install` writes it with every key commented out at its default, so delete what you don't change. It sets autonomy (`standard`, `small` or `off`), `verify`, model tiers and effort per stage, a stage's runtime, flag opt-ins and opt-outs (`features.on`, `features.off`, `features.preview`) and whether to open update issues. `factory doctor` validates it.

The precedence, highest first:

1. A repository Actions variable, such as `FACTORY_AUTONOMY` or `FACTORY_MODEL_TRIAGE`. It is the kill switch, and agents can't change it.
2. `config.yml`.
3. The factory's defaults, in `pipeline.yaml`.

Variables are now optional overrides, set with `gh variable set` (below). A variable you forget to delete keeps overriding the file. The file is read from the default branch, so a pull request can't change the config its own review uses; list it under Protected paths in `FACTORY.md`. [MIGRATION.md](../MIGRATION.md) maps each 0.1 variable to its key.

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
gh variable set FACTORY_MODEL_TRIAGE --repo <owner>/<repo> --body claude-haiku-5-5   # optional override
```

```bash
~/code/factory/scripts/factory doctor --fix
```

Also turn on **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests**. `factory doctor --fix` sets this for you.

### Protecting the factory

Every consuming repository runs the factory's code with its own secrets, so protect the factory too. Rulesets need a public repository or GitHub Pro.

The release workflow needs an actor that may create and move `v*` tags while everyone else, including you, may not. On a personal account that can't be the GitHub Actions app (the API refuses it as a bypass actor), so it is a GitHub App you own:

1. GitHub → Settings → Developer settings → GitHub Apps → **New GitHub App**. Name it `<something>-factory-release`; any homepage URL; untick **Webhook → Active**.
2. **Repository permissions:** Contents: Read and write, Pull requests: Read and write (Metadata: Read is added). **Where can this GitHub App be installed:** Only on this account.
3. Create it, then **Generate a private key** (a `.pem` download) and note the **App ID** and **Client ID** on the app's page.
4. **Install App** → your account → only the factory.
5. Put the two values on the factory, from anywhere:

   ```bash
   gh secret set FACTORY_RELEASE_APP_CLIENT_ID --repo <owner>/factory
   ```

   ```bash
   gh secret set FACTORY_RELEASE_APP_PRIVATE_KEY --repo <owner>/factory < ~/Downloads/<the key>.pem
   ```

   Then delete the `.pem` file.

Then, from inside the factory:

```bash
scripts/factory protect --release-app <App ID>
```

It creates (or updates) two rulesets. On `main`, changes go only through a pull request, with no force pushes or deletion. On `v*` tags, only that app may create, move or delete them; the release workflow mints a short-lived token from it for release-please and the tag push. Without `--release-app` the tag ruleset has no bypass at all and releases fail. There is no admin bypass, because local agent sessions run with your login. Never add the factory to `FACTORY_GITHUB_TOKEN`'s repositories, and never give it the `factory` topic.

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

The job also needs the permissions listed in step 6 of the 0.1 → 0.2 entry in [MIGRATION.md](../MIGRATION.md), because the stub's ceiling can't exceed its caller's.

Then list the consumers under `## Consumers` in the library's `FACTORY.md`. Each consumer's `dependency-bump` stage bumps the pin for a non-breaking release, or opens an issue for a human when the release notes contain `BREAKING CHANGE`.
