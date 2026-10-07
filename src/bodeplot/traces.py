"""The traces of the Bode plot: the live sweep, kept sweeps, CSV files and theory curves
(SPEC.md section 10). No Qt.

A TraceSet owns the list and answers one question, drawn(): what is to be drawn, as it
stands or relative to one reference trace. The plot widget and the image export only
draw that answer, so the maths is in one place and is tested without a display.
"""
from __future__ import annotations

import bisect
import cmath
import math
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import PureWindowsPath

from .measure.theory import TransferFunction
from .models import PointResult, SweepResult

SLOTS = 8                       # colour slots (theme.SERIES); a trace beyond them is drawn muted
THEORY_POINTS_PER_DECADE = 50
EDGE_TOL = 1e-3                 # a frequency within 0.1 % of a reference point is that point
KIND_TEXT = {"live": "live sweep", "kept": "kept sweep", "file": "file", "theory": "theory"}


@dataclass
class Trace:
    id: int
    kind: str                   # "live" | "kept" | "file" | "theory"
    name: str
    slot: int | None            # colour slot 0..SLOTS-1; None: all slots were taken
    visible: bool = True
    points: list[PointResult] = field(default_factory=list)     # measured kinds, by frequency
    theory: TransferFunction | None = None                      # the theory kind: evaluated when drawn
    path: str | None = None                                     # the file kind
    auto_name: bool = False     # the name was made from the theory's values and follows them

    @property
    def removable(self) -> bool:
        return self.kind != "live"


@dataclass
class Drawn:
    """One visible trace as it is to be drawn: absolute, or divided by the reference."""
    trace: Trace
    freqs: list[float]
    h: list[complex]
    points: list[PointResult] | None = None     # the measured point behind each value; None: theory


def _usable(h: complex) -> bool:
    return math.isfinite(h.real) and math.isfinite(h.imag) and abs(h) > 0


def theory_grid(lo: float, hi: float, per_decade: int = THEORY_POINTS_PER_DECADE) -> list[float]:
    """Logarithmic frequencies from lo to hi for a smooth theory curve."""
    if not (lo > 0 and hi > 0):
        return []
    if hi <= lo:
        return [lo]
    n = int(math.ceil(math.log10(hi / lo) * per_decade - 1e-9)) + 1
    return [lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]


class _Reference:
    """A trace as the thing the others are divided by. A theory curve is evaluated at
    the frequency asked for. A measured trace is interpolated in log frequency (gain in dB
    and unwrapped phase, both linearly) and says nothing outside its own range."""

    def __init__(self, trace: Trace):
        self.theory = trace.theory
        pts = [p for p in trace.points if p.freq_hz > 0 and _usable(p.h)]
        self.f = [p.freq_hz for p in pts]
        self.db = [20.0 * math.log10(abs(p.h)) for p in pts]
        self.deg: list[float] = []
        for p in pts:
            d = math.degrees(cmath.phase(p.h))
            if self.deg:
                d += 360.0 * round((self.deg[-1] - d) / 360.0)
            self.deg.append(d)

    def _at_point(self, k: int) -> complex:
        return cmath.rect(10 ** (self.db[k] / 20.0), math.radians(self.deg[k]))

    def at(self, f: float) -> complex | None:
        if self.theory is not None:
            h = self.theory.h(f)
            return h if _usable(h) else None
        fs = self.f
        if not fs or f < fs[0] * (1 - EDGE_TOL) or f > fs[-1] * (1 + EDGE_TOL):
            return None
        i = bisect.bisect_left(fs, f)
        for k in (i - 1, i):
            if 0 <= k < len(fs) and abs(f - fs[k]) <= EDGE_TOL * fs[k]:
                return self._at_point(k)
        x = math.log(f / fs[i - 1]) / math.log(fs[i] / fs[i - 1])
        db = self.db[i - 1] + x * (self.db[i] - self.db[i - 1])
        deg = self.deg[i - 1] + x * (self.deg[i] - self.deg[i - 1])
        return cmath.rect(10 ** (db / 20.0), math.radians(deg))


class TraceSet:
    def __init__(self):
        self.live = Trace(0, "live", "Sweep", 0)
        self.traces: list[Trace] = [self.live]
        self.reference_id: int | None = None
        self._next_id = 1

    # ---- the list
    def get(self, trace_id: int) -> Trace | None:
        return next((t for t in self.traces if t.id == trace_id), None)

    def reference(self) -> Trace | None:
        return self.get(self.reference_id) if self.reference_id is not None else None

    def _free_slot(self) -> int | None:
        used = {t.slot for t in self.traces}
        return next((s for s in range(SLOTS) if s not in used), None)

    def _unique(self, name: str, own: Trace | None = None) -> str:
        taken = {t.name for t in self.traces if t is not own}
        if name not in taken:
            return name
        n = 2
        while "%s (%d)" % (name, n) in taken:
            n += 1
        return "%s (%d)" % (name, n)

    def _add(self, kind: str, name: str, **kw) -> Trace:
        t = Trace(self._next_id, kind, self._unique(name), self._free_slot(), **kw)
        self._next_id += 1
        self.traces.append(t)
        return t

    def add_file(self, result: SweepResult, path) -> Trace:
        """A loaded sweep as a trace. Points with no usable complex value get it from their
        gain and phase (an old or hand-made file); points with neither are dropped.
        Raises ValueError when nothing is left."""
        points = []
        for p in result.points:
            if not (p.freq_hz > 0):
                continue
            if not _usable(p.h):
                if not (math.isfinite(p.gain_db) and math.isfinite(p.phase_deg)):
                    continue
                p = replace(p, h=cmath.rect(10 ** (p.gain_db / 20.0), math.radians(p.phase_deg)))
            points.append(p)
        if not points:
            raise ValueError("it holds no sweep points")
        points.sort(key=lambda p: p.freq_hz)
        return self._add("file", PureWindowsPath(str(path)).stem or "file", points=points, path=str(path))

    def add_theory(self, tf: TransferFunction) -> Trace:
        return self._add("theory", tf.label(), theory=tf, auto_name=True)

    def set_theory(self, trace_id: int, tf: TransferFunction) -> None:
        t = self.get(trace_id)
        if t is None or t.kind != "theory":
            raise ValueError("not a theory trace")
        t.theory = tf
        if t.auto_name:
            t.name = self._unique(tf.label(), t)

    def keep_live(self, now: datetime | None = None) -> Trace:
        if not self.live.points:
            raise ValueError("there is no sweep to keep")
        stamp = (now or datetime.now()).strftime("%H:%M:%S")
        return self._add("kept", "Sweep " + stamp, points=list(self.live.points))

    def remove(self, trace_id: int) -> None:
        t = self.get(trace_id)
        if t is None or not t.removable:
            raise ValueError("this trace cannot be removed")
        self.traces.remove(t)
        if self.reference_id == trace_id:
            self.reference_id = None

    def rename(self, trace_id: int, name: str) -> str:
        """Returns the name the trace has afterwards (made unique; unchanged for an empty one)."""
        t = self.get(trace_id)
        name = (name or "").strip()
        if t is None:
            return name
        if name and name != t.name:
            t.name, t.auto_name = self._unique(name, t), False
        return t.name

    def set_visible(self, trace_id: int, on: bool) -> None:
        t = self.get(trace_id)
        if t is not None:
            t.visible = bool(on)

    def set_reference(self, trace_id: int | None) -> None:
        self.reference_id = trace_id if trace_id is not None and self.get(trace_id) is not None else None

    # ---- what is drawn
    def span(self, hint: tuple[float, float] | None = None) -> tuple[float, float] | None:
        """Frequency range of every measured trace, shown or not, joined with hint (the
        sweep settings): where a theory curve is drawn."""
        los, his = [], []
        if hint is not None and hint[0] > 0 and hint[1] > 0:
            los.append(min(hint))
            his.append(max(hint))
        for t in self.traces:
            fs = [p.freq_hz for p in t.points if p.freq_hz > 0]
            if fs:
                los.append(min(fs))
                his.append(max(fs))
        return (min(los), max(his)) if los else None

    def _absolute(self, t: Trace, span) -> Drawn:
        if t.theory is not None:
            freqs, hs = [], []
            for f in (theory_grid(*span) if span else []):
                h = t.theory.h(f)
                if _usable(h):
                    freqs.append(f)
                    hs.append(h)
            return Drawn(t, freqs, hs)
        pts = [p for p in t.points if p.freq_hz > 0 and _usable(p.h)]
        return Drawn(t, [p.freq_hz for p in pts], [p.h for p in pts], pts)

    def drawn(self, span_hint: tuple[float, float] | None = None, relative: bool = True) -> list[Drawn]:
        """The visible traces in list order. With a reference chosen (and relative True)
        every trace is divided by it: the reference itself becomes 1 (0 dB, 0 degrees), and a
        trace has values only where the reference has one. No extrapolation."""
        span = self.span(span_hint)
        ref_trace = self.reference() if relative else None
        ref = _Reference(ref_trace) if ref_trace is not None else None
        out = []
        for t in self.traces:
            if not t.visible:
                continue
            d = self._absolute(t, span)
            if ref is None:
                out.append(d)
                continue
            if t is ref_trace:
                out.append(Drawn(t, d.freqs, [1 + 0j] * len(d.freqs), d.points))
                continue
            freqs, hs, pts = [], [], ([] if d.points is not None else None)
            for i, (f, h) in enumerate(zip(d.freqs, d.h)):
                r = ref.at(f)
                if r is None or not _usable(r):
                    continue
                freqs.append(f)
                hs.append(h / r)
                if pts is not None:
                    pts.append(d.points[i])
            out.append(Drawn(t, freqs, hs, pts))
        return out
