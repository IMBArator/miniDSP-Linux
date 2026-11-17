# miniDSP-Linux

Python library for the **the t.racks DSP 4x4 Mini** (Musicrown-based DSP processor) — full device control over USB HID, since no official Linux software exists. A Qt-based GUI is available at [miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt).

The `minidsp` package provides a complete Python API ([`DSPmini`](minidsp/device.py) class) covering every DSP opcode. A companion CLI utility and a protocol analysis toolkit (`dspanalyze`) are included.

The USB HID protocol was fully reverse-engineered from Wireshark captures. See [analysis/protocol.md](analysis/protocol.md) for the complete specification and [analysis/feature-list.md](analysis/feature-list.md) for the full feature inventory.

## Features

### Supported DSP Features

All commands are verified against real Wireshark captures on the device.

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
| Read stored presets without recalling them | `0x24` + `0x28` |
| `.unt` file save / restore (like the manufacturer editor) | `0x19` / `0x1a` / `0x23` / `0x25` / `0x04` |
| Device lock (set PIN / submit PIN) | `0x2f` / `0x2d` |
| Test tone generator (pink/white noise, sine 20Hz–20kHz) | `0x39` |
| Real-time level metering (8 ch + limiter mask) | `0x40` |

### CLI (`minidsp`)

A command-line utility for quick access to common operations — additional commands are added on demand:

```
dump                    Dump all DSP configuration parameters as tables
levels [--watch]        Snapshot live level meters (raw level + dBu + clip)
mute    [channel ...]   Mute input channel(s)
unmute  [channel ...]   Unmute input channel(s)
save-unt FILE           Save the stored presets to a .unt file (audio unchanged)
restore-unt FILE --yes  Write a .unt file to the device (rewrites presets, reboots)
unt-info FILE           Show a .unt file's header and presets (offline)
```

The `.unt` format is handled by `minidsp.unt.UntFile` (read, edit, write; unknown
bytes are kept), the transfer by `DSPmini.export_unt()` / `DSPmini.restore_unt()`.

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
- GNU make — runs the setup (on Windows: `winget install ezwinports.make`)

### Linux

- Kernel HID driver — communicates via `/dev/hidraw*` (no libusb needed)
- Read/write access to `/dev/hidraw*` (see [Permissions](#permissions))

### Windows

- No driver installation and no udev equivalent — Windows binds its built-in
  HID driver to the DSP automatically
- `make sync` installs [hidapi](https://pypi.org/project/hidapi/)
  automatically; it is only pulled in on Windows
- Wireshark with USBPcap is needed **only** for `dspanalyze capture`, not for
  controlling the device

## Installation

```bash
git clone https://github.com/IMBArator/miniDSP-Linux.git
cd miniDSP-Linux
make sync            # creates .venv and installs the dependencies
```

### Windows

Install uv (`winget install astral-sh.uv`) and GNU make
(`winget install ezwinports.make`), then run the same commands in
PowerShell — uv provisions Python itself:

```powershell
git clone https://github.com/IMBArator/miniDSP-Linux.git
cd miniDSP-Linux
make sync
uv run minidsp dump
```

Prefix the commands below with `uv run` (`uv run minidsp levels --watch`,
`uv run dspanalyze analyze ...`).

## Usage

### CLI

```bash
# Dump all DSP parameters (presets, gains, EQ, crossover, compressor, …)
minidsp dump

# Snapshot live level meters (all 8 channels: raw 24-bit level + dBu + clip)
minidsp levels

# Continuous level monitoring (Ctrl+C to stop)
minidsp levels --watch

# Log level readings to CSV for offline analysis
minidsp levels --watch --csv levels.csv

# Mute input channels 1 and 2
minidsp mute 1 2

# Unmute all input channels
minidsp unmute 1 2 3 4

# Save every stored preset to a .unt file, like the manufacturer editor
minidsp save-unt my-presets.unt

# Inspect a .unt file without a device
minidsp unt-info my-presets.unt

# Write a .unt file back to the device (keeps the device PIN; the DSP reboots)
minidsp restore-unt my-presets.unt --yes
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

# Regenerate the bundled factory-default JSON from an F00-load capture
dspanalyze extract-defaults analysis/usb_captures/capture_..._load_preset_f00.pcapng

# Calibrate level meters using a signal generator
dspanalyze calibrate capture 0       # capture at 0 dBu
dspanalyze calibrate show            # view points + errors
dspanalyze calibrate apply           # compute and write REF_LEVEL
```

See `Makefile` for pre-defined analysis workflows (`make analyze FILE=...`, `make diff-config FILE=...`, etc.).

## Permissions

### Linux

The tool communicates via `/dev/hidraw*`. By default this requires root. To allow regular users, create a udev rule:

```bash
sudo tee /etc/udev/rules.d/99-dspmini.rules << 'EOF'
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0168", ATTRS{idProduct}=="0821", MODE="0666"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Then reconnect the device.

### Windows

Nothing to configure — HID devices are accessible to normal users, so no
driver, no rule and no elevated shell are required. Only one process may talk
to the DSP at a time (enforced by a named mutex, the counterpart of the Linux
lock); a second one fails immediately with "already in use by another
process". That conflict is raised as `minidsp.device.DeviceBusyError`, an
`OSError` subclass, so a caller can distinguish "the device is busy" from
"the device is not there" and wait for it to be released.

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

Every opcode, with its direction and payload layout, is listed in the
[Known Register Map](analysis/protocol.md#known-register-map) of the protocol
specification.

## Development

To work on the code from a checkout (setup, tests, checks, builds and the
protocol-analysis tooling), see the [developer guide](docs/development.md);
`make help` lists every target. How changes get in is in
[CONTRIBUTING.md](CONTRIBUTING.md); the design, the module map and the
invariants are in [docs/architecture.md](docs/architecture.md).

## Related projects

- [miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt) — Qt-based GUI for this library
- [dsp-408-ui](https://github.com/Aeternitaas/dsp-408-ui) — Same Musicrown protocol over TCP for the DSP 408. Cross-referenced for shared encoding formulas (gain, frequency, Q).

## Changelog

Release notes are generated from [Conventional Commits](https://www.conventionalcommits.org/) with [git-cliff](https://git-cliff.org/) and recorded in [CHANGELOG.md](CHANGELOG.md). The changelog follows the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format, and version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## License

This project is licensed under the [GNU General Public License v3.0 or later](LICENSE) (GPL-3.0-or-later).

Not affiliated with Musicrown, the t.racks, or Thomann. Protocol reverse-engineered for interoperability purposes under applicable law.
