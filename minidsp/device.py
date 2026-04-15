"""
the t.racks DSP 4x4 Mini — USB HID device communication.

Uses /dev/hidraw directly (no library dependency beyond the kernel driver).
Falls back to cython-hidapi if available and hidraw not found.
"""

from __future__ import annotations

import glob
import os
import select

class DeviceLockedError(RuntimeError):
    """Raised when the device is locked and requires a PIN before config access."""


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
    cmd_set_channel_name,
    cmd_peq_band,
    cmd_peq_channel_bypass,
    cmd_submit_pin,
    cmd_set_lock_pin,
    cmd_set_delay_unit,
    cmd_test_tone,
    DELAY_UNIT_MS,
    DELAY_UNIT_M,
    DELAY_UNIT_FT,
    TONE_OFF,
    TONE_PINK,
    TONE_WHITE,
    TONE_SINE,
    is_ack,
    OP_ACTIVATE,
    OP_INIT,
    parse_config_page,
    parse_device_info,
    parse_frame,
    parse_levels,
    parse_pin_response,
    parse_preset_index,
    parse_preset_name,
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

    def set_delay_unit(self, unit: int) -> bool:
        """Set the delay display unit (display-only — protocol uses samples).

        unit: DELAY_UNIT_MS=0x00, DELAY_UNIT_M=0x01, DELAY_UNIT_FT=0x02
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_set_delay_unit(unit))
        if payload is None:
            return False
        return is_ack(payload)

    def set_test_tone(self, mode: int, freq_index: int = 0) -> bool:
        """Enable or disable the internal test tone generator.

        mode:       TONE_OFF=0x00, TONE_PINK=0x01, TONE_WHITE=0x02, TONE_SINE=0x03
        freq_index: sine frequency index (SINE_FREQ_* constants, 0x00=20Hz … 0x1E=20kHz);
                    ignored for noise modes (pass 0).
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_test_tone(mode, freq_index))
        if payload is None:
            return False
        return is_ack(payload)

    def set_channel_name(self, channel: int, name: str) -> bool:
        """Set the display name for a channel.

        channel: unified index (inputs 0-3, outputs 4-7)
        name: up to 8 ASCII characters (zero-padded to 8 bytes)
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_set_channel_name(channel, name))
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
        # Step 3: device info — also contains the lock status flag
        device_info_payload = self._send_recv(cmd_device_info(), skip_polls=True)
        if device_info_payload is not None:
            info = parse_device_info(device_info_payload)
            if info and info.get("locked"):
                raise DeviceLockedError(
                    "Device is locked. Call submit_pin(pin) before read_config()."
                )
        # Step 4: preset header
        self._send_recv(cmd_preset_header(), skip_polls=True)
        # Step 5: active preset index
        preset_idx_payload = self._send_recv(cmd_preset_index(), skip_polls=True)
        active_slot = parse_preset_index(preset_idx_payload) if preset_idx_payload else None
        # Step 6: read all 30 preset names
        preset_names: list[str] = []
        for slot in range(30):
            payload = self._send_recv(cmd_read_name(slot), skip_polls=True)
            result = parse_preset_name(payload) if payload else None
            preset_names.append(result[1] if result else "")
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
        params = parse_preset_params(bytes(config_data))
        if params is None:
            return None
        params["active_slot"] = active_slot
        params["preset_names"] = preset_names
        return params

    def set_peq_band(self, channel: int, band: int, gain_raw: int,
                     freq_raw: int, q_raw: int, filter_type: int,
                     bypass: bool = False) -> bool:
        """Set a single PEQ band for an output channel (0x33).

        channel:     output channel index (0x04=Out1 .. 0x07=Out4)
        band:        0-indexed band (0–6 for bands 1–7)
        gain_raw:    0–240 (dB = (raw − 120) / 10.0; 0 dB = 120)
        freq_raw:    0–300 (Hz = 19.70 × (20160/19.70)^(raw/300))
        q_raw:       0–100 (Q = 0.4 × 320^(raw/100))
        filter_type: use PEQ_TYPE_* constants
        bypass:      True = bypass this band
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_peq_band(channel, band, gain_raw, freq_raw,
                                               q_raw, filter_type, bypass))
        if payload is None:
            return False
        return is_ack(payload)

    def set_peq_channel_bypass(self, channel: int, bypass: bool) -> bool:
        """Bypass or restore all PEQ bands for an output channel (0x3C).

        channel: output channel index (0x04=Out1 .. 0x07=Out4)
        bypass:  True = all bands bypassed, False = all bands active
        Returns True if the device ACK'd.
        """
        payload = self._send_recv(cmd_peq_channel_bypass(channel, bypass))
        if payload is None:
            return False
        return is_ack(payload)

    def is_locked(self) -> bool | None:
        """Check if the device is currently locked.

        Sends a 0x2C device-info query and checks byte 6 of the response.
        Returns True if locked, False if unlocked, None if no response.

        Discovered from comparing 0x2C responses across 3 captures:
          Unlocked: 2c 00 27 0f 00 00 00 00
          Locked:   2c 00 27 0f 00 00 01 00
        """
        payload = self._send_recv(cmd_device_info(), skip_polls=True)
        if payload is None:
            return None
        info = parse_device_info(payload)
        if info is None:
            return None
        return info["locked"]

    def submit_pin(self, pin: str) -> bool:
        """Submit a PIN to unlock a locked device (0x2D).

        Call this BEFORE read_config() if the device is locked. When the device
        is locked it keeps ACKing 0x12 activate commands without proceeding to
        config load — it waits for a correct 0x2D PIN submission.

        pin: exactly 4 ASCII digit characters (e.g. "7654")
        Returns True if PIN was correct, False if wrong or no response.
        """
        payload = self._send_recv(cmd_submit_pin(pin), skip_polls=True)
        if payload is None:
            return False
        result = parse_pin_response(payload)
        return result is True

    def set_lock_pin(self, pin: str) -> bool:
        """Set device lock PIN and immediately lock the device (0x2F).

        ⚠ WARNING: This LOCKS the device immediately after the ACK is received.
        The current session ends — the device will not respond to further
        commands until the correct PIN is entered on the next connection via
        submit_pin(). If the PIN is lost, factory reset procedure is unknown.

        pin: exactly 4 ASCII digit characters (e.g. "7654")
        Returns True if the device ACK'd before disconnecting.
        """
        payload = self._send_recv(cmd_set_lock_pin(pin))
        if payload is None:
            return False
        return is_ack(payload)
