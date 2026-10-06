"""Milestone 7, analysis only (no instrument): what makes the RC low-pass lead the ideal phase?

Usage: python a7_phase_lead.py        (any venv with numpy)

The recorded RC sweeps (results/m7/m7_sweep_rc_*.json) show the measured phase above the
ideal first-order curve: about +1 deg at 22 kHz and +3 deg at 110 kHz (HW_REPORT.md 13.8).
Three explanations are fitted to the points from 300 Hz up to where the DUT SNR is still
20 dB, for every run, with the nominal R = 1 kOhm:
  esr   a resistance r in series with the capacitor (its ESR, plus any contact or ground
        resistance shared by the capacitor and the DUT probe): lead = atan(w r C), grows
        in proportion to the frequency;
  loss  a lossy capacitor with a constant loss angle d (C -> C(1 - j tan d)): the lead
        tends to d and stays there;
  both  r and d together.
Each fit is on the complex transfer function (gain and phase together).
"""
import glob
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
R = 1000.0
RUNS = ("rc_timed_full", "rc_retest", "rc_dc_plus60", "rc_ac")


def model(f, c, r, d):
    w = 2 * np.pi * f
    zc = r + 1.0 / (1j * w * c * (1 - 1j * np.tan(d)))
    return zc / (R + zc)


def fit(f, h, use_r, use_d):
    """Coarse-to-fine grid on (C, r, d); the error is |H_model - H| relative to |H|."""
    best = None
    cs = np.linspace(95e-9, 115e-9, 81)
    rs = np.linspace(0, 3.0, 61) if use_r else np.array([0.0])
    ds = np.radians(np.linspace(0, 4.0, 81)) if use_d else np.array([0.0])
    for _ in range(3):
        for c in cs:
            for r in rs:
                for d in ds:
                    e = float(np.sqrt(np.mean(np.abs((model(f, c, r, d) - h) / h) ** 2)))
                    if best is None or e < best[0]:
                        best = (e, c, r, d)
        _, c, r, d = best
        cs = np.linspace(c - (cs[1] - cs[0]), c + (cs[1] - cs[0]), 21)
        if use_r:
            step = rs[1] - rs[0]
            rs = np.linspace(max(0, r - step), r + step, 21)
        if use_d:
            step = ds[1] - ds[0]
            ds = np.linspace(max(0, d - step), d + step, 21)
    return best


def main():
    out = {}
    for run in RUNS:
        path = os.path.join(HERE, "results", "m7", "m7_sweep_%s.json" % run)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            pts = json.load(fh)["result"]["points"]
        pts = [p for p in pts if p["freq_hz"] >= 300 and (p["snr_dut_db"] or 0) >= 20 and p["vref_amp"] > 0.4]
        f = np.array([p["freq_hz"] for p in pts])
        h = np.array([complex(*p["h"]) for p in pts])
        print("%s: %d points, %.0f Hz to %.0f kHz" % (run, len(pts), f[0], f[-1] / 1e3))
        out[run] = {}
        for name, use_r, use_d in (("ideal", False, False), ("esr", True, False), ("loss", False, True),
                                   ("both", True, True)):
            e, c, r, d = fit(f, h, use_r, use_d)
            m = model(f, c, r, d)
            dph = np.degrees(np.angle(h / m))
            dg = 20 * np.log10(np.abs(h / m))
            out[run][name] = dict(rms_rel=e, c_nf=c * 1e9, r_ohm=r, loss_deg=float(np.degrees(d)),
                                  phase_err=[float(dph.min()), float(dph.max())],
                                  gain_err=[float(dg.min()), float(dg.max())])
            print("   %-5s  C %6.2f nF  r %4.2f ohm  loss angle %4.2f deg (tan d %.4f)   rms error %.2f %%   "
                  "phase %+.2f..%+.2f deg   gain %+.3f..%+.3f dB" % (
                      name, c * 1e9, r, np.degrees(d), np.tan(d), e * 100, dph.min(), dph.max(), dg.min(), dg.max()))
    with open(os.path.join(HERE, "results", "a7_phase_lead.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)


if __name__ == "__main__":
    main()
