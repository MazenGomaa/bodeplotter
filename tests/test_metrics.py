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
    assert all(c.attenuation is None and not c.falling for c in m.cutoffs)     # the depth is in the Notch group
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


def floored(tf, floor=1e-4, freqs=None, seed=1):
    """The curve of a transfer function above an instrument's noise floor: complex noise of
    that size (1e-4: -80 dB) added to every point, as a scope adds it."""
    rnd = random.Random(seed)
    freqs = freqs or grid(20.0, 5e6, 40)
    return curve(freqs, [tf.h(f) + complex(rnd.gauss(0, floor), rnd.gauss(0, floor)) for f in freqs])


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("tf, order", [(RC, 1), (butter(5, 10e3), 5), (HUMP, 2)])
def test_a_noise_floor_ends_the_roll_off(tf, order, seed):
    m = analyse(floored(tf, seed=seed))
    (noise,) = m.noise
    assert not noise.at_low and noise.level < -50.0
    (cut,) = m.cutoffs
    assert cut.order.v == order and abs(cut.slope.v) == pytest.approx(20.0 * order, rel=0.1)
    assert cut.attenuation.limit and cut.attenuation.v > 50.0 and not cut.falling
    assert [r.kind for r in m.resonances] == (["peak"] if tf is HUMP else [])


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_resonance_is_found_in_the_noise_at_the_low_end(seed):
    m = analyse(floored(TWO, seed=seed))
    assert [n.at_low for n in m.noise] == [True] or [n.at_low for n in m.noise] == [True, False]
    assert all(r.f0 > 1e3 for r in m.resonances)
    assert [r.kind for r in m.resonances][:1] == ["peak"] and m.resonances[0].f0 == pytest.approx(1e4, rel=0.02)


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("tf", [cheby(8, 1.0, 10e3), butter(10, 10e3)])
def test_a_sharp_edge_is_not_taken_for_noise(tf, seed):
    m = analyse(floored(tf, seed=seed))                         # its bend is sudden, not a scatter
    (cut,) = m.cutoffs
    assert 9e3 < cut.f < 11e3
    (noise,) = m.noise
    assert noise.lo > 1.15 * cut.f and noise.level < -60.0


def span(lo, hi, ppd):
    """A log sweep from lo to hi with about ppd points per decade, both ends on the grid."""
    n = max(6, int(math.log10(hi / lo) * ppd) + 1)
    return [lo * (hi / lo) ** (k / (n - 1)) for k in range(n)]


ELLIPTIC = TF.custom(np.polymul(np.polymul([1.0, 0.0, w(16e3) ** 2], [1.0, 0.0, w(25e3) ** 2]),
                                [butter(5, 10e3).den[-1] / (w(16e3) * w(25e3)) ** 2]),
                     butter(5, 10e3).den)       # a 5th-order low-pass with notches at 16 and 25 kHz


@pytest.mark.parametrize("tf, freqs", [(NOTCH, span(32.0, 17683.0, 20)), (cheby(5, 1.0, 10e3), span(121.0, 18327.0, 10)),
                                       (TWO, span(52.0, 123518.0, 20)), (ELLIPTIC, span(256.0, 43863.0, 10))])
def test_a_sparse_clean_sweep_ending_past_a_notch_or_an_edge_is_not_noise(tf, freqs):
    m = analyse(of(tf, freqs, db=0.02, seed=11))                # the bends are sudden but do not scatter
    assert m.noise == []
    if tf is NOTCH:
        assert [r.kind for r in m.resonances] == ["notch"] and m.resonances[0].f0 == pytest.approx(F0, rel=0.03)
    else:
        assert m.cutoffs


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("tf, real", [(TF.loop3(), []), (TF.rlc_lpf(), ["peak"])])
def test_no_resonance_where_the_roll_off_meets_the_noise(tf, real, seed):
    """Where the curve comes down to the noise, the noise grows quickly: the scatter close
    around a point counts there (100 points per decade, the noise at -78 dB)."""
    m = analyse(floored(tf, freqs=grid(20.0, 5e6, 100), seed=seed))
    assert [r.kind for r in m.resonances] == real


@pytest.mark.parametrize("tf, order, floor", [(butter(5, 1e4), 5, 1e-3), (butter(5, 1e4), 5, 3e-4),
                                              (butter(4, 1e4), 4, 3e-3)])
def test_a_roll_off_that_meets_a_floor_soon_is_only_a_lower_limit(tf, order, floor):
    """A smooth floor (crosstalk) less than a decade beyond the cut-off: no window of the
    roll-off is free of the knee and of the bend into the floor; the order is not certain."""
    freqs = grid(100.0, 2e7, 20)
    c = curve(freqs, [math.hypot(abs(tf.h(f)), floor) * cmath.exp(1j * cmath.phase(tf.h(f))) for f in freqs])
    (cut,) = analyse(c).cutoffs
    assert cut.order.v == order or (cut.order.limit and cut.slope.limit and cut.order.v < order)
    assert cut.attenuation.v == pytest.approx(-20 * math.log10(floor), abs=1.0)


def test_a_clean_curve_or_a_noisy_whole_has_no_noise_floor():
    assert analyse(of(RC, db=0.2)).noise == []
    assert analyse(floored(TF.custom([1e-5], [1.0]))).noise == []     # all of it in the noise: nothing is left out


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


# ---------------------------------------------------------------------- the simulator's circuits
def test_every_circuit_of_the_simulator_shows_what_it_is_for():
    """The circuits added to Simulation mode to try the analysis on (measure/theory.py), with their defaults."""
    m = analyse(of(TF.rlc_lpf()))                               # a hump: the cut-off from the flat level, one peak
    assert m.source == "flat" and len(m.cutoffs) == 1 and [r.kind for r in m.resonances] == ["peak"]
    assert m.resonances[0].height == pytest.approx(6.3, abs=0.3)
    m = analyse(of(TF.rc_shelf()))                              # a stop band that levels off: a plain attenuation
    assert [b.kind for b in m.bands] == ["pass", "floor"]
    assert m.cutoffs[0].attenuation.v == pytest.approx(40.1, abs=0.5) and not m.cutoffs[0].attenuation.limit
    m = analyse(of(TF.wide_bpf(), grid(5.0, 2e7)))              # a flat top: two cut-offs, centre, bandwidth
    assert m.source == "flat" and [k.f for k in m.cutoffs] == pytest.approx([100.0, 100e3], rel=0.03)
    assert m.resonances == [] and m.bandwidth == pytest.approx(99.9e3, rel=0.03)
    m = analyse(of(TF.butter_lpf()))
    assert m.cutoffs[0].f == pytest.approx(10e3, rel=0.02) and m.cutoffs[0].order.v == 5
    m = analyse(of(TF.cheby_lpf()))
    assert m.ripple == pytest.approx(1.0, abs=0.1) and m.cutoffs[0].order.v == 5
    m = analyse(of(TF.two_res()))
    assert [r.kind for r in m.resonances] == ["peak", "notch", "peak"]      # the valley between them is a notch
    assert [m.resonances[0].f0, m.resonances[2].f0] == pytest.approx([10e3, 300e3], rel=0.03)
    m = analyse(of(TF.crystal(), grid(1e5, 1e7, 200)))
    assert [r.kind for r in m.resonances] == ["peak", "notch"]
    assert [r.f0 for r in m.resonances] == pytest.approx([1e6, 1.05e6], rel=0.01)
    m = analyse(of(TF.amp()))
    assert m.level == pytest.approx(20.0, abs=0.05) and m.cutoffs[0].f == pytest.approx(50e3, rel=0.02)


def test_on_a_linear_sweep_a_passband_from_the_first_point_touches_the_low_end():
    """Its first point has no slope (too few points in its window); the band still reaches the
    end of the sweep, so its level is uncertain (the note of analysis.notes)."""
    m = analyse(of(RC, [100.0 * k for k in range(1, 1001)]))           # 100 Hz to 100 kHz, linear
    (band,) = [b for b in m.bands if b.kind == "pass"]
    assert band.at_low and not band.at_high


def test_two_noisy_ends_leave_enough_of_the_curve_or_none_is_taken():
    rnd = random.Random(4)
    f = grid(20.0, 2e6, 20)
    mid = len(f) // 2
    db = [20 * math.log10(abs(complex(rnd.gauss(0, 1), rnd.gauss(0, 1)))) - 80 for _ in f]
    db[mid - 1:mid + 3] = [0.0, 0.0, 0.0, 0.0]                  # four clean points between two floors
    m = analyse(by_hand(f, db))
    left = sum(1 for i in range(len(f)) if not any(n.first <= i <= n.last for n in m.noise))
    assert m.noise == [] or left >= 5


# LC traps: a series LC to ground at 30 kHz after a low-pass. Over a shelf (the gain comes back to a
# floor 19 dB down), and inside a 3rd-order roll-off (it comes back to a hump, then falls on).
TRAP_SHELF = TF.custom(poly([1.0, w(30e3) / 20, w(30e3) ** 2], [w(10e3) ** 2 / w(30e3) ** 2]),
                       poly([1.0, w(10e3) / 0.7, w(10e3) ** 2]))
TRAP_ROLL = TF.custom(poly([1.0, w(30e3) / 20, w(30e3) ** 2], [butter(3, 10e3).den[-1] / w(30e3) ** 2]),
                      butter(3, 10e3).den)


def _worst_beyond_notch(c, m):
    """The passband level minus the highest gain beyond the first notch, read off the points."""
    f_notch = m.resonances[[r.kind for r in m.resonances].index("notch")].f0
    return m.level - max(d for f, d, ok in zip(c.f, c.db, c.ok) if ok and f > f_notch)


@pytest.mark.parametrize("tf, expect", [(ELLIPTIC, 41.5), (TRAP_SHELF, 19.1), (TRAP_ROLL, None)])
def test_beyond_a_notch_the_stopband_is_the_highest_gain_that_comes_back(tf, expect):
    """A roll-off that ends in a notch: the rejection a filter designer means is the worst case,
    the passband level minus the highest gain beyond the notch, not the depth of the notch."""
    c = of(tf)
    m = analyse(c)
    (cut,) = m.cutoffs
    worst = _worst_beyond_notch(c, m)
    assert cut.attenuation.v == pytest.approx(worst, abs=0.05)
    if expect is not None:
        assert worst == pytest.approx(expect, abs=0.3)
    assert not cut.attenuation.limit and not cut.falling and not cut.rising
    assert cut.slope is None                                    # into a notch there is still no order


def test_a_sweep_that_ends_while_the_gain_beyond_a_notch_still_rises_says_so():
    """Past the notch at 16 kHz the gain climbs to a stopband peak at 18.8 kHz; a sweep that ends at
    18 kHz has not seen that peak: the number is what the sweep saw, and a flag says it may be less."""
    c = of(ELLIPTIC, grid(50.0, 18e3, 40))
    m = analyse(c)
    (cut,) = m.cutoffs
    assert cut.attenuation.v == pytest.approx(m.level - c.db[-1], abs=0.05)
    assert cut.rising and not cut.attenuation.limit and not cut.falling


def test_a_notch_between_two_passbands_has_no_stopband_row_only_its_depth():
    """Beyond the RLC notch lies the other passband: a 'stopband' there would read about 0 dB."""
    m = analyse(of(NOTCH))
    assert len(m.cutoffs) == 2 and all(cut.attenuation is None and not cut.rising for cut in m.cutoffs)
    (notch,) = m.resonances
    assert notch.height > 30.0


def test_a_roll_off_ends_at_a_gap_and_does_not_reach_a_notch_beyond_it():
    freqs = grid()
    hs = [ELLIPTIC.h(f) if not 12e3 < f < 14e3 else complex("nan") for f in freqs]
    m = analyse(curve(freqs, hs))
    (cut,) = [c for c in m.cutoffs if c.f < 12e3]
    assert cut.slope is not None                                # it ends at the gap, not in the notch past it
    assert cut.attenuation.limit and not cut.rising


@pytest.mark.parametrize("tf, ppd, k, expect", [(ELLIPTIC, 10, 0, 41.5), (ELLIPTIC, 8, 3, 41.5), (ELLIPTIC, 12, 2, 41.5),
                                                 (ELLIPTIC, 15, 4, 41.5), (TRAP_ROLL, 10, 7, 37.0)])
def test_a_notch_missed_on_a_sparse_sweep_still_ends_the_roll_off(tf, ppd, k, expect):
    """Below 20 points per decade the stop band's own bends raise the scatter and its notches are
    not found; the gain still comes back up after the roll-off's lowest point, and that is read as
    a notch would be: the highest gain that comes back, no order (it read '≥ 76 dB', order 1)."""
    off = 10 ** (k / 40 / ppd)
    m = analyse(of(tf, grid(50 * off, 2e6 * off, ppd), db=0.02, seed=k))
    cut = m.cutoffs[0]
    assert cut.attenuation.v == pytest.approx(expect, abs=2.0) and not cut.attenuation.limit
    assert cut.slope is None and not cut.falling


def noisy_butterworths(n, seed=11):
    """n random Butterworth low-passes (order 1 to 5, fc 1 to 30 kHz) swept to 5 MHz at 10 to 40
    points per decade over an instrument's noise floor of -60 to -80 dB."""
    rnd = random.Random(seed)
    for t in range(n):
        order, fc = rnd.randint(1, 5), 10 ** rnd.uniform(3, math.log10(3e4))
        ppd = rnd.choice([10, 15, 20, 30, 40])
        floor, lo = 10 ** (-rnd.uniform(60, 80) / 20), 20 * 10 ** rnd.random() / ppd
        yield t, order, floored(butter(order, fc), floor, grid(lo, 5e6, ppd), seed=t)


def test_the_noise_where_a_roll_off_meets_it_invents_no_notch_and_keeps_the_order():
    """Close to a noise floor the noise moves the gain by several dB: a dip there is not a notch
    (it took the order away from 4 % of plain Butterworth sweeps)."""
    wrong = []
    for t, order, c in noisy_butterworths(240):
        m = analyse(c)
        (cut,) = [x for x in m.cutoffs if x.side == "high"]
        if m.resonances or cut.order is None:
            wrong.append((t, order, [(r.kind, round(r.height, 1)) for r in m.resonances]))
    assert wrong == []


def test_repeated_frequencies_break_nothing():
    """A hand-edited file can repeat a frequency: the -3 dB width of a peak there is zero."""
    f = [100, 200, 300, 400, 500, 500, 500, 600, 700, 800, 900]
    m = analyse(by_hand(f, [-20, -18, -15, -12, -6, 0, -6, -12, -15, -18, -20]))
    assert m.ok and all(r.q_width is None or math.isfinite(r.q_width) for r in m.resonances)


def test_a_roll_off_that_ends_at_a_gap_is_not_said_to_end_with_the_sweep():
    freqs = grid()
    hs = [RC.h(f) if not 2e4 < f < 3e4 else complex("nan") for f in freqs]
    m = analyse(curve(freqs, hs))
    (cut,) = m.cutoffs
    assert cut.attenuation.limit and not cut.falling              # a limit, but the sweep goes on past the gap
