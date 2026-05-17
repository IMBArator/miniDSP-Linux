"""
the t.racks DSP 4x4 Mini — USB HID protocol encoding/decoding.

Frame format (inside 64-byte HID report):

```text
10 02 [SRC] [DST] [LEN] [PAYLOAD...] 10 03 [CHK]
```

Checksum = XOR of LEN and all payload bytes.
"""

from __future__ import annotations

import logging
import math

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
    """Compute the protocol frame checksum.

    Args:
        length: The frame length byte value.
        payload: The frame payload bytes.

    Returns:
        XOR of ``length`` and all bytes in ``payload``, masked to 8 bits.
    """
    chk = length
    for b in payload:
        chk ^= b
    return chk & 0xFF


def build_frame(payload: bytes) -> bytes:
    """Build a 64-byte HID OUT report from a payload.

    Frame layout: ``10 02 00 01 [LEN] [PAYLOAD] 10 03 [CHK] [zero-pad to 64]``

    Args:
        payload: Raw command payload bytes (opcode + parameters).

    Returns:
        Zero-padded 64-byte HID report ready to write to the device.
    """
    length = len(payload)
    chk = checksum(length, payload)
    frame = bytes([0x10, 0x02, 0x00, 0x01, length]) + payload + bytes([0x10, 0x03, chk])
    # Pad to 64 bytes
    frame += b"\x00" * (REPORT_SIZE - len(frame))
    return frame


def parse_frame(data: bytes) -> tuple[int, int, int, bytes] | None:
    """Parse a 64-byte HID IN report.

    Args:
        data: Raw 64-byte HID report received from the device.

    Returns:
        ``(src, dst, length, payload)`` on success, or ``None`` if framing
        is invalid (bad STX/ETX, truncated, or checksum mismatch).
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

    Args:
        channel: Unified channel index for outputs (0x04–0x07).
        freq_raw: Frequency raw value 0–300 (log scale;
            Hz = 19.70 × (20160/19.70)^(raw/300), range 19.7 Hz–20.16 kHz).
        slope: Filter slope. ``SLOPE_BYPASS`` (0x00) disables the filter;
            ``SLOPE_BW6``–``SLOPE_LR24`` select active slopes (see ``SLOPE_*`` constants).

    Returns:
        Encoded 64-byte HID report.
    """
    freq_raw = max(0, min(300, freq_raw))
    lo = freq_raw & 0xFF
    hi = (freq_raw >> 8) & 0xFF
    return build_frame(bytes([OP_LOPASS, channel, lo, hi, slope]))


def cmd_hipass(channel: int, freq_raw: int, slope: int = SLOPE_BYPASS) -> bytes:
    """Build a high-pass crossover command (0x32).

    Args:
        channel: Unified channel index for outputs (0x04–0x07).
        freq_raw: Frequency raw value 0–300 (log scale;
            Hz = 19.70 × (20160/19.70)^(raw/300), range 19.7 Hz–20.16 kHz).
        slope: Filter slope. ``SLOPE_BYPASS`` (0x00) disables the filter;
            ``SLOPE_BW6``–``SLOPE_LR24`` select active slopes (see ``SLOPE_*`` constants).

    Returns:
        Encoded 64-byte HID report.
    """
    freq_raw = max(0, min(300, freq_raw))
    lo = freq_raw & 0xFF
    hi = (freq_raw >> 8) & 0xFF
    return build_frame(bytes([OP_HIPASS, channel, lo, hi, slope]))


def cmd_mute(channel: int, mute: bool) -> bytes:
    """Build a mute command (0x35).

    Args:
        channel: Unified channel index (inputs 0–3, outputs 4–7).
        mute: ``True`` to mute, ``False`` to unmute.

    Returns:
        Encoded 64-byte HID report.
    """
    return build_frame(bytes([OP_MUTE, channel, 0x01 if mute else 0x00]))


def cmd_gain(channel: int, raw_value: int) -> bytes:
    """Build a gain command (0x34).

    Args:
        channel: Unified channel index (inputs 0–3, outputs 4–7).
        raw_value: Raw gain value 0–400. Use :func:`db_to_raw` to convert
            from dB; dual resolution (0.5 dB/step below −20 dB,
            0.1 dB/step above).

    Returns:
        Encoded 64-byte HID report.
    """
    raw_value = max(0, min(400, raw_value))
    lo = raw_value & 0xFF
    hi = (raw_value >> 8) & 0xFF
    return build_frame(bytes([OP_GAIN, channel, lo, hi]))


def cmd_phase(channel: int, inverted: bool) -> bytes:
    """Build a phase invert command (0x36).

    Args:
        channel: Unified channel index (inputs 0–3, outputs 4–7).
        inverted: ``True`` for 180° inversion, ``False`` for normal polarity.

    Returns:
        Encoded 64-byte HID report.
    """
    return build_frame(bytes([OP_PHASE, channel, 0x01 if inverted else 0x00]))


def cmd_delay(channel: int, samples: int) -> bytes:
    """Build an output delay command (0x38).

    Args:
        channel: Unified channel index for outputs (0x04–0x07).
        samples: Delay in samples at 48 kHz, range 0–32640
            (ms = samples / 48, max ≈ 680 ms).

    Returns:
        Encoded 64-byte HID report.
    """
    samples = max(0, min(32640, samples))
    lo = samples & 0xFF
    hi = (samples >> 8) & 0xFF
    return build_frame(bytes([OP_DELAY, channel, lo, hi]))


def cmd_set_delay_unit(unit: int) -> bytes:
    """Build a delay display unit command (0x15).

    Controls the unit shown in the UI only; the protocol always transmits
    delay in samples via 0x38. Persisted at config offset 424.

    Args:
        unit: Display unit — ``DELAY_UNIT_MS`` (0x00), ``DELAY_UNIT_M`` (0x01),
            or ``DELAY_UNIT_FT`` (0x02).

    Returns:
        Encoded 64-byte HID report.
    """
    return build_frame(bytes([OP_SET_DELAY_UNIT, unit & 0xFF]))


def cmd_test_tone(mode: int, freq_index: int = 0) -> bytes:
    """Build a test tone generator command (0x39).

    Enables or disables the internal signal generator. Device ACKs with 0x01.
    State is persisted at config offset 420 (mode) and 422 (last sine freq index).

    Args:
        mode: Generator mode — ``TONE_OFF`` (0x00), ``TONE_PINK`` (0x01),
            ``TONE_WHITE`` (0x02), or ``TONE_SINE`` (0x03).
        freq_index: Sine frequency index (``SINE_FREQ_*`` constant, 0x00=20 Hz …
            0x1E=20 kHz). Ignored for noise modes. When disabling after a sine
            session, pass the last used index so the device retains it in config.

    Returns:
        Encoded 64-byte HID report.

    Example::

        # White noise
        cmd_test_tone(TONE_WHITE)
        # Sine at 1 kHz
        cmd_test_tone(TONE_SINE, SINE_FREQ_1KHZ)
        # Off (retain last sine freq index)
        cmd_test_tone(TONE_OFF, SINE_FREQ_1KHZ)
    """
    freq_index = max(0, min(0x1E, freq_index))
    return build_frame(bytes([OP_TEST_TONE, mode & 0xFF, freq_index & 0xFF]))


def cmd_matrix_route(output_ch: int, input_mask: int) -> bytes:
    """Build a matrix routing command (0x3A).

    Sets which input(s) feed a given output. The full bitmask is sent each time.

    Args:
        output_ch: Output channel index (0x04=Out1, 0x05=Out2, 0x06=Out3, 0x07=Out4).
        input_mask: Source bitmask (InA=0x01, InB=0x02, InC=0x04, InD=0x08;
            0x00=silence; multiple bits allowed for summing).

    Returns:
        Encoded 64-byte HID report.
    """
    return build_frame(bytes([OP_MATRIX, output_ch, input_mask & 0x0F]))


def cmd_prepare_link(master_ch: int, slave_ch: int) -> bytes:
    """Build a prepare-link command (0x2A).

    Must be sent once per master↔slave pair immediately before
    :func:`cmd_channel_link` when linking channels. Not sent when unlinking.

    For N-channel links send one ``cmd_prepare_link`` per slave, then all
    :func:`cmd_channel_link` calls. Example — link InA+InB+InC::

        cmd_prepare_link(0, 1)     # InA→InB
        cmd_prepare_link(0, 2)     # InA→InC
        cmd_channel_link(0, 0x07)  # InA master: bits 0|1|2
        cmd_channel_link(1, 0x00)  # InB slave
        cmd_channel_link(2, 0x00)  # InC slave
        cmd_activate()

    Args:
        master_ch: Unified channel index of the master (inputs 0–3, outputs 4–7).
        slave_ch: Unified channel index of the slave.

    Returns:
        Encoded 64-byte HID report.
    """
    return build_frame(bytes([OP_PREPARE_LINK, master_ch & 0xFF, slave_ch & 0xFF]))


def cmd_channel_link(channel: int, link_flags: int) -> bytes:
    """Build a channel link state command (0x3B).

    Sets the link bitmask for one channel. Send for every affected channel
    (both master and all slaves). Preceded by :func:`cmd_prepare_link` per
    slave pair when linking; no prepare needed when unlinking.

    Args:
        channel: Unified channel index (inputs 0–3, outputs 4–7).
        link_flags: Bitmask within the 4-channel group.

            - Inputs:  InA=0x01, InB=0x02, InC=0x04, InD=0x08
            - Outputs: Out1=0x01, Out2=0x02, Out3=0x04, Out4=0x08

            Master gets OR of all linked bits; slaves get 0x00.
            Standalone (unlinked) channel gets its own bit only (e.g. InA=0x01).

    Returns:
        Encoded 64-byte HID report.
    """
    return build_frame(bytes([OP_LINK, channel & 0xFF, link_flags & 0x0F]))


def cmd_set_channel_name(channel: int, name: str) -> bytes:
    """Build a set-channel-name command (0x3D).

    Sets the display name shown in the app's channel strips. Verified from
    captures: Out3 "Out3"→"AUSGANG3" and InC "InC"→"EINGANGC".

    Args:
        channel: Unified channel index (inputs 0–3, outputs 4–7).
        name: Up to 8 ASCII characters. Truncated and zero-padded to exactly
            8 bytes before transmission.

    Returns:
        Encoded 64-byte HID report.
    """
    encoded = name[:8].encode("ascii", errors="replace")
    padded = encoded.ljust(8, b"\x00")
    return build_frame(bytes([OP_SET_CHANNEL_NAME, channel & 0xFF]) + padded)


def cmd_peq_band(channel: int, band: int, gain_raw: int, freq_raw: int,
                 q_raw: int, filter_type: int, bypass: bool = False) -> bytes:
    """Build a PEQ band command (0x33).

    Sets a single parametric EQ band for an output channel. Verified from
    7 captures on the 4x4 Mini (output channels, 7 bands each).

    Args:
        channel: Output channel index (0x04=Out1, 0x05=Out2, 0x06=Out3, 0x07=Out4).
        band: 0-indexed band number (0–6 for bands 1–7).
        gain_raw: LE uint16, range 0–240; gain_dB = (raw − 120) / 10.0 (0 dB = 120).
        freq_raw: LE uint16, range 0–300;
            Hz = 19.70 × (20160/19.70)^(raw/300).
        q_raw: uint8, range 0–100; Q = 0.4 × 320^(raw/100).
            Shelf/pass filters are UI-restricted to raw 0–35.
        filter_type: Filter shape — use ``PEQ_TYPE_*`` constants.
        bypass: ``True`` to bypass this band, ``False`` for active.

    Returns:
        Encoded 64-byte HID report.
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

    Args:
        channel: Output channel index (0x04=Out1 … 0x07=Out4).
        bypass: ``True`` to bypass all bands, ``False`` to restore all bands.

    Returns:
        Encoded 64-byte HID report.
    """
    return build_frame(bytes([OP_PEQ_BYPASS, channel & 0xFF, 0x01 if bypass else 0x00]))


def cmd_gate(channel: int, attack: int, release: int, hold: int, threshold: int) -> bytes:
    """Build a noise gate command (0x3E).

    Args:
        channel: 0-indexed input channel (0–3).
        attack: Attack time raw value 34–998 (maps to 1–999 ms; raw + 1).
        release: Release time raw value 0–2999 (maps to 0–3000 ms; raw + 1).
        hold: Hold time raw value 9–998 (maps to 10–999 ms; raw + 1).
        threshold: Gate threshold raw value 0–180
            (maps to −90.0–0.0 dB; dB = raw × 0.5 − 90).

    Returns:
        Encoded 64-byte HID report.
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

    Args:
        channel: Output channel index (0x04–0x07).
        ratio: Compression ratio enum 0–15 (see ``COMP_RATIO_*`` constants;
            0=1:1.0 no compression, 15=hard limiter).
        knee: Knee width 0–12 (direct dB; 0=hard knee, 12=softest).
        attack: Attack time raw 0–998 (ms = raw + 1, range 1–999 ms).
        release: Release time raw 9–2999 (ms = raw + 1, range 10–3000 ms).
        threshold: Threshold raw 0–220
            (dB = raw / 2 − 90, range −90.0 to +20.0 dB, 0.5 dB/step).

    Returns:
        Encoded 64-byte HID report.
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
    """Parse a 0x2C device-info response.

    Lock flag discovered by comparing 0x2C responses across 3 captures:
    unlocked byte 6 = 0x00, locked byte 6 = 0x01.

    Args:
        payload: Raw response payload starting with opcode byte.

    Returns:
        Dict with key ``'locked'`` (bool) when valid, or ``None`` if the
        payload is too short or has the wrong opcode.
    """
    if len(payload) < 7 or payload[0] != OP_DEVICE_INFO:
        return None
    return {"locked": payload[6] == 0x01}


# Lock PIN response codes (byte 2 of 0x2D response payload)
LOCK_PIN_CORRECT = 0x01
LOCK_PIN_WRONG = 0x00


def cmd_submit_pin(pin: str) -> bytes:
    """Build a PIN authentication command (0x2D).

    Sent when the device is locked. The device responds with a 0x2D payload:
    ``[2d, 00, 01=correct / 00=wrong]``.

    Args:
        pin: Exactly 4 ASCII digit characters (e.g. ``"7654"``). Truncated to
            4 chars and zero-padded with ``b"0"`` if shorter.

    Returns:
        Encoded 64-byte HID report.
    """
    encoded = pin[:4].encode("ascii", errors="replace").ljust(4, b"0")
    return build_frame(bytes([OP_SUBMIT_PIN, 0x00]) + encoded)


def cmd_set_lock_pin(pin: str) -> bytes:
    """Build a device lock PIN command (0x2F).

    Warning:
        Sending this command **immediately locks the device** and disconnects
        the application. The device cannot be controlled again until the correct
        PIN is submitted via :func:`cmd_submit_pin` on the next connection.
        If the PIN is lost, the factory reset procedure is unknown.

    Args:
        pin: Exactly 4 ASCII digit characters (e.g. ``"7654"``).

    Returns:
        Encoded 64-byte HID report.
    """
    encoded = pin[:4].encode("ascii", errors="replace").ljust(4, b"0")
    return build_frame(bytes([OP_SET_LOCK_PIN]) + encoded)


def parse_pin_response(payload: bytes) -> bool | None:
    """Parse a 0x2D PIN authentication response.

    Args:
        payload: Raw response payload starting with opcode byte.

    Returns:
        ``True`` if the PIN was correct, ``False`` if wrong,
        or ``None`` if the payload is invalid.
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

    Args:
        slot: 0-indexed request index 0–29 (0=U01, 1=U02, …, 29=U30).
            F00 (slot 0 in 0x14 terms) is NOT accessible via this command.

    Returns:
        Encoded 64-byte HID report.
    """
    return build_frame(bytes([OP_READ_NAME, slot]))


def cmd_load_preset(slot: int) -> bytes:
    """Build a load-preset command (0x20).

    After the device ACKs, read all 9 config pages (0x27) then send
    :func:`cmd_activate`.

    Args:
        slot: Direct preset slot index — 0=F00, 1=U01, …, 30=U30.

    Returns:
        Encoded 64-byte HID report.
    """
    return build_frame(bytes([OP_LOAD_PRESET, slot & 0xFF]))


def cmd_store_preset_name(name: str) -> bytes:
    """Build a store-preset-name command (0x26).

    Must be sent BEFORE :func:`cmd_store_preset`.

    Warning:
        The device crashes if more than 14 characters are sent.

    Args:
        name: Up to 14 ASCII characters. Truncated and space-padded to exactly
            14 bytes before transmission.

    Returns:
        Encoded 64-byte HID report.
    """
    encoded = name[:14].encode("ascii", errors="replace")
    padded = encoded.ljust(14, b" ")
    return build_frame(bytes([OP_STORE_NAME]) + padded)


def cmd_store_preset(slot: int) -> bytes:
    """Build a store-preset command (0x21).

    Send :func:`cmd_store_preset_name` first, then this command, then
    :func:`cmd_activate`. The device takes ~2 seconds to ACK while writing
    to flash — wait for the ACK before proceeding.

    Warning:
        Never pass ``slot=0`` (F00 factory preset). Overwriting F00 may
        permanently corrupt the device and could require a firmware reflash
        to recover.

    Args:
        slot: User preset slot index 1–30 (1=U01, …, 30=U30).

    Returns:
        Encoded 64-byte HID report.

    Raises:
        ValueError: If ``slot`` is 0 (factory preset F00).
    """
    if slot == 0:
        raise ValueError("slot 0 (F00) is the factory preset and must not be overwritten")
    return build_frame(bytes([OP_STORE_PRESET, slot & 0xFF]))


def cmd_read_config(page: int) -> bytes:
    """Build a config page read command (0x27).

    Args:
        page: Page index 0–8 (9 pages of 50 bytes each). Device responds
            with opcode 0x24.

    Returns:
        Encoded 64-byte HID report.
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

    Args:
        payload: Raw 28-byte level response payload.
        group_start: Byte offset of the first (low) byte of the triplet.

    Returns:
        uint16 LE amplitude (val_lo + val_hi × 256).
    """
    return payload[group_start] + payload[group_start + 1] * 256


def parse_levels(payload: bytes) -> dict | None:
    """Parse a 28-byte level monitoring response (opcode 0x40).

    Payload layout: opcode + 8 × 3-byte channel triplets + 3-byte tail.
    Each triplet: ``[val_lo, val_hi, instant]`` — uint16 LE + instant sample.
    Input channels at offsets 1, 4, 7, 10; output channels at 13, 16, 19, 22.

    Args:
        payload: Raw 28-byte response payload starting with opcode byte.

    Returns:
        Dict with the following keys, or ``None`` if payload length or opcode
        is invalid:

        - ``'inputs'``: list[int] — 4 input channel uint16 levels (InA–InD).
        - ``'outputs'``: list[int] — 4 output channel uint16 levels (Out1–Out4).
        - ``'limiter_mask'``: int — bitmask at payload[25]; bit N set means
            output channel N (Out1=bit0 … Out4=bit3) has the compressor/limiter
            actively clamping (gain reduction engaged).
        - ``'state'``: int — device state byte at payload[26]; semantics not
            fully decoded.
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
    """Check if payload is an ACK response (single byte 0x01).

    Args:
        payload: Raw response payload.

    Returns:
        ``True`` if the payload is exactly ``b'\\x01'``.
    """
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
_INPUT_GATE_THRESH_OFFSET = 16  # uint16 LE, raw 0–180 (−90.0 to 0.0 dB, 0.5 dB/step)
_INPUT_PHASE_OFFSET = 20    # 0x00=normal, 0x01=inverted
_INPUT_LINK_FLAGS_OFFSET = 22  # bitmask: bit0=InA, bit1=InB, bit2=InC, bit3=InD; master=OR, slave=0x00

_PRESET_OUTPUT_START = 112  # 4 × 74-byte output blocks
_OUTPUT_BLOCK_SIZE = 74
_OUTPUT_ROUTING_OFFSET = 8  # uint8, input routing bitmask (InA=0x01, InB=0x02, InC=0x04, InD=0x08)
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
# Test tone generator state in the config footer (0x39 opcode persists here)
_TEST_TONE_MODE_OFFSET = 420   # uint8: TONE_OFF/TONE_PINK/TONE_WHITE/TONE_SINE
_TEST_TONE_FREQ_OFFSET = 422   # uint8: last selected SINE_FREQ_* index


def parse_preset_index(payload: bytes) -> int | None:
    """Parse a 0x14 active-preset-index response.

    Args:
        payload: Raw response payload starting with opcode byte.

    Returns:
        Slot index (0=F00, 1=U01, …, 30=U30), or ``None`` if invalid.
    """
    if len(payload) < 2 or payload[0] != OP_PRESET_INDEX:
        return None
    return payload[1]


def parse_preset_name(payload: bytes) -> tuple[int, str] | None:
    """Parse a 0x29 preset-name response.

    Response format: ``29 [request_index] [14 bytes ASCII name, space-padded]``.
    ``request_index`` 0=U01, 1=U02, …, 29=U30 (not 0x14 slot numbers;
    to convert: slot = request_index + 1).

    Args:
        payload: Raw response payload starting with opcode byte.

    Returns:
        ``(request_index, name)`` tuple on success, or ``None`` if the
        payload is too short or has the wrong opcode.
    """
    if len(payload) < 16 or payload[0] != OP_READ_NAME:
        return None
    slot = payload[1]
    name = payload[2:16].decode("ascii", errors="replace").rstrip()
    return slot, name


def parse_config_page(payload: bytes) -> tuple[int, bytes] | None:
    """Parse a config page response (opcode 0x24).

    Args:
        payload: Raw response payload starting with opcode byte.

    Returns:
        ``(page_index, data)`` where ``data`` is exactly 50 bytes, or
        ``None`` if the payload has the wrong opcode or is too short.
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
    """Extract all preset parameters from the stitched config blob.

    Args:
        config_data: 450-byte blob (9 pages × 50 bytes) from
            :meth:`~minidsp.device.DSPmini.read_config`.

    Returns:
        Dict with the following keys, or ``None`` if ``config_data`` is too
        short:

        - ``'names'``: list[str] — 8 channel display names (null-stripped ASCII).
        - ``'gains'``: list[int] — 8 raw gain values 0–400.
        - ``'mutes'``: list[bool] — 8 mute states.
        - ``'phases'``: list[bool] — 8 phase states (``True`` = inverted).
        - ``'link_flags'``: list[int] — 8 per-channel link bitmasks.
        - ``'routings'``: list[int] — 4 per-output input routing bitmasks.
        - ``'gates'``: list[dict] — 4 input noise gate dicts
            (keys: ``attack``, ``release``, ``hold``, ``threshold``, all raw).
        - ``'delays'``: list[int] — 4 output delay raw values (samples at 48 kHz).
        - ``'crossovers'``: list[dict] — 4 output crossover dicts
            (keys: ``hipass_freq``, ``lopass_freq``, ``hipass_slope``, ``lopass_slope``).
        - ``'compressors'``: list[dict] — 4 output compressor dicts
            (keys: ``ratio``, ``knee``, ``attack``, ``release``, ``threshold``, all raw).
        - ``'peqs'``: list[dict] — 4 output PEQ dicts with keys ``'bands'``
            (list[7] of band dicts: ``gain``, ``freq``, ``q``, ``type``, ``bypass``)
            and ``'channel_bypass'`` (bool).
        - ``'test_tone_mode'``: int — ``TONE_*`` constant (config offset 420).
        - ``'test_tone_freq'``: int — ``SINE_FREQ_*`` index (config offset 422).

        Channel order throughout: inputs 0–3, outputs 4–7.
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
    routings: list[int] = []
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
        routings.append(config_data[base + _OUTPUT_ROUTING_OFFSET])
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

    # Test tone generator state (set by 0x39 command, persisted in config footer)
    test_tone_mode = config_data[_TEST_TONE_MODE_OFFSET] if len(config_data) > _TEST_TONE_MODE_OFFSET else 0
    test_tone_freq = config_data[_TEST_TONE_FREQ_OFFSET] if len(config_data) > _TEST_TONE_FREQ_OFFSET else 0

    return {"names": names, "gains": gains, "mutes": mutes, "phases": phases,
            "link_flags": link_flags, "routings": routings, "gates": gates,
            "delays": delays, "crossovers": crossovers, "compressors": compressors,
            "peqs": peqs,
            "test_tone_mode": test_tone_mode, "test_tone_freq": test_tone_freq}


# --- Gain conversion ---

def raw_to_db(raw: int) -> float:
    """Convert raw gain value (0–400) to dB.

    Uses dual resolution: 0.5 dB/step below −20 dB, 0.1 dB/step above.
    Confirmed via dsp-408-ui project (same Musicrown protocol).

    Args:
        raw: Raw gain value 0–400.

    Returns:
        Gain in dB (range −60.0 to +12.0).
    """
    if raw < 80:
        return raw / 2.0 - 60.0
    return (raw - 80) / 10.0 - 20.0


def db_to_raw(db: float) -> int:
    """Convert dB to raw gain value (0–400).

    Uses dual resolution: 0.5 dB/step below −20 dB, 0.1 dB/step above.

    Args:
        db: Gain in dB (range −60.0 to +12.0; clamped at boundaries).

    Returns:
        Raw gain value 0–400.
    """
    if db < -20.0:
        return max(0, round((db + 60.0) * 2))
    return min(400, round(80 + (db + 20.0) * 10))


def peq_gain_to_raw(gain_db: float) -> int:
    """Convert PEQ gain in dB to raw protocol value.

    Range: −12.0 to +12.0 dB → raw 0–240. 0 dB = raw 120. 0.1 dB resolution.

    Args:
        gain_db: PEQ gain in dB, clamped to −12.0–+12.0.

    Returns:
        Raw PEQ gain value 0–240.
    """
    return max(0, min(240, round(gain_db * 10) + 120))


def peq_raw_to_gain(raw: int) -> float:
    """Convert raw PEQ gain value to dB.

    Args:
        raw: Raw PEQ gain value 0–240.

    Returns:
        Gain in dB (range −12.0 to +12.0).
    """
    return (raw - 120) / 10.0


def peq_q_to_raw(q: float) -> int:
    """Convert PEQ Q value to raw protocol value.

    Formula: Q = 0.4 × 320^(raw/100). Range: Q 0.4–128 → raw 0–100.
    Shelf/pass filters are restricted to Q 0.4–3.0 (raw 0–35) by the app UI.

    Args:
        q: Q factor (minimum 0.4).

    Returns:
        Raw Q value 0–100.
    """
    if q <= 0.4:
        return 0
    raw = round(100 * math.log(q / 0.4) / math.log(320))
    return max(0, min(100, raw))


def peq_raw_to_q(raw: int) -> float:
    """Convert raw PEQ Q value to Q factor.

    Args:
        raw: Raw Q value 0–100.

    Returns:
        Q factor (range 0.4–128).
    """
    return 0.4 * (320 ** (raw / 100))


def freq_raw_to_hz(raw: int) -> float:
    """Convert log-scale frequency raw value to Hz.

    Args:
        raw: Raw frequency value 0–300.

    Returns:
        Frequency in Hz (range 19.7–20160 Hz).
    """
    return 19.70 * (20160.0 / 19.70) ** (raw / 300.0)


def comp_threshold_to_db(raw: int) -> float:
    """Convert compressor threshold raw value to dB.

    Args:
        raw: Raw threshold value 0–220.

    Returns:
        Threshold in dB (range −90.0 to +20.0; formula: raw / 2 − 90).
    """
    return raw / 2.0 - 90.0


def comp_attack_to_ms(raw: int) -> int:
    """Convert compressor attack raw value to milliseconds.

    Args:
        raw: Raw attack value 0–998.

    Returns:
        Attack time in ms (range 1–999; formula: raw + 1).
    """
    return raw + 1


def comp_release_to_ms(raw: int) -> int:
    """Convert compressor release raw value to milliseconds.

    Args:
        raw: Raw release value 9–2999.

    Returns:
        Release time in ms (range 10–3000; formula: raw + 1).
    """
    return raw + 1


def gate_threshold_to_db(raw: int) -> float:
    """Convert noise gate threshold raw value to dB.

    Args:
        raw: Raw threshold value 0–180.

    Returns:
        Threshold in dB (range −90.0 to 0.0; formula: raw × 0.5 − 90).
    """
    return raw * 0.5 - 90.0


def gate_time_to_ms(raw: int) -> int:
    """Convert gate attack/hold/release raw value to milliseconds.

    Same encoding as compressor timings. Confirmed by hold range:
    raw 9 → 10 ms (minimum), raw 998 → 999 ms (maximum).

    Args:
        raw: Raw time value.

    Returns:
        Time in ms (formula: raw + 1).
    """
    return raw + 1


def delay_samples_to_ms(raw: int) -> float:
    """Convert output delay raw sample count to milliseconds at 48 kHz.

    Args:
        raw: Raw delay value 0–32640 (samples at 48 kHz).

    Returns:
        Delay in milliseconds (range 0–680 ms).
    """
    return raw / 48.0


# --- Level conversion & calibration ---

# Factory calibration: designed for 63 dB display range matching the
# manufacturer's LED meter layout.  0 dBu → uint16 ~188, -30 dBu → uint16 ~5.
LEVEL_REF_UINT16_FACTORY = 1153
LEVEL_REF_UINT16 = LEVEL_REF_UINT16_FACTORY

_CALIBRATION_LOADED = False


def _load_calibration_ref() -> float | None:
    """Load the calibrated ``REF_LEVEL`` from the package-bundled TOML file.

    Looks for ``calibration.toml`` inside the installed ``minidsp`` package
    (typically written by ``dspanalyze calibrate write``). The file is expected
    to contain a top-level ``ref_level`` key with a float value.

    Returns:
        The ``ref_level`` float read from ``calibration.toml``, or ``None`` if
        the file is absent, unreadable, malformed, or does not contain a
        ``ref_level`` key. Any exception during lookup/parse is swallowed and
        logged at DEBUG level so the factory default can be used as a fallback.
    """
    import importlib.resources
    import tomllib
    try:
        data = importlib.resources.files("minidsp").joinpath("calibration.toml")
        with importlib.resources.as_file(data) as path:
            if path.exists():
                with open(path, "rb") as f:
                    cal = tomllib.load(f)
                return cal.get("ref_level")
    except Exception:
        log.debug("No calibration.toml found in package, using factory default")
    return None


def _ensure_ref_level() -> float:
    """Return the effective ``REF_LEVEL`` for dBu conversion, caching the result.

    On the first call this attempts to load a user calibration via
    :func:`_load_calibration_ref` and, if successful, replaces the module-level
    ``LEVEL_REF_UINT16`` with the calibrated value. Subsequent calls return the
    cached value without re-reading the file. Module state mutated:
    ``LEVEL_REF_UINT16`` and ``_CALIBRATION_LOADED``.

    Returns:
        The effective ``REF_LEVEL`` (uint16 amplitude corresponding to 0 dBu).
        Falls back to ``LEVEL_REF_UINT16_FACTORY`` (1153) when no calibration
        file is bundled.
    """
    global LEVEL_REF_UINT16, _CALIBRATION_LOADED
    if not _CALIBRATION_LOADED:
        _CALIBRATION_LOADED = True
        ref = _load_calibration_ref()
        if ref is not None:
            LEVEL_REF_UINT16 = ref
            log.debug("Loaded calibrated REF_LEVEL = %.2f", ref)
    return LEVEL_REF_UINT16


def level_uint16_to_dbu(raw: int | float) -> float:
    """Convert a linear uint16 amplitude value to dBu.

    Uses the calibrated reference level from ``minidsp/calibration.toml``
    if present, otherwise the factory default (1153).

    Args:
        raw: Linear uint16 amplitude from the device level response.

    Returns:
        Level in dBu, or ``-inf`` for raw values near zero (silence).
    """
    if raw < 0.01:
        return float("-inf")
    ref = _ensure_ref_level()
    return 20.0 * math.log10(raw / ref)


def calibrate_compute_ref(points: list[dict]) -> float | None:
    """Compute best-fit REF_LEVEL from calibration measurement points.

    Fits the model ``dbu = 20 * log10(uint16 / REF)`` using weighted
    least-squares. Each point contributes a per-point REF estimate;
    the result is a weighted geometric mean, weighted by uint16 magnitude
    (higher values have less quantization error).

    Args:
        points: List of dicts, each with keys ``'dbu'`` (float) and
            ``'mean_uint16'`` (float) from a known-level measurement.

    Returns:
        Best-fit REF_LEVEL float, or ``None`` if fewer than 2 valid points
        are provided.
    """
    if len(points) < 2:
        return None
    log_refs = []
    weights = []
    for p in points:
        v = p["mean_uint16"]
        if v < 1:
            continue
        ref = v / (10.0 ** (p["dbu"] / 20.0))
        log_refs.append(math.log(ref))
        weights.append(v)
    if not log_refs:
        return None
    total_w = sum(weights)
    weighted_mean = sum(lr * w for lr, w in zip(log_refs, weights)) / total_w
    return math.exp(weighted_mean)


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

TONE_MODE_NAMES: dict[int, str] = {
    TONE_OFF:   "Off",
    TONE_PINK:  "Pink Noise",
    TONE_WHITE: "White Noise",
    TONE_SINE:  "Sine Wave",
}

SINE_FREQ_NAMES: dict[int, str] = {
    0x00: "20 Hz",    0x01: "25 Hz",    0x02: "31.5 Hz",  0x03: "40 Hz",
    0x04: "50 Hz",    0x05: "63 Hz",    0x06: "80 Hz",    0x07: "100 Hz",
    0x08: "125 Hz",   0x09: "160 Hz",   0x0A: "200 Hz",   0x0B: "250 Hz",
    0x0C: "315 Hz",   0x0D: "400 Hz",   0x0E: "500 Hz",   0x0F: "630 Hz",
    0x10: "800 Hz",   0x11: "1 kHz",    0x12: "1.25 kHz", 0x13: "1.6 kHz",
    0x14: "2 kHz",    0x15: "2.5 kHz",  0x16: "3.15 kHz", 0x17: "4 kHz",
    0x18: "5 kHz",    0x19: "6.3 kHz",  0x1A: "8 kHz",    0x1B: "10 kHz",
    0x1C: "12.5 kHz", 0x1D: "16 kHz",   0x1E: "20 kHz",
}

# Channel display names. Inputs 0–3 (InA–InD), outputs 4–7 (Out1–Out4).
INPUT_CHANNEL_NAMES: tuple[str, ...] = ("InA", "InB", "InC", "InD")
OUTPUT_CHANNEL_NAMES: tuple[str, ...] = ("Out1", "Out2", "Out3", "Out4")
CHANNEL_NAMES: dict[int, str] = {
    i: name for i, name in enumerate(INPUT_CHANNEL_NAMES + OUTPUT_CHANNEL_NAMES)
}


def decode_link_groups(link_flags: list[int]) -> list[dict]:
    """Decode raw link_flags into structured per-channel link information.

    Link flag semantics within each 4-channel group:

    - Standalone: ``flags == own bit only`` (e.g. InA = 0x01)
    - Master: ``flags == OR of all linked bits`` (e.g. InA+InB = 0x03)
    - Slave: ``flags == 0x00``

    Groups are processed independently: inputs 0–3, outputs 4–7.

    Args:
        link_flags: 8 raw link bitmask values (inputs 0–3, outputs 4–7)
            from :func:`parse_preset_params`.

    Returns:
        List of 8 dicts, one per channel, each with keys:

        - ``'role'``: ``"master"``, ``"slave"``, or ``"standalone"``.
        - ``'master'``: int channel index of the master (slaves only), or ``None``.
        - ``'linked_to'``: list[int] of all channels in the group (masters only,
            including self).
    """
    results: list[dict] = []
    for group_start in (0, 4):
        for i in range(4):
            ch = group_start + i
            own_bit = 1 << i
            flags = link_flags[ch] if ch < len(link_flags) else own_bit

            if flags == 0x00:
                master_ch = _find_master(link_flags, group_start, ch)
                results.append({
                    "role": "slave",
                    "master": master_ch,
                    "linked_to": [],
                })
            elif flags == own_bit:
                results.append({
                    "role": "standalone",
                    "master": None,
                    "linked_to": [],
                })
            else:
                linked = [
                    group_start + b
                    for b in range(4)
                    if flags & (1 << b)
                ]
                results.append({
                    "role": "master",
                    "master": None,
                    "linked_to": linked,
                })
    return results


def _find_master(link_flags: list[int], group_start: int, slave_ch: int) -> int | None:
    """Locate the master channel for a given slave inside a 4-channel link group.

    A slave channel carries ``flags == 0x00``; its master is the channel in the
    same group (inputs 0–3 or outputs 4–7) whose flags bitmask has the slave's
    bit set. This helper scans the three sibling channels in the group and
    returns the first match.

    Args:
        link_flags: Full 8-element list of raw link bitmasks from
            :func:`parse_preset_params`.
        group_start: First channel index of the group (``0`` for inputs,
            ``4`` for outputs).
        slave_ch: Unified channel index of the slave whose master to find.

    Returns:
        Unified channel index of the master, or ``None`` if no other channel
        in the group claims this slave (orphaned/inconsistent link state).
    """
    slave_idx = slave_ch - group_start
    slave_bit = 1 << slave_idx
    for b in range(4):
        ch = group_start + b
        if ch == slave_ch:
            continue
        flags = link_flags[ch] if ch < len(link_flags) else 0
        if flags & slave_bit:
            return ch
    return None


_ROUTING_INPUT_BITS = {0: "InA", 1: "InB", 2: "InC", 3: "InD"}


def decode_routing_matrix(routings: list[int]) -> list[dict]:
    """Decode output routing bitmasks into structured per-output information.

    A mask of 0x00 means no input (silence). Default routing is 1:1 diagonal:
    ``[0x01, 0x02, 0x04, 0x08]`` (Out1←InA, Out2←InB, Out3←InC, Out4←InD).

    Args:
        routings: 4-element list of routing bitmasks from
            :func:`parse_preset_params`.

    Returns:
        List of 4 dicts (one per output channel), each with keys:

        - ``'sources'``: list[str] — source names (e.g. ``["InA", "InB"]``).
        - ``'source_indices'``: list[int] — source channel indices.
        - ``'mask'``: int — raw routing bitmask.
    """
    results: list[dict] = []
    for i in range(4):
        mask = routings[i] if i < len(routings) else (1 << i)
        source_indices = [b for b in range(4) if mask & (1 << b)]
        sources = [_ROUTING_INPUT_BITS[b] for b in source_indices]
        results.append({
            "sources": sources,
            "source_indices": source_indices,
            "mask": mask,
        })
    return results
