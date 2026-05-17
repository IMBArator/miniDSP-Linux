"""CLI entry point for dspanalyze — USB HID protocol analysis tool.

Subcommands (see :func:`main` for the argparse setup):

- ``analyze`` — decode a capture and emit human/Claude/raw output.
- ``check`` — run protocol assertions against a capture.
- ``capture`` — record USB traffic via tshark (Linux/Windows).
- ``diff-config`` — compare repeated config-page reads inside one capture.
- ``list-captures`` — print metadata summaries for a directory of captures.
- ``extract-defaults`` — stitch F00 preset pages into a TOML defaults file.
- ``calibrate`` — manage level-meter calibration (capture/show/apply/reset).

Most subcommands exit with status 1 on missing input or fatal errors so
they are safe to wire into CI scripts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_analyze(args: argparse.Namespace) -> None:
    """Decode a capture, write its sidecar metadata, and emit a formatted dump.

    Reads ``args.file`` (``.pcapng`` or Wireshark text export), decodes every
    frame using ``protocol_config.toml``, regenerates the ``.meta.toml``
    sidecar (unless ``--no-meta``), applies opcode include/exclude filters,
    and renders the result via the chosen formatter.

    Args:
        args: Parsed CLI arguments with attributes:

            - ``file`` (str): capture path.
            - ``format`` (str): ``"claude"``, ``"human"``, or ``"raw"``.
            - ``output`` (str | None): destination file; ``None`` prints to stdout.
            - ``filter`` (str | None): comma-separated hex opcodes to include.
            - ``exclude`` (str | None): comma-separated hex opcodes to drop.
            - ``summary`` (bool): emit summary-only output.
            - ``decode`` (bool): include human-readable field values.
            - ``no_meta`` (bool): skip writing the ``.meta.toml`` sidecar.

    Side effects:
        Writes to ``args.output`` or stdout, and (unless ``--no-meta``)
        writes/updates ``<capture>.meta.toml``. Calls ``sys.exit(1)`` when
        the capture is empty or the requested format is unknown.
    """
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
    """Run protocol assertions against a capture and print pass/fail results.

    When ``--list`` is set, prints every registered assertion name with its
    description and capture-glob filter and returns without opening the file.
    Otherwise loads the capture, decodes it, runs every assertion whose name
    matches ``--assertion`` (or all when ``"all"``) and whose ``capture_glob``
    matches the filename, then prints a formatted result block.

    Args:
        args: Parsed CLI arguments with attributes:

            - ``file`` (str): capture path.
            - ``assertion`` (str): assertion name or ``"all"``.
            - ``list_assertions`` (bool): list-only mode (``--list``).
            - ``verbose`` (bool): also print passing assertions.

    Side effects:
        Prints to stdout. Calls ``sys.exit(1)`` when the capture is empty
        or any assertion fails (so the command is CI-friendly).
    """
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
    """Entry point for the ``dspanalyze`` CLI."""
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

    # --- extract-defaults ---
    p_def = sub.add_parser(
        "extract-defaults",
        help="Extract factory default parameters from a preset-load capture",
    )
    p_def.add_argument("file", help="Path to capture (typically the F00 load capture)")
    p_def.add_argument("--output", "-o", default="minidsp/factory_defaults.toml",
                       help="TOML output path (default: minidsp/factory_defaults.toml)")
    p_def.set_defaults(func=cmd_extract_defaults)

    # --- calibrate ---
    p_cal = sub.add_parser("calibrate",
                           help="Level meter calibration tool")
    cal_sub = p_cal.add_subparsers(dest="calibrate_action", required=True)

    p_cal_capture = cal_sub.add_parser("capture",
                                       help="Capture raw levels at a known analog level")
    p_cal_capture.add_argument("dbu", type=float,
                               help="Known analog signal level in dBu (e.g. 0, -10, -30)")
    p_cal_capture.add_argument("-c", "--channel", type=int, default=0,
                               help="Channel index 0-7 (default: 0=InA)")
    p_cal_capture.add_argument("-s", "--samples", type=int, default=None,
                               help="Number of samples (default: 20)")
    p_cal_capture.set_defaults(func=cmd_calibrate)

    cal_sub.add_parser("show",
                       help="Display stored calibration points and computed REF_LEVEL") \
        .set_defaults(func=cmd_calibrate)

    cal_sub.add_parser("apply",
                       help="Compute best-fit REF_LEVEL and write to calibration.toml") \
        .set_defaults(func=cmd_calibrate)

    cal_sub.add_parser("reset",
                       help="Revert calibration.toml to factory defaults") \
        .set_defaults(func=cmd_calibrate)

    args = parser.parse_args()
    args.func(args)


def cmd_list_captures(args: argparse.Namespace) -> None:
    """List capture files in a directory with their ``.meta.toml`` summaries.

    Scans ``args.directory`` for ``.txt``, ``.pcapng``, and ``.pcap`` files,
    sorts them by filename, and prints — for each — the packet count,
    duration, feature description, observed opcodes, and an ``[HAS UNKNOWNS]``
    marker when the sidecar reports any unrecognized opcodes. Captures
    without a sidecar are listed with a hint to run ``analyze`` first.

    Args:
        args: Parsed CLI arguments with attribute ``directory`` (str, path to
            scan; defaults to ``analysis/usb_captures``).

    Side effects:
        Prints to stdout. Calls ``sys.exit(1)`` when ``directory`` does not
        exist or is not a directory.
    """
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
    """Compare repeated config-page reads inside a single capture.

    When a capture contains multiple full reads of the 9 config pages
    (e.g. before/after a preset load), this command extracts each read and
    reports which bytes changed between them — useful for isolating the
    offsets that store a newly-touched parameter.

    Args:
        args: Parsed CLI arguments with attribute ``file`` (str, capture path
            that contains at least two complete page-0–page-8 sequences).

    Side effects:
        Prints the diff report to stdout. Calls ``sys.exit(1)`` when the
        capture is empty.
    """
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
    """Capture USB traffic from the DSP device using tshark.

    Two modes:

    - ``--detect``: print the detected device's VID/PID, system, USB bus
      and (on Linux) USB device address, then list every tshark capture
      interface and return without recording.
    - Otherwise: invoke :func:`dspanalyze.capture.run_capture` to record a
      ``.pcapng`` into ``--output-dir`` (auto-named from description), with
      an optional time limit.

    Platform notes:
        On Linux the USB bus and device address are auto-discovered from
        sysfs. On Windows the user must pass ``--device-address`` because
        USBPcap filters by address, not VID/PID. ``find_tshark()`` raises
        if tshark is not on ``$PATH``.

    Args:
        args: Parsed CLI arguments with attributes ``output_dir`` (str),
            ``duration`` (int | None, seconds; ``None`` = until Ctrl+C),
            ``interface`` (str | None, auto-detected if absent),
            ``description`` (str), ``notes`` (str),
            ``device_address`` (int | None, required on Windows),
            and ``detect`` (bool).

    Side effects:
        Prints status to stdout. Writes a ``.pcapng`` capture and its
        ``.meta.toml`` sidecar under ``output_dir`` (capture mode only).
    """
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


def cmd_extract_defaults(args: argparse.Namespace) -> None:
    """Stitch the F00 factory-preset config pages from a capture into a TOML file.

    Reads ``args.file`` (typically a capture of an F00 preset load), uses
    :func:`dspanalyze.extract_defaults.extract_defaults` to reconstruct the
    9-page config block, and writes a TOML representation suitable for
    bundling as ``minidsp/factory_defaults.toml``. The parent directory of
    the output path is created if missing.

    Args:
        args: Parsed CLI arguments with attributes ``file`` (str, capture
            path) and ``output`` (str, TOML destination).

    Side effects:
        Creates ``Path(args.output).parent`` and writes the TOML. Prints
        the resulting path on success. Calls ``sys.exit(1)`` and prints
        the error message when
        :class:`~dspanalyze.extract_defaults.ExtractDefaultsError` is raised
        (e.g. capture is missing pages).
    """
    from dspanalyze.extract_defaults import ExtractDefaultsError, extract_defaults

    capture = Path(args.file)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        extract_defaults(capture, output)
    except ExtractDefaultsError as e:
        print(f"extract-defaults: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Wrote {output}")


def cmd_calibrate(args: argparse.Namespace) -> None:
    """Dispatch the ``calibrate`` subcommand to one of four action handlers.

    Routes ``args.calibrate_action`` to a handler in
    :mod:`dspanalyze.calibrate`:

    - ``capture`` — record ``--samples`` level readings on ``--channel`` at
      the known analog level ``dbu`` and append a measurement point.
    - ``show`` — print all stored points and the best-fit ``REF_LEVEL``.
    - ``apply`` — compute the best-fit ``REF_LEVEL`` (weighted geometric
      mean per :func:`minidsp.protocol.calibrate_compute_ref`) and write it
      to the package-bundled ``calibration.toml``.
    - ``reset`` — revert ``calibration.toml`` to the factory default.

    Args:
        args: Parsed CLI arguments with attribute ``calibrate_action`` (str,
            one of the four actions). For ``capture`` also ``dbu`` (float),
            ``channel`` (int 0–7), and ``samples`` (int | None — falls back
            to :data:`dspanalyze.calibrate.DEFAULT_SAMPLES`).

    Side effects:
        Performs disk I/O on ``calibration.toml`` and (for ``capture``) live
        device I/O. Calls ``sys.exit(1)`` for unknown actions.
    """
    from dspanalyze.calibrate import (
        DEFAULT_SAMPLES,
        cmd_calibrate_apply,
        cmd_calibrate_capture,
        cmd_calibrate_reset,
        cmd_calibrate_show,
    )

    action = args.calibrate_action
    if action == "capture":
        n = args.samples or DEFAULT_SAMPLES
        cmd_calibrate_capture(dbu=args.dbu, channel=args.channel, n_samples=n)
    elif action == "show":
        cmd_calibrate_show()
    elif action == "apply":
        cmd_calibrate_apply()
    elif action == "reset":
        cmd_calibrate_reset()
    else:
        print(f"Unknown calibrate action: {action}", file=sys.stderr)
        sys.exit(1)
