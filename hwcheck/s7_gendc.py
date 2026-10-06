"""Milestone 7 bench check: the generator's real DC at 1 Vpp, read on a sensitive range.

Why: with the generator ON at 1 Vpp, CH1 (generator side, 50 mV/div) read about +52 mV of
DC at the probe tip (s7_genoffset.py, dbg7_genoffset_neg.py), while s7_dcsource.py had
found almost none. At 50 mV/div one code is 20 mV at the tip and the scope's own zero is
off by a few codes (HW_REPORT.md 13.7), so CH1 cannot settle it.

The capacitor can: at 100 kHz the filter leaves about 15 mVpp there, so CH2 can sit on
2 mV/div (one code = 0.8 mV at the tip), and the DC on the capacitor IS the generator's DC
(1 k in series against the probe's 10 M).

PRECONDITION: the RC low-pass is wired, CH1 probe on the generator side, CH2 probe on the
capacitor, both 10X. Nobody needs to be at the bench.
Usage: python s7_gendc.py [@py]
Generator output OFF in a finally block; settings restored; no ':RUN'.
"""
import json
import os
import sys
import time
import traceback

import iolayer as io
import wave
from common import GEN_PID, GEN_VID, RESULTS, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from t0b_iolayer import Saver, b01

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
C = ":CHANnel1"
PROBE, F = 10.0, 100000.0
VDIV = {1: 0.05, 2: 0.002}
out = {"backend": BACKEND, "rows": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def main():
    with open(os.path.join(RESULTS, "s7_dcoffset_py.json"), encoding="utf-8") as f:
        base = {(int(ch), r["vdiv"]): d["mean_v"] for r in json.load(f)["rows"] if r["coupling"] == "DC"
                for ch, d in r["ch"].items()}
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

        g.configure_sine(1, F, 1.0, 0.0, "HIGHZ")                                    # UTG p.11-13
        sc.tb_steps = [1e-9, 2e-9, 5e-9, 10e-9, 25e-9, 50e-9] + [m * 10.0 ** e for e in range(-7, -2)
                                                                 for m in (1, 2, 5)] + [0.01, 0.02]
        sc.vdiv_steps = [m * 10.0 ** e for e in range(-4, 2) for m in (1, 2, 5)][2:-2]
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="DC", bw_limit=False, offset_v=0.0)   # forces PROBe 1X
            sc.set_vdiv(ch, VDIV[ch], "exact")
        sc.set_timebase(5.0 / F / sc.HDIV, "ceil")                                   # U1K p.16
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.free_run()
        print("generator CH1 output ON, 1 Vpp, 100 kHz. DC at the probe tips, open-input reading removed:")
        g.output(1, True)
        time.sleep(0.8)
        for off in (0.0, 0.02, 0.03, 0.0):
            g.set_verified(C + ":BASE:OFFSet", num(off), io.v_float, off, tol_abs=0.0005)    # UTG p.13
            time.sleep(0.8)
            row = dict(gen_offset=off, ch={})
            shots = [sc.acquire([1, 2]) for _ in range(4)]
            line = f"   generator offset {off * 1e3:+5.0f} mV:"
            for ch in (1, 2):
                dcs, rails = [], 0
                for s in shots:
                    w = s["waves"][ch]
                    rails += sum(1 for x in w["codes"] if x <= 1 or x >= 254)
                    a, b, dc, _ = wave._fit3(w["volts"], w["dt"], F)
                    dcs.append((dc - base.get((ch, VDIV[ch]), 0.0)) * PROBE)
                m = sum(dcs) / len(dcs)
                row["ch"][ch] = dict(vdiv=VDIV[ch], tip_dc_v=m, shots=dcs, rail_samples=rails,
                                     vpp_tip=2 * (a * a + b * b) ** 0.5 * PROBE)
                line += (f"   CH{ch} @{VDIV[ch] * 1e3:g} mV/div {m * 1e3:+7.1f} mV "
                         f"(spread {(max(dcs) - min(dcs)) * 1e3:.1f}){'  RAIL' if rails else ''}")
            print(line, flush=True)
            out["rows"].append(row)
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
        print("saved", save("s7_gendc_py.json", out))


if __name__ == "__main__":
    main()
