# miniDSP-Linux

> **Protocol:** Fully reverse-engineered (as far as we can tell) — all commands verified from Wireshark captures.

> **minidsp tool (CLI):** Gain, mute, dump, and the full protocol surface are available via the CLI. A graphical interface is available in [miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt).

Linux control tool for the **the t.racks DSP 4x4 Mini** (Musicrown-based DSP processor). Provides a CLI and Python API for device control over USB HID — no official Linux software required.

The USB HID protocol was fully reverse-engineered from Wireshark captures. See [analysis/protocol.md](analysis/protocol.md) for the complete specification and [analysis/feature-list.md](analysis/feature-list.md) for the full feature inventory.

## Features

### GUI

A Qt-based graphical interface is available at [miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt).

### Protocol implemented (usable via `device.py`)

All commands verified against real Wireshark captures on the device.

| Feature | Opcode |
|---|---|
| Input/output gain | `0x34` |
| Mute | `0x35` |
| Phase invert | `0x36` |
| Input noise gate (attack/release/hold/threshold) | `0x3e` |
| Output delay (0–680 ms) | `0x38` |
| Delay display unit (ms / m / ft) | `0x15` |
| Output crossover hi-pass / lo-pass (10 slope types) | `0x32` / `0x31` |
| Output parametric EQ (7 bands: gain/freq/Q/type/bypass) | `0x33` |
| Output PEQ channel bypass | `0x3c` |
| Output compressor/limiter (ratio/knee/attack/release/threshold) | `0x30` |
| 4×4 routing matrix | `0x3a` |
| Channel linking | `0x3b` + `0x2a` |
| Channel name set | `0x3d` |
| Preset load / store / name | `0x20` / `0x21` / `0x26` |
| Read all 30 preset names | `0x29` |
| Config read (9 pages × 50 bytes) | `0x27` |
| Device lock (set PIN / submit PIN) | `0x2f` / `0x2d` |
| Test tone generator (pink/white noise, sine 20Hz–20kHz) | `0x39` |
| Real-time level metering (8 ch + limiter mask) | `0x40` |

### CLI (`minidsp`)

```
dump                    Dump all DSP configuration parameters as tables
levels [--watch]        Snapshot live level meters (raw uint16 + dBu)
mute    [channel ...]   Mute input channel(s)
unmute  [channel ...]   Unmute input channel(s)
```

### Level meter calibration (`dspanalyze calibrate`)

The level meter calibration is maintained in `minidsp/calibration.toml` (shipped as a package resource). The analysis toolkit provides the tooling to calibrate it using a known signal source:

```bash
# Capture raw levels at a known analog level (e.g. 0 dBu from a signal generator)
dspanalyze calibrate capture 0

# Capture at more levels for better accuracy
dspanalyze calibrate capture -10
dspanalyze calibrate capture -30

# View all calibration points and measured errors
dspanalyze calibrate show

# Compute best-fit REF_LEVEL and write it to the package
dspanalyze calibrate apply

# Revert to factory default
dspanalyze calibrate reset
```

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — manages the virtual environment and dependencies
- Linux with kernel HID driver — communicates via `/dev/hidraw*` (no libusb needed)
- Read/write access to `/dev/hidraw*` (see [Permissions](#permissions))

## Installation

```bash
git clone https://github.com/IMBArator/miniDSP-Linux.git
cd miniDSP-Linux
uv sync              # creates .venv, installs core deps
uv sync --extra dev  # also installs pytest for development
```

## Usage

### CLI

```bash
# Dump all DSP parameters (presets, gains, EQ, crossover, compressor, …)
minidsp dump

# Snapshot live level meters (all 8 channels: raw uint16 + dBu)
minidsp levels

# Continuous level monitoring (Ctrl+C to stop)
minidsp levels --watch

# Log level readings to CSV for offline analysis
minidsp levels --watch --csv levels.csv

# Mute input channels 1 and 2
minidsp mute 1 2

# Unmute all input channels
minidsp unmute 1 2 3 4
```

### Protocol analysis toolchain (`dspanalyze`)

A separate analysis package for decoding Wireshark USB captures:

```bash
# Decode a capture, exclude poll noise, human-readable output
dspanalyze analyze capture.pcapng --decode --exclude 0x40

# Show only changed config bytes between two config reads in one session
dspanalyze diff-config capture.pcapng

# Run protocol assertions (checksum, frame structure, known opcodes)
dspanalyze check capture.pcapng --assertion all

# List all captures with metadata summaries
dspanalyze list-captures analysis/usb_captures/

# Calibrate level meters using a signal generator
dspanalyze calibrate capture 0       # capture at 0 dBu
dspanalyze calibrate show            # view points + errors
dspanalyze calibrate apply           # compute and write REF_LEVEL
```

See `Makefile` for pre-defined analysis workflows (`make analyze FILE=...`, `make diff-config FILE=...`, etc.).

## Permissions

The tool communicates via `/dev/hidraw*`. By default this requires root. To allow regular users, create a udev rule:

```bash
sudo tee /etc/udev/rules.d/99-dspmini.rules << 'EOF'
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0168", ATTRS{idProduct}=="0821", MODE="0666"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Then reconnect the device.

## Device

| Property | Value |
|---|---|
| Brand | the t.racks (Thomann house brand) / Musicrown |
| Model | DSP 4x4 Mini |
| USB VID:PID | `0168:0821` |
| USB class | HID, 64-byte interrupt transfers, Full-Speed (USB 1.1) |
| Channels | 4 balanced inputs / 4 balanced outputs |
| DSP | 32-bit, 48 kHz, 24-bit AD/DA |

## Protocol overview

Frames are carried inside 64-byte USB HID reports (interrupt transfers):

```
[10 02] [SRC] [DST] [LEN] [PAYLOAD...] [10 03] [CHK]
```

Checksum = XOR of LEN and all payload bytes. OUT endpoint 0x02 (host→device), IN endpoint 0x81 (device→host).

Key opcodes (see [analysis/protocol.md](analysis/protocol.md) for full reference):

| Opcode | Direction | Function |
|---|---|---|
| `0x10` | both | Init handshake |
| `0x12` | out | Activate / config load complete |
| `0x13` | both | Firmware/model string query |
| `0x14` | both | Active preset index |
| `0x15` | out | Delay display unit (ms/m/ft) |
| `0x20` / `0x21` | out | Load / store preset |
| `0x26` | out | Set preset name (14 chars max) |
| `0x27` / `0x24` | out/in | Read config page / response |
| `0x2c` | both | Device info (counter, lock status) |
| `0x2d` / `0x2f` | both/out | Submit PIN / set lock PIN |
| `0x30` | out | Output compressor (all 5 params) |
| `0x31` / `0x32` | out | Lo-pass / hi-pass crossover |
| `0x33` | out | Output parametric EQ band |
| `0x34` / `0x35` / `0x36` | out | Gain / mute / phase invert |
| `0x38` | out | Output delay (samples @ 48 kHz) |
| `0x39` | out | Test tone generator |
| `0x3a` / `0x3b` | out | Routing matrix / channel link |
| `0x3c` / `0x3d` | out | PEQ channel bypass / channel name |
| `0x3e` | out | Input noise gate |
| `0x40` | both | Level poll / 8-channel metering |

## Repository structure

```
minidsp/                  Python control package
  __main__.py             Entry point (delegates to cli.main)
  device.py               USB HID open/close, send/recv, config read
  protocol.py             Frame encoding/decoding, all command builders
  calibration.toml        Level meter calibration (REF_LEVEL + anchor points)
  cli.py                  CLI subcommands: dump, levels, mute, unmute

dspanalyze/               Protocol analysis toolchain
  cli.py                  Entry point: analyze, check, capture, diff-config, list-captures, calibrate
  calibrate.py            Level meter calibration tool (capture, show, apply, reset)
  protocol_config.toml    All protocol knowledge (opcodes, fields, value formats)
  decode.py               Frame → structured command decoder
  capture.py              tshark-based USB capture with device auto-detect
  check.py                Protocol assertion framework
  readers/                pcapng and Wireshark text export parsers
  output/                 claude / human / raw output formatters

tests/                    Protocol unit tests (pytest)
analysis/                 Reverse engineering reference
  protocol.md             Full protocol specification
  feature-list.md         DSP feature inventory with protocol status
  usb_captures/           Wireshark USBPcap captures (.pcapng + .meta.toml)
  resources/              Screenshots, manual PDF
```

## Related projects

- [miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt) — Qt-based GUI for this library
- [dsp-408-ui](https://github.com/Aeternitaas/dsp-408-ui) — Same Musicrown protocol over TCP for the DSP 408. Cross-referenced for shared encoding formulas (gain, frequency, Q).

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).

Not affiliated with Musicrown, the t.racks, or Thomann. Protocol reverse-engineered for interoperability purposes under applicable law.
