# the t.racks DSP 4x4 Mini — USB HID Protocol Documentation

Reverse-engineered from Wireshark USBPcap sessions (all in `usb_captures/`):

**Startup & initialization:**
- `miniDSP Capture - Start and close windows edit software.txt` — full manufacturer startup sequence (init → config read → polling → shutdown)
- `miniDSP Capture - startup in4 and out4 muted.txt` — startup with In4+Out4 muted (mute bitmask discovery)
- `miniDSP Capture - startup in4 and out4 not muted.txt` — startup with nothing muted (mute bitmask control)

**Mute & gain:**
- `miniDSP Capture.txt` — mute/unmute input ch1 (linked to ch2)
- `miniDSP Capture - Input gain fader moved.txt` — input gain ch1 fader sweep
- `miniDSP Capture - move input gain fader ch3 from -60 to *.txt` (×5) — gain calibration at -12, 0, +3, +6, +12 dB

**Level metering:**
- `miniDSP Capture - monitoring sine wave at static level.txt` — 220 packets, normal/high-res mode switching
- `miniDSP Capture - monitoring sine wave at increasing and decreasing level.txt` — full sweep, uint16 reaching 264
- `miniDSP Capture - monitoring sine wave at static level 0dBu.txt` — meter calibration at 0 dBu
- `miniDSP Capture - monitoring sine wave at static level -30dBu.txt` — meter calibration at -30 dBu
- `miniDSP Capture - monitoring sine wave at static level right before visible level.txt` — below display threshold
- `miniDSP Capture - monitoring sine wave at static level first visible level.txt` — minimum visible level
- `miniDSP Capture - monitoring sine wave at static level end of green area.txt` — green/yellow boundary
- `miniDSP Capture - monitoring sine wave at static level start of yellow area.txt` — yellow zone start
- `miniDSP Capture - clip channel 1+2 in+out.txt` — clipping test on ch1+2 in/out
- `miniDSP Capture - trigger limiter indicator on out channel 4.txt` — compressor/limiter bitmask discovery

**Channel linking:**
- `miniDSP Capture - link input channel channel 1 and 2.txt`
- `miniDSP Capture - unlink input channel channel 1 and 2.txt`
- `miniDSP Capture - link outut channel channel 2 and 3.txt`
- `miniDSP Capture - unlink output channel channel 2 and 3.txt`
- `miniDSP Capture - link unlink out channel 1 and 2.txt`
- `miniDSP Capture - link unlink out channel 3 and 4.txt`
- `miniDSP Capture - link unlink out channel 1,2,3 and 4.txt`

**Phase invert:**
- `capture_20260405_000924_input_channel_phase_invert.pcapng` — InC phase toggled normal↔inverted (opcode 0x36 discovery)
- `capture_20260405_003445_output_channel_phase_invert.pcapng` — Out4 phase toggled (confirms 0x36 works for outputs, config byte 68 in output block)

**Noise gate:**
- `capture_20260405_010105_output_channel_gate_threshold.pcapng` — InC gate threshold swept −90.0→0.0 dB (opcode 0x3e discovery)
- `capture_20260405_010241_output_channel_gate_attack.pcapng` — InC gate attack swept 1→999 ms
- `capture_20260405_010538_output_channel_gate_hold.pcapng` — InC gate hold swept 10→999 ms
- `capture_20260405_010640_output_channel_gate_release.pcapng` — InC gate release swept 1→3000 ms
- `capture_20260405_011619_output_channel_gate_threshold_2.pcapng` — InC threshold (disambiguated: bytes 8-9)
- `capture_20260405_011722_output_channel_gate_attack_2.pcapng` — InC attack (disambiguated: bytes 2-3)
- `capture_20260405_122541_output_channel_gate_all_params.pcapng` — InC all 4 params swept min→max→min→max (corrected hold min=9, release min=0)

**Other:**
- `miniDSP USBTree output.txt` — USB device descriptor (VID/PID/endpoints)

## Physical Layer

| Property | Value |
|---|---|
| Vendor ID | `0x0168` (Musicrown) |
| Product ID | `0x0821` |
| Manufacturer string | "Musicrown" |
| Product string | "Dsp Process" |
| USB version | 1.1 (Full-Speed, 12 Mbit/s) |
| Interface class | USB HID (0x03), no subclass, no protocol |
| HID report size | 64 bytes (IN and OUT) |
| OUT endpoint | 0x02 (Interrupt, 1 ms interval) |
| IN endpoint | 0x81 (Interrupt, 1 ms interval) |
| Max power | 100 mA (bus powered) |
| Serial number | None |

## Frame Format

All communication uses the same serial-style framing inside the 64-byte HID report:

```
 Byte:  [0]   [1]   [2]   [3]   [4]      [5 .. 4+LEN]     [5+LEN] [6+LEN] [7+LEN]
        0x10  0x02  SRC   DST   LEN      PAYLOAD            0x10    0x03    CHK
        └──────────┘                                         └───────────┘
          STX                                                     ETX
```

| Field | Size | Description |
|---|---|---|
| STX | 2 | Always `10 02` — start of frame |
| SRC | 1 | Source: `0x00` = host, `0x01` = device |
| DST | 1 | Destination: `0x01` = device, `0x00` = host |
| LEN | 1 | Byte count of PAYLOAD |
| PAYLOAD | LEN | Command or response data (see below) |
| ETX | 2 | Always `10 03` — end of frame |
| CHK | 1 | XOR of LEN and all PAYLOAD bytes |

**Checksum formula:** `CHK = LEN ^ PAYLOAD[0] ^ PAYLOAD[1] ^ ... ^ PAYLOAD[LEN-1]`

> Verified across all 766 packets (156 + 610) in both captures — 0 failures.

Bytes after `CHK` up to position 55 are **zero-padded**. Bytes 56–63 contain a
static device footer (see below). The receiver should parse only the framed
portion and ignore padding.

### Static Device Footer (bytes 56–63)

Every IN report ends with the same 8 bytes:

```
00 10 03 3d 00 0a bc 8d
```

`0x000abc8d` (703629 decimal) is likely a device identifier or firmware version.

---

## Initialization Sequence (Host → Device)

Discovered from `miniDSP Capture - Start and close windows edit software.txt`
(126 HID packets captured during Windows software startup and shutdown).

The software performs the following sequence on startup:

```
Step  Command    Response    Description
────  ─────────  ─────────   ──────────────────────────────────────────
 1    0x10       0x10        Init handshake
 2    0x13       0x13        Firmware/model string query
 3    0x2c       0x2c        Device info query
 4    0x22       0x22        Active preset header query
 5    0x14       0x14        Active preset index query
 6    0x29 ×30   0x29 ×30    Read all 30 preset names (slots 0–29)
 7    0x27 ×9    0x24 ×9     Read active preset config (9 pages)
 8    0x12       0x01 (ACK)  Config load complete / activate
 9    0x40 loop  0x40 loop   Normal level monitoring begins
```

No special shutdown sequence — the software simply stops polling.

### 0x10 — Init Handshake

```
Payload (1 byte): 10
Full frame:       10 02 00 01 01 10 10 03 11
```

Device responds with 2-byte payload: `10 1e` (0x1e = 30, possibly max preset count).

### 0x13 — Firmware / Model String

```
Payload (1 byte): 13
Full frame:       10 02 00 01 01 13 10 03 12
```

Device responds with 13-byte payload: `13` + ASCII string `"4x4MINI V010"`.
This matches the magic header in the `.unt` config file (`***4x4MINIV010**`).

### 0x2c — Device Info

```
Payload (1 byte): 2c
Full frame:       10 02 00 01 01 2c 10 03 2d
```

Device responds with 8-byte payload: `2c 00 27 0f 00 00 00 00`.
Bytes 2–3 = `0x270f` (9999 decimal). Purpose unknown — possibly a device serial
or configuration counter. This value also appears in the `.unt` file header at
offset 0x19–0x1A.

### 0x22 — Active Preset Header

```
Payload (1 byte): 22
Full frame:       10 02 00 01 01 22 10 03 23
```

Device responds with 31-byte payload: `22 ff ff` + 28 zero bytes.
The `0xFFFF` matches the preset start marker in the `.unt` file format.
The trailing zeros suggest the current state doesn't carry extra header data.

### 0x14 — Active Preset Index

```
Payload (1 byte): 14
Full frame:       10 02 00 01 01 14 10 03 15
```

Device responds with 2-byte payload: `14 02`.
The value `0x02` indicates the active preset. In this capture, the config
pages that followed contained preset "DIY Mon offset" (slot index 1).
The exact mapping between this value and slot indices needs further testing.

### 0x29 — Read Preset Name

Reads the name of a preset slot (30 total slots, indices 0x00–0x1D).

```
Payload (2 bytes): 29 [slot_index]
```

Device responds with 16-byte payload: `29 [slot_index] [14 bytes ASCII name]`.
Names are space-padded to 14 characters.

**Example:**

| Slot | Request | Response (ASCII) |
|---|---|---|
| 0 | `29 00` | `"DIY Mon       "` |
| 1 | `29 01` | `"DIY Mon offset"` |
| 2–29 | `29 02`–`29 1d` | `"Default Preset"` |

### 0x27 — Read Config Page

Reads the active preset's configuration in 50-byte pages. The device responds
with opcode `0x24` (not `0x27`).

```
Payload (2 bytes): 27 [page_index]
  page_index = 0x00 through 0x08 (9 pages)
```

Device responds with 52-byte payload: `24 [page_index] [50 bytes data]`.

The 9 pages (9 × 50 = 450 data bytes) reconstruct the **exact same binary
structure** as a preset block in the `.unt` configuration file:

```
Page 0: FFFF marker + preset name + InA block start
Page 1: InB + InC + InD block start
Page 2: InD end + Out1 block start
Page 3: Out1 end + Out2 block start
Page 4: Out2 middle
Page 5: Out2 end + Out3 block start
Page 6: Out3 end + Out4 block start
Page 7: Out4 middle
Page 8: Out4 end + zero padding
```

**Verification:** All 429 data bytes from the capture matched byte-for-byte
with preset 2 ("DIY Mon offset") in the `.unt` file. This confirms the `.unt`
file is a direct dump of device configuration memory.

### 0x12 — Activate / Config Load Complete

Sent after reading all config pages, before starting the polling loop.

```
Payload (1 byte): 12
Full frame:       10 02 00 01 01 12 10 03 13
```

Device responds with standard ACK (`01`).

---

## Commands (Host → Device)

### 0x40 — Poll / Request Levels

Requests the device to respond with current metering data.

```
Payload (1 byte): 40
Full frame:       10 02 00 01 01 40 10 03 41
```

This is sent continuously (~150 ms interval) to keep the level meters updated.

### 0x35 — Mute Input (Channels 1+2 linked)

Sets the mute state for linked input channels 1+2.

```
Payload (3 bytes): 35 00 XX
  XX = 01  →  MUTE ON
  XX = 00  →  MUTE OFF
```

| Action | Full frame |
|---|---|
| Mute ON | `10 02 00 01 03 35 00 01 10 03 37` |
| Mute OFF | `10 02 00 01 03 35 00 00 10 03 36` |

**Observations from the capture:**
- 4 mute-on / 4 mute-off toggles were recorded.
- The byte at payload[1] (`0x00`) may be a channel-pair selector
  (e.g., `0x00` = pair 1+2, possibly `0x01` = pair 3+4 — untested).
- After each mute command, the device responds with a generic ACK (see below).

### 0x34 — Input Gain

Sets the input gain for a channel.

Sources:
- `miniDSP Capture - Input gain fader moved.txt` — 205 commands, ch1, full sweep 0–400
- `miniDSP Capture - move input gain fader ch3 from -60 to 0 dB.txt` — 95 commands, ch3, −60→0 dB

```
Payload (4 bytes): 34 CC LL HH
  CC    = channel selector (0-indexed: 0x00=ch1, 0x01=ch2, 0x02=ch3, 0x03=ch4)
  LL HH = gain value, 16-bit little-endian
```

| Field | Description |
|---|---|
| Opcode | `0x34` |
| Channel | Byte 1: 0-indexed (`0x00`=ch1, `0x02`=ch3 confirmed) |
| Value | Bytes 2–3: little-endian uint16, range **0–400** (0x0000–0x0190) |

**Gain-to-dB mapping:**

Confirmed from 5 ch3 captures AND cross-referenced with `dsp-408-ui` (same protocol).
The mapping uses **dual resolution** with a breakpoint at −20 dB:

```
Segment 1 (coarse): raw 0–79   → −60.0 to −20.5 dB  (0.5 dB/step)
Segment 2 (fine):   raw 80–400 → −20.0 to +12.0 dB   (0.1 dB/step)
```

**Formulas:**

```
dB → raw:
  if dB < −20:  raw = (dB + 60) × 2
  if dB ≥ −20:  raw = 80 + (dB + 20) × 10

raw → dB:
  if raw < 80:  dB = raw / 2 − 60
  if raw ≥ 80:  dB = (raw − 80) / 10 − 20
```

| Raw | dB | Resolution |
|---|---|---|
| 0 | −60.0 dB (minimum) | 0.5 dB/step |
| 80 | −20.0 dB (breakpoint) | — |
| 160 | −12.0 dB | 0.1 dB/step |
| 280 | 0.0 dB (unity) | 0.1 dB/step |
| 400 | +12.0 dB (maximum) | 0.1 dB/step |

All 5 capture calibration points (−12, 0, +3, +6, +12 dB) match with zero error.
The earlier simple linear formula (`raw × 0.1 − 28`) was coincidentally correct
for all test points (all above −20 dB) but wrong below −20 dB.

> The software sends updates at roughly every ~150 ms fader position change.
> Faster fader movement produces larger value jumps; slower movement near the
> target produces single-unit increments.

**Example frames:**

| Gain | Payload | Full frame |
|---|---|---|
| Min (0) | `34 00 00 00` | `10 02 00 01 04 34 00 00 00 10 03 30` |
| Mid (200) | `34 00 c8 00` | `10 02 00 01 04 34 00 c8 00 10 03 f8` |
| Max (400) | `34 00 90 01` | `10 02 00 01 04 34 00 90 01 10 03 a1` |

---

## Responses (Device → Host)

### ACK — Command Acknowledgment

Sent in reply to a mute (or other write) command.

```
Payload (1 byte): 01
Full frame:       10 02 01 00 01 01 10 03 00
```

A single `0x01` byte = success. Seen for every mute and gain command.

### 0x40 — Level Monitoring

Sent in reply to each poll command. Contains real-time metering data for inputs
and outputs.

```
Payload (28 bytes): 40 [8 × 3-byte channel triplets] [3-byte tail]
Full frame header: 10 02 01 00 1c 40 ...
```

#### Payload layout — 3-byte channel triplets

Each channel is encoded as a **3-byte triplet: `[val_lo] [val_hi] [instant]`**.

The first two bytes form a **uint16 LE** filtered/peak level (range 0–~264,
observed Out2 reaching 264 at max analog input). The third byte is a noisy
instantaneous sample (0–255).

The device autonomously switches between two reporting modes:
- **Normal mode (state=0x00):** uint16=0, `instant` has the level — use instant byte
- **High-res mode (state=0x01):** uint16>0, smooth firmware-filtered value — use uint16

```
Offset  Size  Field
──────  ────  ─────────────────────────────────────────
  0      1    Sub-type: always 0x40

 ── Input channel triplets ────────────────────────────
  1–3    3    Input 1: [val_lo, val_hi, instant]
  4–6    3    Input 2: [val_lo, val_hi, instant]
  7–9    3    Input 3: [val_lo, val_hi, instant]
 10–12   3    Input 4: [val_lo, val_hi, instant]

 ── Output channel triplets ───────────────────────────
 13–15   3    Output 1: [val_lo, val_hi, instant]
 16–18   3    Output 2: [val_lo, val_hi, instant]
 19–21   3    Output 3: [val_lo, val_hi, instant]
 22–24   3    Output 4: [val_lo, val_hi, instant]

 ── Tail ──────────────────────────────────────────────
 25      1    Limiter active channel bitmask (see below)
 26      1    State flag (see below)
 27      1    Reserved (0x00)
```

#### Level decoding

Use only the uint16 LE value for metering:
```
level = val_lo + val_hi * 256
```

The uint16 is a **linear amplitude** value. When uint16 = 0, the signal is
below the display threshold (including noise floor). The instant byte is on an
incompatible scale and should be ignored for metering purposes.

**Calibration** (verified from captures at known analog levels):

| Analog level | uint16 (In1) | Manufacturer display |
|---|---|---|
| -30 dBu | ~5 | 2 green LEDs |
| 0 dBu | ~188 | 1 yellow LED (green/yellow boundary) |
| Max console out | ~264 | Well into yellow |

The 30 dB difference between 188 and 5 confirms linear amplitude encoding:
188 / 5 = 37.6 ≈ 10^(31.5/20) = 37.6. The small deviation from the expected
ratio of 31.6 is due to integer quantization at low values.

**Display scaling**: dB conversion with `20*log10(level / 1153)` and a 63 dB
range places -30 dBu at 25% and 0 dBu at 75% of the meter, matching the
manufacturer's LED meter layout.

#### Limiter active channel bitmask (offset 25)

Reports **which output channel(s)** have their compressor/limiter currently
triggered. Same bitmask scheme as the channel link flags:

```
Bit 0 (0x01) = Out1
Bit 1 (0x02) = Out2
Bit 2 (0x04) = Out3
Bit 3 (0x08) = Out4
```

In the limiter capture (output ch4 triggered 3 times): byte 25 = `0x08` during
each event, `0x00` otherwise. Exactly 3 transitions from `0x00` to `0x08`.

#### State flag (offset 26)

- `0x00` = normal metering mode (uint16=0, levels in instant byte of each triplet).
- `0x01` = high-res mode (levels in uint16 LE of each triplet) or init/processing active.

---

## Communication Pattern

Normal monitoring loop (~6–7 packets/second):

```
Host  ──[POLL 0x40]──►  Device
Host  ◄──[LEVEL 0x40]──  Device
Host  ──[POLL 0x40]──►  Device
Host  ◄──[LEVEL 0x40]──  Device
  ...repeats...
```

Parameter change (mute, gain, etc.):

```
Host  ──[CMD 0x35/0x34/...]──►  Device
Host  ◄──[ACK 0x01]────────────  Device
Host  ──[POLL 0x40]────────────►  Device     (resumes normal polling)
Host  ◄──[LEVEL 0x40]──────────  Device
```

During rapid fader movement, commands are interleaved with polling:

```
Host  ──[GAIN 0x34 val1]──►  Device
Host  ◄──[ACK]──────────────  Device
Host  ──[GAIN 0x34 val2]──►  Device
Host  ◄──[ACK]──────────────  Device
  ...burst of gain updates...
Host  ──[POLL 0x40]────────►  Device       (when fader stops moving)
Host  ◄──[LEVEL 0x40]──────  Device
```

---

## Known Register Map

| Opcode | Length | Dir | Function | Value format |
|---|---|---|---|---|
| `0x10` | 1 | OUT | Init handshake | `10` — device responds `10 1e` |
| `0x12` | 1 | OUT | Activate config | `12` — device responds ACK |
| `0x13` | 1 | OUT | Firmware string | `13` — device responds ASCII `"4x4MINI V010"` |
| `0x14` | 1 | OUT | Active preset index | `14` — device responds `14 [idx]` |
| `0x20` | 2 | OUT | Load preset | `20 [slot+1]` — 1-based index (*) |
| `0x2a` | 3 | OUT | Prepare link | `2a [master_ch] [slave_ch]` — one per pair, sent before linking |
| `0x21` | 2 | OUT | Store preset | `21 [slot+1]` — 1-based index (*) |
| `0x22` | 1 | OUT | Preset header | `22` — device responds `22 ffff` + 28 zeros |
| `0x26` | 15 | OUT | Store preset name | `26 [14-char name]` — space-padded (*) |
| `0x27` | 2 | OUT | Read config page | `27 [page]` — device responds `24 [page] [50 bytes]` |
| `0x29` | 2 | OUT | Read preset name | `29 [slot]` — device responds `29 [slot] [14 char name]` |
| `0x2c` | 1 | OUT | Device info | `2c` — device responds `2c` + 7 bytes |
| `0x31` | 5 | OUT | Lo-pass filter | `31 [ch] [freq_lo] [freq_hi] [slope]` (*) |
| `0x32` | 5 | OUT | Hi-pass filter | `32 [ch] [freq_lo] [freq_hi] [enable]` (*) |
| `0x33` | 10 | OUT | PEQ band | `33 [ch] [band] [gain] 00 [freq_lo] [freq_hi] [Q] [type] [bypass]` (*) |
| `0x34` | 4 | OUT | Gain | `34 [ch] [val_lo] [val_hi]` — LE uint16, 0–400 |
| `0x35` | 3 | OUT | Mute | `35 [ch] [state]` — 0x00=off, 0x01=on |
| `0x36` | 3 | OUT | Phase invert | `36 [ch] [state]` — 0x00=normal, 0x01=inverted |
| `0x3e` | 10 | OUT | Noise gate | `3e [ch] [atk_lo] [atk_hi] [rel_lo] [rel_hi] [hold_lo] [hold_hi] [thr_lo] [thr_hi]` |
| `0x3b` | 3 | OUT | Channel link | `3b [ch] [link_flags]` — see below |
| `0x3a` | 3 | OUT | Matrix routing | `3a [output_ch] [input_bitmask]` (*) |
| `0x40` | 1 | OUT | Poll levels | `40` — request only, no parameters |
| `0x48` | 5 | OUT | GEQ band | `48 [ch] [band] [value] 00` — inputs only (*) |

(*) = from `dsp-408-ui` project (same Musicrown protocol, DSP 408 over TCP).
Not yet capture-verified on the DSP 4x4 Mini but expected to be identical.

**Channel byte (`ch`):** Inputs 0x00–0x03, outputs 0x04–0x07.
Confirmed for inputs: `0x00`=ch1, `0x02`=ch3. Output numbering from `dsp-408-ui`.

---

## Commands from dsp-408-ui (Not Yet Captured on 4x4 Mini)

The following command details are from the `Aeternitaas/dsp-408-ui` project, which
reverse-engineered the same Musicrown protocol for the DSP 408 over TCP/Ethernet.
The binary protocol is transport-agnostic — these should work identically over USB HID.

### 0x33 — PEQ (Parametric EQ)

```
Payload (10 bytes): 33 [ch] [band] [gain] 00 [freq_lo] [freq_hi] [Q] [type] [bypass]
```

- **Channels:** inputs 0x00–0x03 (8 bands each), outputs 0x04–0x07 (9 bands each)
- **Gain:** `value = dB × 10 + 120`, range 0–240, −12.0 to +12.0 dB, 0.1 dB resolution
- **Frequency** (LE uint16): log scale, 0–1000 steps
  - `Hz = 19.70 × (20160 / 19.70) ^ (raw / 1000)`
  - `raw = log(Hz / 19.70) / log(20160 / 19.70) × 1000`
- **Q** (byte, 0–255): log scale
  - `Q = 0.40 × 320 ^ (raw / 255)`, range 0.40–128.0
- **Type** (byte): `0=Peak, 1=Low Shelf, 2=High Shelf, 3=LP -6, 4=LP -12, 5=HP -6, 6=HP -12, 7=AllPass1, 8=AllPass2`
- **Bypass:** `0x00`=active, `0x01`=bypassed

### 0x48 — GEQ (31-Band Graphic EQ)

```
Payload (5 bytes): 48 [ch] [band] [value] 00
```

- **Channels:** inputs only (0x00–0x03)
- **Bands:** 0–30 (31 bands, ISO 1/3-octave: 20 Hz–20 kHz)
- **Value:** `value = dB × 10 + 120`, range 0–240, −12.0 to +12.0 dB

### 0x31 — Lo-Pass Crossover Filter

```
Payload (5 bytes): 31 [ch] [freq_lo] [freq_hi] [slope]
```

- **Frequency:** same log-scale LE uint16 as PEQ (0–1000). Set to 1000 (max) to disable.
- **Slope** (byte, 0–19): `BW -6, BW -12, ..., BW -48, LR -12, LR -24, LR -36, LR -48, BS -6, ..., BS -48`

### 0x32 — Hi-Pass Crossover Filter

```
Payload (5 bytes): 32 [ch] [freq_lo] [freq_hi] [enable]
```

- **Frequency:** same log-scale LE uint16 as PEQ
- **Enable:** `0x01`=on, `0x00`=off

### 0x3a — Matrix Routing

```
Payload (3 bytes): 3a [output_ch] [input_bitmask]
```

- **Output channel:** Out1=0x04, Out2=0x05, Out3=0x06, Out4=0x07
- **Input bitmask:** InA=0x01, InB=0x02, InC=0x04, InD=0x08 (combinable)

### 0x3b — Channel Link

Discovered from input link/unlink captures and output link/unlink captures.

```
Payload (3 bytes): 3b [channel] [link_flags]
```

Sets the link/pairing state for any channel (input or output). When linking,
both channels in the pair must be updated. After changing link state, the
software sends `0x12` (activate) and performs a full config re-read.

**Channel byte:** unified numbering — inputs 0x00–0x03, outputs 0x04–0x07.

**Link flags are a bitmask** within each 4-channel group (inputs or outputs):

```
Inputs:                     Outputs:
  Bit 0 (0x01) = InA          Bit 0 (0x01) = Out1
  Bit 1 (0x02) = InB          Bit 1 (0x02) = Out2
  Bit 2 (0x04) = InC          Bit 2 (0x04) = Out3
  Bit 3 (0x08) = InD          Bit 3 (0x08) = Out4
```

When linked, the master gets the OR of all linked channel bits; slaves get `0x00`:

| Channel | Standalone | Master (2-ch) | Master (all 4) |
|---|---|---|---|
| InA (0x00) | `0x01` | `0x03` = InA+InB | `0x0F` = all four |
| InB (0x01) | `0x02` | slave = `0x00` | slave = `0x00` |
| InC (0x02) | `0x04` | `0x0C` = InC+InD (predicted) | slave = `0x00` |
| InD (0x03) | `0x08` | slave = `0x00` | slave = `0x00` |
| Out1 (0x04) | `0x01` | `0x03` = Out1+Out2 | `0x0F` = all four |
| Out2 (0x05) | `0x02` | `0x06` = Out2+Out3 | slave = `0x00` |
| Out3 (0x06) | `0x04` | `0x0C` = Out3+Out4 | slave = `0x00` |
| Out4 (0x07) | `0x08` | slave = `0x00` | slave = `0x00` |

**Examples (all capture-verified):**

| Action | Commands |
|---|---|
| Link InA+InB | `2a 00 01` + `3b 00 03` + `3b 01 00` + `12` |
| Unlink InA+InB | `3b 00 01` + `3b 01 02` + `12` |
| Link Out1+Out2 | `2a 04 05` + `3b 04 03` + `3b 05 00` + `12` |
| Unlink Out1+Out2 | `3b 04 01` + `3b 05 02` + `12` |
| Link Out2+Out3 | `2a 05 06` + `3b 05 06` + `3b 06 00` + `12` |
| Unlink Out2+Out3 | `3b 05 02` + `3b 06 04` + `12` |
| Link Out3+Out4 | `2a 06 07` + `3b 06 0C` + `3b 07 00` + `12` |
| Unlink Out3+Out4 | `3b 06 04` + `3b 07 08` + `12` |
| Link Out1+2+3+4 | `2a 04 05` + `2a 04 06` + `2a 04 07` + `3b 04 0F` + `3b 05 00` + `3b 06 00` + `3b 07 00` + `12` |
| Unlink Out1+2+3+4 | `3b 04 01` + `3b 05 02` + `3b 06 04` + `3b 07 08` + `12` |

The link flags byte corresponds to offset 22 in input blocks and offset 72
in output blocks of the `.unt` config / `0x24` config page response.

### 0x2a — Prepare Link

```
Payload (3 bytes): 2a [master_channel] [slave_channel]
```

Sent **only when linking** (not when unlinking), immediately before the `0x3b`
commands. One `0x2a` is sent per master↔slave pair. For multi-channel links
(e.g. all four outputs), the master sends one `0x2a` for each slave.

| Link action | 0x2a commands |
|---|---|
| Link InA+InB | `2a 00 01` |
| Link Out1+Out2 | `2a 04 05` |
| Link Out2+Out3 | `2a 05 06` |
| Link Out3+Out4 | `2a 06 07` |
| Link Out1+2+3+4 | `2a 04 05` + `2a 04 06` + `2a 04 07` |

### 0x20 — Load Preset

```
Payload (2 bytes): 20 [slot+1]
```

Uses **1-based** slot index. Loads the preset into the active config.

### 0x21 — Store Preset

```
Payload (2 bytes): 21 [slot+1]
```

Stores current config to the specified slot (1-based).

### 0x26 — Store Preset Name

```
Payload (15 bytes): 26 [14 chars ASCII, space-padded]
```

### 0x3E — Noise Gate (Input Channels)

```
Payload (10 bytes): 3e [ch] [atk_lo] [atk_hi] [rel_lo] [rel_hi] [hold_lo] [hold_hi] [thr_lo] [thr_hi]
```

Sets all 4 noise gate parameters for an input channel in a single command.
All parameters are uint16 LE.

| Field | Bytes | Raw Range | UI Range | Formula |
|---|---|---|---|---|
| Attack | 2–3 | 34–998 | 1–999 ms | ~1:1 (raw ≈ ms) |
| Release | 4–5 | 0–2999 | 0–3000 ms | ~1:1 (raw ≈ ms) |
| Hold | 6–7 | 9–998 | 10–999 ms | ~1:1 (raw ≈ ms) |
| Threshold | 8–9 | 1–180 | −90.0 to 0.0 dB | dB = raw × 0.5 − 90.0 |

**Channel byte:** input channels only (0x00–0x03).

**Config storage:** input block bytes 10–17 (4 × uint16 LE in the same order as the command).

**Capture-verified:** 6 captures on InC sweeping each parameter independently.
Confirmed by diff-config comparing config page reads before/after:
- Attack → config bytes 10–11 (e.g. max 998 = 0xe6,0x03)
- Release → config bytes 12–13 (e.g. max 2999 = 0xb7,0x0b)
- Hold → config bytes 14–15 (e.g. max 998 = 0xe6,0x03)
- Threshold → config bytes 16–17 (e.g. max 180 = 0xb4,0x00)

---

## Unknowns / To Investigate

- [x] **Channel selector:** Inputs 0x00–0x03, outputs 0x04–0x07 (from `dsp-408-ui`).
      Gain/mute commands use the same unified channel numbering.
- [x] **Gain-to-dB mapping:** Dual resolution confirmed via `dsp-408-ui`:
      coarse 0.5 dB/step below −20 dB, fine 0.1 dB/step above.
- [x] **Device descriptor:** VID=`0x0168` PID=`0x0821`, Manufacturer="Musicrown",
      Product="Dsp Process" (from `miniDSP USBTree output.txt`).
- [x] **Channel 4 levels:** Confirmed as regular channel 4 level (same scale as
      ch1–3). Higher values were from a mic on ch4 picking up keyboard noise.
- [ ] **Status flags (offsets 10, 22):** Not clip indicators (disproven). Only appear
      during init phase. Exact meaning unknown — startup artifact?
- [ ] **Firmware version:** Is the footer `0x000abc8d` a version number?
- [ ] **Delay command:** Not yet reverse-engineered even in `dsp-408-ui`.
- [ ] **Compressor/Limiter:** Not yet reverse-engineered. Likely encoded in the
      22-byte post-PEQ tail of output channel config blocks.
- [x] **Phase invert:** Opcode `0x36` — `36 [ch] [state]`, 0x00=normal, 0x01=inverted.
      Also stored in config at input block offset 20 (byte within 24-byte block).
      Captured: InC toggled normal↔inverted. InA+InB were already inverted.
- [x] **Noise gate:** Opcode `0x3E` — 10-byte payload with attack/release/hold/threshold.
      Config stored at input block bytes 10–17 (4 × uint16 LE). 6 captures verified.
- [ ] **Verify PEQ/GEQ/crossover/routing on 4x4 Mini:** Commands from `dsp-408-ui`
      need capture verification on our device.

---

## Configuration File Format (`.unt`)

Reverse-engineered from `miniDSP current settings.unt` (13010 bytes).

### File Structure Overview

```
Offset    Content
────────  ──────────────────────────────────────
0x000     File header (51 bytes)
0x033     Preset 1 (0xFFFF marker + name + channels)
0x1E0     CRLF separator
0x1E1     Preset 2 index byte
0x1E3     Preset 2 (0xFFFF marker + name + channels)
0x390     CRLF terminator
0x392     Padding ('d' = 0x64, repeated to EOF)
```

Total structured data: 914 bytes. Remaining 12096 bytes are `0x64` padding.

### File Header (0x00–0x32)

```
Offset  Size  Field
──────  ────  ─────────────────────────────────────
0x00    16    Magic: "***4x4MINIV010**"
0x10     1    Unknown (0x01)
0x11     1    Preset count (0x02 = 2 presets)
0x12     1    Unknown (0x1E = 30)
0x13     4    ASCII "0000" — possibly version or serial
0x17     2    Zero padding
0x19     1    Unknown (0x27 = 39)
0x1A     1    Unknown (0x0F = 15)
0x1B     2    Zero padding
0x1D     4    ASCII "1234" — unknown identifier
0x21     2    Unknown (0x00 0x0A)
0x23    16    Product name: "4x4D Amplifier" (null-prefixed + 0x01 suffix)
```

### Preset Structure

Each preset begins with a 2-byte `0xFF 0xFF` marker followed by:

```
Offset  Size  Field
──────  ────  ─────────────────────────────────────
  0      2    Marker: 0xFF 0xFF
  2     14    Preset name (ASCII, space-padded to 14 chars)
 16    4×24   Input channel blocks (InA, InB, InC, InD)
112   4×74    Output channel blocks (Out1, Out2, Out3, Out4)
408      2    Input mute bitmask, LE uint16 (bit 0=In1 .. bit 3=In4)
410      2    Output mute bitmask, LE uint16 (bit 0=Out1 .. bit 3=Out4)
412     17    Zero padding
429      2    CRLF (0x0D 0x0A) — preset terminator
```

Preset names found: `"DIY Mon       "`, `"DIY Mon offset"`.

### Input Channel Block (24 bytes)

```
Offset  Size  Field
──────  ────  ─────────────────────────────────────
 0       3    Channel name (ASCII: "InA", "InB", "InC", "InD")
 3       7    Zero padding
10–11    2    **Gate attack**, LE uint16, raw 34–998 (1–999 ms, same as 0x3E command)
12–13    2    **Gate release**, LE uint16, raw 0–2999 (0–3000 ms)
14–15    2    **Gate hold**, LE uint16, raw 9–998 (10–999 ms)
16–17    2    **Gate threshold**, LE uint16, raw 1–180 (−90.0 to 0.0 dB, 0.5 dB/step)
18–19    2    **Input gain**, LE uint16, raw 0–400 (same scale as 0x34 command)
20       1    **Phase invert**: 0x00=normal, 0x01=inverted (same as 0x36 command)
21       1    Always 0x00 (mute state is NOT here — see footer bitmasks)
22       1    Routing/link flags (see below)
23       1    Always 0x00
```

**Routing flags (byte 22):**

| Channel | Value | Binary | Interpretation |
|---|---|---|---|
| InA | `0x03` | `00000011` | Linked to pair (bits 0+1) |
| InB | `0x00` | `00000000` | Not linked / follows InA |
| InC | `0x04` | `00000100` | Linked to pair (bit 2) |
| InD | `0x08` | `00001000` | Linked to pair (bit 3) |

InA=0x03 and InB=0x00 is consistent with InA+InB being a linked stereo pair
(the user confirmed channels 1+2 are linked in the software).

**Preset differences (InD only):**
Preset 2's InD has different values at bytes 10, 12–14, and 15–16 compared to preset 1,
suggesting these bytes contain per-channel gain/EQ parameters that were adjusted for the
"DIY Mon offset" preset.

### Output Channel Block (74 bytes)

```
Offset  Size  Field
──────  ────  ─────────────────────────────────────
 0       4    Channel name (ASCII: "Out1"–"Out4")
 4       4    Zero padding
 8       1    Routing byte (Out1=0x01, Out2=0x02, Out3=0x04, Out4=0x08)
 9       1    Always 0x00
10–11    2    Parameter A, LE uint16 (Out1/2=20, Out3/4=0)
12–13    2    Always 300 (0x012C) — possibly compressor threshold
14–15    2    Parameter B, LE uint16 (Out1/2=10, Out3/4=0)
16–17    2    Crossover/filter param (Out1/2=203, Out3/4=120)
18–19    2    Crossover/filter param (Out1/2=89, Out3/4=31)
20–21    2    Crossover/filter param (Out1/2=272, Out3/4=25)
22–61   40    EQ band data: 6-byte repeating groups (see below)
62–63    2    Always 0x0000
64–65    2    Unknown (49 = 0x0031)
66–67    2    **Output gain**, LE uint16, raw 0–400 (same scale as 0x34 command)
68       1    **Phase invert**: 0x00=normal, 0x01=inverted (same as 0x36 command)
69       1    Always 0x00 (mute state is NOT here — see footer bitmasks)
70–71    2    Unknown (280 = 0x0118 in default, 40 in modified Out1)
72       1    Routing/link flags (same scheme as input)
73       1    Always 0x00
```

**EQ band data (bytes 22–61, 6 bytes per band, ~7 bands):**

Each band appears to be a 6-byte group: `[freq_lo freq_hi] [value_lo value_hi] [Q_lo Q_hi]`

All LE uint16. In the default config, bands share frequency=120 and Q=25, with
varying center values (71, 118, 161, 200, 240, 270), suggesting these are
EQ center frequencies mapped to a similar 0–400-style raw scale.

**Out1/Out2 vs Out3/Out4 differences:**
Out1/Out2 have additional parameters set in the crossover/filter area (bytes 10–21),
while Out3/Out4 have these zeroed. This correlates with Out1/Out2 being the
main stereo outputs with crossover processing, while Out3/Out4 may be aux/sub outputs.

### Padding

From byte 914 (0x392) to EOF (13010), the file is filled with `0x64` (`'d'`).
The fixed file size of 13010 bytes is likely a firmware/software requirement.

### .unt Format Unknowns

- [x] ~~Input/output gain location~~ → Input block bytes 18–19, output block bytes 66–67 (uint16 LE, raw 0–400)
- [x] ~~Mute state location~~ → Footer bitmasks at preset offsets 408–409 (input) and 410–411 (output), NOT in per-channel blocks. Verified by comparing startup captures with In4+Out4 muted vs unmuted.
- [x] ~~Input block bytes 10–17~~ → Noise gate parameters: attack (10–11), release (12–13), hold (14–15), threshold (16–17), all LE uint16
- [ ] Output EQ band count and parameter mapping (frequency in Hz, gain in dB, Q factor)
- [ ] Whether output block bytes 12–13 (always 300) represent compressor threshold
- [ ] Purpose of the "4x4D Amplifier" product string vs "Dsp Process" USB string
- [ ] Whether the file can hold more than 2 presets (count byte at 0x11)
- [ ] Crossover type/slope encoded in Out1/Out2 extra parameters
- [ ] Output block bytes 70–71: purpose (delay? polarity? varies between presets)
