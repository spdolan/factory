#!/usr/bin/env bash
# Review inputs, built from the trusted base checkout before the agent runs (0.1's
# "Prepare review artifacts" step). Writes the files the prompt names into the working
# directory and copies them to $FACTORY_INPUTS for the apply job.
# Env: GH_TOKEN, REPO, ITEM (the PR), BASE_SHA, HEAD_SHA, FACTORY_INPUTS.
set -euo pipefail
scripts=.claude/skills/review-pr/scripts

gh api "repos/$REPO/pulls/$ITEM" > pr_meta.json
test "$(jq -r '.base.sha' pr_meta.json)" = "$BASE_SHA"
test "$(jq -r '.head.sha' pr_meta.json)" = "$HEAD_SHA"
gh api -H "Accept: application/vnd.github.v3.diff" "repos/$REPO/pulls/$ITEM" > raw_diff.txt
python3 "$scripts/annotate_diff.py" --input raw_diff.txt --output pr_diff.txt
gh api --paginate --slurp "repos/$REPO/pulls/$ITEM/reviews?per_page=100" | jq '[.[][]]' > reviews.json
gh api --paginate --slurp "repos/$REPO/pulls/$ITEM/comments?per_page=100" | jq '[.[][]]' > review_comments.json

previous_head="$(python3 "$scripts/build_review_context.py" select reviews.json)"
delta_arg=()
if [ -n "$previous_head" ] && gh api -H "Accept: application/vnd.github.v3.diff" \
  "repos/$REPO/compare/$previous_head...$HEAD_SHA" > raw_followup_diff.txt; then
  delta_arg=(--delta raw_followup_diff.txt)
fi
python3 "$scripts/build_review_context.py" context reviews.json review_comments.json \
  "$HEAD_SHA" followup_context.txt "${delta_arg[@]}"

python3 - <<'PY'
import json, os
from pathlib import Path
meta = json.loads(Path("pr_meta.json").read_text(encoding="utf-8"))
body = (meta.get("body") or "").strip() or "No description provided."
Path("pr_description.txt").write_text(
    f"# Pull Request #{os.environ['ITEM']}\n\n"
    f"- Title: {meta.get('title') or ''}\n"
    f"- Base branch: {(meta.get('base') or {}).get('ref') or ''}\n"
    f"- Head branch: {(meta.get('head') or {}).get('ref') or ''}\n"
    f"- Author: {((meta.get('user') or {}).get('login') or 'unknown')}\n"
    f"- URL: {meta.get('html_url') or ''}\n\n## Body\n\n{body}\n", encoding="utf-8")
PY

python3 "$scripts/resolve_spec_context.py" --repo "$REPO" --pr "$ITEM" \
  --workspace "$GITHUB_WORKSPACE" --output spec_context.md || true
[ -s spec_context.md ] || printf 'No approved or repository spec context was found for this PR.\n' > spec_context.md

mkdir -p "$FACTORY_INPUTS"
cp pr_diff.txt pr_description.txt spec_context.md followup_context.txt "$FACTORY_INPUTS/"
rm -f review.json # never trust a review.json that was there before the agent
wc -l raw_diff.txt pr_diff.txt pr_description.txt spec_context.md followup_context.txt
