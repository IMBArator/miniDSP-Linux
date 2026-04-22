#!/usr/bin/env python3
"""
the t.racks DSP 4x4 Mini — CLI control tool.

Usage:
    python -m minidsp dump            # Dump full DSP configuration as tables
    python -m minidsp levels          # Snapshot live levels (raw + dB)
    python -m minidsp levels --watch  # Continuous level monitoring
    python -m minidsp mute 1         # Mute input channel 1
    python -m minidsp unmute 1        # Unmute input channel 1
    python -m minidsp mute 1 2 3 4   # Mute all input channels
"""

from __future__ import annotations

import argparse
import csv
import logging
import signal as signal_mod
import sys
import time
from pathlib import Path

from .device import DSPmini


def cmd_dump(args: argparse.Namespace) -> None:
    """Read all DSP configuration parameters and print them as formatted tables."""
    from rich.console import Console
    from rich.table import Table
    from rich import box as rich_box
    from .protocol import (
        raw_to_db, freq_raw_to_hz, delay_samples_to_ms,
        gate_threshold_to_db, gate_time_to_ms,
        comp_threshold_to_db, comp_attack_to_ms, comp_release_to_ms,
        SLOPE_NAMES, PEQ_TYPE_NAMES, COMP_RATIO_NAMES,
        INPUT_CHANNEL_NAMES, OUTPUT_CHANNEL_NAMES,
        CHANNEL_NAMES, decode_link_groups, decode_routing_matrix,
        peq_raw_to_gain, peq_raw_to_q,
    )

    dsp = DSPmini()
    try:
        dsp.open()
    except Exception as e:
        print(f"Error: Could not open device: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        cfg = dsp.read_config()
    finally:
        dsp.close()

    if cfg is None:
        print("Error: Failed to read configuration", file=sys.stderr)
        sys.exit(1)

    console = Console()
    CH_IN  = INPUT_CHANNEL_NAMES
    CH_OUT = OUTPUT_CHANNEL_NAMES

    def db_fmt(raw: int) -> str:
        return f"{raw_to_db(raw):+.1f} dB"

    def yn(b: bool) -> str:
        return "Yes" if b else "No"

    def phase_fmt(b: bool) -> str:
        return "180°" if b else "0°"

    def link_fmt(ch: int) -> str:
        info = link_groups[ch]
        if info["role"] == "slave":
            m = info["master"]
            return f"→ {CHANNEL_NAMES[m]}" if m is not None else "slave"
        if info["role"] == "master":
            peers = [CHANNEL_NAMES[p] for p in info["linked_to"] if p != ch]
            return "↔ " + ", ".join(peers) if peers else "master"
        return "No"

    def freq_fmt(raw: int) -> str:
        return "Off" if raw == 0 else f"{freq_raw_to_hz(raw):.0f} Hz"

    def slope_fmt(s: int) -> str:
        return SLOPE_NAMES.get(s, f"0x{s:02x}")

    active_slot  = cfg.get("active_slot")
    preset_names = cfg.get("preset_names", [])

    # ── Preset list ─────────────────────────────────────────────────────
    # 0x29 reads 30 names for user presets U01–U30 (index 0 → U01, index 29 → U30).
    # F00 (slot 0 in 0x14 terms) has no 0x29 entry — shown as a static row.
    pt = Table(title="Presets", box=rich_box.SIMPLE_HEAD)
    pt.add_column("Slot", justify="right", min_width=4)
    pt.add_column("Label", min_width=4)
    pt.add_column("Name", min_width=16)
    pt.add_column("", min_width=1)  # active marker column
    # F00 — factory preset, not readable via 0x29
    f00_active = (active_slot == 0)
    pt.add_row("0", "F00", "—",
               "[bold green]◀ active[/bold green]" if f00_active else "",
               style="bold" if f00_active else "")
    # U01–U30: 0x29 index i → user preset U(i+1), slot (i+1) in 0x14 terms
    for i, pname in enumerate(preset_names):
        slot = i + 1  # 0x14 slot: 1=U01, 2=U02, …, 30=U30
        label = f"U{slot:02d}"
        is_active = (slot == active_slot)
        marker = "[bold green]◀ active[/bold green]" if is_active else ""
        pt.add_row(str(slot), label, pname or "—", marker,
                   style="bold" if is_active else "")
    console.print(pt)

    names    = cfg["names"]
    gains    = cfg["gains"]
    mutes    = cfg["mutes"]
    phases   = cfg["phases"]
    gates    = cfg["gates"]
    routings = cfg.get("routings", [0x01, 0x02, 0x04, 0x08])
    xovers   = cfg["crossovers"]
    comps    = cfg["compressors"]
    delays   = cfg["delays"]
    peqs     = cfg["peqs"]
    link_groups = decode_link_groups(cfg.get("link_flags", [0x01, 0x02, 0x04, 0x08,
                                                             0x01, 0x02, 0x04, 0x08]))
    routing_info = decode_routing_matrix(routings)

    # ── Table 1: Input channels (signal chain: Gain → Gate) ────────────
    t = Table(title="Input Channels", box=rich_box.SIMPLE_HEAD, show_header=True)
    t.add_column("Parameter", style="bold", min_width=14)
    for ch in CH_IN:
        t.add_column(ch, justify="right", min_width=10)

    def section_in(label: str) -> None:
        t.add_row(f"── {label}", *[""] * 4, style="dim")

    t.add_row("Name",  *[names[i] or CH_IN[i] for i in range(4)])
    t.add_row("Gain",  *[db_fmt(gains[i]) for i in range(4)])
    t.add_row("Mute",  *[yn(mutes[i]) for i in range(4)])
    t.add_row("Phase", *[phase_fmt(phases[i]) for i in range(4)])
    t.add_row("Link",  *[link_fmt(i) for i in range(4)])
    section_in("Noise Gate")
    t.add_row("Threshold", *[f"{gate_threshold_to_db(gates[i]['threshold']):.1f} dB" for i in range(4)])
    t.add_row("Attack",    *[f"{gate_time_to_ms(gates[i]['attack'])} ms"  for i in range(4)])
    t.add_row("Hold",      *[f"{gate_time_to_ms(gates[i]['hold'])} ms"    for i in range(4)])
    t.add_row("Release",   *[f"{gate_time_to_ms(gates[i]['release'])} ms" for i in range(4)])

    console.print(t)

    # ── Table 2: Output channels (signal chain: Gain → HP XO → PEQ → Comp → LP XO → Delay) ──
    t2 = Table(title="Output Channels", box=rich_box.SIMPLE_HEAD, show_header=True)
    t2.add_column("Parameter", style="bold", min_width=14)
    for ch in CH_OUT:
        t2.add_column(ch, justify="right", min_width=10)

    def section_out(label: str) -> None:
        t2.add_row(f"── {label}", *[""] * 4, style="dim")

    def routing_str(i: int) -> str:
        sources = routing_info[i]["sources"]
        return "+".join(sources) if sources else "None"

    t2.add_row("Name",    *[names[4 + i] or CH_OUT[i] for i in range(4)])
    t2.add_row("Routing", *[routing_str(i) for i in range(4)])
    t2.add_row("Gain",    *[db_fmt(gains[4 + i]) for i in range(4)])
    t2.add_row("Mute",  *[yn(mutes[4 + i]) for i in range(4)])
    t2.add_row("Phase", *[phase_fmt(phases[4 + i]) for i in range(4)])
    t2.add_row("Link",  *[link_fmt(4 + i) for i in range(4)])
    t2.add_row("Delay", *[f"{delay_samples_to_ms(delays[i]):.3f} ms" for i in range(4)])
    section_out("High-pass Crossover")
    t2.add_row("Frequency", *[freq_fmt(xovers[i]["hipass_freq"]) for i in range(4)])
    t2.add_row("Slope",     *[slope_fmt(xovers[i]["hipass_slope"]) for i in range(4)])
    section_out("Low-pass Crossover")
    t2.add_row("Frequency", *[freq_fmt(xovers[i]["lopass_freq"]) for i in range(4)])
    t2.add_row("Slope",     *[slope_fmt(xovers[i]["lopass_slope"]) for i in range(4)])
    section_out("Compressor")
    t2.add_row("Ratio",     *[COMP_RATIO_NAMES.get(comps[i]["ratio"], "?") for i in range(4)])
    t2.add_row("Threshold", *[f"{comp_threshold_to_db(comps[i]['threshold']):.1f} dB" for i in range(4)])
    t2.add_row("Knee",      *[f"{comps[i]['knee']} dB" for i in range(4)])
    t2.add_row("Attack",    *[f"{comp_attack_to_ms(comps[i]['attack'])} ms" for i in range(4)])
    t2.add_row("Release",   *[f"{comp_release_to_ms(comps[i]['release'])} ms" for i in range(4)])

    console.print(t2)

    # ── Tables 3–6: PEQ per output channel (7 bands each) ──────────────
    for i, ch_name in enumerate(CH_OUT):
        peq = peqs[i]
        bypass_all = peq["channel_bypass"]
        status_tag = "[dim][Bypassed][/dim]" if bypass_all else "[green][Active][/green]"
        tp = Table(title=f"{ch_name} PEQ  {status_tag}", box=rich_box.SIMPLE_HEAD)
        tp.add_column("Band",   justify="center", min_width=4)
        tp.add_column("Type",   min_width=11)
        tp.add_column("Freq",   justify="right",  min_width=8)
        tp.add_column("Gain",   justify="right",  min_width=8)
        tp.add_column("Q",      justify="right",  min_width=5)
        tp.add_column("Bypass", justify="center", min_width=6)
        for b_idx, band in enumerate(peq["bands"]):
            row_style = "dim" if band["bypass"] or bypass_all else ""
            tp.add_row(
                str(b_idx + 1),
                PEQ_TYPE_NAMES.get(band["type"], f"0x{band['type']:02x}"),
                f"{freq_raw_to_hz(band['freq']):.0f} Hz",
                f"{peq_raw_to_gain(band['gain']):+.1f} dB",
                f"{peq_raw_to_q(band['q']):.2f}",
                yn(band["bypass"]),
                style=row_style,
            )
        console.print(tp)


def cmd_levels(args: argparse.Namespace) -> None:
    """Poll device levels and display raw uint16 + dB for all 8 channels."""
    from rich.console import Console
    from rich.table import Table
    from rich import box as rich_box
    from .protocol import (
        level_uint16_to_dbu,
        INPUT_CHANNEL_NAMES, OUTPUT_CHANNEL_NAMES,
    )

    console = Console()
    ch_names = list(INPUT_CHANNEL_NAMES) + list(OUTPUT_CHANNEL_NAMES)

    csv_file = None
    csv_writer = None
    if args.csv:
        csv_path = Path(args.csv)
        csv_file = open(csv_path, "w", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["timestamp"] + [f"{n}_raw" for n in ch_names]
                            + [f"{n}_dB" for n in ch_names])

    count = args.count or 0
    interval = args.interval or 0.3
    watch = args.watch
    if watch:
        count = 0

    dsp = DSPmini()
    try:
        dsp.open()
    except Exception as e:
        print(f"Error: Could not open device: {e}", file=sys.stderr)
        sys.exit(1)

    running = True

    def _stop(sig, frame):
        nonlocal running
        running = False

    signal_mod.signal(signal_mod.SIGINT, _stop)

    try:
        n = 0
        while running:
            levels = dsp.poll_levels()
            if levels is None:
                print("  (timeout — no response)", file=sys.stderr)
                if not watch:
                    break
                time.sleep(interval)
                continue

            inputs = levels["inputs"]
            outputs = levels["outputs"]
            all_vals = inputs + outputs

            if csv_writer:
                ts = f"{time.time():.3f}"
                db_vals = [level_uint16_to_dbu(v) for v in all_vals]
                db_strs = [f"{v:.2f}" if v != float("-inf") else "-inf" for v in db_vals]
                csv_writer.writerow([ts] + all_vals + db_strs)
                csv_file.flush()

            if not args.csv_only:
                t = Table(box=rich_box.SIMPLE, show_header=True)
                t.add_column("Ch", style="bold", min_width=4)
                t.add_column("Raw", justify="right", min_width=5)
                t.add_column("dBu", justify="right", min_width=8)
                for name, val in zip(ch_names, all_vals):
                    db = level_uint16_to_dbu(val)
                    db_str = f"{db:+.1f}" if db != float("-inf") else " -inf"
                    t.add_row(name, str(val), db_str)
                console.print(t)

            n += 1
            if count and n >= count:
                break
            if not watch and count == 0:
                break
            time.sleep(interval)
    finally:
        dsp.close()
        if csv_file:
            csv_file.close()


def cmd_mute(args: argparse.Namespace) -> None:
    """Mute one or more input channels."""
    _do_mute(args.channels, mute=True)


def cmd_unmute(args: argparse.Namespace) -> None:
    """Unmute one or more input channels."""
    _do_mute(args.channels, mute=False)


def _do_mute(channels: list[int], mute: bool) -> None:
    action = "Mute" if mute else "Unmute"
    dsp = DSPmini()
    try:
        dsp.open()
    except Exception as e:
        print(f"Error: Could not open device: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        for ch in channels:
            if ch < 1 or ch > 4:
                print(f"Warning: channel {ch} out of range (1–4), skipping", file=sys.stderr)
                continue
            ok = dsp.mute(ch - 1, mute)  # convert 1-indexed to 0-indexed
            status = "OK" if ok else "FAILED (no ACK)"
            print(f"  {action} input ch{ch}: {status}")
    finally:
        dsp.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="minidsp",
        description="the t.racks DSP 4x4 Mini — USB HID control tool",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Increase verbosity (-v: info, -vv: debug)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # dump
    p_dump = sub.add_parser("dump", help="Dump all DSP configuration parameters as tables")
    p_dump.set_defaults(func=cmd_dump)

    # levels
    p_levels = sub.add_parser("levels",
                              help="Snapshot live level meter values (raw + dB)")
    p_levels.add_argument("-n", "--count", type=int, default=None,
                          help="Number of snapshots (default: 1)")
    p_levels.add_argument("-w", "--watch", action="store_true",
                          help="Continuous monitoring (Ctrl+C to stop)")
    p_levels.add_argument("-i", "--interval", type=float, default=None,
                          help="Poll interval in seconds (default: 0.3)")
    p_levels.add_argument("--csv", type=str, default=None,
                          help="Log all readings to CSV file")
    p_levels.add_argument("--csv-only", action="store_true",
                          help="Only write CSV, no console output")
    p_levels.set_defaults(func=cmd_levels)

    # mute
    p_mute = sub.add_parser("mute", help="Mute input channel(s)")
    p_mute.add_argument("channels", type=int, nargs="+", help="Channel numbers (1–4)")
    p_mute.set_defaults(func=cmd_mute)

    # unmute
    p_unmute = sub.add_parser("unmute", help="Unmute input channel(s)")
    p_unmute.add_argument("channels", type=int, nargs="+", help="Channel numbers (1–4)")
    p_unmute.set_defaults(func=cmd_unmute)

    args = parser.parse_args()
    level = (logging.DEBUG if args.verbose >= 2
             else logging.INFO if args.verbose >= 1
             else logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    args.func(args)


if __name__ == "__main__":
    main()
