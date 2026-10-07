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
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout,
                               QWidget)

from ..io.export_image import ImageSeries
from ..measure.sinefit import unwrap_deg
from ..models import Flag, PointResult
from ..traces import Drawn, Trace, TraceSet
from ..units import fmt_si
from . import theme
from .si_widgets import SiAxis

QUIET = Flag.REMEASURED | Flag.BUILTIN | Flag.PREVIEW | Flag.CALIBRATED   # flags that do not mark a point as suspect
# Vertical unit of the upper plot: key -> (box text, axis label, axis unit, smallest span shown)
UNITS = {"db": ("dB", "Gain", "dB", 1.0),
         "v": ("Voltage", "Output", "Vpp", 0.0),
         "pct": ("% of input", "Output / input", "%", 1.0)}
# the same axis when every trace is divided by a reference
RELATIVE_LABEL = {"db": "Gain difference", "pct": "Output / reference"}
COLORS = theme.SERIES                    # fixed order, one per colour slot; never cycled


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
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.unwrap_box = QCheckBox("Unwrap phase")
        self.readout = QLabel("")
        self.readout.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.fit_btn = QPushButton("Fit view")
        self.fit_btn.setToolTip("Zoom both plots to the curves (also: double-click a plot)")
        self.unit_box = QComboBox()
        for key, (text, *_rest) in UNITS.items():
            self.unit_box.addItem(text, key)
        self.unit_box.setToolTip("Vertical scale of the upper plot: gain in dB, the DUT output voltage "
                                 "(peak to peak, at the probe tip), or the output as a percentage of the input")
        self.ref_box = QComboBox()
        self.ref_box.setMinimumWidth(140)
        self.ref_box.setSizeAdjustPolicy(QComboBox.AdjustToContents)    # trace names are long
        self.ref_box.setToolTip("Draw every trace divided by this one: the gain difference in dB and the phase "
                                "difference in degrees. Not available with the vertical unit Voltage.")
        top.addWidget(self.unwrap_box)
        top.addWidget(self.fit_btn)
        top.addWidget(QLabel(" Vertical"))
        top.addWidget(self.unit_box)
        top.addWidget(QLabel(" Relative to"))
        top.addWidget(self.ref_box)
        top.addStretch(1)
        top.addWidget(self.readout)
        lay.addLayout(top)

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
        # Follow mode: the view tracks the data until the user pans or zooms by hand.
        # "Fit view", a double-click, or a new sweep switch it back on.
        self.follow = True
        for p in (self.gain_plot, self.phase_plot):
            p.getPlotItem().vb.sigRangeChangedManually.connect(self._moved_by_user)
            p.getPlotItem().hideButtons()               # the small "A" button is replaced by Fit view
            p.scene().sigMouseClicked.connect(self._scene_clicked)
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

    def _ref_chosen(self, index: int) -> None:
        self.set.set_reference(self.ref_box.itemData(index))
        self.follow = True                              # differences are another scale: fit it
        self.refresh()

    def traces_changed(self) -> None:
        """The set was changed from outside (the Traces panel): names, order, visibility."""
        self._fill_ref_box()
        self.refresh()

    def set_span_hint(self, lo: float, hi: float) -> None:
        """The sweep range of the panel: a theory curve is drawn at least over it."""
        hint = (float(lo), float(hi)) if lo > 0 and hi > 0 else None
        if hint != self.span_hint:
            self.span_hint = hint
            self.refresh()

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

    def _scene_clicked(self, ev):
        if ev.double():
            ev.accept()
            self.fit_view()

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
        self._items[trace.id] = it
        return it

    def _drop_items(self, trace_id: int) -> None:
        it = self._items.pop(trace_id)
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
        if self.unit() == "v":
            return [d for d in self.set.drawn(self.span_hint, relative=False) if d.points is not None]
        return self.set.drawn(self.span_hint, relative=True)

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
            if trace_id not in seen:                    # hidden, or not drawn in this unit
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

    def export_series(self) -> tuple[list[ImageSeries], tuple[str, str, str]]:
        """What the plot shows, for the image export: the series with their final numbers,
        and (gain axis label, phase axis label, note)."""
        series = []
        for d, f, gain, phase in self._shown:
            flagged = None if d.points is None else np.array([bool(p.flags & ~QUIET) for p in d.points], dtype=bool)
            series.append(ImageSeries(d.trace.name, d.trace.slot, f, gain, phase, flagged))
        gain_label, unit, phase_label, note = self._labels()
        return series, ("%s (%s)" % (gain_label, unit), "%s (deg)" % phase_label, note)

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
        passes closest to y (a value of the gain plot, or of the phase plot)."""
        if not (freq_hz > 0):
            return ""
        best = None
        for d, f, gain, phase in self._shown:
            if not len(f):
                continue
            i = int(np.argmin(np.abs(np.log10(f) - math.log10(freq_hz)) if self.log_x else np.abs(f - freq_hz)))
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
        from PySide6.QtGui import QCursor
        if menu.exec(QCursor.pos()) is act:
            self.remeasure_requested.emit(p.freq_hz)


def _fmt_hz(f: float) -> str:
    if not math.isfinite(f) or f <= 0:
        return ""
    return fmt_si(f, "Hz")
