"""The markers (markers.py): the rules of the automatic ones and the user's own, against theory."""
import cmath
import math
import random

import numpy as np
import pytest

from bodeplot.markers import KINDS, MAX_USER, NO_VALUE, OUTSIDE, Marker, MarkerSet, delta_text, label, table
from bodeplot.measure.response import Curve, curve
from bodeplot.measure import theory
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
    assert m["fc"].db == pytest.approx(-3.0, abs=0.02)             # 3 dB below the flat level, not below one point
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
    assert float(rows[2][1]) == pytest.approx(FC, rel=0.02) and float(rows[2][2]) == pytest.approx(-3.0, abs=0.02)
    assert rows[3] == ["pk", "", "", "", "none"]
    assert rows[7][4] == "reference marker" and rows[8][4].startswith("rel. M1: x10, ")
    assert text.endswith("\n") and all(len(r) == 5 for r in rows[1:])


def test_cutoff_beside_a_steep_drop_stays_between_its_points():
    """Review finding: the parabola lifted the peak 3 dB above every point, the -3 dB level
    lay above the curve, and the edges came out crossed with a negative bandwidth."""
    c = by_hand([100.0, 200.0, 400.0, 800.0, 1600.0, 3200.0], [-10.0, -0.1, 0.0, -25.0, -30.0, -35.0])
    m = every(c)
    assert 100.0 < m["fL"].freq < 200.0 and 400.0 < m["fH"].freq < 800.0
    assert m["fL"].db == pytest.approx(-3.0) and m["fH"].db == pytest.approx(-3.0)       # 3 dB below the highest point
    assert m["fH"].extra.startswith("BW ") and "-" not in m["fH"].extra
    flat_top = by_hand([100.0, 200.0, 400.0, 800.0], [-10.0, 0.0, 0.0, -10.0])
    assert every(flat_top)["fL"].freq < every(flat_top)["fH"].freq


def test_texts_without_phase():
    """Review finding: a magnitude-only measurement showed '+0.0°' in the difference line
    and a phase column of zeros in the copied table."""
    c = by_hand([100.0, 1e5], [0.0, -60.0])
    ms = MarkerSet()
    ms.add(1000.0), ms.add(10000.0)
    ms.toggle_ref(1)
    m1, m2 = ms.evaluate(c, margins=False)
    assert delta_text(m2.delta, with_phase=False) == "Δ M1  ×10  -20.0 dB  -20.0 dB/dec"
    assert label(m2, "-40.00 dB") == "M2 10 kHz  -40.00 dB\nΔ M1  ×10  -20.0 dB  -20.0 dB/dec"
    rows = [r.split("\t") for r in table([m1, m2], "t", with_phase=False).splitlines()]
    assert [r[3] for r in rows[2:]] == ["", ""] and rows[3][4] == "rel. M1: x10, -20.0 dB, -20.0 dB/dec"
    assert "deg" not in rows[3][4] and all(len(r) == 5 for r in rows[1:])


def test_a_large_frequency_ratio_is_written_in_full():
    """Seen in a render: a marker 3333 times above the reference read 'x3.33e+03'."""
    c = by_hand([100.0, 1e7], [0.0, -100.0])
    ms = MarkerSet()
    ms.add(300.0), ms.add(1e6), ms.add(150.0)
    ms.toggle_ref(1)
    _m1, m2, m3 = ms.evaluate(c)
    assert delta_text(m2.delta, with_phase=False).startswith("Δ M1  ×3333  ")
    assert "x3333," in table([m2], "t") and delta_text(m3.delta, with_phase=False).startswith("Δ M1  ×0.5  ")


# ---------------------------------------------------------------------- the small items of the A4 review
def test_phase_jitter_around_180_degrees_is_no_gain_margin():
    """An inverting stage: the phase only wobbles around the level, it never passes it."""
    f = [1.0, 10.0, 100.0, 1000.0, 10000.0]
    assert not every(by_hand(f, [6.0] * 5, [179.9, 180.1, 179.9, 180.2, 179.8]))["GM"].found
    # it starts on the level and leaves it: it was never clearly on the other side
    assert not every(by_hand(f, [6.0, 6.0, 6.0, 0.0, -10.0], [-179.9, -180.1, -179.9, -225.0, -270.0]))["GM"].found


def test_a_noisy_pass_through_minus_180_is_still_a_gain_margin():
    c = by_hand([1.0, 10.0, 100.0, 1000.0, 10000.0], [0.0, -5.0, -6.0, -7.0, -10.0],
                [-170.0, -179.9, -180.1, -179.95, -190.0])
    gm = every(c)["GM"]
    assert gm.found and 5.0 < gm.margin < 6.0                   # the smallest of the three passes


def test_copied_frequency_keeps_its_digits_below_one_hertz():
    rows = table([Marker("M1", "user", 0.0123456, -1.0, -10.0), Marker("M2", "user", 1234.5678, -1.0, -10.0)],
                 "t").splitlines()
    assert rows[2].split("\t")[1] == "0.0123456"
    assert rows[3].split("\t")[1] == "1234.57"


def test_the_cutoff_counts_from_the_flat_level_when_there_is_one():
    """v3 (user, 2026-10-07): a low-pass with a hump before its cut-off. The cut-off lies 3 dB
    below the flat level, not 3 dB below the top of the hump."""
    w0 = 2 * math.pi * 10e3
    hump = TransferFunction.custom([w0 * w0], [1.0, w0 / 2.0, w0 * w0])       # second order, Q = 2: a 6.3 dB hump
    m = every(of(hump))
    x2 = (1.75 + math.sqrt(1.75 ** 2 + 4)) / 2                  # |H|^2 = 1/2
    assert set(m) >= {"fc", "pk"} and "fL" not in m             # counted from the hump it was two edges, 6.2 and 11.7 kHz
    assert m["fc"].freq == pytest.approx(10e3 * math.sqrt(x2), rel=0.01)       # 14.8 kHz
    assert m["fc"].db == pytest.approx(-3.0, abs=0.05)
    assert m["pk"].found and m["pk"].db == pytest.approx(6.3, abs=0.2)         # the peak marker still sits on the hump


def test_a_notch_filter_gets_both_edges_with_bandwidth_and_q():
    m = every(of(NOTCH))
    assert "fc" not in m and m["fL"].freq < F0 < m["fH"].freq
    assert m["fL"].db == pytest.approx(-3.0, abs=0.05) and m["fH"].extra.startswith("BW ")
    assert float(m["fH"].extra.split("Q ")[1]) == pytest.approx(1.0, rel=0.05)


def test_a_resonant_band_pass_keeps_the_rule_of_v2():
    m = every(of(BPF))                                          # no flat stretch: 3 dB below the peak, as before
    assert m["fL"].db == pytest.approx(m["pk"].db - 3.0, abs=1e-9) and m["fH"].db == m["fL"].db


def test_the_simulators_loop_gain_has_both_margins():
    m = every(of(TransferFunction.loop3()))                     # 4 / (1 + s/w)^3 with a pole at 1 kHz
    assert m["GM"].margin == pytest.approx(6.02, abs=0.2) and m["GM"].freq == pytest.approx(1e3 * math.sqrt(3), rel=0.02)
    assert m["PM"].margin == pytest.approx(27.1, abs=1.0)


def test_no_notch_or_margin_in_the_noise_floor():
    """Below -80 dB the curve is the scope's noise: its lowest point there is no notch, and the
    phase wandering through -180 degrees there is no gain margin (measure/metrics.py: noise_ends)."""
    tf = theory.build("butter_lpf", {"fc": 10e3, "n": 5})
    for seed in (1, 2, 3):
        rnd = random.Random(seed)
        freqs = grid(20.0, 5e6, 40)
        m = every(curve(freqs, [tf.h(f) + complex(rnd.gauss(0, 1e-4), rnd.gauss(0, 1e-4)) for f in freqs]))
        assert not m["nt"].found, (seed, m["nt"].freq)
        assert m["GM"].freq is None or m["GM"].freq < 20e3, (seed, m["GM"].freq)
        assert m["fc"].freq == pytest.approx(10e3, rel=0.02)


def test_the_automatic_markers_are_quick_on_a_long_narrow_sweep():
    """They are worked out after every measured point: a narrow linear sweep of 2000 points (a
    crystal's) must not take a large part of a point's time (about one second on the bench)."""
    import time
    tf = theory.TransferFunction.crystal()
    rnd = random.Random(1)
    freqs = [0.99e6 + 0.07e6 * k / 1999 for k in range(2000)]
    c = curve(freqs, [tf.h(f) + complex(rnd.gauss(0, 3e-4), rnd.gauss(0, 3e-4)) for f in freqs])
    ms = MarkerSet()
    ms.kinds = {"cutoff", "peak", "notch"}
    t = time.perf_counter()
    ms.evaluate(c)
    assert time.perf_counter() - t < 0.3


def test_a_clean_notch_at_the_end_of_a_sparse_sweep_keeps_its_marker():
    """The sudden bend of a notch is not noise (measure/metrics.py: noise_ends)."""
    tf = theory.build("rlc_notch", {k: v[0] for k, v in theory.PARAMS["rlc_notch"].items()})
    freqs = [32.0 * (17683.0 / 32.0) ** (k / 54) for k in range(55)]          # 20 per decade, past the notch
    rnd = random.Random(11)
    m = every(curve(freqs, [tf.h(f) * 10 ** (rnd.gauss(0, 0.02) / 20) for f in freqs]))
    assert m["nt"].found and m["nt"].freq == pytest.approx(15.92e3, rel=0.03)
