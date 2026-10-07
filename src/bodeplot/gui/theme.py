"""Dark theme: one place for every colour the app uses.

The values are the dark column of the reference palette from the data-viz method
used for this project (categorical slots, status palette, chart chrome and ink).
That palette is documented as validated against the dark chart surface #1a1a19 for
colour-vision-deficiency separation and contrast; the plots here draw on exactly
that surface, so the published validation applies. The validator script itself
was NOT re-run for this project (it needs Node, which is not installed here).

Rules followed:
  * colour is assigned by job. Series colours identify a trace; status colours
    (good / warning / serious / critical) mean a state and are never used for a series
  * a status colour never carries meaning alone: flagged points also change shape
    (a cross) and name their flags in the tooltip; status text carries a symbol and words
  * text is drawn in ink colours, never in a series colour
  * gain and phase are two plots, never one plot with two y-axes
"""
from __future__ import annotations

# ---- surfaces and ink
PAGE = "#0d0d0d"            # window plane behind the panels
SURFACE = "#1a1a19"         # chart surface and panel background
RAISED = "#242423"          # inputs, buttons, table header
RAISED_HOVER = "#2e2e2c"
BORDER = "#383835"          # baseline / axis line
HAIRLINE = "#2c2c2a"        # gridlines, separators
INK = "#ffffff"
INK_2 = "#c3c2b7"
MUTED = "#898781"           # axis text, disabled text
ACCENT = "#3987e5"          # focus ring, selection (categorical slot 1)
ACCENT_DIM = "#184f95"      # selection background (sequential step 600)

# ---- categorical series, fixed order, never cycled (dark steps)
SERIES = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767")
TRACE = SERIES[0]           # the sweep in the Bode plots
REF = SERIES[0]             # waveform view: reference channel
DUT = SERIES[1]             # waveform view: DUT channel

# ---- status palette (fixed; distinct from the series colours)
GOOD = "#0ca30c"
WARNING = "#fab219"
SERIOUS = "#ec835a"
CRITICAL = "#d03b3b"
FLAGGED = WARNING           # a flagged point: warning colour + cross marker + tooltip text
MARK_INK = INK_2            # the markers of the Bode plot (lines, dots, labels): neutral, never a series colour

# ---- mark sizes (px)
LINE_WIDTH = 2
MARKER = 8
MARKER_FLAGGED = 11
RING = 1.5                  # surface-coloured ring so overlapping markers stay separate


def status_html(kind: str, text: str, bold: bool = False) -> str:
    """Status text: a coloured symbol carries the state, the words stay in ink."""
    color, symbol = {"good": (GOOD, "●"), "warning": (WARNING, "▲"),
                     "serious": (SERIOUS, "▲"), "critical": (CRITICAL, "■"),
                     "idle": (MUTED, "○")}[kind]
    import html
    body = html.escape(text)
    if bold:
        body = "<b>%s</b>" % body
    return '<span style="color:%s">%s</span>&nbsp;%s' % (color, symbol, body)


QSS = f"""
* {{ font-family: "Segoe UI", system-ui, sans-serif; font-size: 9.5pt; }}
QMainWindow, QDialog {{ background: {PAGE}; color: {INK}; }}
QWidget {{ color: {INK}; }}
QToolTip {{ background: {RAISED}; color: {INK}; border: 1px solid {BORDER}; padding: 4px 6px; }}

QMenuBar {{ background: {PAGE}; color: {INK_2}; border-bottom: 1px solid {HAIRLINE}; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {RAISED}; color: {INK}; }}
QMenu {{ background: {SURFACE}; color: {INK}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 22px; border-radius: 3px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::item:disabled {{ color: {MUTED}; }}
QMenu::separator {{ height: 1px; background: {HAIRLINE}; margin: 4px 6px; }}

QToolBar {{ background: {PAGE}; border: none; border-bottom: 1px solid {HAIRLINE}; spacing: 2px; padding: 3px; }}
QToolBar::separator {{ width: 1px; background: {HAIRLINE}; margin: 4px 5px; }}
QToolBar QToolButton {{ background: transparent; color: {INK_2}; border: 1px solid transparent;
                        border-radius: 4px; padding: 4px 9px; }}
QToolBar QToolButton:hover {{ background: {RAISED}; color: {INK}; border-color: {BORDER}; }}
QToolBar QToolButton:pressed {{ background: {ACCENT_DIM}; }}
QToolBar QToolButton:disabled {{ color: #5b5a56; }}
QToolBar QLabel {{ color: {MUTED}; }}

QDockWidget {{ color: {INK_2}; }}
QDockWidget::title {{ background: {PAGE}; padding: 5px 8px; border-bottom: 1px solid {HAIRLINE}; }}
QDockWidget > QWidget {{ background: {SURFACE}; }}
QMainWindow::separator {{ background: {PAGE}; width: 4px; height: 4px; }}
QMainWindow::separator:hover {{ background: {ACCENT_DIM}; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: {SURFACE}; border: none; }}
QGroupBox {{ background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 6px; margin-top: 16px;
             padding: 8px 6px 6px 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {INK_2}; }}
QLabel {{ background: transparent; color: {INK_2}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QListWidget {{
    background: {RAISED}; color: {INK}; border: 1px solid {BORDER}; border-radius: 4px; padding: 3px 6px;
    selection-background-color: {ACCENT_DIM}; selection-color: {INK}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {MUTED}; background: {SURFACE}; border-color: {HAIRLINE}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; color: {INK}; border: 1px solid {BORDER};
                               selection-background-color: {ACCENT_DIM}; outline: 0; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent; border: none; width: 16px; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::down-button:hover {{ background: {RAISED_HOVER}; }}

QCheckBox {{ color: {INK_2}; spacing: 6px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER}; border-radius: 3px;
                        background: {RAISED}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:disabled {{ background: {SURFACE}; border-color: {HAIRLINE}; }}
QCheckBox::indicator:checked:disabled {{ background: {ACCENT_DIM}; border-color: {ACCENT_DIM}; }}

QPushButton {{ background: {RAISED}; color: {INK}; border: 1px solid {BORDER}; border-radius: 4px;
               padding: 5px 14px; }}
QPushButton:hover {{ background: {RAISED_HOVER}; }}
QPushButton:pressed {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}
QPushButton:default {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; border-color: {HAIRLINE}; }}

QTableWidget {{ background: {SURFACE}; alternate-background-color: {SURFACE}; color: {INK};
                gridline-color: {HAIRLINE}; border: 1px solid {HAIRLINE};
                selection-background-color: {ACCENT_DIM}; selection-color: {INK}; }}
QHeaderView::section {{ background: {RAISED}; color: {INK_2}; border: none;
                        border-right: 1px solid {HAIRLINE}; border-bottom: 1px solid {HAIRLINE};
                        padding: 4px 8px; }}
QTableCornerButton::section {{ background: {RAISED}; border: none; }}
QPlainTextEdit {{ background: {SURFACE}; border-color: {HAIRLINE};
                  font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt; }}
QSplitter::handle {{ background: {PAGE}; }}

QScrollBar:vertical {{ background: {SURFACE}; width: 11px; margin: 0; }}
QScrollBar:horizontal {{ background: {SURFACE}; height: 11px; margin: 0; }}
QScrollBar::handle {{ background: {BORDER}; border-radius: 4px; min-width: 24px; min-height: 24px; margin: 2px; }}
QScrollBar::handle:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QStatusBar {{ background: {PAGE}; color: {INK_2}; border-top: 1px solid {HAIRLINE}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {INK_2}; padding: 0 6px; }}
"""


_GLYPH_DIR = None


def _glyph_qss() -> str:
    """Arrow and title-bar glyphs. A stylesheet that restyles combo boxes, spin boxes and
    dock titles loses the native glyphs, and Qt style sheets cannot draw shapes, so small
    images are painted once into a temporary folder and referenced from the sheet."""
    global _GLYPH_DIR
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF

    if _GLYPH_DIR is None:
        d = Path(tempfile.mkdtemp(prefix="bodeplot-theme-"))

        def canvas(w, h):
            pm = QPixmap(w, h)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            return pm, p

        for name, color in (("", INK_2), ("-off", "#5b5a56")):
            for direction, pts in (("down", [(1, 1.5), (9, 1.5), (5, 6)]), ("up", [(1, 6), (9, 6), (5, 1.5)])):
                pm, p = canvas(10, 8)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(color))
                p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
                p.end()
                pm.save(str(d / ("%s%s.png" % (direction, name))))
        pm, p = canvas(12, 12)                          # dock close: a cross
        p.setPen(QPen(QColor(INK_2), 1.4))
        p.drawLine(QPointF(3, 3), QPointF(9, 9))
        p.drawLine(QPointF(9, 3), QPointF(3, 9))
        p.end()
        pm.save(str(d / "close.png"))
        pm, p = canvas(12, 12)                          # dock float: a window outline
        p.setPen(QPen(QColor(INK_2), 1.2))
        p.drawRect(3, 3, 6, 6)
        p.end()
        pm.save(str(d / "float.png"))
        _GLYPH_DIR = d
    u = _GLYPH_DIR.as_posix()
    return f"""
QComboBox::down-arrow {{{{ image: url({u}/down.png); width: 10px; height: 8px; }}}}
QComboBox::down-arrow:disabled {{{{ image: url({u}/down-off.png); }}}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{{{ image: url({u}/up.png); width: 10px; height: 8px; }}}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{{{ image: url({u}/down.png); width: 10px; height: 8px; }}}}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {{{{ image: url({u}/up-off.png); }}}}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{{{ image: url({u}/down-off.png); }}}}
QDockWidget {{{{ titlebar-close-icon: url({u}/close.png); titlebar-normal-icon: url({u}/float.png); }}}}
QDockWidget::close-button, QDockWidget::float-button {{{{ border: 1px solid transparent; border-radius: 3px;
                                                        background: transparent; padding: 1px; }}}}
QDockWidget::close-button:hover, QDockWidget::float-button:hover {{{{ background: {RAISED_HOVER}; }}}}
QToolButton::menu-indicator {{{{ image: url({u}/down.png); subcontrol-position: right center;
                               subcontrol-origin: padding; left: -4px; width: 8px; }}}}
""".replace("{{", "{").replace("}}", "}")


# Design rule (user, 2026-10-07): every option explains itself in a tooltip, and the
# tooltip appears after the mouse has rested on the option for this long. Qt's own delay
# is 0.7 s, which makes the explanations flicker up while the mouse merely passes.
TOOLTIP_DELAY_MS = 3000         # the default; the Settings dialog can change it (set_tooltips)
_style = None                   # the application style; kept so that it is not collected
_tooltip_delay_ms = TOOLTIP_DELAY_MS
_tooltips_on = True
_tip_filter = None
_grid_color = ""                # "" = BORDER; set by the user in the Settings dialog (set_grid_color)


def set_tooltips(enabled: bool, delay_ms: float) -> None:
    """Switch the explanations on or off, and set how long the mouse must rest first."""
    global _tooltips_on, _tooltip_delay_ms
    _tooltips_on, _tooltip_delay_ms = bool(enabled), int(max(0, delay_ms))


def tooltips_enabled() -> bool:
    return _tooltips_on


def tip_filter():
    """The application-wide event filter that swallows tooltips while they are switched off."""
    global _tip_filter
    if _tip_filter is None:
        from PySide6.QtCore import QEvent, QObject

        class TipFilter(QObject):
            def eventFilter(self, obj, event):
                return event.type() == QEvent.ToolTip and not _tooltips_on

        _tip_filter = TipFilter()
    return _tip_filter


def set_grid_color(color: str) -> None:
    """Colour of the plots' grid and axis lines ("#rrggbb"); anything else: the theme's own.
    Call style_plot() on each plot afterwards."""
    import re
    global _grid_color
    _grid_color = color if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) else ""


def _make_style():
    from PySide6.QtWidgets import QProxyStyle, QStyle

    class AppStyle(QProxyStyle):
        """Fusion, with the tooltip delay of the design rule."""

        def styleHint(self, hint, option=None, widget=None, returnData=None):
            if hint == QStyle.SH_ToolTip_WakeUpDelay:
                return _tooltip_delay_ms
            return super().styleHint(hint, option, widget, returnData)

    return AppStyle("Fusion")


def apply(app) -> None:
    """Apply the dark theme to a QApplication and to pyqtgraph. Safe to call twice."""
    import pyqtgraph as pg
    from PySide6.QtGui import QColor, QPalette

    global _style
    _style = _make_style()              # Fusion on every OS, so the stylesheet lands the same
    app.setStyle(_style)
    app.removeEventFilter(tip_filter())
    app.installEventFilter(tip_filter())
    pal = QPalette()
    for role, color in ((QPalette.Window, PAGE), (QPalette.WindowText, INK), (QPalette.Base, RAISED),
                        (QPalette.AlternateBase, SURFACE), (QPalette.Text, INK), (QPalette.Button, RAISED),
                        (QPalette.ButtonText, INK), (QPalette.ToolTipBase, RAISED), (QPalette.ToolTipText, INK),
                        (QPalette.Highlight, ACCENT_DIM), (QPalette.HighlightedText, INK),
                        (QPalette.PlaceholderText, MUTED), (QPalette.Link, ACCENT)):
        pal.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        pal.setColor(QPalette.Disabled, role, QColor(MUTED))
    app.setPalette(pal)
    app.setStyleSheet(QSS + _glyph_qss())
    pg.setConfigOptions(background=SURFACE, foreground=MUTED, antialias=True)


def style_plot(plot_widget) -> None:
    """Recessive axes and grid on a pyqtgraph PlotWidget."""
    import pyqtgraph as pg
    plot_widget.setBackground(SURFACE)
    item = plot_widget.getPlotItem()
    for name in ("left", "bottom"):
        ax = item.getAxis(name)
        ax.setPen(pg.mkPen(_grid_color or BORDER))      # pyqtgraph draws the grid with the axis pen
        ax.setTextPen(pg.mkPen(MUTED))
    # a colour the user chose is meant to be seen: drawn stronger than the recessive default
    item.showGrid(x=True, y=True, alpha=0.5 if _grid_color else 0.18)
