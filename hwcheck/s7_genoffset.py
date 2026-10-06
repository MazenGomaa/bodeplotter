"""Milestone 7 bench check: what does the generator do with ':CHANnel1:BASE:OFFSet'?

Why: in s7_dcsource.py ':CHANnel1:BASE:OFFSet -0.011' read back 0.0 (HW_REPORT.md 13.8).
Milestone 0 only ever set an offset of 0. The app's Stimulus > Offset uses this command.

PRECONDITION: the RC low-pass is wired (generator CH1 -> 1 k -> 100 nF to ground; CH1 probe
on the generator side, 10X). Nobody needs to be at the bench.
Usage: python s7_genoffset.py [@py]

A. Output OFF: a list of offsets is written and read back.                    UTG p.13
B. Output ON, 1 Vpp, 1 kHz: for a few offsets the DC at the CH1 probe tip is measured
   with the scope, so a wrong read-back can be told from an offset that was not applied.
No ':RUN'; stored step tables; generator output OFF in a finally block; settings restored.
"""
import sys
import time
import traceback

import iolayer as io
import wave
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from t0b_iolayer import Saver, b01

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
CMD = ":CHANnel1:BASE:OFFSet"
A_VALUES = (0.5, 0.1, 0.05, 0.02, 0.011, 0.01, 0.005, 0.001, -0.001, -0.005, -0.01, -0.011, -0.02, -0.1, -0.5, 0.0)
B_VALUES = (0.0, 0.1, -0.1, 0.011, -0.011, 0.0)
PROBE = 10.0
F = 1000.0
out = {"backend": BACKEND, "a": [], "b": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def put(g, v):
    """Write the offset, wait, read it back. Returns (argument sent, read-back)."""
    arg = io.GenFmt.num(v)
    g.write(f"{CMD} {arg}")                                                      # UTG p.13
    time.sleep(0.3)
    return arg, g.query(CMD + "?", io.v_float)


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
        k = ":CHANnel1"
        ss.save(k + ":DISPlay", io.v_bool, b01)          # first, so restored last (SCALe needs the channel on)
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
        print("A. output OFF, 1 Vpp, High-Z")
        for v in A_VALUES:
            arg, rb = put(g, v)
            ok = abs(rb - v) <= 0.0005
            out["a"].append(dict(set=v, arg=arg, readback=rb, ok=ok))
            print(f"   set {arg:>7s}   read back {rb:+.6f}   {'ok' if ok else 'DIFFERENT'}", flush=True)

        sc.tb_steps = [1e-9, 2e-9, 5e-9, 10e-9, 25e-9, 50e-9] + [m * 10.0 ** e for e in range(-7, -2)
                                                                 for m in (1, 2, 5)] + [0.01, 0.02]
        sc.vdiv_steps = [m * 10.0 ** e for e in range(-4, 2) for m in (1, 2, 5)][2:-2]
        sc.configure_channel(1, coupling="DC", bw_limit=False, offset_v=0.0)        # forces PROBe 1X
        sc.set_vdiv(1, 0.05, "exact")                    # 100 mVpp + 10 mV of DC at the input: 2.4 div
        sc.set_timebase(5.0 / F / sc.HDIV, "ceil")                                   # U1K p.16
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.free_run()
        print("B. generator CH1 output ON, 1 Vpp, 1 kHz")
        g.output(1, True)
        time.sleep(0.8)
        for v in B_VALUES:
            arg, rb = put(g, v)
            time.sleep(0.5)
            dcs = []
            for _ in range(3):
                w = sc.acquire([1])["waves"][1]
                a, b, dc, _ = wave._fit3(w["volts"], w["dt"], F)
                dcs.append(dc * PROBE)
            dc = sum(dcs) / len(dcs)
            out["b"].append(dict(set=v, arg=arg, readback=rb, tip_dc_v=dc, shots=dcs,
                                 vpp_tip=2 * (a * a + b * b) ** 0.5 * PROBE))
            print(f"   set {arg:>7s}   read back {rb:+.6f}   DC at the probe tip {dc * 1e3:+8.1f} mV", flush=True)
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
        print("saved", save("s7_genoffset_py.json", out))


if __name__ == "__main__":
    main()
