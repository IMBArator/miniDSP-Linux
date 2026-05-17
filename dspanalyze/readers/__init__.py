"""Capture file readers — produce RawPacket sequences from various file formats."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawPacket:
    """A single USB HID packet extracted from a capture file.

    Attributes:
        frame_number: Sequential packet index inside the capture, starting
            at 1 (matches Wireshark's ``frame.number``).
        timestamp: Capture-relative time in seconds (float). Resolution
            depends on the source format — pcapng is microsecond-precise.
        direction: ``"out"`` (host → device, endpoint 0x02) or ``"in"``
            (device → host, endpoint 0x81).
        endpoint: USB endpoint address (``0x02`` for OUT, ``0x81`` for IN).
        hid_data: Raw 64-byte HID report (zero-padded beyond the framed
            payload).
    """
    frame_number: int
    timestamp: float       # seconds from capture start
    direction: str         # "out" (host->device) or "in" (device->host)
    endpoint: int          # 0x02 or 0x81
    hid_data: bytes        # 64 raw bytes


def read_capture(filepath: str | Path) -> list[RawPacket]:
    """Read a capture file, dispatching to the format-specific reader by suffix.

    Files ending in ``.pcapng`` or ``.pcap`` are read via
    :func:`dspanalyze.readers.pcapng.read_pcapng` (which shells out to
    ``tshark``). Anything else — including ``.txt`` — is parsed as a
    Wireshark text export via
    :func:`dspanalyze.readers.wireshark_text.read_wireshark_text`.

    Args:
        filepath: Path to the capture file (``str`` or :class:`Path`).

    Returns:
        Ordered list of :class:`RawPacket` instances, one per HID report
        the underlying reader yields. Returns an empty list if the capture
        contains no HID packets.
    """
    filepath = Path(filepath)
    suffix = filepath.suffix.lower()

    if suffix in (".pcapng", ".pcap"):
        from dspanalyze.readers.pcapng import read_pcapng
        return read_pcapng(filepath)
    else:
        # Default: Wireshark text export (.txt or anything else)
        from dspanalyze.readers.wireshark_text import read_wireshark_text
        return read_wireshark_text(filepath)
