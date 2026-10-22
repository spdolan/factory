# novelty_audit: skills and a small CLI. Defaults throughout (Haiku triage).
include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

inputs = {
  repository = "novelty_audit"
}
