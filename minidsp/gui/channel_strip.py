"""Channel strip widget — vertical fader + level meter + mute button + compressor LED."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..protocol import raw_to_db
from .level_meter import LevelMeter

# Gain slider range maps 1:1 to raw device values (0–400)
GAIN_RAW_MIN = 0    # -60.0 dB
GAIN_RAW_MAX = 400  # +12.0 dB
GAIN_RAW_DEFAULT = 280  # 0.0 dB


def _format_db(raw: int) -> str:
    db = raw_to_db(raw)
    if db <= -60.0:
        return "-inf dB"
    return f"{db:+.1f} dB"


class CompressorLED(QWidget):
    """Small circular LED indicator for compressor/limiter activity."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self.setFixedSize(16, 16)

    def set_active(self, active: bool) -> None:
        if active != self._active:
            self._active = active
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(255, 160, 0) if self._active else QColor(60, 60, 60)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 12, 12)
        p.end()


class ChannelStrip(QWidget):
    """Single channel strip: label, dB readout, fader, meter, mute, LED."""

    gain_changed = Signal(int, int)   # (channel, raw_value)
    mute_changed = Signal(int, bool)  # (channel, mute_state)

    def __init__(
        self,
        label: str,
        channel: int,
        is_output: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._channel = channel
        self._is_output = is_output

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Channel label
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(lbl)

        # dB readout
        self._db_label = QLabel(_format_db(GAIN_RAW_DEFAULT))
        self._db_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._db_label.setStyleSheet("font-size: 10px; color: #bbbbbb;")
        self._db_label.setFixedHeight(16)
        layout.addWidget(self._db_label)

        # Fader + meter row
        fader_row = QHBoxLayout()
        fader_row.setSpacing(2)

        self._slider = QSlider(Qt.Orientation.Vertical)
        self._slider.setRange(GAIN_RAW_MIN, GAIN_RAW_MAX)
        self._slider.setValue(GAIN_RAW_DEFAULT)
        self._slider.setMinimumHeight(200)
        fader_row.addWidget(self._slider)

        self._meter = LevelMeter()
        fader_row.addWidget(self._meter)

        layout.addLayout(fader_row, stretch=1)

        # Mute button
        self._mute_btn = QPushButton("MUTE")
        self._mute_btn.setCheckable(True)
        self._mute_btn.setFixedHeight(28)
        self._update_mute_style(False)
        layout.addWidget(self._mute_btn)

        # Compressor LED (output channels only)
        self._comp_led: CompressorLED | None = None
        if is_output:
            led_row = QHBoxLayout()
            led_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._comp_led = CompressorLED()
            led_row.addWidget(self._comp_led)
            layout.addLayout(led_row)

        # Connections
        self._slider.valueChanged.connect(self._on_slider_moved)
        self._mute_btn.toggled.connect(self._on_mute_toggled)

    # --- Public interface ---

    @property
    def meter(self) -> LevelMeter:
        return self._meter

    def set_level(self, value: int) -> None:
        self._meter.set_level(value)

    def set_compressor_active(self, active: bool) -> None:
        if self._comp_led is not None:
            self._comp_led.set_active(active)

    def set_initial_state(self, gain_raw: int, muted: bool) -> None:
        """Set fader and mute from device config without emitting signals."""
        self._slider.blockSignals(True)
        self._slider.setValue(gain_raw)
        self._slider.blockSignals(False)
        self._db_label.setText(_format_db(gain_raw))

        self._mute_btn.blockSignals(True)
        self._mute_btn.setChecked(muted)
        self._mute_btn.blockSignals(False)
        self._update_mute_style(muted)

    def set_enabled_state(self, enabled: bool) -> None:
        """Enable/disable controls (not the widget itself, so meters still paint)."""
        self._slider.setEnabled(enabled)
        self._mute_btn.setEnabled(enabled)
        if not enabled:
            self._meter.reset()
            if self._comp_led:
                self._comp_led.set_active(False)

    # --- Slots ---

    def _on_slider_moved(self, raw: int) -> None:
        self._db_label.setText(_format_db(raw))
        self.gain_changed.emit(self._channel, raw)

    def _on_mute_toggled(self, checked: bool) -> None:
        self._update_mute_style(checked)
        self.mute_changed.emit(self._channel, checked)

    def _update_mute_style(self, muted: bool) -> None:
        if muted:
            self._mute_btn.setStyleSheet(
                "QPushButton { background-color: #cc0000; color: white; "
                "font-weight: bold; border: 1px solid #880000; }"
            )
        else:
            self._mute_btn.setStyleSheet(
                "QPushButton { background-color: #444444; color: #cccccc; "
                "border: 1px solid #666666; }"
            )
