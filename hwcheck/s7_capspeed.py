"""Milestone 7: how far can the margins of one single-shot capture be shortened?

Run with the APP venv:
    .venv\\Scripts\\python.exe -W ignore hwcheck\\s7_capspeed.py <series> [N] [--ch REF DUT]

series: baseline | hold | quiet | extra | poll | custom QUIET HOLD EXTRA POLL
N:      captures per scenario (default 12)

The driver waits 0.3 s after the last setting change before it arms (ARM_QUIET_S), wants
STOP to hold 0.1 s before it reads (STOP_HOLD_S), waits one screen + 0.05 s
(MIN_WAIT_EXTRA_S) and pauses 10 ms between status polls (STATUS_POLL_S); all four were
set with margin in Milestone 0b (HW_REPORT.md 12.4). This script runs the app's own
driver with shorter values and checks every capture:
  - no driver error, no empty block, no resync, no re-arm, no forced trigger
  - the record has the timebase that was just set (dt), so it is not a stale record
  - both channels hold the stimulus at the frequency that was just set (fit SNR)
  - amplitude, gain and phase agree with the baseline of the same scenario
  - the scope still reads STOP after the read (no second arm cycle under the read)
Scenarios: steady settings at 1 kHz and at 1 MHz, a timebase change before every
capture, a generator frequency change before every capture (what a sweep does).

PRECONDITION: both probes on generator CH1 (through connection), both 10X.
Generator output is on during the run and switched off in a finally block. No ':RUN'.
"""
import logging
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
from bodeplot.measure import sinefit
from bodeplot.measure.meters import DualChannelScopeMeter
from bodeplot.models import MeasureSettings, ScopeConfig, StimulusConfig

logging.basicConfig(level=logging.ERROR)
argv = sys.argv[1:]
REF, DUT = 1, 2
if "--ch" in argv:
    i = argv.index("--ch")
    REF, DUT = int(argv[i + 1]), int(argv[i + 2])
    del argv[i:i + 3]
SERIES = argv[0] if argv else "baseline"
BASE = dict(quiet=0.3, hold=0.1, extra=0.05, poll=0.01)
if SERIES == "custom":
    CONFIGS = [dict(quiet=float(argv[1]), hold=float(argv[2]), extra=float(argv[3]), poll=float(argv[4]))]
    N = int(argv[5]) if len(argv) > 5 else 12
else:
    N = int(argv[1]) if len(argv) > 1 else 12
    CONFIGS = {
        "baseline": [],
        "hold": [dict(BASE, hold=h) for h in (0.05, 0.02, 0.0)],
        "quiet": [dict(BASE, quiet=q) for q in (0.2, 0.1, 0.05, 0.0)],
        "extra": [dict(BASE, extra=0.0)],
        "poll": [dict(BASE, poll=0.0)],
    }[SERIES]
CONFIGS = [dict(BASE)] + CONFIGS                     # the baseline always runs first: it is the reference
out = {"series": SERIES, "n": N, "channels": [REF, DUT], "configs": []}
STIM, MEAS = StimulusConfig(), MeasureSettings()
SCENARIOS = ("steady 1 kHz", "steady 1 MHz", "timebase change", "frequency change")


def name(c):
    return "quiet %.2f hold %.2f extra %.2f poll %.3f" % (c["quiet"], c["hold"], c["extra"], c["poll"])


def main():
    session = connect.open_session("py")
    gen, scope = session.source, session.digitizer
    print("generator: %s\nscope:     %s\nseries %s, %d captures per scenario, reference CH%d, DUT CH%d" % (
        session.source_idn, session.digitizer_idn, SERIES, N, REF, DUT), flush=True)
    cfg = ScopeConfig(ref_channel=REF, dut_channel=DUT, probe_atten={REF: 10.0, DUT: 10.0})
    meter = DualChannelScopeMeter(scope, cfg)
    timing = {}

    def timed(fn_name):
        inner = getattr(scope, fn_name)

        def wrapper(*a, **kw):
            t = time.perf_counter()
            try:
                return inner(*a, **kw)
            finally:
                timing[fn_name] = timing.get(fn_name, 0.0) + time.perf_counter() - t
        setattr(scope, fn_name, wrapper)
    timed("_settle_before_arm")
    timed("_fetch_channel")

    def capture(f, want_tb):
        """One capture and its checks. Returns a dict; 'bad' lists what was wrong."""
        timing.clear()
        before = dict(scope.stats)
        rec, bad = {}, []
        t = time.perf_counter()
        try:
            waves = scope.acquire([REF, DUT], MEAS.acquire_timeout_s)
        except InstrumentUnresponsive:
            raise
        except DriverError as e:
            return dict(bad=["driver error: %s" % e], total=time.perf_counter() - t)
        rec["total"] = time.perf_counter() - t
        rec["settle"] = timing.get("_settle_before_arm", 0.0)
        rec["fetch"] = timing.get("_fetch_channel", 0.0)
        rec["wait"] = rec["total"] - rec["settle"] - rec["fetch"]
        rec["timeline"] = list(scope.last_timeline)
        try:
            if scope.status() != "STOP":
                bad.append("status after the read is not STOP")
        except DriverError as e:
            bad.append("status query failed: %s" % e)
        for k in ("empty_blocks", "resyncs", "rearms", "forced_triggers", "out_of_step", "reply_errors"):
            if scope.stats.get(k, 0) != before.get(k, 0):
                bad.append("%s +%d" % (k, scope.stats.get(k, 0) - before.get(k, 0)))
        w_ref, w_dut = waves[REF], waves[DUT]
        if abs(w_ref.dt - want_tb / 50.0) > 0.01 * want_tb / 50.0:
            bad.append("record dt %.3g s, expected %.3g s (stale record?)" % (w_ref.dt, want_tb / 50.0))
        f_ref = sinefit.fit3(w_ref.volts, w_ref.dt, f, w_ref.t0)
        f_dut = sinefit.fit3(w_dut.volts, w_dut.dt, f, w_dut.t0)
        gain, phase = sinefit.gain_phase(sinefit.transfer(f_ref, f_dut))
        rec.update(amp=f_ref.amp, gain=gain, phase=phase, snr_ref=f_ref.snr_db, snr_dut=f_dut.snr_db)
        if min(f_ref.snr_db, f_dut.snr_db) < 20.0:
            bad.append("fit SNR %.1f / %.1f dB" % (f_ref.snr_db, f_dut.snr_db))
        rec["bad"] = bad
        return rec

    def settle(f):
        time.sleep(max(MEAS.settle_ms / 1000.0, MEAS.settle_cycles / f))

    def scenario(which):
        recs = []
        if which.startswith("steady"):
            f = 1e3 if "kHz" in which else 1e6
            gen.set_frequency(STIM.gen_channel, f)
            tb = meter._set_timebase(f, state)
            settle(f)
            scope.acquire([REF, DUT], MEAS.acquire_timeout_s)        # the first one follows a setting change
            for _ in range(N):
                recs.append(capture(f, tb))
        elif which == "timebase change":
            f = 1e3
            gen.set_frequency(STIM.gen_channel, f)
            tb0 = meter._set_timebase(f, state)
            steps = sorted(scope.caps.timebase_steps)
            tb1 = steps[steps.index(tb0) - 1]                        # one step faster: still whole cycles
            settle(f)
            for k in range(N):
                tb = scope.set_timebase(tb1 if k % 2 == 0 else tb0)
                state.timebase = tb
                recs.append(capture(f, tb))
        else:
            for k in range(N):
                f = 1000.0 if k % 2 else 1258.93                     # same timebase for both
                gen.set_frequency(STIM.gen_channel, f)
                tb = meter._set_timebase(f, state)
                settle(f)
                recs.append(capture(f, tb))
        return recs

    reference = {}
    try:
        session.begin_measurement()
        gen.configure_sine(STIM.gen_channel, 1e3, STIM.amp_vpp, STIM.offset_v, STIM.load)
        meter.prepare(STIM.amp_vpp, STIM.offset_v)
        gen.set_output(STIM.gen_channel, True)
        state = meter.initial_state()
        point, _ = meter.measure(1e3, MEAS, state)                   # auto-range once, as a sweep would
        print("first point: %.3f dB, %.2f deg, reference %.3f V peak" % (point.gain_db, point.phase_deg, point.vref_amp))
        if point.vref_amp < 0.2 * STIM.amp_vpp / 2 or abs(point.gain_db) > 1.0:
            raise SystemExit("STOP: this does not look like a through connection on CH%d / CH%d" % (REF, DUT))
        for c in CONFIGS:
            scope.ARM_QUIET_S, scope.STOP_HOLD_S = c["quiet"], c["hold"]
            scope.MIN_WAIT_EXTRA_S, scope.STATUS_POLL_S = c["extra"], c["poll"]
            entry = dict(config=c, name=name(c), scenarios={})
            print("\n%s" % name(c), flush=True)
            for which in SCENARIOS:
                recs = scenario(which)
                good = [r for r in recs if "amp" in r]
                if c == BASE and which not in reference and good:
                    reference[which] = {k: statistics.median(r[k] for r in good) for k in ("amp", "gain", "phase")}
                ref = reference.get(which)
                for r in good:
                    if ref and "frequency" not in which:             # two frequencies: no single reference
                        if abs(r["amp"] / ref["amp"] - 1) > 0.03:
                            r["bad"].append("amplitude %.4f V, baseline %.4f V" % (r["amp"], ref["amp"]))
                        if abs(r["gain"] - ref["gain"]) > 0.1:
                            r["bad"].append("gain %.3f dB, baseline %.3f dB" % (r["gain"], ref["gain"]))
                        if abs(r["phase"] - ref["phase"]) > 0.5:
                            r["bad"].append("phase %.2f deg, baseline %.2f deg" % (r["phase"], ref["phase"]))
                n_bad = sum(1 for r in recs if r["bad"])
                med = lambda k: statistics.median(r[k] for r in good) if good else float("nan")
                print("   %-17s %2d/%2d ok   total %.3f s = settle %.3f + wait %.3f + read %.3f   (worst %.3f s)" % (
                    which, len(recs) - n_bad, len(recs), med("total"), med("settle"), med("wait"), med("fetch"),
                    max((r["total"] for r in recs), default=float("nan"))), flush=True)
                for r in recs:
                    if r["bad"]:
                        print("      BAD: %s   timeline %s" % ("; ".join(r["bad"]), r.get("timeline")), flush=True)
                if good and c == BASE:
                    print("      typical timeline: %s" % good[len(good) // 2]["timeline"], flush=True)
                entry["scenarios"][which] = recs
            out["configs"].append(entry)
        out["scope_stats"], out["generator_stats"] = dict(scope.stats), dict(gen.stats)
        print("\nscope counters:", out["scope_stats"])
    finally:
        gen.safe_off()
        for k, v in (("ARM_QUIET_S", 0.3), ("STOP_HOLD_S", 0.1), ("MIN_WAIT_EXTRA_S", 0.05), ("STATUS_POLL_S", 0.01)):
            setattr(scope, k, v)
        if session.dead_reason is None:
            try:
                session.end_measurement()
            except Exception as e:
                print("could not restore the scope:", e)
        session.close()
        print("generator outputs off, connections closed")
        print("saved", save(os.path.join("m7", "s7_capspeed_%s.json" % SERIES), out))


if __name__ == "__main__":
    main()
