"""The Markers panel (SPEC.md section 10): which trace the markers measure, which automatic
markers are on, the user's markers, how they look, and a table of all their values.

The panel only switches and shows. The state and the rules are the plot's (gui/bode_plot.py,
markers.py); the plot says when the markers were worked out again and the panel follows.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..markers import KINDS, MAX_USER
from . import theme
from .bode_plot import MARKER_TEXT

COLUMNS = ("Marker", "Frequency", "Gain", "Phase", "Note")


class MarkersPanel(QWidget):
    color_changed = Signal(str)         # "#rrggbb", or "" for the theme's colour

    def __init__(self, plot, parent=None):
        super().__init__(parent)
        self.plot = plot
        self.color = plot.marker_color()
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        self.trace_label = QLabel("Markers on")
        self.trace_box = QComboBox()
        # a fixed width whatever the traces are called, as the plot's own trace box
        self.trace_box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.trace_box.setMinimumContentsLength(14)
        self.trace_box.setToolTip("The trace the markers measure: all automatic markers and your own read this one "
                                  "trace, as it is drawn")
        self.trace_label.setToolTip(self.trace_box.toolTip())
        row.addWidget(self.trace_label)
        row.addWidget(self.trace_box, 1)
        lay.addLayout(row)

        grid = QGridLayout()
        self.kind_boxes: dict[str, QCheckBox] = {}
        for i, kind in enumerate(KINDS):
            text, tip = MARKER_TEXT[kind]
            box = QCheckBox(text)
            box.setToolTip(tip)
            box.toggled.connect(lambda on, k=kind: self.plot.set_marker_kind(k, on))
            grid.addWidget(box, i // 2, i % 2)
            self.kind_boxes[kind] = box
        lay.addLayout(grid)

        self.table = QTreeWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHeaderLabels(list(COLUMNS))
        self.table.setRootIsDecorated(False)
        self.table.setToolTip("Every marker with its frequency, gain and phase on the chosen trace. 'none': the "
                              "marker is switched on, and this curve has none.")
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.add_btn = QPushButton("Add marker")
        self.add_btn.setToolTip("Put a marker of your own in the middle of the visible frequency range; drag it, or "
                                "right-click it to type its frequency (up to %d). A right-click on the plot adds "
                                "one at that place." % MAX_USER)
        self.clear_btn = QPushButton("Remove all")
        self.clear_btn.setToolTip("Remove every marker of your own; the automatic markers stay as ticked")
        self.copy_btn = QPushButton("Copy values")
        self.copy_btn.setToolTip("Copy the markers as a table (name, frequency, gain, phase, note) for a report or "
                                 "a spreadsheet")
        for b in (self.add_btn, self.clear_btn, self.copy_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.values_box = QCheckBox("Values on the plot")
        self.values_box.setChecked(plot.marker_values())
        self.values_box.setToolTip("Write frequency, gain and phase next to each marker on the plot. Without it a "
                                   "marker carries its name only and the numbers are read in this table.")
        self.color_btn = QPushButton("Colour…")
        self.color_btn.setToolTip("Choose the colour of the marker lines, dots and labels on the plot. The exported "
                                  "image keeps its own dark grey for the white background.")
        self.default_color_btn = QPushButton("Default colour")
        self.default_color_btn.setToolTip("Go back to the theme's own marker colour, a neutral light grey")
        row.addWidget(self.values_box)
        row.addStretch(1)
        row.addWidget(self.color_btn)
        row.addWidget(self.default_color_btn)
        lay.addLayout(row)

        self.trace_box.activated.connect(lambda i: self.plot.set_marker_trace(self.trace_box.itemData(i)))
        self.add_btn.clicked.connect(lambda _checked=False: self.plot.add_marker())
        self.clear_btn.clicked.connect(lambda _checked=False: self.plot.clear_markers())
        self.copy_btn.clicked.connect(lambda _checked=False: self.plot.copy_markers())
        self.values_box.toggled.connect(lambda on: self.plot.set_marker_values(on))
        self.color_btn.clicked.connect(lambda _checked=False: self._choose_color())
        self.default_color_btn.clicked.connect(lambda _checked=False: self.set_color(""))
        plot.markers_changed.connect(self.refresh)
        self.refresh()

    # ---- colour
    def set_color(self, color) -> None:
        """"#rrggbb", or "" for the theme's colour; anything else is ignored."""
        if not self.plot.set_marker_color(color):
            return
        self.color = self.plot.marker_color()
        self.color_changed.emit(self.color)

    def _choose_color(self) -> None:
        c = QColorDialog.getColor(QColor(self.color or theme.MARK_INK), self, "Marker colour")
        if c.isValid():
            self.set_color(c.name())

    # ---- following the plot
    def refresh(self) -> None:
        """Show what the plot holds now: the trace, the ticks, the look, the table."""
        plot = self.plot
        self.color = plot.marker_color()
        pix = QPixmap(12, 12)
        pix.fill(QColor(self.color or theme.MARK_INK))
        self.color_btn.setIcon(QIcon(pix))
        self.default_color_btn.setEnabled(bool(self.color))
        self.trace_box.blockSignals(True)
        self.trace_box.clear()
        for t in plot.set.traces:
            self.trace_box.addItem(t.name, t.id)
        self.trace_box.setCurrentIndex(max(0, self.trace_box.findData(plot.markers.trace_id)))
        self.trace_box.blockSignals(False)
        on = plot.marker_kinds()
        for kind, box in self.kind_boxes.items():
            if box.isChecked() != (kind in on):
                box.blockSignals(True)
                box.setChecked(kind in on)
                box.blockSignals(False)
        if self.values_box.isChecked() != plot.marker_values():
            self.values_box.blockSignals(True)
            self.values_box.setChecked(plot.marker_values())
            self.values_box.blockSignals(False)
        self.add_btn.setEnabled(plot.can_add_marker())
        self.clear_btn.setEnabled(bool(plot.markers.user))
        rows = plot.marker_rows()
        self.table.clear()
        for r in rows:
            self.table.addTopLevelItem(QTreeWidgetItem(list(r)))
        for c in range(len(COLUMNS) - 1):
            self.table.resizeColumnToContents(c)
