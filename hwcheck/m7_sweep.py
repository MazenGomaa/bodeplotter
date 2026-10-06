"""Milestone 7: the app's own drivers and sweep engine on the real instruments, headless.

Run with the APP venv (it imports bodeplot):
    .venv\\Scripts\\python.exe -W ignore hwcheck\\m7_sweep.py <label> [start_hz stop_hz points_per_decade] [--no-skew] [--ac]
--ac: scope channels AC coupled (default DC).

What it does, through exactly the code the GUI uses (drivers/connect.py, sweep/core.py):
  1. find and open both instruments (generator outputs forced OFF on open);
  2. unless --no-skew: channel skew check. PRECONDITION for that step: both probes on the
     same node (generator CH1's output);
  3. one sweep with the default stimulus (1 Vpp, High-Z, generator CH1) and 10X probes;
  4. save the result (JSON here, CSV next to it) and print every point with its timing.
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
from bodeplot.measure import skew as skew_mod
from bodeplot.models import MeasureSettings, ScopeConfig, StimulusConfig, SweepConfig, to_jsonable
from bodeplot.sweep.core import Callbacks, SweepRunner, run_skew_check

args = [a for a in sys.argv[1:] if not a.startswith("--")]
LABEL = args[0] if args else "run"
START, STOP, PPD = (float(args[1]), float(args[2]), int(args[3])) if len(args) >= 4 else (50.0, 20e6, 5)
DO_SKEW = "--no-skew" not in sys.argv
# --offset=<volts>: generator DC offset (default 0), to test the DC handling on purpose
OFFSET = next((float(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--offset=")), 0.0)
COUPLING = "AC" if "--ac" in sys.argv else "DC"
SETUP_QUERIES = [":TIMebase:SCALe?", ":TRIGger:SOURce?", ":TRIGger:LEVel?"] + [                # U1K p.16, 38, 37
    ":CHANnel%d:%s?" % (ch, k) for ch in (1, 2)
    for k in ("DISPlay", "PROBe", "SCALe", "OFFSet", "COUPling", "BWLimit", "VERNier")]        # U1K p.12-15
logging.basicConfig(level=logging.WARNING, format="   . %(name)s: %(message)s")
out = {"label": LABEL, "start_hz": START, "stop_hz": STOP, "points_per_decade": PPD, "log": []}


def on_log(e):
    out["log"].append([e.level, e.text])
    print("   [%s] %s" % (e.level, e.text))


def on_point(p):
    print("  %12.2f Hz  %+8.3f dB  %+8.2f deg  ref %.4f V  dut %.4f V  V/div %g / %g  tb %g  "
          "SNR %s / %s  retries %d  %.2f s  %s" % (
              p.freq_hz, p.gain_db, p.phase_deg, p.vref_amp, p.vdut_amp, p.vdiv_ref, p.vdiv_dut, p.timebase,
              "%.0f" % p.snr_ref_db if p.snr_ref_db is not None else "-",
              "%.0f" % p.snr_dut_db if p.snr_dut_db is not None else "-",
              p.retries, p.duration_s, p.flags.name or str(p.flags)))


def main():
    stim, scope_cfg, meas = StimulusConfig(offset_v=OFFSET), ScopeConfig(coupling=COUPLING), MeasureSettings()
    out["offset_v"] = OFFSET
    out["coupling"] = COUPLING
    t0 = time.perf_counter()
    session = connect.open_session("py")
    out["connect_s"] = time.perf_counter() - t0
    print("generator: %s\nscope:     %s   (connected in %.1f s)" % (
        session.source_idn, session.digitizer_idn, out["connect_s"]))
    out["generator_idn"], out["scope_idn"] = session.source_idn, session.digitizer_idn
    from pathlib import Path
    session.capture_dir = Path(RESULTS) / "m7" / "captures"      # raw waveforms of rejected captures
    try:
        for w in session.take_warnings():
            print("WARNING:", w)
        setup = lambda: {q: session.digitizer.query(q, lambda r: r) for q in SETUP_QUERIES}
        out["scope_setup_before"] = setup()
        if DO_SKEW:
            t0 = time.perf_counter()
            check = run_skew_check(session, stim, scope_cfg, meas, SweepConfig(start_hz=START, stop_hz=STOP),
                                   on_log=on_log)
            out["skew_s"] = time.perf_counter() - t0
            out["skew"] = to_jsonable(check)
            print("skew check (%.1f s): %s" % (out["skew_s"], skew_mod.describe(check)))
            for w in check.warnings:
                print("   skew WARNING:", w)
            session.accept_skew(check)
        runner = SweepRunner(session, SweepConfig(start_hz=START, stop_hz=STOP, points_per_decade=PPD),
                             stim, scope_cfg, meas, Callbacks(point=on_point, log=on_log))
        t0 = time.perf_counter()
        result = runner.run()
        out["sweep_s"] = time.perf_counter() - t0
        n = len(result.points)
        out["points"] = n
        out["error"] = result.meta.get("error")
        out["result"] = to_jsonable(result)
        if n:
            durs = [p.duration_s for p in result.points]
            out["per_point_s"] = dict(mean=sum(durs) / n, min=min(durs), max=max(durs))
            print("\n%d points in %.1f s: %.2f s per point (%.2f to %.2f measuring; the rest is settling "
                  "and generator commands)" % (n, out["sweep_s"], out["sweep_s"] / n, min(durs), max(durs)))
            csv_path = os.path.join(RESULTS, "m7", "m7_sweep_%s.csv" % LABEL)
            export_csv.write_csv(csv_path, result)
            print("CSV:", csv_path)
        if out["error"]:
            print("ERROR:", out["error"])
        out["scope_stats"] = dict(session.digitizer.stats)
        out["generator_stats"] = dict(session.source.stats)
        print("scope counters:", out["scope_stats"])
        print("generator counters:", out["generator_stats"])
        if session.dead_reason is None:
            out["scope_setup_after"] = setup()
            diff = {q: (v, out["scope_setup_after"][q]) for q, v in out["scope_setup_before"].items()
                    if out["scope_setup_after"][q] != v}
            out["scope_setup_changed"] = diff
            print("scope settings before the sweep:", out["scope_setup_before"])
            print("scope settings NOT restored:", diff or "none")
            out["outputs_at_end"] = [session.source.output(1), session.source.output(2)]
            out["panel_locked_at_end"] = session.digitizer.query(":SYSTem:LOCK?", lambda r: r)   # U1K p.6
            out["sweep_mode_at_end"] = session.digitizer.query(":TRIGger:SWEep?", lambda r: r)   # U1K p.36
            print("at the end: generator outputs ON? %s, panel lock %s, scope sweep %s" % (
                out["outputs_at_end"], out["panel_locked_at_end"], out["sweep_mode_at_end"]))
    finally:
        session.close()
        os.makedirs(os.path.join(RESULTS, "m7"), exist_ok=True)
        print("saved", save(os.path.join("m7", "m7_sweep_%s.json" % LABEL), out))


if __name__ == "__main__":
    main()
