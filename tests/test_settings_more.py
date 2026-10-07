"""The settings added on the user's request of 2026-10-07: behaviour (skew wizard on connect,
tooltips, auto-keep, folders, grid colour, start-up panels), an Advanced tab (auto-range,
timeouts and noise limits, debug logging) and the skew check's own settings."""
import logging

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QLineEdit, QPushButton, QStyle

from bodeplot import logging_setup
from bodeplot.drivers.base import DriverError
from bodeplot.gui import theme
from bodeplot.gui.main_window import MainWindow
from bodeplot.io import settings as settings_mod
from bodeplot.io.settings import AppSettings
from bodeplot.models import EngineState, MeasureSettings, ScopeConfig, StimulusConfig, SweepConfig, SweepType
from bodeplot.sweep.core import run_skew_check

SIM = {"preset": "rc_lpf", "params": {"r": 1e3, "c": 100e-9}, "noise_vrms": 2e-4, "latency_ms": 0.0}


@pytest.fixture(autouse=True)
def theme_back_to_default():
    yield
    theme.set_tooltips(True, theme.TOOLTIP_DELAY_MS)
    theme.set_grid_color("")
    logging_setup.set_debug(False)


def make_win(qtbot, tmp_path, monkeypatch, **settings):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    w = MainWindow(simulate=True, settings=AppSettings(simulate=True, sim=dict(SIM), **settings), sim_seed=7)
    w.interactive = False
    qtbot.addWidget(w)
    w.show()
    return w


def connect(win, qtbot):
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.toggle_connection()
    qtbot.waitUntil(lambda: win.info.connected, timeout=5000)


def sweep(win, qtbot, lo=1e3, hi=1e4, ppd=3):
    p = win.config.preset()
    p.sweep = SweepConfig(SweepType.LOG, lo, hi, ppd)
    p.measure.settle_ms, p.measure.settle_cycles = 0.0, 0.0
    win.config.set_preset(p)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        assert win.start_sweep(check_skew=False)
    qtbot.waitUntil(lambda: win.state is EngineState.DONE, timeout=5000)


# ---------------------------------------------------------------------- stored values
def test_new_settings_have_defaults_and_survive_a_round_trip():
    s = AppSettings()
    assert (s.skew_wizard_on_connect, s.tooltips, s.tooltip_delay_ms, s.auto_keep_sweeps) == (False, True, 3000.0, 0)
    assert (s.export_folder, s.last_folder, s.grid_color, s.debug_logging, s.advanced) == ("", "", "", False, {})
    assert s.startup_panels == {"dock_config": True, "dock_waveform": True, "dock_traces": True, "dock_log": True}
    assert (s.skew_freq_lo_hz, s.skew_freq_hi_hz, s.skew_captures) == (10e6, 20e6, 3)
    s.skew_wizard_on_connect, s.tooltip_delay_ms, s.auto_keep_sweeps, s.grid_color = True, 500.0, 3, "#445566"
    s.advanced = {"low_snr_db": 15.0, "autorange_max_retries": 5}
    s.startup_panels["dock_waveform"] = False
    s.skew_freq_lo_hz, s.skew_freq_hi_hz, s.skew_captures = 1e6, 5e6, 5
    back = AppSettings.from_dict(s.to_dict())
    assert back == s


def test_bad_stored_values_fall_back():
    s = AppSettings.from_dict({"tooltip_delay_ms": 999999, "auto_keep_sweeps": 50, "grid_color": "pink!",
                               "skew_freq_lo_hz": 2e7, "skew_freq_hi_hz": 1e7, "skew_captures": 0,
                               "startup_panels": {"dock_log": False, "nonsense": 1}, "advanced": "x"})
    assert s.tooltip_delay_ms == 10000.0 and s.auto_keep_sweeps == 6 and s.grid_color == ""
    assert (s.skew_freq_lo_hz, s.skew_freq_hi_hz, s.skew_captures) == (10e6, 20e6, 1)
    assert s.startup_panels == {"dock_config": True, "dock_waveform": True, "dock_traces": True, "dock_log": False}
    assert s.advanced == {}
    assert AppSettings.from_dict({"auto_keep_sweeps": "three", "tooltip_delay_ms": -5}).tooltip_delay_ms == 0.0


def test_measure_overrides_are_checked():
    ok = settings_mod.measure_overrides({"autorange_lo": 0.5, "autorange_hi": 0.7, "autorange_max_retries": 5,
                                         "floor_fraction": 0.05, "acquire_timeout_s": 8, "low_snr_db": 15,
                                         "bad_capture_retries": 1, "unknown": 3})
    assert ok == {"autorange_target": (0.5, 0.7), "autorange_max_retries": 5, "floor_fraction": 0.05,
                  "acquire_timeout_s": 8.0, "low_snr_db": 15.0, "bad_capture_retries": 1}
    assert settings_mod.measure_overrides({}) == {}
    bad = settings_mod.measure_overrides({"autorange_lo": 0.9, "autorange_hi": 0.5, "autorange_max_retries": 99,
                                          "floor_fraction": "x", "acquire_timeout_s": 0})
    assert bad == {"autorange_max_retries": 10, "acquire_timeout_s": 1.0}        # a wrong pair is dropped, the rest clamped
    assert MeasureSettings(**ok).autorange_target == (0.5, 0.7)


# ---------------------------------------------------------------------- theme and logging
def test_tooltip_delay_and_switch(qapp):
    app = qapp
    theme.apply(app)
    theme.set_tooltips(True, 500)
    assert app.style().styleHint(QStyle.SH_ToolTip_WakeUpDelay) == 500 and theme.tooltips_enabled()
    theme.set_tooltips(False, 500)
    assert not theme.tooltips_enabled()
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QLabel
    label = QLabel("x")
    label.setToolTip("an explanation")
    tip = QHelpEvent(QEvent.ToolTip, QPoint(1, 1), QPoint(1, 1))
    assert theme.tip_filter().eventFilter(label, tip) is True       # swallowed: no tooltip
    theme.set_tooltips(True, 3000)
    assert theme.tip_filter().eventFilter(label, tip) is False


def test_grid_colour(qtbot):
    import pyqtgraph as pg
    plot = pg.PlotWidget()
    qtbot.addWidget(plot)
    theme.style_plot(plot)
    assert plot.getPlotItem().getAxis("left").pen().color().name() == theme.BORDER
    theme.set_grid_color("#445566")
    theme.style_plot(plot)
    assert plot.getPlotItem().getAxis("left").pen().color().name() == "#445566"
    assert plot.getPlotItem().getAxis("bottom").grid > 0.18 * 255 - 1          # a chosen colour is drawn stronger
    theme.set_grid_color("not a colour")
    theme.style_plot(plot)
    assert plot.getPlotItem().getAxis("left").pen().color().name() == theme.BORDER


def test_debug_logging_switch():
    root = logging.getLogger("bodeplot")
    logging_setup.set_debug(True)
    assert root.level == logging.DEBUG
    logging_setup.set_debug(False)
    assert root.level == logging.INFO


# ---------------------------------------------------------------------- the settings dialog
def test_settings_dialog_edits_the_new_settings(qtbot, tmp_path):
    from bodeplot.gui.dialogs import SettingsDialog
    s = AppSettings(simulate=True)
    d = SettingsDialog(s)
    qtbot.addWidget(d)
    assert [d.tabs.tabText(i) for i in range(d.tabs.count())] == ["General", "Advanced", "Instruments", "Simulation"]
    assert not d.skew_on_connect.isChecked() and d.tooltips.isChecked() and d.tooltip_delay.value() == 3.0
    assert d.auto_keep.value() == 0 and d.folder.text() == "" and d.grid_color == "" and not d.debug.isChecked()
    assert all(box.isChecked() for box in d.panels.values()) and set(d.panels) == set(s.startup_panels)
    d.skew_on_connect.setChecked(True)
    d.tooltips.setChecked(False)
    d.tooltip_delay.setValue(1.5)
    d.auto_keep.setValue(2)
    d.folder.setText(str(tmp_path))
    d.set_grid_color("#445566")
    d.panels["dock_waveform"].setChecked(False)
    d.debug.setChecked(True)
    d.autorange_lo.setValue(50)
    d.autorange_hi.setValue(70)
    d.autorange_retries.setValue(5)
    d.floor.setValue(5)
    d.timeout.setValue(8.0)
    d.low_snr.setValue(15.0)
    d.bad_retries.setValue(1)
    d._accept()
    d.apply_to(s)
    assert (s.skew_wizard_on_connect, s.tooltips, s.tooltip_delay_ms, s.auto_keep_sweeps) == (True, False, 1500.0, 2)
    assert s.export_folder == str(tmp_path) and s.grid_color == "#445566" and s.debug_logging
    assert s.startup_panels["dock_waveform"] is False and s.startup_panels["dock_log"] is True
    assert settings_mod.measure_overrides(s.advanced) == {
        "autorange_target": (0.5, 0.7), "autorange_max_retries": 5, "floor_fraction": 0.05,
        "acquire_timeout_s": 8.0, "low_snr_db": 15.0, "bad_capture_retries": 1}
    again = SettingsDialog(s)
    qtbot.addWidget(again)
    assert again.autorange_lo.value() == 50 and again.low_snr.value() == 15.0 and again.grid_color == "#445566"
    again.advanced_defaults()
    again.set_grid_color("")
    again.apply_to(s)
    assert s.advanced == {} and s.grid_color == ""


def test_new_settings_explain_themselves(qtbot):
    """The design rule of tests/test_gui_tooltips.py holds for the General and Advanced tabs too."""
    from bodeplot.gui.dialogs import SettingsDialog
    d = SettingsDialog(AppSettings(simulate=True))
    qtbot.addWidget(d)
    for index in (0, 1):
        tab = d.tabs.widget(index)
        inputs = (tab.findChildren(QAbstractSpinBox) + tab.findChildren(QComboBox) + tab.findChildren(QCheckBox)
                  + tab.findChildren(QPushButton) + tab.findChildren(QLineEdit))
        inputs = [w for w in inputs if not isinstance(w.parent(), QAbstractSpinBox)]     # a spin box's own line edit
        silent = [type(w).__name__ + ":" + (w.text() if hasattr(w, "text") else "") for w in inputs
                  if len(w.toolTip().strip()) < 25]
        assert len(inputs) > 5 and not silent, "%s tab: %s" % (d.tabs.tabText(index), silent)


# ---------------------------------------------------------------------- the main window uses them
def test_startup_panels_and_appearance_are_applied(qtbot, tmp_path, monkeypatch):
    win = make_win(qtbot, tmp_path, monkeypatch, tooltip_delay_ms=700.0, grid_color="#445566", debug_logging=True,
                   startup_panels={"dock_config": True, "dock_waveform": False, "dock_traces": True, "dock_log": True},
                   advanced={"low_snr_db": 15.0}, export_folder=str(tmp_path))
    assert not win.docks["dock_waveform"].isVisible() and win.docks["dock_traces"].isVisible()
    win.view_actions["dock_waveform"].trigger()                    # still one click away
    assert win.docks["dock_waveform"].isVisible()
    assert QApplication.style().styleHint(QStyle.SH_ToolTip_WakeUpDelay) == 700
    assert win.plot.gain_plot.getPlotItem().getAxis("left").pen().color().name() == "#445566"
    assert win.waveform.plot.getPlotItem().getAxis("left").pen().color().name() == "#445566"
    assert logging.getLogger("bodeplot").level == logging.DEBUG
    assert win.config.measure().low_snr_db == 15.0 and win.config.measure().autorange_target == (0.6, 0.8)
    assert win.traces_panel.folder == str(tmp_path)
    win.close()


def test_folder_used_last_is_remembered(qtbot, tmp_path, monkeypatch):
    win = make_win(qtbot, tmp_path, monkeypatch)
    assert win.start_folder() == ""
    win.remember_folder(tmp_path / "runs" / "bode.csv")
    assert win.settings.last_folder == str(tmp_path / "runs") and win.start_folder() == str(tmp_path / "runs")
    assert win.traces_panel.folder == str(tmp_path / "runs")
    win.settings.export_folder = str(tmp_path)                     # a fixed folder wins over the last one
    win.apply_settings()
    assert win.start_folder() == str(tmp_path) and win.traces_panel.folder == str(tmp_path)
    win.traces_panel.folder_used.emit(str(tmp_path / "loaded"))    # Load CSV used another folder
    assert win.settings.last_folder == str(tmp_path / "loaded")
    win.close()


def test_auto_keep_keeps_the_last_sweeps(qtbot, tmp_path, monkeypatch):
    win = make_win(qtbot, tmp_path, monkeypatch, auto_keep_sweeps=2)
    connect(win, qtbot)
    for _ in range(4):
        sweep(win, qtbot)
    kinds = [t.kind for t in win.traces.traces]
    assert kinds == ["live", "kept", "kept"]                       # the two sweeps before the current one
    assert win.plot.ref_box.count() == 4
    manual = win.traces.keep_live()                                # one the user kept is never pruned
    win.traces_panel.reload()
    sweep(win, qtbot)
    sweep(win, qtbot)
    assert manual in win.traces.traces and [t.kind for t in win.traces.traces].count("kept") == 3
    win.close()


def test_skew_wizard_on_connect_is_a_setting(qtbot, tmp_path, monkeypatch):
    opened = []
    win = make_win(qtbot, tmp_path, monkeypatch, skew_wizard_on_connect=True)
    win.open_skew_wizard = lambda: opened.append(1) or False
    connect(win, qtbot)
    qtbot.waitUntil(lambda: opened == [1], timeout=2000)
    with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
        win.engine.simulate_resync()                               # a later update is not a connect
    qtbot.wait(50)
    assert opened == [1]
    win.close()
    off = make_win(qtbot, tmp_path, monkeypatch)
    off.open_skew_wizard = lambda: opened.append(2) or False
    connect(off, qtbot)
    qtbot.wait(50)
    assert opened == [1]                                           # off by default: the user's decision of 2026-10-06
    off.close()


# ---------------------------------------------------------------------- the skew check's own settings
def test_skew_check_with_chosen_frequencies_and_captures(make_session, no_sleep):
    session = make_session(seed=91, skew_state=2, checked=False)
    before = session.digitizer.acquire_count
    check = run_skew_check(session, StimulusConfig(), ScopeConfig(), MeasureSettings(), sleep=no_sleep,
                           freqs=(5e6, 15e6), captures=2)
    assert check.freqs_hz == [5e6, 15e6] and check.delay_s == pytest.approx(2.15e-9, abs=0.1e-9)
    four = session.digitizer.acquire_count - before
    check = run_skew_check(session, StimulusConfig(), ScopeConfig(), MeasureSettings(), sleep=no_sleep,
                           freqs=(5e6, 15e6), captures=6)
    assert session.digitizer.acquire_count - before - four > four             # more captures were taken
    top = run_skew_check(session, StimulusConfig(), ScopeConfig(), MeasureSettings(), sleep=no_sleep,
                         freqs=(10e6, 80e6))
    assert top.freqs_hz == [10e6, 30e6]                            # the upper one is limited to what both reach
    with pytest.raises(DriverError, match="frequencies"):
        run_skew_check(session, StimulusConfig(), ScopeConfig(), MeasureSettings(), sleep=no_sleep,
                       freqs=(40e6, 80e6))
    assert session.source.output == {1: False, 2: False}
    default = run_skew_check(session, StimulusConfig(), ScopeConfig(), MeasureSettings(), sleep=no_sleep)
    assert default.freqs_hz == [10e6, 20e6]


def test_skew_wizard_has_its_settings_with_defaults(qtbot, tmp_path, monkeypatch):
    from bodeplot.gui.dialogs import SkewWizard
    win = make_win(qtbot, tmp_path, monkeypatch)
    saved, asked = [], []
    wiz = SkewWizard(win.engine, win.configs, True, win.skew_freqs_hint(), win, settings=win.settings,
                     save=lambda: saved.append(1))
    qtbot.addWidget(wiz)
    assert (wiz.freq_lo.value(), wiz.freq_hi.value(), wiz.captures.value()) == (10e6, 20e6, 3)
    assert "10 MHz" in wiz.intro.text() and "20 MHz" in wiz.intro.text()
    wiz.freq_lo.setValue(2e6)
    wiz.freq_hi.setValue(8e6)
    wiz.captures.setValue(5)
    assert "2 MHz" in wiz.intro.text() and "8 MHz" in wiz.intro.text()
    monkeypatch.setattr(win.engine, "skew_check", lambda cfg: asked.append(cfg))
    wiz.measure()
    assert (win.settings.skew_freq_lo_hz, win.settings.skew_freq_hi_hz, win.settings.skew_captures) == (2e6, 8e6, 5)
    assert saved == [1] and asked[0].skew_freqs == (2e6, 8e6) and asked[0].skew_captures == 5
    wiz.freq_lo.setValue(9e6)                                      # not below the upper one: refused, nothing sent
    wiz.measure_btn.setEnabled(True)
    wiz.measure()
    assert len(asked) == 1 and "below" in wiz.warnings_text
    wiz.defaults_btn.click()
    assert (wiz.freq_lo.value(), wiz.freq_hi.value(), wiz.captures.value()) == (10e6, 20e6, 3)
    for w in (wiz.freq_lo, wiz.freq_hi, wiz.captures, wiz.defaults_btn):
        assert len(w.toolTip()) > 25
    wiz.done(0)
    win.close()


# ---------------------------------------------------------------------- presets (user report 2026-10-07)
def test_loading_a_preset_says_what_it_changed(qtbot, tmp_path, monkeypatch):
    """User: 'changing presets does not change anything'. Their two presets held identical
    settings, and nothing said so. Loading now reports what changed, or that nothing did and
    what a preset holds."""
    win = make_win(qtbot, tmp_path, monkeypatch)
    win.save_preset_as("first")
    p = win.config.preset()
    p.sweep.start_hz, p.stimulus.amp_vpp = 200.0, 2.5
    win.config.set_preset(p)
    win.save_preset_as("second")
    win.preset_box.setCurrentText("first")
    win._preset_chosen(0)
    log = win.status_log.text.toPlainText()
    assert win.config.sweep().start_hz == 50.0 and win.config.stimulus().amp_vpp == 1.0
    assert "Loaded preset 'first': 2 settings changed" in log
    assert "Start 200 Hz → 50 Hz" in log and "Amplitude 2.5 Vpp → 1 Vpp" in log
    win._preset_chosen(0)                                          # the same one again
    log = win.status_log.text.toPlainText()
    assert "Loaded preset 'first': it holds the settings that were already on screen, so nothing changed" in log
    assert "Configuration panel" in log
    win.close()


# ---------------------------------------------------------------------- toolbar buttons (user report 2026-10-07)
def type_into(spin, text):
    """Type into a number field as a user does, WITHOUT pressing Enter or leaving the field."""
    from PySide6.QtTest import QTest
    spin.setFocus()
    spin.lineEdit().selectAll()
    QTest.keyClicks(spin.lineEdit(), text)


def test_a_typed_value_counts_without_pressing_enter(qtbot, tmp_path, monkeypatch):
    """User: two presets saved after changing the stop frequency were identical. A toolbar
    button does not take the keyboard focus, so a number typed into a field and not confirmed
    with Enter was not read: Save stored the old value, and Start would have swept the old range."""
    win = make_win(qtbot, tmp_path, monkeypatch)
    type_into(win.config.stop_hz, "5k")
    assert win.config.sweep().stop_hz == 5000.0
    type_into(win.config.amp_vpp, "2.5")
    assert win.config.stimulus().amp_vpp == 2.5
    type_into(win.config.averages, "4")
    assert win.config.measure().averages == 4
    type_into(win.config.target_cycles, "8")
    assert win.config.scope().target_cycles == 8.0
    win.close()


def test_save_as_and_switching_presets_from_the_toolbar(qtbot, tmp_path, monkeypatch):
    """User: 'the Save As button does nothing' (the button passed its 'checked' flag as the
    preset name) and switching presets did not bring the stop frequency back."""
    from PySide6.QtWidgets import QInputDialog
    from bodeplot.io import presets
    win = make_win(qtbot, tmp_path, monkeypatch)
    names = iter(["LPF", "hpf"])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (next(names), True))
    type_into(win.config.stop_hz, "5M")
    win.act_preset_save_as.trigger()                              # the toolbar button itself
    type_into(win.config.stop_hz, "100k")
    win.act_preset_save_as.trigger()
    assert presets.list_presets() == ["LPF", "hpf"]
    assert presets.load_preset("LPF").sweep.stop_hz == 5e6 and presets.load_preset("hpf").sweep.stop_hz == 1e5
    assert win.preset_box.currentText() == "hpf"
    for name, stop in (("LPF", 5e6), ("hpf", 1e5), ("LPF", 5e6)):
        win.preset_box.setCurrentText(name)
        win.preset_box.activated.emit(win.preset_box.currentIndex())
        assert win.config.sweep().stop_hz == stop, name
    type_into(win.config.stop_hz, "2M")                           # Save overwrites the selected preset
    win.act_preset_save.trigger()
    assert presets.load_preset("LPF").sweep.stop_hz == 2e6 and presets.load_preset("hpf").sweep.stop_hz == 1e5
    win.close()


def test_the_start_button_asks_for_the_skew_check(qtbot, tmp_path, monkeypatch):
    """The Start button passed its 'checked' flag (False) as check_skew, so a sweep started
    from the toolbar never asked for the skew check, whatever its state."""
    from PySide6.QtWidgets import QMessageBox
    win = make_win(qtbot, tmp_path, monkeypatch)
    connect(win, qtbot)
    asked = []
    win._ask = lambda *a, **k: asked.append(a[0]) or QMessageBox.Cancel
    win.act_start.trigger()
    assert asked == ["Channel skew"] and win.state is not EngineState.RUNNING
    win.close()


def test_no_toolbar_button_hands_its_checked_flag_to_its_slot(qtbot, tmp_path, monkeypatch):
    """Every toolbar action calls its slot with no argument (the cause of the two reports above)."""
    win = make_win(qtbot, tmp_path, monkeypatch)
    got = []
    probe = win._toolbar_action("probe", lambda *args: got.append(args))
    probe.trigger()
    assert got == [()]
    win.close()
