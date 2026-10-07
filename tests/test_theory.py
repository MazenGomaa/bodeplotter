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
