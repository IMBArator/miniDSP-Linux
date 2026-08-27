---
status: accepted
date: 2026-05-09
decision-makers: Maximilian Zettler
---

# Bundle factory defaults as a generated TOML package resource in raw protocol form

## Context and Problem Statement

Downstream consumers — the Qt GUI's offline mode and reset-to-default
controls foremost — need the device's factory state (the F00 preset) without a
device attached. Hand-maintaining default constants had already failed in the
GUI (values drifted from the real F00; its ADR-0014 records the fallout).
The question was where authoritative defaults come from and in what form they
travel.

## Decision Drivers

* Defaults must be *extracted from the device*, not transcribed by hand —
  transcription is how the GUI got wrong values.
* Consumers need them before any device I/O, so they must ship inside the
  wheel.
* Regeneration must be mechanical when a firmware revision changes F00.

## Considered Options

* Generate `minidsp/factory_defaults.toml` from an F00-load capture via a
  dedicated `dspanalyze extract-defaults` subcommand; ship it as a package
  resource with a `load_factory_defaults()` loader
* Hardcode defaults as Python constants
* Read defaults from the device at first connect and cache them

## Decision Outcome

Chosen option: **generated TOML resource** (`7d8253e`). `extract-defaults`
stitches the 9 × 50-byte config pages from a preset-load capture into the
450-byte blob, runs the standard `parse_preset_params()`, and additionally
emits the three footer parameters the parser does not expose (test-tone mode,
sine frequency index, delay unit). The values are stored in **raw protocol
form** (raw gain steps, raw frequency indices), and converted for display by
the same canonical helpers as live device data
([ADR-0011](0011-make-minidsp-protocol-the-single-source-of-conversions-and-constants.md)).
`minidsp.defaults.load_factory_defaults()` is the public API.

### Consequences

* Good, because the defaults are evidence-derived: the F00 capture that
  produced them is in `analysis/usb_captures/`, and regeneration is one
  command.
* Good, because raw form means zero conversion ambiguity — the file is
  exactly what the device would report.
* Good, because the Qt GUI's wrong-defaults bug class is closed at the source.
* Neutral, because raw values are unreadable without the helpers; that is the
  point, but it makes the TOML unfriendly to casual eyeballing.
* Bad, because the file is a build artifact committed to the repo; it can
  silently lag a firmware change until someone re-captures F00.

### Confirmation

`tests` load the bundled TOML through `load_factory_defaults()`;
`make`/`dspanalyze extract-defaults` regenerates it reproducibly from the
committed capture.

## More Information

* `7d8253e` — implementation; `e8ce24e`/`20c6105` — the footer test-tone
  fields it exposes; the Qt project's ADR-0014 — the consumer this exists for.
