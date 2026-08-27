---
status: accepted
date: 2026-04-15
decision-makers: Maximilian Zettler
---

# Make minidsp.protocol the single source of truth for conversions and constants

## Context and Problem Statement

Value conversions (raw↔dB gain, log frequency, PEQ Q, level→dBu) and display
constants (channel, slope, ratio, filter-type names) had grown independent
copies in three places: the runtime library, the analyzer's `convert_value()`,
and the CLI. The copies drifted: the analyzer's `q_log` decoder divided by 255
instead of 100 — a copy-paste from the neighbouring frequency decoder — so
`dspanalyze` printed Q=0.70 where the device meant Q=1.69 (`babac86`).

## Decision Drivers

* A conversion formula is a protocol fact; protocol facts must exist exactly
  once ([ADR-0001](0001-verify-every-protocol-claim-against-device-captures.md)).
* The analyzer is the instrument used to *verify* the runtime library —
  drift between them poisons verification itself.
* Display-name tables (channels, slopes, ratios) are the same kind of shared
  fact as formulas.

## Considered Options

* Centralise in `minidsp.protocol`; `dspanalyze` and the CLI import from it
* Keep per-package copies, synchronised by review
* Extract a third shared package both depend on

## Decision Outcome

Chosen option: **centralise in `minidsp.protocol`**, carried out as a series
of refactors: `level_uint16_to_dbu` moved in (`66603cd`), the analyzer's four
inline converters and its `gain_raw_to_db` duplicate replaced by imports
(`274caad`), `CHANNEL_NAMES` moved (`3021810`) and unified with
`INPUT_/OUTPUT_CHANNEL_NAMES` (`0458d99`). Each refactor was verified by
byte-identical analyzer output over the capture corpus. Inverse helpers are
added beside their forward form (`freq_hz_to_raw`, `34b40cb`) so callers never
re-derive a formula.

This reverses the earlier copy-per-package arrangement.

### Consequences

* Good, because the Q-divisor class of bug is structurally gone — there is
  one formula to be wrong in, and it has a regression test.
* Good, because downstream consumers (the Qt GUI) import the same canonical
  helpers instead of re-implementing them.
* Neutral, because `dspanalyze` now imports from `minidsp` — acceptable since
  they ship in one distribution.
* Bad, because `protocol.py` accumulates everything and keeps growing; it
  trades module size for correctness.

### Confirmation

`dspanalyze/config.py` contains imports from `minidsp.protocol`, not
formulas; `babac86` added a regression test pinning the Q conversion; refactor
commits recorded byte-identical output checks.

## More Information

* `babac86` — the motivating bug; `66603cd`, `274caad`, `3021810`, `0458d99`,
  `34b40cb` — the consolidation series.
