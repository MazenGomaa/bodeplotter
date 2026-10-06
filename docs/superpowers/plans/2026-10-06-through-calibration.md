# Through Calibration (v2, milestone A1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure the gain and phase difference between the two measurement paths once, with both probes on one node, and divide it out of every later sweep of this connection.

**Architecture:** A new Qt-free module `sweep/calibration.py` holds every pure decision (frequencies, interpolation, plausibility, validity against the scope settings). `sweep/core.py` measures a calibration inside the same safety frame as the skew check and lets `SweepRunner` pick, once per sweep, calibration first, skew delay second, nothing third. `sweep/engine.py` and the GUI mirror the skew-check plumbing (request, result signal, accept).

**Tech Stack:** Python 3.14, PySide6 6.11, pyqtgraph, numpy, pytest + pytest-qt. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-06-through-calibration-design.md` (approved 2026-10-06). Read it with this plan.

## Global Constraints

- Run everything from the project root in PowerShell. Tests: `.venv\Scripts\python -m pytest`. One file: `.venv\Scripts\python -m pytest tests\test_calibration.py`. The suite stood at 292 passed before this plan (264 plus the 28 document guards of `tests/test_docs.py`); it must never go down.
- `tests/conftest.py` sets `BODEPLOT_NO_HARDWARE`. Never remove it. No test opens a VISA resource.
- No `:RUN` and no `subprocess` anywhere in `src/` (a test in `tests/test_drivers.py` scans for both).
- `sweep/calibration.py` and `sweep/core.py` import no Qt.
- A sweep without a calibration must behave exactly as it does today (design, success criterion 2). Every existing test stays green unchanged, except the two that this plan names.
- Nothing about a calibration is written to the settings folder. It lives in the `Session` and dies with the connection.
- The calibration is never measured with Fast preview and never has a skew correction applied to its stored values.
- New `Flag` members go at the END of the enum (stored files hold flag names, but the order is kept stable anyway).
- Colours only through `gui/theme.py` (`theme.status_html`).
- **Document guards (`tests/test_docs.py`, added 2026-10-06 with the split of the documents).** The spec lives in `docs/SPEC.md` (index) and `docs/spec/`; the hardware report in `HW_REPORT.md` (facts sheet and index) and `docs/hw/`; state in `docs/STATE.md`; `CLAUDE.md` is a size-limited index. In the same commit as the code: a new module or a changed import inside the package goes into the Modules table of `docs/ARCHITECTURE.md` (the test prints the rows to change); a section cited in code (`SPEC.md section 8.7`) must exist as a heading in `docs/spec/`. Nothing about this feature is added to `CLAUDE.md`.
- Commit after every task, on branch `a1-through-calibration`. End every commit message with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01TbULzRjW3WqWNV5wkVxfN7
  ```
- Bench work (Task 10 only): ask what is wired before EVERY run, commit before it, never pipe a bench script into `Select-Object -First N`, run `hwcheck\s6_state.py` after a run that ended oddly.

## Where this plan departs from the design (confirm with the user at review)

1. **Top frequency.** The design's rule ("lowest of the upper limits, not above the scope's `max_hz`") gives 30 MHz on the real pair (generator 30 MHz, scope `max_hz` 50 MHz), but the design states the result as 20 MHz. The plan adds the limit that produces 20 MHz: 40 % of the scope bandwidth, the same limit `plan.make_plan` already warns at.
2. **Point count.** 50 Hz to 20 MHz at 10 per decade is 58 points with the app's own `plan.frequencies` (5.6 decades round up to 57 intervals). The design says 57.
3. **Phase interpolation.** The design interpolates the unwrapped phase linearly in log frequency. A delay is linear in frequency, not in log frequency: with the scope in the +2.15 ns state that leaves 0.09 deg near 18 MHz at a frequency between two calibration points, the whole 0.1 deg budget. The plan fits one delay to the calibration, interpolates only the remainder in log frequency and adds the delay back exactly. Gain is interpolated as designed.
4. **`ThroughCal.acceptable`.** One extra field, so the dialog and the engine know that a result may not be accepted ("the dialog does not offer Accept") without parsing warning texts.
5. **Image footer.** The design says the image export is unchanged; its footer would then print "skew: not checked" under a calibrated plot. The footer prints the calibration line when one was applied.
6. **File menu.** "Calibrate, next to Skew check": Skew check is not in the File menu today, so both are added.

## Review Focus

1. Scope settings changed after a calibration (other channel, probe setting, coupling, bandwidth limit): the calibration must not be applied, and must come back when the setting is put back. Tests: Task 4 `test_validity`, Task 5 `test_a_calibration_for_other_settings_is_not_applied`.
2. Sweep reaching beyond the calibrated range: no extrapolation, skew correction (or `SKEW_UNCHECKED`) there, one warning. Tests: Task 2 `test_no_extrapolation`, Task 5 `test_beyond_the_range_*`.
3. Calibration stopped half-way (Cancel, lost instrument): nothing to accept, generator off, scope restored. Tests: Task 4 `test_cancel_*`, Task 7 `test_aborting_a_calibration_*`.
4. Scope resynchronised while the calibration runs: the result would mix two alignment states, so it is refused. Test: Task 4 `test_a_resync_during_the_calibration_is_refused`.
5. A dead channel or a filter in place of the through (gain 0, NaN, large loss): refused, and a zero in the stored response never divides. Tests: Task 2 `test_a_dead_calibration_point_gives_no_correction`, `test_evaluate_*`, Task 4 `test_a_filter_is_refused`.
6. Old CSV files and old `PointResult`s without the calibration fields still load. Test: Task 6 `test_csv_loader_tolerates_a_minimal_file` (extended).

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/bodeplot/models.py` | modify | `ThroughCal`, `PointResult.cal_gain_db` / `cal_phase_deg`, `Flag.CALIBRATED` |
| `src/bodeplot/sweep/calibration.py` | create | pure functions: frequencies, `response_at`, `correct`, `evaluate`, `matches`, `covers`, texts |
| `src/bodeplot/drivers/mock.py` | modify | `dut_gain_tilt_db_at_20mhz` |
| `src/bodeplot/sweep/core.py` | modify | `Session.cal` and validity, `run_through_cal`, `SweepRunner` applies it |
| `src/bodeplot/io/export_csv.py`, `export_touchstone.py`, `export_image.py` | modify | header lines, two columns, footer, quiet flag |
| `src/bodeplot/sweep/engine.py` | modify | `run_cal`, `accept_cal`, `discard_cal`, `cal_measured`, `SessionInfo.cal*` |
| `src/bodeplot/gui/dialogs.py` | modify | `CalDialog`, `cal_report` |
| `src/bodeplot/gui/main_window.py` | modify | Calibrate action, status text, sweep-start question |
| `src/bodeplot/gui/bode_plot.py` | modify | quiet flag |
| `tests/test_calibration.py` | create | everything Qt-free about the calibration |
| `tests/test_drivers.py`, `tests/test_io.py`, `tests/test_gui.py` | modify | real drivers on the fakes, exports, GUI |
| `hwcheck/m8_throughcal.py`, `hwcheck/m8_rc_compare.py` | create | bench acceptance, headless part |
| `docs/spec/skew.md` (8.7), `docs/spec/sweep.md`, `docs/spec/gui.md`, `docs/spec/roadmap.md`, `docs/ARCHITECTURE.md`, `docs/STATE.md`, `README.md` | modify | documentation |
| `docs/hw/a1-through-cal.md` (create, section 14), `HW_REPORT.md` (facts sheet, index) | create / modify | bench record |

---

### Task 0: Branch

- [ ] **Step 1: Create the branch and commit the plan**

```powershell
git checkout -b a1-through-calibration      # from docs-split, which holds the split documents and their guards
git add docs/superpowers/plans/2026-10-06-through-calibration.md
git commit -m "Implementation plan: through calibration"
```

- [ ] **Step 2: Baseline**

Run: `.venv\Scripts\python -m pytest -q`
Expected: `292 passed`.

---

### Task 1: Data model

**Files:**
- Modify: `src/bodeplot/models.py`
- Modify: `src/bodeplot/gui/bode_plot.py:22`, `src/bodeplot/io/export_image.py:54`
- Test: `tests/test_calibration.py` (create)

**Interfaces:**
- Produces: `Flag.CALIBRATED`; `PointResult.cal_gain_db: float = 0.0`, `PointResult.cal_phase_deg: float = 0.0`; `ThroughCal` (fields below), `ThroughCal.to_meta() -> dict`, `ThroughCal.from_meta(data) -> ThroughCal | None`; `bodeplot.gui.bode_plot.QUIET` and `bodeplot.io.export_image.QUIET` both contain `Flag.CALIBRATED`.

- [ ] **Step 0: Section 8.7 of the spec first**

The code of this task cites `SPEC.md section 8.7`, and `tests/test_docs.py` fails on a cited section that does not exist. Append the block `### 8.7 Through calibration (v2)` given in Task 9, Step 1 to `docs/spec/skew.md` now (it describes the finished feature; Task 9 only checks it against what was built).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_calibration.py`:

```python
"""Through calibration (design of 2026-10-06, SPEC.md section 8.7). No hardware, no Qt
except where a test says so."""
import cmath
import json
import math

import pytest

from bodeplot.models import Flag, PointResult, ThroughCal


def make_cal(freqs, hs, **kw):
    base = dict(checked_at="2026-10-06T21:15:00+02:00", alignment_epoch=1, ref_channel=1, dut_channel=2,
                probe_atten={1: 10.0, 2: 10.0}, coupling="DC", bw_limit=False, amp_vpp=1.0)
    base.update(kw)
    return ThroughCal(freqs_hz=list(freqs), h=list(hs), **base)


def _h(gain_db, deg):
    return cmath.rect(10 ** (gain_db / 20.0), math.radians(deg))


def _point(f, gain_db=0.0, deg=0.0, vref=0.5, flags=Flag.NONE):
    h = _h(gain_db, deg)
    return PointResult(freq_hz=f, h=h, gain_db=gain_db, phase_deg=deg, vref_amp=vref, vdut_amp=vref * abs(h),
                       vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1, snr_ref_db=50.0,
                       snr_dut_db=50.0, flags=flags, duration_s=0.1)


# ------------------------------------------------------------------ data model
def test_calibrated_flag_is_the_last_one_and_survives_text():
    assert list(Flag)[-1] is Flag.CALIBRATED
    assert Flag.from_text("PREVIEW|CALIBRATED") == Flag.PREVIEW | Flag.CALIBRATED


def test_calibrated_is_a_quiet_flag():
    from bodeplot.gui import bode_plot
    from bodeplot.io import export_image
    assert Flag.CALIBRATED & bode_plot.QUIET and Flag.CALIBRATED & export_image.QUIET


def test_point_result_has_calibration_fields_that_default_to_zero():
    p = _point(1e3)
    assert p.cal_gain_db == 0.0 and p.cal_phase_deg == 0.0


def test_through_cal_goes_through_json_and_back():
    cal = make_cal([100.0, 1e3], [_h(0.1, 1.0), _h(0.2, 2.0)], warnings=["w"])
    assert cal.acceptable is True
    back = ThroughCal.from_meta(json.loads(json.dumps(cal.to_meta())))
    assert back == cal and back.probe_atten == {1: 10.0, 2: 10.0}
    assert ThroughCal.from_meta(None) is None and ThroughCal.from_meta({"freqs_hz": [1.0]}) is None
    assert ThroughCal.from_meta("applied") is None
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_calibration.py -q`
Expected: collection error, `ImportError: cannot import name 'ThroughCal'`.

- [ ] **Step 3: Implement**

`src/bodeplot/models.py`, in `class Flag`, after the `PREVIEW` line:

```python
    CALIBRATED = enum.auto()        # corrected with a through calibration; says so, marks no fault
```

In `class PointResult`, after `retries: int = 0`:

```python
    cal_gain_db: float = 0.0    # gain removed by the through calibration; raw = gain_db + this
    cal_phase_deg: float = 0.0  # phase removed by it; raw = phase_deg + this
```

After `class SkewCheck`:

```python
@dataclass
class ThroughCal:
    """Result of a through calibration (SPEC.md section 8.7): Vdut / Vref with both probes
    on one node, over the full range. No skew correction is applied to h: the calibration
    holds the channel delay itself."""
    freqs_hz: list[float]           # ascending
    h: list[complex]
    checked_at: str                 # ISO time
    alignment_epoch: int            # digitizer epoch when measured
    ref_channel: int
    dut_channel: int
    probe_atten: dict[int, float]
    coupling: str
    bw_limit: bool
    amp_vpp: float                  # stimulus used, for the record
    warnings: list[str] = field(default_factory=list)
    acceptable: bool = True         # False: it is not a through connection, or a point is unusable

    def to_meta(self) -> dict:
        return to_jsonable(self)

    @classmethod
    def from_meta(cls, data) -> "ThroughCal | None":
        """From SweepResult.meta["cal"] as read back from a file; None if it is not one."""
        try:
            return cls(freqs_hz=[float(f) for f in data["freqs_hz"]],
                       h=[complex(re, im) for re, im in data["h"]],
                       checked_at=str(data["checked_at"]), alignment_epoch=int(data["alignment_epoch"]),
                       ref_channel=int(data["ref_channel"]), dut_channel=int(data["dut_channel"]),
                       probe_atten={int(k): float(v) for k, v in data["probe_atten"].items()},
                       coupling=str(data["coupling"]), bw_limit=bool(data["bw_limit"]),
                       amp_vpp=float(data["amp_vpp"]),
                       warnings=[str(w) for w in data.get("warnings", [])],
                       acceptable=bool(data.get("acceptable", True)))
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
```

Update the `SweepResult.meta` comment to `# app version, timestamps, IDNs, aborted flag, skew check, through calibration`.

`src/bodeplot/gui/bode_plot.py` line 22:

```python
QUIET = Flag.REMEASURED | Flag.BUILTIN | Flag.PREVIEW | Flag.CALIBRATED   # flags that do not mark a point as suspect
```

`src/bodeplot/io/export_image.py`: add below `FORMATS`:

```python
QUIET = Flag.REMEASURED | Flag.BUILTIN | Flag.PREVIEW | Flag.CALIBRATED    # as gui/bode_plot.py QUIET
```

and in `write_image` replace the two lines `quiet = ...` / `flagged = ...` with:

```python
    flagged = np.array([bool(p.flags & ~QUIET) for p in pts], dtype=bool)
```

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python -m pytest tests\test_calibration.py -q` — expected `4 passed`.
Run: `.venv\Scripts\python -m pytest -q` — expected `296 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/bodeplot/models.py src/bodeplot/gui/bode_plot.py src/bodeplot/io/export_image.py tests/test_calibration.py
git commit -m "Through calibration: data model (ThroughCal, CALIBRATED flag, cal fields of a point)"
```

---

### Task 2: Pure functions (`sweep/calibration.py`)

**Files:**
- Create: `src/bodeplot/sweep/calibration.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: `ThroughCal`, `PointResult`, `Flag`, `ScopeConfig`, `SweepConfig`, `SweepType` from `models`; `plan.frequencies(SweepConfig) -> list[float]`; `units.fmt_si(value, unit)`.
- Produces (all in `bodeplot.sweep.calibration`):
  - `frequencies(source_min_hz, source_max_hz, scope_min_hz, scope_max_hz, bandwidth_hz) -> list[float]` (raises `ValueError` when the range is empty)
  - `response_at(cal, freq_hz) -> complex | None`
  - `correct(h_meas, cal, freq_hz) -> tuple[complex, float, float] | None` (corrected H, removed dB, removed degrees)
  - `fitted_delay_s(cal) -> float`, `max_gain_db(cal) -> float`
  - `matches(cal | None, scope_cfg) -> bool`, `covers(cal, lo_hz, hi_hz) -> bool`
  - `range_text(cal) -> str` ("50 Hz to 20 MHz"), `describe(cal | None) -> str` ("cal: 21:15, 50 Hz to 20 MHz" / "cal: none")
  - `evaluate(points, scope_cfg, amp_vpp, alignment_epoch=0, now=None) -> ThroughCal`
  - constants `NOT_A_THROUGH`, `REFUSE_GAIN_DB = 1.0`, `WARN_GAIN_DB = 0.3`, `EDGE_TOL = 1e-3`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_calibration.py` (add `from bodeplot.models import ScopeConfig` to the import line and `from bodeplot.sweep import calibration` below it):

```python
# ------------------------------------------------------------------ pure functions
def test_frequencies_cover_the_instruments_at_ten_per_decade():
    f = calibration.frequencies(1e-6, 30e6, 20.0, 50e6, 50e6)      # the mock pair and the real pair
    assert f[0] == 50.0 and f[-1] == 20e6 and len(f) == 58 and f == sorted(f)
    f = calibration.frequencies(1e-6, 5e6, 100.0, 50e6, 50e6)      # a narrower pair
    assert f[0] == 100.0 and f[-1] == 5e6
    with pytest.raises(ValueError):
        calibration.frequencies(1e6, 2e6, 5e6, 50e6, 50e6)


def test_response_is_exact_at_a_point_and_within_a_tenth_of_a_percent():
    cal = make_cal([100.0, 1e3, 1e4], [_h(0.0, 0.0), _h(0.1, 1.0), _h(0.2, 2.0)])
    assert calibration.response_at(cal, 1e3) == cal.h[1]
    assert calibration.response_at(cal, 1e3 * 1.0009) == cal.h[1]
    assert calibration.response_at(cal, 1e4 * 1.0009) == cal.h[2]  # just beyond the last point


def test_no_extrapolation():
    cal = make_cal([100.0, 1e3, 1e4], [_h(0.0, 0.0), _h(0.1, 1.0), _h(0.2, 2.0)])
    for f in (99.0, 1e4 * 1.002, 0.0, -5.0):
        assert calibration.response_at(cal, f) is None
        assert calibration.correct(1 + 0j, cal, f) is None
    assert calibration.covers(cal, 100.0, 1e4) and calibration.covers(cal, 100.0 * 0.9995, 1e4 * 1.0005)
    assert not calibration.covers(cal, 50.0, 1e4) and not calibration.covers(cal, 100.0, 2e4)


def test_gain_is_interpolated_linearly_in_db_over_log_frequency():
    cal = make_cal([1e3, 1e4], [_h(0.0, 0.0), _h(0.2, 0.0)])
    h = calibration.response_at(cal, 10 ** 3.5)
    assert 20 * math.log10(abs(h)) == pytest.approx(0.1, abs=1e-9)
    assert math.degrees(cmath.phase(h)) == pytest.approx(0.0, abs=1e-9)


def test_a_pure_delay_is_interpolated_exactly():
    dt = 2.15e-9
    freqs = [1e6, 2e6, 5e6, 1e7, 2e7]
    cal = make_cal(freqs, [cmath.exp(2j * math.pi * f * dt) for f in freqs])
    assert calibration.fitted_delay_s(cal) == pytest.approx(dt, rel=1e-9)
    for f in (1.5e6, 3e6, 7e6, 1.5e7):
        h = calibration.response_at(cal, f)
        assert abs(h) == pytest.approx(1.0, abs=1e-12)
        assert math.degrees(cmath.phase(h)) == pytest.approx(360 * f * dt, abs=1e-6)


def test_phase_is_unwrapped_before_interpolating():
    cal = make_cal([1e6, 2e6], [_h(0.0, 170.0), _h(0.0, -170.0)])  # 170 and 190 degrees
    deg = math.degrees(cmath.phase(calibration.response_at(cal, 1.4e6)))
    assert abs(deg) > 150.0             # near +-180, not near 0 as the wrapped values would give


def test_correct_divides_and_reports_what_was_removed():
    cal = make_cal([1e3, 1e4], [_h(0.2, 10.0), _h(0.2, 10.0)])
    h, db, deg = calibration.correct(_h(-3.0, -35.0), cal, 1e3)
    assert 20 * math.log10(abs(h)) == pytest.approx(-3.2) and math.degrees(cmath.phase(h)) == pytest.approx(-45.0)
    assert db == pytest.approx(0.2) and deg == pytest.approx(10.0)
    assert calibration.max_gain_db(cal) == pytest.approx(0.2)


def test_a_dead_calibration_point_gives_no_correction():
    cal = make_cal([1e3, 1e4], [0j, 0j])
    assert calibration.correct(1 + 0j, cal, 1e3) is None
    assert calibration.correct(1 + 0j, cal, 3e3) is None


def test_matches_compares_channels_probes_coupling_and_bandwidth_limit():
    cal = make_cal([1e3], [1 + 0j])
    assert calibration.matches(cal, ScopeConfig())
    assert not calibration.matches(None, ScopeConfig())
    assert not calibration.matches(cal, ScopeConfig(ref_channel=2, dut_channel=1))
    assert not calibration.matches(cal, ScopeConfig(dut_channel=3, probe_atten={1: 10.0, 3: 10.0}))
    assert not calibration.matches(cal, ScopeConfig(probe_atten={1: 10.0, 2: 1.0}))
    assert not calibration.matches(cal, ScopeConfig(coupling="AC"))
    assert not calibration.matches(cal, ScopeConfig(bw_limit=True))
    # settings that do not change the measurement paths do not matter
    assert calibration.matches(cal, ScopeConfig(target_cycles=8.0, probe_atten={1: 10.0, 2: 10.0, 3: 1.0}))


def test_texts():
    cal = make_cal([50.0, 20e6], [1 + 0j, 1 + 0j])
    assert calibration.range_text(cal) == "50 Hz to 20 MHz"
    assert calibration.describe(cal) == "cal: 21:15, 50 Hz to 20 MHz"
    assert calibration.describe(None) == "cal: none"


def test_evaluate_a_good_through():
    pts = [_point(f, 0.05, 0.2) for f in (20e6, 50.0, 1e3)]         # any order in
    cal = calibration.evaluate(pts, ScopeConfig(), 1.0, alignment_epoch=7)
    assert cal.freqs_hz == [50.0, 1e3, 20e6] and cal.alignment_epoch == 7
    assert cal.acceptable and cal.warnings == []
    assert (cal.ref_channel, cal.dut_channel, cal.coupling, cal.bw_limit, cal.amp_vpp) == (1, 2, "DC", False, 1.0)
    assert cal.probe_atten == {1: 10.0, 2: 10.0} and cal.checked_at.startswith("20")
    assert cal.h[0] == pts[1].h


def test_evaluate_warns_about_a_gain_mismatch_but_accepts_it():
    cal = calibration.evaluate([_point(1e3, 0.0), _point(1e6, 0.5)], ScopeConfig(), 1.0)
    assert cal.acceptable and len(cal.warnings) == 1
    assert "Gain mismatch" in cal.warnings[0] and "1 MHz" in cal.warnings[0]


@pytest.mark.parametrize("points, expect", [
    ([_point(1e3, 0.0), _point(1e5, -3.0)], calibration.NOT_A_THROUGH),                 # a filter
    ([_point(1e3, 0.0, vref=0.1)], calibration.NOT_A_THROUGH),                          # 0.2 Vpp of 1 Vpp
    ([_point(1e3, float("-inf"))], calibration.NOT_A_THROUGH),                          # dead DUT channel
    ([_point(1e3), _point(2e3, flags=Flag.CLIPPED)], "CLIPPED at 2 kHz"),
    ([_point(1e3, flags=Flag.REF_SUSPECT | Flag.LOW_SNR)], "REF_SUSPECT at 1 kHz"),
    ([_point(1e3, flags=Flag.BELOW_FLOOR)], "BELOW_FLOOR at 1 kHz"),
    ([_point(1e3, flags=Flag.AUTORANGE_FAILED)], "AUTORANGE_FAILED at 1 kHz")])
def test_evaluate_refuses(points, expect):
    cal = calibration.evaluate(points, ScopeConfig(), 1.0)
    assert not cal.acceptable and any(expect in w for w in cal.warnings)


def test_evaluate_does_not_list_every_bad_point():
    pts = [_point(1e3 * (i + 1), flags=Flag.CLIPPED) for i in range(20)]
    cal = calibration.evaluate(pts, ScopeConfig(), 1.0)
    assert not cal.acceptable and len(cal.warnings) <= 7 and "more" in cal.warnings[-1]
    with pytest.raises(ValueError):
        calibration.evaluate([], ScopeConfig(), 1.0)
```

Note for `_point(1e3, float("-inf"))`: `_h(-inf, 0)` is `0j`, so that point has `h == 0`.

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_calibration.py -q`
Expected: `ImportError: cannot import name 'calibration'`.

- [ ] **Step 3: Implement**

Create `src/bodeplot/sweep/calibration.py`:

```python
"""Through calibration: the pure part (SPEC.md section 8.7). No Qt, no instrument I/O.

A ThroughCal holds H_cal(f) = Vdut / Vref measured with both probes on one node. A later
measurement is divided by it: H = H_meas / H_cal(f). core.py measures it and decides when
it applies; this module holds the arithmetic and the plausibility rules.
"""
from __future__ import annotations

import bisect
import cmath
import math
from datetime import datetime, timezone

from ..models import Flag, PointResult, ScopeConfig, SweepConfig, SweepType, ThroughCal
from ..units import fmt_si
from . import plan

POINTS_PER_DECADE = 10
MIN_HZ = 50.0
# Above 40 % of the scope bandwidth the single-channel amplitudes fall (plan.make_plan warns
# at the same limit); on the UPO1054 this is the 20 MHz the skew check also stops at.
MAX_FRACTION_OF_BANDWIDTH = 0.4
EDGE_TOL = 1e-3                 # a frequency within 0.1 % of a calibration point is that point
REFUSE_GAIN_DB = 1.0            # more than this is not a through connection
WARN_GAIN_DB = 0.3              # the skew check's limit (measure/skew.py GAIN_WARN_DB)
REF_LEVEL_FRACTION = 0.3        # as core.REF_LEVEL_WARN_FRACTION
BLOCKING_FLAGS = Flag.REF_SUSPECT | Flag.CLIPPED | Flag.BELOW_FLOOR | Flag.AUTORANGE_FAILED
MAX_FLAG_LINES = 5
NOT_A_THROUGH = "This does not look like a through connection"


def frequencies(source_min_hz: float, source_max_hz: float, scope_min_hz: float, scope_max_hz: float,
                bandwidth_hz: float | None) -> list[float]:
    """Always the full range both instruments reach, 10 points per decade."""
    lo = max(source_min_hz, scope_min_hz, MIN_HZ)
    hi = min(source_max_hz, scope_max_hz)
    if bandwidth_hz:
        hi = min(hi, MAX_FRACTION_OF_BANDWIDTH * bandwidth_hz)
    if hi <= lo:
        raise ValueError("the instruments share no frequency range to calibrate")
    return plan.frequencies(SweepConfig(SweepType.LOG, lo, hi, POINTS_PER_DECADE))


def _gain_db(h: complex) -> float:
    return 20.0 * math.log10(abs(h)) if abs(h) > 0 else float("-inf")


def _unwrapped_deg(cal: ThroughCal) -> list[float]:
    out: list[float] = []
    for h in cal.h:
        p = math.degrees(cmath.phase(h))
        if out:
            p += 360.0 * round((out[-1] - p) / 360.0)
        out.append(p)
    return out


def fitted_delay_s(cal: ThroughCal) -> float:
    """The delay (DUT minus reference) that fits the phase best: phase = 360 f dt,
    least squares through the origin."""
    den = sum(f * f for f in cal.freqs_hz)
    if not den:
        return 0.0
    return sum(f * p for f, p in zip(cal.freqs_hz, _unwrapped_deg(cal))) / (360.0 * den)


def max_gain_db(cal: ThroughCal) -> float:
    """Largest gain deviation from 0 dB, as a magnitude."""
    return max(abs(_gain_db(h)) for h in cal.h)


def response_at(cal: ThroughCal, freq_hz: float) -> complex | None:
    """H_cal at freq_hz, or None outside the calibrated range (no extrapolation).

    Between two points the gain in dB is linear in log frequency. The phase is not
    interpolated as it stands: most of it is the channel delay, which is linear in
    frequency, and a straight line over log f would miss it by 0.09 deg near 18 MHz in the
    +2.15 ns state. So the fitted delay is taken out, the remainder is interpolated in
    log f, and the delay is put back exactly."""
    fs = cal.freqs_hz
    if not fs or not freq_hz > 0:
        return None
    if freq_hz < fs[0] * (1 - EDGE_TOL) or freq_hz > fs[-1] * (1 + EDGE_TOL):
        return None
    for f, h in zip(fs, cal.h):
        if abs(freq_hz - f) <= EDGE_TOL * f:
            return h
    i = bisect.bisect_right(fs, freq_hz)            # fs[i - 1] < freq_hz < fs[i]
    f0, f1 = fs[i - 1], fs[i]
    x = math.log(freq_hz / f0) / math.log(f1 / f0)
    dt = fitted_delay_s(cal)
    ph = _unwrapped_deg(cal)
    r0, r1 = ph[i - 1] - 360.0 * f0 * dt, ph[i] - 360.0 * f1 * dt
    g0, g1 = _gain_db(cal.h[i - 1]), _gain_db(cal.h[i])
    gain = g0 + x * (g1 - g0)
    phase = r0 + x * (r1 - r0) + 360.0 * freq_hz * dt
    if not math.isfinite(gain):
        return 0j
    return cmath.rect(10 ** (gain / 20.0), math.radians(phase))


def correct(h_meas: complex, cal: ThroughCal, freq_hz: float) -> tuple[complex, float, float] | None:
    """(H_meas / H_cal, gain removed in dB, phase removed in degrees), or None when the
    calibration says nothing usable about this frequency."""
    h_cal = response_at(cal, freq_hz)
    if h_cal is None or not math.isfinite(abs(h_cal)) or abs(h_cal) == 0:
        return None
    return h_meas / h_cal, _gain_db(h_cal), math.degrees(cmath.phase(h_cal))


def _probe(atten: dict, ch: int) -> float:
    return float(atten.get(ch, 1.0)) or 1.0         # as DualChannelScopeMeter reads it


def matches(cal: ThroughCal | None, scope_cfg: ScopeConfig) -> bool:
    """True when the calibration was measured through the same paths as scope_cfg uses."""
    if cal is None:
        return False
    same = (cal.ref_channel, cal.dut_channel, cal.coupling, bool(cal.bw_limit)) == (
        scope_cfg.ref_channel, scope_cfg.dut_channel, scope_cfg.coupling, bool(scope_cfg.bw_limit))
    return same and all(_probe(cal.probe_atten, ch) == _probe(scope_cfg.probe_atten, ch)
                        for ch in (scope_cfg.ref_channel, scope_cfg.dut_channel))


def covers(cal: ThroughCal, lo_hz: float, hi_hz: float) -> bool:
    return bool(cal.freqs_hz) and lo_hz >= cal.freqs_hz[0] * (1 - EDGE_TOL) and \
        hi_hz <= cal.freqs_hz[-1] * (1 + EDGE_TOL)


def range_text(cal: ThroughCal) -> str:
    return "%s to %s" % (fmt_si(cal.freqs_hz[0], "Hz"), fmt_si(cal.freqs_hz[-1], "Hz"))


def describe(cal: ThroughCal | None) -> str:
    if cal is None:
        return "cal: none"
    return "cal: %s, %s" % (cal.checked_at[11:16], range_text(cal))


def evaluate(points: list[PointResult], scope_cfg: ScopeConfig, amp_vpp: float, alignment_epoch: int = 0,
             now: datetime | None = None) -> ThroughCal:
    """Turn the same-node measurements into a ThroughCal with the plausibility checks of
    the design (section 4). The points carry the raw H: nothing was corrected."""
    pts = sorted(points, key=lambda p: p.freq_hz)
    if not pts:
        raise ValueError("a calibration needs at least one point")
    hz = lambda p: fmt_si(p.freq_hz, "Hz")
    warnings: list[str] = []
    acceptable = True
    size = lambda p: abs(_gain_db(p.h)) if math.isfinite(_gain_db(p.h)) else float("inf")
    worst = max(pts, key=size)
    if size(worst) > REFUSE_GAIN_DB:
        acceptable = False
        warnings.append("%s: the gain is %+.2f dB at %s (limit %.0f dB). Put both probes on the "
                        "generator output." % (NOT_A_THROUGH, _gain_db(worst.h), hz(worst), REFUSE_GAIN_DB))
    low = min(pts, key=lambda p: p.vref_amp)
    if amp_vpp > 0 and 2.0 * low.vref_amp < REF_LEVEL_FRACTION * amp_vpp:
        acceptable = False
        warnings.append("%s: the reference channel saw only %.3g Vpp at %s, with the generator set to "
                        "%.3g Vpp. Check the reference probe and its ground clip."
                        % (NOT_A_THROUGH, 2.0 * low.vref_amp, hz(low), amp_vpp))
    bad = [p for p in pts if p.flags & BLOCKING_FLAGS]
    for p in bad[:MAX_FLAG_LINES]:
        warnings.append("%s at %s: this point cannot be used." % ((p.flags & BLOCKING_FLAGS).to_text(), hz(p)))
    if len(bad) > MAX_FLAG_LINES:
        warnings.append("... and %d more points like these." % (len(bad) - MAX_FLAG_LINES))
    if bad:
        acceptable = False
    if acceptable and size(worst) > WARN_GAIN_DB:
        warnings.append("Gain mismatch between the channels is %+.2f dB at %s (limit %.1f dB): check probe "
                        "compensation, probe settings and the connection."
                        % (_gain_db(worst.h), hz(worst), WARN_GAIN_DB))
    when = (now or datetime.now(timezone.utc)).astimezone().isoformat(timespec="seconds")
    chans = (scope_cfg.ref_channel, scope_cfg.dut_channel)
    return ThroughCal(freqs_hz=[p.freq_hz for p in pts], h=[p.h for p in pts], checked_at=when,
                      alignment_epoch=alignment_epoch, ref_channel=chans[0], dut_channel=chans[1],
                      probe_atten={ch: _probe(scope_cfg.probe_atten, ch) for ch in chans},
                      coupling=scope_cfg.coupling, bw_limit=bool(scope_cfg.bw_limit), amp_vpp=float(amp_vpp),
                      warnings=warnings, acceptable=acceptable)
```

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python -m pytest tests\test_calibration.py -q` — expected `24 passed` (4 + 20; the parametrised refusal test counts 7).
If `test_texts` fails on the time: `checked_at[11:16]` of `"2026-10-06T21:15:00+02:00"` is `"21:15"`.

- [ ] **Step 5: Commit**

```powershell
git add src/bodeplot/sweep/calibration.py tests/test_calibration.py
git commit -m "Through calibration: interpolation, plausibility checks and validity rules (pure functions)"
```

---

### Task 3: Mock scope with a gain tilt

**Files:**
- Modify: `src/bodeplot/drivers/mock.py` (`MockScope.__init__`, `_node_phasors`)
- Test: `tests/test_calibration.py`

**Interfaces:**
- Produces: `MockScope.dut_gain_tilt_db_at_20mhz: float = 0.0`. Gain error of the DUT channel in dB = `dut_gain_error_db + tilt * log10(f / 1 kHz) / log10(20 MHz / 1 kHz)` for f above 1 kHz, `dut_gain_error_db` below. Present in "same node" mode too.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_calibration.py` (extend the imports: `from bodeplot.drivers.mock import SimulatedDUT`, `from bodeplot.models import MeasureSettings, StimulusConfig, SweepConfig, SweepType`, `from bodeplot.sweep.core import SweepRunner`):

```python
# ------------------------------------------------------------------ simulated paths
def test_mock_dut_channel_can_tilt_with_frequency(make_session, no_sleep):
    session = make_session(SimulatedDUT.through(), seed=60, checked=False, skew_enabled=False)
    session.digitizer.dut_gain_tilt_db_at_20mhz = 0.2
    res = SweepRunner(session, SweepConfig(SweepType.LOG, 100.0, 20e6, 2), StimulusConfig(), ScopeConfig(),
                      MeasureSettings(), sleep=no_sleep).run()
    assert res.points[0].freq_hz == 100.0 and res.points[-1].freq_hz == 20e6
    for p in res.points:                                          # flat to 1 kHz, then linear in log f
        expect = 0.2 * math.log10(p.freq_hz / 1e3) / math.log10(20e6 / 1e3) if p.freq_hz > 1e3 else 0.0
        assert p.gain_db == pytest.approx(expect, abs=0.02), p.freq_hz
    assert res.points[-1].gain_db == pytest.approx(0.2, abs=0.02)
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv\Scripts\python -m pytest tests\test_calibration.py -k tilt -q`
Expected: FAIL, 20 MHz reads about 0.0 dB instead of 0.2.

- [ ] **Step 3: Implement**

In `MockScope.__init__`, after the `dut_gain_error_db` line:

```python
        self.dut_gain_tilt_db_at_20mhz = 0.0    # test hook: gain error growing with log f above 1 kHz
```

Add this method above `_node_phasors`:

```python
    def _dut_gain_error(self, f: float) -> float:
        """Gain error of the DUT channel as a factor: the constant part plus the tilt (what
        a probe trimmed for another input does, HW_REPORT.md 13.19). It belongs to the
        channel, so the 'same node' mode keeps it."""
        tilt = 0.0
        if f > 1e3:
            tilt = self.dut_gain_tilt_db_at_20mhz * math.log10(f / 1e3) / math.log10(20e6 / 1e3)
        return 10 ** ((self.dut_gain_error_db + tilt) / 20.0)
```

In `_node_phasors` replace `dut = ref * h * 10 ** (self.dut_gain_error_db / 20.0)` with:

```python
        dut = ref * h * self._dut_gain_error(src.freq_hz)
```

Also extend the module docstring's last line to mention it: `50 MHz roll-off, the UPO1054's channel skew fault (section 8.6) and an optional gain tilt of the DUT channel (section 8.7).`

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python -m pytest tests\test_calibration.py tests\test_skew.py -q` — expected all pass.

- [ ] **Step 5: Commit**

```powershell
git add src/bodeplot/drivers/mock.py tests/test_calibration.py
git commit -m "Mock scope: optional gain tilt of the DUT channel"
```

---

### Task 4: Measuring it and keeping it valid (`sweep/core.py`)

**Files:**
- Modify: `src/bodeplot/sweep/core.py` (imports, `Session`, new functions after `run_skew_check`)
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: `calibration.frequencies`, `calibration.evaluate`, `calibration.matches`; `DualChannelScopeMeter`, `MeasureCancelled`, `measure_with_output`, `save_bad_capture`, `watchdog_message` (all already in `core.py`).
- Produces:
  - `Session.cal: ThroughCal | None`, `Session.accept_cal(cal)`, `Session.invalidate_cal()`, `Session.cal_current() -> ThroughCal | None` (drops a calibration whose epoch is over), `Session.cal_for(scope_cfg) -> ThroughCal | None`
  - `core.through_cal_frequencies(session) -> list[float]`
  - `core.run_through_cal(session, stim, scope_cfg, meas, should_stop=lambda: False, sleep=time.sleep, on_log=None, on_progress=None) -> ThroughCal`. Raises `MeasureCancelled` when stopped, `DriverError` on an instrument fault or a resync during the run. Does NOT store the result.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_calibration.py` (extend imports: `from bodeplot.drivers.base import DriverError`, `from bodeplot.measure.meters import MeasureCancelled`, `from bodeplot.sweep.core import run_through_cal, through_cal_frequencies`):

```python
# ------------------------------------------------------------------ measuring it
def _calibrate(session, no_sleep, scope=None, meas=None, **kw):
    return run_through_cal(session, StimulusConfig(), scope or ScopeConfig(), meas or MeasureSettings(),
                           sleep=no_sleep, **kw)


def test_calibration_finds_the_tilt_and_the_delay(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=61, skew_state=2, checked=False)   # +2.15 ns
    session.digitizer.dut_gain_tilt_db_at_20mhz = 0.2
    progress = []
    cal = _calibrate(session, no_sleep, on_progress=lambda i, n: progress.append((i, n)))
    assert cal.freqs_hz == through_cal_frequencies(session)
    assert cal.freqs_hz[0] == 50.0 and cal.freqs_hz[-1] == 20e6 and len(cal.freqs_hz) == 58
    assert progress[0] == (1, 58) and progress[-1] == (58, 58)
    assert cal.acceptable and cal.warnings == []
    assert calibration.fitted_delay_s(cal) == pytest.approx(2.15e-9, abs=0.05e-9)
    assert calibration.max_gain_db(cal) == pytest.approx(0.2, abs=0.03)
    assert cal.alignment_epoch == session.digitizer.alignment_epoch
    # the simulated DUT probe was moved to the reference node and is back; nothing was stored
    assert session.digitizer.same_node is False and session.cal is None
    assert session.source.output == {1: False, 2: False}
    assert session.skew is None                                    # no skew check was made of it


def test_calibration_is_never_a_fast_preview(make_session, no_sleep):
    from bodeplot.models import Method
    session = make_session(seed=62, checked=False)
    cal = _calibrate(session, no_sleep, meas=MeasureSettings(method=Method.PREVIEW))
    assert cal.acceptable and session.digitizer.running_reads == 0


def test_a_filter_is_refused(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=63, checked=False)
    session.digitizer.sim_set_same_node = lambda on: None           # the probe stays on the filter
    cal = _calibrate(session, no_sleep)
    assert not cal.acceptable and any(calibration.NOT_A_THROUGH in w for w in cal.warnings)


def test_a_gain_mismatch_is_a_warning_only(make_session, no_sleep):
    session = make_session(seed=64, checked=False)
    session.digitizer.dut_gain_error_db = 0.5
    cal = _calibrate(session, no_sleep)
    assert cal.acceptable and any("Gain mismatch" in w for w in cal.warnings)


def test_cancel_leaves_no_result_and_the_generator_off(make_session, no_sleep):
    session = make_session(seed=65, checked=False)
    seen = []
    with pytest.raises(MeasureCancelled):
        _calibrate(session, no_sleep, on_progress=lambda i, n: seen.append(i),
                   should_stop=lambda: len(seen) >= 3)
    assert len(seen) == 3 and session.cal is None
    assert session.source.output == {1: False, 2: False} and session.digitizer.same_node is False


def test_a_resync_during_the_calibration_is_refused(make_session, no_sleep):
    session = make_session(seed=66, checked=False)

    def on_progress(i, n):
        if i == 5:
            session.digitizer.simulate_resync()
    with pytest.raises(DriverError, match="resynchronised"):
        _calibrate(session, no_sleep, on_progress=on_progress)
    assert session.source.output == {1: False, 2: False}


def test_a_generator_fault_switches_off_and_restores(make_session, no_sleep):
    session = make_session(seed=67, checked=False)
    before = session.digitizer.timebase

    def on_progress(i, n):
        if i == 2:
            session.source.fail_next = "generator said no"
    with pytest.raises(DriverError, match="generator said no"):
        _calibrate(session, no_sleep, on_progress=on_progress)
    assert session.source.output == {1: False, 2: False}
    assert session.digitizer.timebase == before and session.digitizer.same_node is False


# ------------------------------------------------------------------ validity
def test_validity(make_session, no_sleep):
    session = make_session(seed=68, checked=False)
    assert session.cal_for(ScopeConfig()) is None
    cal = _calibrate(session, no_sleep)
    session.accept_cal(cal)
    assert session.cal_for(ScopeConfig()) is cal
    assert not session.skew_valid()                                # an independent record
    # other settings: not used, but kept (the user may switch back)
    for other in (ScopeConfig(ref_channel=2, dut_channel=1),
                  ScopeConfig(probe_atten={1: 10.0, 2: 1.0}),
                  ScopeConfig(coupling="AC"), ScopeConfig(bw_limit=True)):
        assert session.cal_for(other) is None
    assert session.cal is cal and session.cal_for(ScopeConfig()) is cal
    # a resync ends it for good
    session.digitizer.simulate_resync()
    assert session.cal_for(ScopeConfig()) is None and session.cal is None
    # front panel
    session.accept_cal(_calibrate(session, no_sleep))
    session.front_panel_used()
    assert session.cal is None
    # reconnect
    session.accept_cal(_calibrate(session, no_sleep))
    session.close()
    session.open()
    assert session.cal is None and session.cal_for(ScopeConfig()) is None
    # a lost connection
    session.accept_cal(_calibrate(session, no_sleep))
    session.mark_dead("gone")
    assert session.cal is None
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_calibration.py -q`
Expected: `ImportError: cannot import name 'run_through_cal'`.

- [ ] **Step 3: Implement**

`src/bodeplot/sweep/core.py`:

Imports: add `ThroughCal` to the `..models` import list, and change `from . import plan as plan_mod` to:

```python
from . import calibration
from . import plan as plan_mod
```

Update the `Session` docstring to `"""One connection to a source and a digitizer, and the skew check and the through calibration that belong to it."""` and add the field after `skew`:

```python
    cal: ThroughCal | None = None
```

In `Session.open`, after the `self.invalidate_skew(...)` line:

```python
        self.invalidate_cal()
```

In `Session.mark_dead`, after `self.invalidate_skew("The connection was lost.")`:

```python
        self.invalidate_cal()
```

In `Session.front_panel_used`, after the `invalidate_skew` line:

```python
        self.invalidate_cal()
```

After `Session.skew_delay`:

```python
    # ---- through calibration validity (SPEC.md 8.7)
    def accept_cal(self, cal: ThroughCal) -> None:
        """Independent of the skew check: accepting one does not create or change the other."""
        self.cal = cal

    def invalidate_cal(self) -> None:
        self.cal = None

    def cal_current(self) -> ThroughCal | None:
        """The calibration of this connection. One measured before a resync is dropped:
        the channel alignment may have changed."""
        if self.cal is not None and self.cal.alignment_epoch != self.digitizer.alignment_epoch:
            self.cal = None
        return self.cal

    def cal_for(self, scope_cfg: ScopeConfig) -> ThroughCal | None:
        """The calibration, if it was measured through the paths scope_cfg uses. One that
        only fails this test is kept: the user may switch the setting back."""
        cal = self.cal_current()
        return cal if calibration.matches(cal, scope_cfg) else None
```

After `run_skew_check` (before `watchdog_message`):

```python
# ---------------------------------------------------------------------- through calibration
def through_cal_frequencies(session: Session) -> list[float]:
    s, d = session.source.caps, session.digitizer.caps
    return calibration.frequencies(s.sine_min_hz, s.sine_max_hz, d.min_hz, d.max_hz or d.bandwidth_hz,
                                   d.bandwidth_hz)


def run_through_cal(session: Session, stim: StimulusConfig, scope_cfg: ScopeConfig, meas: MeasureSettings,
                    should_stop: Callable[[], bool] = lambda: False,
                    sleep: Callable[[float], None] = time.sleep,
                    on_log: Callable[[LogEntry], None] | None = None,
                    on_progress: Callable[[int, int], None] | None = None) -> ThroughCal:
    """Measure Vdut / Vref over the full range with both probes on the same node (SPEC.md
    8.7). The caller has already asked the user to connect them. Always Sine fit on single
    shots, with the averages and settle times given: a Fast preview's phase scatter would
    be built into every later result. No skew correction is applied. Same safety frame as
    a sweep. Raises MeasureCancelled when stopped. Does not store the result: see
    Session.accept_cal."""
    src, dig = session.source, session.digitizer
    freqs = through_cal_frequencies(session)

    def say(level, text):
        if on_log:
            on_log(LogEntry(level, text, _now_iso()))

    def bad(info):
        text = save_bad_capture(session, info)
        log.warning(text)
        say("warn", text)

    meter = DualChannelScopeMeter(dig, scope_cfg, should_stop, sleep, on_bad_capture=bad)
    settings = MeasureSettings(**{**meas.__dict__, "method": Method.SINEFIT})
    same_node = getattr(dig, "sim_set_same_node", None)     # simulation only
    points: list[PointResult] = []
    epoch = dig.alignment_epoch
    try:
        if same_node:
            same_node(True)
        session.begin_measurement()
        src.configure_sine(stim.gen_channel, freqs[0], stim.amp_vpp, stim.offset_v, stim.load)
        meter.prepare(stim.amp_vpp, stim.offset_v)
        src.set_output(stim.gen_channel, True)
        state = meter.initial_state()
        for i, f in enumerate(freqs):
            if should_stop():
                raise MeasureCancelled()
            src.set_frequency(stim.gen_channel, f)
            settle = lambda f=f: sleep(max(meas.settle_ms / 1000.0, meas.settle_cycles / f))
            settle()
            point, _ = measure_with_output(session, stim.gen_channel,
                                           lambda f=f: meter.measure(f, settings, state), settle,
                                           lambda text: say("warn", text))
            points.append(point)
            if on_progress:
                on_progress(i + 1, len(freqs))
    except InstrumentUnresponsive as e:
        src.safe_off()
        session.mark_dead(watchdog_message(e))
        raise DriverError(session.dead_reason, e.last_command)
    finally:
        src.safe_off()
        if same_node:
            same_node(False)
        if session.dead_reason is None:
            session.end_measurement()
    if dig.alignment_epoch != epoch:
        raise DriverError("The scope was resynchronised during the calibration: its points may belong "
                          "to two alignment states. Measure it again.")
    return calibration.evaluate(points, scope_cfg, stim.amp_vpp, alignment_epoch=epoch)
```

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python -m pytest tests\test_calibration.py -q` — expected all pass (33).
Run: `.venv\Scripts\python -m pytest -q` — expected no failure.

If `test_a_generator_fault_switches_off_and_restores` fails on the timebase: `MockScope.restore_setup` puts back what `save_setup` stored in `begin_measurement`; check that the `finally` reaches `end_measurement`.

- [ ] **Step 5: Commit**

```powershell
git add src/bodeplot/sweep/core.py tests/test_calibration.py
git commit -m "Through calibration: measure it (run_through_cal) and keep it valid per connection and scope settings"
```

---

### Task 5: Applying it in a sweep (`SweepRunner`)

**Files:**
- Modify: `src/bodeplot/sweep/core.py` (`SweepRunner._meta`, `_measure_one`, `run`, `remeasure`, new `_correct`)
- Test: `tests/test_calibration.py`, `tests/test_drivers.py`

**Interfaces:**
- Consumes: `Session.cal_for`, `calibration.correct`, `calibration.covers`, `calibration.range_text`.
- Produces: per point `Flag.CALIBRATED`, `cal_gain_db`, `cal_phase_deg` where the calibration covers the frequency; `SweepResult.meta["cal"]` (`ThroughCal.to_meta()` or `None`); `meta["skew"]` / `meta["skew_applied_s"]` are `None` when the calibration covered the whole sweep. Log line `"Through calibration of HH:MM applied."`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_calibration.py` (extend imports: `from bodeplot.models import Method`, `from bodeplot.sweep.core import Callbacks, run_skew_check`):

```python
# ------------------------------------------------------------------ applying it
def _sweep(session, no_sleep, lo=50.0, hi=20e6, ppd=20, meas=None, scope=None, logs=None):
    cb = Callbacks(log=lambda e: logs.append((e.level, e.text))) if logs is not None else None
    return SweepRunner(session, SweepConfig(SweepType.LOG, lo, hi, ppd), StimulusConfig(),
                       scope or ScopeConfig(), meas or MeasureSettings(), cb, sleep=no_sleep)


def _tilted(make_session, dut, seed, checked=False):
    session = make_session(dut, seed=seed, skew_state=2, checked=checked)       # +2.15 ns
    session.digitizer.dut_gain_tilt_db_at_20mhz = 0.2
    return session


def test_through_sweep_reads_zero_after_calibration(make_session, no_sleep):
    """Design, success criterion 1. Four averages keep the simulator's noise (0.013 dB and
    0.08 deg between two single sweeps) well inside the limits; 20 points per decade puts
    every second point between two calibration points."""
    meas = MeasureSettings(averages=4)
    session = _tilted(make_session, SimulatedDUT.through(), 70)
    session.accept_cal(_calibrate(session, no_sleep, meas=meas))
    logs = []
    res = _sweep(session, no_sleep, meas=meas, logs=logs).run()
    assert res.meta["error"] is None and len(res.points) > 100
    assert max(abs(p.gain_db) for p in res.points) < 0.02
    assert max(abs(p.phase_deg) for p in res.points) < 0.1
    assert all(p.flags & Flag.CALIBRATED and not p.flags & Flag.SKEW_UNCHECKED for p in res.points)
    top = res.points[-1]
    assert top.cal_gain_db == pytest.approx(0.2, abs=0.03)
    assert top.cal_phase_deg == pytest.approx(360 * 20e6 * 2.15e-9, abs=0.3)   # 15.5 deg: the delay is in it
    assert top.skew_corr_deg == 0.0
    assert any("Through calibration of" in t and "applied" in t for _, t in logs)
    assert not any("skew" in t.lower() for _, t in logs)
    assert len(res.meta["cal"]["freqs_hz"]) == 58 and res.meta["skew"] is None
    assert res.meta["skew_applied_s"] is None


def test_rc_low_pass_is_right_with_the_tilt_present(make_session, no_sleep):
    r, c = 1e3, 100e-9
    fc = 1 / (2 * math.pi * r * c)
    session = _tilted(make_session, SimulatedDUT.rc_lpf(r, c), 71)
    session.accept_cal(_calibrate(session, no_sleep))
    res = _sweep(session, no_sleep).run()
    by = lambda f: min(res.points, key=lambda p: abs(math.log(p.freq_hz / f)))
    for f in (100.0, fc, 1e4):                                    # further down the DUT signal is small
        p = by(f)
        h = 1 / (1 + 1j * p.freq_hz / fc)
        assert p.gain_db == pytest.approx(20 * math.log10(abs(h)), abs=0.05)
        assert p.phase_deg == pytest.approx(math.degrees(cmath.phase(h)), abs=1.0)


def test_without_a_calibration_nothing_changes(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=72, skew_state=2)        # skew checked
    res = _sweep(session, no_sleep, 1e3, 1e6, 3).run()
    assert res.meta["cal"] is None and res.meta["skew"] is not None
    assert all(p.cal_gain_db == 0.0 and p.cal_phase_deg == 0.0 and not p.flags & Flag.CALIBRATED
               for p in res.points)
    assert all(p.skew_corr_deg != 0.0 for p in res.points)


def test_beyond_the_range_the_skew_check_is_used(make_session, no_sleep):
    session = _tilted(make_session, SimulatedDUT.through(), 73)
    session.accept_cal(_calibrate(session, no_sleep))
    session.accept_skew(run_skew_check(session, StimulusConfig(), ScopeConfig(), MeasureSettings(),
                                       sleep=no_sleep))
    logs = []
    res = _sweep(session, no_sleep, 5e6, 30e6, 10, logs=logs).run()             # the mock reaches 30 MHz
    inside = [p for p in res.points if p.freq_hz <= 20e6 * 1.001]
    outside = [p for p in res.points if p.freq_hz > 20e6 * 1.001]
    assert inside and outside
    assert all(p.flags & Flag.CALIBRATED for p in inside)
    assert all(not p.flags & Flag.CALIBRATED and not p.flags & Flag.SKEW_UNCHECKED and p.skew_corr_deg != 0.0
               and abs(p.phase_deg) < 0.5 for p in outside)
    warns = [t for lvl, t in logs if lvl == "warn" and "covers" in t]
    assert len(warns) == 1 and "50 Hz to 20 MHz" in warns[0] and "skew correction" in warns[0]
    assert res.meta["cal"] is not None and res.meta["skew"] is not None


def test_beyond_the_range_without_a_skew_check_is_flagged(make_session, no_sleep):
    session = _tilted(make_session, SimulatedDUT.through(), 74)
    session.accept_cal(_calibrate(session, no_sleep))
    logs = []
    res = _sweep(session, no_sleep, 5e6, 30e6, 10, logs=logs).run()
    outside = [p for p in res.points if p.freq_hz > 20e6 * 1.001]
    assert outside and all(p.flags & Flag.SKEW_UNCHECKED for p in outside)
    assert all(not p.flags & Flag.SKEW_UNCHECKED for p in res.points if p.flags & Flag.CALIBRATED)
    assert any("covers" in t and "SKEW_UNCHECKED" in t for lvl, t in logs if lvl == "warn")


def test_a_calibration_for_other_settings_is_not_applied(make_session, no_sleep):
    session = _tilted(make_session, SimulatedDUT.through(), 75)
    session.accept_cal(_calibrate(session, no_sleep))
    res = _sweep(session, no_sleep, 1e5, 1e6, 3, scope=ScopeConfig(coupling="AC")).run()
    assert res.meta["cal"] is None and all(p.flags & Flag.SKEW_UNCHECKED for p in res.points)
    res = _sweep(session, no_sleep, 1e5, 1e6, 3).run()                           # back to DC: used again
    assert all(p.flags & Flag.CALIBRATED for p in res.points)


def test_fast_preview_and_remeasure_use_the_calibration(make_session, no_sleep):
    session = _tilted(make_session, SimulatedDUT.through(), 76)
    session.accept_cal(_calibrate(session, no_sleep))
    res = _sweep(session, no_sleep, 1e5, 1e6, 3, meas=MeasureSettings(method=Method.PREVIEW)).run()
    assert all(p.flags & Flag.PREVIEW and p.flags & Flag.CALIBRATED for p in res.points)
    runner = _sweep(session, no_sleep, 1e5, 1e6, 3)
    res = runner.run()
    again = runner.remeasure(res, res.points[1].freq_hz)
    assert again.flags & Flag.CALIBRATED and again.flags & Flag.REMEASURED
    assert abs(again.gain_db) < 0.05
    session.invalidate_cal()                                         # the rule at the time of the re-measure
    again = runner.remeasure(res, res.points[1].freq_hz)
    assert not again.flags & Flag.CALIBRATED and again.flags & Flag.SKEW_UNCHECKED


def test_a_resync_during_a_calibrated_sweep_is_reported(make_session, no_sleep):
    session = _tilted(make_session, SimulatedDUT.through(), 77)
    session.accept_cal(_calibrate(session, no_sleep))
    logs, done = [], []

    def on_point(p):
        if not done:
            done.append(1)
            session.digitizer.simulate_resync()
    runner = SweepRunner(session, SweepConfig(SweepType.LOG, 1e5, 1e6, 3), StimulusConfig(), ScopeConfig(),
                         MeasureSettings(), Callbacks(point=on_point, log=lambda e: logs.append(e.text)),
                         sleep=no_sleep)
    res = runner.run()
    assert res.meta["error"] is None and session.cal is None
    assert any("through calibration used may no longer be right" in t for t in logs)
```

Append to `tests/test_drivers.py`, after `test_a_resync_during_a_sweep_invalidates_the_skew_check` (extend its imports: `from bodeplot.models import Flag`, `from bodeplot.sweep import calibration`, `from bodeplot.sweep.core import run_through_cal`):

```python
def test_through_calibration_then_sweep_with_the_real_drivers():
    session, fgen, fscope, clock = fake_bench(delay=2.15e-9)
    cal = run_through_cal(session, StimulusConfig(), ScopeConfig(), MeasureSettings(), sleep=clock.sleep)
    assert cal.acceptable and cal.freqs_hz[0] == 50.0 and cal.freqs_hz[-1] == 20e6
    assert calibration.fitted_delay_s(cal) == pytest.approx(2.15e-9, abs=0.05e-9)
    assert not fgen.ch[1]["output"] and not fgen.ch[2]["output"] and not fscope.lock
    assert fscope.sweep == "AUTO" and fscope.mode == "run"
    session.accept_cal(cal)
    rc = 1e3 * 100e-9
    fscope.h = lambda f: 1.0 / (1.0 + 2j * math.pi * f * rc)         # the DUT probe moves to the filter
    result = SweepRunner(session, SweepConfig(start_hz=100.0, stop_hz=1e7, points_per_decade=3),
                         StimulusConfig(), ScopeConfig(), MeasureSettings(), sleep=clock.sleep).run()
    assert result.meta["error"] is None and all(p.flags & Flag.CALIBRATED for p in result.points)
    for p in result.points:
        if p.gain_db < -40:
            continue                                                 # into the noise: not this test
        h = 1.0 / (1.0 + 2j * math.pi * p.freq_hz * rc)
        assert p.gain_db == pytest.approx(20 * math.log10(abs(h)), abs=0.15)
        assert p.phase_deg == pytest.approx(math.degrees(math.atan2(h.imag, h.real)), abs=1.0)
    assert not fgen.ch[1]["output"] and not fgen.ch[2]["output"] and not fscope.lock
    assert fscope.sweep == "AUTO" and fscope.mode == "run"
    assert fscope.forbidden == []                                    # never ':RUN'
    session.close()
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_calibration.py tests\test_drivers.py -k "calibration or applying or zero_after or tilt_present or beyond or other_settings or preview_and or resync_during_a_calibrated or nothing_changes" -q`
Expected: failures on `Flag.CALIBRATED` not set and `KeyError: 'cal'`.

- [ ] **Step 3: Implement**

In `SweepRunner`, after `_apply_skew`:

```python
    def _correct(self, point: PointResult, cal: ThroughCal | None, delay_s: float | None) -> PointResult:
        """The through calibration where it covers the frequency (it holds the delay, so no
        skew correction on top); elsewhere the skew correction as before."""
        out = calibration.correct(point.h, cal, point.freq_hz) if cal is not None else None
        if out is None:
            return self._apply_skew(point, delay_s)
        point.h, point.cal_gain_db, point.cal_phase_deg = out
        point.gain_db, point.phase_deg = sinefit.gain_phase(point.h)
        point.flags |= Flag.CALIBRATED
        return point
```

Replace `_meta` with:

```python
    def _meta(self, started: str, delay_s: float | None, aborted: bool, error: str | None,
              cal: ThroughCal | None = None) -> dict:
        s = self.session
        return {
            "app_version": __version__, "started": started, "finished": _now_iso(),
            "source_idn": s.source_idn, "digitizer_idn": s.digitizer_idn, "simulated": s.simulated,
            "aborted": aborted, "error": error,
            "skew": s.skew.to_meta() if (delay_s is not None and s.skew is not None) else None,
            "skew_applied_s": delay_s,
            "skew_text": skew.describe(s.skew if delay_s is not None else None),
            # the calibration itself: a saved result documents what was divided out
            "cal": cal.to_meta() if cal is not None else None,
        }
```

In `_measure_one`: change the signature to

```python
    def _measure_one(self, meter: ResponseMeter, state: MeterState, f: float,
                     delay_s: float | None, cal: ThroughCal | None = None) -> PointResult:
```

and the line `point = self._apply_skew(point, delay_s)` to `point = self._correct(point, cal, delay_s)`.

In `run()`:

Replace `delay_s = self.session.skew_delay()` with:

```python
        # decided once per sweep: the calibration first, the skew delay where it does not reach
        cal = self.session.cal_for(self.scope_cfg)
        delay_s = self.session.skew_delay()
        covered = False
```

Replace the block from `if self.meas.method is Method.PREVIEW:` to the `self._log("info", "Channel skew correction: ...")` line with:

```python
            if cal is not None:
                covered = calibration.covers(cal, min(p.freqs_hz), max(p.freqs_hz))
                self._log("info", "Through calibration of %s applied." % cal.checked_at[11:16])
                if not covered:
                    self._log("warn", "The through calibration covers %s only. Outside it %s." % (
                        calibration.range_text(cal),
                        "the skew correction of %+.2f ns is used" % (delay_s * 1e9) if delay_s is not None
                        else "the phase is NOT corrected and the points are flagged SKEW_UNCHECKED"))
            if self.meas.method is Method.PREVIEW:
                self._log("info", PREVIEW_NOTE)
            elif cal is not None:
                pass                                    # said above
            elif delay_s is None:
                self._log("warn", "No valid channel skew check: phase is NOT corrected and every "
                                  "point is flagged SKEW_UNCHECKED. " + (self.session.recheck_reason or ""))
            else:
                self._log("info", "Channel skew correction: %+.2f ns." % (delay_s * 1e9))
```

Change `points.append(self._measure_one(meter, state, f, delay_s))` to `points.append(self._measure_one(meter, state, f, delay_s, cal))`.

After the existing "resynchronised during the sweep" block (the one that tests `skew_valid()`), add:

```python
        if cal is not None and self.session.dead_reason is None and self.session.cal_for(self.scope_cfg) is None:
            self._log("warn", "The scope was resynchronised during the sweep; the through calibration used "
                              "may no longer be right. Calibrate again.")
```

and guard the existing skew block so that it stays silent when the skew delay was never used: change its condition to

```python
        if delay_s is not None and not covered and not self.session.skew_valid() and self.session.dead_reason is None:
```

Change the `SweepResult(...)` line to:

```python
        result = SweepResult(config, points, self._meta(started, None if covered else delay_s,
                                                        self._abort.is_set(), error, cal))
```

In `remeasure()`: after `delay_s = self.session.skew_delay()` add `cal = self.session.cal_for(self.scope_cfg)`, and change the call to `point = self._measure_one(meter, state, freq_hz, delay_s, cal)`.

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python -m pytest tests\test_calibration.py tests\test_drivers.py tests\test_sweep.py tests\test_skew.py -q` — expected all pass.
Run: `.venv\Scripts\python -m pytest -q` — expected no failure.

If `test_through_sweep_reads_zero_after_calibration` misses 0.1 deg by a few hundredths: print the worst point's frequency. A miss only at frequencies between calibration points means the delay is not being put back (`response_at`); a miss everywhere means noise, and the seed may be changed, not the limit.

- [ ] **Step 5: Commit**

```powershell
git add src/bodeplot/sweep/core.py tests/test_calibration.py tests/test_drivers.py
git commit -m "Sweep and re-measure use the through calibration where it applies, the skew check elsewhere"
```

---

### Task 6: Exports

**Files:**
- Modify: `src/bodeplot/io/export_csv.py`, `src/bodeplot/io/export_touchstone.py`, `src/bodeplot/io/export_image.py`
- Test: `tests/test_io.py`

**Interfaces:**
- Consumes: `ThroughCal.from_meta`, `calibration.max_gain_db`, `calibration.describe`.
- Produces: `export_csv.COLUMNS` ends with `"cal_gain_db", "cal_phase_deg"`; `export_csv.cal_header(meta) -> list[tuple[str, str]]`; `export_csv.describe_correction(meta) -> str`; `skew_header` says `"not used (the through calibration was applied)"` when a calibration covered the sweep.

- [ ] **Step 1: Write the failing tests**

In `tests/test_io.py`, add to the imports `from bodeplot.models import ThroughCal` and `from bodeplot.sweep.core import run_through_cal`, add this fixture after `unchecked_result`:

```python
@pytest.fixture
def cal_result(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=52, skew_state=2, checked=False)
    session.digitizer.dut_gain_tilt_db_at_20mhz = 0.2
    session.accept_cal(run_through_cal(session, StimulusConfig(), ScopeConfig(), MeasureSettings(),
                                       sleep=no_sleep))
    return SweepRunner(session, SweepConfig(SweepType.LOG, 100.0, 1e6, 6), StimulusConfig(),
                       ScopeConfig(), MeasureSettings(), sleep=no_sleep).run()
```

and these tests after `test_csv_loader_tolerates_a_minimal_file`:

```python
def test_csv_round_trip_with_a_calibration(tmp_path, cal_result):
    path = export_csv.write_csv(tmp_path / "cal.csv", cal_result)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert "# cal: applied" in lines and "# cal_points: 58" in lines
    assert "# cal_range_hz: 50, 2e+07" in lines
    assert any(l.startswith("# cal_checked_at: 20") for l in lines)
    assert any(l.startswith("# cal_max_gain_db: 0.") for l in lines)
    assert "# skew: not used (the through calibration was applied)" in lines
    header = next(l for l in lines if not l.startswith("#"))
    assert header.split(",")[-2:] == ["cal_gain_db", "cal_phase_deg"]
    back = export_csv.load_csv(path)
    for a, b in zip(cal_result.points, back.points):
        assert b.flags == a.flags and b.flags & Flag.CALIBRATED
        assert b.cal_gain_db == pytest.approx(a.cal_gain_db, abs=1e-15)
        assert b.cal_phase_deg == pytest.approx(a.cal_phase_deg, abs=1e-12)
        # the raw measurement can be recovered (design, success criterion 3)
        assert b.gain_db + b.cal_gain_db == pytest.approx(a.gain_db + a.cal_gain_db, abs=1e-12)
    cal = ThroughCal.from_meta(back.meta["cal"])
    assert cal is not None and len(cal.freqs_hz) == 58 and len(cal.h) == 58
    assert cal == ThroughCal.from_meta(cal_result.meta["cal"])


def test_csv_without_a_calibration_says_none(tmp_path, result):
    text = export_csv.write_csv(tmp_path / "n.csv", result).read_text(encoding="utf-8")
    assert "# cal: none" in text and "# cal_points" not in text and "# skew: checked" in text
    back = export_csv.load_csv(tmp_path / "n.csv")
    assert back.meta["cal"] is None and all(p.cal_gain_db == 0.0 for p in back.points)


def test_touchstone_and_image_name_the_calibration(tmp_path, cal_result, result):
    text = export_touchstone.write_touchstone(tmp_path / "c.s2p", cal_result).read_text(encoding="utf-8")
    assert "! cal: applied" in text and "! cal_points: 58" in text
    assert "NOT a calibrated S-parameter measurement" in text           # the warning stays
    assert "! cal: none" in export_touchstone.write_touchstone(tmp_path / "n.s2p", result).read_text(encoding="utf-8")
    assert export_csv.describe_correction(cal_result.meta).startswith("cal: ")
    assert export_csv.describe_correction(result.meta).startswith("skew: ")
    assert export_image.write_image(tmp_path / "c.png", cal_result).stat().st_size > 200
```

In the existing `test_csv_loader_tolerates_a_minimal_file` add one line at the end:

```python
    assert back.points[0].cal_gain_db == 0.0 and back.points[0].cal_phase_deg == 0.0
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_io.py -q`
Expected: the three new tests fail (`# cal: applied` missing; `describe_correction` missing).

- [ ] **Step 3: Implement**

`src/bodeplot/io/export_csv.py`:

Imports: `from ..models import Flag, PointResult, SkewCheck, SweepResult, ThroughCal` and `from ..sweep import calibration`.

`COLUMNS`: append `"cal_gain_db", "cal_phase_deg"` after `"flags"`.

In `skew_header`, replace the `if not sk:` branch with:

```python
    if not sk:
        if meta.get("cal"):
            return [("skew", "not used (the through calibration was applied)")]
        return [("skew", "not checked (phase is NOT corrected for channel skew)")]
```

Add after `skew_header`:

```python
def cal_header(meta: dict) -> list[tuple[str, str]]:
    """The through-calibration lines shared by the CSV header and the Touchstone comments."""
    cal = ThroughCal.from_meta(meta.get("cal"))
    if cal is None:
        return [("cal", "none")]
    return [("cal", "applied"),
            ("cal_checked_at", cal.checked_at),
            ("cal_range_hz", "%g, %g" % (cal.freqs_hz[0], cal.freqs_hz[-1])),
            ("cal_points", str(len(cal.freqs_hz))),
            ("cal_max_gain_db", "%.4f" % calibration.max_gain_db(cal))]
```

In `write_csv`: change the header loop to

```python
        for key, value in skew_header(result.meta) + cal_header(result.meta):
            f.write("# %s: %s\n" % (key, value))
```

and the row to end with `p.flags.to_text(), _num(p.cal_gain_db), _num(p.cal_phase_deg)])`.

In `load_csv`, extend the `PointResult(...)` call: after `skew_corr_deg=_f(row, "skew_corr_deg", 0.0)` add `, cal_gain_db=_f(row, "cal_gain_db", 0.0), cal_phase_deg=_f(row, "cal_phase_deg", 0.0)`.

At the end of the file:

```python
def describe_correction(meta: dict) -> str:
    """One line for a footer: the calibration when one was applied, else the skew check."""
    cal = ThroughCal.from_meta(meta.get("cal"))
    return calibration.describe(cal) if cal is not None else describe_skew(meta)
```

`src/bodeplot/io/export_touchstone.py`: import `cal_header` next to `skew_header` and change the loop to `for key, value in skew_header(result.meta) + cal_header(result.meta):`.

`src/bodeplot/io/export_image.py`: import `describe_correction` in place of `describe_skew` and use it in the footer.

A CSV header line `# cal: applied` is read back by `load_csv` into `meta["cal"]` only when the file has no `meta_json` line (the existing `setdefault`); `ThroughCal.from_meta("applied")` is `None`, which Task 1 tests.

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python -m pytest tests\test_io.py tests\test_gui.py -q` — expected all pass (the GUI export test reads `# skew: checked`, unchanged).

- [ ] **Step 5: Commit**

```powershell
git add src/bodeplot/io tests/test_io.py
git commit -m "Exports say whether a through calibration was applied and carry what was removed"
```

---

### Task 7: Engine

**Files:**
- Modify: `src/bodeplot/sweep/engine.py`
- Test: `tests/test_gui.py`

**Interfaces:**
- Consumes: `core.run_through_cal`, `Session.accept_cal` / `invalidate_cal` / `cal_current`, `calibration.describe`, `calibration.max_gain_db`, `calibration.fitted_delay_s`, `calibration.range_text`.
- Produces on `SweepEngine` (and the same slots on `EngineWorker`):
  - `run_cal(cfg: Configs)`, `accept_cal(cal: ThroughCal)`, `discard_cal()`
  - signal `cal_measured(object)`: a `ThroughCal`, or `None` when the run was cancelled. An error goes out on `error` as for the skew check.
  - `progress(int, int)` during the run; `abort()` stops it.
  - `SessionInfo.cal: ThroughCal | None`, `SessionInfo.cal_valid: bool`, `SessionInfo.cal_text: str`. They describe the calibration of the connection; whether it fits the scope settings on screen is the GUI's question (`calibration.matches`), because the worker does not know the panel.

- [ ] **Step 1: Write the failing tests**

In `tests/test_gui.py` add after `_skew_check`:

```python
def _calibrate(win, qtbot):
    with qtbot.waitSignal(win.engine.cal_measured, timeout=30000) as blocker:
        win.engine.run_cal(win.configs())
    cal = blocker.args[0]
    win.engine.accept_cal(cal)
    qtbot.waitUntil(lambda: win.info.cal_valid, timeout=5000)
    return cal
```

and at the end of the file:

```python
# ---------------------------------------------------------------------- through calibration
def test_engine_measures_accepts_and_drops_a_calibration(win, qtbot):
    _connect(win, qtbot)
    assert not win.info.cal_valid and win.info.cal is None and win.info.cal_text == "cal: none"
    progress = []
    win.engine.progress.connect(lambda i, n: progress.append((i, n)))
    cal = _calibrate(win, qtbot)
    assert cal.acceptable and len(cal.freqs_hz) == 58 and progress[-1] == (58, 58)
    assert win.info.cal is cal and win.info.cal_text.startswith("cal: ") and "50 Hz to 20 MHz" in win.info.cal_text
    assert not win.info.skew_valid                               # an independent record
    assert "Through calibration accepted" in win.status_log.text.toPlainText()
    assert win.state is EngineState.IDLE
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.engine.simulate_resync()
    qtbot.waitUntil(lambda: not win.info.cal_valid, timeout=5000)
    _calibrate(win, qtbot)
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.engine.discard_cal()
    qtbot.waitUntil(lambda: not win.info.cal_valid, timeout=5000)
    _calibrate(win, qtbot)
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.front_panel_used()
    qtbot.waitUntil(lambda: not win.info.cal_valid, timeout=5000)


def test_aborting_a_calibration_leaves_none(win, qtbot):
    win.settings.sim["latency_ms"] = 20.0
    _connect(win, qtbot)
    seen = []
    win.engine.progress.connect(lambda i, n: seen.append(i))
    with qtbot.waitSignal(win.engine.cal_measured, timeout=30000) as blocker:
        win.engine.run_cal(win.configs())
        qtbot.waitUntil(lambda: len(seen) >= 2, timeout=20000)
        win.abort()
    assert blocker.args[0] is None and len(seen) < 58
    qtbot.waitUntil(lambda: win.state is EngineState.IDLE, timeout=5000)
    assert not win.info.cal_valid and "Calibration cancelled" in win.status_log.text.toPlainText()


def test_a_refused_calibration_cannot_be_accepted(win, qtbot):
    _connect(win, qtbot)
    with qtbot.waitSignal(win.engine.cal_measured, timeout=30000) as blocker:
        win.engine.run_cal(win.configs())
    cal = blocker.args[0]
    cal.acceptable = False
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.engine.accept_cal(cal)
    assert not win.info.cal_valid and "not accepted" in win.status_log.text.toPlainText()
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_gui.py -k "calibration" -q`
Expected: `AttributeError: 'SessionInfo' object has no attribute 'cal_valid'`.

- [ ] **Step 3: Implement**

`src/bodeplot/sweep/engine.py`:

Imports: add `ThroughCal` to the `..models` list; `from . import calibration`; change the core import to `from .core import Callbacks, Session, SweepRunner, _now_iso, run_skew_check, run_through_cal`.

`SessionInfo`: add at the end

```python
    # The through calibration of this connection (None after a resync). Whether it fits the
    # scope settings on screen is decided by the GUI with calibration.matches().
    cal: ThroughCal | None = None
    cal_valid: bool = False
    cal_text: str = "cal: none"
```

`EngineWorker`: add the signal `cal_measured = Signal(object)          # ThroughCal (not yet accepted), None = cancelled`.

In `_info`, replace the `return SessionInfo(...)` statement with:

```python
        cal = s.cal_current()
        return SessionInfo(True, s.simulated, s.source_idn, s.digitizer_idn, True,
                           caps.has_builtin_amplitude and caps.has_builtin_phase, s.skew, valid,
                           s.recheck_reason, skew.describe(s.skew if valid else None),
                           cal=cal, cal_valid=cal is not None, cal_text=calibration.describe(cal))
```

Add these slots after `accept_skew`:

```python
    @Slot(object)
    def through_cal(self, cfg: Configs):
        if self.session is None:
            self.error.emit("Not connected.")
            return
        self._cancel_skew = False
        self.state_changed.emit(EngineState.RUNNING)
        try:
            cal = run_through_cal(self.session, cfg.stimulus, cfg.scope, cfg.measure,
                                  should_stop=lambda: self._cancel_skew, on_log=self.log.emit,
                                  on_progress=self.progress.emit)
            self.state_changed.emit(EngineState.IDLE)
            self.cal_measured.emit(cal)
        except MeasureCancelled:
            self._say("warn", "Calibration cancelled.")
            self.state_changed.emit(EngineState.IDLE)
            self.cal_measured.emit(None)
        except Exception as e:
            msg = "Calibration failed: %s" % e
            self._say("error", msg)
            self.state_changed.emit(EngineState.ERROR)
            self.error.emit(msg)
        self._emit_session()

    @Slot(object)
    def accept_cal(self, cal: ThroughCal):
        if self.session is None:
            return
        if not cal.acceptable:
            self._say("warn", "Calibration not accepted: " + " ".join(cal.warnings))
        elif cal.alignment_epoch != self.session.digitizer.alignment_epoch:
            self._say("warn", "Calibration discarded: the scope was resynchronised after it.")
        else:
            self.session.accept_cal(cal)
            self._say("info", "Through calibration accepted: %s, %d points, largest gain deviation %.3f dB, "
                              "delay %+.2f ns." % (calibration.range_text(cal), len(cal.freqs_hz),
                                                   calibration.max_gain_db(cal),
                                                   calibration.fitted_delay_s(cal) * 1e9))
            for w in cal.warnings:
                self._say("warn", w)
        self._emit_session()

    @Slot()
    def discard_cal(self):
        if self.session is not None and self.session.cal is not None:
            self.session.invalidate_cal()
            self._say("info", "Through calibration discarded.")
        self._emit_session()
```

Update the comment of `abort()` use: `self._cancel_skew = True` now also stops a calibration; add the comment `# skew check and calibration` on that line.

`SweepEngine`: add request signals `_req_cal = Signal(object)`, `_req_accept_cal = Signal(object)`, `_req_discard_cal = Signal()`; result signal `cal_measured = Signal(object)`; in `__init__` connect `self._req_cal.connect(w.through_cal)`, `self._req_accept_cal.connect(w.accept_cal)`, `self._req_discard_cal.connect(w.discard_cal)`; add `"cal_measured"` to the tuple of re-emitted signal names; add the methods

```python
    def run_cal(self, cfg: Configs): self._req_cal.emit(cfg)
    def accept_cal(self, cal: ThroughCal): self._req_accept_cal.emit(cal)
    def discard_cal(self): self._req_discard_cal.emit()
```

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python -m pytest tests\test_gui.py -q` — expected all pass.

- [ ] **Step 5: Commit**

```powershell
git add src/bodeplot/sweep/engine.py tests/test_gui.py
git commit -m "Engine: run, accept and discard a through calibration"
```

---

### Task 8: GUI

**Files:**
- Modify: `src/bodeplot/gui/dialogs.py` (add `cal_report`, `CalDialog` at the end)
- Modify: `src/bodeplot/gui/main_window.py`
- Test: `tests/test_gui.py`

**Interfaces:**
- Consumes: `SweepEngine.run_cal / accept_cal / discard_cal / cal_measured / progress / error / abort`; `SessionInfo.cal`; `calibration.matches / covers / describe / range_text / max_gain_db / fitted_delay_s`.
- Produces: `dialogs.cal_report(cal) -> str`; `dialogs.CalDialog(engine, get_configs, simulated, current, parent=None)` with `start()`, `start_btn`, `accept_btn`, `cancel_btn`, `discard_btn`, `progress`, `result`, `warn`; `MainWindow.act_cal`, `MainWindow.open_cal_dialog() -> bool`, `MainWindow.cal_in_use() -> ThroughCal | None`. `MainWindow.skew_status` keeps its name and holds the calibration text when one applies.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gui.py`:

```python
def test_calibrate_action_sits_next_to_skew_check(win, qtbot):
    names = [a.text() for a in win.toolbar.actions()]
    assert names.index("Calibrate") == names.index("Skew check") + 1
    assert not win.act_cal.isEnabled()
    _connect(win, qtbot)
    assert win.act_cal.isEnabled()


def test_cal_dialog_measures_shows_and_accepts(win, qtbot):
    from bodeplot.gui.dialogs import CalDialog
    _connect(win, qtbot)
    dlg = CalDialog(win.engine, win.configs, True, None, win)
    qtbot.addWidget(dlg)
    assert not dlg.accept_btn.isEnabled() and dlg.discard_btn.isHidden()
    with qtbot.waitSignal(win.engine.cal_measured, timeout=30000):
        dlg.start()
        assert not dlg.start_btn.isEnabled()
    qtbot.waitUntil(lambda: dlg.accept_btn.isEnabled(), timeout=5000)
    assert dlg.progress.value() == dlg.progress.maximum() == 58
    text = dlg.result.text()
    assert "50 Hz to 20 MHz" in text and "58 points" in text
    assert "Largest gain deviation" in text and "Delay found" in text
    assert dlg.start_btn.text() == "Measure again"
    dlg._accept()
    qtbot.waitUntil(lambda: win.info.cal_valid, timeout=5000)
    assert win.skew_status[0] == "good" and win.skew_status[1].startswith("cal: ")
    assert "50 Hz to 20 MHz" in win.skew_status[1]
    # a second dialog offers to discard it
    dlg2 = CalDialog(win.engine, win.configs, True, win.info.cal, win)
    qtbot.addWidget(dlg2)
    assert not dlg2.discard_btn.isHidden()
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        dlg2._discard()
    qtbot.waitUntil(lambda: not win.info.cal_valid, timeout=5000)
    assert dlg2.discard_btn.isHidden() and "UNCHECKED" in win.skew_status[1]


def test_cal_dialog_does_not_offer_accept_for_a_refused_result(win, qtbot):
    from bodeplot.gui.dialogs import CalDialog
    from bodeplot.sweep import calibration
    _connect(win, qtbot)
    dlg = CalDialog(win.engine, win.configs, True, None, win)
    qtbot.addWidget(dlg)
    with qtbot.waitSignal(win.engine.cal_measured, timeout=30000) as blocker:
        win.engine.run_cal(win.configs())
    cal = blocker.args[0]
    cal.acceptable, cal.warnings = False, [calibration.NOT_A_THROUGH + ": test"]
    dlg._measured(cal)
    assert not dlg.accept_btn.isEnabled() and "through connection" in dlg.warnings_text
    dlg._measured(None)                                          # a cancelled run
    assert not dlg.accept_btn.isEnabled() and dlg.start_btn.isEnabled()


def test_a_calibration_that_applies_replaces_the_skew_question(win, qtbot):
    from PySide6.QtWidgets import QMessageBox
    asked = []
    win._ask = lambda *a, **k: asked.append(a) or QMessageBox.Cancel
    _connect(win, qtbot)
    _calibrate(win, qtbot)
    _short_sweep(win, 1e3, 1e5, 3)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        assert win.start_sweep()                                 # check_skew left at its default
    assert asked == [] and all(p.flags & Flag.CALIBRATED for p in win.result.points)
    table = win.status_log.table
    row = [table.item(0, c).text() for c in range(table.columnCount()) if table.item(0, c) is not None]
    assert any("CALIBRATED" in cell for cell in row)
    # a sweep that leaves the calibrated range asks, and says which part is not covered
    _short_sweep(win, 1e6, 30e6, 3)
    assert win.start_sweep() is False and len(asked) == 1
    assert asked[0][0] == "Channel skew" and "50 Hz to 20 MHz" in asked[0][1] and "30 MHz" in asked[0][1]


def test_status_follows_the_scope_settings(win, qtbot):
    _connect(win, qtbot)
    _calibrate(win, qtbot)
    assert win.skew_status[1].startswith("cal: ") and win.cal_in_use() is not None
    p = win.config.preset()
    p.scope.coupling = "AC"
    win.config.set_preset(p)
    assert win.cal_in_use() is None and "UNCHECKED" in win.skew_status[1]
    p.scope.coupling = "DC"
    win.config.set_preset(p)
    assert win.skew_status[1].startswith("cal: ")                # kept, and used again
    assert "cal: " in win.about_text()
```

In the existing `test_menu_actions_mirror_the_toolbar_and_plot` change the expected list to:

```python
    assert labels == ["Connect", "Connections…", "Sim settings…", "Settings…", "Skew check", "Calibrate",
                      "Export", "Preset", "Exit"]
```

- [ ] **Step 2: Run to see them fail**

Run: `.venv\Scripts\python -m pytest tests\test_gui.py -k "calibrat or cal_dialog or status_follows or menu_actions" -q`
Expected: failures (`'MainWindow' object has no attribute 'act_cal'`, `cannot import name 'CalDialog'`).

- [ ] **Step 3: Implement the dialog**

`src/bodeplot/gui/dialogs.py`: add `QProgressBar` to the `QtWidgets` import, `ThroughCal` to the `..models` import, and `from ..sweep import calibration`. Extend the module docstring's list with "calibration". Append:

```python
# ---------------------------------------------------------------------- through calibration
def cal_report(cal: ThroughCal) -> str:
    return "\n".join([
        "Range:  %s,  %d points" % (calibration.range_text(cal), len(cal.freqs_hz)),
        "Largest gain deviation:  %.3f dB" % calibration.max_gain_db(cal),
        "Delay found (DUT − reference):  %+.2f ns" % (calibration.fitted_delay_s(cal) * 1e9),
        "Measured at %s with %g Vpp" % (cal.checked_at[11:16], cal.amp_vpp)])


class CalDialog(QDialog):
    """Guides the user through the through calibration and shows the result.

    engine: a SweepEngine. get_configs: callable returning engine.Configs. current: the
    calibration the connection holds now, or None.
    """

    def __init__(self, engine, get_configs, simulated: bool, current: ThroughCal | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Through calibration")
        self.resize(540, 420)
        self.engine, self.get_configs = engine, get_configs
        self.cal: ThroughCal | None = None
        self.running = False
        lay = QVBoxLayout(self)
        intro = (
            "<b>Put the reference probe and the DUT probe on the same node</b>: both tips on the "
            "generator output, both ground clips on its shell, both probes at the same setting.<br><br>"
            "The app measures the difference between the two channels over the full frequency range "
            "(about 1 minute) and removes it, gain and phase, from every later sweep of this connection "
            "that uses the same channels, probe settings, coupling and bandwidth limit.<br><br>"
            "The generator output is switched on for the measurement and off again afterwards.")
        if simulated:
            intro += "<br><br><i>Simulation: the simulated DUT probe is moved to the reference node for you.</i>"
        if current is not None:
            intro += "<br><br>Current calibration: %s." % calibration.describe(current)[5:]
        self.intro = QLabel(intro)
        self.intro.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.result = QLabel("")
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result.setWordWrap(True)
        self.warn = QLabel("")
        self.warn.setWordWrap(True)
        self.warn.setTextFormat(Qt.RichText)
        self.warnings_text = ""
        lay.addWidget(self.intro)
        lay.addWidget(self.progress)
        lay.addWidget(self.result, 1)
        lay.addWidget(self.warn)
        row = QHBoxLayout()
        self.start_btn = QPushButton("Probes are connected: calibrate")
        self.discard_btn = QPushButton("Discard calibration")
        self.accept_btn = QPushButton("Accept")
        self.cancel_btn = QPushButton("Cancel")
        self.accept_btn.setEnabled(False)
        self.discard_btn.setVisible(current is not None)
        row.addWidget(self.start_btn)
        row.addWidget(self.discard_btn)
        row.addStretch(1)
        row.addWidget(self.accept_btn)
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)
        self.start_btn.clicked.connect(self.start)
        self.discard_btn.clicked.connect(self._discard)
        self.accept_btn.clicked.connect(self._accept)
        self.cancel_btn.clicked.connect(self.reject)
        engine.cal_measured.connect(self._measured)
        engine.progress.connect(self._progress)
        engine.error.connect(self._failed)

    def start(self) -> None:
        self.running = True
        self.start_btn.setEnabled(False)
        self.accept_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.result.setText("Measuring …")
        self.warn.setText("")
        self.engine.run_cal(self.get_configs())

    def _progress(self, i: int, n: int) -> None:
        if self.running:
            self.progress.setRange(0, n)
            self.progress.setValue(i)

    def _measured(self, cal: ThroughCal | None) -> None:
        self.running = False
        self.start_btn.setEnabled(True)
        self.discard_btn.setEnabled(True)
        if cal is None:                             # cancelled: nothing to accept
            self.cal = None
            self.result.setText("Cancelled.")
            self.accept_btn.setEnabled(False)
            return
        self.cal = cal
        self.result.setText(cal_report(cal))
        kind = "warning" if cal.acceptable else "critical"
        self.warnings_text = "\n\n".join(cal.warnings)
        self.warn.setText("<br><br>".join(theme.status_html(kind, w) for w in cal.warnings))
        self.start_btn.setText("Measure again")
        self.accept_btn.setEnabled(cal.acceptable)

    def _failed(self, message: str) -> None:
        if self.running or self.isVisible():
            self.running = False
            self.result.setText("")
            self.warnings_text = message
            self.warn.setText(theme.status_html("critical", message))
            self.start_btn.setEnabled(True)
            self.discard_btn.setEnabled(True)

    def _accept(self) -> None:
        if self.cal is not None and self.cal.acceptable:
            self.engine.accept_cal(self.cal)
            self.accept()

    def _discard(self) -> None:
        self.engine.discard_cal()
        self.discard_btn.hide()

    def reject(self) -> None:
        if self.running:                            # the first Cancel stops the measurement
            self.engine.abort()
            return
        super().reject()

    def done(self, r: int) -> None:
        for sig, slot in ((self.engine.cal_measured, self._measured), (self.engine.progress, self._progress),
                          (self.engine.error, self._failed)):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        super().done(r)
```

- [ ] **Step 4: Implement the main window**

`src/bodeplot/gui/main_window.py`:

Imports: add `ThroughCal` to the `..models` list, `from ..sweep import calibration`, and `CalDialog` to the `.dialogs` import.

`_build_toolbar`, after the `self.act_skew = act(...)` statement:

```python
        self.act_cal = act("Calibrate", self.open_cal_dialog,
                           "Through calibration: measure the gain and phase difference between the two "
                           "measurement paths over the full range and remove it from later sweeps")
```

`_build_menus`, in the File menu after `m.addAction(self.act_settings)`:

```python
        m.addSeparator()
        m.addAction(self.act_skew)
        m.addAction(self.act_cal)
```

`about_text`: replace the line `"Channel " + self.skew_status[1],` with `"Correction: " + self.skew_status[1],`.

`_update_actions`, after the `self.act_skew.setEnabled(...)` line:

```python
        self.act_cal.setEnabled(connected and not busy)
```

`_on_config_changed`: add a second line `self._refresh_correction()`.

Add after `_show_skew`:

```python
    def cal_in_use(self) -> ThroughCal | None:
        """The connection's through calibration, if it fits the scope settings on screen."""
        cal = self.info.cal if self.info.connected else None
        return cal if calibration.matches(cal, self.config.scope()) else None

    def _refresh_correction(self) -> None:
        """Status bar: the calibration when one applies to the current settings, otherwise
        the skew state as before."""
        info = self.info
        cal = self.cal_in_use()
        if not info.connected:
            self._show_skew("idle", "skew: not connected")
        elif cal is not None:
            self._show_skew("good", calibration.describe(cal))
        elif info.skew_valid:
            self._show_skew("good", info.skew_text)
        else:
            self._show_skew("critical", "skew: UNCHECKED — " + (info.recheck_reason or ""))
```

`_build_statusbar` is called before `self.config.changed` is connected and `self.info` exists by then, so `_refresh_correction` is safe from `_on_config_changed` in `__init__`.

Add after `open_skew_wizard`:

```python
    def open_cal_dialog(self) -> bool:
        if not self.info.connected or self.state in BUSY:
            return False
        dlg = CalDialog(self.engine, self.configs, self.info.simulated, self.info.cal, self)
        ok = bool(dlg.exec())
        self._progress = (0, 0)                     # the calibration used the progress read-out
        self._update_clock()
        return ok
```

`start_sweep`: replace the comment line and the `if check_skew and not self.info.skew_valid and ...:` line, and the start of the `self._ask(` call, so that the block reads:

```python
        # A calibration that covers the whole sweep makes the skew check unnecessary. A Fast
        # preview's phase is rough anyway, so it does not ask either.
        sweep = self.config.sweep()
        lo, hi = min(sweep.start_hz, sweep.stop_hz), max(sweep.start_hz, sweep.stop_hz)
        cal = self.cal_in_use()
        covered = cal is not None and calibration.covers(cal, lo, hi)
        if check_skew and not covered and not self.info.skew_valid \
                and self.config.measure().method is not Method.PREVIEW:
            partly = "" if cal is None else (
                "The through calibration covers %s only; this sweep goes from %s to %s, and the part "
                "outside the calibration needs the skew check.\n\n"
                % (calibration.range_text(cal), fmt_si(lo, "Hz"), fmt_si(hi, "Hz")))
            answer = self._ask(
                "Channel skew",
                partly + (self.info.recheck_reason or "No skew check has been done in this session.") +
                "\n\nWithout it the phase is not corrected: the scope's channels can be 2 ns or more "
                "apart, which is up to 43° at 20 MHz.\n\nRun the skew check first?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.No)
```

(the rest of the block, from `if answer == QMessageBox.Cancel:`, is unchanged). Add `from ..units import fmt_si` to the imports.

`_on_error`: the box must not open over the calibration dialog either. Replace the condition with:

```python
        if self.interactive and not any(w.isVisible() for w in
                                        self.findChildren(SkewWizard) + self.findChildren(CalDialog)):
```

`_on_session`: replace the first `if not info.connected: ... elif ... else: ...` chain (the three `_show_skew` branches) with:

```python
        self._refresh_correction()
        if not info.connected or info.skew_valid:
            self._last_reason = None
```

- [ ] **Step 5: Run**

Run: `.venv\Scripts\python -m pytest tests\test_gui.py -q` — expected all pass.
Run: `.venv\Scripts\python -m pytest -q` — expected no failure. Note the total for Task 9.

If `test_cal_dialog_measures_shows_and_accepts` fails at `discard_btn.isHidden()` on a dialog that was never shown: `isHidden()` is true after `setVisible(False)` and false after `setVisible(True)` even before `show()`, which is what the test relies on.

- [ ] **Step 6: Look at it**

Run: `.venv\Scripts\python -m bodeplot --sim`, connect, press **Calibrate**, run it, accept, start a sweep. Check by eye: the progress bar moves, the summary is readable in the dark theme, the status bar shows `cal: HH:MM, 50 Hz to 20 MHz`, the table shows `CALIBRATED`, the points are not drawn as crosses. Close the app.

- [ ] **Step 7: Commit**

```powershell
git add src/bodeplot/gui tests/test_gui.py
git commit -m "GUI: Calibrate action and dialog, calibration in the status bar, no skew question when it applies"
```

---

### Task 9: Documentation

**Files:**
- Modify: `docs/spec/skew.md` (8.6, 8.7), `docs/spec/sweep.md` (7, 14), `docs/spec/gui.md` (10, 12), `docs/spec/roadmap.md` (15, 16), `docs/ARCHITECTURE.md`, `docs/STATE.md`, `README.md`

- [ ] **Step 1: The spec (`docs/spec/`; section 8.6 and 8.7 are in `skew.md`, 7 and 14 in `sweep.md`, 10 and 12 in `gui.md`, 15 and 16 in `roadmap.md`)**

Section 8.6, in the **Correction** paragraph, replace the sentence "Gain is not corrected in v1; the frequency-dependent calibration of §15 stays in v2." with: "The skew check corrects the phase only. The through calibration of §8.7 corrects gain and phase at every frequency; where one applies, it is used in place of this correction."

At the end of `docs/spec/skew.md` (after the **Limits** paragraph of 8.6; done in Task 1, Step 0: check it against the code as built):

```markdown
### 8.7 Through calibration (v2)

Design: `docs/superpowers/specs/2026-10-06-through-calibration-design.md`. Code: `sweep/calibration.py` (pure functions), `core.run_through_cal`, `Session.cal_for`, `CalDialog` in `gui/dialogs.py`.

**What it is.** With both probes on one node the app measures `H_cal(f) = V_dut / V_ref` over the full range of the instruments and divides every later measurement by it: `H = H_meas / H_cal(f)`. That removes the gain and phase difference between the two measurement paths (probe, scope input, channel), which the skew check does only for the delay. Both exist; the skew check stays the quick everyday step.

**Measuring.** Toolbar and File menu "Calibrate". Logarithmic, 10 points per decade, from the higher of the two instruments' lower limits (not below 50 Hz) to the lowest of the generator's upper limit, the scope's `max_hz` and 40 % of the scope bandwidth: 50 Hz to 20 MHz, 58 points, on the UPO1054 with the UTG932E. Always Sine fit on single shots, with the averages and settle times of the panel; never Fast preview. No skew correction is applied to the stored values: the calibration holds the delay. Same safety frame as a sweep.

**Plausibility.** Not accepted: any gain beyond ±1 dB, a reference below 30 % of the stimulus setting ("This does not look like a through connection"), any point flagged `REF_SUSPECT`, `CLIPPED`, `BELOW_FLOOR` or `AUTORANGE_FAILED`, a resync during the run. Warning only: a gain beyond ±0.3 dB.

**Validity.** This connection only; nothing is saved to disk. A reconnect, a resync (the digitizer's `alignment_epoch`), "Front panel was used" and a lost connection drop it. It is used only for sweeps with the same reference channel, DUT channel, probe settings, coupling and bandwidth limit; with other settings it is kept and not used. Accepting a calibration does not create or change a skew check.

**Applying.** Decided once per sweep: the calibration where it covers the frequency (point flagged `CALIBRATED`, `cal_gain_db` and `cal_phase_deg` hold what was removed, no skew correction), the skew correction outside its range if a skew check is valid, else `SKEW_UNCHECKED`. No extrapolation. Between two calibration points the gain in dB is linear in log frequency; for the phase one delay is fitted to the whole calibration, the remainder is interpolated in log frequency and the delay is added back exactly (a delay is linear in frequency, and a straight line over log f would miss it by 0.09° near 18 MHz in the +2.15 ns state). Fast preview and re-measure use the same rule.

**It does not** correct the gain differences between V/div steps (up to about 0.09 dB, HW_REPORT 13.12), and it is not a 50 Ω or S-parameter calibration.

**Mock.** `MockScope.dut_gain_tilt_db_at_20mhz` adds a gain error of the DUT channel that grows with log frequency above 1 kHz; the simulated "same node" mode keeps it and the skew.
```

Section 7 (data models): add `ThroughCal`, `PointResult.cal_gain_db` / `cal_phase_deg` and `Flag.CALIBRATED` where the existing dataclasses and flags are listed, in the same form as the neighbouring entries.

Section 10 (GUI): add "Calibrate" to the toolbar list next to "Skew check", and one sentence on the status bar: "The status bar shows `cal: HH:MM, range` when a through calibration applies to the current scope settings, otherwise the skew state."

Section 12, CSV bullet: append `, cal_gain_db, cal_phase_deg` to the column list and add the sentence "The header also carries `cal: applied | none` and, when applied, `cal_checked_at`, `cal_range_hz`, `cal_points`, `cal_max_gain_db`; the calibration itself (frequencies and complex values) is in `meta_json` under `cal`." Touchstone bullet: append "and the same calibration facts".

Section 14, add rows to the table:

```markdown
| Calibration | Interpolation: at a point, between points, outside the range, across ±180° | exact at a point; a pure delay exact between points; `None` outside |
| Calibration | Mock with 0.2 dB tilt and +2.15 ns; through sweep after calibration | within 0.02 dB and 0.1° |
| Calibration | RC low-pass with the tilt present | gain within 0.05 dB, phase within 1° of theory |
| Calibration | Reconnect, resync, front panel, other channel, probe, coupling, bandwidth limit | dropped, or kept and not used |
| Calibration | Sweep beyond the calibrated range | skew correction there, one warning |
| Calibration | Calibration through a filter | refused |
```

Section 15, Phase A, first bullet: replace "Not built yet." with "Built on 2026-10-06 (§8.7)." and keep the rest.

Section 16: mark milestone A1 in its table the way finished milestones are marked there, with the bench acceptance still open until Task 10.

- [ ] **Step 2: README.md**

Line 32: remove "through calibration is not built;" from the Open sentence. In "What works", after the bullet "**Channel skew check and correction** (see below).", add:

```markdown
- **Through calibration** (see below): removes the gain and phase difference between the two probes and channels at every frequency.
```

After the "Channel skew check" section, add:

```markdown
## Through calibration

The skew check removes one thing, the delay between the two scope channels. The two measurement paths also differ in gain, and both differences change with frequency and with which probe sits on which channel (0.1 to 0.2 dB up to 20 MHz on the bench). The calibration measures all of it once and divides it out.

1. Press **Calibrate** and put the reference probe and the DUT probe on the same node (the generator output), both at the same probe setting.
2. The app sweeps the full range of the instruments (50 Hz to 20 MHz, 58 points, about 1 minute) with Sine fit and shows the range, the largest gain deviation and the delay it found.
3. Accept. The status bar shows `cal: HH:MM, 50 Hz to 20 MHz`.

Later sweeps with the same channels, probe settings, coupling and bandwidth limit are divided by it; their points carry the `CALIBRATED` flag, and the CSV holds what was removed (`cal_gain_db`, `cal_phase_deg`), so the raw measurement can be recovered. With a calibration that covers the sweep, no skew check is needed. Outside the calibrated range the skew check is used as before.

The calibration belongs to one connection and is not saved: a reconnect, a resync or **Front panel was used** drops it. It is refused when it does not look like a through connection (more than 1 dB anywhere, or a reference far below the generator setting). It does not correct the small gain differences between the scope's V/div steps (up to about 0.09 dB).
```

- [ ] **Step 3: `docs/STATE.md` and `docs/ARCHITECTURE.md` (not `CLAUDE.md`)**

In `docs/STATE.md`, rewrite the "Start here" block: A1 is built and tested against the simulators (date, the pytest total from Task 8, branch `a1-through-calibration`), what is left is the bench acceptance of Task 10 (or its result, if Task 10 is already done when this is written), and A2 is next but not to be started without the user. In `docs/ARCHITECTURE.md`, in "The chain of one measurement", add `sweep/calibration.py` to item 3 ("pure decisions of the through calibration") and `Session` = "one source + one digitizer + the skew check and the through calibration that belong to that connection". Add a row for the calibration to "Where each concern lives" (`Session.cal_for`, `sweep/calibration.py`, `CalDialog`). Add to "What exists" in `docs/STATE.md` one bullet naming `sweep/calibration.py`, `core.run_through_cal`, `Session.cal_for`, `CalDialog`, `tests/test_calibration.py`, and the six departures from the design listed at the top of this plan.

- [ ] **Step 4: Check and commit**

Run: `.venv\Scripts\python -m pytest -q` — expected no failure.

```powershell
git add docs README.md
git commit -m "SPEC 8.7, README and working notes: through calibration"
```

---

### Task 10: Bench acceptance (needs the user at the bench)

**Files:**
- Create: `hwcheck/m8_throughcal.py`, `hwcheck/m8_rc_compare.py`
- Create: `docs/hw/a1-through-cal.md` (section 14)
- Modify: `HW_REPORT.md` (facts sheet and index), `docs/STATE.md`, `docs/spec/roadmap.md` section 16

**Interfaces:**
- Consumes: `connect.open_session("py")`, `core.run_through_cal`, `Session.accept_cal`, `SweepRunner`, `export_csv.write_csv`, `export_csv.load_csv`.

- [ ] **Step 1: Write the headless bench script**

Create `hwcheck/m8_throughcal.py`:

```python
"""Milestone A1: through calibration on the real instruments, headless.

Run with the APP venv (it imports bodeplot):
    .venv\\Scripts\\python.exe -W ignore hwcheck\\m8_throughcal.py <label> [--ch=REF,DUT] [--avg=N] [--ppd=N]

PRECONDITION: the reference probe and the DUT probe on the same node (generator CH1's
output), both 10X.

What it does, through exactly the code the GUI uses (drivers/connect.py, sweep/core.py):
  1. find and open both instruments (generator outputs forced OFF on open);
  2. through calibration, full range, 10 points per decade, Sine fit;
  3. accept it, then one through sweep over the same range at --ppd points per decade
     (default 20, so every second point lies between two calibration points);
  4. print the largest gain and phase deviation against the targets 0.02 dB and 0.1 deg,
     and save everything (JSON here, CSV next to it).
The engine switches the generator off in a finally block, releases the scope's front-panel
lock and leaves the scope in sweep AUTO. No ':RUN' is sent (the driver refuses it).
"""
import logging
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from common import RESULTS, save                    # prints this script's hash and git commit

from bodeplot.drivers import connect
from bodeplot.io import export_csv
from bodeplot.models import MeasureSettings, ScopeConfig, StimulusConfig, SweepConfig, to_jsonable
from bodeplot.sweep import calibration
from bodeplot.sweep.core import Callbacks, SweepRunner, run_through_cal

TARGET_DB, TARGET_DEG = 0.02, 0.1
args = [a for a in sys.argv[1:] if not a.startswith("--")]
LABEL = args[0] if args else "run"


def opt(name, default, kind=str):
    return next((kind(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--%s=" % name)), default)


logging.basicConfig(level=logging.WARNING, format="   . %(name)s: %(message)s")
out = {"label": LABEL, "log": [], "target_db": TARGET_DB, "target_deg": TARGET_DEG}


def on_log(e):
    out["log"].append([e.level, e.text])
    print("   [%s] %s" % (e.level, e.text))


def on_point(p):
    print("  %12.2f Hz  %+8.4f dB  %+8.3f deg  removed %+7.4f dB %+8.3f deg  V/div %g / %g  %.2f s  %s" % (
        p.freq_hz, p.gain_db, p.phase_deg, p.cal_gain_db, p.cal_phase_deg, p.vdiv_ref, p.vdiv_dut,
        p.duration_s, p.flags.name or str(p.flags)))


def main():
    ref, dut = tuple(int(x) for x in opt("ch", "1,2").split(","))
    scope_cfg = ScopeConfig(ref_channel=ref, dut_channel=dut, probe_atten={ref: 10.0, dut: 10.0})
    stim = StimulusConfig()
    meas = MeasureSettings(averages=opt("avg", 1, int))
    ppd = opt("ppd", 20, int)
    out.update(channels=[ref, dut], averages=meas.averages, points_per_decade=ppd)
    session = connect.open_session("py")
    print("generator: %s\nscope:     %s" % (session.source_idn, session.digitizer_idn))
    out["generator_idn"], out["scope_idn"] = session.source_idn, session.digitizer_idn
    from pathlib import Path
    session.capture_dir = Path(RESULTS) / "m8" / "captures"
    try:
        for w in session.take_warnings():
            print("WARNING:", w)
        t0 = time.perf_counter()
        cal = run_through_cal(session, stim, scope_cfg, meas, on_log=on_log,
                              on_progress=lambda i, n: print("   calibration point %d of %d" % (i, n)))
        out["cal_s"] = time.perf_counter() - t0
        out["cal"] = to_jsonable(cal)
        print("\ncalibration (%.1f s): %s, %d points, largest gain deviation %.4f dB, delay %+.3f ns, "
              "acceptable: %s" % (out["cal_s"], calibration.range_text(cal), len(cal.freqs_hz),
                                  calibration.max_gain_db(cal), calibration.fitted_delay_s(cal) * 1e9,
                                  cal.acceptable))
        for f, h in zip(cal.freqs_hz, cal.h):
            import cmath
            import math
            print("  %12.2f Hz  %+8.4f dB  %+8.3f deg" % (
                f, 20 * math.log10(abs(h)) if abs(h) else float("-inf"), math.degrees(cmath.phase(h))))
        for w in cal.warnings:
            print("   calibration WARNING:", w)
        if not cal.acceptable:
            print("NOT ACCEPTABLE: no sweep.")
            return
        session.accept_cal(cal)
        print("\nthrough sweep with the calibration applied:")
        runner = SweepRunner(session, SweepConfig(start_hz=cal.freqs_hz[0], stop_hz=cal.freqs_hz[-1],
                                                  points_per_decade=ppd),
                             stim, scope_cfg, meas, Callbacks(point=on_point, log=on_log))
        t0 = time.perf_counter()
        result = runner.run()
        out["sweep_s"] = time.perf_counter() - t0
        out["error"] = result.meta.get("error")
        out["result"] = to_jsonable(result)
        pts = result.points
        if pts:
            worst_g = max(pts, key=lambda p: abs(p.gain_db))
            worst_p = max(pts, key=lambda p: abs(p.phase_deg))
            out["max_gain_db"], out["max_gain_at_hz"] = abs(worst_g.gain_db), worst_g.freq_hz
            out["max_phase_deg"], out["max_phase_at_hz"] = abs(worst_p.phase_deg), worst_p.freq_hz
            out["passed"] = bool(abs(worst_g.gain_db) <= TARGET_DB and abs(worst_p.phase_deg) <= TARGET_DEG)
            print("\n%d points in %.1f s" % (len(pts), out["sweep_s"]))
            print("largest gain deviation  %.4f dB at %g Hz   (target %.2f dB)" % (
                abs(worst_g.gain_db), worst_g.freq_hz, TARGET_DB))
            print("largest phase deviation %.4f deg at %g Hz  (target %.1f deg)" % (
                abs(worst_p.phase_deg), worst_p.freq_hz, TARGET_DEG))
            print("flags seen:", sorted({n for p in pts for n in p.flags.names()}))
            print("RESULT:", "WITHIN the targets" if out["passed"] else "OUTSIDE the targets")
            os.makedirs(os.path.join(RESULTS, "m8"), exist_ok=True)
            csv_path = os.path.join(RESULTS, "m8", "m8_throughcal_%s.csv" % LABEL)
            export_csv.write_csv(csv_path, result)
            print("CSV:", csv_path)
        if out["error"]:
            print("ERROR:", out["error"])
        out["scope_stats"] = dict(session.digitizer.stats)
        out["generator_stats"] = dict(session.source.stats)
        print("scope counters:", out["scope_stats"])
        print("generator counters:", out["generator_stats"])
        if session.dead_reason is None:
            out["outputs_at_end"] = [session.source.output(1), session.source.output(2)]
            out["panel_locked_at_end"] = session.digitizer.query(":SYSTem:LOCK?", lambda r: r)   # U1K p.6
            out["sweep_mode_at_end"] = session.digitizer.query(":TRIGger:SWEep?", lambda r: r)   # U1K p.36
            print("at the end: generator outputs ON? %s, panel lock %s, scope sweep %s" % (
                out["outputs_at_end"], out["panel_locked_at_end"], out["sweep_mode_at_end"]))
    finally:
        session.close()
        os.makedirs(os.path.join(RESULTS, "m8"), exist_ok=True)
        print("saved", save(os.path.join("m8", "m8_throughcal_%s.json" % LABEL), out))


if __name__ == "__main__":
    main()
```

Create `hwcheck/m8_rc_compare.py` (touches no instrument; reads a CSV the user exported from the GUI):

```python
"""Milestone A1: compare an RC low-pass sweep (CSV exported by the app) with the model built
from the capacitor's LCR readings (HW_REPORT.md 13.18). Touches no instrument.

    .venv\\Scripts\\python.exe hwcheck\\m8_rc_compare.py <sweep.csv> [--r=OHMS] [--fmax=HZ]

Model: the capacitor is Cs in series with ESR = D / (2 pi f Cs); H = Zc / (R + Zc).
Cs and D are the LCR meter's readings, interpolated in log frequency and held constant
outside 100 Hz to 100 kHz. R defaults to 1000 ohm (nominal; it was not measured).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from bodeplot.io import export_csv

LCR_HZ = [100.0, 1e3, 1e4, 1e5]
LCR_CS = [105.7e-9, 105.4e-9, 104.4e-9, 102.6e-9]
LCR_D = [0.001, 0.003, 0.009, 0.028]


def opt(name, default):
    return next((float(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--%s=" % name)), default)


def interp(f, ys):
    x = min(max(math.log10(f), math.log10(LCR_HZ[0])), math.log10(LCR_HZ[-1]))
    xs = [math.log10(v) for v in LCR_HZ]
    for i in range(len(xs) - 1):
        if x <= xs[i + 1]:
            return ys[i] + (x - xs[i]) / (xs[i + 1] - xs[i]) * (ys[i + 1] - ys[i])
    return ys[-1]


def model(f, r):
    cs, d = interp(f, LCR_CS), interp(f, LCR_D)
    w = 2 * math.pi * f
    zc = complex(d / (w * cs), -1.0 / (w * cs))
    return zc / (r + zc)


def main():
    path = next(a for a in sys.argv[1:] if not a.startswith("--"))
    r, fmax = opt("r", 1000.0), opt("fmax", 100e3)
    result = export_csv.load_csv(path)
    print("file: %s   cal: %s   R = %g ohm" % (path, export_csv.describe_correction(result.meta), r))
    print("%12s %10s %10s %9s %10s %10s %9s  flags" % ("Hz", "gain dB", "model dB", "diff", "phase", "model", "diff"))
    worst_g = worst_p = 0.0
    for p in result.points:
        h = model(p.freq_hz, r)
        g, ph = 20 * math.log10(abs(h)), math.degrees(math.atan2(h.imag, h.real))
        dg, dp = p.gain_db - g, p.phase_deg - ph
        inside = p.freq_hz <= fmax
        if inside:
            worst_g, worst_p = max(worst_g, abs(dg)), max(worst_p, abs(dp))
        print("%12.2f %+10.3f %+10.3f %+9.3f %+10.2f %+10.2f %+9.2f  %s%s" % (
            p.freq_hz, p.gain_db, g, dg, p.phase_deg, ph, dp, p.flags.to_text(), "" if inside else "  (not counted)"))
    print("\nup to %g Hz: largest gain difference %.3f dB, largest phase difference %.2f deg" % (fmax, worst_g, worst_p))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Check the scripts without the bench, then commit**

Run: `.venv\Scripts\python -m py_compile hwcheck\m8_throughcal.py hwcheck\m8_rc_compare.py` — expected no output.
Run the compare script on a simulated CSV: start `.venv\Scripts\python -m bodeplot --sim`, sweep the default RC low-pass, export `scratch.csv` to the scratchpad, then `.venv\Scripts\python hwcheck\m8_rc_compare.py <scratch.csv>` — expected a table and a last line with two numbers (the simulated C is 100 nF, so differences of a few tenths of a dB near the corner are right).

```powershell
git add hwcheck/m8_throughcal.py hwcheck/m8_rc_compare.py
git commit -m "Bench scripts for the through calibration: m8_throughcal, m8_rc_compare"
```

- [ ] **Step 3: Ask what is wired**

Ask the user, and wait for the answer: "Are both probes still on generator CH1's output (CH1 = reference, CH2 = DUT), both at 10X, and is the app closed?" Do not rely on what was said earlier in the session.

- [ ] **Step 4: Instruments answer (read-only)**

Run: `.venv-hwcheck\Scripts\python.exe -W ignore hwcheck\s6_state.py "@py"`
Expected: both instruments answer, generator outputs OFF, panel not locked. Read the whole output; do not truncate it.

- [ ] **Step 5: Headless calibration and through sweep**

Run (about 4 minutes; write the output to a file and read all of it):

```powershell
.venv\Scripts\python.exe -W ignore hwcheck\m8_throughcal.py bench1 *> "$env:TEMP\m8_bench1.txt"; Get-Content "$env:TEMP\m8_bench1.txt"
```

Expected: `acceptable: True`, a delay near +0.1 ns (or another known state), `RESULT: WITHIN the targets`, generator outputs OFF, panel lock 0, sweep AUTO. If it is outside the targets, do not change a limit: report the numbers and where the worst points lie (at calibration points or between them; which V/div steps), run it once more with `--avg=4` under the label `bench1_avg4` to separate noise from a systematic error, and discuss with the user.

- [ ] **Step 6: The user's acceptance in the GUI (design section 10)**

Ask the user to run, in the app on the real instruments, and to say what they see at each step:

1. Connect, **Calibrate**, accept. Note the summary (largest gain deviation, delay).
2. Through sweep, 50 Hz to 20 MHz, Sine fit: expect within 0.02 dB and 0.1°. Export CSV.
3. Move the DUT probe to the RC low-pass output (ask before they touch cables), sweep, export CSV. Then run `.venv\Scripts\python hwcheck\m8_rc_compare.py <their file>` and compare with HW_REPORT 13.18 (the uncalibrated result was within 0.11° from 5 to 100 kHz).
4. Disconnect and connect again: the status bar must show no calibration.

- [ ] **Step 7: Record it**

`docs/hw/a1-through-cal.md`: new file with the header the other history files have, then `## 14. Milestone A1: through calibration on the bench` and `### 14.1 ...` with the date, the wiring, the script's numbers (calibration summary, largest deviations and their frequencies, time taken, counters), the user's four GUI steps with their results, and anything that did not meet the target, with the exact numbers. `HW_REPORT.md`: the facts this run establishes under "Measured and settled on the bench", and a row for section 14 in the index table. `docs/STATE.md`: A1 done or what is open. `docs/spec/roadmap.md` section 16: A1's status.

```powershell
git add HW_REPORT.md docs hwcheck/results
git commit -m "Report: through calibration on the bench (milestone A1)"
```

- [ ] **Step 8: Finish the branch**

Use superpowers:finishing-a-development-branch (the project has no remote: the choice is a merge into `main` or leaving the branch).
