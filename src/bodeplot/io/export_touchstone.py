"""Touchstone .s2p export (SPEC.md section 12).

Header '# Hz S RI R 50'. S21 = H; S11, S12, S22 = 0. Comment lines say plainly
that this is a scope-based voltage transfer ratio, not a calibrated 50 ohm
S-parameter measurement.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..models import SweepResult
from .export_csv import cal_header, skew_header


def write_touchstone(path, result: SweepResult) -> Path:
    path = Path(path)
    lines = [
        "! Bode plotter export (bodeplot %s)" % result.meta.get("app_version", "?"),
        "! NOT a calibrated S-parameter measurement.",
        "! S21 is the voltage transfer ratio Vdut/Vref measured with an oscilloscope;",
        "! S11, S12 and S22 are written as 0 and carry no information. The 50 ohm reference",
        "! impedance is nominal only.",
        "! started: %s  finished: %s" % (result.meta.get("started", "?"), result.meta.get("finished", "?")),
        "! source: %s" % result.meta.get("source_idn", "?"),
        "! digitizer: %s" % result.meta.get("digitizer_idn", "?"),
    ]
    if result.meta.get("aborted"):
        lines.append("! NOTE: the sweep was aborted; this file holds a partial result.")
    for key, value in skew_header(result.meta) + cal_header(result.meta):
        lines.append("! %s: %s" % (key, value))
    lines.append("! config: %s" % json.dumps(result.config, default=str))
    lines.append("# Hz S RI R 50")
    for p in sorted(result.points, key=lambda q: q.freq_hz):
        if not (math.isfinite(p.h.real) and math.isfinite(p.h.imag)):
            continue
        lines.append("%.9g 0 0 %.9g %.9g 0 0 0 0" % (p.freq_hz, p.h.real, p.h.imag))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def read_touchstone_s21(path) -> list[tuple[float, complex]]:
    """Minimal reader for files written here (used by the tests)."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line[0] in "!#":
            continue
        v = [float(x) for x in line.split()]
        if len(v) == 9:
            out.append((v[0], complex(v[3], v[4])))
    return out
