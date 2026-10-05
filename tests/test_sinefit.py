import math

import numpy as np
import pytest

from bodeplot.measure import sinefit


def _sine(n, dt, f, amp, phase, offset, noise=0.0, rng=None):
    t = dt * np.arange(n)
    v = amp * np.cos(2 * np.pi * f * t + phase) + offset
    if noise:
        v = v + rng.normal(0.0, noise, n)
    return v


def _phase_err_deg(a, b):
    return abs((math.degrees(a - b) + 180.0) % 360.0 - 180.0)


def test_clean_sines_random_parameters_non_integer_cycles():
    rng = np.random.default_rng(1)
    for _ in range(200):
        f = 10 ** rng.uniform(1.7, 7.3)
        cycles = rng.uniform(2.3, 9.7)                  # deliberately not whole cycles
        n = 700
        dt = cycles / f / n
        amp, phase, off = 10 ** rng.uniform(-3, 1), rng.uniform(-math.pi, math.pi), rng.uniform(-2, 2)
        fit = sinefit.fit3(_sine(n, dt, f, amp, phase, off), dt, f)
        assert abs(fit.amp - amp) / amp < 1e-3          # amplitude error < 0.1 %
        assert _phase_err_deg(fit.phase_rad, phase) < 0.1
        assert abs(fit.offset - off) < 1e-6 + 1e-3 * amp


def test_noise_at_30_db_snr():
    rng = np.random.default_rng(2)
    errs, snrs = [], []
    for _ in range(100):
        f, n = 1e4, 700
        dt = rng.uniform(3.2, 8.8) / f / n
        amp, phase = 1.0, rng.uniform(-math.pi, math.pi)
        noise = (amp / math.sqrt(2)) / 10 ** (30 / 20)   # 30 dB SNR
        fit = sinefit.fit3(_sine(n, dt, f, amp, phase, 0.3, noise, rng), dt, f)
        errs.append(_phase_err_deg(fit.phase_rad, phase))
        snrs.append(fit.snr_db)
    assert max(errs) < 1.0                               # phase error < 1 degree
    assert all(abs(s - 30.0) < 3.0 for s in snrs)        # SNR estimate within 3 dB


def test_t0_shifts_phase_consistently_for_both_channels():
    f, n, dt, t0 = 2e6, 700, 1e-8, -3.5e-6
    t = t0 + dt * np.arange(n)
    ref = np.cos(2 * np.pi * f * t + 0.4)
    dut = 0.5 * np.cos(2 * np.pi * f * t + 0.4 - math.radians(30))
    h = sinefit.transfer(sinefit.fit3(ref, dt, f, t0), sinefit.fit3(dut, dt, f, t0))
    gain, phase = sinefit.gain_phase(h)
    assert gain == pytest.approx(20 * math.log10(0.5), abs=1e-6)
    assert phase == pytest.approx(-30.0, abs=1e-6)


def test_fit4_recovers_a_frequency_error():
    f_true, n = 1000.0, 700
    dt = 7.0 / f_true / n
    v = _sine(n, dt, f_true, 1.0, 0.7, 0.0)
    fit = sinefit.fit4(v, dt, f_true * 1.004)
    assert fit.freq_hz == pytest.approx(f_true, rel=1e-5)
    assert fit.amp == pytest.approx(1.0, rel=1e-4)


def test_wrap_and_unwrap():
    assert sinefit.wrap_deg(190.0) == pytest.approx(-170.0)
    assert sinefit.wrap_deg(-180.0) == 180.0
    assert sinefit.wrap_deg(540.0) == 180.0
    out = sinefit.unwrap_deg([170.0, -170.0, -150.0])
    assert out == pytest.approx([170.0, 190.0, 210.0])


def test_bad_input_rejected():
    with pytest.raises(ValueError):
        sinefit.fit3([1.0, 2.0], 1e-3, 100.0)
    with pytest.raises(ValueError):
        sinefit.fit3(np.zeros(100), 1e-3, 0.0)
