"""Milestone 7: the scope's own measurements (':MEASure:...') against the sine fit.

Run with the APP venv:
    .venv\\Scripts\\python.exe -W ignore hwcheck\\s7_builtin.py [--ch REF DUT] [--amp VPP]

The app has a "Scope built-in" method that the real driver does not offer, because
':MEASure:PHASe?' was never sent to this scope (SPEC.md 9, HW_REPORT.md section 5).
Queries only, all from the UPO1000 programming manual:
    :MEASure:VPP? <source>                 U1K p.30   peak-to-peak, V
    :MEASure:VAMPlitude? <source>          U1K p.31   amplitude (top - base), V
    :MEASure:VRMS? CYCLe,<source>          U1K p.32   RMS over whole cycles, V
    :MEASure:PHASe? <source1>,<source2>    U1K p.30   degrees
    :MEASure:PDELay? <source1>,<source2>   U1K p.30   delay at the rising edges, s
The manual (p.27) says a measurement query switches the measurement on by itself; nothing
is set, cleared or switched off here (':MEASure:CLEar' and ':MEASure:ALL' are not sent),
so a measurement read-out may stay on the scope's screen afterwards.

At each frequency: the app's sine fit from a single shot (the reference result), then the
queries on that STOPPED record, then the same queries on the RUNNING scope, each several
times with the time every query takes.

PRECONDITION: both probes on generator CH1 (through connection), both 10X.
Generator output is on during the run and switched off in a finally block. No ':RUN'.
"""
import logging
import math
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from common import save                              # prints this script's hash and git commit

from bodeplot.drivers import connect
from bodeplot.drivers.base import DriverError
from bodeplot.drivers.scpi import InstrumentUnresponsive
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
AMP = opt("--amp", 1, float, [1.0])[0]
FREQS = (50.0, 1e3, 1e5, 1e6, 1e7, 2e7)
PROBE = 10.0
out = {"channels": [REF, DUT], "amp_vpp": AMP, "points": []}


def num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return math.nan


def main():
    session = connect.open_session("py")
    gen, scope = session.source, session.digitizer
    stim, meas = StimulusConfig(amp_vpp=AMP), MeasureSettings()
    meter = DualChannelScopeMeter(scope, ScopeConfig(ref_channel=REF, dut_channel=DUT,
                                                     probe_atten={REF: PROBE, DUT: PROBE}))
    r, d = "CHANnel%d" % REF, "CHANnel%d" % DUT
    queries = [("vpp_ref", ":MEASure:VPP? " + r), ("vpp_dut", ":MEASure:VPP? " + d),           # U1K p.30
               ("vamp_ref", ":MEASure:VAMPlitude? " + r), ("vamp_dut", ":MEASure:VAMPlitude? " + d),  # U1K p.31
               ("vrms_ref", ":MEASure:VRMS? CYCLe," + r), ("vrms_dut", ":MEASure:VRMS? CYCLe," + d),  # U1K p.32
               ("phase_ref_dut", ":MEASure:PHASe? %s,%s" % (r, d)),                             # U1K p.30
               ("phase_dut_ref", ":MEASure:PHASe? %s,%s" % (d, r)),                             # U1K p.30
               ("pdelay_ref_dut", ":MEASure:PDELay? %s,%s" % (r, d))]                           # U1K p.30
    print("generator: %s\nscope:     %s\n%g Vpp, reference CH%d, DUT CH%d" % (
        session.source_idn, session.digitizer_idn, AMP, REF, DUT), flush=True)

    def ask_all(n):
        rows = []
        for _ in range(n):
            row = {}
            for key, cmd in queries:
                t = time.perf_counter()
                raw = scope.query(cmd, lambda reply: reply)
                row[key] = (raw, round(time.perf_counter() - t, 4))
            rows.append(row)
        return rows

    def show(label, rows, fit):
        print("   %s (%d rounds)" % (label, len(rows)))
        for key, cmd in queries:
            vals = [num(x[key][0]) for x in rows]
            secs = [x[key][1] for x in rows]
            ok = [v for v in vals if math.isfinite(v) and abs(v) < 1e30]
            extra = ""
            if ok and key.startswith(("vpp", "vamp")):
                v = statistics.mean(ok) * PROBE          # ':MEASure' is at the input with the scope at 1X
                ref = 2 * (fit.vref_amp if key.endswith("ref") else fit.vdut_amp)
                extra = "   x%g = %.4f Vpp, fit %.4f Vpp (%+.2f %%)" % (PROBE, v, ref, 100 * (v / ref - 1))
            elif ok and key.startswith("vrms"):
                v = statistics.mean(ok) * PROBE * 2 * math.sqrt(2)
                ref = 2 * (fit.vref_amp if key.endswith("ref") else fit.vdut_amp)
                extra = "   as Vpp of a sine = %.4f, fit %.4f Vpp (%+.2f %%)" % (v, ref, 100 * (v / ref - 1))
            elif ok and key.startswith("phase"):
                extra = "   fit %+.2f deg (DUT - reference)" % fit.phase_deg
            elif ok and key.startswith("pdelay"):
                extra = "   = %+.2f deg at this frequency; fit %+.2f deg" % (
                    360 * fit.freq_hz * statistics.mean(ok), fit.phase_deg)
            print("      %-15s %-34s mean %-12s sd %-9s %.3f s each   first reply %r%s" % (
                key, cmd, "%.5g" % statistics.mean(ok) if ok else "-",
                "%.3g" % statistics.pstdev(ok) if len(ok) > 1 else "-", statistics.median(secs),
                rows[0][key][0], extra), flush=True)

    try:
        session.begin_measurement()
        gen.configure_sine(stim.gen_channel, FREQS[0], stim.amp_vpp, stim.offset_v, stim.load)
        meter.prepare(stim.amp_vpp, stim.offset_v)
        gen.set_output(stim.gen_channel, True)
        state = meter.initial_state()
        for f in FREQS:
            gen.set_frequency(stim.gen_channel, f)
            time.sleep(max(0.3, 5 / f))
            fits = [meter.measure(f, meas, state)[0] for _ in range(3)]
            fit = fits[-1]                               # the scope now holds this stopped record
            print("\n%g Hz   sine fit (single shot): gain %+.3f dB, phase %+.2f deg (sd %.2f), "
                  "reference %.4f Vpp, timebase %g" % (
                      f, statistics.mean(p.gain_db for p in fits), statistics.mean(p.phase_deg for p in fits),
                      statistics.pstdev([p.phase_deg for p in fits]), 2 * fit.vref_amp, state.timebase), flush=True)
            stopped = ask_all(3)
            show("scope STOPPED on that record", stopped, fit)
            scope.free_run()
            time.sleep(max(0.5, 30 * state.timebase))
            running = ask_all(8)
            show("scope RUNNING", running, fit)
            out["points"].append(dict(freq=f, timebase=state.timebase,
                                      fit=[(p.gain_db, p.phase_deg, p.vref_amp, p.vdut_amp) for p in fits],
                                      stopped=stopped, running=running))
        out["scope_stats"] = dict(scope.stats)
        print("\nscope counters:", out["scope_stats"])
        print(":SYSTem:ERRor? ->", scope.query(":SYSTem:ERRor?", lambda reply: reply))          # U1K p.7
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
        print("saved", save(os.path.join("m7", "s7_builtin.json"), out))


if __name__ == "__main__":
    main()
