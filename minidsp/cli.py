#!/usr/bin/env python3
"""
T.racks DSPmini 4x4 — CLI control tool.

Usage:
    python -m minidsp mute 1         # Mute input channel 1
    python -m minidsp unmute 1        # Unmute input channel 1
    python -m minidsp mute 1 2 3 4   # Mute all input channels
    python -m minidsp --gui           # Launch GUI
"""

from __future__ import annotations

import argparse
import sys

from .device import DSPmini


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
        description="T.racks DSPmini 4x4 — USB HID control tool",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # mute
    p_mute = sub.add_parser("mute", help="Mute input channel(s)")
    p_mute.add_argument("channels", type=int, nargs="+", help="Channel numbers (1–4)")
    p_mute.set_defaults(func=cmd_mute)

    # unmute
    p_unmute = sub.add_parser("unmute", help="Unmute input channel(s)")
    p_unmute.add_argument("channels", type=int, nargs="+", help="Channel numbers (1–4)")
    p_unmute.set_defaults(func=cmd_unmute)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
