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

    # Generate metadata sidecar (uses unfiltered commands)
    if not args.no_meta:
        from dspanalyze.metadata import write_metadata
        write_metadata(args.file, commands)

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
                              decode=args.decode, filename=args.file)
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


def cmd_check(args: argparse.Namespace) -> None:
    """Run protocol assertions against a capture file."""
    from dspanalyze.check import ASSERTIONS, format_results, run_assertions

    if args.list_assertions:
        print("Available assertions:")
        for a in ASSERTIONS:
            print(f"  {a.name:<25s}  {a.description}  (files: {a.capture_glob})")
        return

    from dspanalyze.config import load_config
    from dspanalyze.decode import decode_packets
    from dspanalyze.readers import read_capture

    config = load_config()
    packets = read_capture(args.file)

    if not packets:
        print(f"No HID packets found in {args.file}", file=sys.stderr)
        sys.exit(1)

    commands = decode_packets(packets, config)
    results = run_assertions(commands, args.file, args.assertion)

    name = Path(args.file).stem
    print(f"Check: {name}")
    print(format_results(results, verbose=args.verbose))

    # Exit with non-zero if any assertion failed
    if any(not r.passed for r in results):
        sys.exit(1)


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
    p_analyze.add_argument("--no-meta", action="store_true",
                           help="Skip generating .meta.toml sidecar file")
    p_analyze.set_defaults(func=cmd_analyze)

    # --- check ---
    p_check = sub.add_parser("check", help="Run protocol assertions against a capture")
    p_check.add_argument("file", help="Path to capture file")
    p_check.add_argument("--assertion", default="all",
                         help="Run specific assertion (or 'all')")
    p_check.add_argument("--list", action="store_true", dest="list_assertions",
                         help="List available assertions")
    p_check.add_argument("--verbose", "-v", action="store_true",
                         help="Show passing assertions too")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    args.func(args)
