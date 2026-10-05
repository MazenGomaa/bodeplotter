"""V/div and timebase selection (SPEC.md section 8.3). Pure functions.

All voltages here are at the scope INPUT (tip voltage divided by the probe ratio).
Step tables come from the digitizer; they are not assumed to be 1-2-5
(the UPO1054 has 25 ns/div and no 20 ns/div).
"""
from __future__ import annotations

from dataclasses import dataclass


def choose_timebase(freq_hz: float, steps, horizontal_divs: float, target_cycles: float) -> float:
    """Smallest step whose screen holds at least target_cycles periods."""
    need = target_cycles / freq_hz
    for s in sorted(steps):
        if horizontal_divs * s >= need * (1 - 1e-9):
            return s
    return max(steps)


def samples_per_cycle(freq_hz: float, dt: float) -> float:
    return 1.0 / (freq_hz * dt)


def fraction_of_full_scale(vpp: float, vdiv: float, vertical_divs: float) -> float:
    return vpp / (vertical_divs * vdiv)


def choose_vdiv(vpp: float, steps, vertical_divs: float, target=(0.6, 0.8)) -> float:
    """Most sensitive step that keeps vpp at or below the upper target fraction."""
    ordered = sorted(steps)
    for s in ordered:
        if vpp <= target[1] * vertical_divs * s:
            return s
    return ordered[-1]


def step_up(vdiv: float, steps, n: int = 1) -> float:
    ordered = sorted(steps)
    i = min(range(len(ordered)), key=lambda k: abs(ordered[k] - vdiv))
    return ordered[min(i + n, len(ordered) - 1)]


CLIP_JUMP = 7
CLIP_ESTIMATE_MAX_FRACTION = 0.95   # above this share of samples on the rails the estimate is useless
CLIP_ESTIMATE_MARGIN = 1.25         # the estimate assumes a centred sine; an offset makes it too small


def clipped_vpp_estimate(rail_fraction: float, vdiv: float, data_divs: float) -> float | None:
    """Peak-to-peak of a clipped sine, from the share of samples that sit on the rails.

    A centred sine of amplitude A (in divisions) clipped at +/-R spends the fraction
    p = 1 - (2/pi) asin(R/A) of its time on the rails, so A = R / cos(p pi/2).
    Checked against the real scope (HW_REPORT.md 12.14): 20, 50 and 100 divisions p-p
    were estimated as 19.7, 46 and 108. Returns None when no estimate is possible."""
    import math
    if data_divs <= 0 or not (0.0 < rail_fraction < CLIP_ESTIMATE_MAX_FRACTION):
        return None
    amp_div = (data_divs / 2.0) / math.cos(rail_fraction * math.pi / 2.0)
    return 2.0 * amp_div * vdiv * CLIP_ESTIMATE_MARGIN


@dataclass
class RangeDecision:
    action: str             # "ok" | "change" | "floor"
    vdiv: float
    fraction: float


def decide(vpp: float, clipped: bool, vdiv: float, steps, vertical_divs: float,
           target=(0.6, 0.8), floor_fraction: float = 0.1, rail_fraction: float = 0.0,
           data_divs: float = 0.0) -> RangeDecision:
    """One auto-range decision from one capture.

    - clipped: estimate the amplitude from the share of samples on the rails and go to
      the step that predicts (always at least one step up). When no estimate is possible
      (the digitizer does not report it, or nearly every sample is on a rail) go up
      CLIP_JUMP steps (x200 on a 1-2-5 table): a small jump needs too many retries from
      a far-off start; a jump to the top would leave a small signal under one ADC code.
    - above the upper target, or below the lower one: jump straight to the step the
      measured amplitude predicts (not one step at a time).
    - at the most sensitive step and still below floor_fraction: "floor".
    """
    ordered = sorted(steps)
    frac = fraction_of_full_scale(vpp, vdiv, vertical_divs)
    if clipped:
        est = clipped_vpp_estimate(rail_fraction, vdiv, data_divs)
        if est is None:
            new = step_up(vdiv, ordered, CLIP_JUMP)
        else:
            new = max(choose_vdiv(est, ordered, vertical_divs, target), step_up(vdiv, ordered, 1))
        return RangeDecision("change" if new != vdiv else "ok", new, frac)
    if target[0] <= frac <= target[1]:
        return RangeDecision("ok", vdiv, frac)
    want = choose_vdiv(vpp, ordered, vertical_divs, target)
    if target[1] < frac <= 1.0 and fraction_of_full_scale(vpp, want, vertical_divs) < target[0]:
        # Just over the upper target, still on screen, and the next step would drop below
        # the lower target: stay. Without this a noisy p-p on the boundary flips between two
        # steps until the retries run out (seen on the bench at 8.2 MHz: 11 s, AUTORANGE_FAILED).
        return RangeDecision("ok", vdiv, frac)
    if abs(want - vdiv) <= 1e-12 * max(want, vdiv):
        # already on the best step: a coarse table can leave the fraction below the
        # lower target (e.g. 2 -> 5 jumps); that is as good as it gets
        if vdiv <= ordered[0] * (1 + 1e-9) and frac < floor_fraction:
            return RangeDecision("floor", vdiv, frac)
        return RangeDecision("ok", vdiv, frac)
    return RangeDecision("change", want, frac)
