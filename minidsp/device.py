"""
the t.racks DSP 4x4 Mini — USB HID device communication.

Implements the request/response protocol on top of a byte-level
:class:`~minidsp.transport.Transport`: framing, the init handshake and its
retries, response validation, and the high-level command methods. The
platform-specific I/O (``/dev/hidraw`` on Linux) lives in
:mod:`minidsp.transport` and is selected by
:func:`~minidsp.transport.default_transport`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable

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


from .transport import (
    DeviceBusyError,
    DeviceClosedError,
    HidrawTransport,
    Transport,
    default_transport,
)

# Back-compat: both names lived in this module before the transport split.
find_hidraw_device = HidrawTransport.find_device

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
    parse_firmware,
    parse_frame,
    parse_levels,
    parse_pin_response,
    parse_preset_index,
    parse_preset_name,
    parse_preset_params,
    DEVICE_HEADER_PIN,
    OP_READ_STORED_PAGE,
    STORED_WRITE_SIZE,
    cmd_read_device_header,
    cmd_write_device_header,
    cmd_restore_begin,
    cmd_select_stored_preset,
    cmd_read_stored_page,
    cmd_write_stored_page,
    cmd_reboot,
    device_header_with_pin,
    parse_device_header,
    parse_stored_page_ack,
)
from .unt import UNT_BLOB_SIZE, UntFile, slots_to_save


class DSPmini:
    """Interface to the t.racks DSP 4x4 Mini over USB HID.

    Device I/O is delegated to a :class:`~minidsp.transport.Transport`; by
    default :func:`~minidsp.transport.default_transport` picks the right one
    for the running platform. Every transport takes a **single-instance
    guard** in :meth:`open` (an ``fcntl.flock`` on Linux), so a second
    process — or a second :class:`DSPmini` instance — cannot talk to the
    device concurrently. The guard is released by :meth:`close`.

    Use as a context manager to guarantee release even on exceptions::

        with DSPmini() as dsp:
            cfg = dsp.read_config()

    Args:
        transport: Transport to use. Defaults to
            :func:`~minidsp.transport.default_transport`; pass an explicit
            one to force a backend or to inject a fake in tests.

    Note:
        The guard only binds cooperating processes — an ``flock`` is
        advisory and the Windows mutex is honoured by name — so neither
        prevents a raw open by an uncooperative program (e.g. the
        manufacturer Windows app under Wine).
    """

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport: Transport = transport or default_transport()

    # --- Connection ---

    def open(self, device_path: str | None = None) -> None:
        """Open the HID device, acquire the single-instance guard, and init.

        Delegates discovery, opening and locking to the transport. If the
        guard cannot be acquired the transport is closed again and a
        :class:`~minidsp.transport.DeviceBusyError` is raised — the caller
        does not need to call :meth:`close` in that case. That error is an
        ``OSError`` subclass, so a caller that only wants "could not open"
        needs no change, while a reconnect loop can single it out and keep
        waiting for the other process to finish.

        After locking, sends the init handshake (0x10) with up to 5 retries
        (0.5 s apart). If the device still does not respond, closes and raises.

        Args:
            device_path: Transport-specific device path (e.g.
                ``"/dev/hidraw0"`` on Linux). If ``None``, the transport
                auto-detects the device by VID/PID.

        Raises:
            DeviceBusyError: If the single-instance guard is already held by
                another process.
            OSError: If the device is not found or does not respond to the
                init handshake within 5 attempts.
        """
        self._transport.open(device_path)

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
        self._transport.close()
        raise OSError("Device opened but not responding to init handshake")

    def close(self) -> None:
        """Close the HID device and release the single-instance guard."""
        self._transport.close()

    def __enter__(self) -> DSPmini:
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- Low-level I/O ---

    def _send(self, report: bytes) -> None:
        """Send a 64-byte HID OUT report."""
        if not self._transport.is_open:
            raise DeviceClosedError("Device not open")
        if log.isEnabledFor(logging.DEBUG):
            log.debug("TX %s", _frame_hex(report))
        self._transport.write(report)

    def _recv(self, timeout_ms: int = 500) -> bytes | None:
        """Read a 64-byte HID IN report.

        Args:
            timeout_ms: Read timeout in milliseconds.

        Returns:
            Raw 64-byte report, or ``None`` on timeout or empty read.
        """
        data = self._transport.read(timeout_ms)
        if data is None:
            return None
        if log.isEnabledFor(logging.DEBUG):
            log.debug("RX %s", _frame_hex(data))
        return data

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
            Dict with keys ``'inputs'`` / ``'outputs'`` (list[int], legacy
            uint16 units), ``'inputs24'`` / ``'outputs24'`` (list[int], full
            24-bit levels), ``'limiter_mask'`` (int), ``'state'`` (int),
            ``'clip'`` (bool, device any-input clip flag) and ``'clipping'``
            (list[bool], per-channel editor clip rule for inputs 0–3 and
            outputs 4–7). See :func:`~minidsp.protocol.parse_levels`.
            Returns ``None`` on error or timeout.
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
            ``'active_slot'`` (int | None), ``'preset_names'`` (list[str]) and
            ``'firmware'`` (dict | None with ``'model'`` / ``'version'`` /
            ``'raw'``, parsed from the 0x13 response).
            Returns ``None`` on communication failure.

        Raises:
            DeviceLockedError: If the device lock is active (step 3 check).
                Call :meth:`submit_pin` first.
        """
        # Step 2: firmware string
        log.info("Step 2/8: firmware query (0x13)")
        fw_payload = self._send_recv(cmd_firmware(), skip_polls=True)
        if fw_payload is None:
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
        preset_names = self.read_preset_names()
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
        params["firmware"] = parse_firmware(fw_payload)
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

    def read_preset_names(self) -> list[str]:
        """Read the 30 user preset names (0x29 ×30).

        Returns:
            30 names in slot order (index 0 = U01). A never-stored slot reads
            ``"Default Preset"``; a slot whose name could not be read is ``""``.
        """
        names: list[str] = []
        for index in range(30):
            payload = self._send_recv(cmd_read_name(index), skip_polls=True)
            if payload is None:
                log.warning("preset name slot %d — no response", index)
            result = parse_preset_name(payload) if payload else None
            names.append(result[1] if result else "")
        return names

    # --- .unt save / restore (editor-identical sequences, ADR-0026) ---

    def read_device_header(self) -> dict | None:
        """Read the header block (0x19) — the ``.unt`` header bytes 0x10–0x31.

        Returns:
            Dict from :func:`~minidsp.protocol.parse_device_header` (active
            slot, PIN field, product name, ``'raw'`` …), or ``None`` on
            timeout or an invalid reply.
        """
        payload = self._send_recv(cmd_read_device_header(), skip_polls=True)
        if payload is None:
            log.warning("read_device_header: no response to 0x19")
            return None
        header = parse_device_header(payload)
        if header is None:
            log.warning("read_device_header: unexpected reply %s", payload.hex(" "))
        return header

    def _read_stored_slot(self, slot: int) -> bytes | None:
        """Select one stored preset (0x24) and read its 9 pages (0x28).

        Returns:
            The 450-byte stored config, or ``None`` on any failed exchange.
        """
        log.info("reading stored preset U%02d (0x24 + %d× 0x28)", slot, CONFIG_PAGES)
        ack = self._send_recv(cmd_select_stored_preset(slot), timeout_ms=1000, skip_polls=True)
        if ack is None or not is_ack(ack):
            log.warning("select stored preset U%02d (0x24): no ACK", slot)
            return None
        data = bytearray()
        for page in range(CONFIG_PAGES):
            payload = self._send_recv(cmd_read_stored_page(page), skip_polls=True)
            parsed = parse_config_page(payload, opcode=OP_READ_STORED_PAGE) if payload else None
            if parsed is None or parsed[0] != page:
                log.warning("stored preset U%02d page %d (0x28): no or bad reply", slot, page)
                return None
            data.extend(parsed[1])
        return bytes(data)

    def read_stored_presets(self, slots: Iterable[int]) -> dict[int, dict] | None:
        """Read stored user presets without recalling them (0x24 + 0x28).

        Same sequence as the editor's ``.unt`` save: per slot ``24 [slot]``
        (ACK after ~250 ms) and nine ``28 [page]`` reads, then one ``0x12``
        at the end — also after a failure. The live config and the audio are
        not touched (no ``0x20``).

        Args:
            slots: User preset slots 1–30 (1=U01, …, 30=U30).

        Returns:
            ``{slot: preset}`` where each preset dict holds ``'name'`` (str),
            ``'raw'`` (the 450-byte stored config), ``'unt_blob'`` (its first
            429 bytes, as stored in a ``.unt``) and ``'params'``
            (:func:`~minidsp.protocol.parse_preset_params`). ``None`` if any
            exchange fails.

        Raises:
            ValueError: If a slot is outside 1–30 (raised before any I/O).
        """
        slots = list(slots)
        for slot in slots:
            cmd_select_stored_preset(slot)  # validate all slots before talking to the device
        presets: dict[int, dict] | None = {}
        for slot in slots:
            raw = self._read_stored_slot(slot)
            if raw is None:
                presets = None
                break
            presets[slot] = {
                "name": raw[2:16].decode("ascii", errors="replace").rstrip(" \x00"),
                "raw": raw,
                "unt_blob": raw[:UNT_BLOB_SIZE],
                "params": parse_preset_params(raw),
            }
        act = self._send_recv(cmd_activate(), skip_polls=True)
        if act is None or not is_ack(act):
            log.warning("read_stored_presets: activate (0x12) — no ACK")
        return presets

    def read_stored_preset(self, slot: int) -> dict | None:
        """Read one stored preset without recalling it.

        Single-slot form of :meth:`read_stored_presets`.

        Args:
            slot: User preset slot 1–30.

        Returns:
            The preset dict (``'name'``, ``'raw'``, ``'unt_blob'``,
            ``'params'``), or ``None`` on communication failure.
        """
        presets = self.read_stored_presets([slot])
        return presets[slot] if presets else None

    def export_unt(self, preset_names: list[str] | None = None) -> UntFile | None:
        """Build a ``.unt`` file from the device's stored presets, like the editor.

        Reads the header block (0x19) and every slot not named
        ``"Default Preset"`` (:meth:`read_stored_presets`). The result is the
        file the editor writes, byte for byte; nothing on the device changes.

        Note:
            Presets are saved in their *stored* form, as by the editor:
            unsaved live edits of the active slot are not included. Store
            them first (:meth:`store_preset`) or patch them in with
            :meth:`minidsp.unt.UntFile.set_slot_params`.

        Args:
            preset_names: The 30 names from ``read_config()['preset_names']``
                or :meth:`read_preset_names`; read from the device when
                ``None``.

        Returns:
            The :class:`~minidsp.unt.UntFile`, or ``None`` on communication
            failure.
        """
        names = preset_names if preset_names is not None else self.read_preset_names()
        header = self.read_device_header()
        if header is None:
            return None
        stored = self.read_stored_presets(slots_to_save(names))
        if stored is None:
            return None
        unt = UntFile.from_header_block(header["raw"])
        for slot, preset in stored.items():
            unt.set_slot_blob(slot, preset["unt_blob"])
        return unt

    def restore_unt(self, unt: UntFile, *, confirm: bool = False,
                    keep_device_pin: bool = True) -> bool:
        """Write a ``.unt`` file to the device and reboot it, like the editor.

        Sequence (capture-verified): ``0x23`` begin restore (ACK after
        ~1.6 s) → ``0x1a`` header bytes 0x11–0x31 → per filled slot nine
        ``0x25`` page writes (419 bytes, each echo-checked) → ``0x04`` reboot.
        After the reboot command the handle is closed: the device drops off
        USB and re-enumerates, so call :meth:`open` again after a few seconds.

        Warning:
            This rewrites preset flash. Only the file's filled slots are
            written; whether slots that are empty in the file get erased is
            not verified yet. Bytes 419–428 of each preset (test tone, delay
            display unit, Out1 PEQ channel bypass) are not sent — the editor
            does not send them either. F00 is never written.

        Args:
            unt: The file to restore.
            confirm: Must be ``True``; guards against accidental calls.
            keep_device_pin: Keep the device's current lock PIN (read with
                0x19 first) instead of the file's PIN field. ``False`` sends
                the file header exactly like the editor.

        Returns:
            ``True`` if every step was acknowledged and the reboot was sent.
            ``False`` if a step failed; the handle stays open and the device
            may hold a partially restored set of presets.

        Raises:
            ValueError: If ``confirm`` is not ``True`` or the file holds no
                presets (``0x23`` might erase every slot).
        """
        if not confirm:
            raise ValueError("restore_unt rewrites the device presets and reboots it; "
                             "pass confirm=True")
        slots = unt.filled_slots()
        if not slots:
            raise ValueError("the .unt file holds no presets — refusing to restore it")
        block = unt.header_block
        if keep_device_pin:
            current = self.read_device_header()
            if current is None:
                log.warning("restore_unt: cannot read the device PIN (0x19) — nothing written")
                return False
            block = device_header_with_pin(block, current["raw"][DEVICE_HEADER_PIN])

        log.info("restore_unt: begin restore (0x23), slots %s", slots)
        ack = self._send_recv(cmd_restore_begin(), timeout_ms=3000, skip_polls=True)
        if ack is None or not is_ack(ack):
            log.warning("restore_unt: begin restore (0x23) — no ACK, nothing written")
            return False
        ack = self._send_recv(cmd_write_device_header(block[1:]), timeout_ms=1000, skip_polls=True)
        if ack is None or not is_ack(ack):
            log.warning("restore_unt: header write (0x1a) — no ACK")
            return False
        for slot in slots:
            blob = unt.slot_blob(slot)
            for page in range(CONFIG_PAGES):
                start = page * CONFIG_PAGE_SIZE
                data = blob[start:min(start + CONFIG_PAGE_SIZE, STORED_WRITE_SIZE)]
                # the last page of a slot takes ~170 ms (flash commit)
                timeout = 1000 if page == CONFIG_PAGES - 1 else 500
                reply = self._send_recv(cmd_write_stored_page(slot, page, data),
                                        timeout_ms=timeout, skip_polls=True)
                if reply is None or not parse_stored_page_ack(reply, page):
                    log.warning("restore_unt: U%02d page %d (0x25) — no echo", slot, page)
                    return False
        log.info("restore_unt: reboot (0x04) — closing the handle")
        self._send(cmd_reboot())
        self.close()
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
            pin: Exactly 4 ASCII characters (e.g. ``"7654"``).

        Returns:
            ``True`` if the PIN was correct, ``False`` if wrong or no response.
        """
        payload = self._send_recv(cmd_submit_pin(pin), skip_polls=True)
        if payload is None:
            return False
        result = parse_pin_response(payload)
        return result is True

    def set_lock_pin(self, pin: str) -> bool:
        """Set the device lock PIN (0x2F).

        On receipt the device flips its internal lock flag and sends a
        ``0x01`` ACK. The USB session itself remains nominally alive — it is
        the **caller's** responsibility to tear down the connection after
        the ACK; subsequent commands on the same handle will not succeed.
        Reopening the device puts it in the locked state (see
        :meth:`is_locked` / the ``0x2c`` lock byte) and requires
        :meth:`submit_pin` to unlock.

        Example:
            >>> if dsp.set_lock_pin(pin):
            ...     dsp.close()

        Warning:
            If the PIN is lost, the factory-reset procedure is unknown.
            Treat this as a footgun and confirm with the user before
            invoking from automation.

        Args:
            pin: Exactly 4 ASCII characters (e.g. ``"7654"``).

        Returns:
            ``True`` if the device ACK'd, ``False`` on timeout / no response.
        """
        payload = self._send_recv(cmd_set_lock_pin(pin))
        if payload is None:
            return False
        return is_ack(payload)
