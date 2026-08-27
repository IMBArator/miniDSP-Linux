---
status: accepted
date: 2026-05-04
decision-makers: Maximilian Zettler
---

# Retry the init handshake at open, and fail fast when the device is not ready

## Context and Problem Statement

When the DSP is plugged in (or re-enumerates), the hidraw node appears before
the firmware is ready to talk. The original code silently accepted an init
handshake timeout in `open()` and then let `read_config()` walk all eight of
its steps against a mute device — burning 20+ seconds of doomed commands
before the Qt frontend's poll loop failed three times and declared a
disconnect.

## Decision Drivers

* The window between "node exists" and "firmware answers" is a fact of the
  hardware; the library must own it, not every caller.
* Callers (the Qt worker, scripts) have reconnect loops; what they need from
  the library is a *prompt, honest* failure, not a slow limp.
* Partially-completed startup sequences leave the session in an undefined
  protocol state.

## Considered Options

* Retry init a bounded number of times in `open()`, then raise; make
  `read_config()` abort on the first unanswered step
* Keep accepting init timeouts and let higher layers time out eventually
* Have the library itself loop forever until the device answers

## Decision Outcome

Chosen option: **bounded retry, then fail fast** (`74eb3dc`). `open()` retries
the `0x10` init handshake up to 5 times with 500 ms spacing and raises
`OSError` if all fail, so the caller's reconnect loop drives the policy.
`read_config()` returns `None` immediately when the firmware query (step 2)
gets no response instead of continuing through the remaining steps.

This reverses the earlier silently-accept-the-timeout behaviour.

### Consequences

* Good, because reconnect latency dropped from tens of seconds to roughly the
  retry envelope; the Qt app's "device appeared" path became snappy.
* Good, because responsibility is cleanly split: the library reports readiness
  truthfully, callers decide how long to keep trying.
* Neutral, because 5 × 500 ms is empirical; a slower-booting firmware revision
  would need the constants revisited.
* Bad, because `read_config()` signals unready as `None` rather than a typed
  exception — callers must check. (Typed errors elsewhere:
  [ADR-0014](0014-raise-typed-oserror-subclasses-for-device-failures.md).)

### Confirmation

`open()`'s retry loop and `read_config()`'s early return in `device.py`, with
logging at each step visible under `-v`
([ADR-0018](0018-add-observability-with-stdlib-logging-behind-verbosity-flags.md)).

## More Information

* `74eb3dc` — implementation, citing the Qt `device_thread.py` failure mode
  that motivated it.
