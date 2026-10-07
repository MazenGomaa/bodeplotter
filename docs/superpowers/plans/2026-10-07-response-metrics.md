# Response Metrics and Analysis Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the shape of one trace (passband level and ripple, cut-offs, slope and order, stopband attenuation, every resonance with two Q values), show it in an Analysis tab next to a second trace, and make the −3 dB marker count from the passband level.

**Architecture:** A new pure module `measure/metrics.py` works on the existing `Curve` of `measure/response.py`. `analysis.py` (no Qt) turns its result into table rows, notes and clipboard text. `gui/analysis_panel.py` shows that table on a button press and says when it has gone stale. `markers.py` takes its −3 dB cut-offs from `metrics.passband`.

**Tech Stack:** Python 3.14, PySide6 6.11 (offscreen in tests), pytest with pytest-qt. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-07-response-metrics-design.md` (read it first; section numbers below are its sections).

**Where the code in this plan comes from.** Every file and every change below was written and run in a throw-away copy of the repository before this plan was written: the whole suite passed there (580 passed, the docs tests left out because the copy had no `docs/`), and the panel was rendered offscreen at 1280x720, 1536x864 and 2560x1440. So the "run, expect FAIL / PASS" lines state what was seen. If a step does not behave as written, stop and find out why; do not adjust a test to make it pass.

## Global Constraints

- Run everything from the project root in PowerShell with `.venv\Scripts\python`. No build step, no linter.
- Work on a branch `v3-response-metrics` cut from `main`; merge only after the user's review (Task 6).
- Nothing in this plan reaches an instrument. No bench run, no `hwcheck/` script, no SCPI. `BODEPLOT_NO_HARDWARE` stays set by `tests/conftest.py`.
- No `subprocess` in `src/` (a test enforces it). No new dependency in `requirements.txt`.
- `measure/metrics.py` and `analysis.py` import no Qt.
- Every colour comes from `gui/theme.py`. No hex colour and no colour name anywhere else.
- Every button, box and tick box has a tooltip of at least 25 characters that is not its label; a label carries the tooltip of its field (`tests/test_gui_tooltips.py`).
- Never connect `clicked` or `triggered` directly to a method with an optional argument: go through `lambda _checked=False: ...`.
- A panel's width must not depend on a trace's name or on its table's content: the window's smallest width stays 1221 px (it must fit a 1280 px screen).
- Thresholds are constants at the top of `measure/metrics.py`, with the values of spec section 6 item 1: 3 dB/decade, a third of a decade, five points, 3 dB, 10 dB, 1 dB, 8 times the scatter, half a decade, 2 dB/decade, 0.1 dB.
- A limit is written `≥ ` (U+2265 and a space). A number that rounds to zero is written `+0.00`, never `-0.00`.
- Commit after every task with the two trailer lines the session gives (Co-Authored-By, Claude-Session).
- `docs/ARCHITECTURE.md` lists every module and its imports, and `tests/test_docs.py` fails until it does. The docs are brought up to date in Task 6; until then run the suite with `--deselect tests/test_docs.py` where a step says so.

## Review Focus

Inputs the spec implies and a user will meet; each has its test in the task that owns the code:

1. **A sweep that starts close to the cut-off** (less than a decade of passband): the level reads low and the cut-off high. Expected: the numbers are still given, with a note that says to start the sweep lower. Test: `test_notes` in Task 4.
2. **Sweeps that are not 20 points per decade on a log axis** (linear sweeps, 1 to 5 points per decade, files with repeated frequencies, dead points): Expected: no exception, every number finite or absent. Tests: `test_odd_curves_break_nothing`, `test_a_linear_sweep_of_the_rc_still_finds_its_cutoff`, `test_a_gap_is_not_bridged` in Task 2.
3. **The analysed trace changes under the table** (a sweep is running, the trace is removed, the compared trace is removed): Expected: the table stays, the state line warns, the boxes fall back to the live sweep and "off" is kept only when "off" was chosen. Tests: `test_the_table_stays_and_says_when_the_trace_has_changed`, `test_a_removed_trace_makes_the_table_old_and_the_boxes_fall_back` in Task 5.
4. **A magnitude-only measurement**: Expected: no "Q (phase)" row, nothing else changes. Tests: `test_without_phase_there_is_no_q_from_the_phase` in Task 2, `test_a_band_pass_shows_its_resonance` in Task 5.
5. **Two traces of different kinds compared** (a low-pass against a band-pass, a trace against itself, an empty trace): Expected: every quantity keeps its row with the missing cell empty; a trace against itself is shown alone; an empty trace says "no points". Tests: `test_a_quantity_only_one_trace_has_keeps_its_row` in Task 4, `test_a_trace_compared_with_itself_is_shown_alone`, `test_an_empty_trace_says_so` in Task 5.

## File Structure

| File | New / changed | Responsibility |
|---|---|---|
| `src/bodeplot/measure/response.py` | changed | `refine(c, i, highest)`: the parabola of `extremum` for any point |
| `src/bodeplot/measure/metrics.py` | new | the maths of spec section 3: `passband`, `marker_pair`, `ends_extreme`, `analyse` |
| `src/bodeplot/markers.py` | changed | `_cutoffs` takes level and frequencies from `metrics.passband` |
| `src/bodeplot/analysis.py` | new | table rows, difference, notes, clipboard text; no Qt |
| `src/bodeplot/gui/analysis_panel.py` | new | the Analysis dock's widget |
| `src/bodeplot/gui/bode_plot.py` | changed | `analysis_curve(trace_id)`; the tooltip of the −3 dB tick |
| `src/bodeplot/gui/main_window.py` | changed | the dock, the View menu, `LAYOUT_VERSION = 3` |
| `src/bodeplot/io/settings.py`, `src/bodeplot/gui/dialogs.py` | changed | `dock_analysis` in `PANELS` and in the Settings dialog's list |
| `tests/test_metrics.py`, `tests/test_analysis.py`, `tests/test_gui_analysis.py` | new | |
| `tests/test_response.py`, `tests/test_markers.py`, `tests/test_gui_markers.py`, `tests/test_gui_markers_panel.py`, `tests/test_settings_more.py`, `tests/test_gui_tooltips.py` | changed | new tests, and the existing ones the marker rule and the new dock move |
| `docs/ARCHITECTURE.md`, `docs/spec/gui.md`, `docs/spec/roadmap.md`, `README.md`, `docs/STATE.md`, the spec | changed | Task 6 |

---

### Task 1: `response.refine`

**Files:**
- Modify: `src/bodeplot/measure/response.py` (the function `extremum`, at the end of the file)
- Test: `tests/test_response.py`

**Interfaces:**
- Consumes: `Curve` (fields `f`, `db`, `deg`, `ok`, `flagged`), `Extremum(f, db, index, interior)`.
- Produces: `refine(c: Curve, i: int, highest: bool = True) -> tuple[float, float]` (frequency, gain in dB). `extremum` keeps its signature and its results.

- [ ] **Step 1: Cut the branch**

```powershell
git checkout -b v3-response-metrics
```

- [ ] **Step 2: Write the failing test**

Apply to `tests/test_response.py` (the import line, and one test appended at the end):

```diff
--- a/tests/test_response.py
+++ b/tests/test_response.py
@@ -4,7 +4,7 @@
 
 import pytest
 
-from bodeplot.measure.response import Curve, crossings, curve, extremum
+from bodeplot.measure.response import Curve, crossings, curve, extremum, refine
 from bodeplot.measure.theory import TransferFunction
 
 RC = TransferFunction.rc_lpf(1e3, 100e-9)
@@ -100,3 +100,20 @@
     assert flat.db == 0.0 and not flat.interior                 # the first of equal points
     beside_gap = extremum(by_hand([1.0, 10.0, 100.0, 1000.0], [0.0, 5.0, 0.0, 0.0], ok=[True, True, False, True]))
     assert beside_gap.f == 10.0 and beside_gap.db == 5.0        # no parabola across a gap
+
+
+def test_refine_works_on_any_point_and_extremum_uses_it():
+    c = of(BPF)
+    e = extremum(c)
+    assert refine(c, e.index) == (e.f, e.db)                    # the highest point: the same answer
+    f, db = refine(c, e.index)
+    assert c.f[e.index - 1] < f < c.f[e.index + 1] and db >= c.db[e.index]
+    assert refine(c, 0) == (c.f[0], c.db[0])                    # an end has one neighbour only: the point itself
+    assert refine(c, len(c.f) - 1) == (c.f[-1], c.db[-1])
+    rising = e.index - 10                                       # on the flank the parabola opens the wrong way or peaks outside
+    assert refine(c, rising) == (c.f[rising], c.db[rising])
+    gap = by_hand([1.0, 10.0, 100.0], [0.0, 3.0, 0.0], ok=[False, True, True])
+    assert refine(gap, 1) == (10.0, 3.0)                        # a dead neighbour: no parabola
+    notch = of(TransferFunction.rlc_notch(100.0, 1e-3, 100e-9))
+    low = extremum(notch, highest=False)
+    assert refine(notch, low.index, highest=False) == (low.f, low.db)
```

- [ ] **Step 3: Run it and see it fail**

Run: `.venv\Scripts\python -m pytest tests\test_response.py -q`
Expected: an error while collecting, `ImportError: cannot import name 'refine' from 'bodeplot.measure.response'`.

- [ ] **Step 4: Implement**

Apply to `src/bodeplot/measure/response.py`: the body of `extremum` moves into a new function `refine` above it.

```diff
--- a/src/bodeplot/measure/response.py
+++ b/src/bodeplot/measure/response.py
@@ -132,14 +132,10 @@
     interior: bool              # not the first or the last usable point
 
 
-def extremum(c: Curve, highest: bool = True) -> Extremum | None:
-    """The highest (or lowest) gain of the curve. Its position is refined with a parabola
-    through the extreme point and its two neighbours (dB over log frequency) when both
-    exist with no gap between the three."""
-    idx = c.usable()
-    if not idx:
-        return None
-    i = (max if highest else min)(idx, key=lambda k: c.db[k])
+def refine(c: Curve, i: int, highest: bool = True) -> tuple[float, float]:
+    """(frequency, gain in dB) of the extreme at point i, refined with a parabola through the
+    point and its two neighbours (dB over log frequency). The point itself when a neighbour
+    is missing or dead, or when the parabola does not open the right way."""
     f, db = c.f[i], c.db[i]
     if 0 < i < len(c.f) - 1 and c.ok[i - 1] and c.ok[i + 1] and c.f[i - 1] < c.f[i] < c.f[i + 1]:
         x0, x1, x2 = (math.log10(c.f[k]) for k in (i - 1, i, i + 1))
@@ -151,4 +147,15 @@
             xv = -b / (2 * a)
             if x0 < xv < x2:
                 f, db = 10.0 ** xv, y1 + a * (xv * xv - x1 * x1) + b * (xv - x1)
+    return f, db
+
+
+def extremum(c: Curve, highest: bool = True) -> Extremum | None:
+    """The highest (or lowest) gain of the curve, its position refined between the points
+    (refine)."""
+    idx = c.usable()
+    if not idx:
+        return None
+    i = (max if highest else min)(idx, key=lambda k: c.db[k])
+    f, db = refine(c, i, highest)
     return Extremum(f, db, i, idx[0] < i < idx[-1])
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests\test_response.py tests\test_markers.py -q`
Expected: all pass (the markers use `extremum`; nothing may move).

- [ ] **Step 6: Commit**

```powershell
git add src/bodeplot/measure/response.py tests/test_response.py
git commit -m "response.refine: the parabola of extremum for any point of a curve"
```

---

### Task 2: `measure/metrics.py`

**Files:**
- Create: `src/bodeplot/measure/metrics.py`
- Test: `tests/test_metrics.py` (new)

**Interfaces:**
- Consumes: `Curve`, `Extremum`, `extremum`, `refine` from `measure/response.py`.
- Produces (used by Tasks 3, 4, 5 and by parts 2 and 3 of v3):
  - constants `DROP_DB = 3.0`, `PROMINENCE_DB = 1.0`, `FEW_POINTS = 5`, `MIN_POINTS = 5`, `TOO_FEW = "fewer than 5 usable points"`
  - `Value(v: float, limit: bool = False, flagged: bool = False)`
  - `Band(first, last, lo, hi, level, spread, kind, at_low, at_high, flagged)` with `kind` in `"pass" | "floor" | "flat"`
  - `Cutoff(f, side, inner, outer, band=-1, flagged=False, slope: Value | None, order: Value | None, attenuation: Value | None, falling: bool)` with `side` in `"low" | "high"` ("high": the passband lies below the cut-off)
  - `Resonance(kind, index, f0, db, height, q_width: float | None, q_phase: float | None, points: int, flagged: bool)` with `kind` in `"peak" | "notch"`
  - `Passband(level: float | None, source: str, bands, cutoffs, top: Extremum | None, slopes)` with `source` in `"flat" | "peak" | ""`
  - `Metrics(ok, reason, points, flagged_share, level, source, level_flagged, ripple: float | None, bands, cutoffs, pair: tuple[Cutoff, Cutoff] | None, centre, bandwidth, q, resonances)`
  - `passband(c: Curve) -> Passband`
  - `marker_pair(p: Passband) -> list[Cutoff]` (0, 1 or 2 cut-offs, ascending)
  - `ends_extreme(c: Curve, highest: bool) -> tuple[Extremum | None, bool]` (the rule of the peak and notch markers, moved here from `markers._peak`)
  - `analyse(c: Curve, phase: bool = True) -> Metrics`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_metrics.py`:

```python
"""Response metrics (measure/metrics.py): what the shape of a curve says, against theory.

Design: docs/superpowers/specs/2026-10-07-response-metrics-design.md, section 3."""
import cmath
import math
import random
import time

import numpy as np
import pytest

from bodeplot.measure.metrics import FEW_POINTS, TOO_FEW, analyse, marker_pair, passband
from bodeplot.measure.response import Curve, curve
from bodeplot.measure.theory import TransferFunction as TF


def grid(lo=50.0, hi=2e7, ppd=20):
    n = int(round(math.log10(hi / lo) * ppd)) + 1
    return [lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]


def of(tf, freqs=None, db=0.0, deg=0.0, seed=1, flagged=None):
    """The curve of a transfer function, with Gaussian noise of db (dB) and deg (degrees)."""
    rnd = random.Random(seed)
    freqs = freqs or grid()
    hs = [tf.h(f) * cmath.rect(10 ** (rnd.gauss(0, db) / 20), math.radians(rnd.gauss(0, deg))) for f in freqs]
    return curve(freqs, hs, [flagged(f) for f in freqs] if flagged else None)


def by_hand(f, db):
    n = len(f)
    return Curve(list(f), list(db), [0.0] * n, [True] * n, [False] * n)


def w(f):
    return 2 * math.pi * f


def poly(*factors):
    out = [1.0]
    for p in factors:
        out = np.polymul(out, p)
    return list(out)


def bp2(f0, q):
    """Second-order band-pass, 0 dB at f0: (numerator, denominator)."""
    return [w(f0) / q, 0.0], [1.0, w(f0) / q, w(f0) ** 2]


def butter(order, fc):
    poles = [w(fc) * cmath.exp(1j * math.pi * (2 * k + order - 1) / (2 * order)) for k in range(1, order + 1)]
    den = np.real(np.poly(poles))
    return TF.custom([den[-1]], den)


def cheby(order, ripple_db, fc):
    eps = math.sqrt(10 ** (ripple_db / 10) - 1)
    a = math.asinh(1 / eps) / order
    poles = [complex(-math.sinh(a) * math.sin((2 * k - 1) * math.pi / (2 * order)),
                     math.cosh(a) * math.cos((2 * k - 1) * math.pi / (2 * order))) * w(fc)
             for k in range(1, order + 1)]
    den = np.real(np.poly(poles))
    return TF.custom([den[-1] if order % 2 else den[-1] / math.sqrt(1 + eps * eps)], den)


FC = 1 / (2 * math.pi * 1e3 * 100e-9)                       # 1.592 kHz
F0 = 1 / (2 * math.pi * math.sqrt(1e-3 * 100e-9))           # 15.92 kHz, Q = 1
RC = TF.rc_lpf(1e3, 100e-9)
HPF = TF.rc_hpf(1e3, 100e-9)
BPF = TF.rlc_bpf(100.0, 1e-3, 100e-9)
NOTCH = TF.rlc_notch(100.0, 1e-3, 100e-9)
HUMP = TF.custom([w(10e3) ** 2], [1.0, w(10e3) / 2.0, w(10e3) ** 2])       # second-order low-pass, Q = 2
WIDE = TF.custom(poly([1 / w(100.0), 0.0]), poly([1 / w(100.0), 1.0], [1 / w(100e3), 1.0]))    # 100 Hz .. 100 kHz
AMP = TF.custom([10.0], [1 / w(50e3), 1.0])                 # 20 dB, one pole at 50 kHz
# two band-passes side by side: resonances at 10 kHz (Q 10) and 300 kHz (Q 20)
TWO = TF.custom(np.polyadd(poly(bp2(1e4, 10)[0], bp2(3e5, 20)[1]), poly(bp2(3e5, 20)[0], bp2(1e4, 10)[1])),
                poly(bp2(1e4, 10)[1], bp2(3e5, 20)[1]))
# a crystal between two resistors: series resonance (a peak) at 1 MHz, parallel resonance (a notch) at 1.05 MHz
CRYSTAL = TF.custom(poly([1.0, w(1.05e6) / 100, w(1.05e6) ** 2]), poly([1.0, w(1.0e6) / 100, w(1.0e6) ** 2]))


# ---------------------------------------------------------------------- flat stretches and cut-offs
def test_a_wire_is_one_passband_and_nothing_else():
    m = analyse(of(TF.through()))
    assert m.ok and m.source == "flat" and m.level == pytest.approx(0.0, abs=1e-6)
    assert [(b.kind, b.at_low, b.at_high) for b in m.bands] == [("pass", True, True)]
    assert m.cutoffs == [] and m.resonances == [] and m.ripple == pytest.approx(0.0, abs=1e-6)


def test_rc_low_pass():
    m = analyse(of(RC))
    assert m.source == "flat" and m.level == pytest.approx(0.0, abs=0.05)
    assert len(m.bands) == 1 and m.bands[0].at_low and not m.bands[0].at_high
    (cut,) = m.cutoffs
    assert cut.side == "high" and cut.f == pytest.approx(FC, rel=0.02)
    assert cut.slope.v == pytest.approx(-20.0, abs=0.5) and not cut.slope.limit
    assert cut.order.v == 1 and not cut.order.limit
    assert cut.attenuation.limit and cut.falling and cut.attenuation.v > 60.0      # no floor inside the sweep
    assert m.resonances == [] and m.ripple < 0.05 and m.pair is None and m.q is None


def test_rc_high_pass():
    m = analyse(of(HPF))
    (cut,) = m.cutoffs
    assert cut.side == "low" and cut.f == pytest.approx(FC, rel=0.02)
    assert cut.slope.v == pytest.approx(20.0, abs=1.5) and cut.order.v == 1
    assert m.bands[0].at_high and m.resonances == []


@pytest.mark.parametrize("tf, order", [(TF.butter2_lpf(10e3), 2), (butter(5, 10e3), 5)])
def test_butterworth_cutoff_and_order(tf, order):
    (cut,) = analyse(of(tf)).cutoffs
    assert cut.f == pytest.approx(10e3, rel=0.01)
    assert cut.slope.v == pytest.approx(-20.0 * order, abs=1.0) and cut.order.v == order and not cut.order.limit


def test_the_cutoff_counts_from_the_flat_level_not_from_a_hump():
    m = analyse(of(HUMP))
    assert m.source == "flat" and m.level == pytest.approx(0.0, abs=0.05)
    (cut,) = m.cutoffs
    x2 = (1.75 + math.sqrt(1.75 ** 2 + 4)) / 2                  # |H|^2 = 1/2 of the Q = 2 low-pass
    assert cut.f == pytest.approx(10e3 * math.sqrt(x2), rel=0.01) and cut.order.v == 2
    (peak,) = m.resonances
    assert peak.kind == "peak" and peak.f0 == pytest.approx(10e3 * math.sqrt(1 - 1 / 8), rel=0.02)
    assert peak.height == pytest.approx(20 * math.log10(2 / math.sqrt(1 - 1 / 16)), abs=0.2)
    assert peak.q_phase == pytest.approx(2.0, rel=0.1)
    assert m.ripple == pytest.approx(peak.height, abs=0.2)     # the hump is what the passband varies by


def test_chebyshev_ripple_and_order():
    m = analyse(of(cheby(5, 1.0, 10e3)))
    assert m.level == pytest.approx(0.0, abs=0.05) and m.ripple == pytest.approx(1.0, abs=0.05)
    (cut,) = m.cutoffs
    f3 = 10e3 * math.cosh(math.acosh(1 / math.sqrt(10 ** 0.1 - 1)) / 5)        # its -3 dB frequency
    assert cut.f == pytest.approx(f3, rel=0.02) and cut.order.v == 5            # not 7: the settled slope, not the steepest
    even = analyse(of(cheby(4, 1.0, 10e3)))
    assert even.level == pytest.approx(-1.0, abs=0.05) and even.ripple == pytest.approx(1.0, abs=0.05)
    assert even.cutoffs[0].order.v == 4


def test_a_wide_band_pass_has_a_flat_top_two_cutoffs_and_no_resonance():
    m = analyse(of(WIDE))
    assert m.source == "flat" and [c.side for c in m.cutoffs] == ["low", "high"]
    assert m.cutoffs[0].f == pytest.approx(100.0, rel=0.02) and m.cutoffs[1].f == pytest.approx(100e3, rel=0.02)
    assert m.resonances == []                                   # the top of a flat stretch is no peak
    assert m.centre == pytest.approx(math.sqrt(100.0 * 100e3), rel=0.02)
    assert m.bandwidth == pytest.approx(100e3 - 100.0, rel=0.02) and m.q == pytest.approx(0.0316, rel=0.03)
    assert m.cutoffs[0].slope.limit                             # half a decade of sweep below 100 Hz is not there


def test_an_amplifier_gets_its_gain_and_its_bandwidth():
    m = analyse(of(AMP))
    assert m.level == pytest.approx(20.0, abs=0.05)
    assert m.cutoffs[0].f == pytest.approx(50e3, rel=0.02) and m.cutoffs[0].order.v == 1


# ---------------------------------------------------------------------- resonances
def test_rlc_band_pass_is_a_peak_with_both_q():
    m = analyse(of(BPF))
    assert m.source == "peak" and m.bands == [] and m.ripple is None
    assert m.level == pytest.approx(0.0, abs=0.05)
    assert [c.side for c in m.cutoffs] == ["low", "high"] and [c.order.v for c in m.cutoffs] == [1, 1]
    assert m.centre == pytest.approx(F0, rel=0.01) and m.q == pytest.approx(1.0, rel=0.03)
    (peak,) = m.resonances
    assert peak.kind == "peak" and peak.f0 == pytest.approx(F0, rel=0.01)
    assert peak.q_width == pytest.approx(1.0, rel=0.03) and peak.q_phase == pytest.approx(1.0, rel=0.1)
    assert peak.points >= FEW_POINTS


def test_rlc_notch_has_two_passbands_a_notch_and_no_slope():
    m = analyse(of(NOTCH))
    assert [b.kind for b in m.bands] == ["pass", "pass"]
    assert [c.side for c in m.cutoffs] == ["high", "low"]
    assert all(c.slope is None and c.order is None for c in m.cutoffs)      # into a notch there is no order
    assert all(c.attenuation.limit and not c.falling for c in m.cutoffs)
    (notch,) = m.resonances
    assert notch.kind == "notch" and notch.f0 == pytest.approx(F0, rel=0.01) and notch.height > 30.0
    assert notch.q_width == pytest.approx(1.0, rel=0.05) and notch.q_phase is None
    assert m.q == pytest.approx(1.0, rel=0.05)


@pytest.mark.parametrize("q", [1.0, 10.0, 50.0])
def test_q_from_the_phase_agrees_with_q_from_the_width(q):
    (peak,) = analyse(of(TF.custom(*bp2(1e4, q)), grid(1e2, 1e6, 400))).resonances
    assert peak.q_width == pytest.approx(q, rel=0.1) and peak.q_phase == pytest.approx(q, rel=0.1)
    assert peak.q_phase == pytest.approx(peak.q_width, rel=0.1)


def test_every_resonance_gets_a_row():
    m = analyse(of(TWO, grid(ppd=200)))
    assert [r.kind for r in m.resonances] == ["peak", "notch", "peak"]     # the valley between two peaks is a notch
    first, _valley, second = m.resonances
    assert first.f0 == pytest.approx(1e4, rel=0.01) and second.f0 == pytest.approx(3e5, rel=0.01)
    assert first.q_width == pytest.approx(10.0, rel=0.05) and second.q_width == pytest.approx(20.0, rel=0.05)
    assert first.q_phase == pytest.approx(10.0, rel=0.05) and second.q_phase == pytest.approx(20.0, rel=0.05)


def test_a_crystal_shows_its_series_and_its_parallel_resonance():
    m = analyse(of(CRYSTAL, grid(2e5, 5e6, 1000)))
    peak, notch = m.resonances
    assert (peak.kind, notch.kind) == ("peak", "notch")
    assert peak.f0 == pytest.approx(1.0e6, rel=0.01) and notch.f0 == pytest.approx(1.05e6, rel=0.01)
    assert peak.q_width == pytest.approx(100.0, rel=0.1) and peak.q_phase == pytest.approx(100.0, rel=0.1)


def test_a_resonance_with_too_few_points_says_so():
    (peak,) = analyse(of(TF.custom(*bp2(1e4, 50)))).resonances          # 20 points per decade on a Q of 50
    assert peak.points < FEW_POINTS and peak.f0 == pytest.approx(1e4, rel=0.03)


def test_without_phase_there_is_no_q_from_the_phase():
    (peak,) = analyse(of(BPF), phase=False).resonances
    assert peak.q_phase is None and peak.q_width == pytest.approx(1.0, rel=0.03)


# ---------------------------------------------------------------------- how far a number holds
def test_a_sweep_that_ends_early_gives_limits():
    (cut,) = analyse(of(TF.butter2_lpf(10e3), grid(50.0, 3e4))).cutoffs
    assert cut.f == pytest.approx(10e3, rel=0.01)
    assert cut.slope.limit and cut.order.limit and cut.order.v >= 1
    assert cut.attenuation.limit and cut.falling


def test_a_floor_gives_the_attenuation_as_a_number():
    floor = TF.custom(poly([1 / w(1e6), 1.0]), poly([1 / w(1e3), 1.0]))        # falls from 1 kHz, level again at -60 dB
    m = analyse(of(floor))
    assert [b.kind for b in m.bands] == ["pass", "floor"]
    (cut,) = m.cutoffs
    assert cut.attenuation.v == pytest.approx(60.0, abs=0.5) and not cut.attenuation.limit and not cut.falling
    assert cut.order.v == 1 and not cut.order.limit


def test_flagged_points_mark_the_numbers_that_rest_on_them():
    m = analyse(of(RC, flagged=lambda f: 1000.0 < f < 2000.0))
    assert m.cutoffs[0].flagged and not m.level_flagged and not m.bands[0].flagged
    assert m.flagged_share == pytest.approx(6 / 113, abs=0.01)
    m = analyse(of(RC, flagged=lambda f: f < 100.0))
    assert m.level_flagged and m.bands[0].flagged and not m.cutoffs[0].flagged
    m = analyse(of(BPF, flagged=lambda f: 15e3 < f < 17e3))
    assert m.resonances[0].flagged and m.level_flagged


def test_a_gap_is_not_bridged():
    freqs = grid()
    hs = [RC.h(f) for f in freqs]
    hs[10] = 0j                                                 # a dead point inside the passband
    m = analyse(curve(freqs, hs))
    assert m.ok and m.cutoffs[0].f == pytest.approx(FC, rel=0.02)
    hs = [RC.h(f) for f in freqs]
    for i, f in enumerate(freqs):
        if 1400.0 < f < 1800.0:
            hs[i] = complex("nan")                              # the cut-off lies in the gap
    m = analyse(curve(freqs, hs))
    assert m.ok and m.cutoffs == []


def test_too_few_points_give_no_analysis():
    for freqs in ([], [100.0, 1e3, 1e4, 1e5]):
        m = analyse(of(RC, freqs) if freqs else curve([], []))
        assert not m.ok and m.reason == TOO_FEW and m.cutoffs == [] and m.resonances == []
    assert passband(curve([], [])).level is None and marker_pair(passband(curve([], []))) == []


# ---------------------------------------------------------------------- noise
@pytest.mark.parametrize("db, tol", [(0.02, 0.02), (0.2, 0.12)])
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_noise_moves_the_numbers_little_and_invents_nothing(db, tol, seed):
    m = analyse(of(RC, db=db, deg=5 * db, seed=seed))
    assert m.source == "flat" and len(m.cutoffs) == 1 and m.resonances == []
    assert m.cutoffs[0].f == pytest.approx(FC, rel=tol) and m.cutoffs[0].order.v == 1
    m = analyse(of(BPF, db=db, deg=5 * db, seed=seed))
    assert m.source == "peak" and [r.kind for r in m.resonances] == ["peak"]
    assert m.resonances[0].f0 == pytest.approx(F0, rel=tol)
    m = analyse(of(NOTCH, db=db, deg=5 * db, seed=seed))
    assert [r.kind for r in m.resonances] == ["notch"] and len(m.cutoffs) == 2
    assert analyse(of(TF.through(), db=db, seed=seed)).resonances == []


# ---------------------------------------------------------------------- the marker's pair
def test_of_many_cutoffs_the_marker_takes_the_two_around_the_highest_gain():
    f = grid(10.0, 1e6, 20)
    db = []
    for x in f:                                                 # flat, a dip to -10 dB, flat a little higher, then falling
        if x < 300:
            db.append(0.0)
        elif x < 3e3:
            db.append(-10.0 * math.sin(math.pi * math.log10(x / 300)))
        elif x < 1e5:
            db.append(0.2)
        else:
            db.append(0.2 - 40.0 * math.log10(x / 1e5))
    p = passband(by_hand(f, db))
    assert [c.side for c in p.cutoffs] == ["high", "low", "high"]
    lo, hi = marker_pair(p)
    assert (lo.side, hi.side) == ("low", "high") and 300 < lo.f < 3e3 and hi.f == pytest.approx(1.19e5, rel=0.03)
    assert lo.band == hi.band != p.cutoffs[0].band              # both bound the second flat stretch
    m = analyse(by_hand(f, db))
    assert (m.pair[0].f, m.pair[1].f) == (lo.f, hi.f)
    assert m.ripple < 0.05                                      # each passband out to its own cut-offs: the dip is not ripple


# ---------------------------------------------------------------------- odd input, and time
def test_odd_curves_break_nothing():
    """Linear sweeps, a few points per decade, repeated frequencies, dead points, heavy noise:
    whatever comes out is a finite number or nothing."""
    rnd = random.Random(5)
    shapes = [RC, HPF, BPF, NOTCH, HUMP, WIDE, AMP, TWO, CRYSTAL, TF.through()]
    for trial in range(400):
        tf = rnd.choice(shapes)
        kind = rnd.choice(["log", "linear", "sparse", "repeated", "dead"])
        if kind == "linear":
            hi = rnd.choice([1e4, 1e6, 2e7])
            freqs = [100.0 + (hi - 100.0) * i / 100 for i in range(101)]
        elif kind == "sparse":
            freqs = grid(rnd.choice([50.0, 1e3]), rnd.choice([1e4, 2e7]), rnd.choice([1, 2, 3, 5]))
        else:
            freqs = grid(ppd=rnd.choice([5, 10, 20, 50]))
        hs = [tf.h(f) * 10 ** (rnd.gauss(0, rnd.choice([0.0, 0.02, 1.0])) / 20) for f in freqs]
        if kind == "repeated":
            for _ in range(5):
                k = rnd.randrange(len(freqs))
                freqs.insert(k, freqs[k])
                hs.insert(k, hs[k] * 1.01)
        if kind == "dead":
            for _ in range(rnd.randrange(1, 8)):
                hs[rnd.randrange(len(hs))] = rnd.choice([0j, complex("nan")])
        c = curve(freqs, hs, [rnd.random() < 0.1 for _ in freqs])
        m = analyse(c, phase=rnd.random() < 0.8)
        marker_pair(passband(c))
        for cut in m.cutoffs:
            assert math.isfinite(cut.f) and cut.f > 0, (trial, kind)
            assert all(v is None or math.isfinite(v.v) for v in (cut.slope, cut.order, cut.attenuation)), (trial, kind)
        for r in m.resonances:
            assert math.isfinite(r.f0) and math.isfinite(r.db) and r.points >= 1, (trial, kind)
            assert r.q_width is None or (math.isfinite(r.q_width) and r.q_width > 0), (trial, kind)
            assert r.q_phase is None or (math.isfinite(r.q_phase) and r.q_phase > 0), (trial, kind)
        assert m.q is None or (math.isfinite(m.q) and m.q > 0), (trial, kind)


def test_a_linear_sweep_of_the_rc_still_finds_its_cutoff():
    m = analyse(of(RC, [100.0 + (2e4 - 100.0) * i / 200 for i in range(201)]))
    assert m.cutoffs[0].f == pytest.approx(FC, rel=0.05) and m.cutoffs[0].order.v == 1


def test_five_hundred_points_are_analysed_in_well_under_half_a_second():
    c = of(TWO, grid(ppd=90))
    assert len(c.f) >= 500
    start = time.perf_counter()
    analyse(c)
    assert time.perf_counter() - start < 0.5
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_metrics.py -q`
Expected: an error while collecting, `ModuleNotFoundError: No module named 'bodeplot.measure.metrics'`.

- [ ] **Step 3: Implement**

Create `src/bodeplot/measure/metrics.py`:

```python
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
TROUGH_DB = 0.1             # a dip inside the passband counts for the ripple from this depth
SLOPE_WINDOW = 0.5          # decades of the window that measures a roll-off
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


def _window(x, a: int, b: int, i: int, width: float) -> tuple[int, int]:
    """The points of the run a..b inside a window of that width around point i; at an end of
    the run the window is moved inwards, not cut."""
    if x[b] - x[a] <= width:
        return a, b
    centre = min(max(x[i], x[a] + width / 2), x[b] - width / 2)
    j0 = bisect.bisect_left(x, centre - width / 2 - EPS, a, b + 1)
    j1 = bisect.bisect_right(x, centre + width / 2 + EPS, a, b + 1) - 1
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
    for a, b in segments(c):
        for i in range(a, b + 1):
            j0, j1 = _window(x, a, b, i, FLAT_WINDOW)
            if j1 - j0 < 2:
                j0, j1 = max(a, i - 1), min(b, i + 1)
            if j1 - j0 >= 2:
                out[i] = line_slope(x[j0:j1 + 1], c.db[j0:j1 + 1])
    return out


def _scatter(c: Curve, x, a: int, b: int, i: int) -> float:
    """The scatter of the gain around point i, from the second differences of its neighbourhood."""
    j0, j1 = _window(x, a, b, i, NOISE_WINDOW)
    d2 = [abs(c.db[j - 1] - 2 * c.db[j] + c.db[j + 1]) for j in range(max(j0, a + 1), min(j1, b - 1) + 1)]
    return 1.4826 * statistics.median(d2) / math.sqrt(6.0) if d2 else 0.0


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
        out.append(Band(a, b, c.f[a], c.f[b], statistics.median(c.db[i] for i in calm), max(vals) - min(vals),
                        "flat", a == idx[0], b == idx[-1], any(c.flagged[a:b + 1])))
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
def _extremes(c: Curve, x, a: int, b: int, highest: bool, floor: float = PROMINENCE_DB):
    """The peaks (highest) or notches of the run a..b that stand clear: (index, how far it
    stands clear, the foot on its left, the foot on its right; a foot is a gain in dB)."""
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
        if clear >= max(floor, NOISE_FACTOR * _scatter(c, x, a, b, i)):
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


def _resonances(c: Curve, x, phase: bool, bands: list[Band]) -> list[Resonance]:
    out = []
    flat = {i for band in bands for i in range(band.first, band.last + 1)}
    for a, b in segments(c):
        for highest in (True, False):
            for i, clear, left, right in _extremes(c, x, a, b, highest):
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
    if span < SLOPE_WINDOW - EPS:
        slopes.append(line_slope(x[lo:hi + 1], c.db[lo:hi + 1]))
    else:
        for s in idx:
            e = bisect.bisect_right(x, x[s] + SLOPE_WINDOW + EPS, lo, hi + 1) - 1
            if x[e] - x[s] < SLOPE_WINDOW - 2 * (x[e] - x[e - 1] if e > s else 0.0) - EPS:
                break                                   # what is left of the roll-off is shorter than a window
            if e - s >= 2:
                slopes.append(line_slope(x[s:e + 1], c.db[s:e + 1]))
    slopes = [v for v in slopes if v is not None]
    if not slopes:
        return
    at_notch = bool(beyond) and stop in [r.index for r in resonances if r.kind == "notch"]
    if not at_notch:                                    # into a notch the curve has no slope that means an order
        settled = statistics.median(slopes)             # the slope the roll-off settles to
        last = slopes[-1] if step > 0 else slopes[0]    # the window farthest from the passband
        limit = span < SLOPE_WINDOW - EPS or (at_end and sign * last - sign * settled > STEEPENING)
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
    x = _logs(c)
    p = passband(c)
    m.level, m.source, m.bands, m.cutoffs = p.level, p.source, p.bands, p.cutoffs
    m.resonances = _resonances(c, x, phase, m.bands)
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
    pair = marker_pair(p)
    if len(pair) == 2 and pair[1].f > pair[0].f:
        lo, hi = pair
        m.pair = (lo, hi)
        m.centre, m.bandwidth = math.sqrt(lo.f * hi.f), hi.f - lo.f
        m.q = m.centre / m.bandwidth
    return m
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests\test_metrics.py -q`
Expected: 37 passed, in a few seconds.

What the numbers looked like in the prototype, to recognise a slip: RC low-pass from 50 Hz at 20 points per decade: level −0.008 dB, fc 1590.1 Hz (theory 1591.5), slope −20.00, order 1. RLC band-pass Q = 1: source "peak", Q (width) 1.00, Q (phase) 1.00, 9 points. Second-order low-pass with Q = 2: level +0.000, fc 14.85 kHz, peak at 9.27 kHz, height 6.18 dB, Q (phase) 1.92. Fifth-order Chebyshev 1 dB: ripple 0.998 dB, slope −100.0, order 5. With 0.02 dB of noise, 200 seeds: no wrong resonance count, no lost passband, fc spread 0.47 %.

- [ ] **Step 5: Commit**

```powershell
git add src/bodeplot/measure/metrics.py tests/test_metrics.py
git commit -m "measure/metrics.py: passband level and ripple, cut-offs, slope and order, attenuation, resonances with Q from width and phase"
```

---

### Task 3: the −3 dB marker counts from the passband level

**Files:**
- Modify: `src/bodeplot/markers.py` (imports, the constants `DROP_DB` and `PROMINENCE_DB`, `MarkerSet.evaluate`, the functions `_peak`, `_cross`, `_cutoffs`)
- Modify: `src/bodeplot/gui/bode_plot.py` (`MARKER_TEXT["cutoff"]`)
- Test: `tests/test_markers.py`, `tests/test_gui_markers.py`, `tests/test_gui_markers_panel.py`

**Interfaces:**
- Consumes: `DROP_DB`, `ends_extreme`, `marker_pair`, `passband` from `measure/metrics.py` (Task 2).
- Produces: nothing new. `MarkerSet.evaluate` returns the same markers with the same names; only the frequencies of `fc` / `fL` / `fH` follow the new rule (spec section 3.7).

- [ ] **Step 1: Write the failing tests, and correct the tests the rule moves**

Apply to `tests/test_markers.py`. Two existing assertions get a tolerance (the level is now that of the flat part, −0.008 dB on this curve, not the first point's −0.004 dB), and three tests are appended:

```diff
--- a/tests/test_markers.py
+++ b/tests/test_markers.py
@@ -64,7 +64,7 @@
     m = every(of(RC))
     assert set(m) == {"fc", "pk", "nt", "GM", "PM"}
     assert m["fc"].freq == pytest.approx(FC, rel=0.02) and m["fc"].deg == pytest.approx(-45.0, abs=1.0)
-    assert m["fc"].db == pytest.approx(of(RC).db[0] - 3.0)
+    assert m["fc"].db == pytest.approx(-3.0, abs=0.02)             # 3 dB below the flat level, not below one point
     assert not m["pk"].found and not m["nt"].found and not m["GM"].found and not m["PM"].found
 
 
@@ -251,7 +251,7 @@
     assert rows[0] == ["Markers on: Sweep"]
     assert rows[1] == ["Marker", "Frequency (Hz)", "Gain (dB)", "Phase (deg)", "Note"]
     assert [r[0] for r in rows[2:]] == ["fc", "pk", "nt", "GM", "PM", "M1", "M2"]
-    assert float(rows[2][1]) == pytest.approx(FC, rel=0.02) and float(rows[2][2]) == pytest.approx(-3.0, abs=0.01)
+    assert float(rows[2][1]) == pytest.approx(FC, rel=0.02) and float(rows[2][2]) == pytest.approx(-3.0, abs=0.02)
     assert rows[3] == ["pk", "", "", "", "none"]
     assert rows[7][4] == "reference marker" and rows[8][4].startswith("rel. M1: x10, ")
     assert text.endswith("\n") and all(len(r) == 5 for r in rows[1:])
@@ -316,3 +316,28 @@
                  "t").splitlines()
     assert rows[2].split("\t")[1] == "0.0123456"
     assert rows[3].split("\t")[1] == "1234.57"
+
+
+def test_the_cutoff_counts_from_the_flat_level_when_there_is_one():
+    """v3 (user, 2026-10-07): a low-pass with a hump before its cut-off. The cut-off lies 3 dB
+    below the flat level, not 3 dB below the top of the hump."""
+    w0 = 2 * math.pi * 10e3
+    hump = TransferFunction.custom([w0 * w0], [1.0, w0 / 2.0, w0 * w0])       # second order, Q = 2: a 6.3 dB hump
+    m = every(of(hump))
+    x2 = (1.75 + math.sqrt(1.75 ** 2 + 4)) / 2                  # |H|^2 = 1/2
+    assert set(m) >= {"fc", "pk"} and "fL" not in m             # counted from the hump it was two edges, 6.2 and 11.7 kHz
+    assert m["fc"].freq == pytest.approx(10e3 * math.sqrt(x2), rel=0.01)       # 14.8 kHz
+    assert m["fc"].db == pytest.approx(-3.0, abs=0.05)
+    assert m["pk"].found and m["pk"].db == pytest.approx(6.3, abs=0.2)         # the peak marker still sits on the hump
+
+
+def test_a_notch_filter_gets_both_edges_with_bandwidth_and_q():
+    m = every(of(NOTCH))
+    assert "fc" not in m and m["fL"].freq < F0 < m["fH"].freq
+    assert m["fL"].db == pytest.approx(-3.0, abs=0.05) and m["fH"].extra.startswith("BW ")
+    assert float(m["fH"].extra.split("Q ")[1]) == pytest.approx(1.0, rel=0.05)
+
+
+def test_a_resonant_band_pass_keeps_the_rule_of_v2():
+    m = every(of(BPF))                                          # no flat stretch: 3 dB below the peak, as before
+    assert m["fL"].db == pytest.approx(m["pk"].db - 3.0, abs=1e-9) and m["fH"].db == m["fL"].db
```

Apply to `tests/test_gui_markers.py` (a notch filter now shows both edges):

```diff
--- a/tests/test_gui_markers.py
+++ b/tests/test_gui_markers.py
@@ -95,7 +95,8 @@
     assert placed(plot)["pk"].marker.freq == pytest.approx(F0, rel=0.01)
     assert "\nBW " in placed(plot)["fH"].text and " Q " in placed(plot)["fH"].text
     plot.set_points(sweep(NOTCH))
-    assert names(plot) == ["fc", "nt"]                           # one edge of the notch is 3 dB down from the flat part
+    assert names(plot) == ["fL", "fH", "nt"]                     # both edges of the notch, 3 dB below the flat parts
+    assert "\nBW " in placed(plot)["fH"].text
     assert placed(plot)["nt"].marker.freq == pytest.approx(F0, rel=0.03)
 
 
```

Apply to `tests/test_gui_markers_panel.py` (this file's sweep starts at 100 Hz, so the level reads −0.03 dB; see the known limit in spec section 3.1):

```diff
--- a/tests/test_gui_markers_panel.py
+++ b/tests/test_gui_markers_panel.py
@@ -139,7 +139,7 @@
     plot.toggle_reference_marker(1)
     got = rows(panel)
     assert [r[0] for r in got] == ["fc", "pk", "M1", "M2"]
-    assert got[0][1].endswith("kHz") and got[0][2] == "-3.02 dB" and got[0][3].startswith("-4") and got[0][3].endswith("°")
+    assert got[0][1].endswith("kHz") and got[0][2] in ("-3.02 dB", "-3.03 dB", "-3.04 dB") and got[0][3].startswith("-4") and got[0][3].endswith("°")
     assert got[1] == ["pk", "", "", "", "none"]                  # switched on, and a low-pass has no peak
     assert got[2][1] == "1 kHz" and got[2][4] == "reference marker"
     assert got[3][4].startswith("rel. M1: x10, ") and got[3][4].endswith("dB/dec")
```

- [ ] **Step 2: Run them and see the new ones fail**

Run: `.venv\Scripts\python -m pytest tests\test_markers.py tests\test_gui_markers.py -q`
Expected: 3 failed, the rest pass: `test_the_cutoff_counts_from_the_flat_level_when_there_is_one` (counted from the hump, the old rule gives two edges `fL` and `fH` at 6.2 and 11.7 kHz and no `fc`), `test_a_notch_filter_gets_both_edges_with_bandwidth_and_q` (the old rule gives one edge, `fc`), and `test_peak_edges_and_notch` in the GUI file (`['fc', 'nt'] != ['fL', 'fH', 'nt']`).

- [ ] **Step 3: Implement in `markers.py`**

```diff
--- a/src/bodeplot/markers.py
+++ b/src/bodeplot/markers.py
@@ -11,13 +11,12 @@
 import math
 from dataclasses import dataclass
 
-from .measure.response import Curve, crossings, extremum
+from .measure.metrics import DROP_DB, ends_extreme, marker_pair, passband
+from .measure.response import Curve, crossings
 from .units import fmt_si
 
 KINDS = ("cutoff", "peak", "notch", "margins")      # the automatic markers, in menu order
 MAX_USER = 8
-DROP_DB = 3.0                   # the cut-off lies this far below the highest gain
-PROMINENCE_DB = 1.0             # a peak or notch stands at least this far clear of both ends
 PASS_DEG = 2.0                  # the phase passes -180 degrees when it stands this far clear of it on both sides
 SAME_FREQ = 1e-3              # two markers within 0.1 % have no slope between them
 OUTSIDE = "outside the trace"
@@ -117,13 +116,13 @@
         margins False: the margins make no sense here (relative display, no phase) and are
         left out."""
         out: list[Marker] = []
-        top, has_peak = _peak(c, True)
+        top, has_peak = ends_extreme(c, True)
         if "cutoff" in self.kinds:
-            out += _cutoffs(c, top)
+            out += _cutoffs(c)
         if "peak" in self.kinds:
             out.append(_at(c, "pk", "peak", top.f, top.db) if has_peak else Marker("pk", "peak"))
         if "notch" in self.kinds:
-            low, has_notch = _peak(c, False)
+            low, has_notch = ends_extreme(c, False)
             out.append(_at(c, "nt", "notch", low.f, low.db) if has_notch else Marker("nt", "notch"))
         if "margins" in self.kinds and margins:
             out += [_gain_margin(c), _phase_margin(c)]
@@ -155,51 +154,17 @@
     return Marker(name, kind, f, v[0] if db is None else db, v[1], c.flagged_at(f))
 
 
-def _peak(c: Curve, highest: bool):
-    """(extreme, is it a real peak / notch). When it is not, the extreme is the plain
-    highest (lowest) point, not a refined one. (None, False) for an empty curve."""
-    e = extremum(c, highest)
-    if e is None:
-        return None, False
-    idx = c.usable()
-    ends = (c.db[idx[0]], c.db[idx[-1]])
-    clear = e.db - max(ends) if highest else min(ends) - e.db
-    if e.interior and clear >= PROMINENCE_DB:
-        return e, True
-    e.f, e.db = c.f[e.index], c.db[e.index]
-    return e, False
-
-
-def _cross(c: Curve, i: int, j: int, level: float) -> float:
-    a, b = c.db[i] - level, c.db[j] - level
-    if a == b:
-        return c.f[i]
-    return c.f[i] * (c.f[j] / c.f[i]) ** (a / (a - b))
-
-
-def _cutoffs(c: Curve, top) -> list[Marker]:
-    if top is None:
-        return [Marker("fc", "cutoff")]
-    level = top.db - DROP_DB
-    if c.db[top.index] <= level:                # the refined peak stands 3 dB over every point: count from the
-        level = c.db[top.index] - DROP_DB       # highest point, or the level would lie above the whole curve
-    lo = hi = None
-    k = top.index
-    while k > 0 and c.ok[k - 1]:                # down in frequency, to the first crossing or a gap
-        if c.db[k - 1] <= level:
-            lo = _cross(c, k - 1, k, level)
-            break
-        k -= 1
-    k = top.index
-    while k < len(c.f) - 1 and c.ok[k + 1]:
-        if c.db[k + 1] <= level:
-            hi = _cross(c, k, k + 1, level)
-            break
-        k += 1
-    if lo is None and hi is None:
+def _cutoffs(c: Curve) -> list[Marker]:
+    """The -3 dB markers: 3 dB below the passband level (measure/metrics.py: the level of the
+    flat part of the curve; without one, its highest gain)."""
+    p = passband(c)
+    cuts = marker_pair(p)
+    if not cuts:
         return [Marker("fc", "cutoff")]
-    if lo is None or hi is None:
-        return [_at(c, "fc", "cutoff", lo if hi is None else hi, level)]
+    level = p.level - DROP_DB
+    if len(cuts) == 1 or cuts[1].f <= cuts[0].f:
+        return [_at(c, "fc", "cutoff", cuts[0].f, level)]
+    lo, hi = cuts[0].f, cuts[1].f
     low, high = _at(c, "fL", "cutoff", lo, level), _at(c, "fH", "cutoff", hi, level)
     bw = hi - lo
     high.extra = "BW %s  Q %.3g" % (fmt_si(bw, "Hz", 3), math.sqrt(lo * hi) / bw)
```

- [ ] **Step 4: Bring the tick box's explanation up to date**

In `src/bodeplot/gui/bode_plot.py`, in `MARKER_TEXT`, replace

```python
    "cutoff": ("-3 dB", "Mark where the gain has fallen 3 dB below the highest gain of the trace: the cut-off of "
                        "a low-pass or high-pass, or both edges of a band-pass with its bandwidth and Q"),
```

with

```python
    "cutoff": ("-3 dB", "Mark where the gain has fallen 3 dB below the passband level (the flat part of the "
                        "trace; without one, its highest gain): the cut-off of a low-pass or high-pass, or both "
                        "edges of a band-pass or a notch with the bandwidth and Q"),
```

- [ ] **Step 5: Run the whole suite**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all pass. In the prototype exactly four existing tests moved with the rule, and Step 1 corrected them: `test_rc_low_pass_has_a_cutoff_and_nothing_else`, `test_table_for_the_clipboard` (both in `tests/test_markers.py`), `test_peak_edges_and_notch` (`tests/test_gui_markers.py`), `test_the_table_lists_every_marker_with_its_values` (`tests/test_gui_markers_panel.py`). Any other failure is a fault: stop and look.

`tests/test_docs.py` may fail here on the imports of `markers.py` in `docs/ARCHITECTURE.md`. If it does, change the row of `markers.py` there now: its import column becomes `` `measure/metrics.py`, `measure/response.py`, `units.py` ``, and add the row of `measure/metrics.py` from Task 6 Step 3.

- [ ] **Step 6: Commit**

```powershell
git add src/bodeplot/markers.py src/bodeplot/gui/bode_plot.py tests/test_markers.py tests/test_gui_markers.py tests/test_gui_markers_panel.py docs/ARCHITECTURE.md
git commit -m "The -3 dB marker counts from the passband level: a hump no longer moves the cut-off, a notch filter gets both edges"
```

---

### Task 4: `analysis.py`, the table as text

**Files:**
- Create: `src/bodeplot/analysis.py`
- Test: `tests/test_analysis.py` (new)

**Interfaces:**
- Consumes: `Metrics`, `Resonance`, `FEW_POINTS` from `measure/metrics.py`; `fmt_si` from `units.py`.
- Produces (used by Task 5):
  - `Row(group: str, name: str, value: str = "", compare: str = "", diff: str = "", tip: str = "")`
  - `GROUPS: dict[str, str]` (group title -> its rule; keys in table order: Passband, Cut-off, Band, Roll-off, Stopband, Peak, Notch)
  - `AT_LEAST = "≥ "`, `FLAG = " (flagged)"`, `NONE = "none"`
  - `hz(f: float) -> str`
  - `rows(m: Metrics, other: Metrics | None = None, phase: bool = True) -> list[Row]`
  - `notes(m: Metrics) -> list[str]`
  - `table(title: str, table_rows: list[Row], table_notes: list[str], compare: bool = False) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_analysis.py`:

```python
"""The Analysis table as text (analysis.py): rows, limits, the difference to a second trace,
the notes and the clipboard text."""
import math

import pytest

from bodeplot.analysis import AT_LEAST, FLAG, GROUPS, NONE, notes, rows, table
from bodeplot.measure.metrics import analyse
from bodeplot.measure.response import curve
from bodeplot.measure.theory import TransferFunction as TF
from bodeplot.units import parse_si

FC = 1 / (2 * math.pi * 1e3 * 100e-9)
RC = TF.rc_lpf(1e3, 100e-9)
BPF = TF.rlc_bpf(100.0, 1e-3, 100e-9)


def grid(lo=50.0, hi=2e7, ppd=20):
    n = int(round(math.log10(hi / lo) * ppd)) + 1
    return [lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]


def m_of(tf, freqs=None, flagged=None, phase=True):
    freqs = freqs or grid()
    return analyse(curve(freqs, [tf.h(f) for f in freqs], [flagged(f) for f in freqs] if flagged else None), phase)


def cell(table_rows, group, name):
    (row,) = [r for r in table_rows if r.group == group and r.name == name]
    return row


def freq(text):
    return parse_si(text, "Hz")


def bp(f0, q):
    w = 2 * math.pi * f0
    return TF.custom([w / q, 0.0], [1.0, w / q, w * w])


def test_rows_of_an_rc_low_pass():
    t = rows(m_of(RC))
    assert [r.group for r in t] == ["Passband"] * 4 + ["Cut-off"] + ["Roll-off"] * 2 + ["Stopband"]
    assert [r.name for r in t] == ["Level", "Ripple", "Flat from", "Flat to", "fc", "Slope, fc", "Order, fc", "Beyond fc"]
    assert cell(t, "Passband", "Level").value in ("-0.01 dB", "-0.02 dB")
    assert cell(t, "Passband", "Flat from").value == "50 Hz" and cell(t, "Passband", "Flat to").value.endswith(" Hz")
    assert cell(t, "Stopband", "Beyond fc").value.startswith("≥ ") and AT_LEAST == "≥ "
    assert freq(cell(t, "Cut-off", "fc").value) == pytest.approx(FC, rel=0.005) and cell(t, "Cut-off", "fc").value.endswith(" kHz")
    assert cell(t, "Roll-off", "Slope, fc").value == "-20.0 dB/dec" and cell(t, "Roll-off", "Order, fc").value == "1"
    assert cell(t, "Stopband", "Beyond fc").value.startswith(AT_LEAST)                    # a limit says so
    assert all(r.compare == "" and r.diff == "" for r in t)
    assert all(r.tip == GROUPS[r.group] and len(r.tip) > 60 for r in t)


def test_rows_of_a_band_pass_with_its_resonance():
    t = rows(m_of(BPF))
    assert cell(t, "Passband", "Level (peak)").value == "+0.00 dB"       # never "-0.00"
    assert [r.name for r in t if r.group == "Cut-off"] == ["fL", "fH"]
    assert [r.name for r in t if r.group == "Band"] == ["Centre", "Bandwidth", "Q"]
    assert cell(t, "Band", "Q").value == "1"
    group = [r for r in t if r.group.startswith("Peak at ")]
    assert group[0].group == "Peak at 15.91 kHz"
    assert [r.name for r in group] == ["f0", "Gain at f0", "Height", "Q (width)", "Q (phase)", "Points"]
    assert group[3].value == "1" and group[5].value == "9" and all(r.tip == GROUPS["Peak"] for r in group)
    assert "Q (phase)" not in [r.name for r in rows(m_of(BPF, phase=False), phase=False)]
    notch = rows(m_of(TF.rlc_notch(100.0, 1e-3, 100e-9)))
    assert [r.name for r in notch if r.group.startswith("Notch at ")] == ["f0", "Gain at f0", "Depth", "Q (width)", "Points"]
    assert "Roll-off" not in [r.group for r in notch]            # into a notch there is no slope


def test_the_difference_to_a_second_trace():
    measured = m_of(TF.rc_lpf(1e3, 110e-9))                     # the capacitor is 10 % larger than the design says
    t = rows(measured, m_of(RC))
    fc = cell(t, "Cut-off", "fc")
    assert freq(fc.value) == pytest.approx(FC / 1.1, rel=0.005) and freq(fc.compare) == pytest.approx(FC, rel=0.005)
    assert float(fc.diff.rstrip(" %")) == pytest.approx(-9.1, abs=0.2) and fc.diff.endswith(" %")
    assert cell(t, "Passband", "Level").diff.endswith(" dB") and cell(t, "Roll-off", "Slope, fc").diff.endswith(" dB/dec")
    assert cell(t, "Roll-off", "Order, fc").diff == "0"
    assert cell(t, "Stopband", "Beyond fc").diff == ""                 # two limits have no difference
    assert cell(t, "Passband", "Ripple").diff == "+0.00 dB"            # never "-0.00"


def test_a_quantity_only_one_trace_has_keeps_its_row():
    t = rows(m_of(RC), m_of(BPF))
    assert cell(t, "Cut-off", "fc").compare == "" and cell(t, "Cut-off", "fL").value == ""
    assert cell(t, "Cut-off", "fL").compare != "" and cell(t, "Band", "Q").value == ""
    peak = [r for r in t if r.group.startswith("Peak at ")]
    assert peak and all(r.value == "" and r.compare != "" and r.diff == "" for r in peak)
    groups = [r.group for r in t]
    assert groups == sorted(groups, key=lambda g: (list(GROUPS) + [g]).index(g) if g in GROUPS else 99)


def test_resonances_pair_up_when_they_are_close():
    t = rows(m_of(bp(1.1e4, 10), grid(ppd=200)), m_of(bp(1e4, 10), grid(ppd=200)))
    group = [r for r in t if r.group.startswith("Peak at ")]
    assert len({r.group for r in group}) == 1                   # one resonance, seen in both traces
    assert float(group[0].diff.rstrip(" %")) == pytest.approx(10.0, abs=0.3)
    assert float(cell(group, group[0].group, "Q (width)").diff.rstrip(" %")) == pytest.approx(0.0, abs=2.0)
    t = rows(m_of(bp(2e4, 10), grid(ppd=200)), m_of(bp(1e4, 10), grid(ppd=200)))
    titles = []
    for r in t:
        if r.group.startswith("Peak at ") and r.group not in titles:
            titles.append(r.group)
    assert titles == ["Peak at 10 kHz", "Peak at 20 kHz"]       # too far apart: two resonances, in ascending order
    assert all(r.value == "" for r in t if r.group == titles[0]) and all(r.compare == "" for r in t if r.group == titles[1])


def test_flagged_numbers_are_marked_and_a_missing_q_says_none():
    t = rows(m_of(RC, flagged=lambda f: 1000.0 < f < 2000.0))
    assert cell(t, "Cut-off", "fc").value.endswith(FLAG) and not cell(t, "Passband", "Level").value.endswith(FLAG)
    hump = TF.custom([(2 * math.pi * 1e4) ** 2 * 1.0], [1.0, 2 * math.pi * 1e4 / 1.2, (2 * math.pi * 1e4) ** 2])
    peak = [r for r in rows(m_of(hump)) if r.group.startswith("Peak at ")]
    assert peak and peak[3].name == "Q (width)" and peak[3].value == NONE      # a 2 dB hump has no -3 dB width


def test_notes():
    assert notes(m_of(TF.through())) == ["No cut-off inside the sweep."]
    n = notes(m_of(RC))
    assert n == ["Beyond fc the sweep ends before the stop band levels off."]
    assert notes(m_of(BPF))[1] == "Beyond fL and fH the sweep ends before the stop band levels off."
    n = notes(m_of(RC, grid(200.0, 1e6)))                       # the sweep starts 0.9 decades below the cut-off
    assert n[0].startswith("The flat part runs to the low end of the sweep and spans less than a decade")
    assert n[0].endswith("start the sweep lower.") and len(n) == 2
    n = notes(m_of(TF.rc_hpf(1e3, 100e-9), grid(50.0, 1e4)))
    assert n[0].endswith("start the sweep higher.")
    n = notes(m_of(bp(1e4, 50)))
    assert n[0].startswith("No flat stretch") and any(s.startswith("Too few points on the peak at ") for s in n)
    assert any("sweep finer" in s for s in n)
    n = notes(m_of(RC, flagged=lambda f: f < 100.0))
    assert n[-1].endswith("is marked.") and " % of the points are flagged" in n[-1]
    assert notes(m_of(RC, [100.0, 1e3, 1e4])) == ["No analysis: fewer than 5 usable points."]
    assert rows(m_of(RC, [100.0, 1e3, 1e4])) == []


def test_table_for_the_clipboard():
    m = m_of(RC)
    text = table("Analysis of: Sweep", rows(m), notes(m))
    lines = text.splitlines()
    assert lines[0] == "Analysis of: Sweep" and lines[1] == "Quantity\tValue"
    assert lines[2] == "Passband" and lines[3].split("\t")[0] == "Level" and "Flat from\t50 Hz" in lines
    fc = cell(rows(m), "Cut-off", "fc").value
    assert "fc\t" + fc in lines and lines[-2] == "" and lines[-1].startswith("Beyond fc")
    assert text.endswith("\n")
    both = table("Analysis of: Sweep, compared with: RC", rows(m, m), [], compare=True).splitlines()
    assert both[1] == "Quantity\tValue\tCompare\tDifference"
    assert "fc\t%s\t%s\t+0.0 %%" % (fc, fc) in both
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_analysis.py -q`
Expected: an error while collecting, `ModuleNotFoundError: No module named 'bodeplot.analysis'`.

- [ ] **Step 3: Implement**

Create `src/bodeplot/analysis.py`:

```python
"""The Analysis table (SPEC.md section 10): the numbers of measure/metrics.py as rows of
text, for one trace or for two side by side with their difference, the notes under the
table and the clipboard text. No Qt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .measure.metrics import FEW_POINTS, Metrics, Resonance
from .units import fmt_si

SHORT_DECADES = 1.0             # a passband seen over less than this at an end of the sweep: its level is uncertain
PAIR_FACTOR = 1.2               # two resonances this close in frequency are the same one in both traces
AT_LEAST = "≥ "                 # a lower limit: the sweep ends before the number has settled
FLAG = " (flagged)"
NONE = "none"
# the groups of the table in their order: title -> the rule behind its numbers (the tooltip)
GROUPS = {
    "Passband": "The flat part of the trace: a stretch of at least a third of a decade where the gain changes by "
                "no more than 3 dB per decade (from ... to: where it lies). Level: its typical gain. Ripple: how "
                "far the gain moves between the cut-offs, a hump included. Without a flat stretch the level is "
                "the highest gain.",
    "Cut-off": "Where the gain has fallen 3 dB below the passband level, found between two measured points. "
               "One cut-off is fc; two are fL and fH.",
    "Band": "From the two cut-offs: the centre is the geometric mean of fL and fH, the bandwidth their "
            "difference, and Q the centre divided by the bandwidth.",
    "Roll-off": "How fast the gain falls beyond a cut-off: the slope the curve settles to, in dB per decade, and "
                "the filter order that goes with it (20 dB per decade for each order). '≥': at least this "
                "steep; the sweep ends before the slope has settled.",
    "Stopband": "How far below the passband level the trace gets beyond a cut-off. A plain number when the "
                "trace levels off there; '≥' (at least) when it is still falling or runs into a notch.",
    "Peak": "A resonance: a peak that stands at least 1 dB clear of the trace on both sides. Q (width): f0 "
            "divided by the width 3 dB below its top. Q (phase): from how fast the phase turns across it. "
            "Points: how many measured points lie on it; with fewer than five its numbers are uncertain.",
    "Notch": "A resonance: a notch that stands at least 1 dB clear of the trace on both sides. Q (width): f0 "
             "divided by the width 3 dB below its shoulder. Points: how many measured points lie in it; with "
             "fewer than five its numbers are uncertain.",
}


@dataclass
class Cell:
    text: str = ""
    number: float | None = None     # None: nothing to take a difference of
    kind: str = ""                  # "hz" | "ratio" | "db" | "span" | "slope" | "count"
    limit: bool = False


@dataclass
class Row:
    group: str                  # the title of its group: "Passband", "Peak at 15.92 kHz" ...
    name: str
    value: str = ""
    compare: str = ""
    diff: str = ""
    tip: str = ""


def hz(f: float) -> str:
    return fmt_si(f, "Hz", 4)


def _signed(v: float, digits: int, unit: str) -> str:
    """A number with its sign; a value that rounds to zero reads +0, never -0."""
    return "%+.*f %s" % (digits, round(v, digits) + 0.0, unit)


def _cell(kind: str, number: float, limit: bool = False, flagged: bool = False) -> Cell:
    text = {"hz": hz, "ratio": lambda v: "%.3g" % v, "db": lambda v: _signed(v, 2, "dB"),
            "span": lambda v: "%.2f dB" % v, "slope": lambda v: _signed(v, 1, "dB/dec"),
            "count": lambda v: "%d" % v}[kind](number)
    return Cell((AT_LEAST if limit else "") + text + (FLAG if flagged else ""), number, kind, limit)


def _diff(a: Cell | None, b: Cell | None) -> str:
    """The value against the compared one: frequencies and Q in percent of the compared
    value, everything in dB as a plain difference. Nothing where one side is missing or
    only a limit."""
    if a is None or b is None or a.number is None or b.number is None or a.limit or b.limit:
        return ""
    if a.kind in ("hz", "ratio"):
        return _signed(100.0 * (a.number - b.number) / b.number, 1, "%") if b.number else ""
    if a.kind in ("db", "span"):
        return _signed(a.number - b.number, 2, "dB")
    if a.kind == "slope":
        return _signed(a.number - b.number, 1, "dB/dec")
    return "%+d" % (a.number - b.number) if a.number != b.number else "0"


def cut_names(m: Metrics) -> list[str]:
    n = len(m.cutoffs)
    return ["fc"] if n == 1 else ["fL", "fH"] if n == 2 else ["f%d" % k for k in range(1, n + 1)]


def _entries(m: Metrics | None) -> list[tuple[tuple, str, str, Cell]]:
    """Everything but the resonances: (key, group, row name, cell). Rows of two traces with
    the same key stand side by side."""
    out: list[tuple[tuple, str, str, Cell]] = []
    if m is None or not m.ok:
        return out
    out.append((("level",), "Passband", "Level" if m.source == "flat" else "Level (peak)",
                _cell("db", m.level, flagged=m.level_flagged)))
    if m.ripple is not None:
        out.append((("ripple",), "Passband", "Ripple", _cell("span", m.ripple)))
    passes = [b for b in m.bands if b.kind == "pass"]
    for n, b in enumerate(passes, 1):                   # where the flat stretch lies, as two frequencies
        tail = "" if len(passes) == 1 else " %d" % n
        out.append((("flat from", n), "Passband", "Flat from" + tail, _cell("hz", b.lo)))
        out.append((("flat to", n), "Passband", "Flat to" + tail, _cell("hz", b.hi)))
    named = list(zip(cut_names(m), m.cutoffs))
    for name, cut in named:
        out.append((("cut", name), "Cut-off", name, _cell("hz", cut.f, flagged=cut.flagged)))
    if m.pair is not None:
        out.append((("centre",), "Band", "Centre", _cell("hz", m.centre)))
        out.append((("bandwidth",), "Band", "Bandwidth", _cell("hz", m.bandwidth)))
        out.append((("q",), "Band", "Q", _cell("ratio", m.q)))
    for name, cut in named:
        if cut.slope is not None:
            out.append((("slope", name), "Roll-off", "Slope, %s" % name,
                        _cell("slope", cut.slope.v, cut.slope.limit, cut.slope.flagged)))
            out.append((("order", name), "Roll-off", "Order, %s" % name,
                        _cell("count", cut.order.v, cut.order.limit)))
    for name, cut in named:
        if cut.attenuation is not None:
            out.append((("attenuation", name), "Stopband", "Beyond %s" % name,
                        _cell("span", cut.attenuation.v, cut.attenuation.limit, cut.attenuation.flagged)))
    return out


def _resonance(r: Resonance, phase: bool) -> list[tuple[str, Cell]]:
    out = [("f0", _cell("hz", r.f0, flagged=r.flagged)),
           ("Gain at f0", _cell("db", r.db)),
           ("Height" if r.kind == "peak" else "Depth", _cell("span", r.height)),
           ("Q (width)", _cell("ratio", r.q_width) if r.q_width is not None else Cell(NONE))]
    if r.kind == "peak" and phase:
        out.append(("Q (phase)", _cell("ratio", r.q_phase) if r.q_phase is not None else Cell(NONE)))
    out.append(("Points", Cell("%d" % r.points)))
    return out


def _pairs(a: list[Resonance], b: list[Resonance]) -> list[tuple[Resonance | None, Resonance | None]]:
    """The resonances of two traces side by side: one of the first with the nearest of the
    same kind of the second within PAIR_FACTOR; the rest alone. In ascending frequency."""
    free = list(b)
    out: list[tuple[Resonance | None, Resonance | None]] = []
    for r in a:
        near = [o for o in free if o.kind == r.kind and max(o.f0, r.f0) <= PAIR_FACTOR * min(o.f0, r.f0)]
        other = min(near, key=lambda o: abs(math.log(o.f0 / r.f0))) if near else None
        if other is not None:
            free.remove(other)
        out.append((r, other))
    out += [(None, o) for o in free]
    return sorted(out, key=lambda p: (p[0] or p[1]).f0)


def rows(m: Metrics, other: Metrics | None = None, phase: bool = True) -> list[Row]:
    """The table for m, with other next to it when given. A quantity only one of the two
    has still gets its row, with the other cell empty."""
    a, b = _entries(m), _entries(other)
    da, db = {e[0]: e for e in a}, {e[0]: e for e in b}
    keys = [e[0] for e in a] + [e[0] for e in b if e[0] not in da]
    order = list(GROUPS)
    out = []
    for key in sorted(keys, key=lambda k: order.index((da.get(k) or db[k])[1])):      # stable: by group only
        ea, eb = da.get(key), db.get(key)
        _key, group, name, _cell_ = ea or eb
        out.append(Row(group, name, ea[3].text if ea else "", eb[3].text if eb else "",
                       _diff(ea[3] if ea else None, eb[3] if eb else None), GROUPS[group]))
    mine = m.resonances if m.ok else []
    theirs = other.resonances if other is not None and other.ok else []
    for ra, rb in _pairs(mine, theirs):
        r = ra or rb
        kind = "Peak" if r.kind == "peak" else "Notch"
        group = "%s at %s" % (kind, hz(r.f0))
        ca = dict(_resonance(ra, phase)) if ra else {}
        cb = dict(_resonance(rb, phase)) if rb else {}
        for name, _c in _resonance(r, phase):
            xa, xb = ca.get(name), cb.get(name)
            out.append(Row(group, name, xa.text if xa else "", xb.text if xb else "", _diff(xa, xb), GROUPS[kind]))
    return out


def notes(m: Metrics) -> list[str]:
    """What the numbers do not say by themselves, one sentence each."""
    if not m.ok:
        return ["No analysis: %s." % m.reason]
    out = []
    if m.source == "peak":
        out.append("No flat stretch: the passband level is the highest gain of the trace.")
    for b in m.bands:
        if b.kind == "pass" and m.cutoffs and (b.at_low or b.at_high) and math.log10(b.hi / b.lo) < SHORT_DECADES:
            out.append("The flat part runs to the %s end of the sweep and spans less than a decade: the passband "
                       "level, and with it the cut-off, is uncertain; start the sweep %s."
                       % (("low", "lower") if b.at_low else ("high", "higher")))
    if not m.cutoffs:
        out.append("No cut-off inside the sweep.")
    falling = [name for name, cut in zip(cut_names(m), m.cutoffs) if cut.falling]
    if falling:
        out.append("Beyond %s the sweep ends before the stop band levels off." % " and ".join(falling))
    for r in m.resonances:
        if r.points < FEW_POINTS:
            out.append("Too few points on the %s at %s (%d): its top and its Q are uncertain; sweep finer "
                       "around it." % (r.kind, hz(r.f0), r.points))
    if m.flagged_share > 0:
        out.append("%.0f %% of the points are flagged; a number that rests on one is marked."
                   % max(1.0, 100.0 * m.flagged_share))
    return out


def table(title: str, table_rows: list[Row], table_notes: list[str], compare: bool = False) -> str:
    """The table as tab-separated text for the clipboard: the title, the column heads, a
    line per group and per row, then the notes."""
    cols = 4 if compare else 2
    lines = [title, "\t".join(("Quantity", "Value", "Compare", "Difference")[:cols])]
    group = None
    for r in table_rows:
        if r.group != group:
            group = r.group
            lines.append(group)
        lines.append("\t".join((r.name, r.value, r.compare, r.diff)[:cols]))
    if table_notes:
        lines.append("")
        lines += table_notes
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests\test_analysis.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/bodeplot/analysis.py tests/test_analysis.py
git commit -m "analysis.py: the metrics as table rows, the difference to a second trace, notes and clipboard text"
```

---

### Task 5: the Analysis panel and its dock

**Files:**
- Create: `src/bodeplot/gui/analysis_panel.py`
- Modify: `src/bodeplot/gui/bode_plot.py` (a new method `analysis_curve`, placed above `_place`)
- Modify: `src/bodeplot/gui/main_window.py` (import, `LAYOUT_VERSION`, the panel, the dock list, the tab, the View menu)
- Modify: `src/bodeplot/io/settings.py` (`PANELS`), `src/bodeplot/gui/dialogs.py` (`PANEL_LABELS`)
- Test: `tests/test_gui_analysis.py` (new), `tests/test_settings_more.py`, `tests/test_gui_tooltips.py`

**Interfaces:**
- Consumes: `metrics.analyse`, `metrics.Metrics` (Task 2); `analysis.rows`, `analysis.notes`, `analysis.table` (Task 4); from the plot: `plot.set` (`TraceSet`: `.traces`, `.get(id)`, `.live`, `.curve(id, span_hint, relative=False)`), `plot.span_hint`, `plot.has_phase`, the signal `plot.markers_changed` (emitted after every refresh of the plot), `QUIET` in `gui/bode_plot.py`; `theme.status_html(kind, text)` with kinds `"idle" | "good" | "warning"`, `theme.INK_2`.
- Produces:
  - `BodePlot.analysis_curve(trace_id: int) -> Curve | None`
  - `AnalysisPanel(plot)` with `trace_box`, `compare_box`, `trace_label`, `compare_label`, `analyse_btn`, `copy_btn`, `state` (QLabel, rich text), `table` (QTreeWidget, 4 columns), `notes` (QLabel) inside `notes_area` (QScrollArea); methods `analyse()`, `refresh()`, `stale() -> bool`, `rows() -> list[list[str]]`, `text() -> str`, `copy()`
  - `MainWindow.analysis_panel`, `MainWindow.docks["dock_analysis"]`, `MainWindow.view_actions["dock_analysis"]`, `LAYOUT_VERSION == 3`, `"dock_analysis"` in `io.settings.PANELS`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gui_analysis.py`:

```python
"""The Analysis panel (offscreen): nothing before Analyse, the table after it, a second
trace next to the first, the line that says the trace has changed, the clipboard text, and
its place in the window."""
import cmath
import math

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QPushButton

from bodeplot.gui import theme
from bodeplot.gui.analysis_panel import IDLE, AnalysisPanel
from bodeplot.gui.bode_plot import BodePlot
from bodeplot.gui.main_window import LAYOUT_VERSION, MainWindow
from bodeplot.io.settings import PANELS, AppSettings
from bodeplot.measure.theory import TransferFunction
from bodeplot.models import Flag, PointResult
from bodeplot.traces import TraceSet
from bodeplot.units import parse_si

RC = TransferFunction.rc_lpf(1e3, 100e-9)
BPF = TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9)
FC = 1 / (2 * math.pi * 1e3 * 100e-9)
FREQS = [50.0 * (2e7 / 50.0) ** (i / 112) for i in range(113)]  # 50 Hz to 20 MHz, 20 per decade


def point(f, h, flags=Flag.NONE):
    return PointResult(freq_hz=f, h=h, gain_db=20 * math.log10(abs(h)), phase_deg=math.degrees(cmath.phase(h)),
                       vref_amp=0.5, vdut_amp=0.5 * abs(h), vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1,
                       snr_ref_db=50.0, snr_dut_db=50.0, flags=flags, duration_s=0.1)


def sweep(tf=RC, freqs=FREQS):
    return [point(f, tf.h(f)) for f in freqs]


@pytest.fixture
def plot(qtbot):
    p = BodePlot(TraceSet())
    qtbot.addWidget(p)
    p.resize(900, 600)
    p.show()
    QApplication.processEvents()
    return p


@pytest.fixture
def panel(qtbot, plot):
    w = AnalysisPanel(plot)
    qtbot.addWidget(w)
    w.resize(400, 560)
    w.show()
    return w


def value(panel, group, name, column=1):
    rows = panel.rows()
    start = [r[0] for r in rows].index(group)
    for r in rows[start + 1:]:
        if r[0] == name:
            return r[column]
    raise AssertionError("no row %r in %r" % (name, group))


def fc(panel, column=1):
    return parse_si(value(panel, "Cut-off", "fc", column), "Hz")


def choose(box, text):
    box.setCurrentIndex(box.findText(text))
    box.activated.emit(box.currentIndex())


# ---------------------------------------------------------------------- only on the button
def test_nothing_is_worked_out_before_analyse(plot, panel):
    plot.set_points(sweep())
    assert panel.rows() == [] and panel.text() == "" and IDLE in panel.state.text()
    assert not panel.copy_btn.isEnabled() and panel.analyse_btn.isEnabled()
    assert [panel.table.headerItem().text(c) for c in range(4)] == ["Quantity", "Value", "Compare", "Difference"]


def test_analyse_fills_the_table(plot, panel):
    plot.set_points(sweep())
    panel.analyse_btn.click()
    groups = [r[0] for r in panel.rows() if r[1:] == ["", "", ""] and r[0] in ("Passband", "Cut-off", "Roll-off", "Stopband")]
    assert groups == ["Passband", "Cut-off", "Roll-off", "Stopband"]
    assert fc(panel) == pytest.approx(FC, rel=0.01) and value(panel, "Cut-off", "fc").endswith(" kHz")
    assert value(panel, "Roll-off", "Order, fc") == "1"
    assert value(panel, "Stopband", "Beyond fc").startswith("≥ ")
    assert panel.table.isColumnHidden(2) and panel.table.isColumnHidden(3)      # nothing to compare with
    assert "Sweep, analysed " in panel.state.text() and "changed" not in panel.state.text()
    assert panel.copy_btn.isEnabled() and "sweep ends before" in panel.notes.text()
    head = panel.table.topLevelItem(0)
    assert head.isExpanded() and len(head.toolTip(0)) > 60 and head.isFirstColumnSpanned()
    assert head.child(0).toolTip(1) == "Passband, Level. " + head.toolTip(0)     # the name in full, then the rule
    assert head.child(0).textAlignment(1) & Qt.AlignRight


def test_the_analysis_reads_the_trace_itself_whatever_the_plot_shows(plot, panel):
    plot.set_points(sweep())
    theory = plot.set.add_theory(RC)
    plot.traces_changed()
    plot.set.set_reference(theory.id)                   # 'Difference to trace': the plot draws a flat line at 0 dB
    plot.refresh()
    plot.set_unit("pct")
    panel.analyse()
    assert fc(panel) == pytest.approx(FC, rel=0.01)              # still the cut-off of the trace itself


def test_a_band_pass_shows_its_resonance(plot, panel):
    plot.set_points(sweep(BPF))
    panel.analyse()
    titles = [r[0] for r in panel.rows()]
    assert "Peak at 15.91 kHz" in titles and "Band" in titles
    assert value(panel, "Peak at 15.91 kHz", "Q (width)") == "1" and value(panel, "Band", "Q") == "1"
    plot.set_has_phase(False)                           # a magnitude-only measurement
    panel.analyse()
    assert "Q (phase)" not in [r[0] for r in panel.rows()]


# ---------------------------------------------------------------------- a second trace
def test_compare_with_a_theory_curve(plot, panel):
    plot.set_points(sweep(TransferFunction.rc_lpf(1e3, 110e-9)))        # the real capacitor is 10 % larger
    theory = plot.set.add_theory(RC)
    plot.traces_changed()
    assert [panel.compare_box.itemText(i) for i in range(panel.compare_box.count())] == ["off", "Sweep", theory.name]
    assert [panel.trace_box.itemText(i) for i in range(panel.trace_box.count())] == ["Sweep", theory.name]
    choose(panel.compare_box, theory.name)
    panel.analyse()
    assert not panel.table.isColumnHidden(2) and not panel.table.isColumnHidden(3)
    assert fc(panel, 1) == pytest.approx(FC / 1.1, rel=0.01) and fc(panel, 2) == pytest.approx(FC, rel=0.01)
    assert float(value(panel, "Cut-off", "fc", 3).rstrip(" %")) == pytest.approx(-9.1, abs=0.3)
    assert "compared with " + theory.name in panel.state.text()
    assert panel.text().splitlines()[1] == "Quantity\tValue\tCompare\tDifference"


def test_a_trace_compared_with_itself_is_shown_alone(plot, panel):
    plot.set_points(sweep())
    choose(panel.compare_box, "Sweep")
    panel.analyse()
    assert panel.table.isColumnHidden(2) and "compared" not in panel.state.text()


# ---------------------------------------------------------------------- the table stays, and says when it is old
def test_the_table_stays_and_says_when_the_trace_has_changed(plot, panel):
    plot.set_points(sweep())
    panel.analyse()
    before = panel.rows()
    assert not panel.stale()
    plot.add_point(point(3e7, RC.h(3e7)))               # a sweep is running: one more point
    assert panel.stale() and "trace changed since this analysis" in panel.state.text()
    assert theme.WARNING in panel.state.text() and panel.rows() == before     # the numbers wait for the next press
    panel.analyse()
    assert not panel.stale() and "changed" not in panel.state.text()


def test_a_removed_trace_makes_the_table_old_and_the_boxes_fall_back(plot, panel):
    plot.set_points(sweep())
    theory = plot.set.add_theory(BPF)
    plot.traces_changed()
    choose(panel.trace_box, theory.name)
    choose(panel.compare_box, "Sweep")
    panel.analyse()
    assert any(r[0].startswith("Peak at 15.9") for r in panel.rows())
    plot.set.remove(theory.id)
    plot.traces_changed()
    assert panel.stale() and panel.trace_box.currentText() == "Sweep" and panel.compare_box.currentText() == "Sweep"
    panel.analyse()                                     # now the sweep, alone
    assert fc(panel) == pytest.approx(FC, rel=0.01) and panel.table.isColumnHidden(2)


def test_an_empty_trace_says_so(plot, panel):
    panel.analyse()
    assert panel.rows() == [] and "No analysis: the trace has no points." in panel.notes.text()
    assert not panel.notes_area.isHidden()
    plot.set_points(sweep(freqs=[100.0, 1e3, 1e4]))
    panel.analyse()
    assert "fewer than 5 usable points" in panel.notes.text()


def test_flagged_points_show_in_the_table_and_the_notes(plot, panel):
    plot.set_points([point(f, RC.h(f), Flag.LOW_SNR if 1000 < f < 2000 else Flag.NONE) for f in FREQS])
    panel.analyse()
    assert value(panel, "Cut-off", "fc").endswith("(flagged)") and "points are flagged" in panel.notes.text()


# ---------------------------------------------------------------------- clipboard, look
def test_copy_table(plot, panel):
    plot.set_points(sweep())
    panel.analyse()
    panel.copy_btn.click()
    text = QApplication.clipboard().text()
    assert text == panel.text() and text.splitlines()[0] == "Analysis of: Sweep"
    assert "fc\t" + value(panel, "Cut-off", "fc") in text.splitlines()


def test_the_panel_gives_its_height_to_the_table_and_stays_narrow(plot, panel):
    plot.set_points(sweep(BPF))
    QApplication.processEvents()
    narrow = panel.minimumSizeHint().width()
    plot.set.add_theory(TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9)).name = "A theory curve with a very long name indeed"
    plot.traces_changed()
    panel.analyse()
    QApplication.processEvents()
    assert panel.table.height() >= 0.5 * panel.height()
    assert panel.trace_box.y() < panel.analyse_btn.y() < panel.state.y() < panel.table.y() < panel.notes_area.y()
    assert panel.notes_area.height() <= 4 * panel.fontMetrics().lineSpacing() + 2      # the notes never crowd the table out
    assert panel.table.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert panel.table.columnWidth(0) + sum(panel.table.columnWidth(c) for c in (1, 2, 3) if not panel.table.isColumnHidden(c)) \
        <= panel.table.viewport().width() + 2                                           # every column is on screen
    # neither a long trace name nor the table, the state line or the notes widen the panel
    assert panel.minimumSizeHint().width() == narrow
    assert panel.trace_box.view().minimumWidth() > panel.trace_box.width()     # the list that drops down shows the long name


def test_every_control_explains_itself(panel):
    for w in panel.findChildren(QPushButton) + panel.findChildren(QComboBox) + panel.findChildren(QCheckBox):
        tip, text = w.toolTip().strip(), w.text() if hasattr(w, "text") else type(w).__name__
        assert len(tip) >= 25 and tip != text, text
    assert panel.trace_label.toolTip() == panel.trace_box.toolTip()
    assert panel.compare_label.toolTip() == panel.compare_box.toolTip()
    assert all(len(w.toolTip()) >= 25 for w in (panel.table, panel.state, panel.notes, panel.notes_area))


# ---------------------------------------------------------------------- the main window
@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    w = MainWindow(simulate=True, settings=AppSettings(simulate=True), sim_seed=7)
    w.interactive = False
    qtbot.addWidget(w)
    w.show()
    yield w
    w.close()


def test_window_has_an_analysis_tab_behind_traces_and_markers(win):
    dock = win.docks["dock_analysis"]
    assert dock.widget() is win.analysis_panel and dock.windowTitle() == "Analysis"
    assert dock in win.tabifiedDockWidgets(win.docks["dock_traces"])
    assert win.dockWidgetArea(dock) == Qt.RightDockWidgetArea
    assert win.view_actions["dock_analysis"].text() == "&Analysis"
    assert "dock_analysis" in PANELS and win.settings.startup_panels["dock_analysis"] is True
    assert LAYOUT_VERSION == 3                          # the default arrangement changed: an older stored one is dropped once


def test_the_analysis_tab_does_not_widen_the_right_column(win, qtbot):
    """The app must fit a 1280 px wide screen (user, 2026-10-07): the right column is as wide as
    its widest tab, and that stays the Markers panel."""
    before = win.minimumSizeHint().width()
    win.docks["dock_analysis"].raise_()
    qtbot.waitUntil(lambda: win.analysis_panel.isVisible(), timeout=2000)
    win.plot.set_points(sweep(BPF))
    win.analysis_panel.analyse()
    QApplication.processEvents()
    assert win.analysis_panel.minimumSizeHint().width() <= win.markers_panel.minimumSizeHint().width()
    assert win.minimumSizeHint().width() == before


def test_analyse_in_the_window_after_a_simulated_sweep(win, qtbot):
    win.plot.set_points(sweep())
    win.analysis_panel.analyse_btn.click()
    assert fc(win.analysis_panel) == pytest.approx(FC, rel=0.01)
    win.plot.clear()                                    # a new sweep starts
    assert win.analysis_panel.stale()
```

Apply to `tests/test_settings_more.py` (the stored panel list has one more entry, three places) and `tests/test_gui_tooltips.py` (the new panel joins the "nothing without an explanation" sweep):

```diff
--- a/tests/test_settings_more.py
+++ b/tests/test_settings_more.py
@@ -60,7 +60,7 @@
     s = AppSettings()
     assert (s.skew_wizard_on_connect, s.tooltips, s.tooltip_delay_ms, s.auto_keep_sweeps) == (False, True, 3000.0, 0)
     assert (s.export_folder, s.last_folder, s.grid_color, s.debug_logging, s.advanced) == ("", "", "", False, {})
-    assert s.startup_panels == {"dock_config": True, "dock_waveform": True, "dock_traces": True, "dock_markers": True, "dock_log": True}
+    assert s.startup_panels == {"dock_config": True, "dock_waveform": True, "dock_traces": True, "dock_markers": True, "dock_analysis": True, "dock_log": True}
     assert (s.skew_freq_lo_hz, s.skew_freq_hi_hz, s.skew_captures) == (10e6, 20e6, 3)
     s.skew_wizard_on_connect, s.tooltip_delay_ms, s.auto_keep_sweeps, s.grid_color = True, 500.0, 3, "#445566"
     s.advanced = {"low_snr_db": 15.0, "autorange_max_retries": 5}
@@ -76,7 +76,7 @@
                                "startup_panels": {"dock_log": False, "nonsense": 1}, "advanced": "x"})
     assert s.tooltip_delay_ms == 10000.0 and s.auto_keep_sweeps == 6 and s.grid_color == ""
     assert (s.skew_freq_lo_hz, s.skew_freq_hi_hz, s.skew_captures) == (10e6, 20e6, 1)
-    assert s.startup_panels == {"dock_config": True, "dock_waveform": True, "dock_traces": True, "dock_markers": True, "dock_log": False}
+    assert s.startup_panels == {"dock_config": True, "dock_waveform": True, "dock_traces": True, "dock_markers": True, "dock_analysis": True, "dock_log": False}
     assert s.advanced == {}
     assert AppSettings.from_dict({"auto_keep_sweeps": "three", "tooltip_delay_ms": -5}).tooltip_delay_ms == 0.0
 
@@ -196,7 +196,7 @@
 # ---------------------------------------------------------------------- the main window uses them
 def test_startup_panels_and_appearance_are_applied(qtbot, tmp_path, monkeypatch):
     win = make_win(qtbot, tmp_path, monkeypatch, tooltip_delay_ms=700.0, grid_color="#445566", debug_logging=True,
-                   startup_panels={"dock_config": True, "dock_waveform": False, "dock_traces": True, "dock_markers": True, "dock_log": True},
+                   startup_panels={"dock_config": True, "dock_waveform": False, "dock_traces": True, "dock_markers": True, "dock_analysis": True, "dock_log": True},
                    advanced={"low_snr_db": 15.0}, export_folder=str(tmp_path))
     assert not win.docks["dock_waveform"].isVisible() and win.docks["dock_traces"].isVisible()
     win.view_actions["dock_waveform"].trigger()                    # still one click away
```

```diff
--- a/tests/test_gui_tooltips.py
+++ b/tests/test_gui_tooltips.py
@@ -82,7 +82,7 @@
     silent = [name for name, w in named.items() if not explains(w.toolTip(), name)]
     assert not silent, "options without an explanation: %s" % silent
     # nothing new slipped in without one: every button and box of these three panels is in the list
-    for host in (plot, panel, log, win.markers_panel):
+    for host in (plot, panel, log, win.markers_panel, win.analysis_panel):
         for w in host.findChildren(QPushButton) + host.findChildren(QComboBox) + host.findChildren(QCheckBox):
             assert explains(w.toolTip()), "%s in %s has no explanation" % (
                 w.text() if hasattr(w, "text") else type(w).__name__, type(host).__name__)
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_gui_analysis.py -q`
Expected: an error while collecting, `ModuleNotFoundError: No module named 'bodeplot.gui.analysis_panel'`.

- [ ] **Step 3: Give the plot `analysis_curve`**

In `src/bodeplot/gui/bode_plot.py`, directly above `def _place(self, m, curve, points) -> Placed:`, add:

```python
    def analysis_curve(self, trace_id: int):
        """One trace as a response curve for the Analysis panel: the trace itself (gain in dB,
        phase), whatever the vertical unit and 'Difference to trace' are set to, its suspect
        points flagged. None: no such trace, or it has no points."""
        got = self.set.curve(trace_id, self.span_hint, relative=False)
        if got is None or not got[0].f:
            return None
        curve, points = got
        if points is not None:
            curve.flagged = [bool(p.flags & ~QUIET) for p in points]
        return curve

```

- [ ] **Step 4: Write the panel**

Create `src/bodeplot/gui/analysis_panel.py`:

```python
"""The Analysis panel (SPEC.md section 10): the response metrics of one trace as a table,
with a second trace next to it for comparison.

Nothing is worked out until Analyse is pressed, and the table then stays as it is: when the
analysed trace changes afterwards (a new sweep, a removed trace), a line says so and the
numbers wait for the next press. The maths is measure/metrics.py, the texts are analysis.py;
the panel only asks and shows.

Its order is that of the Markers panel: what is chosen on top, then the table with all the
height that is left, the notes under it in a few lines that scroll when there are more. The
figures keep their width and the names of the quantities take what is left, so that the
table needs no sideways scrolling in a narrow column.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QScrollArea, QSizePolicy, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from .. import analysis
from ..measure import metrics
from . import theme

COLUMNS = ("Quantity", "Value", "Compare", "Difference")
FIGURES = (1, 2, 3)                     # the columns of numbers: right-aligned, so that digits line up
IDLE = "Press Analyse to work out the numbers of the chosen trace."
NOTE_LINES = 4                          # the notes take this many lines at most; more are scrolled


def _quiet(label: QLabel) -> QLabel:
    """A text that wraps and has no say in the panel's width (as the plot's read-out)."""
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    label.setMinimumWidth(0)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


class AnalysisPanel(QWidget):
    def __init__(self, plot, parent=None):
        super().__init__(parent)
        self.plot = plot
        self._shown: dict | None = None     # what the table holds: trace ids, names, time, the curves' prints
        self._text = ""                     # the same as clipboard text
        lay = QVBoxLayout(self)

        form = QGridLayout()
        self.trace_label, self.trace_box = QLabel("Trace"), QComboBox()
        self.compare_label, self.compare_box = QLabel("Compare with"), QComboBox()
        self.trace_box.setToolTip("The trace to analyse. Its gain in dB and its phase are read as measured, "
                                  "whatever the vertical unit and 'Difference to trace' are set to.")
        self.compare_box.setToolTip("A second trace, such as a theory curve or an earlier sweep: its numbers are "
                                    "shown next to those of the analysed trace, with the difference. 'off' "
                                    "shows one trace only.")
        for row, (label, box) in enumerate(((self.trace_label, self.trace_box),
                                            (self.compare_label, self.compare_box))):
            # a small fixed width whatever the traces are called: the list that drops down shows the full names
            box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            box.setMinimumContentsLength(8)
            label.setToolTip(box.toolTip())
            form.addWidget(label, row, 0)
            form.addWidget(box, row, 1)
        form.setColumnStretch(1, 1)
        lay.addLayout(form)

        row = QHBoxLayout()
        self.analyse_btn = QPushButton("Analyse")
        self.analyse_btn.setToolTip("Work out the numbers of the chosen trace now: passband level and ripple, "
                                    "cut-offs, slope and order, stopband attenuation, and every resonance. The "
                                    "table then stays as it is until this is pressed again.")
        self.copy_btn = QPushButton("Copy table")
        self.copy_btn.setToolTip("Copy the table and its notes as tab-separated text for a report or a spreadsheet")
        row.addWidget(self.analyse_btn)
        row.addWidget(self.copy_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self.state = _quiet(QLabel())
        self.state.setTextFormat(Qt.RichText)
        self.state.setToolTip("Which trace the table below belongs to and when it was worked out. A warning "
                              "appears here when that trace has changed since.")
        lay.addWidget(self.state)

        self.table = QTreeWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHeaderLabels(list(COLUMNS))
        self.table.setRootIsDecorated(False)
        self.table.setIndentation(self.fontMetrics().averageCharWidth() * 2)
        self.table.setMinimumWidth(0)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.header().setStretchLastSection(False)
        self.table.header().setMinimumSectionSize(0)
        self.table.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in FIGURES:
            self.table.header().setSectionResizeMode(c, QHeaderView.ResizeToContents)
            self.table.headerItem().setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
        self.table.setToolTip("The numbers of the analysed trace, in groups. Rest the mouse on a row to read the "
                              "rule behind its group. '≥': at least; the sweep ends before the number has settled.")
        lay.addWidget(self.table, 1)

        self.notes = _quiet(QLabel())
        self.notes.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.notes.setToolTip("What the numbers do not say by themselves: where the sweep ends too early, where "
                              "a resonance has too few points, how many points are flagged.")
        self.notes_area = QScrollArea()                 # a few lines; the table keeps the height
        self.notes_area.setFrameShape(QFrame.NoFrame)
        self.notes_area.setWidgetResizable(True)
        self.notes_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.notes_area.setWidget(self.notes)
        self.notes_area.setToolTip(self.notes.toolTip())
        self.notes_area.hide()
        lay.addWidget(self.notes_area)

        self.trace_box.activated.connect(lambda _i: self._update_state())
        self.compare_box.activated.connect(lambda _i: self._update_state())
        self.analyse_btn.clicked.connect(lambda _checked=False: self.analyse())
        self.copy_btn.clicked.connect(lambda _checked=False: self.copy())
        plot.markers_changed.connect(self.refresh)      # the plot says so after every change of its traces
        self.refresh()

    # ---- following the plot
    def refresh(self) -> None:
        """The traces may have changed: fill the two boxes again and say whether the table still holds."""
        traces = self.plot.set.traces
        for box, first in ((self.trace_box, None), (self.compare_box, "off")):
            chosen = box.currentData()
            box.blockSignals(True)
            box.clear()
            if first is not None:
                box.addItem(first, None)
            for t in traces:
                box.addItem(t.name, t.id)
            box.setCurrentIndex(max(0, box.findData(chosen)))
            box.blockSignals(False)
            box.view().setMinimumWidth(max(self.fontMetrics().horizontalAdvance(t.name) for t in traces) + 40)
        self._update_state()

    def _print(self, trace_id) -> tuple | None:
        """What a trace looks like to the analysis, to tell later whether it changed."""
        c = self.plot.analysis_curve(trace_id) if trace_id is not None else None
        return None if c is None else (tuple(c.f), tuple(c.db), tuple(c.deg), tuple(c.flagged))

    def stale(self) -> bool:
        """The table no longer belongs to the traces as they are now."""
        s = self._shown
        return s is not None and (self._print(s["trace"]) != s["print"] or self._print(s["compare"]) != s["compare_print"])

    def _update_state(self) -> None:
        s = self._shown
        self.copy_btn.setEnabled(s is not None and bool(self._text))
        if s is None:
            self.state.setText(theme.status_html("idle", IDLE))
            return
        text = "%s, analysed %s" % (s["title"], s["when"].strftime("%H:%M:%S"))
        if self.stale():
            self.state.setText(theme.status_html("warning", text + ": trace changed since this analysis"))
        else:
            self.state.setText(theme.status_html("good", text))

    # ---- the analysis
    def analyse(self) -> None:
        """Work out the table for the chosen trace (and the compared one) as they are now."""
        plot = self.plot
        trace_id, compare_id = self.trace_box.currentData(), self.compare_box.currentData()
        if compare_id == trace_id:
            compare_id = None                           # a trace against itself says nothing
        trace = plot.set.get(trace_id) or plot.set.live
        other = plot.set.get(compare_id) if compare_id is not None else None
        curve = plot.analysis_curve(trace.id)
        other_curve = plot.analysis_curve(other.id) if other is not None else None
        phase = plot.has_phase
        m = metrics.analyse(curve, phase) if curve is not None else metrics.Metrics(reason="the trace has no points")
        mo = metrics.analyse(other_curve, phase) if other_curve is not None else None
        rows = analysis.rows(m, mo, phase)
        notes = analysis.notes(m)
        if other is not None and (mo is None or not mo.ok):     # of the compared trace only that it has no numbers
            notes.append("%s: no analysis, %s." % (other.name, mo.reason if mo is not None else "the trace has no points"))
        title = trace.name + (", compared with %s" % other.name if other is not None else "")
        self._shown = {"trace": trace.id, "compare": other.id if other is not None else None, "title": title,
                       "when": datetime.now(), "print": self._print(trace.id),
                       "compare_print": self._print(other.id) if other is not None else None}
        self._text = analysis.table("Analysis of: " + title, rows, notes, compare=other is not None)
        self._fill(rows, other is not None)
        self.notes.setText("\n".join(notes))
        self.notes_area.setVisible(bool(notes))
        self._fit_notes()
        self._update_state()

    def _fit_notes(self) -> None:
        """The notes are as high as their text, up to NOTE_LINES lines."""
        width = max(1, self.notes_area.viewport().width())
        cap = NOTE_LINES * self.fontMetrics().lineSpacing()
        self.notes_area.setFixedHeight(min(self.notes.heightForWidth(width), cap) + 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_notes()

    def _fill(self, rows, compare: bool) -> None:
        self.table.clear()
        self.table.setColumnHidden(2, not compare)
        self.table.setColumnHidden(3, not compare)
        quiet = QBrush(QColor(theme.INK_2))
        group, head = None, None
        for r in rows:
            if r.group != group:
                group = r.group
                head = QTreeWidgetItem([group])
                head.setForeground(0, quiet)
                head.setToolTip(0, r.tip)
                self.table.addTopLevelItem(head)
                head.setFirstColumnSpanned(True)        # only an item that is in the tree can span: its title is never cut
            item = QTreeWidgetItem([r.name, r.value, r.compare, r.diff])
            for c in range(len(COLUMNS)):               # the name in full (the column may cut it short), then the rule
                item.setToolTip(c, "%s, %s. %s" % (r.group, r.name, r.tip))
            for c in FIGURES:
                item.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            head.addChild(item)
        self.table.expandAll()

    def rows(self) -> list[list[str]]:
        """The table as shown, group lines included: [quantity, value, compare, difference]."""
        out = []
        for i in range(self.table.topLevelItemCount()):
            head = self.table.topLevelItem(i)
            out.append([head.text(0), "", "", ""])
            out += [[head.child(k).text(c) for c in range(len(COLUMNS))] for k in range(head.childCount())]
        return out

    def text(self) -> str:
        """The table and its notes as tab-separated text (the clipboard text)."""
        return self._text

    def copy(self) -> None:
        QApplication.clipboard().setText(self._text)
```

Why it is built this way (each point was a fault seen in the offscreen renders of the prototype):
- the notes sit in a scroll area of four lines at most: as a plain label, six long notes left the table seven rows;
- the names' column stretches and the three figure columns size to their content, with the horizontal scroll bar off: with all four sized to content, "Difference" lay outside the panel;
- `setFirstColumnSpanned(True)` is called after `addTopLevelItem`: before it, it does nothing and the group titles were cut to "Pass…";
- `state` and `notes` have the size policy Ignored horizontally: a long trace name in the state line would otherwise widen the right column and with it the window.

- [ ] **Step 5: Put it into the window**

Apply to `src/bodeplot/gui/main_window.py`:

```diff
--- a/src/bodeplot/gui/main_window.py
+++ b/src/bodeplot/gui/main_window.py
@@ -26,6 +26,7 @@
 from ..units import fmt_si
 from .dialogs import (CalDialog, ConnectionsDialog, ImageExportDialog, SettingsDialog, SimSettingsDialog,
                       SkewWizard)
+from .analysis_panel import AnalysisPanel
 from .status_log import StatusLog
 from .markers_panel import MarkersPanel
 from .traces_panel import TracesPanel
@@ -35,7 +36,7 @@
 BUSY = (EngineState.CONNECTING, EngineState.RUNNING, EngineState.PAUSED, EngineState.ABORTING)
 
 
-LAYOUT_VERSION = 2      # the arrangement of the panels; a window layout stored by another one is not restored
+LAYOUT_VERSION = 3      # the arrangement of the panels; a window layout stored by another one is not restored
 
 class MainWindow(QMainWindow):
     def __init__(self, simulate: bool | None = None, settings: AppSettings | None = None,
@@ -78,10 +79,12 @@
         self.traces_panel = TracesPanel(self.traces)
         self.traces_panel.interactive = self._interactive
         self.markers_panel = MarkersPanel(self.plot)
+        self.analysis_panel = AnalysisPanel(self.plot)
         for title, name, widget, area in (
                 ("Configuration", "dock_config", self.config, Qt.LeftDockWidgetArea),
                 ("Traces", "dock_traces", self.traces_panel, Qt.RightDockWidgetArea),
                 ("Markers", "dock_markers", self.markers_panel, Qt.RightDockWidgetArea),
+                ("Analysis", "dock_analysis", self.analysis_panel, Qt.RightDockWidgetArea),
                 ("Status log", "dock_log", self.status_log, Qt.BottomDockWidgetArea),
                 ("Waveform", "dock_waveform", self.waveform, Qt.BottomDockWidgetArea)):
             dock = QDockWidget(title, self)
@@ -90,10 +93,11 @@
             self.addDockWidget(area, dock)
             self.docks[name] = dock
         # The window reads in working order (user's review of 2026-10-07): set up on the left, the
-        # plot in the middle, reading the result on the right (Traces, and Markers as a tab behind
-        # it: markers belong to a trace). What is watched while a sweep runs, the log and the
+        # plot in the middle, reading the result on the right (Traces, with Markers and Analysis as
+        # tabs behind it: both read a trace). What is watched while a sweep runs, the log and the
         # waveform, shares a low strip underneath.
         self.tabifyDockWidget(self.docks["dock_traces"], self.docks["dock_markers"])
+        self.tabifyDockWidget(self.docks["dock_markers"], self.docks["dock_analysis"])
         self.docks["dock_traces"].raise_()
         self.splitDockWidget(self.docks["dock_log"], self.docks["dock_waveform"], Qt.Horizontal)
         self._default_sizes()
@@ -279,7 +283,7 @@
         m.setToolTipsVisible(True)
         self.view_actions = {}
         for name, text in (("dock_config", "&Configuration"), ("dock_waveform", "&Waveform"), ("dock_traces", "&Traces"),
-                           ("dock_markers", "&Markers"), ("dock_log", "&Status log")):
+                           ("dock_markers", "&Markers"), ("dock_analysis", "&Analysis"), ("dock_log", "&Status log")):
             a = self.docks[name].toggleViewAction()     # checked while the dock is open
             a.setText(text)
             m.addAction(a)
```

Apply to `src/bodeplot/io/settings.py` and `src/bodeplot/gui/dialogs.py`:

```diff
--- a/src/bodeplot/io/settings.py
+++ b/src/bodeplot/io/settings.py
@@ -52,7 +52,7 @@
 TOOLTIP_DELAY_MS = (0.0, 10000.0)
 MARKER_KINDS = ("cutoff", "peak", "notch", "margins")   # as markers.KINDS; a test keeps the two equal
 AUTO_KEEP_MAX = 6                       # with the live sweep, seven of the eight trace colours
-PANELS = ("dock_config", "dock_waveform", "dock_traces", "dock_markers", "dock_log")
+PANELS = ("dock_config", "dock_waveform", "dock_traces", "dock_markers", "dock_analysis", "dock_log")
 SKEW_DEFAULTS = (10e6, 20e6, 3)         # check frequencies and captures per frequency (SPEC.md section 8.6)
 SKEW_CAPTURES_MAX = 20
 # Advanced measurement settings: stored key -> (lowest, highest, integer?). They override the
```

```diff
--- a/src/bodeplot/gui/dialogs.py
+++ b/src/bodeplot/gui/dialogs.py
@@ -278,7 +278,7 @@
 
 # ---------------------------------------------------------------------- settings
 PANEL_LABELS = (("dock_config", "Configuration"), ("dock_waveform", "Waveform"), ("dock_traces", "Traces"),
-                ("dock_markers", "Markers"), ("dock_log", "Status log"))
+                ("dock_markers", "Markers"), ("dock_analysis", "Analysis"), ("dock_log", "Status log"))
 STARTUP_LABELS = (("instruments", "Real instruments"), ("simulation", "Simulation"),
                   ("last", "The mode used last time"))
 
```

- [ ] **Step 6: Run the tests**

Run: `.venv\Scripts\python -m pytest tests\test_gui_analysis.py tests\test_settings_more.py tests\test_gui_tooltips.py tests\test_gui_markers_panel.py tests\test_gui.py -q`
Expected: all pass (`tests/test_gui_analysis.py`: 16 passed).

Then the whole suite: `.venv\Scripts\python -m pytest -q --deselect tests/test_docs.py`
Expected: all pass (580 in the prototype).

- [ ] **Step 7: Commit**

```powershell
git add src/bodeplot/gui/analysis_panel.py src/bodeplot/gui/bode_plot.py src/bodeplot/gui/main_window.py src/bodeplot/io/settings.py src/bodeplot/gui/dialogs.py tests/test_gui_analysis.py tests/test_settings_more.py tests/test_gui_tooltips.py
git commit -m "Analysis tab: the metrics of a trace on a button, a second trace next to it, a line that says when the table is old"
```

---

### Task 6: the look, the documents, the user's review

**Files:**
- Create: `docs/screenshots/analysis_1280x720.png`, `analysis_1536x864.png`, `analysis_2560x1440.png` (offscreen renders)
- Modify: `docs/ARCHITECTURE.md`, `docs/spec/gui.md`, `docs/spec/roadmap.md`, `README.md`, `docs/STATE.md`, `docs/superpowers/specs/2026-10-07-response-metrics-design.md` (status line)

**Interfaces:**
- Consumes: everything above. Produces: nothing for later tasks.

- [ ] **Step 1: Render the window at three sizes and measure its smallest width**

Write this script to the scratchpad as `shot.py` (it is not part of the project) and run it with `.venv\Scripts\python <scratchpad>\shot.py docs\screenshots`:

```python
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BODEPLOT_NO_HARDWARE"] = "1"
os.environ["BODEPLOT_CONFIG_DIR"] = os.path.join(os.environ["TEMP"], "bodeplot_shot_cfg")
os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"      # without it the offscreen platform has no fonts and every width is wrong
sys.path.insert(0, "src"); sys.path.insert(0, "tests")
from PySide6.QtWidgets import QApplication
from bodeplot.gui.main_window import MainWindow
from bodeplot.io.settings import AppSettings
from bodeplot.measure.theory import TransferFunction as TF
import test_gui_analysis as t

out = sys.argv[1]
app = QApplication([])
for wd, ht in ((1280, 720), (1536, 864), (2560, 1440)):
    w = MainWindow(simulate=True, settings=AppSettings(simulate=True), sim_seed=7)
    w.interactive = False
    w.resize(wd, ht); w.show(); app.processEvents()
    w.plot.set_points(t.sweep(TF.rlc_bpf(100.0, 1e-3, 110e-9)))
    theory = w.traces.add_theory(TF.rlc_bpf(100.0, 1e-3, 100e-9)); w.plot.traces_changed()
    w.docks["dock_analysis"].raise_(); app.processEvents()
    t.choose(w.analysis_panel.compare_box, theory.name)
    w.analysis_panel.analyse(); app.processEvents()
    w.grab().save(os.path.join(out, "analysis_%dx%d.png" % (wd, ht)))
    if wd == 1280:
        w.resize(600, 400); app.processEvents()
        print("smallest window:", w.width(), "x", w.height())
    w.close()
```

Expected: `smallest window: 1221 x 510` (1221 x 500 before this work: the Analysis tab's own rows make the right column 10 px higher at least; the width must not move). Three PNG files.

- [ ] **Step 2: Look at the three renders, then review them with the frontend-design skill**

Read the three PNG files. Check by eye, at every size: all four columns of the table are inside the panel; no group title is cut; the notes take four lines at most and the table has more rows than the notes have lines; the state line wraps inside the panel; nothing overlaps; no colour that is not in `gui/theme.py`. Then invoke the skill `frontend-design:frontend-design` with the three renders and the panel's source, ask it for a review against the rest of the app (the Markers panel is the reference), and apply what it finds. Any change to the panel gets a test in `tests/test_gui_analysis.py` first. Render again after a change.

- [ ] **Step 3: `docs/ARCHITECTURE.md`**

Add three rows to the module table, each in its alphabetical place, and change two:

```
| `analysis.py` | the Analysis table as text: rows for one trace or two with their difference, notes, clipboard text; no Qt | `measure/metrics.py`, `units.py` |
| `gui/analysis_panel.py` | the Analysis dock: the trace to analyse and the one to compare with, Analyse / Copy table, the table in groups, the line that says when it is old, the notes | `analysis.py`, `gui/theme.py`, `measure/metrics.py` |
| `measure/metrics.py` | what the shape of one response curve says: flat stretches, passband level and ripple, cut-offs, slope and order, stopband attenuation, resonances with Q from width and phase; no Qt | `measure/response.py` |
```

- the row of `markers.py`: its import column becomes `` `measure/metrics.py`, `measure/response.py`, `units.py` ``;
- the row of `gui/main_window.py`: add `` `gui/analysis_panel.py` `` to its import column, in alphabetical place.

In the prose, after the paragraph that starts "**Markers** are outside it too", add:

```
**The analysis** (v3, part 1) sits beside the markers. `measure/metrics.py` reads the shape of one curve; `markers.py` takes its −3 dB cut-offs from it (`passband`, `marker_pair`), so the marker and the Analysis table show the same cut-off. `analysis.py` turns a `Metrics` into rows of text; `gui/analysis_panel.py` asks the plot for a trace as a curve (`BodePlot.analysis_curve`: always absolute and in dB) when Analyse is pressed, and follows the plot's `markers_changed` only to tell whether its table is still current.
```

In the table "where each concern lives", add a row:

```
| Analysis (passband, cut-offs, slope and order, attenuation, resonances) | the maths and every threshold in `measure/metrics.py`; rows, difference, notes and clipboard text in `analysis.py`; the trace as a curve in `gui/bode_plot.py` (`analysis_curve`); the controls, the table and the stale line in `gui/analysis_panel.py`; the dock in `gui/main_window.py` |
```

Run: `.venv\Scripts\python -m pytest tests\test_docs.py -q`. Expected: all pass. If it names a module or an import, the table is what is wrong: correct the table, not the test.

- [ ] **Step 4: `docs/spec/gui.md`, section 10**

- In the bullet "Window layout", change "`LAYOUT_VERSION` 2" to "`LAYOUT_VERSION` 3 since the Analysis tab" and "Right: reading the result (Traces, with Markers as a tab behind it)" to "Right: reading the result (Traces, with Markers and Analysis as tabs behind it)".
- In the bullet "Markers", change "(`fc`, or `fL` and `fH` with bandwidth and Q; 3 dB below the highest gain, the two crossings nearest to the maximum)" to "(`fc`, or `fL` and `fH` with bandwidth and Q; 3 dB below the passband level, which is the level of the flat part of the trace and, without one, its highest gain: `measure/metrics.py`, since v3)".
- After the bullet "Markers", add a bullet:

```
- **Analysis** (v3, part 1; design `docs/superpowers/specs/2026-10-07-response-metrics-design.md`): a dock "Analysis", a tab behind Traces and Markers. "Trace" chooses what is analysed, "Compare with" a second trace ("off" first). Nothing is worked out until **Analyse** is pressed; the table then stays, and a line above it names the trace and the time and turns into a warning ("trace changed since this analysis") when the trace was swept again, changed or removed. The table has the columns Quantity, Value, Compare, Difference (the last two only with a second trace) and groups under quiet title lines: Passband (level, ripple, where the flat part lies), Cut-off (`fc`, or `fL` and `fH`), Band (centre, bandwidth, Q), Roll-off (slope in dB/decade and order per cut-off), Stopband (attenuation beyond each cut-off), and one group per resonance ("Peak at …", "Notch at …": f0, gain, height or depth, Q from the −3 dB width, Q from the phase for a peak, points across it). "≥" marks a lower limit: the sweep ends before the number has settled. "(flagged)" marks a number that rests on a flagged point. Differences are percent for frequencies and Q, plain for everything in dB. Notes under the table, four lines at most, say what the numbers do not: no flat part, a passband seen over less than a decade, no cut-off inside the sweep, the stop band not reached, too few points on a resonance (the hook for the finer sweep of part 2), flagged points. The analysis reads the trace itself in dB, whatever the vertical unit and "Difference to trace" show. "Copy table" puts the table and the notes on the clipboard, tab-separated. The figures keep their width and the names take the rest, so the table never scrolls sideways; a trace's name never widens the panel. Nothing of it is stored. The rules and thresholds are in the design's section 3.
```

- [ ] **Step 5: `README.md`**

- In the feature list, after the line that starts "- **Markers**:", add:

```
- **Analysis**: on a button, the numbers of a trace: passband level and ripple, cut-off(s), slope and filter order, stopband attenuation, and every resonance with its Q from the width and from the phase; a second trace (a theory curve, an earlier sweep) next to it with the difference.
```

- After the section "## Markers", add a section:

```
## Analysis

The **Analysis** panel (on the right, a tab behind Traces and Markers; View > Analysis) works out the numbers of one trace when you press **Analyse**. Choose the trace under **Trace**, and under **Compare with** a second one, for example a theory curve with your design values: its numbers appear next to the measured ones, with the difference in percent (frequencies, Q) or in dB.

- **Passband:** the level of the flat part of the trace and how far the gain moves inside it. The cut-off is counted 3 dB below this level, here and in the −3 dB marker.
- **Roll-off and stop band:** the slope the curve settles to and the order that goes with it; how far below the passband the trace gets.
- **Resonances:** every peak and every notch with its frequency, its height or depth, Q from its −3 dB width and, for a peak, Q from the phase.
- **≥** means "at least": the sweep ends before the number has settled. The notes under the table say why, and where a resonance has too few points to be trusted.

The table stays until you press Analyse again; the line above it warns when the trace has changed since. **Copy table** puts it on the clipboard.
```

- In the paragraph "What comes next", say that v3 has started: part 1 (response metrics and the Analysis tab) is built, part 2 is a finer sweep around a found feature.

- [ ] **Step 6: The spec's status, the roadmap, `docs/STATE.md`**

- Spec, status line: "built on <date> (plan `docs/superpowers/plans/2026-10-07-response-metrics.md`); waiting for the user's review", and list any departure made while building.
- `docs/spec/roadmap.md`, section 16, the sentence on the five parts: mark part 1 as built, with the date.
- `docs/STATE.md`, "Start here": replace the paragraph "v3 started ..." by the state after the build: what is built, the test count, that the user has not seen it, what they decided in this session (already listed there), the seven rules changed while planning (spec, top), the finding for part 2 (fc scatters 0.45 % at bench noise because it is found between two points; a sweep starting close to the cut-off reads it high), and that part 2's design is next. Add a line to "What exists" for v3 part 1 with the modules and test files.

- [ ] **Step 7: Everything green, then commit**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all pass, `tests/test_docs.py` included. Note the count for `docs/STATE.md`.

```powershell
git add docs README.md
git commit -m "v3 part 1: Analysis tab documented; renders at three window sizes"
```

- [ ] **Step 8: The user's look**

Start the app for the user (`run.bat --sim`), or ask them to: Simulation mode, a sweep of the RC low-pass, the Analysis tab, Analyse; then Traces > Add theory with the same values, "Compare with" set to it, Analyse again; then the RLC band-pass in Sim settings. Ask what they see and what to change. Do not merge before they say so.

- [ ] **Step 9: Branch review and merge**

After the user's go: one fresh reviewer over the whole branch (`superpowers:requesting-code-review`), fix what is important, then `superpowers:finishing-a-development-branch` (merge into `main`, delete the branch, update `docs/STATE.md`).
