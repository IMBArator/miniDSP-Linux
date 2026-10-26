"""Decoding of the .unt save/restore opcodes from protocol_config.toml.

Payloads are taken verbatim from capture_20261026_221454_editor_startup__save_unt
and capture_20261026_222715_editor_startup__load_unt.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dspanalyze.config import load_config
from dspanalyze.decode import decode_frame, parse_raw_packet
from dspanalyze.readers import RawPacket
from minidsp.protocol import build_frame

HEADER_REPLY = bytes.fromhex(
    "1901031e303030300000270f000041534446000a003478344420416d706c6966696572")


def decode(payload: bytes, direction: str):
    """Frame ``payload`` like the device/host would and decode it."""
    report = bytearray(build_frame(payload))
    if direction == "in":
        report[2], report[3] = report[3], report[2]
    pkt = RawPacket(frame_number=1, timestamp=0.0, direction=direction,
                    endpoint=0x81 if direction == "in" else 0x02,
                    hid_data=bytes(report))
    return decode_frame(parse_raw_packet(pkt), load_config())


def test_new_opcodes_are_known():
    for payload in (b"\x04", b"\x19\x00\x00\x22", b"\x23", b"\x24\x01",
                    b"\x28\x00", bytes([0x25, 0x08, 0x1d]) + bytes(19)):
        assert decode(payload, "out").is_known, payload.hex()


def test_read_header_reply_fields():
    cmd = decode(HEADER_REPLY, "in")
    assert cmd.opcode_name == "read_header"
    assert cmd.fields["active_slot"] == 3
    assert cmd.fields["max_presets"] == 30
    assert cmd.fields["pin"] == "ASDF"
    assert cmd.fields["product"] == "4x4D Amplifier"


def test_0x24_is_decoded_by_direction():
    select = decode(b"\x24\x1e", "out")
    assert select.fields == {"select_slot": 30}
    page = decode(bytes([0x24, 0x03]) + bytes(range(50)), "in")
    assert page.fields["page"] == 3
    assert page.fields["data"] == bytes(range(50))


def test_write_stored_page_fields():
    cmd = decode(bytes([0x25, 0x00, 0x1d]) + bytes(50), "out")
    assert cmd.opcode_name == "write_stored_page"
    assert cmd.fields == {"page": 0, "slot": 29}
    assert decode(b"\x25\x08", "in").fields == {"page": 8}


def test_read_stored_page_reply_carries_50_bytes():
    cmd = decode(bytes([0x28, 0x08]) + bytes(50), "in")
    assert cmd.fields["page"] == 8
    assert len(cmd.fields["data"]) == 50
