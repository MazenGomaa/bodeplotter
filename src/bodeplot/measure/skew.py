"""Channel skew check and correction (SPEC.md section 8.6).

On the UPO1054 the DUT channel can sit a whole number of 2 ns samples away from
the reference channel in time. delta-t is DUT minus reference:
    delta_t = phase(H) / (360 deg * f)      with both probes on one node
    phase_corr = phase - 360 * f * delta_t
"""
from __future__ import annotations

import cmath
import math
from datetime import datetime, timezone

from ..models import SkewCheck

# States measured on the bench (HW_REPORT.md 12.11), seconds.
KNOWN_STATES_S: tuple[float, ...] = (-1.85e-9, 0.15e-9, 2.15e-9, 4.15e-9)
SNAP_TOL_S = 0.3e-9             # snap if within this of a known state
CONSISTENCY_TOL_S = 0.3e-9      # the two check frequencies must agree to this
GAIN_WARN_DB = 0.3
DEFAULT_FREQS_HZ = (10e6, 20e6)


def snap(delay_s: float, states=KNOWN_STATES_S, tol_s: float = SNAP_TOL_S) -> tuple[float, bool]:
    """Return (value to apply, snapped?)."""
    nearest = min(states, key=lambda s: abs(s - delay_s))
    if abs(nearest - delay_s) <= tol_s:
        return nearest, True
    return delay_s, False


def delay_from_h(h: complex, freq_hz: float) -> float:
    """delta-t in seconds from a same-node transfer H at freq_hz. Unambiguous for
    |delta-t| < 1/(2 f): 25 ns at 20 MHz, far more than the known states."""
    return cmath.phase(h) / (2.0 * math.pi * freq_hz)


def correction_deg(freq_hz: float, delay_s: float) -> float:
    """Phase (degrees) that the skew adds at freq_hz; subtract it from the measurement."""
    return 360.0 * freq_hz * delay_s


def correct_h(h: complex, freq_hz: float, delay_s: float) -> complex:
    return h * cmath.exp(-2j * math.pi * freq_hz * delay_s)


def check_frequencies(top_hz: float) -> tuple[float, float]:
    """10 MHz and 20 MHz, or f_top/2 and f_top when 20 MHz is out of reach."""
    hi = min(DEFAULT_FREQS_HZ[1], top_hz)
    lo = DEFAULT_FREQS_HZ[0] if hi >= DEFAULT_FREQS_HZ[1] else hi / 2.0
    return lo, hi


def evaluate(freqs_hz, hs, alignment_epoch: int = 0, now: datetime | None = None) -> SkewCheck:
    """Turn same-node transfer measurements into a SkewCheck: mean delay, snapping,
    gain mismatch and the warnings of SPEC.md 8.6."""
    freqs = [float(f) for f in freqs_hz]
    if not freqs or len(freqs) != len(hs):
        raise ValueError("need one H per check frequency")
    delays = [delay_from_h(h, f) for h, f in zip(hs, freqs)]
    gains = [20.0 * math.log10(abs(h)) if abs(h) > 0 else float("-inf") for h in hs]
    measured = sum(delays) / len(delays)
    gain = sum(gains) / len(gains)
    applied, snapped = snap(measured)
    warnings: list[str] = []
    if len(delays) > 1 and max(delays) - min(delays) > CONSISTENCY_TOL_S:
        warnings.append(
            "The two check frequencies disagree by %.2f ns (%s); the offset is not a pure delay."
            % ((max(delays) - min(delays)) * 1e9,
               ", ".join("%.2f ns at %g MHz" % (d * 1e9, f / 1e6) for d, f in zip(delays, freqs))))
    if not snapped:
        warnings.append(
            "Measured delay %.2f ns is more than %.1f ns from every known state (%s ns); "
            "using the measured value." % (measured * 1e9, SNAP_TOL_S * 1e9,
                                           ", ".join("%+.2f" % (s * 1e9) for s in KNOWN_STATES_S)))
    if not math.isfinite(gain) or abs(gain) > GAIN_WARN_DB:
        warnings.append("Gain mismatch between the channels is %+.2f dB (limit %.1f dB): check probe "
                        "compensation, probe settings and the connection." % (gain, GAIN_WARN_DB))
    when = (now or datetime.now(timezone.utc)).astimezone().isoformat(timespec="seconds")
    return SkewCheck(delay_s=applied, measured_s=measured, snapped=snapped, gain_db=gain,
                     freqs_hz=freqs, per_freq_delay_s=delays, per_freq_gain_db=gains,
                     warnings=warnings, checked_at=when, alignment_epoch=alignment_epoch)


def describe(check: SkewCheck | None) -> str:
    if check is None:
        return "skew: not checked"
    return "skew: %+.2f ns (%s, measured %+.2f ns, gain mismatch %+.2f dB, checked %s)" % (
        check.delay_s * 1e9, "snapped" if check.snapped else "not snapped",
        check.measured_s * 1e9, check.gain_db, check.checked_at)
