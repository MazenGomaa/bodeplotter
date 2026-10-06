"""Milestone 7 bench check: does the scope's phase (or gain) depend on the V/div step?

Why: the RC low-pass leads the ideal phase by 1 to 3 degrees above 20 kHz (HW_REPORT.md
13.8, 13.12). In those sweeps the reference channel stays on 20 mV/div while the DUT
channel steps down to 1 mV/div, and the through sweeps that proved the phase (13.5) always
had both channels on the same step. If the input stage shifts the phase from one step to
the next, that would look exactly like a property of the filter.

Method: at fixed frequencies the same DUT signal (the capacitor voltage) is measured with
CH2 on every step it fits on, CH1 staying on 20 mV/div. Gain and phase should not change
with the step. AC coupling on both channels keeps the generator's DC out of it.

PRECONDITION: the RC low-pass is wired, CH1 probe on the generator side, CH2 probe on the
capacitor, both 10X. Nobody needs to be at the bench.
Usage: python s7_rangephase.py [@py]
Generator output OFF in a finally block; settings restored; no ':RUN'; stored step tables.
"""
import cmath
import math
import sys
import time
import traceback

import iolayer as io
import wave
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from t0b_iolayer import Saver, b01

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
C = ":CHANnel1"
FREQS = (5000.0, 20000.0, 50000.0, 100000.0)
STEPS = (0.001, 0.002, 0.005, 0.01, 0.02)
SHOTS = 6
FC = 1513.0
out = {"backend": BACKEND, "rows": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def phasor(w, f):
    a, b, _c, rss = wave._fit3(w["volts"], w["dt"], f)
    return complex(a, -b), math.sqrt(rss / len(w["volts"]))


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
        for k, v, f in ((C + ":BASE:OFFSet", io.v_float, num), (C + ":BASE:AMPLitude", io.v_float, num),
                        (C + ":BASE:FREQuency", io.v_float, num), (C + ":AMPLitude:UNIT", g.V_UNIT, lambda x: x),
                        (C + ":LOAD", io.v_float, num), (C + ":BASE:WAVe", g.V_WAVE, lambda x: x)):
            gs.save(k, v, f)
        ss = Saver(sc)
        for ch in (1, 2):
            k = f":CHANnel{ch}"
            ss.save(k + ":DISPlay", io.v_bool, b01)      # first, so restored last
            ss.save(k + ":SCALe", io.v_float, num)
            ss.save(k + ":OFFSet", io.v_float, num)
            ss.save(k + ":BWLimit", io.V_BWL)
            ss.save(k + ":COUPling", io.V_COUPLING)
            ss.save(k + ":VERNier", io.v_bool, b01)
            ss.save(k + ":PROBe", io.v_float, probe)
        ss.save(":TIMebase:SCALe", io.v_float, num)
        ss.save(":TRIGger:LEVel", io.v_float, num)
        ss.save(":TRIGger:EDGE:SLOPe", io.V_SLOPE)
        ss.save(":TRIGger:SOURce", io.V_TRIGSRC)
        ss.save(":TRIGger:MODE", io.V_TRIGMODE)
        sweep0 = sc.query(":TRIGger:SWEep?", io.V_SWEEP)

        g.configure_sine(1, FREQS[0], 1.0, 0.0, "HIGHZ")                             # UTG p.11-13
        sc.tb_steps = [1e-9, 2e-9, 5e-9, 10e-9, 25e-9, 50e-9] + [m * 10.0 ** e for e in range(-7, -2)
                                                                 for m in (1, 2, 5)] + [0.01, 0.02]
        sc.vdiv_steps = [m * 10.0 ** e for e in range(-4, 2) for m in (1, 2, 5)][2:-2]
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="AC", bw_limit=False, offset_v=0.0)   # forces PROBe 1X
        sc.set_vdiv(1, 0.02, "exact")
        sc.set_vdiv(2, 0.02, "exact")
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.free_run()
        print("generator CH1 output ON, 1 Vpp; CH1 on 20 mV/div, AC coupling")
        g.output(1, True)
        time.sleep(1.5)
        for f in FREQS:
            g.set_frequency(1, f)                                                    # UTG p.12
            sc.set_timebase(5.0 / f / sc.HDIV, "ceil")                               # U1K p.16
            vpp_in = 0.1 / math.sqrt(1 + (f / FC) ** 2)          # expected at the CH2 input
            ideal = -math.degrees(math.atan(f / FC))
            print(f"{f / 1e3:g} kHz: about {vpp_in * 1e3:.1f} mVpp at the CH2 input, ideal phase {ideal:.2f} deg")
            for vd in STEPS:
                if vpp_in > 7.0 * vd:                            # would leave the screen
                    continue
                sc.set_vdiv(2, vd, "exact")                                          # U1K p.14
                time.sleep(0.6)
                hs, rails, noise = [], 0, []
                for _ in range(SHOTS):
                    a = sc.acquire([1, 2])["waves"]
                    rails += sum(1 for x in a[2]["codes"] if x <= 1 or x >= 254)
                    p1, _n1 = phasor(a[1], f)
                    p2, n2 = phasor(a[2], f)
                    hs.append(p2 / p1)
                    noise.append(n2 / a[2]["yinc"])
                h = sum(hs) / len(hs)
                ph = [math.degrees(cmath.phase(x)) for x in hs]
                row = dict(freq_hz=f, vdiv2=vd, gain_db=20 * math.log10(abs(h)), phase_deg=math.degrees(cmath.phase(h)),
                           phase_spread_deg=max(ph) - min(ph), divs_pp=vpp_in / vd, rail_samples=rails,
                           noise_rms_codes=sum(noise) / len(noise), shots=[[x.real, x.imag] for x in hs])
                out["rows"].append(row)
                print(f"   CH2 {vd * 1e3:4.0f} mV/div ({row['divs_pp']:4.1f} div p-p): gain {row['gain_db']:+8.3f} dB   "
                      f"phase {row['phase_deg']:+8.2f} deg (spread {row['phase_spread_deg']:.2f})   "
                      f"lead over ideal {row['phase_deg'] - ideal:+.2f} deg{'   RAIL' if rails else ''}", flush=True)
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
        print("saved", save("s7_rangephase_py.json", out))


if __name__ == "__main__":
    main()
