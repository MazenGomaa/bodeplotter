"""Milestone A1: compare an RC low-pass sweep (CSV exported by the app) with the model built
from the capacitor's LCR readings (HW_REPORT.md 13.18). Touches no instrument.

    .venv\\Scripts\\python.exe hwcheck\\m8_rc_compare.py <sweep.csv> [--r=OHMS] [--fmax=HZ]

Model: the capacitor is Cs in series with ESR = D / (2 pi f Cs); H = Zc / (R + Zc).
Cs and D are the LCR meter's readings, interpolated in log frequency and held constant
outside 100 Hz to 100 kHz. R defaults to 1000 ohm (nominal; it was not measured).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from bodeplot.io import export_csv

LCR_HZ = [100.0, 1e3, 1e4, 1e5]
LCR_CS = [105.7e-9, 105.4e-9, 104.4e-9, 102.6e-9]
LCR_D = [0.001, 0.003, 0.009, 0.028]


def opt(name, default):
    return next((float(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--%s=" % name)), default)


def interp(f, ys):
    x = min(max(math.log10(f), math.log10(LCR_HZ[0])), math.log10(LCR_HZ[-1]))
    xs = [math.log10(v) for v in LCR_HZ]
    for i in range(len(xs) - 1):
        if x <= xs[i + 1]:
            return ys[i] + (x - xs[i]) / (xs[i + 1] - xs[i]) * (ys[i + 1] - ys[i])
    return ys[-1]


def model(f, r):
    cs, d = interp(f, LCR_CS), interp(f, LCR_D)
    w = 2 * math.pi * f
    zc = complex(d / (w * cs), -1.0 / (w * cs))
    return zc / (r + zc)


def main():
    path = next(a for a in sys.argv[1:] if not a.startswith("--"))
    r, fmax = opt("r", 1000.0), opt("fmax", 100e3)
    result = export_csv.load_csv(path)
    print("file: %s   cal: %s   R = %g ohm" % (path, export_csv.describe_correction(result.meta), r))
    print("%12s %10s %10s %9s %10s %10s %9s  flags" % ("Hz", "gain dB", "model dB", "diff", "phase", "model", "diff"))
    worst_g = worst_p = 0.0
    for p in result.points:
        h = model(p.freq_hz, r)
        g, ph = 20 * math.log10(abs(h)), math.degrees(math.atan2(h.imag, h.real))
        dg, dp = p.gain_db - g, p.phase_deg - ph
        inside = p.freq_hz <= fmax
        if inside:
            worst_g, worst_p = max(worst_g, abs(dg)), max(worst_p, abs(dp))
        print("%12.2f %+10.3f %+10.3f %+9.3f %+10.2f %+10.2f %+9.2f  %s%s" % (
            p.freq_hz, p.gain_db, g, dg, p.phase_deg, ph, dp, p.flags.to_text(), "" if inside else "  (not counted)"))
    print("\nup to %g Hz: largest gain difference %.3f dB, largest phase difference %.2f deg" % (fmax, worst_g, worst_p))


if __name__ == "__main__":
    main()
