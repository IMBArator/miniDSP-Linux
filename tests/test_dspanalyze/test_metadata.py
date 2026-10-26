"""Tests for dspanalyze.metadata sidecar handling."""

import sys, os, tomllib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import tomli_w

from dspanalyze.metadata import meta_path_for, write_metadata


def test_refresh_keeps_capture_provenance_and_description(tmp_path):
    capture = tmp_path / "capture_x.pcapng"
    capture.write_bytes(b"")
    with open(meta_path_for(capture), "wb") as f:
        tomli_w.dump({
            "capture": {"file": "old.pcapng", "format": "pcapng",
                        "created": "2026-10-26T22:28:06", "source_machine": "windows",
                        "interface": "\\\\.\\USBPcap1", "device_address": 14},
            "description": {"feature": "editor startup + load .unt", "notes": "reboot"},
        }, f)

    write_metadata(capture, [])

    with open(meta_path_for(capture), "rb") as f:
        meta = tomllib.load(f)
    assert meta["capture"]["file"] == "capture_x.pcapng"      # recomputed
    assert meta["capture"]["device_address"] == 14            # kept
    assert meta["capture"]["created"] == "2026-10-26T22:28:06"
    assert meta["description"]["feature"] == "editor startup + load .unt"
    assert meta["analysis"]["packet_count"] == 0
