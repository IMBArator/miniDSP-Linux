---
status: accepted
date: 2026-04-04
decision-makers: Maximilian Zettler
---

# Guard protocol knowledge with an assertion framework over captures

## Context and Problem Statement

Protocol knowledge accumulates across dozens of captures, and each new
discovery risks quietly contradicting an old one — a re-interpreted byte
offset, a changed value range, a renamed field. Unit tests cover the *code*,
but nothing was checking that the current protocol map still held over all the
*evidence*.

## Decision Drivers

* Reverse engineering revises beliefs; revisions need a tripwire against
  regressions.
* The captures are the ground truth and are already in the repository — they
  should work as a test corpus.
* Claims like "gain is always raw 0–400" are cheap to assert mechanically and
  expensive to re-derive by hand.

## Considered Options

* A `dspanalyze check` mode running named protocol assertions over any capture
* Rely on `tests/test_protocol.py` alone
* Manual re-analysis when in doubt

## Decision Outcome

Chosen option: **`dspanalyze check`** (`e3cd9a9`), an assertion framework with
12 assertions spanning frame integrity (checksums, structure, known opcodes),
value ranges (gain 0–400, mute 0/1, channel 0–7), command semantics (ACK
follows writes, startup ordering), config completeness (9 pages, 30 preset
slots), and calibration anchors (0 dB = raw 280). New captures are routinely
run through `check` before their findings are documented; discovery commits
frequently note "all assertions pass".

### Consequences

* Good, because contradictions between new captures and the current map
  surface as named assertion failures instead of silent doc rot.
* Good, because the check codifies protocol invariants in an executable form
  that is independent of the runtime library.
* Neutral, because assertions must be updated when a belief is legitimately
  revised — that edit is itself useful review pressure.
* Bad, because coverage is only as good as the assertion list; fields nobody
  wrote an assertion for can still drift.

### Confirmation

`dspanalyze/check.py` and its tests; `make check FILE=...`; commit messages
recording assertion runs against new captures (e.g. `102e37b`, `4325fbd`).

## More Information

* `e3cd9a9` — introduction with the initial 12 assertions;
  [ADR-0001](0001-verify-every-protocol-claim-against-device-captures.md) —
  the methodology this enforces.
