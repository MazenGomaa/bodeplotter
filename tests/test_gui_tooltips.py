"""Design rule (user, 2026-10-07): every option explains itself in a tooltip that appears
after the mouse has rested on it for 3 seconds. These tests keep the rule: a new option
without an explanation fails here."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton,
                               QStyle, QToolButton)

from bodeplot.gui import theme
from bodeplot.gui.main_window import MainWindow
from bodeplot.io.settings import AppSettings

MIN_LENGTH = 25         # an explanation, not a repeat of the label


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    w = MainWindow(simulate=True, settings=AppSettings(simulate=True), sim_seed=7)
    w.interactive = False
    qtbot.addWidget(w)
    w.show()
    yield w
    w.close()


def explains(tip: str, label: str = "") -> bool:
    tip = (tip or "").strip()
    return len(tip) >= MIN_LENGTH and tip != label.strip()


def test_tooltips_appear_after_three_seconds(win):
    assert theme.TOOLTIP_DELAY_MS == 3000
    assert QApplication.style().styleHint(QStyle.SH_ToolTip_WakeUpDelay) == 3000


def test_every_configuration_option_explains_itself(win):
    body = win.config.widget()
    fields = body.findChildren(QAbstractSpinBox) + body.findChildren(QComboBox) + body.findChildren(QCheckBox)
    assert len(fields) > 15
    silent = [w.objectName() or type(w).__name__ + ":" + (w.text() if hasattr(w, "text") else "")
              for w in fields if not explains(w.toolTip())]
    assert not silent, "configuration options without an explanation: %s" % silent
    # the label of a field carries the same explanation: the mouse may rest on either
    for form in body.findChildren(QFormLayout):
        for row in range(form.rowCount()):
            label = form.itemAt(row, QFormLayout.LabelRole)
            field = form.itemAt(row, QFormLayout.FieldRole)
            if label is not None and field is not None and label.widget() is not None:
                assert label.widget().toolTip() == field.widget().toolTip(), label.widget().text()


def test_every_toolbar_item_explains_itself(win):
    silent = []
    for action in win.toolbar.actions():
        if action.isSeparator():
            continue
        widget = win.toolbar.widgetForAction(action)
        if isinstance(widget, QLabel):                         # " Mode ", " Preset ": captions of the box next to them
            continue
        if isinstance(widget, (QComboBox,)) or (isinstance(widget, QToolButton) and widget.menu() is not None):
            tip, label = widget.toolTip(), ""
        else:
            tip, label = action.toolTip(), action.text()
        if not explains(tip, label):
            silent.append(action.text() or type(widget).__name__)
    assert not silent, "toolbar items without an explanation: %s" % silent
    for menu_action in win.menuBar().actions():                 # the same texts show in the menus
        assert menu_action.menu().toolTipsVisible(), menu_action.text()
    assert win.export_menu.toolTipsVisible()


def test_plot_trace_and_log_options_explain_themselves(win):
    plot, panel, log = win.plot, win.traces_panel, win.status_log
    named = {"Unwrap phase": plot.unwrap_box, "Fit view": plot.fit_btn, "Vertical": plot.unit_box,
             "Difference to trace": plot.ref_box, "trace list": panel.tree, "Load CSV": panel.load_btn,
             "Add theory": panel.theory_btn, "Keep sweep": panel.keep_btn, "Remove": panel.remove_btn,
             "Copy": log.copy_btn, "Clear": log.clear_btn}
    silent = [name for name, w in named.items() if not explains(w.toolTip(), name)]
    assert not silent, "options without an explanation: %s" % silent
    # nothing new slipped in without one: every button and box of these three panels is in the list
    for host in (plot, panel, log, win.markers_panel, win.analysis_panel):
        for w in host.findChildren(QPushButton) + host.findChildren(QComboBox) + host.findChildren(QCheckBox):
            assert explains(w.toolTip()), "%s in %s has no explanation" % (
                w.text() if hasattr(w, "text") else type(w).__name__, type(host).__name__)


def _points():
    import cmath
    import math
    from bodeplot.measure.theory import TransferFunction
    from bodeplot.models import Flag, PointResult
    rc = TransferFunction.rc_lpf(1e3, 100e-9)
    for f in (100.0, 1000.0, 10000.0):
        h = rc.h(f)
        yield PointResult(freq_hz=f, h=h, gain_db=20 * math.log10(abs(h)), phase_deg=math.degrees(cmath.phase(h)),
                          vref_amp=0.5, vdut_amp=0.5 * abs(h), vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1,
                          snr_ref_db=50.0, snr_dut_db=50.0, flags=Flag.NONE, duration_s=0.1)


def test_marker_menus_explain_themselves(win):
    plot = win.plot
    win.plot.set_points([p for p in _points()])
    plot.add_marker(1000.0)
    menus = {"plot right-click": plot.context_menu(1000.0)}
    silent = []
    for where, menu in menus.items():
        assert menu.toolTipsVisible(), where
        silent += ["%s > %s" % (where, a.text()) for a in menu.actions()
                   if not a.isSeparator() and not explains(a.toolTip(), a.text())]
    marker_menu = plot.context_menu(1000.0, 1)                   # built after the first one: one context menu at a time
    assert marker_menu.toolTipsVisible()
    silent += ["marker right-click > %s" % a.text() for a in marker_menu.actions() if not explains(a.toolTip(), a.text())]
    assert not silent, "marker menu items without an explanation: %s" % silent
