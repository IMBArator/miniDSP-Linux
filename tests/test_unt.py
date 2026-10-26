"""Tests for :mod:`minidsp.unt` — the .unt preset file format."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from minidsp import unt as unt_module
from minidsp.protocol import parse_preset_params
from minidsp.unt import (
    EMPTY_PRESET_NAME,
    UNT_SIZE,
    UntFile,
    UntParseError,
    slots_to_save,
)

ANALYSIS = Path(__file__).resolve().parent.parent / "analysis"
# fixture name → (filled slots, active slot, PIN)
FIXTURES = {
    "miniDSP current settings.unt": ([1, 2], 2, "1234"),
    "miniDSP current settings 260409.unt": ([1, 2, 30], 30, "7654"),
    "miniDSP current settings 261026.unt": ([1, 2, 3, 30], 3, "ASDF"),
}
# First 50 bytes of the editor-made blank template the Qt app shipped
BLANK_HEADER = bytes.fromhex(
    "2a2a2a3478344d494e4956303130 2a2a 01011e 30303030 0000 270f 0000 31323334 000a00"
    "3478344420416d706c6966696572".replace(" ", ""))


def fixture_bytes(name: str) -> bytes:
    path = ANALYSIS / name
    if not path.exists():
        pytest.skip(f"{name} not present")
    return path.read_bytes()


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_parses_and_roundtrips(name):
    raw = fixture_bytes(name)
    unt = UntFile(raw)
    filled, active, pin = FIXTURES[name]
    assert unt.filled_slots() == filled
    assert unt.active_slot == active
    assert unt.pin == pin
    assert unt.header["product"] == "4x4D Amplifier"
    assert unt.to_bytes() == raw


def test_fixture_slot_names_and_params():
    unt = UntFile(fixture_bytes("miniDSP current settings 261026.unt"))
    assert [unt.slot_name(s) for s in unt.filled_slots()] == [
        "DIY Mon", "DIY Mon offset", "DIY Mon off 2", "Test 2"]
    assert unt.slot_name(4) is None
    assert unt.slot_blob(4) is None
    assert unt.slot_params(1)["names"][0] == "InA"


def test_blank_matches_editor_template_header():
    blank = UntFile.blank()
    data = blank.to_bytes()
    assert len(data) == UNT_SIZE
    assert data[:50] == BLANK_HEADER
    empty_slot = b"\x64" * 430 + b"\r\n"     # as in every editor-saved file
    assert data[50:] == empty_slot * 30
    assert blank.filled_slots() == []


def test_clearing_an_empty_editor_slot_changes_nothing():
    raw = fixture_bytes("miniDSP current settings 261026.unt")
    unt = UntFile(raw)
    for slot in range(4, 30):
        unt.clear_slot(slot)
    assert unt.to_bytes() == raw


def test_from_header_block_rejects_wrong_size():
    with pytest.raises(ValueError):
        UntFile.from_header_block(bytes(33))


def test_set_and_clear_slot():
    src = UntFile(fixture_bytes("miniDSP current settings 261026.unt"))
    unt = UntFile.blank()
    unt.set_slot_blob(5, src.slot_blob(2))
    assert unt.filled_slots() == [5]
    assert unt.slot_name(5) == "DIY Mon offset"
    assert unt.to_bytes()[0x32 + 4 * 432] == 5                       # slot byte
    assert unt.to_bytes()[0x32 + 4 * 432 + 430:0x32 + 5 * 432] == b"\r\n"
    unt.clear_slot(5)
    assert unt.to_bytes() == UntFile.blank().to_bytes()


def test_set_slot_blob_accepts_450_byte_device_config():
    src = UntFile(fixture_bytes("miniDSP current settings 261026.unt"))
    unt = UntFile.blank()
    unt.set_slot_blob(1, src.slot_blob(1) + bytes(21))
    assert unt.slot_blob(1) == src.slot_blob(1)
    with pytest.raises(ValueError):
        unt.set_slot_blob(1, bytes(100))


def test_set_slot_params_edits_only_the_field():
    raw = fixture_bytes("miniDSP current settings 261026.unt")
    unt = UntFile(raw)
    params = unt.slot_params(2)
    params["gains"][0] = 100
    unt.set_slot_params(2, params)
    changed = [i for i, (a, b) in enumerate(zip(raw, unt.to_bytes())) if a != b]
    blob_start = 0x32 + 432 + 1
    assert changed == [blob_start + 16 + 18, blob_start + 16 + 19] or \
        changed == [blob_start + 16 + 18]
    assert unt.slot_params(2)["gains"][0] == 100


def test_set_slot_params_on_unused_slot_creates_a_preset():
    src = UntFile(fixture_bytes("miniDSP current settings 261026.unt"))
    unt = UntFile.blank()
    unt.set_slot_params(7, src.slot_params(1), name="NEW PRESET")
    assert unt.slot_name(7) == "NEW PRESET"
    assert unt.slot_blob(7)[:2] == b"\xff\xff"
    assert parse_preset_params(unt.slot_blob(7))["gains"] == src.slot_params(1)["gains"]


def test_header_setters_validate():
    unt = UntFile.blank()
    unt.active_slot = 30
    unt.pin = "7654"
    assert (unt.active_slot, unt.pin) == (30, "7654")
    with pytest.raises(ValueError):
        unt.active_slot = 31
    with pytest.raises(ValueError):
        unt.pin = "12345"
    with pytest.raises(ValueError):
        unt.slot_blob(0)


def test_parse_errors():
    data = bytearray(UntFile.blank().to_bytes())
    with pytest.raises(UntParseError):
        UntFile(bytes(data[:-1]))
    bad_magic = bytearray(data)
    bad_magic[0] = 0x00
    with pytest.raises(UntParseError):
        UntFile(bad_magic)
    bad_active = bytearray(data)
    bad_active[0x11] = 31
    with pytest.raises(UntParseError):
        UntFile(bad_active)


def test_read_and_write_roundtrip(tmp_path):
    raw = fixture_bytes("miniDSP current settings 260409.unt")
    src = tmp_path / "in.unt"
    src.write_bytes(raw)
    dst = tmp_path / "out.unt"
    UntFile.read(src).write(dst)
    assert dst.read_bytes() == raw
    assert not list(tmp_path.glob(".*.tmp"))


def test_failed_write_keeps_existing_file(tmp_path, monkeypatch):
    dst = tmp_path / "out.unt"
    dst.write_bytes(b"old")

    def broken_replace(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(unt_module.os, "replace", broken_replace)
    with pytest.raises(OSError):
        UntFile.blank().write(dst)
    assert dst.read_bytes() == b"old"
    assert not list(tmp_path.glob(".*.tmp"))


def test_slots_to_save_follows_the_editor_rule():
    names = [EMPTY_PRESET_NAME] * 30
    names[0], names[1], names[29] = "DIY Mon", "DIY Mon offset", "Test 2"
    names[5] = ""          # failed read — skipped
    assert slots_to_save(names) == [1, 2, 30]
