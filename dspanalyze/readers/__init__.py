"""Capture file readers — produce RawPacket sequences from various file formats."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawPacket:
    """A single USB HID packet extracted from a capture file."""
    frame_number: int
    timestamp: float       # seconds from capture start
    direction: str         # "out" (host->device) or "in" (device->host)
    endpoint: int          # 0x02 or 0x81
    hid_data: bytes        # 64 raw bytes


def read_capture(filepath: str | Path) -> list[RawPacket]:
    """Auto-detect file format and read capture into RawPacket list."""
    filepath = Path(filepath)
    suffix = filepath.suffix.lower()

    if suffix in (".pcapng", ".pcap"):
        from dspanalyze.readers.pcapng import read_pcapng
        return read_pcapng(filepath)
    else:
        # Default: Wireshark text export (.txt or anything else)
        from dspanalyze.readers.wireshark_text import read_wireshark_text
        return read_wireshark_text(filepath)
