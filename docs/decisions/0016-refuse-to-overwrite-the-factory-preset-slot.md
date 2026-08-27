---
status: accepted
date: 2026-04-07
decision-makers: Maximilian Zettler
---

# Refuse to overwrite the factory preset slot in the library

## Context and Problem Statement

Preset store (`0x21`) takes a direct slot index where 0 is F00, the factory
preset, and 1–30 are the user slots U01–U30 (`5aba93c`). The manufacturer's
software never writes slot 0, so nothing is known about what the firmware does
if a host stores over it — and F00 is the state the device falls back to.
A plausible outcome of overwriting it with bad data is a device that cannot be
factory-reset: effectively bricked.

## Decision Drivers

* The consequence is potentially irreversible and lands on someone else's
  hardware.
* No legitimate use case for writing slot 0 has ever come up.
* Safety rails belong at the lowest layer that has enough information — here,
  the command builder itself, so no caller can bypass it accidentally.

## Considered Options

* Reject slot 0 in `cmd_store_preset()` (and thus every path above it)
* Guard only in the high-level `store_preset()` device method
* Document the danger and trust callers

## Decision Outcome

Chosen option: **reject in the command builder** (`5aba93c`).
`cmd_store_preset()` raises on slot 0, so the CLI, the device method, the Qt
GUI, and any future consumer inherit the protection; warnings were added
throughout the docs. Reading F00 (via `0x20` load) remains unrestricted — the
guard is write-only.

### Consequences

* Good, because an entire category of catastrophic mistake is unrepresentable
  through this library.
* Good, because the guard sits below every API surface, including ones that
  don't exist yet.
* Neutral, because genuinely intentional factory-preset research would need a
  local patch — an appropriate amount of friction for that experiment.
* Bad, because if the firmware turns out to handle slot-0 writes safely, the
  library is stricter than the device. Nobody has volunteered their unit to
  find out.

### Confirmation

`cmd_store_preset()` raises on index 0; tests cover the rejection;
`protocol.md` and `feature-list.md` carry the warnings.

## More Information

* `5aba93c` — verification of direct slot indexing and introduction of the
  guard; [ADR-0001](0001-verify-every-protocol-claim-against-device-captures.md)
  — why unverified firmware behaviour is treated as dangerous by default.
