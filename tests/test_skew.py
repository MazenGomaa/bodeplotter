"""Channel skew check and correction (SPEC.md section 8.6)."""
import cmath
import math

import pytest

from bodeplot.drivers.mock import SKEW_STATES_S, SimulatedDUT
from bodeplot.measure import skew
from bodeplot.models import Flag, MeasureSettings, ScopeConfig, StimulusConfig, SweepConfig, SweepType
from bodeplot.sweep.core import Session, SweepRunner, run_skew_check, skew_check_frequencies


def _check(session, no_sleep, sweep=None):
    return run_skew_check(session, StimulusConfig(), ScopeConfig(), MeasureSettings(), sweep,
                          sleep=no_sleep)


# ------------------------------------------------------------------ pure functions
def test_known_states_match_the_bench():
    assert skew.KNOWN_STATES_S == (-1.85e-9, 0.15e-9, 2.15e-9, 4.15e-9)
    assert SKEW_STATES_S == skew.KNOWN_STATES_S


@pytest.mark.parametrize("measured_ns, expect_ns, snapped", [
    (0.10, 0.15, True), (2.30, 2.15, True), (4.44, 4.15, True), (-1.60, -1.85, True),
    (1.00, 1.00, False), (0.50, 0.50, False), (6.15, 6.15, False), (-2.20, -2.20, False)])
def test_snap(measured_ns, expect_ns, snapped):
    value, did = skew.snap(measured_ns * 1e-9)
    assert did is snapped
    assert value == pytest.approx(expect_ns * 1e-9, abs=1e-15)


def test_phase_correction_formula():
    f, dt = 20e6, 2.15e-9
    assert skew.correction_deg(f, dt) == pytest.approx(360 * f * dt)          # 15.48 deg
    h = 0.5 * cmath.exp(1j * math.radians(-40.0 + 360 * f * dt))
    out = skew.correct_h(h, f, dt)
    assert abs(out) == pytest.approx(0.5)
    assert math.degrees(cmath.phase(out)) == pytest.approx(-40.0, abs=1e-9)


def test_check_frequencies():
    assert skew.check_frequencies(30e6) == (10e6, 20e6)
    assert skew.check_frequencies(20e6) == (10e6, 20e6)
    assert skew.check_frequencies(1e6) == (0.5e6, 1e6)                        # top of the sweep


def test_evaluate_warnings():
    def h(delay_ns, f, gain_db=0.0):
        return 10 ** (gain_db / 20) * cmath.exp(2j * math.pi * f * delay_ns * 1e-9)
    ok = skew.evaluate([10e6, 20e6], [h(2.1, 10e6), h(2.2, 20e6)])
    assert ok.snapped and ok.delay_s == 2.15e-9 and ok.warnings == []
    off = skew.evaluate([10e6, 20e6], [h(1.0, 10e6), h(1.0, 20e6)])
    assert not off.snapped and off.delay_s == pytest.approx(1.0e-9)
    assert len(off.warnings) == 1 and "known state" in off.warnings[0]
    gain = skew.evaluate([10e6, 20e6], [h(0.15, 10e6, 0.5), h(0.15, 20e6, 0.5)])
    assert gain.snapped and gain.gain_db == pytest.approx(0.5)
    assert len(gain.warnings) == 1 and "Gain mismatch" in gain.warnings[0]
    incons = skew.evaluate([10e6, 20e6], [h(0.0, 10e6), h(0.6, 20e6)])
    assert any("disagree" in w for w in incons.warnings)


# ------------------------------------------------------------------ wizard on the mock
@pytest.mark.parametrize("state", range(4))
def test_wizard_finds_each_injected_state(make_session, no_sleep, state):
    session = make_session(seed=20 + state, skew_state=state, checked=False)
    check = _check(session, no_sleep)
    assert check.snapped
    assert check.delay_s == SKEW_STATES_S[state]
    assert check.measured_s == pytest.approx(SKEW_STATES_S[state], abs=0.1e-9)
    assert check.freqs_hz == [10e6, 20e6]
    assert abs(check.gain_db) < 0.1 and check.warnings == []
    assert session.source.output == {1: False, 2: False}          # output off afterwards
    assert session.digitizer.same_node is False                   # sim probe back on the DUT


@pytest.mark.parametrize("state", range(4))
def test_corrected_phase_within_half_a_degree_at_20_mhz(make_session, no_sleep, state):
    """Inject each skew state; a through connection must read 0 deg after correction."""
    session = make_session(SimulatedDUT.through(), seed=30 + state, skew_state=state, checked=False)
    sweep = SweepConfig(SweepType.LOG, 1e6, 20e6, 5)
    raw = SweepRunner(session, sweep, StimulusConfig(), ScopeConfig(), MeasureSettings(),
                      sleep=no_sleep).run()
    injected_deg = 360 * 20e6 * SKEW_STATES_S[state]
    assert raw.points[-1].phase_deg == pytest.approx(injected_deg, abs=0.5)   # the fault is real
    assert all(p.flags & Flag.SKEW_UNCHECKED for p in raw.points)
    session.accept_skew(_check(session, no_sleep, sweep))
    res = SweepRunner(session, sweep, StimulusConfig(), ScopeConfig(), MeasureSettings(),
                      sleep=no_sleep).run()
    top = res.points[-1]
    assert top.freq_hz == 20e6
    assert abs(top.phase_deg) < 0.5                                # within 0.5 deg at 20 MHz
    assert top.skew_corr_deg == pytest.approx(injected_deg, abs=1e-6)
    assert all(abs(p.phase_deg) < 0.5 for p in res.points)
    assert all(not (p.flags & Flag.SKEW_UNCHECKED) for p in res.points)
    assert res.meta["skew"]["delay_s"] == SKEW_STATES_S[state]
    assert res.meta["skew_applied_s"] == SKEW_STATES_S[state]


def test_correction_does_not_disturb_a_real_dut(make_session, no_sleep):
    r, c = 100.0, 100e-12                                          # fc = 15.9 MHz
    session = make_session(SimulatedDUT.rc_lpf(r, c), seed=40, skew_state=3)
    res = SweepRunner(session, SweepConfig(SweepType.LOG, 1e6, 20e6, 5), StimulusConfig(),
                      ScopeConfig(), MeasureSettings(), sleep=no_sleep).run()
    for p in res.points:
        expect = -math.degrees(math.atan(2 * math.pi * p.freq_hz * r * c))
        assert p.phase_deg == pytest.approx(expect, abs=0.5)


def test_off_grid_delay_and_gain_mismatch_warn_and_use_measured_value(make_session, no_sleep):
    session = make_session(seed=41, skew_state=1, checked=False)
    session.digitizer.extra_delay_s = 0.85e-9                      # 0.15 + 0.85 = 1.00 ns: off grid
    session.digitizer.dut_gain_error_db = 0.5
    check = _check(session, no_sleep)
    assert not check.snapped
    assert check.delay_s == pytest.approx(1.0e-9, abs=0.1e-9) and check.delay_s == check.measured_s
    assert check.gain_db == pytest.approx(0.5, abs=0.05)
    text = " ".join(check.warnings)
    assert "known state" in text and "Gain mismatch" in text
    session.accept_skew(check)
    res = SweepRunner(session, SweepConfig(SweepType.LOG, 5e6, 20e6, 4), StimulusConfig(),
                      ScopeConfig(), MeasureSettings(), sleep=no_sleep).run()
    assert abs(res.points[-1].phase_deg) < 0.5                     # measured value corrects it


def test_check_frequencies_do_not_follow_the_sweep_range(make_session, no_sleep):
    """10 and 20 MHz whatever the sweep range: at 1 MHz a 0.3 ns delay is 0.1 degree, which
    the bench could not resolve (Milestone 7)."""
    session = make_session(seed=42, skew_state=2, checked=False)
    sweep = SweepConfig(SweepType.LOG, 100.0, 2e6, 10)
    assert skew_check_frequencies(session, sweep) == (10e6, 20e6)
    check = _check(session, no_sleep, sweep)
    assert check.freqs_hz == [10e6, 20e6]
    assert check.snapped and check.delay_s == SKEW_STATES_S[2]


def test_check_is_per_session_and_invalidated(make_session, no_sleep):
    session = make_session(seed=43, skew_state=2, checked=False)
    assert not session.skew_valid() and "session" in session.recheck_reason
    session.accept_skew(_check(session, no_sleep))
    assert session.skew_valid() and session.recheck_reason is None
    # 1. a driver resync bumps the epoch
    session.digitizer.simulate_resync()
    assert not session.skew_valid() and "resynchronised" in session.recheck_reason
    assert session.skew_delay() is None
    # 2. the user says the front panel was used
    session.accept_skew(_check(session, no_sleep))
    assert session.skew_valid()
    session.front_panel_used()
    assert not session.skew_valid() and "front panel" in session.recheck_reason
    # 3. reconnect
    session.accept_skew(_check(session, no_sleep))
    session.close()
    session.open()
    assert not session.skew_valid() and session.skew is None


def test_mock_rerolls_the_state_on_open_and_resync():
    session = Session.simulated_session(seed=44)
    seen = {session.digitizer.skew_s}
    epochs = [session.digitizer.alignment_epoch]
    for _ in range(60):
        session.digitizer.simulate_resync()
        seen.add(session.digitizer.skew_s)
        epochs.append(session.digitizer.alignment_epoch)
    session.close()
    assert seen == set(SKEW_STATES_S)                              # all four 2 ns-step states occur
    assert epochs == sorted(set(epochs))                           # strictly increasing


def test_resync_during_a_sweep_is_reported(make_session, no_sleep):
    session = make_session(SimulatedDUT.through(), seed=45, skew_state=1)
    logs = []
    from bodeplot.sweep.core import Callbacks

    done = []

    def on_point(p):
        if not done and p.freq_hz > 2e6:
            done.append(1)
            session.digitizer.simulate_resync()
    res = SweepRunner(session, SweepConfig(SweepType.LOG, 1e6, 20e6, 5), StimulusConfig(),
                      ScopeConfig(), MeasureSettings(),
                      Callbacks(point=on_point, log=lambda e: logs.append(e.text)), sleep=no_sleep).run()
    assert res.meta["error"] is None
    assert any("resynchronised during the sweep" in t for t in logs)
    assert not session.skew_valid()
