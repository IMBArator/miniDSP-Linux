---
status: accepted
date: 2026-04-15
decision-makers: Maximilian Zettler
---

# Add observability with stdlib logging behind -v/-vv, configured only at the entry point

## Context and Problem Statement

`minidsp dump` failures printed "Failed to read configuration" and nothing
else, because `read_config()` swallowed every step's failure silently. At the
other extreme, the (then-bundled) GUI hardcoded `basicConfig(DEBUG)` at import
time, spraying debug output on every run and overriding whatever the host
application wanted. Diagnosing a startup-sequence failure meant editing the
source to add prints.

## Decision Drivers

* An 8-step startup sequence over flaky USB needs per-step visibility on
  demand — "which step, which page, what came back".
* A library must never configure the root logger; that is the application's
  prerogative.
* The mechanism should be the boring standard one, usable from any consumer.

## Considered Options

* Module-level stdlib loggers everywhere; `logging.basicConfig` called once
  in the CLI `main()`, mapped from `-v`/`-vv`
* Keep ad-hoc prints / hardcoded `basicConfig` in components
* A custom debug/trace facility

## Decision Outcome

Chosen option: **stdlib logging, configured only at the entry point**
(`91fa1b5`). `-v` maps to INFO (per-step startup progress, warnings naming the
exact failing step and index), `-vv` to DEBUG (full TX/RX hex dumps via
`_frame_hex`, every frame-parse rejection with its reason). `device.py` and
`protocol.py` use module loggers; the GUI's hardcoded `basicConfig` was
removed in the same change. No decoding logic changed — observability only.

This reverses the hardcoded-DEBUG and silent-swallow positions.

### Consequences

* Good, because "no response at step 7/8, config page 3" replaced "failed to
  read configuration" — field debugging of the unready-device behaviour
  ([ADR-0013](0013-fail-fast-on-unready-devices-and-retry-the-init-handshake.md))
  came directly out of this visibility.
* Good, because `-vv` hex dumps make every session a potential protocol
  trace, complementing Wireshark.
* Good, because host applications (the Qt GUI) control presentation and level
  themselves.
* Neutral, because parse-rejection logging sits on hot paths; at HID rates
  the cost is unmeasurable.

### Confirmation

`logging.basicConfig` appears only in `minidsp/cli.py:main()`; library modules
acquire `logging.getLogger(__name__)` and never touch handlers.

## More Information

* `91fa1b5` — the full change, including the GUI cleanup.
