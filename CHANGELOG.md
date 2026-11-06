# Changelog

## [0.2.0](https://github.com/spdolan/factory/compare/v0.1.0...v0.2.0) (2026-11-06)


### ⚠ BREAKING CHANGES

* **pipeline:** reusable workflows and the configuration-driven stage runner ([#19](https://github.com/spdolan/factory/issues/19))

### Features

* **pipeline:** reusable workflows and the configuration-driven stage runner ([#19](https://github.com/spdolan/factory/issues/19)) ([65c114d](https://github.com/spdolan/factory/commit/65c114dd210f352d6554fc7b10411b21f771e7e0))


### Bug Fixes

* **apply:** open the PR with GITHUB_TOKEN when FACTORY_GITHUB_TOKEN can't, and report failures ([#22](https://github.com/spdolan/factory/issues/22)) ([756f86b](https://github.com/spdolan/factory/commit/756f86b9fed0535b48bc22631073a6d5492b804c))
* **materialize:** copy the pinned skills without running fetched code ([#20](https://github.com/spdolan/factory/issues/20)) ([76f5a32](https://github.com/spdolan/factory/commit/76f5a32d2b75113b831d261cf678197f14fbd4f6))
* **stages:** have patch agents report the PR and state as done ([#23](https://github.com/spdolan/factory/issues/23)) ([6cabd0e](https://github.com/spdolan/factory/commit/6cabd0e02dd9d4b5aaa917b2adba51dda52a6659))
* **tracker:** don't ask gh issue view for authorAssociation ([#21](https://github.com/spdolan/factory/issues/21)) ([7f4b728](https://github.com/spdolan/factory/commit/7f4b7286518ba02b548dfaf26b2d4c79936f73e1))
* **workflows:** run agents on the Bun that setup.sh installs ([#17](https://github.com/spdolan/factory/issues/17)) ([246acde](https://github.com/spdolan/factory/commit/246acde3fb425a24fb053a103635ced7e3d238d2))

## 0.1.0 (2026-11-02)


### Features

* cloud factory skills and workflows on claude-code-action ([b0aeb4d](https://github.com/spdolan/factory/commit/b0aeb4dc0ce8b7ee0b879a6f80d2a405f3b73205))
* **infra:** triage plinth and judicial_outcomes on Haiku at high effort ([#9](https://github.com/spdolan/factory/issues/9)) ([04bed76](https://github.com/spdolan/factory/commit/04bed761de58e1840db42ef5fb395c8f454baa8c))
* local sessions on a self-hosted runner (factory-local.yml) ([#3](https://github.com/spdolan/factory/issues/3)) ([207bdf7](https://github.com/spdolan/factory/commit/207bdf7868c38dbc6be5934c53551153436265da))
* **release:** a GitHub App you own moves release tags, not the Actions app ([#15](https://github.com/spdolan/factory/issues/15)) ([ffee969](https://github.com/spdolan/factory/commit/ffee969deda7733ba0ea8c7dd0f4eab693ee0ee1))
* self-declared consumers, a factory CLI, release-please and the 0.2 design ([#12](https://github.com/spdolan/factory/issues/12)) ([a00da7d](https://github.com/spdolan/factory/commit/a00da7dcca49ce0d2aac62e7db3baee713293efb))


### Bug Fixes

* **ci:** skip the generated CHANGELOG.md in the no-references check ([#14](https://github.com/spdolan/factory/issues/14)) ([3dd87ca](https://github.com/spdolan/factory/commit/3dd87ca4e0d345c7baca25b63d5895f236af0878))
* **cli:** protect takes the release app's App ID ([#16](https://github.com/spdolan/factory/issues/16)) ([072752d](https://github.com/spdolan/factory/commit/072752d04485f0a5968cd73117bb16851a300ea3))
* **infra:** set Actions secrets with value, not the deprecated plaintext_value ([873287c](https://github.com/spdolan/factory/commit/873287c4fc25211bb01134d4c17a85adb8dc44d2))
* **infra:** set Actions secrets with value, not the deprecated plaintext_value ([9c27ea5](https://github.com/spdolan/factory/commit/9c27ea52356f510e82c1c6d3db438484291c210d))
* **local:** fetch the clone with the owner's gh login, not the job token ([#5](https://github.com/spdolan/factory/issues/5)) ([202a319](https://github.com/spdolan/factory/commit/202a319dea23ca6e935312568990f48834a18349))
* **local:** keep the job token out of the session step; wording ([#8](https://github.com/spdolan/factory/issues/8)) ([6a4b4fb](https://github.com/spdolan/factory/commit/6a4b4fba1953534d4de15d28183fce2a5602a13a))
* **local:** keep the session alive after the job; use the repo-scoped token ([#6](https://github.com/spdolan/factory/issues/6)) ([58e3694](https://github.com/spdolan/factory/commit/58e3694015239ee6206c406be6fbd1825b5a5467))
* **local:** keyring logins for sessions, project-only settings, always validate ([#7](https://github.com/spdolan/factory/issues/7)) ([af9f982](https://github.com/spdolan/factory/commit/af9f98270eea52baa6a965cbd8cad43bf5798e9f))
* **local:** tighter guardrails for local sessions; optional main ruleset ([#4](https://github.com/spdolan/factory/issues/4)) ([3dea3eb](https://github.com/spdolan/factory/commit/3dea3eb8bdf58ad1ad87c1bd87933ce9d6285f97))
* **triage:** stop double-escaped line breaks in triage comments ([#2](https://github.com/spdolan/factory/issues/2)) ([d3f9d49](https://github.com/spdolan/factory/commit/d3f9d49fc01371ecc48709eeb1630a66066c08ab))
* **triage:** unescape \n only in comments with no real line breaks ([#10](https://github.com/spdolan/factory/issues/10)) ([8deb431](https://github.com/spdolan/factory/commit/8deb431b13a2543f4c4f5fa865b7ba617a399d50))
