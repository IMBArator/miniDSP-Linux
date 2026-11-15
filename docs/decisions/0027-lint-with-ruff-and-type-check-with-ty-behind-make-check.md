---
status: accepted
date: 2026-11-15
decision-makers: Maximilian Zettler
---

# Lint with ruff and type-check with ty behind make check

## Context and Problem Statement

The project had a test suite but no linter and no type checker. Conventions
such as the future import, import order and the handling of `Optional`
results were kept by review only, and the type annotations were never
checked. The first run of a linter and a type checker found unused imports,
`Optional` values used without a check (in the library and in the tests), and
imports below module-level code.

## Decision Drivers

* One command beside `make test` that must pass before every commit.
* Fast enough to run on every commit, configured in `pyproject.toml`, with no
  extra configuration files.
* The tests are checked like the packages.
* Conventions the project already follows are enforced by a tool instead of
  by memory.

## Considered Options

* ruff for linting and ty for type checking
* ruff for linting and mypy for type checking
* no linter or type checker (keep the status quo)

## Decision Outcome

Chosen option: **ruff and ty**, because both are fast, configured in
`pyproject.toml`, and installed through the `dev` extra like pytest
([ADR-0020](0020-manage-the-project-with-uv-and-hatchling.md)).

* ruff runs pyflakes, pycodestyle, isort, pyupgrade and bugbear (`E`, `F`,
  `W`, `I`, `UP`, `B`); `E501` is ignored because formatting is not enforced.
  `required-imports` makes ruff require `from __future__ import annotations`
  in every module that contains code.
* ty takes the Python version from `requires-python`.
* `make check` runs `make check-ruff` and `make check-ty`, both over
  `minidsp`, `dspanalyze` and `tests`; `make fix-ruff` applies ruff's safe
  automatic fixes.
* Findings are fixed, not suppressed: an `Optional` is narrowed with an
  `assert`, and neither ignore comments nor checker configuration hide a
  finding. The Windows-only code (`ctypes.WinDLL`, `windll`,
  `get_last_error`, `import hid`) produces ty findings on Linux; they stay
  visible until they are fixed and verified on Windows.

### Consequences

* Good, because unused imports, unchecked `Optional` results and import-order
  drift are caught before a commit instead of in review.
* Good, because the future-import convention is enforced by ruff.
* Neutral, because ty is pre-1.0 and its findings can change between
  versions; `uv.lock` pins the exact version, and a ty upgrade is a deliberate
  change.
* Bad, because `make check` fails on Linux until the Windows-only findings are
  fixed on Windows; until then each commit notes the known findings in its
  body.

### Confirmation

The `check`, `check-ruff`, `check-ty` and `fix-ruff` targets in the
`Makefile`, `[tool.ruff]` in `pyproject.toml`, and ruff and ty in the `dev`
extra. `make test` and `make check` must both pass before a commit.

## Pros and Cons of the Options

### ruff and ty

* Good, because both run in well under a second on this code base.
* Good, because ruff's isort rule can require the future import.
* Neutral, because ty is young; its rule set may still move.

### ruff and mypy

* Good, because mypy is mature and its behaviour is stable.
* Bad, because it is slower and needs its own configuration and stub
  packages.

### No linter or type checker

* Good, because it costs nothing now.
* Bad, because conventions drift and `Optional` misuse stays undetected until
  it fails at runtime.

## More Information

* `7e537ab`, `6ecbd26`, `953c181`, `e23f5a6` — the cleanups that made ruff
  pass and reduced ty to the Windows-only findings; the targets and the
  configuration land in the commit that adds this record.
* [ADR-0020](0020-manage-the-project-with-uv-and-hatchling.md) noted that
  this repository had not adopted ruff; this record does.
