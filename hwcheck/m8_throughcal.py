"""Milestone A1: through calibration on the real instruments, headless.

Run with the APP venv (it imports bodeplot):
    .venv\\Scripts\\python.exe -W ignore hwcheck\\m8_throughcal.py <label> [--ch=REF,DUT] [--avg=N] [--ppd=N]

PRECONDITION: the reference probe and the DUT probe on the same node (generator CH1's
output), both 10X.

What it does, through exactly the code the GUI uses (drivers/connect.py, sweep/core.py):
  1. find and open both instruments (generator outputs forced OFF on open);
  2. through calibration, full range, 10 points per decade, Sine fit;
  3. accept it, then one through sweep over the same range at --ppd points per decade
     (default 20, so every second point lies between two calibration points);
  4. print the largest gain and phase deviation against the targets 0.02 dB and 0.1 deg,
     and save everything (JSON here, CSV next to it).
The engine switches the generator off in a finally block, releases the scope's front-panel
lock and leaves the scope in sweep AUTO. No ':RUN' is sent (the driver refuses it).
"""
import logging
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from common import RESULTS, save                    # prints this script's hash and git commit

from bodeplot.drivers import connect
from bodeplot.io import export_csv
from bodeplot.models import MeasureSettings, ScopeConfig, StimulusConfig, SweepConfig, to_jsonable
from bodeplot.sweep import calibration
from bodeplot.sweep.core import Callbacks, SweepRunner, run_through_cal

TARGET_DB, TARGET_DEG = 0.02, 0.1
args = [a for a in sys.argv[1:] if not a.startswith("--")]
LABEL = args[0] if args else "run"


def opt(name, default, kind=str):
    return next((kind(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--%s=" % name)), default)


logging.basicConfig(level=logging.WARNING, format="   . %(name)s: %(message)s")
out = {"label": LABEL, "log": [], "target_db": TARGET_DB, "target_deg": TARGET_DEG}


def on_log(e):
    out["log"].append([e.level, e.text])
    print("   [%s] %s" % (e.level, e.text))


def on_point(p):
    print("  %12.2f Hz  %+8.4f dB  %+8.3f deg  removed %+7.4f dB %+8.3f deg  V/div %g / %g  %.2f s  %s" % (
        p.freq_hz, p.gain_db, p.phase_deg, p.cal_gain_db, p.cal_phase_deg, p.vdiv_ref, p.vdiv_dut,
        p.duration_s, p.flags.name or str(p.flags)))


def main():
    ref, dut = tuple(int(x) for x in opt("ch", "1,2").split(","))
    scope_cfg = ScopeConfig(ref_channel=ref, dut_channel=dut, probe_atten={ref: 10.0, dut: 10.0})
    stim = StimulusConfig()
    meas = MeasureSettings(averages=opt("avg", 1, int))
    ppd = opt("ppd", 20, int)
    out.update(channels=[ref, dut], averages=meas.averages, points_per_decade=ppd)
    session = connect.open_session("py")
    print("generator: %s\nscope:     %s" % (session.source_idn, session.digitizer_idn))
    out["generator_idn"], out["scope_idn"] = session.source_idn, session.digitizer_idn
    from pathlib import Path
    session.capture_dir = Path(RESULTS) / "m8" / "captures"
    try:
        for w in session.take_warnings():
            print("WARNING:", w)
        t0 = time.perf_counter()
        cal = run_through_cal(session, stim, scope_cfg, meas, on_log=on_log,
                              on_progress=lambda i, n: print("   calibration point %d of %d" % (i, n)))
        out["cal_s"] = time.perf_counter() - t0
        out["cal"] = to_jsonable(cal)
        print("\ncalibration (%.1f s): %s, %d points, largest gain deviation %.4f dB, delay %+.3f ns, "
              "acceptable: %s" % (out["cal_s"], calibration.range_text(cal), len(cal.freqs_hz),
                                  calibration.max_gain_db(cal), calibration.fitted_delay_s(cal) * 1e9,
                                  cal.acceptable))
        for f, h in zip(cal.freqs_hz, cal.h):
            import cmath
            import math
            print("  %12.2f Hz  %+8.4f dB  %+8.3f deg" % (
                f, 20 * math.log10(abs(h)) if abs(h) else float("-inf"), math.degrees(cmath.phase(h))))
        for w in cal.warnings:
            print("   calibration WARNING:", w)
        if not cal.acceptable:
            print("NOT ACCEPTABLE: no sweep.")
            return
        session.accept_cal(cal)
        print("\nthrough sweep with the calibration applied:")
        runner = SweepRunner(session, SweepConfig(start_hz=cal.freqs_hz[0], stop_hz=cal.freqs_hz[-1],
                                                  points_per_decade=ppd),
                             stim, scope_cfg, meas, Callbacks(point=on_point, log=on_log))
        t0 = time.perf_counter()
        result = runner.run()
        out["sweep_s"] = time.perf_counter() - t0
        out["error"] = result.meta.get("error")
        out["result"] = to_jsonable(result)
        pts = result.points
        if pts:
            worst_g = max(pts, key=lambda p: abs(p.gain_db))
            worst_p = max(pts, key=lambda p: abs(p.phase_deg))
            out["max_gain_db"], out["max_gain_at_hz"] = abs(worst_g.gain_db), worst_g.freq_hz
            out["max_phase_deg"], out["max_phase_at_hz"] = abs(worst_p.phase_deg), worst_p.freq_hz
            out["passed"] = bool(abs(worst_g.gain_db) <= TARGET_DB and abs(worst_p.phase_deg) <= TARGET_DEG)
            print("\n%d points in %.1f s" % (len(pts), out["sweep_s"]))
            print("largest gain deviation  %.4f dB at %g Hz   (target %.2f dB)" % (
                abs(worst_g.gain_db), worst_g.freq_hz, TARGET_DB))
            print("largest phase deviation %.4f deg at %g Hz  (target %.1f deg)" % (
                abs(worst_p.phase_deg), worst_p.freq_hz, TARGET_DEG))
            print("flags seen:", sorted({n for p in pts for n in p.flags.names()}))
            print("RESULT:", "WITHIN the targets" if out["passed"] else "OUTSIDE the targets")
            os.makedirs(os.path.join(RESULTS, "m8"), exist_ok=True)
            csv_path = os.path.join(RESULTS, "m8", "m8_throughcal_%s.csv" % LABEL)
            export_csv.write_csv(csv_path, result)
            print("CSV:", csv_path)
        if out["error"]:
            print("ERROR:", out["error"])
        out["scope_stats"] = dict(session.digitizer.stats)
        out["generator_stats"] = dict(session.source.stats)
        print("scope counters:", out["scope_stats"])
        print("generator counters:", out["generator_stats"])
        if session.dead_reason is None:
            out["outputs_at_end"] = [session.source.output(1), session.source.output(2)]
            out["panel_locked_at_end"] = session.digitizer.query(":SYSTem:LOCK?", lambda r: r)   # U1K p.6
            out["sweep_mode_at_end"] = session.digitizer.query(":TRIGger:SWEep?", lambda r: r)   # U1K p.36
            print("at the end: generator outputs ON? %s, panel lock %s, scope sweep %s" % (
                out["outputs_at_end"], out["panel_locked_at_end"], out["sweep_mode_at_end"]))
    finally:
        session.close()
        os.makedirs(os.path.join(RESULTS, "m8"), exist_ok=True)
        print("saved", save(os.path.join("m8", "m8_throughcal_%s.json" % LABEL), out))


if __name__ == "__main__":
    main()
