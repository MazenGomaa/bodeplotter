"""GUI smoke tests against the mock drivers (offscreen, no hardware, no modal dialogs)."""
import math

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from bodeplot.gui.dialogs import skew_report
from bodeplot.gui.main_window import MainWindow
from bodeplot.io import export_csv, presets
from bodeplot.io.settings import AppSettings
from bodeplot.models import EngineState, Flag, SweepConfig, SweepType

SIM = {"preset": "rc_lpf", "params": {"r": 1e3, "c": 100e-9}, "noise_vrms": 2e-4, "latency_ms": 0.0}


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    w = MainWindow(simulate=True, settings=AppSettings(simulate=True, sim=dict(SIM)), sim_seed=7)
    w.interactive = False
    qtbot.addWidget(w)
    w.show()
    yield w
    w.close()


def _connect(win, qtbot):
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.toggle_connection()
    qtbot.waitUntil(lambda: win.info.connected, timeout=5000)


def _short_sweep(win, lo=100.0, hi=20e6, ppd=4):
    p = win.config.preset()
    p.sweep = SweepConfig(SweepType.LOG, lo, hi, ppd)
    p.measure.settle_ms, p.measure.settle_cycles = 0.0, 0.0
    win.config.set_preset(p)


def _skew_check(win, qtbot):
    with qtbot.waitSignal(win.engine.skew_measured, timeout=10000) as blocker:
        win.engine.skew_check(win.configs())
    check = blocker.args[0]
    win.engine.accept_skew(check)
    qtbot.waitUntil(lambda: win.info.skew_valid, timeout=5000)
    return check


def _calibrate(win, qtbot):
    with qtbot.waitSignal(win.engine.cal_measured, timeout=30000) as blocker:
        win.engine.run_cal(win.configs())
    cal = blocker.args[0]
    win.engine.accept_cal(cal)
    qtbot.waitUntil(lambda: win.info.cal_valid, timeout=5000)
    return cal


def test_window_starts_in_simulation_and_connects(win, qtbot):
    assert "SIMULATION" in win.sim_label.text()
    assert not win.act_start.isEnabled() and win.act_connect.text() == "Connect"
    _connect(win, qtbot)
    assert win.info.simulated and "MOCK" in win.info.digitizer_idn
    assert win.act_start.isEnabled() and win.act_connect.text() == "Disconnect"
    assert not win.info.skew_valid and "UNCHECKED" in win.skew_status[1] and win.skew_status[0] == "critical"       # prompted per session
    assert "Skew check needed" in win.status_log.text.toPlainText()


def test_skew_check_then_sweep_then_export(win, qtbot, tmp_path):
    _connect(win, qtbot)
    check = _skew_check(win, qtbot)
    assert not check.snapped and "the measured value" in skew_report(check)
    assert win.skew_status[0] == "good" and "ns" in win.skew_status[1]
    _short_sweep(win)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        assert win.start_sweep()
    qtbot.waitUntil(lambda: win.state is EngineState.DONE, timeout=5000)
    res = win.result
    assert res is not None and len(res.points) == len(win.plot.points()) > 10
    assert win.status_log.table.rowCount() == len(res.points)
    assert all(not (p.flags & Flag.SKEW_UNCHECKED) for p in res.points)
    assert abs(res.points[0].gain_db) < 0.3 and res.points[-1].gain_db < -40      # RC low-pass shape
    assert win.config.isEnabled() and win.export_button.isEnabled()
    for name in ("a.csv", "a.png", "a.svg", "a.pdf", "a.s2p"):
        out = win.export(tmp_path / name)
        assert out.exists() and out.stat().st_size > 200
    assert "# skew: checked" in (tmp_path / "a.csv").read_text(encoding="utf-8")
    assert len(export_csv.load_csv(tmp_path / "a.csv").points) == len(res.points)
    win.plot.set_unwrap(True)                                                     # no crash, same points
    assert len(win.plot.points()) == len(res.points)


def _data_in_view(win):
    (x0, x1), (g0, g1), (p0, p1) = win.plot.view_ranges()
    import math
    pts = win.plot.points()
    return all(x0 <= math.log10(p.freq_hz) <= x1 and g0 <= p.gain_db <= g1 and p0 <= p.phase_deg <= p1
               for p in pts)


def test_view_follows_the_sweep_and_fit_view_brings_it_back(win, qtbot):
    _connect(win, qtbot)
    _skew_check(win, qtbot)
    _short_sweep(win)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        win.start_sweep()
    qtbot.waitUntil(lambda: win.state is EngineState.DONE, timeout=5000)
    assert win.plot.follow and _data_in_view(win)               # curves are on screen when it finishes
    (x0, x1), (g0, g1), _ = win.plot.view_ranges()
    assert x1 - x0 < 6.5 and g1 - g0 < 120                      # and they fill it, not a speck in a huge view

    # the user drags the view far away
    vb = win.plot.gain_plot.getPlotItem().vb
    vb.setRange(xRange=(9.0, 10.0), yRange=(500.0, 600.0), padding=0)
    win.plot._moved_by_user()
    assert not _data_in_view(win) and not win.plot.follow
    win.plot.add_point(win.plot.points()[0])                    # new data must not yank a manual view
    assert not _data_in_view(win)

    win.plot.fit_btn.click()                                    # one click brings the curves back
    assert win.plot.follow and _data_in_view(win)

    vb.setRange(xRange=(9.0, 10.0), yRange=(500.0, 600.0), padding=0)
    win.plot._moved_by_user()
    win.plot.set_unwrap(True)
    win.plot.fit_view()
    (_, _, (p0, p1)) = win.plot.view_ranges()
    import numpy as np
    from bodeplot.measure.sinefit import unwrap_deg
    un = unwrap_deg([p.phase_deg for p in win.plot.points()])
    assert p0 <= float(np.min(un)) and float(np.max(un)) <= p1   # fits the unwrapped phase too

    # a new sweep is followed again from its first point
    vb.setRange(xRange=(9.0, 10.0), yRange=(500.0, 600.0), padding=0)
    win.plot._moved_by_user()
    win.plot.set_unwrap(False)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        win.start_sweep()
    assert win.plot.follow and _data_in_view(win)


def test_frequency_inputs_and_table_use_si_multipliers(win, qtbot):
    from PySide6.QtGui import QValidator
    box = win.config.stop_hz
    assert box.text() == "20 MHz" and win.config.start_hz.text() == "50 Hz"
    for typed, value in (("1.5k", 1500.0), ("2M", 2e6), ("250 kHz", 250e3), ("3e5", 3e5), ("20meg", 20e6)):
        assert box.validate(typed, 0)[0] == QValidator.Acceptable
        box.lineEdit().setText(typed)
        box.interpretText()
        assert box.value() == pytest.approx(value) and win.config.sweep().stop_hz == pytest.approx(value)
    assert box.text() == "20 MHz"
    assert box.validate("20x", 0)[0] != QValidator.Acceptable          # garbage is not accepted
    assert box.validate("5G", 0)[0] != QValidator.Acceptable           # above the allowed range
    box.setValue(1e3)
    box.stepBy(1)
    assert box.value() == pytest.approx(2e3)
    box.stepBy(1)
    box.stepBy(1)
    assert box.value() == pytest.approx(1e4) and box.text() == "10 kHz"
    box.stepBy(-1)
    assert box.value() == pytest.approx(5e3)
    # table and axis
    _connect(win, qtbot)
    _short_sweep(win, 100.0, 20e6, 2)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        win.start_sweep(check_skew=False)
    t = win.status_log.table
    qtbot.waitUntil(lambda: t.rowCount() == len(win.result.points), timeout=5000)
    assert t.item(0, 1).text() == "100 Hz" and t.item(t.rowCount() - 1, 1).text() == "20 MHz"
    assert t.item(0, 4).text() in ("20 mV", "10 mV", "50 mV")          # V/div with a multiplier
    axis = win.plot.gain_plot.getAxis("bottom")
    assert axis.tickStrings([2.0, 3.0, 4.0, 6.0, 7.0, 2.5], 1.0, 1.0) == ["100", "1 k", "10 k", "1 M", "10 M", ""]
    assert win.waveform.label.text() == "Capture at 20 MHz"


def test_menus_bring_closed_panels_back(win, qtbot):
    titles = [a.text().replace("&", "") for a in win.menuBar().actions()]
    assert titles == ["File", "View", "Help"]
    for name in ("dock_config", "dock_waveform", "dock_log"):
        dock, act = win.docks[name], win.view_actions[name]
        assert dock.isVisible() and act.isChecked()
        dock.close()                                            # what the dock's X button does
        qtbot.waitUntil(lambda: not dock.isVisible(), timeout=2000)
        assert not act.isChecked()
        act.trigger()                                           # View menu brings it back
        qtbot.waitUntil(lambda: dock.isVisible(), timeout=2000)
        assert act.isChecked()
    # toolbar too
    win.toolbar.hide()
    assert not win.view_actions["toolbar_main"].isChecked()
    win.view_actions["toolbar_main"].trigger()
    assert win.toolbar.isVisible()
    # reset layout restores everything at once, floating docks included
    for dock in win.docks.values():
        dock.close()
    win.docks["dock_log"].setFloating(True)
    win.toolbar.hide()
    win.act_reset_layout.trigger()
    assert all(d.isVisible() and not d.isFloating() for d in win.docks.values()) and win.toolbar.isVisible()


def test_menu_actions_mirror_the_toolbar_and_plot(win, qtbot):
    file_menu = win.menuBar().actions()[0].menu()
    labels = [a.text().replace("&", "") for a in file_menu.actions() if not a.isSeparator()]
    assert labels == ["Connect", "Connections…", "Sim settings…", "Settings…", "Export", "Preset", "Exit"]
    assert not win.export_menu.isEnabled()                      # nothing to export yet
    win.act_unwrap.trigger()
    assert win.plot.unwrap() is True and win.act_unwrap.isChecked()
    win.plot.unwrap_box.setChecked(False)
    assert win.act_unwrap.isChecked() is False                  # stays in step both ways
    win.act_fit.trigger()                                       # no data: harmless
    _connect(win, qtbot)
    _short_sweep(win, 100.0, 10e3, 2)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        win.start_sweep(check_skew=False)
    qtbot.waitUntil(lambda: win.export_menu.isEnabled(), timeout=5000)
    text = win.about_text()
    assert "Bode plotter 0.1.0" in text and "Connected (simulation)" in text and "skew:" in text
    assert "Settings:" in text and "Log file:" in text and "PySide6" in text
    win.show_about()
    win.open_log_folder()
    win.open_config_folder()                                    # non-interactive: no window opens


def test_fit_view_with_no_data_is_harmless(win):
    win.plot.fit_view()
    assert win.plot.data_ranges() is None


def test_sweep_without_a_check_is_flagged(win, qtbot, tmp_path):
    _connect(win, qtbot)
    _short_sweep(win, 1e6, 20e6, 3)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        assert win.start_sweep(check_skew=False)
    assert all(p.flags & Flag.SKEW_UNCHECKED for p in win.result.points)
    assert "# skew: not checked" in win.export(tmp_path / "u.csv").read_text(encoding="utf-8")
    assert "! skew: not checked" in win.export(tmp_path / "u.s2p").read_text(encoding="utf-8")


def test_recheck_is_requested_after_resync_and_front_panel(win, qtbot):
    _connect(win, qtbot)
    _skew_check(win, qtbot)
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.engine.simulate_resync()
    qtbot.waitUntil(lambda: not win.info.skew_valid, timeout=5000)
    assert "resynchronised" in win.info.recheck_reason
    _skew_check(win, qtbot)
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.front_panel_used()
    qtbot.waitUntil(lambda: not win.info.skew_valid, timeout=5000)
    assert "front panel" in win.info.recheck_reason
    # connect, resync, front panel: each one prompts (the prompt is posted to the event loop)
    qtbot.waitUntil(lambda: win.status_log.text.toPlainText().count("Skew check needed") >= 3, timeout=5000)
    # reconnect: per session
    _skew_check(win, qtbot)
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.toggle_connection()
    qtbot.waitUntil(lambda: not win.info.connected, timeout=5000)
    _connect(win, qtbot)
    assert not win.info.skew_valid


def test_pause_resume_abort_from_the_gui(win, qtbot):
    win.settings.sim["latency_ms"] = 20.0
    _connect(win, qtbot)
    _skew_check(win, qtbot)
    _short_sweep(win, 100.0, 1e6, 20)
    win.start_sweep()
    qtbot.waitUntil(lambda: len(win.plot.points()) >= 2, timeout=20000)
    assert not win.config.isEnabled(), (win.state, win.status_log.text.toPlainText()[-600:])
    win.toggle_pause()
    qtbot.waitUntil(lambda: win.state is EngineState.PAUSED, timeout=10000)
    assert win.act_pause.text() == "Resume"
    n = len(win.plot.points())
    qtbot.wait(200)
    assert len(win.plot.points()) == n
    win.toggle_pause()
    qtbot.waitUntil(lambda: len(win.plot.points()) > n, timeout=20000)
    with qtbot.waitSignal(win.engine.finished, timeout=20000):
        win.abort()
    assert win.result.meta["aborted"] and 0 < len(win.result.points) < 81
    qtbot.waitUntil(lambda: win.config.isEnabled(), timeout=5000)


def test_remeasure_a_point(win, qtbot):
    _connect(win, qtbot)
    _skew_check(win, qtbot)
    _short_sweep(win, 100.0, 10e3, 3)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        win.start_sweep()
    f = win.result.points[2].freq_hz
    with qtbot.waitSignal(win.engine.point_remeasured, timeout=10000):
        win.remeasure(f)
    assert win.result.points[2].flags & Flag.REMEASURED
    assert len(win.plot.points()) == len(win.result.points)


def test_invalid_sweep_is_refused_before_anything_runs(win, qtbot):
    _connect(win, qtbot)
    p = win.config.preset()
    p.scope.dut_channel = p.scope.ref_channel
    win.config.set_preset(p)
    assert win.start_sweep(check_skew=False) is False
    assert "must be different" in win.status_log.text.toPlainText()
    assert win.state is not EngineState.RUNNING


def test_presets_and_settings_persist(win, qtbot, tmp_path):
    _short_sweep(win, 123.0, 4567.0, 9)
    win.save_preset_as("lab one")
    assert presets.list_presets() == ["lab one"]
    _short_sweep(win, 50.0, 1e6, 5)
    win.preset_box.setCurrentText("lab one")
    win._preset_chosen(0)
    assert win.config.sweep().start_hz == 123.0 and win.config.sweep().points_per_decade == 9
    win.plot.set_unwrap(True)
    win._save_ui_state()
    from bodeplot.io.settings import load_settings
    s = load_settings()
    assert s.last_preset == "lab one" and s.unwrap_phase is True
    assert s.last_config["sweep"]["start_hz"] == 123.0 and s.window_geometry


def test_non_sim_connect_failure_is_reported(qtbot, tmp_path, monkeypatch):
    """A real connection that cannot be made (here: instrument access is disabled for the
    whole test suite) is reported and leaves the app disconnected."""
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    w = MainWindow(simulate=False, settings=AppSettings(simulate=False))
    w.interactive = False
    qtbot.addWidget(w)
    with qtbot.waitSignal(w.engine.error, timeout=5000) as blocker:
        w.toggle_connection()
    assert "instrument access is disabled" in blocker.args[0]
    assert not w.info.connected
    w.close()


def test_sim_flag_is_for_this_run_only(qtbot, tmp_path, monkeypatch):
    """The user started 'run.bat' after a '--sim' run and still got the simulation."""
    from bodeplot.io.settings import load_settings
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    w = MainWindow(simulate=True, settings=AppSettings(simulate=False))
    w.interactive = False
    qtbot.addWidget(w)
    assert w.settings.simulate                      # this run is simulated
    w.close()
    assert load_settings().simulate is False        # the next plain start is not
    w2 = MainWindow()
    qtbot.addWidget(w2)
    assert not w2.settings.simulate
    w2.close()


@pytest.mark.parametrize("mode,stored,expect", [("instruments", True, False), ("simulation", False, True),
                                                ("last", True, True), ("last", False, False)])
def test_startup_mode_decides_what_a_plain_start_comes_up_in(qtbot, tmp_path, monkeypatch, mode, stored, expect):
    from bodeplot.io.settings import load_settings, save_settings
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    save_settings(AppSettings(simulate=stored, startup_mode=mode))
    w = MainWindow()
    w.interactive = False
    qtbot.addWidget(w)
    assert w.settings.simulate is expect
    assert w.mode_box.currentData() is expect
    assert ("SIMULATION" in w.sim_label.text()) is expect
    w.close()
    assert load_settings().simulate is stored       # the start-up mode does not overwrite "last time"


def test_mode_box_switches_between_instruments_and_simulation(win, qtbot):
    from bodeplot.io.settings import load_settings
    assert win.mode_box.currentData() is True and win.mode_box.isEnabled()
    win.mode_box.setCurrentIndex(0)
    win.mode_box.activated.emit(0)
    assert win.settings.simulate is False and win.sim_label.text() == ""
    assert load_settings().simulate is False
    assert win.connect_request().simulate is False
    win.set_mode(True)
    assert win.mode_box.currentData() is True and "SIMULATION" in win.sim_label.text()
    _connect(win, qtbot)
    assert not win.mode_box.isEnabled()             # not while connected
    win.set_mode(False)
    assert win.settings.simulate is True and win.mode_box.currentData() is True


def test_settings_dialog_holds_every_stored_setting(qtbot):
    from bodeplot.gui.dialogs import SettingsDialog
    s = AppSettings(simulate=True, startup_mode="last", sim=dict(SIM))
    d = SettingsDialog(s)
    qtbot.addWidget(d)
    assert [d.tabs.tabText(i) for i in range(d.tabs.count())] == ["General", "Instruments", "Simulation"]
    assert d.startup.currentData() == "last" and d.gap.minimum() == 100
    d.startup.setCurrentIndex(d.startup.findData("simulation"))
    d.gap.setValue(250)
    d.unwrap.setChecked(True)
    d.connections.simulate.setChecked(False)
    d.connections.source.setText(" USB0::1::2::3::INSTR ")
    d.sim.preset.setCurrentIndex(d.sim.preset.findData("through"))
    d._accept()
    d.apply_to(s)
    assert (s.startup_mode, s.scope_min_gap_ms, s.unwrap_phase, s.simulate) == ("simulation", 250.0, True, False)
    assert s.source_resource == "USB0::1::2::3::INSTR" and s.sim["preset"] == "through"
    # while connected the instrument and simulation tabs are read-only and are not applied
    d2 = SettingsDialog(s, connected=True)
    qtbot.addWidget(d2)
    d2.connections.source.setText("changed")
    d2.startup.setCurrentIndex(d2.startup.findData("instruments"))
    d2._accept()
    d2.apply_to(s)
    assert s.source_resource == "USB0::1::2::3::INSTR" and s.startup_mode == "instruments"


def test_settings_file_keeps_numbers_and_rejects_bad_values():
    s = AppSettings.from_dict({"scope_min_gap_ms": 250, "startup_mode": "simulation"})
    assert s.scope_min_gap_ms == 250.0 and s.startup_mode == "simulation"
    s = AppSettings.from_dict({"scope_min_gap_ms": 5, "startup_mode": "nonsense"})
    assert s.scope_min_gap_ms == 100.0 and s.startup_mode == "instruments"


def _sweep(win, qtbot, ppd=3):
    win.config.ppd.setValue(ppd)
    _connect(win, qtbot)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        win.start_sweep()
    qtbot.waitUntil(lambda: win.state is EngineState.DONE, timeout=5000)


def test_vertical_unit_db_voltage_or_percent(win, qtbot):
    _sweep(win, qtbot)
    plot, pts = win.plot, win.plot.points()
    assert [plot.unit_box.itemText(i) for i in range(plot.unit_box.count())] == ["dB", "Voltage", "% of input"]
    low, high = pts[0], pts[-1]                             # RC low-pass: 50 Hz and 20 MHz
    assert plot.unit() == "db" and plot.value(low) == low.gain_db
    assert "dB" in plot.gain_plot.getAxis("left").labelString()

    plot.unit_box.setCurrentIndex(plot.unit_box.findData("v"))
    assert plot.value(low) == pytest.approx(1.0, rel=0.03)         # 1 Vpp through at 50 Hz
    assert plot.value(low) == pytest.approx(2 * low.vdut_amp)
    axis = plot.gain_plot.getAxis("left")
    assert "Output" in axis.labelString() and "Vpp" in axis.labelString()
    (_x, (g0, g1), _p) = plot.data_ranges()
    assert g0 < plot.value(high) < 0.01 and 1.0 < g1 < 1.2         # the view was refitted in volts
    y = plot.traces["sweep"].gain_line.getData()[1]
    assert float(y[0]) == pytest.approx(plot.value(low))
    assert "Vpp" in plot.value_text(low)

    plot.set_unit("pct")
    assert plot.value(low) == pytest.approx(100.0, abs=1.0) and plot.value(high) < 1.0
    assert plot.value(low) == pytest.approx(100.0 * 10 ** (low.gain_db / 20.0))
    assert "%" in plot.gain_plot.getAxis("left").labelString() and "% of input" in plot.value_text(low)
    win.close()                                             # the choice is remembered
    from bodeplot.io.settings import load_settings
    assert load_settings().vertical_unit == "pct"


def test_log_axis_keeps_its_labels_when_zoomed_inside_a_decade():
    from bodeplot.gui.si_widgets import SiAxis
    axis = SiAxis("bottom")
    axis.logMode = True
    # 1.0 kHz to 1.9 kHz: no decade line in view. Before: no tick at all.
    levels = axis.tickValues(math.log10(1050.0), math.log10(1900.0), 600)
    vals = [v for _s, vs in levels for v in vs]
    labels = axis.tickStrings(vals, 1.0, 1.0)
    assert len(vals) >= 4 and all(labels) and len(set(labels)) == len(labels)
    assert "1.2 k" in labels and "1.8 k" in labels
    # 300 Hz to 3 kHz: one decade line; it gets company
    vals = [v for _s, vs in axis.tickValues(math.log10(300.0), math.log10(3000.0), 600) for v in vs]
    labels = axis.tickStrings(vals, 1.0, 1.0)
    assert "1 k" in labels and len([t for t in labels if t]) >= 4
    # a wide view is unchanged: decades labelled, minor ticks blank
    levels = axis.tickValues(1.0, 7.5, 600)
    labels = axis.tickStrings([2.0, 3.0, 2.5], 1.0, 1.0)
    assert labels == ["100", "1 k", ""]


def test_frequency_label_moves_to_the_upper_plot_when_there_is_no_phase(win):
    plot = win.plot
    plot.set_has_phase(False)
    axis = plot.gain_plot.getAxis("bottom")
    assert axis.label.isVisible() and "Frequency" in axis.labelString() and "Hz" in axis.labelString()
    plot.set_has_phase(True)
    assert not plot.gain_plot.getAxis("bottom").label.isVisible()
    assert "Hz" in plot.phase_plot.getAxis("bottom").labelString()


def test_a_ticked_box_still_looks_ticked_while_the_panel_is_disabled():
    """During a sweep the configuration panel is disabled; a ticked 'Descending' then drew
    as empty, as if it had reset itself (reported by the user, 2026-10-06)."""
    from bodeplot.gui import theme
    qss = theme.stylesheet() if hasattr(theme, "stylesheet") else theme.QSS
    assert "QCheckBox::indicator:checked:disabled" in qss
    assert qss.index("QCheckBox::indicator:checked:disabled") > qss.index("QCheckBox::indicator:disabled")


def test_descending_sweep_measures_from_the_top_down(win, qtbot):
    win.config.descending.click()
    order = []
    win.engine.point_measured.connect(lambda p: order.append(p.freq_hz))
    _sweep(win, qtbot)
    assert win.config.descending.isChecked()
    assert order[0] == pytest.approx(20e6) and order == sorted(order, reverse=True)


def test_fast_preview_is_in_the_method_box_and_does_not_ask_for_a_skew_check(win, qtbot):
    from bodeplot.models import Method
    _connect(win, qtbot)
    _short_sweep(win, 1e3, 1e5, 3)
    win.config.method.setCurrentIndex(win.config.method.findData(Method.PREVIEW))
    assert win.config.measure().method is Method.PREVIEW
    asked = []
    win._ask = lambda *a, **k: asked.append(a) or None
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        assert win.start_sweep()                              # check_skew left at its default
    assert asked == [] and all(p.flags & Flag.PREVIEW for p in win.result.points)


def test_method_box_keeps_its_choice_when_the_session_updates(win, qtbot):
    """User report: Fast preview went back to Sine fit when the sweep ended. The real scope has
    no built-in measurement, and every session update reset the box to its first entry."""
    from bodeplot.models import Method
    win.config.method.setCurrentIndex(win.config.method.findData(Method.PREVIEW))
    win.config.set_has_builtin(False)
    assert win.config.measure().method is Method.PREVIEW
    win.config.set_has_builtin(True)
    win.config.method.setCurrentIndex(win.config.method.findData(Method.BUILTIN))
    win.config.set_has_builtin(False)                    # the entry that is gone is the only one left
    assert win.config.measure().method is Method.SINEFIT


def test_connecting_does_not_pop_up_a_skew_question_but_starting_a_sweep_does(win, qtbot):
    """User: the question on every connect was a nuisance. The status bar and the log say that
    the check is needed; only starting a sweep without one asks."""
    from PySide6.QtWidgets import QMessageBox
    asked = []
    win.interactive = True
    win._ask = lambda *a, **k: asked.append(a[0]) or QMessageBox.Cancel
    _connect(win, qtbot)
    qtbot.wait(50)                                       # anything posted to the event loop has run
    assert asked == [] and "UNCHECKED" in win.skew_status[1]
    _short_sweep(win, 1e3, 1e5, 3)
    assert win.start_sweep() is False and asked == ["Channel skew"]     # asked, and Cancel stops it
    win.interactive = False


# ---------------------------------------------------------------------- through calibration
def test_engine_measures_accepts_and_drops_a_calibration(win, qtbot):
    _connect(win, qtbot)
    assert not win.info.cal_valid and win.info.cal is None and win.info.cal_text == "cal: none"
    progress = []
    win.engine.progress.connect(lambda i, n: progress.append((i, n)))
    cal = _calibrate(win, qtbot)
    assert cal.acceptable and len(cal.freqs_hz) == 58 and progress[-1] == (58, 58)
    assert win.info.cal is cal and win.info.cal_text.startswith("cal: ") and "50 Hz to 20 MHz" in win.info.cal_text
    assert not win.info.skew_valid                               # an independent record
    assert "Through calibration accepted" in win.status_log.text.toPlainText()
    assert win.state is EngineState.IDLE
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.engine.simulate_resync()
    qtbot.waitUntil(lambda: not win.info.cal_valid, timeout=5000)
    _calibrate(win, qtbot)
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.engine.discard_cal()
    qtbot.waitUntil(lambda: not win.info.cal_valid, timeout=5000)
    _calibrate(win, qtbot)
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.front_panel_used()
    qtbot.waitUntil(lambda: not win.info.cal_valid, timeout=5000)


def test_aborting_a_calibration_leaves_none(win, qtbot):
    win.settings.sim["latency_ms"] = 20.0
    _connect(win, qtbot)
    seen = []
    win.engine.progress.connect(lambda i, n: seen.append(i))
    with qtbot.waitSignal(win.engine.cal_measured, timeout=30000) as blocker:
        win.engine.run_cal(win.configs())
        qtbot.waitUntil(lambda: len(seen) >= 2, timeout=20000)
        win.abort()
    assert blocker.args[0] is None and len(seen) < 58
    qtbot.waitUntil(lambda: win.state is EngineState.IDLE, timeout=5000)
    assert not win.info.cal_valid and "Calibration cancelled" in win.status_log.text.toPlainText()


def test_a_refused_calibration_cannot_be_accepted(win, qtbot):
    _connect(win, qtbot)
    with qtbot.waitSignal(win.engine.cal_measured, timeout=30000) as blocker:
        win.engine.run_cal(win.configs())
    cal = blocker.args[0]
    cal.acceptable = False
    win.engine.accept_cal(cal)
    # not waitSignal(session_changed): the run itself ends with one, which would be caught instead
    qtbot.waitUntil(lambda: "not accepted" in win.status_log.text.toPlainText(), timeout=5000)
    qtbot.wait(50)
    assert not win.info.cal_valid
