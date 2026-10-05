"""Right dock: the last reference and DUT capture, with the fitted sines overlaid."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..models import WaveformPair
from ..units import fmt_si
from . import theme


class WaveformView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("No capture yet")
        self.plot = pg.PlotWidget()
        self.plot.setLabel("left", "Voltage", units="V")
        self.plot.setLabel("bottom", "Time", units="s")
        theme.style_plot(self.plot)
        # The legend sits in a row above the plot, so it can never cover the traces.
        self.legend = QLabel(
            "&nbsp;&nbsp;".join(
                '<span style="color:%s">%s</span>&nbsp;<span style="color:%s">%s</span>' % (c, mark, theme.INK_2, name)
                for c, mark, name in ((theme.REF, "&#9472;&#9472;", "reference"), (theme.DUT, "&#9472;&#9472;", "DUT"),
                                      (theme.MUTED, "&#9548;&#9548;", "dashed: fitted sine"))))
        self.legend.setTextFormat(Qt.RichText)
        # Each channel keeps one hue: the samples as a thin translucent line, its fit as a
        # 2 px dashed line of the same hue on top.
        def raw(color):
            c = pg.mkColor(color)
            c.setAlpha(150)
            return pg.mkPen(c, width=1)
        fit_pen = dict(width=theme.LINE_WIDTH, style=Qt.DashLine)
        self.ref = self.plot.plot([], [], pen=raw(theme.REF))
        self.dut = self.plot.plot([], [], pen=raw(theme.DUT))
        self.ref_fit = self.plot.plot([], [], pen=pg.mkPen(theme.REF, **fit_pen))
        self.dut_fit = self.plot.plot([], [], pen=pg.mkPen(theme.DUT, **fit_pen))
        head = QHBoxLayout()
        head.setContentsMargins(4, 0, 8, 0)
        head.addWidget(self.label)
        head.addStretch(1)
        head.addWidget(self.legend)
        lay.addLayout(head)
        lay.addWidget(self.plot, 1)

    def show_pair(self, pair: WaveformPair) -> None:
        t = np.asarray(pair.t)
        self.ref.setData(t, np.asarray(pair.ref_v))
        self.dut.setData(t, np.asarray(pair.dut_v))
        if pair.ref_fit is not None and pair.dut_fit is not None:
            self.ref_fit.setData(t, np.asarray(pair.ref_fit))
            self.dut_fit.setData(t, np.asarray(pair.dut_fit))
        else:
            self.ref_fit.setData([], [])
            self.dut_fit.setData([], [])
        self.label.setText("Capture at %s" % fmt_si(pair.freq_hz, "Hz"))

    def clear(self) -> None:
        for c in (self.ref, self.dut, self.ref_fit, self.dut_fit):
            c.setData([], [])
        self.label.setText("No capture yet")
