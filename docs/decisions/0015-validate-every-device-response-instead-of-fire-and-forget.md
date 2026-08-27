---
status: accepted
date: 2026-04-21
decision-makers: Maximilian Zettler
---

# Validate every device response instead of fire-and-forget

## Context and Problem Statement

Early device methods sent commands and discarded the responses. That worked —
until it didn't: the three `0x12` activate calls never checked whether
activation actually happened, and `store_preset` misread the device's reply to
`0x26` (set preset name) because it *isn't* the expected 1-byte ACK but a
16-byte echo of the name, so storing a preset always reported failure
(`9ab617f`). The device also has real timing behaviour — preset load and
flash-write ACKs arrive seconds late — that only a response-checking client
can distinguish from failure.

## Decision Drivers

* A DSP write that silently didn't apply is worse than an error — the user's
  speakers are on the other end.
* The device's ACK discipline is quirky per opcode (plain ACK, echo payloads,
  delayed ACK after flash writes); each quirk must be encoded once, in the
  library.
* Verified response shapes are protocol facts and belong in `protocol.md`
  ([ADR-0001](0001-verify-every-protocol-claim-against-device-captures.md)).

## Considered Options

* Read and validate the response of every command, with per-opcode timeout
  and shape knowledge
* Fire-and-forget writes, trusting the device
* Validate only "important" commands (preset store, lock)

## Decision Outcome

Chosen option: **validate everything**. `f3984a6` made all three activate
paths check for a present, valid ACK; `load_preset` uses a 2 s timeout because
the device applies the preset *before* ACKing (`adb36a9`); `store_preset`
waits up to 3 s for the flash write and validates the `0x26` echo payload
against the name it sent (`9ab617f`). Device methods return success/failure
truthfully instead of unconditionally.

This reverses the original fire-and-forget behaviour of the activate calls.

### Consequences

* Good, because "store always fails" class bugs became impossible to ship
  unnoticed — the echo mismatch was found precisely because a response was
  finally being read.
* Good, because per-opcode timing (2 s load, 3 s store) is documented protocol
  knowledge, not folklore in application code.
* Neutral, because every write now costs a read on a half-duplex-ish HID
  channel; at this protocol's rates that is irrelevant.
* Bad, because response validation needs the response shapes to be captured
  and documented per opcode — more reverse-engineering surface.

### Confirmation

`device.py` wrappers all follow send→receive→validate; `tests` assert builder
bytes, and the unsolicited-poll/response handling is exercised against
captures.

## More Information

* `f3984a6`, `adb36a9`, `9ab617f`.
