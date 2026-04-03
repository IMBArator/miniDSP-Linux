"""Main window — 4 input + 4 output channel strips with device thread."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .channel_strip import ChannelStrip
from .device_thread import DeviceThread

NUM_CHANNELS = 4


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DSP 4x4 Mini")
        self.setMinimumSize(700, 480)

        self._input_strips: list[ChannelStrip] = []
        self._output_strips: list[ChannelStrip] = []

        self._build_ui()
        self._build_device_thread()
        self._set_controls_enabled(False)

    # --- UI construction ---

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        # Input section
        input_section = QVBoxLayout()
        input_label = QLabel("INPUTS")
        input_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        input_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        input_section.addWidget(input_label)

        input_row = QHBoxLayout()
        for i in range(NUM_CHANNELS):
            strip = ChannelStrip(f"In {i + 1}", channel=i, is_output=False)
            input_row.addWidget(strip)
            self._input_strips.append(strip)
        input_section.addLayout(input_row)
        root.addLayout(input_section)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        # Output section
        output_section = QVBoxLayout()
        output_label = QLabel("OUTPUTS")
        output_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        output_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        output_section.addWidget(output_label)

        output_row = QHBoxLayout()
        for i in range(NUM_CHANNELS):
            strip = ChannelStrip(f"Out {i + 1}", channel=i + 4, is_output=True)
            output_row.addWidget(strip)
            self._output_strips.append(strip)
        output_section.addLayout(output_row)
        root.addLayout(output_section)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Waiting for DSP 4x4 Mini...")

    def _build_device_thread(self) -> None:
        self._thread = DeviceThread(self)
        self._thread.levels_updated.connect(self._on_levels)
        self._thread.connection_changed.connect(self._on_connection)
        self._thread.config_loaded.connect(self._on_config_loaded)

        # Wire channel strip signals to device thread
        for strip in self._input_strips + self._output_strips:
            strip.gain_changed.connect(self._thread.request_gain)
            strip.mute_changed.connect(self._thread.request_mute)

        self._thread.start()

    # --- Slots ---

    def _on_levels(self, levels: dict) -> None:
        for i in range(NUM_CHANNELS):
            self._input_strips[i].set_level(levels["inputs"][i])
            self._output_strips[i].set_level(levels["outputs"][i])

        # Compressor LED from limiter_mask bitmask
        mask = levels.get("limiter_mask", 0)
        for i in range(NUM_CHANNELS):
            self._output_strips[i].set_compressor_active(bool(mask & (1 << i)))

    def _on_config_loaded(self, config: dict) -> None:
        gains = config["gains"]   # list[8]: inputs 0–3, outputs 4–7
        mutes = config["mutes"]   # list[8]: inputs 0–3, outputs 4–7
        for i in range(NUM_CHANNELS):
            self._input_strips[i].set_initial_state(gains[i], mutes[i])
            self._output_strips[i].set_initial_state(gains[i + 4], mutes[i + 4])

    def _on_connection(self, connected: bool) -> None:
        self._set_controls_enabled(connected)
        if connected:
            self._status.showMessage("Connected to DSP 4x4 Mini")
        else:
            self._status.showMessage("DSPmini disconnected \u2014 waiting for reconnection...")

    def _set_controls_enabled(self, enabled: bool) -> None:
        for strip in self._input_strips + self._output_strips:
            strip.set_enabled_state(enabled)

    # --- Lifecycle ---

    def closeEvent(self, event) -> None:
        self._thread.request_stop()
        self._thread.wait(2000)
        event.accept()
