"""Through calibration (design of 2026-10-06, SPEC.md section 8.7). No hardware, no Qt
except where a test says so."""
import cmath
import json
import math

import pytest

from bodeplot.models import Flag, PointResult, ThroughCal


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
