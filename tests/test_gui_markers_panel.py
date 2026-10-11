"""The Markers panel: the switches, the table of values, the colour (offscreen).

User's review of 2026-10-07: the Markers button in the row above the plot crowded it (the
vertical unit read as a marker setting), so the controls moved into a panel of their own."""
import cmath
import math

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QPushButton

from bodeplot.gui import theme
from bodeplot.gui.bode_plot import BodePlot
from bodeplot.gui.main_window import MainWindow
from bodeplot.gui.markers_panel import MarkersPanel
from bodeplot.io import export_image
from bodeplot.io.settings import AppSettings
from bodeplot.markers import KINDS, MAX_USER
from bodeplot.measure.theory import TransferFunction
from bodeplot.models import Flag, PointResult
from bodeplot.traces import TraceSet

RC = TransferFunction.rc_lpf(1e3, 100e-9)
BPF = TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9)
FC = 1 / (2 * math.pi * 1e3 * 100e-9)
FREQS = [10.0 ** (2 + i / 20) for i in range(101)]              # 100 Hz to 10 MHz, 20 per decade


def point(f, h):
    return PointResult(freq_hz=f, h=h, gain_db=20 * math.log10(abs(h)), phase_deg=math.degrees(cmath.phase(h)),
                       vref_amp=0.5, vdut_amp=0.5 * abs(h), vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1,
                       snr_ref_db=50.0, snr_dut_db=50.0, flags=Flag.NONE, duration_s=0.1)


def sweep(tf=RC):
    return [point(f, tf.h(f)) for f in FREQS]


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
    w = MarkersPanel(plot)
    qtbot.addWidget(w)
    w.show()
    return w


def rows(panel):
    t = panel.table
    return [[t.topLevelItem(i).text(c) for c in range(t.columnCount())] for i in range(t.topLevelItemCount())]


def names(plot):
    return plot.marker_layer.names()


# ---------------------------------------------------------------------- the row above the plot
def test_the_row_above_the_plot_has_no_marker_control(plot):
    assert [b.text() for b in plot.findChildren(QPushButton)] == ["Fit view"]
    assert not hasattr(plot, "markers_btn") and not hasattr(plot, "marker_menu")


def test_the_difference_box_says_what_it_does(plot):
    """User's review: "Relative to: nothing" did not explain itself."""
    assert plot.ref_label.text().strip() == "Difference to trace"
    assert plot.ref_box.itemText(0) == "off" and plot.ref_box.itemData(0) is None
    assert "difference" in plot.ref_box.toolTip() and plot.ref_label.toolTip() == plot.ref_box.toolTip()


# ---------------------------------------------------------------------- the switches
def test_tick_boxes_switch_the_automatic_markers(plot, panel):
    plot.set_points(sweep())
    assert list(panel.kind_boxes) == list(KINDS) and not any(b.isChecked() for b in panel.kind_boxes.values())
    assert [b.text() for b in panel.kind_boxes.values()] == ["-3 dB", "Peak", "Notch", "Margins"]
    panel.kind_boxes["cutoff"].setChecked(True)
    assert plot.marker_kinds() == ["cutoff"] and names(plot) == ["fc"]
    panel.kind_boxes["cutoff"].setChecked(False)
    assert plot.marker_kinds() == [] and names(plot) == []
    plot.set_marker_kinds(["peak", "margins"])                   # from the settings: the boxes follow
    assert [k for k, b in panel.kind_boxes.items() if b.isChecked()] == ["peak", "margins"]


def test_the_trace_box_chooses_the_trace(plot, panel):
    plot.set_span_hint(100.0, 1e7)
    plot.set_points(sweep())
    th = plot.set.add_theory(BPF)
    plot.traces_changed()
    plot.set_marker_kinds(["peak", "cutoff"])
    box = panel.trace_box
    assert [box.itemText(i) for i in range(box.count())] == ["Sweep", th.name] and box.currentData() == plot.set.live.id
    box.setCurrentIndex(1)
    box.activated.emit(1)                                        # what a choice with the mouse sends
    assert plot.markers.trace_id == th.id and names(plot) == ["fL", "fH", "pk"]
    plot.set.remove(th.id)
    plot.traces_changed()
    assert [box.itemText(i) for i in range(box.count())] == ["Sweep"] and box.currentData() == plot.set.live.id
    assert plot.markers.trace_id == plot.set.live.id and names(plot) == ["fc"]


def test_buttons_add_remove_and_copy(plot, panel):
    assert not panel.add_btn.isEnabled()                         # nothing on the plot: a marker would stand unseen
    plot.set_points(sweep())
    assert panel.add_btn.isEnabled()
    panel.add_btn.click()
    (x0, x1), _g, _p = plot.view_ranges()
    assert math.log10(plot.markers.user[1]) == pytest.approx((x0 + x1) / 2)
    for k in range(MAX_USER - 1):
        plot.add_marker(200.0 * (k + 1))
    assert not panel.add_btn.isEnabled() and plot.add_marker(123.0) is None          # the limit
    panel.copy_btn.click()
    assert QApplication.clipboard().text() == plot.marker_text() and "M8" in plot.marker_text()
    panel.clear_btn.click()
    assert plot.markers.user == {} and panel.add_btn.isEnabled()
    plot.set.set_visible(plot.set.live.id, False)
    plot.traces_changed()
    assert not panel.add_btn.isEnabled() and plot.add_marker(1000.0) is None         # the chosen trace is hidden
    assert not plot.context_menu(1000.0).actions()[0].isEnabled()


# ---------------------------------------------------------------------- the table
def test_the_table_lists_every_marker_with_its_values(plot, panel):
    assert [panel.table.headerItem().text(c) for c in range(5)] == ["Marker", "Frequency", "Gain", "Phase", "Note"]
    assert rows(panel) == []
    plot.set_points(sweep())
    plot.set_marker_kinds(["cutoff", "peak"])
    plot.add_marker(1000.0), plot.add_marker(10000.0)
    plot.toggle_reference_marker(1)
    got = rows(panel)
    assert [r[0] for r in got] == ["fc", "pk", "M1", "M2"]
    assert got[0][1].endswith("kHz") and got[0][2] in ("-3.02 dB", "-3.03 dB", "-3.04 dB") and got[0][3].startswith("-4") and got[0][3].endswith("°")
    assert got[1] == ["pk", "", "", "", "none"]                  # switched on, and a low-pass has no peak
    assert got[2][1] == "1 kHz" and got[2][4] == "reference marker"
    assert got[3][4].startswith("rel. M1: x10, ") and got[3][4].endswith("dB/dec")
    assert panel.table.topLevelItem(3).toolTip(4) == got[3][4]   # a long note can be read in full in a narrow panel
    plot.set_unit("pct")
    assert rows(panel)[0][2].endswith("%")
    plot.set_unit("db")
    plot.set_has_phase(False)
    assert all(r[3] == "" for r in rows(panel)) and "deg" not in rows(panel)[3][4]
    plot.clear()
    assert rows(panel) == []


def test_the_table_follows_a_dragged_marker(plot, panel):
    plot.set_points(sweep())
    plot.add_marker(1000.0)
    plot.move_marker(1, 5000.0)
    assert rows(panel)[0][:2] == ["M1", "5 kHz"]
    plot.add_marker(5e9)
    assert rows(panel)[1] == ["M2", "5 GHz", "", "", "outside the trace"]


# ---------------------------------------------------------------------- values on the plot
def test_values_on_the_plot_can_be_switched_off(plot, panel):
    plot.set_points(sweep(BPF))
    plot.set_marker_kinds(["cutoff", "peak"])
    plot.add_marker(1000.0)
    assert panel.values_box.isChecked() and plot.marker_values()
    full = {p.marker.name: p.text for p in plot.placed()}
    assert "dB" in full["pk"] and "\n" in full["fH"]
    panel.values_box.setChecked(False)
    assert not plot.marker_values()
    assert {p.marker.name: p.text for p in plot.placed() if p.marker.found} == {n: n for n in ("fL", "fH", "pk", "M1")}
    assert plot.marker_layer.items("fH").text.toPlainText() == "fH"
    assert rows(panel)[0][2] == "-3.00 dB"                       # the numbers stay in the table
    assert [m.text for m in plot.export_markers()] == ["fL", "fH", "pk", "M1"]       # the image shows what the screen shows
    plot.set_marker_values(True)
    assert panel.values_box.isChecked() and "dB" in plot.placed()[0].text


def test_every_option_of_the_panel_explains_itself(panel):
    for w in panel.findChildren(QPushButton) + panel.findChildren(QComboBox) + panel.findChildren(QCheckBox):
        tip, text = w.toolTip().strip(), w.text() if hasattr(w, "text") else type(w).__name__
        assert len(tip) >= 25 and tip != text, text
    assert len(panel.table.toolTip()) >= 25


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


def test_window_has_a_markers_panel_tabbed_with_the_traces(win):
    dock = win.docks["dock_markers"]
    assert dock.widget() is win.markers_panel and dock.windowTitle() == "Markers"
    assert dock in win.tabifiedDockWidgets(win.docks["dock_traces"])
    assert win.view_actions["dock_markers"].text() == "&Markers"
    assert win.settings.startup_panels["dock_markers"] is True
    win.markers_panel.kind_boxes["cutoff"].setChecked(True)
    assert win.plot.marker_kinds() == ["cutoff"]


def test_marker_look_survives_a_restart(win, qtbot):
    win.markers_panel.values_box.setChecked(False)
    win._save_ui_state()
    assert win.settings.marker_values is False
    again = MainWindow(simulate=True, settings=AppSettings.from_dict(win.settings.to_dict()), sim_seed=7)
    again.interactive = False
    qtbot.addWidget(again)
    try:
        assert not again.plot.marker_values() and not again.markers_panel.values_box.isChecked()
    finally:
        again.close()
    assert AppSettings.from_dict({"marker_values": "x"}).marker_values is True


# ---------------------------------------------------------------------- layout (user's review, 2026-10-07)
# "the waveform and the markers are squashed": the window is now set up | measure | read, with
# what is watched during a sweep (log, waveform) in a low strip underneath.
def test_the_panel_gives_its_height_to_the_table(plot, panel):
    plot.set_points(sweep())
    plot.set_marker_kinds(["cutoff"])
    panel.resize(380, 520)
    QApplication.processEvents()
    assert panel.table.height() >= 0.6 * panel.height()
    assert len({b.y() for b in panel.kind_boxes.values()}) == 1                  # the four ticks share one line
    assert panel.table.y() < panel.add_btn.y() < panel.values_box.y()            # content, then actions, then options
    item = panel.table.topLevelItem(0)
    from PySide6.QtCore import Qt
    assert all(item.textAlignment(c) & Qt.AlignRight for c in (1, 2, 3))         # figures line up by digit
    row = sum(b.sizeHint().width() for b in (panel.add_btn, panel.clear_btn, panel.copy_btn))
    assert panel.minimumSizeHint().width() <= row + 60           # no wider than its three buttons need


def test_window_layout_is_set_up_measure_read_with_watching_below(win, qtbot):
    from PySide6.QtCore import Qt
    d = win.docks
    area = win.dockWidgetArea
    assert area(d["dock_config"]) == Qt.LeftDockWidgetArea
    assert area(d["dock_traces"]) == Qt.RightDockWidgetArea and area(d["dock_markers"]) == Qt.RightDockWidgetArea
    assert area(d["dock_log"]) == Qt.BottomDockWidgetArea and area(d["dock_waveform"]) == Qt.BottomDockWidgetArea
    qtbot.waitUntil(lambda: d["dock_waveform"].geometry().left() > d["dock_log"].geometry().right() - 2, timeout=2000)
    log, wave, traces = d["dock_log"].geometry(), d["dock_waveform"].geometry(), d["dock_traces"].geometry()
    assert abs(log.top() - wave.top()) < 6                       # side by side in one strip
    assert traces.bottom() <= wave.top() + 2                     # the reading column ends above the strip
    assert traces.height() > 1.8 * log.height() and log.height() <= 0.27 * win.height()
    assert win.plot.width() >= 0.5 * win.width()                 # the plot keeps at least half the window


def test_only_a_layout_saved_by_this_arrangement_is_restored(win, qtbot):
    from PySide6.QtCore import Qt
    win.addDockWidget(Qt.RightDockWidgetArea, win.docks["dock_waveform"])
    old = AppSettings.from_dict(win.settings.to_dict())
    old.window_state = bytes(win.saveState().toBase64()).decode("ascii")       # as versions before this one stored it
    a = MainWindow(simulate=True, settings=old, sim_seed=7)
    a.interactive = False
    qtbot.addWidget(a)
    try:
        assert a.dockWidgetArea(a.docks["dock_waveform"]) == Qt.BottomDockWidgetArea       # the new arrangement shows
        a.addDockWidget(Qt.RightDockWidgetArea, a.docks["dock_waveform"])                  # the user moves it ...
        a._save_ui_state()
        b = MainWindow(simulate=True, settings=AppSettings.from_dict(a.settings.to_dict()), sim_seed=7)
        b.interactive = False
        qtbot.addWidget(b)
        try:
            assert b.dockWidgetArea(b.docks["dock_waveform"]) == Qt.RightDockWidgetArea    # ... and it stays there
        finally:
            b.close()
    finally:
        a.close()


def test_start_is_the_one_accented_toolbar_button(win):
    from PySide6.QtWidgets import QToolButton
    primary = [b for b in win.toolbar.findChildren(QToolButton) if b.objectName() == "primary"]
    assert primary == [win.toolbar.widgetForAction(win.act_start)]
    assert "QToolBar QToolButton#primary" in theme.QSS and theme.ACCENT in theme.QSS


def test_the_right_column_can_be_narrow(win, qtbot):
    """The app must fit a 1280 px wide screen: the Traces panel's four buttons in one row made
    the right column 415 px wide at least, and the window 1361."""
    tp = win.traces_panel
    win.docks["dock_traces"].raise_()
    qtbot.waitUntil(lambda: tp.isVisible() and tp.keep_btn.y() > 0, timeout=2000)
    assert tp.load_btn.y() == tp.theory_btn.y() < tp.keep_btn.y() == tp.remove_btn.y()       # two rows of two
    assert tp.minimumSizeHint().width() <= win.markers_panel.minimumSizeHint().width() + 20
    assert win.plot.ref_box.minimumContentsLength() <= 12
