"""USB HID capture via tshark — auto-detect device, capture traffic, save pcapng.

Works on both Windows (USBPcap interfaces) and Linux (usbmon).
The user runs this on the machine connected to the DSP device.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VENDOR_ID = 0x0168
PRODUCT_ID = 0x0821


def find_tshark() -> str:
    """Locate tshark binary on PATH."""
    tshark = shutil.which("tshark")
    if tshark is None:
        # Windows: try common install locations
        if platform.system() == "Windows":
            for prog in [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]:
                candidate = Path(prog) / "Wireshark" / "tshark.exe"
                if candidate.exists():
                    return str(candidate)
        print("Error: tshark not found. Install Wireshark.", file=sys.stderr)
        sys.exit(1)
    return tshark


def list_interfaces(tshark: str) -> list[dict]:
    """List available capture interfaces from tshark."""
    result = subprocess.run(
        [tshark, "-D"],
        capture_output=True, text=True, timeout=10,
    )
    interfaces = []
    for line in result.stdout.strip().splitlines():
        # Format: "1. interface_name (description)" or "1. interface_name"
        m = re.match(r"(\d+)\.\s+(\S+)(?:\s+\((.+)\))?", line)
        if m:
            interfaces.append({
                "index": int(m.group(1)),
                "name": m.group(2),
                "description": m.group(3) or "",
            })
    return interfaces


def find_usb_interface(tshark: str) -> str | None:
    """Auto-detect the USB capture interface carrying the DSP device.

    On Linux: looks for usbmon interfaces.
    On Windows: looks for USBPcap interfaces.
    """
    interfaces = list_interfaces(tshark)
    system = platform.system()

    if system == "Linux":
        # Linux uses usbmon — we need to find which bus the device is on
        bus = _find_linux_usb_bus()
        if bus is not None:
            target = f"usbmon{bus}"
            for iface in interfaces:
                if iface["name"] == target:
                    return target
        # Fallback: any usbmon interface
        for iface in interfaces:
            if "usbmon" in iface["name"]:
                return iface["name"]

    elif system == "Windows":
        # Windows uses USBPcap — try to find the right root hub
        for iface in interfaces:
            if "USBPcap" in iface["name"] or "USBPcap" in iface["description"]:
                return iface["name"]

    return None


def _find_linux_usb_bus() -> int | None:
    """Find the USB bus number for the DSP device via sysfs."""
    try:
        usb_devices = Path("/sys/bus/usb/devices")
        for dev_dir in usb_devices.iterdir():
            vid_path = dev_dir / "idVendor"
            pid_path = dev_dir / "idProduct"
            if vid_path.exists() and pid_path.exists():
                vid = vid_path.read_text().strip()
                pid = pid_path.read_text().strip()
                if vid == f"{VENDOR_ID:04x}" and pid == f"{PRODUCT_ID:04x}":
                    busnum_path = dev_dir / "busnum"
                    if busnum_path.exists():
                        return int(busnum_path.read_text().strip())
    except (OSError, ValueError):
        pass
    return None


def detect_device() -> dict | None:
    """Detect the DSP device and return info dict, or None if not found."""
    system = platform.system()

    if system == "Linux":
        bus = _find_linux_usb_bus()
        if bus is not None:
            return {"bus": bus, "vid": VENDOR_ID, "pid": PRODUCT_ID, "system": "Linux"}

    elif system == "Windows":
        # Use PowerShell to check for the device
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 f"Get-PnpDevice | Where-Object {{ $_.HardwareID -match 'VID_{VENDOR_ID:04X}&PID_{PRODUCT_ID:04X}' }}"],
                capture_output=True, text=True, timeout=10,
            )
            if f"VID_{VENDOR_ID:04X}" in result.stdout:
                return {"vid": VENDOR_ID, "pid": PRODUCT_ID, "system": "Windows"}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return None


def run_capture(
    output_dir: Path,
    description: str = "",
    notes: str = "",
    duration: int | None = None,
    interface: str | None = None,
) -> Path | None:
    """Run a tshark capture session and save the pcapng file.

    Returns the path to the saved capture file, or None on failure.
    """
    tshark = find_tshark()

    # Auto-detect interface if not specified
    if interface is None:
        interface = find_usb_interface(tshark)
        if interface is None:
            print("Error: Could not auto-detect USB capture interface.", file=sys.stderr)
            print("Available interfaces:", file=sys.stderr)
            for iface in list_interfaces(tshark):
                print(f"  {iface['index']}. {iface['name']} ({iface['description']})", file=sys.stderr)
            print("\nSpecify one with --interface", file=sys.stderr)
            return None

    # Generate output filename from description
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_desc = re.sub(r"[^\w\s-]", "", description).strip().replace(" ", "_")
    if safe_desc:
        filename = f"capture_{timestamp}_{safe_desc}.pcapng"
    else:
        filename = f"capture_{timestamp}.pcapng"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename

    # Build tshark command
    cmd = [
        tshark,
        "-i", interface,
        "-w", str(output_path),
        "-f", f"usb.idVendor == 0x{VENDOR_ID:04x} and usb.idProduct == 0x{PRODUCT_ID:04x}",
    ]

    if duration:
        cmd.extend(["-a", f"duration:{duration}"])

    print(f"Capturing USB traffic on interface: {interface}")
    print(f"Output: {output_path}")
    if duration:
        print(f"Duration: {duration}s")
    else:
        print("Press Ctrl+C to stop capture...")
    print()

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
    except KeyboardInterrupt:
        # Graceful stop on Ctrl+C
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
        print("\nCapture stopped.")

    if not output_path.exists() or output_path.stat().st_size == 0:
        print("Warning: Capture file is empty or was not created.", file=sys.stderr)
        print("The USB capture filter may not match. Try without filter:", file=sys.stderr)
        print(f"  tshark -i {interface} -w {output_path}", file=sys.stderr)
        return None

    # Write metadata sidecar
    from dspanalyze.metadata import meta_path_for
    import tomli_w

    meta = {
        "capture": {
            "file": filename,
            "format": "pcapng",
            "created": datetime.now().isoformat(timespec="seconds"),
            "source_machine": platform.system().lower(),
            "interface": interface,
        },
        "description": {
            "feature": description,
            "notes": notes,
        },
    }

    meta_file = meta_path_for(output_path)
    with open(meta_file, "wb") as f:
        tomli_w.dump(meta, f)

    print(f"Capture saved: {output_path}")
    print(f"Metadata saved: {meta_file}")
    return output_path
