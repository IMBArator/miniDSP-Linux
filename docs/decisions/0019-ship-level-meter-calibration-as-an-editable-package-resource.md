---
status: accepted
date: 2026-04-22
decision-makers: Maximilian Zettler
---

# Ship level-meter calibration as an editable package resource with a fitting workflow

## Context and Problem Statement

The device reports channel levels as linear uint16 amplitudes with no
documented reference point. Mapping them to dBu requires a calibration
constant (`REF_LEVEL`, the raw value corresponding to a known analog level),
which was discovered empirically and initially hardcoded. Different units,
input stages, or future firmware could shift it, and users with a signal
generator can measure their own device better than any shipped constant.

## Decision Drivers

* The dB conversion belongs in the protocol library
  ([ADR-0011](0011-make-minidsp-protocol-the-single-source-of-conversions-and-constants.md)),
  but the *constant* inside it is per-device empirical data.
* Users should be able to recalibrate without editing source.
* The calibration procedure itself (feed a known level, read raw values, fit)
  is analysis-tool territory, not runtime-library territory.

## Considered Options

* `minidsp/calibration.toml` as a package resource read via
  `importlib.resources`, plus a `dspanalyze calibrate` workflow
  (capture/show/apply/reset) that measures and rewrites it
* Hardcode `REF_LEVEL` in `protocol.py`
* A per-user config file under `~/.config`

## Decision Outcome

Chosen option: **package resource + calibrate workflow** (`595666e`). The
library loads `REF_LEVEL` from `minidsp/calibration.toml`;
`dspanalyze calibrate capture <dBu>` records anchor points against a known
source, `show` displays points and residual errors, `apply` computes the
best-fit reference via weighted least squares (`calibrate_compute_ref()`) and
writes the file, `reset` restores the factory value. The split keeps
measurement machinery in the analysis package and only the resulting constant
in the runtime.

### Consequences

* Good, because calibration is data with provenance — the TOML holds the
  anchor points, not just the fitted result.
* Good, because `minidsp levels` output is honest dBu on a calibrated unit,
  and the two-point factory calibration is a documented fallback.
* Neutral, because `apply` rewrites a file inside the installed package —
  fine for the intended editable/`uv sync` installs, surprising for a
  system-wide site-packages install.
* Bad, because per-*user* calibration and per-*install* calibration are
  conflated; two devices on one machine share the file.

### Confirmation

`calibrate_compute_ref()` and the loader have unit tests (`595666e`); the
README documents the full workflow.

## More Information

* `595666e`, `7cbb7c9`; `66603cd` — the `level_uint16_to_dbu` helper that
  consumes `REF_LEVEL`.
