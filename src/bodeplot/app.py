"""QApplication bootstrap."""
from __future__ import annotations

import sys


def run(simulate: bool | None = None, debug: bool = False) -> int:
    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow
    from .logging_setup import setup_logging

    setup_logging(debug)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("bodeplot")
    from .gui import theme
    theme.apply(app)
    win = MainWindow(simulate=simulate)
    win.show()
    return app.exec()
