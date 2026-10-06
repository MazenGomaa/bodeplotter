# Trace Overlay, Theory Curves and Compare (v2, milestone A3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Several traces on the Bode plot (the live sweep, kept sweeps, CSV files, theory curves), each shown or hidden, and all of them drawn relative to one chosen trace on request.

**Architecture:** A Qt-free module `traces.py` owns the list of traces and the "relative to" maths and answers one question, "what is to be drawn"; the plot widget and the image export only draw the answer. Theory curves reuse the simulator's transfer functions, which move into `measure/theory.py`. A new Traces dock manages the list.

**Tech Stack:** Python 3.14, PySide6, pyqtgraph, numpy, matplotlib (image export), pytest + pytest-qt. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-07-trace-overlay-design.md` (approved by the user on 2026-10-07). Read it with this plan.

## Global Constraints

- Run from the project root in PowerShell. Tests: `.venv\Scripts\python -m pytest` (prints a summary; `-q` is already in the config). The suite stood at 349 passed before this plan and must never go down.
- Nothing in this plan touches an instrument. No bench run. `tests/conftest.py` keeps `BODEPLOT_NO_HARDWARE`.
- `traces.py` and `measure/theory.py` import no Qt (`tests/test_docs.py` enforces where Qt may be imported).
- Document guards (`tests/test_docs.py`): a new module or a changed import inside the package goes into the Modules table of `docs/ARCHITECTURE.md` in the same commit; the failing test prints the rows to change. A section cited in code must exist in `docs/spec/`. Nothing about this feature goes into `CLAUDE.md`.
- With no extra trace added, the plot, the read-out and every export behave as before (spec, success criterion 3). Existing tests stay unchanged except the one line this plan names in Task 3.
- Series colours come from `theme.SERIES` in fixed order and are never cycled; a trace beyond the eighth is drawn in `theme.MUTED`. The white-background image export is the one place that may hard-code colours.
- Traces live in memory only: nothing is written to the settings or to presets.
- CSV and Touchstone exports are not changed.
- Commit after every task on branch `a3-trace-overlay`. End every commit message with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01TbULzRjW3WqWNV5wkVxfN7
  ```

## Review Focus

1. A file that is not a sweep (binary, empty, a CSV of something else, a path that does not exist) among several selected: refused with its name and reason, the others load. Test: Task 4 `test_loading_files_good_and_bad`.
2. Reference and trace on different frequency grids, or the trace reaching beyond the reference: interpolated inside, nothing drawn outside, no extrapolation. Test: Task 2 `test_relative_*`.
3. A reference with a dead point (|H| = 0, NaN) or a theory curve with a zero denominator at some frequency: that frequency is skipped, nothing divides by zero. Test: Task 2 `test_relative_skips_unusable_reference_values`.
4. The reference trace is removed, hidden or still being measured: removal switches the relative display off; hiding does not; a partial live reference limits the others to its range. Tests: Task 2 `test_reference_follows_removal_and_hiding`, Task 5 `test_a_new_sweep_keeps_the_other_traces`.
5. Vertical unit "Voltage": theory curves and ratios are not drawn and the box is disabled, nothing raises. Test: Task 3 `test_voltage_unit_draws_measured_traces_only`.
6. Invalid theory values (zero or negative part, text, empty or all-zero denominator): refused in the dialog with the reason, no trace added. Tests: Task 1 `test_build_refuses_bad_values`, Task 4 `test_theory_dialog_refuses_bad_values`.
7. More than eight traces: the ninth is muted, nothing raises, a freed slot is reused. Test: Task 2 `test_colour_slots`.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/bodeplot/measure/theory.py` | create | `TransferFunction`, presets, labels, part tables, `build` |
| `src/bodeplot/drivers/mock.py` | modify | `SimulatedDUT` = `TransferFunction` + input impedance |
| `src/bodeplot/traces.py` | create | `Trace`, `TraceSet`, `Drawn`, `theory_grid`, the relative maths |
| `src/bodeplot/gui/bode_plot.py` | rewrite | draws a `TraceSet`; "Relative to" box; read-out, fit view, export series |
| `src/bodeplot/gui/dialogs.py` | modify | `TransferFunctionForm` (shared), `TheoryDialog`; `SimSettingsPanel` uses the form |
| `src/bodeplot/gui/traces_panel.py` | create | the Traces dock |
| `src/bodeplot/gui/main_window.py` | modify | the dock, its wiring, span hint, image export |
| `src/bodeplot/io/export_image.py` | modify | `ImageSeries`; draws several series with a legend |
| `tests/test_theory.py`, `tests/test_traces.py`, `tests/test_gui_traces.py` | create | tests |
| `docs/ARCHITECTURE.md`, `docs/spec/gui.md`, `docs/spec/roadmap.md`, `docs/STATE.md`, `README.md` | modify | documentation |

---

### Task 1: Transfer functions in their own module

**Files:**
- Create: `src/bodeplot/measure/theory.py`, `tests/test_theory.py`
- Modify: `src/bodeplot/drivers/mock.py` (class `SimulatedDUT`), `src/bodeplot/gui/dialogs.py` (`SIM_PARAMS`, `SIM_LABELS`), `docs/ARCHITECTURE.md`

**Interfaces:**
- Produces, in `bodeplot.measure.theory`:
  - `TransferFunction(name="through", num=(1.0,), den=(1.0,), params={})` dataclass with `h(freq_hz) -> complex`, classmethods `through()`, `rc_lpf(r, c)`, `rc_hpf(r, c)`, `rlc_bpf(r, l, c)`, `rlc_notch(r, l, c)`, `butter2_lpf(fc)`, `custom(num, den)`, `from_preset(name, **kw)`, class attribute `PRESETS`, method `label() -> str`
  - `PARAMS: dict[str, dict[str, tuple[float, str]]]`, `LABELS: dict[str, str]`
  - `build(name: str, params: dict) -> TransferFunction` (raises `ValueError` with a message for the user)
- `bodeplot.drivers.mock.SimulatedDUT` keeps every constructor, `PRESETS`, `from_preset`, `h`, `name`, `params` and `input_impedance_ohm`; it is now a subclass of `TransferFunction`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_theory.py`:

```python
"""Transfer functions of ideal circuits (measure/theory.py)."""
import cmath
import math

import pytest

from bodeplot.drivers.mock import SimulatedDUT
from bodeplot.measure import theory
from bodeplot.measure.theory import TransferFunction

FREQS = (10.0, 1e3, 1.59e3, 1e5, 2e7)


def test_presets_match_their_formulas():
    r, l, c = 1e3, 1e-3, 100e-9
    for f in FREQS:
        s = 2j * math.pi * f
        assert TransferFunction.through().h(f) == 1.0
        assert TransferFunction.rc_lpf(r, c).h(f) == pytest.approx(1 / (1 + s * r * c))
        assert TransferFunction.rc_hpf(r, c).h(f) == pytest.approx(s * r * c / (1 + s * r * c))
        den = s * s * l * c + s * r * c + 1
        assert TransferFunction.rlc_bpf(r, l, c).h(f) == pytest.approx(s * r * c / den)
        assert TransferFunction.rlc_notch(r, l, c).h(f) == pytest.approx((s * s * l * c + 1) / den)
    b = TransferFunction.butter2_lpf(10e3).h(10e3)
    assert abs(b) == pytest.approx(1 / math.sqrt(2)) and math.degrees(cmath.phase(b)) == pytest.approx(-90.0)


def test_custom_and_from_preset():
    tf = TransferFunction.custom([1], [1e-4, 1])
    assert tf.name == "custom" and tf.h(1e3) == pytest.approx(1 / (1 + 2j * math.pi * 1e3 * 1e-4))
    assert tf.params == {"num": [1.0], "den": [1e-4, 1.0]}
    assert TransferFunction.from_preset("rc_lpf", r=2e3, c=1e-9).params == {"r": 2e3, "c": 1e-9}
    with pytest.raises(ValueError):
        TransferFunction.from_preset("nonsense")
    assert TransferFunction.custom([1], [0.0, 0.0]).h(1e3) == complex("inf")       # no exception


def test_labels_name_the_circuit_and_its_values():
    assert TransferFunction.rc_lpf(1e3, 100e-9).label() == "RC low-pass 1 kΩ 100 nF"
    assert TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9).label() == "RLC band-pass 100 Ω 1 mH 100 nF"
    assert TransferFunction.butter2_lpf(10e3).label() == "Butterworth low-pass, 2nd order 10 kHz"
    assert TransferFunction.custom([1], [1, 1]).label() == "Custom H(s)"
    assert TransferFunction.through().label() == "Through (wire)"
    assert set(theory.PARAMS) == set(theory.LABELS) == set(TransferFunction.PRESETS)


def test_build_makes_a_transfer_function_from_entered_values():
    tf = theory.build("rc_hpf", {"r": 997.8, "c": 98.2e-9})
    assert tf.name == "rc_hpf" and tf.params == {"r": 997.8, "c": 98.2e-9}
    assert theory.build("custom", {"num": [1, 0], "den": [1, 2, 3]}).den == (1.0, 2.0, 3.0)
    assert theory.build("through", {}).h(5.0) == 1.0


@pytest.mark.parametrize("name, params, word", [
    ("rc_lpf", {"r": 0.0, "c": 1e-9}, "positive"),
    ("rc_lpf", {"r": -5.0, "c": 1e-9}, "positive"),
    ("rc_lpf", {"r": float("nan"), "c": 1e-9}, "positive"),
    ("rc_lpf", {"r": 1e3}, "missing"),
    ("rlc_bpf", {"r": 1.0, "l": 1e-3, "c": "x"}, "number"),
    ("custom", {"num": [], "den": [1]}, "coefficient"),
    ("custom", {"num": [1], "den": [0, 0]}, "coefficient"),
    ("custom", {"num": [1]}, "coefficient"),
    ("nonsense", {}, "unknown")])
def test_build_refuses_bad_values(name, params, word):
    with pytest.raises(ValueError, match=word):
        theory.build(name, params)


def test_simulated_dut_is_a_transfer_function_with_a_load():
    dut = SimulatedDUT.rc_lpf(1e3, 100e-9)
    assert isinstance(dut, TransferFunction) and type(dut) is SimulatedDUT
    assert dut.input_impedance_ohm == 1e9 and dut.name == "rc_lpf"
    assert dut.h(1e3) == TransferFunction.rc_lpf(1e3, 100e-9).h(1e3)
    assert type(SimulatedDUT.from_preset("custom", num=[1], den=[1e-4, 1])) is SimulatedDUT
    assert SimulatedDUT.PRESETS == TransferFunction.PRESETS
    assert SimulatedDUT("x", (1.0,), (1.0,), input_impedance_ohm=50.0).input_impedance_ohm == 50.0
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_theory.py`
Expected: collection error, `No module named 'bodeplot.measure.theory'`.

- [ ] **Step 3: Implement**

Create `src/bodeplot/measure/theory.py`:

```python
"""Transfer functions of ideal circuits (SPEC.md section 9.5). No Qt, no instrument.

Used twice: as the DUT of Simulation mode (drivers/mock.py adds the load on the source)
and as the theory curves of the Bode plot (traces.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..units import fmt_si

# preset -> {part: (default value, label of its entry field)}
PARAMS: dict[str, dict[str, tuple[float, str]]] = {
    "through": {},
    "rc_lpf": {"r": (1e3, "R (Ω)"), "c": (100e-9, "C (F)")},
    "rc_hpf": {"r": (1e3, "R (Ω)"), "c": (100e-9, "C (F)")},
    "rlc_bpf": {"r": (100.0, "R (Ω)"), "l": (1e-3, "L (H)"), "c": (100e-9, "C (F)")},
    "rlc_notch": {"r": (100.0, "R (Ω)"), "l": (1e-3, "L (H)"), "c": (100e-9, "C (F)")},
    "butter2_lpf": {"fc": (10e3, "Cutoff (Hz)")},
    "custom": {},
}
LABELS: dict[str, str] = {
    "through": "Through (wire)", "rc_lpf": "RC low-pass", "rc_hpf": "RC high-pass",
    "rlc_bpf": "RLC band-pass", "rlc_notch": "RLC notch",
    "butter2_lpf": "Butterworth low-pass, 2nd order", "custom": "Custom H(s)"}
PART_UNITS = {"r": "Ω", "l": "H", "c": "F", "fc": "Hz"}


@dataclass
class TransferFunction:
    """H(s) = num(s) / den(s), coefficients highest power first."""
    name: str = "through"
    num: tuple[float, ...] = (1.0,)
    den: tuple[float, ...] = (1.0,)
    params: dict = field(default_factory=dict)

    def h(self, freq_hz: float) -> complex:
        s = 2j * math.pi * freq_hz
        n = sum(c * s ** (len(self.num) - 1 - i) for i, c in enumerate(self.num))
        d = sum(c * s ** (len(self.den) - 1 - i) for i, c in enumerate(self.den))
        return n / d if d != 0 else complex("inf")

    def label(self) -> str:
        """Name for a trace: the circuit and its part values, e.g. 'RC low-pass 1 kΩ 100 nF'."""
        parts = " ".join(fmt_si(self.params[k], PART_UNITS[k]) for k in PARAMS.get(self.name, {})
                         if k in self.params)
        return (LABELS.get(self.name, self.name) + " " + parts).strip()

    # ---- presets
    @classmethod
    def through(cls):
        return cls("through")

    @classmethod
    def rc_lpf(cls, r: float = 1e3, c: float = 100e-9):
        return cls("rc_lpf", (1.0,), (r * c, 1.0), params=dict(r=r, c=c))

    @classmethod
    def rc_hpf(cls, r: float = 1e3, c: float = 100e-9):
        return cls("rc_hpf", (r * c, 0.0), (r * c, 1.0), params=dict(r=r, c=c))

    @classmethod
    def rlc_bpf(cls, r: float = 100.0, l: float = 1e-3, c: float = 100e-9):
        """Series L-C, output across R:  H = sRC / (s^2 LC + sRC + 1).  Q = sqrt(L/C)/R."""
        return cls("rlc_bpf", (r * c, 0.0), (l * c, r * c, 1.0), params=dict(r=r, l=l, c=c))

    @classmethod
    def rlc_notch(cls, r: float = 100.0, l: float = 1e-3, c: float = 100e-9):
        """Series R, output across series L-C:  H = (s^2 LC + 1) / (s^2 LC + sRC + 1)."""
        return cls("rlc_notch", (l * c, 0.0, 1.0), (l * c, r * c, 1.0), params=dict(r=r, l=l, c=c))

    @classmethod
    def butter2_lpf(cls, fc: float = 10e3):
        w = 2 * math.pi * fc
        return cls("butter2_lpf", (w * w,), (1.0, math.sqrt(2.0) * w, w * w), params=dict(fc=fc))

    @classmethod
    def custom(cls, num, den):
        num, den = [float(x) for x in num], [float(x) for x in den]
        return cls("custom", tuple(num), tuple(den), params=dict(num=num, den=den))

    PRESETS = ("through", "rc_lpf", "rc_hpf", "rlc_bpf", "rlc_notch", "butter2_lpf", "custom")

    @classmethod
    def from_preset(cls, name: str, **kw):
        if name not in cls.PRESETS:
            raise ValueError(f"unknown DUT preset {name!r}")
        return getattr(cls, name)(**kw)


def build(name: str, params: dict) -> TransferFunction:
    """A transfer function from values a user entered. Raises ValueError with a text for
    the user: a part that is missing, not a number or not positive; coefficients that
    leave no transfer function."""
    if name not in TransferFunction.PRESETS:
        raise ValueError("unknown circuit %r" % name)
    try:
        if name == "custom":
            num = [float(x) for x in params.get("num", [])]
            den = [float(x) for x in params.get("den", [])]
            if not num or not den or not any(den) or not all(math.isfinite(x) for x in num + den):
                raise ValueError("numerator and denominator need at least one coefficient, and the "
                                 "denominator one that is not zero")
            return TransferFunction.custom(num, den)
        values = {k: float(params[k]) for k in PARAMS[name]}
    except KeyError as e:
        raise ValueError("a value is missing: %s" % e.args[0]) from None
    except TypeError:
        raise ValueError("every value must be a number") from None
    except ValueError as e:
        if "coefficient" in str(e):
            raise
        raise ValueError("every value must be a number") from None
    if any(not math.isfinite(v) or v <= 0 for v in values.values()):
        raise ValueError("component values must be positive")
    return TransferFunction.from_preset(name, **values)
```

`src/bodeplot/drivers/mock.py`: add `from ..measure.theory import TransferFunction` to the imports, and replace the whole `class SimulatedDUT` (from its `@dataclass` line to the end of `from_preset`) with:

```python
@dataclass
class SimulatedDUT(TransferFunction):
    """The DUT of Simulation mode: a transfer function (measure/theory.py) plus the load
    it puts on the source."""
    input_impedance_ohm: float = 1e9        # loads the source (50 ohm) at the ref node
```

Remove `field` from the `dataclasses` import of `mock.py` if nothing else there uses it.

`src/bodeplot/gui/dialogs.py`: add `theory` to `from ..measure import skew` (`from ..measure import skew, theory`) and replace the two dict literals `SIM_PARAMS = {...}` and `SIM_LABELS = {...}` with:

```python
SIM_PARAMS, SIM_LABELS = theory.PARAMS, theory.LABELS      # the simulated DUT's circuits (measure/theory.py)
```

`docs/ARCHITECTURE.md`, Modules table: add a row for `measure/theory.py` ("transfer functions of ideal circuits: the simulated DUT and the theory curves", imports `units.py`), and add `measure/theory.py` to the Imports cells of `drivers/mock.py` and `gui/dialogs.py`. Run the guard to check the wording of the cells.

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python -m pytest tests\test_theory.py` — expected `14 passed`.
Run: `.venv\Scripts\python -m pytest` — expected `363 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src tests docs
git commit -m "Transfer functions of ideal circuits move out of the simulator into measure/theory.py"
```

---

### Task 2: The trace model (`traces.py`)

**Files:**
- Create: `src/bodeplot/traces.py`, `tests/test_traces.py`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: `TransferFunction` (Task 1), `PointResult`, `SweepResult`.
- Produces, in `bodeplot.traces`:
  - `Trace` dataclass: `id: int`, `kind: str` ("live" | "kept" | "file" | "theory"), `name: str`, `slot: int | None` (colour slot 0..7, `None` = muted), `visible: bool`, `points: list[PointResult]`, `theory: TransferFunction | None`, `path: str | None`, property `removable`
  - `Drawn` dataclass: `trace`, `freqs: list[float]`, `h: list[complex]`, `points: list[PointResult] | None` (aligned with `freqs`; `None` for a theory trace)
  - `TraceSet`: attributes `live: Trace`, `traces: list[Trace]`, `reference_id: int | None`; methods `get(id)`, `reference()`, `add_file(result, path) -> Trace`, `add_theory(tf) -> Trace`, `set_theory(id, tf)`, `keep_live(now=None) -> Trace`, `remove(id)`, `rename(id, name) -> str`, `set_visible(id, on)`, `set_reference(id | None)`, `span(hint=None) -> tuple[float, float] | None`, `drawn(span_hint=None, relative=True) -> list[Drawn]`
  - `theory_grid(lo, hi, per_decade=50) -> list[float]`, constants `SLOTS = 8`, `KIND_TEXT`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_traces.py`:

```python
"""The trace model of the Bode plot (traces.py): no Qt, no hardware."""
import cmath
import math
from datetime import datetime

import pytest

from bodeplot.measure.theory import TransferFunction
from bodeplot.models import Flag, PointResult, SweepResult
from bodeplot.traces import SLOTS, TraceSet, theory_grid


def point(f, h, flags=Flag.NONE, vdut=0.1):
    gain = 20 * math.log10(abs(h)) if h == h and abs(h) > 0 else float("-inf")
    return PointResult(freq_hz=f, h=h, gain_db=gain, phase_deg=math.degrees(cmath.phase(h)) if h == h else 0.0,
                       vref_amp=0.5, vdut_amp=vdut, vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1,
                       snr_ref_db=50.0, snr_dut_db=50.0, flags=flags, duration_s=0.1)


def sweep_of(tf, freqs, scale=1.0):
    return [point(f, scale * tf.h(f)) for f in freqs]


def result_of(points):
    return SweepResult({}, list(points), {})


RC = TransferFunction.rc_lpf(1e3, 100e-9)
DECADES = [10.0 ** (1 + i / 4) for i in range(21)]          # 10 Hz to 1 MHz, 4 per decade


# ------------------------------------------------------------------ the set
def test_a_new_set_holds_only_the_live_trace():
    ts = TraceSet()
    assert [t.kind for t in ts.traces] == ["live"] and ts.live.slot == 0 and ts.live.name == "Sweep"
    assert not ts.live.removable and ts.reference() is None and ts.drawn() == []
    with pytest.raises(ValueError):
        ts.remove(ts.live.id)
    with pytest.raises(ValueError):
        ts.keep_live()                                          # nothing to keep yet


def test_keep_file_theory_rename_remove():
    ts = TraceSet()
    ts.live.points = sweep_of(RC, DECADES)
    kept = ts.keep_live(now=datetime(2026, 10, 7, 12, 34, 56))
    assert kept.kind == "kept" and kept.name == "Sweep 12:34:56" and kept.points == ts.live.points
    assert kept.points is not ts.live.points                    # a copy: a new sweep does not change it
    f1 = ts.add_file(result_of(sweep_of(RC, DECADES)), r"C:\data\filter.csv")
    f2 = ts.add_file(result_of(sweep_of(RC, DECADES)), r"C:\other\filter.csv")
    assert (f1.name, f2.name, f1.kind, f1.path) == ("filter", "filter (2)", "file", r"C:\data\filter.csv")
    th = ts.add_theory(RC)
    assert th.kind == "theory" and th.name == "RC low-pass 1 kΩ 100 nF" and th.points == []
    assert ts.rename(f2.id, "  filter ") == "filter (2)"          # the name of another trace: made unique again
    assert ts.rename(f2.id, "board B") == "board B" and ts.rename(f2.id, "   ") == "board B"
    assert ts.rename(f2.id, "board B") == "board B"              # its own name is not a clash
    ts.set_theory(th.id, TransferFunction.rc_lpf(2e3, 100e-9))
    assert th.name == "RC low-pass 2 kΩ 100 nF"                  # an automatic name follows the values
    ts.rename(th.id, "ideal")
    ts.set_theory(th.id, RC)
    assert th.name == "ideal" and th.theory is RC                # a name the user gave stays
    ts.remove(f1.id)
    assert ts.get(f1.id) is None and [t.name for t in ts.traces] == ["Sweep", "Sweep 12:34:56", "board B", "ideal"]


def test_colour_slots():
    ts = TraceSet()
    made = [ts.add_theory(RC) for _ in range(9)]
    assert [t.slot for t in made] == [1, 2, 3, 4, 5, 6, 7, None, None]    # eight colours, the rest muted
    assert SLOTS == 8
    ts.remove(made[2].id)
    assert ts.add_theory(RC).slot == 3                           # the lowest free slot is reused
    assert ts.live.slot == 0


def test_files_without_complex_values_and_without_points():
    ts = TraceSet()
    nan = complex(float("nan"), float("nan"))
    old = [point(100.0, nan), point(1e3, nan)]
    old[0].gain_db, old[0].phase_deg = -1.0, -10.0
    old[1].gain_db, old[1].phase_deg = -3.0, -45.0
    t = ts.add_file(result_of(old), "old.csv")
    assert [abs(p.h) for p in t.points] == pytest.approx([10 ** (-1 / 20), 10 ** (-3 / 20)])
    assert math.degrees(cmath.phase(t.points[1].h)) == pytest.approx(-45.0)
    assert math.isnan(old[0].h.real)                             # the loaded result itself is not changed
    with pytest.raises(ValueError, match="no sweep points"):
        ts.add_file(result_of([]), "empty.csv")
    dead = [point(100.0, nan)]
    dead[0].gain_db = float("nan")
    with pytest.raises(ValueError, match="no sweep points"):
        ts.add_file(result_of(dead), "dead.csv")
    assert len(ts.traces) == 2


# ------------------------------------------------------------------ what is drawn
def test_absolute_drawing_and_visibility():
    ts = TraceSet()
    ts.live.points = sweep_of(RC, DECADES) + [point(5e6, 0j), point(0.0, 1 + 0j)]
    th = ts.add_theory(RC)
    live, theory = ts.drawn()
    assert live.trace is ts.live and live.freqs == DECADES and live.points == ts.live.points[:21]
    assert live.h == [p.h for p in live.points]                  # a dead point and f = 0 are left out
    assert theory.trace is th and theory.points is None
    assert theory.freqs == theory_grid(10.0, 5e6) and theory.h[0] == RC.h(10.0)
    ts.set_visible(ts.live.id, False)
    assert [d.trace for d in ts.drawn()] == [th]


def test_theory_grid_and_span():
    g = theory_grid(10.0, 1e6)
    assert g[0] == 10.0 and g[-1] == pytest.approx(1e6) and len(g) == 251      # 50 per decade
    assert theory_grid(5.0, 5.0) == [5.0] and theory_grid(0.0, 10.0) == []
    ts = TraceSet()
    th = ts.add_theory(RC)
    assert ts.span() is None and ts.drawn()[0].freqs == []       # nothing to span: nothing drawn
    assert ts.span((50.0, 2e7)) == (50.0, 2e7)
    assert ts.drawn(span_hint=(50.0, 2e7))[0].freqs[0] == 50.0
    ts.live.points = sweep_of(RC, [20.0, 1e3])
    hidden = ts.add_file(result_of(sweep_of(RC, [1e3, 5e7])), "wide.csv")
    ts.set_visible(hidden.id, False)
    assert ts.span((50.0, 2e7)) == (20.0, 5e7)                   # the sweep settings and every measured trace
    assert th.points == []


def test_relative_on_the_same_grid_is_exact():
    ts = TraceSet()
    ts.live.points = sweep_of(RC, DECADES, scale=1.1)
    ref = ts.add_file(result_of(sweep_of(RC, DECADES)), "ref.csv")
    ts.set_reference(ref.id)
    live, zero = ts.drawn()
    assert all(h == pytest.approx(1.1) for h in live.h) and live.freqs == DECADES
    assert zero.trace is ref and zero.h == [1 + 0j] * 21 and zero.points == ref.points
    assert ts.drawn(relative=False)[0].h[0] == ts.live.points[0].h   # the plot can ask for the plain values


def test_relative_interpolates_and_never_extrapolates():
    ts = TraceSet()
    fine = [10.0 ** (2 + i / 20) for i in range(41)]              # 100 Hz to 10 kHz
    ref = ts.add_file(result_of(sweep_of(RC, fine)), "ref.csv")
    ts.live.points = sweep_of(RC, [50.0, 99.95, 150.0, 1234.0, 9999.0, 10005.0, 20000.0])
    ts.set_reference(ref.id)
    live = ts.drawn()[0]
    assert live.freqs == [99.95, 150.0, 1234.0, 9999.0, 10005.0]   # inside, or within 0.1 % of an end
    assert [p.freq_hz for p in live.points] == live.freqs
    for h in live.h:                                               # the same filter: ratio 1 within the interpolation
        assert abs(h) == pytest.approx(1.0, abs=2e-3) and abs(math.degrees(cmath.phase(h))) < 0.05


def test_relative_to_a_theory_curve_is_evaluated_exactly():
    ts = TraceSet()
    ts.live.points = sweep_of(RC, [37.0, 1591.5, 3.3e6], scale=0.5)
    th = ts.add_theory(RC)
    ts.set_reference(th.id)
    live, zero = ts.drawn()
    assert live.freqs == [37.0, 1591.5, 3.3e6] and all(h == pytest.approx(0.5) for h in live.h)
    assert zero.trace is th and all(h == 1 + 0j for h in zero.h) and zero.points is None


def test_relative_phase_across_the_wrap():
    ts = TraceSet()
    ref = ts.add_file(result_of([point(f, cmath.rect(1.0, math.radians(a)))
                                 for f, a in ((100.0, 170.0), (1000.0, -170.0))]), "ref.csv")
    ts.live.points = [point(316.2278, cmath.rect(2.0, math.radians(-175.0)))]
    ts.set_reference(ref.id)
    h = ts.drawn()[0].h[0]
    # the reference goes from 170 to 190 degrees: 180 half way (in log f), not 0
    assert abs(h) == pytest.approx(2.0) and math.degrees(cmath.phase(h)) == pytest.approx(5.0, abs=0.01)


def test_relative_skips_unusable_reference_values():
    ts = TraceSet()
    nan = complex(float("nan"), 0.0)
    ref = ts.add_file(result_of([point(100.0, 1 + 0j), point(200.0, 0j), point(300.0, nan), point(400.0, 1 + 0j)]),
                      "ref.csv")
    assert [p.freq_hz for p in ref.points] == [100.0, 400.0]       # unusable points are not kept at all
    ts.live.points = [point(150.0, 1 + 0j), point(250.0, 2 + 0j)]
    ts.set_reference(ref.id)
    assert ts.drawn()[0].freqs == [150.0, 250.0] and ts.drawn()[0].h[1] == pytest.approx(2.0)
    no_h = ts.add_theory(TransferFunction.custom([1.0], [0.0]))    # a denominator of zero: H is infinite everywhere
    ts.set_reference(no_h.id)
    live = ts.drawn()[0]
    assert live.trace is ts.live and live.freqs == [] and live.h == []      # nothing to divide by: nothing drawn
    assert ts.drawn()[-1].freqs == []                              # and the reference has no line of its own


def test_reference_follows_removal_and_hiding():
    ts = TraceSet()
    ts.live.points = sweep_of(RC, DECADES)
    th = ts.add_theory(RC)
    ts.set_reference(th.id)
    ts.set_visible(th.id, False)
    assert ts.reference() is th and [d.trace for d in ts.drawn()] == [ts.live]     # still relative, no zero line
    assert ts.drawn()[0].h[0] == pytest.approx(1.0)
    ts.remove(th.id)
    assert ts.reference() is None and ts.reference_id is None
    assert ts.drawn()[0].h[0] == ts.live.points[0].h
    ts.set_reference(12345)                                        # an id that does not exist
    assert ts.reference() is None
    kept = ts.keep_live()
    ts.set_reference(ts.live.id)                                   # the live sweep as reference, half measured
    ts.live.points = ts.live.points[:5]
    assert ts.drawn()[1].trace is kept and len(ts.drawn()[1].freqs) == 5
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_traces.py`
Expected: collection error, `No module named 'bodeplot.traces'`.

- [ ] **Step 3: Implement**

Create `src/bodeplot/traces.py`:

```python
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
```

`docs/ARCHITECTURE.md`: add a row for `traces.py` next to `models.py` ("the traces of the Bode plot and the relative-to maths", imports `measure/theory.py`, `models.py`).

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python -m pytest tests\test_traces.py` — expected `12 passed`.
Run: `.venv\Scripts\python -m pytest` — expected `375 passed`.

If `test_files_without_complex_values_and_without_points` fails on `add_file` keeping a dead point: `add_file` drops points whose H is unusable AND whose gain or phase is not finite; a point with H = 0 and gain −inf is dropped by the same rule.

- [ ] **Step 5: Commit**

```powershell
git add src tests docs
git commit -m "Trace model: live, kept, file and theory traces, colour slots, drawing relative to a reference"
```

---

### Task 3: The plot draws a trace set

**Files:**
- Rewrite: `src/bodeplot/gui/bode_plot.py`
- Modify: `src/bodeplot/io/export_image.py` (add `ImageSeries` only; the drawing comes in Task 5), `tests/test_gui.py` (one line), `docs/ARCHITECTURE.md`
- Create: `tests/test_gui_traces.py`

**Interfaces:**
- Consumes: `TraceSet`, `Drawn` (Task 2).
- Produces:
  - `bodeplot.io.export_image.ImageSeries` dataclass: `name: str`, `slot: int | None`, `freqs`, `gain`, `phase` (numpy arrays), `flagged` (bool array, or `None` for a line without markers)
  - `BodePlot(traces: TraceSet | None = None, parent=None)`; attribute `set: TraceSet`; unchanged: `add_point`, `set_points`, `points`, `clear` (all on the live trace), `unit`, `set_unit`, `value`, `value_text`, `unwrap`, `set_unwrap`, `set_log_x`, `set_has_phase`, `fit_view`, `data_ranges`, `view_ranges`, `refresh`, `follow`, `remeasure_enabled`, `remeasure_requested`, `unit_box`, `unwrap_box`, `fit_btn`, `readout`, `gain_plot`, `phase_plot`
  - new: `ref_box: QComboBox`, `traces_changed()`, `set_span_hint(lo, hi)`, `is_relative() -> bool`, `items(trace) -> object with gain_line, phase_line, gain_ok, phase_ok, gain_bad, phase_bad` (scatter attributes are `None` for a theory trace), `readout_at(freq_hz, y=None, phase_plot=False) -> str`, `export_series() -> tuple[list[ImageSeries], tuple[str, str, str]]` (series; gain axis label, phase axis label, note)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gui_traces.py`:

```python
"""Traces on the plot: the plot widget, the Traces panel, the main window (offscreen)."""
import cmath
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from bodeplot.gui import theme
from bodeplot.gui.bode_plot import BodePlot
from bodeplot.measure.theory import TransferFunction
from bodeplot.models import Flag, PointResult, SweepResult
from bodeplot.traces import TraceSet

RC = TransferFunction.rc_lpf(1e3, 100e-9)
FREQS = [10.0 ** (2 + i / 5) for i in range(21)]                 # 100 Hz to 1 MHz


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
    return p


def line_y(plot, trace, which="gain_line"):
    y = getattr(plot.items(trace), which).getData()[1]             # None when the line is empty
    return np.array([] if y is None else y, dtype=float)


# ---------------------------------------------------------------------- the plot widget
def test_plot_with_only_the_live_trace_is_as_before(plot):
    assert plot.ref_box.count() == 1 and plot.ref_box.itemText(0) == "nothing" and not plot.is_relative()
    plot.set_points(sweep())
    assert plot.points() == plot.set.live.points and len(plot.points()) == 21
    y = line_y(plot, plot.set.live)
    assert y[0] == pytest.approx(plot.points()[0].gain_db) and len(y) == 21
    assert "Gain" in plot.gain_plot.getAxis("left").labelString()
    assert "difference" not in plot.gain_plot.getAxis("left").labelString()
    text = plot.readout_at(1000.0)
    assert text.startswith("1 kHz") and "gain" in text and "phase" in text and "Sweep" not in text
    plot.clear()
    assert plot.points() == [] and len(line_y(plot, plot.set.live)) == 0


def test_theory_and_file_traces_are_drawn_in_their_slot_colours(plot):
    plot.set_span_hint(50.0, 2e7)
    plot.set_points(sweep())
    th = plot.set.add_theory(RC)
    bad = sweep(scale=0.9)
    bad[3].flags |= Flag.LOW_SNR
    f = plot.set.add_file(SweepResult({}, bad, {}), "board.csv")
    plot.traces_changed()
    assert [plot.ref_box.itemText(i) for i in range(plot.ref_box.count())] == [
        "nothing", "Sweep", "RC low-pass 1 kΩ 100 nF", "board"]
    y = line_y(plot, th)
    assert len(y) > 250 and y[0] == pytest.approx(20 * math.log10(abs(RC.h(50.0))))      # 50 Hz to 20 MHz, smooth
    assert plot.items(th).gain_ok is None                        # a theory curve has no markers
    assert plot.items(th).gain_line.opts["pen"].color().name() == theme.SERIES[1]
    assert plot.items(f).gain_line.opts["pen"].color().name() == theme.SERIES[2]
    assert len(plot.items(f).gain_bad.points()) == 1 and len(plot.items(f).gain_ok.points()) == 20
    (x0, x1), _g, _p = plot.data_ranges()
    assert x0 < math.log10(50.0) + 0.05 and x1 > math.log10(2e7) - 0.05      # fit view covers every trace
    plot.set.set_visible(th.id, False)
    plot.traces_changed()
    assert len(line_y(plot, th)) == 0
    plot.set.remove(th.id)
    plot.traces_changed()
    with pytest.raises(KeyError):
        plot.items(th)


def test_relative_to_a_theory_curve(plot):
    plot.set_points(sweep(scale=10 ** (-0.06 / 20)))             # the hand comparison: a steady -0.06 dB
    th = plot.set.add_theory(RC)
    plot.traces_changed()
    plot.ref_box.setCurrentIndex(plot.ref_box.findData(th.id))
    plot.ref_box.activated.emit(plot.ref_box.currentIndex())
    assert plot.is_relative() and plot.set.reference() is th
    assert line_y(plot, plot.set.live) == pytest.approx(np.full(21, -0.06), abs=1e-9)
    assert line_y(plot, plot.set.live, "phase_line") == pytest.approx(np.zeros(21), abs=1e-9)
    assert line_y(plot, th) == pytest.approx(0.0, abs=1e-12)     # the reference is the zero line
    assert "Gain difference" in plot.gain_plot.getAxis("left").labelString()
    assert "Phase difference" in plot.phase_plot.getAxis("left").labelString()
    text = plot.readout_at(1000.0, y=-0.06)
    assert "Sweep" in text and "difference" in text and "relative to RC low-pass 1 kΩ 100 nF" in text
    plot.set_unit("pct")
    assert line_y(plot, plot.set.live) == pytest.approx(np.full(21, 100 * 10 ** (-0.06 / 20)))
    assert "reference" in plot.gain_plot.getAxis("left").labelString()
    plot.set.remove(th.id)
    plot.traces_changed()
    assert not plot.is_relative() and plot.ref_box.currentData() is None
    assert "Output / input" in plot.gain_plot.getAxis("left").labelString()


def test_voltage_unit_draws_measured_traces_only(plot):
    plot.set_points(sweep())
    th = plot.set.add_theory(RC)
    plot.set.set_reference(th.id)
    plot.traces_changed()
    plot.set_unit("v")
    assert not plot.ref_box.isEnabled() and not plot.is_relative()
    assert len(line_y(plot, th)) == 0
    assert line_y(plot, plot.set.live)[0] == pytest.approx(2 * plot.points()[0].vdut_amp)
    assert "Vpp" in plot.readout_at(1000.0)
    plot.set_unit("db")
    assert plot.ref_box.isEnabled() and plot.is_relative()        # the choice comes back with the unit


def test_readout_picks_the_trace_under_the_cursor(plot):
    plot.set_points(sweep())
    low = plot.set.add_file(SweepResult({}, sweep(scale=0.1), {}), "low.csv")     # 20 dB below
    plot.traces_changed()
    at = RC.h(1000.0)
    assert plot.readout_at(1000.0, y=20 * math.log10(abs(at))).startswith("Sweep:")
    assert plot.readout_at(1000.0, y=20 * math.log10(abs(at)) - 20.0).startswith("low:")
    assert plot.readout_at(1000.0, y=math.degrees(cmath.phase(at)), phase_plot=True).startswith(("Sweep:", "low:"))
    assert plot.readout_at(-5.0) == ""


def test_export_series_is_what_the_plot_shows(plot):
    plot.set_points(sweep())
    th = plot.set.add_theory(RC)
    plot.traces_changed()
    series, labels = plot.export_series()
    assert [s.name for s in series] == ["Sweep", "RC low-pass 1 kΩ 100 nF"] and [s.slot for s in series] == [0, 1]
    assert labels == ("Gain (dB)", "Phase (deg)", "")
    assert series[0].flagged is not None and not series[0].flagged.any() and series[1].flagged is None
    assert series[0].gain[0] == pytest.approx(plot.points()[0].gain_db)
    plot.set.set_reference(th.id)
    plot.traces_changed()
    series, labels = plot.export_series()
    assert labels == ("Gain difference (dB)", "Phase difference (deg)", "relative to RC low-pass 1 kΩ 100 nF")
    assert series[0].gain == pytest.approx(0.0, abs=1e-9)
```

In `tests/test_gui.py`, in `test_vertical_unit_db_voltage_or_percent`, change the one line

```python
    y = plot.traces["sweep"].gain_line.getData()[1]
```

to

```python
    y = plot.items(plot.set.live).gain_line.getData()[1]
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_gui_traces.py`
Expected: failures (`BodePlot() takes ... positional arguments` or `'BodePlot' object has no attribute 'ref_box'`).

- [ ] **Step 3: Implement**

`src/bodeplot/io/export_image.py`: add `from typing import Any` and, below `ImageOptions`:

```python
@dataclass
class ImageSeries:
    """One trace as the plot shows it: the numbers are final (unit, unwrap, relative)."""
    name: str
    slot: int | None            # colour slot as on screen; None: muted
    freqs: Any                  # numpy arrays of equal length
    gain: Any
    phase: Any
    flagged: Any = None         # bool array (a measured trace: markers); None: a line only
```

Replace `src/bodeplot/gui/bode_plot.py` with:

```python
"""Centre: gain and phase plots, x-axes linked (SPEC.md section 10).

The widget draws a TraceSet (traces.py): the live sweep, kept sweeps, files and theory
curves, as they are or relative to one of them. It decides nothing about the traces
themselves; it asks the set what is to be drawn.
"""
from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout,
                               QWidget)

from ..io.export_image import ImageSeries
from ..measure.sinefit import unwrap_deg
from ..models import Flag, PointResult
from ..traces import Drawn, Trace, TraceSet
from ..units import fmt_si
from . import theme
from .si_widgets import SiAxis

QUIET = Flag.REMEASURED | Flag.BUILTIN | Flag.PREVIEW | Flag.CALIBRATED   # flags that do not mark a point as suspect
# Vertical unit of the upper plot: key -> (box text, axis label, axis unit, smallest span shown)
UNITS = {"db": ("dB", "Gain", "dB", 1.0),
         "v": ("Voltage", "Output", "Vpp", 0.0),
         "pct": ("% of input", "Output / input", "%", 1.0)}
# the same axis when every trace is divided by a reference
RELATIVE_LABEL = {"db": "Gain difference", "pct": "Output / reference"}
COLORS = theme.SERIES                    # fixed order, one per colour slot; never cycled


class _Items:
    """The graphics of one trace. The scatter items are None for a theory curve."""
    gain_line = phase_line = gain_ok = phase_ok = gain_bad = phase_bad = None

    def all(self):
        return [i for i in (self.gain_line, self.phase_line, self.gain_ok, self.phase_ok, self.gain_bad,
                            self.phase_bad) if i is not None]


class BodePlot(QWidget):
    remeasure_requested = Signal(float)

    def __init__(self, traces: TraceSet | None = None, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)
        self.set = traces or TraceSet()
        self.span_hint: tuple[float, float] | None = None
        self._items: dict[int, _Items] = {}
        self._shown: list[tuple[Drawn, np.ndarray, np.ndarray, np.ndarray]] = []    # trace, f, gain, phase
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.unwrap_box = QCheckBox("Unwrap phase")
        self.readout = QLabel("")
        self.readout.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.fit_btn = QPushButton("Fit view")
        self.fit_btn.setToolTip("Zoom both plots to the curves (also: double-click a plot)")
        self.unit_box = QComboBox()
        for key, (text, *_rest) in UNITS.items():
            self.unit_box.addItem(text, key)
        self.unit_box.setToolTip("Vertical scale of the upper plot: gain in dB, the DUT output voltage "
                                 "(peak to peak, at the probe tip), or the output as a percentage of the input")
        self.ref_box = QComboBox()
        self.ref_box.setMinimumWidth(140)
        self.ref_box.setToolTip("Draw every trace divided by this one: the gain difference in dB and the phase "
                                "difference in degrees. Not available with the vertical unit Voltage.")
        top.addWidget(self.unwrap_box)
        top.addWidget(self.fit_btn)
        top.addWidget(QLabel(" Vertical"))
        top.addWidget(self.unit_box)
        top.addWidget(QLabel(" Relative to"))
        top.addWidget(self.ref_box)
        top.addStretch(1)
        top.addWidget(self.readout)
        lay.addLayout(top)

        self.gain_plot = pg.PlotWidget(axisItems={"bottom": SiAxis("bottom")})
        self.phase_plot = pg.PlotWidget(axisItems={"bottom": SiAxis("bottom")})
        for p, label, unit in ((self.gain_plot, "Gain", "dB"), (self.phase_plot, "Phase", "deg")):
            p.setLabel("left", label, units=unit)
            theme.style_plot(p)
            p.getPlotItem().setMenuEnabled(False)
            # no automatic SI prefix: with a log axis it relabelled 10 kHz as "0.01" (MHz)
            p.getAxis("bottom").enableAutoSIPrefix(False)
            p.getAxis("left").enableAutoSIPrefix(False)
        self.phase_plot.setLabel("bottom", "Frequency", units="Hz")
        self.phase_plot.setXLink(self.gain_plot)
        lay.addWidget(self.gain_plot, 1)
        lay.addWidget(self.phase_plot, 1)

        self.log_x = True
        self.has_phase = True
        self.remeasure_enabled = False
        self._vlines = []
        for p in (self.gain_plot, self.phase_plot):
            v = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(theme.MUTED, style=Qt.DashLine))
            v.setVisible(False)
            p.addItem(v, ignoreBounds=True)
            self._vlines.append(v)
            p.scene().sigMouseMoved.connect(lambda pos, plot=p: self._mouse_moved(plot, pos))
        # Follow mode: the view tracks the data until the user pans or zooms by hand.
        # "Fit view", a double-click, or a new sweep switch it back on.
        self.follow = True
        for p in (self.gain_plot, self.phase_plot):
            p.getPlotItem().vb.sigRangeChangedManually.connect(self._moved_by_user)
            p.getPlotItem().hideButtons()               # the small "A" button is replaced by Fit view
            p.scene().sigMouseClicked.connect(self._scene_clicked)
        self.fit_btn.clicked.connect(self.fit_view)
        self.unwrap_box.toggled.connect(self.refresh)
        self.unit_box.currentIndexChanged.connect(lambda _i: self._unit_changed())
        self.ref_box.activated.connect(self._ref_chosen)
        self._fill_ref_box()
        self.set_log_x(True)

    # ---- vertical unit and relative display
    def unit(self) -> str:
        return self.unit_box.currentData()

    def set_unit(self, key: str) -> None:
        i = self.unit_box.findData(key)
        if i >= 0:
            self.unit_box.setCurrentIndex(i)

    def _unit_changed(self) -> None:
        axis = self.gain_plot.getAxis("left")
        axis.enableAutoSIPrefix(self.unit() == "v")     # volts read as mV, uV; dB and % stay plain
        self.ref_box.setEnabled(self.unit() != "v")     # a ratio has no voltage
        self.follow = True                              # another unit is another scale: fit it
        self.refresh()

    def is_relative(self) -> bool:
        """True when the traces are drawn divided by a reference trace."""
        return self.unit() != "v" and self.set.reference() is not None

    def _fill_ref_box(self) -> None:
        self.ref_box.blockSignals(True)
        self.ref_box.clear()
        self.ref_box.addItem("nothing", None)
        for t in self.set.traces:
            self.ref_box.addItem(t.name, t.id)
        i = self.ref_box.findData(self.set.reference_id) if self.set.reference_id is not None else 0
        self.ref_box.setCurrentIndex(max(0, i))
        self.ref_box.blockSignals(False)

    def _ref_chosen(self, index: int) -> None:
        self.set.set_reference(self.ref_box.itemData(index))
        self.follow = True                              # differences are another scale: fit it
        self.refresh()

    def traces_changed(self) -> None:
        """The set was changed from outside (the Traces panel): names, order, visibility."""
        self._fill_ref_box()
        self.refresh()

    def set_span_hint(self, lo: float, hi: float) -> None:
        """The sweep range of the panel: a theory curve is drawn at least over it."""
        hint = (float(lo), float(hi)) if lo > 0 and hi > 0 else None
        if hint != self.span_hint:
            self.span_hint = hint
            self.refresh()

    def value(self, p: PointResult) -> float:
        """What the upper plot shows for a measured point, in the selected unit (not relative)."""
        if self.unit() == "v":
            return 2.0 * p.vdut_amp
        if self.unit() == "pct":
            return 100.0 * abs(p.h)
        return p.gain_db

    def value_text(self, p: PointResult) -> str:
        return self._value_text(self.value(p), relative=False)

    def _value_text(self, y: float, relative: bool) -> str:
        if self.unit() == "v":
            return "output %s" % fmt_si(y, "Vpp", 4)
        if self.unit() == "pct":
            return "output %.4g %% of %s" % (y, "the reference" if relative else "input")
        return ("gain difference %+.3f dB" if relative else "gain %.3f dB") % y

    def _labels(self) -> tuple[str, str, str, str]:
        """(gain axis label, its unit, phase axis label, note) for what is shown now."""
        _text, label, unit, _span = UNITS[self.unit()]
        if not self.is_relative():
            return label, unit, "Phase", ""
        return RELATIVE_LABEL[self.unit()], unit, "Phase difference", "relative to " + self.set.reference().name

    # ---- view
    def _moved_by_user(self, *_):
        self.follow = False

    def _scene_clicked(self, ev):
        if ev.double():
            ev.accept()
            self.fit_view()

    def data_ranges(self):
        """((x0, x1), (gain0, gain1), (phase0, phase1)) of everything plotted, in view
        coordinates (log10 of Hz on a log axis), or None when there is no data."""
        fs, gs, ps = [], [], []
        for _d, f, gain, phase in self._shown:
            ok = np.isfinite(gain)
            fs += [float(v) for v in f[ok]]
            gs += [float(v) for v in gain[ok]]
            ps += [float(v) for v in phase if math.isfinite(v)]
        if not fs:
            return None
        x = np.log10(fs) if self.log_x else np.array(fs)

        def span(v, pad, min_span):
            lo, hi = float(min(v)), float(max(v))
            if hi - lo < min_span:
                mid = (lo + hi) / 2
                lo, hi = mid - min_span / 2, mid + min_span / 2
            d = (hi - lo) * pad
            return lo - d, hi + d
        g_span = UNITS[self.unit()][3] or max(1e-9, 0.05 * max(abs(v) for v in gs))
        return (span(x, 0.03, 0.2 if self.log_x else max(1e-9, abs(float(x[0])) * 0.01)),
                span(gs, 0.08, g_span), span(ps or [0.0], 0.08, 5.0))

    def fit_view(self) -> None:
        """Zoom both plots to the curves, and follow new points from now on."""
        self.follow = True
        r = self.data_ranges()
        if r is None:
            return
        (x0, x1), (g0, g1), (p0, p1) = r
        self.gain_plot.getPlotItem().vb.setRange(xRange=(x0, x1), yRange=(g0, g1), padding=0)
        self.phase_plot.getPlotItem().vb.setRange(xRange=(x0, x1), yRange=(p0, p1), padding=0)

    def view_ranges(self):
        g = self.gain_plot.getPlotItem().vb.viewRange()
        p = self.phase_plot.getPlotItem().vb.viewRange()
        return tuple(g[0]), tuple(g[1]), tuple(p[1])

    # ---- configuration
    def set_log_x(self, log: bool) -> None:
        self.log_x = log
        for p in (self.gain_plot, self.phase_plot):
            p.setLogMode(x=log, y=False)
        self.refresh()

    def set_has_phase(self, has: bool) -> None:
        self.has_phase = has
        self.phase_plot.setVisible(has)
        # the frequency label sits under the lower plot; without it the upper one carries it
        self.gain_plot.showLabel("bottom", not has)
        if not has:
            self.gain_plot.setLabel("bottom", "Frequency", units="Hz")
        self.unwrap_box.setVisible(has)

    def unwrap(self) -> bool:
        return self.unwrap_box.isChecked()

    def set_unwrap(self, on: bool) -> None:
        self.unwrap_box.setChecked(on)

    # ---- the live sweep (the interface the main window has always used)
    def clear(self) -> None:
        """A new sweep: the live trace is emptied; every other trace stays."""
        self.follow = True                              # a new sweep is tracked from its first point
        self.set.live.points = []
        self.refresh()

    def set_points(self, points) -> None:
        self.set.live.points = sorted(points, key=lambda p: p.freq_hz)
        self.refresh()

    def add_point(self, point: PointResult) -> None:
        pts = [p for p in self.set.live.points if abs(p.freq_hz - point.freq_hz) > 1e-9 * point.freq_hz]
        pts.append(point)
        pts.sort(key=lambda p: p.freq_hz)
        self.set.live.points = pts
        self.refresh()

    def points(self) -> list[PointResult]:
        return list(self.set.live.points)

    # ---- drawing
    def items(self, trace: Trace) -> _Items:
        """The graphics of a trace (KeyError when it has none: never drawn, or removed)."""
        return self._items[trace.id]

    def _items_for(self, trace: Trace) -> _Items:
        if trace.id in self._items:
            return self._items[trace.id]
        it = _Items()
        color = COLORS[trace.slot] if trace.slot is not None else theme.MUTED
        pen = pg.mkPen(color, width=theme.LINE_WIDTH)
        it.gain_line = self.gain_plot.plot([], [], pen=pen)
        it.phase_line = self.phase_plot.plot([], [], pen=pen)
        if trace.theory is None:
            for attr, plot, bad in (("gain_ok", self.gain_plot, False), ("phase_ok", self.phase_plot, False),
                                    ("gain_bad", self.gain_plot, True), ("phase_bad", self.phase_plot, True)):
                # ok points: series colour with a surface ring. Flagged points: status
                # colour AND a different shape, so the state never rests on colour alone.
                sc = pg.ScatterPlotItem(
                    size=theme.MARKER_FLAGGED if bad else theme.MARKER, symbol="x" if bad else "o",
                    pen=pg.mkPen(theme.FLAGGED, width=1.6) if bad else pg.mkPen(theme.SURFACE, width=theme.RING),
                    brush=pg.mkBrush(theme.FLAGGED if bad else color), hoverable=True, tip=self._tip,
                    hoverPen=pg.mkPen(theme.INK, width=1.5))
                sc.sigClicked.connect(self._clicked)
                plot.addItem(sc)
                setattr(it, attr, sc)
        self._items[trace.id] = it
        return it

    def _drop_items(self, trace_id: int) -> None:
        it = self._items.pop(trace_id)
        for item in it.all():
            (self.gain_plot if item in (it.gain_line, it.gain_ok, it.gain_bad) else self.phase_plot).removeItem(item)

    def _x(self, f):
        return np.log10(f) if self.log_x else f

    def _gain(self, d: Drawn) -> np.ndarray:
        if self.unit() == "v":
            return np.array([2.0 * p.vdut_amp for p in d.points], dtype=float)
        mag = np.abs(np.array(d.h, dtype=complex))
        return 100.0 * mag if self.unit() == "pct" else 20.0 * np.log10(mag)

    def _phase(self, d: Drawn) -> np.ndarray:
        phase = np.degrees(np.angle(np.array(d.h, dtype=complex)))
        return unwrap_deg(phase) if self.unwrap() and len(phase) else phase

    def _drawn(self) -> list[Drawn]:
        """What the set says is to be drawn, for the unit selected: with Voltage only the
        measured traces, as they are (a theory curve and a ratio have no voltage)."""
        if self.unit() == "v":
            return [d for d in self.set.drawn(self.span_hint, relative=False) if d.points is not None]
        return self.set.drawn(self.span_hint, relative=True)

    def refresh(self) -> None:
        alive = {t.id for t in self.set.traces}
        for trace_id in [k for k in self._items if k not in alive]:
            self._drop_items(trace_id)
        self._shown = []
        seen = set()
        for d in self._drawn():
            it = self._items_for(d.trace)
            seen.add(d.trace.id)
            f = np.array(d.freqs, dtype=float)
            gain, phase = self._gain(d), self._phase(d)
            self._shown.append((d, f, gain, phase))
            # pyqtgraph applies the log itself to PlotDataItem, but not to ScatterPlotItem
            it.gain_line.setData(f, gain)
            it.phase_line.setData(f, phase)
            if d.points is None:
                continue
            x = self._x(f) if len(f) else f
            bad = np.array([bool(p.flags & ~QUIET) for p in d.points], dtype=bool)
            for sc, y, mask in ((it.gain_ok, gain, ~bad), (it.phase_ok, phase, ~bad),
                                (it.gain_bad, gain, bad), (it.phase_bad, phase, bad)):
                idx = np.nonzero(mask)[0] if len(f) else []
                sc.setData([dict(pos=(float(x[i]), float(y[i])),
                                 data=(d.trace.id, d.points[i], float(gain[i]), float(phase[i]))) for i in idx])
        for trace_id, it in self._items.items():
            if trace_id not in seen:                    # hidden, or not drawn in this unit
                it.gain_line.setData([], [])
                it.phase_line.setData([], [])
                for sc in (it.gain_ok, it.phase_ok, it.gain_bad, it.phase_bad):
                    if sc is not None:
                        sc.setData([])
        gain_label, unit, phase_label, _note = self._labels()
        self.gain_plot.setLabel("left", gain_label, units=unit)
        self.phase_plot.setLabel("left", phase_label, units="deg")
        if self.follow:
            r = self.data_ranges()
            if r is not None:
                (x0, x1), (g0, g1), (p0, p1) = r
                self.gain_plot.getPlotItem().vb.setRange(xRange=(x0, x1), yRange=(g0, g1), padding=0)
                self.phase_plot.getPlotItem().vb.setRange(xRange=(x0, x1), yRange=(p0, p1), padding=0)

    def export_series(self) -> tuple[list[ImageSeries], tuple[str, str, str]]:
        """What the plot shows, for the image export: the series with their final numbers,
        and (gain axis label, phase axis label, note)."""
        series = []
        for d, f, gain, phase in self._shown:
            flagged = None if d.points is None else np.array([bool(p.flags & ~QUIET) for p in d.points], dtype=bool)
            series.append(ImageSeries(d.trace.name, d.trace.slot, f, gain, phase, flagged))
        gain_label, unit, phase_label, note = self._labels()
        return series, ("%s (%s)" % (gain_label, unit), "%s (deg)" % phase_label, note)

    # ---- interaction
    def _tip(self, x, y, data) -> str:
        trace_id, p, gain, phase = data
        trace = self.set.get(trace_id)
        flags = ", ".join(p.flags.names()) or "none"
        head = "%s\n" % trace.name if trace is not None and len(self.set.traces) > 1 else ""
        return "%s%s\n%s\nphase %.2f deg\nflags: %s" % (
            head, _fmt_hz(p.freq_hz), self._value_text(gain, self.is_relative()), phase, flags)

    def readout_at(self, freq_hz: float, y: float | None = None, phase_plot: bool = False) -> str:
        """The read-out text for the cursor at freq_hz: the nearest point of the trace that
        passes closest to y (a value of the gain plot, or of the phase plot)."""
        if not (freq_hz > 0):
            return ""
        best = None
        for d, f, gain, phase in self._shown:
            if not len(f):
                continue
            i = int(np.argmin(np.abs(np.log10(f) - math.log10(freq_hz)) if self.log_x else np.abs(f - freq_hz)))
            dist = 0.0 if y is None else abs(float((phase if phase_plot else gain)[i]) - y)
            if best is None or dist < best[0]:
                best = (dist, d, i, float(f[i]), float(gain[i]), float(phase[i]))
        if best is None:
            return _fmt_hz(freq_hz)
        _dist, d, i, f, gain, phase = best
        relative = self.is_relative()
        text = "%s   %s" % (_fmt_hz(f), self._value_text(gain, relative))
        if self.has_phase:
            text += "   phase %s%.2f°" % ("difference " if relative else "", phase)
        if d.points is not None and d.points[i].flags & ~QUIET:
            text += "   [%s]" % ", ".join(d.points[i].flags.names())
        if len(self.set.traces) > 1:                    # with one trace the read-out is as it always was
            text = "%s:   %s" % (d.trace.name, text)
        if relative:
            text += "   (relative to %s)" % self.set.reference().name
        return text

    def _mouse_moved(self, plot, pos) -> None:
        vb = plot.getPlotItem().vb
        if not plot.sceneBoundingRect().contains(pos):
            return
        at = vb.mapSceneToView(pos)
        xv = at.x()
        freq = 10 ** xv if self.log_x else xv
        for v in self._vlines:
            v.setPos(xv)
            v.setVisible(True)
        self.readout.setText(self.readout_at(freq, at.y(), plot is self.phase_plot))

    def _clicked(self, _item, spots, *_):
        if not self.remeasure_enabled or len(spots) == 0:
            return
        trace_id, p, _gain, _phase = spots[0].data()
        if trace_id != self.set.live.id:                # only the live sweep can be measured again
            return
        menu = QMenu(self)
        act = menu.addAction("Re-measure %s" % _fmt_hz(p.freq_hz))
        from PySide6.QtGui import QCursor
        if menu.exec(QCursor.pos()) is act:
            self.remeasure_requested.emit(p.freq_hz)


def _fmt_hz(f: float) -> str:
    if not math.isfinite(f) or f <= 0:
        return ""
    return fmt_si(f, "Hz")
```

`docs/ARCHITECTURE.md`: in the row of `gui/bode_plot.py` add `io/export_image.py` and `traces.py` to the Imports cell and "draws a trace set, relative display" to its description.

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python -m pytest tests\test_gui_traces.py tests\test_gui.py tests\test_docs.py` — expected all pass.
Run: `.venv\Scripts\python -m pytest` — expected `381 passed`.

Notes for a failure:
- `test_plot_with_only_the_live_trace_is_as_before`, `y[0] == approx(gain_db)`: the line is drawn from `20 log10 |h|`, which equals `gain_db` to rounding.
- `opts["pen"].color().name()` is lower-case hex, as `theme.SERIES` is written.
- The main window still calls `BodePlot()` with no argument and `plot.clear()` with none: both are valid here.

- [ ] **Step 5: Commit**

```powershell
git add src tests docs
git commit -m "The plot draws a trace set: several traces, relative to a reference, read-out per trace"
```

---

### Task 4: Theory dialog and the Traces panel

**Files:**
- Modify: `src/bodeplot/gui/dialogs.py` (`SimSettingsPanel`; add `TransferFunctionForm`, `TheoryDialog`)
- Create: `src/bodeplot/gui/traces_panel.py`
- Modify: `tests/test_gui_traces.py`, `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: `theory.build`, `theory.PARAMS`, `theory.LABELS`, `TransferFunction`, `TraceSet`, `export_csv.load_csv`.
- Produces:
  - `dialogs.TransferFunctionForm(preset="rc_lpf", params=None, title="Circuit", parent=None)` with `preset: QComboBox`, `values() -> tuple[str, dict]` (raises `ValueError` with a text for the user)
  - `dialogs.TheoryDialog(tf: TransferFunction | None = None, parent=None)` with `circuit: TransferFunctionForm`, `error: QLabel`, `tf: TransferFunction | None` (set on acceptance), `_accept()`
  - `SimSettingsPanel` keeps `preset`, `noise`, `latency`, `values()`; it gains `circuit: TransferFunctionForm`
  - `traces_panel.TracesPanel(traces: TraceSet, parent=None)`: signals `changed()`, `message(str, str)` (level, text); attributes `tree`, `load_btn`, `theory_btn`, `keep_btn`, `remove_btn`, `interactive: bool`; methods `reload()`, `refresh_buttons()`, `set_unit(unit)`, `selected_id() -> int | None`, `select(trace_id)`, `load_files(paths) -> list[str]` (the error texts), `add_theory(tf)`, `edit_theory(trace_id, tf)`, `keep()`, `remove_selected()`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gui_traces.py`:

```python
# ---------------------------------------------------------------------- theory dialog
def test_theory_dialog_builds_a_transfer_function(qtbot):
    from bodeplot.gui.dialogs import TheoryDialog
    d = TheoryDialog()
    qtbot.addWidget(d)
    assert d.circuit.preset.currentData() == "rc_lpf" and d.tf is None
    d.circuit._edits["r"].setText("997.8")
    d.circuit._edits["c"].setText("98.2n")
    d._accept()
    assert d.tf.name == "rc_lpf" and d.tf.params == pytest.approx({"r": 997.8, "c": 98.2e-9})
    again = TheoryDialog(d.tf)                                   # reopened on a trace: its values are shown
    qtbot.addWidget(again)
    assert again.circuit.preset.currentData() == "rc_lpf" and again.circuit._edits["r"].text() == "997.8"
    again.circuit.preset.setCurrentIndex(again.circuit.preset.findData("custom"))
    again.circuit.num.setText("1")
    again.circuit.den.setText("1e-4, 1")
    again._accept()
    assert again.tf.name == "custom" and again.tf.den == (1e-4, 1.0)


@pytest.mark.parametrize("preset, edits, word", [
    ("rc_lpf", {"r": "0"}, "positive"), ("rc_lpf", {"c": "-1n"}, "positive"),
    ("rc_lpf", {"r": "lots"}, "Invalid"), ("custom", {"den": "0, 0"}, "coefficient"),
    ("custom", {"num": ""}, "coefficient"), ("custom", {"den": "1, x"}, "Invalid")])
def test_theory_dialog_refuses_bad_values(qtbot, preset, edits, word):
    from bodeplot.gui.dialogs import TheoryDialog
    d = TheoryDialog()
    qtbot.addWidget(d)
    d.circuit.preset.setCurrentIndex(d.circuit.preset.findData(preset))
    for key, text in edits.items():
        (getattr(d.circuit, key) if preset == "custom" else d.circuit._edits[key]).setText(text)
    d._accept()
    assert d.tf is None and word in d.error.text() and d.result() == 0     # still open, nothing made


# ---------------------------------------------------------------------- the Traces panel
@pytest.fixture
def panel(qtbot, plot):
    from bodeplot.gui.traces_panel import TracesPanel
    p = TracesPanel(plot.set)
    p.interactive = False
    p.changed.connect(plot.traces_changed)
    p.messages = []
    p.message.connect(lambda level, text: p.messages.append((level, text)))
    qtbot.addWidget(p)
    p.show()
    return p


def rows(panel):
    return [(panel.tree.topLevelItem(i).text(0), panel.tree.topLevelItem(i).text(1))
            for i in range(panel.tree.topLevelItemCount())]


def test_panel_lists_traces_and_its_buttons_follow(panel, plot):
    assert rows(panel) == [("Sweep", "live sweep")]
    assert not panel.keep_btn.isEnabled() and not panel.remove_btn.isEnabled()
    plot.set_points(sweep())
    panel.refresh_buttons()
    assert panel.keep_btn.isEnabled()
    panel.keep()
    panel.add_theory(RC)
    assert [k for _n, k in rows(panel)] == ["live sweep", "kept sweep", "theory"]
    assert plot.ref_box.count() == 4                              # the plot was told
    panel.select(plot.set.live.id)
    assert not panel.remove_btn.isEnabled()                       # the live sweep stays
    kept = plot.set.traces[1]
    panel.select(kept.id)
    assert panel.selected_id() == kept.id and panel.remove_btn.isEnabled()
    panel.remove_selected()
    assert [k for _n, k in rows(panel)] == ["live sweep", "theory"] and plot.ref_box.count() == 3


def test_panel_ticks_and_names_edit_the_traces(panel, plot):
    from PySide6.QtCore import Qt
    plot.set_points(sweep())
    panel.add_theory(RC)
    th = plot.set.traces[1]
    item = panel.tree.topLevelItem(1)
    item.setCheckState(0, Qt.Unchecked)
    assert th.visible is False and len(line_y(plot, th)) == 0
    item.setCheckState(0, Qt.Checked)
    item.setText(0, "ideal")
    assert th.name == "ideal" and plot.ref_box.itemText(2) == "ideal"
    item.setText(0, "Sweep")                                      # the live trace's name: made unique
    assert th.name == "Sweep (2)" and panel.tree.topLevelItem(1).text(0) == "Sweep (2)"
    panel.edit_theory(th.id, TransferFunction.rc_hpf(1e3, 100e-9))
    assert th.theory.name == "rc_hpf" and th.name == "Sweep (2)"
    panel.set_unit("v")
    assert "Voltage" in panel.tree.topLevelItem(1).toolTip(0)
    panel.set_unit("db")
    assert "Voltage" not in panel.tree.topLevelItem(1).toolTip(0)


def test_loading_files_good_and_bad(panel, plot, tmp_path):
    from bodeplot.io import export_csv
    good = export_csv.write_csv(tmp_path / "board A.csv", SweepResult({}, sweep(), {}))
    old = tmp_path / "old.csv"
    old.write_text("freq_hz,gain_db,phase_deg\n100,-1.0,-10\n1000,-3.0,-45\n", encoding="utf-8")
    other = tmp_path / "shopping.csv"
    other.write_text("item,price\nmilk,1\n", encoding="utf-8")
    binary = tmp_path / "photo.csv"
    binary.write_bytes(bytes(range(256)) * 4)
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    errors = panel.load_files([str(good), str(other), str(old), str(binary), str(empty), str(tmp_path / "gone.csv")])
    assert [n for n, _k in rows(panel)] == ["Sweep", "board A", "old"]
    assert len(errors) == 4 and all(any(name in e for e in errors)
                                    for name in ("shopping.csv", "photo.csv", "empty.csv", "gone.csv"))
    assert any("no sweep points" in e for e in errors)
    assert ("info", "Loaded 2 traces.") in panel.messages
    assert sum(1 for level, _t in panel.messages if level == "warn") == 4
    assert plot.ref_box.count() == 4 and len(line_y(plot, plot.set.traces[1])) == 21
    assert panel.load_files([]) == [] and len(plot.set.traces) == 3


def test_keep_without_a_sweep_says_so(panel):
    panel.keep()
    assert panel.messages == [("warn", "Keep sweep: there is no sweep to keep.")] and len(rows(panel)) == 1
```

Also add a regression test for the simulation settings, which now share the form:

```python
def test_simulation_settings_still_use_the_same_form(qtbot):
    from bodeplot.gui.dialogs import SimSettingsPanel
    p = SimSettingsPanel({"preset": "rlc_bpf", "params": {"r": 50.0, "l": 2e-3, "c": 10e-9}, "noise_vrms": 2e-4,
                          "latency_ms": 1.0})
    qtbot.addWidget(p)
    v = p.values()
    assert v == {"preset": "rlc_bpf", "params": pytest.approx({"r": 50.0, "l": 2e-3, "c": 10e-9}),
                 "noise_vrms": pytest.approx(2e-4), "latency_ms": 1.0}
    p.preset.setCurrentIndex(p.preset.findData("rc_lpf"))
    p.circuit._edits["r"].setText("0")
    with pytest.raises(ValueError, match="positive"):
        p.values()
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_gui_traces.py`
Expected: the new tests fail (`cannot import name 'TheoryDialog'`, `No module named 'bodeplot.gui.traces_panel'`).

- [ ] **Step 3: Implement the form and the dialog**

`src/bodeplot/gui/dialogs.py`:

Imports: add `from ..measure.theory import TransferFunction`.

Remove the line `SIM_PARAMS, SIM_LABELS = theory.PARAMS, theory.LABELS ...` of Task 1 and replace the whole `class SimSettingsPanel` with:

```python
# ---------------------------------------------------------------------- circuits
class TransferFunctionForm(QWidget):
    """A circuit and its part values (measure/theory.py): the simulated DUT in the
    simulation settings, and a theory curve of the plot."""

    def __init__(self, preset: str = "rc_lpf", params: dict | None = None, title: str = "Circuit", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.preset = QComboBox()
        for name in TransferFunction.PRESETS:
            self.preset.addItem(theory.LABELS[name], name)
        form.addRow(title, self.preset)
        lay.addLayout(form)
        self.param_host = QWidget()
        self.param_form = QFormLayout(self.param_host)
        lay.addWidget(self.param_host)
        self.num = QLineEdit("1")
        self.den = QLineEdit("1e-4, 1")
        self._params_in = dict(params or {})
        self._edits: dict[str, QLineEdit] = {}
        self.preset.currentIndexChanged.connect(self._rebuild)
        self.preset.setCurrentIndex(max(0, self.preset.findData(preset)))
        self._rebuild()

    def _rebuild(self) -> None:
        while self.param_form.rowCount():
            self.param_form.removeRow(0)
        self._edits = {}
        name = self.preset.currentData()
        if name == "custom":
            self.num = QLineEdit(", ".join("%g" % x for x in self._params_in.get("num", [1.0])))
            self.den = QLineEdit(", ".join("%g" % x for x in self._params_in.get("den", [1e-4, 1.0])))
            self.param_form.addRow("Numerator (highest power first)", self.num)
            self.param_form.addRow("Denominator", self.den)
            return
        for key, (default, label) in theory.PARAMS[name].items():
            e = QLineEdit(fmt_si(float(self._params_in.get(key, default))))
            e.setToolTip("Accepts SI multipliers: 1k, 100n, 1m (M = mega, m = milli)")
            self._edits[key] = e
            self.param_form.addRow(label, e)

    def values(self) -> tuple[str, dict]:
        """(circuit, its values). Raises ValueError with a message for the user when a
        field is not usable."""
        name = self.preset.currentData()
        if name == "custom":
            params = {"num": [float(x) for x in self.num.text().replace(";", ",").split(",") if x.strip()],
                      "den": [float(x) for x in self.den.text().replace(";", ",").split(",") if x.strip()]}
        else:
            params = {k: parse_si(e.text()) for k, e in self._edits.items()}
        theory.build(name, params)                      # the one place that judges the values
        return name, params


class TheoryDialog(QDialog):
    """A theory curve for the plot: pick a circuit and enter its parts, or H(s) itself."""

    def __init__(self, tf: TransferFunction | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theory curve")
        self.resize(420, 260)
        lay = QVBoxLayout(self)
        self.circuit = TransferFunctionForm(tf.name if tf else "rc_lpf", dict(tf.params) if tf else None,
                                            "Circuit", self)
        lay.addWidget(self.circuit)
        note = QLabel("The ideal response of the circuit: no component losses, no lead inductance, no probe.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.RichText)
        lay.addWidget(self.error)
        lay.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.tf: TransferFunction | None = None

    def _accept(self) -> None:
        try:
            self.tf = theory.build(*self.circuit.values())
        except ValueError as e:
            self.tf = None
            self.error.setText(theme.status_html("critical", "Invalid value: %s" % e))
            return
        self.accept()


# ---------------------------------------------------------------------- simulation
class SimSettingsPanel(QWidget):
    def __init__(self, sim: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        self.circuit = TransferFunctionForm(sim.get("preset", "rc_lpf"), sim.get("params"), "DUT", self)
        self.preset = self.circuit.preset           # the settings dialog and its tests reach it by this name
        lay.addWidget(self.circuit)
        tail = QFormLayout()
        self.noise = QDoubleSpinBox()
        self.noise.setDecimals(3)
        self.noise.setRange(0.0, 1000.0)
        self.noise.setSuffix(" mV rms")
        self.noise.setValue(float(sim.get("noise_vrms", 1e-4)) * 1e3)
        self.latency = QDoubleSpinBox()
        self.latency.setRange(0.0, 1000.0)
        self.latency.setSuffix(" ms")
        self.latency.setValue(float(sim.get("latency_ms", 5.0)))
        tail.addRow("Noise at the scope input", self.noise)
        tail.addRow("Latency per command", self.latency)
        lay.addLayout(tail)
        lay.addStretch(1)

    def values(self) -> dict:
        """Raises ValueError with a message for the user when a field is not usable."""
        name, params = self.circuit.values()
        return {"preset": name, "params": params, "noise_vrms": self.noise.value() / 1e3,
                "latency_ms": self.latency.value()}
```

Remove `from ..drivers.mock import SimulatedDUT` from `dialogs.py` if nothing else in the file uses it (the form lists `TransferFunction.PRESETS`). The section comment `# --- simulation` that stood above the old class is replaced by the two above.

- [ ] **Step 4: Implement the panel**

Create `src/bodeplot/gui/traces_panel.py`:

```python
"""The Traces panel (SPEC.md section 10): the list of traces on the plot, and the buttons
that add and remove them. It changes the TraceSet and says so; it draws nothing."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..io import export_csv
from ..measure.theory import TransferFunction
from ..traces import KIND_TEXT, TraceSet
from . import theme
from .dialogs import TheoryDialog

NO_VOLTAGE = "Not drawn while the vertical unit is Voltage: a theory curve has no voltage."


def _swatch(color: str) -> QIcon:
    pix = QPixmap(12, 12)
    pix.fill(QColor(color))
    return QIcon(pix)


class TracesPanel(QWidget):
    changed = Signal()                  # the set was changed: the plot redraws
    message = Signal(str, str)          # level ("info" | "warn"), text: for the status log

    def __init__(self, traces: TraceSet, parent=None):
        super().__init__(parent)
        self.traces = traces
        self.interactive = True         # tests switch this off: no message boxes
        self.unit = "db"
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Trace", "Kind"])
        self.tree.setRootIsDecorated(False)
        self.tree.setToolTip("Tick a trace to show it. Double-click a name to change it; double-click the kind "
                             "of a theory curve to change its values.")
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.load_btn = QPushButton("Load CSV…")
        self.theory_btn = QPushButton("Add theory…")
        self.keep_btn = QPushButton("Keep sweep")
        self.remove_btn = QPushButton("Remove")
        self.load_btn.setToolTip("Add sweeps saved with Export > CSV as traces")
        self.theory_btn.setToolTip("Add the ideal response of a circuit")
        self.keep_btn.setToolTip("Keep the current sweep on the plot when the next one starts")
        for b in (self.load_btn, self.theory_btn, self.keep_btn, self.remove_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.load_btn.clicked.connect(self._load_clicked)
        self.theory_btn.clicked.connect(self._theory_clicked)
        self.keep_btn.clicked.connect(self.keep)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.currentItemChanged.connect(lambda *_: self.refresh_buttons())
        self.reload()

    # ---- the list
    def reload(self) -> None:
        keep = self.selected_id()
        self.tree.blockSignals(True)
        self.tree.clear()
        for t in self.traces.traces:
            item = QTreeWidgetItem([t.name, KIND_TEXT[t.kind]])
            item.setData(0, Qt.UserRole, t.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(0, Qt.Checked if t.visible else Qt.Unchecked)
            item.setIcon(0, _swatch(theme.SERIES[t.slot] if t.slot is not None else theme.MUTED))
            tip = t.path or ""
            if self.unit == "v" and t.kind == "theory":
                tip = NO_VOLTAGE
                for col in (0, 1):
                    item.setForeground(col, QBrush(QColor(theme.MUTED)))
            for col in (0, 1):
                item.setToolTip(col, tip)
            self.tree.addTopLevelItem(item)
            if t.id == keep:
                self.tree.setCurrentItem(item)
        self.tree.resizeColumnToContents(0)
        self.tree.blockSignals(False)
        self.refresh_buttons()

    def refresh_buttons(self) -> None:
        selected = self.traces.get(self.selected_id()) if self.selected_id() is not None else None
        self.keep_btn.setEnabled(bool(self.traces.live.points))
        self.remove_btn.setEnabled(selected is not None and selected.removable)

    def set_unit(self, unit: str) -> None:
        if unit != self.unit:
            self.unit = unit
            self.reload()

    def selected_id(self) -> int | None:
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None

    def select(self, trace_id: int) -> None:
        for i in range(self.tree.topLevelItemCount()):
            if self.tree.topLevelItem(i).data(0, Qt.UserRole) == trace_id:
                self.tree.setCurrentItem(self.tree.topLevelItem(i))

    def _done(self) -> None:
        self.reload()
        self.changed.emit()

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        trace_id = item.data(0, Qt.UserRole)
        self.traces.set_visible(trace_id, item.checkState(0) == Qt.Checked)
        name = self.traces.rename(trace_id, item.text(0))
        if name != item.text(0):                        # empty, or made unique
            self.tree.blockSignals(True)
            item.setText(0, name)
            self.tree.blockSignals(False)
        self.changed.emit()

    def _double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        t = self.traces.get(item.data(0, Qt.UserRole))
        if column == 1 and t is not None and t.kind == "theory" and self.interactive:
            d = TheoryDialog(t.theory, self)
            if d.exec():
                self.edit_theory(t.id, d.tf)

    # ---- actions
    def load_files(self, paths) -> list[str]:
        """Add each file as a trace. A file that cannot be used is refused with its name
        and the reason; the others still load. Returns the refusals."""
        paths = list(paths)
        if not paths:
            return []
        errors = []
        for path in paths:
            try:
                self.traces.add_file(export_csv.load_csv(path), path)
            except OSError as e:
                errors.append("%s: %s" % (Path(path).name, e.strerror or e))
            except Exception as e:                      # not text, not a sweep CSV, no points
                reason = "it is not a text file" if isinstance(e, UnicodeDecodeError) else str(e)
                errors.append("%s: %s" % (Path(path).name, reason))
        loaded = len(paths) - len(errors)
        if loaded:
            self.message.emit("info", "Loaded %d trace%s." % (loaded, "" if loaded == 1 else "s"))
        for e in errors:
            self.message.emit("warn", "Not loaded: " + e)
        self._done()
        if errors and self.interactive:
            QMessageBox.warning(self, "Load CSV", "Not loaded:\n\n" + "\n".join(errors))
        return errors

    def add_theory(self, tf: TransferFunction) -> None:
        self.traces.add_theory(tf)
        self._done()

    def edit_theory(self, trace_id: int, tf: TransferFunction) -> None:
        self.traces.set_theory(trace_id, tf)
        self._done()

    def keep(self) -> None:
        try:
            self.traces.keep_live()
        except ValueError as e:
            self.message.emit("warn", "Keep sweep: %s." % e)
            return
        self._done()

    def remove_selected(self) -> None:
        trace_id = self.selected_id()
        t = self.traces.get(trace_id) if trace_id is not None else None
        if t is None or not t.removable:
            return
        self.traces.remove(trace_id)
        self._done()

    def _load_clicked(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Load CSV", "", "Sweep CSV (*.csv);;All files (*)")
        self.load_files(paths)

    def _theory_clicked(self) -> None:
        d = TheoryDialog(None, self)
        if d.exec():
            self.add_theory(d.tf)
```

`export_csv.load_csv` returns a result with no points for a text file that is not a sweep CSV; `TraceSet.add_file` then raises "it holds no sweep points", which is the message the user reads.

`docs/ARCHITECTURE.md`: add a row for `gui/traces_panel.py` ("the Traces dock: list of traces, load, theory, keep, remove"), and update the Imports cell of `gui/dialogs.py` (the guard prints the difference).

- [ ] **Step 5: Run**

Run: `.venv\Scripts\python -m pytest tests\test_gui_traces.py tests\test_gui.py tests\test_docs.py` — expected all pass.
Run: `.venv\Scripts\python -m pytest` — expected `393 passed` (381 + 12).

Notes for a failure:
- `test_theory_dialog_refuses_bad_values` with `{"r": "lots"}`: `parse_si` raises `ValueError("not a number: ...")`, shown as "Invalid value: not a number ...".
- `test_panel_ticks_and_names_edit_the_traces`: `item.setText` and `setCheckState` fire `itemChanged`, which is what a user's edit does; `reload()` blocks the signal while it rebuilds the rows.
- If the binary file loads as text on this machine (no `UnicodeDecodeError`), it still ends as "it holds no sweep points"; the test only checks that its name is among the refusals.

- [ ] **Step 6: Commit**

```powershell
git add src tests docs
git commit -m "Theory dialog and Traces panel: load CSV files, add theory curves, keep and remove traces"
```

---

### Task 5: Main window and image export

**Files:**
- Modify: `src/bodeplot/gui/main_window.py`, `src/bodeplot/io/export_image.py`
- Modify: `tests/test_gui_traces.py`, `tests/test_io.py`, `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: `TraceSet`, `BodePlot(traces)`, `BodePlot.traces_changed / set_span_hint / export_series`, `TracesPanel`, `ImageSeries`.
- Produces: `MainWindow.traces: TraceSet`, `MainWindow.traces_panel: TracesPanel`, dock `dock_traces` (in `MainWindow.docks` and `view_actions`); `MainWindow.interactive` is a property that also sets the panel's; `export_image.write_image(path, result, opts=None, series=None, labels=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gui_traces.py`:

```python
# ---------------------------------------------------------------------- main window
from bodeplot.gui.main_window import MainWindow          # noqa: E402
from bodeplot.io.settings import AppSettings             # noqa: E402
from bodeplot.models import EngineState, SweepConfig, SweepType     # noqa: E402

SIM = {"preset": "rc_lpf", "params": {"r": 1e3, "c": 100e-9}, "noise_vrms": 2e-4, "latency_ms": 0.0}


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    w = MainWindow(simulate=True, settings=AppSettings(simulate=True, sim=dict(SIM)), sim_seed=7)
    w.interactive = False
    qtbot.addWidget(w)
    w.show()
    yield w
    w.close()


def run_sweep(win, qtbot, lo=100.0, hi=1e5, ppd=4):
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


def test_window_has_a_traces_panel(win):
    assert win.plot.set is win.traces and win.traces_panel.traces is win.traces
    assert win.traces_panel.interactive is False                 # follows the window's switch
    dock, act = win.docks["dock_traces"], win.view_actions["dock_traces"]
    assert dock.isVisible() and act.isChecked() and dock.windowTitle() == "Traces"
    dock.close()
    win.act_reset_layout.trigger()
    assert dock.isVisible()
    assert win.plot.span_hint == (50.0, 20e6)                    # the sweep settings of the panel
    assert not win.traces_panel.keep_btn.isEnabled()


def test_a_new_sweep_keeps_the_other_traces(win, qtbot):
    run_sweep(win, qtbot)
    first = win.plot.points()
    assert win.traces_panel.keep_btn.isEnabled()
    win.traces_panel.keep()
    win.traces_panel.add_theory(RC)
    kept, th = win.traces.traces[1], win.traces.traces[2]
    win.plot.ref_box.setCurrentIndex(win.plot.ref_box.findData(th.id))
    win.plot.ref_box.activated.emit(win.plot.ref_box.currentIndex())
    run_sweep(win, qtbot, 1e3, 1e4, 3)
    assert [t.kind for t in win.traces.traces] == ["live", "kept", "theory"]
    assert kept.points == first and len(win.plot.points()) == 4 and win.traces.reference() is th
    # against the ideal filter the simulated one reads zero within its noise
    y = line_y(win.plot, win.traces.live)
    assert np.abs(y).max() < 0.1
    assert "Loaded" not in win.status_log.text.toPlainText()
    assert win.result is not None and len(win.result.points) == 4          # the exports' result is the live sweep


def test_panel_messages_reach_the_status_log(win, tmp_path):
    win.traces_panel.load_files([str(tmp_path / "missing.csv")])
    assert "Not loaded: missing.csv" in win.status_log.text.toPlainText()
    win.traces_panel.set_unit("db")
    win.plot.set_unit("v")
    assert win.traces_panel.unit == "v"                           # the panel follows the plot's unit


def test_image_export_draws_what_the_plot_shows(win, qtbot, tmp_path, monkeypatch):
    from bodeplot.io import export_image
    run_sweep(win, qtbot)
    win.traces_panel.add_theory(RC)
    win.plot.set.set_reference(win.traces.traces[1].id)
    win.plot.traces_changed()
    seen = {}
    real = export_image.write_image

    def spy(path, result, opts=None, series=None, labels=None):
        seen.update(series=series, labels=labels)
        return real(path, result, opts, series, labels)
    monkeypatch.setattr(export_image, "write_image", spy)
    for name in ("t.png", "t.svg", "t.pdf"):
        out = win.export(tmp_path / name)
        assert out.exists() and out.stat().st_size > 500
    assert [s.name for s in seen["series"]] == ["Sweep", "RC low-pass 1 kΩ 100 nF"]
    assert seen["labels"] == ("Gain difference (dB)", "Phase difference (deg)", "relative to RC low-pass 1 kΩ 100 nF")
    csv = win.export(tmp_path / "t.csv").read_text(encoding="utf-8")
    assert "RC low-pass" not in csv and "# bodeplot_csv: 1" in csv        # the CSV is the live sweep only
```

Append to `tests/test_io.py`:

```python
def test_image_with_several_series_and_a_legend(tmp_path, result):
    import numpy as np
    from bodeplot.io.export_image import ImageSeries
    f = np.array([p.freq_hz for p in result.points])
    g = np.array([p.gain_db for p in result.points])
    ph = np.array([p.phase_deg for p in result.points])
    flagged = np.zeros(len(f), dtype=bool)
    flagged[2] = True
    series = [ImageSeries("Sweep", 0, f, g, ph, flagged), ImageSeries("ideal", 1, f, g - 0.1, ph, None),
              ImageSeries("ninth", None, f, g - 0.2, ph, None), ImageSeries("empty", 3, f[:0], g[:0], ph[:0], None)]
    labels = ("Gain difference (dB)", "Phase difference (deg)", "relative to ideal")
    for ext in ("png", "svg", "pdf"):
        out = export_image.write_image(tmp_path / ("multi." + ext), result, export_image.ImageOptions(), series, labels)
        assert out.stat().st_size > 500
    svg = (tmp_path / "multi.svg").read_text(encoding="utf-8")
    assert export_image.PRINT_SERIES[1].lower() in svg.lower() and export_image.PRINT_MUTED.lower() in svg.lower()
    one = export_image.write_image(tmp_path / "one.svg", result, export_image.ImageOptions()).read_text(encoding="utf-8")
    assert export_image.PRINT_SERIES[0].lower() in one.lower()               # without series: as before
    assert export_image.PRINT_SERIES[1].lower() not in one.lower()
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_gui_traces.py tests\test_io.py`
Expected: the new tests fail (`'MainWindow' object has no attribute 'traces'`, `write_image() takes from 2 to 3 positional arguments`).

- [ ] **Step 3: Implement the image export**

`src/bodeplot/io/export_image.py`: add below `FORMATS` / `QUIET`:

```python
# Series colours on the white background of an exported image, by colour slot (the same
# hues as the app's dark theme, darkened for print). The one place outside gui/theme.py
# that may hard-code colours.
PRINT_SERIES = ("#2a78d6", "#c2410c", "#0f8a5f", "#a16207", "#be3a6f", "#15803d", "#6d5bd0", "#c0392b")
PRINT_MUTED = "#777777"
PRINT_FLAGGED = "#d62728"
```

Replace `write_image` with:

```python
def write_image(path, result: SweepResult, opts: ImageOptions | None = None,
                series: list[ImageSeries] | None = None, labels: tuple[str, str, str] | None = None) -> Path:
    """The Bode plot as an image. Without `series` it draws the sweep of `result` (as it
    always did). With `series` (BodePlot.export_series) it draws exactly what the plot
    shows: every visible trace, absolute or relative, with `labels` = (gain axis, phase
    axis, note for the footer)."""
    import matplotlib
    matplotlib.use("Agg")               # no display needed
    import matplotlib.pyplot as plt

    opts = opts or ImageOptions()
    path = Path(path)
    if path.suffix.lower().lstrip(".") not in FORMATS:
        raise ValueError("unsupported image format %r (use png, svg or pdf)" % path.suffix)
    if series is None:
        pts = sorted(result.points, key=lambda p: p.freq_hz)
        gain_label, value = UNITS.get(opts.unit, UNITS["db"])
        phase = np.array([p.phase_deg for p in pts])
        if opts.unwrap and len(pts):
            phase = unwrap_deg(phase)
        series = [ImageSeries("Sweep", 0, np.array([p.freq_hz for p in pts]), np.array([value(p) for p in pts]),
                              phase, np.array([bool(p.flags & ~QUIET) for p in pts], dtype=bool))]
        labels = (gain_label, "Phase (deg)", "")
    gain_label, phase_label, note = labels or ("Gain (dB)", "Phase (deg)", "")
    named = len(series) > 1

    rows = 2 if opts.show_phase else 1
    fig, axes = plt.subplots(rows, 1, sharex=True, figsize=(opts.width_in, opts.height_in))
    axes = np.atleast_1d(axes)
    any_flagged = False
    for ax, key, label in zip(axes, ("gain", "phase"), (gain_label, phase_label)):
        for s in series:
            colour = PRINT_SERIES[s.slot] if s.slot is not None and s.slot < len(PRINT_SERIES) else PRINT_MUTED
            f, y = np.asarray(s.freqs, dtype=float), np.asarray(getattr(s, key), dtype=float)
            ax.plot(f, y, "-", color=colour, linewidth=1.2, label=s.name if named and ax is axes[0] else None)
            if s.flagged is None or not len(f):
                continue
            bad = np.asarray(s.flagged, dtype=bool)
            ax.plot(f[~bad], y[~bad], "o", color=colour, markersize=3)
            if bad.any():
                ax.plot(f[bad], y[bad], "x", color=PRINT_FLAGGED, markersize=6,
                        label="flagged" if ax is axes[0] and not any_flagged else None)
                any_flagged = True
        ax.set_ylabel(label)
        ax.grid(True, which="both", linewidth=0.4, alpha=0.6)
        if opts.log_x:
            ax.set_xscale("log")
    if named or any_flagged:
        axes[0].legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("Frequency (Hz)")
    axes[0].set_title(opts.title)
    sw = result.config.get("sweep", {})
    st = result.config.get("stimulus", {})
    footer = "%s   %s to %s Hz   %s Vpp   %s%s%s%s" % (
        str(result.meta.get("finished", ""))[:19], _g(sw.get("start_hz")), _g(sw.get("stop_hz")),
        _g(st.get("amp_vpp")), describe_correction(result.meta),
        "   phase unwrapped" if opts.unwrap else "",
        "   " + note if note else "",
        "   ABORTED (partial)" if result.meta.get("aborted") else "")
    fig.text(0.01, 0.005, footer, fontsize=7, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=opts.dpi)
    plt.close(fig)
    return path
```

A log axis with an empty series or with no positive data must not raise: matplotlib accepts empty arrays; the series named "empty" in the test checks it.

- [ ] **Step 4: Implement the main window**

`src/bodeplot/gui/main_window.py`:

Imports: add `from ..traces import TraceSet` and `from .traces_panel import TracesPanel`.

In `__init__`:
- replace `self.interactive = True         # tests switch this off: no modal dialogs` with `self._interactive = True       # tests switch this off: no modal dialogs (see the property)`;
- replace `self.plot = BodePlot()` with:

```python
        self.traces = TraceSet()
        self.plot = BodePlot(self.traces)
```

- after `self.status_log = StatusLog()` add:

```python
        self.traces_panel = TracesPanel(self.traces)
        self.traces_panel.interactive = self._interactive
```

- add to the tuple of docks, after the Waveform line: `("Traces", "dock_traces", self.traces_panel, Qt.RightDockWidgetArea),`
- after `self.plot.remeasure_requested.connect(self.remeasure)` add:

```python
        self.traces_panel.changed.connect(self.plot.traces_changed)
        self.traces_panel.message.connect(self._say)
        self.plot.unit_box.currentIndexChanged.connect(lambda _i: self.traces_panel.set_unit(self.plot.unit()))
```

Add the property below `__init__`:

```python
    @property
    def interactive(self) -> bool:
        """False in the tests: no modal dialog or message box, here or in the Traces panel."""
        return self._interactive

    @interactive.setter
    def interactive(self, on: bool) -> None:
        self._interactive = bool(on)
        self.traces_panel.interactive = self._interactive
```

`_build_menus`: in the tuple of dock names add `("dock_traces", "&Traces")` after the Waveform entry.

`_load_ui_state`: after `self.plot.set_unit(s.vertical_unit)` add `self.traces_panel.set_unit(self.plot.unit())`.

`_on_config_changed`: add, after the `set_log_x` line:

```python
        sweep = self.config.sweep()
        self.plot.set_span_hint(min(sweep.start_hz, sweep.stop_hz), max(sweep.start_hz, sweep.stop_hz))
```

`_begin_sweep`: the line `self.plot.clear()` stays (it now empties only the live trace); add after it `self.traces_panel.refresh_buttons()`.

`_on_point`, `_on_finished`, `_on_remeasured`: add `self.traces_panel.refresh_buttons()` as the last line of each (the Keep button follows the live trace).

`export`: replace the image branch's last line `out = export_image.write_image(path, self.result, o)` with:

```python
            series, labels = self.plot.export_series()
            out = export_image.write_image(path, self.result, o, series, labels)
```

`docs/ARCHITECTURE.md`: Imports cell of `gui/main_window.py` gains `gui/traces_panel.py` and `traces.py`; add a row to "Where each concern lives": "Traces on the plot (overlay, theory, relative display) | the model and the maths in `traces.py`; drawing in `gui/bode_plot.py`; the list and its buttons in `gui/traces_panel.py`; theory circuits in `measure/theory.py`; image export of several series in `io/export_image.py`".

- [ ] **Step 5: Run**

Run: `.venv\Scripts\python -m pytest tests\test_gui_traces.py tests\test_io.py tests\test_gui.py tests\test_docs.py` — expected all pass.
Run: `.venv\Scripts\python -m pytest` — expected `398 passed` (393 + 5).

Notes for a failure:
- `test_window_has_a_traces_panel`, span hint `(50.0, 20e6)`: the default sweep of the panel is 50 Hz to 20 MHz; the fixture uses a fresh config folder.
- `test_a_new_sweep_keeps_the_other_traces`, `np.abs(y).max() < 0.1`: the simulated RC with 0.2 mV noise against its own ideal curve between 1 and 10 kHz, no skew check (phase is not asserted).
- An old saved window layout does not know the new dock: Qt places it in its default area, and `_load_ui_state` shows every dock.

- [ ] **Step 6: Look at it**

Render the window offscreen (as `docs/screenshots/` was made: `QT_QPA_PLATFORM=offscreen`, `QT_QPA_FONTDIR=C:\Windows\Fonts`, a script in the scratchpad): connect in simulation, sweep, add an RC low-pass theory curve, load `hwcheck/results/m8/gui_rc.csv`, grab the window; then choose the theory curve in "Relative to" and grab again. Look at both images: the Traces dock with its swatches, three curves in three colours, the relative view with its axis labels. Export a PNG in the relative view and look at it (legend, colours on white).

- [ ] **Step 7: Commit**

```powershell
git add src tests docs
git commit -m "Main window: Traces dock, theory curves over the sweep range, image export of every visible trace"
```

---

### Task 6: Documentation

**Files:**
- Modify: `docs/spec/gui.md` (sections 10 and 12), `docs/spec/drivers.md` (section 9.5), `docs/spec/roadmap.md` (sections 15 and 16), `docs/STATE.md`, `README.md`, `docs/ARCHITECTURE.md`

- [ ] **Step 1: The spec**

`docs/spec/gui.md`, section 10: after the bullet on the through calibration, add:

```markdown
- **Traces** (v2, milestone A3; design `docs/superpowers/specs/2026-10-07-trace-overlay-design.md`): the plot shows any number of traces: the live sweep, kept sweeps, CSV files and theory curves. A dock "Traces" lists them (visibility tick, colour, name, kind) with the buttons Load CSV…, Add theory…, Keep sweep, Remove. A new sweep replaces only the live trace. A theory curve is a circuit of `measure/theory.py` with entered part values, or H(s) as coefficients; it is drawn at 50 points per decade over the range of the other traces and of the sweep settings. A box "Relative to" draws every visible trace divided by one reference trace (gain difference in dB, phase difference in degrees; a measured reference is interpolated in log frequency, a theory reference is evaluated exactly; nothing is drawn outside the reference's range). With the vertical unit Voltage, theory curves and the relative display are off. The first eight traces take the theme's eight series colours; further ones are drawn muted. Traces live for one run of the app; they are not stored. The read-out names the trace under the cursor; re-measure works on the live sweep only.
```

Section 12, image bullet: append "With several traces the image shows every visible one, in its colour and with a legend, relative or absolute as the plot does. CSV and Touchstone hold the live sweep only."

`docs/spec/drivers.md`, section 9.5 (mock instruments): add the sentence "The transfer functions of the simulated DUT live in `measure/theory.py` (`TransferFunction`); `SimulatedDUT` adds the load on the source. The same module supplies the plot's theory curves."

`docs/spec/roadmap.md`: section 15, the bullet "Trace overlay and compare": append "**Built on 2026-10-07** with theory curves added on the user's request; the difference is shown as a display relative to a reference trace, not as an extra trace." Section 16, row A3: put "**State 2026-10-07: built; the user's review of the GUI is the open step.**" into its Content cell.

- [ ] **Step 2: README**

In "What works" add:

```markdown
- **Traces**: keep a sweep, load saved CSV sweeps and add theory curves (RC, RLC, Butterworth, or your own H(s)) next to the live sweep; show or hide each; draw everything relative to one of them to read the difference directly.
```

and after the "Through calibration" section add:

```markdown
## Comparing traces

The **Traces** panel lists what is on the plot. The live sweep is always there; a new sweep replaces only it.

- **Keep sweep** keeps the current sweep on the plot when the next one starts.
- **Load CSV…** adds sweeps saved earlier with Export > CSV, one or several at once.
- **Add theory…** adds the ideal response of a circuit: pick RC low-pass, RC high-pass, RLC band-pass, RLC notch or a 2nd-order Butterworth and enter the parts (1k, 100n), or enter the coefficients of H(s). Double-click the kind of a theory trace to change its values.

Tick a trace to show it, double-click its name to rename it. **Relative to** above the plot draws every trace divided by the one you choose: gain difference in dB and phase difference in degrees. With a theory curve as the reference this shows how far the measurement is from the ideal circuit. A theory curve is the ideal circuit only: no component losses, no lead inductance, no probe loading.

Traces are kept for this run of the app only. The image export shows every visible trace; CSV and Touchstone hold the live sweep.
```

- [ ] **Step 3: State and architecture map**

`docs/STATE.md`: rewrite "Start here": A3 built on 2026-10-07 on branch `a3-trace-overlay` (the pytest total of Task 5), design and plan paths, the open step (the user's review of the GUI, spec section 10), what the user decided in the brainstorm (the table of spec section 1, and that colours do not repeat after eight), A4 (auto markers) next and not to be started without the user. Keep the list of open A1 review items. Add to "What exists" one bullet naming `traces.py`, `measure/theory.py`, `gui/traces_panel.py`, `TheoryDialog`, `TransferFunctionForm`, `BodePlot.export_series`, `ImageSeries`, and the three test files.

`docs/ARCHITECTURE.md`: read the Modules table once against the code (the guard has kept the Imports cells right; check the descriptions), and add to "The chain of one measurement" a short paragraph "Traces on the plot" saying that `traces.py` is outside that chain: it holds results for display, and nothing below the GUI knows it.

- [ ] **Step 4: Check and commit**

Run: `.venv\Scripts\python -m pytest` — expected `398 passed`.

```powershell
git add docs README.md
git commit -m "Spec, README, state and architecture map: traces, theory curves, relative display"
```

---

### Task 7: The user's review of the GUI

No bench work. Hand over to the user (spec section 10):

- [ ] **Step 1:** Tell the user what to try, in Simulation mode or on their instruments: keep a sweep and sweep again; load `hwcheck/results/m8/gui_rc.csv`; add an RC low-pass theory curve of 997.8 Ω and 98.2 nF; choose it in "Relative to" (the steady −0.06 dB of `HW_REPORT.md` 14.3 should be read directly from the plot between 1 and 100 kHz); hide and rename traces; export an image.
- [ ] **Step 2:** Record the user's verdict and requested changes in `docs/STATE.md`; make the changes test-first; then superpowers:finishing-a-development-branch.
