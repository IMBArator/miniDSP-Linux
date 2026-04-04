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

    # --- capture ---
    p_capture = sub.add_parser("capture", help="Capture USB traffic via tshark")
    p_capture.add_argument("--output-dir", default="analysis/usb_captures",
                           help="Output directory (default: analysis/usb_captures)")
    p_capture.add_argument("--duration", type=int,
                           help="Capture duration in seconds (default: until Ctrl+C)")
    p_capture.add_argument("--interface",
                           help="tshark capture interface (auto-detected if omitted)")
    p_capture.add_argument("--description", "-d", default="",
                           help="What feature is being captured")
    p_capture.add_argument("--notes", "-n", default="",
                           help="Additional notes about the capture")
    p_capture.add_argument("--device-address", type=int,
                           help="USB device address for filtering (auto-detected on Linux, required on Windows)")
    p_capture.add_argument("--detect", action="store_true",
                           help="Only detect device and list interfaces, don't capture")
    p_capture.set_defaults(func=cmd_capture)

    # --- diff-config ---
    p_diff = sub.add_parser("diff-config",
                            help="Compare config reads within a capture to find changed bytes")
    p_diff.add_argument("file", help="Path to capture file with multiple config reads")
    p_diff.set_defaults(func=cmd_diff_config)

    # --- list-captures ---
    p_list = sub.add_parser("list-captures", help="List captures with metadata summaries")
    p_list.add_argument("directory", nargs="?", default="analysis/usb_captures",
                        help="Directory to scan (default: analysis/usb_captures)")
    p_list.set_defaults(func=cmd_list_captures)

    args = parser.parse_args()
    args.func(args)


def cmd_list_captures(args: argparse.Namespace) -> None:
    """List capture files with metadata summaries."""
    import tomllib

    from dspanalyze.metadata import meta_path_for

    capture_dir = Path(args.directory)
    if not capture_dir.is_dir():
        print(f"Not a directory: {capture_dir}", file=sys.stderr)
        sys.exit(1)

    # Find capture files
    captures = sorted(
        list(capture_dir.glob("*.txt")) + list(capture_dir.glob("*.pcapng")) + list(capture_dir.glob("*.pcap")),
        key=lambda p: p.name,
    )

    if not captures:
        print(f"No capture files found in {capture_dir}")
        return

    print(f"Captures in {capture_dir} ({len(captures)} files):\n")

    for cap in captures:
        meta_file = meta_path_for(cap)
        if meta_file.exists():
            with open(meta_file, "rb") as f:
                meta = tomllib.load(f)
            analysis = meta.get("analysis", {})
            desc = meta.get("description", {})
            pkts = analysis.get("packet_count", "?")
            dur = analysis.get("duration_seconds", "?")
            feature = desc.get("feature", "")
            unknown = " [HAS UNKNOWNS]" if analysis.get("has_unknown_opcodes") else ""
            opcodes = ", ".join(analysis.get("opcodes_seen", []))
            print(f"  {cap.name}")
            print(f"    {pkts} packets, {dur}s{unknown}")
            if feature:
                print(f"    Feature: {feature}")
            if opcodes:
                print(f"    Opcodes: {opcodes}")
        else:
            print(f"  {cap.name}")
            print(f"    (no metadata — run 'dspanalyze analyze' to generate)")
        print()


def cmd_diff_config(args: argparse.Namespace) -> None:
    """Compare config page reads within a capture."""
    from dspanalyze.config import load_config
    from dspanalyze.decode import decode_packets
    from dspanalyze.diff_config import diff_config_reads, extract_config_reads
    from dspanalyze.readers import read_capture

    config = load_config()
    packets = read_capture(args.file)

    if not packets:
        print(f"No HID packets found in {args.file}", file=sys.stderr)
        sys.exit(1)

    commands = decode_packets(packets, config)
    reads = extract_config_reads(commands)
    print(diff_config_reads(reads))


def cmd_capture(args: argparse.Namespace) -> None:
    """Capture USB traffic from the DSP device."""
    from dspanalyze.capture import (
        _find_linux_device_address,
        detect_device,
        find_tshark,
        list_interfaces,
        run_capture,
    )

    tshark = find_tshark()

    if args.detect:
        device = detect_device()
        if device:
            print(f"Device found: VID=0x{device['vid']:04x} PID=0x{device['pid']:04x} ({device['system']})")
            if "bus" in device:
                print(f"  USB bus: {device['bus']}")
            # Show device address on Linux (useful for --device-address override)
            if device["system"] == "Linux":
                dev_addr = _find_linux_device_address()
                if dev_addr is not None:
                    print(f"  Device address: {dev_addr}")
        else:
            print("Device not found (VID=0x0168 PID=0x0821)")

        print("\nAvailable capture interfaces:")
        for iface in list_interfaces(tshark):
            print(f"  {iface['index']}. {iface['name']}"
                  + (f" ({iface['description']})" if iface['description'] else ""))
        return

    output_path = run_capture(
        output_dir=Path(args.output_dir),
        description=args.description,
        notes=args.notes,
        duration=args.duration,
        interface=args.interface,
        device_address=args.device_address,
    )
