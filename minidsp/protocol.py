"""
the t.racks DSP 4x4 Mini — USB HID protocol encoding/decoding.

Frame format (inside 64-byte HID report):
    10 02 [SRC] [DST] [LEN] [PAYLOAD...] 10 03 [CHK]

Checksum = XOR of LEN and all payload bytes.
"""

from __future__ import annotations

VENDOR_ID = 0x0168
PRODUCT_ID = 0x0821
REPORT_SIZE = 64

# Opcodes
OP_INIT = 0x10
OP_ACTIVATE = 0x12
OP_FIRMWARE = 0x13
OP_PRESET_INDEX = 0x14
OP_PRESET_HEADER = 0x22
OP_READ_CONFIG = 0x27
OP_READ_NAME = 0x29
OP_DEVICE_INFO = 0x2C
OP_GAIN = 0x34
OP_MUTE = 0x35
OP_POLL = 0x40


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
        return None
    src = data[2]
    dst = data[3]
    length = data[4]
    if 5 + length + 3 > len(data):
        return None
    payload = data[5 : 5 + length]
    etx1 = data[5 + length]
    etx2 = data[5 + length + 1]
    chk = data[5 + length + 2]
    if etx1 != 0x10 or etx2 != 0x03:
        return None
    if chk != checksum(length, payload):
        return None
    return src, dst, length, payload


# --- Command builders ---

def cmd_poll() -> bytes:
    """Build a level-poll command (0x40)."""
    return build_frame(bytes([OP_POLL]))


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


def cmd_init() -> bytes:
    """Build init handshake command (0x10)."""
    return build_frame(bytes([OP_INIT]))


def cmd_firmware() -> bytes:
    """Build firmware/model string query (0x13)."""
    return build_frame(bytes([OP_FIRMWARE]))


def cmd_device_info() -> bytes:
    """Build device info query (0x2C)."""
    return build_frame(bytes([OP_DEVICE_INFO]))


def cmd_preset_header() -> bytes:
    """Build active preset header query (0x22)."""
    return build_frame(bytes([OP_PRESET_HEADER]))


def cmd_preset_index() -> bytes:
    """Build active preset index query (0x14)."""
    return build_frame(bytes([OP_PRESET_INDEX]))


def cmd_read_name(slot: int) -> bytes:
    """Build preset name read command (0x29).

    slot: 0–29.
    """
    return build_frame(bytes([OP_READ_NAME, slot]))


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
_INPUT_GAIN_OFFSET = 18     # uint16 LE within input block

_PRESET_OUTPUT_START = 112  # 4 × 74-byte output blocks
_OUTPUT_BLOCK_SIZE = 74
_OUTPUT_GAIN_OFFSET = 66    # uint16 LE within output block

# Mute bitmasks in the config footer (after channel blocks)
_INPUT_MUTE_BITMASK_OFFSET = 408   # uint16 LE, bit 0=In1 .. bit 3=In4
_OUTPUT_MUTE_BITMASK_OFFSET = 410  # uint16 LE, bit 0=Out1 .. bit 3=Out4


def parse_config_page(payload: bytes) -> tuple[int, bytes] | None:
    """Parse a config page response (opcode 0x24).

    Returns (page_index, 50_bytes_data) or None.
    """
    if len(payload) < 2 or payload[0] != OP_CONFIG_RESP:
        return None
    page = payload[1]
    data = payload[2:2 + CONFIG_PAGE_SIZE]
    if len(data) != CONFIG_PAGE_SIZE:
        return None
    return page, data


def parse_preset_params(config_data: bytes) -> dict | None:
    """Extract gain and mute for all 8 channels from stitched config data.

    config_data: 450 bytes (9 pages × 50 bytes) from read_config().
    Returns dict with 'gains' (list[8], raw 0–400) and 'mutes' (list[8], bool).
    Channel order: inputs 0–3, outputs 4–7.

    Mute state is read from bitmasks in the config footer (offsets 408-411),
    not from the per-channel blocks. Verified against startup captures with
    In4+Out4 muted vs unmuted.
    """
    if len(config_data) < _OUTPUT_MUTE_BITMASK_OFFSET + 2:
        return None

    gains: list[int] = []
    mutes: list[bool] = []

    # Gain: per-channel blocks
    for i in range(4):
        base = _PRESET_INPUT_START + i * _INPUT_BLOCK_SIZE
        gain = config_data[base + _INPUT_GAIN_OFFSET] + config_data[base + _INPUT_GAIN_OFFSET + 1] * 256
        gains.append(gain)

    for i in range(4):
        base = _PRESET_OUTPUT_START + i * _OUTPUT_BLOCK_SIZE
        gain = config_data[base + _OUTPUT_GAIN_OFFSET] + config_data[base + _OUTPUT_GAIN_OFFSET + 1] * 256
        gains.append(gain)

    # Mute: bitmasks in config footer
    input_mute_mask = config_data[_INPUT_MUTE_BITMASK_OFFSET] + config_data[_INPUT_MUTE_BITMASK_OFFSET + 1] * 256
    output_mute_mask = config_data[_OUTPUT_MUTE_BITMASK_OFFSET] + config_data[_OUTPUT_MUTE_BITMASK_OFFSET + 1] * 256

    for i in range(4):
        mutes.append(bool(input_mute_mask & (1 << i)))
    for i in range(4):
        mutes.append(bool(output_mute_mask & (1 << i)))

    return {"gains": gains, "mutes": mutes}


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
