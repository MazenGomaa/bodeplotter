"""Frequency plan (SPEC.md section 8.1)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..models import SweepConfig, SweepType
from ..units import fmt_si


class PlanError(ValueError):
    pass


@dataclass
class Plan:
    freqs_hz: list[float]
    warnings: list[str] = field(default_factory=list)


def frequencies(cfg: SweepConfig) -> list[float]:
    lo, hi = float(cfg.start_hz), float(cfg.stop_hz)
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo <= 0 or hi <= 0:
        raise PlanError("Start and stop frequency must be positive.")
    if hi <= lo:
        raise PlanError("Stop frequency must be above start frequency.")
    if cfg.sweep_type is SweepType.LOG:
        if cfg.points_per_decade < 1:
            raise PlanError("Points per decade must be at least 1.")
        decades = math.log10(hi / lo)
        # the small epsilon keeps exact decades exact despite float noise in log10
        n = int(math.ceil(decades * cfg.points_per_decade - 1e-9)) + 1
        n = max(n, 2)
        out = [lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]
    else:
        if cfg.n_points < 2:
            raise PlanError("A linear sweep needs at least 2 points.")
        n = int(cfg.n_points)
        out = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    out[0], out[-1] = lo, hi            # endpoints exact
    if cfg.descending:
        out.reverse()
    return out


def make_plan(cfg: SweepConfig, source_min_hz: float, source_max_hz: float,
              meter_min_hz: float, meter_max_hz: float, scope_bandwidth_hz: float | None = None) -> Plan:
    freqs = frequencies(cfg)
    lo, hi = min(freqs), max(freqs)
    if lo < source_min_hz or hi > source_max_hz:
        raise PlanError("Sweep %s to %s is outside the generator's range (%s to %s)."
                        % tuple(fmt_si(x, "Hz") for x in (lo, hi, source_min_hz, source_max_hz)))
    if lo < meter_min_hz or hi > meter_max_hz:
        raise PlanError("Sweep %s to %s is outside the scope's usable range (%s to %s)."
                        % tuple(fmt_si(x, "Hz") for x in (lo, hi, meter_min_hz, meter_max_hz)))
    warnings = []
    if scope_bandwidth_hz and hi > 0.4 * scope_bandwidth_hz:
        warnings.append("The sweep goes above 40%% of the scope bandwidth (%g MHz): single-channel "
                        "amplitudes are attenuated there, but ratios remain valid."
                        % (scope_bandwidth_hz / 1e6))
    return Plan(freqs, warnings)
