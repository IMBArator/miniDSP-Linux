# miniDSP-Linux

Linux control tool for the **T.racks DSPmini 4x4** (Musicrown-based DSP processor). Provides a PySide6 GUI and CLI for gain control, muting, and real-time level metering over USB HID — no official Linux software required.

The USB HID protocol was fully reverse-engineered from Wireshark captures. See [analysis/protocol.md](analysis/protocol.md) for the complete protocol specification.

## Features

- **GUI** with per-channel gain faders, mute buttons, dB-scaled level meters, and compressor/limiter activity LEDs
- **Real-time level monitoring** for 4 input + 4 output channels (~7 Hz polling)
- **Startup config read** — faders and mute buttons load the device's current state on connect
- **Auto-reconnect** on USB disconnect
- **CLI** for scripted mute/unmute operations
- Zero native dependencies — communicates via `/dev/hidraw` (kernel HID driver)

## Requirements

- Python 3.11+
- PySide6 (GUI only)
- Linux with kernel HID driver (no additional USB libraries needed)
- Read/write access to `/dev/hidraw*` (see [Permissions](#permissions))

## Installation

```bash
git clone <repo-url> miniDSP-Linux
cd miniDSP-Linux
python3 -m venv .venv
source .venv/bin/activate
pip install PySide6
```

## Usage

### GUI

```bash
python3 -m minidsp --gui
```

### CLI

```bash
# Mute input channels 1 and 2
python3 -m minidsp mute 1 2

# Unmute all input channels
python3 -m minidsp unmute 1 2 3 4
```

## Permissions

The tool communicates with the DSP via `/dev/hidraw*`. By default this requires root access. To allow regular users, create a udev rule:

```bash
sudo tee /etc/udev/rules.d/99-dspmini.rules << 'EOF'
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0168", ATTRS{idProduct}=="0821", MODE="0666"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Then reconnect the device.

## Device

| Property | Value |
|---|---|
| Manufacturer | Musicrown (T.racks / the t.racks) |
| Product | DSPmini 4x4 |
| USB VID:PID | `0168:0821` |
| USB class | HID, 64-byte interrupt transfers |
| Channels | 4 in / 4 out |

## Protocol

The device uses a serial-style framing protocol inside 64-byte USB HID reports:

```
[10 02] [SRC] [DST] [LEN] [PAYLOAD...] [10 03] [CHK]
```

Checksum is XOR of LEN and all payload bytes. Key commands:

| Opcode | Function |
|---|---|
| `0x10` | Init handshake |
| `0x27` | Read config page (9 pages x 50 bytes) |
| `0x34` | Set gain (raw 0-400, dual-resolution dB mapping) |
| `0x35` | Mute/unmute channel |
| `0x40` | Poll levels (returns 8-channel metering data) |
| `0x12` | Activate / config load complete |

Full protocol documentation: [analysis/protocol.md](analysis/protocol.md)

## Repository Structure

```
minidsp/              Python package
  gui/                PySide6 GUI (gain faders, meters, mute, compressor LEDs)
  device.py           USB HID communication
  protocol.py         Protocol encoding/decoding
  cli.py              Command-line interface
tests/                Protocol unit tests
analysis/             Reverse engineering artifacts
  protocol.md         Full protocol specification
  usb_captures/       Wireshark USBPcap exports
```

## Related Projects

- [dsp-408-ui](https://github.com/Aeternitaas/dsp-408-ui) — Same Musicrown protocol over TCP for the DSP 408. Cross-referenced for PEQ, GEQ, crossover, and routing commands.

## License

This project is not affiliated with Musicrown, the t.racks, or Thomann.
