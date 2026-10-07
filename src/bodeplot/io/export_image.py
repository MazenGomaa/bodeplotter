"""PNG / SVG / PDF export with matplotlib (SPEC.md section 12).

Gain and phase subplots matching the current view: wrap state, axis type, flagged
markers. Title, plus a footer with the date and key settings.
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


# unit -> (axis label, value of a point); the same three as gui/bode_plot.py UNITS
UNITS = {"db": ("Gain (dB)", lambda p: p.gain_db),
         "v": ("Output (Vpp)", lambda p: 2.0 * p.vdut_amp),
         "pct": ("Output / input (%)", lambda p: 100.0 * abs(p.h))}


def write_image(path, result: SweepResult, opts: ImageOptions | None = None) -> Path:
    import matplotlib
    matplotlib.use("Agg")               # no display needed
    import matplotlib.pyplot as plt

    opts = opts or ImageOptions()
    path = Path(path)
    if path.suffix.lower().lstrip(".") not in FORMATS:
        raise ValueError("unsupported image format %r (use png, svg or pdf)" % path.suffix)
    pts = sorted(result.points, key=lambda p: p.freq_hz)
    f = np.array([p.freq_hz for p in pts])
    gain_label, value = UNITS.get(opts.unit, UNITS["db"])
    gain = np.array([value(p) for p in pts])
    phase = np.array([p.phase_deg for p in pts])
    if opts.unwrap and len(pts):
        phase = unwrap_deg(phase)
    flagged = np.array([bool(p.flags & ~QUIET) for p in pts], dtype=bool)

    rows = 2 if opts.show_phase else 1
    fig, axes = plt.subplots(rows, 1, sharex=True, figsize=(opts.width_in, opts.height_in))
    axes = np.atleast_1d(axes)
    for ax, y, label in zip(axes, (gain, phase), (gain_label, "Phase (deg)")):
        ax.plot(f, y, "-", color="#2a78d6", linewidth=1.2)
        if len(pts):
            ax.plot(f[~flagged], y[~flagged], "o", color="#2a78d6", markersize=3)
            ax.plot(f[flagged], y[flagged], "x", color="#d62728", markersize=6, label="flagged")
        ax.set_ylabel(label)
        ax.grid(True, which="both", linewidth=0.4, alpha=0.6)
        if opts.log_x:
            ax.set_xscale("log")
    if flagged.any():
        axes[0].legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("Frequency (Hz)")
    axes[0].set_title(opts.title)
    sw = result.config.get("sweep", {})
    st = result.config.get("stimulus", {})
    footer = "%s   %s to %s Hz   %s Vpp   %s%s%s" % (
        str(result.meta.get("finished", ""))[:19], _g(sw.get("start_hz")), _g(sw.get("stop_hz")),
        _g(st.get("amp_vpp")), describe_correction(result.meta),
        "   phase unwrapped" if opts.unwrap else "",
        "   ABORTED (partial)" if result.meta.get("aborted") else "")
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
