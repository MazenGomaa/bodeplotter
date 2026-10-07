"""SweepEngine: the QThread worker that owns all instrument I/O (SPEC.md section 6).

The GUI never touches an instrument. It calls the SweepEngine facade from the
main thread; requests cross to the worker thread as queued signals; results come
back as signals. pause / resume / abort only set thread-safe flags.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from ..drivers.base import DriverError
from ..drivers.mock import SimulatedDUT
from ..measure import skew
from ..measure.meters import MeasureCancelled
from ..models import (EngineState, LogEntry, MeasureSettings, ScopeConfig, SkewCheck, StimulusConfig,
                      SweepConfig, SweepResult, ThroughCal)
from . import calibration
from .core import Callbacks, Session, SweepRunner, _now_iso, run_skew_check, run_through_cal

log = logging.getLogger("bodeplot.engine")


@dataclass
class Configs:
    sweep: SweepConfig
    stimulus: StimulusConfig
    scope: ScopeConfig
    measure: MeasureSettings
    # the skew check's own settings (the wizard); None: the defaults of core.run_skew_check
    skew_freqs: tuple[float, float] | None = None
    skew_captures: int | None = None


@dataclass
class SessionInfo:
    """What the GUI may know about the connection (a snapshot, safe to pass between threads)."""
    connected: bool = False
    simulated: bool = False
    source_idn: str = ""
    digitizer_idn: str = ""
    has_phase: bool = True
    has_builtin: bool = True
    skew: SkewCheck | None = None
    skew_valid: bool = False
    recheck_reason: str | None = None
    skew_text: str = "skew: not checked"
    # The through calibration of this connection (None after a resync). Whether it fits the
    # scope settings on screen is decided by the GUI with calibration.matches().
    cal: ThroughCal | None = None
    cal_valid: bool = False
    cal_text: str = "cal: none"


@dataclass
class ConnectRequest:
    simulate: bool = True
    backend: str = "py"
    source_resource: str = ""
    digitizer_resource: str = ""
    sim_preset: str = "rc_lpf"
    sim_params: dict | None = None
    sim_noise_vrms: float = 1e-4
    sim_latency_s: float = 0.005
    sim_seed: int | None = None
    scope_min_gap_ms: float = 100.0


class EngineWorker(QObject):
    point_measured = Signal(object)         # PointResult
    waveform_captured = Signal(object)      # WaveformPair
    log = Signal(object)                    # LogEntry
    progress = Signal(int, int)
    state_changed = Signal(object)          # EngineState
    finished = Signal(object)               # SweepResult
    error = Signal(str)
    session_changed = Signal(object)        # SessionInfo
    skew_measured = Signal(object)          # SkewCheck (not yet accepted)
    cal_measured = Signal(object)           # ThroughCal (not yet accepted); None = cancelled
    point_remeasured = Signal(object, object)   # SweepResult, PointResult

    def __init__(self):
        super().__init__()
        self.session: Session | None = None
        self.runner: SweepRunner | None = None
        self._cancel_skew = False

    # ---- helpers
    def _info(self) -> SessionInfo:
        s = self.session
        if s is None:
            return SessionInfo()
        valid = s.skew_valid()
        caps = s.digitizer.caps
        cal = s.cal_current()
        return SessionInfo(True, s.simulated, s.source_idn, s.digitizer_idn, True,
                           caps.has_builtin_amplitude and caps.has_builtin_phase, s.skew, valid,
                           s.recheck_reason, skew.describe(s.skew if valid else None),
                           cal=cal, cal_valid=cal is not None, cal_text=calibration.describe(cal))

    def _emit_session(self):
        self._drop_if_dead()
        self.session_changed.emit(self._info())

    def _drop_if_dead(self):
        """Watchdog follow-up: an instrument stopped answering. The generator is already
        off and the partial data are with the GUI; close what is left of the connection."""
        s = self.session
        if s is not None and s.dead_reason:
            s.close()
            self.session = None
            self._say("error", "Disconnected. " + s.dead_reason)

    def _say(self, level: str, text: str):
        self.log.emit(LogEntry(level, text, _now_iso()))

    def _callbacks(self) -> Callbacks:
        return Callbacks(point=self.point_measured.emit, waveform=self.waveform_captured.emit,
                         log=self.log.emit, progress=self.progress.emit,
                         state=self.state_changed.emit, error=self.error.emit)

    # ---- slots (run in the worker thread)
    @Slot(object)
    def connect_instruments(self, req: ConnectRequest):
        self.disconnect_instruments()
        self.state_changed.emit(EngineState.CONNECTING)
        try:
            if req.simulate:
                dut = SimulatedDUT.from_preset(req.sim_preset, **(req.sim_params or {}))
                self.session = Session.simulated_session(dut, latency_s=req.sim_latency_s, seed=req.sim_seed,
                                                         noise_vrms=req.sim_noise_vrms)
                self._say("info", "Connected (simulation): %s | %s | DUT %s" % (
                    self.session.source_idn, self.session.digitizer_idn, dut.name))
            else:
                from ..drivers import connect as real
                self.session = real.open_session(req.backend, req.source_resource, req.digitizer_resource,
                                                 scope_min_gap_s=req.scope_min_gap_ms / 1000.0)
                from ..logging_setup import log_path
                self.session.capture_dir = log_path().parent / "captures"   # rejected captures
                self._say("info", "Connected: %s | %s" % (self.session.source_idn,
                                                          self.session.digitizer_idn))
                for w in self.session.take_warnings():
                    self._say("warn", w)
            self.state_changed.emit(EngineState.IDLE)
        except Exception as e:
            self.session = None
            self._say("error", str(e))
            self.error.emit(str(e))
            self.state_changed.emit(EngineState.ERROR)
        self._emit_session()

    @Slot()
    def disconnect_instruments(self):
        if self.session is not None:
            self.session.close()
            self.session = None
            self._say("info", "Disconnected.")
            self.state_changed.emit(EngineState.IDLE)
        self._emit_session()

    @Slot(object)
    def start_sweep(self, cfg: Configs):
        if self.session is None:
            self.error.emit("Not connected.")
            return
        self.runner = SweepRunner(self.session, cfg.sweep, cfg.stimulus, cfg.scope, cfg.measure,
                                  self._callbacks())
        result = self.runner.run()
        self.runner = None
        self._emit_session()                # a resync during the sweep invalidates the skew check
        self.finished.emit(result)

    @Slot(object, object, float)
    def remeasure(self, cfg: Configs, result: SweepResult, freq_hz: float):
        if self.session is None:
            self.error.emit("Not connected.")
            return
        self.runner = SweepRunner(self.session, cfg.sweep, cfg.stimulus, cfg.scope, cfg.measure,
                                  self._callbacks())
        try:
            point = self.runner.remeasure(result, freq_hz)
            self.point_remeasured.emit(result, point)
        except (DriverError, MeasureCancelled):
            pass                            # already reported through the callbacks
        finally:
            self.runner = None
            self._emit_session()

    @Slot(object)
    def skew_check(self, cfg: Configs):
        if self.session is None:
            self.error.emit("Not connected.")
            return
        self._cancel_skew = False
        self.state_changed.emit(EngineState.RUNNING)
        try:
            check = run_skew_check(self.session, cfg.stimulus, cfg.scope, cfg.measure, cfg.sweep,
                                   should_stop=lambda: self._cancel_skew, on_log=self.log.emit,
                                   freqs=cfg.skew_freqs, captures=cfg.skew_captures)
            self.state_changed.emit(EngineState.IDLE)
            self.skew_measured.emit(check)
        except Exception as e:
            msg = "Skew check failed: %s" % e
            self._say("error", msg)
            self.state_changed.emit(EngineState.ERROR)
            self.error.emit(msg)
        self._emit_session()

    @Slot(object)
    def accept_skew(self, check: SkewCheck):
        if self.session is None:
            return
        if check.alignment_epoch != self.session.digitizer.alignment_epoch:
            self.session.invalidate_skew("The scope was resynchronised after that skew check.")
            self._say("warn", "Skew check discarded: the scope was resynchronised after it.")
        else:
            self.session.accept_skew(check)
            self._say("info", "Channel skew accepted: " + skew.describe(check))
            for w in check.warnings:
                self._say("warn", w)
        self._emit_session()

    @Slot(object)
    def through_cal(self, cfg: Configs):
        if self.session is None:
            self.error.emit("Not connected.")
            return
        self._cancel_skew = False
        self.state_changed.emit(EngineState.RUNNING)
        try:
            cal = run_through_cal(self.session, cfg.stimulus, cfg.scope, cfg.measure,
                                  should_stop=lambda: self._cancel_skew, on_log=self.log.emit,
                                  on_progress=self.progress.emit)
            self.state_changed.emit(EngineState.IDLE)
            self.cal_measured.emit(cal)
        except MeasureCancelled:
            self._say("warn", "Calibration cancelled.")
            self.state_changed.emit(EngineState.IDLE)
            self.cal_measured.emit(None)
        except Exception as e:
            msg = "Calibration failed: %s" % e
            self._say("error", msg)
            self.state_changed.emit(EngineState.ERROR)
            self.error.emit(msg)
        self._emit_session()

    @Slot(object)
    def accept_cal(self, cal: ThroughCal):
        if self.session is None:
            return
        if not cal.acceptable:
            self._say("warn", "Calibration not accepted: " + " ".join(cal.warnings))
        elif cal.alignment_epoch != self.session.digitizer.alignment_epoch:
            self._say("warn", "Calibration discarded: the scope was resynchronised after it.")
        else:
            self.session.accept_cal(cal)
            self._say("info", "Through calibration accepted: %s, %d points, largest gain deviation %.3f dB, "
                              "delay %+.2f ns." % (calibration.range_text(cal), len(cal.freqs_hz),
                                                   calibration.max_gain_db(cal),
                                                   calibration.fitted_delay_s(cal) * 1e9))
            for w in cal.warnings:
                self._say("warn", w)
        self._emit_session()

    @Slot()
    def discard_cal(self):
        if self.session is not None and self.session.cal is not None:
            self.session.invalidate_cal()
            self._say("info", "Through calibration discarded.")
        self._emit_session()

    @Slot()
    def front_panel_used(self):
        if self.session is not None:
            self.session.front_panel_used()
            self._say("warn", self.session.recheck_reason)
        self._emit_session()

    @Slot()
    def simulate_resync(self):
        """Simulation only: what a driver resync does to the scope's alignment."""
        s = self.session
        if s is not None and hasattr(s.digitizer, "simulate_resync"):
            s.digitizer.simulate_resync()
            self._say("warn", "Simulated a scope resync.")
        self._emit_session()

    # ---- called directly from the GUI thread (flags only)
    def pause(self):
        if self.runner:
            self.runner.pause()

    def resume(self):
        if self.runner:
            self.runner.resume()

    def abort(self):
        self._cancel_skew = True            # skew check and calibration
        if self.runner:
            self.runner.abort()


class SweepEngine(QObject):
    """Main-thread facade. Owns the worker thread."""
    _req_connect = Signal(object)
    _req_disconnect = Signal()
    _req_sweep = Signal(object)
    _req_remeasure = Signal(object, object, float)
    _req_skew = Signal(object)
    _req_accept_skew = Signal(object)
    _req_cal = Signal(object)
    _req_accept_cal = Signal(object)
    _req_discard_cal = Signal()
    _req_front_panel = Signal()
    _req_sim_resync = Signal()
    # Results, re-emitted in the main thread. Receivers connect to THESE, never to the
    # worker's own signals: a plain-callable slot connected to a worker signal would run
    # in the worker thread.
    point_measured = Signal(object)
    waveform_captured = Signal(object)
    log = Signal(object)
    progress = Signal(int, int)
    state_changed = Signal(object)
    finished = Signal(object)
    error = Signal(str)
    session_changed = Signal(object)
    skew_measured = Signal(object)
    cal_measured = Signal(object)
    point_remeasured = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.qthread = QThread()
        self.qthread.setObjectName("bodeplot-engine")
        self.worker = EngineWorker()
        self.worker.moveToThread(self.qthread)
        w = self.worker
        self._req_connect.connect(w.connect_instruments)
        self._req_disconnect.connect(w.disconnect_instruments)
        self._req_sweep.connect(w.start_sweep)
        self._req_remeasure.connect(w.remeasure)
        self._req_skew.connect(w.skew_check)
        self._req_accept_skew.connect(w.accept_skew)
        self._req_cal.connect(w.through_cal)
        self._req_accept_cal.connect(w.accept_cal)
        self._req_discard_cal.connect(w.discard_cal)
        self._req_front_panel.connect(w.front_panel_used)
        self._req_sim_resync.connect(w.simulate_resync)
        for name in ("point_measured", "waveform_captured", "log", "progress", "state_changed",
                     "finished", "error", "session_changed", "skew_measured", "cal_measured",
                     "point_remeasured"):
            getattr(w, name).connect(getattr(self, name), Qt.QueuedConnection)
        self.qthread.finished.connect(w.deleteLater)
        self.qthread.start()

    def connect_instruments(self, req: ConnectRequest): self._req_connect.emit(req)
    def disconnect_instruments(self): self._req_disconnect.emit()
    def start_sweep(self, cfg: Configs): self._req_sweep.emit(cfg)
    def remeasure(self, cfg: Configs, result: SweepResult, f: float): self._req_remeasure.emit(cfg, result, f)
    def skew_check(self, cfg: Configs): self._req_skew.emit(cfg)
    def accept_skew(self, check: SkewCheck): self._req_accept_skew.emit(check)
    def run_cal(self, cfg: Configs): self._req_cal.emit(cfg)
    def accept_cal(self, cal: ThroughCal): self._req_accept_cal.emit(cal)
    def discard_cal(self): self._req_discard_cal.emit()
    def front_panel_used(self): self._req_front_panel.emit()
    def simulate_resync(self): self._req_sim_resync.emit()
    def pause(self): self.worker.pause()
    def resume(self): self.worker.resume()
    def abort(self): self.worker.abort()

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        """Abort anything running, switch the generator off, stop the thread."""
        self.abort()
        self._req_disconnect.emit()
        self.qthread.quit()
        ok = self.qthread.wait(timeout_ms)
        if not ok:
            log.error("engine thread did not stop in time")
        return ok
