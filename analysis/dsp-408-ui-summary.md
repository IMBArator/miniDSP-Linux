# dsp-408-ui Project Summary

Comprehensive reference document for the [Aeternitaas/dsp-408-ui](https://github.com/Aeternitaas/dsp-408-ui) repository. Produced by thorough code-level analysis of every source file.

---

## 1. Project Overview and Goals

**dsp-408-ui** is a cross-platform Flutter application that provides a GUI for controlling the **t.racks DSP 408** digital signal processor over a local network. It reverse-engineers the proprietary TCP protocol used by the official "t.racks DSP Processor Editor" Windows software from Thomann and reimplements it in Dart.

**Key goals:**
- Replace the Windows-only vendor software with a modern, multi-platform alternative
- Support Windows, Linux, Android, macOS, and iOS
- Provide mixing-grade control (gain, EQ, matrix routing, metering) from any device on the LAN

**License:** GPL v3

**Version:** 0.2.0

**Tech stack:** Flutter 3.38.9, Dart 3.10.8, Provider state management, Monokai color theme

---

## 2. Device Info: t.racks DSP 408

| Property | Value |
|---|---|
| **Inputs** | 4 analog (In A, In B, In C, In D) |
| **Outputs** | 8 analog (Out 1 through Out 8) |
| **Connectivity** | Ethernet (TCP/IP), default port **9761** |
| **Default IP** | 192.168.3.100 (hardcoded in UI) |
| **Presets** | 20 user presets (U01-U20) |
| **Preset name length** | 14 characters (space-padded) |
| **GEQ** | 31-band ISO 1/3-octave, inputs only |
| **PEQ** | 8 bands per input, 9 bands per output |
| **Crossover** | Hi-pass and lo-pass filters per channel |
| **Matrix** | 4x8 (any input to any output) |
| **Metering** | 12-channel real-time levels (float16) |

**Comparison with DSP 4x4 Mini:**

| Feature | DSP 408 | DSP 4x4 Mini |
|---|---|---|
| **Connectivity** | Ethernet (TCP) | USB HID |
| **Inputs** | 4 | 4 |
| **Outputs** | 8 | 4 |
| **Transport** | TCP socket on port 9761 | 64-byte HID reports |
| **Config pages** | 29 (0x00-0x1C) | 9 |
| **Presets** | 20 | 30 |
| **GEQ bands** | 31 | Unknown (likely 31) |
| **PEQ input bands** | 8 | Unknown |
| **PEQ output bands** | 9 | Unknown |

---

## 3. Protocol Overview

Communication is over TCP. The host sends command frames, the device responds with response frames. A keepalive poll (cmd `0x40`) is sent every 5-300 ms (configurable, default 300 ms) to request meter levels and keep the connection alive.

The protocol is **request-response**: one command is sent, then the host waits for a response before sending the next. A command queue with 500 ms timeout handles this serialization. Commands are enqueued and sent one at a time.

---

## 4. Frame Format and Checksum

### Frame structure

```
[10] [02] [SRC] [DST] [LEN] [PAYLOAD...] [10] [03] [XOR_CHK]
```

| Field | Size | Description |
|---|---|---|
| `10 02` | 2 bytes | Start-of-frame delimiter |
| SRC | 1 byte | Source: `0x00` = host, `0x01` = device |
| DST | 1 byte | Destination: `0x01` = device, `0x00` = host |
| LEN | 1 byte | Length of payload (in bytes) |
| PAYLOAD | LEN bytes | Command byte + parameters |
| `10 03` | 2 bytes | End-of-frame delimiter |
| XOR_CHK | 1 byte | XOR checksum |

**Note on SRC/DST:** In practice, outgoing (host-to-device) frames use `SRC=0x00 DST=0x01`. Response frames from the device use `SRC=0x01 DST=0x00` -- the code checks `data[2] == 0x01` to identify responses.

### Checksum calculation

The checksum is computed as XOR of the SRC, DST, LEN, and all payload bytes, starting with an initial value of 1:

```dart
int calculateChecksum(List<int> dataBytes) {
  int checksum = 1;
  for (int byte in dataBytes) {
    checksum ^= byte;
  }
  return checksum;
}
```

Where `dataBytes` = `[SRC, DST, LEN, ...PAYLOAD]` (everything between `10 02` and `10 03`).

**Example:** Handshake command `10 02 00 01 01 10 10 03 11`
- dataBytes = `[0x00, 0x01, 0x01, 0x10]`
- checksum = `1 ^ 0x00 ^ 0x01 ^ 0x01 ^ 0x10 = 0x11`

---

## 5. All Discovered Opcodes

### Outgoing commands (host to device)

| Opcode | Name | Payload | Description |
|---|---|---|---|
| `0x10` | Handshake | 1 byte: `0x10` | Initial connection handshake. Sent first after TCP connect. |
| `0x12` | Status query / Activate config | 1 byte: `0x12` | Sent after config dump completes. Returns active preset state. |
| `0x13` | Device info request | 1 byte: `0x13` | Requests firmware/device name string. |
| `0x14` | Unknown loading cmd | 1 byte: `0x14` | Sent during initialization. Purpose not fully understood. Possibly active preset index. |
| `0x20` | Load preset | 2 bytes: `0x20 [slot]` | Activates preset by slot (1-based). |
| `0x21` | Store preset to slot | 2 bytes: `0x21 [slot]` | Saves current config to preset slot (1-based). |
| `0x22` | Unknown loading cmd | 1 byte: `0x22` | Sent during initialization. Purpose not fully understood. Possibly preset header. |
| `0x26` | Store preset name | 15 bytes: `0x26 [14-char name]` | Sets the name for the next store operation. Name is space-padded to exactly 14 characters. |
| `0x27` | Config dump request | 2 bytes: `0x27 [page]` | Requests config page (0x00-0x1C, 29 pages total). |
| `0x29` | Read preset name | 2 bytes: `0x29 [slot]` | Reads name of preset at slot (0-based). 20 slots (0x00-0x13). |
| `0x2c` | Request all presets | 1 byte: `0x2c` | Requests preset count / initiates preset enumeration. |
| `0x31` | Lo-pass filter | 5 bytes: `0x31 [ch] [freq_lo] [freq_hi] [slope]` | Sets lo-pass crossover filter. |
| `0x32` | Hi-pass filter | 5 bytes: `0x32 [ch] [freq_lo] [freq_hi] [enable]` | Sets hi-pass crossover filter. |
| `0x33` | PEQ band | 10 bytes: `0x33 [ch] [band] [gain] [00] [freq_lo] [freq_hi] [Q] [type] [bypass]` | Sets parametric EQ band. |
| `0x34` | Gain | 4 bytes: `0x34 [ch] [val_lo] [val_hi]` | Sets channel gain (LE16). |
| `0x35` | Mute | 3 bytes: `0x35 [ch] [mute]` | Sets channel mute (0x00=unmute, 0x01=mute). |
| `0x3a` | Matrix routing | 3 bytes: `0x3a [output] [input_bitmask]` | Sets input routing for an output channel. |
| `0x40` | Keepalive / meter request | 1 byte: `0x40` | Polls for meter levels. |
| `0x48` | GEQ band | 5 bytes: `0x48 [ch] [band] [value] [00]` | Sets graphic EQ band. |

### Response commands (device to host)

| Opcode | Name | Description |
|---|---|---|
| `0x13` | Device info | ASCII device name string in payload. |
| `0x24` | Config chunk | Response to `0x27`. Contains `[page_index] [data...]`. 29 chunks total. |
| `0x29` | Preset name | Response to `0x29`. Contains `[slot_index] [name_ascii...]`. |
| `0x2c` | Preset count | Response to `0x2c`. Contains preset count byte. |
| `0x40` | Meter levels | Response to keepalive. 12 channels of float16 meter data. |

---

## 6. Channel Indexing

Channels are indexed 0x00-0x0B in command payloads:

| Index | Channel |
|---|---|
| `0x00` | In A |
| `0x01` | In B |
| `0x02` | In C |
| `0x03` | In D |
| `0x04` | Out 1 |
| `0x05` | Out 2 |
| `0x06` | Out 3 |
| `0x07` | Out 4 |
| `0x08` | Out 5 |
| `0x09` | Out 6 |
| `0x0A` | Out 7 |
| `0x0B` | Out 8 |

---

## 7. Gain Encoding (Dual Resolution)

The gain command (`0x34`) uses a 2-byte LE16 value with **dual resolution**:

### Value to dB conversion

```
dB = (value - 280) / 10.0
```

This formula is used for decoding. The value 280 corresponds to 0.0 dB.

### dB to value conversion (with dual resolution)

```dart
int gainDbToValue(double dB) {
  if (dB < -20.0) {
    // Coarse range: 0.5 dB resolution (2 units per dB)
    return ((dB + 60) * 2).round();
  } else {
    // Fine range: 0.1 dB resolution (10 units per dB)
    return (80 + (dB + 20) * 10).round();
  }
}
```

### Range

| Parameter | Value |
|---|---|
| Minimum | -60.0 dB |
| Maximum | +12.0 dB |
| Coarse range | -60.0 to -20.0 dB, 0.5 dB steps |
| Fine range | -20.0 to +12.0 dB, 0.1 dB steps |
| 0 dB value | 280 (0x0118) |

### Command format

```
10 02 00 01 04 34 [channel] [value_lo] [value_hi] 10 03 [checksum]
```

LEN = `0x04` (4 payload bytes: cmd + channel + value_lo + value_hi).

---

## 8. Mute Command

### Command format

```
10 02 00 01 03 35 [channel] [mute_flag] 10 03 [checksum]
```

- `mute_flag`: `0x01` = muted, `0x00` = unmuted
- All 12 channels (inputs + outputs) are supported

---

## 9. GEQ (Graphic Equalizer)

### Specifications

- **31-band** ISO 1/3-octave graphic EQ
- **Inputs only** (In A, In B, In C, In D)
- Band indices: 0x00 to 0x1E (0-30)

### Frequency list (31 bands, Hz)

```
20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160,
200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600,
2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000
```

### Value encoding

```
byte = (dB * 10) + 120
dB = (byte - 120) / 10.0
```

| Parameter | Value |
|---|---|
| Range | -12.0 to +12.0 dB |
| Resolution | 0.1 dB |
| Byte range | 0x00 (0) to 0xF0 (240) |
| 0 dB value | 120 (0x78) |

### Command format

```
10 02 00 01 05 48 [channel] [band] [value] 00 10 03 [checksum]
```

LEN = `0x05` (5 payload bytes). The trailing `0x00` byte is always present.

---

## 10. PEQ (Parametric Equalizer)

### Specifications

- **Inputs:** 8 bands per channel (bands 0-7)
- **Outputs:** 9 bands per channel (bands 0-8)
- Available on all 12 channels

### Frequency encoding (log scale)

```
freq_hz = 19.70 * (20160 / 19.70) ^ (raw / 1000)
raw = log(freq_hz / 19.70) / log(20160 / 19.70) * 1000
```

| Parameter | Value |
|---|---|
| Minimum frequency | 19.70 Hz |
| Maximum frequency | 20160 Hz |
| Raw value range | 0-1000 |
| Frequency ratio | 20160 / 19.70 = 1023.35... |

### Q encoding (log scale)

```
Q = 0.40 * 320 ^ (raw / 255)
raw = log(Q / 0.40) / log(320) * 255
```

| Parameter | Value |
|---|---|
| Minimum Q | 0.40 |
| Maximum Q | 128.0 |
| Raw value range | 0-255 |
| Q ratio | 128.0 / 0.40 = 320 |

### Gain encoding

Same as GEQ: `dB = (value - 120) / 10.0`, range -12.0 to +12.0 dB.

### Filter types

| Index | Type |
|---|---|
| 0 | Peak (parametric) |
| 1 | Low Shelf |
| 2 | High Shelf |
| 3 | LP -6dB |
| 4 | LP -12dB |
| 5 | HP -6dB |
| 6 | HP -12dB |
| 7 | All Pass 1 |
| 8 | All Pass 2 |

### Command format

```
10 02 00 01 0a 33 [ch] [band] [gain] [00] [freq_lo] [freq_hi] [Q] [type] [bypass] 10 03 [checksum]
```

LEN = `0x0a` (10 payload bytes).
- `freq_lo`, `freq_hi`: LE16 raw frequency value
- `bypass`: `0x01` = bypassed, `0x00` = active

### Default PEQ frequencies (Hz)

**Inputs (8 bands):** 50.8, 101.5, 203.1, 500.0, 1000.0, 2000.0, 5040.0, 10080.0

**Outputs (9 bands):** 40.3, 84.4, 176.8, 370.3, 757.9, 1590.0, 3320.0, 6810.0, 14250.0

---

## 11. Crossover Filters (Hi-Pass / Lo-Pass)

### Hi-pass filter (cmd `0x32`)

```
10 02 00 01 05 32 [ch] [freq_lo] [freq_hi] [enable] 10 03 [checksum]
```

- `enable`: `0x01` = on, `0x00` = off
- Frequency uses the same PEQ log-scale encoding (raw 0-1000)
- Available on all 12 channels

### Lo-pass filter (cmd `0x31`)

```
10 02 00 01 05 31 [ch] [freq_lo] [freq_hi] [slope] 10 03 [checksum]
```

- `slope`: index into the crossover slope type table
- When disabled, the app sends `freq=1000` (maximum = 20160 Hz, effectively passthrough)

### Crossover slope types (20 types)

| Index | Name | Index | Name |
|---|---|---|---|
| 0 | BW -6 | 10 | LR -36 |
| 1 | BW -12 | 11 | LR -48 |
| 2 | BW -18 | 12 | BS -6 |
| 3 | BW -24 | 13 | BS -12 |
| 4 | BW -30 | 14 | BS -18 |
| 5 | BW -36 | 15 | BS -24 |
| 6 | BW -42 | 16 | BS -30 |
| 7 | BW -48 | 17 | BS -36 |
| 8 | LR -12 | 18 | BS -42 |
| 9 | LR -24 | 19 | BS -48 |

BW = Butterworth, LR = Linkwitz-Riley, BS = Bessel

---

## 12. Matrix Routing (cmd `0x3a`)

### Command format

```
10 02 00 01 03 3a [output_byte] [input_bitmask] 10 03 [checksum]
```

### Output byte mapping

| Output | Byte |
|---|---|
| Out 1 | `0x04` |
| Out 2 | `0x05` |
| Out 3 | `0x06` |
| Out 4 | `0x07` |
| Out 5 | `0x08` |
| Out 6 | `0x09` |
| Out 7 | `0x0A` |
| Out 8 | `0x0B` |

Note: output bytes match the standard channel indices (0x04-0x0B).

### Input bitmask

| Input | Bit |
|---|---|
| In A | `0x01` |
| In B | `0x02` |
| In C | `0x04` |
| In D | `0x08` |

Multiple inputs can be mixed to a single output by OR-ing bits. For example, In A + In C to Out 1: `0x3a 0x04 0x05`.

---

## 13. Metering / Levels (cmd `0x40`)

### Keepalive request

```
10 02 00 01 01 40 10 03 41
```

### Response format

Response payload starts at byte 6 (after `10 02 01 00 [len] 40`).

12 channels, 3 bytes per channel = 36 bytes of meter data:

```
[float16_lo] [float16_hi] [peak_byte]
```

Channel order: In A, In B, In C, In D, Out 1, Out 2, Out 3, Out 4, Out 5, Out 6, Out 7, Out 8

### Float16 encoding (IEEE 754 half-precision, little-endian)

```
value = low_byte | (high_byte << 8)
sign = (value >> 15) & 1
exponent = (value >> 10) & 0x1F
mantissa = value & 0x3FF

if exponent == 0:       subnormal: result = (mantissa / 1024) * 2^-14
elif exponent == 31:    inf/NaN
else:                   result = (1 + mantissa / 1024) * 2^(exponent - 15)
```

### Meter level ranges

| Condition | Linear value | Approximate dB |
|---|---|---|
| Muted/off (noise floor) | ~0.00009 | -81 dB |
| Channel on, no audio | ~0.4-0.55 | -6 to -5 dB |
| Active signal | 0.5-2.0+ | -6 to +6 dB |
| Noise floor threshold (UI) | 0.55 | -5.2 dB |
| Clipping (UI max) | 2.0 | +6 dB |

The device returns `0xFF 0xFF` (NaN) for channels during PEQ recalculation.

---

## 14. Config Dump Structure (cmd `0x27` / response `0x24`)

### Overview

The full device configuration is read via 29 paginated requests (`0x27 [page]`, pages 0x00 through 0x1C). Each response is a `0x24` chunk. The chunks are reassembled into a contiguous byte stream for parsing.

### Page count and reassembly

- **29 pages** (sub-indices 0x00 to 0x1C)
- Each response: `10 02 01 00 [len] 24 [page_index] [data...] 10 03 [checksum]`
- Data per chunk: `len - 2` bytes (subtract cmd byte and page index byte)
- Most chunks contain ~50 bytes of data (LEN = 0x34 = 52 for most, 0x32 = 50 for the last)

### Global header (first 16 bytes of reassembled stream)

| Offset | Size | Description |
|---|---|---|
| 0 | 2 | Flags/version (0xFFFF for default) |
| 2 | 14 | Active preset name (ASCII, space-padded to 14 chars) |

### Input channel record (140 bytes total: 4-byte record header + 136 bytes data)

Record header (before each channel except InA): `[00 00] [ch_bitmask LE16]`

Channel bitmasks: InA=0x0000 (embedded in global header), InB=0x0001, InC=0x0002, InD=0x0004

**Data layout (136 bytes from channel name):**

| Offset from name | Size | Description |
|---|---|---|
| 0 | 8 | Channel name ASCII + null padding ("InA\0\0\0\0\0") |
| 8 | 2 | Unknown1 (always 0x0000) |
| 10 | 2 | Level1 LE16 (always 99 = 0x0063) |
| 12 | 2 | Level2 LE16 (always 99 = 0x0063) |
| 14 | 2 | Unknown2 (always 0x0000) |
| 16 | 62 | GEQ: 31 bands x 2 bytes LE16 (encoding: dB = (val-120)/10.0) |
| 78 | 48 | PEQ: 8 bands x 6 bytes (see PEQ band format below) |
| 126 | 10 | HPF/LPF filter data (see input filter format below) |

**PEQ band format (6 bytes per band in config dump):**

| Offset | Size | Description |
|---|---|---|
| 0 | 2 | Gain LE16 (dB = (val-120)/10.0) |
| 2 | 2 | Frequency LE16 (raw, same log-scale encoding as PEQ command) |
| 4 | 1 | Q (raw, 0-255) |
| 5 | 1 | Type (0-8) |

**Input filter format (10 bytes):**

| Offset | Size | Description |
|---|---|---|
| 0 | 2 | HPF frequency LE16 (0 = disabled) |
| 2 | 2 | HPF slope/type LE16 |
| 4 | 2 | LPF frequency LE16 (0 = disabled) |
| 6 | 2 | LPF slope/type LE16 |
| 8 | 2 | Padding (0x0000) |

### Output channel record (104 bytes total: 4-byte record header + 100 bytes data)

Record header: `[00 00] [ch_bitmask LE16]`

Channel bitmasks: Out1=0x0008, Out2=0x0001, Out3=0x0002, Out4=0x0004, Out5=0x0008, Out6=0x0010, Out7=0x0020, Out8=0x0040

**Data layout (100 bytes from channel name):**

| Offset from name | Size | Description |
|---|---|---|
| 0 | 8 | Channel name ASCII + null padding ("Out1\0\0\0\0") |
| 8 | 2 | Config flags LE16 (varies: 5, 10, 15) |
| 10 | 8 | Source routing: 4x LE16 levels (one per input, default 0x0118 = 280) |
| 18 | 6 | HPF/LPF: [HPF freq LE16] [LPF freq LE16] [HPF slope byte] [LPF slope byte] |
| 24 | 54 | PEQ: 9 bands x 6 bytes (same format as input PEQ) |
| 78 | 22 | Post-PEQ tail (see output tail format below) |

**Output tail format (22 bytes):**

| Offset | Size | Description |
|---|---|---|
| 0 | 2 | Null separator (0x0000) |
| 2 | 8 | Limiter/compressor block A: [threshold? LE16] [ratio? LE16] [attack? LE16] [release? LE16] |
| 10 | 8 | Limiter/compressor block B (duplicate of A) |
| 18 | 2 | Output level LE16 (default 0x0118 = 280 = 0.0 dB) |
| 20 | 2 | Padding (0x0000) |

### Global trailer

After the Out 8 record, remaining bytes contain global routing/config data. The exact structure is not yet fully understood.

### Matrix routing in config dump

For each output channel, the routing bitmask is found at `name_offset + 8` (the first byte after the 8-byte name). This is a bitmask using the same encoding as the `0x3a` command: `0x01=In A, 0x02=In B, 0x04=In C, 0x08=In D`.

The code uses a different approach: it reads the byte at `channel_name_offset + 8` for the flags, which contains the routing bitmask.

---

## 15. Preset Management

### Load preset (cmd `0x20`)

```
10 02 00 01 02 20 [1-based-slot] 10 03 [checksum]
```

Full load sequence:
1. Send load preset command (`0x20`)
2. Send 29 config dump commands (`0x27 [0x00]` through `0x27 [0x1C]`)
3. Send 2 status queries (`0x12`)
4. Parse all `0x24` responses to update local state

### Store/save preset

Two-step process:

**Step 1: Set preset name (cmd `0x26`)**
```
10 02 00 01 0f 26 [14 ASCII chars, space-padded] 10 03 [checksum]
```
LEN = `0x0f` (15 bytes: cmd + 14 name chars).

**Step 2: Store to slot (cmd `0x21`)**
```
10 02 00 01 02 21 [1-based-slot] 10 03 [checksum]
```

Full save sequence:
1. Send store name command (`0x26`)
2. Send store slot command (`0x21`)
3. Send 2 status queries (`0x12`)

### Read preset names (cmd `0x29`)

```
10 02 00 01 02 29 [0-based-slot] 10 03 [checksum]
```

20 presets, slots 0x00-0x13. Response contains ASCII name.

### Request preset count (cmd `0x2c`)

```
10 02 00 01 01 2c 10 03 2d
```

Response contains a count byte at offset 7.

---

## 16. Initialization Sequence

On connection, the app sends the following commands in order (50 ms delay between each response/next-send):

1. **Handshake** (`0x10`)
2. **Handshake** again (from command queue)
3. **Device info request** (`0x13`)
4. **Request all presets** (`0x2c`)
5. **Unknown command** (`0x22`) -- possibly preset header
6. **Unknown command** (`0x14`) -- possibly active preset index
7. **Read 20 preset names** (`0x29 [0x00]` through `0x29 [0x13]`)
8. **Config dump** (`0x27 [0x00]` through `0x27 [0x1C]`) -- 29 commands
9. **Status queries** (`0x12`) x2
10. **Start keepalive** (`0x40` every 300 ms)

Total initialization commands: ~56 commands.

---

## 17. What is NOT Yet Reverse-Engineered

The following features are mentioned as "in active development" or have unexplored protocol regions:

| Feature | Status |
|---|---|
| **Phase invert** | UI toggle exists but protocol command NOT implemented (state is local-only) |
| **Matrix volume attenuation** | UI for per-crossing-point dB gain exists but no protocol command implemented |
| **Gate** | Tab placeholder only ("Gate Tab"), no protocol work |
| **Compressor** | Tab placeholder only ("Comp Tab"), no protocol work |
| **Limiter** | Tab placeholder only ("Limit Tab"), no protocol work. Config dump shows 2x 8-byte blocks per output that may be limiter data but values are not decoded. |
| **Delay** | Tab placeholder only ("Delay Tab"), no protocol work |
| **Channel linking** | Not explored at all (see section 18) |
| **Output post-PEQ tail** | 22 bytes partially decoded. The duplicate 8-byte blocks (values: 49, 499, 0, 220) are suspected to be limiter/compressor parameters but not confirmed. |
| **Global trailer** | Bytes after Out 8's record in the config dump are not decoded. |
| **Input header fields** | The Level1/Level2 values (always 99) at input name+10..13 are not understood. |
| **Output config flags** | The 2-byte flags at output name+8 (values like 5, 10, 15) are not understood. |
| **DSP 204 support** | Mentioned in README as "probably doesn't work yet" |

---

## 18. Channel Linking Search Results

A thorough search of the entire dsp-408-ui codebase found **NO references** to channel linking functionality:

- **Opcodes `0x3b` and `0x2a`:** NOT found as command opcodes anywhere. The bytes `0x3b` and `0x2a` appear only as **checksum values** in pre-computed command arrays (e.g., `0x10, 0x03, 0x3b` is the footer+checksum of the "Get preset 16" command, and `0x10, 0x03, 0x2a` is the footer+checksum of the "Get preset 1" and "Config dump page 0x0f" commands).

- **Keywords searched:** link, pair, gang, stereo, couple, slave, master, grouped -- **NONE found** in any source code, protocol analysis scripts, comments, or documentation (excluding generic hits like GPL license text, HTML link tags, and CMake `target_link_libraries`).

- **UI code:** No channel linking or pairing UI elements exist anywhere.

- **Analysis scripts (analyze2.py through analyze5.py, ap_final.py):** These scripts analyze config dump structure but contain no references to linking. The only tangentially related comment is in `analyze5.py` line 130: "The two blocks are identical -> possibly stereo pair or some redundancy" -- referring to the duplicate 8-byte limiter blocks in the output tail, not to channel linking.

- **No GitHub issues or PRs** could be checked (gh CLI not available), but no references exist in the code itself.

**Conclusion:** The DSP 408 UI project has not discovered or implemented anything related to channel linking. The opcodes `0x3b` (channel link state) and `0x2a` (unknown pre-link command) that we found on the DSP 4x4 Mini are completely absent from this codebase.

---

## 19. Differences Between DSP 408 and DSP 4x4 Mini

Based on comparing the dsp-408-ui protocol with our DSP 4x4 Mini findings:

### Shared protocol elements

Both devices use:
- Same frame format: `10 02 [SRC] [DST] [LEN] [PAYLOAD] 10 03 [XOR_CHK]`
- Same XOR checksum algorithm (initial value = 1)
- Same opcodes for core functions: `0x10` (handshake), `0x12` (status), `0x13` (device info), `0x14` (active preset), `0x22` (preset header), `0x24` (config response), `0x27` (config request), `0x29` (preset name), `0x2c` (device info query), `0x34` (gain), `0x35` (mute), `0x40` (keepalive/levels)
- Same gain encoding formula: `dB = (value - 280) / 10.0`
- Same GEQ/PEQ gain encoding: `dB = (value - 120) / 10.0`

### Different elements

| Aspect | DSP 408 | DSP 4x4 Mini |
|---|---|---|
| **Transport** | TCP/IP socket (Ethernet) | USB HID (64-byte reports) |
| **Default port** | 9761 | N/A (USB endpoint 0x02 out, 0x81 in) |
| **Outputs** | 8 | 4 |
| **Presets** | 20 (U01-U20) | 30 |
| **Config pages** | 29 (0x00-0x1C) | 9 |
| **Meter channels** | 12 (4 in + 8 out), float16 | 8 (4 in + 4 out), different format |
| **Meter bytes/channel** | 3 (float16 + peak byte) | Different structure |
| **GEQ command** | `0x48` | Not yet discovered |
| **PEQ command** | `0x33` | Not yet discovered |
| **Hi-pass command** | `0x32` | Not yet discovered |
| **Lo-pass command** | `0x31` | Not yet discovered |
| **Matrix command** | `0x3a` | Not yet discovered |
| **Preset load command** | `0x20` | Not yet discovered |
| **Preset store commands** | `0x26` (name) + `0x21` (slot) | Not yet discovered |
| **Channel linking** | Not explored | `0x3b` (link state) + `0x2a` (pre-link) |
| **Input gain range** | 0-400 (same protocol) | 0-400 |
| **Static footer in IN** | Not observed | `00 10 03 3d 00 0a bc 8d` |

### Likely shared but unconfirmed

The following DSP 408 opcodes likely exist on the DSP 4x4 Mini but haven't been verified:
- `0x31` (lo-pass), `0x32` (hi-pass), `0x33` (PEQ), `0x48` (GEQ)
- `0x3a` (matrix routing) -- but with only 4 outputs instead of 8
- `0x20` (load preset), `0x21`/`0x26` (store preset)

---

## 20. Wireshark Dissector and Analysis Tools

### Wireshark Lua script

File: `wireshark_scripts/data_text.lua`

A simple Wireshark post-dissector that converts `data.data` fields to ASCII text for easier inspection. It does NOT decode the DSP protocol -- it just shows raw data as a string.

### Python analysis scripts

Five progressive analysis scripts in the repo root:

| File | Purpose |
|---|---|
| `analyze_pcap.py` | Initial hex dump and channel name position finding from hardcoded config dump data. |
| `analyze2.py` | Chunk size analysis and stream rebuilding using the LENGTH field. Compares with/without footer. Contains raw hex data for a "Default Preset" config. |
| `analyze3.py` | Deep structural analysis: record boundaries, PEQ parsing, channel tail analysis. |
| `analyze4.py` | Final structural analysis: determines PEQ count (8 input, 9 output), HPF/LPF layout, output tail structure. |
| `analyze5.py` | Complete verification: validates all 12 channels, produces the definitive per-channel data structure. Contains the most complete stream offset table. |
| `ap_final.py` | Empty file (contains only `import struct`). |

The analysis scripts use a second capture (different from "Default Preset" -- uses "Forest" preset) with non-default PEQ values on some output channels, which helped distinguish PEQ data from filter/limiter data.

---

## 21. Repository Structure and Key Files

```
dsp-408-ui/
  .github/workflows/
    build.yaml              # CI: builds for Windows, Linux, Android
    release.yaml            # CD: auto-releases when version bumps
  lib/
    main.dart               # App entry point, MaterialApp, all providers, tab navigation
    initialize.dart         # DSPInitializer: 56-command startup sequence
    devices/t_racks408/
      protocol.dart         # TRacksProto: static command byte arrays (handshake, presets, config dump)
      load_preset.dart      # ChannelConfigParser: config dump parsing, preset load/save command builders
      services/
        protocol_service.dart  # ProtocolService: encode/decode, gain/GEQ/PEQ/filter math, message parsing
        socket_service.dart    # SocketService: TCP connection, command queue, keepalive timer
      providers/
        device_provider.dart   # DeviceProvider: all device state (gains, mutes, matrix, GEQ, PEQ, meters)
        connection_provider.dart # ConnectionProvider: connect/disconnect, init sequence, debug logging
      widgets/
        gain_tab.dart        # 12-channel fader UI with meters, mute, phase buttons
        matrix_tab.dart      # 8x4 matrix grid with toggle and gain per crossing
        geq_tab.dart         # 31-band GEQ with log-frequency graph, RTA overlay
        peq_tab.dart         # PEQ editor with interactive graph, band/freq/Q/gain sliders, type/bypass
        rta_tab.dart         # Standalone RTA (real-time analyzer) with mic input
      overlays/
        settings_overlay.dart  # Settings dialog: refresh interval, mic input selection
    services/
      rta_service.dart       # RtaService: mic capture, FFT (8192-point), 128-band log-spaced analysis
      rta_settings_provider.dart # RtaSettingsProvider: capture device enumeration/selection
  wireshark_scripts/
    data_text.lua            # Simple Wireshark post-dissector
  analyze_pcap.py            # Config dump hex analysis (initial)
  analyze2.py                # Chunk size / stream rebuild analysis
  analyze3.py                # Deep structural analysis
  analyze4.py                # PEQ count determination
  analyze5.py                # Complete verification / offset table
  ap_final.py                # Empty analysis script stub
  Makefile                   # Build targets: setup, build-windows, build-linux, build-android, etc.
  pubspec.yaml               # Flutter deps: provider, google_fonts, shared_preferences, flutter_recorder, fftea
  README.md                  # Project overview, supported platforms, feature list, build instructions
  LICENSE                    # GPL v3
  CODEOWNERS                 # GitHub code owners
  write_script.ps1           # PowerShell helper (ASCII encoding fix)
  flatpak/                   # Flatpak packaging files
  image.png, image-1.png, image-2.png  # README screenshots
```

### Key dependencies

| Package | Version | Purpose |
|---|---|---|
| `provider` | ^6.1.2 | State management |
| `google_fonts` | ^6.2.1 | Roboto Mono font (Monokai theme) |
| `shared_preferences` | ^2.5.0 | Persistent channel aliases |
| `flutter_recorder` | ^1.1.2 | Microphone audio capture for RTA |
| `fftea` | ^1.5.0 | FFT processing for RTA spectrum analysis |

### Build and CI/CD

- `Makefile` provides standard build targets
- GitHub Actions builds for Windows (x64), Linux (x64, ARM64), Android (APK)
- Automated release workflow triggers on version bump in `pubspec.yaml`
- Flatpak packaging is available for Linux

---

## 22. RTA (Real-Time Analyzer)

Although not protocol-related, the RTA feature is notable:

- Uses device microphone (mobile) or selectable audio input (desktop)
- 8192-point FFT at 44100 Hz sample rate (~5.4 Hz per bin)
- 128 log-spaced bands from 20 Hz to 20 kHz
- Hanning window, 50% overlap
- Peak hold with 6 dB/sec decay
- Display range: -140 to +10 dB
- UI update rate: ~30 fps (33 ms timer)
- Can be overlaid on the GEQ graph for visual feedback while adjusting EQ

---

## 23. Command Throttling

The app throttles rapid parameter changes to avoid overwhelming the device:

- **Gain:** 50 ms debounce per channel. After timeout, sends the latest pending value. Also clears the command queue before sending (only latest gain matters).
- **GEQ band:** 50 ms debounce per channel+band combination.
- **PEQ band:** 50 ms debounce per channel+band combination.
- **All other commands:** Sent immediately via the command queue.

Gain commands are sent **twice** (enqueued as `[command, command]`) for reliability.

---

## 24. Keepalive and Connection Management

- Keepalive poll interval: configurable 5-300 ms (default 300 ms)
- Keepalive is only sent when the command queue is empty and no response is pending
- Response timeout: 500 ms (if no response, the queue auto-unsticks)
- On disconnect: all timers stopped, queue cleared, device state reset
- Connection uses raw TCP socket (Dart `Socket.connect`)
