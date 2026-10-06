"""Milestone 7 bench check: where does the DC at the scope inputs come from?

Why: the RC low-pass sweep found about +6 mV (CH2) and +7.6 mV (CH1) of DC at the scope
inputs (HW_REPORT.md 13.6). The user then ran the scope's self calibration, removed all
probes and still saw the offset at 500 uV/div. So the generator and the DUT are ruled out
and the question is what kind of offset the scope itself has.

PRECONDITION: nothing connected to scope CH1 and CH2 (inputs open). No cable is touched.
Usage: python s7_dcoffset.py [@py]

For each coupling (DC, AC, GND) and each V/div step the mean of CH1 and CH2 is read with
the channel offset at 0. What the table tells:
  - same volts on every step      -> an input-referred offset (before the gain stages);
  - same divisions on every step  -> an offset after the gain stages (ADC / position);
  - still there with GND coupling -> it is generated after the coupling switch;
  - gone with AC coupling         -> AC coupling would cure it (the user's suggestion).
Timebase 10 ms/div: one record is 140 ms, 7 whole periods of 50 Hz, so mains pickup on the
open inputs averages out of the mean.
No ':RUN'; stored step tables; generator outputs forced OFF and never switched on;
scope settings restored.
"""
import math
import sys
import time
import traceback

import iolayer as io
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from t0b_iolayer import Saver, b01

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
SHOTS = 2
COUPLINGS = ("DC", "AC", "GND")
VDIVS = (0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 1.0)
out = {"backend": BACKEND, "rows": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def describe(w):
    codes, volts = w["codes"], w["volts"]
    n = len(codes)
    mean_v = sum(volts) / n
    mean_c = sum(codes) / n
    return dict(mean_v=mean_v, mean_code=mean_c, code_min=min(codes), code_max=max(codes),
                rms_codes=math.sqrt(sum((c - mean_c) ** 2 for c in codes) / n),
                at_low_rail=sum(1 for x in codes if x <= 1), at_high_rail=sum(1 for x in codes if x >= 254),
                yinc=w["yinc"], yor=w["yor"], yref=w["yref"])


def row(sc, coupling, vdiv):
    r = dict(coupling=coupling, vdiv=vdiv, ch={})
    for ch in (1, 2):
        sc.set_vdiv(ch, vdiv, "exact")                                               # U1K p.14
        # the scope keeps the offset in divisions across V/div changes (HW_REPORT 13.6)
        sc.set_verified(f":CHANnel{ch}:OFFSet", "0", io.v_float, 0.0, tol_abs=vdiv / sc.CODES_PER_DIV)
    time.sleep(0.5)
    shots = [sc.acquire([1, 2], force_after_s=0.2) for _ in range(SHOTS)]
    line = f"  {coupling:3s} {vdiv * 1e3:7.1f} mV/div"
    for ch in (1, 2):
        d = [describe(s["waves"][ch]) for s in shots]
        m = sum(x["mean_v"] for x in d) / len(d)
        r["ch"][ch] = dict(shots=d, mean_v=m, mean_div=m / vdiv,
                           offset_readback=sc.query(f":CHANnel{ch}:OFFSet?", io.v_float))
        x = d[0]
        rails = x["at_low_rail"] + x["at_high_rail"]
        line += (f"   CH{ch} {m * 1e3:+8.3f} mV = {m / vdiv:+6.2f} div  codes {x['code_min']:3d}..{x['code_max']:3d}"
                 f" rms {x['rms_codes']:4.1f}{'  RAIL %d' % rails if rails else ''}")
    print(line, flush=True)
    out["rows"].append(r)


def main():
    rm = open_rm(BACKEND)
    g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID), log=log)
    sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID), log=log)
    ss = sweep0 = None
    try:
        out["gen_idn"], out["scope_idn"] = g.connect(), sc.connect(build_tables=False)
        g.output(1, False)
        g.output(2, False)
        num, probe = io.GenFmt.num, io.ScopeFmt.probe
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

        # stored step tables (HW_REPORT.md 12.2): never walked
        sc.tb_steps = [1e-9, 2e-9, 5e-9, 10e-9, 25e-9, 50e-9] + [m * 10.0 ** e for e in range(-7, -2)
                                                                 for m in (1, 2, 5)] + [0.01, 0.02]
        sc.vdiv_steps = [m * 10.0 ** e for e in range(-4, 2) for m in (1, 2, 5)][2:-2]
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="DC", bw_limit=False, offset_v=0.0)   # forces PROBe 1X
        sc.set_timebase(0.01, "exact")                                               # U1K p.16
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.free_run()
        for coupling in COUPLINGS:
            try:
                for ch in (1, 2):
                    sc.set_verified(f":CHANnel{ch}:COUPling", coupling, io.V_COUPLING, coupling)   # U1K p.13
            except Exception as e:
                print(f"  coupling {coupling}: SET FAILED {type(e).__name__}: {e}")
                out.setdefault("coupling_failures", []).append([coupling, str(e)])
                continue
            time.sleep(2.0)                      # let an AC coupling capacitor settle
            for vd in VDIVS:
                row(sc, coupling, vd)
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
            sc.free_run()
            bad = ss.restore() if ss else ["not saved"]
            if sweep0:
                sc.set_verified(":TRIGger:SWEep", sweep0, io.V_SWEEP, sweep0)
            out["scope_restore_failures"] = bad
        except Exception as e:
            out["scope_restore_failures"] = [str(e)]
        out["scope_stats"], out["gen_stats"] = dict(sc.stats), dict(g.stats)
        print("scope restore failures:", out["scope_restore_failures"])
        g.close()
        sc.close()
        rm.close()
        print("saved", save("s7_dcoffset_py.json", out))


if __name__ == "__main__":
    main()
