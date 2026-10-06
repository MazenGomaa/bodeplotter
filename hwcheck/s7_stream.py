"""Milestone 7: can the two channels be read from a RUNNING scope (no single shot, no stop)?

Run with the APP venv:
    .venv\\Scripts\\python.exe -W ignore hwcheck\\s7_stream.py [N] [--ch REF DUT]

A single-shot capture costs 0.40 s of arm cycle plus about 0.1 s after STOP (HW_REPORT.md
13.20). Here the scope is left in sweep AUTO, triggering on the reference channel, and the
two channels are read one after the other from whatever it shows. Three questions:

  1. steady signal (1 kHz, 1 MHz, 20 MHz): do gain and phase agree with single shot, and
     how much do they scatter? The two channels now come from two different acquisitions,
     so their phase is only comparable if every record is aligned to the trigger more
     finely than one sample.
  2. after a generator frequency change (50 Hz, 1 kHz, 1 MHz), how long must the read wait
     so that it never returns a record of the old frequency?
  3. after a timebase change, the same question.

Waits are tried from long to short. An EMPTY reply to ':WAVeform:DATA?' is the dangerous
case (HW_REPORT.md S4, S5: it once left the scope out of step until a power cycle), so it
is never retried in place: the driver resyncs and the shorter waits of that test are
skipped. If the scope stops answering the script ends and says so.

PRECONDITION: both probes on generator CH1 (through connection), both 10X.
Generator output is on during the run and switched off in a finally block. No ':RUN'.
"""
import hashlib
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
from bodeplot.drivers.scpi import EmptyBlock, InstrumentUnresponsive
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
N = int(argv[0]) if argv else 30
STIM, MEAS = StimulusConfig(), MeasureSettings()
WAITS = (1.0, 0.5, 0.3, 0.2, 0.1, 0.05, 0.0)
out = {"n": N, "channels": [REF, DUT], "steady": [], "frequency_change": [], "timebase_change": [], "events": []}


def spread(xs):
    return (statistics.mean(xs), statistics.pstdev(xs), min(xs), max(xs)) if xs else (float("nan"),) * 4


def main():
    session = connect.open_session("py")
    gen, scope = session.source, session.digitizer
    print("generator: %s\nscope:     %s\n%d pairs per steady test, reference CH%d, DUT CH%d" % (
        session.source_idn, session.digitizer_idn, N, REF, DUT), flush=True)
    meter = DualChannelScopeMeter(scope, ScopeConfig(ref_channel=REF, dut_channel=DUT,
                                                     probe_atten={REF: 10.0, DUT: 10.0}))

    def run_and_wait(tb, extra=0.5):
        """Sweep AUTO restarts a stopped scope (HW_REPORT.md 12.13); then let it fill a record."""
        scope.free_run()
        time.sleep(max(extra, 30 * tb))

    def pair(f, want_tb):
        """Both channels from the running scope. Returns a dict with 'bad'; raises EmptyBlock."""
        t = time.perf_counter()
        status = scope.status()
        w_ref = scope._fetch_channel(REF)
        w_dut = scope._fetch_channel(DUT)
        rec = dict(total=time.perf_counter() - t, status=status, bad=[])
        if abs(w_ref.dt - want_tb / 50.0) > 0.01 * want_tb / 50.0:
            rec["bad"].append("reference dt %.3g s, expected %.3g s" % (w_ref.dt, want_tb / 50.0))
        if abs(w_dut.dt - want_tb / 50.0) > 0.01 * want_tb / 50.0:
            rec["bad"].append("DUT dt %.3g s, expected %.3g s" % (w_dut.dt, want_tb / 50.0))
        f_ref = sinefit.fit3(w_ref.volts, w_ref.dt, f, w_ref.t0)
        f_dut = sinefit.fit3(w_dut.volts, w_dut.dt, f, w_dut.t0)
        gain, phase = sinefit.gain_phase(sinefit.transfer(f_ref, f_dut))
        rec.update(amp=f_ref.amp, gain=gain, phase=phase, snr_ref=f_ref.snr_db, snr_dut=f_dut.snr_db,
                   ref_hash=hashlib.md5(w_ref.volts.tobytes()).hexdigest()[:8])
        if f_ref.snr_db < 20.0:
            rec["bad"].append("reference fit SNR %.1f dB" % f_ref.snr_db)
        if f_dut.snr_db < 20.0:
            rec["bad"].append("DUT fit SNR %.1f dB" % f_dut.snr_db)
        return rec

    def empty(where, e):
        """An empty reply: never retried in place. Resync (raises if the scope is gone)."""
        print("      EMPTY REPLY at %s: %s" % (where, e), flush=True)
        out["events"].append(dict(where=where, error=str(e)))
        scope.resync()
        print("      resync ok", flush=True)

    try:
        session.begin_measurement()
        gen.configure_sine(STIM.gen_channel, 1e3, STIM.amp_vpp, STIM.offset_v, STIM.load)
        meter.prepare(STIM.amp_vpp, STIM.offset_v)
        gen.set_output(STIM.gen_channel, True)
        state = meter.initial_state()
        point, _ = meter.measure(1e3, MEAS, state)
        print("first point (single shot): %.3f dB, %.2f deg, reference %.3f V peak" % (
            point.gain_db, point.phase_deg, point.vref_amp))
        if point.vref_amp < 0.2 * STIM.amp_vpp / 2 or abs(point.gain_db) > 1.0:
            raise SystemExit("STOP: this does not look like a through connection on CH%d / CH%d" % (REF, DUT))

        # ---- 1. steady signal: single shot against reads from the running scope
        print("\n1. steady signal")
        for f in (1e3, 1e6, 20e6):
            gen.set_frequency(STIM.gen_channel, f)
            time.sleep(0.3)
            single = [meter.measure(f, MEAS, state)[0] for _ in range(6)]
            tb = state.timebase
            t0 = time.perf_counter()
            for _ in range(3):
                meter.measure(f, MEAS, state)
            t_single = (time.perf_counter() - t0) / 3
            run_and_wait(tb)
            recs = []
            try:
                for _ in range(N):
                    recs.append(pair(f, tb))
            except EmptyBlock as e:
                empty("steady %g Hz, pair %d" % (f, len(recs) + 1), e)
            good = [r for r in recs if not r["bad"]]
            g1, p1 = spread([p.gain_db for p in single]), spread([p.phase_deg for p in single])
            g2, p2 = spread([r["gain"] for r in good]), spread([r["phase"] for r in good])
            fresh = len({r["ref_hash"] for r in recs})
            print("   %-8g Hz  single shot: gain %+.3f dB (sd %.3f)  phase %+.2f deg (sd %.2f, %+.2f..%+.2f)  %.2f s each" % (
                f, g1[0], g1[1], p1[0], p1[1], p1[2], p1[3], t_single))
            print("   %-8s     running:     gain %+.3f dB (sd %.3f)  phase %+.2f deg (sd %.2f, %+.2f..%+.2f)  %.2f s each"
                  "   %d/%d good, %d different records, status %s" % (
                      "", g2[0], g2[1], p2[0], p2[1], p2[2], p2[3],
                      statistics.median(r["total"] for r in recs) if recs else float("nan"),
                      len(good), len(recs), fresh, sorted({r["status"] for r in recs})), flush=True)
            for r in recs:
                if r["bad"]:
                    print("      BAD: %s" % "; ".join(r["bad"]))
            out["steady"].append(dict(freq=f, timebase=tb, single=[(p.gain_db, p.phase_deg) for p in single],
                                      single_s=t_single, running=recs))

        # ---- 2. frequency change before every read
        print("\n2. frequency change before the read (wait is the time after the frequency was set)")
        for f_a in (50.0, 1e3, 1e6):
            f_b = f_a * 1.258925
            gen.set_frequency(STIM.gen_channel, f_a)
            time.sleep(0.3)
            meter.measure(f_a, MEAS, state)                              # timebase for this band
            tb = state.timebase
            run_and_wait(tb)
            for wait in WAITS:
                recs, stop = [], False
                for k in range(10):
                    f = f_b if k % 2 == 0 else f_a
                    gen.set_frequency(STIM.gen_channel, f)
                    time.sleep(wait)
                    try:
                        recs.append(pair(f, tb))
                    except EmptyBlock as e:
                        empty("frequency change at %g Hz, wait %.2f s" % (f_a, wait), e)
                        run_and_wait(tb)
                        stop = True
                        break
                n_bad = sum(1 for r in recs if r["bad"])
                print("   %-8g Hz  wait %.2f s: %2d/%2d good   %s" % (
                    f_a, wait, len(recs) - n_bad, len(recs),
                    "; ".join(sorted({b.split(" fit")[0] for r in recs for b in r["bad"]}))), flush=True)
                out["frequency_change"].append(dict(freq=f_a, timebase=tb, wait=wait, recs=recs, empty=stop))
                if stop:
                    print("      shorter waits skipped for this band")
                    break

        # ---- 3. timebase change before every read
        print("\n3. timebase change before the read (wait is the time after the timebase was set)")
        f = 1e3
        gen.set_frequency(STIM.gen_channel, f)
        time.sleep(0.3)
        meter.measure(f, MEAS, state)
        tb0 = state.timebase
        steps = sorted(scope.caps.timebase_steps)
        tb1 = steps[steps.index(tb0) - 1]
        run_and_wait(tb0)
        for wait in WAITS:
            recs, stop = [], False
            for k in range(8):
                tb = scope.set_timebase(tb1 if k % 2 == 0 else tb0)
                time.sleep(wait)
                try:
                    recs.append(pair(f, tb))
                except EmptyBlock as e:
                    empty("timebase change, wait %.2f s" % wait, e)
                    stop = True
                    break
            n_bad = sum(1 for r in recs if r["bad"])
            print("   wait %.2f s: %2d/%2d good   %s" % (
                wait, len(recs) - n_bad, len(recs),
                "; ".join(sorted({b.split(" fit")[0].split(" dt")[0] for r in recs for b in r["bad"]}))), flush=True)
            out["timebase_change"].append(dict(wait=wait, recs=recs, empty=stop))
            if stop:
                print("      shorter waits skipped")
                break
        state.timebase = None
        out["scope_stats"], out["generator_stats"] = dict(scope.stats), dict(gen.stats)
        print("\nscope counters:", out["scope_stats"])
    except InstrumentUnresponsive as e:
        out["events"].append(dict(where="fatal", error=str(e)))
        print("\nTHE SCOPE STOPPED ANSWERING: %s\n%s" % (e, getattr(e, "advice", "")))
        session.mark_dead(str(e))
    except DriverError as e:
        out["events"].append(dict(where="driver error", error=str(e)))
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
        print("saved", save(os.path.join("m7", "s7_stream.json"), out))


if __name__ == "__main__":
    main()
