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
PRINT_MARKER = "#444444"        # marker lines, dots and labels


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
        row = 0
        for mk in markers or []:
            ax.axvline(mk.freq, color=PRINT_MARKER, linewidth=0.7, linestyle="--")
            y = mk.y_gain if key == "gain" else mk.y_phase
            if y is not None:
                ax.plot([mk.freq], [y], "D", color=PRINT_MARKER, markersize=4)
            if mk.label_on != key or not mk.text:
                continue
            # labels are staggered by rows so that neighbours do not sit on each other
            if y is None:
                ax.annotate(mk.text, xy=(mk.freq, 1.0), xycoords=("data", "axes fraction"),
                            xytext=(4, -4 - 9 * row), textcoords="offset points", va="top",
                            fontsize=7, color=PRINT_MARKER)
            else:
                ax.annotate(mk.text, xy=(mk.freq, y), xytext=(4, 4 + 9 * row), textcoords="offset points",
                            va="bottom", fontsize=7, color=PRINT_MARKER)
            row = (row + mk.text.count("\n") + 1) % 6
        ax.set_ylabel(label)
        ax.grid(True, which="both", linewidth=0.4, alpha=0.6)
        if opts.log_x:
            ax.set_xscale("log")
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
    fig.savefig(path, dpi=opts.dpi)
    plt.close(fig)
    return path


def _g(x) -> str:
    try:
        return "%g" % float(x)
    except (TypeError, ValueError):
        return "?"
