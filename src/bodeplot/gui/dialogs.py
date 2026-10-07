"""Dialogs: settings, connections, simulation settings, image export, skew wizard, calibration
(SPEC.md section 10). Connections and simulation are panels, shown on their own and as
tabs of the settings dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
                               QProgressBar, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..drivers import registry, visa_util
from ..io.export_image import ImageOptions
from ..io.settings import AUTO_KEEP_MAX, SCOPE_MIN_GAP_MS, SKEW_CAPTURES_MAX, SKEW_DEFAULTS, AppSettings, measure_overrides
from ..measure import skew, theory
from ..measure.theory import TransferFunction
from ..models import MeasureSettings, SkewCheck, ThroughCal
from ..sweep import calibration
from ..units import fmt_si, parse_si
from . import theme



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


# ---------------------------------------------------------------------- circuits
class TransferFunctionForm(QWidget):
    """A circuit and its part values (measure/theory.py): the simulated DUT in the
    simulation settings, and a theory curve of the plot."""

    def __init__(self, preset: str = "rc_lpf", params: dict | None = None, title: str = "Circuit", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.preset = QComboBox()
        for name in TransferFunction.PRESETS:
            self.preset.addItem(theory.LABELS[name], name)
        form.addRow(title, self.preset)
        lay.addLayout(form)
        self.param_host = QWidget()
        self.param_form = QFormLayout(self.param_host)
        lay.addWidget(self.param_host)
        self.num = QLineEdit("1")
        self.den = QLineEdit("1e-4, 1")
        self._params_in = dict(params or {})
        self._edits: dict[str, QLineEdit] = {}
        self.preset.currentIndexChanged.connect(self._rebuild)
        self.preset.setCurrentIndex(max(0, self.preset.findData(preset)))
        self._rebuild()

    def _rebuild(self) -> None:
        while self.param_form.rowCount():
            self.param_form.removeRow(0)
        self._edits = {}
        name = self.preset.currentData()
        if name == "custom":
            # every digit: pressing OK without a change must not alter the curve
            self.num = QLineEdit(", ".join("%.12g" % x for x in self._params_in.get("num", [1.0])))
            self.den = QLineEdit(", ".join("%.12g" % x for x in self._params_in.get("den", [1e-4, 1.0])))
            self.param_form.addRow("Numerator (highest power first)", self.num)
            self.param_form.addRow("Denominator", self.den)
            return
        for key, (default, label) in theory.PARAMS[name].items():
            e = QLineEdit(fmt_si(float(self._params_in.get(key, default)), digits=12))
            e.setToolTip("Accepts SI multipliers: 1k, 100n, 1m (M = mega, m = milli)")
            self._edits[key] = e
            self.param_form.addRow(label, e)

    def values(self) -> tuple[str, dict]:
        """(circuit, its values). Raises ValueError with a message for the user when a
        field is not usable."""
        name = self.preset.currentData()
        if name == "custom":
            params = {"num": [float(x) for x in self.num.text().replace(";", ",").split(",") if x.strip()],
                      "den": [float(x) for x in self.den.text().replace(";", ",").split(",") if x.strip()]}
        else:
            params = {k: parse_si(e.text()) for k, e in self._edits.items()}
        theory.build(name, params)                      # the one place that judges the values
        return name, params


class TheoryDialog(QDialog):
    """A theory curve for the plot: pick a circuit and enter its parts, or H(s) itself."""

    def __init__(self, tf: TransferFunction | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theory curve")
        self.resize(420, 260)
        lay = QVBoxLayout(self)
        self.circuit = TransferFunctionForm(tf.name if tf else "rc_lpf", dict(tf.params) if tf else None,
                                            "Circuit", self)
        lay.addWidget(self.circuit)
        note = QLabel("The ideal response of the circuit: no component losses, no lead inductance, no probe.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.RichText)
        lay.addWidget(self.error)
        lay.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.tf: TransferFunction | None = None

    def _accept(self) -> None:
        try:
            self.tf = theory.build(*self.circuit.values())
        except ValueError as e:
            self.tf = None
            self.error.setText(theme.status_html("critical", "Invalid value: %s" % e))
            return
        self.accept()


# ---------------------------------------------------------------------- simulation
class SimSettingsPanel(QWidget):
    def __init__(self, sim: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        self.circuit = TransferFunctionForm(sim.get("preset", "rc_lpf"), sim.get("params"), "DUT", self)
        self.preset = self.circuit.preset           # the settings dialog and its tests reach it by this name
        lay.addWidget(self.circuit)
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

    def values(self) -> dict:
        """Raises ValueError with a message for the user when a field is not usable."""
        name, params = self.circuit.values()
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
PANEL_LABELS = (("dock_config", "Configuration"), ("dock_waveform", "Waveform"), ("dock_traces", "Traces"),
                ("dock_markers", "Markers"), ("dock_log", "Status log"))
STARTUP_LABELS = (("instruments", "Real instruments"), ("simulation", "Simulation"),
                  ("last", "The mode used last time"))


class SettingsDialog(QDialog):
    """Every stored setting in one place: General, Advanced, Instruments, Simulation."""

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
        self.unwrap.setToolTip("Draw the phase as one continuous curve when the app starts. The box above the "
                               "plot changes it for the running session.")
        form.addRow("Plot", self.unwrap)

        # ---- behaviour (user request 2026-10-07)
        self.skew_on_connect = QCheckBox("Open the skew wizard after every connect")
        self.skew_on_connect.setChecked(settings.skew_wizard_on_connect)
        self.skew_on_connect.setToolTip("Off: after a connect the status bar and the log say that the skew check is "
                                        "needed, and starting a sweep asks. On: the wizard opens by itself.")
        form.addRow("Connect", self.skew_on_connect)
        self.tooltips = QCheckBox("Show explanations after")
        self.tooltips.setChecked(settings.tooltips)
        self.tooltips.setToolTip("Explanations like this one, shown when the mouse rests on an option. "
                                 "Untick to switch them all off.")
        self.tooltip_delay = QDoubleSpinBox()
        self.tooltip_delay.setRange(0.0, 10.0)
        self.tooltip_delay.setDecimals(1)
        self.tooltip_delay.setSingleStep(0.5)
        self.tooltip_delay.setSuffix(" s")
        self.tooltip_delay.setValue(settings.tooltip_delay_ms / 1000.0)
        self.tooltip_delay.setToolTip("How long the mouse must rest on an option before its explanation appears.")
        row = QHBoxLayout()
        row.addWidget(self.tooltips)
        row.addWidget(self.tooltip_delay)
        row.addStretch(1)
        form.addRow("Explanations", row)
        self.auto_keep = QSpinBox()
        self.auto_keep.setRange(0, AUTO_KEEP_MAX)
        self.auto_keep.setSpecialValueText("off")
        self.auto_keep.setValue(int(settings.auto_keep_sweeps))
        self.auto_keep.setToolTip("When a new sweep starts, keep this many previous sweeps on the plot as traces. "
                                  "Older ones are removed; sweeps you kept yourself stay.")
        form.addRow("Keep previous sweeps", self.auto_keep)
        self.folder = QLineEdit(settings.export_folder)
        self.folder.setPlaceholderText("the folder used last")
        self.folder.setToolTip("Folder that Export and Load CSV open in. Leave it empty to start in the folder "
                               "that was used last.")
        self.folder_btn = QPushButton("Browse…")
        self.folder_btn.setToolTip("Choose the folder that Export and Load CSV open in.")
        self.folder_btn.clicked.connect(self._browse_folder)
        row = QHBoxLayout()
        row.addWidget(self.folder, 1)
        row.addWidget(self.folder_btn)
        form.addRow("Folder for files", row)
        self.grid_color = ""
        self.grid_swatch = QLabel()
        self.grid_btn = QPushButton("Choose…")
        self.grid_btn.setToolTip("Choose the colour of the grid and axis lines of the plots.")
        self.grid_default_btn = QPushButton("Theme default")
        self.grid_default_btn.setToolTip("Back to the theme's own faint grid and axis lines.")
        self.grid_btn.clicked.connect(self._choose_grid_color)
        self.grid_default_btn.clicked.connect(lambda: self.set_grid_color(""))
        row = QHBoxLayout()
        row.addWidget(self.grid_swatch)
        row.addWidget(self.grid_btn)
        row.addWidget(self.grid_default_btn)
        row.addStretch(1)
        form.addRow("Grid colour", row)
        self.set_grid_color(settings.grid_color)
        self.panels: dict[str, QCheckBox] = {}
        row = QHBoxLayout()
        for name, label in PANEL_LABELS:
            box = QCheckBox(label)
            box.setChecked(bool(settings.startup_panels.get(name, True)))
            box.setToolTip("Show the %s panel when the app starts. A panel that is not shown is one click away "
                           "in the View menu." % label)
            self.panels[name] = box
            row.addWidget(box)
        row.addStretch(1)
        form.addRow("Panels at start-up", row)
        self.debug = QCheckBox("Log every instrument command")
        self.debug.setChecked(settings.debug_logging)
        self.debug.setToolTip("Write every command sent to the instruments and every reply into the log file "
                              "(Help > Open log folder). For finding a fault; the file grows quickly.")
        form.addRow("Log file", self.debug)
        if open_folders:
            row = QHBoxLayout()
            for label, slot in open_folders:
                b = QPushButton(label)
                b.setToolTip("Open this folder in the file manager: %s." % label.lower())
                b.clicked.connect(slot)
                row.addWidget(b)
            row.addStretch(1)
            form.addRow("Folders", row)
        self.tabs.addTab(general, "General")

        # ---- advanced: measurement limits, for every sweep whatever a preset holds
        adv = QWidget()
        form = QFormLayout(adv)
        note = QLabel("These apply to every sweep. The defaults are what the app was tested with on the bench; "
                      "change them only for a reason.")
        note.setWordWrap(True)
        form.addRow(note)
        defaults = MeasureSettings()
        now = measure_overrides(settings.advanced)

        def spin(lo, hi, value, suffix, tip):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setValue(int(round(value)))
            s.setSuffix(suffix)
            s.setToolTip(tip)
            return s

        def dspin(lo, hi, value, suffix, tip):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(1)
            s.setValue(float(value))
            s.setSuffix(suffix)
            s.setToolTip(tip)
            return s

        target = now.get("autorange_target", defaults.autorange_target)
        self.autorange_lo = spin(20, 90, target[0] * 100, " %", "Auto-range: a signal that fills less of the scope's "
                                 "screen than this is measured again on a more sensitive V/div step.")
        self.autorange_hi = spin(25, 95, target[1] * 100, " %", "Auto-range: a signal that fills more of the scope's "
                                 "screen than this is measured again on a less sensitive V/div step.")
        row = QHBoxLayout()
        row.addWidget(self.autorange_lo)
        row.addWidget(QLabel("to"))
        row.addWidget(self.autorange_hi)
        row.addStretch(1)
        form.addRow("Screen filled by the signal", row)
        self.autorange_retries = spin(1, 10, now.get("autorange_max_retries", defaults.autorange_max_retries), "",
                                      "How many times a point may be measured again to find the right V/div step "
                                      "before it is flagged AUTORANGE_FAILED.")
        form.addRow("Auto-range retries", self.autorange_retries)
        self.floor = spin(1, 50, now.get("floor_fraction", defaults.floor_fraction) * 100, " %",
                          "A signal smaller than this share of the screen on the most sensitive V/div step is "
                          "flagged BELOW_FLOOR.")
        form.addRow("Noise floor", self.floor)
        self.timeout = dspin(1.0, 60.0, now.get("acquire_timeout_s", defaults.acquire_timeout_s), " s",
                             "How long the app waits for the scope to finish one capture before it gives up on it.")
        form.addRow("Capture timeout", self.timeout)
        self.low_snr = dspin(0.0, 60.0, now.get("low_snr_db", defaults.low_snr_db), " dB",
                             "A point whose fitted sine stands out of the noise by less than this is flagged LOW_SNR.")
        form.addRow("Low SNR below", self.low_snr)
        self.bad_retries = spin(0, 5, now.get("bad_capture_retries", defaults.bad_capture_retries), "",
                                "How many times a capture whose reference does not hold the stimulus is taken "
                                "again before the point is flagged REF_SUSPECT.")
        form.addRow("Bad-capture retries", self.bad_retries)
        self.adv_defaults_btn = QPushButton("Defaults")
        self.adv_defaults_btn.setToolTip("Put every value on this tab back to the one the app was tested with.")
        self.adv_defaults_btn.clicked.connect(self.advanced_defaults)
        row = QHBoxLayout()
        row.addWidget(self.adv_defaults_btn)
        row.addStretch(1)
        form.addRow(row)
        self.tabs.addTab(adv, "Advanced")

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

    # ---- the settings added on 2026-10-07
    def set_grid_color(self, color: str) -> None:
        """The chosen grid colour ("#rrggbb"), or "" for the theme's own."""
        import re
        self.grid_color = color if re.fullmatch(r"#[0-9a-fA-F]{6}", color or "") else ""
        if self.grid_color:
            from PySide6.QtGui import QColor, QPixmap
            pix = QPixmap(48, 14)
            pix.fill(QColor(self.grid_color))
            self.grid_swatch.setPixmap(pix)
        else:
            self.grid_swatch.setText("theme default")

    def _choose_grid_color(self) -> None:
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self.grid_color or theme.BORDER), self, "Grid colour")
        if c.isValid():
            self.set_grid_color(c.name())

    def _browse_folder(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "Folder for Export and Load CSV", self.folder.text())
        if path:
            self.folder.setText(path)

    def advanced_defaults(self) -> None:
        d = MeasureSettings()
        self.autorange_lo.setValue(int(round(d.autorange_target[0] * 100)))
        self.autorange_hi.setValue(int(round(d.autorange_target[1] * 100)))
        self.autorange_retries.setValue(d.autorange_max_retries)
        self.floor.setValue(int(round(d.floor_fraction * 100)))
        self.timeout.setValue(d.acquire_timeout_s)
        self.low_snr.setValue(d.low_snr_db)
        self.bad_retries.setValue(d.bad_capture_retries)

    def _advanced(self) -> dict:
        """The Advanced tab as stored: only what differs from the defaults."""
        d = MeasureSettings()
        out: dict = {}
        lo, hi = self.autorange_lo.value() / 100.0, self.autorange_hi.value() / 100.0
        if lo < hi and (abs(lo - d.autorange_target[0]) > 1e-9 or abs(hi - d.autorange_target[1]) > 1e-9):
            out.update(autorange_lo=lo, autorange_hi=hi)
        for key, value, default in (("autorange_max_retries", self.autorange_retries.value(), d.autorange_max_retries),
                                    ("floor_fraction", self.floor.value() / 100.0, d.floor_fraction),
                                    ("acquire_timeout_s", self.timeout.value(), d.acquire_timeout_s),
                                    ("low_snr_db", self.low_snr.value(), d.low_snr_db),
                                    ("bad_capture_retries", self.bad_retries.value(), d.bad_capture_retries)):
            if abs(value - default) > 1e-9:
                out[key] = value
        return out

    def apply_to(self, settings: AppSettings) -> None:
        settings.startup_mode = self.startup.currentData()
        settings.scope_min_gap_ms = float(self.gap.value())
        settings.unwrap_phase = self.unwrap.isChecked()
        settings.skew_wizard_on_connect = self.skew_on_connect.isChecked()
        settings.tooltips = self.tooltips.isChecked()
        settings.tooltip_delay_ms = self.tooltip_delay.value() * 1000.0
        settings.auto_keep_sweeps = self.auto_keep.value()
        settings.export_folder = self.folder.text().strip()
        settings.grid_color = self.grid_color
        settings.startup_panels = {name: box.isChecked() for name, box in self.panels.items()}
        settings.debug_logging = self.debug.isChecked()
        settings.advanced = self._advanced()
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

    def __init__(self, engine, get_configs, simulated: bool, freqs_hint: tuple[float, float], parent=None,
                 settings: AppSettings | None = None, save=None):
        """settings: the app settings, whose skew check values the wizard shows and edits (without
        them the wizard has no settings row). save: called after they were changed."""
        super().__init__(parent)
        self.setWindowTitle("Channel skew check")
        self.resize(540, 440)
        self.engine, self.get_configs = engine, get_configs
        self.check: SkewCheck | None = None
        lay = QVBoxLayout(self)
        self.simulated, self.freqs_hint = simulated, freqs_hint
        self.settings, self.save = settings, save
        self.intro = QLabel("")
        self.intro.setWordWrap(True)
        self.result = QLabel("")
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result.setWordWrap(True)
        self.warn = QLabel("")
        self.warn.setWordWrap(True)
        self.warn.setTextFormat(Qt.RichText)
        self.warnings_text = ""
        lay.addWidget(self.intro)
        if settings is not None:
            from .si_widgets import SiSpinBox
            self.freq_lo = SiSpinBox(1.0, 1e9, settings.skew_freq_lo_hz, "Hz")
            self.freq_hi = SiSpinBox(1.0, 1e9, settings.skew_freq_hi_hz, "Hz")
            self.captures = QSpinBox()
            self.captures.setRange(1, SKEW_CAPTURES_MAX)
            self.captures.setValue(int(settings.skew_captures))
            self.defaults_btn = QPushButton("Defaults")
            self.freq_lo.setToolTip("The lower of the two frequencies the delay is measured at. High frequencies "
                                    "resolve a delay best: 0.3 ns is only 0.1° at 1 MHz.")
            self.freq_hi.setToolTip("The upper of the two frequencies the delay is measured at. It is limited to "
                                    "what the generator and the scope both reach.")
            self.captures.setToolTip("Captures averaged at each of the two frequencies. More captures: a steadier "
                                     "result, a slightly longer check.")
            self.defaults_btn.setToolTip("Back to 10 MHz, 20 MHz and 3 captures, the values tested on the bench.")
            row = QHBoxLayout()
            for text, w in (("Check at", self.freq_lo), ("and", self.freq_hi), ("captures", self.captures)):
                row.addWidget(QLabel(text))
                row.addWidget(w)
            row.addWidget(self.defaults_btn)
            row.addStretch(1)
            lay.addLayout(row)
            self.freq_lo.valueChanged.connect(lambda *_: self._show_intro())
            self.freq_hi.valueChanged.connect(lambda *_: self._show_intro())
            self.defaults_btn.clicked.connect(self._defaults)
        self._show_intro()
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

    def _freqs(self) -> tuple[float, float]:
        if self.settings is not None:
            return float(self.freq_lo.value()), float(self.freq_hi.value())
        return self.freqs_hint

    def _show_intro(self) -> None:
        lo, hi = self._freqs()
        text = (
            "<b>Put the reference probe and the DUT probe on the same node</b>: both tips on the "
            "generator output, both ground clips on its shell, both probes at the same setting.<br><br>"
            "The app then measures the delay between the two scope channels at %s and %s and "
            "removes it from every phase reading for the rest of this session.<br><br>"
            "The generator output is switched on for the measurement and off again afterwards."
            % (fmt_si(lo, "Hz"), fmt_si(hi, "Hz")))
        if self.simulated:
            text += "<br><br><i>Simulation: the simulated DUT probe is moved to the reference node for you.</i>"
        self.intro.setText(text)

    def _defaults(self) -> None:
        self.freq_lo.setValue(SKEW_DEFAULTS[0])
        self.freq_hi.setValue(SKEW_DEFAULTS[1])
        self.captures.setValue(SKEW_DEFAULTS[2])

    def measure(self) -> None:
        if self.settings is not None:
            lo, hi = self._freqs()
            if not (0 < lo < hi):
                self.warnings_text = "The lower check frequency must be below the upper one."
                self.warn.setText(theme.status_html("critical", self.warnings_text))
                return
            s = self.settings
            s.skew_freq_lo_hz, s.skew_freq_hi_hz, s.skew_captures = lo, hi, int(self.captures.value())
            if self.save:
                self.save()
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
