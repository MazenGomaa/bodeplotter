import math

import pytest

from bodeplot.drivers.mock import TB_STEPS, VDIV_STEPS
from bodeplot.models import SweepConfig, SweepType
from bodeplot.sweep import autorange, plan


# ------------------------------------------------------------------ plan
def test_log_plan_endpoints_and_count():
    cfg = SweepConfig(SweepType.LOG, 50.0, 20e6, points_per_decade=20)
    f = plan.frequencies(cfg)
    decades = math.log10(20e6 / 50.0)
    assert len(f) == math.ceil(decades * 20) + 1
    assert f[0] == 50.0 and f[-1] == 20e6
    ratios = [b / a for a, b in zip(f, f[1:])]
    assert max(ratios) / min(ratios) == pytest.approx(1.0, rel=1e-9)     # geometric spacing


def test_log_plan_exact_decades():
    f = plan.frequencies(SweepConfig(SweepType.LOG, 100.0, 100e3, points_per_decade=10))
    assert len(f) == 31
    assert f[10] == pytest.approx(1000.0, rel=1e-12)


def test_linear_plan_and_descending():
    f = plan.frequencies(SweepConfig(SweepType.LINEAR, 100.0, 200.0, n_points=11))
    assert f == pytest.approx([100.0 + 10.0 * i for i in range(11)])
    d = plan.frequencies(SweepConfig(SweepType.LINEAR, 100.0, 200.0, n_points=11, descending=True))
    assert d[0] == 200.0 and d[-1] == 100.0


@pytest.mark.parametrize("cfg", [
    SweepConfig(SweepType.LOG, 0.0, 1e3), SweepConfig(SweepType.LOG, 1e3, 1e3),
    SweepConfig(SweepType.LOG, 2e3, 1e3), SweepConfig(SweepType.LOG, 10.0, 1e3, points_per_decade=0),
    SweepConfig(SweepType.LINEAR, 10.0, 1e3, n_points=1)])
def test_plan_validation_errors(cfg):
    with pytest.raises(plan.PlanError):
        plan.frequencies(cfg)


def test_plan_range_checks_and_bandwidth_warning():
    cfg = SweepConfig(SweepType.LOG, 50.0, 20e6)
    p = plan.make_plan(cfg, 1e-6, 30e6, 20.0, 50e6, 50e6)
    assert not p.warnings                                   # 20 MHz is exactly 40 % of 50 MHz
    p = plan.make_plan(SweepConfig(SweepType.LOG, 50.0, 25e6), 1e-6, 30e6, 20.0, 50e6, 50e6)
    assert len(p.warnings) == 1
    with pytest.raises(plan.PlanError):
        plan.make_plan(SweepConfig(SweepType.LOG, 50.0, 40e6), 1e-6, 30e6, 20.0, 50e6)
    with pytest.raises(plan.PlanError):
        plan.make_plan(SweepConfig(SweepType.LOG, 5.0, 1e6), 1e-6, 30e6, 20.0, 50e6)


# ------------------------------------------------------------------ timebase
def test_timebase_uses_real_steps_not_1_2_5():
    # 5 cycles of 20 MHz need 250 ns / 14 div = 17.9 ns/div: the next REAL step is 25 ns
    assert autorange.choose_timebase(20e6, TB_STEPS, 14.0, 5.0) == 2.5e-8
    assert autorange.choose_timebase(1e3, TB_STEPS, 14.0, 5.0) == 5e-4
    assert autorange.choose_timebase(1e6, TB_STEPS, 14.0, 5.0) == 5e-7
    assert autorange.choose_timebase(1.0, TB_STEPS, 14.0, 5.0) == max(TB_STEPS)     # clamps


# ------------------------------------------------------------------ V/div
def test_choose_vdiv_matches_bench_values():
    # Milestone 0c: 1 Vpp through a 10X probe -> 20 mV/div; 50 mVpp -> 1 mV/div
    assert autorange.choose_vdiv(0.1, VDIV_STEPS, 8.0) == 0.02
    assert autorange.choose_vdiv(0.005, VDIV_STEPS, 8.0) == 0.001
    assert autorange.choose_vdiv(1000.0, VDIV_STEPS, 8.0) == max(VDIV_STEPS)


def _converge(vpp_in, start):
    """Simulate the loop: an 8-bit ADC spanning 10.2 divisions clips above that."""
    vdiv, retries = start, 0
    for _ in range(10):
        clipped = vpp_in > 10.2 * vdiv
        seen = min(vpp_in, 10.2 * vdiv)
        d = autorange.decide(seen, clipped, vdiv, VDIV_STEPS, 8.0)
        if d.action != "change":
            return vdiv, retries, d
        vdiv, retries = d.vdiv, retries + 1
    raise AssertionError("did not converge")


@pytest.mark.parametrize("vpp_tip", [1e-3, 3e-3, 0.02, 0.1, 0.7, 1.0, 5.0, 20.0])
@pytest.mark.parametrize("probe", [1.0, 10.0])
@pytest.mark.parametrize("start", [5e-4, 0.2, 20.0])
def test_autorange_converges_within_three_retries(vpp_tip, probe, start):
    vpp_in = vpp_tip / probe
    vdiv, retries, d = _converge(vpp_in, start)
    assert retries <= 3
    assert not vpp_in > 10.2 * vdiv                       # never left clipped
    frac = vpp_in / (8.0 * vdiv)
    # at or below the upper target; or just above it but still on screen, where the next
    # step up would fall below the lower target (hysteresis added in Milestone 7)
    nxt = autorange.step_up(vdiv, VDIV_STEPS, 1)
    assert frac <= 0.8 + 1e-9 or vdiv == max(VDIV_STEPS) or (frac <= 1.0 and vpp_in / (8.0 * nxt) < 0.6)
    if d.action == "floor":
        assert vdiv == min(VDIV_STEPS) and frac < 0.1


def test_clip_steps_up_and_floor_is_reported():
    d = autorange.decide(2.0, True, 0.2, VDIV_STEPS, 8.0)
    assert d.action == "change" and d.vdiv == 20.0         # seven steps up from 0.2, clamped
    d = autorange.decide(1e-5, False, 5e-4, VDIV_STEPS, 8.0)
    assert d.action == "floor"
    d = autorange.decide(0.1, False, 0.02, VDIV_STEPS, 8.0)
    assert d.action == "ok"
