"""The numbers behind the analysis (v3): every threshold of measure/metrics.py and analysis.py,
as settings with a default, a range and an explanation. No Qt.

Design: docs/superpowers/specs/2026-11-02-classification-design.md, section 5 (the user,
2026-11-02: "never let values be hardcoded, and add settings for it if possible"). A number
of the analysis lives here and nowhere else; the Settings dialog's Analysis tab is built from
FIELDS. The defaults are the values part 1 was built and tested with.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    key: str
    default: float
    group: str
    label: str
    unit: str           # shown after the number; "" for a plain count or ratio
    lo: float           # the range the Settings dialog allows
    hi: float
    decimals: int       # 0: a whole number
    tip: str


GENERAL, FLAT, ROLL, RES, NOISE = ("General", "Passband and flat stretches", "Cut-off and roll-off", "Resonances",
                                   "Noise floor")
CLASSIFY, WEIGHTS = "Classification", "Score weights"
GROUPS = (GENERAL, FLAT, ROLL, RES, NOISE, CLASSIFY, WEIGHTS)

FIELDS = (
    Field("min_points", 5, GENERAL, "Fewest usable points", "", 3, 50, 0,
          "With fewer usable points than this the trace is not analysed."),
    Field("flat_slope", 3.0, FLAT, "Flat: slope at most", "dB/dec", 0.5, 20.0, 1,
          "A point is flat when the line through the points around it (over the flat window) is no steeper "
          "than this."),
    Field("flat_window", 1.0 / 3.0, FLAT, "Flat window", "dec", 0.05, 2.0, 3,
          "The width of the window whose line decides whether a point is flat."),
    Field("flat_span", 1.0 / 3.0, FLAT, "Flat stretch spans at least", "dec", 0.05, 3.0, 3,
          "A run of flat points is a flat stretch only when it spans at least this much..."),
    Field("flat_points", 5, FLAT, "Flat stretch has at least", "points", 3, 100, 0,
          "... and has at least this many points."),
    Field("flat_range", 3.0, FLAT, "Flat stretch stays within", "dB", 0.5, 20.0, 1,
          "A flat stretch may not move by more than this from its lowest to its highest gain; a run that drifts "
          "further is cut where it leaves this range."),
    Field("calm_share", 0.25, FLAT, "Level from the flattest", "share", 0.05, 1.0, 2,
          "The level of a flat stretch is the median gain of this share of its points, the flattest ones, so "
          "that the shoulder before a cut-off or the foot of a hump does not pull it."),
    Field("calm_points", 3, FLAT, "Level from at least", "points", 1, 50, 0,
          "... and of at least this many points."),
    Field("drop_db", 3.0, FLAT, "Cut-off below the level", "dB", 0.5, 20.0, 1,
          "The cut-off lies this far below the passband level; also the width at which a resonance's Q is "
          "read. A flat stretch within this of the highest one is a passband."),
    Field("floor_db", 10.0, FLAT, "Stopband floor below the level", "dB", 3.0, 100.0, 1,
          "A flat stretch at least this far below the passband level is a stopband floor. The noise at an "
          "end of the sweep must lie this far below the rest, too."),
    Field("trough_db", 0.1, FLAT, "Ripple: a dip counts from", "dB", 0.01, 3.0, 2,
          "A dip inside the passband counts for the ripple when it is at least this deep."),
    Field("short_decades", 1.0, FLAT, "Short passband: under", "dec", 0.1, 5.0, 2,
          "A passband that runs to an end of the sweep and spans less than this gets the note that its level, "
          "and with it the cut-off, is uncertain."),
    Field("slope_window", 0.5, ROLL, "Slope window", "dec", 0.1, 2.0, 2,
          "The roll-off's slope is the median slope of every window this wide inside it."),
    Field("settle_decades", 1.0, ROLL, "Floor closer than this: a limit", "dec", 0.1, 5.0, 2,
          "When the stopband floor begins less than this beyond the cut-off, no window is free of the knee "
          "or of the bend into the floor: the slope and the order are limits (≥)."),
    Field("steepening", 2.0, ROLL, "Still steepening by", "dB/dec", 0.1, 20.0, 1,
          "A roll-off that runs to the end of the sweep and whose outermost window is this much steeper than "
          "the median slope was still getting steeper: the slope and the order are limits (≥)."),
    Field("comeback_db", 3.0, ROLL, "Hidden notch: gain comes back", "dB", 0.5, 30.0, 1,
          "A roll-off that reaches no floor and no notch ends in a notch where the gain comes back up by this "
          "much and then goes on as a curve (a notch the scatter hid)."),
    Field("settle_points", 4, ROLL, "... over at least", "points", 3, 50, 0,
          "The curve after a hidden notch's comeback must go on for at least this many points without turning "
          "up and down like noise."),
    Field("prominence_db", 1.0, RES, "Stands clear by at least", "dB", 0.1, 20.0, 1,
          "A peak or notch stands at least this far clear of the trace on both sides."),
    Field("noise_factor", 8.0, RES, "... and the scatter times", "", 1.0, 50.0, 1,
          "A peak or notch also stands at least this many times the scatter of the trace around it clear."),
    Field("noise_window", 1.0, RES, "Scatter window", "dec", 0.1, 5.0, 2,
          "The scatter of the trace around a point is estimated over this width..."),
    Field("scatter_points", 41, RES, "Scatter from at most", "points", 9, 400, 0,
          "... from at most this many points (a decade at 40 points per decade)."),
    Field("few_points", 5, RES, "Too few points: under", "points", 2, 50, 0,
          "A resonance with fewer points across it than this gets the note that its top and its Q are "
          "uncertain."),
    Field("pair_factor", 1.2, RES, "Same resonance within", "×", 1.01, 3.0, 2,
          "With 'Compare with', two resonances of the same kind this close in frequency are the same one in "
          "both traces."),
    Field("noise_db", 0.5, NOISE, "Noise: scatter over", "dB", 0.05, 10.0, 2,
          "From an end inwards, a point lies in noise when the gain around it scatters by more than this..."),
    Field("noise_flips", 0.35, NOISE, "... and turns at least", "share", 0.05, 1.0, 2,
          "... and its second differences change sign at least this often (noise about 0.73; the bend of a "
          "notch or an edge keeps one sign)."),
    Field("noise_points", 9, NOISE, "Noise test over at least", "points", 3, 100, 0,
          "The fewest points the noise test is made on, and the fewest a noisy end must have."),
    Field("noise_gap", 3, NOISE, "Clean gap inside noise up to", "points", 0, 20, 0,
          "A gap this short in the noise, where it looks clean by chance, does not end it."),
    Field("noise_turns", 0.4, NOISE, "Noisy end turns at least", "share", 0.05, 1.0, 2,
          "A noisy end turns up or down at least this often from point to point (noise about 0.67); a sparse "
          "sweep across a notch runs one way for many points."),
    Field("noise_near", 30.0, NOISE, "Near the noise: within", "dB", 1.0, 100.0, 1,
          "Within this of a noise floor's level the scatter close around each point counts too, when larger."),
    Field("noise_peak", 10.0, NOISE, "Noise peaks reach", "dB", 1.0, 40.0, 1,
          "How far over its median level the noise's peaks reach; a peak or notch near the noise must stand "
          "clearer than that can push its own point."),
    Field("noise_rise", 12.0, NOISE, "Still the curve above", "dB", 1.0, 40.0, 1,
          "A point this far over the noise's level is still the curve, not noise."),
    # Classification (design section 3)
    Field("crystal_ratio", 1.2, CLASSIFY, "Crystal: notch within", "×", 1.01, 2.0, 2,
          "A peak with a notch above it, closer than this ratio of their frequencies, is crystal-like (a "
          "ceramic resonator reads the same)."),
    Field("crystal_q", 10, CLASSIFY, "Crystal: Q at least", "", 1, 1000, 0,
          "Both the peak and the notch of a crystal-like pair must be at least this sharp (Q from their width)."),
    Field("allpass_deg", 90, CLASSIFY, "All-pass: phase turns", "°", 10, 360, 0,
          "A flat magnitude whose phase turns by at least this much across the sweep is an all-pass; less "
          "is flat (a wire or an amplifier)."),
    Field("notch_db", 10.0, CLASSIFY, "Notch / peak: at least", "dB", 1.0, 60.0, 1,
          "A notch this deep makes a band-stop; two peaks this high with no flat passband read unknown; a "
          "peak that falls this much on one side only is a peaking low-pass or high-pass."),
    Field("shelf_lo", 3.0, CLASSIFY, "Shelf: step at least", "dB", 0.5, 20.0, 1,
          "A flat stretch beyond the cut-offs at least this far below the level makes a shelf..."),
    Field("shelf_hi", 20.0, CLASSIFY, "Shelf: step under", "dB", 3.0, 100.0, 1,
          "... and less than this far below; deeper, it is the stopband of a low-pass or high-pass with a "
          "finite rejection."),
    Field("ripple_db", 0.3, CLASSIFY, "Ripple: at least", "dB", 0.01, 6.0, 2,
          "A passband ripple at least this large (and the next factor times the scatter) gives the word "
          "'ripple (Chebyshev-like)'."),
    Field("ripple_scatter", 6.0, CLASSIFY, "Ripple: scatter times", "×", 1.0, 50.0, 1,
          "The ripple must also be at least this many times the scatter, so that noise is not read as ripple."),
    Field("peaking_db", 1.0, CLASSIFY, "Peaking: at least", "dB", 0.1, 20.0, 1,
          "A peak this far over a flat level on the passband's side of a cut-off gives the word 'peaking'."),
    Field("gain_db", 1.0, CLASSIFY, "Gain: more than", "dB", 0.1, 20.0, 1,
          "A flat level further than this from 0 dB gives the word 'gain' or 'loss'."),
    Field("min_stop_db", 10.0, CLASSIFY, "Stopband seen: at least", "dB", 1.0, 100.0, 1,
          "A low-pass, high-pass or band-pass with less stopband than this below its level loses the "
          "'little stopband' weight."),
    Field("span_dec", 1.0, CLASSIFY, "Short span: under", "dec", 0.1, 5.0, 2,
          "A sweep (without its noise ends) narrower than this is refused when no resonance lies whole "
          "inside it, and otherwise loses the 'short span' weight (not a crystal-like one)."),
    Field("noise_share", 0.5, CLASSIFY, "Refuse: noise ends over", "share", 0.05, 1.0, 2,
          "Not classified when the noise ends cover more than this share of the usable points."),
    Field("scatter_db", 1.0, CLASSIFY, "Refuse: scatter over", "dB", 0.05, 10.0, 2,
          "Not classified when the scatter near the level (the noise, from the second differences that "
          "change sign against both neighbours) is more than this."),
    Field("scatter_warn", 0.3, CLASSIFY, "Scatter: weight over", "dB", 0.01, 10.0, 2,
          "A scatter near the level over this loses the 'scatter' weight."),
    Field("point_flag_share", 0.3, CLASSIFY, "Refuse: flagged points over", "share", 0.0, 1.0, 2,
          "Not classified when more than this share of the points carry a flag that marks a single point "
          "(clipped, for example); a flag on the whole sweep never refuses."),
    Field("min_score", 40, CLASSIFY, "Refuse: score under", "%", 0, 100, 0,
          "A type whose confidence comes out under this is not given: 'Not classified', with the reasons."),
    # Score weights (design section 3.4): each reason that holds subtracts its weight from 100 %
    Field("w_wide_flag", 10, WEIGHTS, "Flag on the whole sweep", "%", 0, 100, 0,
          "Subtracted when a flag marks every point (skew unchecked)."),
    Field("w_short_passband", 20, WEIGHTS, "Short passband at an end", "%", 0, 100, 0,
          "Subtracted when a passband at an end of the sweep spans less than the short-passband width."),
    Field("w_limit", 10, WEIGHTS, "Order only a limit", "%", 0, 100, 0,
          "Subtracted when a roll-off's order is only a limit (≥)."),
    Field("w_from_peak", 15, WEIGHTS, "Type read from a peak", "%", 0, 100, 0,
          "Subtracted when a low-pass or high-pass is read from a peak, or its passband was never seen flat."),
    Field("w_noise_end", 5, WEIGHTS, "Each noise end", "%", 0, 100, 0,
          "Subtracted for each end of the sweep that lies in noise."),
    Field("w_scatter", 10, WEIGHTS, "Scatter", "%", 0, 100, 0,
          "Subtracted when the scatter near the level is over its weight limit."),
    Field("w_no_phase", 30, WEIGHTS, "Flat without phase", "%", 0, 100, 0,
          "Subtracted from a flat type when the phase was not measured: an all-pass looks the same."),
    Field("w_few_points", 15, WEIGHTS, "Too few points on a resonance", "%", 0, 100, 0,
          "Subtracted when a resonance the type rests on (crystal-like, a band-pass from a peak) has too few "
          "points across it."),
    Field("w_little_stop", 20, WEIGHTS, "Little stopband seen", "%", 0, 100, 0,
          "Subtracted when a low-pass, high-pass or band-pass shows less stopband than the stopband limit."),
    Field("w_short_span", 30, WEIGHTS, "Sweep under the short span", "%", 0, 100, 0,
          "Subtracted when the sweep spans less than the short span (not for crystal-like)."),
)
_BY_KEY = {f.key: f for f in FIELDS}


def _whole(f: Field) -> bool:
    return f.decimals == 0


AnalysisSettings = dataclasses.make_dataclass(
    "AnalysisSettings",
    [(f.key, int if _whole(f) else float, dataclasses.field(default=int(f.default) if _whole(f) else float(f.default)))
     for f in FIELDS],
    frozen=True, module=__name__)
AnalysisSettings.__doc__ = "Every number of the analysis; the defaults are FIELDS'."
DEFAULTS = AnalysisSettings()


def clean(stored) -> dict:
    """The stored values that count: known keys only, numbers only, limited to their range,
    whole numbers rounded."""
    out: dict = {}
    if not isinstance(stored, dict):
        return out
    for key, v in stored.items():
        f = _BY_KEY.get(key)
        if f is None or isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            continue
        v = min(max(float(v), f.lo), f.hi)
        out[key] = int(round(v)) if _whole(f) else v
    return out


def from_stored(stored) -> "AnalysisSettings":
    """The settings for a stored dict of the values that differ from the defaults."""
    return dataclasses.replace(DEFAULTS, **clean(stored))


def to_stored(s: "AnalysisSettings") -> dict:
    """Only what differs from the defaults, as it is stored."""
    return {f.key: getattr(s, f.key) for f in FIELDS if getattr(s, f.key) != getattr(DEFAULTS, f.key)}


def field(key: str) -> Field:
    return _BY_KEY[key]
