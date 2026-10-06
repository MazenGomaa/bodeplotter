"""Milestone 7 bench check: does the DC seen in the RC sweep come from the generator?

Why: with the scope inputs open, the scope's own offset is 0.3 mV or less on the sensitive
steps (s7_dcoffset.py, HW_REPORT.md 13.7). The RC sweep had +6 to +9 mV at the inputs
(60 to 90 mV at the probe tips). Either the generator puts out that DC, or the scope's
self calibration (run by the user in between) removed it.

PRECONDITION: the RC low-pass is wired (generator CH1 -> 1 k -> 100 nF to ground; CH1 probe
on the generator side, CH2 probe on the capacitor; both 10X).
Usage: python s7_dcsource.py [@py]

The DC of both channels is read with the generator output OFF, ON at 1 Vpp (1 kHz and
35 kHz), ON at 0.1 Vpp, and ON with the generator's own offset set to cancel what was
measured. Each reading is corrected with the open-input reading of the same channel and
V/div step from results/s7_dcoffset_py.json.
No ':RUN'; stored step tables; generator output OFF in a finally block; settings restored.
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
SHOTS = 3
PROBE = 10.0
out = {"backend": BACKEND, "cases": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def baseline():
    """Open-input DC per (channel, V/div) from s7_dcoffset.py, DC coupling."""
    with open(os.path.join(RESULTS, "s7_dcoffset_py.json"), encoding="utf-8") as f:
        rows = json.load(f)["rows"]
    return {(int(ch), r["vdiv"]): d["mean_v"] for r in rows if r["coupling"] == "DC" for ch, d in r["ch"].items()}


def case(sc, base, label, f, vdivs, tb):
    """f = None: no signal, plain mean. Otherwise the DC term of a sine fit at f."""
    for ch in (1, 2):
        sc.set_vdiv(ch, vdivs[ch], "exact")                                          # U1K p.14
        sc.set_verified(f":CHANnel{ch}:OFFSet", "0", io.v_float, 0.0, tol_abs=vdivs[ch] / sc.CODES_PER_DIV)
    sc.set_timebase(tb, "ceil")                                                      # U1K p.16
    time.sleep(0.5)
    shots = [sc.acquire([1, 2], force_after_s=0.2 if f is None else None) for _ in range(SHOTS)]
    c = dict(label=label, freq_hz=f, ch={})
    line = f"  {label:34s}"
    for ch in (1, 2):
        dcs, vpps, rails = [], [], 0
        for s in shots:
            w = s["waves"][ch]
            rails += sum(1 for x in w["codes"] if x <= 1 or x >= 254)
            if f is None:
                dcs.append(sum(w["volts"]) / len(w["volts"]))
                vpps.append((max(w["codes"]) - min(w["codes"])) * w["yinc"])
            else:
                a, b, dc, _ = wave._fit3(w["volts"], w["dt"], f)
                dcs.append(dc)
                vpps.append(2 * (a * a + b * b) ** 0.5)
        dc, vpp = sum(dcs) / len(dcs), sum(vpps) / len(vpps)
        corr = dc - base.get((ch, vdivs[ch]), 0.0)
        c["ch"][ch] = dict(vdiv=vdivs[ch], dc_input_v=dc, dc_shots=dcs, open_input_v=base.get((ch, vdivs[ch])),
                           dc_corrected_input_v=corr, dc_tip_v=corr * PROBE, vpp_input_v=vpp, rail_samples=rails)
        line += (f"   CH{ch} @{vdivs[ch] * 1e3:g} mV/div: {dc * 1e3:+7.3f} mV, corrected {corr * 1e3:+7.3f}"
                 f" = {corr * PROBE * 1e3:+7.1f} mV at the tip, {vpp * 1e3:6.1f} mVpp{'  RAIL' if rails else ''}")
    print(line, flush=True)
    out["cases"].append(c)
    return c


def main():
    base = baseline()
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
            ss.save(k + ":DISPlay", io.v_bool, b01)      # first, so restored last (SCALe needs the channel on)
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

        # stored step tables (HW_REPORT.md 12.2): never walked
        sc.tb_steps = [1e-9, 2e-9, 5e-9, 10e-9, 25e-9, 50e-9] + [m * 10.0 ** e for e in range(-7, -2)
                                                                 for m in (1, 2, 5)] + [0.01, 0.02]
        sc.vdiv_steps = [m * 10.0 ** e for e in range(-4, 2) for m in (1, 2, 5)][2:-2]
        g.configure_sine(1, 1000.0, 1.0, 0.0, "HIGHZ")                               # UTG p.11-13
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="DC", bw_limit=False, offset_v=0.0)   # forces PROBe 1X
        sc.set_vdiv(1, 0.02, "exact")
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.free_run()

        tb = lambda f: 5.0 / f / sc.HDIV
        case(sc, base, "output OFF", None, {1: 0.02, 2: 0.02}, 0.01)
        case(sc, base, "output OFF", None, {1: 0.002, 2: 0.002}, 0.01)
        print("generator CH1 output ON")
        g.output(1, True)
        time.sleep(0.8)
        b = case(sc, base, "ON 1 Vpp 1 kHz, gen offset 0", 1000.0, {1: 0.02, 2: 0.02}, tb(1000.0))
        g.set_frequency(1, 35000.0)                                                  # UTG p.12
        case(sc, base, "ON 1 Vpp 35 kHz, gen offset 0", 35000.0, {1: 0.02, 2: 0.002}, tb(35000.0))
        g.set_frequency(1, 1000.0)
        g.set_verified(c + ":BASE:AMPLitude", num(0.1), io.v_float, 0.1)             # UTG p.13
        time.sleep(0.5)
        case(sc, base, "ON 0.1 Vpp 1 kHz, gen offset 0", 1000.0, {1: 0.005, 2: 0.005}, tb(1000.0))
        g.set_verified(c + ":BASE:AMPLitude", num(1.0), io.v_float, 1.0)
        cancel = -round(b["ch"][1]["dc_tip_v"], 3)
        out["cancel_offset_v"] = cancel
        g.set_verified(c + ":BASE:OFFSet", num(cancel), io.v_float, cancel, tol_abs=0.0011)   # UTG p.13
        time.sleep(0.5)
        case(sc, base, "ON 1 Vpp 1 kHz, gen offset %+.0f mV" % (cancel * 1e3), 1000.0, {1: 0.02, 2: 0.02}, tb(1000.0))
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
        print("saved", save("s7_dcsource_py.json", out))


if __name__ == "__main__":
    main()
