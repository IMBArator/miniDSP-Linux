# Architecture

This document describes how miniDSP-Linux is built and why. It condenses the
architecture decision records in [decisions/](decisions/index.md) into one
reading order. The records stay the authority for *why*; this page is the map
of *what* and *how*. The rules every change must keep are collected in
[Invariants](#invariants).

<!-- Keep this page in step with the code and the records: update it in the
     same change that alters the design, adds or removes a module, or accepts
     a record that changes the picture. -->

## Goal and shape

miniDSP-Linux controls the t.racks DSP 4x4 Mini, a Musicrown-based DSP (USB
VID:PID `0168:0821`), from Linux and Windows without the manufacturer's
Windows editor. The manufacturer publishes no protocol, so the project has two
halves that ship in one distribution (`minidsp-linux`):

* **`minidsp`** — the runtime library and the `minidsp` command line tool. It
  speaks the reverse-engineered USB HID protocol: framed commands in 64-byte
  HID reports over interrupt transfers, specified in
  [protocol.md](../analysis/protocol.md). The Qt GUI, miniDSP-Linux-qt, is a
  separate project that consumes this library as a released wheel
  ([ADR-0004](decisions/0004-keep-this-repository-library-first-and-develop-the-gui-separately.md)).
* **`dspanalyze`** — the analysis toolchain that reverse-engineers and
  verifies the protocol from USB captures of the manufacturer's editor
  ([ADR-0006](decisions/0006-build-a-dedicated-analysis-package-instead-of-throwaway-scripts.md)).

```
  minidsp CLI        Qt GUI (miniDSP-Linux-qt)
          \             /
           v           v
        minidsp.device  ─────────►  minidsp.protocol  ◄───────  dspanalyze
        (DSPmini)                   (frames, builders,          (capture, decode,
            │                        parsers, conversions)       check, diff-config,
            ▼                                                    extract-defaults,
        minidsp.transport                                        calibrate)
        hidraw (Linux) │ hidapi (Windows)                            ▲
            │                                                        │ tshark
            ▼                                                        │
        t.racks DSP 4x4 Mini  ── USB traffic of the editor ──────────┘
```

## The core idea

Two choices shape everything else:

1. **The protocol is known only through captures.** Every claim is verified
   on the device before it is documented or implemented
   ([ADR-0001](decisions/0001-verify-every-protocol-claim-against-device-captures.md));
   the related DSP 408 project is a source of hypotheses, not of facts
   ([ADR-0005](decisions/0005-cross-reference-dsp-408-ui-but-trust-only-on-device-verification.md)).
   Verified knowledge is encoded once: the wire format and the conversions in
   `minidsp.protocol`
   ([ADR-0011](decisions/0011-make-minidsp-protocol-the-single-source-of-conversions-and-constants.md)),
   the analyzer's view in `protocol_config.toml`
   ([ADR-0007](decisions/0007-encode-protocol-knowledge-in-a-declarative-toml.md)).
   Assertions over the committed captures guard it against regressions
   ([ADR-0009](decisions/0009-guard-protocol-knowledge-with-capture-assertions.md)).
2. **The runtime library is small and protective.** It is a GUI-free,
   dependency-light layer over a swappable `Transport`
   ([ADR-0002](decisions/0002-speak-to-the-device-through-hidraw-without-a-usb-library.md),
   [ADR-0024](decisions/0024-support-windows-through-a-hidapi-transport.md))
   that serialises device access
   ([ADR-0012](decisions/0012-serialise-device-access-with-an-exclusive-flock-on-the-hidraw-fd.md)),
   validates every response
   ([ADR-0015](decisions/0015-validate-every-device-response-instead-of-fire-and-forget.md)),
   and refuses destructive writes: the factory preset F00, and on a restore the
   device PIN
   ([ADR-0016](decisions/0016-refuse-to-overwrite-the-factory-preset-slot.md),
   [ADR-0026](decisions/0026-transfer-presets-the-way-the-editor-does.md)).

## Components

### Protocol (`minidsp.protocol`)

Frame encoding (`10 02 SRC DST LEN PAYLOAD 10 03 CHK` with an XOR checksum),
one `cmd_*` builder per opcode, `parse_*` functions for the replies, and the
conversions between raw values and dB, Hz, ms and Q, plus the constants and
channel names. The module does no I/O, so the tests assert the exact bytes of
frames taken from captures. It is the executable form of
[protocol.md](../analysis/protocol.md).

### Device and transport (`minidsp.device`, `minidsp.transport`)

`DSPmini` opens the device through a `Transport`. `default_transport()`
picks the one for the platform, and tests pass a fake. `open()` runs the init
handshake with retries and fails fast on a device that isn't ready
([ADR-0013](decisions/0013-fail-fast-on-unready-devices-and-retry-the-init-handshake.md)).
Every command method sends, waits for the reply and validates it
([ADR-0015](decisions/0015-validate-every-device-response-instead-of-fire-and-forget.md)).
Failures raise typed exceptions: `DeviceClosedError` and `DeviceBusyError`
(both `OSError`) and `DeviceLockedError`
([ADR-0014](decisions/0014-raise-typed-oserror-subclasses-for-device-failures.md)).
`HidrawTransport` reads and writes `/dev/hidraw*` and holds an exclusive
`flock`; `HidapiTransport` uses hidapi and a named mutex on Windows
([ADR-0024](decisions/0024-support-windows-through-a-hidapi-transport.md)).

### Presets and `.unt` files (`minidsp.unt`)

`UntFile` reads, edits and writes the editor's `.unt` preset files and keeps
every byte it doesn't model
([ADR-0025](decisions/0025-the-library-owns-the-unt-file-format.md)).
`DSPmini.export_unt()` and `DSPmini.restore_unt()` transfer presets the way
the editor does: stored presets are read without recalling them, and a
restore is guarded and keeps the device PIN
([ADR-0026](decisions/0026-transfer-presets-the-way-the-editor-does.md)).

### Package resources (`minidsp.defaults` and the TOML files)

The F00 factory values are a generated TOML resource in raw protocol form,
loaded by `load_factory_defaults()`
([ADR-0017](decisions/0017-bundle-factory-defaults-as-a-package-resource-in-raw-protocol-form.md)).
The level-meter calibration is an editable TOML resource that
`dspanalyze calibrate` fits against a known signal
([ADR-0019](decisions/0019-ship-level-meter-calibration-as-an-editable-package-resource.md)).

### Command line (`minidsp.cli`)

`argparse` subcommands to dump the configuration, watch the levels, mute and
unmute, and save, restore and inspect `.unt` files. The entry point is the
only place that configures logging, behind `-v`/`-vv`
([ADR-0018](decisions/0018-add-observability-with-stdlib-logging-behind-verbosity-flags.md)).

### Analysis toolchain (`dspanalyze`)

Reads captures (pcapng through tshark
([ADR-0008](decisions/0008-drive-usb-capture-and-parsing-through-tshark-subprocesses.md)),
or Wireshark text exports), decodes them with the knowledge in
`protocol_config.toml`, and renders the result compactly (`claude`), as a
table (`human`) or as hex (`raw`). Around that: `capture` records USB
traffic, `check` runs the protocol assertions, `diff-config` shows the bytes
that changed between config reads, `list-captures` reads the `.meta.toml`
sidecars
([ADR-0010](decisions/0010-record-capture-metadata-in-toml-sidecars.md)),
and `extract-defaults` and `calibrate` produce the two package resources. The
command reference is [DSPanalyze CLI Usage](../dspanalyze/USAGE.md).

## Module map

| Path | Role |
|---|---|
| `minidsp/__init__.py` | Package docstring and `__version__` |
| `minidsp/__main__.py` | `python -m minidsp`, delegates to `cli.main` |
| `minidsp/cli.py` | `minidsp` CLI: dump, levels, mute, unmute, save-unt, restore-unt, unt-info |
| `minidsp/device.py` | `DSPmini`: open/close, init handshake, command methods, config and stored-preset reads, `.unt` export and restore |
| `minidsp/transport.py` | `Transport` interface, `HidrawTransport` (Linux), `HidapiTransport` (Windows), `default_transport()` |
| `minidsp/protocol.py` | Framing, command builders, response parsers, conversions, constants, channel names |
| `minidsp/unt.py` | `.unt` preset file format (`UntFile`: read, edit, write) |
| `minidsp/defaults.py` | `load_factory_defaults()` for the bundled factory values |
| `minidsp/factory_defaults.toml` | F00 factory-preset values in raw protocol form (generated) |
| `minidsp/calibration.toml` | Level-meter calibration (reference level and anchor points) |
| `dspanalyze/__init__.py`, `dspanalyze/__main__.py` | Package docstring and `__version__`; `python -m dspanalyze` |
| `dspanalyze/cli.py` | `dspanalyze` CLI: analyze, check, capture, diff-config, list-captures, extract-defaults, calibrate |
| `dspanalyze/protocol_config.toml` | The analyzer's protocol knowledge: opcodes, fields, value formats |
| `dspanalyze/config.py` | Loads `protocol_config.toml`; its value formats call the `minidsp.protocol` conversions |
| `dspanalyze/readers/` | `RawPacket` and `read_capture()`: pcapng through tshark, Wireshark text exports |
| `dspanalyze/decode.py` | Raw packets to `DecodedCommand`s |
| `dspanalyze/output/` | Output formats `claude`, `human` and `raw` |
| `dspanalyze/check.py` | Protocol assertions over captures (`ASSERTIONS`) |
| `dspanalyze/capture.py` | USB capture through tshark with device auto-detection |
| `dspanalyze/diff_config.py` | Changed bytes between config reads within one capture |
| `dspanalyze/metadata.py` | `.meta.toml` sidecar file per capture |
| `dspanalyze/extract_defaults.py` | F00 config pages from a capture into `factory_defaults.toml` |
| `dspanalyze/calibrate.py` | Level-meter calibration: capture, show, apply, reset |
| `dspanalyze/USAGE.md` | The `dspanalyze` command reference |
| `tests/` | The test suite: protocol, device (with `FakeTransport`), `.unt`, analyzer, version |
| `docs/` | MkDocs site sources: include stubs, `hooks.py`, `gen_ref_pages.py`, this page, `decisions/` |
| `analysis/` | Reverse-engineering reference: `protocol.md` (the specification), `feature-list.md`, `.unt` fixtures, `usb_captures/` (captures with `.meta.toml`), `resources/` |
| `scripts/` | `version.sh` and `publish.sh`, the release tooling |
| `Makefile` | The only entry point for setup, tests, checks, builds, docs, analysis and releases |

### Import rules

* `minidsp.protocol` imports nothing from the project; it is the base.
* `minidsp.transport` and `minidsp.unt` import `minidsp.protocol`;
  `minidsp.device` imports `protocol`, `transport` and `unt`; `minidsp.cli`
  imports `device`, `protocol` and `unt`; `minidsp.defaults` uses only the
  standard library.
* `minidsp` never imports `dspanalyze`.
* `dspanalyze` takes every conversion and constant from `minidsp.protocol`;
  only `dspanalyze.calibrate` also imports `minidsp.device`, to read live
  levels.
* `hid` (hidapi) is imported only inside `minidsp.transport`, and only when
  the Windows transport is used.

### How things plug in

* **A protocol command.** Capture one isolated action of the editor and find
  the bytes (the "Typical Workflow" in
  [DSPanalyze CLI Usage](../dspanalyze/USAGE.md)). Then, in one change: add
  the opcode block to `protocol_config.toml`, add the builder, parser and
  conversions to `minidsp/protocol.py` with tests that assert the captured
  bytes, and document the opcode in [protocol.md](../analysis/protocol.md)
  and the [feature list](../analysis/feature-list.md). A `DSPmini` method
  sends, receives and validates with its own timeout; a CLI subcommand is
  added only when it is needed. `make analyze-check` stays green.
* **A CLI subcommand.** An `argparse` subparser in the package's `cli.py`
  with `set_defaults(func=cmd_<name>)` and a `help=` line.
* **A protocol assertion.** An `Assertion` in `ASSERTIONS` in
  `dspanalyze/check.py`, with the capture glob it applies to.
* **A transport.** A `Transport` subclass in `minidsp/transport.py`, chosen by
  `default_transport()`.
* **An output format.** A module in `dspanalyze/output/` and a `--format`
  choice in `dspanalyze/cli.py`.

## Invariants

The rules below follow from the design above. A change that breaks one is
wrong even when every test passes; the record named with each rule explains
why.

### Protocol knowledge

- No protocol claim is documented or implemented without a device capture
  that shows it; anything else is marked unverified
  ([ADR-0001](decisions/0001-verify-every-protocol-claim-against-device-captures.md),
  [ADR-0005](decisions/0005-cross-reference-dsp-408-ui-but-trust-only-on-device-verification.md)).
- `minidsp.protocol` is the only home of conversion formulas, constants and
  channel names; `dspanalyze` imports them instead of re-deriving them
  ([ADR-0011](decisions/0011-make-minidsp-protocol-the-single-source-of-conversions-and-constants.md)).
- `dspanalyze/protocol_config.toml` is the analyzer's only protocol
  knowledge; a new opcode is a TOML block, not decoder code
  ([ADR-0007](decisions/0007-encode-protocol-knowledge-in-a-declarative-toml.md)).
- Every committed capture has a `.meta.toml` sidecar next to it
  ([ADR-0010](decisions/0010-record-capture-metadata-in-toml-sidecars.md)).

### Device safety

- Nothing writes preset slot 0 (F00, the factory preset): `cmd_store_preset`
  raises `ValueError` for it, and `restore_unt` writes only the filled slots
  1–30
  ([ADR-0016](decisions/0016-refuse-to-overwrite-the-factory-preset-slot.md),
  [ADR-0026](decisions/0026-transfer-presets-the-way-the-editor-does.md)).
- `restore_unt` writes only with `confirm=True` (CLI: `--yes`), refuses a file
  without presets, and keeps the device's PIN by default
  ([ADR-0026](decisions/0026-transfer-presets-the-way-the-editor-does.md)).
- Device access is exclusive: `open()` takes `flock` on the hidraw fd on Linux
  or a named mutex on Windows, never a lock file; a second opener gets
  `DeviceBusyError`
  ([ADR-0012](decisions/0012-serialise-device-access-with-an-exclusive-flock-on-the-hidraw-fd.md),
  [ADR-0024](decisions/0024-support-windows-through-a-hidapi-transport.md)).
- Every device write is send → receive → validate, and a method reports
  success only when the device's reply confirms it
  ([ADR-0015](decisions/0015-validate-every-device-response-instead-of-fire-and-forget.md)).

### Sources of truth

- `minidsp/unt.py` with `pack_preset_params` owns the `.unt` format: offsets
  exist once, unknown bytes survive, and `pack(parse(b), b) == b`
  ([ADR-0025](decisions/0025-the-library-owns-the-unt-file-format.md)).
- `minidsp/factory_defaults.toml` is generated by `dspanalyze extract-defaults`
  from an F00 capture and never edited by hand
  ([ADR-0017](decisions/0017-bundle-factory-defaults-as-a-package-resource-in-raw-protocol-form.md)).
- Level-meter calibration lives only in `minidsp/calibration.toml`, written by
  `dspanalyze calibrate`
  ([ADR-0019](decisions/0019-ship-level-meter-calibration-as-an-editable-package-resource.md)).
- `CHANGELOG.md` is generated from the commit subjects by git-cliff at release
  time; hand-curated sections are kept
  ([ADR-0021](decisions/0021-drive-the-changelog-from-conventional-commits-with-git-cliff.md)).

### Layering and dependencies

- `minidsp` never imports `dspanalyze`; `dspanalyze` imports
  `minidsp.protocol`, and only `dspanalyze calibrate` uses `minidsp.device` to
  read live levels
  ([ADR-0011](decisions/0011-make-minidsp-protocol-the-single-source-of-conversions-and-constants.md),
  [ADR-0019](decisions/0019-ship-level-meter-calibration-as-an-editable-package-resource.md)).
- On Linux the library talks to `/dev/hidraw` with no USB or HID library;
  hidapi is installed only on Windows, and the `0x00` report-number prefix
  stays inside `HidapiTransport`
  ([ADR-0002](decisions/0002-speak-to-the-device-through-hidraw-without-a-usb-library.md),
  [ADR-0024](decisions/0024-support-windows-through-a-hidapi-transport.md)).
- This repository contains no GUI and no GUI extra; the GUI lives in
  miniDSP-Linux-qt
  ([ADR-0004](decisions/0004-keep-this-repository-library-first-and-develop-the-gui-separately.md)).
- Only `minidsp/cli.py:main()` calls `logging.basicConfig`; library modules use
  `logging.getLogger(__name__)` and never touch handlers
  ([ADR-0018](decisions/0018-add-observability-with-stdlib-logging-behind-verbosity-flags.md)).

### Tests and releases

- Tests never talk to a real DSP; they use `FakeTransport` and a stubbed `hid`
  module, so the suite runs the same on Linux and Windows without hardware
  ([ADR-0024](decisions/0024-support-windows-through-a-hidapi-transport.md)).
- `scripts/version.sh` refuses a dirty working tree, an existing tag and a
  duplicate changelog section, and pushes only after an explicit yes, never
  without a terminal
  ([ADR-0023](decisions/0023-write-release-automation-in-plain-bash-against-the-github-api.md)).

## Decision records

Every architectural decision has a record under
[decisions/](decisions/index.md); the index groups them by area and lists the
decisions that reversed an earlier position. The sections above link to the
record behind each choice where it is made.
