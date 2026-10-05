"""Scope built-in measurement mode (SPEC.md section 8.3, method BUILTIN)."""
from __future__ import annotations

import cmath
import math

from ..drivers.base import Digitizer


def builtin_transfer(digitizer: Digitizer, ref_ch: int, dut_ch: int) -> tuple[complex, float, float]:
    """H from the scope's own amplitude and phase measurements.
    Returns (H, ref amplitude, dut amplitude) with amplitudes in volts peak."""
    if not (digitizer.caps.has_builtin_amplitude and digitizer.caps.has_builtin_phase):
        raise NotImplementedError("this scope has no built-in amplitude and phase measurement")
    a_ref = digitizer.builtin_amplitude(ref_ch)
    a_dut = digitizer.builtin_amplitude(dut_ch)
    if a_ref <= 0:
        raise ZeroDivisionError("built-in reference amplitude is zero")
    phase = math.radians(digitizer.builtin_phase(ref_ch, dut_ch))
    return (a_dut / a_ref) * cmath.exp(1j * phase), a_ref, a_dut
