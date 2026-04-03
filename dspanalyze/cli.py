"""CLI entry point for dspanalyze — USB HID protocol analysis tool."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_analyze(args: argparse.Namespace) -> None:
    """Decode and display capture data."""
    from dspanalyze.config import load_config
    from dspanalyze.decode import decode_packets
    from dspanalyze.readers import read_capture

    config = load_config()
    packets = read_capture(args.file)

    if not packets:
        print(f"No HID packets found in {args.file}", file=sys.stderr)
        sys.exit(1)

    commands = decode_packets(packets, config)

    # Apply opcode filters
    if args.filter:
        opcodes = {int(o, 16) for o in args.filter.split(",")}
        commands = [c for c in commands if c.opcode in opcodes]
    if args.exclude:
        opcodes = {int(o, 16) for o in args.exclude.split(",")}
        commands = [c for c in commands if c.opcode not in opcodes]

    # Select formatter
    if args.format == "claude":
        from dspanalyze.output.claude import format_claude
        output = format_claude(commands, config, summary=args.summary,
                               decode=args.decode, mask_noise=True,
                               filename=args.file)
    elif args.format == "human":
        from dspanalyze.output.human import format_human
        output = format_human(commands, config, summary=args.summary,
                              decode=args.decode)
    elif args.format == "raw":
        from dspanalyze.output.raw import format_raw
        output = format_raw(commands)
    else:
        print(f"Unknown format: {args.format}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        Path(args.output).write_text(output)
        print(f"Written to {args.output}")
    else:
        print(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dspanalyze",
        description="USB HID protocol analysis for the t.racks DSP 4x4 Mini",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- analyze ---
    p_analyze = sub.add_parser("analyze", help="Decode and display capture data")
    p_analyze.add_argument("file", help="Path to .pcapng or Wireshark .txt export")
    p_analyze.add_argument("--format", choices=["claude", "human", "raw"],
                           default="claude", help="Output format (default: claude)")
    p_analyze.add_argument("--output", "-o", help="Write output to file")
    p_analyze.add_argument("--filter", help="Only show opcodes (comma-sep hex, e.g. 0x34,0x35)")
    p_analyze.add_argument("--exclude", help="Exclude opcodes (comma-sep hex, e.g. 0x40)")
    p_analyze.add_argument("--summary", action="store_true",
                           help="Show only summary statistics")
    p_analyze.add_argument("--decode", action="store_true",
                           help="Show human-readable field values")
    p_analyze.set_defaults(func=cmd_analyze)

    args = parser.parse_args()
    args.func(args)
