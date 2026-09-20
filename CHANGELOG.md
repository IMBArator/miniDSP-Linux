# Changelog

All notable changes to this project will be documented in this file.

## [1.4.0] - 2026-09-20

### Added

- Expose the 0x40 input clip flag (payload byte 27) ([`5c7793a`](https://github.com/IMBArator/miniDSP-Linux/commit/5c7793a526876429ea39eebc02d6051cdfe1f096))
- Add per-channel clip rule (level >= 256) and expose it ([`4b67af2`](https://github.com/IMBArator/miniDSP-Linux/commit/4b67af2590549edc3f561ad9a52728efc4c2d04f))
- Decode 24-bit levels, add editor dB scale, clip at editor threshold ([`1aa5e1f`](https://github.com/IMBArator/miniDSP-Linux/commit/1aa5e1fe120608c800ea73f2b81d9fd71707e912))

### Fixed

- Re-anchor level meter to a voltmeter-verified 0 dBu ([`3e8cc16`](https://github.com/IMBArator/miniDSP-Linux/commit/3e8cc160f35db2d68fd959a85c6dbf935ba21ac6))
- Refit reference from three 24-bit points on InC ([`df1bf4c`](https://github.com/IMBArator/miniDSP-Linux/commit/df1bf4c1c854df97b8d4f4f873a859a160abf357))

## [1.3.0] - 2026-09-15

### Added

- Extract transport interface and add Windows hidapi backend ([`ff55876`](https://github.com/IMBArator/miniDSP-Linux/commit/ff558767b79c6f3013de10f913a14ff8a9e9ce6f))
- Raise DeviceBusyError when another process holds the device ([`7f09147`](https://github.com/IMBArator/miniDSP-Linux/commit/7f09147a78bc11c2748b2bfe51cfd3918b32ee0d))

### Documentation

- Add MADR architecture decision log ([`38a1d51`](https://github.com/IMBArator/miniDSP-Linux/commit/38a1d514eb22e8641d89374d0f7ba6d90fa5c1d2))
- Add working rules and docs/ to repo layout ([`dcd116d`](https://github.com/IMBArator/miniDSP-Linux/commit/dcd116dd37aade71960b3e8c1d0f3fbb373734eb))
- Record Windows transport decision (ADR-0024) and document Windows install ([`a791f7e`](https://github.com/IMBArator/miniDSP-Linux/commit/a791f7ec5ef74738710c4a878e9701996f660051))
- Replace development notes stub with a contributor guide ([`2aef99a`](https://github.com/IMBArator/miniDSP-Linux/commit/2aef99a4e189e9fb432636858dd6c40e6f824cef))

### Fixed

- Reuse capture's tshark discovery in the pcapng reader ([`d6de28d`](https://github.com/IMBArator/miniDSP-Linux/commit/d6de28dd98deff45460e295cdb8d3644390b0c39))

## [1.2.0] - 2026-06-20

### Added

- Expose device firmware/model string from read_config ([`c6101a3`](https://github.com/IMBArator/miniDSP-Linux/commit/c6101a3022ddabb8f532c41e68a60b1b9edc603c))

### Documentation

- Document 0x13 firmware parsing and read_config exposure ([`de6d4d6`](https://github.com/IMBArator/miniDSP-Linux/commit/de6d4d6c2835ca9c554b4a988eba3cd96963426a))

## [1.1.0] - 2026-06-19

### Added

- Add freq_hz_to_raw inverse helper ([`34b40cb`](https://github.com/IMBArator/miniDSP-Linux/commit/34b40cb2e205aaca2526ed4547e538eb007076ac))

## [1.0.1] - 2026-05-24

### Changed

- Source publish notes from CHANGELOG.md, not git-cliff ([`20e2399`](https://github.com/IMBArator/miniDSP-Linux/commit/20e239972b2c9072ae6ea6d20ee0a0462f6ef42b))

### Documentation

- Include CHANGELOG.md in the rendered docs site ([`e679606`](https://github.com/IMBArator/miniDSP-Linux/commit/e67960608a00c636578f126baf4eca9f42895baf))
- Rename CLI Usage page to DSP-Analyze CLI Usage ([`cb8e1a6`](https://github.com/IMBArator/miniDSP-Linux/commit/cb8e1a633ba27659a0242e096c4b4f965ce0d46d))
- Reposition project as library-first ([`8bf0178`](https://github.com/IMBArator/miniDSP-Linux/commit/8bf017802a2ac6ea900c16c88a312e2a93989356))
- Correct disconnect ownership and PIN charset for 0x2f ([`9e84b34`](https://github.com/IMBArator/miniDSP-Linux/commit/9e84b34fc8066bec44db4a02f2821194ce5a147c))

### Fixed

- Raise DeviceClosedError instead of bare assertion on closed handle ([`39bdbae`](https://github.com/IMBArator/miniDSP-Linux/commit/39bdbaeb7d7b72475d5c44b430e065fdcaf92138))

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
