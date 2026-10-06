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
        self._plain_ticks = False

    def tickValues(self, minVal, maxVal, size):
        """A log axis normally labels the decades only. Zoomed in to less than two decade
        lines there was one label or none (found by the user, 2026-10-06), so in that case
        the ticks are round frequencies (1-2-5 steps) and every one is labelled."""
        self._plain_ticks = False
        lo, hi = min(minVal, maxVal), max(minVal, maxVal)
        if self.logMode and hi > lo and math.floor(hi) - math.ceil(lo) + 1 < 2:
            try:
                f0, f1 = 10.0 ** lo, 10.0 ** hi
                raw = (f1 - f0) / max(2, int(size // 90))
                mag = 10.0 ** math.floor(math.log10(raw))
                step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw * (1 - 1e-9))
                k0, k1 = math.ceil(f0 / step - 1e-9), math.floor(f1 / step + 1e-9)
                vals = [k * step for k in range(k0, k1 + 1) if k * step > 0]
            except (OverflowError, ValueError, StopIteration):
                vals = []
            if 2 <= len(vals) <= 50:
                self._plain_ticks = True
                return [(step, [math.log10(v) for v in vals])]
        return super().tickValues(minVal, maxVal, size)

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            x = 10 ** v if self.logMode else v * scale
            if self.logMode and not self._plain_ticks and abs(v - round(v)) > 1e-6:
                out.append("")              # minor log ticks stay unlabelled
                continue
            num, prefix = split_si(float(x), 4)
            out.append((num + " " + prefix).strip())
        return out
