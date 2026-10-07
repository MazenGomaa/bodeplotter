"""Left dock: sweep, stimulus, scope and measurement settings (SPEC.md section 10)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..io.presets import Preset
from .si_widgets import SiSpinBox
from ..models import (MeasureSettings, Method, ScopeConfig, StimulusConfig, SweepConfig, SweepType)

PROBES = (1.0, 10.0, 100.0)
# Every number field and box may shrink to this width. Their natural minimum follows the
# longest value they could ever hold (1e9 Hz, 100000 points), which made the panel much wider
# than what is in it (user report 2026-10-07).
FIELD_MIN_WIDTH = 100          # "1.000 Vpp" and "Logarithmic" still fit


def _dspin(lo, hi, value, decimals=3, suffix="", step=None) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setRange(lo, hi)
    s.setValue(value)
    s.setKeyboardTracking(False)
    if suffix:
        s.setSuffix(suffix)
    if step:
        s.setSingleStep(step)
    return s


def _spin(lo, hi, value) -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(value)
    s.setKeyboardTracking(False)
    return s


class ConfigPanel(QScrollArea):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        body = QWidget()
        lay = QVBoxLayout(body)

        # ---- sweep
        g = QGroupBox("Sweep")
        f = QFormLayout(g)
        self.sweep_type = QComboBox()
        self.sweep_type.addItem("Logarithmic", SweepType.LOG)
        self.sweep_type.addItem("Linear", SweepType.LINEAR)
        self.start_hz = SiSpinBox(1e-3, 1e9, 50.0, "Hz")
        self.stop_hz = SiSpinBox(1e-3, 1e9, 20e6, "Hz")
        self.ppd = _spin(1, 1000, 20)
        self.n_points = _spin(2, 100000, 101)
        self.descending = QCheckBox("Descending")
        f.addRow("Type", self.sweep_type)
        f.addRow("Start", self.start_hz)
        f.addRow("Stop", self.stop_hz)
        f.addRow("Points / decade", self.ppd)
        f.addRow("Points", self.n_points)
        f.addRow(self.descending)                 # across both columns: a tick box must not widen the field column
        lay.addWidget(g)

        # ---- stimulus
        g = QGroupBox("Stimulus")
        f = QFormLayout(g)
        self.gen_channel = _spin(1, 2, 1)
        self.amp_vpp = _dspin(0.001, 20.0, 1.0, 3, " Vpp", 0.1)
        self.offset_v = _dspin(-10.0, 10.0, 0.0, 3, " V", 0.1)
        self.load = QComboBox()
        self.load.addItem("High-Z", "HIGHZ")
        self.load.addItem("50 Ω", "50")
        f.addRow("Generator channel", self.gen_channel)
        f.addRow("Amplitude", self.amp_vpp)
        f.addRow("Offset", self.offset_v)
        f.addRow("Load", self.load)
        lay.addWidget(g)

        # ---- scope
        g = QGroupBox("Scope")
        f = QFormLayout(g)
        self.ref_channel = _spin(1, 4, 1)
        self.dut_channel = _spin(1, 4, 2)
        self.ref_probe, self.dut_probe = QComboBox(), QComboBox()
        for box in (self.ref_probe, self.dut_probe):
            for p in PROBES:
                box.addItem("%gX" % p, p)
            box.setCurrentIndex(1)
        self.coupling = QComboBox()
        self.coupling.addItems(["DC", "AC"])
        self.bw_limit = QCheckBox("20 MHz bandwidth limit")
        self.target_cycles = _dspin(1.0, 50.0, 5.0, 1)
        f.addRow("Reference channel", self.ref_channel)
        f.addRow("DUT channel", self.dut_channel)
        f.addRow("Reference probe", self.ref_probe)
        f.addRow("DUT probe", self.dut_probe)
        f.addRow("Coupling", self.coupling)
        f.addRow(self.bw_limit)                 # across both columns: a tick box must not widen the field column
        f.addRow("Target cycles", self.target_cycles)
        lay.addWidget(g)

        # ---- measurement
        g = QGroupBox("Measurement")
        f = QFormLayout(g)
        self.method = QComboBox()
        self.method.addItem("Sine fit", Method.SINEFIT)
        self.method.addItem("Scope built-in", Method.BUILTIN)
        self.method.addItem("Fast preview (rough phase)", Method.PREVIEW)
        self.method.setToolTip("Fast preview reads the scope while it runs: about twice as fast, the same "
                               "gain, but the phase is rough (about 1° below 1 MHz, up to about 10° at 20 MHz).")
        self.averages = _spin(1, 256, 1)
        self.settle_ms = _dspin(0.0, 10000.0, 50.0, 1, " ms", 10.0)
        self.settle_cycles = _dspin(0.0, 100.0, 3.0, 1)
        f.addRow("Method", self.method)
        f.addRow("Averages", self.averages)
        f.addRow("Settle time", self.settle_ms)
        f.addRow("Settle cycles", self.settle_cycles)
        lay.addWidget(g)
        lay.addStretch(1)
        for field in body.findChildren(QAbstractSpinBox) + body.findChildren(QComboBox):
            field.setMinimumWidth(FIELD_MIN_WIDTH)
        self.setWidget(body)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._fit_width()

        self._base_measure = MeasureSettings()
        self._base_scope = ScopeConfig()
        self.sweep_type.currentIndexChanged.connect(self._sync_enabled)
        for w in body.findChildren(QDoubleSpinBox) + body.findChildren(QSpinBox):
            w.valueChanged.connect(self.changed)
        for w in body.findChildren(QComboBox):
            w.currentIndexChanged.connect(self.changed)
        for w in body.findChildren(QCheckBox):
            w.toggled.connect(self.changed)
        self._sync_enabled()

    def _fit_width(self) -> None:
        """Never narrower than the labels and the fields at their smallest (FIELD_MIN_WIDTH):
        the panel can be dragged slim, but its neighbours cannot squeeze it into a horizontal
        scroll bar (user reports 2026-10-07)."""
        body = self.widget()
        if body is not None:
            self.setMinimumWidth(body.minimumSizeHint().width() + self.verticalScrollBar().sizeHint().width()
                                 + 2 * self.frameWidth())

    def showEvent(self, event) -> None:
        self._fit_width()               # fonts and style are final once the panel is shown
        super().showEvent(event)

    def _sync_enabled(self):
        log = self.sweep_type.currentData() is SweepType.LOG
        self.ppd.setEnabled(log)
        self.n_points.setEnabled(not log)

    # ---- read
    def sweep(self) -> SweepConfig:
        return SweepConfig(self.sweep_type.currentData(), self.start_hz.value(), self.stop_hz.value(),
                           self.ppd.value(), self.n_points.value(), self.descending.isChecked())

    def stimulus(self) -> StimulusConfig:
        return StimulusConfig(self.gen_channel.value(), self.amp_vpp.value(), self.offset_v.value(),
                              self.load.currentData())

    def scope(self) -> ScopeConfig:
        b = self._base_scope
        ref, dut = self.ref_channel.value(), self.dut_channel.value()
        return ScopeConfig(ref, dut, {ref: self.ref_probe.currentData(), dut: self.dut_probe.currentData()},
                           self.coupling.currentText(), self.bw_limit.isChecked(),
                           self.target_cycles.value(), b.min_samples_per_cycle)

    def measure(self) -> MeasureSettings:
        b = self._base_measure
        return MeasureSettings(self.method.currentData(), self.averages.value(), self.settle_ms.value(),
                               self.settle_cycles.value(), b.autorange_target, b.autorange_max_retries,
                               b.floor_fraction, b.acquire_timeout_s, b.vdiv_settle_ms, b.low_snr_db)

    def preset(self) -> Preset:
        return Preset(self.sweep(), self.stimulus(), self.scope(), self.measure())

    def validation_error(self) -> str | None:
        if self.ref_channel.value() == self.dut_channel.value():
            return "The reference and DUT channels must be different."
        if self.stop_hz.value() <= self.start_hz.value():
            return "Stop frequency must be above start frequency."
        return None

    # ---- write
    def _set_combo(self, box: QComboBox, data) -> None:
        i = box.findData(data)
        if i < 0 and isinstance(data, float):
            i = min(range(box.count()), key=lambda k: abs(box.itemData(k) - data))
        if i >= 0:
            box.setCurrentIndex(i)

    def set_preset(self, p: Preset) -> None:
        self.blockSignals(True)
        try:
            self._set_combo(self.sweep_type, p.sweep.sweep_type)
            self.start_hz.setValue(p.sweep.start_hz)
            self.stop_hz.setValue(p.sweep.stop_hz)
            self.ppd.setValue(p.sweep.points_per_decade)
            self.n_points.setValue(p.sweep.n_points)
            self.descending.setChecked(p.sweep.descending)
            self.gen_channel.setValue(p.stimulus.gen_channel)
            self.amp_vpp.setValue(p.stimulus.amp_vpp)
            self.offset_v.setValue(p.stimulus.offset_v)
            self._set_combo(self.load, p.stimulus.load)
            self.ref_channel.setValue(p.scope.ref_channel)
            self.dut_channel.setValue(p.scope.dut_channel)
            self._set_combo(self.ref_probe, float(p.scope.probe_atten.get(p.scope.ref_channel, 10.0)))
            self._set_combo(self.dut_probe, float(p.scope.probe_atten.get(p.scope.dut_channel, 10.0)))
            self.coupling.setCurrentText(p.scope.coupling if p.scope.coupling in ("DC", "AC") else "DC")
            self.bw_limit.setChecked(p.scope.bw_limit)
            self.target_cycles.setValue(p.scope.target_cycles)
            self._set_combo(self.method, p.measure.method)
            self.averages.setValue(p.measure.averages)
            self.settle_ms.setValue(p.measure.settle_ms)
            self.settle_cycles.setValue(p.measure.settle_cycles)
            self._base_measure, self._base_scope = p.measure, p.scope
        finally:
            self.blockSignals(False)
        self._sync_enabled()
        self.changed.emit()

    def set_has_builtin(self, has: bool) -> None:
        item = self.method.model().item(1)
        item.setEnabled(has)
        # only away from the entry that is not there: this runs on every session update, and
        # it used to put the Method box back on Sine fit after every sweep
        if not has and self.method.currentData() is Method.BUILTIN:
            self.method.setCurrentIndex(0)
