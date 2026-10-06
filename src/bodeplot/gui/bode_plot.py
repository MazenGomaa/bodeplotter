"""Centre: gain and phase plots, x-axes linked (SPEC.md section 10).

Internally the widget holds any number of named traces (v2 overlay needs that);
v1 shows one, called "sweep".
"""
from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout,
                               QWidget)

from ..measure.sinefit import unwrap_deg
from ..models import Flag, PointResult
from ..units import fmt_si
from . import theme
from .si_widgets import SiAxis

QUIET = Flag.REMEASURED | Flag.BUILTIN | Flag.PREVIEW | Flag.CALIBRATED   # flags that do not mark a point as suspect
# Vertical unit of the upper plot: key -> (box text, axis label, axis unit, smallest span shown)
UNITS = {"db": ("dB", "Gain", "dB", 1.0),
         "v": ("Voltage", "Output", "Vpp", 0.0),
         "pct": ("% of input", "Output / input", "%", 1.0)}
COLORS = theme.SERIES                    # fixed order; a trace beyond the last slot is drawn muted


class _Trace:
    def __init__(self, name: str, color: str):
        self.name, self.color = name, color
        self.points: list[PointResult] = []
        self.gain_line = self.phase_line = None
        self.gain_ok = self.phase_ok = self.gain_bad = self.phase_bad = None


class BodePlot(QWidget):
    remeasure_requested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.unwrap_box = QCheckBox("Unwrap phase")
        self.readout = QLabel("")
        self.readout.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.fit_btn = QPushButton("Fit view")
        self.fit_btn.setToolTip("Zoom both plots to the measured curves (also: double-click a plot)")
        self.unit_box = QComboBox()
        for key, (text, *_rest) in UNITS.items():
            self.unit_box.addItem(text, key)
        self.unit_box.setToolTip("Vertical scale of the upper plot: gain in dB, the DUT output voltage "
                                 "(peak to peak, at the probe tip), or the output as a percentage of the input")
        top.addWidget(self.unwrap_box)
        top.addWidget(self.fit_btn)
        top.addWidget(QLabel(" Vertical"))
        top.addWidget(self.unit_box)
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
        self.traces: dict[str, _Trace] = {}
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
        self.set_log_x(True)

    # ---- vertical unit
    def unit(self) -> str:
        return self.unit_box.currentData()

    def set_unit(self, key: str) -> None:
        i = self.unit_box.findData(key)
        if i >= 0:
            self.unit_box.setCurrentIndex(i)

    def _unit_changed(self) -> None:
        _text, label, unit, _span = UNITS[self.unit()]
        axis = self.gain_plot.getAxis("left")
        axis.enableAutoSIPrefix(self.unit() == "v")     # volts read as mV, uV; dB and % stay plain
        self.gain_plot.setLabel("left", label, units=unit)
        self.follow = True                              # another unit is another scale: fit it
        self.refresh()

    def value(self, p: PointResult) -> float:
        """What the upper plot shows for a point, in the selected unit."""
        if self.unit() == "v":
            return 2.0 * p.vdut_amp
        if self.unit() == "pct":
            return 100.0 * abs(p.h)
        return p.gain_db

    def value_text(self, p: PointResult) -> str:
        if self.unit() == "v":
            return "output %s" % fmt_si(2.0 * p.vdut_amp, "Vpp", 4)
        if self.unit() == "pct":
            return "output %.4g %% of input" % (100.0 * abs(p.h))
        return "gain %.3f dB" % p.gain_db

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
        for t in self.traces.values():
            pts = [p for p in t.points if p.freq_hz > 0 and math.isfinite(p.gain_db)]
            if not pts:
                continue
            ph = np.array([p.phase_deg for p in pts], dtype=float)
            if self.unwrap():
                ph = unwrap_deg(ph)
            fs += [p.freq_hz for p in pts]
            gs += [self.value(p) for p in pts]
            ps += [float(v) for v in ph if math.isfinite(v)]
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

    # ---- data
    def _trace(self, name: str) -> _Trace:
        if name not in self.traces:
            i = len(self.traces)
            t = _Trace(name, COLORS[i] if i < len(COLORS) else theme.MUTED)     # never cycled
            pen = pg.mkPen(t.color, width=theme.LINE_WIDTH)
            t.gain_line = self.gain_plot.plot([], [], pen=pen)
            t.phase_line = self.phase_plot.plot([], [], pen=pen)
            for attr, plot, bad in (("gain_ok", self.gain_plot, False), ("phase_ok", self.phase_plot, False),
                                    ("gain_bad", self.gain_plot, True), ("phase_bad", self.phase_plot, True)):
                # ok points: series colour with a surface ring. Flagged points: status
                # colour AND a different shape, so the state never rests on colour alone.
                sc = pg.ScatterPlotItem(
                    size=theme.MARKER_FLAGGED if bad else theme.MARKER, symbol="x" if bad else "o",
                    pen=pg.mkPen(theme.FLAGGED, width=1.6) if bad else pg.mkPen(theme.SURFACE, width=theme.RING),
                    brush=pg.mkBrush(theme.FLAGGED if bad else t.color), hoverable=True, tip=self._tip,
                    hoverPen=pg.mkPen(theme.INK, width=1.5))
                sc.sigClicked.connect(self._clicked)
                plot.addItem(sc)
                setattr(t, attr, sc)
            self.traces[name] = t
        return self.traces[name]

    def clear(self, name: str | None = None) -> None:
        self.follow = True                              # a new sweep is tracked from its first point
        for t in ([self.traces[name]] if name in self.traces else list(self.traces.values()) if name is None else []):
            t.points = []
        self.refresh()

    def set_points(self, points, name: str = "sweep") -> None:
        self._trace(name).points = sorted(points, key=lambda p: p.freq_hz)
        self.refresh()

    def add_point(self, point: PointResult, name: str = "sweep") -> None:
        t = self._trace(name)
        t.points = [p for p in t.points if abs(p.freq_hz - point.freq_hz) > 1e-9 * point.freq_hz]
        t.points.append(point)
        t.points.sort(key=lambda p: p.freq_hz)
        self.refresh()

    def points(self, name: str = "sweep") -> list[PointResult]:
        return list(self.traces[name].points) if name in self.traces else []

    def _x(self, f):
        return np.log10(f) if self.log_x else f

    def _tip(self, x, y, data) -> str:
        p: PointResult = data
        flags = ", ".join(p.flags.names()) or "none"
        return "%s\n%s\nphase %.2f deg\nflags: %s" % (_fmt_hz(p.freq_hz), self.value_text(p),
                                                      p.phase_deg, flags)

    def refresh(self) -> None:
        for t in self.traces.values():
            pts = [p for p in t.points if p.freq_hz > 0 and math.isfinite(p.gain_db)]
            f = np.array([p.freq_hz for p in pts], dtype=float)
            gain = np.array([self.value(p) for p in pts], dtype=float)
            phase = np.array([p.phase_deg for p in pts], dtype=float)
            if self.unwrap() and len(pts):
                phase = unwrap_deg(phase)
            x = self._x(f) if len(pts) else f
            # pyqtgraph applies the log itself to PlotDataItem, but not to ScatterPlotItem
            t.gain_line.setData(f, gain)
            t.phase_line.setData(f, phase)
            bad = np.array([bool(p.flags & ~QUIET) for p in pts], dtype=bool)
            for sc, y, mask in ((t.gain_ok, gain, ~bad), (t.phase_ok, phase, ~bad),
                                (t.gain_bad, gain, bad), (t.phase_bad, phase, bad)):
                idx = np.nonzero(mask)[0] if len(pts) else []
                sc.setData([dict(pos=(float(x[i]), float(y[i])), data=pts[i]) for i in idx])
        if self.follow:
            r = self.data_ranges()
            if r is not None:
                (x0, x1), (g0, g1), (p0, p1) = r
                self.gain_plot.getPlotItem().vb.setRange(xRange=(x0, x1), yRange=(g0, g1), padding=0)
                self.phase_plot.getPlotItem().vb.setRange(xRange=(x0, x1), yRange=(p0, p1), padding=0)

    # ---- interaction
    def _mouse_moved(self, plot, pos) -> None:
        vb = plot.getPlotItem().vb
        if not plot.sceneBoundingRect().contains(pos):
            return
        xv = vb.mapSceneToView(pos).x()
        freq = 10 ** xv if self.log_x else xv
        for v in self._vlines:
            v.setPos(xv)
            v.setVisible(True)
        pts = self.points()
        if not pts or freq <= 0:
            self.readout.setText(_fmt_hz(freq) if freq > 0 else "")
            return
        near = min(pts, key=lambda p: abs(math.log10(p.freq_hz) - math.log10(freq)) if self.log_x
                   else abs(p.freq_hz - freq))
        text = "%s   %s" % (_fmt_hz(near.freq_hz), self.value_text(near))
        if self.has_phase:
            text += "   phase %.2f°" % near.phase_deg
        if near.flags & ~QUIET:
            text += "   [%s]" % ", ".join(near.flags.names())
        self.readout.setText(text)

    def _clicked(self, _item, spots, *_):
        if not self.remeasure_enabled or len(spots) == 0:
            return
        p: PointResult = spots[0].data()
        menu = QMenu(self)
        act = menu.addAction("Re-measure %s" % _fmt_hz(p.freq_hz))
        from PySide6.QtGui import QCursor
        if menu.exec(QCursor.pos()) is act:
            self.remeasure_requested.emit(p.freq_hz)


def _fmt_hz(f: float) -> str:
    if not math.isfinite(f) or f <= 0:
        return ""
    return fmt_si(f, "Hz")
