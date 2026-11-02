"""Classification (measure/classify.py): the type, the shape words, the confidence and the
refusals, read from part 1's Metrics.

Design: docs/superpowers/specs/2026-11-02-classification-design.md, section 3."""
import cmath
import dataclasses
import math
import random

import pytest

from bodeplot.measure.analysis_settings import DEFAULTS
from bodeplot.measure.classify import classify, scatter
from bodeplot.measure.metrics import analyse
from bodeplot.measure.response import curve
from bodeplot.measure.theory import TransferFunction as TF

FC = 1 / (2 * math.pi * 1e3 * 100e-9)                       # the RC: 1.592 kHz
F0 = 1 / (2 * math.pi * math.sqrt(1e-3 * 100e-9))           # the RLC circuits: 15.92 kHz
LO, HI = 50.0, 2e7                                          # part 1's sweep (tests/test_metrics.py)


def sweep(tf, lo=LO, hi=HI, ppd=20, noise=0.0, lin=False, n=200, seed=1, off=0):
    """The curve of a transfer function: a log sweep from lo to hi at ppd points per decade, moved by
    off / 4 of a step, or a linear one of n points; Gaussian noise of noise dB and 5 times that in
    degrees, as the bench has (0.02 dB / 0.1 degree)."""
    if lin:
        step = (hi - lo) / (n - 1)
        freqs = [lo + step * (i + off / 4) for i in range(n)]
    else:
        k = int(round(math.log10(hi / lo) * ppd)) + 1
        freqs = [lo * 10 ** (off / 4 / ppd) * (hi / lo) ** (i / (k - 1)) for i in range(k)]
    rnd = random.Random(seed)
    return curve(freqs, [tf.h(f) * cmath.rect(10 ** (rnd.gauss(0, noise) / 20), math.radians(rnd.gauss(0, 5 * noise)))
                         for f in freqs])


def of(c, phase=True, s=DEFAULTS):
    return classify(analyse(c, phase, s), c, phase, s)


CRYSTAL_LIN = dict(lo=0.9e6, hi=1.2e6, lin=True, n=200)
# preset, the type with the defaults, its sweep (part 1's log sweep unless given)
CIRCUITS = [("through", "Flat", {}), ("rc_lpf", "Low-pass", {}), ("butter2_lpf", "Low-pass", {}),
            ("rlc_lpf", "Low-pass", {}), ("butter_lpf", "Low-pass", {}), ("cheby_lpf", "Low-pass", {}),
            ("amp", "Low-pass", {}), ("loop3", "Low-pass", {}), ("rc_hpf", "High-pass", {}),
            ("rlc_bpf", "Band-pass", {}), ("wide_bpf", "Band-pass", dict(lo=5.0)), ("rlc_notch", "Band-stop", {}),
            ("rc_shelf", "Low-pass", {}), ("crystal", "Crystal-like", CRYSTAL_LIN), ("two_res", "Unknown", {})]
ELLIPTIC_DEN = TF.butter_lpf(10e3, 5).den
ELLIPTIC = TF.custom(                                       # tests/test_metrics.py: notches at 16 and 25 kHz
    [x * ELLIPTIC_DEN[-1] / ((2 * math.pi) ** 4 * (16e3 * 25e3) ** 2)
     for x in (1.0, 0.0, (2 * math.pi) ** 2 * (16e3 ** 2 + 25e3 ** 2), 0.0, (2 * math.pi) ** 4 * (16e3 * 25e3) ** 2)],
    ELLIPTIC_DEN)


# ---------------------------------------------------------------------- the type and its words
@pytest.mark.parametrize("noise", [0.0, 0.02])
@pytest.mark.parametrize("name, kind, how", CIRCUITS)
def test_every_theory_circuit_gets_its_type(name, kind, how, noise):
    k = of(sweep(TF.from_preset(name), noise=noise, **how))
    assert not k.refused and k.kind == kind, (k.refused, k.kind, k.words, k.reasons)


def test_gain_only_from_a_flat_level():
    """Design change 8: a level read from a peak is that peak, not a passband gain."""
    k = of(sweep(TF.rc_lpf(), lo=800.0))
    assert k.kind == "Low-pass" and not any(w.startswith(("gain", "loss")) for w in k.words), k.words
    assert "gain +20.0 dB" in of(sweep(TF.amp())).words


def _word(k, start):
    (w,) = [w for w in k.words if w.startswith(start)]
    return w


def test_shape_words():
    assert "order 1" in of(sweep(TF.rc_lpf())).words
    assert "order 5" in of(sweep(TF.butter_lpf())).words
    peaking = _word(of(sweep(TF.rlc_lpf())), "peaking")
    assert float(peaking.split()[1]) == pytest.approx(6.3, abs=0.2) and peaking.endswith(" dB")
    assert "ripple 1.0 dB (Chebyshev-like)" in of(sweep(TF.cheby_lpf())).words
    assert "gain +20.0 dB" in of(sweep(TF.amp())).words
    assert "stopband notches (elliptic-like)" in of(sweep(ELLIPTIC)).words
    assert "Q 1" in of(sweep(TF.rlc_bpf())).words
    k = of(sweep(TF.crystal(), **CRYSTAL_LIN))
    fs, fp = (_word(k, w).split(" ", 1)[1] for w in ("fs ", "fp "))
    assert _hz(fs) == pytest.approx(1e6, rel=0.005) and _hz(fp) == pytest.approx(1.05e6, rel=0.005)
    assert k.score == 100


def _hz(text):
    number, unit = text.split()
    return float(number) * {"Hz": 1, "kHz": 1e3, "MHz": 1e6}[unit]


def test_two_resonances_are_unknown_with_both_peaks_named():
    k = of(sweep(TF.two_res()))
    peaks = [_hz(w.split(" at ")[1]) for w in k.words if w.startswith("peak at")]
    assert k.kind == "Unknown" and peaks == [pytest.approx(10e3, rel=0.03), pytest.approx(300e3, rel=0.03)]


@pytest.mark.parametrize("off", range(4))
@pytest.mark.parametrize("ppd", [12, 40])
@pytest.mark.parametrize("name, kind, how", CIRCUITS)
def test_noise_changes_no_type(name, kind, how, ppd, off):
    how = dict(how, ppd=ppd) if not how.get("lin") else how
    k = of(sweep(TF.from_preset(name), noise=0.2, off=off, seed=off, **how))
    assert not k.refused and k.kind == kind, (k.refused, k.kind, k.words, k.reasons)


LINEAR = [("rc_lpf", FC, "Low-pass"), ("rc_hpf", FC, "High-pass"), ("rlc_bpf", F0, "Band-pass"),
          ("rlc_notch", F0, "Band-stop"), ("butter2_lpf", 10e3, "Low-pass"), ("rlc_lpf", F0, "Low-pass"),
          ("butter_lpf", 10e3, "Low-pass"), ("cheby_lpf", 10e3, "Low-pass"), ("amp", 50e3, "Low-pass"),
          ("loop3", 1e3, "Low-pass"), ("rc_shelf", 1 / (2 * math.pi * 1010.0 * 100e-9), "Low-pass")]


@pytest.mark.parametrize("n", [100, 200, 400])
@pytest.mark.parametrize("name, f, kind", LINEAR)
def test_linear_sweeps(name, f, kind, n):
    """From 0.1 to 10 times the circuit's frequency, clean, 0.02 dB and 0.2 dB (two seeds): 132 sweeps."""
    for noise, seed in ((0.0, 1), (0.02, 1), (0.2, 1), (0.2, 2)):
        k = of(sweep(TF.from_preset(name), 0.1 * f, 10 * f, lin=True, n=n, noise=noise, seed=seed))
        assert not k.refused and k.kind == kind, (noise, seed, k.refused, k.kind, k.words, k.reasons)


# ---------------------------------------------------------------------- under-sampled
def test_a_coarse_sweep_is_never_sure():
    for off in range(4):
        for ppd in (5, 8):
            k = of(sweep(TF.two_res(), ppd=ppd, off=off))
            assert k.refused or k.score <= 85, (ppd, off, k.kind, k.score, k.reasons)


def test_a_narrow_sweep_that_missed_the_peak_is_refused():
    """A sweep that starts above the series resonance sees only the notch: never sure of it."""
    for n in (40, 80, 200):
        k = of(sweep(TF.crystal(), **dict(CRYSTAL_LIN, lo=1.01e6, n=n)))
        assert k.refused or k.score < 60, (n, k.kind, k.score, k.reasons)


@pytest.mark.parametrize("off", range(4))
@pytest.mark.parametrize("n", [20, 40, 80])
def test_a_thin_narrow_sweep_across_a_crystal_is_crystal_like_but_not_sure(n, off):
    k = of(sweep(TF.crystal(), **dict(CRYSTAL_LIN, n=n, off=off)))
    assert k.kind == "Crystal-like" and k.score <= 85 and any("Too few points" in t for t, _a in k.reasons)


# ---------------------------------------------------------------------- refusals, each alone
def test_a_slice_of_a_slope_is_refused():
    k = of(sweep(TF.rc_lpf(), 10e3, 50e3))
    assert k.kind == "Not classified" and "decade" in k.refused and k.score is None


def test_a_narrow_sweep_across_a_crystal_is_not_refused():
    k = of(sweep(TF.crystal(), **CRYSTAL_LIN))
    assert not k.refused and k.kind == "Crystal-like"


def floored(tf, floor, lo, hi, ppd=20, seed=1):
    rnd = random.Random(seed)
    k = int(round(math.log10(hi / lo) * ppd)) + 1
    freqs = [lo * (hi / lo) ** (i / (k - 1)) for i in range(k)]
    return curve(freqs, [tf.h(f) + complex(rnd.gauss(0, floor), rnd.gauss(0, floor)) for f in freqs])


def test_mostly_noise_is_refused():
    k = of(floored(TF.butter_lpf(), 1e-2, 100.0, 100e6))          # a floor at -40 dB from about 25 kHz
    assert k.refused and "noise" in k.refused, (k.kind, k.refused, k.reasons)


def test_heavy_scatter_refuses():
    k = of(sweep(TF.through(), noise=2.0))
    assert k.refused and "scatter" in k.refused, (k.kind, k.refused)


def test_noise_is_not_ripple():
    c = sweep(TF.butter_lpf(), noise=0.5)
    k = of(c)
    assert k.kind == "Low-pass" and not any("ripple" in w for w in k.words), k.words
    assert ("The scatter near the level is %.2f dB: the numbers are uncertain." % scatter(analyse(c), c), 10) \
        in k.reasons


def _flag_share(c, share):
    n = len(c.f)
    c.point_flagged = [math.floor((i + 1) * share) > math.floor(i * share) for i in range(n)]
    return c


def test_many_flagged_points_refuse():
    c = _flag_share(sweep(TF.rc_lpf()), 0.31)
    assert sum(c.point_flagged) / len(c.f) > 0.3
    k = of(c)
    assert k.refused and "flag" in k.refused


def test_a_few_flagged_points_cost_their_share():
    c = _flag_share(sweep(TF.rc_lpf()), 0.1)
    share = sum(c.point_flagged) / len(c.f)
    k = of(c)
    assert not k.refused and k.score == 100 - round(100 * share)


def test_a_sweep_wide_flag_lowers_the_score_only():
    c = sweep(TF.rc_lpf())
    assert of(c).score == 100
    c.wide_flags = ["skew unchecked"]
    k = of(c)
    assert not k.refused and k.kind == "Low-pass" and k.score == 90
    assert k.reasons[0][1] == 10 and "skew unchecked" in k.reasons[0][0].lower()


def test_a_low_score_refuses():
    c = sweep(TF.rc_lpf(), lo=100.0)                                # the passband spans 0.8 decade
    k = of(c)
    assert not k.refused and k.score == 80, (k.score, k.reasons)
    k = of(c, s=dataclasses.replace(DEFAULTS, min_score=95))
    assert k.kind == "Not classified" and k.score == 80 and k.reasons and "95" in k.refused


def test_flat_and_all_pass():
    c = sweep(TF.through())
    k = of(c)
    assert (k.kind, k.score) == ("Flat", 100)
    k = of(c, phase=False)
    assert (k.kind, k.score) == ("Flat", 70) and k.reasons == [("Phase not measured: an all-pass looks the same.", 30)]
    w = 2 * math.pi * 10e3
    assert of(sweep(TF.custom([-1 / w, 1], [1 / w, 1]))).kind == "All-pass"


# ---------------------------------------------------------------------- the settings
def test_settings_move_the_answer():
    c = sweep(TF.rc_shelf())
    assert of(c).kind == "Low-pass"
    k = of(c, s=dataclasses.replace(DEFAULTS, shelf_hi=50.0))
    assert k.kind == "Shelf" and any(w.startswith("high-frequency step") for w in k.words), k.words
    c = sweep(TF.crystal(), **CRYSTAL_LIN)
    assert of(c, s=dataclasses.replace(DEFAULTS, crystal_q=200)).kind != "Crystal-like"


def test_the_score_adds_up():
    for name, _kind, how in CIRCUITS:
        for noise in (0.0, 0.2):
            k = of(sweep(TF.from_preset(name), noise=noise, ppd=10, **how) if not how.get("lin")
                   else sweep(TF.from_preset(name), noise=noise, **how))
            if k.score is not None:
                assert k.score == max(0, 100 - sum(amount for _text, amount in k.reasons)), name


def test_a_trace_part_1_cannot_analyse_is_refused_with_its_reason():
    c = sweep(TF.rc_lpf(), 100.0, 200.0, lin=True, n=3)
    k = of(c)
    assert k.kind == "Not classified" and "usable points" in k.refused and k.score is None
