"""Sweep logic without Qt: session, skew check, sweep runner (SPEC.md section 8).

engine.py wraps this in a QThread worker; the tests drive it directly.
All instrument I/O happens in whichever thread calls these methods.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .. import __version__
from ..drivers.base import Digitizer, DriverError, SignalSource
from ..drivers.mock import SimulatedDUT, make_sim
from ..drivers.scpi import InstrumentUnresponsive
from ..measure import sinefit, skew
from ..measure.meters import DualChannelScopeMeter, MeasureCancelled, MeterState, ResponseMeter
from ..models import (EngineState, Flag, LogEntry, MeasureSettings, PointResult, ScopeConfig,
                      SkewCheck, StimulusConfig, SweepConfig, SweepResult, WaveformPair,
                      config_snapshot)
from . import plan as plan_mod

log = logging.getLogger("bodeplot.sweep")

SKEW_CAPTURES = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------- session
@dataclass
class Session:
    """One connection to a source and a digitizer, and the skew check that belongs to it."""
    source: SignalSource
    digitizer: Digitizer
    simulated: bool = False
    source_idn: str = ""
    digitizer_idn: str = ""
    skew: SkewCheck | None = None
    recheck_reason: str | None = "No skew check has been done in this session."
    # Set by the watchdog when an instrument stops answering: the connection is finished
    # and the engine closes it (SPEC.md section 13).
    dead_reason: str | None = None
    # Where the raw waveforms of a rejected capture go (see save_bad_capture). None: not kept.
    capture_dir: Path | None = None
    captures_saved: int = 0

    @classmethod
    def simulated_session(cls, dut: SimulatedDUT | None = None, **kw) -> "Session":
        src, scope = make_sim(dut, **kw)
        s = cls(src, scope, simulated=True)
        s.open()
        return s

    def open(self, source_resource: str = "SIM::GEN", digitizer_resource: str = "SIM::SCOPE",
             backend: str = "sim") -> None:
        # the generator first: its outputs are forced off before anything else happens
        self.source.open(source_resource, backend)
        try:
            self.digitizer.open(digitizer_resource, backend)
            self.source_idn, self.digitizer_idn = self.source.idn(), self.digitizer.idn()
        except Exception:
            self.close()
            raise
        self.invalidate_skew("Connected: the channel skew must be checked once per session.")

    def take_warnings(self) -> list[str]:
        """Driver warnings meant for the user (e.g. unknown scope firmware), each once."""
        out: list[str] = []
        for dev in (self.source, self.digitizer):
            pending = getattr(dev, "warnings", None)
            if pending:
                out.extend(pending)
                pending.clear()
        return out

    def mark_dead(self, reason: str) -> None:
        self.dead_reason = reason
        self.invalidate_skew("The connection was lost.")

    def lock_panel(self, on: bool) -> None:
        """Keep the scope's front panel out of a running measurement. Never raises:
        a lock that cannot be set is logged, and the measurement goes on."""
        try:
            self.digitizer.lock_panel(on)
        except Exception as e:
            log.warning("front-panel %s failed: %s", "lock" if on else "unlock", e)

    def begin_measurement(self) -> None:
        """Before a sweep, skew check or re-measure: lock the front panel and remember
        the scope's settings for end_measurement(). Never raises."""
        self.lock_panel(True)
        try:
            self.digitizer.save_setup()
        except Exception as e:
            log.warning("could not read the scope's settings; they will not be restored: %s", e)

    def end_measurement(self) -> None:
        """After a sweep, skew check or re-measure: put the scope's settings back, leave
        it running (it stops after every single shot) and give the front panel back.
        Never raises."""
        try:
            self.digitizer.restore_setup()
        except Exception as e:
            log.warning("could not restore the scope's settings: %s", e)
        try:
            self.digitizer.free_run()
        except Exception as e:
            log.warning("could not leave the scope running: %s", e)
        self.lock_panel(False)

    def close(self) -> None:
        try:
            self.source.safe_off()
        finally:
            for dev in (self.source, self.digitizer):
                try:
                    dev.close()
                except Exception:           # closing must not raise
                    pass

    # ---- skew validity (SPEC.md 8.6)
    def invalidate_skew(self, reason: str) -> None:
        self.skew = None
        self.recheck_reason = reason

    def front_panel_used(self) -> None:
        self.invalidate_skew("The front panel was used: the channel skew may have changed.")

    def skew_valid(self) -> bool:
        if self.skew is None:
            return False
        if self.skew.alignment_epoch != self.digitizer.alignment_epoch:
            self.invalidate_skew("The scope connection was resynchronised: the channel skew may "
                                 "have changed.")
            return False
        return True

    def accept_skew(self, check: SkewCheck) -> None:
        self.skew, self.recheck_reason = check, None

    def skew_delay(self) -> float | None:
        return self.skew.delay_s if self.skew_valid() else None


# ---------------------------------------------------------------------- rejected captures
MAX_SAVED_CAPTURES = 50         # per connection: a dead reference must not fill the disk


def save_bad_capture(session: Session, info: dict) -> str:
    """Called by the meter for a capture whose reference fit is not the stimulus. Writes
    both raw waveforms to session.capture_dir as .npz and returns the line for the log."""
    text = ("Bad capture at %g Hz: reference %.4g V, SNR %.0f dB; %s." % (
        info["freq_hz"], info["ref_amp"], info["snr_ref_db"],
        "taken again" if info["will_retry"] else "no retries left, point flagged REF_SUSPECT"))
    folder = session.capture_dir
    if folder is None or session.captures_saved >= MAX_SAVED_CAPTURES:
        return text
    try:
        import numpy as np
        folder.mkdir(parents=True, exist_ok=True)
        session.captures_saved += 1
        path = folder / ("badcapture_%s_%03d_%gHz.npz" % (
            time.strftime("%Y%m%d_%H%M%S"), session.captures_saved, info["freq_hz"]))
        ref, dut = info["waves"][info["ref_channel"]], info["waves"][info["dut_channel"]]
        np.savez_compressed(
            path, freq_hz=info["freq_hz"], timebase=info["timebase"],
            ref_volts=ref.volts, ref_dt=ref.dt, ref_t0=ref.t0, ref_clipped=ref.clipped,
            dut_volts=dut.volts, dut_dt=dut.dt, dut_t0=dut.t0, dut_clipped=dut.clipped,
            vdiv_ref=info["vdiv"].get(info["ref_channel"], 0.0), vdiv_dut=info["vdiv"].get(info["dut_channel"], 0.0),
            snr_ref_db=info["snr_ref_db"], snr_dut_db=info["snr_dut_db"],
            ref_amp=info["ref_amp"], dut_amp=info["dut_amp"])
        return text + " Raw waveforms: %s" % path
    except Exception as e:                          # never let the diagnosis break the sweep
        log.warning("could not save the rejected capture: %s", e)
        return text


# ---------------------------------------------------------------------- skew check
def skew_check_frequencies(session: Session, sweep: SweepConfig | None = None) -> tuple[float, float]:
    """10 MHz and 20 MHz whenever the instruments reach them, whatever the sweep range.
    The check used to stop at the top of the sweep; on the bench (Milestone 7) a check at
    0.5 and 1 MHz could not resolve the delay at all: 0.3 ns is 0.1 degree at 1 MHz, and
    the two frequencies disagreed by 0.32 ns. `sweep` is accepted for compatibility."""
    top = min(session.source.caps.sine_max_hz, session.digitizer.caps.max_hz or
              session.digitizer.caps.bandwidth_hz)
    return skew.check_frequencies(top)


def run_skew_check(session: Session, stim: StimulusConfig, scope_cfg: ScopeConfig,
                   meas: MeasureSettings, sweep: SweepConfig | None = None,
                   should_stop: Callable[[], bool] = lambda: False,
                   sleep: Callable[[float], None] = time.sleep,
                   on_log: Callable[[LogEntry], None] | None = None) -> SkewCheck:
    """Measure delta-t with the reference and DUT probes on the same node (SPEC.md 8.6).
    The caller has already asked the user to connect them. Generator output is
    switched off in a finally block. Does not store the result: see Session.accept_skew."""
    src, dig = session.source, session.digitizer
    freqs = skew_check_frequencies(session, sweep)
    def bad(info):
        text = save_bad_capture(session, info)
        log.warning(text)
        if on_log:
            on_log(LogEntry("warn", text, _now_iso()))

    meter = DualChannelScopeMeter(dig, scope_cfg, should_stop, sleep, on_bad_capture=bad)
    settings = MeasureSettings(**{**meas.__dict__, "averages": SKEW_CAPTURES})
    from ..models import Method
    settings.method = Method.SINEFIT
    same_node = getattr(dig, "sim_set_same_node", None)     # simulation only
    hs = []
    epoch = dig.alignment_epoch
    try:
        if same_node:
            same_node(True)
        session.begin_measurement()
        src.configure_sine(stim.gen_channel, freqs[0], stim.amp_vpp, stim.offset_v, stim.load)
        meter.prepare(stim.amp_vpp, stim.offset_v)
        src.set_output(stim.gen_channel, True)
        state = meter.initial_state()
        for f in freqs:
            if should_stop():
                raise DriverError("skew check cancelled")
            src.set_frequency(stim.gen_channel, f)
            sleep(max(meas.settle_ms / 1000.0, meas.settle_cycles / f))
            point, _ = meter.measure(f, settings, state)
            hs.append(point.h)
            if on_log:
                on_log(LogEntry("info", "Skew check at %g MHz: phase %+.2f deg, gain %+.3f dB"
                                % (f / 1e6, point.phase_deg, point.gain_db), _now_iso()))
    except InstrumentUnresponsive as e:
        src.safe_off()
        session.mark_dead(watchdog_message(e))
        raise DriverError(session.dead_reason, e.last_command)
    finally:
        src.safe_off()
        if same_node:
            same_node(False)
        if session.dead_reason is None:
            session.end_measurement()
    return skew.evaluate(freqs, hs, alignment_epoch=epoch,
                         snap_states=skew.snaps(scope_cfg.ref_channel, scope_cfg.dut_channel))


def watchdog_message(e: InstrumentUnresponsive) -> str:
    return "%s %s" % (str(e).rstrip(".").capitalize() + ".", e.advice or
                      "The generator outputs have been switched off. Power-cycle the instrument and "
                      "connect again.")


# ---------------------------------------------------------------------- runner
@dataclass
class Callbacks:
    point: Callable[[PointResult], None] = lambda p: None
    waveform: Callable[[WaveformPair], None] = lambda w: None
    log: Callable[[LogEntry], None] = lambda e: None
    progress: Callable[[int, int], None] = lambda i, n: None
    state: Callable[[EngineState], None] = lambda s: None
    error: Callable[[str], None] = lambda m: None


class SweepRunner:
    """Runs one sweep (or re-measures one point) on a Session."""

    def __init__(self, session: Session, sweep: SweepConfig, stim: StimulusConfig,
                 scope_cfg: ScopeConfig, meas: MeasureSettings, callbacks: Callbacks | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.session, self.sweep, self.stim, self.scope_cfg, self.meas = session, sweep, stim, scope_cfg, meas
        self.cb = callbacks or Callbacks()
        self._sleep = sleep
        self._abort = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self.state = EngineState.IDLE
        self.last_command: str | None = None

    # ---- control (thread-safe)
    def pause(self) -> None:
        if self.state is EngineState.RUNNING:
            self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def abort(self) -> None:
        self._abort.set()
        self._resume.set()

    @property
    def aborted(self) -> bool:
        return self._abort.is_set()

    # ---- helpers
    def _set_state(self, s: EngineState) -> None:
        self.state = s
        self.cb.state(s)

    def _log(self, level: str, text: str) -> None:
        getattr(log, "warning" if level == "warn" else level)(text)
        self.cb.log(LogEntry(level, text, _now_iso()))

    def _interruptible_sleep(self, seconds: float) -> None:
        if self._sleep is not time.sleep:       # injected (tests): one call, no real waiting
            self._sleep(seconds)
            return
        end = time.perf_counter() + seconds
        while not self._abort.is_set():
            left = end - time.perf_counter()
            if left <= 0:
                return
            self._sleep(min(left, 0.05))

    def _wait_if_paused(self) -> None:
        if not self._resume.is_set():
            self._set_state(EngineState.PAUSED)
            self._resume.wait()
            if not self._abort.is_set():
                self._set_state(EngineState.RUNNING)

    def _should_stop(self) -> bool:
        return self._abort.is_set()

    def make_plan(self) -> plan_mod.Plan:
        s, d = self.session.source.caps, self.session.digitizer.caps
        return plan_mod.make_plan(self.sweep, s.sine_min_hz, s.sine_max_hz, d.min_hz,
                                  d.max_hz or d.bandwidth_hz, d.bandwidth_hz)

    def _apply_skew(self, point: PointResult, delay_s: float | None) -> PointResult:
        if delay_s is None:
            point.flags |= Flag.SKEW_UNCHECKED
            return point
        point.skew_corr_deg = skew.correction_deg(point.freq_hz, delay_s)
        point.h = skew.correct_h(point.h, point.freq_hz, delay_s)
        point.gain_db, point.phase_deg = sinefit.gain_phase(point.h)
        return point

    def _meta(self, started: str, delay_s: float | None, aborted: bool, error: str | None) -> dict:
        s = self.session
        return {
            "app_version": __version__, "started": started, "finished": _now_iso(),
            "source_idn": s.source_idn, "digitizer_idn": s.digitizer_idn, "simulated": s.simulated,
            "aborted": aborted, "error": error,
            "skew": s.skew.to_meta() if (delay_s is not None and s.skew is not None) else None,
            "skew_applied_s": delay_s,
            "skew_text": skew.describe(s.skew if delay_s is not None else None),
        }

    def _measure_one(self, meter: ResponseMeter, state: MeterState, f: float,
                     delay_s: float | None) -> PointResult:
        src, st = self.session.source, self.stim
        self.last_command = "set_frequency %g" % f
        src.set_frequency(st.gen_channel, f)
        self._interruptible_sleep(max(self.meas.settle_ms / 1000.0, self.meas.settle_cycles / f))
        self.last_command = "measure %g Hz" % f
        point, pair = meter.measure(f, self.meas, state)
        point = self._apply_skew(point, delay_s)
        self.cb.point(point)
        if pair is not None:
            self.cb.waveform(pair)
        return point

    def _start(self, first_freq: float) -> tuple[ResponseMeter, MeterState]:
        src, st = self.session.source, self.stim
        self.last_command = "configure_sine"
        src.configure_sine(st.gen_channel, first_freq, st.amp_vpp, st.offset_v, st.load)
        meter = DualChannelScopeMeter(
            self.session.digitizer, self.scope_cfg, self._should_stop, self._interruptible_sleep,
            on_bad_capture=lambda info: self._log("warn", save_bad_capture(self.session, info)))
        self.last_command = "configure scope"
        meter.prepare(st.amp_vpp, st.offset_v)
        self.last_command = "output on"
        src.set_output(st.gen_channel, True)
        return meter, meter.initial_state()

    # ---- operations
    def run(self) -> SweepResult:
        started = _now_iso()
        points: list[PointResult] = []
        error: str | None = None
        delay_s = self.session.skew_delay()
        config = config_snapshot(self.sweep, self.stim, self.scope_cfg, self.meas)
        p = None
        try:
            self._set_state(EngineState.CONNECTING)
            p = self.make_plan()
            for w in p.warnings:
                self._log("warn", w)
            if delay_s is None:
                self._log("warn", "No valid channel skew check: phase is NOT corrected and every "
                                  "point is flagged SKEW_UNCHECKED. " + (self.session.recheck_reason or ""))
            else:
                self._log("info", "Channel skew correction: %+.2f ns." % (delay_s * 1e9))
            self.session.begin_measurement()
            meter, state = self._start(p.freqs_hz[0])
            self._set_state(EngineState.RUNNING)
            n = len(p.freqs_hz)
            for i, f in enumerate(p.freqs_hz):
                self._wait_if_paused()
                if self._abort.is_set():
                    break
                try:
                    points.append(self._measure_one(meter, state, f, delay_s))
                except MeasureCancelled:
                    break                               # aborted mid-point: not an error
                self.cb.progress(i + 1, n)
            if self._abort.is_set():
                self._set_state(EngineState.ABORTING)
                self._log("warn", "Sweep aborted after %d of %d points." % (len(points), n))
        except plan_mod.PlanError as e:
            error = str(e)
        except InstrumentUnresponsive as e:
            # Watchdog: the instrument is gone. Generator off first (also in the finally
            # below), stop here, keep the points measured so far, tell the user what to do.
            self.session.source.safe_off()
            self.session.mark_dead(watchdog_message(e))
            error = "%s %d of %d points were measured and are kept. (last command: %s)" % (
                self.session.dead_reason, len(points), len(p.freqs_hz) if p else 0,
                e.last_command or self.last_command)
        except DriverError as e:
            error = "%s (last command: %s)" % (e, e.last_command or self.last_command)
        except Exception as e:                      # keep partial results whatever happens
            log.exception("sweep failed")
            error = "%s: %s (last command: %s)" % (type(e).__name__, e, self.last_command)
        finally:
            self.session.source.safe_off()
            if self.session.dead_reason is None:
                self.session.end_measurement()
        # an epoch change during the sweep means the correction may be stale
        if delay_s is not None and not self.session.skew_valid() and self.session.dead_reason is None:
            self._log("warn", "The scope was resynchronised during the sweep; the skew correction "
                              "used may no longer be right. Re-check the skew.")
        points.sort(key=lambda q: q.freq_hz)
        result = SweepResult(config, points, self._meta(started, delay_s, self._abort.is_set(), error))
        if error:
            self._log("error", error)
            self._set_state(EngineState.ERROR)
            self.cb.error(error)
        else:
            self._set_state(EngineState.DONE)
        return result

    def remeasure(self, result: SweepResult, freq_hz: float) -> PointResult:
        """Re-measure one point with the full per-point procedure and replace it."""
        delay_s = self.session.skew_delay()
        try:
            self._set_state(EngineState.RUNNING)
            self.session.begin_measurement()
            meter, state = self._start(freq_hz)
            point = self._measure_one(meter, state, freq_hz, delay_s)
            point.flags |= Flag.REMEASURED
        except MeasureCancelled:
            self._set_state(EngineState.DONE)
            raise
        except DriverError as e:
            if isinstance(e, InstrumentUnresponsive):
                self.session.source.safe_off()
                self.session.mark_dead(watchdog_message(e))
                msg = "%s (last command: %s)" % (self.session.dead_reason, e.last_command or self.last_command)
            else:
                msg = "%s (last command: %s)" % (e, e.last_command or self.last_command)
            self._log("error", msg)
            self._set_state(EngineState.ERROR)
            self.cb.error(msg)
            raise
        finally:
            self.session.source.safe_off()
            if self.session.dead_reason is None:
                self.session.end_measurement()
        for i, q in enumerate(result.points):
            if abs(q.freq_hz - freq_hz) <= 1e-9 * freq_hz:
                result.points[i] = point
                break
        else:
            result.points.append(point)
            result.points.sort(key=lambda q: q.freq_hz)
        self._set_state(EngineState.DONE)
        return point
