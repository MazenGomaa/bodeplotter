"""Sine fitting (SPEC.md section 8.4).

3-parameter least squares at a known frequency:  v(t) = a*cos(wt) + b*sin(wt) + c
amplitude = hypot(a, b), phase = atan2(-b, a), so v(t) = A*cos(wt + phase) + c.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class SineFit:
    freq_hz: float
    amp: float              # volts peak
    phase_rad: float
    offset: float
    resid_rms: float
    snr_db: float

    @property
    def phasor(self) -> complex:
        return self.amp * complex(math.cos(self.phase_rad), math.sin(self.phase_rad))

    def evaluate(self, t: np.ndarray) -> np.ndarray:
        return self.amp * np.cos(2 * np.pi * self.freq_hz * t + self.phase_rad) + self.offset


def _snr_db(amp: float, resid_rms: float) -> float:
    if resid_rms <= 0 or not math.isfinite(resid_rms):
        return float("inf")
    if amp <= 0:
        return float("-inf")
    return 20.0 * math.log10((amp / math.sqrt(2.0)) / resid_rms)


def fit3(volts, dt: float, freq_hz: float, t0: float = 0.0) -> SineFit:
    """3-parameter fit at a known frequency. Tolerates non-integer cycle counts and DC offset."""
    v = np.asarray(volts, dtype=float)
    if v.size < 4:
        raise ValueError("need at least 4 samples")
    if not (freq_hz > 0 and dt > 0):
        raise ValueError("freq_hz and dt must be positive")
    t = t0 + dt * np.arange(v.size)
    w = 2.0 * np.pi * freq_hz
    m = np.column_stack((np.cos(w * t), np.sin(w * t), np.ones(v.size)))
    (a, b, c), *_ = np.linalg.lstsq(m, v, rcond=None)
    resid = v - m @ np.array([a, b, c])
    # 3 fitted parameters: unbiased residual estimate
    resid_rms = float(np.sqrt(np.sum(resid ** 2) / max(v.size - 3, 1)))
    amp = float(math.hypot(a, b))
    return SineFit(freq_hz, amp, float(math.atan2(-b, a)), float(c), resid_rms, _snr_db(amp, resid_rms))


def fit4(volts, dt: float, freq_guess_hz: float, t0: float = 0.0, iterations: int = 8) -> SineFit:
    """4-parameter refinement (frequency free), IEEE-1057 style Gauss-Newton started
    from freq_guess_hz. The guess must come from the generator setting, never from
    zero crossings (Milestone 0c: that locked onto the wrong frequency at low SNR)."""
    v = np.asarray(volts, dtype=float)
    t = t0 + dt * np.arange(v.size)
    f = float(freq_guess_hz)
    best = fit3(v, dt, f, t0)
    for _ in range(iterations):
        w = 2.0 * np.pi * f
        a = best.amp * math.cos(best.phase_rad)
        b = -best.amp * math.sin(best.phase_rad)
        cw, sw = np.cos(w * t), np.sin(w * t)
        m = np.column_stack((cw, sw, np.ones(v.size), 2 * np.pi * t * (-a * sw + b * cw)))
        sol, *_ = np.linalg.lstsq(m, v, rcond=None)
        df = float(sol[3])
        if not math.isfinite(df):
            break
        f_new = f + df
        if not (0.5 * freq_guess_hz < f_new < 2.0 * freq_guess_hz):
            break
        cand = fit3(v, dt, f_new, t0)
        if cand.resid_rms > best.resid_rms * 1.0001:
            break
        converged = abs(df) < 1e-9 * f
        f, best = f_new, cand
        if converged:
            break
    return best


def transfer(ref: SineFit, dut: SineFit) -> complex:
    """H = Vdut / Vref as a phasor ratio."""
    if ref.amp == 0:
        raise ZeroDivisionError("reference amplitude is zero")
    return dut.phasor / ref.phasor


def wrap_deg(deg: float) -> float:
    """Wrap to (-180, 180]."""
    d = (deg + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def gain_phase(h: complex) -> tuple[float, float]:
    mag = abs(h)
    gain = 20.0 * math.log10(mag) if mag > 0 else float("-inf")
    return gain, wrap_deg(math.degrees(math.atan2(h.imag, h.real)))


def unwrap_deg(phases) -> np.ndarray:
    return np.degrees(np.unwrap(np.radians(np.asarray(phases, dtype=float))))
