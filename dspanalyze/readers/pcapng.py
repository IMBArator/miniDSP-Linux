"""Read pcapng/pcap capture files via tshark subprocess.

Shells out to `tshark -T fields` to extract USB HID data — fast,
no Python pcap library needed, works with any Wireshark-supported format.

Note: On Windows (USBPcap), HID data appears in the `usbhid.data` field.
On Linux (usbmon), it appears in `usb.capdata` instead. We query both
fields and use whichever is populated.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from dspanalyze.readers import RawPacket


def read_pcapng(filepath: str | Path) -> list[RawPacket]:
    """Extract HID interrupt packets from a pcapng/pcap file via tshark.

    Tries ``usbhid.data`` first (typical for Windows/USBPcap captures) and
    falls back to ``usb.capdata`` filtered by ``usb.transfer_type == 0x01``
    (typical for Linux/usbmon). The first attempt that yields any packets
    is returned — captures from either platform are handled transparently.

    Args:
        filepath: Path to a ``.pcapng`` or ``.pcap`` file.

    Returns:
        Ordered list of :class:`RawPacket`. Empty if no HID interrupt
        traffic is found.

    Raises:
        SystemExit: When ``tshark`` is not found on ``$PATH`` (prints an
            error and exits with status 1).
    """
    filepath = Path(filepath)
    tshark = shutil.which("tshark")
    if tshark is None:
        print("Error: tshark not found on PATH. Install Wireshark/tshark.",
              file=sys.stderr)
        sys.exit(1)

    # Try usbhid.data first (Windows/USBPcap captures)
    packets = _extract_with_filter(tshark, filepath, "usbhid.data", "usbhid.data")
    if packets:
        return packets

    # Fallback: usb.capdata for Linux/usbmon captures
    # Filter for interrupt transfers (type 1) to avoid bulk/isochronous noise
    packets = _extract_with_filter(tshark, filepath, "usb.capdata",
                                   "usb.transfer_type == 0x01 && usb.capdata")
    return packets


def _extract_with_filter(
    tshark: str,
    filepath: Path,
    data_field: str,
    display_filter: str,
) -> list[RawPacket]:
    """Invoke tshark with a specific data field and display filter.

    Runs ``tshark -T fields`` requesting frame number, relative timestamp,
    endpoint address, and the chosen HID data field, with the display filter
    applied. Each non-empty hex blob is decoded into a :class:`RawPacket`.
    Endpoint 0x02 is mapped to ``direction="out"`` and 0x81 to ``"in"``;
    other endpoints fall back to a high-bit heuristic.

    Args:
        tshark: Absolute path to the tshark executable.
        filepath: Capture file to read.
        data_field: Field to extract for the HID payload — either
            ``"usbhid.data"`` or ``"usb.capdata"``.
        display_filter: Wireshark display filter passed via ``-Y``.

    Returns:
        Ordered list of :class:`RawPacket`. Returns an empty list when
        tshark exits with a non-zero status (e.g. unknown field name on an
        older tshark) — callers should try the alternate field rather than
        propagating an exception.
    """
    result = subprocess.run(
        [
            tshark, "-r", str(filepath),
            "-T", "fields",
            "-e", "frame.number",
            "-e", "frame.time_relative",
            "-e", "usb.endpoint_address",
            "-e", data_field,
            "-Y", display_filter,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        return []

    packets: list[RawPacket] = []

    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 4 or not parts[3]:
            continue

        frame_num = int(parts[0])
        timestamp = float(parts[1])
        endpoint_str = parts[2]
        hex_data = parts[3].replace(":", "")  # usb.capdata may use colon separators

        try:
            endpoint = int(endpoint_str, 16)
        except ValueError:
            endpoint = 0

        if endpoint == 0x02:
            direction = "out"
        elif endpoint == 0x81:
            direction = "in"
        else:
            direction = "out" if endpoint < 0x80 else "in"

        try:
            hid_data = bytes.fromhex(hex_data)
        except ValueError:
            continue

        packets.append(RawPacket(
            frame_number=frame_num,
            timestamp=timestamp,
            direction=direction,
            endpoint=endpoint,
            hid_data=hid_data,
        ))

    return packets
