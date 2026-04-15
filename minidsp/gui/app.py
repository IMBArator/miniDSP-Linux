"""Application entry point — dark-themed PySide6 app."""

from __future__ import annotations

import signal
import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def _apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(50, 50, 50))
    p.setColor(QPalette.ColorRole.WindowText, QColor(200, 200, 200))
    p.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
    p.setColor(QPalette.ColorRole.Text, QColor(200, 200, 200))
    p.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(200, 200, 200))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Highlight, QColor(80, 120, 180))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(p)


def run_gui() -> None:
    # Root logger is configured by minidsp.cli.main() based on -v/-vv flags;
    # use `uv run minidsp -vv gui` to restore the old DEBUG default.

    # Let Ctrl+C work from the terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    _apply_dark_theme(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
