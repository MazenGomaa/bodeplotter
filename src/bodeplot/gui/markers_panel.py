"""The Markers panel (SPEC.md section 10): which trace the markers measure, which automatic
markers are on, a table of all their values, the user's markers, and how they look.

The panel only switches and shows. The state and the rules are the plot's (gui/bode_plot.py,
markers.py); the plot says when the markers were worked out again and the panel follows.

Its order is content first: the table takes every pixel the switches above it and the two
rows below it leave (user's review of 2026-10-07: the table had been squeezed to two rows).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..markers import KINDS, MAX_USER
from . import theme
from .bode_plot import MARKER_TEXT
from .color_menu import palette_menu, swatch

COLUMNS = ("Marker", "Frequency", "Gain", "Phase", "Note")
FIGURES = (1, 2, 3)                     # the columns of numbers: right-aligned, so that digits line up


class MarkersPanel(QWidget):
    def __init__(self, plot, parent=None):
        super().__init__(parent)
        self.plot = plot
        self.open_menu = None           # the palette that a click on a colour square opened last
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        self.trace_label = QLabel("Markers on")
        self.trace_box = QComboBox()
        # a small fixed width whatever the traces are called: the list that drops down shows the full names
        self.trace_box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.trace_box.setMinimumContentsLength(8)
        self.trace_box.setToolTip("The trace the markers measure: all automatic markers and your own read this one "
                                  "trace, as it is drawn")
        self.trace_label.setToolTip(self.trace_box.toolTip())
        row.addWidget(self.trace_label)
        row.addWidget(self.trace_box, 1)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.kind_boxes: dict[str, QCheckBox] = {}
        for kind in KINDS:
            text, tip = MARKER_TEXT[kind]
            box = QCheckBox(text)
            box.setToolTip(tip)
            box.toggled.connect(lambda on, k=kind: self.plot.set_marker_kind(k, on))
            row.addWidget(box)
            self.kind_boxes[kind] = box
        row.addStretch(1)
        lay.addLayout(row)

        self.table = QTreeWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHeaderLabels(list(COLUMNS))
        self.table.setRootIsDecorated(False)
        self.table.setMinimumWidth(0)
        for c in FIGURES:
            self.table.headerItem().setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
        self.table.setToolTip("Every marker with its frequency, gain and phase on the chosen trace. Click a "
                              "marker's colour square to choose its colour. 'none': the marker is switched "
                              "on, and this curve has none.")
        self.table.itemClicked.connect(self._item_clicked)
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

        # how the labels look: changed once in a while, so one quiet row at the bottom
        row = QHBoxLayout()
        self.values_box = QCheckBox("Values on the plot")
        self.values_box.setChecked(plot.marker_values())
        self.values_box.setToolTip("Write frequency, gain and phase next to each marker on the plot. Without it a "
                                   "marker carries its name only and the numbers are read in this table.")
        row.addWidget(self.values_box)
        row.addStretch(1)
        lay.addLayout(row)

        self.trace_box.activated.connect(lambda i: self.plot.set_marker_trace(self.trace_box.itemData(i)))
        self.add_btn.clicked.connect(lambda _checked=False: self.plot.add_marker())
        self.clear_btn.clicked.connect(lambda _checked=False: self.plot.clear_markers())
        self.copy_btn.clicked.connect(lambda _checked=False: self.plot.copy_markers())
        self.values_box.toggled.connect(lambda on: self.plot.set_marker_values(on))
        plot.markers_changed.connect(self.refresh)
        self.refresh()

    # ---- colour: one per marker, from the palette
    def color_menu(self, marker: str):
        """The palette for the marker of that name, its present colour pressed."""
        menu = palette_menu(self, self.plot.marker_color_of(marker),
                            lambda color, m=marker: self.plot.set_marker_color(m, color))
        menu.marker = marker
        return menu

    def _item_clicked(self, item, column: int) -> None:
        if column != 0:
            return
        self.open_menu = self.color_menu(item.text(0))
        self.open_menu.popup(QCursor.pos())

    # ---- following the plot
    def refresh(self) -> None:
        """Show what the plot holds now: the trace, the ticks, the look, the table."""
        plot = self.plot
        side = self.fontMetrics().height()      # the squares grow with the font, on any screen scale
        self.trace_box.blockSignals(True)
        self.trace_box.clear()
        for t in plot.set.traces:
            self.trace_box.addItem(t.name, t.id)
        self.trace_box.setCurrentIndex(max(0, self.trace_box.findData(plot.markers.trace_id)))
        self.trace_box.blockSignals(False)
        self.trace_box.view().setMinimumWidth(
            max(self.fontMetrics().horizontalAdvance(t.name) for t in plot.set.traces) + 40)
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
        self.table.clear()
        for r in plot.marker_rows():
            item = QTreeWidgetItem(list(r))
            item.setIcon(0, swatch(theme.marker_hex(plot.marker_color_of(r[0])), side))
            item.setToolTip(len(COLUMNS) - 1, r[-1])    # the note in full, when the column is cut short
            for c in FIGURES:
                item.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            self.table.addTopLevelItem(item)
        for c in range(len(COLUMNS) - 1):
            self.table.resizeColumnToContents(c)
