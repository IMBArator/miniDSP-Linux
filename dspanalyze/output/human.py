"""Human-readable terminal output format with header, table, and summary."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from dspanalyze.config import ProtocolConfig
from dspanalyze.decode import DecodedCommand


def format_human(
    commands: list[DecodedCommand],
    config: ProtocolConfig,
    *,
    summary: bool = False,
    decode: bool = False,
    filename: str = "",
) -> str:
    """Format decoded commands as a human-readable table with header and summary."""
    lines: list[str] = []

    # ── Header ──
    name = Path(filename).stem if filename else "capture"
    out_count = sum(1 for c in commands if c.direction == "out")
    in_count = sum(1 for c in commands if c.direction == "in")
    duration = _duration(commands)

    lines.append(f"=== miniDSP Capture Analysis ===")
    lines.append(f"File: {name}")
    lines.append(f"Duration: {duration:.1f}s | {len(commands)} HID packets ({out_count} OUT, {in_count} IN)")
    lines.append("")

    if not summary:
        # ── Packet table ──
        lines.append(f"{'#':>6s}  {'Time':>9s}  {'Dir':<3s}  {'Opcode':<8s}  {'Name':<18s}  {'Details'}")
        lines.append(f"{'─'*6}  {'─'*9}  {'─'*3}  {'─'*8}  {'─'*18}  {'─'*40}")

        for cmd in commands:
            pkt = cmd.frame.raw
            details = _format_details(cmd, decode)
            chk = "" if cmd.frame.checksum_valid else " [BAD CHK]"

            lines.append(
                f"{pkt.frame_number:>6d}  {pkt.timestamp:>9.3f}  "
                f"{cmd.direction.upper():<3s}  "
                f"0x{cmd.opcode:02x}      {cmd.opcode_name:<18s}  {details}{chk}"
            )

        lines.append("")

    # ── Summary table ──
    lines.append(f"=== Summary ===")

    by_opcode: dict[int, list[DecodedCommand]] = {}
    for cmd in commands:
        by_opcode.setdefault(cmd.opcode, []).append(cmd)

    lines.append(f"{'Opcode':<8s}  {'Name':<18s}  {'Count':>5s}  {'Verified':<8s}  {'Description'}")
    lines.append(f"{'─'*8}  {'─'*18}  {'─'*5}  {'─'*8}  {'─'*40}")

    for opcode in sorted(by_opcode.keys()):
        cmds = by_opcode[opcode]
        cmd0 = cmds[0]
        verified = "YES" if cmd0.verified else ("no" if cmd0.is_known else "UNKNOWN")
        lines.append(
            f"0x{opcode:02x}      {cmd0.opcode_name:<18s}  {len(cmds):>5d}  "
            f"{verified:<8s}  {cmd0.description}"
        )

    # ── Warnings ──
    unknowns = [c for c in commands if not c.is_known]
    bad_chk = [c for c in commands if not c.frame.checksum_valid]
    if unknowns or bad_chk:
        lines.append("")
        lines.append("=== Warnings ===")
        if unknowns:
            unknown_ops = sorted({f"0x{c.opcode:02x}" for c in unknowns})
            lines.append(f"  Unknown opcodes: {', '.join(unknown_ops)} ({len(unknowns)} packets)")
        if bad_chk:
            lines.append(f"  Checksum failures: {len(bad_chk)} packets")

    return "\n".join(lines)


def _duration(commands: list[DecodedCommand]) -> float:
    if not commands:
        return 0.0
    times = [c.frame.raw.timestamp for c in commands]
    return max(times) - min(times)


def _format_details(cmd: DecodedCommand, decode: bool) -> str:
    """Format field details for a single command."""
    if decode and cmd.human_fields:
        return ", ".join(f"{k}={v}" for k, v in cmd.human_fields.items())
    if not cmd.is_known and cmd.frame.payload:
        return f"[{cmd.frame.payload.hex()}]"
    if not cmd.verified and not cmd.is_known and cmd.frame.payload:
        return f"[{cmd.frame.payload.hex()}]"
    return ""
