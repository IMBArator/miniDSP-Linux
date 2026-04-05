# Preliminary Feature List: the t.racks DSP 4x4 Mini

Compiled from: manufacturer tool screenshots (`analysis/resources/`), PDF user manual, and our protocol reverse-engineering (`analysis/protocol.md`).

> **Note on cross-references:** The DSP 408 (Aeternitaas/dsp-408-ui) uses the same Musicrown protocol framing and some shared opcodes, but it is a larger device (8 outputs, Ethernet, GEQ, more PEQ bands). Features and parameter counts from that project should NOT be assumed to apply here. Only protocol-level encoding formulas (gain, frequency, Q) are likely shared.

---

## Hardware

- **4 inputs** (InA-InD): balanced 6.3mm TRS, +12 dBu, 20k ohm
- **4 outputs** (Out1-Out4): balanced 6.3mm TRS, +12 dBu, <500 ohm
- **USB-B** for PC control (USB 1.1 Full-Speed, HID class)
- **32-bit DSP**, 24-bit AD/DA, 48 kHz sampling rate
- **12V DC** external power, 160x150x40mm, 0.6 kg
- Front: 4 signal-present LEDs, USB port
- Back: 4x input jacks, 4x output jacks, DC power, power LED

---

## DSP Features

### 1. Input Channels (x4: InA, InB, InC, InD)

| Feature | Details | Protocol Status |
|---|---|---|
| **Gain** | -60.0 to +12.0 dB, dual resolution (0.5 dB/step below -20 dB, 0.1 dB/step above) | **Captured & implemented** (`0x34`) |
| **Mute** | Per-channel on/off | **Captured & implemented** (`0x35`) |
| **Phase Invert** | 180 degree polarity flip ("Normal" / "Inverse" button) | **Captured & implemented** (`0x36`) |
| **Noise Gate** | Per-input: Threshold, Attack, Hold, Release | **Captured & implemented** (`0x3E`) |
| **Level Meter** | Real-time level with clip indicator | **Captured & implemented** (`0x40`) |

**Gate parameters:**
- Threshold: -90.0 to 0.0 dB
- Attack: 1 to 999 ms
- Hold: 10 to 999 ms (raw 9–998)
- Release: 0 to 3000 ms (raw 0–2999)

**Signal chain (from Matrix tab):** GAIN -> GATE -> PHASE -> MUTE -> routing matrix

### 2. Output Channels (x4: Out1, Out2, Out3, Out4)

| Feature | Details | Protocol Status |
|---|---|---|
| **Gain** | -60.0 to +12.0 dB (same encoding as input) | **Captured & implemented** (`0x34`) |
| **Mute** | Per-channel on/off | **Captured & implemented** (`0x35`) |
| **Phase Invert** | 180 degree polarity flip | **Captured & implemented** (`0x36`) |
| **Compressor** | Per-output: Threshold, Attack, Ratio, Release, Knee | Visible in screenshots & manual; protocol unknown |
| **Output Delay** | Per-output, 0–680 ms in sample steps | **Captured & implemented** (`0x38`) |
| **Level Meter** | Real-time level with clip + limiter active indicators | **Captured & implemented** (`0x40`, limiter bitmask at byte 25) |

**Compressor parameters:**
- Threshold: -90.0 to 20 dB
- Attack: 1 to 999 ms
- Ratio: 1:1.0, 1:1.1, 1:1.3, 1:1.5, 1:1.7, 1:2.0, 1:2.5, 1:3.0, 1:3.5, 1:4.0, 1:5.0, 1:6.0, 1:8.0, 1:10.0, 1:20.0, limit
- Release: 10 to 3000 ms
- Knee: 0 to 12 dB (1 dB increments)

**Delay:**
- Range: 0.000 ms to 680.000 ms per output (raw 0–32640 samples at 48 kHz, ~0.02083 ms/step)
- Unit selector: ms, m (meters), ft (feet) — display-only, protocol always uses samples

**Signal chain (from Matrix tab):** XOVER -> PEQ -> GAIN -> COMP -> PHASE -> DELAY -> MUTE -> output

### 3. Parametric EQ (Output channels only)

The 4x4 Mini has PEQ on output channels only (no GEQ, no input EQ).

| Feature | Details | Protocol Status |
|---|---|---|
| **PEQ Bands** | 7 bands per output channel (visible in screenshots as bands 1-7) | Protocol: likely `0x33` (shared opcode); NOT yet captured |
| **Frequency** | ~20 Hz to 20 kHz | Encoding likely shared with DSP 408 (log-scale, raw 0-1000) |
| **Gain** | -12.0 to +12.0 dB, 0.1 dB resolution | Encoding likely shared: `dB = (value - 120) / 10.0` |
| **Q Factor** | Adjustable per band | Encoding likely shared (log-scale, raw 0-255) |
| **Per-band Bypass** | Individual band bypass toggle | Visible in screenshots |
| **EQ Bypass** | Global EQ bypass per channel | "EQ Bypass" button visible in screenshots |
| **EQ Reset** | Reset all bands to flat | "EQ Reset" button visible in screenshots |

**Filter types (from screenshots, 7 types):**
- Peak
- Low Shelf
- High Shelf
- Low Pass
- High Pass
- Allpass 1
- Allpass 2

**Display features:**
- Mag / Phase view toggle (level-vs-frequency or phase-vs-frequency)
- "SHOW ALL EQ" button to overlay all output channels' curves
- Interactive: drag corner points on the frequency response graph

### 4. Crossover Filters (per output channel)

| Feature | Details                                       | Protocol Status |
|---|-----------------------------------------------|---|
| **High-Pass** | 19.7 Hz to 20.16 kHz, Per-output, with bypass | **Captured & implemented** (`0x32`, raw 0–300) |
| **Low-Pass** | 19.7 Hz to 20.16 kHz, Per-output, with bypass | **Captured & implemented** (`0x31`, raw 0–300) |

**Slope types (from screenshots, 10 options):**
| Slope | Types available |
|---|---|
| -6 dB/oct | BW (Butterworth), BL (Bessel) |
| -12 dB/oct | BW, BL, LK (Linkwitz-Riley) |
| -18 dB/oct | BW, BL |
| -24 dB/oct | BW, BL, LK |

Note: The DSP 408 has 20 slope types (up to -48 dB/oct). The 4x4 Mini has only 10.

### 5. Routing Matrix (4x4)

| Feature | Details | Protocol Status |
|---|---|---|
| **4x4 Matrix** | Any combination of inputs routable to any output | Protocol: likely `0x3a`; NOT yet captured |
| **Multi-input mixing** | Multiple inputs can feed one output | Expected bitmask-based |

From the screenshots: columns are outputs, rows are inputs. Green = routed.

### 6. Channel Linking

| Feature | Details | Protocol Status |
|---|---|---|
| **Input linking** | Link settings of input channels together | **Captured & documented** (`0x3b` + `0x2a`) |
| **Output linking** | Link settings of output channels together | **Captured & documented** (`0x3b` + `0x2a`) |

**Key behaviors (from screenshots.md notes):**
- Links **settings only**, not audio streams
- Syncing done by DSP firmware, not the config tool
- When linking, first channel is master (settings copied to slaves)
- Client must re-read DSP config after linking to update UI

### 7. Preset Management

| Feature | Details | Protocol Status |
|---|---|---|
| **User presets** | U01-U30 (30 slots) | Names: **captured** (`0x29`); load/store: likely `0x20`/`0x21`/`0x26`, NOT captured |
| **Factory preset** | F00 (read-only) | Visible in screenshots |
| **Preset names** | Max 15 characters. **Length check critical to avoid crashing DSP!** | From screenshots.md notes |
| **Quick access** | Address, Preset, Store, Recall buttons in status bar | Visible in screenshots |
| **File load/save** | .unt preset files on PC | .unt format partially reverse-engineered |

### 8. Test Tone Generator

| Feature | Details | Protocol Status |
|---|---|---|
| **Analog Input** | Normal operation (default) | N/A |
| **Pink Noise** | Internal generator | Protocol unknown |
| **White Noise** | Internal generator | Protocol unknown |
| **Sine Wave** | Selectable frequency (20 Hz dropdown visible) | Protocol unknown |

### 9. System / Utility

| Feature | Details | Protocol Status |
|---|---|---|
| **Device Lock** | Password protection | Protocol unknown |
| **Copy settings** | Copy channel parameters between channels | Menu item visible |
| **Device Address/ID** | Identification (ID: 1 in screenshots) | Visible in status bar |
| **Online/Offline** | Connection status | **Implemented** |
| **Language** | English / German | Software-only |

---

## Implementation Status Summary

### Captured & implemented in our Python tool:
- Gain (input + output)
- Mute (input + output)
- Phase invert (input + output)
- Noise gate (input: attack, release, hold, threshold)
- Output delay (0–680 ms, sample-based)
- Crossover hi/lo pass (raw 0–300, 19.7 Hz–20.16 kHz)
- Level metering (8 channels + limiter indicators)
- Config read (9 pages)
- Preset name reading (30 slots)
- Initialization sequence

### Protocol likely known but NOT yet or not fully captured on our device:
- PEQ (`0x33`) - 7 bands per output
- Matrix routing (`0x3a`)
- Preset load/store (`0x20`/`0x21`/`0x26`)
- Channel linking (`0x3b`/`0x2a`)

### Completely unknown protocol:
- Compressor settings (output)
- Test Tone Generator
- Device Lock/Password (careful. DO NOT TOUCH! could lock us out.)
