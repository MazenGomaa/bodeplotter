"""Pure maths on one frequency response: a curve of gain (dB) and unwrapped phase (degrees)
over frequency (SPEC.md section 10). No Qt, no knowledge of traces or markers.

Between two points the gain in dB and the unwrapped phase are interpolated linearly over
the logarithm of the frequency. A dead point (|H| zero or not finite) has no value, and
neither has the stretch between it and its neighbours: a gap is not bridged.
"""
from __future__ import annotations

import bisect
import cmath
import math
from dataclasses import dataclass, field

EDGE_TOL = 1e-3                 # a frequency within 0.1 % of a point is that point


def usable(h: complex) -> bool:
    return math.isfinite(h.real) and math.isfinite(h.imag) and abs(h) > 0


@dataclass
class Curve:
    f: list[float] = field(default_factory=list)        # ascending
    db: list[float] = field(default_factory=list)
    deg: list[float] = field(default_factory=list)      # unwrapped from the first usable point
    ok: list[bool] = field(default_factory=list)        # False: a dead point
    flagged: list[bool] = field(default_factory=list)   # the caller's mark per point

    def usable(self) -> list[int]:
        return [i for i, ok in enumerate(self.ok) if ok]

    def span(self) -> tuple[float, float] | None:
        """First and last frequency of the curve, dead points included."""
        return (self.f[0], self.f[-1]) if self.f else None

    def locate(self, freq: float) -> tuple[int, int, float] | None:
        """(i, j, x): the value at freq is v[i] + x * (v[j] - v[i]); i == j on a point.
        None outside the curve, on a dead point and inside a gap."""
        fs = self.f
        if not fs or not (freq > 0) or freq < fs[0] * (1 - EDGE_TOL) or freq > fs[-1] * (1 + EDGE_TOL):
            return None
        i = bisect.bisect_left(fs, freq)
        for k in (i - 1, i):
            if 0 <= k < len(fs) and abs(freq - fs[k]) <= EDGE_TOL * fs[k]:
                return (k, k, 0.0) if self.ok[k] else None
        if i == 0 or i == len(fs):                      # inside the range test, a rounding away from the end point
            k = 0 if i == 0 else len(fs) - 1
            return (k, k, 0.0) if self.ok[k] else None
        if not (self.ok[i - 1] and self.ok[i]):
            return None
        return i - 1, i, math.log(freq / fs[i - 1]) / math.log(fs[i] / fs[i - 1])

    def interp(self, freq: float, values) -> float | None:
        """Any per-point quantity at freq, by the rule of the curve. None where the curve
        has no value or the quantity is not finite there."""
        loc = self.locate(freq)
        if loc is None:
            return None
        i, j, x = loc
        v = values[i] + x * (values[j] - values[i]) if i != j else values[i]
        return float(v) if math.isfinite(v) else None

    def at(self, freq: float) -> tuple[float, float] | None:
        """(gain in dB, unwrapped phase in degrees) at freq, or None."""
        loc = self.locate(freq)
        if loc is None:
            return None
        i, j, x = loc
        return self.db[i] + x * (self.db[j] - self.db[i]), self.deg[i] + x * (self.deg[j] - self.deg[i])

    def flagged_at(self, freq: float) -> bool:
        loc = self.locate(freq)
        return loc is not None and (self.flagged[loc[0]] or self.flagged[loc[1]])


def curve(freqs, hs, flagged=None) -> Curve:
    """A curve from frequencies and complex values. Rows with an impossible frequency are
    dropped; the rest is put in ascending order."""
    flagged = list(flagged) if flagged is not None else [False] * len(freqs)
    rows = sorted(((float(f), complex(h), bool(b)) for f, h, b in zip(freqs, hs, flagged)
                   if f > 0 and math.isfinite(f)), key=lambda r: r[0])
    c = Curve()
    last = None
    for f, h, bad in rows:
        ok = usable(h)
        d = math.degrees(cmath.phase(h)) if ok else 0.0
        if ok and last is not None:
            d += 360.0 * round((last - d) / 360.0)
        if ok:
            last = d
        c.f.append(f)
        c.db.append(20.0 * math.log10(abs(h)) if ok else 0.0)
        c.deg.append(d)
        c.ok.append(ok)
        c.flagged.append(bad)
    return c


def crossings(c: Curve, level: float, of: str = "db") -> list[float]:
    """The frequencies where the gain (of="db") or the unwrapped phase (of="deg") passes
    through level, ascending. Touching the level without passing it is no crossing, and
    nothing is found across a gap."""
    vals = c.db if of == "db" else c.deg
    out: list[float] = []
    prev_sign, prev_i, zero_f = 0, None, None
    for i in range(len(c.f)):
        if not c.ok[i]:
            prev_sign, prev_i, zero_f = 0, None, None
            continue
        d = vals[i] - level
        sign = (d > 0) - (d < 0)
        if sign == 0:
            if zero_f is None:
                zero_f = c.f[i]
            continue
        if prev_sign and sign != prev_sign:
            if zero_f is not None:
                out.append(zero_f)
            else:
                a = vals[prev_i] - level
                out.append(c.f[prev_i] * (c.f[i] / c.f[prev_i]) ** (a / (a - d)))
        prev_sign, prev_i, zero_f = sign, i, None
    return out


@dataclass
class Extremum:
    f: float
    db: float
    index: int                  # the extreme point itself
    interior: bool              # not the first or the last usable point


def extremum(c: Curve, highest: bool = True) -> Extremum | None:
    """The highest (or lowest) gain of the curve. Its position is refined with a parabola
    through the extreme point and its two neighbours (dB over log frequency) when both
    exist with no gap between the three."""
    idx = c.usable()
    if not idx:
        return None
    i = (max if highest else min)(idx, key=lambda k: c.db[k])
    f, db = c.f[i], c.db[i]
    if 0 < i < len(c.f) - 1 and c.ok[i - 1] and c.ok[i + 1] and c.f[i - 1] < c.f[i] < c.f[i + 1]:
        x0, x1, x2 = (math.log10(c.f[k]) for k in (i - 1, i, i + 1))
        y0, y1, y2 = c.db[i - 1], c.db[i], c.db[i + 1]
        den = (x0 - x1) * (x0 - x2) * (x1 - x2)
        a = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / den
        b = (x2 * x2 * (y0 - y1) + x1 * x1 * (y2 - y0) + x0 * x0 * (y1 - y2)) / den
        if a != 0 and (a < 0) == highest:
            xv = -b / (2 * a)
            if x0 < xv < x2:
                f, db = 10.0 ** xv, y1 + a * (xv * xv - x1 * x1) + b * (xv - x1)
    return Extremum(f, db, i, idx[0] < i < idx[-1])
