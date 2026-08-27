---
status: accepted
date: 2026-05-17
decision-makers: Maximilian Zettler
---

# Write release automation in plain bash against the GitHub API, with defensive preconditions

## Context and Problem Statement

Releasing means bumping the version, regenerating the changelog, tagging,
building wheels, creating a GitHub Release with assets, and deploying the docs
site. Doing that by hand is error-prone; doing it with heavyweight automation
(CI release pipelines, the `gh` CLI) adds dependencies and hides state from
the person releasing — who, in a one-maintainer project, is always at a
terminal with the repo in front of them.

## Decision Drivers

* Releases happen from the maintainer's machine; the tooling should be
  inspectable and runnable there with nothing exotic installed.
* Half-done releases (tag without changelog, release without assets) are the
  real hazard — preconditions matter more than orchestration.
* Owner/repo and notes must derive from the repository itself so forks work
  unchanged.

## Considered Options

* Two bash scripts (`version.sh`, `publish.sh`) using git, uv, curl, and jq
  directly against the GitHub REST API
* The `gh` CLI for the GitHub half
* GitHub Actions release workflow on tag push

## Decision Outcome

Chosen option: **plain bash + curl + jq** (`aa46748`, `e70bfa8`), wrapped as
`make version` / `make build` / `make publish`. `version.sh` refuses shaky
states before touching anything: dirty tree, wrong branch, behind origin,
duplicate tag on origin, version regression — then previews the diff and the
new changelog section before committing. `publish.sh` authenticates with a
PAT in `GITHUB_TOKEN`, derives owner/repo from `git remote get-url origin`,
attaches the matching wheel+sdist, takes release notes from CHANGELOG.md
([ADR-0021](0021-drive-the-changelog-from-conventional-commits-with-git-cliff.md)),
auto-flags prereleases from `-rc/-beta/-alpha` suffixes, and deploys docs via
`mkdocs gh-deploy`. The scripts never shell out to `make`; make targets are a
thin discoverability layer.

### Consequences

* Good, because every step is readable bash a maintainer can audit or run
  line-by-line when something goes sideways.
* Good, because the precondition battery converts classic release accidents
  into refusals with remediation hints.
* Good, because no `gh` CLI, no CI secrets, no third-party actions — the
  dependency surface is curl and jq.
* Neutral, because releases are manual by design; there is no tag-push
  automation to forget about.
* Bad, because raw REST calls carry maintenance risk if GitHub's API
  evolves, and bash error handling remains bash error handling.

### Confirmation

`scripts/version.sh` and `scripts/publish.sh` under version control; the
Makefile documents the four-step flow (`version` → push → `build` →
`publish`).

## More Information

* `aa46748` — publish.sh design notes; `e70bfa8` — version.sh hardening;
  `20e2399` — notes extraction; `c1c50b0` — lockfile inclusion.
