# Local sessions on a self-hosted runner

`factory-local.yml` runs the implement or spec stage as a background Claude Code session on your own machine, instead of inside a GitHub-hosted job. The Actions job only dispatches the work. It updates a clone, starts `claude --bg --worktree gh-<n>`, posts the session ID on the issue, and exits. The session keeps running with the machine owner's logins from the login keychain: the Claude CLI's subscription login and `gh`'s keyring token. It opens the PR itself.

Use it for work that needs what only this machine has: local databases, private data, gstack's browser, or macOS. You can watch it and step in with `claude agents` or `claude attach <id>`.

Start a session by adding `factory:local` to an issue that has `ready-to-implement` or `ready-to-spec`, or by running the workflow with an issue number. Model and effort follow the same tiers as the hosted workflows.

## Setup, once per machine

1. **Update the CLI.** Background sessions need a recent version (2.1.300 or later has `--bg` and `--worktree`):
   ```bash
   brew upgrade --cask claude-code
   ```
2. **Sign the CLI in.** The CLI's login is separate from the desktop app's. Check that `subscriptionType` shows your plan, not API billing:
   ```bash
   claude auth login && claude auth status
   ```
   Unset `ANTHROPIC_API_KEY` in the runner's environment. The workflow also unsets it before starting the session.

## Setup, once per repository

1. **Register a runner** with the label `factory`. GitHub publishes a checksum for each release, so verify the download against it:
   ```bash
   mkdir -p ~/actions-runner/<repo> && cd ~/actions-runner/<repo>
   ```
   Download `actions-runner-osx-arm64-<version>.tar.gz` from https://github.com/actions/runner/releases, verify it, extract it, then:
   ```bash
   ./config.sh --unattended --url https://github.com/<owner>/<repo> --token "$(gh api -X POST repos/<owner>/<repo>/actions/runners/registration-token -q .token)" --name "$(scutil --get LocalHostName)-factory" --labels factory --work _work
   ```
   ```bash
   ./svc.sh install && ./svc.sh start
   ```
   The service is a LaunchAgent, so it runs while you're logged in. Personal-account repositories each need their own runner registration.

   Turn off `SessionCreate`. The runner's LaunchAgent is installed with `SessionCreate = true`, which runs it in a separate security session without your login keychain, where the Claude CLI keeps its login (and `gh` its token):
   ```bash
   ./svc.sh stop && plutil -replace SessionCreate -bool false ~/Library/LaunchAgents/actions.runner.<owner>-<repo>.*.plist && ./svc.sh start
   ```
   Reinstalling the service (`./svc.sh install`) turns it back on.
2. **Clone the repository for sessions** over HTTPS, using `gh` for credentials. A LaunchAgent can't always reach your ssh-agent, and the job's token expires when the job ends.
   ```bash
   mkdir -p ~/factory-work && cd ~/factory-work && git -c credential.helper='!gh auth git-credential' clone https://github.com/<owner>/<repo>.git
   ```
   ```bash
   cd ~/factory-work/<repo> && git config credential.helper '!gh auth git-credential'
   ```
   Set `FACTORY_WORK_DIR` (a repository variable) to use a different parent folder.
3. **Trust the clone.** Background sessions refuse untrusted folders. Run `claude` in `~/factory-work/<repo>`, choose **Yes, I trust this folder**, and exit.

## Things to know

- **Worktrees stay** under `<clone>/.claude/worktrees/gh-<n>` after a session ends, so you can inspect them. Remove one with `git worktree remove --force --force <path>` once its PR has merged.
- **The session must outlive the job.** The runner kills processes tagged with the job's `RUNNER_TRACKING_ID` when the job ends, including Claude's background service. The workflow clears that variable before `claude --bg`.
- **Pass the prompt first.** `--allowedTools` and `--disallowedTools` take lists and swallow any argument after them, so the workflow passes the prompt as the first argument.
- **Sessions use the background service's environment.** Claude runs background sessions in one service per user. The service keeps the environment it had when it first started, and every later session gets that environment, not the environment of the command that asked for it. (Tested: a variable set on the `claude --bg` call reached the session only when that call also started the service.) So the job can't reliably hand a session a token. The workflow passes none, and it unsets `GH_TOKEN`, `GITHUB_TOKEN` and `ANTHROPIC_API_KEY` in case its call starts the service. Sessions use your keyring logins.
- **For narrower credentials, use a dedicated user.** Your `gh` keyring token reaches all your repositories. Run the runner as a separate macOS user whose `gh` is logged in with a token limited to the factory's repositories, so its sessions only ever have that.
- **Setting sources:** sessions load project and local settings only (`--setting-sources project,local`), not your user-level settings, skills or CLAUDE.md, so they follow the repository's instructions. That saved about 4k tokens per session in a test (39.6k against 43.7k on the first turn). Set the repository variable `FACTORY_LOCAL_SETTING_SOURCES` to `user,project,local` where sessions need user-level tools, such as gstack's `/browse` for UI checks.
- **The agent runs as you**, with access to everything your user can reach, including your keyring `gh` login if it goes looking. The workflow's deny list blocks force-pushes, pushes to `main`, creating, pushing or deleting tags, merges, `gh api`, `gh workflow`, `curl`/`wget` and `sudo`. Tags matter because your login can reach any repository whose release tags other repositories run, the factory included. Treat it as a guard against mistakes, not a security boundary: prefix rules can be bypassed with `bash -c` or a script.
- **Protect `main` on the server.** A ruleset that requires a pull request and blocks force-pushes, with no bypass list, is the only thing that stops a session (or a prompt injected through issue text) from pushing to `main` with your credentials. Rulesets on private repositories need GitHub Pro or higher. `infra/` manages them when `protect_default_branch` is on.
- **Only collaborators' text reaches the session.** In a private repository only collaborators can open issues, and only a human adds `factory:local`. Keep it that way: don't run local sessions on issues from people you don't trust.
- For stronger isolation, use a dedicated machine or macOS user with its own Claude login and a GitHub token limited to its repositories.
- **The machine must be awake.** A queued job waits until the runner is back online.
- **Cost:** self-hosted runner minutes are free on GitHub (the announced platform fee was postponed), and the session draws on your subscription's usage limits.
