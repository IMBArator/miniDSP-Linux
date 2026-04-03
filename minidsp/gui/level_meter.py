"""Vertical audio level meter with peak hold indicator and dB-scaled display."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

PEAK_DECAY = 0.93   # ~7% drop per update cycle
EMA_ALPHA = 0.55    # smoothing factor: 0=frozen, 1=no smoothing

# Calibrated from captures at known analog levels:
#   0 dBu  → uint16 ~188 → manufacturer shows first yellow LED (~75%)
#  -30 dBu → uint16 ~5   → manufacturer shows 2 green LEDs (~25%)
# Two-point dB calibration: REF_LEVEL = 188 * 10^(15.75/20) ≈ 1153
REF_LEVEL = 1153    # uint16 value that maps to 0 dB (meter top)
DB_RANGE = 63.0     # meter spans -63 dB to 0 dB


def _to_db_fraction(value: float) -> float:
    """Convert a linear uint16 level to a 0.0–1.0 fraction on a dB-scaled meter.

    Calibrated so that 0 dBu (~188) appears at 75% and -30 dBu (~5) at 25%.
    """
    if value <= 0:
        return 0.0
    db = 20.0 * math.log10(value / REF_LEVEL)
    return max(0.0, min(1.0, (db + DB_RANGE) / DB_RANGE))


class LevelMeter(QWidget):
    """Vertical bar meter with EMA smoothing, peak hold, dB-scaled gradient."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = 0.0
        self._peak = 0.0
        self.setMinimumWidth(16)
        self.setMaximumWidth(24)
        self.setMinimumHeight(200)

    def set_level(self, value: int) -> None:
        """Update the current level (uint16 from device) with EMA smoothing and peak hold."""
        clamped = max(0.0, float(value))
        # Exponential moving average for smooth bar movement
        self._level = EMA_ALPHA * clamped + (1 - EMA_ALPHA) * self._level
        if self._level >= self._peak:
            self._peak = self._level
        else:
            self._peak *= PEAK_DECAY
        self.update()

    def reset(self) -> None:
        """Zero out level and peak (e.g. on disconnect)."""
        self._level = 0.0
        self._peak = 0.0
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter()
        if not p.begin(self):
            return
        try:
            w, h = self.width(), self.height()

            # Background
            p.fillRect(0, 0, w, h, QColor(30, 30, 30))

            # Level bar (bottom-up, dB-scaled)
            frac = _to_db_fraction(self._level)
            bar_h = int(frac * h)
            if bar_h > 0:
                bar_top = h - bar_h
                grad = QLinearGradient(0, h, 0, 0)
                grad.setColorAt(0.0, QColor(0, 180, 0))
                grad.setColorAt(0.70, QColor(0, 200, 0))
                grad.setColorAt(0.75, QColor(220, 200, 0))   # 0 dBu boundary
                grad.setColorAt(0.88, QColor(220, 60, 0))
                grad.setColorAt(1.0, QColor(220, 0, 0))
                p.fillRect(1, bar_top, w - 2, bar_h, grad)

            # Peak hold marker (white horizontal line)
            peak_frac = _to_db_fraction(self._peak)
            if peak_frac > 0.01:
                peak_y = h - int(peak_frac * h)
                p.setPen(QColor(255, 255, 255))
                p.drawLine(1, peak_y, w - 2, peak_y)
        finally:
            p.end()
