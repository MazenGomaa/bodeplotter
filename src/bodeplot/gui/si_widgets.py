"""Input and axis widgets that speak SI prefixes (k, M, m, µ, n)."""
from __future__ import annotations

import math

import pyqtgraph as pg
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox

from ..units import fmt_si, parse_si, split_si


class SiSpinBox(QDoubleSpinBox):
    """A spin box that shows '20 MHz' and accepts '20M', '20 MHz', '1.5k', '2e7', '20meg'.
    The arrows step through 1-2-5 values."""

    def __init__(self, lo: float, hi: float, value: float, unit: str = "", digits: int = 6, parent=None):
        super().__init__(parent)
        self.unit, self.digits = unit, digits
        self.setDecimals(9)                 # resolution of the stored value, not of the display
        self.setRange(lo, hi)
        self.setKeyboardTracking(False)
        self.setValue(value)
        self.setToolTip("Accepts SI multipliers: 20M, 1.5k, 100n (M = mega, m = milli)")

    def textFromValue(self, value: float) -> str:
        return fmt_si(value, self.unit, self.digits)

    def valueFromText(self, text: str) -> float:
        try:
            return parse_si(text, self.unit)
        except ValueError:
            return self.value()

    def validate(self, text: str, pos: int):
        try:
            v = parse_si(text, self.unit)
        except ValueError:
            return QValidator.Intermediate, text, pos
        if self.minimum() <= v <= self.maximum():
            return QValidator.Acceptable, text, pos
        return QValidator.Intermediate, text, pos

    def fixup(self, text: str) -> str:
        return self.textFromValue(self.value())

    def stepBy(self, steps: int) -> None:
        v = self.value()
        if v <= 0:
            v = self.minimum() if self.minimum() > 0 else 1.0
        for _ in range(abs(steps)):
            exp = math.floor(math.log10(v) + 1e-12)
            mant = v / 10 ** exp
            if steps > 0:
                mant = 2 if mant < 2 - 1e-9 else 5 if mant < 5 - 1e-9 else 10
            else:
                mant = 5 if mant > 5 + 1e-9 else 2 if mant > 2 + 1e-9 else 1 if mant > 1 + 1e-9 else 0.5
            v = mant * 10 ** exp
        self.setValue(min(max(v, self.minimum()), self.maximum()))


class SiAxis(pg.AxisItem):
    """Axis whose ticks read 100, 1 k, 10 k, 1 M (on a log axis the tick values are exponents)."""

    def __init__(self, orientation: str, **kw):
        super().__init__(orientation, **kw)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            x = 10 ** v if self.logMode else v * scale
            if self.logMode and abs(v - round(v)) > 1e-6:
                out.append("")              # minor log ticks stay unlabelled
                continue
            num, prefix = split_si(float(x), 4)
            out.append((num + " " + prefix).strip())
        return out
