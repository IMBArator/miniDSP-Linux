"""Raw hex dump output format — every byte, minimal processing."""

from __future__ import annotations

from dspanalyze.decode import DecodedCommand


def format_raw(commands: list[DecodedCommand]) -> str:
    """Render decoded commands as one line of raw hex per packet.

    Each output line has fixed-width fields suitable for piping into ``less``
    or ``grep``:

    - Frame number, right-aligned to 5 characters.
    - Timestamp in seconds, right-aligned to 8 characters with 3 decimals
      (millisecond precision).
    - Direction (``OUT`` or ``IN``), left-aligned to 3 characters.
    - The full 64-byte HID report as lowercase hex, no separators.

    Args:
        commands: Decoded commands to render, in capture order.

    Returns:
        Newline-joined string with one line per command. Returns an empty
        string when ``commands`` is empty. No trailing newline.
    """
    lines: list[str] = []
    for cmd in commands:
        pkt = cmd.frame.raw
        hex_data = pkt.hid_data.hex()
        lines.append(
            f"{pkt.frame_number:>5d} {pkt.timestamp:>8.3f} "
            f"{cmd.direction.upper():<3s} {hex_data}"
        )
    return "\n".join(lines)
