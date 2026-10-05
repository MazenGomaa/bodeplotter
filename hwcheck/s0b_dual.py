"""Milestone 0b step 3: dual-channel test through the I/O layer.

PRECONDITION (confirmed by the user): generator CH1 -> BNC tee -> scope CH1
and scope CH2. Both scope channels therefore see the same signal, so the
measured transfer CH2/CH1 should be about 0 dB and 0 degrees.

Usage: python s0b_dual.py [@py|@ivi] [runs]

For each of 1 kHz, 1 MHz and 20 MHz: `runs` single-shot acquisitions, each one
read on BOTH channels from the SAME stopped record (ScopeIO.acquire). Per run a
sine is fitted to both channels at one common frequency and the complex ratio
CH2/CH1 gives gain (dB) and phase (degrees).

This is the only 0b script that switches a generator output on. The output is
switched OFF in a finally block and every changed setting is restored.
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
RUNS = next((int(a) for i, a in enumerate(sys.argv[1:], 1) if a.isdigit() and sys.argv[i - 1] != "--probe"), 50)
FREQS = [1e3, 1e6, 20e6]
TARGET_CYCLES = 5.0          # SPEC.md ScopeConfig.target_cycles
AMP_VPP = 1.0
# --probe N: passive probes of ratio N on BOTH scope inputs (the user has no BNC
# tee, so both probe tips sit on generator CH1). The scope stays at 1X (M0
# finding S2: waveform data are input-referred whatever the scope's ratio), so
# the input sees AMP_VPP / N and volts are multiplied by N here in software.
PROBE = next((float(sys.argv[i + 1]) for i, a in enumerate(sys.argv[:-1]) if a == "--probe"), 1.0)
VDIV = 0.2 / PROBE           # 1 Vpp at the tip = 5 of ~10 ADC divisions
out = {"backend": BACKEND, "runs_per_frequency": RUNS, "probe_ratio_software": PROBE,
       "wiring": "both scope probes on generator CH1 (no BNC tee available)", "points": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def stats(xs):
    return dict(n=len(xs), mean=statistics.mean(xs), stdev=statistics.stdev(xs) if len(xs) > 1 else 0.0,
                min=min(xs), max=max(xs))


def phasor(volts, dt, f):
    a, b, c, rss = wave._fit3(volts, dt, f)          # v = a*cos + b*sin + c
    amp = math.hypot(a, b)
    rms = math.sqrt(rss / len(volts))
    snr = 20 * math.log10((amp / math.sqrt(2)) / rms) if rms > 0 else float("inf")
    return complex(a, -b), c, snr                    # amplitude*exp(j*phase), offset, SNR dB


def main():
    rm = open_rm(BACKEND)
    g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID), log=log)
    sc = io.ScopeIO(rm, find_resource(rm, SCOPE_VID, SCOPE_PID), log=log)
    gs = ss = None
    sweep0 = None
    try:
        out["gen_idn"] = g.connect()
        out["scope_idn"] = sc.connect(build_tables=False)
        g.output(1, False)
        g.output(2, False)

        # ---- remember everything that will be changed
        num, probe = io.GenFmt.num, io.ScopeFmt.probe
        gs = Saver(g)
        c = ":CHANnel1"
        gs.save(c + ":BASE:OFFSet", io.v_float, num)
        gs.save(c + ":BASE:AMPLitude", io.v_float, num)
        gs.save(c + ":BASE:FREQuency", io.v_float, num)
        gs.save(c + ":AMPLitude:UNIT", g.V_UNIT)
        gs.save(c + ":LOAD", io.v_float, num)
        gs.save(c + ":BASE:WAVe", g.V_WAVE)
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

        # ---- configure (outputs still OFF)
        g.configure_sine(1, FREQS[0], AMP_VPP, 0.0, "HIGHZ")
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="DC", bw_limit=False, offset_v=0.0)
        sc.build_tables(1)
        out["tb_steps"], out["vdiv_steps"] = sc.tb_steps, sc.vdiv_steps
        for ch in (1, 2):
            sc.set_vdiv(ch, VDIV, "exact")
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.free_run()

        print("generator CH1 output ON")
        g.output(1, True)
        out["gen_output_on"] = g.output(1)
        time.sleep(0.5)

        for f in FREQS:
            p = {"freq_set_hz": f}
            p["gen_freq_readback"] = g.set_frequency(1, f)
            want_tb = TARGET_CYCLES / f / sc.HDIV
            p["timebase_wanted"] = want_tb
            p["timebase"] = sc.set_timebase(want_tb, "ceil")
            p["cycles_on_screen"] = sc.HDIV * p["timebase"] * f
            time.sleep(0.5)
            runs, errors = [], []
            b0 = dict(sc.stats)
            t_start = time.perf_counter()
            for i in range(RUNS):
                try:
                    a = sc.acquire([1, 2])
                    w1, w2 = a["waves"][1], a["waves"][2]
                    if w1["dt"] != w2["dt"] or len(w1["codes"]) != len(w2["codes"]):
                        raise ValueError(f"channels differ: dt {w1['dt']} / {w2['dt']}")
                    fit = wave.sine_fit(w1["volts"], w1["dt"], f_hint=f)     # frequency from CH1
                    ff = fit["freq_hz"]
                    P1, o1, snr1 = phasor(w1["volts"], w1["dt"], ff)
                    P2, o2, snr2 = phasor(w2["volts"], w2["dt"], ff)
                    H = P2 / P1
                    runs.append(dict(
                        f_fit=ff, vpp1=2 * abs(P1) * PROBE, vpp2=2 * abs(P2) * PROBE,
                        gain_db=20 * math.log10(abs(H)),
                        phase_deg=math.degrees(cmath.phase(H)), snr1=snr1, snr2=snr2, off1=o1, off2=o2,
                        dt=w1["dt"], n=len(w1["codes"]), clipped=w1["clipped"] or w2["clipped"],
                        states=a["states"], wait_s=a["wait_s"], total_s=a["total_s"],
                        forced=a["forced"], attempts=a["attempts"],
                        codes1=[min(w1["codes"]), max(w1["codes"])], codes2=[min(w2["codes"]), max(w2["codes"])]))
                except Exception as e:
                    errors.append(dict(run=i, error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()))
                    print(f"  run {i} ERROR {type(e).__name__}: {e}")
            p["elapsed_s"] = time.perf_counter() - t_start
            p["errors"] = errors
            p["layer_counters"] = {k: sc.stats.get(k, 0) - b0.get(k, 0)
                                   for k in ("resyncs", "out_of_step", "reply_errors", "empty_blocks",
                                             "forced_triggers", "empty_retries", "set_retries", "rearms")}
            p["runs"] = runs
            if runs:
                p["summary"] = dict(
                    ok_runs=len(runs),
                    gain_db=stats([r["gain_db"] for r in runs]),
                    phase_deg=stats([r["phase_deg"] for r in runs]),
                    skew_ps=stats([r["phase_deg"] / 360.0 / f * 1e12 for r in runs]),
                    f_fit_hz=stats([r["f_fit"] for r in runs]),
                    vpp1=stats([r["vpp1"] for r in runs]), vpp2=stats([r["vpp2"] for r in runs]),
                    snr1_db=stats([r["snr1"] for r in runs]), snr2_db=stats([r["snr2"] for r in runs]),
                    acq_total_s=stats([r["total_s"] for r in runs]),
                    forced=sum(1 for r in runs if r["forced"]), second_attempts=sum(r["attempts"] > 1 for r in runs),
                    clipped=sum(r["clipped"] for r in runs), dt=runs[0]["dt"], points=runs[0]["n"],
                    state_sequences=sorted({"->".join(r["states"]) for r in runs}))
                s = p["summary"]
                print(f"{f:>10g} Hz  tb {p['timebase']:g} s/div ({p['cycles_on_screen']:.1f} cycles)  "
                      f"{len(runs)}/{RUNS} ok")
                print(f"    gain  {s['gain_db']['mean']:+.4f} dB  sd {s['gain_db']['stdev']:.4f}  "
                      f"[{s['gain_db']['min']:+.4f}, {s['gain_db']['max']:+.4f}]")
                print(f"    phase {s['phase_deg']['mean']:+.4f} deg sd {s['phase_deg']['stdev']:.4f}  "
                      f"[{s['phase_deg']['min']:+.4f}, {s['phase_deg']['max']:+.4f}]  "
                      f"(= {s['skew_ps']['mean']:+.1f} ps)")
                print(f"    f_fit {s['f_fit_hz']['mean']:.6g} Hz  Vpp {s['vpp1']['mean']:.4f} / {s['vpp2']['mean']:.4f}  "
                      f"SNR {s['snr1_db']['mean']:.1f} / {s['snr2_db']['mean']:.1f} dB  "
                      f"acq {s['acq_total_s']['mean']:.2f} s  forced {s['forced']}  counters {p['layer_counters']}")
                print(f"    states {s['state_sequences']}")
            out["points"].append(p)
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
            out["scope_error_queue"] = sc.error_queue()
        except Exception as e:
            out["scope_restore_failures"] = [str(e)]
        out["scope_stats"], out["gen_stats"] = dict(sc.stats), dict(g.stats)
        print("restore failures: gen", out["gen_restore_failures"], "scope", out["scope_restore_failures"])
        print("scope stats", out["scope_stats"])
        g.close()
        sc.close()
        rm.close()
        print("saved", save(f"s0b_dual_{BACKEND.strip('@')}.json", out))


if __name__ == "__main__":
    main()
