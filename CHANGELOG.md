# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-05-17

First public release. Complete reverse-engineering of the **the t.racks
DSP 4x4 Mini** USB HID protocol (Musicrown-based, VID:PID `0168:0821`)
and a full Linux control toolchain. Every implemented opcode has been
verified against real Wireshark captures of the manufacturer Windows
application.

A graphical front-end ships separately as
[miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt) and is
not included in this package.

### Added

- **Runtime control library (`minidsp`)** — Python API + CLI exposing
  the full protocol surface:
    - Input/output gain (`0x34`) with dual-resolution dB encoding
    - Mute (`0x35`) and phase invert (`0x36`)
    - Input noise gate (`0x3E`) — attack / release / hold / threshold
    - Output delay (`0x38`, 0–680 ms) and display-unit selection
      (`0x15`: ms / m / ft)
    - Crossover high-pass / low-pass (`0x32` / `0x31`) with 10 filter
      slope types
    - 7-band parametric EQ per output (`0x33`) including channel bypass
      (`0x3C`)
    - Output compressor / limiter (`0x30`) — ratio / knee / attack /
      release / threshold
    - 4×4 routing matrix (`0x3A`)
    - Channel linking (`0x3B` + `0x2A` prepare-link handshake)
    - Channel naming (`0x3D`, `0x26` preset name)
    - Preset load / store (`0x20` / `0x21`) for slots U01–U30
    - Read all 30 preset names (`0x29`) and full config (`0x27`, 9 pages
      × 50 bytes)
    - Test-tone generator (`0x39`) — pink/white noise + sine 20 Hz–20 kHz
    - Device lock (`0x2F` set PIN / `0x2D` submit PIN)
    - Real-time 8-channel level metering (`0x40`) including the limiter
      bitmask
- **`DSPmini` device wrapper** with exclusive `fcntl.flock(LOCK_EX)`
  advisory locking on the hidraw fd to prevent concurrent access from a
  second process or another `DSPmini` instance.
- **`minidsp` CLI** — `dump`, `levels [--watch]`, `mute`, `unmute`
  subcommands.
- **Protocol-analysis toolchain (`dspanalyze`)** — `capture` (auto-detects
  the device's USB bus/address and drives `tshark`), `analyze`, `decode`,
  `check` (12 protocol assertions guarding against regressions),
  `calibrate` (live level-meter calibration), `extract-defaults`
  (regenerate the bundled F00 factory preset from a startup capture),
  `diff-config`, `list-captures`. Output formats: human (rich tables),
  raw (hex dump), and a compact "claude" format.
- **Bundled F00 factory defaults** in `minidsp/factory_defaults.toml`,
  loadable via `minidsp.defaults.load_factory_defaults()`.
- **HTML documentation site** built with mkdocs-material; API reference
  auto-generated from docstrings at build time; deployable to GitHub
  Pages via `make publish`. Run locally with `make docs-serve`.
- **Release pipeline** — `make version VERSION=X.Y.Z` (bump pyproject,
  generate changelog, tag), `make build` (sdist + wheel), `make publish`
  (GitHub Release with assets + Pages deploy in one step, no `gh` CLI
  required).
- Complete protocol specification at
  [analysis/protocol.md](analysis/protocol.md) and feature inventory at
  [analysis/feature-list.md](analysis/feature-list.md).
