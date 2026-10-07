"""The palette of the markers as a pop-up: a grid of colour squares to choose one from
(SPEC.md section 10). Used by the Markers panel and by a marker's right-click menu."""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QGridLayout, QMenu, QToolButton, QWidget, QWidgetAction

from . import theme

COLUMNS = 5


def swatch(color: str, side: int) -> QIcon:
    """A square of one colour, for a table row or a palette button."""
    pix = QPixmap(side, side)
    pix.fill(QColor(color))
    return QIcon(pix)


def palette_menu(parent, current: str, on_pick, title: str = "Colour") -> QMenu:
    """A menu that holds the marker palette as a grid. current: the name of the colour in
    use (its square is shown pressed). on_pick(name) is called with the colour chosen.
    The buttons are in menu.buttons, by colour name."""
    menu = QMenu(title, parent)
    body = QWidget(menu)
    grid = QGridLayout(body)
    grid.setContentsMargins(6, 6, 6, 6)
    grid.setSpacing(4)
    side = body.fontMetrics().height() + 4          # the squares grow with the font, on any screen scale
    menu.buttons = {}
    for i, (name, color) in enumerate(theme.MARKER_PALETTE):
        b = QToolButton(body)
        b.setIcon(swatch(color, side))
        b.setIconSize(QSize(side, side))
        b.setCheckable(True)
        b.setChecked(name == current)
        b.setAutoRaise(True)
        b.setToolTip("%s: draw this marker's line and dot in this colour" % name)

        def pick(_checked=False, name=name):
            menu.close()
            on_pick(name)
        b.clicked.connect(pick)
        grid.addWidget(b, i // COLUMNS, i % COLUMNS)
        menu.buttons[name] = b
    action = QWidgetAction(menu)
    action.setDefaultWidget(body)
    menu.addAction(action)
    return menu
