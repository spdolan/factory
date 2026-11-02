# Architecture at a glance

Status: target architecture for 0.2, as proposed in [rollout.md](rollout.md) and [pipeline.md](pipeline.md). Today (0.1) the factory is still copied into each repository by `scripts/install-factory.sh`.

## Components

Each repository keeps a thin stub and its own settings. Everything else runs from the factory, pinned to the release line the stub calls. The factory names no repository. The ops repository holds the list of repositories and the infra applied to them.

```mermaid
flowchart LR
  subgraph F["factory (public, names no repository)"]
    direction TB
    REL["Releases<br/>v0.2.3, line tag v0.2<br/>test repository: main"]
    STAGE["stage.yml<br/>plan → agent → apply"]
    DEF["pipeline.yaml · features.yaml<br/>skills · prompt templates · prepare"]
    MOD["infra/modules/factory-repo"]
  end

  subgraph C["consuming repository"]
    direction TB
    STUB["Stub workflow<br/>triggers · permission ceiling<br/>secrets by name · uses …@v0.2"]
    RCFG[".github/factory/config.yml<br/>tiers · autonomy · runtime<br/>flag opt-outs · updates"]
    OWN["FACTORY.md · review-pr-local<br/>setup.sh · its own skills"]
    VARS["Repository variables<br/>kill switch"]
  end

  subgraph O["ops repository (private)"]
    LIVE["live/REPO/terragrunt.hcl"]
  end

  RUN["Runtime<br/>GitHub-hosted runner<br/>or self-hosted local session"]
  CLAUDE["Claude Code<br/>skill + prompt + tool profile"]
  GH["GitHub<br/>issues · labels · PRs · reviews"]

  STUB -->|"calls at its version"| STAGE
  REL --- STAGE
  STAGE -->|"checks out one commit"| DEF
  STAGE -->|"reads"| RCFG
  STAGE -->|"reads"| OWN
  STAGE -->|"reads"| VARS
  STAGE -->|"agent job, read-only"| RUN
  RUN --> CLAUDE
  STAGE -->|"apply job: the only writes"| GH
  LIVE -->|"module at a release tag"| MOD
  LIVE -->|"secrets · labels · rulesets"| C
  LIVE -->|"rulesets on main and v* tags"| F
```

Dependencies point one way. The consuming repository calls the factory, and the ops repository depends on both. The factory depends on neither, and `scripts/check-references.sh` enforces that in CI.

## How an issue flows

An abstract example: someone opens "Export results as CSV" in a consuming repository. Every box marked *run* is the same three-job stage runner. Only apply jobs write to GitHub.

```mermaid
flowchart TD
  OPEN["Issue opened<br/>e.g. 'Export results as CSV'"] --> P1

  subgraph T["triage run"]
    P1["plan<br/>stage, tier, flags<br/>+ update check"] --> A1["agent, read-only<br/>state · size · risk"] --> W1["apply<br/>set state · comment · route"]
  end

  W1 --> D{"autonomy rules<br/>pipeline.yaml + config.yml"}
  D -->|"needs-info or wait"| STOP["comment, stop"]
  D -->|"small, low risk"| GO["factory:agent<br/>next stage dispatched"]
  D -->|"otherwise"| WAIT["factory:awaiting-approval"]
  WAIT -->|"you add factory:approved"| GO

  GO --> P2
  subgraph B["spec or implement run"]
    P2["plan"] --> A2["agent, no write token<br/>commits locally → patch"] --> W2["apply<br/>rejects workflow-file changes<br/>pushes branch · opens PR"]
  end

  W2 --> P3
  subgraph R["review run"]
    P3["plan"] --> A3["agent writes review.json"] --> W3["apply<br/>validates · posts review"]
  end

  W3 --> MERGE["you merge"]

  P1 -. "newer release line or<br/>undecided flag, no open<br/>update issue" .-> UPD["factory:update issue"]
  UPD --> P4
  subgraph U["update run, on the current version"]
    P4["plan"] --> A4["agent<br/>config.yml and FACTORY.md<br/>per MIGRATION.md"] --> W4["apply<br/>renders new stubs · opens PR"]
  end
  W4 --> MERGE
```

A spec run ends at a specs PR. You merge it and add `ready-to-implement`, which starts the implement run. Flags decide which steps exist for a repository, for example whether medium `ready-to-spec` issues may advance without approval. The update check runs inside whatever run happens next, so an idle repository costs nothing.
