"""Milestone 6 bench check: ADC rail codes and vertical division count (SPEC.md 17).

PRECONDITION: both 10X probes on generator CH1's output (as in Milestone 0c).
Usage: python s6_overdrive.py [@py]

Generator CH1: 1 kHz sine, 1 Vpp, High-Z, i.e. 0.1 Vpp at each scope input. CH1 (trigger
and reference) stays at 20 mV/div. CH2 is deliberately overdriven by making its V/div
smaller, and separately pushed off the top and bottom with its vertical offset. For every
case the raw waveform codes of both channels are recorded: lowest and highest code, how
many samples sit on them, and the longest flat run. From that:
  - the codes the data stop at (the rails),
  - whether the data stop at the screen edge or beyond it, i.e. how many divisions the
    waveform data cover (25 codes per division, U1K p.72),
  - whether overdriving CH2 disturbs CH1.

The overdrive is 0.1 Vpp into a 1 Mohm input: display overdrive only, far inside the input
rating. No ':RUN' is sent; step tables are the stored ones (no walk). Generator output is
ON only inside this script, OFF in a finally block; every changed setting is restored.
"""
import sys
import time
import traceback

import iolayer as io
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from t0b_iolayer import Saver, b01

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
F = 1000.0
AMP_VPP = 1.0
PROBE = 10.0
SHOTS = 3
out = {"backend": BACKEND, "freq_hz": F, "gen_amp_vpp": AMP_VPP, "probe_ratio": PROBE, "cases": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def describe(w):
    codes = w["codes"]
    lo, hi = min(codes), max(codes)

    def longest(val):
        best = run = 0
        for c in codes:
            run = run + 1 if c == val else 0
            best = max(best, run)
        return best
    return dict(code_min=lo, code_max=hi, n_at_min=codes.count(lo), n_at_max=codes.count(hi),
                run_at_min=longest(lo), run_at_max=longest(hi), yinc=w["yinc"], yor=w["yor"],
                yref=w["yref"], n=len(codes), mean_code=sum(codes) / len(codes),
                clipped_by_current_rule=w["clipped"])


def case(sc, label, vdiv2, offset2_v):
    """Set CH2's V/div and offset, take SHOTS single shots, describe both channels."""
    sc.set_vdiv(2, vdiv2, "exact")                                              # U1K p.14
    sc.set_verified(":CHANnel2:OFFSet", io.ScopeFmt.num(offset2_v), io.v_float, float(offset2_v),
                    tol_abs=vdiv2 / sc.CODES_PER_DIV)                           # U1K p.14
    off_rb = sc.query(":CHANnel2:OFFSet?", io.v_float)
    time.sleep(0.5)
    c = dict(label=label, vdiv2=vdiv2, offset2_set_v=offset2_v, offset2_readback_v=off_rb,
             signal_pp_div=(AMP_VPP / PROBE) / vdiv2, offset_div=off_rb / vdiv2, shots=[])
    for _ in range(SHOTS):
        a = sc.acquire([1, 2])
        c["shots"].append({"ch1": describe(a["waves"][1]), "ch2": describe(a["waves"][2]),
                           "states": "->".join(a["states"])})
    s2 = [s["ch2"] for s in c["shots"]]
    s1 = [s["ch1"] for s in c["shots"]]
    c["ch2_min"], c["ch2_max"] = min(x["code_min"] for x in s2), max(x["code_max"] for x in s2)
    c["ch1_min"], c["ch1_max"] = min(x["code_min"] for x in s1), max(x["code_max"] for x in s1)
    print(f"[{label}] CH2 {vdiv2:g} V/div, offset {off_rb:+g} V ({c['offset_div']:+.2f} div), signal "
          f"{c['signal_pp_div']:.1f} div p-p")
    for x in s2:
        print(f"    CH2 codes {x['code_min']:3d}..{x['code_max']:3d}  at min {x['n_at_min']:3d} (run "
              f"{x['run_at_min']:3d})  at max {x['n_at_max']:3d} (run {x['run_at_max']:3d})  YOR {x['yor']:g}  "
              f"mean {x['mean_code']:.1f}  rule-clipped {x['clipped_by_current_rule']}")
    print(f"    CH1 codes {c['ch1_min']}..{c['ch1_max']} (span {c['ch1_max'] - c['ch1_min']})")
    out["cases"].append(c)
    return c


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

        g.configure_sine(1, F, AMP_VPP, 0.0, "HIGHZ")                # UTG p.11-13
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="DC", bw_limit=False, offset_v=0.0)   # forces PROBe 1X
        # step tables as measured in 0b (HW_REPORT.md 12): never walked here
        sc.tb_steps = [1e-9, 2e-9, 5e-9, 10e-9, 25e-9, 50e-9] + [m * 10.0 ** e for e in range(-7, -2)
                                                                 for m in (1, 2, 5)] + [0.01, 0.02]
        sc.vdiv_steps = [m * 10.0 ** e for e in range(-4, 2) for m in (1, 2, 5)][2:-2]
        for ch in (1, 2):
            sc.set_vdiv(ch, 0.02, "exact")                           # U1K p.14
        sc.set_timebase(5.0 / F / sc.HDIV, "ceil")                   # U1K p.16
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.free_run()
        print("generator CH1 output ON")
        g.output(1, True)
        time.sleep(0.8)

        # A. reference: 5 divisions p-p, nothing overdriven
        case(sc, "A reference", 0.02, 0.0)
        # B. overdrive by V/div: 10, 20, 50, 100, 200 divisions p-p
        for vd in (0.01, 0.005, 0.002, 0.001, 0.0005):
            case(sc, "B overdrive by V/div", vd, 0.0)
        # C. push the 5-division signal off the top and the bottom with the offset.
        #    Offset in divisions: 1, 2, 3, 4, 5, 6, 8 each way (at 20 mV/div).
        for div in (1, 2, 3, 4, 5, 6, 8):
            case(sc, "C offset up", 0.02, div * 0.02)
        for div in (1, 2, 3, 4, 5, 6, 8):
            case(sc, "C offset down", 0.02, -div * 0.02)
        case(sc, "A reference again", 0.02, 0.0)

        allc = [c for c in out["cases"] if not c["label"].startswith("A")]
        out["lowest_code_seen"] = min(c["ch2_min"] for c in allc)
        out["highest_code_seen"] = max(c["ch2_max"] for c in allc)
        span = out["highest_code_seen"] - out["lowest_code_seen"]
        out["data_divisions"] = span / sc.CODES_PER_DIV
        print(f"\nlowest code {out['lowest_code_seen']}, highest code {out['highest_code_seen']}, "
              f"= {out['data_divisions']:.2f} divisions of waveform data")
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
        print("saved", save(f"s6_overdrive_{BACKEND.strip('@')}.json", out))


if __name__ == "__main__":
    main()
