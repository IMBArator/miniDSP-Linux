# dspanalyze — Usage Guide

USB HID protocol analysis toolchain for the t.racks DSP 4x4 Mini (Musicrown-based).

## Quick Start

```bash
# Install in dev mode
make install

# Analyze a capture with human-readable field decoding
python -m dspanalyze analyze analysis/usb_captures/capture.pcapng --decode

# Run protocol assertions against a capture
python -m dspanalyze check analysis/usb_captures/capture.pcapng
```

## Subcommands

### `analyze` — Decode and display capture data

```
dspanalyze analyze <file> [options]
```

| Flag | Description |
|------|-------------|
| `--format {claude,human,raw}` | Output format (default: `claude`) |
| `--output, -o <path>` | Write output to file instead of stdout |
| `--filter <hex,...>` | Show only specific opcodes (e.g. `0x34,0x35`) |
| `--exclude <hex,...>` | Exclude opcodes (e.g. `0x40` to hide polls) |
| `--summary` | Show only summary statistics, no full sequence |
| `--decode` | Show human-readable field values (dB, channel names, etc.) |
| `--no-meta` | Skip generating `.meta.toml` sidecar file |

**Examples:**

```bash
# Full decode with field values
python -m dspanalyze analyze capture.pcapng --format claude --decode

# Focus on gain and mute commands only
python -m dspanalyze analyze capture.pcapng --filter 0x34,0x35 --decode

# Hide level-polling noise to see commands clearly
python -m dspanalyze analyze capture.pcapng --exclude 0x40 --decode

# Quick overview of a capture
python -m dspanalyze analyze capture.pcapng --summary --decode

# Human-readable table for terminal review
python -m dspanalyze analyze capture.pcapng --format human --decode

# Raw hex for manual inspection
python -m dspanalyze analyze capture.pcapng --format raw
```

### `check` — Run protocol assertions

```
dspanalyze check <file> [options]
```

| Flag | Description |
|------|-------------|
| `--assertion <name\|all>` | Run a specific assertion or all (default: `all`) |
| `--list` | List available assertions with descriptions |
| `--verbose, -v` | Show passing assertions too (default: failures only) |

Returns non-zero exit code if any assertion fails.

**Available assertions (12):**

| Assertion | Applies To | Check |
|-----------|-----------|-------|
| `checksum_valid` | `*` | All frames have valid XOR checksums |
| `frame_structure` | `*` | All packets have parseable frame structure |
| `no_unknown_opcodes` | `*` | All opcodes recognized by config |
| `gain_range_0_400` | `*` | Gain values (0x34) in range 0-400 |
| `mute_values` | `*` | Mute states (0x35) are 0 or 1 |
| `channel_range` | `*` | Channel bytes 0-7 |
| `ack_follows_write` | `*` | Write commands get ACK within 3 packets |
| `startup_sequence` | `*startup*` | Init starts with 0x10→0x13→0x2c→0x22→0x14 |
| `config_pages_complete` | `*startup*` | Config reads cover all 9 pages (0-8) |
| `preset_names_30` | `*startup*` | Preset name reads cover all 30 slots |
| `gain_cal_0db` | `*from -60 to 0 dB*` | Sweep ends at raw 280 |
| `gain_cal_12db` | `*from -60 to +12 dB*` | Sweep ends at raw 400 |

Assertions match captures by filename glob pattern (shown in "Applies To" column).

**Examples:**

```bash
# Run all applicable assertions
python -m dspanalyze check capture.pcapng

# List assertions without running
python -m dspanalyze check capture.pcapng --list

# Run one specific assertion with verbose output
python -m dspanalyze check capture.pcapng --assertion checksum_valid -v
```

### `capture` — Capture USB traffic via tshark

```
dspanalyze capture [options]
```

| Flag | Description |
|------|-------------|
| `--output-dir <path>` | Output directory (default: `analysis/usb_captures`) |
| `--duration <seconds>` | Capture duration (default: until Ctrl+C) |
| `--interface <name>` | tshark capture interface (auto-detected if omitted) |
| `--description, -d <text>` | Feature being captured (saved to metadata) |
| `--notes, -n <text>` | Additional notes about the capture |
| `--device-address <int>` | USB device address (auto-detected on Linux) |
| `--detect` | Only detect device and list interfaces, don't capture |

Produces a `.pcapng` file and a `.meta.toml` sidecar in the output directory.

**Setup (Linux, one-time):**

```bash
make capture-enable    # loads usbmon, grants permissions
```

**Examples:**

```bash
# Auto-detect device and capture
python -m dspanalyze capture -d "gain sweep" -n "InA from -60 to +12 dB"

# Just detect device info without capturing
python -m dspanalyze capture --detect

# Timed capture
python -m dspanalyze capture --duration 30 -d "mute toggle test"

# Cleanup when done
make capture-disable
```

### `diff-config` — Compare config reads

```
dspanalyze diff-config <file>
```

Finds consecutive complete config reads (9 pages x 50 bytes = 450-byte blob) in a capture and shows byte-by-byte differences with field names. Useful for identifying which bytes change when a DSP parameter is adjusted.

**Example:**

```bash
# Capture with a parameter change between two startups
python -m dspanalyze diff-config startup_with_change.pcapng
```

### `list-captures` — List captures with metadata

```
dspanalyze list-captures [directory]
```

Default directory: `analysis/usb_captures`. Scans for `.txt`, `.pcapng`, `.pcap` files and shows metadata summaries.

## Output Formats

### `claude` (default)
Compact, structured format optimized for LLM consumption:
- Header with filename, packet count, duration
- Opcode histogram (e.g. `0x40(142) ACK(141) ...`)
- Warnings for unknown opcodes and checksum failures
- Collapsed poll cycles to save space
- Full hex for unknown opcodes

### `human`
Terminal-friendly table with fixed-width columns:
```
#       Time  Dir  Opcode  Name                Details
────────────────────────────────────────────────────
```

### `raw`
Minimal hex dump for manual inspection:
```
frame# timestamp direction hex_data
```

## Makefile Targets

| Target | Usage | Description |
|--------|-------|-------------|
| `install` | `make install` | Install package in dev mode |
| `test` | `make test` | Run pytest suite |
| `analyze` | `make analyze FILE="path"` | Claude format + decode |
| `analyze-raw` | `make analyze-raw FILE="path"` | Raw hex dump |
| `analyze-no-poll` | `make analyze-no-poll FILE="path"` | Claude format, no 0x40 polls |
| `analyze-human` | `make analyze-human FILE="path"` | Human table + decode |
| `analyze-summary` | `make analyze-summary FILE="path"` | Summary stats only |
| `diff-config` | `make diff-config FILE="path"` | Compare config reads |
| `analyze-all` | `make analyze-all` | Batch analyze all captures (summaries) |
| `check-all` | `make check-all` | Run assertions against all captures |
| `capture-enable` | `make capture-enable` | Load usbmon, grant permissions (sudo) |
| `capture-disable` | `make capture-disable` | Remove caps, unload usbmon (sudo) |

## Protocol Config (`protocol_config.toml`)

All protocol knowledge is centralized in `dspanalyze/protocol_config.toml`. This is the single source of truth for opcode definitions, field layouts, and value format converters.

### Adding a new opcode

Add a TOML block under `[opcodes]`:

```toml
[opcodes.0xNN]
name = "new_command"
direction = "out"          # "out", "in", or "both"
description = "What this command does"
verified = false           # Set true after capturing on real hardware

[opcodes.0xNN.fields.request]
channel = { offset = 1, size = 1, format = "channel" }
value = { offset = 2, size = 2, format = "gain_raw" }
```

### Value formats

Formats define how raw bytes convert to human-readable values. Key formats:

| Format | Description |
|--------|-------------|
| `channel` | 0-7 → InA, InB, InC, InD, Out1-4 |
| `gain_raw` | Dual-resolution: raw→dB with breakpoint at -20 dB |
| `mute_state` | 0=unmuted, 1=muted |
| `phase_state` | 0=normal, 1=inverted |
| `filter_type` | PEQ filter types (Peak, Shelf, LP, HP, AllPass) |
| `freq_log` | Logarithmic Hz encoding |
| `q_log` | Logarithmic Q factor |
| `peq_gain` | PEQ gain in dB |
| `delay_samples` | Delay in samples at 48 kHz |
| `slope_index` | Crossover slope types |
| `level_uint16` | Metering level → dB conversion |

## Typical Workflow

1. **Enable capture:** `make capture-enable`
2. **Capture:** `python -m dspanalyze capture -d "feature name" -n "notes"`
3. **Analyze:** `make analyze FILE="analysis/usb_captures/capture_xxx.pcapng"`
4. **Focus:** `make analyze-no-poll FILE="..."` to see commands without poll noise
5. **Validate:** `python -m dspanalyze check capture.pcapng`
6. **Compare configs:** `make diff-config FILE="..."` if a parameter was changed
7. **Update protocol:** Add new opcodes to `protocol_config.toml`, then to `analysis/protocol.md` and `minidsp/protocol.py`
8. **Verify:** `make check-all` to ensure no regressions
9. **Cleanup:** `make capture-disable`

## Supported Capture Formats

| Extension | Source | Reader |
|-----------|--------|--------|
| `.pcapng`, `.pcap` | tshark / Wireshark | `readers/pcapng.py` (subprocess) |
| `.txt` | Wireshark text export | `readers/wireshark_text.py` |

Both produce `RawPacket` objects with frame number, timestamp, direction, endpoint, and 64-byte HID data.
