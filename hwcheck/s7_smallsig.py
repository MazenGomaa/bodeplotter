"""Milestone 7 bench check: what do the most sensitive V/div steps really return?

Why: in the RC low-pass sweep (m7_sweep.py rc_1k_100n) the DUT channel read correctly down
to 1 mV/div, auto-range failed on several points between 11 and 44 kHz, and from 55 kHz
on, at 500 uV/div, the data collapsed (SNR 2 dB, then an amplitude of exactly zero).

PRECONDITION: the RC low-pass is still wired (generator CH1 -> 1 k -> 100 nF to ground;
CH1 probe on the generator side, CH2 probe on the capacitor, both 10X).
Usage: python s7_smallsig.py [@py]

The filter is used as a known attenuator: at 35 kHz the capacitor carries about 43 mVpp
(4.3 mVpp at the scope input), at 60 kHz about 25 mVpp (2.5 mVpp at the input). CH2 is
read at 5 mV, 2 mV, 1 mV and 500 uV per division and the raw codes are described.
No ':RUN'; stored step tables; generator output OFF in a finally block; settings restored.
"""
import math
import sys
import time
import traceback

import iolayer as io
import wave
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from t0b_iolayer import Saver, b01

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
SHOTS = 4
out = {"backend": BACKEND, "cases": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def describe(w, f):
    codes = w["codes"]
    n = len(codes)
    s = sorted(codes)
    a, b, c, rss = wave._fit3(w["volts"], w["dt"], f)
    amp = math.hypot(a, b)
    resid_rms = math.sqrt(rss / n)
    # residual in codes, sample by sample
    worst = 0.0
    for i, v in enumerate(w["volts"]):
        t = i * w["dt"]
        fit = a * math.cos(2 * math.pi * f * t) + b * math.sin(2 * math.pi * f * t) + c
        worst = max(worst, abs(v - fit) / w["yinc"])
    return dict(code_min=s[0], code_max=s[-1], p005=s[int(0.005 * n)], p995=s[int(0.995 * n) - 1],
                distinct=len(set(codes)), at_low_rail=sum(1 for x in codes if x <= 1),
                at_high_rail=sum(1 for x in codes if x >= 254), yinc=w["yinc"], yor=w["yor"],
                fit_vpp_input=2 * amp, fit_pp_codes=2 * amp / w["yinc"], offset_codes=c / w["yinc"],
                resid_rms_codes=resid_rms / w["yinc"], worst_resid_codes=worst,
                snr_db=20 * math.log10((amp / math.sqrt(2)) / resid_rms) if resid_rms > 0 and amp > 0 else None)


def case(sc, f, vdiv):
    sc.set_vdiv(2, vdiv, "exact")                                    # U1K p.14
    time.sleep(0.5)
    c = dict(freq_hz=f, vdiv2=vdiv, vdiv2_readback=sc.query(":CHANnel2:SCALe?", io.v_float), shots=[])
    for _ in range(SHOTS):
        a = sc.acquire([1, 2])
        c["shots"].append(dict(ch1=describe(a["waves"][1], f), ch2=describe(a["waves"][2], f)))
    print(f"[{f:g} Hz, CH2 {vdiv:g} V/div, read-back {c['vdiv2_readback']:g}]")
    for s in c["shots"]:
        x = s["ch2"]
        snr = "%.1f" % x["snr_db"] if x["snr_db"] is not None else "-"
        print(f"    codes {x['code_min']:3d}..{x['code_max']:3d} (0.5%..99.5%: {x['p005']:3d}..{x['p995']:3d}) "
              f"distinct {x['distinct']:3d}  on rails {x['at_low_rail']}/{x['at_high_rail']}  "
              f"fit {x['fit_vpp_input'] * 1e3:6.3f} mVpp = {x['fit_pp_codes']:6.1f} codes  "
              f"noise rms {x['resid_rms_codes']:5.2f} worst {x['worst_resid_codes']:5.1f} codes  "
              f"SNR {snr} dB  YINC {x['yinc']:g}")
    r = c["shots"][0]["ch1"]
    print(f"    CH1 fit {r['fit_vpp_input'] * 1e3:.2f} mVpp at the input, codes {r['code_min']}..{r['code_max']}")
    out["cases"].append(c)


def main():
    rm = open_rm(BACKEND)
    g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID), log=log)
    sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID), log=log)
    gs = ss = sweep0 = None
    try:
        out["gen_idn"], out["scope_idn"] = g.connect(), sc.connect(build_tables=False)
        g.output(1, False)
        g.output(2, False)
        num, probe = io.GenFmt.num, io.ScopeFmt.probe
        gs = Saver(g)
        c = ":CHANnel1"
        for k, v, f in ((c + ":BASE:OFFSet", io.v_float, num), (c + ":BASE:AMPLitude", io.v_float, num),
                        (c + ":BASE:FREQuency", io.v_float, num), (c + ":AMPLitude:UNIT", g.V_UNIT, lambda x: x),
                        (c + ":LOAD", io.v_float, num), (c + ":BASE:WAVe", g.V_WAVE, lambda x: x)):
            gs.save(k, v, f)
        ss = Saver(sc)
        for ch in (1, 2):
            k = f":CHANnel{ch}"
            ss.save(k + ":SCALe", io.v_float, num)
            ss.save(k + ":OFFSet", io.v_float, num)
            ss.save(k + ":BWLimit", io.V_BWL)
            ss.save(k + ":COUPling", io.V_COUPLING)
            ss.save(k + ":VERNier", io.v_bool, b01)
            ss.save(k + ":PROBe", io.v_float, probe)
            ss.save(k + ":DISPlay", io.v_bool, b01)
        ss.save(":TIMebase:SCALe", io.v_float, num)
        ss.save(":TRIGger:LEVel", io.v_float, num)
        ss.save(":TRIGger:EDGE:SLOPe", io.V_SLOPE)
        ss.save(":TRIGger:SOURce", io.V_TRIGSRC)
        ss.save(":TRIGger:MODE", io.V_TRIGMODE)
        sweep0 = sc.query(":TRIGger:SWEep?", io.V_SWEEP)

        g.configure_sine(1, 35000.0, 1.0, 0.0, "HIGHZ")              # UTG p.11-13
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="DC", bw_limit=False, offset_v=0.0)   # forces PROBe 1X
        # stored step tables (HW_REPORT.md 12.2): never walked
        sc.tb_steps = [1e-9, 2e-9, 5e-9, 10e-9, 25e-9, 50e-9] + [m * 10.0 ** e for e in range(-7, -2)
                                                                 for m in (1, 2, 5)] + [0.01, 0.02]
        sc.vdiv_steps = [m * 10.0 ** e for e in range(-4, 2) for m in (1, 2, 5)][2:-2]
        sc.set_vdiv(1, 0.02, "exact")
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.free_run()
        print("generator CH1 output ON")
        g.output(1, True)
        time.sleep(0.8)
        if "offset" in sys.argv:
            # Second question (after the first run of this script found about 6 mV of DC on
            # CH2): can the channel offset re-centre the trace, and what happens to the
            # offset when V/div changes afterwards?
            f = 35000.0
            sc.set_timebase(5.0 / f / sc.HDIV, "ceil")               # U1K p.16
            sc.set_vdiv(2, 0.002, "exact")
            time.sleep(0.5)
            a = sc.acquire([1, 2])
            w = a["waves"][2]
            dc = sum(w["volts"]) / len(w["volts"])
            out["dc_ch2_input_v"] = dc
            print(f"CH2 at 2 mV/div, offset 0: mean {dc * 1e3:+.3f} mV at the input")
            for label, vd, off in (("offset set at 2 mV/div", 0.002, -dc), ("then V/div -> 1 mV", 0.001, None),
                                   ("then V/div -> 500 uV", 0.0005, None),
                                   ("offset set again at 500 uV/div", 0.0005, -dc),
                                   ("back to 2 mV/div", 0.002, None), ("offset 0 at 2 mV/div", 0.002, 0.0)):
                sc.set_vdiv(2, vd, "exact")
                if off is not None:
                    try:
                        rb = sc.set_verified(":CHANnel2:OFFSet", io.ScopeFmt.num(off), io.v_float, float(off),
                                             tol_abs=vd / sc.CODES_PER_DIV)                 # U1K p.14
                    except Exception as e:
                        print(f"  {label}: SET FAILED {type(e).__name__}: {e}")
                time.sleep(0.5)
                rb = sc.query(":CHANnel2:OFFSet?", io.v_float)
                print(f"--- {label}: V/div {vd:g}, offset read-back {rb * 1e3:+.4f} mV ({rb / vd:+.2f} div)")
                out.setdefault("offset_steps", []).append(dict(label=label, vdiv=vd, offset_set=off, offset_readback=rb))
                case(sc, f, vd)
        else:
            for f in (35000.0, 60000.0):
                g.set_frequency(1, f)                                    # UTG p.12
                sc.set_timebase(5.0 / f / sc.HDIV, "ceil")               # U1K p.16
                for vd in (0.005, 0.002, 0.001, 0.0005):
                    case(sc, f, vd)
    except Exception:
        out["fatal"] = traceback.format_exc()
        print(out["fatal"])
    finally:
        g.safe_off()
        try:
            out["gen_outputs_final"] = [g.output(1), g.output(2)]
            print("generator outputs ON at end?", out["gen_outputs_final"])
        except Exception as e:
            out["gen_outputs_final_error"] = str(e)
        try:
            out["gen_restore_failures"] = gs.restore() if gs else ["not saved"]
        except Exception as e:
            out["gen_restore_failures"] = [str(e)]
        try:
            sc.free_run()
            bad = ss.restore() if ss else ["not saved"]
            if sweep0:
                sc.set_verified(":TRIGger:SWEep", sweep0, io.V_SWEEP, sweep0)
            out["scope_restore_failures"] = bad
        except Exception as e:
            out["scope_restore_failures"] = [str(e)]
        out["scope_stats"], out["gen_stats"] = dict(sc.stats), dict(g.stats)
        print("restore failures: gen", out["gen_restore_failures"], "scope", out["scope_restore_failures"])
        g.close()
        sc.close()
        rm.close()
        print("saved", save("s7_smallsig_offset_py.json" if "offset" in sys.argv else "s7_smallsig_py.json", out))


if __name__ == "__main__":
    main()
