"""PNG / SVG / PDF export with matplotlib (SPEC.md section 12).

Gain and phase subplots matching the current view: wrap state, axis type, flagged
points, markers. Title, plus a footer with the date and key settings.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from pathlib import Path

import numpy as np

from ..measure.sinefit import unwrap_deg
from ..models import Flag, SweepResult
from .export_csv import describe_correction

FORMATS = ("png", "svg", "pdf")
QUIET = Flag.REMEASURED | Flag.BUILTIN | Flag.PREVIEW | Flag.CALIBRATED    # as gui/bode_plot.py QUIET


# Series colours on the white background of an exported image, by colour slot (the same
# hues as the app's dark theme, darkened for print). The one place outside gui/theme.py
# that may hard-code colours.
PRINT_SERIES = ("#2a78d6", "#c2410c", "#0f8a5f", "#a16207", "#be3a6f", "#15803d", "#6d5bd0", "#c0392b")
PRINT_MUTED = "#777777"
PRINT_FLAGGED = "#d62728"
PRINT_MARKER = "#444444"        # marker labels, and a marker with no colour of its own
# The marker palette on white, by the names of gui/theme.py MARKER_PALETTE (a test keeps the two in
# step): the same hues, darkened for print.
PRINT_MARKERS = {
    "Grey": "#444444", "White": "#111111", "Red": "#bc4945", "Deep red": "#8d1a1e", "Orange": "#af5b0b",
    "Deep orange": "#753b07", "Amber": "#926e10", "Deep amber": "#624902", "Lime": "#628202", "Deep lime":
    "#405601", "Green": "#098b47", "Deep green": "#015d2d", "Teal": "#038586", "Deep teal": "#055959",
    "Sky": "#0d7cb6", "Deep sky": "#03527b", "Violet": "#7c5ec2", "Deep violet": "#553494", "Pink":
    "#af4a88", "Deep pink": "#811e5f"}


@dataclass
class ImageOptions:
    title: str = "Bode plot"
    dpi: int = 150
    width_in: float = 8.0
    height_in: float = 6.0
    unwrap: bool = False
    log_x: bool = True
    show_phase: bool = True
    unit: str = "db"            # vertical unit of the upper plot, as in the GUI: "db" | "v" | "pct"


@dataclass
class ImageSeries:
    """One trace as the plot shows it: the numbers are final (unit, unwrap, relative)."""
    name: str
    slot: int | None            # colour slot as on screen; None: muted
    freqs: Any                  # numpy arrays of equal length
    gain: Any
    phase: Any
    flagged: Any = None         # bool array (a measured trace: markers); None: a line only


@dataclass
class ImageMarker:
    """One marker as the plot shows it: a line through both plots, a dot where it has a
    value, its text on one of them."""
    freq: float
    text: str
    y_gain: Any = None          # None: no dot on the gain plot
    y_phase: Any = None
    label_on: str = "gain"      # the plot that carries the text: "gain" | "phase"
    left: bool = False          # the text goes to the left of the dot (the curve rises to the right)
    color: str = "Grey"         # the palette name of its line and dot (PRINT_MARKERS)


# unit -> (axis label, value of a point); the same three as gui/bode_plot.py UNITS
UNITS = {"db": ("Gain (dB)", lambda p: p.gain_db),
         "v": ("Output (Vpp)", lambda p: 2.0 * p.vdut_amp),
         "pct": ("Output / input (%)", lambda p: 100.0 * abs(p.h))}


def write_image(path, result: SweepResult, opts: ImageOptions | None = None,
                series: list[ImageSeries] | None = None, labels: tuple[str, str, str] | None = None,
                markers: list[ImageMarker] | None = None) -> Path:
    """The Bode plot as an image. Without `series` it draws the sweep of `result` (as it
    always did). With `series` (BodePlot.export_series) it draws exactly what the plot
    shows: every visible trace, absolute or relative, with `labels` = (gain axis, phase
    axis, note for the footer). `markers` (BodePlot.export_markers) are drawn on top."""
    import matplotlib
    matplotlib.use("Agg")               # no display needed
    import matplotlib.pyplot as plt

    opts = opts or ImageOptions()
    path = Path(path)
    if path.suffix.lower().lstrip(".") not in FORMATS:
        raise ValueError("unsupported image format %r (use png, svg or pdf)" % path.suffix)
    if series is None:
        pts = sorted(result.points, key=lambda p: p.freq_hz)
        gain_label, value = UNITS.get(opts.unit, UNITS["db"])
        phase = np.array([p.phase_deg for p in pts])
        if opts.unwrap and len(pts):
            phase = unwrap_deg(phase)
        series = [ImageSeries("Sweep", 0, np.array([p.freq_hz for p in pts]), np.array([value(p) for p in pts]),
                              phase, np.array([bool(p.flags & ~QUIET) for p in pts], dtype=bool))]
        labels = (gain_label, "Phase (deg)", "")
    gain_label, phase_label, note = labels or ("Gain (dB)", "Phase (deg)", "")
    named = len(series) > 1

    rows = 2 if opts.show_phase else 1
    fig, axes = plt.subplots(rows, 1, sharex=True, figsize=(opts.width_in, opts.height_in))
    axes = np.atleast_1d(axes)
    any_flagged = False
    labels_to_place = []                # per plot: the marker texts, written once the layout is final
    for ax, key, label in zip(axes, ("gain", "phase"), (gain_label, phase_label)):
        for s in series:
            colour = PRINT_SERIES[s.slot] if s.slot is not None and s.slot < len(PRINT_SERIES) else PRINT_MUTED
            f, y = np.asarray(s.freqs, dtype=float), np.asarray(getattr(s, key), dtype=float)
            ax.plot(f, y, "-", color=colour, linewidth=1.2, label=s.name if named and ax is axes[0] else None)
            if s.flagged is None or not len(f):
                continue
            bad = np.asarray(s.flagged, dtype=bool)
            ax.plot(f[~bad], y[~bad], "o", color=colour, markersize=3)
            if bad.any():
                ax.plot(f[bad], y[bad], "x", color=PRINT_FLAGGED, markersize=6,
                        label="flagged" if ax is axes[0] and not any_flagged else None)
                any_flagged = True
        ax.set_ylabel(label)
        ax.grid(True, which="both", linewidth=0.4, alpha=0.6)
        if opts.log_x:
            ax.set_xscale("log")
    for ax, key in zip(axes, ("gain", "phase")):
        texts = []
        xlim = ax.get_xlim()            # the curves have set the frequency axis; a marker never widens it,
        for mk in (markers or []):      # and one beyond it is left out (on screen Fit view ignores markers too)
            if not (min(xlim) <= mk.freq <= max(xlim)):
                continue
            ink = PRINT_MARKERS.get(mk.color, PRINT_MARKER)
            ax.axvline(mk.freq, color=ink, linewidth=0.7, linestyle="--")
            y = mk.y_gain if key == "gain" else mk.y_phase
            if y is not None:
                ax.plot([mk.freq], [y], "D", color=ink, markersize=4)
            if mk.label_on == key and mk.text:
                texts.append((mk, y))
        if markers:
            ax.set_xlim(xlim)
        labels_to_place.append((ax, texts))
    if named or any_flagged:
        axes[0].legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("Frequency (Hz)")
    axes[0].set_title(opts.title)
    sw = result.config.get("sweep", {})
    st = result.config.get("stimulus", {})
    footer = "%s   %s to %s Hz   %s Vpp   %s%s%s%s" % (
        str(result.meta.get("finished", ""))[:19], _g(sw.get("start_hz")), _g(sw.get("stop_hz")),
        _g(st.get("amp_vpp")), describe_correction(result.meta),
        "   phase unwrapped" if opts.unwrap else "",
        "   " + note if note else "",
        "   ABORTED (partial)" if result.meta.get("aborted") else "")
    if not result.points:               # no live sweep (only loaded or theory traces): nothing to describe
        footer = note
    fig.text(0.01, 0.005, footer, fontsize=7, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    for ax, texts in labels_to_place:
        _place_labels(ax, texts)
    fig.savefig(path, dpi=opts.dpi)
    plt.close(fig)
    return path


def _place_labels(ax, items) -> list:
    """Write the marker texts of one plot: next to the dot (at the top of the plot for a
    marker with no value), on the side that is free of the curve, moved down (up, or to the
    other side, when the plot ends there) until no text covers another or the legend, and
    kept inside the plot. items: (ImageMarker, y or None). Returns the
    boxes of the texts in pixels. Called when the layout of the figure is final."""
    fig = ax.figure
    renderer = fig.canvas.get_renderer()
    area = ax.get_window_extent(renderer)
    pt = 72.0 / fig.dpi                 # points per pixel
    taken = []
    legend = ax.get_legend()
    keep_clear = [legend.get_window_extent(renderer)] if legend is not None and items else []
    for mk, y in sorted(items, key=lambda it: it[0].freq):
        xy, coords = ((mk.freq, 1.0), ("data", "axes fraction")) if y is None else ((mk.freq, y), "data")
        ann = ax.annotate(mk.text, xy=xy, xycoords=coords, xytext=(4, 4), textcoords="offset points",
                          va="bottom", ha="left", fontsize=7, color=PRINT_MARKER, annotation_clip=False,
                          bbox=dict(facecolor="white", alpha=0.75, edgecolor="none", pad=0.8))

        def put(left: bool, down_px: float, ann=ann):
            ann.set_ha("right" if left else "left")
            ann.xyann = (-4 if left else 4, 4 - down_px * pt)
            return ann.get_window_extent(renderer)
        left = mk.left
        box = put(left, 0.0)
        if (box.x0 < area.x0) if left else (box.x1 > area.x1):      # no room on that side
            left = not left
            box = put(left, 0.0)
        start = box.y1 - area.y1 if box.y1 > area.y1 else min(0.0, box.y0 - area.y0)

        def free(side: bool):
            """The nearest free place on that side, downwards or else upwards; None: there is none."""
            for step in (1.0, -1.0):
                down = start
                for _ in range(40):
                    b = put(side, down)
                    if b.y0 < area.y0 - 0.5 or b.y1 > area.y1 + 0.5:
                        break
                    if side != left and (b.x0 < area.x0 or b.x1 > area.x1):
                        break
                    if not any(b.overlaps(t) for t in taken + keep_clear):
                        return b
                    down += step * (b.height + 2.0)
            return None
        # a label that covers another one stays where it was first put only when the plot is full
        box = free(left) or free(not left) or put(left, start)
        taken.append(box)
    return taken


def _g(x) -> str:
    try:
        return "%g" % float(x)
    except (TypeError, ValueError):
        return "?"
