"""The Analysis panel (SPEC.md section 10): the response metrics of one trace as a table,
with a second trace next to it for comparison.

Nothing is worked out until Analyse is pressed, and the table then stays as it is: when the
analysed trace changes afterwards (a new sweep, a removed trace), a line says so and the
numbers wait for the next press. The maths is measure/metrics.py, the texts are analysis.py;
the panel only asks and shows.

Its order is that of the Markers panel: what is chosen on top, then the table with all the
height that is left, the notes under it in a few lines that scroll when there are more. The
figures keep their width and the names of the quantities take what is left, so that the
table needs no sideways scrolling in a narrow column.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QScrollArea, QSizePolicy, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from .. import analysis
from ..measure import metrics
from ..measure.analysis_settings import DEFAULTS
from . import theme

COLUMNS = ("Quantity", "Value", "Compare", "Difference")
FIGURES = (1, 2, 3)                     # the columns of numbers: right-aligned, so that digits line up
IDLE = "Press Analyse to work out the numbers of the chosen trace."
NOTE_LINES = 4                          # the notes take this many lines at most; more are scrolled


def _quiet(label: QLabel) -> QLabel:
    """A text that wraps and has no say in the panel's width (as the plot's read-out)."""
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    label.setMinimumWidth(0)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


class AnalysisPanel(QWidget):
    def __init__(self, plot, parent=None):
        super().__init__(parent)
        self.plot = plot
        self._shown: dict | None = None     # what the table holds: trace ids, names, time, the curves' prints
        self._text = ""                     # the same as clipboard text
        self.settings = DEFAULTS            # the numbers of the analysis (Settings, Analysis tab)
        lay = QVBoxLayout(self)

        form = QGridLayout()
        self.trace_label, self.trace_box = QLabel("Trace"), QComboBox()
        self.compare_label, self.compare_box = QLabel("Compare with"), QComboBox()
        self.trace_box.setToolTip("The trace to analyse. Its gain in dB and its phase are read as measured, "
                                  "whatever the vertical unit and 'Difference to trace' are set to.")
        self.compare_box.setToolTip("A second trace, such as a theory curve or an earlier sweep: its numbers are "
                                    "shown next to those of the analysed trace, with the difference. 'off' "
                                    "shows one trace only.")
        for row, (label, box) in enumerate(((self.trace_label, self.trace_box),
                                            (self.compare_label, self.compare_box))):
            # a small fixed width whatever the traces are called: the list that drops down shows the full names
            box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            box.setMinimumContentsLength(8)
            label.setToolTip(box.toolTip())
            form.addWidget(label, row, 0)
            form.addWidget(box, row, 1)
        form.setColumnStretch(1, 1)
        lay.addLayout(form)

        row = QHBoxLayout()
        self.analyse_btn = QPushButton("Analyse")
        self.analyse_btn.setToolTip("Work out the numbers of the chosen trace now: passband level and ripple, "
                                    "cut-offs, slope and order, stopband attenuation, and every resonance. The "
                                    "table then stays as it is until this is pressed again.")
        self.copy_btn = QPushButton("Copy table")
        self.copy_btn.setToolTip("Copy the table and its notes as tab-separated text for a report or a spreadsheet")
        row.addWidget(self.analyse_btn)
        row.addWidget(self.copy_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self.state = _quiet(QLabel())
        self.state.setTextFormat(Qt.RichText)
        self.state.setToolTip("Which trace the table below belongs to and when it was worked out. A warning "
                              "appears here when that trace has changed since.")
        lay.addWidget(self.state)

        self.table = QTreeWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHeaderLabels(list(COLUMNS))
        self.table.setRootIsDecorated(False)
        self.table.setIndentation(self.fontMetrics().averageCharWidth() * 2)
        self.table.setMinimumWidth(0)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.header().setStretchLastSection(False)
        self.table.header().setMinimumSectionSize(0)
        self.table.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in FIGURES:
            self.table.header().setSectionResizeMode(c, QHeaderView.ResizeToContents)
            self.table.headerItem().setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
        self.table.setToolTip("The numbers of the analysed trace, in groups. Rest the mouse on a row to read the "
                              "rule behind its group. '≥': at least; the sweep ends before the number has settled.")
        lay.addWidget(self.table, 1)

        self.notes = _quiet(QLabel())
        self.notes.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.notes.setToolTip("What the numbers do not say by themselves: where the sweep ends too early, where "
                              "a resonance has too few points, how many points are flagged.")
        self.notes_area = QScrollArea()                 # a few lines; the table keeps the height
        self.notes_area.setFrameShape(QFrame.NoFrame)
        self.notes_area.setWidgetResizable(True)
        self.notes_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.notes_area.setWidget(self.notes)
        self.notes_area.setToolTip(self.notes.toolTip())
        self.notes_area.hide()
        lay.addWidget(self.notes_area)

        self.trace_box.activated.connect(lambda _i: self._update_state())
        self.compare_box.activated.connect(lambda _i: self._update_state())
        self.analyse_btn.clicked.connect(lambda _checked=False: self.analyse())
        self.copy_btn.clicked.connect(lambda _checked=False: self.copy())
        plot.markers_changed.connect(self.refresh)      # the plot says so after every change of its traces
        self.refresh()

    # ---- following the plot
    def refresh(self) -> None:
        """The traces may have changed: fill the two boxes again and say whether the table still holds."""
        traces = self.plot.set.traces
        for box, first in ((self.trace_box, None), (self.compare_box, "off")):
            chosen = box.currentData()
            box.blockSignals(True)
            box.clear()
            if first is not None:
                box.addItem(first, None)
            for t in traces:
                box.addItem(t.name, t.id)
            box.setCurrentIndex(max(0, box.findData(chosen)))
            box.blockSignals(False)
            box.view().setMinimumWidth(max(self.fontMetrics().horizontalAdvance(t.name) for t in traces) + 40)
        self._update_state()

    def _print(self, trace_id) -> tuple | None:
        """What a trace looks like to the analysis, to tell later whether it changed."""
        c = self.plot.analysis_curve(trace_id) if trace_id is not None else None
        return None if c is None else (tuple(c.f), tuple(c.db), tuple(c.deg), tuple(c.flagged))

    def set_settings(self, s) -> None:
        """New numbers for the analysis; the table waits for the next Analyse, and the state line
        says that it was made with others."""
        self.settings = s
        self._update_state()

    def stale(self) -> bool:
        """The table no longer belongs to the traces as they are now."""
        s = self._shown
        return s is not None and (self._print(s["trace"]) != s["print"] or self._print(s["compare"]) != s["compare_print"])

    def _update_state(self) -> None:
        s = self._shown
        self.copy_btn.setEnabled(s is not None and bool(self._text))
        if s is None:
            self.state.setText(theme.status_html("idle", IDLE))
            return
        text = "%s, analysed %s" % (s["title"], s["when"].strftime("%H:%M:%S"))
        why = [w for w, old in (("trace changed", self.stale()), ("settings changed", s["settings"] != self.settings))
               if old]
        if why:
            self.state.setText(theme.status_html("warning", text + ": %s since this analysis" % " and ".join(why)))
        else:
            self.state.setText(theme.status_html("good", text))

    # ---- the analysis
    def analyse(self) -> None:
        """Work out the table for the chosen trace (and the compared one) as they are now."""
        plot = self.plot
        trace_id, compare_id = self.trace_box.currentData(), self.compare_box.currentData()
        if compare_id == trace_id:
            compare_id = None                           # a trace against itself says nothing
        trace = plot.set.get(trace_id) or plot.set.live
        other = plot.set.get(compare_id) if compare_id is not None else None
        curve = plot.analysis_curve(trace.id)
        other_curve = plot.analysis_curve(other.id) if other is not None else None
        phase = plot.has_phase
        s = self.settings
        m = metrics.analyse(curve, phase, s) if curve is not None else metrics.Metrics(reason="the trace has no points")
        mo = metrics.analyse(other_curve, phase, s) if other_curve is not None else None
        rows = analysis.rows(m, mo, phase, s)
        notes = analysis.notes(m, s)
        if other is not None and (mo is None or not mo.ok):     # of the compared trace only that it has no numbers
            notes.append("%s: no analysis, %s." % (other.name, mo.reason if mo is not None else "the trace has no points"))
        title = trace.name + (", compared with %s" % other.name if other is not None else "")
        self._shown = {"trace": trace.id, "compare": other.id if other is not None else None, "title": title,
                       "when": datetime.now(), "print": self._print(trace.id), "settings": s,
                       "compare_print": self._print(other.id) if other is not None else None}
        self._text = analysis.table("Analysis of: " + title, rows, notes, compare=other is not None)
        self._fill(rows, other is not None)
        self.notes.setText("\n".join(notes))
        self.notes_area.setVisible(bool(notes))
        self._fit_notes()
        self._update_state()

    def _fit_notes(self) -> None:
        """The notes are as high as their text, up to NOTE_LINES lines."""
        width = max(1, self.notes_area.viewport().width())
        cap = NOTE_LINES * self.fontMetrics().lineSpacing()
        self.notes_area.setFixedHeight(min(self.notes.heightForWidth(width), cap) + 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_notes()

    def _fill(self, rows, compare: bool) -> None:
        self.table.clear()
        self.table.setColumnHidden(2, not compare)
        self.table.setColumnHidden(3, not compare)
        quiet = QBrush(QColor(theme.INK_2))
        group, head = None, None
        for r in rows:
            if r.group != group:
                group = r.group
                head = QTreeWidgetItem([group])
                head.setForeground(0, quiet)
                head.setToolTip(0, r.tip)
                self.table.addTopLevelItem(head)
                head.setFirstColumnSpanned(True)        # only an item that is in the tree can span: its title is never cut
            item = QTreeWidgetItem([r.name, r.value, r.compare, r.diff])
            for c in range(len(COLUMNS)):               # the name in full (the column may cut it short), then the rule
                item.setToolTip(c, "%s, %s. %s" % (r.group, r.name, r.tip))
            for c in FIGURES:
                item.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            head.addChild(item)
        self.table.expandAll()

    def rows(self) -> list[list[str]]:
        """The table as shown, group lines included: [quantity, value, compare, difference]."""
        out = []
        for i in range(self.table.topLevelItemCount()):
            head = self.table.topLevelItem(i)
            out.append([head.text(0), "", "", ""])
            out += [[head.child(k).text(c) for c in range(len(COLUMNS))] for k in range(head.childCount())]
        return out

    def text(self) -> str:
        """The table and its notes as tab-separated text (the clipboard text)."""
        return self._text

    def copy(self) -> None:
        QApplication.clipboard().setText(self._text)
