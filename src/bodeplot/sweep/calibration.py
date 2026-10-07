"""Through calibration: the pure part (SPEC.md section 8.7). No Qt, no instrument I/O.

A ThroughCal holds H_cal(f) = Vdut / Vref measured with both probes on one node. A later
measurement is divided by it: H = H_meas / H_cal(f). core.py measures it and decides when
it applies; this module holds the arithmetic and the plausibility rules.
"""
from __future__ import annotations

import bisect
import cmath
import math
from datetime import datetime, timezone

from ..models import Flag, PointResult, ScopeConfig, SweepConfig, SweepType, ThroughCal
from ..units import fmt_si
from . import plan

POINTS_PER_DECADE = 10
MIN_HZ = 50.0
# Above 40 % of the scope bandwidth the single-channel amplitudes fall (plan.make_plan warns
# at the same limit); on the UPO1054 this is the 20 MHz the skew check also stops at.
MAX_FRACTION_OF_BANDWIDTH = 0.4
EDGE_TOL = 1e-3                 # a frequency within 0.1 % of a calibration point is that point
REFUSE_GAIN_DB = 1.0            # more than this is not a through connection
WARN_GAIN_DB = 0.3              # the skew check's limit (measure/skew.py GAIN_WARN_DB)
REF_LEVEL_FRACTION = 0.3        # as core.REF_LEVEL_WARN_FRACTION
BLOCKING_FLAGS = Flag.REF_SUSPECT | Flag.CLIPPED | Flag.BELOW_FLOOR | Flag.AUTORANGE_FAILED
MAX_FLAG_LINES = 5
NOT_A_THROUGH = "This does not look like a through connection"


def frequencies(source_min_hz: float, source_max_hz: float, scope_min_hz: float, scope_max_hz: float,
                bandwidth_hz: float | None) -> list[float]:
    """Always the full range both instruments reach, 10 points per decade."""
    lo = max(source_min_hz, scope_min_hz, MIN_HZ)
    hi = min(source_max_hz, scope_max_hz)
    if bandwidth_hz:
        hi = min(hi, MAX_FRACTION_OF_BANDWIDTH * bandwidth_hz)
    if hi <= lo:
        raise ValueError("the instruments share no frequency range to calibrate")
    return plan.frequencies(SweepConfig(SweepType.LOG, lo, hi, POINTS_PER_DECADE))


def _gain_db(h: complex) -> float:
    return 20.0 * math.log10(abs(h)) if abs(h) > 0 else float("-inf")


def _finite(h: complex) -> bool:
    return math.isfinite(h.real) and math.isfinite(h.imag)


def _unwrapped_deg(cal: ThroughCal) -> list[float]:
    """Phase of every point, unwrapped along the frequency axis. A point that is not a
    number stays NaN and does not disturb the unwrapping of the others."""
    out: list[float] = []
    last = None
    for h in cal.h:
        if not _finite(h):
            out.append(float("nan"))
            continue
        p = math.degrees(cmath.phase(h))
        if last is not None:
            p += 360.0 * round((last - p) / 360.0)
        last = p
        out.append(p)
    return out


def fitted_delay_s(cal: ThroughCal) -> float:
    """The delay (DUT minus reference) that fits the phase best: phase = 360 f dt,
    least squares through the origin, over the points that are numbers."""
    pairs = [(f, p) for f, p in zip(cal.freqs_hz, _unwrapped_deg(cal)) if math.isfinite(p)]
    den = sum(f * f for f, _p in pairs)
    if not den:
        return 0.0
    return sum(f * p for f, p in pairs) / (360.0 * den)


def max_gain_db(cal: ThroughCal) -> float:
    """Largest gain deviation from 0 dB, as a magnitude (points that are not numbers left out)."""
    values = [abs(_gain_db(h)) for h in cal.h if _finite(h)]
    return max(values) if values else float("nan")


def response_at(cal: ThroughCal, freq_hz: float) -> complex | None:
    """H_cal at freq_hz, or None outside the calibrated range (no extrapolation).

    Between two points the gain in dB is linear in log frequency. The phase is not
    interpolated as it stands: most of it is the channel delay, which is linear in
    frequency, and a straight line over log f would miss it by 0.09 deg near 18 MHz in the
    +2.15 ns state. So the fitted delay is taken out, the remainder is interpolated in
    log f, and the delay is put back exactly."""
    fs = cal.freqs_hz
    if not fs or not freq_hz > 0:
        return None
    if freq_hz < fs[0] * (1 - EDGE_TOL) or freq_hz > fs[-1] * (1 + EDGE_TOL):
        return None
    for f, h in zip(fs, cal.h):
        if abs(freq_hz - f) <= EDGE_TOL * f:
            return h
    i = bisect.bisect_right(fs, freq_hz)            # fs[i - 1] < freq_hz < fs[i]
    f0, f1 = fs[i - 1], fs[i]
    x = math.log(freq_hz / f0) / math.log(f1 / f0)
    dt = fitted_delay_s(cal)
    ph = _unwrapped_deg(cal)
    r0, r1 = ph[i - 1] - 360.0 * f0 * dt, ph[i] - 360.0 * f1 * dt
    g0, g1 = _gain_db(cal.h[i - 1]), _gain_db(cal.h[i])
    gain = g0 + x * (g1 - g0)
    phase = r0 + x * (r1 - r0) + 360.0 * freq_hz * dt
    if not math.isfinite(gain):
        return 0j
    return cmath.rect(10 ** (gain / 20.0), math.radians(phase))


def correct(h_meas: complex, cal: ThroughCal, freq_hz: float) -> tuple[complex, float, float] | None:
    """(H_meas / H_cal, gain removed in dB, phase removed in degrees), or None when the
    calibration says nothing usable about this frequency."""
    h_cal = response_at(cal, freq_hz)
    if h_cal is None or not math.isfinite(abs(h_cal)) or abs(h_cal) == 0:
        return None
    return h_meas / h_cal, _gain_db(h_cal), math.degrees(cmath.phase(h_cal))


def _probe(atten: dict, ch: int) -> float:
    return float(atten.get(ch, 1.0)) or 1.0         # as DualChannelScopeMeter reads it


def matches(cal: ThroughCal | None, scope_cfg: ScopeConfig) -> bool:
    """True when the calibration was measured through the same paths as scope_cfg uses."""
    if cal is None:
        return False
    same = (cal.ref_channel, cal.dut_channel, cal.coupling, bool(cal.bw_limit)) == (
        scope_cfg.ref_channel, scope_cfg.dut_channel, scope_cfg.coupling, bool(scope_cfg.bw_limit))
    return same and all(_probe(cal.probe_atten, ch) == _probe(scope_cfg.probe_atten, ch)
                        for ch in (scope_cfg.ref_channel, scope_cfg.dut_channel))


def covers(cal: ThroughCal, lo_hz: float, hi_hz: float) -> bool:
    return bool(cal.freqs_hz) and lo_hz >= cal.freqs_hz[0] * (1 - EDGE_TOL) and \
        hi_hz <= cal.freqs_hz[-1] * (1 + EDGE_TOL)


def range_text(cal: ThroughCal) -> str:
    return "%s to %s" % (fmt_si(cal.freqs_hz[0], "Hz"), fmt_si(cal.freqs_hz[-1], "Hz"))


def describe(cal: ThroughCal | None) -> str:
    if cal is None:
        return "cal: none"
    return "cal: %s, %s" % (cal.checked_at[11:16], range_text(cal))


def evaluate(points: list[PointResult], scope_cfg: ScopeConfig, amp_vpp: float, alignment_epoch: int = 0,
             now: datetime | None = None) -> ThroughCal:
    """Turn the same-node measurements into a ThroughCal with the plausibility checks of
    the design (section 4). The points carry the raw H: nothing was corrected."""
    pts = sorted(points, key=lambda p: p.freq_hz)
    if not pts:
        raise ValueError("a calibration needs at least one point")
    hz = lambda p: fmt_si(p.freq_hz, "Hz")
    warnings: list[str] = []
    acceptable = True
    size = lambda p: abs(_gain_db(p.h)) if math.isfinite(_gain_db(p.h)) else float("inf")
    worst = max(pts, key=size)
    if size(worst) > REFUSE_GAIN_DB:
        acceptable = False
        warnings.append("%s: the gain is %+.2f dB at %s (limit %.0f dB). Put both probes on the "
                        "generator output." % (NOT_A_THROUGH, _gain_db(worst.h), hz(worst), REFUSE_GAIN_DB))
    low = min(pts, key=lambda p: p.vref_amp)
    if amp_vpp > 0 and 2.0 * low.vref_amp < REF_LEVEL_FRACTION * amp_vpp:
        acceptable = False
        warnings.append("%s: the reference channel saw only %.3g Vpp at %s, with the generator set to "
                        "%.3g Vpp. Check the reference probe and its ground clip."
                        % (NOT_A_THROUGH, 2.0 * low.vref_amp, hz(low), amp_vpp))
    bad = [p for p in pts if p.flags & BLOCKING_FLAGS]
    for p in bad[:MAX_FLAG_LINES]:
        warnings.append("%s at %s: this point cannot be used." % ((p.flags & BLOCKING_FLAGS).to_text(), hz(p)))
    if len(bad) > MAX_FLAG_LINES:
        warnings.append("... and %d more points like these." % (len(bad) - MAX_FLAG_LINES))
    if bad:
        acceptable = False
    if acceptable and size(worst) > WARN_GAIN_DB:
        warnings.append("Gain mismatch between the channels is %+.2f dB at %s (limit %.1f dB): check probe "
                        "compensation, probe settings and the connection."
                        % (_gain_db(worst.h), hz(worst), WARN_GAIN_DB))
    when = (now or datetime.now(timezone.utc)).astimezone().isoformat(timespec="seconds")
    chans = (scope_cfg.ref_channel, scope_cfg.dut_channel)
    return ThroughCal(freqs_hz=[p.freq_hz for p in pts], h=[p.h for p in pts], checked_at=when,
                      alignment_epoch=alignment_epoch, ref_channel=chans[0], dut_channel=chans[1],
                      probe_atten={ch: _probe(scope_cfg.probe_atten, ch) for ch in chans},
                      coupling=scope_cfg.coupling, bw_limit=bool(scope_cfg.bw_limit), amp_vpp=float(amp_vpp),
                      warnings=warnings, acceptable=acceptable)
