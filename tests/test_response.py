"""The maths on one response curve (measure/response.py), against the theory of the simulated DUTs."""
import cmath
import math

import pytest

from bodeplot.measure.response import Curve, crossings, curve, extremum, refine
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


def test_refine_works_on_any_point_and_extremum_uses_it():
    c = of(BPF)
    e = extremum(c)
    assert refine(c, e.index) == (e.f, e.db)                    # the highest point: the same answer
    f, db = refine(c, e.index)
    assert c.f[e.index - 1] < f < c.f[e.index + 1] and db >= c.db[e.index]
    assert refine(c, 0) == (c.f[0], c.db[0])                    # an end has one neighbour only: the point itself
    assert refine(c, len(c.f) - 1) == (c.f[-1], c.db[-1])
    rising = e.index - 10                                       # on the flank the parabola opens the wrong way or peaks outside
    assert refine(c, rising) == (c.f[rising], c.db[rising])
    gap = by_hand([1.0, 10.0, 100.0], [0.0, 3.0, 0.0], ok=[False, True, True])
    assert refine(gap, 1) == (10.0, 3.0)                        # a dead neighbour: no parabola
    notch = of(TransferFunction.rlc_notch(100.0, 1e-3, 100e-9))
    low = extremum(notch, highest=False)
    assert refine(notch, low.index, highest=False) == (low.f, low.db)
