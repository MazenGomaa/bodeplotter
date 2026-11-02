"""The Analysis table (SPEC.md section 10): the numbers of measure/metrics.py as rows of
text, for one trace or for two side by side with their difference, the notes under the
table and the clipboard text. No Qt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .measure.analysis_settings import DEFAULTS, AnalysisSettings
from .measure.metrics import DB_PER_ORDER, Metrics, Resonance
from .units import fmt_si

AT_LEAST = "≥ "                 # a lower limit: the sweep ends before the number has settled
FLAG = " (flagged)"
NONE = "none"


def _n(v: float) -> str:
    return "%g" % round(v, 3)


def group_tips(s: AnalysisSettings = DEFAULTS) -> dict[str, str]:
    """The groups of the table in their order: title -> the rule behind its numbers (the
    tooltip), with the numbers of the settings in force."""
    return {
        "Passband": "The flat part of the trace: a stretch of at least %s decade where the gain changes by no more "
                    "than %s dB per decade (from ... to: where it lies). Level: its typical gain. Ripple: how far the "
                    "gain moves between the cut-offs, a hump included. Without a flat stretch the level is the "
                    "highest gain." % (_n(s.flat_span), _n(s.flat_slope)),
        "Cut-off": "Where the gain has fallen %s dB below the passband level, found between two measured points. "
                   "One cut-off is fc; two are fL and fH." % _n(s.drop_db),
        "Band": "From the two cut-offs: the centre is the geometric mean of fL and fH, the bandwidth their "
                "difference, and Q the centre divided by the bandwidth.",
        "Roll-off": "How fast the gain falls beyond a cut-off: the slope the curve settles to, in dB per decade, and "
                    "the filter order that goes with it (%s dB per decade for each order). '≥': at least this "
                    "steep; the sweep ends, or the stop band's floor comes, before the slope has settled."
                    % _n(DB_PER_ORDER),
        "Stopband": "How far below the passband level the trace stays beyond a cut-off. A plain number when the "
                    "trace levels off there; '≥' (at least) when it is still falling. Beyond a notch: down to the "
                    "highest gain that comes back after it (the worst case); the notch's own depth is in its Notch "
                    "group. No row when another passband follows the notch.",
        "Peak": "A resonance: a peak that stands at least %s dB clear of the trace on both sides. Q (width): f0 "
                "divided by the width %s dB below its top. Q (phase): from how fast the phase turns across it. "
                "Points: how many measured points lie on it; with fewer than %d its numbers are uncertain."
                % (_n(s.prominence_db), _n(s.drop_db), s.few_points),
        "Notch": "A resonance: a notch that stands at least %s dB clear of the trace on both sides. Q (width): f0 "
                 "divided by the width %s dB below its shoulder. Points: how many measured points lie in it; with "
                 "fewer than %d its numbers are uncertain." % (_n(s.prominence_db), _n(s.drop_db), s.few_points),
    }


GROUPS = group_tips()           # the order of the groups, and their tips with the default settings


@dataclass
class Cell:
    text: str = ""
    number: float | None = None     # None: nothing to take a difference of
    kind: str = ""                  # "hz" | "ratio" | "db" | "span" | "slope" | "count"
    limit: bool = False


@dataclass
class Row:
    group: str                  # the title of its group: "Passband", "Peak at 15.92 kHz" ...
    name: str
    value: str = ""
    compare: str = ""
    diff: str = ""
    tip: str = ""


def hz(f: float) -> str:
    return fmt_si(f, "Hz", 4)


def _signed(v: float, digits: int, unit: str) -> str:
    """A number with its sign; a value that rounds to zero reads +0, never -0."""
    return "%+.*f %s" % (digits, round(v, digits) + 0.0, unit)


def _cell(kind: str, number: float, limit: bool = False, flagged: bool = False) -> Cell:
    text = {"hz": hz, "ratio": lambda v: "%.3g" % v, "db": lambda v: _signed(v, 2, "dB"),
            "span": lambda v: "%.2f dB" % v, "slope": lambda v: _signed(v, 1, "dB/dec"),
            "count": lambda v: "%d" % v}[kind](number)
    return Cell((AT_LEAST if limit else "") + text + (FLAG if flagged else ""), number, kind, limit)


def _diff(a: Cell | None, b: Cell | None) -> str:
    """The value against the compared one: frequencies and Q in percent of the compared
    value, everything in dB as a plain difference. Nothing where one side is missing or
    only a limit."""
    if a is None or b is None or a.number is None or b.number is None or a.limit or b.limit:
        return ""
    if a.kind in ("hz", "ratio"):
        return _signed(100.0 * (a.number - b.number) / b.number, 1, "%") if b.number else ""
    if a.kind in ("db", "span"):
        return _signed(a.number - b.number, 2, "dB")
    if a.kind == "slope":
        return _signed(a.number - b.number, 1, "dB/dec")
    return "%+d" % (a.number - b.number) if a.number != b.number else "0"


def cut_names(m: Metrics) -> list[str]:
    n = len(m.cutoffs)
    return ["fc"] if n == 1 else ["fL", "fH"] if n == 2 else ["f%d" % k for k in range(1, n + 1)]


def _entries(m: Metrics | None) -> list[tuple[tuple, str, str, Cell]]:
    """Everything but the resonances: (key, group, row name, cell). Rows of two traces with
    the same key stand side by side."""
    out: list[tuple[tuple, str, str, Cell]] = []
    if m is None or not m.ok:
        return out
    out.append((("level",), "Passband", "Level" if m.source == "flat" else "Level (peak)",
                _cell("db", m.level, flagged=m.level_flagged)))
    if m.ripple is not None:
        out.append((("ripple",), "Passband", "Ripple", _cell("span", m.ripple)))
    passes = [b for b in m.bands if b.kind == "pass"]
    for n, b in enumerate(passes, 1):                   # where the flat stretch lies, as two frequencies
        tail = "" if len(passes) == 1 else " %d" % n
        out.append((("flat from", n), "Passband", "Flat from" + tail, _cell("hz", b.lo)))
        out.append((("flat to", n), "Passband", "Flat to" + tail, _cell("hz", b.hi)))
    named = list(zip(cut_names(m), m.cutoffs))
    for name, cut in named:
        out.append((("cut", name), "Cut-off", name, _cell("hz", cut.f, flagged=cut.flagged)))
    if m.pair is not None:
        out.append((("centre",), "Band", "Centre", _cell("hz", m.centre)))
        out.append((("bandwidth",), "Band", "Bandwidth", _cell("hz", m.bandwidth)))
        out.append((("q",), "Band", "Q", _cell("ratio", m.q)))
    for name, cut in named:
        if cut.slope is not None:
            out.append((("slope", name), "Roll-off", "Slope, %s" % name,
                        _cell("slope", cut.slope.v, cut.slope.limit, cut.slope.flagged)))
            out.append((("order", name), "Roll-off", "Order, %s" % name,
                        _cell("count", cut.order.v, cut.order.limit)))
    for name, cut in named:
        if cut.attenuation is not None:
            out.append((("attenuation", name), "Stopband", "Beyond %s" % name,
                        _cell("span", cut.attenuation.v, cut.attenuation.limit, cut.attenuation.flagged)))
    return out


def _resonance(r: Resonance, phase: bool) -> list[tuple[str, Cell]]:
    out = [("f0", _cell("hz", r.f0, flagged=r.flagged)),
           ("Gain at f0", _cell("db", r.db)),
           ("Height" if r.kind == "peak" else "Depth", _cell("span", r.height)),
           ("Q (width)", _cell("ratio", r.q_width) if r.q_width is not None else Cell(NONE))]
    if r.kind == "peak" and phase:
        out.append(("Q (phase)", _cell("ratio", r.q_phase) if r.q_phase is not None else Cell(NONE)))
    out.append(("Points", Cell("%d" % r.points)))
    return out


def _pairs(a: list[Resonance], b: list[Resonance], factor: float) -> list[tuple[Resonance | None, Resonance | None]]:
    """The resonances of two traces side by side: one of the first with the nearest of the
    same kind of the second within factor in frequency; the rest alone. In ascending frequency."""
    free = list(b)
    out: list[tuple[Resonance | None, Resonance | None]] = []
    for r in a:
        near = [o for o in free if o.kind == r.kind and max(o.f0, r.f0) <= factor * min(o.f0, r.f0)]
        other = min(near, key=lambda o: abs(math.log(o.f0 / r.f0))) if near else None
        if other is not None:
            free.remove(other)
        out.append((r, other))
    out += [(None, o) for o in free]
    return sorted(out, key=lambda p: (p[0] or p[1]).f0)


def rows(m: Metrics, other: Metrics | None = None, phase: bool = True, s: AnalysisSettings = DEFAULTS) -> list[Row]:
    """The table for m, with other next to it when given. A quantity only one of the two
    has still gets its row, with the other cell empty."""
    a, b = _entries(m), _entries(other)
    da, db = {e[0]: e for e in a}, {e[0]: e for e in b}
    keys = [e[0] for e in a] + [e[0] for e in b if e[0] not in da]
    tips = group_tips(s)
    order = list(tips)
    out = []
    for key in sorted(keys, key=lambda k: order.index((da.get(k) or db[k])[1])):      # stable: by group only
        ea, eb = da.get(key), db.get(key)
        _key, group, name, _cell_ = ea or eb
        out.append(Row(group, name, ea[3].text if ea else "", eb[3].text if eb else "",
                       _diff(ea[3] if ea else None, eb[3] if eb else None), tips[group]))
    mine = m.resonances if m.ok else []
    theirs = other.resonances if other is not None and other.ok else []
    for ra, rb in _pairs(mine, theirs, s.pair_factor):
        r = ra or rb
        kind = "Peak" if r.kind == "peak" else "Notch"
        group = "%s at %s" % (kind, hz(r.f0))
        ca = dict(_resonance(ra, phase)) if ra else {}
        cb = dict(_resonance(rb, phase)) if rb else {}
        for name, _c in _resonance(r, phase):
            xa, xb = ca.get(name), cb.get(name)
            out.append(Row(group, name, xa.text if xa else "", xb.text if xb else "", _diff(xa, xb), tips[kind]))
    return out


def notes(m: Metrics, s: AnalysisSettings = DEFAULTS) -> list[str]:
    """What the numbers do not say by themselves, one sentence each."""
    if not m.ok:
        return ["No analysis: %s." % m.reason]
    out = []
    if m.source == "peak":
        out.append("No flat stretch: the passband level is the highest gain of the trace.")
    for b in m.bands:
        if b.kind == "pass" and m.cutoffs and (b.at_low or b.at_high) and math.log10(b.hi / b.lo) < s.short_decades:
            span = "a decade" if s.short_decades == 1 else "%s decades" % _n(s.short_decades)
            out.append("The flat part runs to the %s end of the sweep and spans less than %s: the passband "
                       "level, and with it the cut-off, is uncertain; start the sweep %s."
                       % ((("low",) if b.at_low else ("high",)) + (span,) + (("lower",) if b.at_low else ("higher",))))
    if not m.cutoffs:
        out.append("No cut-off inside the sweep.")
    falling = [name for name, cut in zip(cut_names(m), m.cutoffs) if cut.falling]
    if falling:
        out.append("Beyond %s the sweep ends before the stop band levels off." % " and ".join(falling))
    rising = [name for name, cut in zip(cut_names(m), m.cutoffs) if cut.rising]
    if rising:
        out.append("Beyond %s the gain still rises where the sweep ends, past the notch: the stop band may come "
                   "back higher than the sweep shows." % " and ".join(rising))
    for n in m.noise:
        where = ("Below", hz(n.hi)) if n.at_low else ("Above", hz(n.lo))
        out.append("%s %s the gain is lost in the noise (about %.0f dB): that part is left out of the analysis."
                   % (where + (n.level,)))
    for r in m.resonances:
        if r.points < s.few_points:
            out.append("Too few points on the %s at %s (%d): its top and its Q are uncertain; sweep finer "
                       "around it." % (r.kind, hz(r.f0), r.points))
    if m.flagged_share > 0:
        out.append("%.0f %% of the points are flagged; a number that rests on one is marked."
                   % max(1.0, 100.0 * m.flagged_share))
    return out


def table(title: str, table_rows: list[Row], table_notes: list[str], compare: bool = False) -> str:
    """The table as tab-separated text for the clipboard: the title, the column heads, a
    line per group and per row, then the notes."""
    cols = 4 if compare else 2
    lines = [title, "\t".join(("Quantity", "Value", "Compare", "Difference")[:cols])]
    group = None
    for r in table_rows:
        if r.group != group:
            group = r.group
            lines.append(group)
        lines.append("\t".join((r.name, r.value, r.compare, r.diff)[:cols]))
    if table_notes:
        lines.append("")
        lines += table_notes
    return "\n".join(lines) + "\n"
