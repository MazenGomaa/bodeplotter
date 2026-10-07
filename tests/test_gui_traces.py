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
