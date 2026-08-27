---
status: accepted
date: 2026-04-21
decision-makers: Maximilian Zettler
---

# Keep this repository library-first; develop the GUI in a separate repository

## Context and Problem Statement

The project started as one repository containing everything: the protocol
analysis, the control library, a CLI, and a PySide6 GUI with faders, meters,
and mute buttons (`cf6c68b`). As the protocol work matured, the GUI's needs
diverged: it wanted its own release cadence, a Qt-specific architecture
(worker threads, theming, panels), a GUI test stack, and eventually AppImage
packaging — none of which belongs in a protocol library that other frontends
should be able to depend on cheaply.

## Decision Drivers

* A GUI dependency (PySide6, ~100 MB) is far too heavy for consumers who only
  want the protocol.
* Protocol releases and GUI releases have different rhythms and different
  definitions of "done".
* A clean library boundary forces the protocol API to be complete rather than
  letting the GUI reach into internals.

## Considered Options

* Split the GUI into its own repository; reposition this one as a library
* Keep the monorepo with the GUI behind an optional dependency
* Keep the monorepo and make the GUI the primary product

## Decision Outcome

Chosen option: **split**. `2cba9bb` removed `minidsp/gui/`, the `gui` extra,
and the `minidsp gui` subcommand; the GUI now lives at
[miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt) and consumes
this project as a versioned dependency (its ADR-0001/0003 record that side of
the contract). The README was rewritten library-first (`8bf0178`): it leads
with the `DSPmini` API, and the CLI is explicitly a convenience whose commands
are added on demand.

This reverses the original bundled-GUI position — the optional-dependency
arrangement was tried first (`gui` extra in `pyproject.toml`) and abandoned.

### Consequences

* Good, because `uv sync` here installs two small pure-Python dependencies,
  not a Qt stack.
* Good, because the split immediately surfaced missing library API (activate
  ACK validation `f3984a6`, unready-device handling `74eb3dc` were both found
  by the Qt frontend's poll loop).
* Good, because releases became meaningful: the Qt project pins published
  wheels of this library.
* Bad, because cross-cutting changes now need two commits, two releases, and
  a version bump dance.
* Neutral, because the GUI's device-facing bug reports arrive as issues
  against the library contract — which is where they belong.

### Confirmation

`pyproject.toml` has no GUI dependency or extra; the README's first paragraph
states the library-first positioning and links the Qt project.

## Pros and Cons of the Options

### Separate repositories

* Good, because each project has one job and one dependency profile
* Good, because the library API is exercised by a real external consumer
* Bad, because coordinated changes span repositories

### Monorepo with optional GUI extra

* Good, because one clone contains everything
* Bad, because the GUI still couples release cadence and test infrastructure
* Bad, because "optional" extras leak — docs, CI, and issues all straddle both

## More Information

* `2cba9bb` — GUI removal; `60aae0b` — docs repointed; `8bf0178` — README
  repositioned library-first; `5473496` — the earlier interim position ("GUI
  is proof of concept, protocol is complete").
