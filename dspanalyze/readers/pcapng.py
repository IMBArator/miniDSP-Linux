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
    """Extract HID interrupt packets from a pcapng/pcap file using tshark.

    Requires tshark to be installed and on PATH.
    Queries both usbhid.data (Windows/USBPcap) and usb.capdata (Linux/usbmon)
    since tshark classifies the data differently depending on the capture source.
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
    """Run tshark with a specific data field and display filter."""
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
