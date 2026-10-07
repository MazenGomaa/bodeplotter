"""Bottom dock: per-point table plus a free-text log (SPEC.md section 10)."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QPlainTextEdit, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..models import LogEntry, PointResult
from ..units import fmt_si

HEADERS = ["Time", "Frequency", "Gain (dB)", "Phase (deg)", "V/div ref", "V/div DUT", "Retries",
           "Flags", "Duration (s)"]


class StatusLog(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(5000)
        split.addWidget(self.table)
        split.addWidget(self.text)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        self.copy_btn = QPushButton("Copy")
        self.clear_btn = QPushButton("Clear")
        self.copy_btn.setToolTip("Copy the table of measured points and the messages to the clipboard, "
                                 "tab-separated: it pastes into a spreadsheet.")
        self.clear_btn.setToolTip("Empty the table of measured points and the messages. The plot and the "
                                  "sweep result are not touched.")
        row.addStretch(1)
        row.addWidget(self.copy_btn)
        row.addWidget(self.clear_btn)
        lay.addLayout(row)
        self.copy_btn.clicked.connect(self.copy)
        self.clear_btn.clicked.connect(self.clear)

    def add_point(self, p: PointResult) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        cells = [datetime.now().strftime("%H:%M:%S"), fmt_si(p.freq_hz, "Hz"), "%.3f" % p.gain_db,
                 "%.2f" % p.phase_deg, fmt_si(p.vdiv_ref, "V", 3), fmt_si(p.vdiv_dut, "V", 3), str(p.retries),
                 ", ".join(p.flags.names()), "%.2f" % p.duration_s]
        for c, text in enumerate(cells):
            self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.scrollToBottom()

    def add_log(self, e: LogEntry) -> None:
        stamp = e.time[11:19] if len(e.time) >= 19 else datetime.now().strftime("%H:%M:%S")
        self.text.appendPlainText("%s  %-5s %s" % (stamp, e.level.upper(), e.text))

    def as_text(self) -> str:
        lines = ["\t".join(HEADERS)]
        for r in range(self.table.rowCount()):
            lines.append("\t".join(self.table.item(r, c).text() if self.table.item(r, c) else ""
                                   for c in range(self.table.columnCount())))
        return "\n".join(lines) + "\n\n" + self.text.toPlainText()

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self.as_text())

    def clear(self) -> None:
        self.table.setRowCount(0)
        self.text.clear()

    def clear_points(self) -> None:
        self.table.setRowCount(0)
