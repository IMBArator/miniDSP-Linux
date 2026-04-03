"""Human-readable terminal output format (Phase 2 — basic implementation)."""

from __future__ import annotations

from dspanalyze.config import ProtocolConfig
from dspanalyze.decode import DecodedCommand


def format_human(
    commands: list[DecodedCommand],
    config: ProtocolConfig,
    *,
    summary: bool = False,
    decode: bool = False,
) -> str:
    """Format decoded commands as a human-readable table."""
    lines: list[str] = []
    lines.append(f"{'#':>5s}  {'Time':>8s}  {'Dir':<3s}  {'Opcode':<8s}  {'Name':<20s}  Decoded")
    lines.append(f"{'─'*5}  {'─'*8}  {'─'*3}  {'─'*8}  {'─'*20}  {'─'*40}")

    for cmd in commands:
        pkt = cmd.frame.raw
        decoded = ""
        if decode and cmd.human_fields:
            decoded = ", ".join(f"{k}={v}" for k, v in cmd.human_fields.items())
        elif not cmd.is_known and cmd.frame.payload:
            decoded = f"[{cmd.frame.payload.hex()}]"

        lines.append(
            f"{pkt.frame_number:>5d}  {pkt.timestamp:>8.3f}  "
            f"{cmd.direction.upper():<3s}  "
            f"0x{cmd.opcode:02x}      {cmd.opcode_name:<20s}  {decoded}"
        )

    return "\n".join(lines)
