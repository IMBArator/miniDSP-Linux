"""USB HID capture via tshark — auto-detect device, capture traffic, save pcapng.

Works on both Windows (USBPcap interfaces) and Linux (usbmon).
The user runs this on the machine connected to the DSP device.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import time
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


def _find_linux_device_address() -> int | None:
    """Find the USB device address (devnum) for the DSP device via sysfs."""
    try:
        usb_devices = Path("/sys/bus/usb/devices")
        for dev_dir in usb_devices.iterdir():
            vid_path = dev_dir / "idVendor"
            pid_path = dev_dir / "idProduct"
            if vid_path.exists() and pid_path.exists():
                vid = vid_path.read_text().strip()
                pid = pid_path.read_text().strip()
                if vid == f"{VENDOR_ID:04x}" and pid == f"{PRODUCT_ID:04x}":
                    devnum_path = dev_dir / "devnum"
                    if devnum_path.exists():
                        return int(devnum_path.read_text().strip())
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
    device_address: int | None = None,
) -> Path | None:
    """Run a tshark capture session and save the pcapng file.

    Uses a two-pass approach: captures all USB traffic to a temp file, then
    filters by usb.device_address to produce a small final pcapng with only
    DSP device traffic. This is necessary because tshark has no BPF capture
    filters for USB-specific fields — they're only available as display filters,
    which can't be combined with -w during live capture.

    Returns the path to the saved capture file, or None on failure.
    """
    tshark = find_tshark()
    system = platform.system()

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

    # Determine USB device address for post-capture filtering
    if device_address is None:
        if system == "Linux":
            device_address = _find_linux_device_address()
            if device_address is None:
                print("Error: Could not auto-detect USB device address.", file=sys.stderr)
                print("Is the DSP device connected? (VID=0x0168 PID=0x0821)", file=sys.stderr)
                return None
        else:
            # Windows: require explicit --device-address
            print("Error: --device-address is required on Windows.", file=sys.stderr)
            print("Find the device address in Wireshark's USB device list.", file=sys.stderr)
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
    temp_path = output_dir / f".capture_{timestamp}_raw.pcapng"

    # Build tshark command — capture all traffic on the interface (no filter)
    cmd = [
        tshark,
        "-i", interface,
        "-w", str(temp_path),
    ]

    if duration:
        cmd.extend(["-a", f"duration:{duration}"])

    print(f"Capturing USB traffic on interface: {interface}")
    print(f"Device address: {device_address}")
    print(f"Output: {output_path}")
    if duration:
        print(f"Duration: {duration}s")
    else:
        print("Press Ctrl+C to stop capture...")
    print()

    # Run tshark with a polling loop so Ctrl+C is handled cleanly
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while proc.poll() is None:
            time.sleep(0.2)
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait(timeout=5)
        print("\nCapture stopped.")

    if not temp_path.exists() or temp_path.stat().st_size == 0:
        print("Warning: Capture file is empty or was not created.", file=sys.stderr)
        temp_path.unlink(missing_ok=True)
        return None

    # Second pass: filter by device address to produce a small final pcapng
    print(f"Filtering by usb.device_address == {device_address}...")
    filter_result = subprocess.run(
        [
            tshark,
            "-r", str(temp_path),
            "-Y", f"usb.device_address == {device_address}",
            "-w", str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Clean up temp file
    temp_path.unlink(missing_ok=True)

    if filter_result.returncode != 0:
        print(f"Error filtering capture: {filter_result.stderr}", file=sys.stderr)
        return None

    if not output_path.exists() or output_path.stat().st_size == 0:
        print("Warning: No packets matched the device address filter.", file=sys.stderr)
        print(f"Device address {device_address} may be incorrect.", file=sys.stderr)
        output_path.unlink(missing_ok=True)
        return None

    # Write metadata sidecar
    import tomli_w

    from dspanalyze.metadata import meta_path_for

    meta = {
        "capture": {
            "file": filename,
            "format": "pcapng",
            "created": datetime.now().isoformat(timespec="seconds"),
            "source_machine": system.lower(),
            "interface": interface,
            "device_address": device_address,
        },
        "description": {
            "feature": description,
            "notes": notes,
        },
    }

    meta_file = meta_path_for(output_path)
    with open(meta_file, "wb") as f:
        tomli_w.dump(meta, f)

    size_kb = output_path.stat().st_size / 1024
    print(f"Capture saved: {output_path} ({size_kb:.1f} KB)")
    print(f"Metadata saved: {meta_file}")
    return output_path
