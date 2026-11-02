"""Response metrics (v3, part 1): what the shape of one response curve says. No Qt.

Design: docs/superpowers/specs/2026-10-07-response-metrics-design.md, section 3. Everything
works on a Curve (measure/response.py): gain in dB and unwrapped phase over frequency. A
slope is always that of a least-squares line through the points of a window, gain in dB
over log10 of the frequency, and no window reaches across a gap.
"""
from __future__ import annotations

import bisect
import math
import statistics
from dataclasses import dataclass, field

from .response import Curve, Extremum, extremum, refine

FLAT_SLOPE = 3.0            # dB/decade: a point is flat when the line through its window is no steeper
FLAT_WINDOW = 1.0 / 3.0     # decades, the window of that line
FLAT_SPAN = 1.0 / 3.0       # decades a flat stretch must span
FLAT_POINTS = 5             # and the points it must have
FLAT_RANGE = 3.0            # dB a flat stretch may cover from its lowest to its highest gain
DROP_DB = 3.0               # the cut-off lies this far below the passband level
FLOOR_DB = 10.0             # a flat stretch this far below the passband level is a stopband floor
PROMINENCE_DB = 1.0         # a peak or notch stands this far clear of its surroundings
NOISE_WINDOW = 1.0          # decades over which the scatter of the curve is estimated
NOISE_FACTOR = 8.0          # ... and a peak or notch stands this many times the scatter clear
NOISE_DB = 0.5              # dB of scatter (over FLAT_WINDOW): from here to an end of the curve it is noise
NOISE_FLIPS = 0.35          # ... and its second differences change sign this often (noise ~0.73, a bend ~0)
NOISE_POINTS = 9            # the fewest points that test is made on, and the fewest a noisy end must have
NOISE_GAP = 3               # points: a gap this short in the noise, where it looks clean by chance, does not end it
NOISE_TURNS = 0.4           # a noisy end turns up or down this often from point to point (noise ~0.67)
NOISE_NEAR = 30.0           # dB over a noise floor's level: the scatter there is judged close around each point
SCATTER_POINTS = 41         # a scatter is taken over at most this many points (a decade at 40 per decade)
NOISE_RISE = 12.0           # dB over the noise's level: a point this high is still the curve (noise peaks reach ~10)
TROUGH_DB = 0.1             # a dip inside the passband counts for the ripple from this depth
SLOPE_WINDOW = 0.5          # decades of the window that measures a roll-off
SETTLE_DECADES = 1.0        # a floor nearer the cut-off than this: the slope has not settled, it is a limit
STEEPENING = 2.0            # dB/decade: the outermost window is this much steeper than the settled slope: a limit
FEW_POINTS = 5              # fewer points across a resonance: its top and its Q are uncertain
MIN_POINTS = 5              # fewer usable points: no analysis
EPS = 1e-9
TOO_FEW = "fewer than %d usable points" % MIN_POINTS


@dataclass
class Value:
    v: float
    limit: bool = False         # True: "at least" (the sweep or a short transition cut it short)
    flagged: bool = False       # it rests on a flagged point


@dataclass
class Band:
    """A flat stretch of the curve."""
    first: int                  # index of its first and last point
    last: int
    lo: float                   # their frequencies
    hi: float
    level: float                # dB
    spread: float               # highest minus lowest gain of the stretch, dB
    kind: str                   # "pass" | "floor" | "flat"
    at_low: bool                # it touches the low (high) end of the curve
    at_high: bool
    flagged: bool = False


@dataclass
class Noise:
    """A stretch at an end of the curve where the gain is the instrument's noise, not the circuit."""
    first: int                  # index of its first and last point
    last: int
    lo: float                   # their frequencies
    hi: float
    level: float                # dB, the median gain of the stretch
    at_low: bool                # it is at the low end of the curve (else at the high end)


@dataclass
class Cutoff:
    f: float
    side: str                   # "high": the passband lies below it (a low-pass edge); "low": above it
    inner: int                  # the two points it lies between; inner is the one towards the passband
    outer: int
    band: int = -1              # the first point of the flat stretch it bounds; -1: counted from the peak
    flagged: bool = False
    slope: Value | None = None          # dB/decade, signed
    order: Value | None = None
    attenuation: Value | None = None    # dB, positive
    falling: bool = False       # the sweep ends before the stop band levels off


@dataclass
class Resonance:
    kind: str                   # "peak" | "notch"
    index: int
    f0: float
    db: float
    height: float               # how far it stands clear (the depth of a notch), dB, positive
    q_width: float | None = None
    q_phase: float | None = None
    points: int = 0             # points across it
    flagged: bool = False


@dataclass
class Passband:
    """The part the -3 dB marker needs: the level and the cut-offs."""
    level: float | None = None
    source: str = ""            # "flat": from a flat stretch; "peak": the highest gain; "": no curve
    bands: list[Band] = field(default_factory=list)
    cutoffs: list[Cutoff] = field(default_factory=list)
    top: Extremum | None = None
    slopes: list = field(default_factory=list)      # the local slope at every point (None: no value)


@dataclass
class Metrics:
    ok: bool = False
    reason: str = ""            # why there is no analysis
    points: int = 0             # usable points
    flagged_share: float = 0.0
    level: float | None = None
    source: str = ""
    level_flagged: bool = False
    ripple: float | None = None         # flat passbands only
    bands: list[Band] = field(default_factory=list)
    cutoffs: list[Cutoff] = field(default_factory=list)
    pair: tuple[Cutoff, Cutoff] | None = None       # the two cut-offs of centre, bandwidth and Q
    centre: float | None = None
    bandwidth: float | None = None
    q: float | None = None
    resonances: list[Resonance] = field(default_factory=list)
    noise: list[Noise] = field(default_factory=list)    # left out of everything above


# ---- small tools
def segments(c: Curve) -> list[tuple[int, int]]:
    """The runs of usable points, as (first index, last index)."""
    out, start = [], None
    for i, ok in enumerate(c.ok):
        if ok and start is None:
            start = i
        if not ok and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(c.ok) - 1))
    return out


def line_slope(xs, ys) -> float | None:
    """Slope of the least-squares line; None with fewer than two different x."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


class _Sums:
    """Running sums of x and y: the slope of the least-squares line over any range of points
    in constant time (a narrow linear sweep puts thousands of points in one window)."""

    def __init__(self, x, y):
        x0 = x[0] if x else 0.0                         # centred: the sums keep their precision
        self.n, self.x, self.y, self.xx, self.xy = [0], [0.0], [0.0], [0.0], [0.0]
        for u, v in zip(x, y):
            u -= x0
            self.n.append(self.n[-1] + 1)
            self.x.append(self.x[-1] + u)
            self.y.append(self.y[-1] + v)
            self.xx.append(self.xx[-1] + u * u)
            self.xy.append(self.xy[-1] + u * v)

    def slope(self, j0: int, j1: int) -> float | None:
        """As line_slope(x[j0:j1 + 1], y[j0:j1 + 1])."""
        n = j1 - j0 + 1
        if n < 2:
            return None
        sx, sy = self.x[j1 + 1] - self.x[j0], self.y[j1 + 1] - self.y[j0]
        sxx, sxy = self.xx[j1 + 1] - self.xx[j0], self.xy[j1 + 1] - self.xy[j0]
        den = n * sxx - sx * sx
        if den <= 1e-9 * n * sxx:                       # all x the same, but for rounding
            return None
        return (n * sxy - sx * sy) / den


def _window(x, a: int, b: int, i: int, width: float) -> tuple[int, int]:
    """The points of the run a..b inside a window of that width around point i; at an end of
    the run the window is moved inwards, not cut."""
    if x[b] - x[a] <= width:
        return a, b
    centre = min(max(x[i], x[a] + width / 2), x[b] - width / 2)
    j0 = bisect.bisect_left(x, centre - width / 2 - EPS, a, b + 1)
    j1 = bisect.bisect_right(x, centre + width / 2 + EPS, a, b + 1) - 1
    return j0, j1


def _around(x, a: int, b: int, i: int, width: float, least: int = 0) -> tuple[int, int]:
    """The window of a scatter: _window, widened to at least `least` points, then cut to the
    SCATTER_POINTS nearest point i."""
    j0, j1 = _window(x, a, b, i, width)
    while j1 - j0 + 1 < least and (j0 > a or j1 < b):
        j0, j1 = max(a, j0 - 1), min(b, j1 + 1)
    if j1 - j0 + 1 > SCATTER_POINTS:
        j0 = max(j0, min(i - SCATTER_POINTS // 2, j1 - SCATTER_POINTS + 1))
        j1 = j0 + SCATTER_POINTS - 1
    return j0, j1


def _cross(c: Curve, i: int, j: int, level: float) -> float:
    a, b = c.db[i] - level, c.db[j] - level
    if a == b:
        return c.f[i]
    return c.f[i] * (c.f[j] / c.f[i]) ** (a / (a - b))


def _logs(c: Curve) -> list[float]:
    return [math.log10(f) for f in c.f]


def local_slopes(c: Curve, x=None) -> list:
    """dB per decade at every point, over a window of FLAT_WINDOW; None where there is none."""
    x = x or _logs(c)
    out: list = [None] * len(c.f)
    sums = _Sums(x, c.db)
    for a, b in segments(c):
        for i in range(a, b + 1):
            j0, j1 = _window(x, a, b, i, FLAT_WINDOW)
            if j1 - j0 < 2:
                j0, j1 = max(a, i - 1), min(b, i + 1)
            if j1 - j0 >= 2:
                out[i] = sums.slope(j0, j1)
    return out


def _scatter(c: Curve, x, a: int, b: int, i: int, width: float = NOISE_WINDOW) -> float:
    """The scatter of the gain around point i, from the second differences of its neighbourhood."""
    j0, j1 = _around(x, a, b, i, width)
    d2 = [abs(c.db[j - 1] - 2 * c.db[j] + c.db[j + 1]) for j in range(max(j0, a + 1), min(j1, b - 1) + 1)]
    return 1.4826 * statistics.median(d2) / math.sqrt(6.0) if d2 else 0.0


def _near_scatter(c: Curve, x, a: int, b: int, i: int) -> float:
    """The scatter close around point i (FLAT_WINDOW, at least NOISE_POINTS points) from the
    second differences that change sign against both neighbours, as noise does; the bends of
    the curve keep their sign and are not counted, and neither is point i's own (i - 1 to i + 1)."""
    j0, j1 = _around(x, a, b, i, FLAT_WINDOW, NOISE_POINTS)
    d2 = {j: c.db[j - 1] - 2 * c.db[j] + c.db[j + 1] for j in range(max(j0, a + 1), min(j1, b - 1) + 1)}
    noise = [abs(v) for j, v in d2.items()
             if abs(j - i) > 1 and v * d2.get(j - 1, -v) < 0 and v * d2.get(j + 1, -v) < 0]
    return 1.4826 * statistics.median(noise) / math.sqrt(6.0) if len(noise) >= 3 else 0.0


def _noisy(c: Curve, x, a: int, b: int, i: int) -> bool:
    """Point i lies in noise: around it (FLAT_WINDOW, at least NOISE_POINTS points) the gain
    scatters by more than NOISE_DB and its second differences keep changing sign. The bend of a
    notch or of a sharp edge gives large second differences too, but of one sign."""
    j0, j1 = _around(x, a, b, i, FLAT_WINDOW, NOISE_POINTS)
    d2 = [c.db[j - 1] - 2 * c.db[j] + c.db[j + 1] for j in range(max(j0, a + 1), min(j1, b - 1) + 1)]
    if len(d2) < 3:
        return False
    flips = sum(1 for u, v in zip(d2, d2[1:]) if u * v < 0) / (len(d2) - 1)
    return 1.4826 * statistics.median(abs(v) for v in d2) / math.sqrt(6.0) > NOISE_DB and flips >= NOISE_FLIPS


def noise_ends(c: Curve) -> list[Noise]:
    """The ends of the curve that are lost in the noise: from an end inwards, the points that
    lie in noise (_noisy), at least NOISE_POINTS of them (fewer: a sparse sweep across a notch
    looks the same), lying FLOOR_DB or more below the
    highest gain of the rest. The sudden bend of a steep edge scatters the second differences
    too: the points up to the outermost one that stands NOISE_RISE over the noise's level are
    given back (noise never reaches that high). What is left must turn up or down at NOISE_TURNS
    of its points, as noise does; a sparse sweep across a notch runs one way for many points.
    A curve that is noise all through has none (nothing would be left)."""
    segs = segments(c)
    if not segs:
        return []
    x = _logs(c)
    out = []
    for (a, b), step in ((segs[0], +1), (segs[-1], -1)):
        start = a if step > 0 else b
        k, end = start, None                            # end: the innermost noisy point so far
        while a <= k <= b:
            if _noisy(c, x, a, b, k):
                end = k
            elif end is None or abs(k - end) > NOISE_GAP:
                break
            k += step
        if end is None:
            continue
        first, last = sorted((start, end))
        if last - first + 1 < NOISE_POINTS:
            continue
        level = statistics.median(c.db[first:last + 1])
        high = [i for i in range(first, last + 1) if c.db[i] > level + NOISE_RISE]
        if high:                                        # the curve, up to the outermost point that high
            first, last = (first, min(high) - 1) if step > 0 else (max(high) + 1, last)
        if last - first + 1 < NOISE_POINTS:
            continue
        d1 = [c.db[i + 1] - c.db[i] for i in range(first, last)]
        if sum(1 for u, v in zip(d1, d1[1:]) if u * v < 0) / (len(d1) - 1) < NOISE_TURNS:
            continue                                    # long runs one way: a sparse curve, not noise
        rest = [c.db[i] for i in c.usable() if not first <= i <= last]
        if len(rest) >= MIN_POINTS and level <= max(rest) - FLOOR_DB:
            out.append(Noise(first, last, c.f[first], c.f[last], level, step > 0))
    if len(out) == 2 and out[1].first - out[0].last - 1 < MIN_POINTS:      # all of it noise, but for a few
        return []
    return out


def without_noise(c: Curve, noise: list[Noise]) -> Curve:
    """The curve with its noisy ends as dead points."""
    ok = list(c.ok)
    for n in noise:
        ok[n.first:n.last + 1] = [False] * (n.last - n.first + 1)
    return Curve(c.f, c.db, c.deg, ok, c.flagged)


def ends_extreme(c: Curve, highest: bool):
    """(extreme, is it a real peak / notch against both ends of the curve): the rule of the
    peak and notch markers. When it is not, the extreme is the plain highest (lowest) point.
    (None, False) for an empty curve."""
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


# ---- flat stretches
def _bands(c: Curve, x, slopes) -> list[Band]:
    idx = c.usable()
    if not idx:
        return []
    runs, start = [], None
    for i in range(len(c.f) + 1):
        flat = i < len(c.f) and c.ok[i] and slopes[i] is not None and abs(slopes[i]) <= FLAT_SLOPE
        if flat and start is None:
            start = i
        if not flat and start is not None:
            runs.append((start, i - 1))
            start = None
    pieces = []
    for a, b in runs:               # cut a run where it leaves FLAT_RANGE; what remains is tested again
        s = a
        lo = hi = c.db[a]
        for i in range(a + 1, b + 1):
            lo, hi = min(lo, c.db[i]), max(hi, c.db[i])
            if hi - lo > FLAT_RANGE:
                pieces.append((s, i - 1))
                s, lo, hi = i, c.db[i], c.db[i]
        pieces.append((s, b))
    out = []
    for a, b in pieces:
        if b - a + 1 < FLAT_POINTS or x[b] - x[a] < FLAT_SPAN - EPS:
            continue
        order = sorted(range(a, b + 1), key=lambda i: abs(slopes[i]))
        calm = order[:max(3, (len(order) + 3) // 4)]    # the flattest quarter: a shoulder or the foot of a hump at
                                                        # its edge does not pull the level
        vals = c.db[a:b + 1]
        at_low = all(slopes[i] is None for i in idx if i < a)      # nothing before it but points without a
        at_high = all(slopes[i] is None for i in idx if i > b)     # slope (a linear sweep's first ones)
        out.append(Band(a, b, c.f[a], c.f[b], statistics.median(c.db[i] for i in calm), max(vals) - min(vals),
                        "flat", at_low, at_high, any(c.flagged[a:b + 1])))
    if out:
        top = max(band.level for band in out)
        for band in out:
            band.kind = "pass" if band.level >= top - DROP_DB else "floor" if band.level <= top - FLOOR_DB else "flat"
    return out


# ---- cut-offs
def _walk(c: Curve, start: int, step: int, level: float, stop: set[int]) -> tuple[int, int] | None:
    """From point start outwards (step -1 or +1) to the first point at or below level:
    (the point before it, that point). None at a gap, at the end, or on reaching a point of stop."""
    k = start
    while 0 <= k + step < len(c.f) and c.ok[k + step] and (k + step) not in stop:
        if c.db[k + step] <= level:
            return k, k + step
        k += step
    return None


def passband(c: Curve) -> Passband:
    """The passband level and the cut-offs 3 dB below it. With a flat stretch the level is
    that of the highest one; without, the highest gain of the curve (the rule of v2)."""
    p = Passband()
    if not c.usable():
        return p
    x = _logs(c)
    p.slopes = local_slopes(c, x)
    p.bands = _bands(c, x, p.slopes)
    p.top, _real = ends_extreme(c, True)
    passes = [b for b in p.bands if b.kind == "pass"]
    if passes:
        p.source, p.level = "flat", max(b.level for b in passes)
        level = p.level - DROP_DB
        inside = {i for b in passes for i in range(b.first, b.last + 1)}
        for b in passes:
            for start, step, side in ((b.first, -1, "low"), (b.last, +1, "high")):
                hit = _walk(c, start, step, level, inside)
                if hit is not None:
                    p.cutoffs.append(_cutoff(c, hit, side, level, b.first))
    else:
        p.source, p.level = "peak", p.top.db
        level = p.level - DROP_DB
        if c.db[p.top.index] <= level:              # the refined peak stands 3 dB over every point: count from the
            p.level = c.db[p.top.index]             # highest point, or the level would lie above the whole curve
            level = p.level - DROP_DB
        for step, side in ((-1, "low"), (+1, "high")):
            hit = _walk(c, p.top.index, step, level, set())
            if hit is not None:
                p.cutoffs.append(_cutoff(c, hit, side, level))
    p.cutoffs.sort(key=lambda k: k.f)
    return p


def _cutoff(c: Curve, hit: tuple[int, int], side: str, level: float, band: int = -1) -> Cutoff:
    inner, outer = hit
    return Cutoff(_cross(c, inner, outer, level), side, inner, outer, band, c.flagged[inner] or c.flagged[outer])


def marker_pair(p: Passband) -> list[Cutoff]:
    """The cut-offs the -3 dB marker shows, and the pair of centre, bandwidth and Q: all of
    them when there are one or two, otherwise the two around the highest gain."""
    if len(p.cutoffs) <= 2:
        return list(p.cutoffs)
    below = [k for k in p.cutoffs if k.f <= p.top.f]
    above = [k for k in p.cutoffs if k.f > p.top.f]
    if below and above:
        return [below[-1], above[0]]
    return above[:2] if above else below[-2:]


# ---- resonances
def _extremes(c: Curve, x, a: int, b: int, highest: bool, floor: float = PROMINENCE_DB,
              quiet: float | None = None):
    """The peaks (highest) or notches of the run a..b that stand clear: (index, how far it
    stands clear, the foot on its left, the foot on its right; a foot is a gain in dB).
    quiet: the level of a noise floor; within NOISE_NEAR of it the noise grows quickly as the
    gain falls, and the scatter close around the point counts as well."""
    s = 1.0 if highest else -1.0
    y = [s * v for v in c.db]
    out = []
    for i in range(a + 1, b):
        if not (y[i] > y[i - 1] and y[i] >= y[i + 1]):
            continue
        feet = []
        for step, end in ((-1, a), (+1, b)):
            low, k = y[i], i
            while k != end and y[k + step] <= y[i]:
                k += step
                low = min(low, y[k])
            feet.append(low)
        clear = y[i] - max(feet)
        scatter = _scatter(c, x, a, b, i)
        if quiet is not None and c.db[i] < quiet + NOISE_NEAR:
            scatter = max(scatter, _near_scatter(c, x, a, b, i))
        if clear >= max(floor, NOISE_FACTOR * scatter):
            out.append((i, clear, s * feet[0], s * feet[1]))
    return out


def _width(c: Curve, i: int, a: int, b: int, level: float, rising: bool) -> tuple[float, float, int, int] | None:
    """Both sides of point i where the gain passes level (rising: a notch, the gain comes up
    to it): (low frequency, high frequency, the inner point on either side). None when one
    side does not reach it inside the run a..b."""
    found = []
    for step, end in ((-1, a), (+1, b)):
        k = i
        while k != end and ((c.db[k + step] < level) if rising else (c.db[k + step] > level)):
            k += step
        if k == end:
            return None
        found.append((_cross(c, k, k + step, level), k))
    return found[0][0], found[1][0], found[0][1], found[1][1]


def _q_from_phase(c: Curve, f0: float, pairs) -> float | None:
    """Q of a single resonance from its phase: across the resonance the phase turns by
    atan(Q (f/f0 - f0/f)). Each pair of points, one below and one above f0, gives one Q;
    the answer is their median."""
    qs = []
    for lo, hi in pairs:
        ua, ub = c.f[lo] / f0 - f0 / c.f[lo], c.f[hi] / f0 - f0 / c.f[hi]
        turn = math.radians(abs(c.deg[hi] - c.deg[lo]))
        if not (ua < 0 < ub) or not (0.0 < turn < math.pi):
            continue
        q_lo, q_hi = 1e-3, 1e6                          # atan(q ub) - atan(q ua) grows with q: bisection
        for _ in range(80):
            q = math.sqrt(q_lo * q_hi)
            if math.atan(q * ub) - math.atan(q * ua) < turn:
                q_lo = q
            else:
                q_hi = q
        qs.append(math.sqrt(q_lo * q_hi))
    return statistics.median(qs) if qs else None


def _resonances(c: Curve, x, phase: bool, bands: list[Band], quiet: float | None = None) -> list[Resonance]:
    out = []
    flat = {i for band in bands for i in range(band.first, band.last + 1)}
    for a, b in segments(c):
        for highest in (True, False):
            for i, clear, left, right in _extremes(c, x, a, b, highest, quiet=quiet):
                if i in flat:                           # the top of a flat stretch is no resonance
                    continue
                f0, db = refine(c, i, highest)
                if abs(db - c.db[i]) >= DROP_DB:        # three points far apart: the parabola says nothing
                    f0, db = c.f[i], c.db[i]
                r = Resonance("peak" if highest else "notch", i, f0, db, clear)
                level = db - DROP_DB if highest else min(left, right) - DROP_DB
                w = _width(c, i, a, b, level, rising=not highest) if (highest or c.db[i] < level) else None
                if w is not None:
                    f_lo, f_hi, k_lo, k_hi = w
                    r.q_width = f0 / (f_hi - f_lo)
                    inside = list(range(k_lo, k_hi + 1))
                else:                                   # no -3 dB width: the points that stand in its upper half
                    half = db - clear / 2 if highest else db + clear / 2
                    k_lo = k_hi = i
                    while k_lo > a and ((c.db[k_lo - 1] > half) if highest else (c.db[k_lo - 1] < half)):
                        k_lo -= 1
                    while k_hi < b and ((c.db[k_hi + 1] > half) if highest else (c.db[k_hi + 1] < half)):
                        k_hi += 1
                    inside = list(range(k_lo, k_hi + 1))
                r.points = len(inside)
                if highest and phase:
                    below = [k for k in range(max(a, i - 2), i + 1) if c.f[k] < f0] if len(inside) < FEW_POINTS \
                        else [k for k in inside if c.f[k] < f0]
                    above = [k for k in range(i, min(b, i + 2) + 1) if c.f[k] > f0] if len(inside) < FEW_POINTS \
                        else [k for k in inside if c.f[k] > f0]
                    pairs = list(zip(reversed(below), above))       # nearest pair first, then outwards
                    r.q_phase = _q_from_phase(c, f0, pairs)
                near = range(max(a, min(inside[0], i - 1)), min(b, max(inside[-1], i + 1)) + 1)
                r.flagged = any(c.flagged[k] for k in near)
                out.append(r)
    out.sort(key=lambda r: r.f0)
    return out


# ---- slope, order, attenuation
def _roll_off(c: Curve, x, cut: Cutoff, level: float, bands: list[Band], resonances: list[Resonance]) -> None:
    step = 1 if cut.side == "high" else -1
    a, b = next(s for s in segments(c) if s[0] <= cut.inner <= s[1])
    end = b if step > 0 else a
    stops = [band.first if step > 0 else band.last for band in bands if band.kind == "floor"]
    stops += [r.index for r in resonances if r.kind == "notch"]
    beyond = [k for k in stops if (k - cut.outer) * step >= 0]
    stop = min(beyond, key=lambda k: abs(k - cut.outer)) if beyond else end
    at_end = not beyond
    lo, hi = sorted((cut.inner, stop))
    if hi - lo < 2:
        return
    span = x[hi] - x[lo]
    idx = list(range(lo, hi + 1))
    flagged = any(c.flagged[k] for k in idx)
    sign = -1.0 if step > 0 else 1.0                     # the gain falls away from the passband
    slopes = []                                         # of every window of SLOPE_WINDOW, in ascending frequency
    sums = _Sums(x, c.db)
    windows = []
    if span < SLOPE_WINDOW - EPS:
        slopes.append(sums.slope(lo, hi))
    else:
        for s in idx:
            e = bisect.bisect_right(x, x[s] + SLOPE_WINDOW + EPS, lo, hi + 1) - 1
            if x[e] - x[s] < SLOPE_WINDOW - 2 * (x[e] - x[e - 1] if e > s else 0.0) - EPS:
                break                                   # what is left of the roll-off is shorter than a window
            if e - s >= 2:
                windows.append((s, e))
    at_notch = bool(beyond) and stop in [r.index for r in resonances if r.kind == "notch"]
    if beyond and not at_notch:                         # into a floor: the windows clear of the bend into it
        clear = [(s, e) for s, e in windows
                 if (x[e] <= x[hi] - FLAT_WINDOW + EPS if step > 0 else x[s] >= x[lo] + FLAT_WINDOW - EPS)]
        windows = clear or windows
    slopes += [sums.slope(s, e) for s, e in windows]
    slopes = [v for v in slopes if v is not None]
    if not slopes:
        return
    if not at_notch:                                    # into a notch the curve has no slope that means an order
        settled = statistics.median(slopes)             # the slope the roll-off settles to
        last = slopes[-1] if step > 0 else slopes[0]    # the window farthest from the passband
        at_floor = bool(beyond) and not at_notch            # every window holds the knee or the bend into it
        limit = (span < SLOPE_WINDOW - EPS or (at_end and sign * last - sign * settled > STEEPENING)
                 or (at_floor and span < SETTLE_DECADES - EPS))
        cut.slope = Value(settled, limit, flagged)
        cut.order = Value(float(max(1, round(abs(settled) / 20.0))), limit, flagged)
    floor = next((band for band in bands if band.kind == "floor" and (band.first if step > 0 else band.last) == stop),
                 None) if beyond else None
    if floor is not None:
        cut.attenuation = Value(level - floor.level, False, flagged or floor.flagged)
    else:
        cut.attenuation = Value(level - min(c.db[k] for k in idx), True, flagged)
        cut.falling = at_end


# ---- the whole answer
def analyse(c: Curve, phase: bool = True) -> Metrics:
    """Everything of section 3 for one curve. phase False: a magnitude-only measurement."""
    m = Metrics()
    idx = c.usable()
    m.points = len(idx)
    if m.points < MIN_POINTS:
        m.reason = TOO_FEW
        return m
    m.ok = True
    m.flagged_share = sum(1 for i in idx if c.flagged[i]) / m.points
    m.noise = noise_ends(c)
    c = without_noise(c, m.noise)
    x = _logs(c)
    p = passband(c)
    m.level, m.source, m.bands, m.cutoffs = p.level, p.source, p.bands, p.cutoffs
    m.resonances = _resonances(c, x, phase, m.bands, max((n.level for n in m.noise), default=None))
    passes = [b for b in m.bands if b.kind == "pass"]
    if passes:
        m.level_flagged = any(b.flagged for b in passes)
        region = set()
        for b in passes:                                # each passband out to its own cut-offs
            lo, hi = b.first, b.last
            for cut in m.cutoffs:
                if cut.band == b.first:
                    lo, hi = min(lo, cut.inner), max(hi, cut.inner)
            region.update(range(lo, hi + 1))
        dips = [c.db[i] for a, b in segments(c) for i, _clear, _l, _r in _extremes(c, x, a, b, False, TROUGH_DB)
                if i in region]
        m.ripple = max(c.db[i] for i in region) - min(dips + [m.level])
    else:
        m.level_flagged = c.flagged[p.top.index]
    for cut in m.cutoffs:
        _roll_off(c, x, cut, m.level, m.bands, m.resonances)
        noise = next((n for n in m.noise if n.at_low == (cut.side == "low")), None)
        if cut.falling and noise is not None:           # it falls into the noise: at least down to the noise
            cut.falling = False
            cut.attenuation = Value(m.level - noise.level, True, cut.attenuation.flagged)
    pair = marker_pair(p)
    if len(pair) == 2 and pair[1].f > pair[0].f:
        lo, hi = pair
        m.pair = (lo, hi)
        m.centre, m.bandwidth = math.sqrt(lo.f * hi.f), hi.f - lo.f
        m.q = m.centre / m.bandwidth
    return m
