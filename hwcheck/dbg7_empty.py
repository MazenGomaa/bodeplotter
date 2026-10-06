"""Milestone 7 debug: when does a RUNNING scope answer ':WAVeform:DATA?' with an empty reply?

Run with the APP venv:
    .venv\\Scripts\\python.exe -W ignore hwcheck\\dbg7_empty.py [N] [--ch REF DUT] [--amp VPP]

Fast preview reads both channels from the running scope (HW_REPORT.md 13.21, 13.23). In
5 of 9 full-range sweeps the SECOND channel read came back empty once, always at a
timebase of 200 or 500 ns/div. This script repeats what a sweep does there (frequency
steps at 2e-07 s/div), reads the trigger status just before every channel read, and
reports which statuses the empty replies follow. An empty reply is not retried in place:
the driver resyncs, the scope is restarted and the loop goes on.

PRECONDITION: both probes on generator CH1 (through connection), both 10X.
Generator output is on during the run and switched off in a finally block. No ':RUN'.
"""
import logging
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from common import save                              # prints this script's hash and git commit

from bodeplot.drivers import connect
from bodeplot.drivers.base import DriverError
from bodeplot.drivers.scpi import EmptyBlock, InstrumentUnresponsive
from bodeplot.measure.meters import DualChannelScopeMeter
from bodeplot.models import MeasureSettings, ScopeConfig, StimulusConfig

logging.basicConfig(level=logging.ERROR)
argv = sys.argv[1:]


def opt(name, n, cast, default):
    if name in argv:
        i = argv.index(name)
        vals = [cast(x) for x in argv[i + 1:i + 1 + n]]
        del argv[i:i + 1 + n]
        return vals
    return default


REF, DUT = opt("--ch", 2, int, [1, 2])
AMP = opt("--amp", 1, float, [5.0])[0]
# --sentinel: after an empty reply only check that the link is in step ('*IDN?' five times);
# resync only if it is not. Shows whether an empty reply of a RUNNING scope needs a resync.
SENTINEL = "--sentinel" in argv
if SENTINEL:
    argv.remove("--sentinel")
# --driver: call the driver's acquire_running and print where a slow call spent its time
DRIVER = "--driver" in argv
if DRIVER:
    argv.remove("--driver")
N = int(argv[0]) if argv else 200
FREQS = [1852237.46, 2000000.0, 2159550.32, 2331828.80, 2517850.82, 2718712.78, 2935598.54, 3169786.38]
out = {"n": N, "channels": [REF, DUT], "amp_vpp": AMP, "reads": []}


def main():
    session = connect.open_session("py")
    gen, scope = session.source, session.digitizer
    stim, meas = StimulusConfig(amp_vpp=AMP), MeasureSettings()
    meter = DualChannelScopeMeter(scope, ScopeConfig(ref_channel=REF, dut_channel=DUT,
                                                     probe_atten={REF: 10.0, DUT: 10.0}))
    print("generator: %s\nscope:     %s\n%d pair reads, %g Vpp, CH%d / CH%d" % (
        session.source_idn, session.digitizer_idn, N, AMP, REF, DUT), flush=True)
    seen, empties = Counter(), []
    try:
        session.begin_measurement()
        gen.configure_sine(stim.gen_channel, FREQS[0], stim.amp_vpp, stim.offset_v, stim.load)
        meter.prepare(stim.amp_vpp, stim.offset_v)
        gen.set_output(stim.gen_channel, True)
        state = meter.initial_state()
        meter.measure(FREQS[0], meas, state)             # auto-range and timebase, single shot
        print("timebase %g s/div" % state.timebase)
        scope.free_run()
        time.sleep(0.5)
        if DRIVER:
            # the driver's own acquire_running, with every status poll and channel read timed;
            # the trace of a slow call is printed
            trace = []
            for fn in ("status", "_fetch_channel", "_sentinel", "resync"):
                def wrap(inner=getattr(scope, fn), fn=fn):
                    def w(*a, **kw):
                        t = time.perf_counter()
                        try:
                            r = inner(*a, **kw)
                            trace.append((round(t - t0, 3), fn, r if fn == "status" else "ok",
                                          round(time.perf_counter() - t, 3)))
                            return r
                        except Exception as e:
                            trace.append((round(t - t0, 3), fn, type(e).__name__, round(time.perf_counter() - t, 3)))
                            raise
                    return w
                setattr(scope, fn, wrap())
            slow = 0
            for k in range(N):
                f = FREQS[k % len(FREQS)]
                gen.set_frequency(stim.gen_channel, f)
                time.sleep(max(meas.settle_ms / 1000.0, meas.settle_cycles / f))
                trace.clear()
                t0 = time.perf_counter()
                scope.acquire_running([REF, DUT], 5.0)
                dt = time.perf_counter() - t0
                if dt > 0.5:
                    slow += 1
                    print("   read %3d took %.2f s:" % (k, dt), flush=True)
                    last = None
                    for e in trace:                      # runs of the same status poll are folded
                        key = (e[1], e[2])
                        if key != last or e[1] != "status":
                            print("      t=%.3f  %-14s %-10s %.3f s" % e, flush=True)
                        last = key
                    out["reads"].append(dict(k=k, f=f, seconds=dt, trace=list(trace)))
            print("slow reads: %d of %d; scope counters %s" % (slow, N, dict(scope.stats)))
            return
        for k in range(N):
            f = FREQS[k % len(FREQS)]
            gen.set_frequency(stim.gen_channel, f)
            time.sleep(max(meas.settle_ms / 1000.0, meas.settle_cycles / f))
            rec = dict(k=k, f=f, status=[], empty=None)
            try:
                for ch in (REF, DUT):
                    t = time.perf_counter()
                    st = scope.status()
                    rec["status"].append(st)
                    seen[(ch == DUT, st)] += 1
                    scope._fetch_channel(ch)
                    rec.setdefault("t", []).append(round(time.perf_counter() - t, 3))
            except EmptyBlock as e:
                rec["empty"] = "CH%d after status %s" % (ch, rec["status"][-1])
                empties.append(rec)
                print("   read %3d  %.0f Hz: EMPTY on CH%d, status before the read: %s   (%s)" % (
                    k, f, ch, rec["status"], e), flush=True)
                if SENTINEL:
                    # is the link still in step? five '*IDN?' 50 ms apart, raw replies recorded.
                    # This is what the resync does too, without the device clear before it.
                    raws = []
                    for _ in range(5):
                        scope.t.write("*IDN?")
                        r = scope.t.read()
                        raws.append((len(r), r[:12].decode("ascii", "replace")))
                        time.sleep(0.05)
                    rec["sentinel"] = raws
                    clean = all(txt.startswith("UNI-T") for _, txt in raws)
                    print("      sentinel replies: %s -> %s" % (raws, "in step, no resync" if clean else "OUT OF STEP"),
                          flush=True)
                    if clean:
                        out["reads"].append(rec)
                        continue
                scope.resync()
                scope.free_run()
                time.sleep(0.5)
            out["reads"].append(rec)
        print("\nstatus seen just before a read (second channel?, status): count")
        for key, n in sorted(seen.items()):
            print("   %-6s %-7s %d" % ("DUT" if key[0] else "REF", key[1], n))
        print("empty replies: %d of %d pair reads" % (len(empties), N))
        for r in empties:
            print("   ", r["empty"], r["status"])
        out["scope_stats"] = dict(scope.stats)
    except InstrumentUnresponsive as e:
        print("\nTHE SCOPE STOPPED ANSWERING: %s\n%s" % (e, getattr(e, "advice", "")))
        session.mark_dead(str(e))
    except DriverError as e:
        print("\nSTOPPED on a driver error: %s" % e)
    finally:
        gen.safe_off()
        if session.dead_reason is None:
            try:
                session.end_measurement()
            except Exception as e:
                print("could not restore the scope:", e)
        session.close()
        print("generator outputs off, connections closed")
        print("saved", save(os.path.join("m7", "dbg7_empty.json"), out))


if __name__ == "__main__":
    main()
