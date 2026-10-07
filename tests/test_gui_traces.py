"""Traces on the plot: the plot widget, the Traces panel, the main window (offscreen)."""
import cmath
import math

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from bodeplot.gui import theme
from bodeplot.gui.bode_plot import BodePlot
from bodeplot.measure.theory import TransferFunction
from bodeplot.models import Flag, PointResult, SweepResult
from bodeplot.traces import TraceSet

RC = TransferFunction.rc_lpf(1e3, 100e-9)
FREQS = [10.0 ** (2 + i / 5) for i in range(21)]                 # 100 Hz to 1 MHz


def point(f, h, flags=Flag.NONE):
    return PointResult(freq_hz=f, h=h, gain_db=20 * math.log10(abs(h)), phase_deg=math.degrees(cmath.phase(h)),
                       vref_amp=0.5, vdut_amp=0.5 * abs(h), vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1,
                       snr_ref_db=50.0, snr_dut_db=50.0, flags=flags, duration_s=0.1)


def sweep(tf=RC, scale=1.0, freqs=FREQS):
    return [point(f, scale * tf.h(f)) for f in freqs]


@pytest.fixture
def plot(qtbot):
    p = BodePlot(TraceSet())
    qtbot.addWidget(p)
    p.resize(900, 600)
    p.show()
    return p


def line_y(plot, trace, which="gain_line"):
    y = getattr(plot.items(trace), which).getData()[1]             # None when the line is empty
    return np.array([] if y is None else y, dtype=float)


# ---------------------------------------------------------------------- the plot widget
def test_plot_with_only_the_live_trace_is_as_before(plot):
    assert [plot.ref_box.itemText(i) for i in range(plot.ref_box.count())] == ["nothing", "Sweep"]
    assert plot.ref_box.currentData() is None and not plot.is_relative()
    plot.set_points(sweep())
    assert plot.points() == plot.set.live.points and len(plot.points()) == 21
    y = line_y(plot, plot.set.live)
    assert y[0] == pytest.approx(plot.points()[0].gain_db) and len(y) == 21
    assert "Gain" in plot.gain_plot.getAxis("left").labelString()
    assert "difference" not in plot.gain_plot.getAxis("left").labelString()
    text = plot.readout_at(1000.0)
    assert text.startswith("1 kHz") and "gain" in text and "phase" in text and "Sweep" not in text
    plot.clear()
    assert plot.points() == [] and len(line_y(plot, plot.set.live)) == 0


def test_theory_and_file_traces_are_drawn_in_their_slot_colours(plot):
    plot.set_span_hint(50.0, 2e7)
    plot.set_points(sweep())
    th = plot.set.add_theory(RC)
    bad = sweep(scale=0.9)
    bad[3].flags |= Flag.LOW_SNR
    f = plot.set.add_file(SweepResult({}, bad, {}), "board.csv")
    plot.traces_changed()
    assert [plot.ref_box.itemText(i) for i in range(plot.ref_box.count())] == [
        "nothing", "Sweep", "RC low-pass 1 kΩ 100 nF", "board"]
    y = line_y(plot, th)
    assert len(y) > 250 and y[0] == pytest.approx(20 * math.log10(abs(RC.h(50.0))))      # 50 Hz to 20 MHz, smooth
    assert plot.items(th).gain_ok is None                        # a theory curve has no markers
    assert plot.items(th).gain_line.opts["pen"].color().name() == theme.SERIES[1]
    assert plot.items(f).gain_line.opts["pen"].color().name() == theme.SERIES[2]
    assert len(plot.items(f).gain_bad.points()) == 1 and len(plot.items(f).gain_ok.points()) == 20
    (x0, x1), _g, _p = plot.data_ranges()
    assert x0 < math.log10(50.0) + 0.05 and x1 > math.log10(2e7) - 0.05      # fit view covers every trace
    plot.set.set_visible(th.id, False)
    plot.traces_changed()
    assert len(line_y(plot, th)) == 0
    plot.set.remove(th.id)
    plot.traces_changed()
    with pytest.raises(KeyError):
        plot.items(th)


def test_relative_to_a_theory_curve(plot):
    plot.set_points(sweep(scale=10 ** (-0.06 / 20)))             # the hand comparison: a steady -0.06 dB
    th = plot.set.add_theory(RC)
    plot.traces_changed()
    plot.ref_box.setCurrentIndex(plot.ref_box.findData(th.id))
    plot.ref_box.activated.emit(plot.ref_box.currentIndex())
    assert plot.is_relative() and plot.set.reference() is th
    assert line_y(plot, plot.set.live) == pytest.approx(np.full(21, -0.06), abs=1e-9)
    assert line_y(plot, plot.set.live, "phase_line") == pytest.approx(np.zeros(21), abs=1e-9)
    assert line_y(plot, th) == pytest.approx(0.0, abs=1e-12)     # the reference is the zero line
    assert "Gain difference" in plot.gain_plot.getAxis("left").labelString()
    assert "Phase difference" in plot.phase_plot.getAxis("left").labelString()
    text = plot.readout_at(1000.0, y=-0.06)
    assert "Sweep" in text and "difference" in text and "relative to RC low-pass 1 kΩ 100 nF" in text
    plot.set_unit("pct")
    assert line_y(plot, plot.set.live) == pytest.approx(np.full(21, 100 * 10 ** (-0.06 / 20)))
    assert "reference" in plot.gain_plot.getAxis("left").labelString()
    plot.set.remove(th.id)
    plot.traces_changed()
    assert not plot.is_relative() and plot.ref_box.currentData() is None
    assert "Output / input" in plot.gain_plot.getAxis("left").labelString()


def test_voltage_unit_draws_measured_traces_only(plot):
    plot.set_points(sweep())
    th = plot.set.add_theory(RC)
    plot.set.set_reference(th.id)
    plot.traces_changed()
    plot.set_unit("v")
    assert not plot.ref_box.isEnabled() and not plot.is_relative()
    assert len(line_y(plot, th)) == 0
    assert line_y(plot, plot.set.live)[0] == pytest.approx(2 * plot.points()[0].vdut_amp)
    assert "Vpp" in plot.readout_at(1000.0)
    plot.set_unit("db")
    assert plot.ref_box.isEnabled() and plot.is_relative()        # the choice comes back with the unit


def test_readout_picks_the_trace_under_the_cursor(plot):
    plot.set_points(sweep())
    low = plot.set.add_file(SweepResult({}, sweep(scale=0.1), {}), "low.csv")     # 20 dB below
    plot.traces_changed()
    at = RC.h(1000.0)
    assert plot.readout_at(1000.0, y=20 * math.log10(abs(at))).startswith("Sweep:")
    assert plot.readout_at(1000.0, y=20 * math.log10(abs(at)) - 20.0).startswith("low:")
    assert plot.readout_at(1000.0, y=math.degrees(cmath.phase(at)), phase_plot=True).startswith(("Sweep:", "low:"))
    assert plot.readout_at(-5.0) == ""


def test_export_series_is_what_the_plot_shows(plot):
    plot.set_points(sweep())
    th = plot.set.add_theory(RC)
    plot.traces_changed()
    series, labels = plot.export_series()
    assert [s.name for s in series] == ["Sweep", "RC low-pass 1 kΩ 100 nF"] and [s.slot for s in series] == [0, 1]
    assert labels == ("Gain (dB)", "Phase (deg)", "")
    assert series[0].flagged is not None and not series[0].flagged.any() and series[1].flagged is None
    assert series[0].gain[0] == pytest.approx(plot.points()[0].gain_db)
    plot.set.set_reference(th.id)
    plot.traces_changed()
    series, labels = plot.export_series()
    assert labels == ("Gain difference (dB)", "Phase difference (deg)", "relative to RC low-pass 1 kΩ 100 nF")
    assert series[0].gain == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------- theory dialog
def test_theory_dialog_builds_a_transfer_function(qtbot):
    from bodeplot.gui.dialogs import TheoryDialog
    d = TheoryDialog()
    qtbot.addWidget(d)
    assert d.circuit.preset.currentData() == "rc_lpf" and d.tf is None
    d.circuit._edits["r"].setText("997.8")
    d.circuit._edits["c"].setText("98.2n")
    d._accept()
    assert d.tf.name == "rc_lpf" and d.tf.params == pytest.approx({"r": 997.8, "c": 98.2e-9})
    again = TheoryDialog(d.tf)                                   # reopened on a trace: its values are shown
    qtbot.addWidget(again)
    assert again.circuit.preset.currentData() == "rc_lpf" and again.circuit._edits["r"].text() == "997.8"
    again.circuit.preset.setCurrentIndex(again.circuit.preset.findData("custom"))
    again.circuit.num.setText("1")
    again.circuit.den.setText("1e-4, 1")
    again._accept()
    assert again.tf.name == "custom" and again.tf.den == (1e-4, 1.0)


@pytest.mark.parametrize("preset, edits, word", [
    ("rc_lpf", {"r": "0"}, "positive"), ("rc_lpf", {"c": "-1n"}, "positive"),
    ("rc_lpf", {"r": "lots"}, "Invalid"), ("custom", {"den": "0, 0"}, "coefficient"),
    ("custom", {"num": ""}, "coefficient"), ("custom", {"den": "1, x"}, "Invalid")])
def test_theory_dialog_refuses_bad_values(qtbot, preset, edits, word):
    from bodeplot.gui.dialogs import TheoryDialog
    d = TheoryDialog()
    qtbot.addWidget(d)
    d.circuit.preset.setCurrentIndex(d.circuit.preset.findData(preset))
    for key, text in edits.items():
        (getattr(d.circuit, key) if preset == "custom" else d.circuit._edits[key]).setText(text)
    d._accept()
    assert d.tf is None and word in d.error.text() and d.result() == 0     # still open, nothing made


# ---------------------------------------------------------------------- the Traces panel
@pytest.fixture
def panel(qtbot, plot):
    from bodeplot.gui.traces_panel import TracesPanel
    p = TracesPanel(plot.set)
    p.interactive = False
    p.changed.connect(plot.traces_changed)
    p.messages = []
    p.message.connect(lambda level, text: p.messages.append((level, text)))
    qtbot.addWidget(p)
    p.show()
    return p


def rows(panel):
    return [(panel.tree.topLevelItem(i).text(0), panel.tree.topLevelItem(i).text(1))
            for i in range(panel.tree.topLevelItemCount())]


def test_panel_lists_traces_and_its_buttons_follow(panel, plot):
    assert rows(panel) == [("Sweep", "live sweep")]
    assert not panel.keep_btn.isEnabled() and not panel.remove_btn.isEnabled()
    plot.set_points(sweep())
    panel.refresh_buttons()
    assert panel.keep_btn.isEnabled()
    panel.keep()
    panel.add_theory(RC)
    assert [k for _n, k in rows(panel)] == ["live sweep", "kept sweep", "theory"]
    assert plot.ref_box.count() == 4                              # the plot was told
    panel.select(plot.set.live.id)
    assert not panel.remove_btn.isEnabled()                       # the live sweep stays
    kept = plot.set.traces[1]
    panel.select(kept.id)
    assert panel.selected_id() == kept.id and panel.remove_btn.isEnabled()
    panel.remove_selected()
    assert [k for _n, k in rows(panel)] == ["live sweep", "theory"] and plot.ref_box.count() == 3


def test_panel_ticks_and_names_edit_the_traces(panel, plot):
    from PySide6.QtCore import Qt
    plot.set_points(sweep())
    panel.add_theory(RC)
    th = plot.set.traces[1]
    item = panel.tree.topLevelItem(1)
    item.setCheckState(0, Qt.Unchecked)
    assert th.visible is False and len(line_y(plot, th)) == 0
    item.setCheckState(0, Qt.Checked)
    item.setText(0, "ideal")
    assert th.name == "ideal" and plot.ref_box.itemText(2) == "ideal"
    item.setText(0, "Sweep")                                      # the live trace's name: made unique
    assert th.name == "Sweep (2)" and panel.tree.topLevelItem(1).text(0) == "Sweep (2)"
    panel.edit_theory(th.id, TransferFunction.rc_hpf(1e3, 100e-9))
    assert th.theory.name == "rc_hpf" and th.name == "Sweep (2)"
    panel.set_unit("v")
    assert "Voltage" in panel.tree.topLevelItem(1).toolTip(0)
    panel.set_unit("db")
    assert "Voltage" not in panel.tree.topLevelItem(1).toolTip(0)


def test_loading_files_good_and_bad(panel, plot, tmp_path):
    from bodeplot.io import export_csv
    good = export_csv.write_csv(tmp_path / "board A.csv", SweepResult({}, sweep(), {}))
    old = tmp_path / "old.csv"
    old.write_text("freq_hz,gain_db,phase_deg\n100,-1.0,-10\n1000,-3.0,-45\n", encoding="utf-8")
    other = tmp_path / "shopping.csv"
    other.write_text("item,price\nmilk,1\n", encoding="utf-8")
    binary = tmp_path / "photo.csv"
    binary.write_bytes(bytes(range(256)) * 4)
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    errors = panel.load_files([str(good), str(other), str(old), str(binary), str(empty), str(tmp_path / "gone.csv")])
    assert [n for n, _k in rows(panel)] == ["Sweep", "board A", "old"]
    assert len(errors) == 4 and all(any(name in e for e in errors)
                                    for name in ("shopping.csv", "photo.csv", "empty.csv", "gone.csv"))
    assert any("no sweep points" in e for e in errors)
    assert ("info", "Loaded 2 traces.") in panel.messages
    assert sum(1 for level, _t in panel.messages if level == "warn") == 4
    assert plot.ref_box.count() == 4 and len(line_y(plot, plot.set.traces[1])) == 21
    assert panel.load_files([]) == [] and len(plot.set.traces) == 3


def test_keep_without_a_sweep_says_so(panel):
    panel.keep()
    assert panel.messages == [("warn", "Keep sweep: there is no sweep to keep.")] and len(rows(panel)) == 1


def test_simulation_settings_still_use_the_same_form(qtbot):
    from bodeplot.gui.dialogs import SimSettingsPanel
    p = SimSettingsPanel({"preset": "rlc_bpf", "params": {"r": 50.0, "l": 2e-3, "c": 10e-9}, "noise_vrms": 2e-4,
                          "latency_ms": 1.0})
    qtbot.addWidget(p)
    v = p.values()
    assert v == {"preset": "rlc_bpf", "params": pytest.approx({"r": 50.0, "l": 2e-3, "c": 10e-9}),
                 "noise_vrms": pytest.approx(2e-4), "latency_ms": 1.0}
    p.preset.setCurrentIndex(p.preset.findData("rc_lpf"))
    p.circuit._edits["r"].setText("0")
    with pytest.raises(ValueError, match="positive"):
        p.values()


# ---------------------------------------------------------------------- main window
from bodeplot.gui.main_window import MainWindow          # noqa: E402
from bodeplot.io.settings import AppSettings             # noqa: E402
from bodeplot.models import EngineState, SweepConfig, SweepType     # noqa: E402

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


def run_sweep(win, qtbot, lo=100.0, hi=1e5, ppd=4):
    if not win.info.connected:
        with qtbot.waitSignal(win.engine.session_changed, timeout=5000):
            win.toggle_connection()
        qtbot.waitUntil(lambda: win.info.connected, timeout=5000)
    p = win.config.preset()
    p.sweep = SweepConfig(SweepType.LOG, lo, hi, ppd)
    p.measure.settle_ms, p.measure.settle_cycles = 0.0, 0.0
    win.config.set_preset(p)
    with qtbot.waitSignal(win.engine.finished, timeout=30000):
        assert win.start_sweep(check_skew=False)
    qtbot.waitUntil(lambda: win.state is EngineState.DONE, timeout=5000)


def test_window_has_a_traces_panel(win):
    assert win.plot.set is win.traces and win.traces_panel.traces is win.traces
    assert win.traces_panel.interactive is False                 # follows the window's switch
    dock, act = win.docks["dock_traces"], win.view_actions["dock_traces"]
    assert dock.isVisible() and act.isChecked() and dock.windowTitle() == "Traces"
    dock.close()
    win.act_reset_layout.trigger()
    assert dock.isVisible()
    assert win.plot.span_hint == (50.0, 20e6)                    # the sweep settings of the panel
    assert not win.traces_panel.keep_btn.isEnabled()


def test_a_new_sweep_keeps_the_other_traces(win, qtbot):
    run_sweep(win, qtbot)
    first = win.plot.points()
    assert win.traces_panel.keep_btn.isEnabled()
    win.traces_panel.keep()
    win.traces_panel.add_theory(RC)
    kept, th = win.traces.traces[1], win.traces.traces[2]
    win.plot.ref_box.setCurrentIndex(win.plot.ref_box.findData(th.id))
    win.plot.ref_box.activated.emit(win.plot.ref_box.currentIndex())
    run_sweep(win, qtbot, 1e3, 1e4, 3)
    assert [t.kind for t in win.traces.traces] == ["live", "kept", "theory"]
    assert kept.points == first and len(win.plot.points()) == 4 and win.traces.reference() is th
    # against the ideal filter the simulated one reads zero within its noise
    y = line_y(win.plot, win.traces.live)
    assert np.abs(y).max() < 0.1
    assert "Loaded" not in win.status_log.text.toPlainText()
    assert win.result is not None and len(win.result.points) == 4          # the exports' result is the live sweep


def test_panel_messages_reach_the_status_log(win, tmp_path):
    win.traces_panel.load_files([str(tmp_path / "missing.csv")])
    assert "Not loaded: missing.csv" in win.status_log.text.toPlainText()
    win.traces_panel.set_unit("db")
    win.plot.set_unit("v")
    assert win.traces_panel.unit == "v"                           # the panel follows the plot's unit


def test_image_export_draws_what_the_plot_shows(win, qtbot, tmp_path, monkeypatch):
    from bodeplot.io import export_image
    run_sweep(win, qtbot)
    win.traces_panel.add_theory(RC)
    win.plot.set.set_reference(win.traces.traces[1].id)
    win.plot.traces_changed()
    seen = {}
    real = export_image.write_image

    def spy(path, result, opts=None, series=None, labels=None, **kw):
        seen.update(series=series, labels=labels)
        return real(path, result, opts, series, labels, **kw)
    monkeypatch.setattr(export_image, "write_image", spy)
    for name in ("t.png", "t.svg", "t.pdf"):
        out = win.export(tmp_path / name)
        assert out.exists() and out.stat().st_size > 500
    assert [s.name for s in seen["series"]] == ["Sweep", "RC low-pass 1 kΩ 100 nF"]
    assert seen["labels"] == ("Gain difference (dB)", "Phase difference (deg)", "relative to RC low-pass 1 kΩ 100 nF")
    csv = win.export(tmp_path / "t.csv").read_text(encoding="utf-8")
    assert "RC low-pass" not in csv and "# bodeplot_csv: 1" in csv        # the CSV is the live sweep only


# ---------------------------------------------------------------------- found by the branch review
def test_live_points_stay_on_top_for_the_re_measure_click(plot):
    """Review I2: a kept or loaded trace drawn over the live sweep took the click, so
    re-measure stopped working exactly when two similar sweeps were compared."""
    plot.set_points(sweep())
    kept = plot.set.keep_live()
    plot.traces_changed()
    live, other = plot.items(plot.set.live), plot.items(kept)
    for name in ("gain_ok", "gain_bad", "phase_ok", "phase_bad"):
        assert getattr(live, name).zValue() > getattr(other, name).zValue(), name
    assert live.gain_line.zValue() > other.gain_line.zValue()
    seen = []
    plot.remeasure_enabled = True
    plot.remeasure_requested.connect(seen.append)
    spot = type("Spot", (), {"data": lambda self: (kept.id, kept.points[3], 0.0, 0.0)})()
    plot._clicked(None, [spot])                                  # a click that does reach another trace: no menu
    assert seen == []


def test_voltage_unit_with_a_file_that_has_no_voltages(panel, plot, tmp_path):
    """Review I4: such a file was drawn as NaN and not marked in the list."""
    old = tmp_path / "old.csv"
    old.write_text("freq_hz,gain_db,phase_deg\n100,-1.0,-10\n1000,-3.0,-45\n", encoding="utf-8")
    plot.set_points(sweep())
    assert panel.load_files([str(old)]) == []
    t = plot.set.traces[1]
    assert len(line_y(plot, t)) == 2
    plot.set_unit("v")
    panel.set_unit("v")
    assert len(line_y(plot, t)) == 0 and len(line_y(plot, plot.set.live)) == 21
    assert "Vpp" in plot.readout_at(1000.0) and plot.readout_at(1000.0).startswith("Sweep:")
    assert "Voltage" in panel.tree.topLevelItem(1).toolTip(0)
    assert "Voltage" not in panel.tree.topLevelItem(0).toolTip(0)
    plot.set_unit("db")
    assert len(line_y(plot, t)) == 2


def test_the_kind_column_cannot_be_edited(panel, plot):
    """Review M6: double-clicking a kind opened an inline editor on the word 'file'."""
    delegate = panel.tree.itemDelegateForColumn(1)
    assert delegate is not None and delegate.createEditor(None, None, None) is None
    assert panel.tree.itemDelegateForColumn(0) is None           # names stay editable


def test_a_csv_saved_by_a_spreadsheet_with_a_byte_order_mark_loads(panel, plot, tmp_path):
    """Review M8."""
    from bodeplot.io import export_csv
    path = export_csv.write_csv(tmp_path / "excel.csv", SweepResult({}, sweep(), {}))
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert panel.load_files([str(path)]) == [] and len(plot.set.traces[1].points) == 21


def test_image_export_needs_no_finished_sweep(win, tmp_path):
    """Review I3: with a loaded file and a theory curve but no sweep, the Export button was
    disabled and the export raised; that is the design's own acceptance case."""
    from bodeplot.io import export_csv
    assert not win.export_button.isEnabled()
    path = export_csv.write_csv(tmp_path / "saved.csv", SweepResult({}, sweep(), {}))
    win.traces_panel.load_files([str(path)])
    win.traces_panel.add_theory(RC)
    assert win.result is None and win.export_button.isEnabled() and win.export_menu.isEnabled()
    for name in ("only.png", "only.svg", "only.pdf"):
        assert win.export(tmp_path / name).stat().st_size > 500
    with pytest.raises(ValueError, match="no sweep"):
        win.export(tmp_path / "only.csv")                        # CSV and Touchstone are the live sweep
    win.traces.set_visible(win.traces.traces[1].id, False)
    win.traces.set_visible(win.traces.traces[2].id, False)
    win.plot.traces_changed()
    with pytest.raises(ValueError, match="nothing on the plot"):
        win.export(tmp_path / "empty.png")


# ---------------------------------------------------------------------- layout (user report 2026-10-07)
def test_plot_size_does_not_follow_the_readout_or_the_trace_names(plot):
    """User: the Configuration panel was squeezed by the plot and its width jumped while it
    was being resized. Cause: the read-out text and the Relative-to box grew the plot's
    minimum width as the mouse moved or a trace was named."""
    plot.set_points(sweep())
    before = (plot.minimumSizeHint().width(), plot.sizeHint().width())
    plot.readout.setText("some trace with a long name:   1.23456 MHz   gain difference -12.345 dB   "
                         "phase difference -123.45°   [LOW_SNR, BELOW_FLOOR]   (relative to another long name)" * 3)
    t = plot.set.add_theory(RC)
    plot.set.rename(t.id, "a theory curve with a very long name that the user typed in " * 3)
    plot.traces_changed()
    assert (plot.minimumSizeHint().width(), plot.sizeHint().width()) == before
    assert plot.ref_box.itemText(2).startswith("a theory curve with a very long name")
    assert plot.ref_box.toolTip() and plot.ref_box.view().minimumWidth() > plot.ref_box.width() - 1


def test_configuration_panel_keeps_the_width_its_fields_need(win, qtbot):
    from PySide6.QtCore import Qt
    need = win.config.widget().minimumSizeHint().width()
    assert win.config.minimumWidth() >= need
    assert win.config.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    dock = win.docks["dock_config"]
    qtbot.waitUntil(lambda: dock.width() >= need, timeout=2000)
    width = dock.width()
    win.plot.readout.setText("x" * 600)
    win.traces_panel.add_theory(RC)
    win.traces.rename(win.traces.traces[1].id, "y" * 300)
    win.traces_panel.reload()
    win.plot.traces_changed()
    qtbot.wait(50)
    assert dock.width() == width and win.config.viewport().width() >= need


# ---------------------------------------------------------------------- deferred review items, fixed 2026-10-07
def test_a_new_live_point_does_not_redraw_the_other_traces(plot):
    """Review M1: every trace was redrawn for every point of a running sweep."""
    pts = sweep()
    plot.set.add_file(SweepResult({}, sweep(scale=0.5), {}), "other.csv")
    th = plot.set.add_theory(RC)
    plot.set_span_hint(100.0, 1e6)
    plot.traces_changed()
    other = plot.items(plot.set.traces[1])
    calls = []
    for item, name in ((other.gain_ok, "scatter"), (other.gain_line, "line"), (plot.items(th).gain_line, "theory")):
        real = item.setData
        item.setData = lambda *a, _real=real, _name=name, **k: (calls.append(_name), _real(*a, **k))[1]
    for p in pts[:5]:
        plot.add_point(p)
    assert calls == [] and len(line_y(plot, plot.set.live)) == 5
    plot.set_unit("pct")                                         # a real change still redraws them
    assert "scatter" in calls and "theory" in calls


def test_readout_ignores_a_trace_that_ends_far_from_the_cursor(plot):
    """Review M7: the read-out showed the last point of a short trace while the cursor was decades away."""
    plot.set_points(sweep())                                     # 100 Hz to 1 MHz
    short = plot.set.add_file(SweepResult({}, sweep(scale=0.1, freqs=FREQS[:6]), {}), "short.csv")   # to 1 kHz
    plot.traces_changed()
    last = 20 * math.log10(abs(0.1 * RC.h(FREQS[5])))
    assert plot.readout_at(FREQS[5], y=last).startswith("short:")
    far = plot.readout_at(1e5, y=last)                           # the cursor at 100 kHz, at the height of that last point
    assert far.startswith("Sweep:") and "100 kHz" in far
    assert plot.readout_at(1e9) == "1 GHz"                       # beyond every trace: the frequency only
    assert short.points[-1].freq_hz == FREQS[5]


def test_reopening_a_theory_curve_keeps_its_values_exactly(qtbot):
    """Review M5: the form showed 6 significant digits, so OK without a change altered the curve."""
    from bodeplot.gui.dialogs import TheoryDialog
    tf = TransferFunction.rc_lpf(1234.5678, 98.19e-9)
    d = TheoryDialog(tf)
    qtbot.addWidget(d)
    d._accept()
    assert d.tf.params == pytest.approx({"r": 1234.5678, "c": 98.19e-9}, rel=1e-12)
    custom = TheoryDialog(TransferFunction.custom([1.0], [1.23456789e-4, 1.0]))
    qtbot.addWidget(custom)
    custom._accept()
    assert custom.tf.den == pytest.approx((1.23456789e-4, 1.0), rel=1e-12)


def test_configuration_panel_can_be_made_slim(win, qtbot):
    """User, after the fix above: the panel now stopped the plot from growing, and it has a lot
    of unused space. Its fields may shrink to a small fixed minimum, so the panel can be
    dragged much narrower than its natural width (and never needs a horizontal scroll bar)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractSpinBox, QComboBox
    from bodeplot.gui.config_panel import FIELD_MIN_WIDTH
    fields = win.config.widget().findChildren(QAbstractSpinBox) + win.config.widget().findChildren(QComboBox)
    assert len(fields) > 10 and all(w.minimumWidth() == FIELD_MIN_WIDTH for w in fields)
    slim, natural = win.config.minimumWidth(), win.config.widget().sizeHint().width()
    assert slim >= win.config.widget().minimumSizeHint().width() and slim < 0.8 * natural
    dock = win.docks["dock_config"]
    win.resizeDocks([dock], [slim], Qt.Horizontal)
    qtbot.waitUntil(lambda: dock.width() <= slim + 30, timeout=2000)
    assert win.config.viewport().width() >= win.config.widget().minimumSizeHint().width()
