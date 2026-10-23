# judicial_outcomes: sensitive data and published findings. Careful triage
# (Haiku at high effort, as for plinth), and agents only take small issues on
# their own. List the human-only areas in FACTORY.md.
include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

inputs = {
  repository = "judicial_outcomes"
  variables = {
    FACTORY_AUTONOMY      = "small"
    FACTORY_MODEL_TRIAGE  = "claude-haiku-5-5"
    FACTORY_EFFORT_TRIAGE = "high"
  }
}
