"""Claude-optimized output format — compact, structured, context-efficient.

Design principles:
- Collapse repetitive poll/level cycles into summary lines
- Always highlight unknown opcodes prominently
- Include opcode frequency histogram in header
- Mask noise by default (instant bytes, footer, padding)
- Show raw hex only for unknown/unverified commands
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from dspanalyze.config import ProtocolConfig
from dspanalyze.decode import DecodedCommand


def format_claude(
    commands: list[DecodedCommand],
    config: ProtocolConfig,
    *,
    summary: bool = False,
    decode: bool = False,
    mask_noise: bool = True,
    filename: str = "",
) -> str:
    """Format decoded commands for Claude consumption."""
    lines: list[str] = []

    # ── Header ──
    name = Path(filename).stem if filename else "capture"
    out_count = sum(1 for c in commands if c.direction == "out")
    in_count = sum(1 for c in commands if c.direction == "in")
    duration = _duration(commands)

    lines.append(f"## Capture: {name}")
    lines.append(f"Packets: {len(commands)} HID ({out_count} OUT, {in_count} IN) | Duration: {duration:.1f}s")

    # Opcode histogram
    opcode_counts = Counter(
        f"0x{c.opcode:02x}" if c.opcode != 0x01 else "ACK"
        for c in commands
    )
    hist = " ".join(f"{op}({n})" for op, n in opcode_counts.most_common())
    lines.append(f"Opcodes: {hist}")

    # Unknown opcodes warning
    unknowns = [c for c in commands if not c.is_known]
    unverified = {c.opcode for c in commands if c.is_known and not c.verified}

    if unknowns:
        unknown_ops = sorted({f"0x{c.opcode:02x}" for c in unknowns})
        lines.append(f"**UNKNOWN OPCODES: {', '.join(unknown_ops)}**")
    if unverified:
        unv_ops = sorted(f"0x{op:02x}" for op in unverified)
        lines.append(f"Unverified opcodes present: {', '.join(unv_ops)}")

    bad_chk = [c for c in commands if not c.frame.checksum_valid]
    if bad_chk:
        lines.append(f"**CHECKSUM FAILURES: {len(bad_chk)} packets**")

    lines.append("")

    if summary:
        lines.extend(_format_summary(commands, config, decode))
    else:
        lines.extend(_format_sequence(commands, config, decode, mask_noise))

    # ── Unknown opcode detail ──
    if unknowns:
        lines.append("")
        lines.append("### Unknown Opcode Detail")
        for cmd in unknowns:
            pkt = cmd.frame.raw
            payload_hex = cmd.frame.payload.hex() if cmd.frame.payload else ""
            lines.append(
                f"  #{pkt.frame_number:<5d} {pkt.timestamp:>8.3f}s "
                f"{cmd.direction.upper():<3s}  0x{cmd.opcode:02x}  "
                f"len={cmd.frame.length}  payload={payload_hex}"
            )

    return "\n".join(lines)


def _duration(commands: list[DecodedCommand]) -> float:
    """Calculate capture duration from first to last packet timestamp."""
    if not commands:
        return 0.0
    times = [c.frame.raw.timestamp for c in commands]
    return max(times) - min(times)


def _format_sequence(
    commands: list[DecodedCommand],
    config: ProtocolConfig,
    decode: bool,
    mask_noise: bool,
) -> list[str]:
    """Format the full packet sequence with poll cycles collapsed."""
    lines = ["### Sequence"]
    i = 0

    while i < len(commands):
        cmd = commands[i]

        # Collapse consecutive poll/level cycles
        if cmd.opcode == 0x40:
            poll_start = i
            while i < len(commands) and commands[i].opcode == 0x40:
                i += 1
            count = i - poll_start
            t_start = commands[poll_start].frame.raw.timestamp
            t_end = commands[i - 1].frame.raw.timestamp

            if count > 2:
                lines.append(
                    f"  [{count}x poll/level cycle, "
                    f"{t_start:.3f}s-{t_end:.3f}s]"
                )
            else:
                # Show individually if only 1-2
                for j in range(poll_start, i):
                    lines.append(_format_single(commands[j], config, decode, mask_noise))
            continue

        # Collapse consecutive ACKs if preceded by same opcode type
        lines.append(_format_single(cmd, config, decode, mask_noise))
        i += 1

    return lines


def _format_single(
    cmd: DecodedCommand,
    config: ProtocolConfig,
    decode: bool,
    mask_noise: bool,
) -> str:
    """Format a single decoded command as one line."""
    pkt = cmd.frame.raw
    direction = cmd.direction.upper()

    parts = [
        f"  #{pkt.frame_number:<5d}",
        f"{pkt.timestamp:>8.3f}s",
        f"{direction:<3s}",
        f"0x{cmd.opcode:02x}",
        cmd.opcode_name,
    ]

    if decode and cmd.human_fields:
        field_strs = [f"{k}={v}" for k, v in cmd.human_fields.items()]
        parts.append(": " + ", ".join(field_strs))
    elif not cmd.is_known:
        # Always show raw hex for unknown commands
        payload_hex = cmd.frame.payload.hex() if cmd.frame.payload else ""
        parts.append(f"  [{payload_hex}]")
    elif not cmd.verified and cmd.frame.payload:
        # Show hex for unverified commands too
        payload_hex = cmd.frame.payload.hex() if cmd.frame.payload else ""
        parts.append(f"  [{payload_hex}]")

    return " ".join(parts)


def _format_summary(
    commands: list[DecodedCommand],
    config: ProtocolConfig,
    decode: bool,
) -> list[str]:
    """Format summary statistics only."""
    lines = ["### Summary"]

    # Group by opcode
    by_opcode: dict[int, list[DecodedCommand]] = {}
    for cmd in commands:
        by_opcode.setdefault(cmd.opcode, []).append(cmd)

    lines.append(f"{'Opcode':<8s} {'Name':<20s} {'Count':>5s}  {'Verified':<8s}  Notes")
    lines.append(f"{'─'*8} {'─'*20} {'─'*5}  {'─'*8}  {'─'*30}")

    for opcode in sorted(by_opcode.keys()):
        cmds = by_opcode[opcode]
        cmd0 = cmds[0]
        verified = "YES" if cmd0.verified else ("no" if cmd0.is_known else "UNKNOWN")

        notes = ""
        if decode and cmd0.is_known:
            notes = _summarize_fields(cmds, config)

        lines.append(
            f"0x{opcode:02x}     {cmd0.opcode_name:<20s} {len(cmds):>5d}  "
            f"{verified:<8s}  {notes}"
        )

    return lines


def _summarize_fields(cmds: list[DecodedCommand], config: ProtocolConfig) -> str:
    """Generate a brief summary of field values across a group of commands."""
    if not cmds or not cmds[0].human_fields:
        return ""

    # For gain commands, show the range
    if cmds[0].opcode_name == "gain":
        channels = sorted({c.human_fields.get("channel", "?") for c in cmds if c.human_fields})
        values = [c.fields.get("value", 0) for c in cmds if "value" in c.fields]
        if values and isinstance(values[0], int):
            from dspanalyze.config import gain_raw_to_db
            dbs = [gain_raw_to_db(v) for v in values]
            return f"ch={','.join(channels)} range={min(dbs):.1f}..{max(dbs):.1f} dB"
        return f"ch={','.join(channels)}"

    if cmds[0].opcode_name == "mute":
        channels = sorted({c.human_fields.get("channel", "?") for c in cmds if c.human_fields})
        states = sorted({c.human_fields.get("state", "?") for c in cmds if c.human_fields})
        return f"ch={','.join(channels)} states={','.join(states)}"

    if cmds[0].opcode_name == "read_name":
        return f"{len(cmds)} slots"

    if cmds[0].opcode_name == "read_config":
        pages = sorted({c.fields.get("page", "?") for c in cmds if "page" in c.fields})
        return f"pages {min(pages)}-{max(pages)}" if pages else ""

    return ""
