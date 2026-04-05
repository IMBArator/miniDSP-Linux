"""Tests for the protocol encoding/decoding — verified against real captures."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from minidsp.protocol import (
    _ch_level,
    build_frame,
    checksum,
    cmd_delay,
    cmd_gain,
    cmd_gate,
    cmd_mute,
    cmd_phase,
    cmd_poll,
    db_to_raw,
    parse_config_page,
    parse_frame,
    parse_levels,
    parse_preset_params,
    raw_to_db,
)


# --- Checksum ---

def test_checksum_poll():
    # Poll: LEN=1, payload=0x40, CHK should be 0x41
    assert checksum(1, bytes([0x40])) == 0x41


def test_checksum_mute_on():
    # Mute ON: LEN=3, payload=35 00 01, CHK should be 0x37
    assert checksum(3, bytes([0x35, 0x00, 0x01])) == 0x37


def test_checksum_mute_off():
    # Mute OFF: LEN=3, payload=35 00 00, CHK should be 0x36
    assert checksum(3, bytes([0x35, 0x00, 0x00])) == 0x36


# --- Frame building ---

def test_build_poll_frame():
    frame = build_frame(bytes([0x40]))
    # Known good: 10 02 00 01 01 40 10 03 41
    assert frame[:9] == bytes([0x10, 0x02, 0x00, 0x01, 0x01, 0x40, 0x10, 0x03, 0x41])
    assert len(frame) == 64


def test_build_mute_on_frame():
    frame = build_frame(bytes([0x35, 0x00, 0x01]))
    expected = bytes([0x10, 0x02, 0x00, 0x01, 0x03, 0x35, 0x00, 0x01, 0x10, 0x03, 0x37])
    assert frame[:11] == expected


def test_build_mute_off_frame():
    frame = build_frame(bytes([0x35, 0x00, 0x00]))
    expected = bytes([0x10, 0x02, 0x00, 0x01, 0x03, 0x35, 0x00, 0x00, 0x10, 0x03, 0x36])
    assert frame[:11] == expected


def test_build_gain_frame_min():
    frame = build_frame(bytes([0x34, 0x00, 0x00, 0x00]))
    expected = bytes([0x10, 0x02, 0x00, 0x01, 0x04, 0x34, 0x00, 0x00, 0x00, 0x10, 0x03, 0x30])
    assert frame[:12] == expected


def test_build_gain_frame_max():
    frame = build_frame(bytes([0x34, 0x00, 0x90, 0x01]))
    expected = bytes([0x10, 0x02, 0x00, 0x01, 0x04, 0x34, 0x00, 0x90, 0x01, 0x10, 0x03, 0xA1])
    assert frame[:12] == expected


# --- Frame parsing ---

def test_parse_ack():
    # ACK: 10 02 01 00 01 01 10 03 00
    data = bytes([0x10, 0x02, 0x01, 0x00, 0x01, 0x01, 0x10, 0x03, 0x00])
    data += b"\x00" * (64 - len(data))
    result = parse_frame(data)
    assert result is not None
    src, dst, length, payload = result
    assert src == 0x01
    assert dst == 0x00
    assert length == 1
    assert payload == bytes([0x01])


def test_parse_invalid():
    assert parse_frame(b"\x00" * 64) is None
    assert parse_frame(b"") is None


# --- Command helpers ---

def test_cmd_poll():
    frame = cmd_poll()
    assert len(frame) == 64
    assert frame[5] == 0x40


def test_cmd_mute():
    frame = cmd_mute(0, True)
    assert frame[5:8] == bytes([0x35, 0x00, 0x01])

    frame = cmd_mute(2, False)
    assert frame[5:8] == bytes([0x35, 0x02, 0x00])


def test_cmd_phase():
    # InC inverted: 36 02 01
    frame = cmd_phase(2, True)
    assert frame[5:8] == bytes([0x36, 0x02, 0x01])

    # Out4 normal: 36 07 00
    frame = cmd_phase(7, False)
    assert frame[5:8] == bytes([0x36, 0x07, 0x00])


def test_cmd_gain():
    # channel 0, raw 280 (0 dB)
    frame = cmd_gain(0, 280)
    assert frame[5] == 0x34
    assert frame[6] == 0x00  # channel
    assert frame[7] == 0x18  # 280 & 0xFF
    assert frame[8] == 0x01  # 280 >> 8

    # channel 2, raw 400 (+12 dB)
    frame = cmd_gain(2, 400)
    assert frame[6] == 0x02
    assert frame[7] == 0x90  # 400 & 0xFF
    assert frame[8] == 0x01  # 400 >> 8


def test_cmd_delay():
    # Out4 (channel 7), 32640 samples = 680 ms max
    # Verified from capture: 38 07 80 7f
    frame = cmd_delay(7, 32640)
    assert frame[5] == 0x38   # opcode
    assert frame[6] == 0x07   # channel (Out4)
    assert frame[7] == 0x80   # 32640 & 0xFF
    assert frame[8] == 0x7F   # 32640 >> 8

    # Out1 (channel 4), 0 samples = 0 ms
    frame = cmd_delay(4, 0)
    assert frame[5] == 0x38
    assert frame[6] == 0x04
    assert frame[7] == 0x00
    assert frame[8] == 0x00

    # Out2 (channel 5), 4800 samples = 100 ms
    frame = cmd_delay(5, 4800)
    assert frame[5] == 0x38
    assert frame[6] == 0x05
    assert frame[7] == 0xC0   # 4800 & 0xFF = 192 = 0xC0
    assert frame[8] == 0x12   # 4800 >> 8 = 18 = 0x12

    # Clamping: above 32640 should clamp
    frame = cmd_delay(7, 99999)
    assert frame[7] == 0x80
    assert frame[8] == 0x7F


def test_cmd_gate():
    # InC (channel 2): attack=998, release=2999, hold=998, threshold=180
    # Verified from capture: 3e 02 e6 03 b7 0b e6 03 b4 00
    frame = cmd_gate(2, 998, 2999, 998, 180)
    assert frame[5] == 0x3E   # opcode
    assert frame[6] == 0x02   # channel
    assert frame[7] == 0xE6   # attack lo (998 & 0xFF)
    assert frame[8] == 0x03   # attack hi (998 >> 8)
    assert frame[9] == 0xB7   # release lo (2999 & 0xFF)
    assert frame[10] == 0x0B  # release hi (2999 >> 8)
    assert frame[11] == 0xE6  # hold lo (998 & 0xFF)
    assert frame[12] == 0x03  # hold hi (998 >> 8)
    assert frame[13] == 0xB4  # threshold lo (180 & 0xFF)
    assert frame[14] == 0x00  # threshold hi (180 >> 8)

    # InA defaults: attack=49, release=9, hold=9, threshold=0
    frame = cmd_gate(0, 49, 9, 9, 0)
    assert frame[5] == 0x3E
    assert frame[6] == 0x00
    assert frame[7] == 0x31  # 49 & 0xFF
    assert frame[8] == 0x00


# --- Level parsing ---

def test_parse_levels_normal_mode():
    """Normal mode: uint16=0 for all channels → all zeros (instant ignored)."""
    payload = bytearray(28)
    payload[0] = 0x40
    # Triplets: [val_lo=0, val_hi=0, instant] — uint16=0 → level is 0
    payload[1] = 0;  payload[2] = 0;  payload[3] = 240   # in1 instant ignored
    payload[4] = 0;  payload[5] = 0;  payload[6] = 178   # in2 instant ignored
    payload[7] = 0;  payload[8] = 0;  payload[9] = 15    # in3 noise floor ignored
    payload[10] = 0; payload[11] = 0; payload[12] = 0    # in4 silence
    payload[13] = 0; payload[14] = 0; payload[15] = 200  # out1 instant ignored
    payload[16] = 0; payload[17] = 0; payload[18] = 28   # out2 noise floor ignored
    payload[19] = 0; payload[20] = 0; payload[21] = 5    # out3 noise floor ignored
    payload[22] = 0; payload[23] = 0; payload[24] = 150  # out4 instant ignored
    payload[25] = 0x00  # no limiter
    payload[26] = 0x00  # idle

    result = parse_levels(bytes(payload))
    assert result is not None
    assert result["inputs"] == [0, 0, 0, 0]
    assert result["outputs"] == [0, 0, 0, 0]
    assert result["limiter_mask"] == 0x00
    assert result["state"] == 0x00


def test_parse_levels_highres_mode():
    """High-res mode: uint16 LE > 0, level comes from uint16."""
    payload = bytearray(28)
    payload[0] = 0x40
    # In1: val_lo=134, val_hi=0 → uint16=134
    payload[1] = 134; payload[2] = 0; payload[3] = 67
    # In2: val_lo=141, val_hi=0 → uint16=141
    payload[4] = 141; payload[5] = 0; payload[6] = 178
    # In3: uint16=0 → 0
    payload[7] = 0;   payload[8] = 0; payload[9] = 10
    # In4: all zero
    payload[10] = 0;  payload[11] = 0; payload[12] = 0
    # Out1: val_lo=93, val_hi=0 → uint16=93
    payload[13] = 93; payload[14] = 0; payload[15] = 183
    # Out2: val_lo=8, val_hi=1 → uint16=264 (exceeds 255)
    payload[16] = 8;  payload[17] = 1; payload[18] = 191
    # Out3: uint16=0 → 0
    payload[19] = 0;  payload[20] = 0; payload[21] = 10
    # Out4: uint16=0 → 0
    payload[22] = 0;  payload[23] = 0; payload[24] = 10
    payload[25] = 0x00
    payload[26] = 0x01

    result = parse_levels(bytes(payload))
    assert result is not None
    assert result["inputs"] == [134, 141, 0, 0]
    assert result["outputs"] == [93, 264, 0, 0]


def test_ch_level_uint16_le():
    """_ch_level returns uint16 LE from first two bytes, ignores instant."""
    # uint16=0 → 0 (instant byte ignored)
    data = bytes([0x00, 0x00, 0x64])
    assert _ch_level(data, 0) == 0
    # uint16=0x85 (lo only) → 133
    data = bytes([0x85, 0x00, 0x43])
    assert _ch_level(data, 0) == 0x85
    # uint16 exceeds 255: val_lo=8, val_hi=1 → 264
    data = bytes([0x08, 0x01, 0x43])
    assert _ch_level(data, 0) == 264


# --- dB conversion ---

def test_raw_to_db_calibration_points():
    """Verified from 5 captures at known dB targets."""
    assert raw_to_db(160) == -12.0
    assert raw_to_db(280) == 0.0
    assert abs(raw_to_db(310) - 3.0) < 0.01
    assert raw_to_db(340) == 6.0
    assert raw_to_db(400) == 12.0


def test_raw_to_db_dual_resolution():
    """Dual resolution: coarse below -20 dB, fine above."""
    assert raw_to_db(0) == -60.0
    assert raw_to_db(1) == -59.5
    assert raw_to_db(79) == -20.5
    assert raw_to_db(80) == -20.0
    assert raw_to_db(81) == -19.9


def test_db_to_raw_roundtrip():
    assert db_to_raw(-60.0) == 0
    assert db_to_raw(-40.0) == 40
    assert db_to_raw(-20.0) == 80
    assert db_to_raw(-12.0) == 160
    assert db_to_raw(0.0) == 280
    assert db_to_raw(3.0) == 310
    assert db_to_raw(6.0) == 340
    assert db_to_raw(12.0) == 400


def test_gain_clamping():
    assert db_to_raw(-70.0) == 0
    assert db_to_raw(20.0) == 400


# --- Config parsing ---

def test_parse_config_page():
    payload = bytearray(52)
    payload[0] = 0x24  # config response opcode
    payload[1] = 0x03  # page 3
    payload[2:52] = bytes(range(50))  # dummy data
    page, data = parse_config_page(bytes(payload))
    assert page == 3
    assert len(data) == 50
    assert data == bytes(range(50))


def test_parse_config_page_invalid():
    assert parse_config_page(bytes([0x40, 0x00])) is None
    assert parse_config_page(bytes([0x24])) is None


def test_parse_preset_params_from_unt():
    """Verify config parsing against real .unt file (preset 0 = 'DIY Mon')."""
    unt_path = os.path.join(os.path.dirname(__file__), "..", "analysis", "miniDSP current settings.unt")
    if not os.path.exists(unt_path):
        return  # skip if .unt not present
    with open(unt_path, "rb") as f:
        file_data = f.read()
    # Preset 0 starts at offset 0x33, config data starts 2 bytes after (skip FF FF marker)
    # The config pages contain: [FF FF marker + preset name + blocks...]
    # parse_preset_params expects the full 459 bytes including the FF FF + name
    preset_start = file_data.index(b"\xFF\xFF")
    config_data = file_data[preset_start:preset_start + 459]
    result = parse_preset_params(config_data)
    assert result is not None
    # Preset 0 "DIY Mon": all gains = 280 (0 dB), all mutes = False, all phases normal
    assert result["gains"] == [280, 280, 280, 280, 280, 280, 280, 280]
    assert result["mutes"] == [False, False, False, False, False, False, False, False]
    assert result["phases"] == [False, False, False, False, False, False, False, False]
    # Gate params should be present for 4 input channels
    assert len(result["gates"]) == 4
    for gate in result["gates"]:
        assert "attack" in gate
        assert "release" in gate
        assert "hold" in gate
        assert "threshold" in gate
    # Delay should be present for 4 output channels
    assert len(result["delays"]) == 4


def test_parse_preset_params_modified():
    """Verify config parsing for preset 1 ('DIY Mon offset') with modified output gains."""
    unt_path = os.path.join(os.path.dirname(__file__), "..", "analysis", "miniDSP current settings.unt")
    if not os.path.exists(unt_path):
        return  # skip if .unt not present
    with open(unt_path, "rb") as f:
        file_data = f.read()
    # Preset 1 starts at second FF FF marker
    first = file_data.index(b"\xFF\xFF")
    second = file_data.index(b"\xFF\xFF", first + 2)
    config_data = file_data[second:second + 459]
    result = parse_preset_params(config_data)
    assert result is not None
    # Input gains unchanged (all 280)
    assert result["gains"][:4] == [280, 280, 280, 280]
    # Output gains: Out1=255, Out2=286, Out3=280, Out4=300
    assert result["gains"][4:] == [255, 286, 280, 300]
    assert result["mutes"] == [False, False, False, False, False, False, False, False]
    assert result["phases"] == [False, False, False, False, False, False, False, False]


if __name__ == "__main__":
    # Simple test runner — no pytest needed
    import inspect
    tests = [(name, obj) for name, obj in globals().items()
             if name.startswith("test_") and inspect.isfunction(obj)]
    passed = failed = 0
    for name, func in sorted(tests):
        try:
            func()
            passed += 1
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
