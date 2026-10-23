# Factory settings for one GitHub repository: Actions secrets, Actions
# variables, labels, and the permission for Actions to open pull requests.

terraform {
  required_version = ">= 1.5"
  required_providers {
    github = {
      source  = "integrations/github"
      version = "6.13.0"
    }
  }
}

variable "repository" {
  description = "Repository name, without the owner."
  type        = string
}

variable "variables" {
  description = "Actions variables (FACTORY_AUTONOMY, FACTORY_MODEL_TRIAGE, ...)."
  type        = map(string)
  default     = {}
}

variable "secret_names" {
  description = "Names of the secrets to set. Kept separate from the values because for_each can't use sensitive keys."
  type        = list(string)
  default     = []
}

variable "secret_values" {
  description = "Secret values by name. Only the names in secret_names are set."
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "labels" {
  description = "Factory labels: name => { color, description }."
  type = map(object({
    color       = string
    description = string
  }))
  default = {}
}

resource "github_actions_variable" "this" {
  for_each      = var.variables
  repository    = var.repository
  variable_name = each.key
  value         = each.value
}

resource "github_actions_secret" "this" {
  for_each    = toset(var.secret_names)
  repository  = var.repository
  secret_name = each.value
  value       = var.secret_values[each.value]
}

resource "github_issue_label" "this" {
  for_each    = var.labels
  repository  = var.repository
  name        = each.key
  color       = each.value.color
  description = each.value.description
}

# Lets workflows using GITHUB_TOKEN open PRs (the improve-review loop, and spec and
# implement runs when FACTORY_GITHUB_TOKEN isn't set).
resource "github_workflow_repository_permissions" "this" {
  repository                       = var.repository
  default_workflow_permissions     = "read"
  can_approve_pull_request_reviews = true
}

variable "protect_default_branch" {
  description = "Require a pull request and block force-pushes and deletion on the default branch, with no bypass. Needs GitHub Pro or higher for private repositories."
  type        = bool
  default     = false
}

# The server-side control that stops any credential, including an agent
# session's, from pushing straight to the default branch.
resource "github_repository_ruleset" "default_branch" {
  count       = var.protect_default_branch ? 1 : 0
  name        = "factory: protect default branch"
  repository  = var.repository
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["~DEFAULT_BRANCH"]
      exclude = []
    }
  }

  rules {
    deletion         = true
    non_fast_forward = true
    pull_request {
      required_approving_review_count = 0
    }
  }
}
