---
status: accepted
date: 2026-05-15
decision-makers: Maximilian Zettler
---

# Drive the changelog from Conventional Commits with git-cliff, prepending to a hand-curatable file

## Context and Problem Statement

With versioned releases starting at v1.0.0, the project needed release notes.
The commit history was already disciplined (conventional-commit style since
early on, codified in `CLAUDE.md`), so the changelog could in principle be
generated — but generated *how* matters: a naive full regeneration destroys
any hand-written content, and raw conventional-commit categories are written
for maintainers, not users.

## Decision Drivers

* Commit messages are the project's richest record; release notes should be
  derived from them, not written twice.
* Milestone releases (v1.0.0) deserve hand-curated prose that must survive
  subsequent releases.
* Users read changelogs; Keep a Changelog's Added/Changed/Fixed vocabulary is
  written for them, unlike `refactor:`/`chore:`.

## Considered Options

* git-cliff with a Keep-a-Changelog mapping, `--unreleased --prepend` per
  release, CHANGELOG.md as the single source for release notes
* git-cliff regenerating CHANGELOG.md wholesale each release
* Hand-written changelog
* GitHub's auto-generated release notes

## Decision Outcome

Chosen option: **git-cliff, prepend-only, CHANGELOG as source of truth**,
reached in stages. `3d74811` introduced `cliff.toml` and `make version`.
`39d565e` mapped commit types to Keep a Changelog categories (feat→Added,
fix→Fixed, refactor/perf→Changed) and dropped non-user-visible types —
then `51ee088` partially reversed that by surfacing `docs` commits as a
Documentation group, since docs corrections *are* user-visible in a project
whose main deliverable is a spec. `cbf0083` switched from regeneration to
`--unreleased --prepend` with a duplicate-section guard, making hand-curated
sections durable. `20e2399` completed the inversion: GitHub Release bodies
are extracted *from* CHANGELOG.md rather than re-rendered by git-cliff, so
curated prose flows to the release verbatim.

Two earlier positions were reversed along the way: wholesale regeneration
(`cbf0083`) and skipping docs commits (`51ee088`).

### Consequences

* Good, because one disciplined commit message becomes changelog entry and
  release notes with no re-writing.
* Good, because hand-curated milestone sections survive forever; the tooling
  refuses to double-generate a version.
* Neutral, because the mapping demands ongoing commit-message discipline —
  a mislabelled type is a mislabelled changelog line.
* Bad, because template/header mismatches between cliff.toml and the existing
  file break `--prepend` in obscure ways (`1dcf6e5` fixed a duplicated
  header caused by a missing blank line).

### Confirmation

`cliff.toml` at the root; `scripts/version.sh` performs the prepend with the
duplicate guard; `scripts/publish.sh` extracts release notes from
CHANGELOG.md; the README's Changelog section states the convention.

## More Information

* `3d74811`, `39d565e`, `cbf0083`, `20e2399`, `51ee088`, `1dcf6e5`;
  miniDSP-Linux-qt ADR-0028 — the sibling adopting the same scheme.
