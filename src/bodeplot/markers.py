"""The markers of the Bode plot: the automatic ones (-3 dB, peak, notch, gain and phase
margin) and the user's own (SPEC.md section 10). No Qt.

A MarkerSet holds what is switched on and where the user's markers stand; evaluate()
reads one curve (measure/response.py) and returns the markers with their numbers. The
plot, the clipboard text and the image export only show that answer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .measure.response import Curve, crossings, extremum
from .units import fmt_si

KINDS = ("cutoff", "peak", "notch", "margins")      # the automatic markers, in menu order
MAX_USER = 8
DROP_DB = 3.0                   # the cut-off lies this far below the highest gain
PROMINENCE_DB = 1.0             # a peak or notch stands at least this far clear of both ends
SAME_FREQ = 1e-3                # two markers within 0.1 % have no slope between them
OUTSIDE = "outside the trace"
NO_VALUE = "no value here"


@dataclass
class Delta:
    """A user marker against the reference marker."""
    ref: str
    ratio: float                # frequency ratio
    db: float
    deg: float
    slope: float | None         # dB per decade; None when the two stand at one frequency


@dataclass
class Marker:
    name: str                   # "fc", "fL", "fH", "pk", "nt", "GM", "PM", "M1" ...
    kind: str                   # "cutoff" | "peak" | "notch" | "gm" | "pm" | "user"
    freq: float | None = None   # None: switched on, but the curve has none
    db: float | None = None     # None: no value at freq (outside the trace, or in a gap)
    deg: float | None = None    # unwrapped
    flagged: bool = False
    note: str = ""              # why there is no value
    extra: str = ""             # second label line of fH: bandwidth and Q
    margin: float | None = None     # GM in dB, PM in degrees
    number: int | None = None   # user markers: the 1 of M1
    is_ref: bool = False
    delta: Delta | None = None

    @property
    def found(self) -> bool:
        return self.freq is not None

    @property
    def has_value(self) -> bool:
        return self.db is not None


@dataclass
class Placed:
    """A marker as the plot shows it: its label and where its dots sit, in plot units."""
    marker: Marker
    text: str
    y_gain: float | None
    y_phase: float | None
    left: bool = False          # the label goes to the left of the dot: the curve rises to the right there
    value: str = ""             # the gain as the plot's unit writes it (the Markers panel's table)
    phase: str = ""             # the phase as the phase plot shows it; "" without a phase plot
    color: str = "Grey"         # the palette name of its line and dot (gui/theme.py MARKER_PALETTE)


class MarkerSet:
    def __init__(self):
        self.kinds: set[str] = set()
        self.user: dict[int, float] = {}        # number -> frequency
        self.ref: int | None = None
        self.trace_id: int = 0                  # the live sweep

    # ---- what is switched on
    def set_kind(self, kind: str, on: bool) -> None:
        if kind not in KINDS:
            raise ValueError("unknown marker kind %r" % kind)
        (self.kinds.add if on else self.kinds.discard)(kind)

    def add(self, freq: float) -> int | None:
        """A new user marker; returns its number, or None (limit reached, impossible frequency)."""
        if len(self.user) >= MAX_USER or not (freq > 0 and math.isfinite(freq)):
            return None
        n = next(k for k in range(1, MAX_USER + 1) if k not in self.user)
        self.user[n] = float(freq)
        return n

    def move(self, number: int, freq: float) -> bool:
        if number not in self.user or not (freq > 0 and math.isfinite(freq)):
            return False
        self.user[number] = float(freq)
        return True

    def remove(self, number: int) -> None:
        self.user.pop(number, None)
        if self.ref == number:
            self.ref = None

    def clear_user(self) -> None:
        self.user.clear()
        self.ref = None

    def toggle_ref(self, number: int) -> None:
        self.ref = None if self.ref == number or number not in self.user else number

    # ---- the answer
    def evaluate(self, c: Curve, margins: bool = True) -> list[Marker]:
        """The markers for this curve, in the order -3 dB, peak, notch, margins, user. An
        automatic marker that is switched on and does not exist comes back with freq None.
        margins False: the margins make no sense here (relative display, no phase) and are
        left out."""
        out: list[Marker] = []
        top, has_peak = _peak(c, True)
        if "cutoff" in self.kinds:
            out += _cutoffs(c, top)
        if "peak" in self.kinds:
            out.append(_at(c, "pk", "peak", top.f, top.db) if has_peak else Marker("pk", "peak"))
        if "notch" in self.kinds:
            low, has_notch = _peak(c, False)
            out.append(_at(c, "nt", "notch", low.f, low.db) if has_notch else Marker("nt", "notch"))
        if "margins" in self.kinds and margins:
            out += [_gain_margin(c), _phase_margin(c)]
        users = {n: self._user(c, n, f) for n, f in sorted(self.user.items())}
        ref = users.get(self.ref)
        for n, m in users.items():
            if ref is not None and m is not ref and m.has_value and ref.has_value:
                ratio = m.freq / ref.freq
                ddb = m.db - ref.db
                slope = ddb / math.log10(ratio) if abs(ratio - 1.0) > SAME_FREQ else None
                m.delta = Delta(ref.name, ratio, ddb, m.deg - ref.deg, slope)
            out.append(m)
        return out

    def _user(self, c: Curve, n: int, f: float) -> Marker:
        m = _at(c, "M%d" % n, "user", f)
        m.number, m.is_ref = n, n == self.ref
        if not m.has_value:
            span = c.span()
            m.note = OUTSIDE if span is None or not (span[0] * (1 - 1e-3) <= f <= span[1] * (1 + 1e-3)) else NO_VALUE
        return m


def _at(c: Curve, name: str, kind: str, f: float, db: float | None = None) -> Marker:
    """A marker at f with the curve's values there (db given: the refined gain of an extreme)."""
    v = c.at(f)
    if v is None:
        return Marker(name, kind, f)
    return Marker(name, kind, f, v[0] if db is None else db, v[1], c.flagged_at(f))


def _peak(c: Curve, highest: bool):
    """(extreme, is it a real peak / notch). When it is not, the extreme is the plain
    highest (lowest) point, not a refined one. (None, False) for an empty curve."""
    e = extremum(c, highest)
    if e is None:
        return None, False
    idx = c.usable()
    ends = (c.db[idx[0]], c.db[idx[-1]])
    clear = e.db - max(ends) if highest else min(ends) - e.db
    if e.interior and clear >= PROMINENCE_DB:
        return e, True
    e.f, e.db = c.f[e.index], c.db[e.index]
    return e, False


def _cross(c: Curve, i: int, j: int, level: float) -> float:
    a, b = c.db[i] - level, c.db[j] - level
    if a == b:
        return c.f[i]
    return c.f[i] * (c.f[j] / c.f[i]) ** (a / (a - b))


def _cutoffs(c: Curve, top) -> list[Marker]:
    if top is None:
        return [Marker("fc", "cutoff")]
    level = top.db - DROP_DB
    if c.db[top.index] <= level:                # the refined peak stands 3 dB over every point: count from the
        level = c.db[top.index] - DROP_DB       # highest point, or the level would lie above the whole curve
    lo = hi = None
    k = top.index
    while k > 0 and c.ok[k - 1]:                # down in frequency, to the first crossing or a gap
        if c.db[k - 1] <= level:
            lo = _cross(c, k - 1, k, level)
            break
        k -= 1
    k = top.index
    while k < len(c.f) - 1 and c.ok[k + 1]:
        if c.db[k + 1] <= level:
            hi = _cross(c, k, k + 1, level)
            break
        k += 1
    if lo is None and hi is None:
        return [Marker("fc", "cutoff")]
    if lo is None or hi is None:
        return [_at(c, "fc", "cutoff", lo if hi is None else hi, level)]
    low, high = _at(c, "fL", "cutoff", lo, level), _at(c, "fH", "cutoff", hi, level)
    bw = hi - lo
    high.extra = "BW %s  Q %.3g" % (fmt_si(bw, "Hz", 3), math.sqrt(lo * hi) / bw)
    return [low, high]


def _phase_margin(c: Curve) -> Marker:
    best = None
    for f in crossings(c, 0.0, "db"):
        v = c.at(f)
        if v is None:
            continue
        pm = 180.0 - (-v[1]) % 360.0                    # 180 + phase, brought into -180 .. +180
        if best is None or pm < best.margin:
            best = Marker("PM", "pm", f, 0.0, v[1], c.flagged_at(f), margin=pm)
    return best or Marker("PM", "pm")


def _gain_margin(c: Curve) -> Marker:
    idx = c.usable()
    if not idx:
        return Marker("GM", "gm")
    lo, hi = min(c.deg[i] for i in idx), max(c.deg[i] for i in idx)
    best = None
    k = math.ceil((lo + 180.0) / 360.0)
    while -180.0 + 360.0 * k <= hi:
        level = -180.0 + 360.0 * k
        for f in crossings(c, level, "deg"):
            v = c.at(f)
            if v is not None and (best is None or -v[0] < best.margin):
                best = Marker("GM", "gm", f, v[0], level, c.flagged_at(f), margin=-v[0])
        k += 1
    return best or Marker("GM", "gm")


# ---- texts
def freq_text(f: float) -> str:
    return fmt_si(f, "Hz", 3)


def _ratio(r: float) -> str:
    """A frequency ratio as a plain number: 0.5, 10, 3333."""
    return "%.0f" % r if r >= 1000 else "%.3g" % r


def delta_text(d: Delta | None, with_phase: bool = True) -> str:
    if d is None:
        return ""
    text = "Δ %s  ×%s  %+.1f dB" % (d.ref, _ratio(d.ratio), d.db) + ("  %+.1f°" % d.deg if with_phase else "")
    return text + ("  %+.1f dB/dec" % d.slope if d.slope is not None else "")


def label(m: Marker, value: str = "", phase: float | None = None) -> str:
    """The text next to a marker. value: its gain as the plot's unit writes it; phase: as
    the phase plot shows it, None without a phase plot."""
    flag = "  (flagged)" if m.flagged else ""
    if m.kind == "gm":
        return "GM %.1f dB at %s%s" % (m.margin, freq_text(m.freq), flag)
    if m.kind == "pm":
        return "PM %.1f° at %s%s" % (m.margin, freq_text(m.freq), flag)
    head = "%s %s" % (m.name, freq_text(m.freq))
    if not m.has_value:
        return "%s  %s%s" % (head, m.note, "  (ref)" if m.is_ref else "")
    text = "  ".join([head, value] + (["%+.1f°" % phase] if phase is not None else []))
    text += ("  (ref)" if m.is_ref else "") + flag
    second = m.extra or delta_text(m.delta, phase is not None)
    return text + ("\n" + second if second else "")


def notes(m: Marker, with_phase: bool = True) -> str:
    """What a table says about a marker besides its numbers: margin, bandwidth and Q,
    reference marker, the difference to it, why there is no value, flagged."""
    out = []
    if m.kind == "gm":
        out.append("gain margin %.2f dB" % m.margin)
    if m.kind == "pm":
        out.append("phase margin %.2f deg" % m.margin)
    if m.extra:
        out.append(m.extra.replace("  ", ", "))
    if m.is_ref:
        out.append("reference marker")
    if m.delta is not None:
        d = m.delta
        out.append("rel. %s: x%s, %+.1f dB" % (d.ref, _ratio(d.ratio), d.db)
                   + (", %+.1f deg" % d.deg if with_phase else "")
                   + (", %+.1f dB/dec" % d.slope if d.slope is not None else ""))
    if m.note:
        out.append(m.note)
    if m.flagged:
        out.append("flagged")
    return "; ".join(out)


def table(markers: list[Marker], title: str, phase=lambda m: m.deg, with_phase: bool = True) -> str:
    """The markers as tab-separated text for the clipboard. Gain in dB, plain numbers.
    with_phase False (a magnitude-only measurement): the phase column stays empty."""
    rows = [title, "Marker\tFrequency (Hz)\tGain (dB)\tPhase (deg)\tNote"]
    for m in markers:
        if not m.found:
            rows.append("%s\t\t\t\tnone" % m.name)
            continue
        ph = phase(m) if m.has_value and with_phase else None
        rows.append("%s\t%.2f\t%s\t%s\t%s" % (m.name, m.freq, "%.3f" % m.db if m.has_value else "",
                                             "%.2f" % ph if ph is not None else "", notes(m, with_phase)))
    return "\n".join(rows) + "\n"
