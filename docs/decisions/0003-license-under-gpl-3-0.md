---
status: accepted
date: 2026-04-03
decision-makers: Maximilian Zettler
---

# License under GPL-3.0 with an interoperability notice

## Context and Problem Statement

The repository publishes a reverse-engineered protocol specification, a control
library, and analysis tooling for a commercial device. It needed a license
before publication on GitHub, and — because the content is derived from
observing a vendor's USB traffic — a clear statement of the project's legal
footing.

## Decision Drivers

* The closest related project, dsp-408-ui (same Musicrown protocol), is
  GPL-licensed; license compatibility keeps cross-pollination frictionless.
* The broader Linux audio / HID reverse-engineering ecosystem is
  copyleft-leaning.
* Improvements to the protocol knowledge should flow back rather than being
  captured in proprietary forks.

## Considered Options

* GPL-3.0
* MIT / BSD permissive licensing
* LGPL

## Decision Outcome

Chosen option: **GPL-3.0** (`9609a84`), matching dsp-408-ui and the ecosystem.
The README adds two notices: the project is not affiliated with Musicrown,
the t.racks, or Thomann, and the protocol was reverse-engineered for
interoperability purposes under applicable law.

### Consequences

* Good, because code and findings can be exchanged with dsp-408-ui without
  license friction.
* Good, because derived tools must publish their protocol improvements.
* Neutral, because downstream consumers must be GPL-compatible — the Qt GUI
  (GPLv3, see its ADR-0004) already is.
* Bad, because permissive-licensed projects cannot vendor the library.

### Confirmation

`LICENSE` at the repository root; the notice paragraph closes the README.

## More Information

* `9609a84` — license commit, naming the dsp-408-ui precedent.
