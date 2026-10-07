# Auto Markers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Markers on the Bode plot: automatic ones (−3 dB, peak, notch, gain and phase margin) and the user's own with a reference marker, read from one chosen trace, written next to the curve, copied as text and drawn in the exported image.

**Architecture:** The maths is pure and has no Qt: `measure/response.py` works on one curve (interpolation, crossings, extremes) and `markers.py` holds the marker rules and state. `traces.py` hands the chosen trace over as a curve. `gui/marker_layer.py` draws; `gui/bode_plot.py` owns the Markers menu and decides texts and positions; the image export draws the same list.

**Tech Stack:** Python 3.14, PySide6 6.11, pyqtgraph 0.14, numpy, matplotlib (image export), pytest + pytest-qt (offscreen).

**Spec:** `docs/superpowers/specs/2026-10-07-auto-markers-design.md` (read it with this plan).

## Global Constraints

- Work on a branch `a4-auto-markers` cut from `main`; one commit per task. Commit messages are a plain sentence, as in `git log`, and end with the two attribution lines of the session.
- Run tests with `.venv\Scripts\python -m pytest` from the project root (PowerShell). No test may reach an instrument (`tests/conftest.py` sets `BODEPLOT_NO_HARDWARE`); nothing in this plan touches a driver. No bench run.
- Qt (PySide6, pyqtgraph) only in `gui/`: `measure/response.py`, `markers.py` and `traces.py` stay Qt-free (`tests/test_docs.py` enforces it).
- Every new or changed import inside `src/bodeplot/` goes into the Modules table of `docs/ARCHITECTURE.md` in the same task; `tests/test_docs.py` fails until it does.
- Every colour comes from `gui/theme.py`; the white-background image export is the one exception.
- Every new option has a tooltip of at least 25 characters that is not its label (`tests/test_gui_tooltips.py`).
- Never connect `triggered`, `toggled` or `clicked` directly to a method with an optional argument: go through a lambda that passes exactly what the slot needs.
- Numbers of the spec, verbatim: drop 3 dB below the highest gain; peak / notch at least 1 dB clear of both ends and not an end point; at most 8 user markers; a point within 0.1 % of a frequency is that frequency; no slope when two markers stand within 0.1 %; PM = 180° + phase at the 0 dB crossing; GM = −gain where the unwrapped phase crosses −180° − k·360°; the smallest margin when there are several.
- The code of Tasks 1 and 3 and their tests were run as a prototype before this plan was written (26 tests passed against the project's `measure/theory.py`). Copy them as they stand.

**Three departures from the spec, on purpose:**
1. The label texts are built by `markers.label()` (pure) and `BodePlot._place()`, not by the layer: the clipboard text and the image export need the same texts without a display.
2. `TraceSet.curve()` is new: `drawn()` drops dead points, so a curve built from it would bridge gaps, which the spec forbids.
3. The spec's GUI test "the SVG holds the label texts" becomes "the SVG holds the marker colour": matplotlib writes SVG text as outlines.

## Review Focus

Inputs the spec implies and a person will meet; each has its test in the task named.

1. **A linear frequency axis** (sweep type Linear): markers stand at the frequency, not at its logarithm; "Add marker" lands inside the view. Task 4, `test_markers_on_a_linear_frequency_axis`.
2. **A new sweep while markers are on:** the live trace is emptied and refilled point by point; nothing raises, user markers keep their frequency and come back. Task 4, `test_markers_follow_a_running_sweep`.
3. **A loaded CSV with a repeated frequency or a single row:** no division by zero anywhere in the maths. Task 3, `test_a_file_with_repeated_frequencies_breaks_nothing`.
4. **A magnitude-only measurement** (no phase plot): labels carry no phase, margins are not shown, nothing is put on the hidden plot. Task 4, `test_markers_without_phase`.
5. **Vertical unit Voltage on a file that has no voltage columns:** the trace is not drawn, so it has no markers and no error. Task 4, `test_no_markers_on_a_trace_that_is_not_drawn`.

---

## File Structure

| File | Task | Responsibility |
|---|---|---|
| `src/bodeplot/measure/response.py` (new) | 1 | one response curve: value at a frequency, crossings, extremes |
| `tests/test_response.py` (new) | 1 | its tests against theory |
| `src/bodeplot/traces.py` | 2 | `_Reference` uses `response.Curve`; `TraceSet.curve()` |
| `tests/test_traces.py` | 2 | tests of `TraceSet.curve()` |
| `src/bodeplot/markers.py` (new) | 3 | `MarkerSet`, `Marker`, `Placed`, the rules, `label()`, `table()` |
| `tests/test_markers.py` (new) | 3 | its tests against theory |
| `src/bodeplot/gui/marker_layer.py` (new) | 4 | graphics of the markers, label placement, drag |
| `src/bodeplot/gui/theme.py` | 4 | `MARK_INK` |
| `src/bodeplot/gui/bode_plot.py` | 4, 5 | Markers button and menu, texts and positions, user-marker actions, right-click menu, clipboard, `export_markers()` |
| `tests/test_gui_markers.py` (new) | 4, 5, 6 | GUI tests, offscreen |
| `tests/test_gui_tooltips.py` | 5 | the new options and menu items |
| `src/bodeplot/io/export_image.py` | 6 | `ImageMarker`, drawn in `write_image` |
| `src/bodeplot/io/settings.py` | 6 | `AppSettings.markers` |
| `src/bodeplot/gui/main_window.py` | 6 | passes markers to the export; loads and stores the ticks |
| `tests/test_io.py`, `tests/test_gui_traces.py` | 6 | image with markers; the export spy takes the new argument |
| `docs/…` | 7 | spec text, state, README |

---

### Task 0: Branch

- [ ] **Step 1: Cut the branch**

```powershell
git switch -c a4-auto-markers
```

---

### Task 1: `measure/response.py`, the curve maths

**Files:**
- Create: `src/bodeplot/measure/response.py`
- Create: `tests/test_response.py`
- Modify: `docs/ARCHITECTURE.md` (Modules table)

**Interfaces:**
- Consumes: nothing from this package.
- Produces:
  - `usable(h: complex) -> bool`
  - `Curve` (dataclass: `f`, `db`, `deg`, `ok`, `flagged`, all lists of equal length) with `usable() -> list[int]`, `span() -> tuple[float, float] | None`, `locate(freq) -> tuple[int, int, float] | None`, `interp(freq, values) -> float | None`, `at(freq) -> tuple[float, float] | None`, `flagged_at(freq) -> bool`
  - `curve(freqs, hs, flagged=None) -> Curve`
  - `crossings(c: Curve, level: float, of: str = "db") -> list[float]`
  - `Extremum` (dataclass: `f`, `db`, `index`, `interior`) and `extremum(c: Curve, highest: bool = True) -> Extremum | None`
  - `EDGE_TOL = 1e-3`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_response.py`:

```python
"""The maths on one response curve (measure/response.py), against the theory of the simulated DUTs."""
import cmath
import math

import pytest

from bodeplot.measure.response import Curve, crossings, curve, extremum
from bodeplot.measure.theory import TransferFunction

RC = TransferFunction.rc_lpf(1e3, 100e-9)
BPF = TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9)


def grid(lo=50.0, hi=2e7, ppd=20):
    n = int(round(math.log10(hi / lo) * ppd)) + 1
    return [lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]


def of(tf, freqs=None):
    freqs = freqs or grid()
    return curve(freqs, [tf.h(f) for f in freqs])


def by_hand(f, db, deg=None, ok=None):
    n = len(f)
    return Curve(list(f), list(db), list(deg or [0.0] * n), list(ok or [True] * n), [False] * n)


def test_curve_sorts_unwraps_and_keeps_dead_points():
    c = curve([1000.0, 100.0, 0.0, 10000.0, 1e5], [cmath.rect(1, math.radians(-170)), 1 + 0j, 1 + 0j,
                                                    cmath.rect(0.1, math.radians(170)), 0j],
              flagged=[False, True, False, False, False])
    assert c.f == [100.0, 1000.0, 10000.0, 1e5]                 # the impossible frequency is gone
    assert c.ok == [True, True, True, False]
    assert c.flagged == [True, False, False, False]
    assert c.deg[:3] == pytest.approx([0.0, -170.0, -190.0])    # +170 is -190 on the unwrapped curve
    assert c.db[:3] == pytest.approx([0.0, 0.0, -20.0])
    assert c.usable() == [0, 1, 2] and c.span() == (100.0, 1e5)


def test_at_interpolates_over_log_frequency():
    c = by_hand([100.0, 10000.0], [0.0, -40.0], [0.0, -90.0])
    assert c.at(1000.0) == pytest.approx((-20.0, -45.0))
    assert c.at(100.0) == pytest.approx((0.0, 0.0)) and c.at(10000.0) == pytest.approx((-40.0, -90.0))
    assert c.at(100.05) == pytest.approx((0.0, 0.0))            # within 0.1 % of a point: that point
    assert c.at(99.0) is None and c.at(10100.0) is None and c.at(0.0) is None
    assert c.interp(1000.0, [1.0, 3.0]) == pytest.approx(2.0)
    assert c.interp(1000.0, [1.0, float("nan")]) is None
    assert Curve().at(100.0) is None and Curve().span() is None


def test_a_gap_is_not_bridged():
    c = by_hand([100.0, 1000.0, 10000.0, 1e5], [0.0, 0.0, -20.0, -40.0], ok=[True, False, True, True])
    assert c.at(300.0) is None and c.at(1000.0) is None and c.at(3000.0) is None
    assert c.at(30000.0) is not None and c.at(100.0) is not None
    c.flagged[3] = True
    assert c.flagged_at(30000.0) and not c.flagged_at(100.0) and not c.flagged_at(300.0)


def test_crossings_of_a_level():
    c = by_hand([1.0, 10.0, 100.0, 1000.0, 10000.0], [0.0, -2.0, -4.0, -2.0, 0.0])
    assert crossings(c, -3.0) == pytest.approx([10.0 ** 1.5, 10.0 ** 2.5])
    assert crossings(c, -4.0) == []                             # touched, not passed
    assert crossings(c, -2.0) == pytest.approx([10.0, 1000.0])  # passed exactly on a point
    assert crossings(c, 5.0) == []
    flat = by_hand([1.0, 10.0, 100.0], [0.0, 0.0, 0.0])
    assert crossings(flat, 0.0) == []
    gap = by_hand([1.0, 10.0, 100.0, 1000.0], [0.0, 0.0, -6.0, -6.0], ok=[True, True, False, True])
    assert crossings(gap, -3.0) == []                           # the crossing lies in the gap
    ph = by_hand([1.0, 10.0, 100.0], [0.0] * 3, [-90.0, -170.0, -190.0])
    assert crossings(ph, -180.0, "deg") == pytest.approx([10.0 ** 1.5])


def test_rc_low_pass_crossing_against_theory():
    c = of(RC)
    fc = 1 / (2 * math.pi * 1e3 * 100e-9)
    (f,) = crossings(c, c.db[0] - 3.0)
    assert f == pytest.approx(fc, rel=0.02)
    assert c.at(f)[1] == pytest.approx(-45.0, abs=1.0)


def test_extremum_is_refined_between_the_points():
    c = of(BPF)
    f0 = 1 / (2 * math.pi * math.sqrt(1e-3 * 100e-9))
    e = extremum(c)
    assert e.interior and e.f == pytest.approx(f0, rel=0.01) and e.db == pytest.approx(0.0, abs=0.1)
    assert e.f != c.f[e.index]                                  # between two points of the grid
    low = extremum(of(TransferFunction.rlc_notch(100.0, 1e-3, 100e-9)), highest=False)
    assert low.interior and low.f == pytest.approx(f0, rel=0.03)


def test_extremum_at_an_end_and_on_poor_curves():
    e = extremum(of(RC))
    assert not e.interior and e.index == 0 and e.f == 50.0
    assert extremum(Curve()) is None
    assert extremum(by_hand([1.0, 10.0], [0.0, 0.0], ok=[False, False])) is None
    one = extremum(by_hand([10.0], [-3.0]))
    assert (one.f, one.db, one.interior) == (10.0, -3.0, False)
    flat = extremum(by_hand([1.0, 10.0, 100.0], [0.0, 0.0, 0.0]))
    assert flat.db == 0.0 and not flat.interior                 # the first of equal points
    beside_gap = extremum(by_hand([1.0, 10.0, 100.0, 1000.0], [0.0, 5.0, 0.0, 0.0], ok=[True, True, False, True]))
    assert beside_gap.f == 10.0 and beside_gap.db == 5.0        # no parabola across a gap
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_response.py -q`
Expected: an error at collection, `ModuleNotFoundError: No module named 'bodeplot.measure.response'`.

- [ ] **Step 3: Write the module**

Create `src/bodeplot/measure/response.py`:

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests\test_response.py -q`
Expected: 7 passed.

- [ ] **Step 5: Architecture map**

In `docs/ARCHITECTURE.md`, Modules table, add after the row of `measure/meters.py`:

```markdown
| `measure/response.py` | one response curve (gain in dB, unwrapped phase): value at a frequency, level crossings, refined extremes; no Qt | - |
```

Run: `.venv\Scripts\python -m pytest tests\test_docs.py -q`
Expected: all passed.

- [ ] **Step 6: Commit**

```powershell
git add src/bodeplot/measure/response.py tests/test_response.py docs/ARCHITECTURE.md
git commit -m "Response curve maths: value at a frequency, crossings, refined extremes"
```

---

### Task 2: `traces.py` hands a trace over as a curve

**Files:**
- Modify: `src/bodeplot/traces.py` (imports, `EDGE_TOL`, `_usable`, `_Reference`, new `TraceSet.curve`)
- Modify: `tests/test_traces.py` (append)
- Modify: `docs/ARCHITECTURE.md` (row of `traces.py`)

**Interfaces:**
- Consumes: `response.curve`, `response.Curve.at`, `response.usable` (Task 1).
- Produces: `TraceSet.curve(trace_id: int, span_hint: tuple[float, float] | None = None, relative: bool = True) -> tuple[Curve, list[PointResult] | None] | None`. The second item is the measured point behind each curve point, in the curve's order and of the same length; `None` for a theory trace. The whole result is `None` when no trace has that id. `_Reference.at(f)` keeps its signature and its results.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_traces.py` (it already has helpers for points; these tests bring their own so that they do not depend on names in that file):

```python
# ---------------------------------------------------------------------- a trace as a curve (markers)
def _pt(f, h):
    import cmath as _c
    import math as _m
    from bodeplot.models import Flag, PointResult
    dead = not (_m.isfinite(abs(h)) and abs(h) > 0)
    return PointResult(freq_hz=f, h=h, gain_db=float("nan") if dead else 20 * _m.log10(abs(h)),
                       phase_deg=float("nan") if dead else _m.degrees(_c.phase(h)), vref_amp=0.5,
                       vdut_amp=0.5 * abs(h), vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1,
                       snr_ref_db=50.0, snr_dut_db=50.0, flags=Flag.NONE, duration_s=0.1)


def test_curve_of_a_measured_trace_keeps_dead_points():
    import pytest
    from bodeplot.traces import TraceSet
    ts = TraceSet()
    ts.live.points = [_pt(100.0, 1 + 0j), _pt(1000.0, 0j), _pt(10000.0, 0.1 + 0j)]
    c, points = ts.curve(ts.live.id)
    assert c.f == [100.0, 1000.0, 10000.0] and c.ok == [True, False, True]
    assert points == ts.live.points and len(c.flagged) == 3
    assert c.at(300.0) is None                                   # the gap is not bridged
    assert c.db[2] == pytest.approx(-20.0)
    assert ts.curve(99) is None


def test_curve_of_a_theory_trace_and_relative_to_a_reference():
    import math
    import pytest
    from bodeplot.measure.theory import TransferFunction
    from bodeplot.traces import TraceSet
    rc = TransferFunction.rc_lpf(1e3, 100e-9)
    ts = TraceSet()
    ts.live.points = [_pt(f, 0.5 * rc.h(f)) for f in (100.0, 1000.0, 10000.0)]
    th = ts.add_theory(rc)
    c, points = ts.curve(th.id)
    assert points is None and c.f[0] == pytest.approx(100.0) and c.f[-1] == pytest.approx(10000.0)
    assert c.db[0] == pytest.approx(20 * math.log10(abs(rc.h(100.0))))
    assert ts.curve(th.id, (50.0, 2e7))[0].f[0] == pytest.approx(50.0)      # the span hint widens it
    ts.set_reference(th.id)
    c, points = ts.curve(ts.live.id)
    assert c.db == pytest.approx([-6.0206] * 3, abs=1e-3) and c.deg == pytest.approx([0.0] * 3, abs=1e-6)
    assert len(points) == 3
    own, _ = ts.curve(th.id)
    assert set(own.db) == {0.0} and all(own.ok)                  # the reference against itself
    absolute, _ = ts.curve(ts.live.id, relative=False)
    assert absolute.db[0] == pytest.approx(20 * math.log10(abs(0.5 * rc.h(100.0))))


def test_relative_curve_has_no_value_outside_the_reference():
    from bodeplot.models import SweepResult
    from bodeplot.traces import TraceSet
    ts = TraceSet()
    ts.live.points = [_pt(f, 1 + 0j) for f in (10.0, 100.0, 1000.0, 10000.0)]
    ref = ts.add_file(SweepResult({}, [_pt(100.0, 1 + 0j), _pt(1000.0, 1 + 0j)], {}), "ref.csv")
    ts.set_reference(ref.id)
    c, points = ts.curve(ts.live.id)
    assert c.ok == [False, True, True, False] and len(points) == 4
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_traces.py -q -k curve`
Expected: 3 failed with `AttributeError: 'TraceSet' object has no attribute 'curve'`.

- [ ] **Step 3: Change `traces.py`**

Imports at the top: remove `import bisect`; keep `cmath` and `math`; add the response module:

```python
from .measure import response
from .measure.theory import TransferFunction
from .models import PointResult, SweepResult
```

Delete the line `EDGE_TOL = 1e-3 …` (the tolerance now lives in `measure/response.py`). Replace the function `_usable` by the shared one, keeping the name the file uses:

```python
_usable = response.usable
```

Replace the whole class `_Reference` by:

```python
class _Reference:
    """A trace as the thing the others are divided by. A theory curve is evaluated at
    the frequency asked for. A measured trace is a response curve (measure/response.py):
    interpolated in log frequency, nothing outside its own range, and a gap is not bridged."""

    def __init__(self, trace: Trace):
        self.theory = trace.theory
        self.curve = response.curve([p.freq_hz for p in trace.points], [p.h for p in trace.points])

    def at(self, f: float) -> complex | None:
        if self.theory is not None:
            h = self.theory.h(f)
            return h if _usable(h) else None
        v = self.curve.at(f)
        return None if v is None else cmath.rect(10 ** (v[0] / 20.0), math.radians(v[1]))
```

Add to `TraceSet`, after `drawn`:

```python
    def curve(self, trace_id: int, span_hint: tuple[float, float] | None = None, relative: bool = True):
        """One trace as a response curve, for the markers: (curve, the measured point behind
        each curve point or None for a theory curve). As it is, or divided by the reference
        like drawn(). Unlike drawn() it keeps dead points, so that a gap stays a gap. None:
        there is no such trace."""
        t = self.get(trace_id)
        if t is None:
            return None
        if t.theory is not None:
            span = self.span(span_hint)
            freqs = theory_grid(*span) if span else []
            hs, points = [t.theory.h(f) for f in freqs], None
        else:
            points = sorted((p for p in t.points if p.freq_hz > 0 and math.isfinite(p.freq_hz)),
                            key=lambda p: p.freq_hz)
            freqs, hs = [p.freq_hz for p in points], [p.h for p in points]
        ref_trace = self.reference() if relative else None
        if ref_trace is t:
            hs = [1 + 0j if _usable(h) else h for h in hs]
        elif ref_trace is not None:
            ref = _Reference(ref_trace)
            dead = complex("nan")
            rs = [ref.at(f) for f in freqs]
            hs = [h / r if r is not None and _usable(r) and _usable(h) else dead for h, r in zip(hs, rs)]
        return response.curve(freqs, hs), points
```

- [ ] **Step 4: Run the trace tests, old and new**

Run: `.venv\Scripts\python -m pytest tests\test_traces.py tests\test_gui_traces.py -q`
Expected: all passed (the old tests prove `_Reference` behaves as before).

- [ ] **Step 5: Architecture map**

In `docs/ARCHITECTURE.md` change the Imports cell of `traces.py` to:

```markdown
| `traces.py` | the traces of the Bode plot (live, kept, file, theory), the relative-to maths, a trace as a response curve | `measure/response.py`, `measure/theory.py`, `models.py` |
```

Run: `.venv\Scripts\python -m pytest tests\test_docs.py -q`
Expected: all passed.

- [ ] **Step 6: Commit**

```powershell
git add src/bodeplot/traces.py tests/test_traces.py docs/ARCHITECTURE.md
git commit -m "A trace as a response curve; the reference trace interpolates through the shared maths"
```

---

### Task 3: `markers.py`, the rules and the texts

**Files:**
- Create: `src/bodeplot/markers.py`
- Create: `tests/test_markers.py`
- Modify: `docs/ARCHITECTURE.md` (Modules table)

**Interfaces:**
- Consumes: `Curve`, `crossings`, `extremum` (Task 1); `units.fmt_si`.
- Produces:
  - `KINDS = ("cutoff", "peak", "notch", "margins")`, `MAX_USER = 8`, `OUTSIDE`, `NO_VALUE`
  - `Marker` (dataclass: `name`, `kind` in `"cutoff" | "peak" | "notch" | "gm" | "pm" | "user"`, `freq`, `db`, `deg`, `flagged`, `note`, `extra`, `margin`, `number`, `is_ref`, `delta`; properties `found`, `has_value`)
  - `Delta` (dataclass: `ref`, `ratio`, `db`, `deg`, `slope`)
  - `Placed` (dataclass: `marker: Marker`, `text: str`, `y_gain: float | None`, `y_phase: float | None`)
  - `MarkerSet` with attributes `kinds: set[str]`, `user: dict[int, float]`, `ref: int | None`, `trace_id: int`, and methods `set_kind(kind, on)`, `add(freq) -> int | None`, `move(number, freq) -> bool`, `remove(number)`, `clear_user()`, `toggle_ref(number)`, `evaluate(c: Curve, margins: bool = True) -> list[Marker]`
  - `label(m: Marker, value: str = "", phase: float | None = None) -> str`, `delta_text(d) -> str`, `freq_text(f) -> str`, `table(markers, title, phase=lambda m: m.deg) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_markers.py`:

```python
"""The markers (markers.py): the rules of the automatic ones and the user's own, against theory."""
import cmath
import math
import random

import numpy as np
import pytest

from bodeplot.markers import KINDS, MAX_USER, NO_VALUE, OUTSIDE, Marker, MarkerSet, delta_text, label, table
from bodeplot.measure.response import Curve, curve
from bodeplot.measure.theory import TransferFunction

RC = TransferFunction.rc_lpf(1e3, 100e-9)
BPF = TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9)


def grid(lo=50.0, hi=2e7, ppd=20):
    n = int(round(math.log10(hi / lo) * ppd)) + 1
    return [lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]


def of(tf, freqs=None):
    freqs = freqs or grid()
    return curve(freqs, [tf.h(f) for f in freqs])


def by_hand(f, db, deg=None, ok=None):
    n = len(f)
    return Curve(list(f), list(db), list(deg or [0.0] * n), list(ok or [True] * n), [False] * n)
NOTCH = TransferFunction.rlc_notch(100.0, 1e-3, 100e-9)
F0 = 1 / (2 * math.pi * math.sqrt(1e-3 * 100e-9))          # 15.92 kHz, Q = 1
FC = 1 / (2 * math.pi * 1e3 * 100e-9)                       # 1.592 kHz
W = [2 * math.pi * f for f in (100.0, 10e3, 100e3)]
LOOP = TransferFunction.custom([100.0], np.polymul(np.polymul([1 / W[0], 1.0], [1 / W[1], 1.0]), [1 / W[2], 1.0]))


def every(c, margins=True):
    ms = MarkerSet()
    for k in KINDS:
        ms.set_kind(k, True)
    return {m.name: m for m in ms.evaluate(c, margins)}


def solve(fn, lo, hi):
    """The frequency between lo and hi where fn changes sign (bisection on the theory)."""
    a = fn(lo)
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if (fn(mid) > 0) == (a > 0):
            lo = mid
        else:
            hi = mid
    return lo


def noisy(tf, seed=1, db=0.05, deg=0.3, freqs=None):
    rnd = random.Random(seed)
    freqs = freqs or grid()
    return curve(freqs, [tf.h(f) * cmath.rect(10 ** (rnd.gauss(0, db) / 20), math.radians(rnd.gauss(0, deg)))
                         for f in freqs])


def test_rc_low_pass_has_a_cutoff_and_nothing_else():
    m = every(of(RC))
    assert set(m) == {"fc", "pk", "nt", "GM", "PM"}
    assert m["fc"].freq == pytest.approx(FC, rel=0.02) and m["fc"].deg == pytest.approx(-45.0, abs=1.0)
    assert m["fc"].db == pytest.approx(of(RC).db[0] - 3.0)
    assert not m["pk"].found and not m["nt"].found and not m["GM"].found and not m["PM"].found


def test_rc_high_pass_and_butterworth_cutoff():
    m = every(of(TransferFunction.rc_hpf(1e3, 100e-9)))
    assert m["fc"].freq == pytest.approx(FC, rel=0.02) and m["fc"].deg == pytest.approx(45.0, abs=1.0)
    assert every(of(TransferFunction.butter2_lpf(10e3)))["fc"].freq == pytest.approx(10e3, rel=0.01)


def test_band_pass_peak_edges_bandwidth_and_q():
    m = every(of(BPF))
    assert m["pk"].freq == pytest.approx(F0, rel=0.01) and m["pk"].db == pytest.approx(0.0, abs=0.1)
    assert m["pk"].deg == pytest.approx(0.0, abs=2.0)
    bw = 100.0 / (2 * math.pi * 1e-3)                           # R / (2 pi L)
    lo = -bw / 2 + math.sqrt(bw * bw / 4 + F0 * F0)
    assert m["fL"].freq == pytest.approx(lo, rel=0.03) and m["fH"].freq == pytest.approx(lo + bw, rel=0.03)
    assert m["fH"].freq - m["fL"].freq == pytest.approx(bw, rel=0.03)
    assert m["fH"].extra.startswith("BW 15.") and m["fH"].extra.endswith("Q 1") and not m["fL"].extra
    assert "fc" not in m and not m["nt"].found


def test_notch_is_found_and_is_no_peak():
    m = every(of(NOTCH))
    assert m["nt"].freq == pytest.approx(F0, rel=0.03) and m["nt"].db < -20.0
    assert not m["pk"].found


def test_margins_of_a_three_pole_loop():
    m = every(of(LOOP))
    f_gc = solve(lambda f: abs(LOOP.h(f)) - 1.0, 100.0, 1e6)
    phase = lambda f: math.degrees(sum(-math.atan(2 * math.pi * f / w) for w in W))
    f_pc = solve(lambda f: phase(f) + 180.0, 100.0, 1e7)
    assert m["PM"].freq == pytest.approx(f_gc, rel=0.02) and m["PM"].margin == pytest.approx(180 + phase(f_gc), abs=1.0)
    assert m["GM"].freq == pytest.approx(f_pc, rel=0.02)
    assert m["GM"].margin == pytest.approx(-20 * math.log10(abs(LOOP.h(f_pc))), abs=0.2)
    assert m["GM"].deg == -180.0 and m["PM"].db == 0.0
    assert set(every(of(LOOP), margins=False)) == {"fc", "pk", "nt"}


def test_the_smallest_margin_is_taken():
    c = by_hand([1.0, 10.0, 100.0, 1000.0, 10000.0], [10.0, -10.0, 10.0, -10.0, -30.0],
                [-100.0, -120.0, -140.0, -170.0, -200.0])
    m = every(c)
    assert m["PM"].freq == pytest.approx(10 ** 2.5) and m["PM"].margin == pytest.approx(25.0)
    c = by_hand([1.0, 10.0, 100.0, 1000.0, 10000.0], [0.0, -10.0, -20.0, -5.0, -40.0],
                [-170.0, -190.0, -170.0, -190.0, -200.0])
    m = every(c)
    assert m["GM"].margin == pytest.approx(5.0) and m["GM"].freq == pytest.approx(10 ** 0.5)
    in_phase = by_hand([1.0, 10.0], [10.0, -10.0], [0.0, 0.0])
    assert every(in_phase)["PM"].margin == pytest.approx(180.0)      # not -180


def test_phase_crossing_found_after_unwrapping():
    freqs = grid(100.0, 1e7)
    c = of(LOOP, freqs)
    assert min(c.deg) < -180.0                                  # the wrapped phase never shows -180 as a level passed
    assert every(c)["GM"].found


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_noise_moves_the_markers_little_and_adds_none(seed):
    m = every(noisy(RC, seed))
    assert m["fc"].freq == pytest.approx(FC, rel=0.04) and "fL" not in m
    m = every(noisy(BPF, seed))
    assert m["pk"].freq == pytest.approx(F0, rel=0.06)
    assert m["fH"].freq - m["fL"].freq == pytest.approx(100.0 / (2 * math.pi * 1e-3), rel=0.06)
    m = every(noisy(LOOP, seed))
    assert m["PM"].margin == pytest.approx(every(of(LOOP))["PM"].margin, abs=2.0)
    assert m["GM"].margin == pytest.approx(every(of(LOOP))["GM"].margin, abs=0.4)


def test_poor_curves_give_no_markers_and_no_error():
    for c in (Curve(), by_hand([10.0], [0.0]), by_hand([1.0, 10.0], [0.0, 0.0], ok=[False, False]),
              of(TransferFunction.through())):
        m = every(c)
        assert set(m) == {"fc", "pk", "nt", "GM", "PM"} and not any(x.found for x in m.values())
    gap = by_hand([1.0, 10.0, 100.0, 1000.0], [0.0, 0.0, -6.0, -6.0], ok=[True, True, False, True])
    assert not every(gap)["fc"].found                           # the crossing lies in the gap
    rising = by_hand([1.0, 10.0, 100.0], [-20.0, -10.0, 0.0])   # the maximum is the last point
    m = every(rising)
    assert m["fc"].freq == pytest.approx(10 ** (2 - 0.3)) and not m["pk"].found


def test_a_file_with_repeated_frequencies_breaks_nothing():
    """Review focus: a hand-made CSV may hold the same frequency twice, or a single row."""
    c = curve([100.0, 1000.0, 1000.0, 1000.0, 10000.0, 10000.0], [1.0, 2.0, 0.5, 2.0, 0.1, 0.1])
    ms = MarkerSet()
    for k in KINDS:
        ms.set_kind(k, True)
    ms.add(1000.0), ms.add(3000.0)
    out = ms.evaluate(c)
    assert len(out) == 8 and all(m.db is None or math.isfinite(m.db) for m in out)
    assert all(m.freq is None or math.isfinite(m.freq) for m in out)
    assert table(out, "t") and all(label(m, "x", 0.0) for m in out if m.found)


def test_a_flagged_point_marks_the_marker():
    c = of(RC)
    i = next(k for k, f in enumerate(c.f) if f > FC)
    c.flagged[i] = True
    assert every(c)["fc"].flagged
    c.flagged[i] = False
    assert not every(c)["fc"].flagged


def test_user_markers_numbers_and_limit():
    ms = MarkerSet()
    assert [ms.add(1000.0 * k) for k in range(1, MAX_USER + 1)] == list(range(1, MAX_USER + 1))
    assert ms.add(5.0) is None                                  # the limit
    ms.remove(3)
    assert ms.add(42.0) == 3                                    # the lowest free number
    assert ms.add(0.0) is None and ms.add(float("nan")) is None
    assert ms.move(3, 50.0) and ms.user[3] == 50.0
    assert not ms.move(3, -1.0) and not ms.move(99, 10.0) and ms.user[3] == 50.0
    with pytest.raises(ValueError):
        ms.set_kind("bogus", True)
    ms.clear_user()
    assert ms.user == {} and ms.ref is None


def test_user_marker_reads_the_interpolated_value():
    c = of(RC)
    ms = MarkerSet()
    ms.add(1000.0)
    (m,) = ms.evaluate(c)
    h = RC.h(1000.0)
    assert (m.name, m.kind, m.number, m.freq) == ("M1", "user", 1, 1000.0)
    assert m.db == pytest.approx(20 * math.log10(abs(h)), abs=0.02)
    assert m.deg == pytest.approx(math.degrees(cmath.phase(h)), abs=0.2)
    ms.move(1, c.f[7])                                          # exactly on a point
    assert ms.evaluate(c)[0].db == c.db[7]


def test_user_marker_without_a_value():
    c = by_hand([100.0, 1000.0, 10000.0, 1e5], [0.0, 0.0, -20.0, -40.0], ok=[True, False, True, True])
    ms = MarkerSet()
    ms.add(5e7), ms.add(300.0), ms.add(10.0)
    out = ms.evaluate(c)
    assert [m.note for m in out] == [OUTSIDE, NO_VALUE, OUTSIDE] and not any(m.has_value for m in out)
    assert all(m.found for m in out)
    assert [m.note for m in ms.evaluate(Curve())] == [OUTSIDE] * 3
    assert label(out[0]) == "M1 50 MHz  outside the trace"


def test_reference_marker_and_delta():
    c = by_hand([100.0, 1e5], [0.0, -60.0], [0.0, -90.0])       # -20 dB and -30 degrees per decade
    ms = MarkerSet()
    ms.add(1000.0), ms.add(10000.0), ms.add(1000.0)
    ms.toggle_ref(1)
    m1, m2, m3 = ms.evaluate(c)
    assert m1.is_ref and m1.delta is None
    d = m2.delta
    assert (d.ref, d.ratio) == ("M1", 10.0) and d.db == pytest.approx(-20.0) and d.deg == pytest.approx(-30.0)
    assert d.slope == pytest.approx(-20.0)
    assert m3.delta.slope is None and m3.delta.db == pytest.approx(0.0)     # at the same frequency
    assert delta_text(d) == "Δ M1  ×10  -20.0 dB  -30.0°  -20.0 dB/dec"
    ms.toggle_ref(1)
    assert ms.ref is None
    ms.toggle_ref(2), ms.remove(2)
    assert ms.ref is None and all(m.delta is None for m in ms.evaluate(c))
    ms.toggle_ref(99)
    assert ms.ref is None


def test_labels():
    assert label(Marker("fc", "cutoff", 1620.0, -3.01, -45.2), "-3.01 dB", -45.2) == "fc 1.62 kHz  -3.01 dB  -45.2°"
    assert label(Marker("fc", "cutoff", 1620.0, -3.01, -45.2), "-3.01 dB") == "fc 1.62 kHz  -3.01 dB"
    assert label(Marker("fH", "cutoff", 2054.0, -3.0, -45.0, extra="BW 820 Hz  Q 1.94"), "-3.00 dB", -45.0) == \
        "fH 2.05 kHz  -3.00 dB  -45.0°\nBW 820 Hz  Q 1.94"
    assert label(Marker("GM", "gm", 20000.0, -12.4, -180.0, margin=12.4)) == "GM 12.4 dB at 20 kHz"
    assert label(Marker("PM", "pm", 3100.0, 0.0, -131.7, True, margin=48.3)) == "PM 48.3° at 3.1 kHz  (flagged)"
    assert label(Marker("M1", "user", 500.0, 0.2, -12.4, is_ref=True), "+0.20 dB", -12.4) == \
        "M1 500 Hz  +0.20 dB  -12.4°  (ref)"


def test_table_for_the_clipboard():
    ms = MarkerSet()
    for k in KINDS:
        ms.set_kind(k, True)
    ms.add(1000.0), ms.add(10000.0)
    ms.toggle_ref(1)
    text = table(ms.evaluate(of(RC)), "Markers on: Sweep")
    rows = [r.split("\t") for r in text.splitlines()]
    assert rows[0] == ["Markers on: Sweep"]
    assert rows[1] == ["Marker", "Frequency (Hz)", "Gain (dB)", "Phase (deg)", "Note"]
    assert [r[0] for r in rows[2:]] == ["fc", "pk", "nt", "GM", "PM", "M1", "M2"]
    assert float(rows[2][1]) == pytest.approx(FC, rel=0.02) and float(rows[2][2]) == pytest.approx(-3.0, abs=0.01)
    assert rows[3] == ["pk", "", "", "", "none"]
    assert rows[7][4] == "reference marker" and rows[8][4].startswith("rel. M1: x10, ")
    assert text.endswith("\n") and all(len(r) == 5 for r in rows[1:])
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_markers.py -q`
Expected: an error at collection, `ModuleNotFoundError: No module named 'bodeplot.markers'`.

- [ ] **Step 3: Write the module**

Create `src/bodeplot/markers.py`:

```python
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
    return c.f[i] * (c.f[j] / c.f[i]) ** (a / (a - b))


def _cutoffs(c: Curve, top) -> list[Marker]:
    if top is None:
        return [Marker("fc", "cutoff")]
    level = top.db - DROP_DB
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


def delta_text(d: Delta | None) -> str:
    if d is None:
        return ""
    text = "Δ %s  ×%.3g  %+.1f dB  %+.1f°" % (d.ref, d.ratio, d.db, d.deg)
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
    second = m.extra or delta_text(m.delta)
    return text + ("\n" + second if second else "")


def table(markers: list[Marker], title: str, phase=lambda m: m.deg) -> str:
    """The markers as tab-separated text for the clipboard. Gain in dB, plain numbers."""
    rows = [title, "Marker\tFrequency (Hz)\tGain (dB)\tPhase (deg)\tNote"]
    for m in markers:
        if not m.found:
            rows.append("%s\t\t\t\tnone" % m.name)
            continue
        notes = []
        if m.kind == "gm":
            notes.append("gain margin %.2f dB" % m.margin)
        if m.kind == "pm":
            notes.append("phase margin %.2f deg" % m.margin)
        if m.extra:
            notes.append(m.extra.replace("  ", ", "))
        if m.is_ref:
            notes.append("reference marker")
        if m.delta is not None:
            d = m.delta
            notes.append("rel. %s: x%.3g, %+.1f dB, %+.1f deg" % (d.ref, d.ratio, d.db, d.deg)
                         + (", %+.1f dB/dec" % d.slope if d.slope is not None else ""))
        if m.note:
            notes.append(m.note)
        if m.flagged:
            notes.append("flagged")
        ph = phase(m) if m.has_value else None
        rows.append("%s\t%.2f\t%s\t%s\t%s" % (m.name, m.freq, "%.3f" % m.db if m.has_value else "",
                                             "%.2f" % ph if ph is not None else "", "; ".join(notes)))
    return "\n".join(rows) + "\n"
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests\test_markers.py tests\test_response.py -q`
Expected: 26 passed.

- [ ] **Step 5: Architecture map**

In `docs/ARCHITECTURE.md`, Modules table, add after the row of `logging_setup.py`:

```markdown
| `markers.py` | the markers of the Bode plot: what is switched on, the user's markers, the rules (-3 dB, peak, notch, margins), label and clipboard texts; no Qt | `measure/response.py`, `units.py` |
```

Run: `.venv\Scripts\python -m pytest tests\test_docs.py -q`
Expected: all passed.

- [ ] **Step 6: Commit**

```powershell
git add src/bodeplot/markers.py tests/test_markers.py docs/ARCHITECTURE.md
git commit -m "Marker rules: -3 dB, peak, notch, margins, user markers with a reference; label and clipboard texts"
```

---

### Task 4: Markers on the plot (the layer, the menu, the automatic markers)

**Files:**
- Create: `src/bodeplot/gui/marker_layer.py`
- Modify: `src/bodeplot/gui/theme.py` (one constant)
- Modify: `src/bodeplot/gui/bode_plot.py`
- Create: `tests/test_gui_markers.py`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: `MarkerSet`, `Marker`, `Placed`, `KINDS`, `MAX_USER`, `label`, `table` (Task 3); `TraceSet.curve` (Task 2).
- Produces:
  - `theme.MARK_INK`
  - `MarkerLayer(gain_plot, phase_plot, on_moved)` with `show(placed: list[Placed], log_x: bool)`, `layout()`, `names() -> list[str]`, `items(name) -> _Items` (attributes `lines` [gain, phase], `dots` [gain, phase], `text`, `host` 0 = gain plot / 1 = phase plot), `label_rect(name) -> QRectF | None`, `user_at(plot, scene_pos) -> int | None`. `on_moved(number: int, freq_hz: float)` is called while a user marker is dragged.
  - On `BodePlot`: `markers: MarkerSet`, `marker_layer: MarkerLayer`, `markers_btn`, `marker_menu`, `marker_actions: dict[str, QAction]`, `marker_trace_menu`, `act_add_marker`, `act_clear_markers`, `act_copy_markers`; methods `marker_kinds() -> list[str]`, `set_marker_kinds(kinds)`, `set_marker_kind(kind, on)`, `set_marker_trace(trace_id)`, `placed() -> list[Placed]`, `add_marker(freq_hz=None) -> int | None`, `move_marker(number, freq_hz)`, `remove_marker(number)`, `clear_markers()`. (The three menu items Add / Remove all / Copy exist from this task on; Copy is connected in Task 5.)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gui_markers.py`:

```python
"""Markers on the plot: the Markers menu, the automatic markers, the user's own (offscreen)."""
import cmath
import math
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication

from bodeplot.gui import theme
from bodeplot.gui.bode_plot import BodePlot
from bodeplot.markers import KINDS, MAX_USER
from bodeplot.measure.theory import TransferFunction
from bodeplot.models import Flag, PointResult, SweepResult
from bodeplot.traces import TraceSet

RC = TransferFunction.rc_lpf(1e3, 100e-9)
BPF = TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9)
NOTCH = TransferFunction.rlc_notch(100.0, 1e-3, 100e-9)
W = [2 * math.pi * f for f in (100.0, 10e3, 100e3)]
LOOP = TransferFunction.custom([100.0], np.polymul(np.polymul([1 / W[0], 1.0], [1 / W[1], 1.0]), [1 / W[2], 1.0]))
FC = 1 / (2 * math.pi * 1e3 * 100e-9)                           # 1.592 kHz
F0 = 1 / (2 * math.pi * math.sqrt(1e-3 * 100e-9))               # 15.92 kHz
FREQS = [10.0 ** (2 + i / 20) for i in range(101)]              # 100 Hz to 10 MHz, 20 per decade


def point(f, h, flags=Flag.NONE):
    return PointResult(freq_hz=f, h=h, gain_db=20 * math.log10(abs(h)), phase_deg=math.degrees(cmath.phase(h)),
                       vref_amp=0.5, vdut_amp=0.5 * abs(h), vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1,
                       snr_ref_db=50.0, snr_dut_db=50.0, flags=flags, duration_s=0.1)


def sweep(tf=RC, scale=1.0, freqs=FREQS):
    return [point(f, scale * tf.h(f)) for f in freqs]


@pytest.fixture
def plot(qtbot):
    p = BodePlot(TraceSet())
    qtbot.addWidget(p)
    p.resize(900, 600)
    p.show()
    QApplication.processEvents()
    return p


def names(plot):
    return plot.marker_layer.names()


def placed(plot):
    return {p.marker.name: p for p in plot.placed()}


def tick(plot, *kinds, on=True):
    for k in kinds:
        plot.marker_actions[k].setChecked(on)


# ---------------------------------------------------------------------- the menu and the automatic markers
def test_no_marker_until_one_is_switched_on(plot):
    plot.set_points(sweep())
    assert names(plot) == [] and plot.marker_kinds() == [] and plot.placed() == []
    assert plot.markers_btn.menu() is plot.marker_menu and plot.marker_menu.toolTipsVisible()
    assert [a.text() for a in plot.marker_menu.actions() if not a.isSeparator()] == [
        "-3 dB", "Peak", "Notch", "Margins", "Markers on", "Add marker", "Remove all markers", "Copy marker values"]
    assert list(plot.marker_actions) == list(KINDS) and all(a.isCheckable() for a in plot.marker_actions.values())


def test_cutoff_marker_follows_its_tick(plot):
    plot.set_points(sweep())
    tick(plot, "cutoff")
    assert names(plot) == ["fc"] and plot.marker_kinds() == ["cutoff"]
    p = placed(plot)["fc"]
    assert p.marker.freq == pytest.approx(FC, rel=0.02)
    assert p.y_gain == pytest.approx(-3.0, abs=0.05) and p.y_phase == pytest.approx(-45.0, abs=1.0)
    assert p.text.startswith("fc 1.") and "kHz" in p.text and "dB" in p.text and p.text.endswith("°")
    it = plot.marker_layer.items("fc")
    assert it.host == 0 and it.text.toPlainText() == p.text
    for line in it.lines:                                        # a line through both plots, at log10 of the frequency
        assert line.value() == pytest.approx(math.log10(p.marker.freq)) and not line.movable
    assert it.dots[0].getData()[0][0] == pytest.approx(math.log10(p.marker.freq))
    assert it.dots[0].getData()[1][0] == pytest.approx(p.y_gain)
    assert it.dots[1].getData()[1][0] == pytest.approx(p.y_phase)
    tick(plot, "cutoff", on=False)
    assert names(plot) == [] and plot.marker_kinds() == []


def test_peak_edges_and_notch(plot):
    plot.set_points(sweep(BPF))
    tick(plot, "cutoff", "peak", "notch")
    assert names(plot) == ["fL", "fH", "pk"]                     # a band-pass has no notch: switched on, not drawn
    assert [p.marker.name for p in plot.placed()] == ["fL", "fH", "pk", "nt"]
    assert placed(plot)["pk"].marker.freq == pytest.approx(F0, rel=0.01)
    assert "\nBW " in placed(plot)["fH"].text and " Q " in placed(plot)["fH"].text
    plot.set_points(sweep(NOTCH))
    assert names(plot) == ["fc", "nt"]                           # one edge of the notch is 3 dB down from the flat part
    assert placed(plot)["nt"].marker.freq == pytest.approx(F0, rel=0.03)


def test_margins_sit_on_their_own_plots(plot):
    plot.set_points(sweep(LOOP))
    tick(plot, "margins")
    assert names(plot) == ["GM", "PM"]
    gm, pm = placed(plot)["GM"], placed(plot)["PM"]
    assert gm.text.startswith("GM ") and " dB at " in gm.text and pm.text.startswith("PM ") and "° at " in pm.text
    assert gm.y_phase is None and gm.y_gain == pytest.approx(-gm.marker.margin)
    assert pm.y_gain is None and pm.y_phase == pytest.approx(pm.marker.margin - 180.0)
    layer = plot.marker_layer
    assert layer.items("GM").host == 0 and layer.items("PM").host == 1
    assert len(layer.items("GM").dots[1].getData()[0]) == 0 and len(layer.items("PM").dots[0].getData()[0]) == 0
    assert 30.0 < pm.marker.margin < 60.0 and 15.0 < gm.marker.margin < 25.0


def test_set_marker_kinds_ticks_the_menu(plot):
    plot.set_points(sweep(BPF))
    plot.set_marker_kinds(["peak", "cutoff", "bogus"])
    assert plot.marker_kinds() == ["cutoff", "peak"]
    assert [k for k, a in plot.marker_actions.items() if a.isChecked()] == ["cutoff", "peak"]
    plot.set_marker_kinds([])
    assert plot.marker_kinds() == [] and names(plot) == []


# ---------------------------------------------------------------------- which trace
def test_markers_on_another_trace(plot):
    plot.set_span_hint(100.0, 1e7)
    plot.set_points(sweep())
    th = plot.set.add_theory(BPF)
    plot.traces_changed()
    tick(plot, "peak", "cutoff")
    assert names(plot) == ["fc"]                                 # the live sweep is the RC low-pass
    assert [a.text() for a in plot.marker_trace_menu.actions()] == ["Sweep", th.name]
    assert [a.isChecked() for a in plot.marker_trace_menu.actions()] == [True, False]
    plot.marker_trace_menu.actions()[1].trigger()
    assert plot.markers.trace_id == th.id and names(plot) == ["fL", "fH", "pk"]
    assert [a.isChecked() for a in plot.marker_trace_menu.actions()] == [False, True]
    plot.set.set_visible(th.id, False)
    plot.traces_changed()
    assert names(plot) == []                                     # a hidden trace has no markers
    plot.set.set_visible(th.id, True)
    plot.set.remove(th.id)
    plot.traces_changed()
    assert plot.markers.trace_id == plot.set.live.id and names(plot) == ["fc"]
    assert [a.text() for a in plot.marker_trace_menu.actions()] == ["Sweep"]


def test_markers_measure_the_difference_in_relative_view(plot):
    plot.set_points(sweep(scale=0.5))
    th = plot.set.add_theory(RC)
    plot.set.set_reference(th.id)
    plot.traces_changed()
    tick(plot, "cutoff", "margins")
    plot.add_marker(1000.0)
    assert [p.marker.name for p in plot.placed()] == ["fc", "M1"]            # no margins in the relative display
    assert names(plot) == ["M1"]                                 # a flat difference has no cut-off
    assert placed(plot)["M1"].y_gain == pytest.approx(-6.02, abs=0.01)
    assert placed(plot)["M1"].y_phase == pytest.approx(0.0, abs=0.01)


def test_no_markers_on_a_trace_that_is_not_drawn(plot):
    """Review focus: Voltage on a theory curve or on a file with no voltage columns."""
    plot.set_span_hint(100.0, 1e7)
    plot.set_points(sweep())
    th = plot.set.add_theory(BPF)
    f = plot.set.add_file(SweepResult({}, [replace(p, vdut_amp=float("nan")) for p in sweep(BPF)], {}), "old.csv")
    plot.traces_changed()
    tick(plot, "peak")
    plot.add_marker(1000.0)
    for trace in (th, f):
        plot.set_marker_trace(trace.id)
        plot.set_unit("db")
        assert names(plot) == ["pk", "M1"]
        plot.set_unit("v")
        assert names(plot) == [] and plot.placed() == []


# ---------------------------------------------------------------------- units, phase, axis
def test_marker_values_in_the_three_units(plot):
    plot.set_points(sweep())
    tick(plot, "cutoff")
    db = placed(plot)["fc"]
    plot.set_unit("pct")
    pct = placed(plot)["fc"]
    assert pct.y_gain == pytest.approx(100 * 10 ** (db.y_gain / 20)) and " %" in pct.text and "dB" not in pct.text
    plot.set_unit("v")
    v = placed(plot)["fc"]
    assert v.marker.freq == pytest.approx(db.marker.freq)        # the rule works on the gain, also in Voltage
    assert v.y_gain == pytest.approx(abs(RC.h(v.marker.freq)), rel=0.01) and "Vpp" in v.text       # 2 x 0.5 x |H|


def test_marker_phase_follows_the_unwrap_box(plot):
    plot.set_points(sweep(LOOP))
    plot.add_marker(50e3)                                        # the loop's phase is about -195 degrees there
    assert placed(plot)["M1"].y_phase == pytest.approx(164.8, abs=1.0) and "+16" in placed(plot)["M1"].text
    plot.set_unwrap(True)
    assert placed(plot)["M1"].y_phase == pytest.approx(-195.2, abs=1.0) and "-19" in placed(plot)["M1"].text
    line_y = plot.items(plot.set.live).phase_line.getData()[1]
    i = int(np.argmin(np.abs(np.array(FREQS) - 50e3)))
    assert placed(plot)["M1"].y_phase == pytest.approx(float(line_y[i]), abs=3.0)        # on the drawn curve


def test_markers_without_phase(plot):
    """Review focus: a magnitude-only measurement has no phase plot."""
    plot.set_points(sweep(LOOP))
    plot.set_has_phase(False)
    tick(plot, "cutoff", "margins")
    plot.add_marker(1000.0)
    assert names(plot) == ["fc", "M1"]
    assert all(p.y_phase is None and "°" not in p.text for p in plot.placed())
    assert all(plot.marker_layer.items(n).host == 0 for n in names(plot))


def test_markers_on_a_linear_frequency_axis(plot):
    """Review focus: sweep type Linear."""
    plot.set_log_x(False)
    plot.set_points(sweep())
    tick(plot, "cutoff")
    f = placed(plot)["fc"].marker.freq
    it = plot.marker_layer.items("fc")
    assert it.lines[0].value() == pytest.approx(f) and it.dots[0].getData()[0][0] == pytest.approx(f)
    n = plot.add_marker()
    (x0, x1), _g, _p = plot.view_ranges()
    assert n == 1 and x0 < plot.markers.user[1] < x1 and plot.markers.user[1] > 0
    plot.set_log_x(True)
    assert plot.marker_layer.items("fc").lines[0].value() == pytest.approx(math.log10(f))


def test_a_flagged_point_shows_in_the_label(plot):
    pts = sweep()
    i = next(k for k, p in enumerate(pts) if p.freq_hz > FC)
    pts[i].flags |= Flag.LOW_SNR
    plot.set_points(pts)
    tick(plot, "cutoff")
    assert placed(plot)["fc"].text.endswith("(flagged)")
    pts[i].flags = Flag.PREVIEW                                  # a quiet flag does not count
    plot.set_points(pts)
    assert "(flagged)" not in placed(plot)["fc"].text


# ---------------------------------------------------------------------- user markers
def test_add_move_and_remove_user_markers(plot):
    plot.set_points(sweep())
    assert plot.add_marker(1000.0) == 1 and plot.add_marker(5000.0) == 2
    assert names(plot) == ["M1", "M2"]
    p = placed(plot)["M1"]
    h = RC.h(1000.0)
    assert p.marker.freq == 1000.0 and p.y_gain == pytest.approx(20 * math.log10(abs(h)), abs=0.02)
    assert p.text.startswith("M1 1 kHz  ") and p.y_phase == pytest.approx(math.degrees(cmath.phase(h)), abs=0.2)
    it = plot.marker_layer.items("M1")
    assert all(line.movable for line in it.lines)
    plot.move_marker(1, 2500.0)
    assert placed(plot)["M1"].marker.freq == 2500.0
    assert all(line.value() == pytest.approx(math.log10(2500.0)) for line in it.lines)
    plot.move_marker(1, -5.0)                                    # an impossible frequency is ignored
    assert plot.markers.user[1] == 2500.0
    plot.remove_marker(1)
    assert names(plot) == ["M2"]
    assert plot.add_marker(100e3) == 1                           # the lowest free number
    plot.clear_markers()
    assert names(plot) == [] and plot.markers.user == {}


def test_dragging_a_marker_line_moves_the_marker(plot):
    plot.set_points(sweep())
    plot.add_marker(1000.0)
    gain_line, phase_line = plot.marker_layer.items("M1").lines
    gain_line.setValue(math.log10(5000.0))
    gain_line.sigDragged.emit(gain_line)                         # what pyqtgraph sends while the mouse drags it
    assert plot.markers.user[1] == pytest.approx(5000.0)
    assert phase_line.value() == pytest.approx(math.log10(5000.0))           # the other plot's line follows
    assert placed(plot)["M1"].text.startswith("M1 5 kHz")
    assert plot.marker_layer.items("M1").lines[0] is gain_line   # the dragged line was not rebuilt


def test_at_most_eight_user_markers(plot):
    plot.set_points(sweep())
    assert [plot.add_marker(1000.0 * k) for k in range(1, MAX_USER + 1)] == list(range(1, MAX_USER + 1))
    assert not plot.act_add_marker.isEnabled()
    assert plot.add_marker(123.0) is None and len(names(plot)) == MAX_USER
    plot.remove_marker(4)
    assert plot.act_add_marker.isEnabled()


def test_add_marker_from_the_menu_lands_in_the_view(plot):
    plot.set_points(sweep())
    plot.act_add_marker.trigger()
    (x0, x1), _g, _p = plot.view_ranges()
    assert math.log10(plot.markers.user[1]) == pytest.approx((x0 + x1) / 2)
    plot.act_clear_markers.trigger()
    assert plot.markers.user == {}


def test_user_marker_outside_the_trace_keeps_its_line(plot):
    plot.set_points(sweep())
    plot.add_marker(5e7)
    p = placed(plot)["M1"]
    assert p.text == "M1 50 MHz  outside the trace" and p.y_gain is None and p.y_phase is None
    it = plot.marker_layer.items("M1")
    assert it.lines[0].value() == pytest.approx(math.log10(5e7)) and len(it.dots[0].getData()[0]) == 0


def test_markers_follow_a_running_sweep(plot):
    """Review focus: a new sweep empties the live trace and fills it point by point."""
    plot.set_points(sweep())
    tick(plot, "cutoff", "peak", "notch", "margins")
    plot.add_marker(1000.0)
    plot.clear()                                                 # Start: the live trace is emptied
    assert names(plot) == [] and plot.markers.user == {1: 1000.0}
    seen = []
    for p in sweep():
        plot.add_point(p)
        seen.append(tuple(names(plot)))
    assert seen[0] == ("M1",) and seen[-1] == ("fc", "M1")       # M1 waits outside the trace; no peak, notch or margin
    assert set(seen) == {("M1",), ("fc", "M1")} and seen.index(("fc", "M1")) > 10        # the cut-off appears once the curve has fallen


# ---------------------------------------------------------------------- layout
def test_labels_do_not_overlap(plot):
    plot.set_points(sweep())
    plot.add_marker(1000.0), plot.add_marker(1010.0), plot.add_marker(1020.0)
    QApplication.processEvents()
    plot.refresh()
    rects = [plot.marker_layer.label_rect(n) for n in ("M1", "M2", "M3")]
    assert all(r is not None and r.width() > 10 for r in rects)
    assert not any(a.intersects(b) for i, a in enumerate(rects) for b in rects[i + 1:])


def test_fit_view_ignores_the_markers(plot):
    plot.set_points(sweep())
    before_data, before_view = plot.data_ranges(), plot.view_ranges()
    tick(plot, "cutoff")
    plot.add_marker(5e9)                                         # far beyond the data
    plot.fit_view()
    assert plot.data_ranges() == before_data
    assert np.allclose(np.ravel(plot.view_ranges()), np.ravel(before_view))


def test_marker_items_use_the_marker_colour_and_stay_below_the_live_points(plot):
    plot.set_points(sweep())
    tick(plot, "cutoff")
    it = plot.marker_layer.items("fc")
    assert it.lines[0].pen.color().name() == theme.MARK_INK.lower()
    assert theme.MARK_INK not in theme.SERIES
    live = plot.items(plot.set.live)
    assert all(item.zValue() < live.gain_ok.zValue() for item in it.lines + it.dots + [it.text])
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_gui_markers.py -q`
Expected: every test fails with `AttributeError: 'BodePlot' object has no attribute 'marker_actions'` (or `marker_layer`, `add_marker`).

- [ ] **Step 3: The marker colour**

In `src/bodeplot/gui/theme.py`, after the line `FLAGGED = WARNING …`:

```python
MARK_INK = INK_2            # the markers of the Bode plot (lines, dots, labels): neutral, never a series colour
```

- [ ] **Step 4: Write the layer**

Create `src/bodeplot/gui/marker_layer.py`:

```python
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
    def _make(self, m) -> _Items:
        it = _Items()
        it.host = 1 if m.kind == "pm" else 0
        movable = m.kind == "user"
        for plot in self.plots:
            line = pg.InfiniteLine(angle=90, movable=movable,
                                   pen=pg.mkPen(theme.MARK_INK, width=1, style=Qt.DashLine),
                                   hoverPen=pg.mkPen(theme.INK, width=1.5, style=Qt.DashLine))
            if movable:
                line.sigDragged.connect(lambda ln, n=m.number: self.on_moved(n, self.freq(ln.value())))
            dot = pg.ScatterPlotItem(size=theme.MARKER, symbol="d", pen=pg.mkPen(theme.SURFACE, width=theme.RING),
                                     brush=pg.mkBrush(theme.MARK_INK))
            for item in (line, dot):
                item.setZValue(Z)
                plot.addItem(item, ignoreBounds=True)        # a marker never widens "Fit view"
            it.lines.append(line)
            it.dots.append(dot)
        it.text = pg.TextItem(color=theme.MARK_INK, anchor=(0, 0), fill=pg.mkBrush(theme.SURFACE))
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
            it = self._items.get(p.marker.name) or self._make(p.marker)
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
        """Put every label next to its dot (at the top of the plot when it has none), to the
        left of it when the right edge is near, and below any label already there."""
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
                left = dot.x() + GAP
                if left + w > box.right():
                    left = dot.x() - GAP - w
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
```

- [ ] **Step 5: Wire it into `gui/bode_plot.py`**

Change the import block at the top to (`QApplication` and the dialogs come in Task 5):

```python
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..io.export_image import ImageSeries
from ..markers import KINDS, MAX_USER, MarkerSet, Placed, label
from ..measure.sinefit import unwrap_deg
from ..models import Flag, PointResult
from ..traces import Drawn, Trace, TraceSet
from ..units import fmt_si
from . import theme
from .marker_layer import MarkerLayer
from .si_widgets import SiAxis
```

Below the constant `COLORS` add the menu texts:

```python
# The automatic markers of the Markers menu: kind -> (menu text, explanation)
MARKER_MENU = {
    "cutoff": ("-3 dB", "Mark where the gain has fallen 3 dB below the highest gain of the trace: the cut-off of "
                        "a low-pass or high-pass, or both edges of a band-pass with its bandwidth and Q"),
    "peak": ("Peak", "Mark the highest gain of the trace when it is a real peak: not at an end of the trace and "
                     "at least 1 dB above both ends"),
    "notch": ("Notch", "Mark the lowest gain of the trace when it is a real notch: not at an end of the trace and "
                       "at least 1 dB below both ends"),
    "margins": ("Margins", "For a trace that is a loop gain: the gain margin where the phase passes -180° and the "
                           "phase margin where the gain passes 0 dB. Not shown in the relative display or "
                           "without phase"),
}
```

In `BodePlot.__init__`:

1. After the block that sets up `self.ref_box` (before `top.addWidget(self.unwrap_box)`), create the marker state and the button:

```python
        self.markers = MarkerSet()
        self._marks: list = []              # the markers of the last refresh (markers.Marker)
        self._placed: list[Placed] = []     # the same, with texts and positions
        self.markers_btn = QPushButton("Markers")
        self.markers_btn.setToolTip("Markers on the curve: the -3 dB points, the peak, the notch, the gain and "
                                    "phase margin, and markers of your own at any frequency")
        self._build_marker_menu()
```

2. In the row, put the button after Fit view:

```python
        top.addWidget(self.unwrap_box)
        top.addWidget(self.fit_btn)
        top.addWidget(self.markers_btn)
        top.addWidget(QLabel(" Vertical"))
```

3. After the loop that creates `self._vlines` (the plots exist now) and before `self.follow = True`:

```python
        self.marker_layer = MarkerLayer(self.gain_plot, self.phase_plot, self.move_marker)
```

Add a new section to the class, after `set_span_hint`:

```python
    # ---- markers (rules in markers.py, graphics in gui/marker_layer.py)
    def _build_marker_menu(self) -> None:
        menu = QMenu(self.markers_btn)
        menu.setToolTipsVisible(True)
        self.marker_actions = {}
        for kind in KINDS:
            text, tip = MARKER_MENU[kind]
            act = menu.addAction(text)
            act.setCheckable(True)
            act.setToolTip(tip)
            act.toggled.connect(lambda on, k=kind: self.set_marker_kind(k, on))
            self.marker_actions[kind] = act
        menu.addSeparator()
        self.marker_trace_menu = menu.addMenu("Markers on")
        self.marker_trace_menu.setToolTipsVisible(True)
        self.marker_trace_menu.menuAction().setToolTip("The trace the markers measure: all automatic markers and "
                                                       "your own read this one trace, as it is drawn")
        menu.addSeparator()
        self.act_add_marker = menu.addAction("Add marker")
        self.act_add_marker.setToolTip("Put a marker of your own in the middle of the visible frequency range; "
                                       "drag it, or right-click it to type its frequency (up to %d)" % MAX_USER)
        self.act_add_marker.triggered.connect(lambda _checked=False: self.add_marker())
        self.act_clear_markers = menu.addAction("Remove all markers")
        self.act_clear_markers.setToolTip("Remove every marker of your own; the automatic markers stay as ticked")
        self.act_clear_markers.triggered.connect(lambda _checked=False: self.clear_markers())
        self.act_copy_markers = menu.addAction("Copy marker values")
        self.act_copy_markers.setToolTip("Copy the markers as a table (name, frequency, gain, phase, note) "
                                         "for a report or a spreadsheet")
        self.markers_btn.setMenu(menu)
        self.marker_menu = menu
        self._fill_marker_traces()

    def _fill_marker_traces(self) -> None:
        if self.set.get(self.markers.trace_id) is None:     # the chosen trace was removed
            self.markers.trace_id = self.set.live.id
        self.marker_trace_menu.clear()
        group = QActionGroup(self.marker_trace_menu)
        for t in self.set.traces:
            act = self.marker_trace_menu.addAction(t.name)
            act.setCheckable(True)
            act.setChecked(t.id == self.markers.trace_id)
            act.setToolTip("Measure the trace '%s' with the markers" % t.name)
            act.triggered.connect(lambda _checked=False, i=t.id: self.set_marker_trace(i))
            group.addAction(act)

    def marker_kinds(self) -> list[str]:
        """The automatic markers that are switched on, in menu order."""
        return [k for k in KINDS if k in self.markers.kinds]

    def set_marker_kinds(self, kinds) -> None:
        for kind, act in self.marker_actions.items():
            act.setChecked(kind in kinds)                   # toggled -> set_marker_kind

    def set_marker_kind(self, kind: str, on: bool) -> None:
        self.markers.set_kind(kind, on)
        if self.marker_actions[kind].isChecked() != on:
            self.marker_actions[kind].setChecked(on)
        self._update_markers()

    def set_marker_trace(self, trace_id: int) -> None:
        self.markers.trace_id = trace_id
        self._fill_marker_traces()
        self._update_markers()

    def placed(self) -> list[Placed]:
        """The markers of the chosen trace as shown, switched-on ones that were not found included."""
        return list(self._placed)

    def add_marker(self, freq_hz: float | None = None) -> int | None:
        """A marker of the user's at freq_hz (None: the middle of the visible range).
        Returns its number, or None when there are MAX_USER already."""
        if freq_hz is None:
            x0, x1 = self.gain_plot.getPlotItem().vb.viewRange()[0]
            mid = (x0 + x1) / 2.0
            freq_hz = 10.0 ** mid if self.log_x else mid
        n = self.markers.add(freq_hz)
        self._update_markers()
        return n

    def move_marker(self, number: int, freq_hz: float) -> None:
        if self.markers.move(number, freq_hz):
            self._update_markers()

    def remove_marker(self, number: int) -> None:
        self.markers.remove(number)
        self._update_markers()

    def clear_markers(self) -> None:
        self.markers.clear_user()
        self._update_markers()

    def _phase_shown(self, deg: float) -> float:
        """A phase of the unwrapped curve as the phase plot shows it."""
        return deg if self.unwrap() else (deg + 180.0) % 360.0 - 180.0

    def _marker_curve(self):
        """(curve, the measured points behind it or None) of the chosen trace as it is drawn;
        None when that trace is not on the plot (hidden, empty, or not drawn in this unit)."""
        t = self.set.get(self.markers.trace_id)
        if t is None:
            self.markers.trace_id = self.set.live.id
            t = self.set.live
        if not any(d.trace is t and len(f) for d, f, _gain, _phase in self._shown):
            return None
        curve, points = self.set.curve(t.id, self.span_hint, relative=self.is_relative())
        if points is not None:
            curve.flagged = [bool(p.flags & ~QUIET) for p in points]
        return curve, points

    def _place(self, m, curve, points) -> Placed:
        """Text and dot positions of one marker in what the plots show now."""
        if not m.found:
            return Placed(m, "", None, None)
        if not m.has_value:
            return Placed(m, label(m), None, None)
        if self.unit() == "v":
            # the output voltage between two points, by the curve's own rule (log over log frequency)
            logs = [math.log10(2.0 * p.vdut_amp) if p.vdut_amp > 0 and math.isfinite(p.vdut_amp) else float("nan")
                    for p in points]
            lg = curve.interp(m.freq, logs)
            y = 10.0 ** lg if lg is not None else None
            value = fmt_si(y, "Vpp", 3) if y is not None else ""
        elif self.unit() == "pct":
            y = 100.0 * 10.0 ** (m.db / 20.0)
            value = "%.3g %%" % y
        else:
            y = m.db
            value = "%+.2f dB" % y
        phase = self._phase_shown(m.deg) if self.has_phase else None
        return Placed(m, label(m, value, phase), None if m.kind == "pm" else y, None if m.kind == "gm" else phase)

    def _update_markers(self) -> None:
        got = self._marker_curve()
        self._marks, self._placed = [], []
        if got is not None:
            curve, points = got
            self._marks = self.markers.evaluate(curve, margins=self.has_phase and not self.is_relative())
            self._placed = [self._place(m, curve, points) for m in self._marks]
        self.marker_layer.show(self._placed, self.log_x)
        self.act_add_marker.setEnabled(len(self.markers.user) < MAX_USER)
```

Three existing methods change:

`traces_changed` also refills the trace submenu:

```python
    def traces_changed(self) -> None:
        """The set was changed from outside (the Traces panel): names, order, visibility."""
        self._fill_ref_box()
        self._fill_marker_traces()
        self.refresh()
```

`set_has_phase` ends with a marker update (the labels lose or gain their phase):

```python
        self.unwrap_box.setVisible(has)
        self._update_markers()
```

`refresh` ends with one (after the `if self.follow:` block, at the method's own indentation):

```python
        self._update_markers()
```

`set_has_phase` and `refresh` are first called from `__init__` (`self.set_log_x(True)` at its end), after `self.marker_layer` exists; keep that order.

- [ ] **Step 6: Run the new tests**

Run: `.venv\Scripts\python -m pytest tests\test_gui_markers.py -q`
Expected: 22 passed.

- [ ] **Step 7: Architecture map and the whole suite**

In `docs/ARCHITECTURE.md`, Modules table: add the row of the layer after `gui/main_window.py`, and replace the row of `gui/bode_plot.py`:

```markdown
| `gui/bode_plot.py` | gain and phase plots of a trace set, relative display, follow / fit view, vertical unit, re-measure request; the Markers menu, marker texts and positions | `gui/marker_layer.py`, `gui/si_widgets.py`, `gui/theme.py`, `io/export_image.py`, `markers.py`, `measure/sinefit.py`, `models.py`, `traces.py`, `units.py` |
| `gui/marker_layer.py` | the markers as graphics on both plots: lines, dots, labels that do not overlap, dragging | `gui/theme.py`, `markers.py` |
```

Run: `.venv\Scripts\python -m pytest -q`
Expected: all passed: the 437 tests from before this plan and the new ones. (The tooltip guard already passes: the new button has its explanation.)

- [ ] **Step 8: Commit**

```powershell
git add src/bodeplot/gui/marker_layer.py src/bodeplot/gui/theme.py src/bodeplot/gui/bode_plot.py tests/test_gui_markers.py docs/ARCHITECTURE.md
git commit -m "Markers on the plot: the Markers menu, automatic markers and the user's own on the chosen trace"
```

---

### Task 5: Right-click menus, typed frequency, reference marker, clipboard, tooltips

**Files:**
- Modify: `src/bodeplot/gui/bode_plot.py`
- Modify: `tests/test_gui_markers.py` (append)
- Modify: `tests/test_gui_tooltips.py`

**Interfaces:**
- Consumes: everything of Task 4; `markers.table`; `units.parse_si`.
- Produces on `BodePlot`: `context_menu(freq_hz: float, number: int | None = None) -> QMenu` (built, not shown), `set_marker_frequency(number: int, text: str) -> bool`, `toggle_reference_marker(number: int)`, `marker_text() -> str`, `copy_markers()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gui_markers.py`:

```python
# ---------------------------------------------------------------------- right-click, typed frequency, reference, copy
def test_right_click_on_the_plot_adds_a_marker_there(plot):
    plot.set_points(sweep())
    menu = plot.context_menu(2000.0)
    assert [a.text() for a in menu.actions()] == ["Add marker here"] and menu.toolTipsVisible()
    menu.actions()[0].trigger()
    assert plot.markers.user == {1: 2000.0}
    for k in range(MAX_USER - 1):
        plot.add_marker(100.0 * (k + 1))
    assert not plot.context_menu(2000.0).actions()[0].isEnabled()            # the limit


def test_right_click_on_a_user_marker(plot):
    plot.set_points(sweep())
    plot.add_marker(1000.0), plot.add_marker(10000.0)
    menu = plot.context_menu(1000.0, 1)
    assert [a.text() for a in menu.actions()] == ["Set frequency…", "Reference marker", "Remove"]
    ref = menu.actions()[1]
    assert ref.isCheckable() and not ref.isChecked()
    ref.trigger()
    assert plot.markers.ref == 1 and plot.context_menu(1000.0, 1).actions()[1].isChecked()
    assert placed(plot)["M1"].text.endswith("(ref)")
    second = placed(plot)["M2"].text.split("\n")[1]
    assert second.startswith("Δ M1  ×10  ") and second.endswith("dB/dec")
    plot.context_menu(1000.0, 1).actions()[2].trigger()          # Remove
    assert names(plot) == ["M2"] and plot.markers.ref is None and "\n" not in placed(plot)["M2"].text


def test_the_layer_finds_the_marker_under_the_mouse(plot):
    plot.set_points(sweep())
    plot.add_marker(1000.0)
    QApplication.processEvents()
    vb = plot.gain_plot.getPlotItem().vb
    from PySide6.QtCore import QPointF
    on = vb.mapViewToScene(QPointF(math.log10(1000.0), -10.0))
    off = vb.mapViewToScene(QPointF(math.log10(30000.0), -10.0))
    assert plot.marker_layer.user_at(plot.gain_plot, on) == 1
    assert plot.marker_layer.user_at(plot.gain_plot, off) is None
    plot.marker_actions["cutoff"].setChecked(True)               # an automatic marker has no menu of its own
    fc = vb.mapViewToScene(QPointF(math.log10(placed(plot)["fc"].marker.freq), -10.0))
    assert plot.marker_layer.user_at(plot.gain_plot, fc) is None


def test_typed_frequency(plot):
    plot.set_points(sweep())
    plot.add_marker(1000.0)
    assert plot.set_marker_frequency(1, "2.5k") and plot.markers.user[1] == 2500.0
    assert plot.set_marker_frequency(1, "1 MHz") and plot.markers.user[1] == 1e6
    for bad in ("", "abc", "-5", "0", "1x"):
        assert not plot.set_marker_frequency(1, bad)
    assert plot.markers.user[1] == 1e6 and placed(plot)["M1"].text.startswith("M1 1 MHz")
    assert not plot.set_marker_frequency(7, "1k")                # no such marker


def test_copy_marker_values(plot):
    plot.set_points(sweep())
    tick(plot, "cutoff", "peak")
    plot.add_marker(1000.0)
    text = plot.marker_text()
    rows = [r.split("\t") for r in text.splitlines()]
    assert rows[0] == ["Markers on: Sweep"] and [r[0] for r in rows[2:]] == ["fc", "pk", "M1"]
    assert rows[3] == ["pk", "", "", "", "none"] and float(rows[4][1]) == 1000.0
    assert float(rows[2][3]) == pytest.approx(-45.0, abs=1.0)
    plot.act_copy_markers.trigger()
    assert QApplication.clipboard().text() == text
    th = plot.set.add_theory(RC)
    plot.set.set_reference(th.id)
    plot.traces_changed()
    assert plot.marker_text().splitlines()[0] == "Markers on: Sweep, relative to " + th.name


def test_copied_phase_is_the_phase_shown(plot):
    plot.set_points(sweep(LOOP))
    plot.add_marker(50e3)
    wrapped = float(plot.marker_text().splitlines()[2].split("\t")[3])
    plot.set_unwrap(True)
    unwrapped = float(plot.marker_text().splitlines()[2].split("\t")[3])
    assert wrapped == pytest.approx(164.8, abs=1.0) and unwrapped == pytest.approx(wrapped - 360.0, abs=0.02)
```

In `tests/test_gui_tooltips.py`, in `test_plot_trace_and_log_options_explain_themselves`, add `"Markers": plot.markers_btn,` to the `named` dictionary, and add a new test at the end of the file:

```python
def test_marker_menus_explain_themselves(win):
    plot = win.plot
    plot.add_marker(1000.0)
    menus = {"Markers": plot.marker_menu, "Markers on": plot.marker_trace_menu,
             "plot right-click": plot.context_menu(1000.0)}
    silent = []
    for where, menu in menus.items():
        assert menu.toolTipsVisible(), where
        silent += ["%s > %s" % (where, a.text()) for a in menu.actions()
                   if not a.isSeparator() and not explains(a.toolTip(), a.text())]
    marker_menu = plot.context_menu(1000.0, 1)                   # built after the first one: one context menu at a time
    assert marker_menu.toolTipsVisible()
    silent += ["marker right-click > %s" % a.text() for a in marker_menu.actions() if not explains(a.toolTip(), a.text())]
    assert not silent, "marker menu items without an explanation: %s" % silent
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_gui_markers.py tests\test_gui_tooltips.py -q`
Expected: the six new marker tests and `test_marker_menus_explain_themselves` fail with `AttributeError` (`context_menu`, `set_marker_frequency`, `marker_text`); the rest pass.

- [ ] **Step 3: Implement in `gui/bode_plot.py`**

Imports: add `QApplication`, `QInputDialog`, `QMessageBox` to the `PySide6.QtWidgets` import, `QCursor` to the `PySide6.QtGui` import (and delete the local `from PySide6.QtGui import QCursor` inside `_clicked`), `table` to the `..markers` import, `parse_si` to the `..units` import.

In `__init__`, next to `self._placed`:

```python
        self._ctx_menu: QMenu | None = None
```

and connect the copy action at the end of `_build_marker_menu`, before `self.markers_btn.setMenu(menu)`:

```python
        self.act_copy_markers.triggered.connect(lambda _checked=False: self.copy_markers())
```

Change the scene connection in `__init__` so that the handler knows the plot:

```python
            p.scene().sigMouseClicked.connect(lambda ev, plot=p: self._scene_clicked(plot, ev))
```

and replace `_scene_clicked`:

```python
    def _scene_clicked(self, plot, ev):
        if ev.double():
            ev.accept()
            self.fit_view()
        elif ev.button() == Qt.RightButton and plot.sceneBoundingRect().contains(ev.scenePos()):
            ev.accept()
            xv = plot.getPlotItem().vb.mapSceneToView(ev.scenePos()).x()
            number = self.marker_layer.user_at(plot, ev.scenePos())
            self.context_menu(10.0 ** xv if self.log_x else xv, number).exec(QCursor.pos())
```

Add to the markers section:

```python
    def context_menu(self, freq_hz: float, number: int | None = None) -> QMenu:
        """The right-click menu of the plot at freq_hz (number: the user marker under the
        mouse). Built here and shown by the caller, so that a test can read it."""
        if self._ctx_menu is not None:
            self._ctx_menu.deleteLater()
        menu = self._ctx_menu = QMenu(self)
        menu.setToolTipsVisible(True)
        if number is None:
            act = menu.addAction("Add marker here")
            act.setToolTip("Put a marker of your own at this frequency; it reads gain and phase of the "
                           "chosen trace there")
            act.setEnabled(len(self.markers.user) < MAX_USER)
            act.triggered.connect(lambda _checked=False: self.add_marker(freq_hz))
            return menu
        act = menu.addAction("Set frequency…")
        act.setToolTip("Type the frequency this marker stands at, for example 1k or 2.5M")
        act.triggered.connect(lambda _checked=False: self._ask_frequency(number))
        act = menu.addAction("Reference marker")
        act.setCheckable(True)
        act.setChecked(self.markers.ref == number)
        act.setToolTip("Make this the reference marker: every other marker of yours also shows its difference "
                       "to it and the slope in dB per decade")
        act.triggered.connect(lambda _checked=False: self.toggle_reference_marker(number))
        act = menu.addAction("Remove")
        act.setToolTip("Remove this marker from the plot; the others keep their numbers")
        act.triggered.connect(lambda _checked=False: self.remove_marker(number))
        return menu

    def set_marker_frequency(self, number: int, text: str) -> bool:
        """Move a user marker to a typed frequency ('1k', '2.5 MHz'). False, and nothing
        changes, when the text is not a positive frequency."""
        try:
            freq = parse_si(text, "Hz")
        except ValueError:
            return False
        if not self.markers.move(number, freq):
            return False
        self._update_markers()
        return True

    def _ask_frequency(self, number: int) -> None:
        if number not in self.markers.user:
            return
        text, ok = QInputDialog.getText(self, "Marker M%d" % number, "Frequency (for example 1k or 2.5M):",
                                        text=fmt_si(self.markers.user[number], "Hz"))
        if ok and not self.set_marker_frequency(number, text):
            QMessageBox.warning(self, "Marker M%d" % number,
                                "'%s' is not a frequency. The marker stays where it was." % text)

    def toggle_reference_marker(self, number: int) -> None:
        self.markers.toggle_ref(number)
        self._update_markers()

    def marker_text(self) -> str:
        """The markers as a tab-separated table (the clipboard text)."""
        t = self.set.get(self.markers.trace_id) or self.set.live
        title = "Markers on: " + t.name
        if self.is_relative():
            title += ", relative to " + self.set.reference().name
        return table(self._marks, title, lambda m: self._phase_shown(m.deg))

    def copy_markers(self) -> None:
        QApplication.clipboard().setText(self.marker_text())
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests\test_gui_markers.py tests\test_gui_tooltips.py tests\test_gui_traces.py tests\test_gui.py -q`
Expected: all passed (the double-click "Fit view" and the re-measure click of the older tests still work).

- [ ] **Step 5: Commit**

```powershell
git add src/bodeplot/gui/bode_plot.py tests/test_gui_markers.py tests/test_gui_tooltips.py
git commit -m "Markers: right-click menus, typed frequency, reference marker with difference and slope, copy as a table"
```

---

### Task 6: Image export and the remembered ticks

**Files:**
- Modify: `src/bodeplot/io/export_image.py`
- Modify: `src/bodeplot/io/settings.py`
- Modify: `src/bodeplot/gui/bode_plot.py` (`export_markers`)
- Modify: `src/bodeplot/gui/main_window.py` (`export`, `_load_ui_state`, `_save_ui_state`)
- Modify: `tests/test_io.py`, `tests/test_gui_traces.py` (the export spy), `tests/test_gui_markers.py` (append)

**Interfaces:**
- Consumes: `BodePlot.placed()`, `marker_kinds()`, `set_marker_kinds()` (Task 4).
- Produces:
  - `export_image.ImageMarker(freq: float, text: str, y_gain=None, y_phase=None, label_on: str = "gain")`, `export_image.PRINT_MARKER`, and `write_image(path, result, opts=None, series=None, labels=None, markers=None)`
  - `BodePlot.export_markers() -> list[ImageMarker]`
  - `AppSettings.markers: list` (the kinds switched on, in menu order) and `settings.MARKER_KINDS`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_io.py`:

```python
def test_image_with_markers(tmp_path, result):
    from bodeplot.io.export_image import ImageMarker
    marks = [ImageMarker(1591.5, "fc 1.59 kHz  -3.01 dB  -45.0°", -3.01, -45.0),
             ImageMarker(3100.0, "PM 48.3° at 3.1 kHz", None, -131.7, "phase"),
             ImageMarker(5e7, "M1 50 MHz  outside the trace"),
             ImageMarker(2000.0, "fH 2 kHz  -3.00 dB\nBW 820 Hz  Q 1.94", -3.0, -50.0)]
    for ext in ("png", "svg", "pdf"):
        out = export_image.write_image(tmp_path / ("m." + ext), result, export_image.ImageOptions(), markers=marks)
        assert out.stat().st_size > 500
    svg = (tmp_path / "m.svg").read_text(encoding="utf-8")
    assert export_image.PRINT_MARKER.lower() in svg.lower()
    plain = export_image.write_image(tmp_path / "plain.svg", result).read_text(encoding="utf-8")
    assert export_image.PRINT_MARKER.lower() not in plain.lower()            # without markers: as before
    one = export_image.write_image(tmp_path / "gain_only.svg", result, export_image.ImageOptions(show_phase=False),
                                   markers=marks)
    assert one.stat().st_size > 500                              # a phase-plot label with no phase plot is left out


def test_marker_ticks_in_the_settings():
    from bodeplot import markers
    assert settings.MARKER_KINDS == markers.KINDS
    assert settings.AppSettings().markers == []
    s = settings.AppSettings.from_dict({"markers": ["peak", "bogus", 3, "cutoff"]})
    assert s.markers == ["cutoff", "peak"]                       # known kinds only, in menu order
    assert settings.AppSettings.from_dict({"markers": "peak"}).markers == []
    assert settings.AppSettings.from_dict(s.to_dict()).markers == ["cutoff", "peak"]
```

In `tests/test_gui_traces.py`, `test_image_export_draws_what_the_plot_shows`, let the spy take the new argument:

```python
    def spy(path, result, opts=None, series=None, labels=None, **kw):
        seen.update(series=series, labels=labels)
        return real(path, result, opts, series, labels, **kw)
```

Append to `tests/test_gui_markers.py`:

```python
# ---------------------------------------------------------------------- the main window: export and settings
from bodeplot.gui.main_window import MainWindow
from bodeplot.io.settings import AppSettings
from bodeplot.models import EngineState, SweepConfig, SweepType

SIM = {"preset": "rc_lpf", "params": {"r": 1e3, "c": 100e-9}, "noise_vrms": 2e-4, "latency_ms": 0.0}


def window(qtbot, settings):
    w = MainWindow(simulate=True, settings=settings, sim_seed=7)
    w.interactive = False
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    w = window(qtbot, AppSettings(simulate=True, sim=dict(SIM)))
    yield w
    w.close()


def run_sweep(win, qtbot, lo=100.0, hi=1e5, ppd=10):
    if not win.info.connected:
        with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
            win.toggle_connection()
        qtbot.waitUntil(lambda: win.info.connected, timeout=5000)
    p = win.config.preset()
    p.sweep = SweepConfig(SweepType.LOG, lo, hi, ppd)
    p.measure.settle_ms, p.measure.settle_cycles = 0.0, 0.0
    win.config.set_preset(p)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        assert win.start_sweep(check_skew=False)
    qtbot.waitUntil(lambda: win.state is EngineState.DONE, timeout=5000)


def test_export_markers_is_what_the_plot_shows(plot):
    plot.set_points(sweep(LOOP))
    tick(plot, "cutoff", "peak", "margins")
    plot.add_marker(1000.0), plot.add_marker(5e9)
    marks = plot.export_markers()
    shown = {p.text: p for p in plot.placed() if p.marker.found}
    assert [m.text for m in marks] == list(shown) and len(marks) == len(names(plot))
    for m in marks:
        p = shown[m.text]
        assert (m.freq, m.y_gain, m.y_phase) == (p.marker.freq, p.y_gain, p.y_phase)
        assert m.label_on == ("phase" if p.marker.kind == "pm" else "gain")


def test_a_swept_cutoff_and_the_image_with_markers(win, qtbot, tmp_path, monkeypatch):
    from bodeplot.io import export_image
    run_sweep(win, qtbot)
    win.plot.marker_actions["cutoff"].setChecked(True)
    win.plot.add_marker(1000.0)
    fc = {p.marker.name: p for p in win.plot.placed()}["fc"].marker.freq
    assert fc == pytest.approx(FC, rel=0.03)                     # the simulated RC low-pass, with its noise
    seen = {}
    real = export_image.write_image

    def spy(path, result, opts=None, series=None, labels=None, markers=None):
        seen.update(markers=markers)
        return real(path, result, opts, series, labels, markers)
    monkeypatch.setattr(export_image, "write_image", spy)
    for name in ("m.png", "m.svg", "m.pdf"):
        assert win.export(tmp_path / name).stat().st_size > 500
    assert [m.text.split()[0] for m in seen["markers"]] == ["fc", "M1"]
    assert export_image.PRINT_MARKER.lower() in (tmp_path / "m.svg").read_text(encoding="utf-8").lower()


def test_marker_ticks_survive_a_restart(win, qtbot):
    assert win.plot.marker_kinds() == []                         # a first start: all four off
    win.plot.marker_actions["peak"].setChecked(True)
    win.plot.marker_actions["cutoff"].setChecked(True)
    win.plot.add_marker(1000.0)
    win._save_ui_state()
    assert win.settings.markers == ["cutoff", "peak"]
    again = window(qtbot, AppSettings.from_dict(win.settings.to_dict()))
    try:
        assert again.plot.marker_kinds() == ["cutoff", "peak"]
        assert again.plot.markers.user == {}                     # the user's markers are not kept
    finally:
        again.close()
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_io.py tests\test_gui_markers.py -q -k "markers or marker or cutoff"`
Expected: the new tests fail (`ImportError: cannot import name 'ImageMarker'`, `AttributeError: module … has no attribute 'MARKER_KINDS'`, `'BodePlot' object has no attribute 'export_markers'`).

- [ ] **Step 3: `io/export_image.py`**

After `PRINT_FLAGGED`:

```python
PRINT_MARKER = "#444444"        # marker lines, dots and labels
```

After the class `ImageSeries`:

```python
@dataclass
class ImageMarker:
    """One marker as the plot shows it: a line through both plots, a dot where it has a
    value, its text on one of them."""
    freq: float
    text: str
    y_gain: Any = None          # None: no dot on the gain plot
    y_phase: Any = None
    label_on: str = "gain"      # the plot that carries the text: "gain" | "phase"
```

Change the signature and the docstring's last sentence:

```python
def write_image(path, result: SweepResult, opts: ImageOptions | None = None,
                series: list[ImageSeries] | None = None, labels: tuple[str, str, str] | None = None,
                markers: list[ImageMarker] | None = None) -> Path:
    """The Bode plot as an image. Without `series` it draws the sweep of `result` (as it
    always did). With `series` (BodePlot.export_series) it draws exactly what the plot
    shows: every visible trace, absolute or relative, with `labels` = (gain axis, phase
    axis, note for the footer). `markers` (BodePlot.export_markers) are drawn on top."""
```

In the loop `for ax, key, label in zip(axes, …)`, after the inner `for s in series:` loop and before `ax.set_ylabel(label)`:

```python
        row = 0
        for mk in markers or []:
            ax.axvline(mk.freq, color=PRINT_MARKER, linewidth=0.7, linestyle="--")
            y = mk.y_gain if key == "gain" else mk.y_phase
            if y is not None:
                ax.plot([mk.freq], [y], "D", color=PRINT_MARKER, markersize=4)
            if mk.label_on != key or not mk.text:
                continue
            # labels are staggered by rows so that neighbours do not sit on each other
            if y is None:
                ax.annotate(mk.text, xy=(mk.freq, 1.0), xycoords=("data", "axes fraction"),
                            xytext=(4, -4 - 9 * row), textcoords="offset points", va="top",
                            fontsize=7, color=PRINT_MARKER)
            else:
                ax.annotate(mk.text, xy=(mk.freq, y), xytext=(4, 4 + 9 * row), textcoords="offset points",
                            va="bottom", fontsize=7, color=PRINT_MARKER)
            row = (row + mk.text.count("\n") + 1) % 6
```

Update the module docstring's second paragraph to: `Gain and phase subplots matching the current view: wrap state, axis type, flagged points, markers. Title, plus a footer with the date and key settings.`

- [ ] **Step 4: `io/settings.py`**

Next to the other module constants (near `TOOLTIP_DELAY_MS`):

```python
MARKER_KINDS = ("cutoff", "peak", "notch", "margins")   # as markers.KINDS; a test keeps the two equal
```

In `AppSettings`, after `vertical_unit`:

```python
    markers: list = field(default_factory=list)     # the automatic markers switched on (MARKER_KINDS)
```

In `from_dict`, add a branch after the `dict` branch:

```python
            elif isinstance(default, list):
                setattr(s, key, list(v) if isinstance(v, list) else default)
```

and with the other clean-ups, before `return s`:

```python
        s.markers = [k for k in MARKER_KINDS if k in s.markers]
```

- [ ] **Step 5: `gui/bode_plot.py` and `gui/main_window.py`**

`bode_plot.py`: import `ImageMarker` next to `ImageSeries` (`from ..io.export_image import ImageMarker, ImageSeries`) and add after `export_series`:

```python
    def export_markers(self) -> list[ImageMarker]:
        """The markers as shown, for the image export."""
        return [ImageMarker(p.marker.freq, p.text, p.y_gain, p.y_phase, "phase" if p.marker.kind == "pm" else "gain")
                for p in self._placed if p.marker.found]
```

`main_window.py`, in `export`, pass them on:

```python
            out = export_image.write_image(path, self.result or SweepResult({}, [], {}), o, series, labels,
                                           markers=self.plot.export_markers())
```

In `_load_ui_state`, after `self.plot.set_unit(s.vertical_unit)`:

```python
        self.plot.set_marker_kinds(s.markers)
```

In `_save_ui_state`, after `s.vertical_unit = self.plot.unit()`:

```python
        s.markers = self.plot.marker_kinds()
```

- [ ] **Step 6: Run everything**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all passed, none skipped that ran before.

- [ ] **Step 7: Look at it once**

Render the simulated app offscreen with markers on and read the picture (not a test; a check that labels sit where a person expects them). Save this as a throwaway script in the session scratchpad, not in the project, and run it with `.venv\Scripts\python`:

```python
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
os.environ["BODEPLOT_NO_HARDWARE"] = "1"
os.environ["BODEPLOT_CONFIG_DIR"] = os.path.join(os.path.dirname(__file__), "cfg")
sys.path.insert(0, r"C:\Users\mazen\Desktop\bodeplotter\src")
from PySide6.QtWidgets import QApplication
from bodeplot.gui import theme
from bodeplot.gui.main_window import MainWindow
from bodeplot.io.settings import AppSettings
from bodeplot.measure.theory import TransferFunction

app = QApplication([])
theme.apply(app)
w = MainWindow(simulate=True, settings=AppSettings(simulate=True), sim_seed=7)
w.interactive = False
w.resize(1400, 850)
w.show()
bpf = w.traces.add_theory(TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9))
w.plot.traces_changed()
w.plot.set_marker_trace(bpf.id)
w.plot.set_marker_kinds(["cutoff", "peak"])
w.plot.add_marker(1000.0), w.plot.add_marker(100e3)
w.plot.toggle_reference_marker(1)
app.processEvents()
w.plot.fit_view()
app.processEvents()
w.grab().save(os.path.join(os.path.dirname(__file__), "markers.png"))
w.export(os.path.join(os.path.dirname(__file__), "markers_export.png"))
w.close()
```

Read both PNG files. Expected: fL, fH (with its BW / Q line) and pk on the band-pass, M1 "(ref)" and M2 with its Δ line, no label on top of another, nothing outside the plot area; the exported image shows the same markers in dark grey. If a label covers another or leaves the plot, fix `MarkerLayer.layout` (or the stagger in `write_image`) and add the case to `test_labels_do_not_overlap`.

- [ ] **Step 8: Commit**

```powershell
git add src/bodeplot/io/export_image.py src/bodeplot/io/settings.py src/bodeplot/gui/bode_plot.py src/bodeplot/gui/main_window.py tests/test_io.py tests/test_gui_traces.py tests/test_gui_markers.py
git commit -m "Markers in the exported image; the ticked automatic markers are remembered between runs"
```

---

### Task 7: Documents

**Files:**
- Modify: `docs/spec/gui.md`, `docs/SPEC.md`, `docs/spec/roadmap.md`, `docs/ARCHITECTURE.md`, `docs/STATE.md`, `README.md`, `docs/superpowers/specs/2026-10-07-auto-markers-design.md`

**Interfaces:** none.

- [ ] **Step 1: `docs/spec/gui.md`, section 10**

Add after the bullet **Traces** in "Dialogs":

```markdown
- **Markers** (v2, milestone A4; design `docs/superpowers/specs/2026-10-07-auto-markers-design.md`): a button "Markers" above the plot switches the automatic markers on one chosen trace ("Markers on", the live sweep by default): −3 dB (`fc`, or `fL` and `fH` with bandwidth and Q; 3 dB below the highest gain, the two crossings nearest to the maximum), peak `pk` and notch `nt` (refined between the points; only when not at an end of the trace and 1 dB clear of both ends), gain margin `GM` and phase margin `PM` (the trace taken as the loop gain: PM = 180° + phase at the 0 dB crossing, GM where the unwrapped phase passes −180°; the smallest when there are several; not in the relative display, not without phase). User markers `M1` to `M8` stand at any frequency (right-click > "Add marker here", drag, or right-click the marker > "Set frequency…"); one can be the reference marker, the others then show frequency ratio, Δ dB, Δ deg and dB/decade. Values between points are interpolated (gain in dB and unwrapped phase, linearly over log frequency); a gap is not bridged. Each marker is a dashed line through both plots, a dot on the curve and its text next to it; labels do not cover each other; "Fit view" ignores markers. The markers read the trace as drawn (also the difference curve of "Relative to"); with the unit Voltage the rules still work on the gain. "Copy marker values" puts a tab-separated table on the clipboard; the exported image shows the markers. The four ticks are stored in `settings.json` (`markers`); user markers and the chosen trace are not.
```

In section 11 (settings), where the stored fields are listed, add `markers` (the automatic markers switched on) next to the vertical unit. In section 12, image export bullet, add "markers" to the list "wrap state, axis type, flagged markers".

- [ ] **Step 2: `docs/SPEC.md` and `docs/spec/roadmap.md`**

`docs/SPEC.md`, the line that lists what is deferred to v2 ("Full probe/channel calibration over frequency, trace overlay, auto markers (v2, §15; in progress since 2026-10-06)"): change "in progress since 2026-10-06" to "built 2026-10-06 to 2026-10-07, awaiting the user's review of the markers".

`docs/spec/roadmap.md`: section 15, the bullet **Auto markers**, append: `**Built on 2026-10-07** (design `docs/superpowers/specs/2026-10-07-auto-markers-design.md`); awaits the user's review, which ends v2.` Section 16, row A4, first cell of "Content": prefix `**BUILT 2026-10-07, awaiting the user's review.**`.

- [ ] **Step 3: `docs/ARCHITECTURE.md`**

Add after the paragraph "**Traces on the plot** are outside that chain…":

```markdown
**Markers** are outside it too. `markers.py` holds what is switched on and the rules; `measure/response.py` is the maths on one curve, which `traces.py` also uses for the reference trace and which v3 (response metrics) is to build on. The plot asks `TraceSet.curve` for the chosen trace, lets `MarkerSet.evaluate` read it, and hands texts and positions to `gui/marker_layer.py` and to the image export.
```

Add to the table "Where each concern lives":

```markdown
| Markers (−3 dB, peak, notch, margins, user markers) | rules and texts in `markers.py`; curve maths in `measure/response.py`; the chosen trace as a curve in `traces.py` (`TraceSet.curve`); menu, texts in the plot's unit and positions in `gui/bode_plot.py`; graphics and label placement in `gui/marker_layer.py`; in an image in `io/export_image.py` |
```

- [ ] **Step 4: `docs/STATE.md`**

Replace the first bold paragraph under "Start here" by:

```markdown
**v1, milestone A1 (through calibration), A3 (traces on the plot) and A4 (markers) are built. A2 was PARKED by the user on 2026-10-07 (ignore it until the user brings it up). A4 awaits the user's review, which ends v2; after it comes v3, B1 response metrics (`docs/spec/roadmap.md` section 16), which starts with the brainstorming step.**
```

Add as the first numbered item of that list (renumber the rest):

```markdown
1. A4 was built on 2026-10-07 on the branch `a4-auto-markers` (design `docs/superpowers/specs/2026-10-07-auto-markers-design.md`, plan `docs/superpowers/plans/2026-10-07-auto-markers.md`). What the user decided: all four marker kinds; one chosen trace; −3 dB counted from the highest gain; values written on the plot, no panel; a "Markers" button next to Fit view; user markers at any frequency, interpolated; a reference marker with differences; markers in the exported image and as a copied table. Mine, listed in section 10 of the design and not objected to: the trace is taken as the loop gain (PM = 180° + phase; the user was asked about inverted-loop setups and did not answer: an "Inverted loop" tick is built only if asked for); in Voltage the rules work on the gain; peak / notch need 1 dB over both ends; only the two −3 dB crossings nearest the maximum; the smallest margin; at most 8 user markers; the ticks are remembered, the user markers are not. Checked in offscreen renders and tests only; the user has not seen it. No bench run was needed.
```

Add to "What exists":

```markdown
- Markers (v2, A4): `measure/response.py` (`Curve`, `crossings`, `extremum`), `markers.py` (`MarkerSet`, `Marker`, `label`, `table`), `TraceSet.curve`, `gui/marker_layer.py` (`MarkerLayer`), the Markers menu and `context_menu` in `gui/bode_plot.py`, `ImageMarker` in `io/export_image.py`, `AppSettings.markers`; tests in `tests/test_response.py`, `tests/test_markers.py`, `tests/test_gui_markers.py`.
```

Update the `pytest` count in the hand-over paragraph to the number the last full run printed.

- [ ] **Step 5: `README.md` and the design's status line**

`README.md`: in the features list add one line in the style of its neighbours: `Markers: −3 dB cut-off(s) with bandwidth and Q, peak, notch, gain and phase margin, and up to eight markers of your own with a reference marker; copied as a table and drawn in the exported image.` If the README has a status line naming the last finished milestone, name A4 there as built and awaiting review.

`docs/superpowers/specs/2026-10-07-auto-markers-design.md`, status line: `Status: **built on 2026-10-07 (plan `docs/superpowers/plans/2026-10-07-auto-markers.md`); awaits the user's review of the result.**` and add under it the three departures listed at the top of this plan.

- [ ] **Step 6: Guards and the whole suite**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all passed (`tests/test_docs.py` checks the index files, the section numbers and the module table).

- [ ] **Step 7: Commit**

```powershell
git add docs README.md
git commit -m "Documents: markers (A4) in the spec, the architecture map, the state and the README"
```

---

## After the last task

Hand over to the user for the review the roadmap asks for ("user's review; end of v2"): say what was built, what was checked only offscreen, the open question of the phase margin convention, and that the branch `a4-auto-markers` is not merged. Merge into `main` only on the user's word.
