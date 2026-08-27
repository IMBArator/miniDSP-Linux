---
status: accepted
date: 2026-04-15
decision-makers: Maximilian Zettler
---

# Manage the project with uv and Hatchling, and commit the lockfile

## Context and Problem Statement

The project started on setuptools with plain `pip install -e`. As it grew two
packages, optional dependency groups, TOML package resources, and a release
pipeline, environment management needed to be fast, reproducible, and shared
with the sibling Qt project, which was standardising on the same stack.

## Decision Drivers

* Reproducible environments for a project whose tests assert byte-exact
  protocol behaviour.
* One command (`uv sync`) for contributors, with extras (`dev`, `docs`)
  opt-in.
* Consistency with miniDSP-Linux-qt (its ADR-0026), so working across both
  repos feels identical.

## Considered Options

* uv for environments/locking + Hatchling as build backend
* Stay on setuptools + pip + venv
* Poetry / PDM

## Decision Outcome

Chosen option: **uv + Hatchling** (`5d8d931`): build backend switched to
`hatchling.build`, uv manages `.venv` and `uv.lock`, README and Makefile use
`uv run`/`uv sync` throughout. Notably, `uv.lock` had been added to
`.gitignore` a week earlier (`b2311bf`) — that position was reversed and the
lockfile committed, since a protocol library wants deterministic dev
environments more than it fears lockfile churn. Release tooling keeps the
lock self-consistent: `make version` runs `uv lock` and includes it in the
release commit (`c1c50b0`, `9a9fc9b`).

### Consequences

* Good, because `uv sync --extra dev` reproduces the tested environment
  exactly, on any machine.
* Good, because docs and release tooling could safely assume uv
  ([ADR-0022](0022-publish-docs-as-an-mkdocs-site-that-transcludes-sources-in-place.md),
  [ADR-0023](0023-write-release-automation-in-plain-bash-against-the-github-api.md)
  both shell out to it).
* Good, because Hatchling's default wheel layout handles the two packages and
  their TOML resources without MANIFEST gymnastics.
* Neutral, because uv is a hard tool prerequisite for contributors; the
  README states it up front.
* Bad, because lockfile bumps show up in release diffs — accepted noise for
  determinism.

### Confirmation

`pyproject.toml` declares the Hatchling backend; `uv.lock` is tracked;
Makefile targets invoke `uv run`.

## More Information

* `5d8d931` — migration; `b2311bf` — the reversed gitignore decision;
  `c1c50b0` — lockfile discipline in releases; miniDSP-Linux-qt ADR-0026 —
  the sibling decision (which additionally adopts ruff; this repo has not).
