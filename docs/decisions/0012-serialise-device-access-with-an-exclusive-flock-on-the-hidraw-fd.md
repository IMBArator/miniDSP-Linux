---
status: accepted
date: 2026-05-04
decision-makers: Maximilian Zettler
---

# Serialise device access with an exclusive flock on the hidraw fd

## Context and Problem Statement

Two processes can open the same `/dev/hidrawN` node — e.g. the Qt GUI's poll
loop and a `minidsp dump` in a terminal. Both then read from one interrupt IN
endpoint, and each steals responses the other is waiting for: commands appear
to time out, config reads interleave, and the failures look like protocol bugs
rather than what they are — concurrent access.

## Decision Drivers

* The protocol is strictly request/response with no session multiplexing;
  concurrent readers are unsound by construction.
* The failure mode without a guard is silent corruption of reads, the most
  expensive kind of bug report.
* Whatever mechanism is chosen must not leave stale state after a crash.

## Considered Options

* `fcntl.flock(LOCK_EX | LOCK_NB)` on the device fd at open
* A PID/lock file under `/run` or `/tmp`
* No guard; document "one process at a time"

## Decision Outcome

Chosen option: **flock on the fd itself** (`ca91676`). `DSPmini.open()`
acquires the exclusive advisory lock immediately after `os.open`; if another
process holds it, open fails with a clear "already in use" `OSError`. Because
the lock is a property of the open fd, the kernel releases it on close *and*
on crash — no cleanup path, no stale lock files. This works precisely because
the transport owns a raw fd
([ADR-0002](0002-speak-to-the-device-through-hidraw-without-a-usb-library.md)).

### Consequences

* Good, because the CLI-vs-GUI collision became a crisp, immediate error
  message instead of intermittent timeouts.
* Good, because there is nothing to clean up ever — the kernel owns the
  lock's lifetime.
* Neutral, because advisory locks only bind cooperating processes; a foreign
  tool ignoring flock can still interleave. All known consumers go through
  this library.
* Bad, because legitimate read-only observers (a second `minidsp levels`) are
  also excluded; the protocol gives no safe way to allow them anyway.

### Confirmation

`DSPmini.open()` in `device.py` performs the flock and raises on conflict;
the docstring documents the semantics.

## More Information

* `ca91676` — implementation, motivated by CLI/Qt-app concurrent access.
* Amended by [ADR-0024](0024-support-windows-through-a-hidapi-transport.md):
  this decision is scoped to Linux — the flock moved with the hidraw code into
  `minidsp/transport.py`, and Windows reaches the same guarantee with a named
  Win32 mutex that the OS likewise abandons on process death.
* Amended by the typed lock-conflict error: a failed flock now raises
  `DeviceBusyError` instead of a plain `OSError`. It subclasses `OSError` and
  keeps the same "already in use by another process" message, so every
  existing `except OSError` caller is unaffected, but a GUI can now tell
  "busy" from "not found" — showing a *busy* state and continuing to retry
  until the other process releases the device, instead of reporting a
  disconnect.
