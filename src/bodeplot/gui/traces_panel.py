"""The Traces panel (SPEC.md section 10): the list of traces on the plot, and the buttons
that add and remove them. It changes the TraceSet and says so; it draws nothing."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QFileDialog, QGridLayout, QMessageBox, QPushButton, QStyledItemDelegate, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..io import export_csv
from ..measure.theory import TransferFunction
from ..traces import KIND_TEXT, TraceSet
from . import theme
from .dialogs import TheoryDialog

NO_VOLTAGE = "Not drawn while the vertical unit is Voltage: a theory curve has no voltage."
NO_VOLTAGE_FILE = "Not drawn while the vertical unit is Voltage: this file holds no voltages."


class _NoEdit(QStyledItemDelegate):
    """For the Kind column: the item is editable for its name only."""

    def createEditor(self, parent, option, index):
        return None


def _swatch(color: str) -> QIcon:
    pix = QPixmap(12, 12)
    pix.fill(QColor(color))
    return QIcon(pix)


class TracesPanel(QWidget):
    changed = Signal()                  # the set was changed: the plot redraws
    message = Signal(str, str)          # level ("info" | "warn"), text: for the status log
    folder_used = Signal(str)           # Load CSV took files from this folder

    def __init__(self, traces: TraceSet, parent=None):
        super().__init__(parent)
        self.traces = traces
        self.interactive = True         # tests switch this off: no message boxes
        self.unit = "db"
        self.folder = ""                # where Load CSV opens (set by the main window from the settings)
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Trace", "Kind"])
        self.tree.setRootIsDecorated(False)
        self._no_edit = _NoEdit(self.tree)
        self.tree.setItemDelegateForColumn(1, self._no_edit)
        self.tree.setToolTip("Tick a trace to show it. Double-click a name to change it; double-click the kind "
                             "of a theory curve to change its values.")
        lay.addWidget(self.tree, 1)
        # two rows of two: four buttons in one row made the right column too wide for a small screen
        grid = QGridLayout()
        self.load_btn = QPushButton("Load CSV…")
        self.theory_btn = QPushButton("Add theory…")
        self.keep_btn = QPushButton("Keep sweep")
        self.remove_btn = QPushButton("Remove")
        self.load_btn.setToolTip("Add sweeps saved with Export > CSV as traces")
        self.theory_btn.setToolTip("Add the ideal response of a circuit")
        self.keep_btn.setToolTip("Keep the current sweep on the plot when the next one starts")
        self.remove_btn.setToolTip("Take the selected trace off the plot. The live sweep cannot be removed; "
                                   "untick it to hide it.")
        for i, b in enumerate((self.load_btn, self.theory_btn, self.keep_btn, self.remove_btn)):
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)
        self.load_btn.clicked.connect(self._load_clicked)
        self.theory_btn.clicked.connect(self._theory_clicked)
        self.keep_btn.clicked.connect(self.keep)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.currentItemChanged.connect(lambda *_: self.refresh_buttons())
        self.reload()

    # ---- the list
    def reload(self) -> None:
        keep = self.selected_id()
        self.tree.blockSignals(True)
        self.tree.clear()
        for t in self.traces.traces:
            item = QTreeWidgetItem([t.name, KIND_TEXT[t.kind]])
            item.setData(0, Qt.UserRole, t.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(0, Qt.Checked if t.visible else Qt.Unchecked)
            item.setIcon(0, _swatch(theme.SERIES[t.slot] if t.slot is not None else theme.MUTED))
            tip = t.path or ""
            no_voltage = t.kind == "theory" or (bool(t.points) and not any(math.isfinite(p.vdut_amp) for p in t.points))
            if self.unit == "v" and no_voltage:
                tip = NO_VOLTAGE if t.kind == "theory" else NO_VOLTAGE_FILE
                for col in (0, 1):
                    item.setForeground(col, QBrush(QColor(theme.MUTED)))
            for col in (0, 1):
                item.setToolTip(col, tip)
            self.tree.addTopLevelItem(item)
            if t.id == keep:
                self.tree.setCurrentItem(item)
        self.tree.resizeColumnToContents(0)
        self.tree.blockSignals(False)
        self.refresh_buttons()

    def refresh_buttons(self) -> None:
        selected = self.traces.get(self.selected_id()) if self.selected_id() is not None else None
        self.keep_btn.setEnabled(bool(self.traces.live.points))
        self.remove_btn.setEnabled(selected is not None and selected.removable)

    def set_unit(self, unit: str) -> None:
        if unit != self.unit:
            self.unit = unit
            self.reload()

    def selected_id(self) -> int | None:
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None

    def select(self, trace_id: int) -> None:
        for i in range(self.tree.topLevelItemCount()):
            if self.tree.topLevelItem(i).data(0, Qt.UserRole) == trace_id:
                self.tree.setCurrentItem(self.tree.topLevelItem(i))

    def _done(self) -> None:
        self.reload()
        self.changed.emit()

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        trace_id = item.data(0, Qt.UserRole)
        self.traces.set_visible(trace_id, item.checkState(0) == Qt.Checked)
        name = self.traces.rename(trace_id, item.text(0))
        if name != item.text(0):                        # empty, or made unique
            self.tree.blockSignals(True)
            item.setText(0, name)
            self.tree.blockSignals(False)
        self.changed.emit()

    def _double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        t = self.traces.get(item.data(0, Qt.UserRole))
        if column == 1 and t is not None and t.kind == "theory" and self.interactive:
            d = TheoryDialog(t.theory, self)
            if d.exec():
                self.edit_theory(t.id, d.tf)

    # ---- actions
    def load_files(self, paths) -> list[str]:
        """Add each file as a trace. A file that cannot be used is refused with its name
        and the reason; the others still load. Returns the refusals."""
        paths = list(paths)
        if not paths:
            return []
        errors = []
        for path in paths:
            try:
                self.traces.add_file(export_csv.load_csv(path), path)
            except OSError as e:
                errors.append("%s: %s" % (Path(path).name, e.strerror or e))
            except Exception as e:                      # not text, not a sweep CSV, no points
                reason = "it is not a text file" if isinstance(e, UnicodeDecodeError) else str(e)
                errors.append("%s: %s" % (Path(path).name, reason))
        loaded = len(paths) - len(errors)
        if loaded:
            self.message.emit("info", "Loaded %d trace%s." % (loaded, "" if loaded == 1 else "s"))
        for e in errors:
            self.message.emit("warn", "Not loaded: " + e)
        self._done()
        if errors and self.interactive:
            QMessageBox.warning(self, "Load CSV", "Not loaded:\n\n" + "\n".join(errors))
        return errors

    def add_theory(self, tf: TransferFunction) -> None:
        self.traces.add_theory(tf)
        self._done()

    def edit_theory(self, trace_id: int, tf: TransferFunction) -> None:
        self.traces.set_theory(trace_id, tf)
        self._done()

    def keep(self) -> None:
        try:
            self.traces.keep_live()
        except ValueError as e:
            self.message.emit("warn", "Keep sweep: %s." % e)
            return
        self._done()

    def remove_selected(self) -> None:
        trace_id = self.selected_id()
        t = self.traces.get(trace_id) if trace_id is not None else None
        if t is None or not t.removable:
            return
        self.traces.remove(trace_id)
        self._done()

    def _load_clicked(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Load CSV", self.folder, "Sweep CSV (*.csv);;All files (*)")
        if paths:
            self.folder_used.emit(str(Path(paths[0]).parent))
        self.load_files(paths)

    def _theory_clicked(self) -> None:
        d = TheoryDialog(None, self)
        if d.exec():
            self.add_theory(d.tf)
