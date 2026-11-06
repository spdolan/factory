## Output contract for this run

You have no write access to GitHub in this run. Follow the skill, but where it says to comment, label, push, open a PR, or report on the issue, do this instead:

- Commit your work on a local branch, using the branch name the skill gives. Do not push. Do not open a PR, comment, or change labels. A separate job does those with your result.
- Do not change anything under `.github/workflows/`. A patch that touches it is refused.
- End your final response with one JSON object and nothing after it: no prose, no code fences. It must match this shape:

```json
{
  "outcome": "pr | none | blocked",
  "branch": "the branch you committed on, or an empty string",
  "pr_title": "Conventional Commits title for the PR, or an empty string",
  "pr_body": "Markdown body for the PR, or an empty string",
  "draft": false,
  "comment": "Markdown for the issue",
  "state": null
}
```

Fields:

- `outcome`:
  - `pr`: there are commits on `branch`. The job pushes the branch and opens a PR with `pr_title` and `pr_body` (as a draft if `draft` is true), then posts `comment` on the issue with the PR URL appended.
  - `none`: there is nothing to change (for example, no durable learning, or the dependency is already at that version). `comment` is your report.
  - `blocked`: you stopped because information is missing or something blocks the work. Make no commits you want kept. `comment` says exactly what is missing. It is posted as written.
- `branch`: the local branch with your commits. Empty unless `outcome` is `pr`.
- `pr_title`, `pr_body`: what the skill says the PR title and body should contain. Empty unless `outcome` is `pr`.
- `draft`: true when the skill says to open the PR as a draft.
- `comment`: the skill's final report on the issue, in Markdown, with real line breaks. Do not add the PR URL; it is appended for you. Do not include secrets, environment variables or raw command output. Include {{run_url}} as the follow-along link. The "started" and progress comments the skill describes are skipped in this run.
- `state`: used only by the spec stage. Use `spec-ready-for-review` when neither spec has material open questions, `wait-to-implement` when the novelty gate decided `adopt` or `drop`, and otherwise null. Every other stage sets null.

Write all five text fields even when empty. Give real line breaks, not `\n` escapes.
