"""The Analysis panel (offscreen): nothing before Analyse, the table after it, a second
trace next to the first, the line that says the trace has changed, the clipboard text, and
its place in the window."""
import cmath
import math

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QPushButton

from bodeplot.gui import theme
from bodeplot.gui.analysis_panel import IDLE, AnalysisPanel
from bodeplot.gui.bode_plot import BodePlot
from bodeplot.gui.main_window import LAYOUT_VERSION, MainWindow
from bodeplot.io.settings import PANELS, AppSettings
from bodeplot.measure.theory import TransferFunction
from bodeplot.models import Flag, PointResult
from bodeplot.traces import TraceSet
from bodeplot.units import parse_si

RC = TransferFunction.rc_lpf(1e3, 100e-9)
BPF = TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9)
FC = 1 / (2 * math.pi * 1e3 * 100e-9)
FREQS = [50.0 * (2e7 / 50.0) ** (i / 112) for i in range(113)]  # 50 Hz to 20 MHz, 20 per decade


def point(f, h, flags=Flag.NONE):
    return PointResult(freq_hz=f, h=h, gain_db=20 * math.log10(abs(h)), phase_deg=math.degrees(cmath.phase(h)),
                       vref_amp=0.5, vdut_amp=0.5 * abs(h), vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1,
                       snr_ref_db=50.0, snr_dut_db=50.0, flags=flags, duration_s=0.1)


def sweep(tf=RC, freqs=FREQS):
    return [point(f, tf.h(f)) for f in freqs]


@pytest.fixture
def plot(qtbot):
    p = BodePlot(TraceSet())
    qtbot.addWidget(p)
    p.resize(900, 600)
    p.show()
    QApplication.processEvents()
    return p


@pytest.fixture
def panel(qtbot, plot):
    w = AnalysisPanel(plot)
    qtbot.addWidget(w)
    w.resize(400, 560)
    w.show()
    return w


def value(panel, group, name, column=1):
    rows = panel.rows()
    start = [r[0] for r in rows].index(group)
    for r in rows[start + 1:]:
        if r[0] == name:
            return r[column]
    raise AssertionError("no row %r in %r" % (name, group))


def fc(panel, column=1):
    return parse_si(value(panel, "Cut-off", "fc", column), "Hz")


def choose(box, text):
    box.setCurrentIndex(box.findText(text))
    box.activated.emit(box.currentIndex())


# ---------------------------------------------------------------------- only on the button
def test_nothing_is_worked_out_before_analyse(plot, panel):
    plot.set_points(sweep())
    assert panel.rows() == [] and panel.text() == "" and IDLE in panel.state.text()
    assert not panel.copy_btn.isEnabled() and panel.analyse_btn.isEnabled()
    assert [panel.table.headerItem().text(c) for c in range(4)] == ["Quantity", "Value", "Compare", "Difference"]


def test_analyse_fills_the_table(plot, panel):
    plot.set_points(sweep())
    panel.analyse_btn.click()
    groups = [r[0] for r in panel.rows() if r[1:] == ["", "", ""] and r[0] in ("Passband", "Cut-off", "Roll-off", "Stopband")]
    assert groups == ["Passband", "Cut-off", "Roll-off", "Stopband"]
    assert fc(panel) == pytest.approx(FC, rel=0.01) and value(panel, "Cut-off", "fc").endswith(" kHz")
    assert value(panel, "Roll-off", "Order, fc") == "1"
    assert value(panel, "Stopband", "Beyond fc").startswith("≥ ")
    assert panel.table.isColumnHidden(2) and panel.table.isColumnHidden(3)      # nothing to compare with
    assert "Sweep, analysed " in panel.state.text() and "changed" not in panel.state.text()
    assert panel.copy_btn.isEnabled() and "sweep ends before" in panel.notes.text()
    head = panel.table.topLevelItem(1)                  # after the Type group
    assert head.text(0) == "Passband"
    assert head.isExpanded() and len(head.toolTip(0)) > 60 and head.isFirstColumnSpanned()
    assert head.child(0).toolTip(1) == "Passband, Level. " + head.toolTip(0)     # the name in full, then the rule
    assert head.child(0).textAlignment(1) & Qt.AlignRight


def test_the_analysis_reads_the_trace_itself_whatever_the_plot_shows(plot, panel):
    plot.set_points(sweep())
    theory = plot.set.add_theory(RC)
    plot.traces_changed()
    plot.set.set_reference(theory.id)                   # 'Difference to trace': the plot draws a flat line at 0 dB
    plot.refresh()
    plot.set_unit("pct")
    panel.analyse()
    assert fc(panel) == pytest.approx(FC, rel=0.01)              # still the cut-off of the trace itself


def test_a_band_pass_shows_its_resonance(plot, panel):
    plot.set_points(sweep(BPF))
    panel.analyse()
    titles = [r[0] for r in panel.rows()]
    assert "Peak at 15.91 kHz" in titles and "Band" in titles
    assert value(panel, "Peak at 15.91 kHz", "Q (width)") == "1" and value(panel, "Band", "Q") == "1"
    plot.set_has_phase(False)                           # a magnitude-only measurement
    panel.analyse()
    assert "Q (phase)" not in [r[0] for r in panel.rows()]


# ---------------------------------------------------------------------- a second trace
def test_compare_with_a_theory_curve(plot, panel):
    plot.set_points(sweep(TransferFunction.rc_lpf(1e3, 110e-9)))        # the real capacitor is 10 % larger
    theory = plot.set.add_theory(RC)
    plot.traces_changed()
    assert [panel.compare_box.itemText(i) for i in range(panel.compare_box.count())] == ["off", "Sweep", theory.name]
    assert [panel.trace_box.itemText(i) for i in range(panel.trace_box.count())] == ["Sweep", theory.name]
    choose(panel.compare_box, theory.name)
    panel.analyse()
    assert not panel.table.isColumnHidden(2) and not panel.table.isColumnHidden(3)
    assert fc(panel, 1) == pytest.approx(FC / 1.1, rel=0.01) and fc(panel, 2) == pytest.approx(FC, rel=0.01)
    assert float(value(panel, "Cut-off", "fc", 3).rstrip(" %")) == pytest.approx(-9.1, abs=0.3)
    assert "compared with " + theory.name in panel.state.text()
    assert panel.text().splitlines()[1] == "Quantity\tValue\tCompare\tDifference"


def test_a_trace_compared_with_itself_is_shown_alone(plot, panel):
    plot.set_points(sweep())
    choose(panel.compare_box, "Sweep")
    panel.analyse()
    assert panel.table.isColumnHidden(2) and "compared" not in panel.state.text()


# ---------------------------------------------------------------------- the table stays, and says when it is old
def test_the_table_stays_and_says_when_the_trace_has_changed(plot, panel):
    plot.set_points(sweep())
    panel.analyse()
    before = panel.rows()
    assert not panel.stale()
    plot.add_point(point(3e7, RC.h(3e7)))               # a sweep is running: one more point
    assert panel.stale() and "trace changed since this analysis" in panel.state.text()
    assert theme.WARNING in panel.state.text() and panel.rows() == before     # the numbers wait for the next press
    panel.analyse()
    assert not panel.stale() and "changed" not in panel.state.text()


def test_a_removed_trace_makes_the_table_old_and_the_boxes_fall_back(plot, panel):
    plot.set_points(sweep())
    theory = plot.set.add_theory(BPF)
    plot.traces_changed()
    choose(panel.trace_box, theory.name)
    choose(panel.compare_box, "Sweep")
    panel.analyse()
    assert any(r[0].startswith("Peak at 15.9") for r in panel.rows())
    plot.set.remove(theory.id)
    plot.traces_changed()
    assert panel.stale() and panel.trace_box.currentText() == "Sweep" and panel.compare_box.currentText() == "Sweep"
    panel.analyse()                                     # now the sweep, alone
    assert fc(panel) == pytest.approx(FC, rel=0.01) and panel.table.isColumnHidden(2)


def test_an_empty_trace_says_so(plot, panel):
    panel.analyse()
    assert panel.rows() == [] and "No analysis: the trace has no points." in panel.notes.text()
    assert not panel.notes_area.isHidden()
    plot.set_points(sweep(freqs=[100.0, 1e3, 1e4]))
    panel.analyse()
    assert "fewer than 5 usable points" in panel.notes.text()


def test_flagged_points_show_in_the_table_and_the_notes(plot, panel):
    plot.set_points([point(f, RC.h(f), Flag.LOW_SNR if 1000 < f < 2000 else Flag.NONE) for f in FREQS])
    panel.analyse()
    assert value(panel, "Cut-off", "fc").endswith("(flagged)") and "points are flagged" in panel.notes.text()


# ---------------------------------------------------------------------- clipboard, look
def test_copy_table(plot, panel):
    plot.set_points(sweep())
    panel.analyse()
    panel.copy_btn.click()
    text = QApplication.clipboard().text()
    assert text == panel.text() and text.splitlines()[0] == "Analysis of: Sweep"
    assert "fc\t" + value(panel, "Cut-off", "fc") in text.splitlines()


def test_the_panel_gives_its_height_to_the_table_and_stays_narrow(plot, panel):
    plot.set_points(sweep(BPF))
    QApplication.processEvents()
    narrow = panel.minimumSizeHint().width()
    plot.set.add_theory(TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9)).name = "A theory curve with a very long name indeed"
    plot.traces_changed()
    panel.analyse()
    QApplication.processEvents()
    assert panel.table.height() >= 0.5 * panel.height()
    assert panel.trace_box.y() < panel.analyse_btn.y() < panel.state.y() < panel.table.y() < panel.notes_area.y()
    assert panel.notes_area.height() <= 4 * panel.fontMetrics().lineSpacing() + 2      # the notes never crowd the table out
    assert panel.table.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert panel.table.columnWidth(0) + sum(panel.table.columnWidth(c) for c in (1, 2, 3) if not panel.table.isColumnHidden(c)) \
        <= panel.table.viewport().width() + 2                                           # every column is on screen
    # neither a long trace name nor the table, the state line or the notes widen the panel
    assert panel.minimumSizeHint().width() == narrow
    assert panel.trace_box.view().minimumWidth() > panel.trace_box.width()     # the list that drops down shows the long name


def test_every_control_explains_itself(panel):
    for w in panel.findChildren(QPushButton) + panel.findChildren(QComboBox) + panel.findChildren(QCheckBox):
        tip, text = w.toolTip().strip(), w.text() if hasattr(w, "text") else type(w).__name__
        assert len(tip) >= 25 and tip != text, text
    assert panel.trace_label.toolTip() == panel.trace_box.toolTip()
    assert panel.compare_label.toolTip() == panel.compare_box.toolTip()
    assert all(len(w.toolTip()) >= 25 for w in (panel.table, panel.state, panel.notes, panel.notes_area))


# ---------------------------------------------------------------------- the main window
@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    w = MainWindow(simulate=True, settings=AppSettings(simulate=True), sim_seed=7)
    w.interactive = False
    qtbot.addWidget(w)
    w.show()
    yield w
    w.close()


def test_window_has_an_analysis_tab_behind_traces_and_markers(win):
    dock = win.docks["dock_analysis"]
    assert dock.widget() is win.analysis_panel and dock.windowTitle() == "Analysis"
    assert dock in win.tabifiedDockWidgets(win.docks["dock_traces"])
    assert win.dockWidgetArea(dock) == Qt.RightDockWidgetArea
    assert win.view_actions["dock_analysis"].text() == "&Analysis"
    assert "dock_analysis" in PANELS and win.settings.startup_panels["dock_analysis"] is True
    assert LAYOUT_VERSION == 3                          # the default arrangement changed: an older stored one is dropped once


def test_the_analysis_tab_does_not_widen_the_right_column(win, qtbot):
    """The app must fit a 1280 px wide screen (user, 2026-10-07): the right column is as wide as
    its widest tab, and that stays the Markers panel."""
    before = win.minimumSizeHint().width()
    win.docks["dock_analysis"].raise_()
    qtbot.waitUntil(lambda: win.analysis_panel.isVisible(), timeout=2000)
    win.plot.set_points(sweep(BPF))
    win.analysis_panel.analyse()
    QApplication.processEvents()
    assert win.analysis_panel.minimumSizeHint().width() <= win.markers_panel.minimumSizeHint().width()
    assert win.minimumSizeHint().width() == before


def test_analyse_in_the_window_after_a_simulated_sweep(win, qtbot):
    win.plot.set_points(sweep())
    win.analysis_panel.analyse_btn.click()
    assert fc(win.analysis_panel) == pytest.approx(FC, rel=0.01)
    win.plot.clear()                                    # a new sweep starts
    assert win.analysis_panel.stale()


# ---------------------------------------------------------------------- the analysis numbers (Settings, Analysis tab)
def test_changed_settings_wait_for_analyse_and_the_line_says_so(plot, panel):
    import dataclasses
    from bodeplot.measure.analysis_settings import DEFAULTS
    plot.set_points(sweep())
    panel.analyse_btn.click()
    assert fc(panel) == pytest.approx(FC, rel=0.02)
    panel.set_settings(dataclasses.replace(DEFAULTS, drop_db=6.0))
    assert "settings changed since this analysis" in panel.state.text()
    assert fc(panel) == pytest.approx(FC, rel=0.02)                     # the table waits
    panel.analyse_btn.click()
    assert "changed" not in panel.state.text()
    assert fc(panel) == pytest.approx(FC * math.sqrt(10 ** 0.6 - 1), rel=0.02)
    tips = [panel.table.topLevelItem(i).toolTip(0) for i in range(panel.table.topLevelItemCount())]
    assert any("fallen 6 dB below" in t for t in tips)                  # the rules name the numbers in force


def test_analysis_curve_splits_the_flags(plot):
    """Classification design section 4: a flag on every point is the sweep's, not a point's."""
    wide = Flag.SKEW_UNCHECKED
    plot.set_points([point(f, RC.h(f), wide | Flag.CLIPPED if i in (10, 20) else wide) for i, f in enumerate(FREQS)])
    c = plot.analysis_curve(plot.set.live.id)
    assert c.wide_flags == ["skew unchecked"]
    assert [i for i, b in enumerate(c.point_flagged) if b] == [10, 20]
    assert all(c.flagged)
    plot.set_points([point(f, RC.h(f), Flag.CLIPPED if i == 3 else Flag.NONE) for i, f in enumerate(FREQS)])
    c = plot.analysis_curve(plot.set.live.id)
    assert c.wide_flags == [] and [i for i, b in enumerate(c.point_flagged) if b] == [3]


# ---------------------------------------------------------------------- the type (classification design, section 6)
def test_the_type_comes_first_after_analyse(plot, panel):
    plot.set_points(sweep())
    panel.analyse()
    assert panel.rows()[0] == ["Type", "", "", ""]
    assert value(panel, "Type", "Type") == "Low-pass" and value(panel, "Type", "Confidence") == "100 %"
    assert panel.text().splitlines()[2:4] == ["Type", "Type\tLow-pass"]
    assert "type" in panel.analyse_btn.toolTip() and "confidence" in panel.analyse_btn.toolTip()


def test_compare_shows_both_types(plot, panel):
    plot.set_points(sweep())
    theory = plot.set.add_theory(BPF)
    plot.traces_changed()
    choose(panel.compare_box, theory.name)
    panel.analyse()
    assert value(panel, "Type", "Type", 2) == "Band-pass" and value(panel, "Type", "Type", 3) == "differs"


def test_type_rows_have_tooltips(plot, panel):
    plot.set_points(sweep())
    panel.analyse()
    head = panel.table.topLevelItem(0)
    assert head.text(0) == "Type" and "Confidence" in head.toolTip(0) and "40 %" in head.toolTip(0)
    assert head.child(0).toolTip(1) == "Type, Type. " + head.toolTip(0)


def test_a_sweep_with_unchecked_skew_says_so_first_in_the_notes(plot, panel):
    plot.set_points([point(f, RC.h(f), Flag.SKEW_UNCHECKED) for f in FREQS])
    panel.analyse()
    assert value(panel, "Type", "Confidence") == "90 %"
    assert panel.notes.text().splitlines()[0].startswith("−10 % Skew unchecked")
