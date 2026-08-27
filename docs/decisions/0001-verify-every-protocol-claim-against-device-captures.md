---
status: accepted
date: 2026-04-04
decision-makers: Maximilian Zettler
---

# Verify every protocol claim against device captures before documenting or implementing it

## Context and Problem Statement

The USB HID protocol of the t.racks DSP 4x4 Mini is undocumented. Knowledge
about it comes from three sources of very different reliability: live Wireshark
captures of the manufacturer's Windows software, cross-references from the
related dsp-408-ui project, and plausible-looking inference from observed
bytes. Early on, all three were treated as roughly equal — and inference kept
being wrong in small, expensive ways: gate hold/release minimums were misread
from the first drag-step of a fader sweep (`75f36db`), preset indices were
assumed 1-based from the DSP 408 (`5aba93c`), and channel name fields were
assumed 3 bytes wide (`6c2c608`).

The question is what standard of evidence a protocol fact must meet before it
enters `protocol.py`, `protocol_config.toml`, or `analysis/protocol.md`.

## Decision Drivers

* Wrong protocol claims propagate: the spec, the analyzer config, the runtime
  library, and the Qt GUI all consume the same facts.
* Writes go to a real device holding the user's presets; a wrong frame can at
  best corrupt settings and at worst lock or brick the hardware.
* The docs (`protocol.md`) are the project's core deliverable and are consumed
  by third parties; their credibility rests on every claim being reproducible.

## Considered Options

* Require a device capture demonstrating each claim before it is documented as
  verified; mark everything else explicitly as unverified/TBD
* Accept cross-referenced knowledge from dsp-408-ui as verified
* Accept plausible inference from config-blob defaults as verified

## Decision Outcome

Chosen option: **capture-verified or explicitly marked unverified**. The
workflow is: capture the manufacturer software performing one isolated action →
analyze with `dspanalyze` → implement in `protocol.py`/`device.py` with tests
asserting the exact captured bytes → document in `protocol.md` — all in the
same pass. Captures are committed to `analysis/usb_captures/` as `data:`
commits so every claim's evidence is in the repository. Fields that have not
been swept end-to-end are marked TBD in `protocol_config.toml` (as the
compressor fields initially were in `9dd5ac4`).

The working convention (recorded in `CLAUDE.md`) is that protocol docs and
protocol code are never changed without verified results and explicit
confirmation.

### Consequences

* Good, because every entry in the feature table can say "verified against
  real Wireshark captures" and mean it.
* Good, because sweep captures repeatedly falsified first guesses (gate
  minimums, preset indexing, name widths) before they shipped.
* Good, because tests lock the verified bytes in place — a regression in an
  encoder fails against the captured frame, not against an opinion.
* Bad, because progress is gated on access to the physical device and the
  Windows editor; nothing can be "quickly assumed" to unblock a feature.
* Neutral, because full-parameter sweeps (min→max→min) are tedious to record,
  but they are precisely what caught the wrong minimums.

### Confirmation

`dspanalyze check` runs the protocol assertion framework over captures
([ADR-0009](0009-guard-protocol-knowledge-with-capture-assertions.md));
`tests/test_protocol.py` asserts command builders byte-for-byte against
captured frames; `protocol_config.toml` carries an explicit `verified` flag
per opcode.

## Pros and Cons of the Options

### Capture-verified only

* Good, because the evidence is committed alongside the claim
* Good, because it caught real errors that inference and cross-reference missed
* Bad, because it is slow and requires the hardware on the desk

### Trust dsp-408-ui cross-references

* Good, because it bootstraps quickly from an existing implementation
* Bad, because the devices genuinely differ — see
  [ADR-0005](0005-cross-reference-dsp-408-ui-but-trust-only-on-device-verification.md)

### Trust inference from defaults

* Good, because it needs no new captures
* Bad, because defaults are degenerate (zeros everywhere) and hid, e.g., that
  footer byte 424 stores the delay unit (`f58c0ea`)

## More Information

* `75f36db` — gate minimums corrected by an all-params sweep; `5aba93c` —
  preset indexing corrected against five captures; `6c2c608` — input name
  width corrected; `f58c0ea` — "always zero" footer claim falsified.
* [ADR-0005](0005-cross-reference-dsp-408-ui-but-trust-only-on-device-verification.md),
  [ADR-0009](0009-guard-protocol-knowledge-with-capture-assertions.md)
