#!/usr/bin/env bash
# Collect the review-feedback corpus before the agent runs. Writes feedback_corpus.json
# and copies it to $FACTORY_INPUTS. When there's nothing actionable, writes
# $FACTORY_INPUTS/skip-agent so the job skips the agent (0.1 behavior).
# Env: GH_TOKEN, REPO, PARAM_SINCE_HOURS, FACTORY_INPUTS.
set -euo pipefail
python3 .claude/skills/improve-review-pr/scripts/collect_review_feedback.py \
  --repo "$REPO" --since-hours "${PARAM_SINCE_HOURS:-168}" --output feedback_corpus.json
mkdir -p "$FACTORY_INPUTS"
cp feedback_corpus.json "$FACTORY_INPUTS/"
jq -r '.summary | "PRs inspected: \(.prs_inspected // 0); validated=\(.validated // 0), corrected=\(.corrected // 0), refined=\(.refined // 0), ambiguous=\(.ambiguous // 0)"' feedback_corpus.json
if [ "$(jq -r '.summary | (.validated // 0) + (.corrected // 0) + (.refined // 0)' feedback_corpus.json)" = 0 ]; then
  echo "No validated, corrected or refined feedback in the window; skipping the agent."
  touch "$FACTORY_INPUTS/skip-agent"
fi
