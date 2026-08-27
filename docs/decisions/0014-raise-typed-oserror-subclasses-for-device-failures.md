---
status: accepted
date: 2026-05-24
decision-makers: Maximilian Zettler
---

# Raise typed exceptions for device failure states

## Context and Problem Statement

Device failure states were signalled inconsistently: a closed handle tripped a
bare `assert self._fd is not None` in `_send`/`_recv`, and a PIN-locked device
simply never answered config reads, hanging the caller. Assertions vanish
under `python -O`, don't derive from `OSError` (so callers' `except OSError`
transport handling missed them), and a silent hang is the worst possible way
to learn the device is locked.

## Decision Drivers

* Callers — the Qt worker foremost — handle "device went away" via
  `except OSError`; closed-handle errors should land in the same net
  (the Qt project's ADR-0012 catches exactly this family).
* Lock state is an expected, user-facing condition that deserves a
  recognisable type, not a timeout.
* `assert` is a debugging aid, not an error contract.

## Considered Options

* Typed exceptions: `DeviceClosedError(OSError)`, `DeviceLockedError`
* Bare asserts and `None` returns
* Generic `RuntimeError` with message strings

## Decision Outcome

Chosen option: **typed exceptions**. `DeviceClosedError` subclasses `OSError`
so cable-yank and use-after-close flow through existing transport handling
(`39bdbae`). `DeviceLockedError` is raised by `read_config()` after checking
the lock flag in the `0x2c` device-info response (byte 6), turning a silent
hang into an immediate, actionable error (`fab455a`); `is_locked()` lets
callers query the state cheaply.

### Consequences

* Good, because failure semantics are part of the API: `except OSError`
  means transport, `except DeviceLockedError` means "ask the user for a PIN".
* Good, because behaviour no longer changes under `python -O`.
* Neutral, because `DeviceLockedError` derives from `RuntimeError`, not
  `OSError` — deliberate, since a locked device is not a transport failure.
* Bad, because `read_config()` still returns `None` for "unready"
  ([ADR-0013](0013-fail-fast-on-unready-devices-and-retry-the-init-handshake.md)),
  so the error surface is typed but not yet uniform.

### Confirmation

Both exception classes are defined and documented in `device.py`; tests cover
the locked, unlocked, and invalid device-info cases (`fab455a`).

## More Information

* `39bdbae`, `fab455a`; the Qt project's ADR-0012 (catch only device and
  transport errors) is the principal consumer of these types.
