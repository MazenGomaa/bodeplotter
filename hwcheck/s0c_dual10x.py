"""Milestone 0c: dual-channel test with 10X probes, through iolayer.py.

PRECONDITION (confirmed by the user): both probes switched to 10X, both
compensated on the scope's cal output, both tips on generator CH1's output.

Usage: python s0c_dual10x.py [@py] main     steps 3 and 4
       python s0c_dual10x.py [@py] swap     step 5 (20 MHz only, probes swapped)

Scope channels stay at PROBe 1X in the scope (U1K p.14); the x10 is applied
here in software. Generator: sine, High-Z (UTG p.11). Output ON only inside
this script, OFF in a finally block; every changed setting is restored.
"""
import cmath
import math
import statistics
import sys
import time
import traceback

import iolayer as io
import wave
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from t0b_iolayer import Saver, b01

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
MODE = next((a for a in sys.argv[1:] if a in ("main", "swap")), "main")
PROBE = 10.0
TARGET_CYCLES = 5.0                 # SPEC.md ScopeConfig.target_cycles
VERTICAL_DIVS = 8.0                 # ASSUMED on-screen divisions (not verified on this scope)
TARGET = (0.6, 0.8)                 # SPEC.md MeasureSettings.autorange_target, fraction of full scale p-p
out = {"backend": BACKEND, "mode": MODE, "probe_ratio_software": PROBE,
       "vertical_divs_assumed": VERTICAL_DIVS, "blocks": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def stats(xs):
    return dict(n=len(xs), mean=statistics.mean(xs), stdev=statistics.stdev(xs) if len(xs) > 1 else 0.0,
                min=min(xs), max=max(xs))


def phasor(volts, dt, f):
    a, b, c, rss = wave._fit3(volts, dt, f)
    amp = math.hypot(a, b)
    rms = math.sqrt(rss / len(volts))
    snr = 20 * math.log10((amp / math.sqrt(2)) / rms) if rms > 0 else float("inf")
    return complex(a, -b), c, snr


def autoselect(vpp_at_input, steps):
    """SPEC.md 8.3 rule: the most sensitive V/div whose p-p stays at or below
    the upper target fraction of full scale (VERTICAL_DIVS x V/div)."""
    for s in steps:
        if vpp_at_input <= TARGET[1] * VERTICAL_DIVS * s:
            return s
    return steps[-1]


def block(g, sc, f, amp_vpp, runs, label):
    b = {"label": label, "freq_set_hz": f, "gen_amp_set_vpp": amp_vpp}
    b["gen_amp_readback"] = g.set_verified(":CHANnel1:BASE:AMPLitude", io.GenFmt.num(amp_vpp),
                                           io.v_float, float(amp_vpp))          # UTG p.13
    b["gen_freq_readback"] = g.set_frequency(1, f)                               # UTG p.12
    b["timebase"] = sc.set_timebase(TARGET_CYCLES / f / sc.HDIV, "ceil")         # U1K p.16
    vd = autoselect(amp_vpp / PROBE, sc.vdiv_steps)
    for ch in (1, 2):
        sc.set_vdiv(ch, vd, "exact")                                             # U1K p.14
    b["vdiv_used"] = vd
    b["expected_fraction_of_8div"] = (amp_vpp / PROBE) / (VERTICAL_DIVS * vd)
    time.sleep(0.6)
    rows, errors = [], []
    c0 = dict(sc.stats)
    for i in range(runs):
        try:
            a = sc.acquire([1, 2])
            w1, w2 = a["waves"][1], a["waves"][2]
            fit = wave.sine_fit(w1["volts"], w1["dt"], f_hint=f)
            ff = fit["freq_hz"]
            P1, o1, s1 = phasor(w1["volts"], w1["dt"], ff)
            P2, o2, s2 = phasor(w2["volts"], w2["dt"], ff)
            H = P2 / P1
            rows.append(dict(
                f_fit=ff, vpp1=2 * abs(P1) * PROBE, vpp2=2 * abs(P2) * PROBE,
                gain_db=20 * math.log10(abs(H)), phase_deg=math.degrees(cmath.phase(H)),
                snr1=s1, snr2=s2, span1=max(w1["codes"]) - min(w1["codes"]),
                span2=max(w2["codes"]) - min(w2["codes"]), clipped=w1["clipped"] or w2["clipped"],
                forced=a["forced"], attempts=a["attempts"], states="->".join(a["states"]),
                total_s=a["total_s"], dt=w1["dt"], n=len(w1["codes"])))
        except Exception as e:
            errors.append(dict(run=i, error=f"{type(e).__name__}: {e}"))
            print(f"  run {i} ERROR {type(e).__name__}: {str(e)[:200]}")
    b["errors"] = errors
    b["layer_counters"] = {k: sc.stats.get(k, 0) - c0.get(k, 0)
                           for k in ("resyncs", "out_of_step", "reply_errors", "empty_blocks",
                                     "forced_triggers", "empty_retries", "set_retries", "rearms")}
    b["runs"] = rows
    if rows:
        col = lambda k: [r[k] for r in rows]
        s = b["summary"] = dict(
            ok=len(rows), of=runs, vpp1=stats(col("vpp1")), vpp2=stats(col("vpp2")),
            gain_db=stats(col("gain_db")), phase_deg=stats(col("phase_deg")),
            snr1=stats(col("snr1")), snr2=stats(col("snr2")), f_fit=stats(col("f_fit")),
            code_span1=stats(col("span1")), code_span2=stats(col("span2")),
            clipped=sum(col("clipped")), forced=sum(1 for r in rows if r["forced"]),
            second_attempts=sum(r["attempts"] > 1 for r in rows), acq_s=stats(col("total_s")),
            states=sorted(set(col("states"))), dt=rows[0]["dt"])
        # what auto-selection would pick from the MEASURED amplitude at each input
        s["autoselect_vdiv_ch1"] = autoselect(s["vpp1"]["mean"] / PROBE, sc.vdiv_steps)
        s["autoselect_vdiv_ch2"] = autoselect(s["vpp2"]["mean"] / PROBE, sc.vdiv_steps)
        g_, p_ = s["gain_db"], s["phase_deg"]
        print(f"[{label}] {f:g} Hz, gen {amp_vpp:g} Vpp, tb {b['timebase']:g}, V/div {vd:g}: {len(rows)}/{runs} ok")
        print(f"    Vpp x10: CH1 {s['vpp1']['mean']:.4f}  CH2 {s['vpp2']['mean']:.4f}   "
              f"code span {s['code_span1']['mean']:.0f} / {s['code_span2']['mean']:.0f} of 255")
        print(f"    gain  {g_['mean']:+.4f} dB  sd {g_['stdev']:.4f}  [{g_['min']:+.4f}, {g_['max']:+.4f}]")
        print(f"    phase {p_['mean']:+.4f} deg sd {p_['stdev']:.4f}  [{p_['min']:+.4f}, {p_['max']:+.4f}]"
              f"   (= {p_['mean'] / 360 / f * 1e12:+.0f} ps)")
        print(f"    SNR {s['snr1']['mean']:.1f} / {s['snr2']['mean']:.1f} dB (min {s['snr1']['min']:.1f} / "
              f"{s['snr2']['min']:.1f})   autoselect V/div CH1 {s['autoselect_vdiv_ch1']:g}  CH2 "
              f"{s['autoselect_vdiv_ch2']:g}   acq {s['acq_s']['mean']:.2f} s  forced {s['forced']}  "
              f"clipped {s['clipped']}")
        print(f"    counters {b['layer_counters']}  states {s['states']}")
    out["blocks"].append(b)
    return b


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

        g.configure_sine(1, 1000.0, 1.0, 0.0, "HIGHZ")               # UTG p.11-13
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="DC", bw_limit=False, offset_v=0.0)   # forces PROBe 1X
        sc.build_tables(1)
        out["tb_steps"], out["vdiv_steps"] = sc.tb_steps, sc.vdiv_steps
        for ch in (1, 2):
            sc.set_vdiv(ch, 0.02, "exact")
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")

        # Step 2: per-channel settings. The UPO1000 manual documents NO per-channel
        # delay / deskew command (CHANnel subsystem, p.12-15: BWLimit, COUPling,
        # DISPlay, INVert, PROBe:TYPe, PROBe, OFFSet, SCALe, UNITs, VERNier, SELect;
        # TIMebase subsystem, p.15-17: MODE, OFFSet, WINDow:OFFSet, SCALe,
        # WINDow:SCALe, HOLDoff). So the documented per-channel settings are logged.
        raw = lambda r: r
        chset = {}
        for ch in (1, 2):
            k = f":CHANnel{ch}"
            chset[ch] = {n: sc.query(f"{k}:{n}?", raw) for n in
                         ("PROBe", "PROBe:TYPe", "INVert", "VERNier", "UNITs", "BWLimit", "COUPling",
                          "OFFSet", "SCALe", "DISPlay")}
        out["channel_settings"] = chset
        out["timebase_offset"] = sc.query(":TIMebase:OFFSet?", io.v_float)        # U1K p.16
        out["timebase_mode"] = sc.query(":TIMebase:MODE?", raw)                   # U1K p.15-16
        out["cal_square_select"] = sc.query(":SYSTem:SQUare:SELect?", raw)        # U1K p.8
        out["acquire_type"] = sc.query(":ACQuire:TYPE?", raw)                     # U1K p.65
        print("channel settings:", chset)
        print("timebase offset", out["timebase_offset"], "mode", out["timebase_mode"],
              "| cal square", out["cal_square_select"], "| acquire", out["acquire_type"])

        sc.free_run()
        print("generator CH1 output ON")
        g.output(1, True)
        time.sleep(0.5)
        if MODE == "main":
            for f in (1e3, 1e6, 20e6):
                block(g, sc, f, 1.0, 50, "step3 1Vpp")
            for f in (1e3, 20e6):
                block(g, sc, f, 0.05, 20, "step4 50mVpp")
        else:
            block(g, sc, 20e6, 1.0, 50, "step5 swapped 1Vpp")
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
        print("saved", save(f"s0c_dual10x_{MODE}_{BACKEND.strip('@')}.json", out))


if __name__ == "__main__":
    main()
