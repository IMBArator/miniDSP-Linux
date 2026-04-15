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
- `capture_20260407_190307_link_input_ch1_and_ch2.pcapng` — link input Ch1+Ch2 then restart
- `capture_20260407_190414_link_input_ch1_ch2_and_ch3.pcapng` — link input Ch1+Ch2+Ch3 then restart
- `capture_20260407_190705_link_output_ch1_and_ch2.pcapng` — link output Ch1+Ch2 then restart

**Phase invert:**
- `capture_20260405_000924_input_channel_phase_invert.pcapng` — InC phase toggled normal↔inverted (opcode 0x36 discovery)
- `capture_20260405_003445_output_channel_phase_invert.pcapng` — Out4 phase toggled (confirms 0x36 works for outputs, config byte 68 in output block)

**Noise gate:**
- `capture_20260405_010105_input_channel_gate_threshold.pcapng` — InC gate threshold swept −90.0→0.0 dB (opcode 0x3e discovery)
- `capture_20260405_010241_input_channel_gate_attack.pcapng` — InC gate attack swept 1→999 ms
- `capture_20260405_010538_input_channel_gate_hold.pcapng` — InC gate hold swept 10→999 ms
- `capture_20260405_010640_input_channel_gate_release.pcapng` — InC gate release swept 1→3000 ms
- `capture_20260405_011619_input_channel_gate_threshold_2.pcapng` — InC threshold (disambiguated: bytes 8-9)
- `capture_20260405_011722_input_channel_gate_attack_2.pcapng` — InC attack (disambiguated: bytes 2-3)
- `capture_20260405_122541_input_channel_gate_all_params.pcapng` — InC all 4 params swept min→max→min→max (corrected hold min=9, release min=0)

**Output delay:**
- `capture_20260405_123925_output_channel_delay.pcapng` — Out4 delay swept 0→680→0→680 ms (opcode 0x38 discovery, sample-based encoding)
- `capture_20260409_220822_output_delay_unit.pcapng` — delay unit cycled ms→m→ft→ms→m (opcode 0x15 discovery; config byte 424 confirmed)

**Crossover filters:**
- `capture_20260405_170911_output_channel_xover_highpass.pcapng` — Out3 hi-pass freq swept raw 0→300→0→300 (opcode 0x32, first capture verification on 4x4 Mini)
- `capture_20260405_171114_output_channel_xover_lowpass.pcapng` — Out3 lo-pass freq swept raw 300→0→300→0 (opcode 0x31, confirmed config bytes 12–13)
- `capture_20260405_174550_output_channel_xover_highpass_2.pcapng` — Out3 hi-pass to ~50% fader (raw 128 = 379 Hz, confirmed formula Hz = 19.70 × (20160/19.70)^(raw/300))
- `capture_20260405_171715_output_channel_xover_lowpass_bypass.pcapng` — Out3 lo-pass bypass toggled (confirmed slope byte 0x00=bypass, 0x0a=LR-24 active)
- `capture_20260405_171839_output_channel_xover_highpass_bypass.pcapng` — Out3 hi-pass bypass toggled (same encoding, config byte 14)
- `capture_20260405_172431_output_channel_xover_highpass_slope.pcapng` — Out3 hi-pass slope swept through all 10 types (LR-24→BW-6→LR-24, verified full enum)

**Output compressor:**
- `capture_20260407_184757_output_channel_compressor_threshold.pcapng` — Out3 compressor threshold +20→−90→+20→−90 dB (opcode 0x30 discovery, 87 occurrences)
- `capture_20260407_184842_output_channel_compressor_attack.pcapng` — Out3 compressor attack 50→1→999→1 ms
- `capture_20260407_185003_output_channel_compressor_release.pcapng` — Out3 compressor release 500→10→3000→1 ms
- `capture_20260407_185056_output_channel_compressor_ratio.pcapng` — Out3 compressor ratio 1:1.0→1:20→Limit→1:1.1
- `capture_20260407_185154_output_channel_compressor_knee.pcapng` — Out3 compressor knee 0→12→0→1 dB in 1 dB steps
- `capture_20260407_233926_change_name_of_out_3.pcapng` — Out3 name changed "Out3"→"AUSGANG3"; confirmed output channel name is 8 bytes (0–7)

**Preset management:**
- `capture_20260407_185424_load_preset_f00.pcapng` — load factory preset F00 (Default Preset)
- `capture_20260407_185541_load_preset_u01.pcapng` — load user preset U01 (DIY Mon)
- `capture_20260407_185634_load_preset_u30.pcapng` — load user preset U30 (empty user preset)
- `capture_20260407_185756_load_preset_change_from_u01_to_u02.pcapng` — switch from U01→U02 mid-session then restart
- `capture_20260407_190042_store_preset_u30.pcapng` — store settings to U30 with name "Capture Test"

**Routing matrix:**
- `capture_20260407_191659_matrix_Out1_from_InA_and_InB.pcapng` — Out1 routed from InA+InB (default: 1:1 diagonal)
- `capture_20260407_191838_matrix_Out1_from_InA_InB_InC_InD.pcapng` — Out1 summed from all 4 inputs
- `capture_20260407_192739_matrix_remove_source_of_Out1.pcapng` — Out1 silenced (no source); no init sequence included

**Device lock:**
- `capture_20260409_091144_device_lock_set_pin.pcapng` — full app load, then PIN "7654" set via 0x2f; device locks and disconnects
- `capture_20260409_091341_device_lock_unlock.pcapng` — locked device; app waits in 0x12 loop, correct PIN "7654" submitted via 0x2d → response 01, then normal config load
- `capture_20260409_091530_device_lock_unlock_wrong_pin.pcapng` — locked device; wrong PIN "8888" submitted via 0x2d → response 00, device stays locked

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

Device responds with 8-byte payload. Byte 6 is a **lock status flag**:
- Unlocked: `2c 00 27 0f 00 00 **00** 00`
- Locked:   `2c 00 27 0f 00 00 **01** 00`

| Byte | Value | Meaning |
|---|---|---|
| 0 | `2c` | opcode |
| 1 | `00` | padding |
| 2–3 | `27 0f` | 0x0F27 (big-endian: 0x270F = 9999) — possibly serial or counter; also in `.unt` header at offset 0x19–0x1A |
| 4–5 | `00 00` | unknown |
| 6 | `00` / `01` | **Lock status: `0x00` = unlocked, `0x01` = locked** |
| 7 | `00` | unknown |

**Lock flag verified** by comparing the `0x2c` response across 3 captures (set-pin=unlocked, device-lock-unlock=locked, device-lock-wrong-pin=locked). All other bytes are identical.

### 0x2d — Submit Lock PIN

```
OUT payload (6 bytes): 2d 00 [pin_byte0] [pin_byte1] [pin_byte2] [pin_byte3]
IN  payload (3 bytes): 2d 00 [result]
```

Sent when the device is locked. The PIN is 4 ASCII digit characters (e.g. "7654" = `37 36 35 34`).

| Byte | Direction | Value | Meaning |
|---|---|---|---|
| 0 | both | `2d` | opcode |
| 1 | both | `00` | padding |
| 2–5 | OUT | ASCII digits | PIN digits as ASCII (e.g. "7654" = 37 36 35 34) |
| 2 | IN | `0x01` / `0x00` | `0x01` = PIN correct, `0x00` = PIN wrong |

**Behavior:**
- When locked, the device sits in an ACK loop (responding `0x01` to `0x12` activate) without loading config.
- On correct PIN → device responds `2d 00 01` → app proceeds with normal config load (`0x22`, `0x14`, `0x29`, `0x27` × 9, `0x12`).
- On wrong PIN → device responds `2d 00 00` → device remains locked; app shows error.

**Verified captures:**
- Correct PIN "7654": OUT `2d 00 37 36 35 34` → IN `2d 00 01` → full config load follows
- Wrong PIN "8888":  OUT `2d 00 38 38 38 38` → IN `2d 00 00` → device stays locked

### 0x2f — Set Device Lock PIN

```
OUT payload (5 bytes): 2f [pin_byte0] [pin_byte1] [pin_byte2] [pin_byte3]
```

Sets the device lock PIN and immediately locks the device. No dedicated IN response — the device sends `0x01` ACK then disconnects.

| Byte | Value | Meaning |
|---|---|---|
| 0 | `2f` | opcode |
| 1–4 | ASCII digits | PIN digits as ASCII (e.g. "7654" = 37 36 35 34) |

**⚠ WARNING:** After receiving this command, the device immediately locks and the USB connection is terminated. The device cannot be controlled until the correct PIN is submitted via `0x2d` on next connection. If the PIN is lost, factory reset procedure is unknown — do not use this without careful consideration.

**Verified capture:** Set PIN "7654" → OUT `2f 37 36 35 34` → `0x01` ACK → device disconnects.

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

Device responds with 2-byte payload: `14 [slot]`.
The slot value uses the same direct index as `0x20`: 0=F00, 1=U01, …, 30=U30.

**Verified examples:**
- `14 01` → U01 ("DIY Mon") is the active preset
- `14 02` → U02 ("DIY Mon offset") is the active preset (confirmed after mid-session
  preset change from U01→U02 and app restart — device remembers the last loaded preset)

### 0x15 — Set Delay Display Unit

```
Payload (2 bytes): 15 [unit]
```

Sets the delay display unit shown in the application UI. This is a **display-only** setting — the delay value itself is always transmitted in samples via opcode `0x38` regardless of the selected unit.

| Field | Byte | Type | Values |
|---|---|---|---|
| Unit | 1 | uint8 | `0x00`=ms (milliseconds, default), `0x01`=m (meters), `0x02`=ft (feet) |

Device responds with ACK (`0x01`).

**Config storage:** persisted at config offset **424** (page 8, byte 24). Value 0x00/0x01/0x02 matches the unit enum above.

**Verified from capture** `capture_20260409_220822_output_delay_unit.pcapng`:

| Frame | Raw frame | Meaning |
|---|---|---|
| #223 | `10 02 00 01 02 15 01 10 03 16` | set unit → m |
| #247 | `10 02 00 01 02 15 02 10 03 15` | set unit → ft |
| #271 | `10 02 00 01 02 15 00 10 03 17` | set unit → ms |
| #307 | `10 02 00 01 02 15 01 10 03 16` | set unit → m |

The diff-config between the two config reads in that capture shows only byte 424 changing (0x00→0x01), confirming the unit is the only thing stored.

### 0x29 — Read Preset Name

Reads the name of a user preset. The command uses a **0-based request index** that
maps to user presets U01–U30 (30 entries). F00 is the factory default and has no
entry here — its name cannot be read or written via 0x29.

**Index mapping: request index 0 = U01, 1 = U02, …, 29 = U30.**
To convert to the 0x14/0x20 slot number: `slot = request_index + 1`.

```
Payload (2 bytes): 29 [request_index]   (0x00–0x1D, i.e. 0–29)
```

Device responds with 16-byte payload: `29 [request_index] [14 bytes ASCII name]`.
Names are space-padded to 14 characters.

**Example** (from a device with two custom presets):

| Request index | User Preset | Request | Response (ASCII) |
|---|---|---|---|
| 0 | U01 | `29 00` | `"DIY Mon       "` |
| 1 | U02 | `29 01` | `"DIY Mon offset"` |
| 2–29 | U03–U30 | `29 02`–`29 1d` | `"Default Preset"` |

Cross-check with 0x14: `14 01` (U01 active) → name is at request index 0; `14 02` (U02 active) → name is at request index 1.

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
| `0x15` | 2 | OUT | Delay display unit | `15 [unit]` — 0x00=ms, 0x01=m, 0x02=ft; display-only |
| `0x20` | 2 | OUT | Load preset | `20 [slot]` — direct index: 0=F00, 1=U01…30=U30 |
| `0x2a` | 3 | OUT | Prepare link | `2a [master_ch] [slave_ch]` — one per pair, sent before linking |
| `0x21` | 2 | OUT | Store preset | `21 [slot]` — direct index, same as 0x20. **Never use slot 0 (F00)!** |
| `0x22` | 1 | OUT | Preset header | `22` — device responds `22 ffff` + 28 zeros |
| `0x26` | 15 | OUT | Store preset name | `26 [14-char name]` — space-padded, sent before 0x21. Max 14 chars! |
| `0x27` | 2 | OUT | Read config page | `27 [page]` — device responds `24 [page] [50 bytes]` |
| `0x29` | 2 | OUT | Read preset name | `29 [idx]` — idx 0=U01…29=U30 (NOT 0x14 slot); responds `29 [idx] [14 char name]` |
| `0x2c` | 1 | OUT | Device info | `2c` — device responds `2c` + 7 bytes |
| `0x2d` | 6 | BOTH | Submit lock PIN | OUT: `2d 00 [4 ASCII digits]`; IN: `2d 00 [01=correct/00=wrong]` |
| `0x2f` | 5 | OUT | Set lock PIN | `2f [4 ASCII digits]` — ⚠ locks device immediately on receipt |
| `0x30` | 10 | OUT | Compressor/limiter | `30 [ch] [ratio] [knee] [atk_lo] [atk_hi] [rel_lo] [rel_hi] [thr_lo] [thr_hi]` |
| `0x31` | 5 | OUT | Lo-pass filter | `31 [ch] [freq_lo] [freq_hi] [slope]` — log freq 0–300, slope 0=bypass |
| `0x32` | 5 | OUT | Hi-pass filter | `32 [ch] [freq_lo] [freq_hi] [slope]` — log freq 0–300, slope 0=bypass |
| `0x33` | 10 | OUT | PEQ band | `33 [ch] [band] [gain_lo] [gain_hi] [freq_lo] [freq_hi] [Q] [type] [bypass]` — outputs verified, 7 bands |
| `0x34` | 4 | OUT | Gain | `34 [ch] [val_lo] [val_hi]` — LE uint16, 0–400 |
| `0x35` | 3 | OUT | Mute | `35 [ch] [state]` — 0x00=off, 0x01=on |
| `0x36` | 3 | OUT | Phase invert | `36 [ch] [state]` — 0x00=normal, 0x01=inverted |
| `0x38` | 4 | OUT | Output delay | `38 [ch] [samples_lo] [samples_hi]` — LE uint16, 0–32640 (samples @ 48 kHz) |
| `0x39` | 3 | OUT | Test tone generator | `39 [mode] [freq_idx]` — mode: 0=off,1=pink,2=white,3=sine; freq_idx: 0x00–0x1E (ISO 1/3-oct 20Hz–20kHz) |
| `0x3e` | 10 | OUT | Noise gate | `3e [ch] [atk_lo] [atk_hi] [rel_lo] [rel_hi] [hold_lo] [hold_hi] [thr_lo] [thr_hi]` |
| `0x3b` | 3 | OUT | Channel link | `3b [ch] [link_flags]` — see below |
| `0x3a` | 3 | OUT | Matrix routing | `3a [output_ch] [input_bitmask]` |
| `0x3c` | 3 | OUT | PEQ channel bypass | `3c [ch] [state]` — 0x00=all active, 0x01=all bands bypassed |
| `0x3d` | 10 | OUT | Set channel name | `3d [ch] [8 ASCII bytes]` — zero-padded name |
| `0x40` | 1 | OUT | Poll levels | `40` — request only, no parameters |
0x33 verified on 4x4 Mini from 7 captures. **The 4x4 Mini has no GEQ** — that is a DSP 408 feature only.

**Channel byte (`ch`):** Inputs 0x00–0x03, outputs 0x04–0x07.
Confirmed for inputs: `0x00`=ch1, `0x02`=ch3. Output numbering from `dsp-408-ui`.

---

## Commands from dsp-408-ui (Not Yet Captured on 4x4 Mini)

The following command details are from the `Aeternitaas/dsp-408-ui` project, which
reverse-engineered the same Musicrown protocol for the DSP 408 over TCP/Ethernet.
The binary protocol is transport-agnostic — these should work identically over USB HID.

### 0x33 — PEQ (Parametric EQ)

Verified from 7 captures on 4x4 Mini (output channel 1, all parameters swept independently).

```
Payload (10 bytes): 33 [ch] [band] [gain_lo] [gain_hi] [freq_lo] [freq_hi] [Q] [type] [bypass]
```

- **Channel:** output channels only verified: Out1=0x04, Out2=0x05, Out3=0x06, Out4=0x07
- **Band:** 0-indexed (0=band 1 … 6=band 7); 7 bands per output channel
- **Gain:** LE uint16, raw 0–240; `gain_dB = (raw − 120) / 10.0`; ±12 dB, 0.1 dB resolution; 0 dB = raw 120
- **Frequency:** LE uint16, raw 0–300; same formula as crossover: `Hz = 19.70 × (20160/19.70)^(raw/300)`
- **Q:** uint8, raw 0–100; `Q = 0.4 × 320^(raw/100)`; min Q=0.4 (raw=0), max Q=128 (raw=100)
  - Shelf and pass filters restrict Q to 0.4–3.0 (raw 0–35) in the app UI
- **Type:** uint8
  | raw | Filter type |
  |-----|-------------|
  | 0x00 | Peak (default) |
  | 0x01 | Low Shelf |
  | 0x02 | High Shelf |
  | 0x03 | Low Pass |
  | 0x04 | High Pass |
  | 0x05 | Allpass 1st order |
  | 0x06 | Allpass 2nd order |
- **Bypass:** uint8, 0x00=active, 0x01=band bypassed (stored separately in config footer)

**Config storage:** output block bytes 16–57 (verified); each of 7 bands = 6 bytes:
`[gain_lo] [gain_hi] [freq_lo] [freq_hi] [Q] [type]`
Band bypass is NOT stored in the band data — see footer (offset 412–415).

**EQ Reset:** No dedicated opcode — the app sends one `0x33` per band with 0 dB gain, Peak type, Q_raw=25 (Q≈1.7), and these preset frequencies:

| Band | freq_raw | ≈Hz |
|------|----------|-----|
| 1 | 31 | 40 Hz |
| 2 | 71 | 102 Hz |
| 3 | 118 | 301 Hz |
| 4 | 161 | 813 Hz |
| 5 | 200 | 2001 Hz |
| 6 | 240 | 5041 Hz |
| 7 | 270 | 10081 Hz |

Verified from `capture_20260409_200328_output_peq_channel_3_reset_eq.pcapng` (Out3).

**Captured examples (Out1 band 1):**
- `33 04 00 78 00 00 00 19 00 00` → gain=0dB, freq=min, Q=25(≈1.7), Peak, active
- `33 04 00 78 00 00 00 0a 01 01` → gain=0dB, freq=min, Q=10(≈0.8), Low Shelf, bypassed

### 0x3c — PEQ Channel Bypass

Discovered from `capture_20260409_091811_output_peq_channel_1_bypass.pcapng`.

```
Payload (3 bytes): 3c [ch] [state]
```

- **Channel:** same unified numbering — Out1=0x04 … Out4=0x07
- **State:** 0x00=all PEQ bands active, 0x01=all PEQ bands bypassed for this channel
- **Config storage:** footer byte at absolute config offset 428 (Out1); predicted Out2=429, Out3=430, Out4=431

Device responds with `0x01` ACK.

**Captured:** `3c 04 01` (Out1 all bypassed) → config offset 428: 0x00→0x01

### 0x31 — Lo-Pass Crossover Filter

```
Payload (5 bytes): 31 [ch] [freq_lo] [freq_hi] [slope]
```

- **Channel:** output channels 0x04–0x07
- **Frequency:** log-scale LE uint16, raw 0–300 on 4x4 Mini. Hz = 19.70 × (20160/19.70)^(raw/300).
  DSP 408 uses 0–1000 with /1000 denominator; same frequency range, fewer steps.
- **Slope** (byte): combined bypass + slope type. See slope table below.
- **Config storage:** output block bytes 12–13 (freq), byte 15 (slope)

**Capture-verified:** Out3 freq swept raw 300→0→300→0; bypass toggled; slope sweep on hi-pass (same encoding).

### 0x32 — Hi-Pass Crossover Filter

```
Payload (5 bytes): 32 [ch] [freq_lo] [freq_hi] [slope]
```

- **Channel:** output channels 0x04–0x07
- **Frequency:** log-scale LE uint16, raw 0–300. Hz = 19.70 × (20160/19.70)^(raw/300).
  Verified: raw 128 = 379.1 Hz (user reported 378.9 Hz at ~50% fader).
- **Slope** (byte): combined bypass + slope type. See slope table below.
- **Config storage:** output block bytes 10–11 (freq), byte 14 (slope)

**Capture-verified:** Out3 freq swept raw 0→300→0→300; bypass toggled; slope swept through all 10 types.

#### Crossover Slope Encoding (byte 4 of 0x31 and 0x32)

Both commands use the same encoding for the slope byte:

| Raw | Slope | Filter type |
|-----|-------|-------------|
| 0x00 | **Bypassed** | Filter disabled |
| 0x01 | BW-6 | Butterworth 6 dB/oct |
| 0x02 | BL-6 | Bessel 6 dB/oct |
| 0x03 | BW-12 | Butterworth 12 dB/oct |
| 0x04 | BL-12 | Bessel 12 dB/oct |
| 0x05 | LR-12 | Linkwitz-Riley 12 dB/oct |
| 0x06 | BW-18 | Butterworth 18 dB/oct |
| 0x07 | BL-18 | Bessel 18 dB/oct |
| 0x08 | BW-24 | Butterworth 24 dB/oct |
| 0x09 | BL-24 | Bessel 24 dB/oct |
| 0x0a | LR-24 | Linkwitz-Riley 24 dB/oct (**device default**) |

**Bypass behavior:** When slope=0x00, the filter is bypassed. The device does not retain
the previously selected slope — on bypass, the slope value is overwritten with 0x00 in
config storage. The PC application must track the last-active slope and re-send it when
un-bypassing. After an application restart with a bypassed filter, the slope resets to
LR-24 (0x0a, the default).

Pattern: grouped by filter order (6→12→18→24 dB/oct), within each order: BW, BL, then
LR (LR only at even orders 12/24, which is physically correct for Linkwitz-Riley filters).

### 0x3a — Matrix Routing

```
Payload (3 bytes): 3a [output_ch] [input_bitmask]
```

- **Output channel:** Out1=0x04, Out2=0x05, Out3=0x06, Out4=0x07
- **Input bitmask:** InA=0x01, InB=0x02, InC=0x04, InD=0x08 (combinable; 0x00 = no input / silence)
- **Behavior:** Full bitmask sent each time — not incremental add/remove. Device ACKs with `0x01`.
- **Config byte:** Output block byte 8 stores the bitmask for each output (default diagonal: Out1=0x01, Out2=0x02, Out3=0x04, Out4=0x08).

**Verified from captures:**
- `capture_20260407_191659_matrix_Out1_from_InA_and_InB.pcapng` — Out1 mask 0x03 (InA|InB)
- `capture_20260407_191838_matrix_Out1_from_InA_InB_InC_InD.pcapng` — Out1 mask incremented to 0x07, then 0x0f
- `capture_20260407_192739_matrix_remove_source_of_Out1.pcapng` — Out1 mask 0x00 (no input)

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
| Link InA+InB+InC | `2a 00 01` + `2a 00 02` + `3b 00 07` + `3b 01 00` + `3b 02 00` + `12` |
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
| Link InA+InB+InC | `2a 00 01` + `2a 00 02` |
| Link Out1+Out2 | `2a 04 05` |
| Link Out2+Out3 | `2a 05 06` |
| Link Out3+Out4 | `2a 06 07` |
| Link Out1+2+3+4 | `2a 04 05` + `2a 04 06` + `2a 04 07` |

### 0x3d — Set Channel Name

Discovered from `capture_20260407_233926_change_name_of_out_3.pcapng` — renaming Out3 from "Out3" to "AUSGANG3".

```
Payload (10 bytes): 3d [channel] [name_byte_0] … [name_byte_7]

Captured: 3d 06 41 55 53 47 41 4e 47 33
           op ch  A  U  S  G  A  N  G  3
```

**Channel byte:** unified numbering — inputs 0x00–0x03, outputs 0x04–0x07 (Out3 = 0x06).

**Name field:** 8-byte ASCII, zero-padded. Up to 8 characters. The same 8 bytes are stored at output block bytes 0–7 and input block bytes 0–7 in the `.unt` config. Default input names ("InA"–"InD") are 3 chars zero-padded to 8 bytes, but the full 8 bytes are writable.

**Verified captures:**
- `capture_20260407_233926_change_name_of_out_3.pcapng` — Out3 (ch 0x06): `3d 06 41 55 53 47 41 4e 47 33` ("Out3"→"AUSGANG3")
- `capture_20260407_234815_change_name_of_in_c.pcapng` — InC (ch 0x02): `3d 02 45 49 4e 47 41 4e 47 43` ("InC"→"EINGANGC")

Device responds with `0x01` ACK.

### 0x20 — Load Preset

```
Payload (2 bytes): 20 [slot]
```

Uses a **direct slot index**: 0=F00, 1=U01, 2=U02, …, 30=U30.
Previous documentation (from DSP 408 cross-reference) incorrectly stated 1-based — our
captures confirm it is zero-based with F00 at index 0.

> **WARNING — F00 is the factory default preset (read-only).** Never send `0x21` (store)
> with slot=0. Overwriting F00 could corrupt the device's default state and may be
> irreversible without a full firmware reflash.

**Verified slot values:**
| Preset | `0x20` payload |
|---|---|
| F00 (factory) | `20 00` |
| U01 | `20 01` |
| U02 | `20 02` |
| U30 | `20 1e` |

**Load sequence (capture-verified):**
1. `0x20 [slot]` → ACK
2. `0x27 00` … `0x27 08` → 9× `0x24` config page responses
3. `0x12` activate → ACK

Mid-session preset change requires no re-init — just step 1→3 above.

**Config page 0 marker bytes (bytes 0–1 of the 450-byte config blob):**
- `ff ff` — user preset with customised content (U01, U02)
- `ff 00` — factory/default state (F00, or an empty user slot that was never modified)

### 0x21 — Store Preset

```
Payload (2 bytes): 21 [slot]
```

Stores the current active config to the specified slot. Same direct slot index as `0x20`
(1=U01 … 30=U30).

> **WARNING — Never store to slot 0 (F00).** F00 is the factory default preset and must
> remain read-only. Overwriting it may permanently corrupt the device baseline.

Device ACK is delayed ~2 seconds (device writes to non-volatile flash). The host must
wait for ACK before proceeding.

**Store sequence (capture-verified):**
1. `0x26 [name]` → ACK  (set the name first)
2. `0x21 [slot]` → ACK  (~2 s delay while device writes flash)
3. `0x12` activate → ACK

### 0x26 — Store Preset Name

```
Payload (15 bytes): 26 [14 chars ASCII, space-padded]
```

Sets the name for the currently active preset slot. Must be sent **before** `0x21`.
Maximum name length is **14 characters** — space-pad shorter names to fill 14 bytes.

> **WARNING — Do not exceed 14 characters.** Sending a longer name is known to crash
> the DSP firmware and may require a power cycle to recover.

### 0x38 — Output Delay

```
Payload (4 bytes): 38 [ch] [samples_lo] [samples_hi]
```

Sets the per-output delay in samples at the 48 kHz sample rate.

| Field | Bytes | Type | Range | Formula |
|---|---|---|---|---|
| Channel | 1 | uint8 | 0x04–0x07 | Outputs only (Out1–Out4) |
| Samples | 2–3 | uint16 LE | 0–32640 | ms = raw / 48 |

**Max delay:** 32640 samples = 680.000 ms (exactly 680 × 48).

**Config storage:** output block bytes 70–71 (uint16 LE, same value as command).

**Capture-verified:** Out4 swept 0→32640→0→32640, config diff confirmed
offset 70–71 changed to 0x80,0x7f = 32640.

**Note:** This opcode was not previously known even in the `dsp-408-ui` project.

### 0x3E — Noise Gate (Input Channels)

```
Payload (10 bytes): 3e [ch] [atk_lo] [atk_hi] [rel_lo] [rel_hi] [hold_lo] [hold_hi] [thr_lo] [thr_hi]
```

Sets all 4 noise gate parameters for an input channel in a single command.
All parameters are uint16 LE.

| Field | Bytes | Raw Range | UI Range | Formula |
|---|---|---|---|---|
| Attack | 2–3 | 0–998 | 1–999 ms | ms = raw + 1 |
| Release | 4–5 | 0–2999 | 1–3000 ms | ms = raw + 1 |
| Hold | 6–7 | 9–998 | 10–999 ms | ms = raw + 1 (confirmed: raw 9 → 10 ms) |
| Threshold | 8–9 | 1–180 | −90.0 to 0.0 dB | dB = raw × 0.5 − 90.0 |

**Note:** The `ms = raw + 1` encoding is identical to the compressor attack/release.
The raw minimum for attack was previously noted as 34 from captured sweeps; the
true minimum is 0 (= 1 ms). Hold confirms the formula exactly: raw 9 → 10 ms.

**Channel byte:** input channels only (0x00–0x03).

**Config storage:** input block bytes 10–17 (4 × uint16 LE in the same order as the command).

**Capture-verified:** 6 captures on InC sweeping each parameter independently.
Confirmed by diff-config comparing config page reads before/after:
- Attack → config bytes 10–11 (e.g. max 998 = 0xe6,0x03)
- Release → config bytes 12–13 (e.g. max 2999 = 0xb7,0x0b)
- Hold → config bytes 14–15 (e.g. max 998 = 0xe6,0x03)
- Threshold → config bytes 16–17 (e.g. max 180 = 0xb4,0x00)

### 0x39 — Test Tone Generator

```
Payload (3 bytes): 39 [mode] [freq_idx]
```

Enables or disables the internal test signal generator. The device ACKs with `0x01`.

| Field | Byte | Type | Values |
|---|---|---|---|
| Mode | 1 | uint8 | 0x00=off (analog input), 0x01=pink noise, 0x02=white noise, 0x03=sine wave |
| Freq index | 2 | uint8 | Sine frequency index (0x00–0x1E); 0x00 for noise modes |

**Sine wave frequency table** (ISO 1/3-octave, 31 steps, index 0x00–0x1E):

| Idx | Hz | Idx | Hz | Idx | Hz |
|---|---|---|---|---|---|
| 0x00 | 20 | 0x0B | 250 | 0x16 | 3150 |
| 0x01 | 25 | 0x0C | 315 | 0x17 | 4000 |
| 0x02 | 31.5 | 0x0D | 400 | 0x18 | 5000 |
| 0x03 | 40 | 0x0E | 500 | 0x19 | 6300 |
| 0x04 | 50 | 0x0F | 630 | 0x1A | 8000 |
| 0x05 | 63 | 0x10 | 800 | 0x1B | 10000 |
| 0x06 | 80 | 0x11 | 1000 | 0x1C | 12500 |
| 0x07 | 100 | 0x12 | 1250 | 0x1D | 16000 |
| 0x08 | 125 | 0x13 | 1600 | 0x1E | 20000 |
| 0x09 | 160 | 0x14 | 2000 | | |
| 0x0A | 200 | 0x15 | 2500 | | |

**Behavior notes:**
- For noise modes (pink/white), `freq_idx` is always `0x00`.
- When disabling (mode=`0x00`), the software sends the **last-used sine freq index** as `freq_idx`
  (carried state — device ignores it in off mode, but the config byte retains it).
- The sine frequency index **persists** in the config even when switching to noise or off mode.

**Config storage** (confirmed from diff-config on all 4 captures):
- Config offset **420** (page 8, byte 20): test tone mode — changes immediately on `0x39`
- Config offset **421**: always `0x00`
- Config offset **422** (page 8, byte 22): last sine frequency index — set by sine selection, retained when mode changes

**Persistence:** The device stores the test tone state in its live config. The state survives application
restarts (the app reads it back via `0x27`). All preset slots in `.unt` files store `0x00` (off) at
offset 420 when the test tone was off at export time.

**Capture-verified:** 4 captures (white noise, pink noise, sine wave frequency sweep 20Hz→20kHz→20Hz→25Hz,
analog input disable). Sine wave sweep confirmed all 31 frequency indices 0x00–0x1E in sequence.

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
- [x] **Delay command:** Opcode `0x38` — `38 [ch] [samples_lo] [samples_hi]`, uint16 LE samples at 48 kHz.
      Config stored at output block bytes 70–71. First known implementation (not in dsp-408-ui).
- [x] **Compressor/Limiter:** Opcode `0x30` — 10-byte payload, all 5 params sent in one frame.
      `30 [ch] [ratio] [knee] [atk_lo] [atk_hi] [rel_lo] [rel_hi] [thr_lo] [thr_hi]`
      Threshold (bytes 8–9): uint16 LE, `dB = raw/2 − 90`, range 0–220 (−90 to +20 dB, 0.5 dB/step).
      Attack (bytes 4–5): uint16 LE, `ms = raw + 1`, range 0–998 (1–999 ms).
      Release (bytes 6–7): uint16 LE, `ms = raw + 1`, range 9–2999 (10–3000 ms).
      Ratio (byte 2): uint8 enum 0–15 (0=1:1.0 … 14=1:20.0, 15=Limit).
      Knee (byte 3): uint8 direct dB, 0–12.
      Config storage: output block bytes 58–65 (same field order as command payload).
- [x] **Phase invert:** Opcode `0x36` — `36 [ch] [state]`, 0x00=normal, 0x01=inverted.
      Also stored in config at input block offset 20 (byte within 24-byte block).
      Captured: InC toggled normal↔inverted. InA+InB were already inverted.
- [x] **Noise gate:** Opcode `0x3E` — 10-byte payload with attack/release/hold/threshold.
      Config stored at input block bytes 10–17 (4 × uint16 LE). 6 captures verified.
- [x] **Crossover filters:** Opcodes `0x31`/`0x32` capture-verified on 4x4 Mini.
      Raw 0–300 maps to 19.7–20160 Hz via Hz = 19.70 × (20160/19.70)^(raw/300).
      DSP 408 uses 0–1000; same range, different step count.
- [x] **Routing matrix verified on 4x4 Mini:** Opcode `0x3a` capture-confirmed. Config byte 8 of each output block stores the input bitmask.
- [x] **Output PEQ verified on 4x4 Mini:** Opcode `0x33` — 10-byte payload. 7 bands per output channel. Gain ±12dB (raw 0–240, 0.1dB step), freq raw 0–300 (same scale as crossover), Q raw 0–100 (log Q=0.4×320^(raw/100)), 7 filter types (Peak/Low Shelf/High Shelf/Low Pass/High Pass/Allpass 1st/Allpass 2nd). Band bypass in footer bitmask. Channel bypass via `0x3c` command. Confirmed from 7 captures.
- [x] **Footer bytes 416–427:** Bytes 416–423 and 425–427 are always zero (padding). Byte 424 = delay display unit (0x00=ms default, 0x01=m, 0x02=ft), set by opcode `0x15`, verified from `capture_20260409_220822_output_delay_unit.pcapng` diff-config. Note: all 5 previously analyzed presets had byte 424=0x00 (ms was selected), explaining why it appeared to be all-zero.

---

## Configuration File Format (`.unt`)

Reverse-engineered from `miniDSP current settings.unt` and `miniDSP current settings 260409.unt`.
Both files are exactly **13010 bytes**.

### File Structure Overview

```
Offset    Size   Content
────────  ─────  ─────────────────────────────────────────────
0x000       50   File header
0x032      432   Slot 0 = U01 (prefix byte + 429 config bytes + CRLF)
0x1E2      432   Slot 1 = U02
  ...
0x3112     432   Slot 29 = U30
```

The file stores **30 user preset slots** (U01–U30). The factory preset F00 is read-only in device firmware and is NOT stored in the .unt file.

**Slot structure (432 bytes each):**
- Byte 0: **slot number** (1-indexed, 1=U01, 2=U02, ..., 30=U30)
- Bytes 1–429: config blob (429 bytes — see Preset Structure below)
- Bytes 430–431: `0x0D 0x0A` (CRLF — Windows text-mode record terminator)

Empty/unused slots are filled with `0x64` (`'d'`) repeated for all 432 bytes.

### File Header (50 bytes, offset 0x00–0x31)

```
Offset  Size  Field
──────  ────  ─────────────────────────────────────────────────────────────
0x00    16    Magic: "***4x4MINIV010**"
0x10     1    Device address (always 0x01)
0x11     1    Active preset slot (1=U01, 2=U02, ..., 30=U30)
0x12     1    Max user presets (always 0x1E = 30)
0x13     4    ASCII "0000" — purpose unknown
0x17     2    Always 0x00 0x00
0x19     2    Device counter: 0x270F (same value as 0x2C USB response bytes 2–3)
0x1B     2    Always 0x00 0x00
0x1D     4    Device lock PIN (4 ASCII digits, e.g. "7654" = 37 36 35 34; "0000" = default/no-PIN)
0x21     1    Always 0x00
0x22     1    Firmware version? (0x0A = 10, matches "V010" from 0x13 USB response)
0x23     1    Always 0x00
0x24    14    Product name: "4x4D Amplifier"
```

**Key header discoveries (verified from 2 files):**
- `0x11` changes between files: old file=0x02 (U02 was active), new file=0x1E=30 (U30 was active)
- `0x1D–0x20` holds the PIN: old file="1234", new file="7654" (matches our device lock captures)
- `0x19–0x1A` = 0x270F matches the constant in the `0x2C` device-info USB response

### Preset Structure (stored config blob, 429 bytes)

The 429-byte config blob stored per slot is a partial view of the 450-byte USB config.
The last 21 bytes (USB config offsets 429–449) are **not stored** in the .unt file —
they are consistently zero and include the CRLF record separator at the slot boundary.

```
Offset  Size  Field
──────  ────  ─────────────────────────────────────
  0      2    Marker: 0xFF 0xFF
  2     14    Preset name (ASCII, space-padded to 14 chars)
 16    4×24   Input channel blocks (InA, InB, InC, InD)
112   4×74    Output channel blocks (Out1, Out2, Out3, Out4)
408      2    Input mute bitmask, LE uint16 (bit 0=In1 .. bit 3=In4)
410      2    Output mute bitmask, LE uint16 (bit 0=Out1 .. bit 3=Out4)
412      1    Out1 PEQ band bypass bitmask (bit 0=band1 .. bit 6=band7; 0x00=all active)
413      1    Out2 PEQ band bypass bitmask
414      1    Out3 PEQ band bypass bitmask
415      1    Out4 PEQ band bypass bitmask
416      4    Always 0x00 — reserved (padding)
420      1    **Test tone mode**: 0x00=off, 0x01=pink noise, 0x02=white noise, 0x03=sine wave (set by `0x39` command)
421      1    Always 0x00 — reserved
422      1    **Sine wave frequency index**: last used sine freq (0x00=20Hz … 0x1E=20kHz); persists across mode changes
423      1    Always 0x00 — reserved (padding)
424      1    **Delay display unit**: 0x00=ms, 0x01=m, 0x02=ft (set by `0x15` command)
425      3    Always 0x00 — reserved (padding)
428      1    Out1 PEQ channel bypass (0x00=active, 0x01=all bands bypassed)
[429–449 NOT stored — slot ends with CRLF at absolute position 430–431]
```

Preset names found across both .unt files: `"DIY Mon"`, `"DIY Mon offset"`, `"test preset"`.

### Input Channel Block (24 bytes)

```
Offset  Size  Field
──────  ────  ─────────────────────────────────────
 0–7     8    Channel name (ASCII, zero-padded; default 3-char "InA"/"InB"/"InC"/"InD", up to 8 chars e.g. "EINGANGC")
10–11    2    **Gate attack**, LE uint16, raw 0–998 (ms = raw + 1 → 1–999 ms)
12–13    2    **Gate release**, LE uint16, raw 0–2999 (ms = raw + 1 → 1–3000 ms)
14–15    2    **Gate hold**, LE uint16, raw 9–998 (ms = raw + 1 → 10–999 ms)
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
 0–7     8    Channel name (8-byte ASCII, zero-padded: "Out1"–"Out4"; up to 8 chars e.g. "AUSGANG3")
 8       1    **Input routing mask** — bitmask of sources feeding this output (InA=0x01, InB=0x02, InC=0x04, InD=0x08). Default diagonal routing makes this look like a channel ID, but it's the `0x3a` input bitmask.
 9       1    Always 0x00
10–11    2    **Crossover hi-pass freq**, LE uint16, raw 0–300 (same as 0x32 command)
12–13    2    **Crossover lo-pass freq**, LE uint16, raw 0–300 (same as 0x31 command, default 300 = 20.16 kHz)
14       1    **Crossover hi-pass slope**, 0x00=bypassed, 0x01–0x0a=active slope type (see slope table)
15       1    **Crossover lo-pass slope**, 0x00=bypassed, 0x01–0x0a=active slope type (see slope table)
16–57   42    **PEQ band data** — 7 bands × 6 bytes each (verified)
58       1    **Compressor ratio**, uint8 enum 0–15 (see COMP_RATIO_* constants; 0=1:1.0, 15=Limit)
59       1    **Compressor knee**, uint8 0–12 (direct dB, 0=hard knee, 12=softest)
60–61    2    **Compressor attack**, LE uint16, raw 0–998 (ms = raw + 1, range 1–999 ms)
62–63    2    **Compressor release**, LE uint16, raw 9–2999 (ms = raw + 1, range 10–3000 ms)
64–65    2    **Compressor threshold**, LE uint16, raw 0–220 (dB = raw/2 − 90, range −90 to +20 dB)
66–67    2    **Output gain**, LE uint16, raw 0–400 (same scale as 0x34 command)
68       1    **Phase invert**: 0x00=normal, 0x01=inverted (same as 0x36 command)
69       1    Always 0x00 (mute state is NOT here — see footer bitmasks)
70–71    2    **Output delay**, LE uint16, samples at 48 kHz (0–32640 = 0–680 ms, same as 0x38 command)
72       1    Routing/link flags (same scheme as input)
73       1    Always 0x00
```

**PEQ band data (bytes 16–57, 42 bytes, verified):**

7 bands × 6 bytes per band. Each band: `[gain_lo] [gain_hi] [freq_lo] [freq_hi] [Q] [type]`
- gain: LE uint16, raw 0–240, 0dB=120
- freq: LE uint16, raw 0–300 (same formula as crossover)
- Q: uint8, raw 0–100
- type: uint8 (0=Peak, 1=Low Shelf, 2=High Shelf, 3=Low Pass, 4=High Pass, 5=Allpass 1st, 6=Allpass 2nd)

Band bypass state is NOT stored per-band — it is stored as a bitmask per channel in the config footer (offset 412–415).

In the default config, observed constant values across bands suggest frequency and Q are pre-set,
with per-band gain values varying (71, 118, 161, 200, 240, 270 — EQ center frequencies in raw scale).

**Compressor parameters (bytes 58–65):**

Verified by 5 diff-config captures (one per parameter), each showing exactly one field change:
- threshold default: raw 220 (+20.0 dB) — `capture_20260407_184757`
- attack default: raw 49 (50 ms) — `capture_20260407_184842`
- release default: raw 499 (500 ms) — `capture_20260407_185003`
- ratio/knee: both 0 (no compression, hard knee) — `capture_20260407_185056/185154`

### Empty Slot Filler

Unused preset slots are filled with `0x64` (`'d'`) repeated for all 432 bytes.
The fixed file size of 13010 bytes (50 + 30 × 432) is a software requirement.

### .unt Format Unknowns

- [x] ~~Input/output gain location~~ → Input block bytes 18–19, output block bytes 66–67 (uint16 LE, raw 0–400)
- [x] ~~Mute state location~~ → Footer bitmasks at preset offsets 408–409 (input) and 410–411 (output), NOT in per-channel blocks. Verified by comparing startup captures with In4+Out4 muted vs unmuted.
- [x] ~~Input block bytes 10–17~~ → Noise gate parameters: attack (10–11), release (12–13), hold (14–15), threshold (16–17), all LE uint16
- [x] ~~Output EQ band count and parameter mapping~~ → 7 bands × 6 bytes: [gain_lo,gain_hi,freq_lo,freq_hi,Q,type]. Verified from PEQ captures.
- [x] ~~Output block bytes 12–13 (always 300)~~ → Lo-pass crossover frequency (raw 300 = 20.16 kHz = default/max)
- [x] ~~Whether the file can hold more than 2 presets~~ → Yes. File holds 30 slots (U01–U30). Verified: `miniDSP current settings 260409.unt` has U01 + U30 both filled.
- [x] ~~Header byte 0x11 meaning~~ → Active preset slot (1-indexed: 1=U01, 2=U02, ..., 30=U30). Verified: old file has 0x02 (U02 active), new file has 0x1E (U30 active).
- [x] ~~Header bytes 0x1D–0x20~~ → Device lock PIN (4 ASCII digits). Old file has "1234", new file has "7654" matching our device-lock capture.
- [x] ~~Input block unknown bytes (8–9, 21, 23)~~ → Always zero (pure padding). Verified across 5 presets.
- [x] ~~Output block unknown bytes (9, 69, 73)~~ → Always zero (pure padding). Verified across 5 presets.
- [x] ~~Footer bytes 416–427~~ → Bytes 416–419 and 423 and 425–427 are padding (always zero). Byte 420 = test tone mode (0x00=off, 0x01=pink, 0x02=white, 0x03=sine). Byte 421 = always 0x00. Byte 422 = last sine frequency index (0x00–0x1E). Byte 424 = delay display unit (0x00=ms, 0x01=m, 0x02=ft). All presets analyzed had ms selected (0x00), which appeared as all-zero until the delay unit capture revealed byte 424.
- [x] ~~Crossover type/slope~~ → bytes 10–11 = hi-pass freq, 12–13 = lo-pass freq, byte 14 = hi-pass slope, byte 15 = lo-pass slope. All stored in config; slope 0x00 = bypassed, 0x01–0x0a = active slope type.
- [x] ~~Output block compressor location~~ → bytes 58–65: ratio(1B), knee(1B), attack(2B LE), release(2B LE), threshold(2B LE). Verified by 5 diff-config captures.
- [x] ~~Output block bytes 6–7~~ → bytes 0–7 are the full 8-byte channel name field (verified: "Out3" → "AUSGANG3" changes all 8 bytes)
- [x] ~~Output block bytes 70–71~~ → Output delay in samples at 48 kHz (uint16 LE, 0–32640 = 0–680 ms)
- [ ] Header bytes 0x13–0x16: ASCII "0000" — purpose unknown (device address in padded ASCII? version field?)
- [ ] Purpose of the "4x4D Amplifier" product string (header 0x24) vs "Dsp Process" USB descriptor string
