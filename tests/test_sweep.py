import math
import threading

import numpy as np
import pytest

from bodeplot.drivers.base import DriverError
from bodeplot.drivers.mock import SimulatedDUT
from bodeplot.models import (EngineState, Flag, MeasureSettings, Method, ScopeConfig, StimulusConfig,
                             SweepConfig, SweepType)
from bodeplot.sweep.core import Callbacks, SweepRunner


def _runner(session, sweep, no_sleep, cb=None, meas=None, stim=None, scope=None):
    return SweepRunner(session, sweep, stim or StimulusConfig(), scope or ScopeConfig(),
                       meas or MeasureSettings(), cb, sleep=no_sleep)


def _interp_logf(freqs, ys, target):
    """Frequency where ys crosses target, linear in log f."""
    for (f0, y0), (f1, y1) in zip(zip(freqs, ys), zip(freqs[1:], ys[1:])):
        if (y0 - target) * (y1 - target) <= 0 and y0 != y1:
            x = math.log10(f0) + (target - y0) / (y1 - y0) * (math.log10(f1) - math.log10(f0))
            return 10 ** x
    raise AssertionError("no crossing")


def test_rc_lowpass_full_range(make_session, no_sleep):
    r, c = 1e3, 100e-9
    fc = 1 / (2 * math.pi * r * c)                               # 1591.5 Hz
    session = make_session(SimulatedDUT.rc_lpf(r, c), seed=11)
    res = _runner(session, SweepConfig(SweepType.LOG, 50.0, 20e6, 20), no_sleep).run()
    assert res.meta["error"] is None and not res.meta["aborted"]
    f = [p.freq_hz for p in res.points]
    g = [p.gain_db for p in res.points]
    assert f == sorted(f) and f[0] == 50.0 and f[-1] == 20e6
    f3 = _interp_logf(f, g, g[0] - 3.0103)
    assert f3 == pytest.approx(fc, rel=0.02)                     # -3 dB within 2 % of fc
    ph = np.interp(math.log10(fc), np.log10(f), [p.phase_deg for p in res.points])
    assert ph == pytest.approx(-45.0, abs=1.0)                   # -45 deg +/- 1 at fc
    assert all(not (p.flags & Flag.SKEW_UNCHECKED) for p in res.points)
    # far into the stop band the DUT signal sinks towards the noise floor and says so
    assert res.points[-1].gain_db < -60


def test_rlc_bandpass_peak_and_q(make_session, no_sleep):
    r, l, c = 100.0, 1e-3, 100e-9
    f0 = 1 / (2 * math.pi * math.sqrt(l * c))                    # 15.9 kHz
    q = math.sqrt(l / c) / r                                     # 1.0
    session = make_session(SimulatedDUT.rlc_bpf(r, l, c), seed=12)
    res = _runner(session, SweepConfig(SweepType.LOG, 1e3, 300e3, 80), no_sleep).run()
    assert res.meta["error"] is None
    f = np.array([p.freq_hz for p in res.points])
    g = np.array([p.gain_db for p in res.points])
    i = int(np.argmax(g))
    # parabola through the three points around the maximum, in log f
    x = np.log10(f[i - 1:i + 2])
    a, b, _ = np.polyfit(x, g[i - 1:i + 2], 2)
    f_peak = 10 ** (-b / (2 * a))
    assert f_peak == pytest.approx(f0, rel=0.02)                 # peak within 2 %
    level = g.max() - 3.0103
    f_lo = _interp_logf(list(f[:i + 1]), list(g[:i + 1]), level)
    f_hi = _interp_logf(list(f[i:]), list(g[i:]), level)
    assert f_peak / (f_hi - f_lo) == pytest.approx(q, rel=0.05)  # Q within 5 %


def test_callbacks_progress_and_states(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=3)
    seen = dict(points=0, waves=0, progress=[], states=[], logs=[])
    cb = Callbacks(point=lambda p: seen.__setitem__("points", seen["points"] + 1),
                   waveform=lambda w: seen.__setitem__("waves", seen["waves"] + 1),
                   progress=lambda i, n: seen["progress"].append((i, n)),
                   state=seen["states"].append, log=seen["logs"].append)
    res = _runner(session, SweepConfig(SweepType.LOG, 100.0, 10e3, 5), no_sleep, cb).run()
    n = len(res.points)
    assert seen["points"] == n and seen["waves"] == n
    assert seen["progress"][-1] == (n, n)
    assert seen["states"] == [EngineState.CONNECTING, EngineState.RUNNING, EngineState.DONE]
    assert session.source.output == {1: False, 2: False} and session.source.safe_off_calls >= 1
    assert res.config["sweep"]["start_hz"] == 100.0
    assert res.meta["source_idn"] and res.meta["digitizer_idn"] and res.meta["simulated"]


def test_averaging_and_builtin_method(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=4)
    sweep = SweepConfig(SweepType.LOG, 1e3, 3e3, 4)
    res = _runner(session, sweep, no_sleep, meas=MeasureSettings(averages=4)).run()
    assert all(p.n_avg == 4 for p in res.points)
    res_b = _runner(session, sweep, no_sleep, meas=MeasureSettings(method=Method.BUILTIN)).run()
    assert all(p.flags & Flag.BUILTIN for p in res_b.points)
    for a, b in zip(res.points, res_b.points):
        assert b.gain_db == pytest.approx(a.gain_db, abs=0.3)
        assert b.phase_deg == pytest.approx(a.phase_deg, abs=2.0)


def test_out_of_range_sweep_is_an_error_before_any_output(make_session, no_sleep):
    session = make_session(seed=5)
    errors = []
    res = _runner(session, SweepConfig(SweepType.LOG, 50.0, 40e6), no_sleep,
                  Callbacks(error=errors.append)).run()
    assert res.points == [] and "generator" in res.meta["error"] and errors
    assert session.source.output == {1: False, 2: False}


def test_driver_error_keeps_partial_result_and_switches_off(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=6)
    errors, states = [], []

    def on_point(p):
        if p.freq_hz > 400:
            session.digitizer.fail_next = "simulated VISA failure"
    res = _runner(session, SweepConfig(SweepType.LOG, 100.0, 10e3, 5), no_sleep,
                  Callbacks(point=on_point, error=errors.append, state=states.append)).run()
    assert 0 < len(res.points) < 11                               # partial, kept
    assert "simulated VISA failure" in res.meta["error"] and "last command" in res.meta["error"]
    assert errors and states[-1] is EngineState.ERROR
    assert session.source.output == {1: False, 2: False}


def test_acquisition_timeout_counts_as_a_retry_not_a_crash(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=7)
    session.digitizer.timeout_next = 2
    res = _runner(session, SweepConfig(SweepType.LOG, 1e3, 2e3, 3), no_sleep).run()
    assert res.meta["error"] is None
    assert res.points[0].retries >= 2


def test_pause_resume_and_abort(make_session):
    session = make_session(SimulatedDUT.rc_lpf(), seed=8, latency_s=0.002)
    states, got = [], []
    paused, first = threading.Event(), threading.Event()
    runner = SweepRunner(session, SweepConfig(SweepType.LOG, 100.0, 1e6, 10), StimulusConfig(),
                         ScopeConfig(), MeasureSettings(settle_ms=1.0, settle_cycles=0.0),
                         Callbacks(point=lambda p: (got.append(p), first.set()),
                                   state=lambda s: (states.append(s),
                                                    paused.set() if s is EngineState.PAUSED else None)))
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("res", runner.run()))
    t.start()
    assert first.wait(10)
    runner.pause()
    assert paused.wait(10)
    n_paused = len(got)
    threading.Event().wait(0.15)
    assert len(got) == n_paused                                   # nothing measured while paused
    assert session.source.is_on                                   # generator stays on during a pause
    runner.resume()
    while len(got) < n_paused + 2:
        threading.Event().wait(0.005)
    runner.abort()
    t.join(10)
    assert not t.is_alive()
    res = out["res"]
    assert res.meta["aborted"] is True and res.meta["error"] is None
    assert 0 < len(res.points) < 41                               # partial result kept
    assert EngineState.PAUSED in states and EngineState.ABORTING in states
    assert session.source.output == {1: False, 2: False}          # safe_off called


def test_remeasure_replaces_the_point_and_flags_it(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=9)
    runner = _runner(session, SweepConfig(SweepType.LOG, 100.0, 10e3, 5), no_sleep)
    res = runner.run()
    target = res.points[4]
    n = len(res.points)
    new = runner.remeasure(res, target.freq_hz)
    assert len(res.points) == n and res.points[4] is new
    assert new.flags & Flag.REMEASURED
    assert new.gain_db == pytest.approx(target.gain_db, abs=0.2)
    assert session.source.output == {1: False, 2: False}


def test_clipping_start_recovers(make_session, no_sleep):
    session = make_session(SimulatedDUT.through(), seed=10)
    runner = _runner(session, SweepConfig(SweepType.LOG, 1e3, 2e3, 2), no_sleep,
                     stim=StimulusConfig(amp_vpp=10.0),
                     scope=ScopeConfig(probe_atten={1: 1.0, 2: 1.0}))
    res = runner.run()
    assert res.meta["error"] is None
    assert all(not (p.flags & Flag.CLIPPED) for p in res.points)
    assert res.points[0].gain_db == pytest.approx(0.0, abs=0.1)
