"""Centre: gain and phase plots, x-axes linked (SPEC.md section 10).

The widget draws a TraceSet (traces.py): the live sweep, kept sweeps, files and theory
curves, as they are or relative to one of them. It decides nothing about the traces
themselves; it asks the set what is to be drawn.
"""
from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QActionGroup, QCursor
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QInputDialog, QLabel, QMenu,
                               QMessageBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from ..io.export_image import ImageMarker, ImageSeries
from ..markers import KINDS, MAX_USER, MarkerSet, Placed, label, table
from ..measure.sinefit import unwrap_deg
from ..models import Flag, PointResult
from ..traces import Drawn, Trace, TraceSet
from ..units import fmt_si, parse_si
from . import theme
from .marker_layer import MarkerLayer
from .si_widgets import SiAxis

QUIET = Flag.REMEASURED | Flag.BUILTIN | Flag.PREVIEW | Flag.CALIBRATED   # flags that do not mark a point as suspect
# Vertical unit of the upper plot: key -> (box text, axis label, axis unit, smallest span shown)
UNITS = {"db": ("dB", "Gain", "dB", 1.0),
         "v": ("Voltage", "Output", "Vpp", 0.0),
         "pct": ("% of input", "Output / input", "%", 1.0)}
# the same axis when every trace is divided by a reference
RELATIVE_LABEL = {"db": "Gain difference", "pct": "Output / reference"}
COLORS = theme.SERIES                    # fixed order, one per colour slot; never cycled
# The automatic markers of the Markers menu: kind -> (menu text, explanation)
MARKER_MENU = {
    "cutoff": ("-3 dB", "Mark where the gain has fallen 3 dB below the highest gain of the trace: the cut-off of "
                        "a low-pass or high-pass, or both edges of a band-pass with its bandwidth and Q"),
    "peak": ("Peak", "Mark the highest gain of the trace when it is a real peak: not at an end of the trace and "
                     "at least 1 dB above both ends"),
    "notch": ("Notch", "Mark the lowest gain of the trace when it is a real notch: not at an end of the trace and "
                       "at least 1 dB below both ends"),
    "margins": ("Margins", "For a trace that is a loop gain: the gain margin where the phase passes -180° and the "
                           "phase margin where the gain passes 0 dB. Not shown in the relative display or "
                           "without phase"),
}


class _Items:
    """The graphics of one trace. The scatter items are None for a theory curve."""
    gain_line = phase_line = gain_ok = phase_ok = gain_bad = phase_bad = None

    def all(self):
        return [i for i in (self.gain_line, self.phase_line, self.gain_ok, self.phase_ok, self.gain_bad,
                            self.phase_bad) if i is not None]


class BodePlot(QWidget):
    remeasure_requested = Signal(float)

    def __init__(self, traces: TraceSet | None = None, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)
        self.set = traces or TraceSet()
        self.span_hint: tuple[float, float] | None = None
        self._items: dict[int, _Items] = {}
        self._shown: list[tuple[Drawn, np.ndarray, np.ndarray, np.ndarray]] = []    # trace, f, gain, phase
        self._painted: dict[int, object] = {}    # per trace: what its items hold now (see refresh)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.unwrap_box = QCheckBox("Unwrap phase")
        self.unwrap_box.setToolTip("Draw the phase as one continuous curve. Without it the phase is shown "
                                   "between -180° and +180° and jumps where it passes either limit.")
        self.readout = QLabel("")
        self.readout.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # The read-out has a row of its own and no say in the layout: its text changes with
        # every mouse move, and a text that could widen the plot pushed the docks about
        # (user report 2026-10-07: the Configuration panel was squeezed and jumped).
        self.readout.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.readout.setMinimumWidth(0)
        self.readout.setFixedHeight(self.readout.fontMetrics().height() + 4)
        self.fit_btn = QPushButton("Fit view")
        self.fit_btn.setToolTip("Zoom both plots to the curves (also: double-click a plot)")
        self.unit_box = QComboBox()
        for key, (text, *_rest) in UNITS.items():
            self.unit_box.addItem(text, key)
        self.unit_box.setToolTip("Vertical scale of the upper plot: gain in dB, the DUT output voltage "
                                 "(peak to peak, at the probe tip), or the output as a percentage of the input")
        self.ref_box = QComboBox()
        # a fixed width whatever the traces are called (the list that drops down is as wide as
        # its longest name, and the tooltip shows the chosen one in full)
        self.ref_box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.ref_box.setMinimumContentsLength(18)
        self.ref_box.setToolTip("Draw every trace divided by this one: the gain difference in dB and the phase "
                                "difference in degrees. Not available with the vertical unit Voltage.")
        self.markers = MarkerSet()
        self._marks: list = []              # the markers of the last refresh (markers.Marker)
        self._placed: list[Placed] = []     # the same, with texts and positions
        self._ctx_menu: QMenu | None = None
        self.markers_btn = QPushButton("Markers")
        self.markers_btn.setToolTip("Markers on the curve: the -3 dB points, the peak, the notch, the gain and "
                                    "phase margin, and markers of your own at any frequency")
        self._build_marker_menu()
        top.addWidget(self.unwrap_box)
        top.addWidget(self.fit_btn)
        top.addWidget(self.markers_btn)
        top.addWidget(QLabel(" Vertical"))
        top.addWidget(self.unit_box)
        top.addWidget(QLabel(" Relative to"))
        top.addWidget(self.ref_box)
        top.addStretch(1)
        lay.addLayout(top)
        lay.addWidget(self.readout)

        self.gain_plot = pg.PlotWidget(axisItems={"bottom": SiAxis("bottom")})
        self.phase_plot = pg.PlotWidget(axisItems={"bottom": SiAxis("bottom")})
        for p, label, unit in ((self.gain_plot, "Gain", "dB"), (self.phase_plot, "Phase", "deg")):
            p.setLabel("left", label, units=unit)
            theme.style_plot(p)
            p.getPlotItem().setMenuEnabled(False)
            # no automatic SI prefix: with a log axis it relabelled 10 kHz as "0.01" (MHz)
            p.getAxis("bottom").enableAutoSIPrefix(False)
            p.getAxis("left").enableAutoSIPrefix(False)
        self.phase_plot.setLabel("bottom", "Frequency", units="Hz")
        self.phase_plot.setXLink(self.gain_plot)
        lay.addWidget(self.gain_plot, 1)
        lay.addWidget(self.phase_plot, 1)

        self.log_x = True
        self.has_phase = True
        self.remeasure_enabled = False
        self._vlines = []
        for p in (self.gain_plot, self.phase_plot):
            v = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(theme.MUTED, style=Qt.DashLine))
            v.setVisible(False)
            p.addItem(v, ignoreBounds=True)
            self._vlines.append(v)
            p.scene().sigMouseMoved.connect(lambda pos, plot=p: self._mouse_moved(plot, pos))
        self.marker_layer = MarkerLayer(self.gain_plot, self.phase_plot, self.move_marker)
        # Follow mode: the view tracks the data until the user pans or zooms by hand.
        # "Fit view", a double-click, or a new sweep switch it back on.
        self.follow = True
        for p in (self.gain_plot, self.phase_plot):
            p.getPlotItem().vb.sigRangeChangedManually.connect(self._moved_by_user)
            p.getPlotItem().hideButtons()               # the small "A" button is replaced by Fit view
            p.scene().sigMouseClicked.connect(lambda ev, plot=p: self._scene_clicked(plot, ev))
        self.fit_btn.clicked.connect(self.fit_view)
        self.unwrap_box.toggled.connect(self.refresh)
        self.unit_box.currentIndexChanged.connect(lambda _i: self._unit_changed())
        self.ref_box.activated.connect(self._ref_chosen)
        self._fill_ref_box()
        self.set_log_x(True)

    # ---- vertical unit and relative display
    def unit(self) -> str:
        return self.unit_box.currentData()

    def set_unit(self, key: str) -> None:
        i = self.unit_box.findData(key)
        if i >= 0:
            self.unit_box.setCurrentIndex(i)

    def _unit_changed(self) -> None:
        axis = self.gain_plot.getAxis("left")
        axis.enableAutoSIPrefix(self.unit() == "v")     # volts read as mV, uV; dB and % stay plain
        self.ref_box.setEnabled(self.unit() != "v")     # a ratio has no voltage
        self.follow = True                              # another unit is another scale: fit it
        self.refresh()

    def is_relative(self) -> bool:
        """True when the traces are drawn divided by a reference trace."""
        return self.unit() != "v" and self.set.reference() is not None

    def _fill_ref_box(self) -> None:
        self.ref_box.blockSignals(True)
        self.ref_box.clear()
        self.ref_box.addItem("nothing", None)
        for t in self.set.traces:
            self.ref_box.addItem(t.name, t.id)
        i = self.ref_box.findData(self.set.reference_id) if self.set.reference_id is not None else 0
        self.ref_box.setCurrentIndex(max(0, i))
        self.ref_box.blockSignals(False)
        fm = self.ref_box.fontMetrics()
        self.ref_box.view().setMinimumWidth(max(fm.horizontalAdvance(t.name) for t in self.set.traces) + 40)

    def _ref_chosen(self, index: int) -> None:
        self.set.set_reference(self.ref_box.itemData(index))
        self.follow = True                              # differences are another scale: fit it
        self.refresh()

    def traces_changed(self) -> None:
        """The set was changed from outside (the Traces panel): names, order, visibility."""
        self._fill_ref_box()
        self._fill_marker_traces()
        self.refresh()

    def set_span_hint(self, lo: float, hi: float) -> None:
        """The sweep range of the panel: a theory curve is drawn at least over it."""
        hint = (float(lo), float(hi)) if lo > 0 and hi > 0 else None
        if hint != self.span_hint:
            self.span_hint = hint
            self.refresh()

    # ---- markers (rules in markers.py, graphics in gui/marker_layer.py)
    def _build_marker_menu(self) -> None:
        menu = QMenu(self.markers_btn)
        menu.setToolTipsVisible(True)
        self.marker_actions = {}
        for kind in KINDS:
            text, tip = MARKER_MENU[kind]
            act = menu.addAction(text)
            act.setCheckable(True)
            act.setToolTip(tip)
            act.toggled.connect(lambda on, k=kind: self.set_marker_kind(k, on))
            self.marker_actions[kind] = act
        menu.addSeparator()
        self.marker_trace_menu = menu.addMenu("Markers on")
        self.marker_trace_menu.setToolTipsVisible(True)
        self.marker_trace_menu.menuAction().setToolTip("The trace the markers measure: all automatic markers and "
                                                       "your own read this one trace, as it is drawn")
        menu.addSeparator()
        self.act_add_marker = menu.addAction("Add marker")
        self.act_add_marker.setToolTip("Put a marker of your own in the middle of the visible frequency range; "
                                       "drag it, or right-click it to type its frequency (up to %d)" % MAX_USER)
        self.act_add_marker.triggered.connect(lambda _checked=False: self.add_marker())
        self.act_clear_markers = menu.addAction("Remove all markers")
        self.act_clear_markers.setToolTip("Remove every marker of your own; the automatic markers stay as ticked")
        self.act_clear_markers.triggered.connect(lambda _checked=False: self.clear_markers())
        self.act_copy_markers = menu.addAction("Copy marker values")
        self.act_copy_markers.setToolTip("Copy the markers as a table (name, frequency, gain, phase, note) "
                                         "for a report or a spreadsheet")
        self.act_copy_markers.triggered.connect(lambda _checked=False: self.copy_markers())
        self.markers_btn.setMenu(menu)
        self.marker_menu = menu
        self._fill_marker_traces()

    def _fill_marker_traces(self) -> None:
        if self.set.get(self.markers.trace_id) is None:     # the chosen trace was removed
            self.markers.trace_id = self.set.live.id
        self.marker_trace_menu.clear()
        group = QActionGroup(self.marker_trace_menu)
        for t in self.set.traces:
            act = self.marker_trace_menu.addAction(t.name)
            act.setCheckable(True)
            act.setChecked(t.id == self.markers.trace_id)
            act.setToolTip("Measure the trace '%s' with the markers" % t.name)
            act.triggered.connect(lambda _checked=False, i=t.id: self.set_marker_trace(i))
            group.addAction(act)

    def marker_kinds(self) -> list[str]:
        """The automatic markers that are switched on, in menu order."""
        return [k for k in KINDS if k in self.markers.kinds]

    def set_marker_kinds(self, kinds) -> None:
        for kind, act in self.marker_actions.items():
            act.setChecked(kind in kinds)                   # toggled -> set_marker_kind

    def set_marker_kind(self, kind: str, on: bool) -> None:
        self.markers.set_kind(kind, on)
        if self.marker_actions[kind].isChecked() != on:
            self.marker_actions[kind].setChecked(on)
        self._update_markers()

    def set_marker_trace(self, trace_id: int) -> None:
        self.markers.trace_id = trace_id
        self._fill_marker_traces()
        self._update_markers()

    def placed(self) -> list[Placed]:
        """The markers of the chosen trace as shown, switched-on ones that were not found included."""
        return list(self._placed)

    def add_marker(self, freq_hz: float | None = None) -> int | None:
        """A marker of the user's at freq_hz (None: the middle of the visible range).
        Returns its number, or None when there are MAX_USER already."""
        if freq_hz is None:
            x0, x1 = self.gain_plot.getPlotItem().vb.viewRange()[0]
            mid = (x0 + x1) / 2.0
            freq_hz = 10.0 ** mid if self.log_x else mid
        n = self.markers.add(freq_hz)
        self._update_markers()
        return n

    def move_marker(self, number: int, freq_hz: float) -> None:
        if self.markers.move(number, freq_hz):
            self._update_markers()

    def remove_marker(self, number: int) -> None:
        self.markers.remove(number)
        self._update_markers()

    def clear_markers(self) -> None:
        self.markers.clear_user()
        self._update_markers()

    def _phase_shown(self, deg: float) -> float:
        """A phase of the unwrapped curve as the phase plot shows it."""
        return deg if self.unwrap() else (deg + 180.0) % 360.0 - 180.0

    def _marker_curve(self):
        """(curve, the measured points behind it or None) of the chosen trace as it is drawn;
        None when that trace is not on the plot (hidden, empty, or not drawn in this unit)."""
        t = self.set.get(self.markers.trace_id)
        if t is None:
            self.markers.trace_id = self.set.live.id
            t = self.set.live
        if not any(d.trace is t and len(f) for d, f, _gain, _phase in self._shown):
            return None
        curve, points = self.set.curve(t.id, self.span_hint, relative=self.is_relative())
        if points is not None:
            curve.flagged = [bool(p.flags & ~QUIET) for p in points]
        return curve, points

    def _place(self, m, curve, points) -> Placed:
        """Text and dot positions of one marker in what the plots show now."""
        if not m.found:
            return Placed(m, "", None, None)
        if not m.has_value:
            return Placed(m, label(m), None, None)
        if self.unit() == "v":
            # the output voltage between two points, by the curve's own rule (log over log frequency)
            logs = [math.log10(2.0 * p.vdut_amp) if p.vdut_amp > 0 and math.isfinite(p.vdut_amp) else float("nan")
                    for p in points]
            lg = curve.interp(m.freq, logs)
            y = 10.0 ** lg if lg is not None else None
            value = fmt_si(y, "Vpp", 3) if y is not None else ""
        elif self.unit() == "pct":
            y = 100.0 * 10.0 ** (m.db / 20.0)
            value = "%.3g %%" % y
        else:
            y = m.db
            value = "%+.2f dB" % y
        phase = self._phase_shown(m.deg) if self.has_phase else None
        return Placed(m, label(m, value, phase), None if m.kind == "pm" else y, None if m.kind == "gm" else phase)

    def _update_markers(self) -> None:
        got = self._marker_curve()
        self._marks, self._placed = [], []
        if got is not None:
            curve, points = got
            self._marks = self.markers.evaluate(curve, margins=self.has_phase and not self.is_relative())
            self._placed = [self._place(m, curve, points) for m in self._marks]
        self.marker_layer.show(self._placed, self.log_x)
        self.act_add_marker.setEnabled(len(self.markers.user) < MAX_USER)

    def context_menu(self, freq_hz: float, number: int | None = None) -> QMenu:
        """The right-click menu of the plot at freq_hz (number: the user marker under the
        mouse). Built here and shown by the caller, so that a test can read it."""
        if self._ctx_menu is not None:
            self._ctx_menu.deleteLater()
        menu = self._ctx_menu = QMenu(self)
        menu.setToolTipsVisible(True)
        if number is None:
            act = menu.addAction("Add marker here")
            act.setToolTip("Put a marker of your own at this frequency; it reads gain and phase of the "
                           "chosen trace there")
            act.setEnabled(len(self.markers.user) < MAX_USER)
            act.triggered.connect(lambda _checked=False: self.add_marker(freq_hz))
            return menu
        act = menu.addAction("Set frequency…")
        act.setToolTip("Type the frequency this marker stands at, for example 1k or 2.5M")
        act.triggered.connect(lambda _checked=False: self._ask_frequency(number))
        act = menu.addAction("Reference marker")
        act.setCheckable(True)
        act.setChecked(self.markers.ref == number)
        act.setToolTip("Make this the reference marker: every other marker of yours also shows its difference "
                       "to it and the slope in dB per decade")
        act.triggered.connect(lambda _checked=False: self.toggle_reference_marker(number))
        act = menu.addAction("Remove")
        act.setToolTip("Remove this marker from the plot; the others keep their numbers")
        act.triggered.connect(lambda _checked=False: self.remove_marker(number))
        return menu

    def set_marker_frequency(self, number: int, text: str) -> bool:
        """Move a user marker to a typed frequency ('1k', '2.5 MHz'). False, and nothing
        changes, when the text is not a positive frequency."""
        try:
            freq = parse_si(text, "Hz")
        except ValueError:
            return False
        if not self.markers.move(number, freq):
            return False
        self._update_markers()
        return True

    def _ask_frequency(self, number: int) -> None:
        if number not in self.markers.user:
            return
        text, ok = QInputDialog.getText(self, "Marker M%d" % number, "Frequency (for example 1k or 2.5M):",
                                        text=fmt_si(self.markers.user[number], "Hz"))
        if ok and not self.set_marker_frequency(number, text):
            QMessageBox.warning(self, "Marker M%d" % number,
                                "'%s' is not a frequency. The marker stays where it was." % text)

    def toggle_reference_marker(self, number: int) -> None:
        self.markers.toggle_ref(number)
        self._update_markers()

    def marker_text(self) -> str:
        """The markers as a tab-separated table (the clipboard text)."""
        t = self.set.get(self.markers.trace_id) or self.set.live
        title = "Markers on: " + t.name
        if self.is_relative():
            title += ", relative to " + self.set.reference().name
        return table(self._marks, title, lambda m: self._phase_shown(m.deg))

    def copy_markers(self) -> None:
        QApplication.clipboard().setText(self.marker_text())

    def value(self, p: PointResult) -> float:
        """What the upper plot shows for a measured point, in the selected unit (not relative)."""
        if self.unit() == "v":
            return 2.0 * p.vdut_amp
        if self.unit() == "pct":
            return 100.0 * abs(p.h)
        return p.gain_db

    def value_text(self, p: PointResult) -> str:
        return self._value_text(self.value(p), relative=False)

    def _value_text(self, y: float, relative: bool) -> str:
        if self.unit() == "v":
            return "output %s" % fmt_si(y, "Vpp", 4)
        if self.unit() == "pct":
            return "output %.4g %% of %s" % (y, "the reference" if relative else "input")
        return ("gain difference %+.3f dB" if relative else "gain %.3f dB") % y

    def _labels(self) -> tuple[str, str, str, str]:
        """(gain axis label, its unit, phase axis label, note) for what is shown now."""
        _text, label, unit, _span = UNITS[self.unit()]
        if not self.is_relative():
            return label, unit, "Phase", ""
        return RELATIVE_LABEL[self.unit()], unit, "Phase difference", "relative to " + self.set.reference().name

    # ---- view
    def _moved_by_user(self, *_):
        self.follow = False

    def _scene_clicked(self, plot, ev):
        if ev.double():
            ev.accept()
            self.fit_view()
        elif ev.button() == Qt.RightButton and plot.sceneBoundingRect().contains(ev.scenePos()):
            ev.accept()
            xv = plot.getPlotItem().vb.mapSceneToView(ev.scenePos()).x()
            number = self.marker_layer.user_at(plot, ev.scenePos())
            self.context_menu(10.0 ** xv if self.log_x else xv, number).exec(QCursor.pos())

    def data_ranges(self):
        """((x0, x1), (gain0, gain1), (phase0, phase1)) of everything plotted, in view
        coordinates (log10 of Hz on a log axis), or None when there is no data."""
        fs, gs, ps = [], [], []
        for _d, f, gain, phase in self._shown:
            ok = np.isfinite(gain)
            fs += [float(v) for v in f[ok]]
            gs += [float(v) for v in gain[ok]]
            ps += [float(v) for v in phase if math.isfinite(v)]
        if not fs:
            return None
        x = np.log10(fs) if self.log_x else np.array(fs)

        def span(v, pad, min_span):
            lo, hi = float(min(v)), float(max(v))
            if hi - lo < min_span:
                mid = (lo + hi) / 2
                lo, hi = mid - min_span / 2, mid + min_span / 2
            d = (hi - lo) * pad
            return lo - d, hi + d
        g_span = UNITS[self.unit()][3] or max(1e-9, 0.05 * max(abs(v) for v in gs))
        return (span(x, 0.03, 0.2 if self.log_x else max(1e-9, abs(float(x[0])) * 0.01)),
                span(gs, 0.08, g_span), span(ps or [0.0], 0.08, 5.0))

    def fit_view(self) -> None:
        """Zoom both plots to the curves, and follow new points from now on."""
        self.follow = True
        r = self.data_ranges()
        if r is None:
            return
        (x0, x1), (g0, g1), (p0, p1) = r
        self.gain_plot.getPlotItem().vb.setRange(xRange=(x0, x1), yRange=(g0, g1), padding=0)
        self.phase_plot.getPlotItem().vb.setRange(xRange=(x0, x1), yRange=(p0, p1), padding=0)

    def view_ranges(self):
        g = self.gain_plot.getPlotItem().vb.viewRange()
        p = self.phase_plot.getPlotItem().vb.viewRange()
        return tuple(g[0]), tuple(g[1]), tuple(p[1])

    # ---- configuration
    def set_log_x(self, log: bool) -> None:
        self.log_x = log
        for p in (self.gain_plot, self.phase_plot):
            p.setLogMode(x=log, y=False)
        self.refresh()

    def set_has_phase(self, has: bool) -> None:
        self.has_phase = has
        self.phase_plot.setVisible(has)
        # the frequency label sits under the lower plot; without it the upper one carries it
        self.gain_plot.showLabel("bottom", not has)
        if not has:
            self.gain_plot.setLabel("bottom", "Frequency", units="Hz")
        self.unwrap_box.setVisible(has)
        self._update_markers()

    def unwrap(self) -> bool:
        return self.unwrap_box.isChecked()

    def set_unwrap(self, on: bool) -> None:
        self.unwrap_box.setChecked(on)

    # ---- the live sweep (the interface the main window has always used)
    def clear(self) -> None:
        """A new sweep: the live trace is emptied; every other trace stays."""
        self.follow = True                              # a new sweep is tracked from its first point
        self.set.live.points = []
        self.refresh()

    def set_points(self, points) -> None:
        self.set.live.points = sorted(points, key=lambda p: p.freq_hz)
        self.refresh()

    def add_point(self, point: PointResult) -> None:
        pts = [p for p in self.set.live.points if abs(p.freq_hz - point.freq_hz) > 1e-9 * point.freq_hz]
        pts.append(point)
        pts.sort(key=lambda p: p.freq_hz)
        self.set.live.points = pts
        self.refresh()

    def points(self) -> list[PointResult]:
        return list(self.set.live.points)

    # ---- drawing
    def items(self, trace: Trace) -> _Items:
        """The graphics of a trace (KeyError when it has none: never drawn, or removed)."""
        return self._items[trace.id]

    def _items_for(self, trace: Trace) -> _Items:
        if trace.id in self._items:
            return self._items[trace.id]
        it = _Items()
        color = COLORS[trace.slot] if trace.slot is not None else theme.MUTED
        pen = pg.mkPen(color, width=theme.LINE_WIDTH)
        it.gain_line = self.gain_plot.plot([], [], pen=pen)
        it.phase_line = self.phase_plot.plot([], [], pen=pen)
        if trace.theory is None:
            for attr, plot, bad in (("gain_ok", self.gain_plot, False), ("phase_ok", self.phase_plot, False),
                                    ("gain_bad", self.gain_plot, True), ("phase_bad", self.phase_plot, True)):
                # ok points: series colour with a surface ring. Flagged points: status
                # colour AND a different shape, so the state never rests on colour alone.
                sc = pg.ScatterPlotItem(
                    size=theme.MARKER_FLAGGED if bad else theme.MARKER, symbol="x" if bad else "o",
                    pen=pg.mkPen(theme.FLAGGED, width=1.6) if bad else pg.mkPen(theme.SURFACE, width=theme.RING),
                    brush=pg.mkBrush(theme.FLAGGED if bad else color), hoverable=True, tip=self._tip,
                    hoverPen=pg.mkPen(theme.INK, width=1.5))
                sc.sigClicked.connect(self._clicked)
                plot.addItem(sc)
                setattr(it, attr, sc)
        if trace.kind == "live":
            # The live sweep is drawn on top: its points take the hover and the re-measure
            # click also where a kept or loaded trace lies over them.
            for item in it.all():
                item.setZValue(11 if item not in (it.gain_line, it.phase_line) else 10)
        self._items[trace.id] = it
        return it

    def _drop_items(self, trace_id: int) -> None:
        it = self._items.pop(trace_id)
        self._painted.pop(trace_id, None)
        for item in it.all():
            (self.gain_plot if item in (it.gain_line, it.gain_ok, it.gain_bad) else self.phase_plot).removeItem(item)

    def _x(self, f):
        return np.log10(f) if self.log_x else f

    def _gain(self, d: Drawn) -> np.ndarray:
        if self.unit() == "v":
            return np.array([2.0 * p.vdut_amp for p in d.points], dtype=float)
        mag = np.abs(np.array(d.h, dtype=complex))
        return 100.0 * mag if self.unit() == "pct" else 20.0 * np.log10(mag)

    def _phase(self, d: Drawn) -> np.ndarray:
        phase = np.degrees(np.angle(np.array(d.h, dtype=complex)))
        return unwrap_deg(phase) if self.unwrap() and len(phase) else phase

    def _drawn(self) -> list[Drawn]:
        """What the set says is to be drawn, for the unit selected: with Voltage only the
        measured traces, as they are (a theory curve and a ratio have no voltage)."""
        if self.unit() != "v":
            return self.set.drawn(self.span_hint, relative=True)
        out = []
        for d in self.set.drawn(self.span_hint, relative=False):
            if d.points is None:
                continue
            # a file without voltage columns has none to show (the Traces panel says so)
            keep = [i for i, p in enumerate(d.points) if math.isfinite(p.vdut_amp)]
            out.append(Drawn(d.trace, [d.freqs[i] for i in keep], [d.h[i] for i in keep],
                             [d.points[i] for i in keep]))
        return out

    def refresh(self) -> None:
        alive = {t.id for t in self.set.traces}
        for trace_id in [k for k in self._items if k not in alive]:
            self._drop_items(trace_id)
        self._shown = []
        seen = set()
        for d in self._drawn():
            it = self._items_for(d.trace)
            seen.add(d.trace.id)
            f = np.array(d.freqs, dtype=float)
            gain, phase = self._gain(d), self._phase(d)
            self._shown.append((d, f, gain, phase))
            # A trace whose numbers did not change keeps its items: while a sweep runs only the
            # live trace is drawn again, not every loaded one for every new point.
            state = (f.tobytes(), gain.tobytes(), phase.tobytes(), self.log_x,
                     None if d.points is None else tuple(int(p.flags.value) for p in d.points))
            if self._painted.get(d.trace.id) == state:
                continue
            self._painted[d.trace.id] = state
            # pyqtgraph applies the log itself to PlotDataItem, but not to ScatterPlotItem
            it.gain_line.setData(f, gain)
            it.phase_line.setData(f, phase)
            if d.points is None:
                continue
            x = self._x(f) if len(f) else f
            bad = np.array([bool(p.flags & ~QUIET) for p in d.points], dtype=bool)
            for sc, y, mask in ((it.gain_ok, gain, ~bad), (it.phase_ok, phase, ~bad),
                                (it.gain_bad, gain, bad), (it.phase_bad, phase, bad)):
                idx = np.nonzero(mask)[0] if len(f) else []
                sc.setData([dict(pos=(float(x[i]), float(y[i])),
                                 data=(d.trace.id, d.points[i], float(gain[i]), float(phase[i]))) for i in idx])
        for trace_id, it in self._items.items():
            if trace_id not in seen and self._painted.get(trace_id) != "empty":    # hidden, or not drawn in this unit
                self._painted[trace_id] = "empty"
                it.gain_line.setData([], [])
                it.phase_line.setData([], [])
                for sc in (it.gain_ok, it.phase_ok, it.gain_bad, it.phase_bad):
                    if sc is not None:
                        sc.setData([])
        gain_label, unit, phase_label, _note = self._labels()
        self.gain_plot.setLabel("left", gain_label, units=unit)
        self.phase_plot.setLabel("left", phase_label, units="deg")
        if self.follow:
            r = self.data_ranges()
            if r is not None:
                (x0, x1), (g0, g1), (p0, p1) = r
                self.gain_plot.getPlotItem().vb.setRange(xRange=(x0, x1), yRange=(g0, g1), padding=0)
                self.phase_plot.getPlotItem().vb.setRange(xRange=(x0, x1), yRange=(p0, p1), padding=0)
        self._update_markers()

    def has_data(self) -> bool:
        """True when at least one trace is drawn with at least one point."""
        return any(len(f) for _d, f, _gain, _phase in self._shown)

    def export_series(self) -> tuple[list[ImageSeries], tuple[str, str, str]]:
        """What the plot shows, for the image export: the series with their final numbers,
        and (gain axis label, phase axis label, note)."""
        series = []
        for d, f, gain, phase in self._shown:
            flagged = None if d.points is None else np.array([bool(p.flags & ~QUIET) for p in d.points], dtype=bool)
            series.append(ImageSeries(d.trace.name, d.trace.slot, f, gain, phase, flagged))
        gain_label, unit, phase_label, note = self._labels()
        return series, ("%s (%s)" % (gain_label, unit), "%s (deg)" % phase_label, note)

    def export_markers(self) -> list[ImageMarker]:
        """The markers as shown, for the image export."""
        return [ImageMarker(p.marker.freq, p.text, p.y_gain, p.y_phase, "phase" if p.marker.kind == "pm" else "gain")
                for p in self._placed if p.marker.found]

    # ---- interaction
    def _tip(self, x, y, data) -> str:
        trace_id, p, gain, phase = data
        trace = self.set.get(trace_id)
        flags = ", ".join(p.flags.names()) or "none"
        head = "%s\n" % trace.name if trace is not None and len(self.set.traces) > 1 else ""
        return "%s%s\n%s\nphase %.2f deg\nflags: %s" % (
            head, _fmt_hz(p.freq_hz), self._value_text(gain, self.is_relative()), phase, flags)

    def readout_at(self, freq_hz: float, y: float | None = None, phase_plot: bool = False) -> str:
        """The read-out text for the cursor at freq_hz: the nearest point of the trace that
        passes closest to y (a value of the gain plot, or of the phase plot). A trace that has
        no point near the cursor's frequency (it ends elsewhere) is left out; with none left,
        the text is the frequency alone."""
        if not (freq_hz > 0):
            return ""
        best = None
        for d, f, gain, phase in self._shown:
            if not len(f):
                continue
            x = np.log10(f) if self.log_x else f
            x0 = math.log10(freq_hz) if self.log_x else freq_hz
            i = int(np.argmin(np.abs(x - x0)))
            near = [abs(float(x[k] - x[i])) for k in (i - 1, i + 1) if 0 <= k < len(x)]
            reach = max(min(near) if near else 0.0, 0.05 if self.log_x else 0.01 * float(f[i]))
            if abs(float(x[i]) - x0) > reach:           # further away than this trace's own point spacing
                continue
            dist = 0.0 if y is None else abs(float((phase if phase_plot else gain)[i]) - y)
            if best is None or dist < best[0]:
                best = (dist, d, i, float(f[i]), float(gain[i]), float(phase[i]))
        if best is None:
            return _fmt_hz(freq_hz)
        _dist, d, i, f, gain, phase = best
        relative = self.is_relative()
        text = "%s   %s" % (_fmt_hz(f), self._value_text(gain, relative))
        if self.has_phase:
            text += "   phase %s%.2f°" % ("difference " if relative else "", phase)
        if d.points is not None and d.points[i].flags & ~QUIET:
            text += "   [%s]" % ", ".join(d.points[i].flags.names())
        if len(self.set.traces) > 1:                    # with one trace the read-out is as it always was
            text = "%s:   %s" % (d.trace.name, text)
        if relative:
            text += "   (relative to %s)" % self.set.reference().name
        return text

    def _mouse_moved(self, plot, pos) -> None:
        vb = plot.getPlotItem().vb
        if not plot.sceneBoundingRect().contains(pos):
            return
        at = vb.mapSceneToView(pos)
        xv = at.x()
        freq = 10 ** xv if self.log_x else xv
        for v in self._vlines:
            v.setPos(xv)
            v.setVisible(True)
        self.readout.setText(self.readout_at(freq, at.y(), plot is self.phase_plot))

    def _clicked(self, _item, spots, *_):
        if not self.remeasure_enabled or len(spots) == 0:
            return
        trace_id, p, _gain, _phase = spots[0].data()
        if trace_id != self.set.live.id:                # only the live sweep can be measured again
            return
        menu = QMenu(self)
        act = menu.addAction("Re-measure %s" % _fmt_hz(p.freq_hz))
        if menu.exec(QCursor.pos()) is act:
            self.remeasure_requested.emit(p.freq_hz)


def _fmt_hz(f: float) -> str:
    if not math.isfinite(f) or f <= 0:
        return ""
    return fmt_si(f, "Hz")
