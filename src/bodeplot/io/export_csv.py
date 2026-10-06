"""CSV export and loader (SPEC.md section 12). Must round-trip: v2 overlay needs the loader.

Metadata are '# key: value' header lines; structured values are JSON on one line.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from ..measure import skew
from ..measure.sinefit import unwrap_deg
from ..models import Flag, PointResult, SkewCheck, SweepResult, ThroughCal
from ..sweep import calibration

COLUMNS = ["freq_hz", "gain_db", "phase_deg", "phase_unwrapped_deg", "h_re", "h_im", "vref_amp_v",
           "vdut_amp_v", "vdiv_ref", "vdiv_dut", "timebase_s", "n_avg", "snr_ref_db", "snr_dut_db",
           "skew_corr_deg", "flags", "cal_gain_db", "cal_phase_deg"]


def _num(x) -> str:
    if x is None:
        return ""
    return repr(float(x))


def skew_header(meta: dict) -> list[tuple[str, str]]:
    """The skew lines shared by the CSV header and the Touchstone comments."""
    sk = meta.get("skew")
    if not sk:
        if ThroughCal.from_meta(meta.get("cal")) is not None:
            if meta.get("cal_covered", True):
                return [("skew", "not used (the through calibration was applied)")]
            return [("skew", "not checked (points outside the calibrated range are NOT corrected for channel skew)")]
        return [("skew", "not checked (phase is NOT corrected for channel skew)")]
    return [("skew", "checked"),
            ("skew_delay_ns", "%.4f" % (sk["delay_s"] * 1e9)),
            ("skew_measured_ns", "%.4f" % (sk["measured_s"] * 1e9)),
            ("skew_snapped", "yes" if sk["snapped"] else "no"),
            ("skew_gain_mismatch_db", "%.4f" % sk["gain_db"]),
            ("skew_check_freqs_hz", ", ".join("%g" % f for f in sk["freqs_hz"])),
            ("skew_checked_at", str(sk["checked_at"]))]


def cal_header(meta: dict) -> list[tuple[str, str]]:
    """The through-calibration lines shared by the CSV header and the Touchstone comments."""
    cal = ThroughCal.from_meta(meta.get("cal"))
    if cal is None:
        return [("cal", "none")]
    return [("cal", "applied" if meta.get("cal_covered", True) else "applied in part"),
            ("cal_checked_at", cal.checked_at),
            ("cal_range_hz", "%g, %g" % (cal.freqs_hz[0], cal.freqs_hz[-1])),
            ("cal_points", str(len(cal.freqs_hz))),
            ("cal_max_gain_db", "%.4f" % calibration.max_gain_db(cal))]


def write_csv(path, result: SweepResult) -> Path:
    path = Path(path)
    pts = sorted(result.points, key=lambda p: p.freq_hz)
    unwrapped = unwrap_deg([p.phase_deg for p in pts]) if pts else []
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("# bodeplot_csv: 1\n")
        for key in ("app_version", "started", "finished", "source_idn", "digitizer_idn",
                    "simulated", "aborted", "error"):
            if key in result.meta:
                f.write("# %s: %s\n" % (key, result.meta[key]))
        for key, value in skew_header(result.meta) + cal_header(result.meta):
            f.write("# %s: %s\n" % (key, value))
        f.write("# meta_json: %s\n" % json.dumps(result.meta, default=str))
        f.write("# config_json: %s\n" % json.dumps(result.config, default=str))
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for p, pu in zip(pts, unwrapped):
            w.writerow([_num(p.freq_hz), _num(p.gain_db), _num(p.phase_deg), _num(pu),
                        _num(p.h.real), _num(p.h.imag), _num(p.vref_amp), _num(p.vdut_amp),
                        _num(p.vdiv_ref), _num(p.vdiv_dut), _num(p.timebase), p.n_avg,
                        _num(p.snr_ref_db), _num(p.snr_dut_db), _num(p.skew_corr_deg),
                        p.flags.to_text(), _num(p.cal_gain_db), _num(p.cal_phase_deg)])
    return path


def _f(row: dict, key: str, default=None):
    v = row.get(key, "")
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


def load_csv(path) -> SweepResult:
    """Read a file written by write_csv. Tolerant: missing columns take defaults."""
    meta: dict = {}
    config: dict = {}
    data_lines: list[str] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        for line in f:
            if line.startswith("#"):
                key, _, value = line[1:].partition(":")
                key, value = key.strip(), value.strip()
                if key == "meta_json":
                    try:
                        meta = json.loads(value)
                    except ValueError:
                        pass
                elif key == "config_json":
                    try:
                        config = json.loads(value)
                    except ValueError:
                        pass
                else:
                    meta.setdefault("_header", {})[key] = value
            elif line.strip():
                data_lines.append(line)
    header = meta.pop("_header", {})
    for k, v in header.items():
        meta.setdefault(k, v)
    points: list[PointResult] = []
    for row in csv.DictReader(data_lines):
        freq = _f(row, "freq_hz")
        if freq is None:
            continue
        h = complex(_f(row, "h_re", math.nan), _f(row, "h_im", math.nan))
        points.append(PointResult(
            freq_hz=freq, h=h, gain_db=_f(row, "gain_db", math.nan),
            phase_deg=_f(row, "phase_deg", math.nan), vref_amp=_f(row, "vref_amp_v", math.nan),
            vdut_amp=_f(row, "vdut_amp_v", math.nan), vdiv_ref=_f(row, "vdiv_ref", math.nan),
            vdiv_dut=_f(row, "vdiv_dut", math.nan), timebase=_f(row, "timebase_s", math.nan),
            n_avg=int(_f(row, "n_avg", 1)), snr_ref_db=_f(row, "snr_ref_db"),
            snr_dut_db=_f(row, "snr_dut_db"), flags=Flag.from_text(row.get("flags", "")),
            duration_s=0.0, skew_corr_deg=_f(row, "skew_corr_deg", 0.0),
            cal_gain_db=_f(row, "cal_gain_db", 0.0), cal_phase_deg=_f(row, "cal_phase_deg", 0.0)))
    points.sort(key=lambda p: p.freq_hz)
    return SweepResult(config, points, meta)


def skew_from_meta(meta: dict) -> SkewCheck | None:
    sk = meta.get("skew")
    if not isinstance(sk, dict):
        return None
    try:
        return SkewCheck(**sk)
    except TypeError:
        return None


def describe_skew(meta: dict) -> str:
    return skew.describe(skew_from_meta(meta))


def describe_correction(meta: dict) -> str:
    """One line for a footer: the calibration when one was applied, else the skew check."""
    cal = ThroughCal.from_meta(meta.get("cal"))
    return calibration.describe(cal) if cal is not None else describe_skew(meta)
