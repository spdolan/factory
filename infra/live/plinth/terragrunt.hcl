# plinth: the shared library. Invariants (replay identity, the proto schema)
# need careful triage, and agents only take small issues on their own. Triage
# runs on Haiku at high effort: in a 2026-10-22 comparison on four plinth cases
# it matched Sonnet's safety calls, read the hash case most sharply, and cost
# about a tenth as much.
include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

inputs = {
  repository = "plinth"
  variables = {
    FACTORY_AUTONOMY      = "small"
    FACTORY_MODEL_TRIAGE  = "claude-haiku-5-5"
    FACTORY_EFFORT_TRIAGE = "high"
  }
}
