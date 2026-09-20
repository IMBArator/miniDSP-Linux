"""Level meter calibration tool for the analysis toolkit.

Reads and writes ``minidsp/calibration.toml`` which is shipped as a package
resource with the library.  The calibration file stores:

- ``ref_level24`` — the calibrated 0 dBu reference in 24-bit level units,
  used by ``level24_to_dbu()`` / ``level_uint16_to_dbu()``
- ``ref_level`` — the same reference in legacy uint16 units (÷ 256), kept
  for readability and for older readers of the file
- ``[[points]]`` — measured anchor points (dbu, mean_level24, …); points
  written before the 24-bit change carry ``mean_uint16`` instead and are
  still accepted

Usage::

    dspanalyze calibrate capture 0           # capture at 0 dBu
    dspanalyze calibrate capture -30         # capture at -30 dBu
    dspanalyze calibrate show                # display all points + residuals
    dspanalyze calibrate apply               # compute best-fit and write ref_level
    dspanalyze calibrate reset               # revert to factory default
"""

from __future__ import annotations

import importlib.resources
import logging
import math
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

CALIBRATION_FILENAME = "calibration.toml"
DEFAULT_SAMPLES = 20


def _calibration_file_path() -> Path:
    """Return the path to ``minidsp/calibration.toml`` on disk.

    Uses importlib.resources to locate the package directory regardless
    of whether it is an editable install or a wheel.
    """
    ref = importlib.resources.files("minidsp").joinpath(CALIBRATION_FILENAME)
    with importlib.resources.as_file(ref) as p:
        return p


def calibrate_load() -> dict:
    """Load calibration TOML from the minidsp package directory."""
    import tomllib
    path = _calibration_file_path()
    if path.exists():
        with open(path, "rb") as f:
            return tomllib.load(f)
    return {}


def calibrate_save(data: dict) -> None:
    """Write calibration TOML back to the minidsp package directory."""
    import tomli_w
    path = _calibration_file_path()
    with open(path, "wb") as f:
        tomli_w.dump(data, f)
    log.info("Calibration saved to %s", path)


def _stored_ref24(cal: dict) -> float | None:
    """Return the file's reference in 24-bit units (``ref_level24``, or the
    legacy ``ref_level`` × 256), or ``None`` if neither is present."""
    from minidsp.protocol import LEVEL24_PER_UINT16
    if cal.get("ref_level24") is not None:
        return float(cal["ref_level24"])
    if cal.get("ref_level") is not None:
        return float(cal["ref_level"]) * LEVEL24_PER_UINT16
    return None


def _fmt_ref(ref24: float) -> str:
    """Format a 24-bit reference with its uint16 equivalent."""
    from minidsp.protocol import LEVEL24_PER_UINT16
    return f"{ref24:.1f} (level24) = {ref24 / LEVEL24_PER_UINT16:.2f} (uint16)"


def cmd_calibrate_show() -> None:
    """Display stored calibration points and the computed reference."""
    from rich.console import Console
    from rich.table import Table
    from rich import box as rich_box
    from minidsp.protocol import (
        LEVEL_REF_LEVEL24_FACTORY,
        LEVEL24_PER_UINT16,
        calibrate_compute_ref,
        _point_level24,
    )

    console = Console()
    cal = calibrate_load()
    points = cal.get("points", [])
    ref = _stored_ref24(cal)
    path = _calibration_file_path()

    console.print(f"\n[bold]Calibration file:[/bold] {path}")
    if ref is not None:
        console.print(f"[bold]Current reference (0 dBu):[/bold] {_fmt_ref(ref)}")
    else:
        console.print(f"[bold]Current reference (0 dBu):[/bold] factory, "
                      f"{_fmt_ref(LEVEL_REF_LEVEL24_FACTORY)}")
    console.print(f"[dim]Factory default = editor's own 0 dB point: "
                  f"{_fmt_ref(LEVEL_REF_LEVEL24_FACTORY)}[/dim]")
    console.print(f"[bold]Calibration points:[/bold] {len(points)}")

    if not points:
        console.print("\n[dim]No calibration points recorded yet.[/dim]")
        return

    t = Table(title="Calibration Points", box=rich_box.SIMPLE_HEAD)
    t.add_column("#", justify="right", min_width=3)
    t.add_column("dBu", justify="right", min_width=8)
    t.add_column("Channel", min_width=6)
    t.add_column("Mean level24", justify="right", min_width=12)
    t.add_column("≈ uint16", justify="right", min_width=8)
    t.add_column("Min", justify="right", min_width=6)
    t.add_column("Max", justify="right", min_width=6)
    t.add_column("Samples", justify="right", min_width=7)
    if ref is not None:
        t.add_column("Measured dBu", justify="right", min_width=10)
        t.add_column("Error", justify="right", min_width=7)

    for i, p in enumerate(points):
        v24 = _point_level24(p)
        legacy = p.get("mean_level24") is None
        row = [
            str(i + 1),
            f"{p['dbu']:+.1f}",
            p.get("channel", "InA"),
            f"{v24:.0f}" + (" *" if legacy else ""),
            f"{v24 / LEVEL24_PER_UINT16:.1f}",
            str(p.get("min_level24", p.get("min_uint16", ""))),
            str(p.get("max_level24", p.get("max_uint16", ""))),
            str(p.get("samples", "")),
        ]
        if ref is not None:
            measured = 20 * math.log10(v24 / ref) if v24 > 0 else float("-inf")
            err = measured - p["dbu"]
            row.append(f"{measured:+.2f}")
            row.append(f"{err:+.2f}")
        t.add_row(*row)
    console.print(t)
    if any(p.get("mean_level24") is None for p in points):
        console.print("[dim]* legacy point recorded in uint16 units (× 256 shown); "
                      "recapture for full resolution[/dim]")

    computed = calibrate_compute_ref(points)
    if computed:
        console.print(f"\n[bold]Best-fit reference:[/bold] {_fmt_ref(computed)}")
        console.print("[dim]Run 'dspanalyze calibrate apply' to write this value.[/dim]")


def cmd_calibrate_capture(dbu: float, channel: int = 0,
                          n_samples: int = DEFAULT_SAMPLES) -> None:
    """Capture 24-bit levels at a known analog level and store the point."""
    from rich.console import Console
    from minidsp.device import DSPmini
    from minidsp.protocol import (
        INPUT_CHANNEL_NAMES, OUTPUT_CHANNEL_NAMES, LEVEL24_PER_UINT16,
        calibrate_compute_ref,
    )

    console = Console()
    ch_names = list(INPUT_CHANNEL_NAMES) + list(OUTPUT_CHANNEL_NAMES)
    ch_label = ch_names[channel]

    console.print(f"\n[bold]Capturing level at {dbu:+.1f} dBu[/bold] "
                  f"on {ch_label} ({n_samples} samples)...")
    console.print("[dim]Send the calibration signal now. Press Ctrl+C to abort.[/dim]\n")

    dsp = DSPmini()
    try:
        dsp.open()
    except Exception as e:
        print(f"Error: Could not open device: {e}", file=sys.stderr)
        sys.exit(1)

    raw_vals: list[int] = []
    try:
        while len(raw_vals) < n_samples:
            levels = dsp.poll_levels()
            if levels is None:
                console.print("  [yellow](timeout)[/yellow]")
                continue
            all_vals = levels["inputs24"] + levels["outputs24"]
            val = all_vals[channel]
            raw_vals.append(val)
            bar_len = min(40, val // (7 * LEVEL24_PER_UINT16))
            console.print(f"  [{len(raw_vals):>3}/{n_samples}] "
                          f"level24={val:>7} (uint16 {val // LEVEL24_PER_UINT16:>3}) "
                          f"{'█' * bar_len}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
    finally:
        dsp.close()

    if not raw_vals:
        console.print("[red]No samples collected.[/red]")
        return

    mean_v = sum(raw_vals) / len(raw_vals)
    min_v = min(raw_vals)
    max_v = max(raw_vals)
    console.print(f"\n  [bold]Results:[/bold] mean={mean_v:.1f} (uint16 "
                  f"{mean_v / LEVEL24_PER_UINT16:.2f}), min={min_v}, max={max_v}, "
                  f"N={len(raw_vals)}")

    cal = calibrate_load()
    if "points" not in cal:
        cal["points"] = []
    cal["points"].append({
        "dbu": dbu,
        "channel": ch_label,
        "channel_index": channel,
        "mean_level24": round(mean_v, 1),
        "min_level24": min_v,
        "max_level24": max_v,
        "mean_uint16": round(mean_v / LEVEL24_PER_UINT16, 2),  # for readability
        "samples": len(raw_vals),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    cal["points"].sort(key=lambda p: p["dbu"], reverse=True)

    computed = calibrate_compute_ref(cal["points"])
    if computed:
        cal["ref_level24_computed"] = round(computed, 1)
        console.print(f"\n  [green]Best-fit reference: {_fmt_ref(computed)}[/green]")
        console.print("  [dim]Run 'dspanalyze calibrate show' to see all points, "
                      "'dspanalyze calibrate apply' to activate.[/dim]")

    calibrate_save(cal)
    console.print(f"\n  Saved to {_calibration_file_path()}")


def cmd_calibrate_apply() -> None:
    """Compute the best-fit reference from stored points and write it."""
    from rich.console import Console
    from minidsp.protocol import (
        LEVEL24_PER_UINT16,
        calibrate_compute_ref,
    )

    console = Console()
    cal = calibrate_load()
    points = cal.get("points", [])

    if len(points) < 2:
        console.print("[red]Need at least 2 calibration points to compute the reference.[/red]")
        console.print(f"  Currently have {len(points)} point(s). "
                      "Run 'dspanalyze calibrate capture <dBu>' to add more.")
        sys.exit(1)

    ref = calibrate_compute_ref(points)
    if ref is None:
        console.print("[red]Could not compute the reference from calibration points.[/red]")
        sys.exit(1)

    previous = _stored_ref24(cal)
    cal["ref_level24"] = round(ref, 1)
    cal["ref_level"] = round(ref / LEVEL24_PER_UINT16, 2)   # legacy uint16 units
    calibrate_save(cal)
    console.print(f"[green]Calibration applied![/green] reference = {_fmt_ref(ref)}")
    if previous is not None:
        console.print(f"  (was {_fmt_ref(previous)})")
    console.print(f"  Written to {_calibration_file_path()}")
    console.print("\n  [dim]The library will load this value on next import.[/dim]")


def cmd_calibrate_reset() -> None:
    """Revert calibration.toml to the factory default (the editor's 0 dB point)."""
    from rich.console import Console
    from minidsp.protocol import LEVEL_REF_LEVEL24_FACTORY, LEVEL24_PER_UINT16

    console = Console()
    calibrate_save({
        "ref_level24": round(float(LEVEL_REF_LEVEL24_FACTORY), 1),
        "ref_level": round(float(LEVEL_REF_LEVEL24_FACTORY) / LEVEL24_PER_UINT16, 2),
        "points": [],
    })
    console.print(f"[green]Calibration reset.[/green]")
    console.print(f"  reference = {_fmt_ref(LEVEL_REF_LEVEL24_FACTORY)} (factory default)")
    console.print(f"  Written to {_calibration_file_path()}")
