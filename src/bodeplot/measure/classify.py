"""Classification (v3, part 3): what kind of circuit one response is, read from part 1's
Metrics. No Qt.

Design: docs/superpowers/specs/2026-11-02-classification-design.md, section 3. A type, a few
shape words, a confidence in percent with the reasons that took it down, or a refusal when the
sweep cannot carry a type. Every threshold and weight is a field of AnalysisSettings.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from ..units import fmt_si
from .analysis_settings import DEFAULTS, AnalysisSettings
from .metrics import EPS, SIGMA_OF_D2, Cutoff, Metrics, Resonance, without_noise
from .response import Curve

# What is left here is arithmetic, not a choice.
FULL = 100                      # the score before any reason, and a share in percent
FREQ_DIGITS = 4                 # digits of a frequency in the shape words
Q_DIGITS = 2                    # significant digits of a Q

NOT_CLASSIFIED = "Not classified"
CRYSTAL, FLAT, ALL_PASS, UNKNOWN = "Crystal-like", "Flat", "All-pass", "Unknown"
LOW_PASS, HIGH_PASS, BAND_PASS, BAND_STOP, SHELF = "Low-pass", "High-pass", "Band-pass", "Band-stop", "Shelf"
ROLLING = (LOW_PASS, HIGH_PASS, BAND_PASS)          # the types whose roll-offs have an order and a stopband
KINDS = (LOW_PASS, HIGH_PASS, BAND_PASS, BAND_STOP, ALL_PASS, FLAT, SHELF, CRYSTAL, UNKNOWN)


@dataclass
class Classification:
    kind: str                                   # one of KINDS, or NOT_CLASSIFIED
    words: list[str] = field(default_factory=list)
    score: int | None = None                    # percent; None: refused before a type was tried
    reasons: list[tuple[str, int]] = field(default_factory=list)    # (a sentence, the percent it costs)
    refused: str = ""                           # why there is no type, a sentence; "": classified


def _hz(f: float) -> str:
    return fmt_si(f, "Hz", FREQ_DIGITS)


def _db(v: float) -> str:
    """A level change with its sign, the minus a real one."""
    return ("%+.1f dB" % (round(v, 1) + 0.0)).replace("-", "−")


def _q(q: float) -> str:
    return "%g" % float("%.*g" % (Q_DIGITS, q))


def _refuse(why: str, score: int | None = None, reasons=None) -> Classification:
    return Classification(NOT_CLASSIFIED, [], score, list(reasons or []), "%s: %s." % (NOT_CLASSIFIED, why))


def scatter(m: Metrics, c: Curve, s: AnalysisSettings = DEFAULTS) -> float:
    """The noise near the level (design section 3): over the usable points outside the noise ends
    within floor_db of the level, the second differences that change sign against both neighbours
    (noise does, a bend keeps its sign), their median as a sigma; 0 with fewer than noise_points."""
    if not m.ok or m.level is None:
        return 0.0
    c = without_noise(c, m.noise)
    near = [ok and abs(v - m.level) <= s.floor_db for ok, v in zip(c.ok, c.db)]
    d2 = {j: c.db[j - 1] - 2 * c.db[j] + c.db[j + 1] for j in range(1, len(c.f) - 1)
          if near[j - 1] and near[j] and near[j + 1]}
    noise = [abs(v) for j, v in d2.items() if j - 1 in d2 and j + 1 in d2 and v * d2[j - 1] < 0 and v * d2[j + 1] < 0]
    return SIGMA_OF_D2 * statistics.median(noise) if len(noise) >= s.noise_points else 0.0


# ---- the type (section 3.2)
@dataclass
class _Read:
    kind: str
    words: list[str] = field(default_factory=list)
    reasons: list[tuple[str, int]] = field(default_factory=list)
    on: list[Resonance] = field(default_factory=list)       # the resonances the type rests on
    top: tuple[float, int] | None = None                    # a band-pass from a peak: its top, the points across it


def _crystal(m: Metrics, s: AnalysisSettings) -> _Read | None:
    for p in (r for r in m.resonances if r.kind == "peak"):
        for n in (r for r in m.resonances if r.kind == "notch"):
            if (p.f0 < n.f0 < s.crystal_ratio * p.f0 and p.q_width is not None and n.q_width is not None
                    and p.q_width >= s.crystal_q and n.q_width >= s.crystal_q):
                return _Read(CRYSTAL, ["fs " + _hz(p.f0), "fp " + _hz(n.f0)], on=[p, n])
    return None


def _falls(m: Metrics, c: Curve) -> tuple[float, float]:
    """How far the gain falls from the highest point to the lowest one below and above it."""
    idx = c.usable()
    top = max(idx, key=lambda i: c.db[i])
    below = [c.db[i] for i in idx if i < top]
    above = [c.db[i] for i in idx if i > top]
    return (c.db[top] - min(below) if below else 0.0), (c.db[top] - min(above) if above else 0.0)


def _beyond(c: Curve, cut: Cutoff) -> list[float]:
    """The gains of the usable points beyond a cut-off, away from its passband."""
    return [c.db[i] for i in c.usable() if (c.f[i] > cut.f if cut.side == "high" else c.f[i] < cut.f)]


def _type(m: Metrics, c: Curve, phase: bool, s: AnalysisSettings) -> _Read:
    """The first of the nine rules of section 3.2 that fits. c: without its noise ends."""
    flat = m.source == "flat"
    sides = [k.side for k in m.cutoffs]
    peaks = [r for r in m.resonances if r.kind == "peak"]
    notches = [r for r in m.resonances if r.kind == "notch"]
    passes = [b for b in m.bands if b.kind == "pass"]
    from_peak = ("No flat passband: the type is read from the highest gain.", s.w_from_peak)

    crystal = _crystal(m, s)
    if crystal is not None:
        return crystal
    if flat and not m.cutoffs and not any(r.height >= s.drop_db for r in m.resonances):
        if not phase:
            return _Read(FLAT, reasons=[("Phase not measured: an all-pass looks the same.", s.w_no_phase)])
        deg = [c.deg[i] for i in c.usable()]
        return _Read(ALL_PASS if max(deg) - min(deg) >= s.allpass_deg else FLAT)
    tall = [r for r in peaks if r.height >= s.notch_db]
    if not flat and len(tall) >= 2:
        return _Read(UNKNOWN, on=tall)
    if notches and any(k.slope is None and k.attenuation is not None and k.attenuation.v < s.drop_db
                       for k in m.cutoffs):
        return _Read(BAND_STOP, on=notches)
    if not flat and sides == ["low", "high"]:
        low, high = _falls(m, c)
        if (low >= s.notch_db) != (high >= s.notch_db):
            return _Read(LOW_PASS if low < s.notch_db else HIGH_PASS, ["peaking"],
                         [("Passband not seen flat: the type is read from a peak.", s.w_from_peak)])
    if sides and len(set(sides)) == 1:
        kind = LOW_PASS if sides[0] == "high" else HIGH_PASS
        edge = max(k.f for k in m.cutoffs) if kind == LOW_PASS else min(k.f for k in m.cutoffs)
        for b in m.bands:
            step = m.level - b.level
            if b.kind != "pass" and (b.lo > edge if kind == LOW_PASS else b.hi < edge) and s.shelf_lo <= step < s.shelf_hi:
                words = [("high" if kind == LOW_PASS else "low") + "-frequency step " + _db(-step)]
                return _Read(SHELF, words + ["notch at " + _hz(r.f0) for r in notches])
        return _Read(kind, reasons=[] if flat else [from_peak])
    if sides == ["low", "high"]:
        if flat:
            return _Read(BAND_PASS)
        lo, hi = m.cutoffs                              # from a peak: the points of its -3 dB width
        return _Read(BAND_PASS, top=(math.sqrt(lo.f * hi.f), sum(1 for i in c.usable() if lo.f < c.f[i] < hi.f)))
    if sides == ["high", "low"] and (len(passes) >= 2 or any(r.height >= s.notch_db for r in notches)):
        return _Read(BAND_STOP, on=[max(notches, key=lambda r: r.height)] if notches else [])
    return _Read(UNKNOWN)


# ---- shape words (section 3.3) and the reasons of the score (section 3.4)
def _words(r: _Read, m: Metrics, sc: float, s: AnalysisSettings) -> list[str]:
    if r.kind in (CRYSTAL, NOT_CLASSIFIED):
        return r.words
    if r.kind == UNKNOWN:
        return ["%s at %s" % (x.kind, _hz(x.f0)) for x in m.resonances]
    out = list(r.words)
    if r.kind in ROLLING:
        orders = [k.order for k in m.cutoffs if k.order is not None]
        texts = [("≥ " if o.limit else "") + "%d" % o.v for o in orders]
        if len(texts) == 1:
            out.append("order " + texts[0])
        elif len(texts) == 2:
            out.append("order %s below, %s above" % tuple(texts))
    peaking = "peaking" in out
    if r.kind in ROLLING and m.source == "flat":
        for p in (x for x in m.resonances if x.kind == "peak"):
            inside = all(p.f0 < k.f if k.side == "high" else p.f0 > k.f for k in m.cutoffs)
            if inside and p.db - m.level >= s.peaking_db:
                out.append("peaking " + _db(p.db - m.level))
                peaking = True
                break
    if (m.ripple is not None and not peaking and m.ripple >= s.ripple_db - EPS
            and m.ripple >= s.ripple_scatter * sc):
        out.append("ripple %.1f dB (Chebyshev-like)" % m.ripple)
    if r.kind in ROLLING and any(k.slope is None and k.attenuation is not None for k in m.cutoffs):
        out.append("stopband notches (elliptic-like)")
    if r.kind in (BAND_PASS, BAND_STOP) and m.q is not None:
        out.append("Q " + _q(m.q))
    if m.source == "flat" and abs(m.level) > s.gain_db:
        out.append(("gain " if m.level > 0 else "loss ") + _db(m.level))
    return out


def _reasons(r: _Read, m: Metrics, c: Curve, clean: Curve, sc: float, span: float,
             s: AnalysisSettings) -> list[tuple[str, int]]:
    out = []
    for name in c.wide_flags:
        out.append(("%s on every point: the numbers that need it are uncertain." % name.capitalize(), s.w_wide_flag))
    idx = c.usable()
    share = sum(1 for i in idx if c.point_flagged and c.point_flagged[i]) / len(idx)
    if round(FULL * share):
        out.append(("%.0f %% of the points carry a flag." % (FULL * share), round(FULL * share)))
    for b in m.bands:
        if b.kind == "pass" and m.cutoffs and (b.at_low or b.at_high) and math.log10(b.hi / b.lo) < s.short_decades:
            out.append(("The passband runs to the %s end of the sweep and spans less than %g decade."
                        % ("low" if b.at_low else "high", s.short_decades), s.w_short_passband))
            break
    if r.kind in ROLLING and any(k.order is not None and k.order.limit for k in m.cutoffs):
        out.append(("An order is only a limit (≥).", s.w_limit))
    out += r.reasons
    for n in m.noise:
        out.append(("The %s end of the sweep is lost in the noise." % ("low" if n.at_low else "high"), s.w_noise_end))
    if sc > s.scatter_warn:
        out.append(("The scatter near the level is %.2f dB: the numbers are uncertain." % sc, s.w_scatter))
    few = [(x.kind, x.f0) for x in r.on if x.points < s.few_points]
    if r.top is not None and r.top[1] < s.few_points:
        few.append(("peak", r.top[0]))
    if few:
        out.append(("Too few points on the %s at %s." % (few[0][0], _hz(few[0][1])), s.w_few_points))
    if r.kind in ROLLING and any(m.level - min(_beyond(clean, k), default=m.level) < s.min_stop_db
                                 for k in m.cutoffs):
        out.append(("Less than %g dB of stopband seen." % s.min_stop_db, s.w_little_stop))
    if r.kind != CRYSTAL and span < s.span_dec - EPS:
        out.append(("The sweep spans less than %g decade." % s.span_dec, s.w_short_span))
    return [(text, amount) for text, amount in out if amount]


def classify(m: Metrics, c: Curve, phase: bool = True, s: AnalysisSettings = DEFAULTS) -> Classification:
    """The type of the curve c whose metrics are m (analyse(c, phase, s)). phase False: a
    magnitude-only measurement."""
    if not m.ok:                                                        # 3.1, in its order
        return _refuse(m.reason)
    idx = c.usable()
    noisy = sum(1 for i in idx if any(n.first <= i <= n.last for n in m.noise))
    if noisy > s.noise_share * len(idx):
        return _refuse("the noise ends cover %.0f %% of the points" % (FULL * noisy / len(idx)))
    sc = scatter(m, c, s)
    if sc > s.scatter_db:
        return _refuse("the scatter near the level is %.2f dB, more than %g dB" % (sc, s.scatter_db))
    flagged = sum(1 for i in idx if c.point_flagged and c.point_flagged[i]) / len(idx)
    if flagged > s.point_flag_share:
        return _refuse("%.0f %% of the points carry a flag" % (FULL * flagged))
    clean = without_noise(c, m.noise)
    kept = clean.usable()
    span = math.log10(clean.f[kept[-1]] / clean.f[kept[0]])
    if span < s.span_dec - EPS and not any(r.q_width is not None for r in m.resonances):
        return _refuse("the sweep spans less than %g decade and holds no whole resonance" % s.span_dec)
    r = _type(m, clean, phase, s)
    reasons = _reasons(r, m, c, clean, sc, span, s)
    score = max(0, FULL - sum(amount for _text, amount in reasons))
    if score < s.min_score:
        return _refuse("the confidence is %d %%, under %d %%" % (score, s.min_score), score, reasons)
    return Classification(r.kind, _words(r, m, sc, s), score, reasons)
