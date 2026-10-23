# Shared Terragrunt config for every repository the factory is installed in.
# Each child directory (live/<repo>/terragrunt.hcl) includes this file and
# overrides inputs as needed. See docs/setup.md.
#
# Credentials come from the environment and are never committed:
#   GITHUB_TOKEN             admin token for the provider (e.g. `export GITHUB_TOKEN=$(gh auth token)`)
#   FACTORY_GITHUB_TOKEN     fine-grained token the workflows use (docs/setup.md)
#   CLAUDE_CODE_OAUTH_TOKEN  from `claude setup-token`; or ANTHROPIC_API_KEY
# A secret whose variable is unset is left unmanaged, so applying without it
# doesn't remove the secret.
#
# State is local under live/.state/ (gitignored). It contains the secret values
# in plain text, so keep it on this machine, or move to an encrypted remote backend.

locals {
  owner        = "spdolan"
  secret_names = [for n in ["FACTORY_GITHUB_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"] : n if get_env(n, "") != ""]
}

remote_state {
  backend = "local"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    path = "${get_parent_terragrunt_dir()}/.state/${path_relative_to_include()}/terraform.tfstate"
  }
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<-EOF
    provider "github" {
      owner = "${local.owner}"
    }
  EOF
}

terraform {
  source = "${get_parent_terragrunt_dir()}/../modules/factory-repo"
}

inputs = {
  secret_names = local.secret_names
  secret_values = {
    for n in local.secret_names : n => get_env(n, "")
  }

  # Cheapest defaults: Haiku where the risk is low, Sonnet where judgment
  # matters, Opus only for invariant-risk work. Medium effort throughout.
  variables = {
    FACTORY_AUTONOMY              = "standard"
    FACTORY_MODEL_TRIAGE          = "claude-haiku-5-5"
    FACTORY_MODEL_IMPLEMENT_AGENT = "claude-haiku-5-5"
    FACTORY_MODEL_IMPLEMENT       = "claude-sonnet-5-5"
    FACTORY_MODEL_REVIEW_SMALL    = "claude-haiku-5-5"
    FACTORY_MODEL_REVIEW          = "claude-sonnet-5-5"
    FACTORY_MODEL_SPEC            = "claude-sonnet-5-5"
    FACTORY_MODEL_RISK            = "claude-opus-5-5"
    FACTORY_MODEL_BUMP            = "claude-haiku-5-5"
    FACTORY_EFFORT_TRIAGE         = "medium"
    FACTORY_EFFORT_IMPLEMENT      = "medium"
    FACTORY_EFFORT_REVIEW         = "medium"
    FACTORY_REVIEW_SMALL_LINES    = "400"
  }

  labels = {
    "ready-to-implement"        = { color = "0E8A16", description = "Factory: an agent may implement this now" }
    "ready-to-spec"             = { color = "1D76DB", description = "Factory: needs PRODUCT.md and TECH.md first" }
    "needs-info"                = { color = "FBCA04", description = "Factory: blocked on questions in the triage comment" }
    "wait-to-implement"         = { color = "C5DEF5", description = "Factory: doesn't fit the vision or an open bet yet" }
    "spec-ready-for-review"     = { color = "5319E7", description = "Factory: specs PR is ready for a human" }
    "invariant-risk"            = { color = "B60205", description = "Factory: touches protected paths; Opus and human review" }
    "factory:agent"             = { color = "0E8A16", description = "Factory: small and low risk; agents advance it" }
    "factory:awaiting-approval" = { color = "FBCA04", description = "Factory: a human must approve the next stage" }
    "factory:approved"          = { color = "0E8A16", description = "Factory: human approval to start the next stage" }
    "factory:local"             = { color = "006B75", description = "Factory: run the next stage as a session on the self-hosted machine" }
    "factory:proposed"          = { color = "EDEDED", description = "Factory: drafted by the bet skill" }
    "maintenance"               = { color = "EDEDED", description = "Bugs, CI, dependencies, security: needs no bet" }
  }
}
