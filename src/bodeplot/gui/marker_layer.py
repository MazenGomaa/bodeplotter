"""The markers as graphics on the gain and the phase plot (SPEC.md section 10).

The layer draws what it is given: a list of placed markers (markers.Placed) with their
texts and positions. It decides only where a label goes so that labels do not cover each
other, and it reports a user marker that is dragged. The rules are in markers.py.
"""
from __future__ import annotations

import math

import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt

from ..markers import Placed
from . import theme

Z = 5               # above the other traces, below the live sweep (10 and 11): a point keeps its click
GAP = 6             # px between a dot and its label
GRAB_PX = 6         # a right-click this close to a user marker's line is on that marker
MAX_ROWS = 30


class _Items:
    """The graphics of one marker: a line and a dot per plot, one label on its host plot."""

    def __init__(self):
        self.lines: list = []       # [gain plot, phase plot]
        self.dots: list = []
        self.text = None
        self.color = ""             # the palette name the line and the dot were made in
        self.host = 0               # 0: the label is on the gain plot; 1: on the phase plot


class MarkerLayer:
    def __init__(self, gain_plot, phase_plot, on_moved):
        self.plots = (gain_plot, phase_plot)
        self.on_moved = on_moved    # (number, freq_hz) while a user marker is dragged
        self.log_x = True
        self._items: dict[str, _Items] = {}
        self._placed: list[Placed] = []
        self._rects: dict[str, QRectF] = {}
        self._busy = False
        for plot in self.plots:
            vb = plot.getPlotItem().vb
            vb.sigRangeChanged.connect(lambda *_a: self.layout())
            vb.sigResized.connect(lambda *_a: self.layout())

    # ---- coordinates
    def x(self, freq_hz: float) -> float:
        return math.log10(freq_hz) if self.log_x else freq_hz

    def freq(self, x: float) -> float:
        try:
            return 10.0 ** x if self.log_x else x
        except OverflowError:
            return float("inf")

    # ---- what the tests and the plot ask
    def names(self) -> list[str]:
        return [p.marker.name for p in self._placed]

    def items(self, name: str) -> _Items:
        return self._items[name]

    def label_rect(self, name: str) -> QRectF | None:
        """Where the label was put, in scene pixels of its plot."""
        return self._rects.get(name)

    def user_at(self, plot, scene_pos) -> int | None:
        """The number of the user marker whose line is under scene_pos, or None."""
        vb = plot.getPlotItem().vb
        for p in self._placed:
            if p.marker.kind != "user":
                continue
            px = vb.mapViewToScene(QPointF(self.x(p.marker.freq), 0.0)).x()
            if abs(px - scene_pos.x()) <= GRAB_PX:
                return p.marker.number
        return None

    # ---- drawing
    def _make(self, m, color: str) -> _Items:
        it = _Items()
        it.color = color
        ink = theme.marker_hex(color)
        it.host = 1 if m.kind == "pm" else 0
        movable = m.kind == "user"
        for plot in self.plots:
            line = pg.InfiniteLine(angle=90, movable=movable,
                                   pen=pg.mkPen(ink, width=1, style=Qt.DashLine),
                                   hoverPen=pg.mkPen(theme.INK, width=1.5, style=Qt.DashLine))
            if movable:
                line.sigDragged.connect(lambda ln, n=m.number: self.on_moved(n, self.freq(ln.value())))
            dot = pg.ScatterPlotItem(size=theme.MARKER, symbol="d", pen=pg.mkPen(theme.SURFACE, width=theme.RING),
                                     brush=pg.mkBrush(ink))
            for item in (line, dot):
                item.setZValue(Z)
                plot.addItem(item, ignoreBounds=True)        # a marker never widens "Fit view"
            it.lines.append(line)
            it.dots.append(dot)
        fill = pg.mkColor(theme.SURFACE)
        fill.setAlpha(190)              # the curve shows through a label that lies on it
        # the label stays in ink whatever the marker's colour: coloured text is hard to read
        it.text = pg.TextItem(color=theme.MARK_INK, anchor=(0, 0), fill=pg.mkBrush(fill))
        it.text.setZValue(Z)
        self.plots[it.host].addItem(it.text, ignoreBounds=True)
        self._items[m.name] = it
        return it

    def _drop(self, name: str) -> None:
        it = self._items.pop(name)
        self._rects.pop(name, None)
        for plot, line, dot in zip(self.plots, it.lines, it.dots):
            plot.removeItem(line)
            plot.removeItem(dot)
        self.plots[it.host].removeItem(it.text)

    def show(self, placed: list[Placed], log_x: bool) -> None:
        """Draw these markers and nothing else. A marker that is switched on but was not
        found on the curve is not drawn. Items of a marker that stays are kept, so a line
        that is being dragged is not replaced under the mouse."""
        self.log_x = log_x
        self._placed = [p for p in placed if p.marker.found]
        keep = {p.marker.name for p in self._placed}
        for name in [n for n in self._items if n not in keep]:
            self._drop(name)
        for p in self._placed:
            it = self._items.get(p.marker.name)
            if it is not None and it.color != p.color:      # another colour was chosen: drawn again
                self._drop(p.marker.name)
                it = None
            if it is None:
                it = self._make(p.marker, p.color)
            x = self.x(p.marker.freq)
            for line in it.lines:
                if line.value() != x:
                    line.setValue(x)
            for dot, y in zip(it.dots, (p.y_gain, p.y_phase)):
                if y is not None and math.isfinite(y):
                    dot.setData([x], [y])
                else:
                    dot.setData([], [])
            if it.text.toPlainText() != p.text:
                it.text.setText(p.text)
        self.layout()

    def layout(self) -> None:
        """Put every label next to its dot (at the top of the plot when it has none), on the
        side the marker asks for unless the plot ends there, and below any label already there."""
        if self._busy:
            return
        self._busy = True
        try:
            taken: dict[int, list[QRectF]] = {0: [], 1: []}
            for p in sorted(self._placed, key=lambda q: q.marker.freq):
                it = self._items[p.marker.name]
                vb = self.plots[it.host].getPlotItem().vb
                box = vb.sceneBoundingRect()
                y = p.y_phase if it.host else p.y_gain
                size = it.text.boundingRect()
                w, h = size.width(), size.height()
                if y is not None and math.isfinite(y):
                    dot = vb.mapViewToScene(QPointF(self.x(p.marker.freq), y))
                    top = max(dot.y() - h - GAP, box.top())
                else:
                    dot = vb.mapViewToScene(QPointF(self.x(p.marker.freq), vb.viewRange()[1][1]))
                    top = box.top()
                right_of, left_of = dot.x() + GAP, dot.x() - GAP - w
                if p.left:
                    left = left_of if left_of >= box.left() else right_of
                else:
                    left = right_of if right_of + w <= box.right() else left_of
                rect = QRectF(left, top, w, h)
                for _ in range(MAX_ROWS):
                    if not any(rect.intersects(r) for r in taken[it.host]):
                        break
                    rect.translate(0.0, h + 2.0)
                taken[it.host].append(rect)
                self._rects[p.marker.name] = rect
                it.text.setPos(vb.mapSceneToView(rect.topLeft()))
        finally:
            self._busy = False
