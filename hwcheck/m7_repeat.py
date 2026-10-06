"""Milestone 7: try to reproduce the one bad capture of HW_REPORT.md 13.9.

Run with the APP venv:
    .venv\\Scripts\\python.exe -W ignore hwcheck\\m7_repeat.py [runs] [--dc] [start_hz stop_hz ppd]

That capture was the first point after the timebase went from 10 to 5 ms/div (62.7 Hz to
78.62 Hz), AC coupled: both channels read 0.021 V instead of 0.496 V. This script repeats
a short sweep across that transition (default 50 to 100 Hz, 10 points per decade: 50,
62.7, 78.6, 98.6 Hz) through the app's own code and counts the captures the meter rejects.
Each rejected capture is written to results/m7/captures/ with its raw waveforms.
PRECONDITION: the RC low-pass is wired; nobody needs to be at the bench. No ':RUN'.
"""
import logging
import os
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from common import RESULTS, save                    # prints this script's hash and git commit

from bodeplot.drivers import connect
from bodeplot.models import Flag, MeasureSettings, ScopeConfig, StimulusConfig, SweepConfig
from bodeplot.sweep.core import Callbacks, SweepRunner

logging.basicConfig(level=logging.ERROR)
args = [a for a in sys.argv[1:] if not a.startswith("--")]
RUNS = int(args[0]) if args else 40
START, STOP, PPD = (float(args[1]), float(args[2]), int(args[3])) if len(args) >= 4 else (50.0, 100.0, 10)
COUPLING = "DC" if "--dc" in sys.argv else "AC"
out = {"runs": RUNS, "coupling": COUPLING, "start_hz": START, "stop_hz": STOP, "ppd": PPD, "events": [], "run_log": []}


def main():
    session = connect.open_session("py")
    session.capture_dir = Path(RESULTS) / "m7" / "captures"
    print("generator: %s\nscope:     %s\n%d sweeps %g to %g Hz, %s coupled" % (
        session.source_idn, session.digitizer_idn, RUNS, START, STOP, COUPLING), flush=True)
    points = suspects = 0
    t0 = time.perf_counter()
    try:
        for n in range(1, RUNS + 1):
            logs = []
            runner = SweepRunner(session, SweepConfig(start_hz=START, stop_hz=STOP, points_per_decade=PPD),
                                 StimulusConfig(), ScopeConfig(coupling=COUPLING), MeasureSettings(),
                                 Callbacks(log=lambda e: logs.append((e.level, e.text))))
            result = runner.run()
            bad = [t for lvl, t in logs if "Bad capture" in t]
            sus = [p.freq_hz for p in result.points if Flag.REF_SUSPECT in p.flags]
            low = [(p.freq_hz, p.vref_amp) for p in result.points if p.vref_amp < 0.4]
            points += len(result.points)
            suspects += len(sus)
            out["run_log"].append(dict(run=n, points=len(result.points), error=result.meta.get("error"),
                                       bad=bad, suspect=sus, low_ref=low,
                                       retries=sum(p.retries for p in result.points)))
            for t in bad:
                out["events"].append(dict(run=n, text=t))
                print("   run %d: %s" % (n, t), flush=True)
            if result.meta.get("error"):
                print("   run %d ERROR: %s" % (n, result.meta["error"]), flush=True)
                break
            if low:
                print("   run %d: LOW REFERENCE kept in the result: %s" % (n, low), flush=True)
            if n % 10 == 0:
                print("   %d sweeps, %d points, %d rejected captures, %.0f s" % (
                    n, points, len(out["events"]), time.perf_counter() - t0), flush=True)
        out.update(points=points, rejected=len(out["events"]), ref_suspect_points=suspects,
                   seconds=time.perf_counter() - t0, scope_stats=dict(session.digitizer.stats),
                   generator_stats=dict(session.source.stats))
        print("TOTAL: %d points in %d sweeps, %d captures rejected and retried, %d points left REF_SUSPECT" % (
            points, len(out["run_log"]), len(out["events"]), suspects))
        print("scope counters:", out["scope_stats"])
        if session.dead_reason is None:
            print("at the end: generator outputs ON? %s, panel lock %s, scope sweep %s" % (
                [session.source.output(1), session.source.output(2)],
                session.digitizer.query(":SYSTem:LOCK?", lambda r: r),                 # U1K p.6
                session.digitizer.query(":TRIGger:SWEep?", lambda r: r)))              # U1K p.36
    finally:
        session.close()
        print("saved", save(os.path.join("m7", "m7_repeat_%s.json" % COUPLING.lower()), out))


if __name__ == "__main__":
    main()
