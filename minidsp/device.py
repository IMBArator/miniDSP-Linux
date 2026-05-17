"""
the t.racks DSP 4x4 Mini — USB HID device communication.

Uses /dev/hidraw directly (no library dependency beyond the kernel driver).
Falls back to cython-hidapi if available and hidraw not found.
"""

from __future__ import annotations

import fcntl
import glob
import logging
import os
import select
import time

log = logging.getLogger(__name__)


def _frame_hex(report: bytes) -> str:
    """Return the used portion of a HID report as a spaced hex string.

    Strips the zero-padding beyond the frame so ``-vv`` output stays readable.
    Falls back to the full report if framing can't be decoded.
    """
    if len(report) >= 5 and report[0] == 0x10 and report[1] == 0x02:
        length = report[4]
        end = 5 + length + 3  # STX(2) + src + dst + len + payload + ETX(2) + chk
        if end <= len(report):
            return report[:end].hex(" ")
    return report.hex(" ")


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
    cmd_compressor,
    cmd_device_info,
    cmd_firmware,
    cmd_delay,
    cmd_gain,
    cmd_gate,
    cmd_hipass,
    cmd_channel_link,
    cmd_init,
    cmd_load_preset,
    cmd_lopass,
    cmd_matrix_route,
    cmd_mute,
    cmd_phase,
    cmd_poll,
    cmd_prepare_link,
    cmd_preset_header,
    cmd_preset_index,
    cmd_read_config,
    cmd_read_name,
    cmd_store_preset,
    cmd_store_preset_name,
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
    """Find the ``/dev/hidrawN`` path for the DSPmini by scanning sysfs for VID/PID.

    Returns:
        Path string such as ``"/dev/hidraw0"``, or ``None`` if the device is
        not connected or not yet visible in sysfs.
    """
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
    """Interface to the t.racks DSP 4x4 Mini over USB HID.

    Acquires an **exclusive advisory lock** (``fcntl.flock(LOCK_EX|LOCK_NB)``)
    on the hidraw file descriptor in :meth:`open`. This prevents a second
    process (or a second :class:`DSPmini` instance in the same process) from
    opening the device concurrently. The lock is released automatically when
    :meth:`close` calls ``os.close()``.

    Use as a context manager to guarantee release even on exceptions::

        with DSPmini() as dsp:
            cfg = dsp.read_config()

    Note:
        ``fcntl`` locks are advisory — they protect against other cooperative
        Python processes but do not prevent a raw ``open()`` by uncooperative
        programs (e.g. the manufacturer Windows app under Wine).
    """

    def __init__(self) -> None:
        self._fd: int | None = None

    # --- Connection ---

    def open(self, device_path: str | None = None) -> None:
        """Open the HID device, acquire an exclusive lock, and perform init.

        Opens the hidraw node with ``O_RDWR`` then immediately calls
        ``fcntl.flock(LOCK_EX|LOCK_NB)`` so that no other process can open
        the same device concurrently. If the lock cannot be acquired the fd
        is closed and an ``OSError`` is raised — the caller does not need to
        call :meth:`close` in that case.

        After locking, sends the init handshake (0x10) with up to 5 retries
        (0.5 s apart). If the device still does not respond, closes and raises.

        Args:
            device_path: Path to the hidraw device (e.g. ``"/dev/hidraw0"``).
                If ``None``, auto-detects via sysfs VID/PID matching.

        Raises:
            OSError: If the device is not found, the exclusive lock cannot be
                acquired (already held by another process), or the device does
                not respond to the init handshake within 5 attempts.
        """
        if device_path is None:
            device_path = find_hidraw_device()
            if device_path is None:
                raise OSError(
                    "DSP 4x4 Mini not found. Is it connected? "
                    "Check: lsusb | grep 0168"
                )
        self._fd = os.open(device_path, os.O_RDWR)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            os.close(self._fd)
            self._fd = None
            raise OSError(
                f"{device_path} is already in use by another process"
            )
        log.info("Opened %s (exclusive lock acquired)", device_path)

        max_retries = 5
        retry_delay = 0.5
        for attempt in range(1, max_retries + 1):
            self._send(cmd_init())
            response = self._recv(timeout_ms=500)
            if response is not None:
                log.debug("Init handshake succeeded (attempt %d/%d)",
                          attempt, max_retries)
                return
            log.debug("Init handshake attempt %d/%d — no response",
                      attempt, max_retries)
            if attempt < max_retries:
                time.sleep(retry_delay)

        log.warning("Init handshake failed after %d attempts", max_retries)
        os.close(self._fd)
        self._fd = None
        raise OSError("Device opened but not responding to init handshake")

    def close(self) -> None:
        """Close the HID device and release the exclusive lock."""
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
        if log.isEnabledFor(logging.DEBUG):
            log.debug("TX %s", _frame_hex(report))
        os.write(self._fd, report)

    def _recv(self, timeout_ms: int = 500) -> bytes | None:
        """Read a 64-byte HID IN report.

        Args:
            timeout_ms: Read timeout in milliseconds.

        Returns:
            Raw 64-byte report, or ``None`` on timeout or empty read.
        """
        assert self._fd is not None, "Device not open"
        timeout_s = timeout_ms / 1000.0
        r, _, _ = select.select([self._fd], [], [], timeout_s)
        if not r:
            log.debug("RX timeout (%d ms)", timeout_ms)
            return None
        data = os.read(self._fd, REPORT_SIZE)
        if not data:
            log.debug("RX empty read")
            return None
        if log.isEnabledFor(logging.DEBUG):
            log.debug("RX %s", _frame_hex(bytes(data)))
        return bytes(data)

    def _send_recv(self, report: bytes, timeout_ms: int = 500,
                    skip_polls: bool = False) -> bytes | None:
        """Send a report and return the parsed payload of the response.

        Args:
            report: Encoded 64-byte HID OUT report to send.
            timeout_ms: Per-read timeout in milliseconds.
            skip_polls: When ``True``, discard unsolicited level poll responses
                (opcode 0x40) the device may interleave between non-poll commands.

        Returns:
            Parsed payload bytes on success, or ``None`` on timeout or
            parse failure.
        """
        from .protocol import OP_POLL
        self._send(report)
        for _ in range(10):
            data = self._recv(timeout_ms)
            if data is None:
                return None
            result = parse_frame(data)
            if result is None:
                log.debug("parse_frame rejected response")
                return None
            _src, _dst, _length, payload = result
            if skip_polls and payload and payload[0] == OP_POLL:
                log.debug("skip poll response (0x40) while awaiting reply")
                continue  # skip unsolicited level response
            return payload
        log.debug("no usable response after 10 receives")
        return None

    # --- High-level commands ---

    def init(self) -> bytes | None:
        """Send the init handshake (0x10).

        Returns:
            Response payload bytes, or ``None`` on timeout.
        """
        return self._send_recv(cmd_init())

    def poll_levels(self) -> dict | None:
        """Poll the device for current input/output level meter values.

        Returns:
            Dict with keys ``'inputs'`` (list[int], 4 channels),
            ``'outputs'`` (list[int], 4 channels), ``'limiter_mask'`` (int),
            and ``'state'`` (int). Returns ``None`` on error or timeout.
        """
        payload = self._send_recv(cmd_poll())
        if payload is None:
            return None
        return parse_levels(payload)

    def set_gain(self, channel: int, raw_value: int) -> bool:
        """Set gain for a channel.

        Args:
            channel: Unified channel index (inputs 0–3, outputs 4–7).
            raw_value: Raw gain 0–400. Use :func:`~minidsp.protocol.db_to_raw`
                to convert from dB.

        Returns:
            ``True`` if the device ACK'd, ``False`` on timeout or NACK.
        """
        payload = self._send_recv(cmd_gain(channel, raw_value))
        if payload is None:
            return False
        return is_ack(payload)

    def set_phase(self, channel: int, inverted: bool) -> bool:
        """Set phase polarity for a channel.

        Args:
            channel: Unified channel index (inputs 0–3, outputs 4–7).
            inverted: ``True`` for 180° inversion, ``False`` for normal polarity.

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_phase(channel, inverted))
        if payload is None:
            return False
        return is_ack(payload)

    def set_lopass(self, channel: int, freq_raw: int, slope: int = 0) -> bool:
        """Set the low-pass crossover for an output channel.

        Args:
            channel: Unified output channel index (4–7).
            freq_raw: Frequency raw value 0–300 (log scale;
                Hz = 19.70 × (20160/19.70)^(raw/300)).
            slope: Filter slope — 0x00=bypassed, 0x01–0x0A=active
                (see ``SLOPE_*`` constants in :mod:`minidsp.protocol`).

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_lopass(channel, freq_raw, slope))
        if payload is None:
            return False
        return is_ack(payload)

    def set_hipass(self, channel: int, freq_raw: int, slope: int = 0) -> bool:
        """Set the high-pass crossover for an output channel.

        Args:
            channel: Unified output channel index (4–7).
            freq_raw: Frequency raw value 0–300 (log scale;
                Hz = 19.70 × (20160/19.70)^(raw/300)).
            slope: Filter slope — 0x00=bypassed, 0x01–0x0A=active
                (see ``SLOPE_*`` constants in :mod:`minidsp.protocol`).

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_hipass(channel, freq_raw, slope))
        if payload is None:
            return False
        return is_ack(payload)

    def set_delay(self, channel: int, samples: int) -> bool:
        """Set output delay for a channel.

        Args:
            channel: Unified output channel index (4–7).
            samples: Delay in samples at 48 kHz, range 0–32640
                (ms = samples / 48, max ≈ 680 ms).

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_delay(channel, samples))
        if payload is None:
            return False
        return is_ack(payload)

    def set_delay_unit(self, unit: int) -> bool:
        """Set the delay display unit (display-only — protocol transmits samples).

        Args:
            unit: ``DELAY_UNIT_MS`` (0x00), ``DELAY_UNIT_M`` (0x01), or
                ``DELAY_UNIT_FT`` (0x02).

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_set_delay_unit(unit))
        if payload is None:
            return False
        return is_ack(payload)

    def set_test_tone(self, mode: int, freq_index: int = 0) -> bool:
        """Enable or disable the internal test tone generator.

        Args:
            mode: Generator mode — ``TONE_OFF`` (0x00), ``TONE_PINK`` (0x01),
                ``TONE_WHITE`` (0x02), or ``TONE_SINE`` (0x03).
            freq_index: Sine frequency index (``SINE_FREQ_*`` constants,
                0x00=20 Hz … 0x1E=20 kHz). Ignored for noise modes.

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_test_tone(mode, freq_index))
        if payload is None:
            return False
        return is_ack(payload)

    def set_channel_name(self, channel: int, name: str) -> bool:
        """Set the display name for a channel.

        Args:
            channel: Unified channel index (inputs 0–3, outputs 4–7).
            name: Up to 8 ASCII characters (truncated and zero-padded to 8 bytes).

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_set_channel_name(channel, name))
        if payload is None:
            return False
        return is_ack(payload)

    def set_gate(self, channel: int, attack: int, release: int,
                 hold: int, threshold: int) -> bool:
        """Set noise gate parameters for an input channel.

        Args:
            channel: 0-indexed input channel (0–3).
            attack: Attack raw value 34–998 (ms = raw + 1, range 1–999 ms).
            release: Release raw value 0–2999 (ms = raw + 1, range 0–3000 ms).
            hold: Hold raw value 9–998 (ms = raw + 1, range 10–999 ms).
            threshold: Threshold raw value 0–180
                (dB = raw × 0.5 − 90, range −90 to 0 dB).

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_gate(channel, attack, release, hold, threshold))
        if payload is None:
            return False
        return is_ack(payload)

    def mute(self, channel: int, mute: bool) -> bool:
        """Mute or unmute a channel.

        Args:
            channel: Unified channel index (inputs 0–3, outputs 4–7).
            mute: ``True`` to mute, ``False`` to unmute.

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_mute(channel, mute))
        if payload is None:
            return False
        return is_ack(payload)

    def read_config(self) -> dict | None:
        """Run the manufacturer startup sequence and read the active preset config.

        Replicates the exact 8-step command sequence the manufacturer software
        uses before reading config pages. Step 1 (init handshake) is already
        performed in :meth:`open`.

        Returns:
            Config dict in the same format as
            :func:`~minidsp.protocol.parse_preset_params`, augmented with
            ``'active_slot'`` (int | None) and ``'preset_names'`` (list[str]).
            Returns ``None`` on communication failure.

        Raises:
            DeviceLockedError: If the device lock is active (step 3 check).
                Call :meth:`submit_pin` first.
        """
        # Step 2: firmware string
        log.info("Step 2/8: firmware query (0x13)")
        if self._send_recv(cmd_firmware(), skip_polls=True) is None:
            log.warning("Step 2/8: firmware query — no response — device not ready")
            return None
        # Step 3: device info — also contains the lock status flag
        log.info("Step 3/8: device info (0x2C)")
        device_info_payload = self._send_recv(cmd_device_info(), skip_polls=True)
        if device_info_payload is None:
            log.warning("Step 3/8: device info — no response")
        else:
            info = parse_device_info(device_info_payload)
            if info and info.get("locked"):
                raise DeviceLockedError(
                    "Device is locked. Call submit_pin(pin) before read_config()."
                )
        # Step 4: preset header
        log.info("Step 4/8: preset header (0x22)")
        if self._send_recv(cmd_preset_header(), skip_polls=True) is None:
            log.warning("Step 4/8: preset header — no response")
        # Step 5: active preset index
        log.info("Step 5/8: active preset index (0x14)")
        preset_idx_payload = self._send_recv(cmd_preset_index(), skip_polls=True)
        if preset_idx_payload is None:
            log.warning("Step 5/8: active preset index — no response")
        active_slot = parse_preset_index(preset_idx_payload) if preset_idx_payload else None
        # Step 6: read all 30 preset names
        log.info("Step 6/8: reading 30 preset names (0x29)")
        preset_names: list[str] = []
        for slot in range(30):
            payload = self._send_recv(cmd_read_name(slot), skip_polls=True)
            if payload is None:
                log.warning("Step 6/8: preset name slot %d — no response", slot)
            result = parse_preset_name(payload) if payload else None
            preset_names.append(result[1] if result else "")
        # Step 7: read 9 config pages
        log.info("Step 7/8: reading %d config pages (0x27)", CONFIG_PAGES)
        config_data = bytearray()
        for page in range(CONFIG_PAGES):
            payload = self._send_recv(cmd_read_config(page), skip_polls=True)
            if payload is None:
                log.warning("Step 7/8: config page %d/%d — no response",
                            page, CONFIG_PAGES - 1)
                return None
            result = parse_config_page(payload)
            if result is None:
                log.warning("Step 7/8: config page %d/%d — parse failed (payload %d bytes)",
                            page, CONFIG_PAGES - 1, len(payload))
                return None
            _page_idx, data = result
            config_data.extend(data)
        # Step 8: activate
        log.info("Step 8/8: activate (0x12)")
        act = self._send_recv(cmd_activate(), skip_polls=True)
        if act is None or not is_ack(act):
            log.warning("Step 8/8: activate — no ACK (config data is valid but activation uncertain)")
        params = parse_preset_params(bytes(config_data))
        if params is None:
            log.warning("parse_preset_params failed on %d bytes of config data",
                        len(config_data))
            return None
        params["active_slot"] = active_slot
        params["preset_names"] = preset_names
        return params

    def load_preset(self, slot: int) -> dict | None:
        """Load a preset from the device (0x20) and re-read the config.

        Sequence: send load command → re-read 9 config pages → activate.

        Args:
            slot: Direct preset slot index — 0=F00, 1=U01, …, 30=U30.

        Returns:
            New config dict (same format as :meth:`read_config`), or ``None``
            on communication failure.
        """
        log.info("load_preset: sending 0x20 for slot %d", slot)
        payload = self._send_recv(cmd_load_preset(slot), skip_polls=True, timeout_ms=2000)
        if payload is None or not is_ack(payload):
            log.warning("load_preset: device did not ACK load command")
            return None
        # Re-read config pages (the device now has the new preset active)
        log.info("load_preset: reading %d config pages", CONFIG_PAGES)
        config_data = bytearray()
        for page in range(CONFIG_PAGES):
            payload = self._send_recv(cmd_read_config(page), skip_polls=True)
            if payload is None:
                log.warning("load_preset: config page %d — no response", page)
                return None
            result = parse_config_page(payload)
            if result is None:
                log.warning("load_preset: config page %d — parse failed", page)
                return None
            _page_idx, data = result
            config_data.extend(data)
        # Activate the new preset
        log.info("load_preset: sending activate")
        payload = self._send_recv(cmd_activate(), skip_polls=True)
        if payload is None or not is_ack(payload):
            log.warning("load_preset: activate — no ACK, preset may not be active")
            return None
        return parse_preset_params(bytes(config_data))

    def store_preset(self, slot: int, name: str) -> bool:
        """Store the active settings to a user preset slot (0x21).

        Sequence: send name (0x26) → send store (0x21) → activate.
        The device takes ~2 seconds to write to flash.

        Args:
            slot: User preset slot 1–30 (1=U01, …, 30=U30). Slot 0 (F00)
                raises ``ValueError`` in the underlying command builder.
            name: Up to 14 ASCII characters for the preset name.

        Returns:
            ``True`` if the device ACK'd the store command.
        """
        log.info("store_preset: sending name '%s' for slot %d", name, slot)
        payload = self._send_recv(cmd_store_preset_name(name), skip_polls=True)
        if payload is None:
            log.warning("store_preset: device did not respond to name command (0x26)")
            return False
        if payload[0] != 0x01:
            log.warning("store_preset: unexpected response to name command: %s",
                         payload.hex(" "))
            return False
        # 0x26 responds with 16-byte echo (01 02 + 14-char name), not a simple ACK
        if len(payload) == 16:
            echoed = payload[2:16].decode("ascii", errors="replace").rstrip()
            if echoed != name:
                log.warning("store_preset: name echo mismatch (sent=%r, got=%r)",
                            name, echoed)
        # Store command — device takes ~2s to write to flash
        log.info("store_preset: sending store (0x21) with 3s timeout")
        payload = self._send_recv(
            cmd_store_preset(slot), timeout_ms=3000, skip_polls=True)
        if payload is None:
            log.warning("store_preset: device did not respond to store command (0x21)")
            return False
        if not is_ack(payload):
            log.warning("store_preset: device did not ACK store command")
            return False
        # Activate after store
        log.info("store_preset: sending activate")
        payload = self._send_recv(cmd_activate(), skip_polls=True)
        if payload is None or not is_ack(payload):
            log.warning("store_preset: activate — no ACK")
            return False
        return True

    def set_peq_band(self, channel: int, band: int, gain_raw: int,
                     freq_raw: int, q_raw: int, filter_type: int,
                     bypass: bool = False) -> bool:
        """Set a single PEQ band for an output channel (0x33).

        Args:
            channel: Output channel index (0x04=Out1 … 0x07=Out4).
            band: 0-indexed band number (0–6 for bands 1–7).
            gain_raw: Raw gain 0–240 (dB = (raw − 120) / 10.0; 0 dB = 120).
            freq_raw: Raw frequency 0–300 (Hz = 19.70 × (20160/19.70)^(raw/300)).
            q_raw: Raw Q 0–100 (Q = 0.4 × 320^(raw/100)).
            filter_type: Filter shape — use ``PEQ_TYPE_*`` constants.
            bypass: ``True`` to bypass this band.

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_peq_band(channel, band, gain_raw, freq_raw,
                                               q_raw, filter_type, bypass))
        if payload is None:
            return False
        return is_ack(payload)

    def set_peq_channel_bypass(self, channel: int, bypass: bool) -> bool:
        """Bypass or restore all PEQ bands for an output channel (0x3C).

        Args:
            channel: Output channel index (0x04=Out1 … 0x07=Out4).
            bypass: ``True`` to bypass all bands, ``False`` to restore.

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_peq_channel_bypass(channel, bypass))
        if payload is None:
            return False
        return is_ack(payload)

    def set_compressor(self, channel: int, ratio: int, knee: int,
                       attack: int, release: int, threshold: int) -> bool:
        """Set compressor/limiter parameters for an output channel (0x30).

        Args:
            channel: Output channel index (0x04–0x07).
            ratio: Compression ratio enum 0–15 (see ``COMP_RATIO_*`` constants;
                0=1:1.0, 15=hard limiter).
            knee: Knee width 0–12 (direct dB; 0=hard knee).
            attack: Attack raw 0–998 (ms = raw + 1, range 1–999 ms).
            release: Release raw 9–2999 (ms = raw + 1, range 10–3000 ms).
            threshold: Threshold raw 0–220
                (dB = raw / 2 − 90, range −90 to +20 dB).

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(
            cmd_compressor(channel, ratio, knee, attack, release, threshold))
        if payload is None:
            return False
        return is_ack(payload)

    def set_matrix_route(self, output_ch: int, input_mask: int) -> bool:
        """Set the routing matrix for an output channel (0x3A).

        Args:
            output_ch: Output channel index (0x04=Out1 … 0x07=Out4).
            input_mask: Source bitmask
                (InA=0x01, InB=0x02, InC=0x04, InD=0x08; 0x00=silence).

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_matrix_route(output_ch, input_mask))
        if payload is None:
            return False
        return is_ack(payload)

    def prepare_link(self, master_ch: int, slave_ch: int) -> bool:
        """Declare a master-slave pair before linking channels (0x2A).

        Must be sent once per slave immediately before :meth:`set_channel_link`
        when linking. Not needed when unlinking.

        Args:
            master_ch: Unified channel index of the master (inputs 0–3, outputs 4–7).
            slave_ch: Unified channel index of the slave.

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_prepare_link(master_ch, slave_ch))
        if payload is None:
            return False
        return is_ack(payload)

    def set_channel_link(self, channel: int, link_flags: int) -> bool:
        """Set the channel link bitmask (0x3B).

        Send for every affected channel (both master and all slaves).
        Preceded by :meth:`prepare_link` per slave pair when linking.

        Args:
            channel: Unified channel index (inputs 0–3, outputs 4–7).
            link_flags: Bitmask within the 4-channel group.
                Master gets OR of all linked bits; slaves get 0x00.

        Returns:
            ``True`` if the device ACK'd.
        """
        payload = self._send_recv(cmd_channel_link(channel, link_flags))
        if payload is None:
            return False
        return is_ack(payload)

    def is_locked(self) -> bool | None:
        """Check whether the device lock is currently active.

        Sends a 0x2C device-info query and inspects byte 6 of the response.
        Discovered by comparing 0x2C responses across 3 captures:
        unlocked byte 6 = 0x00, locked byte 6 = 0x01.

        Returns:
            ``True`` if locked, ``False`` if unlocked, ``None`` if no response
            or the response could not be parsed.
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

        Call this before :meth:`read_config` when the device is locked. A
        locked device keeps ACKing 0x12 activate commands without proceeding
        to config load — it waits for a correct 0x2D PIN submission.

        Args:
            pin: Exactly 4 ASCII digit characters (e.g. ``"7654"``).

        Returns:
            ``True`` if the PIN was correct, ``False`` if wrong or no response.
        """
        payload = self._send_recv(cmd_submit_pin(pin), skip_polls=True)
        if payload is None:
            return False
        result = parse_pin_response(payload)
        return result is True

    def set_lock_pin(self, pin: str) -> bool:
        """Set the device lock PIN and immediately lock the device (0x2F).

        Warning:
            This **locks the device immediately** after the ACK is received.
            The current session ends — the device will not respond to further
            commands until the correct PIN is entered via :meth:`submit_pin`
            on the next connection. If the PIN is lost, the factory reset
            procedure is unknown.

        Args:
            pin: Exactly 4 ASCII digit characters (e.g. ``"7654"``).

        Returns:
            ``True`` if the device ACK'd before disconnecting.
        """
        payload = self._send_recv(cmd_set_lock_pin(pin))
        if payload is None:
            return False
        return is_ack(payload)
