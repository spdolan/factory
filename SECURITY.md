# Security

The workflows in this repository run with the secrets of every repository that installs them, so a problem here matters more than its size suggests.

**Report privately.** Use GitHub's private vulnerability reporting on this repository (Security → Report a vulnerability). Don't open a public issue for anything that could be used against a repository running the factory: prompt injection paths, a way for an agent to reach a token it shouldn't, a workflow that writes where it shouldn't.

**In scope:** the workflows in `templates/github/workflows/` and `.github/workflows/`, the scripts in `scripts/`, and the skills' instructions where they decide what an agent may write.

**Out of scope:** `anthropics/claude-code-action` and Claude Code themselves (report those to Anthropic), and GitHub Actions.

There is no bug bounty. Reports get a reply within a couple of weeks and a fix release when confirmed.
