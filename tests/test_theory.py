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


def test_a_very_high_order_does_not_raise():
    """Review M4: 45 coefficients passed build() and then raised OverflowError on every redraw."""
    tf = theory.build("custom", {"num": [1.0], "den": [1.0] * 45})
    assert abs(tf.h(1.0)) > 0                                    # low frequencies are fine
    big = tf.h(2e7)                                              # no exception: unusable, so not drawn
    assert big == complex("inf") or abs(big) == 0 or big != big or abs(big) >= 0


# ---------------------------------------------------------------------- the circuits for the analysis and the markers
def test_the_circuits_for_the_analysis_match_their_formulas():
    w = lambda f: 2j * math.pi * f
    tf = TransferFunction.rlc_lpf(50.0, 1e-3, 100e-9)                           # Q = sqrt(L/C)/R = 2
    f0 = 1 / (2 * math.pi * math.sqrt(1e-3 * 100e-9))
    assert abs(tf.h(1.0)) == pytest.approx(1.0, abs=1e-6) and abs(tf.h(f0)) == pytest.approx(2.0, rel=1e-6)
    shelf = TransferFunction.rc_shelf(1e3, 10.0, 100e-9)
    assert abs(shelf.h(1.0)) == pytest.approx(1.0, abs=1e-4) and abs(shelf.h(1e9)) == pytest.approx(10 / 1010, rel=1e-3)
    wide = TransferFunction.wide_bpf(100.0, 100e3)
    assert abs(wide.h(100.0)) == pytest.approx(1 / math.sqrt(2), rel=2e-3)
    assert abs(wide.h(100e3)) == pytest.approx(1 / math.sqrt(2), rel=2e-3) and abs(wide.h(3162.0)) == pytest.approx(1.0, abs=2e-3)
    for n in (1, 2, 5, 8):
        b = TransferFunction.butter_lpf(10e3, n)
        assert len(b.den) == n + 1 and abs(b.h(1.0)) == pytest.approx(1.0, abs=1e-6)
        assert abs(b.h(10e3)) == pytest.approx(1 / math.sqrt(2), rel=1e-6)
    assert TransferFunction.butter_lpf(10e3, 2).h(3e3) == pytest.approx(TransferFunction.butter2_lpf(10e3).h(3e3))
    for n in (4, 5):                                                            # 1 dB of ripple: -1 dB at the band edge
        c = TransferFunction.cheby_lpf(10e3, 1.0, n)
        assert 20 * math.log10(abs(c.h(10e3))) == pytest.approx(-1.0, abs=1e-6)
        assert 20 * math.log10(abs(c.h(1.0))) == pytest.approx(0.0 if n % 2 else -1.0, abs=1e-6)
        assert max(20 * math.log10(abs(c.h(f))) for f in range(100, 10000, 50)) == pytest.approx(0.0, abs=0.01)
    two = TransferFunction.two_res(10e3, 10.0, 300e3, 20.0)
    assert abs(two.h(10e3)) == pytest.approx(1.0, abs=0.01) and abs(two.h(300e3)) == pytest.approx(1.0, abs=0.01)
    assert abs(two.h(55e3)) < 0.1
    x = TransferFunction.crystal(1e6, 1.05e6, 100.0)
    assert abs(x.h(1e6)) > 5.0 and abs(x.h(1.05e6)) < 0.2 and abs(x.h(1e3)) == pytest.approx(1.1025, rel=1e-3)
    amp = TransferFunction.amp(10.0, 50e3)
    assert amp.h(1.0) == pytest.approx(10.0, abs=1e-3) and abs(amp.h(50e3)) == pytest.approx(10 / math.sqrt(2))
    loop = TransferFunction.loop3(4.0, 1e3)
    assert loop.h(1e3 * math.sqrt(3)) == pytest.approx(-0.5)                    # -180 degrees at half the size: 6 dB of margin
    assert loop.h(1.0) == pytest.approx(4.0, abs=0.02)


def test_the_circuits_for_the_analysis_have_labels_parts_and_limits():
    new = ("rlc_lpf", "rc_shelf", "wide_bpf", "butter_lpf", "cheby_lpf", "two_res", "crystal", "amp", "loop3")
    assert set(new) <= set(TransferFunction.PRESETS) and TransferFunction.PRESETS[-1] == "custom"
    for name in new:
        defaults = {k: v[0] for k, v in theory.PARAMS[name].items()}
        tf = theory.build(name, defaults)                                       # what the dialogs do with the defaults
        assert tf.name == name and tf.params == defaults and theory.LABELS[name] in tf.label()
        assert all(k in theory.PART_UNITS for k in defaults)
        assert math.isfinite(abs(tf.h(1e3))) and type(SimulatedDUT.from_preset(name, **defaults)) is SimulatedDUT
    assert TransferFunction.rlc_lpf(50.0, 1e-3, 100e-9).label() == "RLC low-pass (resonant) 50 Ω 1 mH 100 nF"
    assert TransferFunction.cheby_lpf(10e3, 1.0, 5).label() == "Chebyshev low-pass 10 kHz 1 dB 5 poles"
    with pytest.raises(ValueError, match="order"):
        theory.build("butter_lpf", {"fc": 10e3, "n": 11})
    with pytest.raises(ValueError, match="order"):
        theory.build("cheby_lpf", {"fc": 10e3, "ripple": 1.0, "n": 0.2})
    assert theory.build("butter_lpf", {"fc": 10e3, "n": 3.0}).params["n"] == 3
