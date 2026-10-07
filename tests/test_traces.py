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
    assert not ts.live.removable and ts.reference() is None
    assert [(d.trace, d.freqs) for d in ts.drawn()] == [(ts.live, [])]      # the live trace is always there, empty
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
    assert ts.span() is None and ts.drawn()[1].trace is th and ts.drawn()[1].freqs == []       # nothing to span: nothing drawn
    assert ts.span((50.0, 2e7)) == (50.0, 2e7)
    assert ts.drawn(span_hint=(50.0, 2e7))[1].freqs[0] == 50.0
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
