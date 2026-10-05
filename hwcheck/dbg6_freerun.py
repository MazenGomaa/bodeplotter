"""Why did every second free-running capture fail in s6_capbench.py (HW_REPORT.md 12.12)?

The failing step was: after a restart by ':TRIGger:SWEep SINGle' then ':TRIGger:SWEep AUTO',
the next ':STOP' did not bring ':TRIGger:STATus?' to STOP within 5 s.

PRECONDITION: both 10X probes on generator CH1's output (as in s6_capbench.py).
Usage: python dbg6_freerun.py [@py] [cycles]

Each variant is one way of restarting the scope after a ':STOP'. Per cycle: restart, run
for RUN_S, ':STOP', poll the status; if it does not stop, send ':STOP' again (up to 3 in
all). When it stops, both channels are read and the CH2 - CH1 delay at 20 MHz is logged.

No ':RUN' is sent (the layer refuses it). Generator output ON only inside this script,
OFF in a finally block; every changed setting is restored.
"""
import sys
import time
import traceback

import iolayer as io
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from s0c_dual10x import PROBE, TARGET_CYCLES, autoselect, stats
from s6_capbench import measure
from t0b_iolayer import Saver, b01

BACKEND = next((a for a in sys.argv[1:] if a.startswith("@")), "@py")
CYCLES = next((int(a) for a in sys.argv[1:] if a.isdigit()), 12)
F = 20e6
out = {"backend": BACKEND, "cycles": CYCLES, "freq_hz": F, "variants": [], "log": []}


def log(msg):
    out["log"].append(msg)
    print("   .", msg)


def sweep(sc, mode):
    sc.write(":TRIGger:SWEep " + mode)                               # U1K p.36


def sweep_q(sc):
    return sc.query(":TRIGger:SWEep?", io.V_SWEEP)                   # U1K p.36


def watch_for(sc, want, seconds):
    """Poll until the status reads `want`. Returns (timeline, seen)."""
    t0 = time.perf_counter()
    tl = []
    while True:
        st = sc.status()
        el = time.perf_counter() - t0
        if not tl or tl[-1][1] != st:
            tl.append((round(el, 2), st))
        if st == want:
            return tl, True
        if el >= seconds:
            return tl, False
        time.sleep(0.01)


def watch(sc, seconds, until_stop_held=None):
    """Poll ':TRIGger:STATus?' (U1K p.37). Returns (timeline, stopped)."""
    t0 = time.perf_counter()
    tl, t_stop = [], None
    while True:
        st = sc.status()
        el = time.perf_counter() - t0
        if not tl or tl[-1][1] != st:
            tl.append((round(el, 2), st))
        t_stop = (t_stop if t_stop is not None else el) if st == "STOP" else None
        if until_stop_held is not None and t_stop is not None and el - t_stop >= until_stop_held:
            return tl, True
        if el >= seconds:
            return tl, False
        time.sleep(0.01)


# name, restart function, run time before ':STOP'
def r_single_auto(sc):
    sweep(sc, "SINGle")
    sweep(sc, "AUTO")


def r_auto_only(sc):
    sweep(sc, "AUTO")


def r_normal_auto(sc):
    sweep(sc, "NORMal")
    sweep(sc, "AUTO")


def r_single_normal(sc):                             # free-run in NORMal sweep instead of AUTO
    sweep(sc, "SINGle")
    sweep(sc, "NORMal")


# run_s None = wait until the status reads TRIGED (at most 3 s) and only then send :STOP.
# Runs 1 and 2 of this script (results/dbg6_freerun_py_run1.json, _run2.json) showed that a
# :STOP sent before TRIGED either does not last or stops the scope with no record (empty
# waveform block). Their third variant ("SINGle, wait for its STOP, then AUTO, run 0.3 s")
# was removed: its wait returned at once on the stale STOP, and it gave 8 of 8 empty blocks.
VARIANTS = (
    ("1 SINGle then AUTO, run 0.3 s (as in s6_capbench)", r_single_auto, 0.3),
    ("2 SINGle then AUTO, run 1.5 s", r_single_auto, 1.5),
    ("3 SINGle then AUTO, :STOP once TRIGED", r_single_auto, None),
    ("4 AUTO only, :STOP once TRIGED", r_auto_only, None),
    ("5 NORMal then AUTO, :STOP once TRIGED", r_normal_auto, None),
    ("6 SINGle then NORMal (free-run in NORMal), :STOP once TRIGED", r_single_normal, None),
)
ONLY = [a[2:] for a in sys.argv[1:] if a.startswith("v=")]
if ONLY:
    VARIANTS = tuple(v for v in VARIANTS if v[0][0] in ONLY[0].split(","))


def run_variant(sc, name, restart, run_s):
    v = {"name": name, "run_s": run_s, "cycles": []}
    print("\n==", name)
    # known start: a stopped scope with a record (one layer single shot), sweep back to AUTO
    sc.acquire([1, 2])
    for i in range(CYCLES):
        c = {"i": i}
        try:
            t0 = time.perf_counter()
            c["status_before_restart"] = sc.status()
            c["restart_timeline"] = restart(sc)
            c["restart_s"] = time.perf_counter() - t0
            if run_s is None:
                tl, running = watch_for(sc, "TRIGED", 3.0)
                c["to_triged_s"] = time.perf_counter() - t0
            else:
                (tl, _), running = watch(sc, run_s), True
            c["run_timeline"] = tl
            c["sweep_before_stop"] = sweep_q(sc)
            if not running:
                c["never_triged"] = True         # no :STOP and no fetch: there may be no record
                c["stops_needed"] = "not sent"
                v["cycles"].append(c)
                print(f"  {i:2d} never TRIGED: run {tl} sweep {c['sweep_before_stop']}")
                sc.acquire([1, 2])               # back to a stopped scope with a record
                continue
            c["stop_timelines"] = []
            stopped = False
            t1 = time.perf_counter()
            for n in (1, 2, 3):
                sc.write(":STOP")                                    # U1K p.6
                tl, stopped = watch(sc, 2.0, until_stop_held=0.1)
                c["stop_timelines"].append(tl)
                if stopped:
                    c["stops_needed"] = n
                    break
            c["stop_s"] = time.perf_counter() - t1
            if stopped:
                waves = {ch: sc._fetch_channel(ch) for ch in (1, 2)}
                c.update(measure(waves, F))
            else:
                c["stops_needed"] = None
            c["cycle_s"] = time.perf_counter() - t0
        except Exception as e:
            c["error"] = f"{type(e).__name__}: {e}"
            print(f"  cycle {i} ERROR {c['error'][:200]}")
            sc.resync()
            sc.acquire([1, 2])
        v["cycles"].append(c)
        print(f"  {i:2d} before {c.get('status_before_restart')}  run {c.get('run_timeline')}  "
              f"sweep {c.get('sweep_before_stop')}  stops {c.get('stops_needed')}  "
              f"after STOP {c.get('stop_timelines')}  "
              + (f"delay {c['delay_ns']:+.3f} ns" if "delay_ns" in c else ""))
    cyc = v["cycles"]
    need = [c.get("stops_needed") for c in cyc]
    v["summary"] = dict(first_stop_ok=need.count(1), second_stop=need.count(2), third_stop=need.count(3),
                        never=sum(1 for c in cyc if "error" not in c and c.get("stops_needed") is None),
                        errors=sum("error" in c for c in cyc))
    d = [c["delay_ns"] for c in cyc if "delay_ns" in c]
    if d:
        v["summary"]["delay_ns"] = stats(d)
    v["summary"]["never_triged"] = sum(1 for c in cyc if c.get("never_triged"))
    xs = [c["to_triged_s"] for c in cyc if "to_triged_s" in c and not c.get("never_triged")]
    if xs:
        v["summary"]["to_triged_s"] = stats(xs)
    ok = [c["cycle_s"] for c in cyc if c.get("stops_needed") == 1 and "cycle_s" in c]
    if ok:
        v["summary"]["cycle_s_first_stop"] = stats(ok)
    print("  summary:", {k: (round(x["mean"], 3) if isinstance(x, dict) else x) for k, x in v["summary"].items()})
    out["variants"].append(v)
    # leave the scope stopped-with-record or recover, whatever happened
    if v["summary"]["never"]:
        sc.resync()


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
        sweep0 = sweep_q(sc)

        g.configure_sine(1, F, 1.0, 0.0, "HIGHZ")                    # UTG p.11-13
        for ch in (1, 2):
            sc.configure_channel(ch, coupling="DC", bw_limit=False, offset_v=0.0)   # forces PROBe 1X
        # Step tables as measured in 0b (HW_REPORT.md 12): not walked again here, because the
        # first run of this script froze the scope during that walk (2026-10-06).
        sc.tb_steps = [1e-9, 2e-9, 5e-9, 10e-9, 25e-9, 50e-9] + [m * 10.0 ** e for e in range(-7, -2)
                                                                 for m in (1, 2, 5)] + [0.01, 0.02]
        sc.vdiv_steps = [m * 10.0 ** e for e in range(-4, 2) for m in (1, 2, 5)][2:-2]
        vd = autoselect(1.0 / PROBE, sc.vdiv_steps)
        for ch in (1, 2):
            sc.set_vdiv(ch, vd, "exact")                             # U1K p.14
        sc.set_timebase(TARGET_CYCLES / F / sc.HDIV, "ceil")         # U1K p.16
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.free_run()
        print("generator CH1 output ON")
        g.output(1, True)
        time.sleep(0.8)
        a = sc.acquire([1, 2])
        m = measure(a["waves"], F)
        out["baseline"] = m
        print(f"baseline single shot: delay {m['delay_ns']:+.3f} ns, SNR {m['snr1']:.1f} / {m['snr2']:.1f} dB")
        if min(m["snr1"], m["snr2"]) < 15:
            raise RuntimeError("no clean 20 MHz signal on both channels: are both probes on generator CH1?")
        for name, restart, run_s in VARIANTS:
            run_variant(sc, name, restart, run_s)
        a = sc.acquire([1, 2])
        out["final"] = measure(a["waves"], F)
        print(f"\nfinal single shot: delay {out['final']['delay_ns']:+.3f} ns")
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
        print("saved", save(f"dbg6_freerun_{BACKEND.strip('@')}.json", out))


if __name__ == "__main__":
    main()
