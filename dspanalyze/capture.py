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
    """Locate the tshark binary on PATH (or common Windows install paths).

    Returns:
        Absolute path to the tshark executable.

    Raises:
        SystemExit: If tshark is not found (prints an error and exits with code 1).
    """
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
    """List available capture interfaces reported by tshark.

    Args:
        tshark: Path to the tshark binary.

    Returns:
        List of dicts with keys ``'index'`` (int), ``'name'`` (str), and
        ``'description'`` (str).
    """
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

    On Linux looks for the correct ``usbmonN`` interface by matching the
    device's USB bus number. On Windows looks for a USBPcap interface.

    Args:
        tshark: Path to the tshark binary.

    Returns:
        Interface name string (e.g. ``"usbmon1"``), or ``None`` if no
        suitable interface is found.
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
    """Find the Linux USB bus number for the DSP device via sysfs.

    Iterates ``/sys/bus/usb/devices/*`` looking for the entry whose
    ``idVendor``/``idProduct`` files match ``VENDOR_ID``/``PRODUCT_ID``
    (``0168``/``0821``), then returns the integer parsed from ``busnum``.

    Returns:
        The USB bus number (integer matching ``usbmonN``), or ``None`` if
        the device is not present in sysfs. Any ``OSError`` or ``ValueError``
        encountered while reading sysfs files is swallowed and treated as
        "not found".
    """
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
    """Find the Linux USB device address (``devnum``) for the DSP device.

    Same sysfs scan as :func:`_find_linux_usb_bus`, but returns the
    ``devnum`` instead of the ``busnum``. The device address is what the
    pcapng filter ``usb.device_address == N`` needs.

    Returns:
        The integer USB device address, or ``None`` if the device is not
        present or sysfs cannot be read.
    """
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


def find_usbpcapcmd(tshark: str) -> str | None:
    """Locate ``USBPcapCMD.exe`` (Wireshark's USBPcap extcap helper) on Windows.

    Args:
        tshark: Path to the tshark binary; USBPcapCMD lives in its ``extcap``
            folder.

    Returns:
        Path to ``USBPcapCMD.exe``, or ``None`` if it is not installed.
    """
    base = Path(tshark).parent / "extcap"
    for candidate in (base / "USBPcapCMD.exe", base / "wireshark" / "USBPcapCMD.exe"):
        if candidate.exists():
            return str(candidate)
    return None


def list_usbpcap_devices(usbpcapcmd: str, interface: str) -> list[dict]:
    """List the devices attached to one USBPcap root hub (Windows only).

    Runs ``USBPcapCMD --extcap-config``, which only enumerates the hub — it
    captures nothing and does not raise a UAC prompt.

    Args:
        usbpcapcmd: Path to ``USBPcapCMD.exe`` (see :func:`find_usbpcapcmd`).
        interface: USBPcap interface name, e.g. ``"\\\\.\\USBPcap1"``.

    Returns:
        One dict per entry with ``'value'`` (str — the USB device address for
        devices, ``"<addr>_<n>"`` for their functions), ``'display'`` (str) and
        ``'parent'`` (str | None). Empty if the hub has no devices or the
        helper fails.
    """
    try:
        result = subprocess.run(
            [usbpcapcmd, "--extcap-interface", interface, "--extcap-config"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    entries = []
    for line in result.stdout.splitlines():
        if not line.startswith("value {arg=99}"):
            continue
        fields = dict(re.findall(r"\{(\w+)=([^}]*)\}", line))
        entries.append({
            "value": fields.get("value", ""),
            "display": fields.get("display", ""),
            "parent": fields.get("parent"),
        })
    return entries


# Programs that hold a USB capture interface open while they run.
_CAPTURE_PROGRAMS = ("wireshark", "dumpcap", "tshark", "usbpcapcmd")


def running_capture_programs() -> list[str]:
    """Return the names of capture programs that are already running.

    A forgotten Wireshark capturing on the same USBPcap hub makes a new
    capture come back empty, so :func:`run_capture` warns about these.

    Returns:
        Sorted process names (e.g. ``["Wireshark.exe", "dumpcap.exe"]``);
        empty if none run or the process list cannot be read.
    """
    try:
        if platform.system() == "Windows":
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=10).stdout
            names = [line.split('","')[0].strip('"') for line in out.splitlines() if line]
        else:
            out = subprocess.run(["ps", "-A", "-o", "comm="],
                                 capture_output=True, text=True, timeout=10).stdout
            names = out.split()
    except (OSError, subprocess.TimeoutExpired):
        return []
    return sorted({n for n in names if Path(n).stem.lower() in _CAPTURE_PROGRAMS})


def is_windows_admin() -> bool | None:
    """Report whether this Windows process is elevated.

    Returns:
        ``True``/``False`` on Windows, ``None`` elsewhere or if unknown.
    """
    if platform.system() != "Windows":
        return None
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return None


def _print_tshark_failure(returncode: int | None, stderr: bytes) -> None:
    """Print tshark's exit code and error output to stderr.

    Args:
        returncode: tshark's exit status (``None`` if still unknown).
        stderr: Everything tshark wrote to stderr.
    """
    print(f"tshark exit code: {returncode}", file=sys.stderr)
    text = stderr.decode(errors="replace").strip()
    if text:
        print("tshark output:\n  " + text.replace("\n", "\n  "), file=sys.stderr)


def detect_device() -> dict | None:
    """Detect the DSP device and return its connection info.

    Returns:
        Dict with keys ``'vid'``, ``'pid'``, and ``'system'``. Linux builds
        also include ``'bus'`` (int). Returns ``None`` if the device is not
        found.
    """
    system = platform.system()

    if system == "Linux":
        bus = _find_linux_usb_bus()
        if bus is not None:
            return {"bus": bus, "vid": VENDOR_ID, "pid": PRODUCT_ID, "system": "Linux"}

    elif system == "Windows":
        # Use PowerShell to check for the device
        try:
            # Print only the InstanceId: the default table output truncates
            # that column in a narrow (non-console) pipe, hiding the VID.
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match "
                 f"'VID_{VENDOR_ID:04X}&PID_{PRODUCT_ID:04X}' }} | "
                 "Select-Object -ExpandProperty InstanceId"],
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
    """Run a tshark capture session and save the result as a pcapng file.

    Uses a two-pass approach: captures all USB traffic to a temp file, then
    filters by ``usb.device_address`` to produce a small final pcapng with
    only DSP device traffic. This is necessary because tshark has no BPF
    capture filters for USB-specific fields — they're only available as
    display filters, which can't be combined with ``-w`` during live capture.

    Args:
        output_dir: Directory where the pcapng and metadata sidecar are saved.
        description: Short label embedded in the filename and metadata.
        notes: Free-text notes written to the ``.meta.toml`` sidecar.
        duration: Capture duration in seconds. ``None`` means capture until
            Ctrl+C.
        interface: tshark interface name to capture on. Auto-detected if
            ``None``.
        device_address: USB device address for post-capture filtering.
            Auto-detected on Linux; required explicitly on Windows.

    Returns:
        Path to the saved ``.pcapng`` file, or ``None`` on failure.
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

    busy = running_capture_programs()
    if busy:
        print(f"Warning: other capture programs are running ({', '.join(busy)}). "
              "A capture already open on the same interface can leave this one empty.",
              file=sys.stderr)
    if is_windows_admin() is False:
        print("Note: this shell is not elevated. USBPcap will ask for administrator "
              "rights (UAC prompt) and the capture only starts once you approve it — "
              "approve it before starting the editor.", file=sys.stderr)

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
    _stdout, tshark_stderr = proc.communicate()

    if not temp_path.exists() or temp_path.stat().st_size == 0:
        print("Warning: Capture file is empty or was not created.", file=sys.stderr)
        _print_tshark_failure(proc.returncode, tshark_stderr)
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
        print(f"Device address {device_address} may be incorrect "
              "(check with --detect), or nothing was captured:", file=sys.stderr)
        _print_tshark_failure(proc.returncode, tshark_stderr)
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
