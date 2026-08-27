---
status: accepted
date: 2026-04-04
decision-makers: Maximilian Zettler
---

# Encode the analyzer's protocol knowledge in a declarative TOML file

## Context and Problem Statement

The analysis tool must decode ~30 opcodes, each with named fields, byte
offsets, value formats, and verification status — knowledge that changes
weekly as reverse engineering progresses. Hardcoding it in Python would bury
the protocol map in decoder logic; every discovery session would mean code
edits in several functions.

## Decision Drivers

* Protocol knowledge changes far more often than decoding machinery.
* The map should be reviewable at a glance — "what do we currently believe
  about 0x33?" should be one table lookup, not a code read.
* Verification status (`verified` flags, TBD fields) is data about the
  knowledge, and belongs next to it.

## Considered Options

* A declarative `protocol_config.toml` describing opcodes, fields, and value
  formats, interpreted by a generic decoder
* Python dataclasses/dicts inside the decoder module
* Docstrings/comments in `protocol.py` as the only machine-adjacent map

## Decision Outcome

Chosen option: **`dspanalyze/protocol_config.toml`** (`e6a6cbe`). Each opcode
is a TOML table with name, direction, payload fields (offset, size, format),
and a `verified` flag; value formats (e.g. `freq_log`, `q_log`, `gate_time`)
are named and implemented once in `config.py`. The decoder (`decode.py`) is
generic and driven entirely by the config.

Note the boundary with
[ADR-0011](0011-make-minidsp-protocol-the-single-source-of-conversions-and-constants.md):
the TOML names the formats, but the conversion *formulas* are imported from
`minidsp.protocol` — the analyzer's early private copies drifted (the `q_log`
divisor bug `babac86`) and were removed.

### Consequences

* Good, because a new opcode is a TOML block, not a decoder change — most
  discovery commits touch the config plus docs plus tests, no decoder logic.
* Good, because the TOML doubles as a compact machine-readable protocol
  reference alongside the prose spec.
* Good, because `verified = false` entries make the boundary of knowledge
  explicit and grep-able.
* Bad, because there are now two protocol descriptions (`protocol_config.toml`
  for the analyzer, `protocol.py` for the runtime) that must be kept in
  agreement by discipline rather than by construction.

### Confirmation

`dspanalyze check` asserts decoding invariants over real captures; discovery
commits touch `protocol_config.toml`, `protocol.py`, and `protocol.md`
together (enforced by convention recorded in `CLAUDE.md`).

## More Information

* `e6a6cbe` — introduction; `babac86` — the drift bug that sharpened the
  formula-ownership boundary.
