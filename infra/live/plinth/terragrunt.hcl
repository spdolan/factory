# plinth: the shared library. Invariants (replay identity, the proto schema)
# need sharper triage, and agents only take small issues on their own.
include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

inputs = {
  repository = "plinth"
  variables = {
    FACTORY_AUTONOMY     = "small"
    FACTORY_MODEL_TRIAGE = "claude-sonnet-5-5"
  }
}
