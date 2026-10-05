"""Capture-speed benchmark (SPEC.md section 17, "Capture method"), through iolayer.py.

PRECONDITION (ask the user first): both 10X probes on generator CH1's output, as in
Milestone 0c. Nobody touches the scope front panel during the run.

Usage: python s6_capbench.py [@py] [runs]

Compares two ways of getting CH1 and CH2 from ONE acquisition, at 1 kHz, 1 MHz, 20 MHz:
  A  single shot    iolayer.ScopeIO.acquire(): ':TRIGger:SWEep SINGle', poll for STOP, read.
  B  free running   sweep AUTO running, wait max(0.3 s, 30 x timebase) (M0 rule), ':STOP',
                    poll for STOP, read, restart with sweep SINGle then AUTO.
For each: seconds per capture with a breakdown, failures, and the CH2 - CH1 delay, so a
method that is faster but moves the channel alignment (HW_REPORT.md 12.11) is caught.

No ':RUN' is sent anywhere (the layer refuses it). Generator output is ON only inside
this script and OFF in a finally block; every changed setting is restored.
"""
import cmath
import math
import sys
import time
import traceback

import iolayer as io
import wave
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from s0c_dual10x import PROBE, TARGET_CYCLES, autoselect, phasor, stats
from t0b_iolayer import Saver, b01

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
RUNS = next((int(a) for a in sys.argv[1:] if a.isdigit()), 20)
FREQS = (1e3, 1e6, 20e6)
AMP_VPP = 1.0
out = {"backend": BACKEND, "runs_per_block": RUNS, "blocks": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def measure(waves, f):
    w1, w2 = waves[1], waves[2]
    ff = wave.sine_fit(w1["volts"], w1["dt"], f_hint=f)["freq_hz"]
    P1, _, s1 = phasor(w1["volts"], w1["dt"], ff)
    P2, _, s2 = phasor(w2["volts"], w2["dt"], ff)
    H = P2 / P1
    ph = math.degrees(cmath.phase(H))
    return dict(gain_db=20 * math.log10(abs(H)), phase_deg=ph, delay_ns=ph / 360 / ff * 1e9,
                snr1=s1, snr2=s2, clipped=w1["clipped"] or w2["clipped"])


def single_shot(sc, f):
    t0 = time.perf_counter()
    a = sc.acquire([1, 2])
    r = measure(a["waves"], f)
    r.update(cycle_s=time.perf_counter() - t0, wait_s=a["wait_s"], fetch_s=a["total_s"] - a["wait_s"],
             attempts=a["attempts"], forced=a["forced"], states="->".join(a["states"]))
    return r


class FreeRun:
    """Method B. The scope runs in sweep AUTO between captures."""

    def __init__(self, sc):
        self.sc = sc
        self.t_restart = None

    def start(self):
        self.sc.free_run()                                           # U1K p.36
        self.t_restart = time.perf_counter()

    def capture(self, f, timeout_s=5.0):
        sc = self.sc
        t0 = time.perf_counter()
        run_s = max(0.3, 30 * sc.tb)                                 # M0 rule: a screen record must exist
        while time.perf_counter() - self.t_restart < run_s:
            time.sleep(0.005)
        t1 = time.perf_counter()
        before = sc.status()                                         # U1K p.37
        sc.write(":STOP")                                            # U1K p.6
        t_stop = None
        while True:                                                  # STOP must hold 0.1 s (0b finding)
            st = sc.status()
            now = time.perf_counter()
            t_stop = (t_stop if t_stop is not None else now) if st == "STOP" else None
            if t_stop is not None and now - t_stop >= 0.1:
                break
            if now - t1 > timeout_s:
                raise io.IOErrorBase("status did not reach STOP after :STOP (last %s)" % st)
            time.sleep(0.01)
        t2 = time.perf_counter()
        waves = {ch: sc._fetch_channel(ch) for ch in (1, 2)}
        t3 = time.perf_counter()
        # restart: from a :STOP with the sweep already AUTO, writing AUTO again does nothing
        # (t0b_iolayer.restart), so go through SINGle; the change back to AUTO restarts it
        sc.write(":TRIGger:SWEep SINGle")                            # U1K p.36
        sc.free_run()                                                # U1K p.36
        self.t_restart = t4 = time.perf_counter()
        r = measure(waves, f)
        r.update(cycle_s=t4 - t0, run_wait_s=t1 - t0, stop_s=t2 - t1, fetch_s=t3 - t2, restart_s=t4 - t3,
                 status_before_stop=before)
        return r


def block(g, sc, f, method, fr):
    b = {"method": method, "freq_set_hz": f}
    b["gen_freq_readback"] = g.set_frequency(1, f)                               # UTG p.12
    b["timebase"] = sc.set_timebase(TARGET_CYCLES / f / sc.HDIV, "ceil")         # U1K p.16
    time.sleep(0.6)
    rows, errors = [], []
    c0 = dict(sc.stats)
    if method == "B free-run":
        fr.start()
    t_block = time.perf_counter()
    for i in range(RUNS):
        try:
            rows.append(single_shot(sc, f) if method == "A single-shot" else fr.capture(f))
        except Exception as e:
            errors.append(dict(run=i, error=f"{type(e).__name__}: {e}"))
            print(f"  run {i} ERROR {type(e).__name__}: {str(e)[:200]}")
            try:
                sc.resync()
                if method == "B free-run":
                    fr.start()
            except Exception as e2:
                errors.append(dict(run=i, error=f"recovery failed: {type(e2).__name__}: {e2}"))
                break
    b["block_s"] = time.perf_counter() - t_block
    b["errors"], b["runs"] = errors, rows
    b["layer_counters"] = {k: sc.stats.get(k, 0) - c0.get(k, 0)
                           for k in ("resyncs", "out_of_step", "reply_errors", "empty_blocks",
                                     "forced_triggers", "empty_retries", "set_retries", "rearms")}
    if rows:
        col = lambda k: [r[k] for r in rows]
        s = b["summary"] = dict(ok=len(rows), of=RUNS, per_capture_s=b["block_s"] / RUNS,
                                clipped=sum(col("clipped")))
        for k in rows[0]:
            if isinstance(rows[0][k], float):
                s[k] = stats(col(k))
        for k in ("states", "status_before_stop"):
            if k in rows[0]:
                s[k] = sorted(set(col(k)))
        d = s["delay_ns"]
        parts = "  ".join(f"{k[:-2]} {s[k]['mean']:.3f}" for k in
                          ("run_wait_s", "wait_s", "stop_s", "fetch_s", "restart_s") if k in s)
        print(f"[{method}] {f:g} Hz, tb {b['timebase']:g}: {len(rows)}/{RUNS} ok, "
              f"{s['per_capture_s']:.3f} s per capture  ({parts})")
        print(f"    delay CH2-CH1 {d['mean']:+.3f} ns sd {d['stdev']:.3f} [{d['min']:+.3f}, {d['max']:+.3f}]   "
              f"gain {s['gain_db']['mean']:+.4f} dB sd {s['gain_db']['stdev']:.4f}   "
              f"SNR {s['snr1']['mean']:.1f} / {s['snr2']['mean']:.1f} dB   clipped {s['clipped']}")
        print(f"    counters {b['layer_counters']}  {s.get('states') or s.get('status_before_stop')}")
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

        g.configure_sine(1, 1000.0, AMP_VPP, 0.0, "HIGHZ")           # UTG p.11-13
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="DC", bw_limit=False, offset_v=0.0)   # forces PROBe 1X
        sc.build_tables(1)
        vd = autoselect(AMP_VPP / PROBE, sc.vdiv_steps)
        for ch in (1, 2):
            sc.set_vdiv(ch, vd, "exact")                             # U1K p.14
        out["vdiv_used"] = vd
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.free_run()
        print("generator CH1 output ON")
        g.output(1, True)
        time.sleep(0.5)
        fr = FreeRun(sc)
        # A, B, then A again: the second A shows whether B moved the channel alignment
        for method in ("A single-shot", "B free-run", "A single-shot"):
            for f in FREQS:
                block(g, sc, f, method, fr)
        d20 = [b["summary"]["delay_ns"] for b in out["blocks"] if b["freq_set_hz"] == 20e6 and "summary" in b]
        if d20:
            lo, hi = min(x["min"] for x in d20), max(x["max"] for x in d20)
            out["delay_20MHz_range_ns"] = [lo, hi]
            out["alignment_moved"] = (hi - lo) > 1.0
            print(f"20 MHz delay over all blocks: {lo:+.3f} to {hi:+.3f} ns -> "
                  f"alignment {'MOVED' if out['alignment_moved'] else 'did not move'}")
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
        print("saved", save(f"s6_capbench_{BACKEND.strip('@')}.json", out))


if __name__ == "__main__":
    main()
