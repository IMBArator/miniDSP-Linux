"""Raw hex dump output format — every byte, minimal processing."""

from __future__ import annotations

from dspanalyze.decode import DecodedCommand


def format_raw(commands: list[DecodedCommand]) -> str:
    """Format decoded commands as raw hex lines."""
    lines: list[str] = []
    for cmd in commands:
        pkt = cmd.frame.raw
        hex_data = pkt.hid_data.hex()
        lines.append(
            f"{pkt.frame_number:>5d} {pkt.timestamp:>8.3f} "
            f"{cmd.direction.upper():<3s} {hex_data}"
        )
    return "\n".join(lines)
