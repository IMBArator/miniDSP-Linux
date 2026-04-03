"""Background thread for DSPmini device communication.

Owns the DSPmini instance, runs the poll loop, and dispatches
gain/mute commands via a coalescing dict (thread-safe).
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QThread, Signal

from ..device import DSPmini

log = logging.getLogger(__name__)


class DeviceThread(QThread):
    """Polls levels and sends commands on a background thread."""

    levels_updated = Signal(dict)
    connection_changed = Signal(bool)
    config_loaded = Signal(dict)  # {'gains': list[8], 'mutes': list[8]}

    POLL_INTERVAL_MS = 150
    RECONNECT_INTERVAL_MS = 2000
    MAX_CONSECUTIVE_FAILURES = 3

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop = False
        self._lock = threading.Lock()
        self._pending_gains: dict[int, int] = {}
        self._pending_mutes: dict[int, bool] = {}

    # --- Thread-safe command interface (called from main thread) ---

    def request_gain(self, channel: int, raw_value: int) -> None:
        with self._lock:
            self._pending_gains[channel] = raw_value

    def request_mute(self, channel: int, mute: bool) -> None:
        with self._lock:
            self._pending_mutes[channel] = mute

    def request_stop(self) -> None:
        self._stop = True

    # --- Thread body ---

    def run(self) -> None:
        while not self._stop:
            dsp = DSPmini()
            if not self._try_connect(dsp):
                continue  # retry or stop

            log.info("Connected to DSPmini")
            self.connection_changed.emit(True)
            # Read initial config (gain/mute state) before polling
            log.info("Reading device config...")
            config = dsp.read_config()
            if config is not None:
                log.info("Config loaded: gains=%s mutes=%s", config["gains"], config["mutes"])
                self.config_loaded.emit(config)
            else:
                log.warning("Config read failed")
            log.info("Starting poll loop")
            self._poll_loop(dsp)
            log.info("Poll loop exited, closing device")
            dsp.close()
            self.connection_changed.emit(False)

    def _try_connect(self, dsp: DSPmini) -> bool:
        """Attempt to open the device, retrying every 2s until stopped."""
        while not self._stop:
            try:
                dsp.open()
                return True
            except OSError:
                log.debug("Device not found, retrying in %dms", self.RECONNECT_INTERVAL_MS)
                for _ in range(self.RECONNECT_INTERVAL_MS // 100):
                    if self._stop:
                        return False
                    self.msleep(100)
        return False

    def _poll_loop(self, dsp: DSPmini) -> None:
        """Main polling loop — drain commands, poll levels, repeat."""
        failures = 0

        while not self._stop:
            # 1. Drain pending commands
            self._send_pending(dsp)

            # 2. Poll levels
            levels = dsp.poll_levels()
            if levels is not None:
                failures = 0
                self.levels_updated.emit(levels)
            else:
                failures += 1
                log.warning("Poll failed (%d/%d)", failures, self.MAX_CONSECUTIVE_FAILURES)
                if failures >= self.MAX_CONSECUTIVE_FAILURES:
                    log.error("Too many poll failures, disconnecting")
                    return  # disconnect — caller will emit signal and retry

            # 3. Sleep
            self.msleep(self.POLL_INTERVAL_MS)

    def _send_pending(self, dsp: DSPmini) -> None:
        """Send coalesced gain/mute commands."""
        with self._lock:
            gains = dict(self._pending_gains)
            mutes = dict(self._pending_mutes)
            self._pending_gains.clear()
            self._pending_mutes.clear()

        for ch, raw in gains.items():
            dsp.set_gain(ch, raw)

        for ch, mute in mutes.items():
            dsp.mute(ch, mute)
