# groundwork: the app with a viewer, so UI verification is on. Haiku triages.
include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

inputs = {
  repository = "groundwork"
  variables = {
    FACTORY_VERIFY = "true"
  }
}
