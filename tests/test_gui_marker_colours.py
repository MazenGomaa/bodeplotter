"""A colour per marker, chosen from a fixed palette of twenty (user's request of 2026-10-07):
the palette itself, the defaults, the picker, what is drawn, what is stored (offscreen)."""
import cmath
import math

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication

from bodeplot.gui import theme
from bodeplot.gui.bode_plot import BodePlot
from bodeplot.gui.color_menu import palette_menu
from bodeplot.gui.main_window import MainWindow
from bodeplot.gui.markers_panel import MarkersPanel
from bodeplot.io import export_image
from bodeplot.io.settings import AppSettings
from bodeplot.measure.theory import TransferFunction
from bodeplot.models import Flag, PointResult
from bodeplot.traces import TraceSet

BPF = TransferFunction.rlc_bpf(100.0, 1e-3, 100e-9)
FREQS = [10.0 ** (2 + i / 20) for i in range(101)]
PALETTE = dict(theme.MARKER_PALETTE)


def point(f, h):
    return PointResult(freq_hz=f, h=h, gain_db=20 * math.log10(abs(h)), phase_deg=math.degrees(cmath.phase(h)),
                       vref_amp=0.5, vdut_amp=0.5 * abs(h), vdiv_ref=0.02, vdiv_dut=0.02, timebase=1e-3, n_avg=1,
                       snr_ref_db=50.0, snr_dut_db=50.0, flags=Flag.NONE, duration_s=0.1)


@pytest.fixture
def plot(qtbot):
    p = BodePlot(TraceSet())
    qtbot.addWidget(p)
    p.resize(900, 600)
    p.show()
    p.set_points([point(f, BPF.h(f)) for f in FREQS])
    QApplication.processEvents()
    return p


@pytest.fixture
def panel(qtbot, plot):
    w = MarkersPanel(plot)
    qtbot.addWidget(w)
    w.show()
    return w


def line_colour(plot, name):
    return plot.marker_layer.items(name).lines[0].pen.color().name()


# ---------------------------------------------------------------------- the palette
def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(h):
    return [_lin(int(h[i:i + 2], 16)) for i in (1, 3, 5)]


def contrast(a, b):
    la, lb = sorted((0.2126 * r + 0.7152 * g + 0.0722 * b_ for r, g, b_ in (_rgb(a), _rgb(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def oklab(h):
    r, g, b = _rgb(h)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def test_the_palette_has_twenty_colours_that_read_on_the_plot():
    assert len(theme.MARKER_PALETTE) == 20 and len(PALETTE) == 20 and len(set(PALETTE.values())) == 20
    assert theme.MARKER_PALETTE[0] == ("Grey", theme.MARK_INK)             # the first one is the neutral default
    for name, colour in theme.MARKER_PALETTE:
        assert contrast(colour, theme.SURFACE) >= 4.5, name                # a thin dashed line must stay visible
    closest = min((100 * math.dist(oklab(a), oklab(b)), x, y) for i, (x, a) in enumerate(theme.MARKER_PALETTE)
                  for y, b in theme.MARKER_PALETTE[i + 1:])
    assert closest[0] >= 5.0, closest                                       # no two of them are the same to the eye
    assert theme.marker_hex("Sky") == PALETTE["Sky"] and theme.marker_hex("no such colour") == theme.MARK_INK


def test_the_image_has_a_print_colour_for_each():
    assert list(export_image.PRINT_MARKERS) == [name for name, _c in theme.MARKER_PALETTE]
    assert export_image.PRINT_MARKERS["Grey"] == export_image.PRINT_MARKER
    for name, colour in export_image.PRINT_MARKERS.items():
        assert contrast(colour, "#ffffff") >= 4.3, name


def test_default_colours():
    d = theme.MARKER_DEFAULTS
    users = [d["M%d" % k] for k in range(1, 9)]
    assert len(set(users)) == 8 and "Grey" not in users                     # two of the user's markers never look alike
    assert d["fc"] == d["fL"] == d["fH"]                                    # -3 dB is one thing
    assert len({d["fc"], d["pk"], d["nt"], "Grey"}) == 4                    # -3 dB, peak and notch each have their own
    assert not set(users) & {d["fc"], d["pk"], d["nt"]}
    assert "GM" not in d and "PM" not in d                                  # the margins stay neutral
    assert set(d.values()) <= set(PALETTE)


# ---------------------------------------------------------------------- what is drawn
def test_markers_are_drawn_in_their_default_colours_and_the_text_stays_plain(plot):
    plot.set_marker_kinds(["cutoff", "peak", "margins"])
    plot.add_marker(1000.0), plot.add_marker(5000.0)
    d = theme.MARKER_DEFAULTS
    for name in ("fL", "fH", "pk", "M1", "M2"):
        it = plot.marker_layer.items(name)
        want = PALETTE[d[name]]
        assert it.lines[0].pen.color().name() == want and it.lines[1].pen.color().name() == want, name
        assert it.dots[0].opts["brush"].color().name() == want
        assert it.text.color.name() == theme.MARK_INK                       # coloured text is hard to read: ink only
    assert line_colour(plot, "M1") != line_colour(plot, "M2")
    assert plot.marker_color_of("GM") == "Grey" and plot.marker_colors() == {}


def test_a_marker_takes_the_colour_chosen_for_it(plot):
    plot.set_marker_kinds(["peak"])
    plot.add_marker(1000.0)
    gain_line = plot.marker_layer.items("M1").lines[0]
    assert plot.set_marker_color("M1", "Deep pink")
    assert line_colour(plot, "M1") == PALETTE["Deep pink"] and plot.marker_color_of("M1") == "Deep pink"
    assert plot.marker_layer.items("M1").lines[0] is not gain_line          # redrawn in the new colour
    assert line_colour(plot, "pk") == PALETTE[theme.MARKER_DEFAULTS["pk"]]  # the others keep theirs
    assert plot.marker_colors() == {"M1": "Deep pink"}
    plot.remove_marker(1)
    plot.add_marker(2000.0)
    assert line_colour(plot, "M1") == PALETTE["Deep pink"]                  # the colour belongs to the name
    assert plot.set_marker_color("M1", theme.MARKER_DEFAULTS["M1"]) and plot.marker_colors() == {}
    for marker, colour in (("M1", "Puce"), ("M9", "Sky"), ("zz", "Sky"), ("M1", ""), ("M1", None)):
        assert not plot.set_marker_color(marker, colour)
    assert plot.marker_colors() == {}
    plot.set_marker_colors({"pk": "Teal", "bogus": "Sky", "M2": "nothing", "M3": 7})
    assert plot.marker_colors() == {"pk": "Teal"} and line_colour(plot, "pk") == PALETTE["Teal"]


# ---------------------------------------------------------------------- the picker
def test_the_palette_menu_is_a_grid_of_twenty(qtbot, plot):
    picked = []
    menu = palette_menu(plot, "Sky", picked.append)
    assert list(menu.buttons) == [name for name, _c in theme.MARKER_PALETTE]
    assert [n for n, b in menu.buttons.items() if b.isChecked()] == ["Sky"]
    for name, b in menu.buttons.items():
        assert not b.icon().isNull() and b.toolTip().startswith(name) and len(b.toolTip()) >= 25
    rows = {b.y() for b in menu.buttons.values()}
    menu.buttons["Deep teal"].click()
    assert picked == ["Deep teal"]


def test_every_table_row_has_a_colour_square_that_opens_the_palette(plot, panel):
    assert not hasattr(panel, "color_btn")                                  # one colour for all markers is gone
    plot.set_marker_kinds(["cutoff", "peak", "notch"])
    plot.add_marker(1000.0)
    t = panel.table
    names = [t.topLevelItem(i).text(0) for i in range(t.topLevelItemCount())]
    assert names == ["fL", "fH", "pk", "nt", "M1"]
    assert all(not t.topLevelItem(i).icon(0).isNull() for i in range(5))    # also a marker this curve does not have
    assert "colour" in t.toolTip()
    menu = panel.color_menu("nt")
    assert [n for n, b in menu.buttons.items() if b.isChecked()] == [theme.MARKER_DEFAULTS["nt"]]
    menu.buttons["Lime"].click()
    assert plot.marker_color_of("nt") == "Lime"
    panel._item_clicked(t.topLevelItem(4), 0)                               # a click on the square of M1
    assert panel.open_menu is not None and panel.open_menu.marker == "M1"
    panel.open_menu.buttons["Deep red"].click()
    assert line_colour(plot, "M1") == PALETTE["Deep red"]
    panel.open_menu = None
    panel._item_clicked(t.topLevelItem(4), 2)                               # a click on a number opens nothing
    assert panel.open_menu is None


def test_right_click_on_a_user_marker_offers_the_palette(plot):
    plot.add_marker(1000.0)
    menu = plot.context_menu(1000.0, 1)
    assert [a.text() for a in menu.actions()] == ["Set frequency…", "Reference marker", "Colour", "Remove"]
    sub = menu.actions()[2].menu()
    assert len(menu.actions()[2].toolTip()) >= 25 and sub.marker == "M1"
    sub.buttons["Violet"].click()
    assert plot.marker_color_of("M1") == "Violet"


# ---------------------------------------------------------------------- stored, and in the image
def test_marker_colours_survive_a_restart(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("BODEPLOT_CONFIG_DIR", str(tmp_path / "cfg"))
    win = MainWindow(simulate=True, settings=AppSettings(simulate=True), sim_seed=7)
    win.interactive = False
    qtbot.addWidget(win)
    try:
        win.plot.set_marker_color("pk", "Teal")
        win.plot.set_marker_color("M3", "White")
        win._save_ui_state()
        assert win.settings.marker_colors == {"pk": "Teal", "M3": "White"}
        again = MainWindow(simulate=True, settings=AppSettings.from_dict(win.settings.to_dict()), sim_seed=7)
        again.interactive = False
        qtbot.addWidget(again)
        try:
            assert again.plot.marker_colors() == {"pk": "Teal", "M3": "White"}
        finally:
            again.close()
    finally:
        win.close()
    assert AppSettings().marker_colors == {}
    s = AppSettings.from_dict({"marker_colors": {"pk": "Teal", "M1": 5, 7: "Sky"}, "marker_color": "#ff8800"})
    assert s.marker_colors == {"pk": "Teal"} and not hasattr(s, "marker_color")     # the single colour of a day is gone
    assert AppSettings.from_dict({"marker_colors": ["pk"]}).marker_colors == {}


def test_the_image_draws_each_marker_in_its_print_colour(plot, tmp_path):
    from bodeplot.models import SweepResult
    plot.set_marker_kinds(["peak"])
    plot.add_marker(1000.0)
    plot.set_marker_color("M1", "Deep pink")
    marks = plot.export_markers()
    assert [(m.text.split()[0], m.color) for m in marks] == [("pk", theme.MARKER_DEFAULTS["pk"]), ("M1", "Deep pink")]
    series, labels = plot.export_series()
    svg = export_image.write_image(tmp_path / "c.svg", SweepResult({}, [], {}), export_image.ImageOptions(),
                                   series, labels, markers=marks).read_text(encoding="utf-8").lower()
    assert export_image.PRINT_MARKERS["Deep pink"] in svg and export_image.PRINT_MARKERS[theme.MARKER_DEFAULTS["pk"]] in svg
    assert export_image.PRINT_MARKER in svg                                 # the label text stays dark grey
    odd = export_image.ImageMarker(1000.0, "M1 1 kHz", -3.0, -45.0, color="no such colour")
    assert export_image.write_image(tmp_path / "odd.png", SweepResult({}, [], {}), export_image.ImageOptions(),
                                    series, labels, markers=[odd]).stat().st_size > 500


def test_a_marker_line_is_not_hidden_by_the_trace_it_runs_along(plot):
    """User report: the notch marker had one colour in the gain plot and another in the phase
    plot. At a notch the phase jumps, the trace runs straight up along the marker's line, and
    the trace was drawn over the marker: there the line looked like the trace."""
    plot.set_marker_kinds(["peak"])
    live = plot.items(plot.set.live)
    it = plot.marker_layer.items("pk")
    for k, trace_line in enumerate((live.gain_line, live.phase_line)):
        assert it.lines[k].zValue() > trace_line.zValue() and it.dots[k].zValue() > trace_line.zValue()
    assert all(item.zValue() < live.gain_ok.zValue() for item in it.lines + it.dots + [it.text])   # a point keeps its click
