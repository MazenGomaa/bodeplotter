"""Markers on the plot: the Markers menu, the automatic markers, the user's own (offscreen)."""
import cmath
import math
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication

from bodeplot.gui import theme
from bodeplot.gui.bode_plot import BodePlot
from bodeplot.markers import KINDS, MAX_USER
from bodeplot.measure.theory import TransferFunction
from bodeplot.models import Flag, PointResult, SweepResult
from bodeplot.traces import TraceSet

RC = TransferFunction.rc_lpf(1e3, 100e-9)
BPF = TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9)
NOTCH = TransferFunction.rlc_notch(100.0, 1e-3, 100e-9)
W = [2 * math.pi * f for f in (100.0, 10e3, 100e3)]
LOOP = TransferFunction.custom([100.0], np.polymul(np.polymul([1 / W[0], 1.0], [1 / W[1], 1.0]), [1 / W[2], 1.0]))
FC = 1 / (2 * math.pi * 1e3 * 100e-9)                           # 1.592 kHz
F0 = 1 / (2 * math.pi * math.sqrt(1e-3 * 100e-9))               # 15.92 kHz
FREQS = [10.0 ** (2 + i / 20) for i in range(101)]              # 100 Hz to 10 MHz, 20 per decade


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
    QApplication.processEvents()
    return p


def names(plot):
    return plot.marker_layer.names()


def placed(plot):
    return {p.marker.name: p for p in plot.placed()}


def tick(plot, *kinds, on=True):
    for k in kinds:
        plot.set_marker_kind(k, on)


# ---------------------------------------------------------------------- the menu and the automatic markers
def test_no_marker_until_one_is_switched_on(plot):
    plot.set_points(sweep())
    assert names(plot) == [] and plot.marker_kinds() == [] and plot.placed() == []
    assert list(KINDS) == ["cutoff", "peak", "notch", "margins"]


def test_cutoff_marker_follows_its_tick(plot):
    plot.set_points(sweep())
    tick(plot, "cutoff")
    assert names(plot) == ["fc"] and plot.marker_kinds() == ["cutoff"]
    p = placed(plot)["fc"]
    assert p.marker.freq == pytest.approx(FC, rel=0.02)
    assert p.y_gain == pytest.approx(-3.0, abs=0.05) and p.y_phase == pytest.approx(-45.0, abs=1.0)
    assert p.text.startswith("fc 1.") and "kHz" in p.text and "dB" in p.text and p.text.endswith("°")
    it = plot.marker_layer.items("fc")
    assert it.host == 0 and it.text.toPlainText() == p.text
    for line in it.lines:                                        # a line through both plots, at log10 of the frequency
        assert line.value() == pytest.approx(math.log10(p.marker.freq)) and not line.movable
    assert it.dots[0].getData()[0][0] == pytest.approx(math.log10(p.marker.freq))
    assert it.dots[0].getData()[1][0] == pytest.approx(p.y_gain)
    assert it.dots[1].getData()[1][0] == pytest.approx(p.y_phase)
    tick(plot, "cutoff", on=False)
    assert names(plot) == [] and plot.marker_kinds() == []


def test_peak_edges_and_notch(plot):
    plot.set_points(sweep(BPF))
    tick(plot, "cutoff", "peak", "notch")
    assert names(plot) == ["fL", "fH", "pk"]                     # a band-pass has no notch: switched on, not drawn
    assert [p.marker.name for p in plot.placed()] == ["fL", "fH", "pk", "nt"]
    assert placed(plot)["pk"].marker.freq == pytest.approx(F0, rel=0.01)
    assert "\nBW " in placed(plot)["fH"].text and " Q " in placed(plot)["fH"].text
    plot.set_points(sweep(NOTCH))
    assert names(plot) == ["fc", "nt"]                           # one edge of the notch is 3 dB down from the flat part
    assert placed(plot)["nt"].marker.freq == pytest.approx(F0, rel=0.03)


def test_margins_sit_on_their_own_plots(plot):
    plot.set_points(sweep(LOOP))
    tick(plot, "margins")
    assert names(plot) == ["GM", "PM"]
    gm, pm = placed(plot)["GM"], placed(plot)["PM"]
    assert gm.text.startswith("GM ") and " dB at " in gm.text and pm.text.startswith("PM ") and "° at " in pm.text
    assert gm.y_phase is None and gm.y_gain == pytest.approx(-gm.marker.margin)
    assert pm.y_gain is None and pm.y_phase == pytest.approx(pm.marker.margin - 180.0)
    layer = plot.marker_layer
    assert layer.items("GM").host == 0 and layer.items("PM").host == 1
    assert len(layer.items("GM").dots[1].getData()[0]) == 0 and len(layer.items("PM").dots[0].getData()[0]) == 0
    assert 30.0 < pm.marker.margin < 60.0 and 15.0 < gm.marker.margin < 25.0


def test_set_marker_kinds_ticks_the_menu(plot):
    plot.set_points(sweep(BPF))
    plot.set_marker_kinds(["peak", "cutoff", "bogus"])
    assert plot.marker_kinds() == ["cutoff", "peak"]
    plot.set_marker_kinds([])
    assert plot.marker_kinds() == [] and names(plot) == []


# ---------------------------------------------------------------------- which trace
def test_markers_on_another_trace(plot):
    plot.set_span_hint(100.0, 1e7)
    plot.set_points(sweep())
    th = plot.set.add_theory(BPF)
    plot.traces_changed()
    tick(plot, "peak", "cutoff")
    assert names(plot) == ["fc"]                                 # the live sweep is the RC low-pass
    plot.set_marker_trace(th.id)
    assert plot.markers.trace_id == th.id and names(plot) == ["fL", "fH", "pk"]
    plot.set.set_visible(th.id, False)
    plot.traces_changed()
    assert names(plot) == []                                     # a hidden trace has no markers
    plot.set.set_visible(th.id, True)
    plot.set.remove(th.id)
    plot.traces_changed()
    assert plot.markers.trace_id == plot.set.live.id and names(plot) == ["fc"]


def test_markers_measure_the_difference_in_relative_view(plot):
    plot.set_points(sweep(scale=0.5))
    th = plot.set.add_theory(RC)
    plot.set.set_reference(th.id)
    plot.traces_changed()
    tick(plot, "cutoff", "margins")
    plot.add_marker(1000.0)
    assert [p.marker.name for p in plot.placed()] == ["fc", "M1"]            # no margins in the relative display
    assert names(plot) == ["M1"]                                 # a flat difference has no cut-off
    assert placed(plot)["M1"].y_gain == pytest.approx(-6.02, abs=0.01)
    assert placed(plot)["M1"].y_phase == pytest.approx(0.0, abs=0.01)


def test_no_markers_on_a_trace_that_is_not_drawn(plot):
    """Review focus: Voltage on a theory curve or on a file with no voltage columns."""
    plot.set_span_hint(100.0, 1e7)
    plot.set_points(sweep())
    th = plot.set.add_theory(BPF)
    f = plot.set.add_file(SweepResult({}, [replace(p, vdut_amp=float("nan")) for p in sweep(BPF)], {}), "old.csv")
    plot.traces_changed()
    tick(plot, "peak")
    plot.add_marker(1000.0)
    for trace in (th, f):
        plot.set_marker_trace(trace.id)
        plot.set_unit("db")
        assert names(plot) == ["pk", "M1"]
        plot.set_unit("v")
        assert names(plot) == [] and plot.placed() == []


# ---------------------------------------------------------------------- units, phase, axis
def test_marker_values_in_the_three_units(plot):
    plot.set_points(sweep())
    tick(plot, "cutoff")
    db = placed(plot)["fc"]
    plot.set_unit("pct")
    pct = placed(plot)["fc"]
    assert pct.y_gain == pytest.approx(100 * 10 ** (db.y_gain / 20)) and " %" in pct.text and "dB" not in pct.text
    plot.set_unit("v")
    v = placed(plot)["fc"]
    assert v.marker.freq == pytest.approx(db.marker.freq)        # the rule works on the gain, also in Voltage
    assert v.y_gain == pytest.approx(abs(RC.h(v.marker.freq)), rel=0.01) and "Vpp" in v.text       # 2 x 0.5 x |H|


def test_marker_phase_follows_the_unwrap_box(plot):
    plot.set_points(sweep(LOOP))
    plot.add_marker(50e3)                                        # the loop's phase is about -195 degrees there
    assert placed(plot)["M1"].y_phase == pytest.approx(164.8, abs=1.0) and "+16" in placed(plot)["M1"].text
    plot.set_unwrap(True)
    assert placed(plot)["M1"].y_phase == pytest.approx(-195.2, abs=1.0) and "-19" in placed(plot)["M1"].text
    line_y = plot.items(plot.set.live).phase_line.getData()[1]
    i = int(np.argmin(np.abs(np.array(FREQS) - 50e3)))
    assert placed(plot)["M1"].y_phase == pytest.approx(float(line_y[i]), abs=3.0)        # on the drawn curve


def test_markers_without_phase(plot):
    """Review focus: a magnitude-only measurement has no phase plot."""
    plot.set_points(sweep(LOOP))
    plot.set_has_phase(False)
    tick(plot, "cutoff", "margins")
    plot.add_marker(1000.0)
    assert names(plot) == ["fc", "M1"]
    assert all(p.y_phase is None and "°" not in p.text for p in plot.placed())
    assert all(plot.marker_layer.items(n).host == 0 for n in names(plot))


def test_markers_on_a_linear_frequency_axis(plot):
    """Review focus: sweep type Linear."""
    plot.set_log_x(False)
    plot.set_points(sweep())
    tick(plot, "cutoff")
    f = placed(plot)["fc"].marker.freq
    it = plot.marker_layer.items("fc")
    assert it.lines[0].value() == pytest.approx(f) and it.dots[0].getData()[0][0] == pytest.approx(f)
    n = plot.add_marker()
    (x0, x1), _g, _p = plot.view_ranges()
    assert n == 1 and x0 < plot.markers.user[1] < x1 and plot.markers.user[1] > 0
    plot.set_log_x(True)
    assert plot.marker_layer.items("fc").lines[0].value() == pytest.approx(math.log10(f))


def test_a_flagged_point_shows_in_the_label(plot):
    pts = sweep()
    i = next(k for k, p in enumerate(pts) if p.freq_hz > FC)
    pts[i].flags |= Flag.LOW_SNR
    plot.set_points(pts)
    tick(plot, "cutoff")
    assert placed(plot)["fc"].text.endswith("(flagged)")
    pts[i].flags = Flag.PREVIEW                                  # a quiet flag does not count
    plot.set_points(pts)
    assert "(flagged)" not in placed(plot)["fc"].text


# ---------------------------------------------------------------------- user markers
def test_add_move_and_remove_user_markers(plot):
    plot.set_points(sweep())
    assert plot.add_marker(1000.0) == 1 and plot.add_marker(5000.0) == 2
    assert names(plot) == ["M1", "M2"]
    p = placed(plot)["M1"]
    h = RC.h(1000.0)
    assert p.marker.freq == 1000.0 and p.y_gain == pytest.approx(20 * math.log10(abs(h)), abs=0.02)
    assert p.text.startswith("M1 1 kHz  ") and p.y_phase == pytest.approx(math.degrees(cmath.phase(h)), abs=0.2)
    it = plot.marker_layer.items("M1")
    assert all(line.movable for line in it.lines)
    plot.move_marker(1, 2500.0)
    assert placed(plot)["M1"].marker.freq == 2500.0
    assert all(line.value() == pytest.approx(math.log10(2500.0)) for line in it.lines)
    plot.move_marker(1, -5.0)                                    # an impossible frequency is ignored
    assert plot.markers.user[1] == 2500.0
    plot.remove_marker(1)
    assert names(plot) == ["M2"]
    assert plot.add_marker(100e3) == 1                           # the lowest free number
    plot.clear_markers()
    assert names(plot) == [] and plot.markers.user == {}


def test_dragging_a_marker_line_moves_the_marker(plot):
    plot.set_points(sweep())
    plot.add_marker(1000.0)
    gain_line, phase_line = plot.marker_layer.items("M1").lines
    gain_line.setValue(math.log10(5000.0))
    gain_line.sigDragged.emit(gain_line)                         # what pyqtgraph sends while the mouse drags it
    assert plot.markers.user[1] == pytest.approx(5000.0)
    assert phase_line.value() == pytest.approx(math.log10(5000.0))           # the other plot's line follows
    assert placed(plot)["M1"].text.startswith("M1 5 kHz")
    assert plot.marker_layer.items("M1").lines[0] is gain_line   # the dragged line was not rebuilt


def test_at_most_eight_user_markers(plot):
    plot.set_points(sweep())
    assert [plot.add_marker(1000.0 * k) for k in range(1, MAX_USER + 1)] == list(range(1, MAX_USER + 1))
    assert not plot.can_add_marker()
    assert plot.add_marker(123.0) is None and len(names(plot)) == MAX_USER
    plot.remove_marker(4)
    assert plot.can_add_marker()


def test_add_marker_without_a_frequency_lands_in_the_view(plot):
    plot.set_points(sweep())
    plot.add_marker()
    (x0, x1), _g, _p = plot.view_ranges()
    assert math.log10(plot.markers.user[1]) == pytest.approx((x0 + x1) / 2)
    plot.clear_markers()
    assert plot.markers.user == {}


def test_user_marker_outside_the_trace_keeps_its_line(plot):
    plot.set_points(sweep())
    plot.add_marker(5e7)
    p = placed(plot)["M1"]
    assert p.text == "M1 50 MHz  outside the trace" and p.y_gain is None and p.y_phase is None
    it = plot.marker_layer.items("M1")
    assert it.lines[0].value() == pytest.approx(math.log10(5e7)) and len(it.dots[0].getData()[0]) == 0


def test_markers_follow_a_running_sweep(plot):
    """Review focus: a new sweep empties the live trace and fills it point by point."""
    plot.set_points(sweep())
    tick(plot, "cutoff", "peak", "notch", "margins")
    plot.add_marker(1000.0)
    plot.clear()                                                 # Start: the live trace is emptied
    assert names(plot) == [] and plot.markers.user == {1: 1000.0}
    seen = []
    for p in sweep():
        plot.add_point(p)
        seen.append(tuple(names(plot)))
    assert seen[0] == ("M1",) and seen[-1] == ("fc", "M1")       # M1 waits outside the trace; no peak, notch or margin
    assert set(seen) == {("M1",), ("fc", "M1")} and seen.index(("fc", "M1")) > 10        # the cut-off appears once the curve has fallen


# ---------------------------------------------------------------------- layout
def test_labels_do_not_overlap(plot):
    plot.set_points(sweep())
    plot.add_marker(1000.0), plot.add_marker(1010.0), plot.add_marker(1020.0)
    QApplication.processEvents()
    plot.refresh()
    rects = [plot.marker_layer.label_rect(n) for n in ("M1", "M2", "M3")]
    assert all(r is not None and r.width() > 10 for r in rects)
    assert not any(a.intersects(b) for i, a in enumerate(rects) for b in rects[i + 1:])


def test_fit_view_ignores_the_markers(plot):
    plot.set_points(sweep())
    before_data, before_view = plot.data_ranges(), plot.view_ranges()
    tick(plot, "cutoff")
    plot.add_marker(5e9)                                         # far beyond the data
    plot.fit_view()
    assert plot.data_ranges() == before_data
    assert np.allclose(np.ravel(plot.view_ranges()), np.ravel(before_view))


def test_marker_items_use_the_marker_colour_and_stay_below_the_live_points(plot):
    plot.set_points(sweep())
    tick(plot, "cutoff")
    it = plot.marker_layer.items("fc")
    assert it.lines[0].pen.color().name() == theme.marker_hex(theme.MARKER_DEFAULTS["fc"])
    assert it.text.color.name() == theme.MARK_INK and theme.MARK_INK not in theme.SERIES
    live = plot.items(plot.set.live)
    assert all(item.zValue() < live.gain_ok.zValue() for item in it.lines + it.dots + [it.text])


# ---------------------------------------------------------------------- right-click, typed frequency, reference, copy
def test_right_click_on_the_plot_adds_a_marker_there(plot):
    plot.set_points(sweep())
    menu = plot.context_menu(2000.0)
    assert [a.text() for a in menu.actions()] == ["Add marker here"] and menu.toolTipsVisible()
    menu.actions()[0].trigger()
    assert plot.markers.user == {1: 2000.0}
    for k in range(MAX_USER - 1):
        plot.add_marker(100.0 * (k + 1))
    assert not plot.context_menu(2000.0).actions()[0].isEnabled()            # the limit


def test_right_click_on_a_user_marker(plot):
    plot.set_points(sweep())
    plot.add_marker(1000.0), plot.add_marker(10000.0)
    menu = plot.context_menu(1000.0, 1)
    assert [a.text() for a in menu.actions()] == ["Set frequency…", "Reference marker", "Colour", "Remove"]
    ref = menu.actions()[1]
    assert ref.isCheckable() and not ref.isChecked()
    ref.trigger()
    assert plot.markers.ref == 1 and plot.context_menu(1000.0, 1).actions()[1].isChecked()
    assert placed(plot)["M1"].text.endswith("(ref)")
    second = placed(plot)["M2"].text.split("\n")[1]
    assert second.startswith("Δ M1  ×10  ") and second.endswith("dB/dec")
    plot.context_menu(1000.0, 1).actions()[3].trigger()          # Remove
    assert names(plot) == ["M2"] and plot.markers.ref is None and "\n" not in placed(plot)["M2"].text


def test_the_layer_finds_the_marker_under_the_mouse(plot):
    plot.set_points(sweep())
    plot.add_marker(1000.0)
    QApplication.processEvents()
    vb = plot.gain_plot.getPlotItem().vb
    from PySide6.QtCore import QPointF
    on = vb.mapViewToScene(QPointF(math.log10(1000.0), -10.0))
    off = vb.mapViewToScene(QPointF(math.log10(30000.0), -10.0))
    assert plot.marker_layer.user_at(plot.gain_plot, on) == 1
    assert plot.marker_layer.user_at(plot.gain_plot, off) is None
    plot.set_marker_kind("cutoff", True)                         # an automatic marker has no menu of its own
    fc = vb.mapViewToScene(QPointF(math.log10(placed(plot)["fc"].marker.freq), -10.0))
    assert plot.marker_layer.user_at(plot.gain_plot, fc) is None


def test_typed_frequency(plot):
    plot.set_points(sweep())
    plot.add_marker(1000.0)
    assert plot.set_marker_frequency(1, "2.5k") and plot.markers.user[1] == 2500.0
    assert plot.set_marker_frequency(1, "1 MHz") and plot.markers.user[1] == 1e6
    for bad in ("", "abc", "-5", "0", "1x"):
        assert not plot.set_marker_frequency(1, bad)
    assert plot.markers.user[1] == 1e6 and placed(plot)["M1"].text.startswith("M1 1 MHz")
    assert not plot.set_marker_frequency(7, "1k")                # no such marker


def test_copy_marker_values(plot):
    plot.set_points(sweep())
    tick(plot, "cutoff", "peak")
    plot.add_marker(1000.0)
    text = plot.marker_text()
    rows = [r.split("\t") for r in text.splitlines()]
    assert rows[0] == ["Markers on: Sweep"] and [r[0] for r in rows[2:]] == ["fc", "pk", "M1"]
    assert rows[3] == ["pk", "", "", "", "none"] and float(rows[4][1]) == 1000.0
    assert float(rows[2][3]) == pytest.approx(-45.0, abs=1.0)
    plot.copy_markers()
    assert QApplication.clipboard().text() == text
    th = plot.set.add_theory(RC)
    plot.set.set_reference(th.id)
    plot.traces_changed()
    assert plot.marker_text().splitlines()[0] == "Markers on: Sweep, relative to " + th.name


def test_copied_phase_is_the_phase_shown(plot):
    plot.set_points(sweep(LOOP))
    plot.add_marker(50e3)
    wrapped = float(plot.marker_text().splitlines()[2].split("\t")[3])
    plot.set_unwrap(True)
    unwrapped = float(plot.marker_text().splitlines()[2].split("\t")[3])
    assert wrapped == pytest.approx(164.8, abs=1.0) and unwrapped == pytest.approx(wrapped - 360.0, abs=0.02)


# ---------------------------------------------------------------------- the main window: export and settings
from bodeplot.gui.main_window import MainWindow
from bodeplot.io.settings import AppSettings
from bodeplot.models import EngineState, SweepConfig, SweepType

SIM = {"preset": "rc_lpf", "params": {"r": 1e3, "c": 100e-9}, "noise_vrms": 2e-4, "latency_ms": 0.0}


def window(qtbot, settings):
    w = MainWindow(simulate=True, settings=settings, sim_seed=7)
    w.interactive = False
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    w = window(qtbot, AppSettings(simulate=True, sim=dict(SIM)))
    yield w
    w.close()


def run_sweep(win, qtbot, lo=100.0, hi=1e5, ppd=10):
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


def test_export_markers_is_what_the_plot_shows(plot):
    plot.set_points(sweep(LOOP))
    tick(plot, "cutoff", "peak", "margins")
    plot.add_marker(1000.0), plot.add_marker(5e9)
    marks = plot.export_markers()
    shown = {p.text: p for p in plot.placed() if p.marker.found}
    assert [m.text for m in marks] == list(shown) and len(marks) == len(names(plot))
    for m in marks:
        p = shown[m.text]
        assert (m.freq, m.y_gain, m.y_phase) == (p.marker.freq, p.y_gain, p.y_phase)
        assert m.label_on == ("phase" if p.marker.kind == "pm" else "gain")


def test_a_swept_cutoff_and_the_image_with_markers(win, qtbot, tmp_path, monkeypatch):
    from bodeplot.io import export_image
    run_sweep(win, qtbot)
    win.plot.set_marker_kind("cutoff", True)
    win.plot.add_marker(1000.0)
    fc = {p.marker.name: p for p in win.plot.placed()}["fc"].marker.freq
    assert fc == pytest.approx(FC, rel=0.03)                     # the simulated RC low-pass, with its noise
    seen = {}
    real = export_image.write_image

    def spy(path, result, opts=None, series=None, labels=None, markers=None):
        seen.update(markers=markers)
        return real(path, result, opts, series, labels, markers)
    monkeypatch.setattr(export_image, "write_image", spy)
    for name in ("m.png", "m.svg", "m.pdf"):
        assert win.export(tmp_path / name).stat().st_size > 500
    assert [m.text.split()[0] for m in seen["markers"]] == ["fc", "M1"]
    assert export_image.PRINT_MARKER.lower() in (tmp_path / "m.svg").read_text(encoding="utf-8").lower()


def test_marker_ticks_survive_a_restart(win, qtbot):
    assert win.plot.marker_kinds() == []                         # a first start: all four off
    win.plot.set_marker_kind("peak", True)
    win.plot.set_marker_kind("cutoff", True)
    win.plot.add_marker(1000.0)
    win._save_ui_state()
    assert win.settings.markers == ["cutoff", "peak"]
    again = window(qtbot, AppSettings.from_dict(win.settings.to_dict()))
    try:
        assert again.plot.marker_kinds() == ["cutoff", "peak"]
        assert again.plot.markers.user == {}                     # the user's markers are not kept
    finally:
        again.close()


def test_a_label_stands_on_the_free_side_of_the_curve(plot):
    """Found in the offscreen render: a label to the right of a rising curve sat on the curve."""
    from PySide6.QtCore import QPointF
    plot.set_points(sweep(BPF))
    tick(plot, "cutoff", "peak")
    QApplication.processEvents()
    plot.refresh()
    p = placed(plot)
    assert p["fL"].left and not p["fH"].left and not p["pk"].left
    vb = plot.gain_plot.getPlotItem().vb
    for name in ("fL", "fH"):
        dot_x = vb.mapViewToScene(QPointF(math.log10(p[name].marker.freq), p[name].y_gain)).x()
        rect = plot.marker_layer.label_rect(name)
        assert (rect.right() < dot_x) == p[name].left and (rect.left() > dot_x) == (not p[name].left)
    assert [m.left for m in plot.export_markers()] == [x.left for x in plot.placed() if x.marker.found]
    assert plot.marker_layer.items("fL").text.fill.color().alpha() < 255         # the curve shows through a label


def test_no_phase_anywhere_in_a_magnitude_only_measurement(plot):
    """Review finding: the reference marker's difference line and the copied table still had a phase."""
    plot.set_points(sweep())
    plot.set_has_phase(False)
    plot.add_marker(1000.0), plot.add_marker(10000.0)
    plot.toggle_reference_marker(1)
    assert "°" not in placed(plot)["M2"].text and "dB/dec" in placed(plot)["M2"].text
    rows = [r.split("\t") for r in plot.marker_text().splitlines()[2:]]
    assert [r[3] for r in rows] == ["", ""] and "deg" not in plot.marker_text().split("\n", 2)[2]


def test_a_refused_drag_puts_the_line_back(plot):
    """Review finding: on a linear axis a marker dragged to zero or below stayed torn: one
    line at the impossible place, the other and the label at the old frequency."""
    plot.set_log_x(False)
    plot.set_points(sweep())
    plot.add_marker(1000.0)
    gain_line, phase_line = plot.marker_layer.items("M1").lines
    gain_line.setValue(-500.0)
    gain_line.sigDragged.emit(gain_line)
    assert plot.markers.user[1] == 1000.0
    assert gain_line.value() == pytest.approx(1000.0) and phase_line.value() == pytest.approx(1000.0)
