"""Dialogs: settings, connections, simulation settings, image export, skew wizard, calibration
(SPEC.md section 10). Connections and simulation are panels, shown on their own and as
tabs of the settings dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
                               QProgressBar, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..drivers import registry, visa_util
from ..drivers.mock import SimulatedDUT
from ..io.export_image import ImageOptions
from ..io.settings import SCOPE_MIN_GAP_MS, AppSettings
from ..measure import skew, theory
from ..models import SkewCheck, ThroughCal
from ..sweep import calibration
from ..units import fmt_si, parse_si
from . import theme

SIM_PARAMS, SIM_LABELS = theory.PARAMS, theory.LABELS      # the simulated DUT's circuits (measure/theory.py)


# ---------------------------------------------------------------------- connections
class ConnectionsPanel(QWidget):
    def __init__(self, settings: AppSettings, parent=None, connected: bool = False):
        super().__init__(parent)
        self.connected = connected
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.simulate = QCheckBox("Simulate (mock instruments and simulated DUT)")
        self.simulate.setChecked(settings.simulate)
        self.backend = QComboBox()
        for b, label in (("py", "pyvisa-py (free, default)"), ("auto", "Auto (pyvisa-py first)"),
                         ("ivi", "Vendor VISA library (needs its own licence)")):
            self.backend.addItem(label, b)
        self.backend.setCurrentIndex(max(0, self.backend.findData(settings.backend)))
        self.source = QLineEdit(settings.source_resource)
        self.digitizer = QLineEdit(settings.digitizer_resource)
        form.addRow("", self.simulate)
        form.addRow("Backend", self.backend)
        form.addRow("Generator resource", self.source)
        form.addRow("Scope resource", self.digitizer)
        lay.addLayout(form)
        row = QHBoxLayout()
        self.discover_btn = QPushButton("Discover")
        self.test_btn = QPushButton("Test")
        row.addWidget(self.discover_btn)
        row.addWidget(self.test_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.found = QListWidget()
        lay.addWidget(self.found, 1)
        self.note = QLabel("Double-click a resource to use it. Hold Shift to set it as the scope. Leave "
                           "both fields empty to find the instruments automatically.")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.discover_btn.clicked.connect(self.discover)
        self.test_btn.clicked.connect(self.test)
        self.found.itemDoubleClicked.connect(self._pick)

    def discover(self) -> None:
        self.found.clear()
        try:
            for r in visa_util.discover(self.backend.currentData()):
                ids = visa_util.usb_ids(r)
                hint = ""
                if ids and ids[:2] == (0x5656, 0x0832):
                    hint = "   (UNI-T UPO1000 scope)"
                elif ids and ids[:2] == (0x6656, 0x0834):
                    hint = "   (UNI-T UTG900E generator)"
                self.found.addItem(r + hint)
            if self.found.count() == 0:
                self.found.addItem("No resources found. On Windows the instruments need the WinUSB "
                                   "driver (Zadig) for the pyvisa-py backend.")
        except Exception as e:
            self.found.addItem("Discovery failed: %s" % e)

    def _pick(self, item) -> None:
        text = item.text().split("   ")[0]
        if "::" not in text:
            return
        from PySide6.QtWidgets import QApplication
        target = self.digitizer if QApplication.keyboardModifiers() & Qt.ShiftModifier else self.source
        ids = visa_util.usb_ids(text)
        if ids and ids[:2] == (0x5656, 0x0832):
            target = self.digitizer
        elif ids and ids[:2] == (0x6656, 0x0834):
            target = self.source
        target.setText(text)

    def test(self) -> None:
        if self.simulate.isChecked():
            QMessageBox.information(self, "Test", "Simulation mode: nothing to test.")
            return
        if self.connected:
            QMessageBox.information(self, "Test", "Disconnect first: the instruments are in use.")
            return
        # Identification only: *IDN? is the one query both instruments are known to accept.
        from ..drivers import connect
        only = tuple(x for x in (self.source.text().strip(), self.digitizer.text().strip()) if x)
        self.found.clear()
        try:
            results = connect.scan(self.backend.currentData(), only)
        except Exception as e:
            self.found.addItem("Test failed: %s" % e)
            return
        for r in results:
            what = r.entry.label if r.entry else ("no reply" if not r.idn else "not a supported instrument")
            self.found.addItem("%s   %s   [%s]" % (r.resource, r.idn or "-", what))
        if not results:
            self.found.addItem("Nothing to test: no USB or LAN instrument was found.")

    def apply_to(self, settings: AppSettings) -> None:
        settings.simulate = self.simulate.isChecked()
        settings.backend = self.backend.currentData()
        settings.source_resource = self.source.text().strip()
        settings.digitizer_resource = self.digitizer.text().strip()


class ConnectionsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None, connected: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Connections")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        self.panel = ConnectionsPanel(settings, self, connected)
        lay.addWidget(self.panel)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def apply_to(self, settings: AppSettings) -> None:
        self.panel.apply_to(settings)


# ---------------------------------------------------------------------- simulation
class SimSettingsPanel(QWidget):
    def __init__(self, sim: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        self.form = QFormLayout()
        self.preset = QComboBox()
        for name in SimulatedDUT.PRESETS:
            self.preset.addItem(SIM_LABELS[name], name)
        self.form.addRow("DUT", self.preset)
        lay.addLayout(self.form)
        self.param_host = QWidget()
        self.param_form = QFormLayout(self.param_host)
        lay.addWidget(self.param_host)
        self.num = QLineEdit("1")
        self.den = QLineEdit("1e-4, 1")
        tail = QFormLayout()
        self.noise = QDoubleSpinBox()
        self.noise.setDecimals(3)
        self.noise.setRange(0.0, 1000.0)
        self.noise.setSuffix(" mV rms")
        self.noise.setValue(float(sim.get("noise_vrms", 1e-4)) * 1e3)
        self.latency = QDoubleSpinBox()
        self.latency.setRange(0.0, 1000.0)
        self.latency.setSuffix(" ms")
        self.latency.setValue(float(sim.get("latency_ms", 5.0)))
        tail.addRow("Noise at the scope input", self.noise)
        tail.addRow("Latency per command", self.latency)
        lay.addLayout(tail)
        lay.addStretch(1)
        self._params_in = dict(sim.get("params") or {})
        self._edits: dict[str, QLineEdit] = {}
        self.preset.currentIndexChanged.connect(self._rebuild)
        self.preset.setCurrentIndex(max(0, self.preset.findData(sim.get("preset", "rc_lpf"))))
        self._rebuild()

    def _rebuild(self) -> None:
        while self.param_form.rowCount():
            self.param_form.removeRow(0)
        self._edits = {}
        name = self.preset.currentData()
        if name == "custom":
            self.num = QLineEdit(", ".join("%g" % x for x in self._params_in.get("num", [1.0])))
            self.den = QLineEdit(", ".join("%g" % x for x in self._params_in.get("den", [1e-4, 1.0])))
            self.param_form.addRow("Numerator (highest power first)", self.num)
            self.param_form.addRow("Denominator", self.den)
            return
        for key, (default, label) in SIM_PARAMS[name].items():
            e = QLineEdit(fmt_si(float(self._params_in.get(key, default))))
            e.setToolTip("Accepts SI multipliers: 1k, 100n, 1m (M = mega, m = milli)")
            self._edits[key] = e
            self.param_form.addRow(label, e)

    def values(self) -> dict:
        """Raises ValueError with a message for the user when a field is not usable."""
        name = self.preset.currentData()
        if name == "custom":
            params = {"num": [float(x) for x in self.num.text().replace(";", ",").split(",") if x.strip()],
                      "den": [float(x) for x in self.den.text().replace(";", ",").split(",") if x.strip()]}
            if not params["num"] or not params["den"] or not any(params["den"]):
                raise ValueError("numerator and denominator need at least one coefficient")
        else:
            params = {k: parse_si(e.text()) for k, e in self._edits.items()}
            if any(v <= 0 for v in params.values()):
                raise ValueError("component values must be positive")
        return {"preset": name, "params": params, "noise_vrms": self.noise.value() / 1e3,
                "latency_ms": self.latency.value()}

class SimSettingsDialog(QDialog):
    def __init__(self, sim: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Simulation settings")
        lay = QVBoxLayout(self)
        self.panel = SimSettingsPanel(sim, self)
        lay.addWidget(self.panel)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _accept(self) -> None:
        try:
            self.result_sim = self.panel.values()
        except ValueError as e:
            QMessageBox.warning(self, "Simulation settings", "Invalid value: %s" % e)
            return
        self.accept()


# ---------------------------------------------------------------------- settings
STARTUP_LABELS = (("instruments", "Real instruments"), ("simulation", "Simulation"),
                  ("last", "The mode used last time"))


class SettingsDialog(QDialog):
    """Every stored setting in one place: General, Instruments, Simulation."""

    def __init__(self, settings: AppSettings, parent=None, connected: bool = False, open_folders=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(620, 520)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        general = QWidget()
        form = QFormLayout(general)
        self.startup = QComboBox()
        for key, label in STARTUP_LABELS:
            self.startup.addItem(label, key)
        self.startup.setCurrentIndex(max(0, self.startup.findData(settings.startup_mode)))
        self.startup.setToolTip("What the app comes up in when it is started. The Mode box in the "
                                "toolbar changes the mode of the running session.")
        form.addRow("Start-up mode", self.startup)
        self.gap = QSpinBox()
        self.gap.setRange(int(SCOPE_MIN_GAP_MS[0]), int(SCOPE_MIN_GAP_MS[1]))
        self.gap.setSingleStep(50)
        self.gap.setSuffix(" ms")
        self.gap.setValue(int(round(settings.scope_min_gap_ms)))
        self.gap.setToolTip("Minimum pause after the app changes the scope's timebase or V/div. "
                            "Takes effect at the next Connect.")
        form.addRow("Pause after a scope range change", self.gap)
        self.unwrap = QCheckBox("Unwrap phase")
        self.unwrap.setChecked(settings.unwrap_phase)
        form.addRow("Plot", self.unwrap)
        if open_folders:
            row = QHBoxLayout()
            for label, slot in open_folders:
                b = QPushButton(label)
                b.clicked.connect(slot)
                row.addWidget(b)
            row.addStretch(1)
            form.addRow("Folders", row)
        self.tabs.addTab(general, "General")

        self.connections = ConnectionsPanel(settings, self, connected)
        self.tabs.addTab(self.connections, "Instruments")
        self.sim = SimSettingsPanel(settings.sim, self)
        self.tabs.addTab(self.sim, "Simulation")
        if connected:
            for w in (self.connections, self.sim):
                w.setEnabled(False)
            note = QLabel("Disconnect to change the instrument and simulation settings.")
            note.setWordWrap(True)
            lay.addWidget(note)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.result_sim = dict(settings.sim)

    def _accept(self) -> None:
        try:
            self.result_sim = self.sim.values()
        except ValueError as e:
            self.tabs.setCurrentWidget(self.sim)
            QMessageBox.warning(self, "Settings", "Invalid simulation value: %s" % e)
            return
        self.accept()

    def apply_to(self, settings: AppSettings) -> None:
        settings.startup_mode = self.startup.currentData()
        settings.scope_min_gap_ms = float(self.gap.value())
        settings.unwrap_phase = self.unwrap.isChecked()
        if self.connections.isEnabled():
            self.connections.apply_to(settings)
            settings.sim = self.result_sim


# ---------------------------------------------------------------------- image export
class ImageExportDialog(QDialog):
    def __init__(self, opts: ImageOptions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export image")
        form = QFormLayout(self)
        self.title = QLineEdit(opts.title)
        self.dpi = QSpinBox()
        self.dpi.setRange(50, 1200)
        self.dpi.setValue(opts.dpi)
        self.width = QDoubleSpinBox()
        self.width.setRange(2.0, 40.0)
        self.width.setValue(opts.width_in)
        self.width.setSuffix(" in")
        self.height = QDoubleSpinBox()
        self.height.setRange(2.0, 40.0)
        self.height.setValue(opts.height_in)
        self.height.setSuffix(" in")
        form.addRow("Title", self.title)
        form.addRow("DPI", self.dpi)
        form.addRow("Width", self.width)
        form.addRow("Height", self.height)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)

    def options(self, unwrap: bool, log_x: bool, show_phase: bool) -> ImageOptions:
        return ImageOptions(self.title.text(), self.dpi.value(), self.width.value(), self.height.value(),
                            unwrap, log_x, show_phase)


# ---------------------------------------------------------------------- skew wizard
def skew_report(check: SkewCheck) -> str:
    state = skew.near_state(check.measured_s)
    lines = ["Delay applied (DUT − reference):  %+.2f ns   (%s)" % (
        check.delay_s * 1e9, "snapped to a known state" if check.snapped else "the measured value"),
        "Delay measured:  %+.2f ns%s" % (check.measured_s * 1e9,
                                         "" if state is None else "   (scope state %+.2f ns)" % (state * 1e9))]
    for f, d, g in zip(check.freqs_hz, check.per_freq_delay_s, check.per_freq_gain_db):
        lines.append("   at %g MHz:  %+.2f ns  (%+.2f°),  gain %+.3f dB"
                     % (f / 1e6, d * 1e9, 360.0 * f * d, g))
    lines.append("Gain mismatch:  %+.3f dB" % check.gain_db)
    top = max(check.freqs_hz)
    lines.append("Correction at %g MHz:  %+.2f°" % (top / 1e6, -skew.correction_deg(top, check.delay_s)))
    return "\n".join(lines)


class SkewWizard(QDialog):
    """Guides the user through the same-node measurement and shows the result.

    engine: a SweepEngine. get_configs: callable returning engine.Configs.
    """

    def __init__(self, engine, get_configs, simulated: bool, freqs_hint: tuple[float, float], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Channel skew check")
        self.resize(520, 380)
        self.engine, self.get_configs = engine, get_configs
        self.check: SkewCheck | None = None
        lay = QVBoxLayout(self)
        intro = (
            "<b>Put the reference probe and the DUT probe on the same node</b>: both tips on the "
            "generator output, both ground clips on its shell, both probes at the same setting.<br><br>"
            "The app then measures the delay between the two scope channels at %g MHz and %g MHz and "
            "removes it from every phase reading for the rest of this session.<br><br>"
            "The generator output is switched on for the measurement and off again afterwards."
            % (freqs_hint[0] / 1e6, freqs_hint[1] / 1e6))
        if simulated:
            intro += "<br><br><i>Simulation: the simulated DUT probe is moved to the reference node for you.</i>"
        self.intro = QLabel(intro)
        self.intro.setWordWrap(True)
        self.result = QLabel("")
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result.setWordWrap(True)
        self.warn = QLabel("")
        self.warn.setWordWrap(True)
        self.warn.setTextFormat(Qt.RichText)
        self.warnings_text = ""
        lay.addWidget(self.intro)
        lay.addWidget(self.result, 1)
        lay.addWidget(self.warn)
        row = QHBoxLayout()
        self.measure_btn = QPushButton("Probes are connected: measure")
        self.accept_btn = QPushButton("Accept")
        self.cancel_btn = QPushButton("Cancel")
        self.accept_btn.setEnabled(False)
        row.addWidget(self.measure_btn)
        row.addStretch(1)
        row.addWidget(self.accept_btn)
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)
        self.measure_btn.clicked.connect(self.measure)
        self.accept_btn.clicked.connect(self._accept)
        self.cancel_btn.clicked.connect(self.reject)
        engine.skew_measured.connect(self._measured)
        engine.error.connect(self._failed)

    def measure(self) -> None:
        self.measure_btn.setEnabled(False)
        self.accept_btn.setEnabled(False)
        self.result.setText("Measuring …")
        self.warn.setText("")
        self.engine.skew_check(self.get_configs())

    def _measured(self, check: SkewCheck) -> None:
        self.check = check
        self.result.setText(skew_report(check))
        self.warnings_text = "\n\n".join("Warning: " + w for w in check.warnings)
        self.warn.setText("<br><br>".join(theme.status_html("warning", "Warning: " + w) for w in check.warnings))
        self.measure_btn.setText("Measure again")
        self.measure_btn.setEnabled(True)
        self.accept_btn.setEnabled(True)

    def _failed(self, message: str) -> None:
        if self.isVisible():
            self.result.setText("")
            self.warnings_text = message
            self.warn.setText(theme.status_html("critical", message))
            self.measure_btn.setEnabled(True)

    def _accept(self) -> None:
        if self.check is not None:
            self.engine.accept_skew(self.check)
            self.accept()

    def done(self, r: int) -> None:
        for sig, slot in ((self.engine.skew_measured, self._measured), (self.engine.error, self._failed)):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        super().done(r)


# ---------------------------------------------------------------------- through calibration
def cal_report(cal: ThroughCal) -> str:
    return "\n".join([
        "Range:  %s,  %d points" % (calibration.range_text(cal), len(cal.freqs_hz)),
        "Largest gain deviation:  %.3f dB" % calibration.max_gain_db(cal),
        "Delay found (DUT − reference):  %+.2f ns" % (calibration.fitted_delay_s(cal) * 1e9),
        "Measured at %s with %g Vpp" % (cal.checked_at[11:16], cal.amp_vpp)])


class CalDialog(QDialog):
    """Guides the user through the through calibration and shows the result.

    engine: a SweepEngine. get_configs: callable returning engine.Configs. current: the
    calibration the connection holds now, or None.
    """

    def __init__(self, engine, get_configs, simulated: bool, current: ThroughCal | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Through calibration")
        self.resize(540, 420)
        self.engine, self.get_configs = engine, get_configs
        self.cal: ThroughCal | None = None
        self.running = False
        lay = QVBoxLayout(self)
        intro = (
            "<b>Put the reference probe and the DUT probe on the same node</b>: both tips on the "
            "generator output, both ground clips on its shell, both probes at the same setting.<br><br>"
            "The app measures the difference between the two channels over the full frequency range "
            "(about 1 minute) and removes it, gain and phase, from every later sweep of this connection "
            "that uses the same channels, probe settings, coupling and bandwidth limit.<br><br>"
            "The generator output is switched on for the measurement and off again afterwards.")
        if simulated:
            intro += "<br><br><i>Simulation: the simulated DUT probe is moved to the reference node for you.</i>"
        if current is not None:
            intro += "<br><br>Current calibration: %s." % calibration.describe(current)[5:]
        self.intro = QLabel(intro)
        self.intro.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.result = QLabel("")
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result.setWordWrap(True)
        self.warn = QLabel("")
        self.warn.setWordWrap(True)
        self.warn.setTextFormat(Qt.RichText)
        self.warnings_text = ""
        lay.addWidget(self.intro)
        lay.addWidget(self.progress)
        lay.addWidget(self.result, 1)
        lay.addWidget(self.warn)
        row = QHBoxLayout()
        self.start_btn = QPushButton("Probes are connected: calibrate")
        self.discard_btn = QPushButton("Discard calibration")
        self.accept_btn = QPushButton("Accept")
        self.cancel_btn = QPushButton("Cancel")
        self.accept_btn.setEnabled(False)
        self.discard_btn.setVisible(current is not None)
        row.addWidget(self.start_btn)
        row.addWidget(self.discard_btn)
        row.addStretch(1)
        row.addWidget(self.accept_btn)
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)
        self.start_btn.clicked.connect(self.start)
        self.discard_btn.clicked.connect(self._discard)
        self.accept_btn.clicked.connect(self._accept)
        self.cancel_btn.clicked.connect(self.reject)
        engine.cal_measured.connect(self._measured)
        engine.progress.connect(self._progress)
        engine.error.connect(self._failed)

    def start(self) -> None:
        self.running = True
        self.start_btn.setEnabled(False)
        self.accept_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.result.setText("Measuring …")
        self.warn.setText("")
        self.engine.run_cal(self.get_configs())

    def _progress(self, i: int, n: int) -> None:
        if self.running:
            self.progress.setRange(0, n)
            self.progress.setValue(i)

    def _measured(self, cal: ThroughCal | None) -> None:
        self.running = False
        self.start_btn.setEnabled(True)
        self.discard_btn.setEnabled(True)
        if cal is None:                             # cancelled: nothing to accept
            self.cal = None
            self.result.setText("Cancelled.")
            self.accept_btn.setEnabled(False)
            return
        self.cal = cal
        self.result.setText(cal_report(cal))
        kind = "warning" if cal.acceptable else "critical"
        self.warnings_text = "\n\n".join(cal.warnings)
        self.warn.setText("<br><br>".join(theme.status_html(kind, w) for w in cal.warnings))
        self.start_btn.setText("Measure again")
        self.accept_btn.setEnabled(cal.acceptable)

    def _failed(self, message: str) -> None:
        if self.running or self.isVisible():
            self.running = False
            self.result.setText("")
            self.warnings_text = message
            self.warn.setText(theme.status_html("critical", message))
            self.start_btn.setEnabled(True)
            self.discard_btn.setEnabled(True)

    def _accept(self) -> None:
        if self.cal is not None and self.cal.acceptable:
            self.engine.accept_cal(self.cal)
            self.accept()

    def _discard(self) -> None:
        self.engine.discard_cal()
        self.discard_btn.hide()

    def reject(self) -> None:
        if self.running:                            # the first Cancel stops the measurement
            self.engine.abort()
            return
        super().reject()

    def done(self, r: int) -> None:
        for sig, slot in ((self.engine.cal_measured, self._measured), (self.engine.progress, self._progress),
                          (self.engine.error, self._failed)):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        super().done(r)
