"""
the t.racks DSP 4x4 Mini — USB HID device communication.

Uses /dev/hidraw directly (no library dependency beyond the kernel driver).
Falls back to cython-hidapi if available and hidraw not found.
"""

from __future__ import annotations

import glob
import os
import select

from .protocol import (
    VENDOR_ID,
    PRODUCT_ID,
    REPORT_SIZE,
    CONFIG_PAGES,
    CONFIG_PAGE_SIZE,
    build_frame,
    cmd_activate,
    cmd_device_info,
    cmd_firmware,
    cmd_delay,
    cmd_gain,
    cmd_gate,
    cmd_hipass,
    cmd_init,
    cmd_lopass,
    cmd_mute,
    cmd_phase,
    cmd_poll,
    cmd_preset_header,
    cmd_preset_index,
    cmd_read_config,
    cmd_read_name,
    is_ack,
    OP_ACTIVATE,
    OP_INIT,
    parse_config_page,
    parse_frame,
    parse_levels,
    parse_preset_params,
)


def find_hidraw_device() -> str | None:
    """Find the /dev/hidrawN path for the DSPmini by checking sysfs for VID/PID."""
    for path in sorted(glob.glob("/sys/class/hidraw/hidraw*/device")):
        uevent_path = os.path.join(path, "uevent")
        try:
            with open(uevent_path) as f:
                uevent = f.read()
        except OSError:
            continue
        # Look for HID_ID=0003:00000168:00000821 (bus_type:vid:pid)
        vid_str = f"{VENDOR_ID:08X}"
        pid_str = f"{PRODUCT_ID:08X}"
        if vid_str in uevent and pid_str in uevent:
            hidraw_name = path.split("/")[-2]  # e.g. "hidraw0"
            return f"/dev/{hidraw_name}"
    return None


class DSPmini:
    """Interface to a the t.racks DSP 4x4 Mini over USB HID."""

    def __init__(self) -> None:
        self._fd: int | None = None

    # --- Connection ---

    def open(self, device_path: str | None = None) -> None:
        """Open the HID device and perform init handshake.

        If device_path is None, auto-detects via sysfs VID/PID matching.
        """
        if device_path is None:
            device_path = find_hidraw_device()
            if device_path is None:
                raise OSError(
                    "DSP 4x4 Mini not found. Is it connected? "
                    "Check: lsusb | grep 0168"
                )
        self._fd = os.open(device_path, os.O_RDWR)
        # Device requires init handshake before it responds to any commands
        self._send(cmd_init())
        self._recv(timeout_ms=500)  # consume init response

    def close(self) -> None:
        """Close the HID device."""
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> DSPmini:
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- Low-level I/O ---

    def _send(self, report: bytes) -> None:
        """Send a 64-byte HID OUT report."""
        assert self._fd is not None, "Device not open"
        os.write(self._fd, report)

    def _recv(self, timeout_ms: int = 500) -> bytes | None:
        """Read a 64-byte HID IN report. Returns None on timeout."""
        assert self._fd is not None, "Device not open"
        timeout_s = timeout_ms / 1000.0
        r, _, _ = select.select([self._fd], [], [], timeout_s)
        if not r:
            return None
        data = os.read(self._fd, REPORT_SIZE)
        if not data:
            return None
        return bytes(data)

    def _send_recv(self, report: bytes, timeout_ms: int = 500,
                    skip_polls: bool = False) -> bytes | None:
        """Send a report and return the parsed payload of the response.

        When skip_polls=True, discards unsolicited level poll responses (0x40)
        that the device may send between non-poll commands.
        """
        from .protocol import OP_POLL
        self._send(report)
        for _ in range(10):
            data = self._recv(timeout_ms)
            if data is None:
                return None
            result = parse_frame(data)
            if result is None:
                return None
            _src, _dst, _length, payload = result
            if skip_polls and payload and payload[0] == OP_POLL:
                continue  # skip unsolicited level response
            return payload
        return None

    # --- High-level commands ---

    def init(self) -> bytes | None:
        """Send the init handshake (0x10). Returns response payload."""
        return self._send_recv(cmd_init())

    def poll_levels(self) -> dict | None:
        """Poll the device for current input/output levels.

        Returns dict with keys: inputs (list[4]), outputs (list[4]),
        input_flags, output_flags, state.  Or None on error/timeout.
        """
        payload = self._send_recv(cmd_poll())
        if payload is None:
            return None
        return parse_levels(payload)

    def set_gain(self, channel: int, raw_value: int) -> bool:
        """Set gain for a channel (unified index: inputs 0–3, outputs 4–7).

        raw_value: 0–400 (use db_to_raw() to convert from dB).
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_gain(channel, raw_value))
        if payload is None:
            return False
        return is_ack(payload)

    def set_phase(self, channel: int, inverted: bool) -> bool:
        """Set phase invert for a channel (unified index: inputs 0-3, outputs 4-7).

        inverted: True=180° inverted, False=normal.
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_phase(channel, inverted))
        if payload is None:
            return False
        return is_ack(payload)

    def set_lopass(self, channel: int, freq_raw: int, slope: int = 0) -> bool:
        """Set low-pass crossover for an output channel.

        channel: unified index (outputs 4–7)
        freq_raw: 0–300 (log scale, Hz = 19.70 × (20160/19.70)^(raw/300))
        slope: 0x00=bypassed, 0x01–0x0a=active with slope type (see SLOPE_* constants)
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_lopass(channel, freq_raw, slope))
        if payload is None:
            return False
        return is_ack(payload)

    def set_hipass(self, channel: int, freq_raw: int, slope: int = 0) -> bool:
        """Set high-pass crossover for an output channel.

        channel: unified index (outputs 4–7)
        freq_raw: 0–300 (log scale, Hz = 19.70 × (20160/19.70)^(raw/300))
        slope: 0x00=bypassed, 0x01–0x0a=active with slope type (see SLOPE_* constants)
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_hipass(channel, freq_raw, slope))
        if payload is None:
            return False
        return is_ack(payload)

    def set_delay(self, channel: int, samples: int) -> bool:
        """Set output delay for a channel.

        channel: unified index (outputs 4–7)
        samples: 0–32640 (delay in samples at 48 kHz; ms = samples / 48)
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_delay(channel, samples))
        if payload is None:
            return False
        return is_ack(payload)

    def set_gate(self, channel: int, attack: int, release: int,
                 hold: int, threshold: int) -> bool:
        """Set noise gate parameters for an input channel.

        channel: 0-indexed input (0–3)
        attack: raw 34–998 (1–999 ms)
        release: raw 0–2999 (0–3000 ms)
        hold: raw 9–998 (10–999 ms)
        threshold: raw 1–180 (−90.0 to 0.0 dB, 0.5 dB/step)
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_gate(channel, attack, release, hold, threshold))
        if payload is None:
            return False
        return is_ack(payload)

    def mute(self, channel: int, mute: bool) -> bool:
        """Mute or unmute a channel (unified index: inputs 0–3, outputs 4–7).

        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_mute(channel, mute))
        if payload is None:
            return False
        return is_ack(payload)

    def read_config(self) -> dict | None:
        """Run the manufacturer startup sequence and read active preset config.

        Replicates the exact command sequence the manufacturer software uses
        before reading config pages (steps 2–8 from the protocol spec).
        Step 1 (init) is already done in open().

        Returns dict with 'gains' (list[8], raw 0–400) and 'mutes' (list[8], bool),
        or None on failure.
        """
        # Step 2: firmware string
        self._send_recv(cmd_firmware(), skip_polls=True)
        # Step 3: device info
        self._send_recv(cmd_device_info(), skip_polls=True)
        # Step 4: preset header
        self._send_recv(cmd_preset_header(), skip_polls=True)
        # Step 5: active preset index
        self._send_recv(cmd_preset_index(), skip_polls=True)
        # Step 6: read all 30 preset names
        for slot in range(30):
            self._send_recv(cmd_read_name(slot), skip_polls=True)
        # Step 7: read 9 config pages
        config_data = bytearray()
        for page in range(CONFIG_PAGES):
            payload = self._send_recv(cmd_read_config(page), skip_polls=True)
            if payload is None:
                return None
            result = parse_config_page(payload)
            if result is None:
                return None
            _page_idx, data = result
            config_data.extend(data)
        # Step 8: activate
        self._send_recv(cmd_activate(), skip_polls=True)
        return parse_preset_params(bytes(config_data))
