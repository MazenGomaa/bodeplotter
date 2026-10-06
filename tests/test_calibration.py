"""Through calibration (design of 2026-10-06, SPEC.md section 8.7). No hardware, no Qt
except where a test says so."""
import cmath
import json
import math

import pytest

from bodeplot.drivers.base import DriverError
from bodeplot.drivers.mock import SimulatedDUT
from bodeplot.measure.meters import MeasureCancelled
from bodeplot.models import (Flag, MeasureSettings, PointResult, ScopeConfig, StimulusConfig, SweepConfig,
                             SweepType, ThroughCal)
from bodeplot.sweep import calibration
from bodeplot.sweep.core import SweepRunner, run_through_cal, through_cal_frequencies


def make_cal(freqs, hs, **kw):
    base = dict(checked_at="2026-10-06T21:15:00+02:00", alignment_epoch=1, ref_channel=1, dut_channel=2,
                probe_atten={1: 10.0, 2: 10.0}, coupling="DC", bw_limit=False, amp_vpp=1.0)
    base.update(kw)
    return ThroughCal(freqs_hz=list(freqs), h=list(hs), **base)


def _h(gain_db, deg):
    return cmath.rect(10 ** (gain_db / 20.0), math.radians(deg))


def _point(f, gain_db=0.0, deg=0.0, vref=0.5, flags=Flag.NONE):
    h = _h(gain_db, deg)
    return PointResult(freq_hz=f, h=h, gain_db=gain_db, phase_deg=deg, vref_amp=vref, vdut_amp=vref * abs(h),
                       vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1, snr_ref_db=50.0,
                       snr_dut_db=50.0, flags=flags, duration_s=0.1)


# ------------------------------------------------------------------ data model
def test_calibrated_flag_is_the_last_one_and_survives_text():
    assert list(Flag)[-1] is Flag.CALIBRATED
    assert Flag.from_text("PREVIEW|CALIBRATED") == Flag.PREVIEW | Flag.CALIBRATED


def test_calibrated_is_a_quiet_flag():
    from bodeplot.gui import bode_plot
    from bodeplot.io import export_image
    assert Flag.CALIBRATED & bode_plot.QUIET and Flag.CALIBRATED & export_image.QUIET


def test_point_result_has_calibration_fields_that_default_to_zero():
    p = _point(1e3)
    assert p.cal_gain_db == 0.0 and p.cal_phase_deg == 0.0


def test_through_cal_goes_through_json_and_back():
    cal = make_cal([100.0, 1e3], [_h(0.1, 1.0), _h(0.2, 2.0)], warnings=["w"])
    assert cal.acceptable is True
    back = ThroughCal.from_meta(json.loads(json.dumps(cal.to_meta())))
    assert back == cal and back.probe_atten == {1: 10.0, 2: 10.0}
    assert ThroughCal.from_meta(None) is None and ThroughCal.from_meta({"freqs_hz": [1.0]}) is None
    assert ThroughCal.from_meta("applied") is None


# ------------------------------------------------------------------ pure functions
def test_frequencies_cover_the_instruments_at_ten_per_decade():
    f = calibration.frequencies(1e-6, 30e6, 20.0, 50e6, 50e6)      # the mock pair and the real pair
    assert f[0] == 50.0 and f[-1] == 20e6 and len(f) == 58 and f == sorted(f)
    f = calibration.frequencies(1e-6, 5e6, 100.0, 50e6, 50e6)      # a narrower pair
    assert f[0] == 100.0 and f[-1] == 5e6
    with pytest.raises(ValueError):
        calibration.frequencies(1e6, 2e6, 5e6, 50e6, 50e6)


def test_response_is_exact_at_a_point_and_within_a_tenth_of_a_percent():
    cal = make_cal([100.0, 1e3, 1e4], [_h(0.0, 0.0), _h(0.1, 1.0), _h(0.2, 2.0)])
    assert calibration.response_at(cal, 1e3) == cal.h[1]
    assert calibration.response_at(cal, 1e3 * 1.0009) == cal.h[1]
    assert calibration.response_at(cal, 1e4 * 1.0009) == cal.h[2]  # just beyond the last point


def test_no_extrapolation():
    cal = make_cal([100.0, 1e3, 1e4], [_h(0.0, 0.0), _h(0.1, 1.0), _h(0.2, 2.0)])
    for f in (99.0, 1e4 * 1.002, 0.0, -5.0):
        assert calibration.response_at(cal, f) is None
        assert calibration.correct(1 + 0j, cal, f) is None
    assert calibration.covers(cal, 100.0, 1e4) and calibration.covers(cal, 100.0 * 0.9995, 1e4 * 1.0005)
    assert not calibration.covers(cal, 50.0, 1e4) and not calibration.covers(cal, 100.0, 2e4)


def test_gain_is_interpolated_linearly_in_db_over_log_frequency():
    cal = make_cal([1e3, 1e4], [_h(0.0, 0.0), _h(0.2, 0.0)])
    h = calibration.response_at(cal, 10 ** 3.5)
    assert 20 * math.log10(abs(h)) == pytest.approx(0.1, abs=1e-9)
    assert math.degrees(cmath.phase(h)) == pytest.approx(0.0, abs=1e-9)


def test_a_pure_delay_is_interpolated_exactly():
    dt = 2.15e-9
    freqs = [1e6, 2e6, 5e6, 1e7, 2e7]
    cal = make_cal(freqs, [cmath.exp(2j * math.pi * f * dt) for f in freqs])
    assert calibration.fitted_delay_s(cal) == pytest.approx(dt, rel=1e-9)
    for f in (1.5e6, 3e6, 7e6, 1.5e7):
        h = calibration.response_at(cal, f)
        assert abs(h) == pytest.approx(1.0, abs=1e-12)
        assert math.degrees(cmath.phase(h)) == pytest.approx(360 * f * dt, abs=1e-6)


def test_phase_is_unwrapped_before_interpolating():
    cal = make_cal([1e6, 2e6], [_h(0.0, 170.0), _h(0.0, -170.0)])  # 170 and 190 degrees
    deg = math.degrees(cmath.phase(calibration.response_at(cal, 1.4e6)))
    assert abs(deg) > 150.0             # near +-180, not near 0 as the wrapped values would give


def test_correct_divides_and_reports_what_was_removed():
    cal = make_cal([1e3, 1e4], [_h(0.2, 10.0), _h(0.2, 10.0)])
    h, db, deg = calibration.correct(_h(-3.0, -35.0), cal, 1e3)
    assert 20 * math.log10(abs(h)) == pytest.approx(-3.2) and math.degrees(cmath.phase(h)) == pytest.approx(-45.0)
    assert db == pytest.approx(0.2) and deg == pytest.approx(10.0)
    assert calibration.max_gain_db(cal) == pytest.approx(0.2)


def test_a_dead_calibration_point_gives_no_correction():
    cal = make_cal([1e3, 1e4], [0j, 0j])
    assert calibration.correct(1 + 0j, cal, 1e3) is None
    assert calibration.correct(1 + 0j, cal, 3e3) is None


def test_matches_compares_channels_probes_coupling_and_bandwidth_limit():
    cal = make_cal([1e3], [1 + 0j])
    assert calibration.matches(cal, ScopeConfig())
    assert not calibration.matches(None, ScopeConfig())
    assert not calibration.matches(cal, ScopeConfig(ref_channel=2, dut_channel=1))
    assert not calibration.matches(cal, ScopeConfig(dut_channel=3, probe_atten={1: 10.0, 3: 10.0}))
    assert not calibration.matches(cal, ScopeConfig(probe_atten={1: 10.0, 2: 1.0}))
    assert not calibration.matches(cal, ScopeConfig(coupling="AC"))
    assert not calibration.matches(cal, ScopeConfig(bw_limit=True))
    # settings that do not change the measurement paths do not matter
    assert calibration.matches(cal, ScopeConfig(target_cycles=8.0, probe_atten={1: 10.0, 2: 10.0, 3: 1.0}))


def test_texts():
    cal = make_cal([50.0, 20e6], [1 + 0j, 1 + 0j])
    assert calibration.range_text(cal) == "50 Hz to 20 MHz"
    assert calibration.describe(cal) == "cal: 21:15, 50 Hz to 20 MHz"
    assert calibration.describe(None) == "cal: none"


def test_evaluate_a_good_through():
    pts = [_point(f, 0.05, 0.2) for f in (20e6, 50.0, 1e3)]         # any order in
    cal = calibration.evaluate(pts, ScopeConfig(), 1.0, alignment_epoch=7)
    assert cal.freqs_hz == [50.0, 1e3, 20e6] and cal.alignment_epoch == 7
    assert cal.acceptable and cal.warnings == []
    assert (cal.ref_channel, cal.dut_channel, cal.coupling, cal.bw_limit, cal.amp_vpp) == (1, 2, "DC", False, 1.0)
    assert cal.probe_atten == {1: 10.0, 2: 10.0} and cal.checked_at.startswith("20")
    assert cal.h[0] == pts[1].h


def test_evaluate_warns_about_a_gain_mismatch_but_accepts_it():
    cal = calibration.evaluate([_point(1e3, 0.0), _point(1e6, 0.5)], ScopeConfig(), 1.0)
    assert cal.acceptable and len(cal.warnings) == 1
    assert "Gain mismatch" in cal.warnings[0] and "1 MHz" in cal.warnings[0]


@pytest.mark.parametrize("points, expect", [
    ([_point(1e3, 0.0), _point(1e5, -3.0)], calibration.NOT_A_THROUGH),                 # a filter
    ([_point(1e3, 0.0, vref=0.1)], calibration.NOT_A_THROUGH),                          # 0.2 Vpp of 1 Vpp
    ([_point(1e3, float("-inf"))], calibration.NOT_A_THROUGH),                          # dead DUT channel
    ([_point(1e3), _point(2e3, flags=Flag.CLIPPED)], "CLIPPED at 2 kHz"),
    ([_point(1e3, flags=Flag.REF_SUSPECT | Flag.LOW_SNR)], "REF_SUSPECT at 1 kHz"),
    ([_point(1e3, flags=Flag.BELOW_FLOOR)], "BELOW_FLOOR at 1 kHz"),
    ([_point(1e3, flags=Flag.AUTORANGE_FAILED)], "AUTORANGE_FAILED at 1 kHz")])
def test_evaluate_refuses(points, expect):
    cal = calibration.evaluate(points, ScopeConfig(), 1.0)
    assert not cal.acceptable and any(expect in w for w in cal.warnings)


def test_evaluate_does_not_list_every_bad_point():
    pts = [_point(1e3 * (i + 1), flags=Flag.CLIPPED) for i in range(20)]
    cal = calibration.evaluate(pts, ScopeConfig(), 1.0)
    assert not cal.acceptable and len(cal.warnings) <= 7 and "more" in cal.warnings[-1]
    with pytest.raises(ValueError):
        calibration.evaluate([], ScopeConfig(), 1.0)


# ------------------------------------------------------------------ simulated paths
def test_mock_dut_channel_can_tilt_with_frequency(make_session, no_sleep):
    session = make_session(SimulatedDUT.through(), seed=60, checked=False, skew_enabled=False)
    session.digitizer.dut_gain_tilt_db_at_20mhz = 0.2
    res = SweepRunner(session, SweepConfig(SweepType.LOG, 100.0, 20e6, 2), StimulusConfig(), ScopeConfig(),
                      MeasureSettings(), sleep=no_sleep).run()
    assert res.points[0].freq_hz == 100.0 and res.points[-1].freq_hz == 20e6
    for p in res.points:                                          # flat to 1 kHz, then linear in log f
        expect = 0.2 * math.log10(p.freq_hz / 1e3) / math.log10(20e6 / 1e3) if p.freq_hz > 1e3 else 0.0
        assert p.gain_db == pytest.approx(expect, abs=0.02), p.freq_hz
    assert res.points[-1].gain_db == pytest.approx(0.2, abs=0.02)


# ------------------------------------------------------------------ measuring it
def _calibrate(session, no_sleep, scope=None, meas=None, **kw):
    return run_through_cal(session, StimulusConfig(), scope or ScopeConfig(), meas or MeasureSettings(),
                           sleep=no_sleep, **kw)


def test_calibration_finds_the_tilt_and_the_delay(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=61, skew_state=2, checked=False)   # +2.15 ns
    session.digitizer.dut_gain_tilt_db_at_20mhz = 0.2
    progress = []
    cal = _calibrate(session, no_sleep, on_progress=lambda i, n: progress.append((i, n)))
    assert cal.freqs_hz == through_cal_frequencies(session)
    assert cal.freqs_hz[0] == 50.0 and cal.freqs_hz[-1] == 20e6 and len(cal.freqs_hz) == 58
    assert progress[0] == (1, 58) and progress[-1] == (58, 58)
    assert cal.acceptable and cal.warnings == []
    assert calibration.fitted_delay_s(cal) == pytest.approx(2.15e-9, abs=0.05e-9)
    assert calibration.max_gain_db(cal) == pytest.approx(0.2, abs=0.03)
    assert cal.alignment_epoch == session.digitizer.alignment_epoch
    # the simulated DUT probe was moved to the reference node and is back; nothing was stored
    assert session.digitizer.same_node is False and session.cal is None
    assert session.source.output == {1: False, 2: False}
    assert session.skew is None                                    # no skew check was made of it


def test_calibration_is_never_a_fast_preview(make_session, no_sleep):
    from bodeplot.models import Method
    session = make_session(seed=62, checked=False)
    cal = _calibrate(session, no_sleep, meas=MeasureSettings(method=Method.PREVIEW))
    assert cal.acceptable and session.digitizer.running_reads == 0


def test_a_filter_is_refused(make_session, no_sleep):
    session = make_session(SimulatedDUT.rc_lpf(), seed=63, checked=False)
    session.digitizer.sim_set_same_node = lambda on: None           # the probe stays on the filter
    cal = _calibrate(session, no_sleep)
    assert not cal.acceptable and any(calibration.NOT_A_THROUGH in w for w in cal.warnings)


def test_a_gain_mismatch_is_a_warning_only(make_session, no_sleep):
    session = make_session(seed=64, checked=False)
    session.digitizer.dut_gain_error_db = 0.5
    cal = _calibrate(session, no_sleep)
    assert cal.acceptable and any("Gain mismatch" in w for w in cal.warnings)


def test_cancel_leaves_no_result_and_the_generator_off(make_session, no_sleep):
    session = make_session(seed=65, checked=False)
    seen = []
    with pytest.raises(MeasureCancelled):
        _calibrate(session, no_sleep, on_progress=lambda i, n: seen.append(i),
                   should_stop=lambda: len(seen) >= 3)
    assert len(seen) == 3 and session.cal is None
    assert session.source.output == {1: False, 2: False} and session.digitizer.same_node is False


def test_a_resync_during_the_calibration_is_refused(make_session, no_sleep):
    session = make_session(seed=66, checked=False)

    def on_progress(i, n):
        if i == 5:
            session.digitizer.simulate_resync()
    with pytest.raises(DriverError, match="resynchronised"):
        _calibrate(session, no_sleep, on_progress=on_progress)
    assert session.source.output == {1: False, 2: False}


def test_a_generator_fault_switches_off_and_restores(make_session, no_sleep):
    session = make_session(seed=67, checked=False)
    before = session.digitizer.timebase

    def on_progress(i, n):
        if i == 2:
            session.source.fail_next = "generator said no"
    with pytest.raises(DriverError, match="generator said no"):
        _calibrate(session, no_sleep, on_progress=on_progress)
    assert session.source.output == {1: False, 2: False}
    assert session.digitizer.timebase == before and session.digitizer.same_node is False


# ------------------------------------------------------------------ validity
def test_validity(make_session, no_sleep):
    session = make_session(seed=68, checked=False)
    assert session.cal_for(ScopeConfig()) is None
    cal = _calibrate(session, no_sleep)
    session.accept_cal(cal)
    assert session.cal_for(ScopeConfig()) is cal
    assert not session.skew_valid()                                # an independent record
    # other settings: not used, but kept (the user may switch back)
    for other in (ScopeConfig(ref_channel=2, dut_channel=1),
                  ScopeConfig(probe_atten={1: 10.0, 2: 1.0}),
                  ScopeConfig(coupling="AC"), ScopeConfig(bw_limit=True)):
        assert session.cal_for(other) is None
    assert session.cal is cal and session.cal_for(ScopeConfig()) is cal
    # a resync ends it for good
    session.digitizer.simulate_resync()
    assert session.cal_for(ScopeConfig()) is None and session.cal is None
    # front panel
    session.accept_cal(_calibrate(session, no_sleep))
    session.front_panel_used()
    assert session.cal is None
    # reconnect
    session.accept_cal(_calibrate(session, no_sleep))
    session.close()
    session.open()
    assert session.cal is None and session.cal_for(ScopeConfig()) is None
    # a lost connection
    session.accept_cal(_calibrate(session, no_sleep))
    session.mark_dead("gone")
    assert session.cal is None
