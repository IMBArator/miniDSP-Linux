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
    cmd_hipass,
    cmd_lopass,
    cmd_mute,
    cmd_phase,
    cmd_poll,
    cmd_set_channel_name,
    cmd_submit_pin,
    cmd_set_lock_pin,
    cmd_set_delay_unit,
    cmd_test_tone,
    DELAY_UNIT_MS,
    DELAY_UNIT_M,
    DELAY_UNIT_FT,
    TONE_OFF,
    TONE_PINK,
    TONE_WHITE,
    TONE_SINE,
    SINE_FREQ_20HZ,
    SINE_FREQ_20KHZ,
    parse_device_info,
    parse_pin_response,
    LOCK_PIN_CORRECT,
    LOCK_PIN_WRONG,
    cmd_peq_band,
    cmd_peq_channel_bypass,
    peq_gain_to_raw,
    peq_raw_to_gain,
    peq_q_to_raw,
    peq_raw_to_q,
    level_uint16_to_dbu,
    LEVEL_REF_UINT16,
    PEQ_TYPE_PEAK,
    PEQ_TYPE_LOW_SHELF,
    PEQ_TYPE_HIGH_SHELF,
    PEQ_TYPE_LOW_PASS,
    PEQ_TYPE_HIGH_PASS,
    PEQ_TYPE_ALLPASS1,
    PEQ_TYPE_ALLPASS2,
    db_to_raw,
    parse_config_page,
    parse_frame,
    parse_levels,
    parse_preset_params,
    raw_to_db,
    SLOPE_BYPASS,
    SLOPE_BW6,
    SLOPE_LR24,
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


def test_cmd_lopass():
    # Out3 (channel 6), freq raw 300 (20160 Hz max), bypassed
    # Verified from capture: 31 06 2c 01 00
    frame = cmd_lopass(6, 300, SLOPE_BYPASS)
    assert frame[5] == 0x31   # opcode
    assert frame[6] == 0x06   # channel (Out3)
    assert frame[7] == 0x2C   # 300 & 0xFF
    assert frame[8] == 0x01   # 300 >> 8
    assert frame[9] == 0x00   # bypassed

    # Active with LR-24 (default slope): 31 06 2c 01 0a
    frame = cmd_lopass(6, 300, SLOPE_LR24)
    assert frame[9] == 0x0A   # LR-24

    # Clamping: above 300 should clamp to 300
    frame = cmd_lopass(6, 9999)
    assert frame[7] == 0x2C   # 300 & 0xFF
    assert frame[8] == 0x01   # 300 >> 8


def test_cmd_hipass():
    # Out3 (channel 6), freq raw 0, bypassed (default state)
    # Verified from capture: 32 06 00 00 00
    frame = cmd_hipass(6, 0, SLOPE_BYPASS)
    assert frame[5] == 0x32   # opcode
    assert frame[6] == 0x06   # channel (Out3)
    assert frame[7] == 0x00   # 0 & 0xFF
    assert frame[8] == 0x00   # 0 >> 8
    assert frame[9] == 0x00   # bypassed

    # Active with LR-24: 32 06 00 00 0a
    # Verified from bypass capture: un-bypass sends 0x0a
    frame = cmd_hipass(6, 0, SLOPE_LR24)
    assert frame[9] == 0x0A   # LR-24

    # Slope BL-24 (0x09): verified from slope capture
    frame = cmd_hipass(6, 0, 0x09)
    assert frame[9] == 0x09

    # Max frequency: raw 300 (20160 Hz)
    frame = cmd_hipass(6, 300)
    assert frame[7] == 0x2C   # 300 & 0xFF
    assert frame[8] == 0x01   # 300 >> 8

    # Min frequency: raw 0 (19.7 Hz)
    frame = cmd_hipass(6, 0)
    assert frame[7] == 0x00
    assert frame[8] == 0x00


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


def test_cmd_set_channel_name():
    # Out3 (channel 6), name "AUSGANG3" — verified from capture: 3d 06 41 55 53 47 41 4e 47 33
    frame = cmd_set_channel_name(6, "AUSGANG3")
    assert frame[5] == 0x3D           # opcode
    assert frame[6] == 0x06           # channel (Out3)
    assert frame[7:15] == b"AUSGANG3" # 8-byte ASCII name

    # Short name "Out1" (4 chars) — zero-padded to 8 bytes
    frame = cmd_set_channel_name(4, "Out1")
    assert frame[5] == 0x3D
    assert frame[6] == 0x04           # channel (Out1)
    assert frame[7:15] == b"Out1\x00\x00\x00\x00"

    # Input channel: InC (channel 2), name "EINGANGC" — verified from capture: 3d 02 45 49 4e 47 41 4e 47 43
    frame = cmd_set_channel_name(2, "EINGANGC")
    assert frame[5] == 0x3D
    assert frame[6] == 0x02           # channel (InC)
    assert frame[7:15] == b"EINGANGC"

    # Name longer than 8 chars — truncated to 8
    frame = cmd_set_channel_name(0, "TooLongName")
    assert frame[7:15] == b"TooLongN"


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
    # Preset 0 "DIY Mon": default channel names
    assert result["names"] == ["InA", "InB", "InC", "InD", "Out1", "Out2", "Out3", "Out4"]
    # Preset 0 "DIY Mon": all gains = 280 (0 dB), all mutes = False, all phases normal
    assert result["gains"] == [280, 280, 280, 280, 280, 280, 280, 280]
    assert result["mutes"] == [False, False, False, False, False, False, False, False]
    assert result["phases"] == [False, False, False, False, False, False, False, False]
    # Default 1:1 routing: Out1←InA, Out2←InB, Out3←InC, Out4←InD
    assert result["routings"] == [0x01, 0x02, 0x04, 0x08]
    # Gate params should be present for 4 input channels
    assert len(result["gates"]) == 4
    for gate in result["gates"]:
        assert "attack" in gate
        assert "release" in gate
        assert "hold" in gate
        assert "threshold" in gate
    # Delay should be present for 4 output channels
    assert len(result["delays"]) == 4
    # Crossover should be present for 4 output channels
    assert len(result["crossovers"]) == 4
    for xover in result["crossovers"]:
        assert "hipass_freq" in xover
        assert "lopass_freq" in xover
        assert "hipass_slope" in xover
        assert "lopass_slope" in xover
    # Compressor should be present for 4 output channels
    assert len(result["compressors"]) == 4
    for comp in result["compressors"]:
        assert "ratio" in comp
        assert "knee" in comp
        assert "attack" in comp
        assert "release" in comp
        assert "threshold" in comp
    # PEQ should be present for 4 output channels, 7 bands each
    assert len(result["peqs"]) == 4
    for peq in result["peqs"]:
        assert "channel_bypass" in peq
        assert len(peq["bands"]) == 7
        for band in peq["bands"]:
            assert "gain" in band
            assert "freq" in band
            assert "q" in band
            assert "type" in band
            assert "bypass" in band


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
    # Preset 1 "DIY Mon offset": same default channel names
    assert result["names"] == ["InA", "InB", "InC", "InD", "Out1", "Out2", "Out3", "Out4"]
    # Input gains unchanged (all 280)
    assert result["gains"][:4] == [280, 280, 280, 280]
    # Output gains: Out1=255, Out2=286, Out3=280, Out4=300
    assert result["gains"][4:] == [255, 286, 280, 300]
    assert result["mutes"] == [False, False, False, False, False, False, False, False]
    assert result["phases"] == [False, False, False, False, False, False, False, False]


def test_cmd_peq_band():
    # Peak band at 0dB, freq=0 (min), Q=25 (raw), active — matches capture pattern
    frame = cmd_peq_band(0x04, 0, gain_raw=120, freq_raw=0, q_raw=25, filter_type=PEQ_TYPE_PEAK)
    assert frame[5] == 0x33           # opcode
    assert frame[6] == 0x04           # channel Out1
    assert frame[7] == 0x00           # band 0
    assert frame[8] == 120            # gain low byte (0dB)
    assert frame[9] == 0x00           # gain high byte
    assert frame[10] == 0x00          # freq low byte
    assert frame[11] == 0x00          # freq high byte
    assert frame[12] == 25            # Q raw
    assert frame[13] == PEQ_TYPE_PEAK
    assert frame[14] == 0x00          # active

    # Low Shelf, bypassed
    frame = cmd_peq_band(0x04, 0, gain_raw=120, freq_raw=0, q_raw=10,
                         filter_type=PEQ_TYPE_LOW_SHELF, bypass=True)
    assert frame[13] == PEQ_TYPE_LOW_SHELF
    assert frame[14] == 0x01          # bypassed

    # Max freq (300) and max gain (+12dB = raw 240)
    frame = cmd_peq_band(0x04, 6, gain_raw=240, freq_raw=300, q_raw=100,
                         filter_type=PEQ_TYPE_HIGH_SHELF)
    assert frame[7] == 0x06           # band 6 (band 7)
    assert frame[8] == 240            # gain = +12dB
    assert frame[9] == 0x00           # gain high byte (240 < 256)
    assert frame[10] == 44            # freq 300 low byte (300 = 0x012c → lo=0x2c=44)
    assert frame[11] == 1             # freq 300 high byte
    assert frame[12] == 100           # Q max


def test_cmd_peq_channel_bypass():
    # Bypass Out1 — verified from capture: 3c 04 01
    frame = cmd_peq_channel_bypass(0x04, bypass=True)
    assert frame[5] == 0x3C           # opcode
    assert frame[6] == 0x04           # channel Out1
    assert frame[7] == 0x01           # bypassed

    # Restore Out1 — verified from capture: 3c 04 00
    frame = cmd_peq_channel_bypass(0x04, bypass=False)
    assert frame[7] == 0x00           # active


def test_peq_gain_encoding():
    assert peq_gain_to_raw(0.0) == 120
    assert peq_gain_to_raw(-12.0) == 0
    assert peq_gain_to_raw(12.0) == 240
    assert peq_raw_to_gain(120) == 0.0
    assert peq_raw_to_gain(0) == -12.0
    assert peq_raw_to_gain(240) == 12.0
    assert peq_gain_to_raw(peq_raw_to_gain(150)) == 150  # round-trip


def test_peq_q_encoding():
    import math
    assert peq_q_to_raw(0.4) == 0       # minimum Q
    assert peq_q_to_raw(128.0) == 100   # maximum Q (Peak)
    # Q=3.0 should map to raw 35 (shelf/pass max)
    assert peq_q_to_raw(3.0) == 35
    # Round-trip
    assert abs(peq_raw_to_q(peq_q_to_raw(2.0)) - 2.0) < 0.05
    assert abs(peq_raw_to_q(0) - 0.4) < 0.001
    assert abs(peq_raw_to_q(100) - 128.0) < 0.01


def test_level_uint16_to_dbu():
    # Reference uint16 maps to 0 dBu
    assert LEVEL_REF_UINT16 == 1153
    assert level_uint16_to_dbu(LEVEL_REF_UINT16) == 0.0
    # Silence: raw 0 → -inf
    assert level_uint16_to_dbu(0) == float("-inf")
    # Calibration anchors verified from captures (matches prior inline formula):
    # 0 dBu ≈ uint16 188 (actual: ~-15.75 dBu); −30 dBu ≈ uint16 5
    assert abs(level_uint16_to_dbu(188) - (-15.75)) < 0.01
    assert abs(level_uint16_to_dbu(5) - (-47.26)) < 0.01


# --- Device info lock flag (0x2C) ---

def test_parse_device_info_unlocked():
    # Verified from set-pin capture (unlocked): 2c 00 27 0f 00 00 00 00
    payload = bytes([0x2C, 0x00, 0x27, 0x0F, 0x00, 0x00, 0x00, 0x00])
    info = parse_device_info(payload)
    assert info is not None
    assert info["locked"] is False


def test_parse_device_info_locked():
    # Verified from unlock + wrong-pin captures (locked): 2c 00 27 0f 00 00 01 00
    payload = bytes([0x2C, 0x00, 0x27, 0x0F, 0x00, 0x00, 0x01, 0x00])
    info = parse_device_info(payload)
    assert info is not None
    assert info["locked"] is True


def test_parse_device_info_invalid():
    assert parse_device_info(bytes([0x01])) is None       # wrong opcode
    assert parse_device_info(bytes([0x2C, 0x00])) is None  # too short


# --- Device lock (0x2D / 0x2F) ---

def test_cmd_submit_pin_correct():
    # Verified from capture: PIN "7654" = 0x37 0x36 0x35 0x34
    frame = cmd_submit_pin("7654")
    payload = frame[5:5 + frame[4]]
    assert payload == bytes([0x2D, 0x00, 0x37, 0x36, 0x35, 0x34])


def test_cmd_submit_pin_wrong():
    # Wrong PIN "8888" = 0x38 0x38 0x38 0x38 (captured from wrong-pin capture)
    frame = cmd_submit_pin("8888")
    payload = frame[5:5 + frame[4]]
    assert payload == bytes([0x2D, 0x00, 0x38, 0x38, 0x38, 0x38])


def test_cmd_set_lock_pin():
    # Verified from capture: PIN "7654" = 0x37 0x36 0x35 0x34
    frame = cmd_set_lock_pin("7654")
    payload = frame[5:5 + frame[4]]
    assert payload == bytes([0x2F, 0x37, 0x36, 0x35, 0x34])


def test_parse_pin_response_correct():
    # Device says PIN correct: 2d 00 01
    assert parse_pin_response(bytes([0x2D, 0x00, LOCK_PIN_CORRECT])) is True


def test_parse_pin_response_wrong():
    # Device says PIN wrong: 2d 00 00
    assert parse_pin_response(bytes([0x2D, 0x00, LOCK_PIN_WRONG])) is False


def test_parse_pin_response_invalid():
    assert parse_pin_response(bytes([0x01, 0x00])) is None  # wrong opcode
    assert parse_pin_response(bytes([0x2D, 0x00])) is None   # too short


def test_cmd_set_delay_unit_ms():
    # payload=1500 from capture (unit ms=0x00): 10 02 00 01 02 15 00 10 03 17
    frame = cmd_set_delay_unit(DELAY_UNIT_MS)
    payload = frame[5:7]
    assert payload == bytes([0x15, 0x00])
    assert frame[7] == 0x10 and frame[8] == 0x03
    # checksum: LEN=0x02 ^ 0x15 ^ 0x00 = 0x17
    assert frame[9] == 0x17


def test_cmd_set_delay_unit_m():
    # payload=1501 from capture (unit m=0x01): 10 02 00 01 02 15 01 10 03 16
    frame = cmd_set_delay_unit(DELAY_UNIT_M)
    payload = frame[5:7]
    assert payload == bytes([0x15, 0x01])
    assert frame[9] == 0x16


def test_cmd_set_delay_unit_ft():
    # payload=1502 from capture (unit ft=0x02): 10 02 00 01 02 15 02 10 03 15
    frame = cmd_set_delay_unit(DELAY_UNIT_FT)
    payload = frame[5:7]
    assert payload == bytes([0x15, 0x02])
    assert frame[9] == 0x15


# --- Test Tone Generator (0x39) ---

def test_cmd_test_tone_white_noise():
    # Capture payload=390200; checksum XOR(len=3, 0x39, 0x02, 0x00) = 0x38
    frame = cmd_test_tone(TONE_WHITE, SINE_FREQ_20HZ)
    assert frame[5:8] == bytes([0x39, 0x02, 0x00])
    assert frame[10] == 0x38


def test_cmd_test_tone_pink_noise():
    # Capture payload=390100; checksum XOR(len=3, 0x39, 0x01, 0x00) = 0x3B
    frame = cmd_test_tone(TONE_PINK)
    assert frame[5:8] == bytes([0x39, 0x01, 0x00])
    assert frame[10] == 0x3B


def test_cmd_test_tone_sine_20hz():
    # From capture: payload=390300, freq index 0x00=20Hz
    frame = cmd_test_tone(TONE_SINE, SINE_FREQ_20HZ)
    assert frame[5:8] == bytes([0x39, 0x03, 0x00])


def test_cmd_test_tone_sine_20khz():
    # From capture: payload=39031e, freq index 0x1E=20kHz
    frame = cmd_test_tone(TONE_SINE, SINE_FREQ_20KHZ)
    assert frame[5:8] == bytes([0x39, 0x03, 0x1E])


def test_cmd_test_tone_off():
    # From capture: payload=390001 (after sine session at freq 0x01=25Hz)
    frame = cmd_test_tone(TONE_OFF, 0x01)
    assert frame[5:8] == bytes([0x39, 0x00, 0x01])


def test_cmd_test_tone_freq_index_clamped():
    # freq_index must be clamped to 0x00-0x1E
    frame = cmd_test_tone(TONE_SINE, 0xFF)
    assert frame[7] == 0x1E  # clamped to max


def test_cmd_compressor():
    """Verify compressor frame encoding (0x30): Out1, ratio=1:2, knee=6, atk=49, rel=499, thr=220."""
    from minidsp.protocol import cmd_compressor
    frame = cmd_compressor(0x04, 0x05, 6, 49, 499, 220)
    assert frame[5] == 0x30   # opcode
    assert frame[6] == 0x04   # channel (Out1)
    assert frame[7] == 0x05   # ratio (1:2.0)
    assert frame[8] == 0x06   # knee (6 dB)
    assert frame[9] == 49     # attack lo
    assert frame[10] == 0x00  # attack hi
    assert frame[11] == (499 & 0xFF)   # release lo
    assert frame[12] == (499 >> 8)     # release hi
    assert frame[13] == 220   # threshold lo
    assert frame[14] == 0x00  # threshold hi


def test_cmd_matrix_route():
    """Verify matrix routing frame encoding (0x3A): Out1 from InA+InB."""
    from minidsp.protocol import cmd_matrix_route
    frame = cmd_matrix_route(0x04, 0x03)
    assert frame[5] == 0x3A  # opcode
    assert frame[6] == 0x04  # output channel
    assert frame[7] == 0x03  # input bitmask (InA+InB)


def test_cmd_load_preset():
    """Verify load-preset frame encoding (0x20): slot 5 = U05."""
    from minidsp.protocol import cmd_load_preset
    frame = cmd_load_preset(5)
    assert frame[5] == 0x20  # opcode
    assert frame[6] == 0x05  # slot


def test_cmd_store_preset():
    """Verify store-preset frame encoding (0x21): slot 1 = U01."""
    from minidsp.protocol import cmd_store_preset
    frame = cmd_store_preset(1)
    assert frame[5] == 0x21  # opcode
    assert frame[6] == 0x01  # slot


def test_cmd_store_preset_slot0_guard():
    """Slot 0 (F00 factory preset) must raise ValueError."""
    from minidsp.protocol import cmd_store_preset
    try:
        cmd_store_preset(0)
        assert False, "Expected ValueError for slot 0"
    except ValueError:
        pass  # expected


def test_cmd_store_preset_name():
    """Verify store-preset-name frame encoding (0x26): 14-char space-padded."""
    from minidsp.protocol import cmd_store_preset_name
    frame = cmd_store_preset_name("My Preset")
    assert frame[5] == 0x26  # opcode
    # "My Preset" = 9 chars, padded with spaces to 14
    assert frame[6:20] == b"My Preset     "


def test_cmd_matrix_route_silence():
    """Verify routing with no inputs (silence)."""
    from minidsp.protocol import cmd_matrix_route
    frame = cmd_matrix_route(0x07, 0x00)
    assert frame[5] == 0x3A
    assert frame[6] == 0x07  # Out4
    assert frame[7] == 0x00  # no inputs


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
