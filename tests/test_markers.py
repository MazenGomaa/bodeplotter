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
