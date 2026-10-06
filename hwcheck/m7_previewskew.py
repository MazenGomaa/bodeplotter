"""Milestone 7: does a Fast preview sweep move the scope's channel alignment?

Run with the APP venv:
    .venv\\Scripts\\python.exe -W ignore hwcheck\\m7_previewskew.py [rounds] [--ch REF DUT] [--single]

The user saw the +2.15 ns alignment state in a GUI session in which a Fast preview sweep
had run (HW_REPORT.md 13.25). Fast preview reads the scope while it runs, which nothing
did before. This script alternates, through the app's own code:
    skew check  ->  Fast preview sweep 200 kHz to 20 MHz  ->  skew check  ->  ...
and prints the measured delay after every sweep, with the number of empty replies (the
scope's busy episodes of 13.24) that sweep had. --single runs the same loop with ordinary
single-shot sweeps, as the control.

PRECONDITION: both probes on generator CH1 (through connection), both 10X.
Generator output is switched off by the app's code in a finally block. No ':RUN'.
"""
import logging
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from common import save                              # prints this script's hash and git commit

from bodeplot.drivers import connect
from bodeplot.models import MeasureSettings, Method, ScopeConfig, StimulusConfig, SweepConfig
from bodeplot.sweep.core import SweepRunner, run_skew_check

logging.basicConfig(level=logging.ERROR)
argv = sys.argv[1:]
REF, DUT = 1, 2
if "--ch" in argv:
    i = argv.index("--ch")
    REF, DUT = int(argv[i + 1]), int(argv[i + 2])
    del argv[i:i + 3]
METHOD = Method.SINEFIT if "--single" in argv else Method.PREVIEW
# --resync: no sweeps; a driver resync while the scope is running, then the skew check
RESYNC = "--resync" in argv
argv = [a for a in argv if a not in ("--single", "--resync")]
ROUNDS = int(argv[0]) if argv else 10
out = {"rounds": ROUNDS, "channels": [REF, DUT], "method": METHOD.value, "log": []}


def main():
    session = connect.open_session("py")
    scope = session.digitizer
    stim = StimulusConfig()
    cfg = ScopeConfig(ref_channel=REF, dut_channel=DUT, probe_atten={REF: 10.0, DUT: 10.0})
    print("generator: %s\nscope:     %s\n%d rounds of %s sweeps, CH%d / CH%d" % (
        session.source_idn, session.digitizer_idn, ROUNDS, METHOD.value, REF, DUT), flush=True)

    def check(label):
        c = run_skew_check(session, stim, cfg, MeasureSettings())
        row = dict(label=label, measured_ns=c.measured_s * 1e9, per_freq_ns=[d * 1e9 for d in c.per_freq_delay_s],
                   gain_db=c.gain_db, epoch=scope.alignment_epoch, warnings=c.warnings)
        out["log"].append(row)
        print("   %-28s delay %+.2f ns  (%s)  gain %+.3f dB  epoch %d%s" % (
            label, row["measured_ns"], ", ".join("%+.2f" % d for d in row["per_freq_ns"]), c.gain_db,
            scope.alignment_epoch, "   " + "; ".join(c.warnings) if c.warnings else ""), flush=True)
        return row["measured_ns"]

    try:
        first = check("at the start")
        if abs(first) > 6 or any("Gain mismatch" in w for w in out["log"][0]["warnings"]):
            raise SystemExit("STOP: this does not look like a through connection on CH%d / CH%d" % (REF, DUT))
        for n in range(1, ROUNDS + 1):
            if RESYNC:
                # what the first version of Fast preview did after an empty reply: a resync
                # (device clear: the USB session is closed and reopened) while the scope runs
                scope.free_run()
                time.sleep(0.5)
                scope.resync()
                check("after resync %d while running" % n)
                continue
            before = dict(scope.stats)
            t0 = time.perf_counter()
            res = SweepRunner(session, SweepConfig(start_hz=2e5, stop_hz=2e7, points_per_decade=30), stim, cfg,
                              MeasureSettings(method=METHOD)).run()
            d = {k: scope.stats[k] - before.get(k, 0) for k in ("empty_blocks", "resyncs", "stale_records")}
            out["log"].append(dict(label="sweep %d" % n, points=len(res.points), error=res.meta.get("error"),
                                   seconds=time.perf_counter() - t0, **d))
            if res.meta.get("error"):
                print("   sweep %d ERROR: %s" % (n, res.meta["error"]), flush=True)
                break
            check("after sweep %d (%d empty, %d resync)" % (n, d["empty_blocks"], d["resyncs"]))
        delays = [r["measured_ns"] for r in out["log"] if "measured_ns" in r]
        print("delays: min %+.2f ns, max %+.2f ns over %d checks" % (min(delays), max(delays), len(delays)))
        out["scope_stats"] = dict(scope.stats)
    finally:
        session.source.safe_off()
        session.close()
        print("generator outputs off, connections closed")
        print("saved", save(os.path.join("m7", "m7_previewskew_%s.json" % METHOD.value), out))


if __name__ == "__main__":
    main()
