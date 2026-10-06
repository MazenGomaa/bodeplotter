"""Milestone 7 debug: how can the generator be given a NEGATIVE offset?

Why: s7_genoffset.py showed that ':CHANnel1:BASE:OFFSet -0.1' is ignored (the read-back
keeps the previous value, and the DC at the output does not move), while positive values
work. The manual gives the range as 0 to +/- max (UTG p.13).

PRECONDITION: the RC low-pass is wired, CH1 probe (10X) on the generator side.
Usage: python dbg7_genoffset_neg.py [@py]

A. Output OFF: other spellings of a negative number for OFFSet, then the documented
   high / low level commands (':CHANnel1:BASE:HIGH', ':CHANnel1:BASE:LOW', UTG p.13-14),
   which the manual says can replace amplitude and offset (UTG p.37).
B. Output ON, 1 Vpp, 1 kHz: the DC at the CH1 probe tip for each state that read back a
   negative offset, against offset 0.
Generator output OFF in a finally block; settings restored; no ':RUN'.
"""
import re
import sys
import time
import traceback

import iolayer as io
import wave
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from t0b_iolayer import Saver, b01

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
C = ":CHANnel1"
PROBE, F = 10.0, 1000.0
out = {"backend": BACKEND, "steps": [], "b": [], "log": []}

# commands this script adds to the layer's list; both are printed in the UTG manual
_CH, _NUM = io.GenIO._CH, io.GenIO._NUM
io.GenIO.ALLOWED = io.GenIO.ALLOWED + [re.compile(p) for p in (
    rf"^{_CH}:BASE:HIGH( {_NUM}|\?)$",                                   # UTG p.13
    rf"^{_CH}:BASE:LOW( {_NUM}|\?)$",                                    # UTG p.14
    rf"^{_CH}:BASE:OFFSet -?\d(\.\d+)?e[+-]\d+$",                        # UTG p.13, number as the generator prints it
)]


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def state(g):
    s = {}
    for k in ("OFFSet", "AMPLitude", "HIGH", "LOW"):
        try:
            s[k] = g.query(f"{C}:BASE:{k}?", io.v_float)
        except Exception as e:
            s[k] = "%s: %s" % (type(e).__name__, e)
    return s


def step(g, label, *cmds):
    for cmd in cmds:
        g.write(cmd)
        time.sleep(0.3)
    s = state(g)
    out["steps"].append(dict(label=label, cmds=list(cmds), state=s))
    print(f"   {label:44s} -> offset {s['OFFSet']}  amplitude {s['AMPLitude']}  high {s['HIGH']}  low {s['LOW']}",
          flush=True)
    return s


def tip_dc(sc):
    dcs = []
    for _ in range(3):
        w = sc.acquire([1])["waves"][1]
        a, b, dc, _ = wave._fit3(w["volts"], w["dt"], F)
        dcs.append(dc * PROBE)
    return sum(dcs) / len(dcs), 2 * (a * a + b * b) ** 0.5 * PROBE


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
        ss.save(C + ":DISPlay", io.v_bool, b01)          # first, so restored last
        ss.save(C + ":SCALe", io.v_float, num)
        ss.save(C + ":OFFSet", io.v_float, num)
        ss.save(C + ":BWLimit", io.V_BWL)
        ss.save(C + ":COUPling", io.V_COUPLING)
        ss.save(C + ":VERNier", io.v_bool, b01)
        ss.save(C + ":PROBe", io.v_float, probe)
        ss.save(":TIMebase:SCALe", io.v_float, num)
        ss.save(":TRIGger:LEVel", io.v_float, num)
        ss.save(":TRIGger:EDGE:SLOPe", io.V_SLOPE)
        ss.save(":TRIGger:SOURce", io.V_TRIGSRC)
        ss.save(":TRIGger:MODE", io.V_TRIGMODE)
        sweep0 = sc.query(":TRIGger:SWEep?", io.V_SWEEP)

        g.configure_sine(1, F, 1.0, 0.0, "HIGHZ")                                    # UTG p.11-13
        print("A. output OFF, 1 Vpp sine, High-Z")
        step(g, "start (offset 0)")
        step(g, "OFFSet -0.1 (plain decimal, known to fail)", f"{C}:BASE:OFFSet -0.1")
        step(g, "OFFSet 0", f"{C}:BASE:OFFSet 0")
        step(g, "OFFSet -1e-1", f"{C}:BASE:OFFSet -1e-1")
        step(g, "OFFSet 0", f"{C}:BASE:OFFSet 0")
        step(g, "OFFSet -1.000000e-01", f"{C}:BASE:OFFSet -1.000000e-01")
        step(g, "OFFSet 0", f"{C}:BASE:OFFSet 0")
        step(g, "LOW -0.6", f"{C}:BASE:LOW -0.6")
        a = step(g, "then HIGH 0.4 (wanted: offset -0.1, 1 Vpp)", f"{C}:BASE:HIGH 0.4")
        via_levels = isinstance(a["OFFSet"], float) and abs(a["OFFSet"] + 0.1) < 0.002
        out["negative_via_levels"] = via_levels
        step(g, "HIGH 0.5, LOW -0.5 (back to offset 0)", f"{C}:BASE:HIGH 0.5", f"{C}:BASE:LOW -0.5")

        if via_levels:
            sc.tb_steps = [1e-9, 2e-9, 5e-9, 10e-9, 25e-9, 50e-9] + [m * 10.0 ** e for e in range(-7, -2)
                                                                     for m in (1, 2, 5)] + [0.01, 0.02]
            sc.vdiv_steps = [m * 10.0 ** e for e in range(-4, 2) for m in (1, 2, 5)][2:-2]
            sc.configure_channel(1, coupling="DC", bw_limit=False, offset_v=0.0)    # forces PROBe 1X
            sc.set_vdiv(1, 0.05, "exact")
            sc.set_timebase(5.0 / F / sc.HDIV, "ceil")                               # U1K p.16
            sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
            sc.free_run()
            print("B. generator CH1 output ON, 1 Vpp, 1 kHz")
            g.output(1, True)
            time.sleep(0.8)
            for label, cmds in (("offset 0", (f"{C}:BASE:HIGH 0.5", f"{C}:BASE:LOW -0.5")),
                                ("offset -0.1 by LOW -0.6, HIGH 0.4", (f"{C}:BASE:LOW -0.6", f"{C}:BASE:HIGH 0.4")),
                                ("offset -0.3 by LOW -0.8, HIGH 0.2", (f"{C}:BASE:LOW -0.8", f"{C}:BASE:HIGH 0.2")),
                                ("offset 0", (f"{C}:BASE:HIGH 0.5", f"{C}:BASE:LOW -0.5"))):
                for cmd in cmds:
                    g.write(cmd)
                    time.sleep(0.3)
                s = state(g)
                time.sleep(0.5)
                dc, vpp = tip_dc(sc)
                out["b"].append(dict(label=label, state=s, tip_dc_v=dc, vpp_tip=vpp))
                print(f"   {label:36s} read-back offset {s['OFFSet']}  amplitude {s['AMPLitude']}   "
                      f"DC at the tip {dc * 1e3:+8.1f} mV, {vpp:.3f} Vpp", flush=True)
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
            out["gen_final_state"] = state(g)
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
        print("generator at the end:", out.get("gen_final_state"))
        g.close()
        sc.close()
        rm.close()
        print("saved", save("dbg7_genoffset_neg_py.json", out))


if __name__ == "__main__":
    main()
