"""
the t.racks DSP 4x4 Mini — USB HID protocol encoding/decoding.

Frame format (inside 64-byte HID report):
    10 02 [SRC] [DST] [LEN] [PAYLOAD...] 10 03 [CHK]

Checksum = XOR of LEN and all payload bytes.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

VENDOR_ID = 0x0168
PRODUCT_ID = 0x0821
REPORT_SIZE = 64

# Opcodes
OP_INIT = 0x10
OP_ACTIVATE = 0x12
OP_FIRMWARE = 0x13
OP_PRESET_INDEX = 0x14
OP_SET_DELAY_UNIT = 0x15  # set delay display unit (0x00=ms, 0x01=m, 0x02=ft)
OP_LOAD_PRESET = 0x20   # direct slot index: 0=F00, 1=U01 … 30=U30
OP_STORE_PRESET = 0x21  # direct slot index: 1=U01 … 30=U30  (NEVER 0/F00!)
OP_PRESET_HEADER = 0x22
OP_STORE_NAME = 0x26    # 14-char name, space-padded; send BEFORE 0x21
OP_READ_CONFIG = 0x27
OP_READ_NAME = 0x29
OP_DEVICE_INFO = 0x2C
OP_SUBMIT_PIN = 0x2D    # PIN auth when device is locked (request + response)
OP_SET_LOCK_PIN = 0x2F  # Set lock PIN — ⚠ LOCKS DEVICE IMMEDIATELY on receipt
OP_COMPRESSOR = 0x30
OP_LOPASS = 0x31
OP_HIPASS = 0x32
OP_GAIN = 0x34
OP_MUTE = 0x35
OP_PHASE = 0x36
OP_DELAY = 0x38
OP_MATRIX = 0x3A
OP_LINK = 0x3B       # channel link state; send OP_PREPARE_LINK first when linking
OP_PREPARE_LINK = 0x2A  # declare master↔slave pair before 0x3B (linking only, not unlinking)
OP_PEQ = 0x33            # PEQ band; outputs verified, 7 bands per channel
OP_PEQ_BYPASS = 0x3C     # PEQ channel bypass (bypasses all bands for that channel)
OP_SET_CHANNEL_NAME = 0x3D  # set channel display name (8-byte ASCII, zero-padded)
OP_GATE = 0x3E
OP_TEST_TONE = 0x39      # test tone generator (mode + sine freq index); config offset 420/422
OP_POLL = 0x40

# Test tone generator mode values (byte 1 of 0x39 payload)
# State persisted at config offset 420; sine freq index at offset 422.
TONE_OFF   = 0x00  # off — pass-through / analog input (default)
TONE_PINK  = 0x01  # pink noise
TONE_WHITE = 0x02  # white noise
TONE_SINE  = 0x03  # sine wave at selected frequency

# Sine wave frequency indices (byte 2 of 0x39 payload when mode=TONE_SINE)
# ISO 1/3-octave series, 31 steps, 20 Hz to 20 kHz.
SINE_FREQ_20HZ    = 0x00
SINE_FREQ_25HZ    = 0x01
SINE_FREQ_31HZ    = 0x02
SINE_FREQ_40HZ    = 0x03
SINE_FREQ_50HZ    = 0x04
SINE_FREQ_63HZ    = 0x05
SINE_FREQ_80HZ    = 0x06
SINE_FREQ_100HZ   = 0x07
SINE_FREQ_125HZ   = 0x08
SINE_FREQ_160HZ   = 0x09
SINE_FREQ_200HZ   = 0x0A
SINE_FREQ_250HZ   = 0x0B
SINE_FREQ_315HZ   = 0x0C
SINE_FREQ_400HZ   = 0x0D
SINE_FREQ_500HZ   = 0x0E
SINE_FREQ_630HZ   = 0x0F
SINE_FREQ_800HZ   = 0x10
SINE_FREQ_1KHZ    = 0x11
SINE_FREQ_1K25HZ  = 0x12
SINE_FREQ_1K6HZ   = 0x13
SINE_FREQ_2KHZ    = 0x14
SINE_FREQ_2K5HZ   = 0x15
SINE_FREQ_3K15HZ  = 0x16
SINE_FREQ_4KHZ    = 0x17
SINE_FREQ_5KHZ    = 0x18
SINE_FREQ_6K3HZ   = 0x19
SINE_FREQ_8KHZ    = 0x1A
SINE_FREQ_10KHZ   = 0x1B
SINE_FREQ_12K5HZ  = 0x1C
SINE_FREQ_16KHZ   = 0x1D
SINE_FREQ_20KHZ   = 0x1E

# PEQ filter type values (byte 8 of 0x33 command)
PEQ_TYPE_PEAK       = 0x00
PEQ_TYPE_LOW_SHELF  = 0x01
PEQ_TYPE_HIGH_SHELF = 0x02
PEQ_TYPE_LOW_PASS   = 0x03
PEQ_TYPE_HIGH_PASS  = 0x04
PEQ_TYPE_ALLPASS1   = 0x05  # 1st-order allpass
PEQ_TYPE_ALLPASS2   = 0x06  # 2nd-order allpass

# Crossover slope/bypass values (byte 4 of 0x31/0x32)
# 0x00 = filter bypassed; non-zero = active with slope type.
# NOTE: when bypassed, the slope selection is lost on the device — the
# application must remember the last-active slope and re-send it on un-bypass.
SLOPE_BYPASS = 0x00
SLOPE_BW6 = 0x01   # Butterworth 6 dB/oct
SLOPE_BL6 = 0x02   # Bessel 6 dB/oct
SLOPE_BW12 = 0x03  # Butterworth 12 dB/oct
SLOPE_BL12 = 0x04  # Bessel 12 dB/oct
SLOPE_LR12 = 0x05  # Linkwitz-Riley 12 dB/oct
SLOPE_BW18 = 0x06  # Butterworth 18 dB/oct
SLOPE_BL18 = 0x07  # Bessel 18 dB/oct
SLOPE_BW24 = 0x08  # Butterworth 24 dB/oct
SLOPE_BL24 = 0x09  # Bessel 24 dB/oct
SLOPE_LR24 = 0x0A  # Linkwitz-Riley 24 dB/oct (device default)

# Delay display unit values (byte 1 of 0x15 payload; stored at config offset 424)
DELAY_UNIT_MS = 0x00  # milliseconds (default)
DELAY_UNIT_M  = 0x01  # meters
DELAY_UNIT_FT = 0x02  # feet

# Compressor ratio indices (byte 2 of 0x30 payload)
COMP_RATIO_1_1  = 0x00  # 1:1.0 — no compression (default)
COMP_RATIO_1_11 = 0x01  # 1:1.1
COMP_RATIO_1_13 = 0x02  # 1:1.3
COMP_RATIO_1_15 = 0x03  # 1:1.5
COMP_RATIO_1_17 = 0x04  # 1:1.7
COMP_RATIO_1_2  = 0x05  # 1:2.0
COMP_RATIO_1_25 = 0x06  # 1:2.5
COMP_RATIO_1_3  = 0x07  # 1:3.0
COMP_RATIO_1_35 = 0x08  # 1:3.5
COMP_RATIO_1_4  = 0x09  # 1:4.0
COMP_RATIO_1_5  = 0x0A  # 1:5.0
COMP_RATIO_1_6  = 0x0B  # 1:6.0
COMP_RATIO_1_8  = 0x0C  # 1:8.0
COMP_RATIO_1_10 = 0x0D  # 1:10.0
COMP_RATIO_1_20 = 0x0E  # 1:20.0
COMP_RATIO_LIMIT = 0x0F # Hard limiter


def checksum(length: int, payload: bytes) -> int:
    """XOR of length byte and all payload bytes."""
    chk = length
    for b in payload:
        chk ^= b
    return chk & 0xFF


def build_frame(payload: bytes) -> bytes:
    """Build a 64-byte HID OUT report from a payload.

    Frame: 10 02 00 01 [LEN] [PAYLOAD] 10 03 [CHK] [zero-pad to 64]
    """
    length = len(payload)
    chk = checksum(length, payload)
    frame = bytes([0x10, 0x02, 0x00, 0x01, length]) + payload + bytes([0x10, 0x03, chk])
    # Pad to 64 bytes
    frame += b"\x00" * (REPORT_SIZE - len(frame))
    return frame


def parse_frame(data: bytes) -> tuple[int, int, int, bytes] | None:
    """Parse a 64-byte HID IN report.

    Returns (src, dst, length, payload) or None if framing is invalid.
    """
    if len(data) < 8 or data[0] != 0x10 or data[1] != 0x02:
        log.debug("parse_frame: bad STX (got %s, need 10 02)",
                  data[:2].hex(" ") if len(data) >= 2 else "<short>")
        return None
    src = data[2]
    dst = data[3]
    length = data[4]
    if 5 + length + 3 > len(data):
        log.debug("parse_frame: truncated (len=%d, need %d, got %d)",
                  length, 5 + length + 3, len(data))
        return None
    payload = data[5 : 5 + length]
    etx1 = data[5 + length]
    etx2 = data[5 + length + 1]
    chk = data[5 + length + 2]
    if etx1 != 0x10 or etx2 != 0x03:
        log.debug("parse_frame: bad ETX (got %02x %02x, need 10 03)", etx1, etx2)
        return None
    expected = checksum(length, payload)
    if chk != expected:
        log.debug("parse_frame: bad checksum (got %02x, want %02x)", chk, expected)
        return None
    return src, dst, length, payload


# --- Command builders ---

def cmd_poll() -> bytes:
    """Build a level-poll command (0x40)."""
    return build_frame(bytes([OP_POLL]))


def cmd_lopass(channel: int, freq_raw: int, slope: int = SLOPE_BYPASS) -> bytes:
    """Build a low-pass crossover command (0x31).

    channel: unified index (outputs 0x04–0x07)
    freq_raw: 0–300 (log scale, Hz = 19.70 × (20160/19.70)^(raw/300), 19.7 Hz–20.16 kHz)
    slope: 0x00=bypassed, 0x01–0x0a=active with slope type (see SLOPE_* constants)
    """
    freq_raw = max(0, min(300, freq_raw))
    lo = freq_raw & 0xFF
    hi = (freq_raw >> 8) & 0xFF
    return build_frame(bytes([OP_LOPASS, channel, lo, hi, slope]))


def cmd_hipass(channel: int, freq_raw: int, slope: int = SLOPE_BYPASS) -> bytes:
    """Build a high-pass crossover command (0x32).

    channel: unified index (outputs 0x04–0x07)
    freq_raw: 0–300 (log scale, Hz = 19.70 × (20160/19.70)^(raw/300), 19.7 Hz–20.16 kHz)
    slope: 0x00=bypassed, 0x01–0x0a=active with slope type (see SLOPE_* constants)
    """
    freq_raw = max(0, min(300, freq_raw))
    lo = freq_raw & 0xFF
    hi = (freq_raw >> 8) & 0xFF
    return build_frame(bytes([OP_HIPASS, channel, lo, hi, slope]))


def cmd_mute(channel: int, mute: bool) -> bytes:
    """Build a mute command (0x35).

    channel: 0-indexed (0=ch1, 1=ch2, 2=ch3, 3=ch4)
    mute: True=mute on, False=mute off
    """
    return build_frame(bytes([OP_MUTE, channel, 0x01 if mute else 0x00]))


def cmd_gain(channel: int, raw_value: int) -> bytes:
    """Build an input gain command (0x34).

    channel: 0-indexed
    raw_value: 0–400  (dB = raw × 0.1 − 28)
    """
    raw_value = max(0, min(400, raw_value))
    lo = raw_value & 0xFF
    hi = (raw_value >> 8) & 0xFF
    return build_frame(bytes([OP_GAIN, channel, lo, hi]))


def cmd_phase(channel: int, inverted: bool) -> bytes:
    """Build a phase invert command (0x36).

    channel: unified index (inputs 0-3, outputs 4-7)
    inverted: True=180° inverted, False=normal
    """
    return build_frame(bytes([OP_PHASE, channel, 0x01 if inverted else 0x00]))


def cmd_delay(channel: int, samples: int) -> bytes:
    """Build an output delay command (0x38).

    channel: unified index (outputs 0x04–0x07)
    samples: 0–32640 (delay in samples at 48 kHz; ms = samples / 48)
    """
    samples = max(0, min(32640, samples))
    lo = samples & 0xFF
    hi = (samples >> 8) & 0xFF
    return build_frame(bytes([OP_DELAY, channel, lo, hi]))


def cmd_set_delay_unit(unit: int) -> bytes:
    """Build a delay display unit command (0x15).

    unit: DELAY_UNIT_MS=0x00, DELAY_UNIT_M=0x01, DELAY_UNIT_FT=0x02
    Display-only — protocol always transmits delay in samples via 0x38.
    Persisted at config offset 424.
    """
    return build_frame(bytes([OP_SET_DELAY_UNIT, unit & 0xFF]))


def cmd_test_tone(mode: int, freq_index: int = 0) -> bytes:
    """Build a test tone generator command (0x39).

    Enables or disables the internal signal generator. Device ACKs with 0x01.
    State is persisted at config offset 420 (mode) and 422 (last sine freq index).

    mode:       TONE_OFF=0x00, TONE_PINK=0x01, TONE_WHITE=0x02, TONE_SINE=0x03
    freq_index: SINE_FREQ_* constant (0x00=20Hz … 0x1E=20kHz); 0x00 for noise modes.
                When disabling (mode=TONE_OFF), pass the last used sine freq index
                so the device retains it in config — or just use 0x00.

    Captured examples:
      White noise:  39 02 00
      Pink noise:   39 01 00
      Sine 20 Hz:   39 03 00
      Sine 20 kHz:  39 03 1e
      Off (after sine 25Hz session): 39 00 01
    """
    freq_index = max(0, min(0x1E, freq_index))
    return build_frame(bytes([OP_TEST_TONE, mode & 0xFF, freq_index & 0xFF]))


def cmd_matrix_route(output_ch: int, input_mask: int) -> bytes:
    """Build a matrix routing command (0x3A).

    Sets which input(s) feed the given output. Sends the full bitmask each time.

    output_ch:  output channel index (0x04=Out1, 0x05=Out2, 0x06=Out3, 0x07=Out4)
    input_mask: bitmask of sources (InA=0x01, InB=0x02, InC=0x04, InD=0x08; 0x00=silence)
    """
    return build_frame(bytes([OP_MATRIX, output_ch, input_mask & 0x0F]))


def cmd_prepare_link(master_ch: int, slave_ch: int) -> bytes:
    """Build a prepare-link command (0x2A).

    Must be sent once per master↔slave pair immediately before cmd_channel_link()
    when linking channels. Not sent when unlinking.

    master_ch: unified channel index of the master (inputs 0-3, outputs 4-7)
    slave_ch:  unified channel index of the slave

    For N-channel links send one cmd_prepare_link per slave, then all cmd_channel_link calls.
    Example — link InA+InB+InC:
        cmd_prepare_link(0, 1)  # InA→InB
        cmd_prepare_link(0, 2)  # InA→InC
        cmd_channel_link(0, 0x07)  # InA master: bits 0|1|2
        cmd_channel_link(1, 0x00)  # InB slave
        cmd_channel_link(2, 0x00)  # InC slave
        cmd_activate()
    """
    return build_frame(bytes([OP_PREPARE_LINK, master_ch & 0xFF, slave_ch & 0xFF]))


def cmd_channel_link(channel: int, link_flags: int) -> bytes:
    """Build a channel link state command (0x3B).

    Sets the link bitmask for one channel. Send for every affected channel
    (both master and all slaves). Preceded by cmd_prepare_link() per slave pair
    when linking; no prepare needed when unlinking.

    channel:    unified channel index (inputs 0-3, outputs 4-7)
    link_flags: bitmask within the 4-channel group:
                  inputs:  InA=0x01, InB=0x02, InC=0x04, InD=0x08
                  outputs: Out1=0x01, Out2=0x02, Out3=0x04, Out4=0x08
                Master gets OR of all linked bits; slaves get 0x00.
                Standalone (unlinked) channel gets its own bit only (e.g. InA=0x01).
    """
    return build_frame(bytes([OP_LINK, channel & 0xFF, link_flags & 0x0F]))


def cmd_set_channel_name(channel: int, name: str) -> bytes:
    """Build a set-channel-name command (0x3D).

    Sets the display name for a channel (shown in the app's channel strips).
    Verified from captures:
      Out3 "Out3"→"AUSGANG3": 3d 06 41 55 53 47 41 4e 47 33
      InC  "InC" →"EINGANGC": 3d 02 45 49 4e 47 41 4e 47 43

    channel: unified index (inputs 0-3, outputs 4-7)
    name:    up to 8 ASCII characters — truncated and zero-padded to exactly 8 bytes.
    """
    encoded = name[:8].encode("ascii", errors="replace")
    padded = encoded.ljust(8, b"\x00")
    return build_frame(bytes([OP_SET_CHANNEL_NAME, channel & 0xFF]) + padded)


def cmd_peq_band(channel: int, band: int, gain_raw: int, freq_raw: int,
                 q_raw: int, filter_type: int, bypass: bool = False) -> bytes:
    """Build a PEQ band command (0x33).

    Sets a single parametric EQ band for an output channel.
    Verified from 7 captures on 4x4 Mini (output channels, 7 bands each).

    channel:     output channel index (0x04=Out1, 0x05=Out2, 0x06=Out3, 0x07=Out4)
    band:        0-indexed band number (0–6 for bands 1–7)
    gain_raw:    LE uint16, raw 0–240; gain_dB = (raw - 120) / 10.0; 0dB = 120
    freq_raw:    LE uint16, raw 0–300; Hz = 19.70 * (20160/19.70)^(raw/300)
    q_raw:       uint8, raw 0–100; Q = 0.4 * 320^(raw/100); shelf/pass max = 35
    filter_type: uint8, use PEQ_TYPE_* constants
    bypass:      True = this band bypassed, False = active

    Captured examples:
      Band1 Peak 1kHz 0dB Q=1.0 active: 33 04 00 78 00 78 00 19 00 00
      Band1 Low Shelf bypass:            33 04 00 78 00 00 00 0a 01 01
    """
    gain_raw = max(0, min(240, gain_raw))
    freq_raw = max(0, min(300, freq_raw))
    q_raw = max(0, min(100, q_raw))
    payload = bytes([
        OP_PEQ,
        channel & 0xFF,
        band & 0xFF,
        gain_raw & 0xFF,
        (gain_raw >> 8) & 0xFF,
        freq_raw & 0xFF,
        (freq_raw >> 8) & 0xFF,
        q_raw & 0xFF,
        filter_type & 0xFF,
        0x01 if bypass else 0x00,
    ])
    return build_frame(payload)


def cmd_peq_channel_bypass(channel: int, bypass: bool) -> bytes:
    """Build a PEQ channel bypass command (0x3C).

    Bypasses or restores ALL PEQ bands for an output channel at once.
    Verified from capture: capture_20260409_091811_output_peq_channel_1_bypass.pcapng

    channel: output channel index (0x04=Out1 .. 0x07=Out4)
    bypass:  True = all bands bypassed, False = all bands active

    Captured: 3c 04 01 (Out1 all bypassed), 3c 04 00 (Out1 active)
    """
    return build_frame(bytes([OP_PEQ_BYPASS, channel & 0xFF, 0x01 if bypass else 0x00]))


def cmd_gate(channel: int, attack: int, release: int, hold: int, threshold: int) -> bytes:
    """Build a noise gate command (0x3E).

    channel: 0-indexed input channel (0–3)
    attack: raw 34–998 (maps to 1–999 ms)
    release: raw 0–2999 (maps to 0–3000 ms)
    hold: raw 9–998 (maps to 10–999 ms)
    threshold: raw 1–180 (maps to −90.0 to 0.0 dB, 0.5 dB/step)
    """
    return build_frame(bytes([
        OP_GATE, channel,
        attack & 0xFF, (attack >> 8) & 0xFF,
        release & 0xFF, (release >> 8) & 0xFF,
        hold & 0xFF, (hold >> 8) & 0xFF,
        threshold & 0xFF, (threshold >> 8) & 0xFF,
    ]))


def cmd_compressor(
    channel: int,
    ratio: int,
    knee: int,
    attack: int,
    release: int,
    threshold: int,
) -> bytes:
    """Build a compressor/limiter command (0x30).

    All 5 compressor parameters are sent in one frame.

    channel:   output channel (0x04–0x07)
    ratio:     0–15 enum (see COMP_RATIO_* constants; 0=1:1.0, 15=Limit)
    knee:      0–12 (direct dB, 0=hard knee, 12=softest)
    attack:    raw 0–998 (ms = raw + 1, range 1–999 ms)
    release:   raw 9–2999 (ms = raw + 1, range 10–3000 ms)
    threshold: raw 0–220 (dB = raw/2 − 90, range −90.0 to +20.0 dB, 0.5 dB/step)
    """
    return build_frame(bytes([
        OP_COMPRESSOR, channel,
        ratio & 0xFF,
        knee & 0xFF,
        attack & 0xFF, (attack >> 8) & 0xFF,
        release & 0xFF, (release >> 8) & 0xFF,
        threshold & 0xFF, (threshold >> 8) & 0xFF,
    ]))


def cmd_init() -> bytes:
    """Build init handshake command (0x10)."""
    return build_frame(bytes([OP_INIT]))


def cmd_firmware() -> bytes:
    """Build firmware/model string query (0x13)."""
    return build_frame(bytes([OP_FIRMWARE]))


def cmd_device_info() -> bytes:
    """Build device info query (0x2C)."""
    return build_frame(bytes([OP_DEVICE_INFO]))


def parse_device_info(payload: bytes) -> dict | None:
    """Parse a 0x2C device-info response from the device.

    Returns dict with keys:
      'locked': bool — True if device lock is active (requires PIN via 0x2D)

    Lock flag discovered by comparing 0x2c responses across 3 captures:
      Unlocked: 2c 00 27 0f 00 00 00 00
      Locked:   2c 00 27 0f 00 00 01 00
    Byte 6 of the response payload is 0x01 when locked, 0x00 when unlocked.
    """
    if len(payload) < 7 or payload[0] != OP_DEVICE_INFO:
        return None
    return {"locked": payload[6] == 0x01}


# Lock PIN response codes (byte 2 of 0x2D response payload)
LOCK_PIN_CORRECT = 0x01
LOCK_PIN_WRONG = 0x00


def cmd_submit_pin(pin: str) -> bytes:
    """Build a PIN authentication command (0x2D).

    Sent when the device is locked. PIN is 4 ASCII digit characters.
    The device responds with a 0x2D payload: [2d, 00, 01=correct / 00=wrong].

    Captured:
      2d 00 37 36 35 34 (PIN "7654" — correct) → response 2d 00 01
      2d 00 38 38 38 38 (PIN "8888" — wrong)   → response 2d 00 00

    pin: exactly 4 ASCII digit characters (e.g. "7654")
    """
    encoded = pin[:4].encode("ascii", errors="replace").ljust(4, b"0")
    return build_frame(bytes([OP_SUBMIT_PIN, 0x00]) + encoded)


def cmd_set_lock_pin(pin: str) -> bytes:
    """Build a device lock PIN command (0x2F).

    ⚠ WARNING: Sending this command IMMEDIATELY locks the device and
    disconnects the application. The device cannot be controlled again
    until the correct PIN is submitted via cmd_submit_pin() on the next
    connection. If the PIN is lost, factory reset procedure is unknown.

    pin: exactly 4 ASCII digit characters (e.g. "7654")

    Captured: 2f 37 36 35 34 (set PIN "7654") → device locks + disconnects
    """
    encoded = pin[:4].encode("ascii", errors="replace").ljust(4, b"0")
    return build_frame(bytes([OP_SET_LOCK_PIN]) + encoded)


def parse_pin_response(payload: bytes) -> bool | None:
    """Parse a 0x2D PIN response from the device.

    Returns True if PIN was correct, False if wrong, None if payload invalid.
    """
    if len(payload) < 3 or payload[0] != OP_SUBMIT_PIN:
        return None
    return payload[2] == LOCK_PIN_CORRECT


def cmd_preset_header() -> bytes:
    """Build active preset header query (0x22)."""
    return build_frame(bytes([OP_PRESET_HEADER]))


def cmd_preset_index() -> bytes:
    """Build active preset index query (0x14)."""
    return build_frame(bytes([OP_PRESET_INDEX]))


def cmd_read_name(slot: int) -> bytes:
    """Build preset name read command (0x29).

    slot: 0-indexed request index, 0–29.
    Index 0 = U01, index 1 = U02, …, index 29 = U30.
    F00 (slot 0 in 0x14 terms) is NOT accessible via this command.
    """
    return build_frame(bytes([OP_READ_NAME, slot]))


def cmd_load_preset(slot: int) -> bytes:
    """Build a load-preset command (0x20).

    slot: direct index — 0=F00, 1=U01, …, 30=U30.
    After the device ACKs, read all 9 config pages (0x27) then send cmd_activate().
    """
    return build_frame(bytes([OP_LOAD_PRESET, slot & 0xFF]))


def cmd_store_preset_name(name: str) -> bytes:
    """Build a store-preset-name command (0x26).

    name: up to 14 ASCII characters — truncated and space-padded to exactly 14.
    Must be sent BEFORE cmd_store_preset().

    WARNING: the device crashes if more than 14 characters are sent.
    """
    encoded = name[:14].encode("ascii", errors="replace")
    padded = encoded.ljust(14, b" ")
    return build_frame(bytes([OP_STORE_NAME]) + padded)


def cmd_store_preset(slot: int) -> bytes:
    """Build a store-preset command (0x21).

    slot: 1=U01, …, 30=U30.
    Send cmd_store_preset_name() first, then this command, then cmd_activate().
    The device takes ~2 seconds to ACK while writing to flash — wait for it.

    WARNING: never pass slot=0 (F00 factory preset). Overwriting F00 may
    permanently corrupt the device's factory default and could require a
    firmware reflash to recover.
    """
    if slot == 0:
        raise ValueError("slot 0 (F00) is the factory preset and must not be overwritten")
    return build_frame(bytes([OP_STORE_PRESET, slot & 0xFF]))


def cmd_read_config(page: int) -> bytes:
    """Build a config page read command (0x27).

    page: 0–8 (9 pages of 51 bytes each).
    Device responds with opcode 0x24.
    """
    return build_frame(bytes([OP_READ_CONFIG, page]))


def cmd_activate() -> bytes:
    """Build config activate command (0x12)."""
    return build_frame(bytes([OP_ACTIVATE]))


# --- Response parsers ---

def _ch_level(payload: bytes, group_start: int) -> int:
    """Extract a channel level from a 3-byte triplet [val_lo, val_hi, instant].

    First two bytes are a uint16 LE filtered/peak level (0–~264).
    Third byte is an instantaneous noisy sample (0–255).

    The instant byte and uint16 are on incompatible scales (instant 247
    = barely visible, uint16 136 = end of green zone), so only the uint16
    value is used for metering. The device transitions to uint16 mode
    right at the manufacturer's display threshold.
    """
    return payload[group_start] + payload[group_start + 1] * 256


def parse_levels(payload: bytes) -> dict | None:
    """Parse a 28-byte level monitoring response (opcode 0x40).

    Payload: opcode + 8 × 3-byte channel triplets + 3-byte tail.
    Each triplet: [val_lo, val_hi, instant] — uint16 LE + instant sample.
    Input channels at offsets 1,4,7,10; output channels at 13,16,19,22.
    """
    if len(payload) != 28 or payload[0] != OP_POLL:
        return None
    return {
        "inputs": [_ch_level(payload, 1), _ch_level(payload, 4),
                   _ch_level(payload, 7), _ch_level(payload, 10)],
        "outputs": [_ch_level(payload, 13), _ch_level(payload, 16),
                    _ch_level(payload, 19), _ch_level(payload, 22)],
        "limiter_mask": payload[25],
        "state": payload[26],
    }


def is_ack(payload: bytes) -> bool:
    """Check if payload is an ACK response (single byte 0x01)."""
    return len(payload) == 1 and payload[0] == 0x01


# --- Config parsing ---

CONFIG_PAGES = 9
CONFIG_PAGE_SIZE = 50
OP_CONFIG_RESP = 0x24

# Offsets within the 450-byte stitched config blob (preset structure)
_PRESET_INPUT_START = 16    # 4 × 24-byte input blocks
_INPUT_BLOCK_SIZE = 24
_CHANNEL_NAME_OFFSET = 0    # 8-byte ASCII name, zero-padded (shared by input and output blocks)
_CHANNEL_NAME_SIZE = 8
_INPUT_GAIN_OFFSET = 18     # uint16 LE within input block
_INPUT_GATE_ATTACK_OFFSET = 10  # uint16 LE, raw 34–998 (1–999 ms)
_INPUT_GATE_RELEASE_OFFSET = 12 # uint16 LE, raw 0–2999 (0–3000 ms)
_INPUT_GATE_HOLD_OFFSET = 14    # uint16 LE, raw 9–998 (10–999 ms)
_INPUT_GATE_THRESH_OFFSET = 16  # uint16 LE, raw 1–180 (−90.0 to 0.0 dB, 0.5 dB/step)
_INPUT_PHASE_OFFSET = 20    # 0x00=normal, 0x01=inverted
_INPUT_LINK_FLAGS_OFFSET = 22  # bitmask: bit0=InA, bit1=InB, bit2=InC, bit3=InD; master=OR, slave=0x00

_PRESET_OUTPUT_START = 112  # 4 × 74-byte output blocks
_OUTPUT_BLOCK_SIZE = 74
_OUTPUT_HIPASS_OFFSET = 10  # uint16 LE, crossover hi-pass freq (raw 0–300 on 4x4 Mini)
_OUTPUT_LOPASS_OFFSET = 12  # uint16 LE, crossover lo-pass freq (raw 0–300 on 4x4 Mini)
_OUTPUT_HIPASS_SLOPE_OFFSET = 14  # uint8, 0x00=bypassed, 0x01–0x0a=slope (SLOPE_* constants)
_OUTPUT_LOPASS_SLOPE_OFFSET = 15  # uint8, 0x00=bypassed, 0x01–0x0a=slope (SLOPE_* constants)
_OUTPUT_PEQ_OFFSET = 16   # 7 bands × 6 bytes = 42 bytes (verified from PEQ captures)
_OUTPUT_PEQ_BAND_SIZE = 6
_OUTPUT_COMP_RATIO_OFFSET = 58   # uint8 enum 0–15 (see COMP_RATIO_* constants)
_OUTPUT_COMP_KNEE_OFFSET = 59    # uint8, 0–12 (direct dB, 0=hard knee)
_OUTPUT_COMP_ATTACK_OFFSET = 60  # uint16 LE, raw 0–998 (ms = raw + 1, range 1–999 ms)
_OUTPUT_COMP_RELEASE_OFFSET = 62 # uint16 LE, raw 9–2999 (ms = raw + 1, range 10–3000 ms)
_OUTPUT_COMP_THRESH_OFFSET = 64  # uint16 LE, raw 0–220 (dB = raw/2 − 90, range −90 to +20 dB)
_OUTPUT_GAIN_OFFSET = 66    # uint16 LE within output block
_OUTPUT_PHASE_OFFSET = 68   # 0x00=normal, 0x01=inverted
_OUTPUT_DELAY_OFFSET = 70   # uint16 LE, raw 0–32640 (samples at 48 kHz, 0–680 ms)
_OUTPUT_LINK_FLAGS_OFFSET = 72  # bitmask: bit0=Out1, bit1=Out2, bit2=Out3, bit3=Out4; master=OR, slave=0x00

# Mute bitmasks in the config footer (after channel blocks)
_INPUT_MUTE_BITMASK_OFFSET = 408   # uint16 LE, bit 0=In1 .. bit 3=In4
_OUTPUT_MUTE_BITMASK_OFFSET = 410  # uint16 LE, bit 0=Out1 .. bit 3=Out4
# PEQ bypass flags in config footer
_PEQ_BAND_BYPASS_OFFSET = 412  # 4 bytes (one per output channel); bit 0=band1..bit6=band7; 1=bypassed
_PEQ_CHANNEL_BYPASS_OFFSET = 428  # 4 bytes (one per output channel); 0x00=active, 0x01=all bands bypassed


def parse_preset_index(payload: bytes) -> int | None:
    """Parse a 0x14 active-preset-index response.

    Returns the slot index (0=F00, 1=U01, …, 30=U30) or None if invalid.
    """
    if len(payload) < 2 or payload[0] != OP_PRESET_INDEX:
        return None
    return payload[1]


def parse_preset_name(payload: bytes) -> tuple[int, str] | None:
    """Parse a 0x29 preset-name response → (request_index, name).

    Response format: 29 [request_index] [14 bytes ASCII name, space-padded].
    request_index 0 = U01, 1 = U02, …, 29 = U30 (NOT 0x14 slot numbers).
    To convert to 0x14 slot: slot = request_index + 1.
    """
    if len(payload) < 16 or payload[0] != OP_READ_NAME:
        return None
    slot = payload[1]
    name = payload[2:16].decode("ascii", errors="replace").rstrip()
    return slot, name


def parse_config_page(payload: bytes) -> tuple[int, bytes] | None:
    """Parse a config page response (opcode 0x24).

    Returns (page_index, 50_bytes_data) or None.
    """
    if len(payload) < 2 or payload[0] != OP_CONFIG_RESP:
        log.debug("parse_config_page: bad header (opcode=%02x, len=%d, need 0x%02x)",
                  payload[0] if payload else 0, len(payload), OP_CONFIG_RESP)
        return None
    page = payload[1]
    data = payload[2:2 + CONFIG_PAGE_SIZE]
    if len(data) != CONFIG_PAGE_SIZE:
        log.debug("parse_config_page: short data (page=%d, got %d bytes, need %d)",
                  page, len(data), CONFIG_PAGE_SIZE)
        return None
    return page, data


def parse_preset_params(config_data: bytes) -> dict | None:
    """Extract gain, mute, phase, gate, and delay from stitched config data.

    config_data: 450 bytes (9 pages × 50 bytes) from read_config().
    Returns dict with:
      'names' (list[8], str — ASCII channel names, null-stripped),
      'gains' (list[8], raw 0–400), 'mutes' (list[8], bool),
      'phases' (list[8], bool — True=inverted),
      'link_flags' (list[8], uint8 — per-channel link bitmask from config; standalone=own bit, master=OR of all linked bits, slave=0x00),
      'gates' (list[4], dict with attack/release/hold/threshold raw values),
      'delays' (list[4], int — raw samples 0–32640, ms = raw / 48),
      'crossovers' (list[4], dict with hipass/lopass freq and slope per filter),
      'compressors' (list[4], dict with ratio/knee/attack/release/threshold raw values),
      'peqs' (list[4], dict with 'bands' list[7] and 'channel_bypass' bool).
        Each band dict: gain (raw 0–240), freq (raw 0–300), q (raw 0–100),
        type (0–6, use PEQ_TYPE_* constants), bypass (bool — True=this band bypassed).
    Channel order: inputs 0–3, outputs 4–7 (gates input-only; delays/crossovers/compressors/peqs output-only).
    """
    if len(config_data) < _OUTPUT_MUTE_BITMASK_OFFSET + 2:
        log.debug("parse_preset_params: too short (%d bytes, need %d)",
                  len(config_data), _OUTPUT_MUTE_BITMASK_OFFSET + 2)
        return None

    names: list[str] = []
    gains: list[int] = []
    mutes: list[bool] = []
    phases: list[bool] = []
    gates: list[dict[str, int]] = []
    delays: list[int] = []
    crossovers: list[dict[str, int]] = []
    compressors: list[dict[str, int]] = []
    peqs: list[dict] = []
    link_flags: list[int] = []

    # Input channels: name, gain, phase, gate from per-channel blocks
    for i in range(4):
        base = _PRESET_INPUT_START + i * _INPUT_BLOCK_SIZE
        raw_name = config_data[base + _CHANNEL_NAME_OFFSET : base + _CHANNEL_NAME_OFFSET + _CHANNEL_NAME_SIZE]
        names.append(raw_name.rstrip(b"\x00").decode("ascii", errors="replace"))
        gain = config_data[base + _INPUT_GAIN_OFFSET] + config_data[base + _INPUT_GAIN_OFFSET + 1] * 256
        gains.append(gain)
        phases.append(bool(config_data[base + _INPUT_PHASE_OFFSET]))
        link_flags.append(config_data[base + _INPUT_LINK_FLAGS_OFFSET])
        gates.append({
            "attack": config_data[base + _INPUT_GATE_ATTACK_OFFSET] + config_data[base + _INPUT_GATE_ATTACK_OFFSET + 1] * 256,
            "release": config_data[base + _INPUT_GATE_RELEASE_OFFSET] + config_data[base + _INPUT_GATE_RELEASE_OFFSET + 1] * 256,
            "hold": config_data[base + _INPUT_GATE_HOLD_OFFSET] + config_data[base + _INPUT_GATE_HOLD_OFFSET + 1] * 256,
            "threshold": config_data[base + _INPUT_GATE_THRESH_OFFSET] + config_data[base + _INPUT_GATE_THRESH_OFFSET + 1] * 256,
        })

    # Output channels: name, gain, phase, delay, crossover, compressor from per-channel blocks
    for i in range(4):
        base = _PRESET_OUTPUT_START + i * _OUTPUT_BLOCK_SIZE
        raw_name = config_data[base + _CHANNEL_NAME_OFFSET : base + _CHANNEL_NAME_OFFSET + _CHANNEL_NAME_SIZE]
        names.append(raw_name.rstrip(b"\x00").decode("ascii", errors="replace"))
        gain = config_data[base + _OUTPUT_GAIN_OFFSET] + config_data[base + _OUTPUT_GAIN_OFFSET + 1] * 256
        gains.append(gain)
        phases.append(bool(config_data[base + _OUTPUT_PHASE_OFFSET]))
        link_flags.append(config_data[base + _OUTPUT_LINK_FLAGS_OFFSET])
        delays.append(config_data[base + _OUTPUT_DELAY_OFFSET] + config_data[base + _OUTPUT_DELAY_OFFSET + 1] * 256)
        crossovers.append({
            "hipass_freq": config_data[base + _OUTPUT_HIPASS_OFFSET] + config_data[base + _OUTPUT_HIPASS_OFFSET + 1] * 256,
            "lopass_freq": config_data[base + _OUTPUT_LOPASS_OFFSET] + config_data[base + _OUTPUT_LOPASS_OFFSET + 1] * 256,
            "hipass_slope": config_data[base + _OUTPUT_HIPASS_SLOPE_OFFSET],
            "lopass_slope": config_data[base + _OUTPUT_LOPASS_SLOPE_OFFSET],
        })
        compressors.append({
            "ratio": config_data[base + _OUTPUT_COMP_RATIO_OFFSET],
            "knee": config_data[base + _OUTPUT_COMP_KNEE_OFFSET],
            "attack": config_data[base + _OUTPUT_COMP_ATTACK_OFFSET] + config_data[base + _OUTPUT_COMP_ATTACK_OFFSET + 1] * 256,
            "release": config_data[base + _OUTPUT_COMP_RELEASE_OFFSET] + config_data[base + _OUTPUT_COMP_RELEASE_OFFSET + 1] * 256,
            "threshold": config_data[base + _OUTPUT_COMP_THRESH_OFFSET] + config_data[base + _OUTPUT_COMP_THRESH_OFFSET + 1] * 256,
        })
        # PEQ: 7 bands × 6 bytes starting at output block offset 16
        # Band bypass bitmask for this channel is in footer at _PEQ_BAND_BYPASS_OFFSET + i
        band_bypass_byte = config_data[_PEQ_BAND_BYPASS_OFFSET + i] if len(config_data) > _PEQ_BAND_BYPASS_OFFSET + i else 0
        channel_bypassed = bool(config_data[_PEQ_CHANNEL_BYPASS_OFFSET + i]) if len(config_data) > _PEQ_CHANNEL_BYPASS_OFFSET + i else False
        bands = []
        for b in range(7):
            boff = base + _OUTPUT_PEQ_OFFSET + b * _OUTPUT_PEQ_BAND_SIZE
            gain_raw = config_data[boff] + config_data[boff + 1] * 256
            freq_raw = config_data[boff + 2] + config_data[boff + 3] * 256
            q_raw = config_data[boff + 4]
            ftype = config_data[boff + 5]
            band_bypassed = bool(band_bypass_byte & (1 << b))
            bands.append({"gain": gain_raw, "freq": freq_raw, "q": q_raw,
                           "type": ftype, "bypass": band_bypassed})
        peqs.append({"bands": bands, "channel_bypass": channel_bypassed})

    # Mute: bitmasks in config footer
    input_mute_mask = config_data[_INPUT_MUTE_BITMASK_OFFSET] + config_data[_INPUT_MUTE_BITMASK_OFFSET + 1] * 256
    output_mute_mask = config_data[_OUTPUT_MUTE_BITMASK_OFFSET] + config_data[_OUTPUT_MUTE_BITMASK_OFFSET + 1] * 256

    for i in range(4):
        mutes.append(bool(input_mute_mask & (1 << i)))
    for i in range(4):
        mutes.append(bool(output_mute_mask & (1 << i)))

    return {"names": names, "gains": gains, "mutes": mutes, "phases": phases,
            "link_flags": link_flags, "gates": gates, "delays": delays,
            "crossovers": crossovers, "compressors": compressors, "peqs": peqs}


# --- Gain conversion ---

def raw_to_db(raw: int) -> float:
    """Convert raw gain value (0–400) to dB.

    Dual resolution: coarse 0.5 dB/step below −20 dB, fine 0.1 dB/step above.
    Confirmed via dsp-408-ui project (same Musicrown protocol).
    """
    if raw < 80:
        return raw / 2.0 - 60.0
    return (raw - 80) / 10.0 - 20.0


def db_to_raw(db: float) -> int:
    """Convert dB to raw gain value (0–400).

    Dual resolution: coarse 0.5 dB/step below −20 dB, fine 0.1 dB/step above.
    """
    if db < -20.0:
        return max(0, round((db + 60.0) * 2))
    return min(400, round(80 + (db + 20.0) * 10))


def peq_gain_to_raw(gain_db: float) -> int:
    """Convert PEQ gain in dB to raw protocol value.

    Range: −12.0 to +12.0 dB → raw 0–240. 0 dB = raw 120. 0.1 dB resolution.
    """
    return max(0, min(240, round(gain_db * 10) + 120))


def peq_raw_to_gain(raw: int) -> float:
    """Convert raw PEQ gain value to dB."""
    return (raw - 120) / 10.0


def peq_q_to_raw(q: float) -> int:
    """Convert PEQ Q value to raw protocol value.

    Q = 0.4 * 320^(raw/100). Range: Q 0.4–128 → raw 0–100.
    Shelf/pass filters are restricted to Q 0.4–3.0 (raw 0–35) by the app UI.
    """
    import math
    if q <= 0.4:
        return 0
    raw = round(100 * math.log(q / 0.4) / math.log(320))
    return max(0, min(100, raw))


def peq_raw_to_q(raw: int) -> float:
    """Convert raw PEQ Q value to Q."""
    return 0.4 * (320 ** (raw / 100))


def freq_raw_to_hz(raw: int) -> float:
    """Log-scale frequency: raw 0–300 → 19.7–20160 Hz."""
    return 19.70 * (20160.0 / 19.70) ** (raw / 300.0)


def comp_threshold_to_db(raw: int) -> float:
    """raw 0–220 → dB; formula: raw/2 − 90. Range −90 to +20 dB."""
    return raw / 2.0 - 90.0


def comp_attack_to_ms(raw: int) -> int:
    """raw 0–998 → ms; formula: raw + 1. Range 1–999 ms."""
    return raw + 1


def comp_release_to_ms(raw: int) -> int:
    """raw 9–2999 → ms; formula: raw + 1. Range 10–3000 ms."""
    return raw + 1


def gate_threshold_to_db(raw: int) -> float:
    """raw 1–180 → dB; formula: raw × 0.5 − 90.0. Range −90 to 0 dB."""
    return raw * 0.5 - 90.0


def gate_time_to_ms(raw: int) -> int:
    """Convert gate attack/hold/release raw value to ms. Formula: raw + 1.

    Same encoding as compressor timings. Confirmed by hold range:
    raw 9 → 10 ms (minimum), raw 998 → 999 ms (maximum).
    """
    return raw + 1


def delay_samples_to_ms(raw: int) -> float:
    """raw 0–32640 samples → ms at 48 kHz."""
    return raw / 48.0


# Human-readable name lookup tables for display

SLOPE_NAMES: dict[int, str] = {
    0x00: "Off",
    0x01: "BW 6",   0x02: "BL 6",
    0x03: "BW 12",  0x04: "BL 12",  0x05: "LR 12",
    0x06: "BW 18",  0x07: "BL 18",
    0x08: "BW 24",  0x09: "BL 24",  0x0A: "LR 24",
}

PEQ_TYPE_NAMES: dict[int, str] = {
    PEQ_TYPE_PEAK:       "Peak",
    PEQ_TYPE_LOW_SHELF:  "Low Shelf",
    PEQ_TYPE_HIGH_SHELF: "High Shelf",
    PEQ_TYPE_LOW_PASS:   "Low Pass",
    PEQ_TYPE_HIGH_PASS:  "High Pass",
    PEQ_TYPE_ALLPASS1:   "Allpass 1",
    PEQ_TYPE_ALLPASS2:   "Allpass 2",
}

COMP_RATIO_NAMES: dict[int, str] = {
    0x00: "1:1.0",  0x01: "1:1.1",  0x02: "1:1.3",  0x03: "1:1.5",
    0x04: "1:1.7",  0x05: "1:2.0",  0x06: "1:2.5",  0x07: "1:3.0",
    0x08: "1:3.5",  0x09: "1:4.0",  0x0A: "1:5.0",  0x0B: "1:6.0",
    0x0C: "1:8.0",  0x0D: "1:10.0", 0x0E: "1:20.0", 0x0F: "Limit",
}
