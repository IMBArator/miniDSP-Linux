---
status: accepted
date: 2026-04-07
decision-makers: Maximilian Zettler
---

# Cross-reference dsp-408-ui, but trust only on-device verification

## Context and Problem Statement

[dsp-408-ui](https://github.com/Aeternitaas/dsp-408-ui) implements the same
Musicrown protocol family over TCP for the DSP 408. It is an enormously
valuable head start — opcodes, frame format, and many encodings carry over.
But the DSP 408 is a different device (8 outputs, GEQ, input PEQ, different
fader resolutions), and it was unclear how much of its protocol map could be
adopted for the 4x4 Mini without independent proof.

## Decision Drivers

* Bootstrapping from a known sibling protocol saves weeks of blind capture
  work.
* Silent differences between the devices would corrupt the spec — and the
  spec is the core deliverable.
* [ADR-0001](0001-verify-every-protocol-claim-against-device-captures.md)
  already demands capture-level evidence for claims.

## Considered Options

* Use dsp-408-ui as a map of hypotheses; verify each on the 4x4 Mini before
  marking it verified
* Adopt dsp-408-ui's protocol tables wholesale
* Ignore dsp-408-ui and reverse-engineer from scratch

## Decision Outcome

Chosen option: **hypotheses, not facts**. Every cross-referenced opcode was
re-captured on the 4x4 Mini before being marked `verified` in
`protocol_config.toml`. The policy paid for itself repeatedly:

* Crossover frequency uses raw 0–300 on the 4x4 Mini where the DSP 408 uses
  0–1000 for the same 19.7 Hz–20.16 kHz log scale (`c77e973`).
* Preset load (`0x20`) uses direct slot indices, not the 1-based mapping
  documented from the DSP 408 (`5aba93c`).
* The GEQ opcode `0x48` does not exist on the 4x4 Mini at all and was removed
  from the docs and analyzer config (`bca628a`, `b1320a3`); input PEQ likewise.
* Output delay (`0x38`) was unknown even to dsp-408-ui and was discovered
  here first (`06cccce`).

### Consequences

* Good, because the head start was real — frame format, checksum, and most
  opcode numbers carried over unchanged.
* Good, because each verified divergence is now documented explicitly, so
  future readers know which facts are device-specific.
* Neutral, because the GPL licensing alignment
  ([ADR-0003](0003-license-under-gpl-3-0.md)) keeps the relationship
  reciprocal.
* Bad, because everything cross-referenced still costs a capture session.

### Confirmation

`protocol_config.toml` opcode entries carry `verified` flags;
`analysis/protocol.md` and `analysis/dsp-408-ui-summary.md` note the
divergences explicitly.

## More Information

* `c77e973`, `5aba93c`, `bca628a`, `b1320a3`, `06cccce` — the divergences
  listed above; `102e37b` — channel linking confirmed to match.
