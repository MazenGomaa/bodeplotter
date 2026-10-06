"""The real drivers against simulated SCPI instruments (tests/fakes.py). No hardware."""
import math
import re
from pathlib import Path

import numpy as np
import pytest

from bodeplot.drivers import connect, registry, step_tables
from bodeplot.drivers.base import AcquireTimeout, DriverError
from bodeplot.drivers.scpi import BlockedCommand, InstrumentUnresponsive, plain_decimal
from bodeplot.drivers.uni_t_upo1000 import UniTUPO1000
from bodeplot.drivers.uni_t_utg900e import UniTUTG900E
from bodeplot.measure import sinefit
from bodeplot.models import MeasureSettings, ScopeConfig, StimulusConfig, SweepConfig
from bodeplot.sweep import autorange
from bodeplot.sweep.core import Session, SweepRunner, run_skew_check
from fakes import FakeClock, FakeGen, FakeScope

SRC = Path(__file__).resolve().parents[1] / "src" / "bodeplot"


def make_scope(tmp_path=None, **kw):
    clock = FakeClock()
    fake = FakeScope(clock, **kw)
    drv = UniTUPO1000(lambda r, b: fake, sleep=clock.sleep, clock=clock.now,
                      user_tables=(tmp_path / "step_tables.json") if tmp_path else None)
    return drv, fake, clock


def make_gen():
    clock = FakeClock()
    fake = FakeGen(clock)
    drv = UniTUTG900E(lambda r, b: fake, sleep=clock.sleep, clock=clock.now)
    return drv, fake, clock


def opened_scope(tmp_path=None, **kw):
    drv, fake, clock = make_scope(tmp_path, **kw)
    drv.open("FAKE::SCOPE", "py")
    return drv, fake, clock


def ready_scope(vdiv=0.02, tb=2e-4):
    """Opened, both channels configured for 10X probes, triggered on CH1."""
    drv, fake, clock = opened_scope()
    for ch in (1, 2):
        drv.configure_channel(ch, "DC", 10.0, False, 0.0)
        drv.set_vdiv(ch, vdiv)
    drv.set_timebase(tb)
    drv.set_trigger_edge(1, 0.0)
    return drv, fake, clock


# ---------------------------------------------------------------------- step tables
def test_shipped_tables_are_the_measured_ones():
    t = step_tables.SHIPPED[("UPO1054", "1. 01. 0047")]
    assert 2.5e-8 in t.timebase and 2e-8 not in t.timebase          # 25 ns, no 20 ns
    assert max(t.timebase) == 2e-2                                  # nothing at 50 ms/div or slower
    assert t.vdiv[0] == 5e-4 and t.vdiv[-1] == 20.0 and len(t.vdiv) == 15
    assert list(t.timebase) == sorted(set(t.timebase)) and len(t.timebase) == 23


def test_unknown_firmware_uses_stored_tables_and_warns_once(tmp_path):
    drv, fake, _ = make_scope(tmp_path, idn="UNI-T Technologies,UPO1054,SIM0001,9. 99. 0001")
    drv.open("FAKE::SCOPE", "py")
    assert not drv.tables_exact and drv.tables is step_tables.FALLBACK
    assert len(drv.warnings) == 1 and "--walk-tables" in drv.warnings[0]
    s = Session(UniTUTG900E(lambda r, b: FakeGen(FakeClock())), drv)
    assert len(s.take_warnings()) == 1 and s.take_warnings() == []   # delivered once


def test_known_firmware_has_no_warning_and_never_walks(tmp_path):
    drv, fake, _ = opened_scope(tmp_path)
    assert drv.tables_exact and drv.warnings == []
    assert not any(c.endswith((" UP", " DOWN")) for c in fake.sent())
    assert not any("SCALe " in c for c in fake.sent())               # connect changes no scale at all


def test_walked_tables_in_the_settings_folder_take_precedence(tmp_path):
    step_tables.save_user(tmp_path / "step_tables.json", "UPO1054", "9. 99. 0001",
                          [1e-6, 2e-6, 5e-6, 1e-5, 2e-5], [0.01, 0.02, 0.05, 0.1, 0.2], "test walk")
    drv, _, _ = make_scope(tmp_path, idn="UNI-T Technologies,UPO1054,SIM0001,9. 99. 0001")
    drv.open("FAKE::SCOPE", "py")
    assert drv.tables_exact and drv.warnings == []
    assert drv.caps.timebase_steps == (1e-6, 2e-6, 5e-6, 1e-5, 2e-5)


# ---------------------------------------------------------------------- scope: I/O rules
def test_scope_caps_come_from_the_idn():
    drv, _, _ = opened_scope()
    assert drv.caps.model == "UPO1054" and drv.caps.channels == 4 and drv.caps.bandwidth_hz == 50e6
    assert drv.caps.vertical_divs == 8.0 and drv.caps.data_vertical_divs == pytest.approx(10.12)
    assert not drv.caps.has_builtin_phase


def test_numbers_are_plain_decimals_and_every_write_is_followed_by_opc():
    drv, fake, _ = ready_scope(vdiv=0.001, tb=2.5e-8)
    sent = fake.sent()
    assert ":TIMebase:SCALe 0.000000025" in sent and ":CHANnel1:SCALe 0.001" in sent
    assert ":CHANnel1:PROBe 1X" in sent                              # X suffix; scope stays at 1X
    assert fake.ch[1]["probe"] == 1.0 and drv.probe[1] == 10.0       # ratio applied in software
    assert not any(re.search(r"\d[eE][+-]?\d", c) for c in sent)
    start = sent.index("*OPC?")          # everything after the resync that opens the connection
    for i, c in enumerate(sent[:-1]):
        if i > start and "?" not in c:
            assert sent[i + 1] == "*OPC?", (c, sent[i + 1])
    assert fake.timebase == 2.5e-8 and fake.ch[1]["scale"] == 0.001


def test_plain_decimal():
    assert plain_decimal(1e-9) == "0.000000001" and plain_decimal(2e7) == "20000000"
    assert plain_decimal(0.1 + 0.2) == "0.3" and plain_decimal(-0.0) == "0"
    with pytest.raises(ValueError):
        plain_decimal(float("nan"))


@pytest.mark.parametrize("gap", [0.1, 0.25])
def test_minimum_gap_after_timebase_and_vdiv_changes(gap):
    clock = FakeClock()
    fake = FakeScope(clock)
    drv = UniTUPO1000(lambda r, b: fake, min_gap_s=gap, sleep=clock.sleep, clock=clock.now)
    drv.open("FAKE::SCOPE", "py")
    drv.configure_channel(1, "DC", 10.0, False, 0.0)        # as the app does: scope ratio 1X first
    for v in (0.05, 0.02, 0.5):
        drv.set_vdiv(1, v)
    for tb in (1e-3, 2.5e-8, 1e-5):
        drv.set_timebase(tb)
    log = fake.log
    changes = [i for i, (_, c) in enumerate(log) if re.match(r":(TIMebase|CHANnel\d):SCALe \d", c)]
    assert len(changes) == 6
    for i in changes:
        # log[i+1] is the *OPC? of this write (and its sentinel); the next real command waits
        after = next(t for t, c in log[i + 1:] if c not in ("*OPC?", "*IDN?"))
        opc_done = next(t for t, c in log[i + 1:] if c == "*IDN?")
        assert after - opc_done >= gap - 1e-9


def test_forbidden_commands_never_reach_the_scope():
    drv, fake, _ = opened_scope()
    for cmd in (":RUN", "RUN", ":TRIGger:SWEep NORMal", ":TRIG:SWE NORM", "*RST", ":AUTO"):
        with pytest.raises(BlockedCommand):
            drv.write(cmd)
    assert fake.forbidden == [] and not any("NORM" in c.upper() and "SWE" in c.upper() for c in fake.sent())


def test_no_run_and_no_elevation_anywhere_in_the_app():
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "subprocess" not in text, path                        # nothing is spawned, so nothing elevated
        for line in text.splitlines():
            if re.search(r"""write\(\s*["']:?RUN["']""", line):
                pytest.fail("':RUN' is sent in %s: %s" % (path, line))


def test_busy_empty_replies_are_retried_without_a_resync():
    drv, fake, _ = opened_scope()
    fake.empty_next = 3
    assert drv.query(":TIMebase:SCALe?", float) == 1e-3
    assert drv.stats["empty_retries"] == 3 and drv.stats["resyncs"] == 1      # only the one at connect


def test_out_of_step_reply_is_detected_and_resynced():
    drv, fake, _ = opened_scope()
    epoch = drv.alignment_epoch
    fake.stray = b"#3700" + bytes(700) + b"\r\n"                     # a late waveform block
    from bodeplot.drivers import scpi
    assert drv.query(":TIMebase:SCALe?", scpi.v_float) == 1e-3       # right answer, not the stray
    assert drv.stats["resyncs"] == 2 and drv.alignment_epoch == epoch + 1
    assert fake.clears >= 2


def test_panel_lock_reads_back_and_close_releases_it():
    drv, fake, _ = opened_scope()
    drv.lock_panel(True)
    assert fake.lock and drv.panel_locked
    drv.close()
    assert not fake.lock and fake.closed


# ---------------------------------------------------------------------- scope: acquisition
def test_two_channels_from_one_single_shot():
    drv, fake, _ = ready_scope(vdiv=0.02, tb=2e-4)
    fake.freq, fake.tips = 1000.0, {1: (0.5, 0.0), 2: (0.25, -math.pi / 3)}
    n0 = fake.sent().count(":TRIGger:SWEep SINGle")
    waves = drv.acquire([1, 2], 5.0)
    assert fake.sent().count(":TRIGger:SWEep SINGle") == n0 + 1      # ONE acquisition for both
    assert fake.sent().count(":WAVeform:DATA?") == 2
    w1, w2 = waves[1], waves[2]
    assert w1.volts.size == 700 and w1.dt == pytest.approx(2e-4 / 50) and w1.t0 == pytest.approx(-7 * 2e-4)
    f1, f2 = sinefit.fit3(w1.volts, w1.dt, 1000.0, w1.t0), sinefit.fit3(w2.volts, w2.dt, 1000.0, w2.t0)
    assert f1.amp == pytest.approx(0.5, rel=0.01) and f2.amp == pytest.approx(0.25, rel=0.02)   # tip volts
    gain, phase = sinefit.gain_phase(sinefit.transfer(f1, f2))
    assert gain == pytest.approx(-6.02, abs=0.1) and phase == pytest.approx(-60.0, abs=0.5)
    assert not w1.clipped and w1.rail_fraction == 0.0


def test_waveform_is_only_read_after_the_stop_that_follows_arming():
    drv, fake, _ = ready_scope()
    drv.acquire([1], 5.0)
    drv.acquire([1], 5.0)                # second shot starts from a stale STOP
    sent = fake.sent()
    last_arm = len(sent) - 1 - sent[::-1].index(":TRIGger:SWEep SINGle")
    first_data = sent.index(":WAVeform:DATA?", last_arm)
    t_arm, t_data = fake.log[last_arm][0], fake.log[first_data][0]
    assert t_data - t_arm >= 0.33 + 0.1 - 1e-6        # armed, triggered, then STOP held 0.1 s
    assert drv.stats["empty_blocks"] == 0


def test_rail_codes_1_and_254_mark_clipping():
    drv, fake, _ = ready_scope(vdiv=0.005)
    fake.tips = {1: (0.5, 0.0), 2: (0.5, 0.0)}      # 0.1 Vpp at the input = 20 divisions at 5 mV/div
    w = drv.acquire([1], 5.0)[1]
    assert w.clipped and 0.5 < w.rail_fraction < 0.8
    codes = fake.codes(1)
    assert codes.min() == 1 and codes.max() == 254                   # never 0 or 255
    drv.set_vdiv(1, 0.02)                                            # 5 divisions: inside
    w = drv.acquire([1], 5.0)[1]
    assert not w.clipped and w.rail_fraction == 0.0


def test_force_trigger_is_only_sent_from_ready():
    drv, fake, _ = ready_scope()
    fake.trigger_present = False
    waves = drv.acquire([1], 5.0)
    sent = fake.sent()
    i = sent.index(":TRIGger:FORCe")
    assert drv.stats["forced_triggers"] == 1 and waves[1].volts.size == 700
    # the status poll just before the force command answered READY
    assert fake.log[i][0] - fake.log[sent.index(":TRIGger:SWEep SINGle", i - 400 if i > 400 else 0)][0] >= 1.0


def test_acquire_timeout_when_the_scope_never_arms():
    drv, fake, _ = ready_scope()
    drv.acquire([1], 5.0)                # leave it stopped
    fake.ignore_single = True
    with pytest.raises(AcquireTimeout):
        drv.acquire([1], 3.0)
    assert drv.stats["rearms"] == 1 and ":WAVeform:DATA?" not in fake.sent()[-40:]


def test_empty_block_is_not_retried_in_place():
    drv, fake, _ = ready_scope()
    epoch = drv.alignment_epoch
    fake.empty_blocks = 1
    waves = drv.acquire([1, 2], 5.0)
    sent = fake.sent()
    first = sent.index(":WAVeform:DATA?")
    nxt = sent.index(":WAVeform:DATA?", first + 1)
    between = sent[first + 1:nxt]
    assert ":TRIGger:SWEep AUTO" in between and ":TRIGger:SWEep SINGle" in between   # resync, new shot
    assert drv.stats["empty_blocks"] == 1 and drv.alignment_epoch == epoch + 1
    assert waves[2].volts.size == 700


def test_a_record_of_the_previous_timebase_is_thrown_away_without_a_resync():
    """Bench, HW_REPORT 13.20: read too soon after a timebase change the scope hands out the
    old record. Its sample interval gives it away."""
    drv, fake, _ = ready_scope()
    epoch, tb = drv.alignment_epoch, drv.tb
    fake.stale_tb, fake.stale_preambles = tb * 2.5, 1                # the reference only, as on the bench
    waves = drv.acquire([1, 2], 5.0)
    assert drv.stats["stale_records"] == 1 and drv.alignment_epoch == epoch
    assert all(w.dt * w.volts.size == pytest.approx(14 * tb) for w in waves.values())
    assert fake.sent().count(":TRIGger:SWEep SINGle") == 2           # a new acquisition, not a re-read


def test_a_record_that_stays_stale_is_an_error():
    drv, fake, _ = ready_scope()
    fake.stale_tb, fake.stale_preambles = drv.tb * 2.5, 99
    with pytest.raises(DriverError, match="stale record"):
        drv.acquire([1, 2], 5.0)
    assert drv.stats["stale_records"] == 3


# ---------------------------------------------------------------------- scope: watchdog
def test_dead_scope_raises_unresponsive_and_then_fails_fast():
    drv, fake, clock = ready_scope()
    fake.dead = True
    with pytest.raises(InstrumentUnresponsive) as e:
        drv.acquire([1, 2], 5.0)
    assert "Power-cycle the scope" in e.value.advice
    assert drv.dead
    t = clock.now()
    with pytest.raises(InstrumentUnresponsive):
        drv.set_timebase(1e-3)
    assert clock.now() == t                                         # no further I/O attempted
    drv.close()                                                     # must not raise


def test_unplugged_scope_is_told_apart_from_a_frozen_one():
    """Bench, HW_REPORT 13.15: with the USB cable pulled the advice was to power-cycle."""
    drv, fake, clock = ready_scope()
    fake.dead = fake.unplugged = True
    with pytest.raises(InstrumentUnresponsive) as e:
        drv.acquire([1, 2], 5.0)
    assert "USB cable" in e.value.advice and "Power-cycle" not in e.value.advice
    with pytest.raises(InstrumentUnresponsive) as again:            # the fast failure says the same
        drv.set_timebase(1e-3)
    assert "USB cable" in again.value.advice


def test_watchdog_stops_the_sweep_keeps_partial_data_and_switches_the_generator_off():
    clock = FakeClock()
    fgen = FakeGen(clock)
    fscope = FakeScope(clock, gen=fgen)
    session = Session(UniTUTG900E(lambda r, b: fgen, sleep=clock.sleep, clock=clock.now),
                      UniTUPO1000(lambda r, b: fscope, sleep=clock.sleep, clock=clock.now))
    session.open("FAKE::GEN", "FAKE::SCOPE", "py")
    fscope.die_after_data_reads = 2 * 4 + 1          # dies during the fifth capture
    errors, logs = [], []
    from bodeplot.sweep.core import Callbacks
    runner = SweepRunner(session, SweepConfig(start_hz=1e3, stop_hz=1e5, points_per_decade=5),
                         StimulusConfig(), ScopeConfig(), MeasureSettings(),
                         Callbacks(error=errors.append, log=logs.append), sleep=clock.sleep)
    result = runner.run()
    assert not any("was resynchronised" in entry.text for entry in logs)  # the resync failed
    assert 1 <= len(result.points) < 11                              # partial data kept
    assert result.meta["error"] and "Power-cycle the scope" in result.meta["error"]
    assert "points were measured and are kept" in errors[0]
    assert session.dead_reason and not session.skew_valid()
    assert ":CHANnel1:OUTPut OFF" in fgen.sent()[-4:]                # generator switched off
    assert not fgen.ch[1]["output"] and not fgen.ch[2]["output"]
    # off as soon as the scope fails a transfer in the resync, not when the resync has failed
    t_on = max(t for t, c in fgen.log if c == ":CHANnel1:OUTPut ON")
    t_off = min(t for t, c in fgen.log if c == ":CHANnel1:OUTPut OFF" and t > t_on)
    assert clock.now() - t_off > 1.0
    session.close()


def test_generator_comes_back_on_when_the_scope_recovers_from_a_failed_transfer():
    clock = FakeClock()
    fgen = FakeGen(clock)
    fscope = FakeScope(clock, gen=fgen)
    session = Session(UniTUTG900E(lambda r, b: fgen, sleep=clock.sleep, clock=clock.now),
                      UniTUPO1000(lambda r, b: fscope, sleep=clock.sleep, clock=clock.now))
    session.open("FAKE::GEN", "FAKE::SCOPE", "py")
    logs, seen = [], []

    def on_point(p):
        seen.append(p)
        if len(seen) == 2:
            fscope.fail_writes = 2                    # the failing command, then the resync's first write
    from bodeplot.models import Flag
    from bodeplot.sweep.core import Callbacks
    runner = SweepRunner(session, SweepConfig(start_hz=1e3, stop_hz=1e5, points_per_decade=5),
                         StimulusConfig(), ScopeConfig(), MeasureSettings(),
                         Callbacks(point=on_point, log=logs.append), sleep=clock.sleep)
    result = runner.run()
    assert result.meta["error"] is None and len(result.points) == 11
    assert any("generator was switched off" in entry.text for entry in logs)
    assert [c for c in fgen.sent() if c == ":CHANnel1:OUTPut ON"] == [":CHANnel1:OUTPut ON"] * 2
    assert all(abs(p.gain_db) < 0.1 and not p.flags & Flag.REF_SUSPECT for p in result.points)
    assert not fgen.ch[1]["output"]
    session.close()


# ---------------------------------------------------------------------- generator
def test_generator_open_identifies_and_forces_outputs_off():
    drv, fake, _ = make_gen()
    fake.ch[1]["output"] = fake.ch[2]["output"] = True              # left on from the front panel
    drv.open("FAKE::GEN", "py")
    assert drv.idn().startswith("UNI-T Technologies,UTG900E")
    assert not fake.ch[1]["output"] and not fake.ch[2]["output"]


def test_generator_configure_sine_order_and_format():
    drv, fake, _ = make_gen()
    drv.open("FAKE::GEN", "py")
    drv.configure_sine(1, 12668.6, 1.0, 0.0, "HIGHZ")
    sent = fake.sent()
    assert ":CHANnel1:LOAD 10000" in sent and ":CHANnel1:BASE:FREQuency 12668.6" in sent
    assert sent.index(":CHANnel1:AMPLitude:UNIT VPP") < sent.index(":CHANnel1:BASE:AMPLitude 1")
    assert not any(re.search(r"\d[eE][+-]?\d", c) for c in sent)
    assert fake.ch[1]["wave"] == "SINe" and not fake.ch[1]["output"]  # configuring does not switch on
    drv.set_output(1, True)
    assert fake.ch[1]["output"]
    drv.safe_off()
    assert not fake.ch[1]["output"]


def test_generator_never_receives_a_command_outside_its_manual():
    drv, fake, _ = make_gen()
    drv.open("FAKE::GEN", "py")
    n = len(fake.log)
    for cmd in ("*OPC?", "*RST", ":CHANnel3:OUTPut ON", ":SYSTem:ERRor?", ":CHANnel1:BASE:FREQuency 1e3"):
        with pytest.raises(BlockedCommand):
            drv.write(cmd)
        with pytest.raises(BlockedCommand):
            drv.query(cmd, str)
    assert len(fake.log) == n and not fake.hung
    for p in drv.ALLOWED:
        assert not p.match("*OPC?")


def test_generator_timeout_is_cleared_and_retried_once():
    drv, fake, _ = make_gen()
    drv.open("FAKE::GEN", "py")
    fake.drop_replies = 1
    assert drv.output(1) is False
    assert drv.stats["timeouts"] == 1 and drv.stats["retries"] == 1 and fake.clears == 1
    fake.drop_replies = 2
    with pytest.raises(InstrumentUnresponsive):
        drv.output(1)


def test_generator_safe_off_never_raises():
    drv, fake, _ = make_gen()
    drv.open("FAKE::GEN", "py")
    fake.dead = True
    drv.safe_off()
    drv.close()
    UniTUTG900E().safe_off()                                        # not even open


def test_generator_limits():
    drv, fake, _ = make_gen()
    drv.open("FAKE::GEN", "py")
    with pytest.raises(DriverError):
        drv.set_frequency(1, 40e6)
    with pytest.raises(DriverError):
        drv.configure_sine(1, 1e3, 25.0, 0.0, "HIGHZ")
    with pytest.raises(DriverError):
        drv.configure_sine(3, 1e3, 1.0, 0.0, "HIGHZ")


# ---------------------------------------------------------------------- whole chain
def fake_bench(h=None, delay=0.0):
    clock = FakeClock()
    fgen = FakeGen(clock)
    fscope = FakeScope(clock, gen=fgen)
    fscope.h, fscope.delay_ch2_s = h, delay
    session = Session(UniTUTG900E(lambda r, b: fgen, sleep=clock.sleep, clock=clock.now),
                      UniTUPO1000(lambda r, b: fscope, sleep=clock.sleep, clock=clock.now))
    session.open("FAKE::GEN", "FAKE::SCOPE", "py")
    return session, fgen, fscope, clock


def test_sweep_with_the_real_drivers_measures_an_rc_low_pass():
    rc = 1e3 * 100e-9
    session, fgen, fscope, clock = fake_bench(h=lambda f: 1.0 / (1.0 + 2j * math.pi * f * rc))
    session.accept_skew(run_skew_check(session, StimulusConfig(), ScopeConfig(), MeasureSettings(),
                                       sleep=clock.sleep))
    runner = SweepRunner(session, SweepConfig(start_hz=100.0, stop_hz=1e5, points_per_decade=3),
                         StimulusConfig(), ScopeConfig(), MeasureSettings(), sleep=clock.sleep)
    result = runner.run()
    assert result.meta["error"] is None and len(result.points) == 10
    for p in result.points:
        h = 1.0 / (1.0 + 2j * math.pi * p.freq_hz * rc)
        assert p.gain_db == pytest.approx(20 * math.log10(abs(h)), abs=0.15)
        assert p.phase_deg == pytest.approx(math.degrees(math.atan2(h.imag, h.real)), abs=1.0)
    # how the instruments are left
    assert not fgen.ch[1]["output"] and not fgen.ch[2]["output"]
    assert not fscope.lock                                           # front panel released
    assert fscope.sweep == "AUTO" and fscope.mode == "run"           # left running, not frozen
    assert fscope.forbidden == []                                    # never ':RUN'
    assert ":SYSTem:LOCK ON" in fscope.sent()                        # and it was locked during the sweep
    assert not any(c.endswith((" UP", " DOWN")) for c in fscope.sent())
    session.close()


def test_sweep_puts_the_users_scope_settings_back():
    """Bench, 2026-10-06: a sweep left the scope on the last point's V/div and timebase.
    CH2 is off here on purpose: the scope ignores SCALe on a channel that is off."""
    rc = 1e3 * 100e-9
    session, fgen, fscope, clock = fake_bench(h=lambda f: 1.0 / (1.0 + 2j * math.pi * f * rc))
    fscope.ch[1].update(scale=0.5, offset=0.1, probe=1.0, coupling="AC", bwl="20M")
    fscope.ch[2].update(scale=0.05, offset=-0.004, probe=10.0, display=False)
    fscope.timebase = 2e-3
    fscope.trig.update(src="CHANnel2", slope="NEGative", level=0.01)
    before = ({n: dict(c) for n, c in fscope.ch.items()}, fscope.timebase, dict(fscope.trig))
    runner = SweepRunner(session, SweepConfig(start_hz=100.0, stop_hz=1e5, points_per_decade=2),
                         StimulusConfig(), ScopeConfig(), MeasureSettings(), sleep=clock.sleep)
    result = runner.run()
    assert result.meta["error"] is None and len(result.points) == 7
    assert any(c.startswith(":CHANnel2:SCALe ") for c in fscope.sent())     # the sweep did change it
    after = ({n: dict(c) for n, c in fscope.ch.items()}, fscope.timebase, dict(fscope.trig))
    assert after[0][1] == pytest.approx(before[0][1])
    assert after[0][2] == pytest.approx(before[0][2])
    assert after[1] == before[1] and after[2] == pytest.approx(before[2])
    assert fscope.sweep == "AUTO" and fscope.mode == "run" and not fscope.lock
    session.close()


def test_restore_reports_what_it_could_not_put_back_and_does_not_raise():
    drv, fake, clock = opened_scope()
    drv.save_setup()
    drv.configure_channel(1, "DC", 10.0, False, 0.0)
    drv.set_timebase(1e-4)
    fake.ch[1]["scale"] = 0.3            # between steps: cannot be read back as set
    drv._saved["channels"][1]["scale"] = 0.3
    fake.ch[1]["scale"] = 0.2
    bad = drv.restore_setup()
    assert len(bad) == 1 and ":CHANnel1:SCALe" in bad[0]
    assert fake.timebase == 1e-3 and drv.restore_setup() == []       # the rest went back; second call is a no-op


@pytest.mark.parametrize("state", [-1.85e-9, 0.15e-9, 2.15e-9, 4.15e-9])
def test_skew_check_with_the_real_driver_finds_each_state(state):
    session, fgen, fscope, clock = fake_bench(delay=state)
    check = run_skew_check(session, StimulusConfig(), ScopeConfig(), MeasureSettings(), sleep=clock.sleep)
    assert check.delay_s == check.measured_s and check.delay_s == pytest.approx(state, abs=0.05e-9)
    assert not fgen.ch[1]["output"] and not fscope.lock
    session.close()


def test_a_resync_during_a_sweep_invalidates_the_skew_check():
    session, fgen, fscope, clock = fake_bench()
    session.accept_skew(run_skew_check(session, StimulusConfig(), ScopeConfig(), MeasureSettings(),
                                       sleep=clock.sleep))
    assert session.skew_valid()
    fscope.empty_blocks = 1
    session.digitizer.acquire([1, 2], 5.0)
    assert not session.skew_valid() and "resynchronised" in session.recheck_reason
    session.close()


# ---------------------------------------------------------------------- auto-range with real rails
def test_clipped_amplitude_estimate_matches_the_bench_numbers():
    # HW_REPORT.md 12.14: share of samples on the rails for 20, 50 and 100 divisions p-p
    for rail_fraction, true_div in ((460 / 700, 20.0), (602 / 700, 50.0), (658 / 700, 100.0)):
        est = autorange.clipped_vpp_estimate(rail_fraction, 1.0, 10.12) / autorange.CLIP_ESTIMATE_MARGIN
        assert est == pytest.approx(true_div, rel=0.15)
    assert autorange.clipped_vpp_estimate(0.99, 1.0, 10.12) is None
    assert autorange.clipped_vpp_estimate(0.5, 1.0, 0.0) is None


def test_clipped_capture_goes_to_the_right_step_in_one_jump():
    steps = step_tables.FALLBACK.vdiv
    # 0.1 Vpp at the input seen at 5 mV/div: 20 divisions, 66% of the samples on the rails
    d = autorange.decide(0.05, True, 0.005, steps, 8.0, rail_fraction=0.657, data_divs=10.12)
    assert d.action == "change" and d.vdiv == 0.02                   # 5 divisions of 8
    # no estimate available: the old fixed jump
    d = autorange.decide(0.05, True, 0.005, steps, 8.0)
    assert d.vdiv == autorange.step_up(0.005, steps, autorange.CLIP_JUMP)
    # nearly everything on a rail: fixed jump as well
    d = autorange.decide(0.05, True, 0.0005, steps, 8.0, rail_fraction=0.97, data_divs=10.12)
    assert d.vdiv == autorange.step_up(0.0005, steps, autorange.CLIP_JUMP)


# ---------------------------------------------------------------------- finding the instruments
def test_registry_points_at_the_real_drivers():
    e = registry.match("UNI-T Technologies,UPO1054,APX1424510001,1. 01. 0047", "digitizer")
    assert registry.load(e) is UniTUPO1000 and registry.is_available(e)
    e = registry.match("UNI-T Technologies,UTG900E,69746177,1.09", "source")
    assert registry.load(e) is UniTUTG900E


def test_instrument_selection_errors_are_plain():
    scope = connect.Found("USB0::1::2::A::0::INSTR", "UNI-T Technologies,UPO1054,A,1. 01. 0047", None)
    scope.entry = registry.match(scope.idn)
    gen = connect.Found("USB0::3::4::B::0::INSTR", "UNI-T Technologies,UTG900E,B,1.09", None)
    gen.entry = registry.match(gen.idn)
    assert connect._pick([scope, gen], "digitizer", "") is scope
    assert connect._pick([scope, gen], "source", gen.resource) is gen
    with pytest.raises(DriverError, match="No supported scope"):
        connect._pick([gen], "digitizer", "")
    with pytest.raises(DriverError, match="More than one"):
        connect._pick([scope, scope], "digitizer", "")
    with pytest.raises(DriverError, match="not a supported generator"):
        connect._pick([scope, gen], "source", scope.resource)
    with pytest.raises(DriverError, match="was not found"):
        connect._pick([scope], "source", "USB0::9::9::Z::0::INSTR")


def test_every_command_cites_its_manual_page():
    for drv, tag in ((UniTUPO1000, "U1K p."), (UniTUTG900E, "UTG p.")):
        assert len(drv.COMMANDS) >= 10
        for c in drv.COMMANDS:
            assert c.page.startswith(tag) and c.text

# ---------------------------------------------------------------------- probe tool
def _probe_session(idn=None):
    clock = FakeClock()
    fgen = FakeGen(clock)
    fscope = FakeScope(clock, idn=idn, gen=fgen)
    fscope.ch[1]["probe"] = 1.0
    session = Session(UniTUTG900E(lambda r, b: fgen, sleep=clock.sleep, clock=clock.now),
                      UniTUPO1000(lambda r, b: fscope, sleep=clock.sleep, clock=clock.now))
    session.open("FAKE::GEN", "FAKE::SCOPE", "py")
    return session, fgen, fscope


def test_probe_tool_default_run_is_read_only_and_safe(tmp_path):
    from bodeplot.tools import probe
    session, fgen, fscope = _probe_session()
    fgen.ch[2]["output"] = True                                     # left on by somebody
    tb0, v0 = fscope.timebase, fscope.ch[1]["scale"]
    lines = []
    out = tmp_path / "report.json"
    code = probe.main(["--json", str(out)], session_opener=lambda: session, say=lines.append)
    text = "\n".join(lines)
    assert code == 0, text
    assert "probe.py sha256" in lines[0]                            # says which version ran
    assert "0 failed" in text and "single-shot acquisition CH1" in text
    assert not fgen.ch[1]["output"] and not fgen.ch[2]["output"]
    assert not any(c.endswith(" ON") for c in fgen.sent())          # never switches an output on
    sent = fscope.sent()
    assert fscope.forbidden == [] and not any(c.endswith((" UP", " DOWN")) for c in sent)   # no :RUN, no walk
    assert (fscope.timebase, fscope.ch[1]["scale"]) == (tb0, v0)
    assert fscope.sweep == "AUTO" and fscope.mode == "run" and not fscope.lock
    import json
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["hashes"]["probe.py"] and len(report["rows"]) > 30


def test_probe_tool_walk_needs_confirmation_and_is_paced(tmp_path, monkeypatch):
    from bodeplot.tools import probe
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path))
    session, fgen, fscope = _probe_session(idn="UNI-T Technologies,UPO1054,SIM0001,9. 99. 0001")
    lines = []
    # refused: nothing at all is sent
    n = len(fscope.log)
    assert probe.main(["--walk-tables"], session_opener=lambda: session, say=lines.append,
                      confirm=lambda prompt: "no") == 2
    assert len(fscope.log) == n and "froze" in "\n".join(lines)
    # confirmed
    tb0, v0 = fscope.timebase, fscope.ch[1]["scale"]
    assert probe.main(["--walk-tables", "--gap-ms", "250"], session_opener=lambda: session,
                      say=lines.append, confirm=lambda prompt: "WALK") == 0
    steps = [i for i, (_, c) in enumerate(fscope.log) if c.endswith((" UP", " DOWN"))]
    assert len(steps) > 30
    for i in steps:                                                 # paced: 250 ms after every step
        after = next(t for t, c in fscope.log[i + 1:] if c not in ("*OPC?", "*IDN?"))
        assert after - fscope.log[i][0] >= 0.25
    assert (fscope.timebase, fscope.ch[1]["scale"]) == (tb0, v0)    # restored
    found = step_tables.lookup("UPO1054", "9. 99. 0001", tmp_path / "step_tables.json")
    assert found.exact and found.tables.timebase == step_tables.FALLBACK.timebase
    assert found.tables.vdiv == step_tables.FALLBACK.vdiv
    assert fscope.forbidden == [] and not fgen.ch[1]["output"]


def test_probe_tool_unlock(tmp_path):
    from bodeplot.tools import probe
    session, fgen, fscope = _probe_session()
    fscope.lock = True
    session.digitizer.panel_locked = True
    assert probe.main(["--unlock"], session_opener=lambda: session, say=lambda s: None) == 0
    assert not fscope.lock


def test_engine_drops_a_dead_connection(qtbot):
    from bodeplot.sweep.engine import EngineWorker
    session, fgen, fscope, clock = fake_bench()
    worker = EngineWorker()
    worker.session = session
    infos, logs = [], []
    worker.session_changed.connect(infos.append)
    worker.log.connect(logs.append)
    worker._emit_session()
    assert infos[-1].connected and not infos[-1].has_builtin        # the real scope has no built-in method
    session.mark_dead("The scope does not answer after a resync. Power-cycle the scope.")
    worker._emit_session()
    assert worker.session is None and not infos[-1].connected
    assert "Power-cycle the scope" in logs[-1].text and fgen.closed


def test_autorange_does_not_flip_between_two_steps_on_the_boundary():
    """Bench, Milestone 7: 10.5 mVpp at the input with a noisy p-p flipped between 2 and
    5 mV/div until the retries ran out."""
    steps = step_tables.FALLBACK.vdiv
    d = autorange.decide(0.0135, False, 0.002, steps, 8.0)           # 84% of 8 divisions: just over
    assert d.action == "ok" and d.vdiv == 0.002
    d = autorange.decide(0.0105, False, 0.005, steps, 8.0)           # 26%: go down, as before
    assert d.action == "change" and d.vdiv == 0.002
    d = autorange.decide(0.017, False, 0.002, steps, 8.0)            # 106%: off screen, go up
    assert d.action == "change" and d.vdiv == 0.005
    d = autorange.decide(0.03, False, 0.005, steps, 8.0)             # 75% -> ok; and 0.035 (87%) at 5 mV:
    assert d.action == "ok"
    d = autorange.decide(0.035, False, 0.005, steps, 8.0)            # next step 10 mV gives 44%: stay
    assert d.action == "ok"


# ---------------------------------------------------------------------- DC on the signal (bench, Milestone 7)
def test_min_vdiv_for_dc():
    steps = step_tables.FALLBACK.vdiv
    # 6.2 mV of DC with a 0.6 mVpp signal: needs 2 mV/div (9.1 mV of half range x 0.9), not 500 uV
    assert autorange.min_vdiv_for_dc(0.0062, 0.0006, steps, 10.12, 8.0) == 0.002
    assert autorange.min_vdiv_for_dc(0.0, 0.0006, steps, 10.12, 8.0) == 0.0005


def _rc(f, rc=1e3 * 100e-9):
    return 1.0 / (1.0 + 2j * math.pi * f * rc)


def test_sweep_survives_dc_on_the_signal_with_the_real_driver():
    """The bench case: about 65 mV of DC at the probe tips. Without re-centring, the DUT
    channel went off scale at 1 mV/div and the scope returned wrong data at 500 uV/div."""
    session, fgen, fscope, clock = fake_bench(h=_rc)
    fscope.noise_codes = 0.4
    runner = SweepRunner(session, SweepConfig(start_hz=1e3, stop_hz=2e5, points_per_decade=4),
                         StimulusConfig(offset_v=0.065), ScopeConfig(), MeasureSettings(), sleep=clock.sleep)
    result = runner.run()
    assert result.meta["error"] is None
    from bodeplot.models import Flag
    for p in result.points:
        want = 20 * math.log10(abs(_rc(p.freq_hz)))
        assert p.gain_db == pytest.approx(want, abs=0.5), (p.freq_hz, p.gain_db, want, p.flags)
        assert not p.flags & (Flag.AUTORANGE_FAILED | Flag.CLIPPED | Flag.BELOW_FLOOR)
    assert any(c.startswith(":CHANnel2:OFFSet -0.00") for c in fscope.sent())     # trace was re-centred
    assert result.points[-1].vdiv_dut <= 0.001                                    # and the sensitive steps used
    session.close()


def test_without_an_offset_command_the_dc_limits_the_step(make_session, no_sleep):
    """A digitizer that cannot set an offset: auto-range must stay on a step the DC fits
    in, and must never read the wrong data that lie beyond the rails."""
    from bodeplot.drivers.mock import MockScope, SimulatedDUT
    from bodeplot.models import Flag

    def refuse(self, ch, offset_v):
        raise NotImplementedError

    session = make_session(SimulatedDUT.rc_lpf(), checked=False, skew_enabled=False)
    session.digitizer.set_offset = refuse.__get__(session.digitizer, MockScope)
    runner = SweepRunner(session, SweepConfig(start_hz=2e4, stop_hz=1e5, points_per_decade=3),
                         StimulusConfig(offset_v=0.065), ScopeConfig(), MeasureSettings(), sleep=no_sleep)
    result = runner.run()
    assert result.meta["error"] is None
    for p in result.points:
        want = 20 * math.log10(abs(_rc(p.freq_hz)))
        assert p.gain_db == pytest.approx(want, abs=1.5), (p.freq_hz, p.gain_db, want)
        assert p.vdiv_dut >= 0.002 and not p.flags & Flag.CLIPPED     # 6.5 mV of DC does not fit below 2 mV/div


def test_500_microvolt_step_is_never_used_on_the_real_scope():
    """Its data wrap instead of clipping (HW_REPORT.md 13.6), so the driver leaves it out."""
    drv, fake, _ = opened_scope()
    assert 5e-4 in drv.tables.vdiv and 5e-4 not in drv.caps.vdiv_steps
    assert min(drv.caps.vdiv_steps) == 1e-3
    drv.configure_channel(1, "DC", 10.0, False, 0.0)
    assert drv.set_vdiv(1, 0.0005) == 0.001                         # even when asked for it
    assert not any(c == ":CHANnel1:SCALe 0.0005" for c in fake.sent())


def test_offset_volts_are_put_back_after_a_vdiv_change():
    """The real scope keeps the offset in divisions; the driver keeps it in volts."""
    drv, fake, _ = opened_scope()
    drv.configure_channel(2, "DC", 10.0, False, 0.0)
    drv.set_vdiv(2, 0.002)
    assert drv.set_offset(2, -0.00624) == pytest.approx(-0.00624)
    drv.set_vdiv(2, 0.001)
    assert fake.ch[2]["offset"] == pytest.approx(-0.00624)          # not -0.00312
    drv.set_vdiv(2, 0.02)
    assert fake.ch[2]["offset"] == pytest.approx(-0.0064)           # re-quantised to 0.8 mV steps


# ---------------------------------------------------------------------- generator offset
def test_negative_offset_is_reached_without_sending_a_negative_number():
    """Bench, 2026-10-06: the generator ignores every negative argument (HW_REPORT 13.11)."""
    drv, fake, clock = make_gen()
    drv.open("FAKE::GEN", "py")
    drv.configure_sine(1, 1000.0, 1.0, -0.1, "HIGHZ")
    assert fake.ch[1]["offset"] == pytest.approx(-0.1) and fake.ch[1]["amp"] == pytest.approx(1.0)
    sets = [c for c in fake.sent() if " " in c and not c.endswith("?")]
    assert not any(re.search(r" -\d", c) for c in sets)
    assert ":CHANnel1:BASE:AMPLitude 1.2" in sets and ":CHANnel1:BASE:HIGH 0.4" in sets
    # the next configuration starts from a known state, whatever the sign was
    drv.configure_sine(1, 1000.0, 0.5, 0.05, "HIGHZ")
    assert fake.ch[1]["offset"] == pytest.approx(0.05) and fake.ch[1]["amp"] == pytest.approx(0.5)
    drv.configure_sine(1, 1000.0, 1.0, -0.5, "HIGHZ")                 # the lowest reachable: HIGH 0
    assert fake.ch[1]["offset"] == pytest.approx(-0.5) and fake.ch[1]["amp"] == pytest.approx(1.0)
    drv.configure_sine(1, 1000.0, 1.0, 0.0, "HIGHZ")
    assert fake.ch[1]["offset"] == 0.0 and fake.ch[1]["amp"] == pytest.approx(1.0)


def test_an_offset_the_generator_cannot_reach_is_refused_in_plain_words():
    drv, fake, clock = make_gen()
    drv.open("FAKE::GEN", "py")
    drv.configure_sine(1, 1000.0, 1.0, 0.0, "HIGHZ")
    before = dict(fake.ch[1])
    with pytest.raises(DriverError, match="minus half the amplitude"):
        drv.configure_sine(1, 1000.0, 1.0, -0.6, "HIGHZ")
    assert fake.ch[1]["amp"] == before["amp"] and fake.ch[1]["offset"] == before["offset"]
    fake.ch[1]["output"] = True
    with pytest.raises(DriverError, match="output is off"):
        drv.configure_sine(1, 1000.0, 1.0, -0.1, "HIGHZ")
    assert fake.ch[1]["amp"] == pytest.approx(1.0)                  # never widened with the output on


# ---------------------------------------------------------------------- fast preview
def test_fast_preview_reads_the_running_scope_and_never_arms_a_single_shot():
    """HW_REPORT 13.21: no single shot, no stop; the scope is restarted with sweep AUTO and
    given time before the first read, because a scope that has just restarted has no record."""
    drv, fake, _ = ready_scope()
    drv.acquire([1, 2], 5.0)                             # leaves the scope stopped
    n_single = fake.sent().count(":TRIGger:SWEep SINGle")
    waves = drv.acquire_running([1, 2], 5.0)
    sent = fake.sent()
    assert sent.count(":TRIGger:SWEep SINGle") == n_single and ":STOP" not in sent
    restart = len(sent) - 1 - sent[::-1].index(":TRIGger:SWEep AUTO")
    first_data = sent.index(":WAVeform:DATA?", restart)
    assert fake.log[first_data][0] - fake.log[restart][0] >= 0.3
    assert waves[1].volts.size == 700 and waves[2].volts.size == 700
    assert drv.stats["empty_blocks"] == 0 and fake.forbidden == []
    t = fake.clock.now()
    drv.acquire_running([1, 2], 5.0)                     # already running: no restart, no wait
    assert fake.clock.now() - t < 0.2


def test_fast_preview_empty_reply_waits_and_reads_again_without_a_resync():
    """Bench, HW_REPORT 13.24: a running scope has no record for a moment now and then; the
    link stays in step, and a resync would end the validity of the skew check for nothing."""
    drv, fake, clock = ready_scope()
    drv.acquire_running([1, 2], 5.0)
    epoch, t = drv.alignment_epoch, clock.now()
    fake.empty_blocks = 2                                # two reads in a row, as on the bench
    waves = drv.acquire_running([1, 2], 5.0)
    assert drv.stats["empty_blocks"] == 2 and drv.alignment_epoch == epoch
    assert clock.now() - t >= 1.0 and waves[2].volts.size == 700


def test_fast_preview_empty_reply_with_the_link_out_of_step_is_resynced():
    drv, fake, _ = ready_scope()
    drv.acquire_running([1, 2], 5.0)
    epoch = drv.alignment_epoch
    fake.empty_blocks, fake.stray = 1, b"#3700" + bytes(700) + b"\r\n"   # a late block ahead of the sentinel
    waves = drv.acquire_running([1, 2], 5.0)
    assert drv.alignment_epoch == epoch + 1 and waves[1].volts.size == 700


def test_fast_preview_sweep_with_the_real_drivers():
    rc = 1e3 * 100e-9
    session, fgen, fscope, clock = fake_bench(h=lambda f: 1.0 / (1.0 + 2j * math.pi * f * rc))
    fscope.run_jitter_s = 1e-7
    from bodeplot.models import Flag, Method
    from bodeplot.sweep.core import Callbacks
    logs = []
    runner = SweepRunner(session, SweepConfig(start_hz=100.0, stop_hz=1e5, points_per_decade=3),
                         StimulusConfig(), ScopeConfig(), MeasureSettings(method=Method.PREVIEW),
                         Callbacks(log=logs.append), sleep=clock.sleep)
    result = runner.run()
    assert result.meta["error"] is None and len(result.points) == 10
    for p in result.points:
        h = 1.0 / (1.0 + 2j * math.pi * p.freq_hz * rc)
        assert p.gain_db == pytest.approx(20 * math.log10(abs(h)), abs=0.15)
        assert p.flags & Flag.PREVIEW and not p.flags & Flag.SKEW_UNCHECKED
    assert ":TRIGger:SWEep SINGle" not in fscope.sent() and fscope.forbidden == []
    assert any("Fast preview" in e.text for e in logs) and not any("skew" in e.text.lower() for e in logs)
    assert not fgen.ch[1]["output"] and not fscope.lock and fscope.mode == "run"
    session.close()


@pytest.mark.parametrize("method_name, uses_them", [("PREVIEW", False), ("SINEFIT", True)])
def test_fast_preview_keeps_off_the_timebases_at_which_the_running_scope_goes_busy(method_name, uses_them):
    """Bench, HW_REPORT 13.24 and 13.27: read while running at 200 or 500 ns/div the scope goes
    busy for 3.4 s now and then; at 100 ns/div and 1 us/div it does not. Single shot is free."""
    from bodeplot.models import Method
    session, fgen, fscope, clock = fake_bench()
    result = SweepRunner(session, SweepConfig(start_hz=5e5, stop_hz=5e6, points_per_decade=12),
                         StimulusConfig(), ScopeConfig(), MeasureSettings(method=Method[method_name]),
                         sleep=clock.sleep).run()
    assert result.meta["error"] is None
    used = {p.timebase for p in result.points}
    assert bool(used & {2e-7, 5e-7}) is uses_them
    for p in result.points:                              # still at least one cycle, and enough samples
        assert 14 * p.timebase * p.freq_hz >= 1.0 and abs(p.gain_db) < 0.2
    session.close()
