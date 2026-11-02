"""Main window (SPEC.md section 10). The GUI never touches an instrument: everything
goes through the SweepEngine."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QComboBox, QDockWidget, QFileDialog, QInputDialog, QLabel, QMainWindow,
                               QApplication, QMenu, QMessageBox, QSizePolicy, QToolBar, QToolButton, QWidget)

from .. import __version__
from ..io import export_csv, export_image, export_touchstone, presets
from ..io.settings import AppSettings, load_settings, measure_overrides, save_settings
from ..measure import analysis_settings, skew
from ..models import EngineState, LogEntry, Method, PointResult, SweepResult, SweepType, ThroughCal
from ..sweep import calibration
from ..sweep import plan as plan_mod
from ..sweep.engine import Configs, ConnectRequest, SessionInfo, SweepEngine
from ..traces import TraceSet
from . import theme
from .bode_plot import BodePlot
from .config_panel import ConfigPanel
from ..units import fmt_si
from .dialogs import (CalDialog, ConnectionsDialog, ImageExportDialog, SettingsDialog, SimSettingsDialog,
                      SkewWizard)
from .analysis_panel import AnalysisPanel
from .status_log import StatusLog
from .markers_panel import MarkersPanel
from .traces_panel import TracesPanel
from .waveform_view import WaveformView

log = logging.getLogger("bodeplot.gui")
BUSY = (EngineState.CONNECTING, EngineState.RUNNING, EngineState.PAUSED, EngineState.ABORTING)


LAYOUT_VERSION = 3      # the arrangement of the panels; a window layout stored by another one is not restored

class MainWindow(QMainWindow):
    def __init__(self, simulate: bool | None = None, settings: AppSettings | None = None,
                 sim_seed: int | None = None):
        super().__init__()
        self.settings = settings or load_settings()
        # '--sim' is for this run only. It used to be saved with the settings, so a later
        # start without the flag still came up in simulation (found by the user, 2026-10-06).
        self._stored_simulate: bool | None = None
        if simulate is None and self.settings.startup_mode != "last":
            simulate = self.settings.startup_mode == "simulation"       # Settings > Start-up mode
        if simulate is not None and simulate != self.settings.simulate:
            self._stored_simulate = self.settings.simulate
            self.settings.simulate = simulate
        self.sim_seed = sim_seed
        self._interactive = True        # tests switch this off: no modal dialogs (see the property)
        self.info = SessionInfo()
        self.state = EngineState.IDLE
        self.result: SweepResult | None = None
        self._points: list[PointResult] = []
        self._t_start = 0.0
        self._progress = (0, 0)
        self._pending_sweep = False
        self._last_reason: str | None = None
        self._image_opts = export_image.ImageOptions()
        self._auto_kept: list[int] = []     # traces kept by the 'keep previous sweeps' setting, oldest first

        app = QApplication.instance()
        if app is not None:
            theme.apply(app)                # before any plot widget is created
        self.setWindowTitle("Bode plotter %s" % __version__)
        self.resize(1400, 860)
        self.docks: dict[str, QDockWidget] = {}
        self.traces = TraceSet()
        self.plot = BodePlot(self.traces)
        self.setCentralWidget(self.plot)
        self.config = ConfigPanel()
        self.waveform = WaveformView()
        self.status_log = StatusLog()
        self.traces_panel = TracesPanel(self.traces)
        self.traces_panel.interactive = self._interactive
        self.markers_panel = MarkersPanel(self.plot)
        self.analysis_panel = AnalysisPanel(self.plot)
        for title, name, widget, area in (
                ("Configuration", "dock_config", self.config, Qt.LeftDockWidgetArea),
                ("Traces", "dock_traces", self.traces_panel, Qt.RightDockWidgetArea),
                ("Markers", "dock_markers", self.markers_panel, Qt.RightDockWidgetArea),
                ("Analysis", "dock_analysis", self.analysis_panel, Qt.RightDockWidgetArea),
                ("Status log", "dock_log", self.status_log, Qt.BottomDockWidgetArea),
                ("Waveform", "dock_waveform", self.waveform, Qt.BottomDockWidgetArea)):
            dock = QDockWidget(title, self)
            dock.setObjectName(name)
            dock.setWidget(widget)
            self.addDockWidget(area, dock)
            self.docks[name] = dock
        # The window reads in working order (user's review of 2026-10-07): set up on the left, the
        # plot in the middle, reading the result on the right (Traces, with Markers and Analysis as
        # tabs behind it: both read a trace). What is watched while a sweep runs, the log and the
        # waveform, shares a low strip underneath.
        self.tabifyDockWidget(self.docks["dock_traces"], self.docks["dock_markers"])
        self.tabifyDockWidget(self.docks["dock_markers"], self.docks["dock_analysis"])
        self.docks["dock_traces"].raise_()
        self.splitDockWidget(self.docks["dock_log"], self.docks["dock_waveform"], Qt.Horizontal)
        self._default_sizes()

        self.engine = SweepEngine(self)
        e = self.engine
        e.point_measured.connect(self._on_point)
        e.waveform_captured.connect(self.waveform.show_pair)
        e.log.connect(self.status_log.add_log)
        e.progress.connect(self._on_progress)
        e.state_changed.connect(self._on_state)
        e.finished.connect(self._on_finished)
        e.error.connect(self._on_error)
        e.session_changed.connect(self._on_session)
        e.point_remeasured.connect(self._on_remeasured)
        self.plot.remeasure_requested.connect(self.remeasure)
        self.traces_panel.changed.connect(self.plot.traces_changed)
        self.traces_panel.changed.connect(self._update_actions)     # after the plot: Export follows what is drawn
        self.traces_panel.message.connect(self._say)
        self.traces_panel.folder_used.connect(lambda folder: self.remember_folder(Path(folder) / "x"))
        self.plot.unit_box.currentIndexChanged.connect(lambda _i: self.traces_panel.set_unit(self.plot.unit()))

        self._build_toolbar()
        self._build_menus()
        self._build_statusbar()
        self._default_state = self.saveState(LAYOUT_VERSION)    # the layout "Reset layout" goes back to
        self._load_ui_state()
        self.apply_settings()
        self.config.changed.connect(self._on_config_changed)
        self._on_config_changed()
        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._update_clock)
        self._tick.start()
        self._update_actions()

    @property
    def interactive(self) -> bool:
        """False in the tests: no modal dialog or message box, here or in the Traces panel."""
        return self._interactive

    @interactive.setter
    def interactive(self, on: bool) -> None:
        self._interactive = bool(on)
        self.traces_panel.interactive = self._interactive

    # ------------------------------------------------------------------ UI construction
    def _toolbar_action(self, text: str, slot, tip: str = "") -> QAction:
        """A toolbar button that calls slot() with NO argument. A QAction hands its 'checked'
        flag (False) to any slot that can take an argument: connected directly, Start called
        start_sweep(False) and never asked for the skew check, and Save As took False for the
        preset name and did nothing (found on 2026-10-07)."""
        a = QAction(text, self)
        a.triggered.connect(lambda *_checked, _slot=slot: _slot())
        if tip:
            a.setToolTip(tip)
        self.toolbar.addAction(a)
        return a

    def _default_sizes(self) -> None:
        """Sizes of the panels at a first start, as shares of the window, so that they fit any
        screen: the strip underneath is low, the right column a good quarter of the width, and
        the waveform as wide as that column, so that its edge lines up with it."""
        d = self.docks
        right = int(0.27 * self.width())
        self.resizeDocks([d["dock_traces"]], [right], Qt.Horizontal)
        self.resizeDocks([d["dock_log"], d["dock_waveform"]], [self.width() - right, right], Qt.Horizontal)
        self.resizeDocks([d["dock_log"]], [int(0.2 * self.height())], Qt.Vertical)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setObjectName("toolbar_main")
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(tb)
        self.toolbar = tb

        act = self._toolbar_action

        tb.addWidget(QLabel(" Mode "))
        self.mode_box = QComboBox()
        self.mode_box.addItem("Instruments", False)
        self.mode_box.addItem("Simulation", True)
        self.mode_box.setToolTip("Real instruments or the built-in simulation, for this session. "
                                 "Disconnect to change it. The mode at start-up is in File > Settings.")
        self.mode_box.activated.connect(lambda i: self.set_mode(bool(self.mode_box.itemData(i))))
        tb.addWidget(self.mode_box)
        self.act_connect = act("Connect", self.toggle_connection,
                               "Open the generator and the scope (or the simulation), or close them again. "
                               "With no addresses set, both instruments are found by themselves.")
        self.act_connections = act("Connections…", self.edit_connections,
                                   "Choose the backend and the addresses of the generator and the scope. "
                                   "Only while disconnected.")
        tb.addSeparator()
        self.act_start = act("Start", self.start_sweep,
                             "Run a sweep with the settings of the Configuration panel. It replaces the live "
                             "sweep on the plot; kept and loaded traces stay.")
        # the one action the window exists for: the only accented button (theme: QToolButton#primary)
        tb.widgetForAction(self.act_start).setObjectName("primary")
        self.act_pause = act("Pause", self.toggle_pause,
                             "Hold the sweep after the point being measured, and go on from there later.")
        self.act_abort = act("Abort", self.abort,
                             "Stop the sweep now. The generator is switched off and the points measured so far "
                             "are kept.")
        tb.addSeparator()
        self.act_skew = act("Skew check", self.open_skew_wizard,
                            "Measure and correct the delay between the two scope channels")
        self.act_cal = act("Calibrate", self.open_cal_dialog,
                           "Through calibration: measure the gain and phase difference between the two "
                           "measurement paths over the full range and remove it from later sweeps")
        self.act_panel = act("Front panel was used", self.front_panel_used,
                             "Tell the app the scope's front panel was used: the skew check is discarded")
        tb.addSeparator()
        export = QToolButton()
        export.setText("Export")
        export.setPopupMode(QToolButton.InstantPopup)
        export.setToolTip("Save the result: CSV (can be loaded again as a trace) and Touchstone hold the live "
                          "sweep; PNG, SVG and PDF show the plot as it is, with every visible trace.")
        menu = QMenu(export)
        for label, fmt in (("CSV…", "csv"), ("PNG…", "png"), ("SVG…", "svg"), ("PDF…", "pdf"),
                           ("Touchstone .s2p…", "s2p")):
            menu.addAction(label, lambda fmt=fmt: self.export_dialog(fmt))
        export.setMenu(menu)
        self.export_button = export
        tb.addWidget(export)
        tb.addSeparator()
        tb.addWidget(QLabel(" Preset "))
        self.preset_box = QComboBox()
        self.preset_box.setMinimumWidth(160)
        self.preset_box.setToolTip("A preset is a saved set of the Configuration panel's settings (sweep, "
                                   "stimulus, scope, measurement), nothing else. Choose one to load it; the status "
                                   "log says what it changed. To make a new one: set the panel, then Save As.")
        tb.addWidget(self.preset_box)
        self.act_preset_save = act("Save", self.save_preset,
                                   "Store the current settings in the preset that is selected.")
        self.act_preset_save_as = act("Save As…", self.save_preset_as,
                                      "Store the current settings as a new preset with a name of your choice.")
        self.act_preset_delete = act("Delete", self.delete_preset,
                                     "Delete the selected preset. The settings on screen stay as they are.")
        tb.addSeparator()
        # File menu only: the toolbar has no room for it, and it is a tab of Settings
        self.act_sim = QAction("Sim settings…", self)
        self.act_sim.triggered.connect(self.edit_sim_settings)
        self.act_sim.setToolTip("The simulated circuit and its noise, for Simulation mode. Only while disconnected.")
        self.act_settings = act("Settings…", self.edit_settings,
                                "Start-up mode, instruments, simulation and the other stored settings")
        self.act_settings.setShortcut("Ctrl+,")
        self.sim_label = QLabel("")
        self.sim_label.setTextFormat(Qt.RichText)
        self.sim_label.setContentsMargins(0, 0, 12, 0)
        self.menuBar().setCornerWidget(self.sim_label, Qt.TopRightCorner)
        self._reload_presets()
        self.preset_box.activated.connect(self._preset_chosen)

    def _build_menus(self) -> None:
        """File, View and Help menus. A closed dock or toolbar comes back from View."""
        mb = self.menuBar()

        m = mb.addMenu("&File")
        m.setToolTipsVisible(True)      # the explanations of the toolbar show in the menus too
        m.addAction(self.act_connect)
        m.addAction(self.act_connections)
        m.addAction(self.act_sim)
        m.addAction(self.act_settings)
        m.addSeparator()
        m.addAction(self.act_skew)
        m.addAction(self.act_cal)
        m.addSeparator()
        self.export_menu = m.addMenu("&Export")
        self.export_menu.setToolTipsVisible(True)
        for label, fmt in (("CSV\u2026", "csv"), ("PNG\u2026", "png"), ("SVG\u2026", "svg"), ("PDF\u2026", "pdf"),
                           ("Touchstone .s2p\u2026", "s2p")):
            self.export_menu.addAction(label, lambda fmt=fmt: self.export_dialog(fmt))
        p = m.addMenu("&Preset")
        p.setToolTipsVisible(True)
        p.addAction(self.act_preset_save)
        p.addAction(self.act_preset_save_as)
        p.addAction(self.act_preset_delete)
        m.addSeparator()
        self.act_quit = m.addAction("E&xit", self.close)
        self.act_quit.setShortcut("Ctrl+Q")

        m = mb.addMenu("&View")
        m.setToolTipsVisible(True)
        self.view_actions = {}
        for name, text in (("dock_config", "&Configuration"), ("dock_waveform", "&Waveform"), ("dock_traces", "&Traces"),
                           ("dock_markers", "&Markers"), ("dock_analysis", "&Analysis"), ("dock_log", "&Status log")):
            a = self.docks[name].toggleViewAction()     # checked while the dock is open
            a.setText(text)
            m.addAction(a)
            self.view_actions[name] = a
        a = self.toolbar.toggleViewAction()
        a.setText("&Toolbar")
        m.addAction(a)
        self.view_actions["toolbar_main"] = a
        m.addSeparator()
        self.act_fit = m.addAction("&Fit view to curves", self.plot.fit_view)
        self.act_fit.setShortcut("Ctrl+F")
        self.act_unwrap = m.addAction("&Unwrap phase")
        self.act_unwrap.setCheckable(True)
        self.act_unwrap.toggled.connect(self.plot.set_unwrap)
        self.plot.unwrap_box.toggled.connect(self.act_unwrap.setChecked)
        m.addSeparator()
        self.act_reset_layout = m.addAction("&Reset layout", self.reset_layout)

        m = mb.addMenu("&Help")
        m.setToolTipsVisible(True)
        self.act_open_logs = m.addAction("Open &log folder", self.open_log_folder)
        self.act_open_config = m.addAction("Open &settings folder", self.open_config_folder)
        m.addSeparator()
        self.act_about = m.addAction("&About Bode plotter", self.show_about)

    def reset_layout(self) -> None:
        """Every dock and the toolbar back where they started, all visible."""
        self.restoreState(self._default_state, LAYOUT_VERSION)
        for dock in self.docks.values():
            dock.setFloating(False)
            dock.show()
        self.toolbar.show()

    def about_text(self) -> str:
        import platform

        import numpy
        import pyqtgraph
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion

        from ..io.settings import config_dir
        from ..logging_setup import log_path
        if self.info.connected:
            mode = "simulation" if self.info.simulated else "instruments"
            conn = "Connected (%s): %s | %s" % (mode, self.info.source_idn, self.info.digitizer_idn)
        else:
            conn = "Not connected (%s)" % ("simulation mode" if self.settings.simulate else "instrument mode")
        return "\n".join([
            "Bode plotter %s" % __version__,
            "Sweeps a function generator and reads an oscilloscope to measure gain and phase.",
            "",
            conn,
            "Correction: " + self.skew_status[1],
            "Real instruments: UNI-T UPO1000 scopes and UTG900E generators over USB (pyvisa-py).",
            "",
            "Python %s, PySide6 %s (Qt %s), pyqtgraph %s, numpy %s" % (
                platform.python_version(), pyside_version, qVersion(), pyqtgraph.__version__, numpy.__version__),
            "Settings: %s" % config_dir(),
            "Log file: %s" % log_path(),
        ])

    def show_about(self) -> None:
        if self.interactive:
            QMessageBox.about(self, "About Bode plotter", self.about_text())

    def _open_folder(self, path) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        path.mkdir(parents=True, exist_ok=True)
        if self.interactive:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_log_folder(self) -> None:
        from ..logging_setup import log_path
        self._open_folder(log_path().parent)

    def open_config_folder(self) -> None:
        from ..io.settings import config_dir
        self._open_folder(config_dir())

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.lbl_state = QLabel("Idle")
        self.lbl_progress = QLabel("")
        self.lbl_time = QLabel("")
        self.lbl_skew = QLabel()
        self.lbl_skew.setTextFormat(Qt.RichText)
        self.skew_status = ("idle", "skew: not connected")      # (state, plain text)
        self._show_skew("idle", "skew: not connected")
        for w in (self.lbl_state, self.lbl_progress, self.lbl_time):
            sb.addWidget(w)
        sb.addPermanentWidget(self.lbl_skew)

    def _show_skew(self, kind: str, text: str) -> None:
        self.skew_status = (kind, text)
        self.lbl_skew.setText(theme.status_html(kind, text, bold=kind == "critical"))

    def cal_in_use(self) -> ThroughCal | None:
        """The connection's through calibration, if it fits the scope settings on screen."""
        cal = self.info.cal if self.info.connected else None
        return cal if calibration.matches(cal, self.config.scope()) else None

    def _refresh_correction(self) -> None:
        """Status bar: the calibration when one applies to the current settings, otherwise
        the skew state as before."""
        info = self.info
        cal = self.cal_in_use()
        if not info.connected:
            self._show_skew("idle", "skew: not connected")
        elif cal is not None:
            self._show_skew("good", calibration.describe(cal))
        elif info.skew_valid:
            self._show_skew("good", info.skew_text)
        else:
            self._show_skew("critical", "skew: UNCHECKED — " + (info.recheck_reason or ""))

    # ------------------------------------------------------------------ settings
    def _load_ui_state(self) -> None:
        s = self.settings
        if s.last_config:
            self.config.set_preset(presets.Preset.from_dict(s.last_config))
        if s.last_preset and s.last_preset in presets.list_presets():
            self.preset_box.setCurrentText(s.last_preset)
        self.plot.set_unwrap(s.unwrap_phase)
        self.plot.set_unit(s.vertical_unit)
        self.plot.set_marker_kinds(s.markers)
        self.plot.set_marker_values(s.marker_values)
        self.plot.set_marker_colors(s.marker_colors)
        self.traces_panel.set_unit(self.plot.unit())
        self.act_unwrap.setChecked(s.unwrap_phase)
        try:
            if s.window_geometry:
                self.restoreGeometry(QByteArray.fromBase64(s.window_geometry.encode("ascii")))
            if s.window_state:
                # a layout stored by another arrangement of the panels is refused: the new one shows
                self.restoreState(QByteArray.fromBase64(s.window_state.encode("ascii")), LAYOUT_VERSION)
        except Exception:                           # a bad saved layout must not stop the app
            log.warning("could not restore the window layout")
        # The panels ticked in Settings > General are shown at start-up (all of them unless the
        # user unticked one), whatever was closed last time; so is the toolbar. The saved layout
        # still decides where they sit and how big they are.
        for name, dock in self.docks.items():
            dock.setVisible(bool(s.startup_panels.get(name, True)))
        self.toolbar.show()

    def _save_ui_state(self) -> None:
        s = self.settings
        s.last_config = self.config.preset().to_dict()
        s.last_preset = self.preset_box.currentText()
        s.unwrap_phase = self.plot.unwrap()
        s.vertical_unit = self.plot.unit()
        s.markers = self.plot.marker_kinds()
        s.marker_values = self.plot.marker_values()
        s.marker_colors = self.plot.marker_colors()
        s.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        s.window_state = bytes(self.saveState(LAYOUT_VERSION).toBase64()).decode("ascii")
        self._save_settings()

    def _save_settings(self) -> None:
        s = self.settings
        if self._stored_simulate is None:
            save_settings(s)
            return
        this_run, s.simulate = s.simulate, self._stored_simulate
        try:
            save_settings(s)
        finally:
            s.simulate = this_run

    # ------------------------------------------------------------------ helpers
    def configs(self) -> Configs:
        c, s = self.config, self.settings
        return Configs(c.sweep(), c.stimulus(), c.scope(), c.measure(),
                       (s.skew_freq_lo_hz, s.skew_freq_hi_hz), int(s.skew_captures))

    def apply_settings(self) -> None:
        """Put the stored settings into effect: explanations, grid colour, debug logging, the
        advanced measurement limits, the analysis numbers, the folder for files. Called at start and after the
        Settings dialog."""
        from ..logging_setup import set_debug
        s = self.settings
        theme.set_tooltips(s.tooltips, s.tooltip_delay_ms)
        theme.set_grid_color(s.grid_color)
        for plot in (self.plot.gain_plot, self.plot.phase_plot, self.waveform.plot):
            theme.style_plot(plot)
        set_debug(s.debug_logging)
        self.config.advanced = measure_overrides(s.advanced)
        numbers = analysis_settings.from_stored(s.analysis)
        self.plot.set_analysis_settings(numbers)
        self.analysis_panel.set_settings(numbers)
        self.traces_panel.folder = self.start_folder()

    def start_folder(self) -> str:
        """Where Export and Load CSV open: the folder set in the settings, else the one used last."""
        return self.settings.export_folder or self.settings.last_folder

    def remember_folder(self, path) -> None:
        """A file was written to or read from this path: its folder is the one used last."""
        self.settings.last_folder = str(Path(path).parent)
        self.traces_panel.folder = self.start_folder()

    def _say(self, level: str, text: str) -> None:
        self.status_log.add_log(LogEntry(level, text, time.strftime("%Y-%m-%dT%H:%M:%S")))

    def _warn_box(self, title: str, text: str) -> None:
        self._say("warn", text)
        if self.interactive:
            QMessageBox.warning(self, title, text)

    def _ask(self, title: str, text: str, buttons=QMessageBox.Yes | QMessageBox.No,
             default=QMessageBox.Yes):
        """Modal question. Non-interactive (tests): returns the default."""
        if not self.interactive:
            return default
        return QMessageBox.question(self, title, text, buttons, default)

    def _on_config_changed(self) -> None:
        self.plot.set_log_x(self.config.sweep().sweep_type is SweepType.LOG)
        sweep = self.config.sweep()
        self.plot.set_span_hint(min(sweep.start_hz, sweep.stop_hz), max(sweep.start_hz, sweep.stop_hz))
        self._refresh_correction()

    def _update_actions(self) -> None:
        busy = self.state in BUSY
        connected = self.info.connected
        self.act_connect.setText("Disconnect" if connected else "Connect")
        self.act_connect.setEnabled(not busy)
        self.act_connections.setEnabled(not busy and not connected)
        self.act_sim.setEnabled(not busy and not connected)
        self.act_start.setEnabled(connected and not busy)
        self.act_pause.setEnabled(self.state in (EngineState.RUNNING, EngineState.PAUSED))
        self.act_pause.setText("Resume" if self.state is EngineState.PAUSED else "Pause")
        self.act_abort.setEnabled(busy and self.state is not EngineState.CONNECTING)
        self.act_skew.setEnabled(connected and not busy)
        self.act_cal.setEnabled(connected and not busy)
        self.act_panel.setEnabled(connected and not busy)
        # an image shows whatever is on the plot; CSV and Touchstone need the live sweep (export says so)
        can_export = (bool(self.result and self.result.points) or self.plot.has_data()) and not busy
        self.export_button.setEnabled(can_export)
        self.export_menu.setEnabled(can_export)
        self.config.setEnabled(not busy)                # inputs are disabled while a sweep runs
        for a in (self.act_preset_save, self.act_preset_save_as, self.act_preset_delete):
            a.setEnabled(not busy)
        self.preset_box.setEnabled(not busy)
        self.plot.remeasure_enabled = connected and not busy and bool(self.result)
        self.act_settings.setEnabled(not busy)
        sim = self.info.simulated if connected else self.settings.simulate
        self.mode_box.setEnabled(not busy and not connected)
        self.mode_box.setCurrentIndex(1 if sim else 0)
        self.sim_label.setText(theme.status_html("warning", "SIMULATION", bold=True) if sim else "")

    # ------------------------------------------------------------------ connection
    def connect_request(self) -> ConnectRequest:
        s, sim = self.settings, self.settings.sim
        return ConnectRequest(simulate=s.simulate, backend=s.backend, source_resource=s.source_resource,
                              digitizer_resource=s.digitizer_resource,
                              sim_preset=sim.get("preset", "rc_lpf"), sim_params=dict(sim.get("params") or {}),
                              sim_noise_vrms=float(sim.get("noise_vrms", 1e-4)),
                              sim_latency_s=float(sim.get("latency_ms", 5.0)) / 1000.0, sim_seed=self.sim_seed,
                              scope_min_gap_ms=float(s.scope_min_gap_ms))

    def toggle_connection(self) -> None:
        if self.info.connected:
            self.engine.disconnect_instruments()
        else:
            self.engine.connect_instruments(self.connect_request())

    def edit_connections(self) -> None:
        d = ConnectionsDialog(self.settings, self, connected=self.info.connected)
        if d.exec():
            d.apply_to(self.settings)
            self._stored_simulate = None        # the user chose: this is now the stored value
            save_settings(self.settings)
            self._update_actions()

    def set_mode(self, simulate: bool) -> None:
        """Instruments or simulation for this session (the Mode box). Only while disconnected."""
        if self.info.connected or self.state in BUSY:
            self._update_actions()              # put the box back
            return
        self.settings.simulate = bool(simulate)
        self._stored_simulate = None            # the user chose: this is now "the mode used last time"
        save_settings(self.settings)
        self._say("info", "Mode: %s." % ("simulation" if simulate else "real instruments"))
        self._update_actions()

    def edit_settings(self) -> None:
        was = self.settings.simulate
        d = SettingsDialog(self.settings, self, connected=self.info.connected,
                           open_folders=(("Open settings folder", self.open_config_folder),
                                         ("Open log folder", self.open_log_folder)))
        if d.exec():
            d.apply_to(self.settings)
            self.apply_settings()
            if self.settings.simulate != was:
                self._stored_simulate = None
            self.act_unwrap.setChecked(self.settings.unwrap_phase)
            self._save_settings()
            self._update_actions()

    def edit_sim_settings(self) -> None:
        d = SimSettingsDialog(self.settings.sim, self)
        if d.exec():
            self.settings.sim = d.result_sim
            self._save_settings()

    # ------------------------------------------------------------------ skew
    def skew_freqs_hint(self) -> tuple[float, float]:
        # the check does not follow the sweep range; its frequencies are a setting of the wizard
        return (self.settings.skew_freq_lo_hz, self.settings.skew_freq_hi_hz)

    def open_skew_wizard(self) -> bool:
        if not self.info.connected:
            return False
        wiz = SkewWizard(self.engine, self.configs, self.info.simulated, self.skew_freqs_hint(), self,
                         settings=self.settings, save=self._save_settings)
        return bool(wiz.exec())

    def open_cal_dialog(self) -> bool:
        if not self.info.connected or self.state in BUSY:
            return False
        dlg = CalDialog(self.engine, self.configs, self.info.simulated, self.info.cal, self)
        ok = bool(dlg.exec())
        self._progress = (0, 0)                     # the calibration used the progress read-out
        self._update_clock()
        return ok

    def front_panel_used(self) -> None:
        self.engine.front_panel_used()

    def _prompt_recheck(self, reason: str) -> None:
        """After a connect, a resync or 'Front panel was used': say so in the status log. No
        pop-up (user decision 2026-10-06: it came up on every connect); the status bar shows
        UNCHECKED, and starting a sweep without a valid check still asks (start_sweep)."""
        self._say("warn", "Skew check needed: " + reason)

    # ------------------------------------------------------------------ sweep control
    def start_sweep(self, check_skew: bool = True) -> bool:
        if not self.info.connected or self.state in BUSY:
            return False
        err = self.config.validation_error()
        if err is None:
            try:
                plan_mod.frequencies(self.config.sweep())
            except plan_mod.PlanError as e:
                err = str(e)
        if err:
            self._warn_box("Sweep", err)
            return False
        # A calibration that covers the whole sweep makes the skew check unnecessary. A Fast
        # preview's phase is rough anyway, so it does not ask either.
        sweep = self.config.sweep()
        lo, hi = min(sweep.start_hz, sweep.stop_hz), max(sweep.start_hz, sweep.stop_hz)
        cal = self.cal_in_use()
        covered = cal is not None and calibration.covers(cal, lo, hi)
        if check_skew and not covered and not self.info.skew_valid \
                and self.config.measure().method is not Method.PREVIEW:
            partly = "" if cal is None else (
                "The through calibration covers %s only; this sweep goes from %s to %s, and the part "
                "outside the calibration needs the skew check.\n\n"
                % (calibration.range_text(cal), fmt_si(lo, "Hz"), fmt_si(hi, "Hz")))
            answer = self._ask(
                "Channel skew",
                partly + (self.info.recheck_reason or "No skew check has been done in this session.") +
                "\n\nWithout it the phase is not corrected: the scope's channels can be 2 ns or more "
                "apart, which is up to 43° at 20 MHz.\n\nRun the skew check first?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.No)
            if answer == QMessageBox.Cancel:
                return False
            if answer == QMessageBox.Yes:
                # set before the wizard runs: its acceptance comes back through the engine
                # as a session update, and that update starts the sweep
                self._pending_sweep = True
                if not self.open_skew_wizard():
                    self._pending_sweep = False
                    return False
                if self.info.skew_valid and self._pending_sweep:
                    self._begin_sweep()
                return True
        self._begin_sweep()
        return True

    def _begin_sweep(self) -> None:
        self._pending_sweep = False
        keep = int(self.settings.auto_keep_sweeps)
        if keep > 0 and self.traces.live.points:        # Settings > Keep previous sweeps
            self._auto_kept.append(self.traces.keep_live().id)
            while len(self._auto_kept) > keep:
                old = self._auto_kept.pop(0)
                if self.traces.get(old) is not None:    # the user may have removed it already
                    self.traces.remove(old)
            self.traces_panel.reload()
            self.plot.traces_changed()
        self.result = None
        self._points = []
        self.plot.clear()
        self.traces_panel.refresh_buttons()
        self.status_log.clear_points()
        self.waveform.clear()
        self._t_start = time.monotonic()
        self._progress = (0, 0)
        self.engine.start_sweep(self.configs())

    def toggle_pause(self) -> None:
        if self.state is EngineState.PAUSED:
            self.engine.resume()
        elif self.state is EngineState.RUNNING:
            self.engine.pause()

    def abort(self) -> None:
        self.engine.abort()

    def remeasure(self, freq_hz: float) -> None:
        if self.result is None or not self.info.connected or self.state in BUSY:
            return
        self.engine.remeasure(self.configs(), self.result, freq_hz)

    # ------------------------------------------------------------------ engine signals
    def _on_point(self, p: PointResult) -> None:
        self._points.append(p)
        self.plot.add_point(p)
        self.status_log.add_point(p)
        self.traces_panel.refresh_buttons()

    def _on_progress(self, i: int, n: int) -> None:
        self._progress = (i, n)
        self._update_clock()

    def _on_state(self, s: EngineState) -> None:
        self.state = s
        self.lbl_state.setText({EngineState.IDLE: "Idle", EngineState.CONNECTING: "Connecting",
                                EngineState.RUNNING: "Running", EngineState.PAUSED: "Paused",
                                EngineState.ABORTING: "Aborting", EngineState.DONE: "Done",
                                EngineState.ERROR: "Error"}[s])
        self._update_actions()

    def _on_finished(self, result: SweepResult) -> None:
        self.result = result
        self.plot.set_points(result.points)             # re-fits the view while it is following
        self._update_clock()
        self._update_actions()
        self.traces_panel.refresh_buttons()

    def _on_remeasured(self, result: SweepResult, point: PointResult) -> None:
        self.result = result
        self.plot.set_points(result.points)
        self._update_actions()
        self.traces_panel.refresh_buttons()

    def _on_error(self, message: str) -> None:
        if self.interactive and not any(w.isVisible() for w in
                                        self.findChildren(SkewWizard) + self.findChildren(CalDialog)):
            QMessageBox.critical(self, "Error", message)

    def _on_session(self, info: SessionInfo) -> None:
        was_connected = self.info.connected
        was_valid, self.info = self.info.skew_valid, info
        if info.connected and not was_connected and self.settings.skew_wizard_on_connect and not info.skew_valid:
            QTimer.singleShot(0, lambda: self.open_skew_wizard())     # Settings > Connect; off by default
        self._refresh_correction()
        if not info.connected or info.skew_valid:
            self._last_reason = None
        self.config.set_has_builtin(info.has_builtin if info.connected else True)
        self.plot.set_has_phase(info.has_phase)
        self._update_actions()
        if info.connected and info.skew_valid and self._pending_sweep:
            self._begin_sweep()
            return
        reason = info.recheck_reason
        if info.connected and not info.skew_valid and reason and reason != self._last_reason:
            self._last_reason = reason
            # the first connect also prompts: the check is per session
            QTimer.singleShot(0, lambda r=reason: self._prompt_recheck(r))

    def _update_clock(self) -> None:
        i, n = self._progress
        self.lbl_progress.setText("%d / %d" % (i, n) if n else "")
        if self.state in (EngineState.RUNNING, EngineState.PAUSED) and self._t_start:
            el = time.monotonic() - self._t_start
            eta = " ETA %s" % _mmss(el / i * (n - i)) if i and n else ""
            self.lbl_time.setText("elapsed %s%s" % (_mmss(el), eta))
        elif self.result is not None and self._t_start and self.state in (EngineState.DONE, EngineState.ERROR):
            pass                                    # keep the last elapsed time on screen
        elif self.state is EngineState.IDLE:
            self.lbl_time.setText("")

    # ------------------------------------------------------------------ presets
    def _reload_presets(self, select: str | None = None) -> None:
        self.preset_box.blockSignals(True)
        self.preset_box.clear()
        self.preset_box.addItem("")
        self.preset_box.addItems(presets.list_presets())
        if select:
            self.preset_box.setCurrentText(select)
        self.preset_box.blockSignals(False)

    def _preset_chosen(self, _index: int) -> None:
        name = self.preset_box.currentText()
        if name:
            before = self.config.preset()
            self.config.set_preset(presets.load_preset(name))
            changed = presets.describe_changes(before, self.config.preset())
            if not changed:
                # two presets saved from the same settings made the box look dead (user report 2026-10-07)
                self._say("info", "Loaded preset '%s': it holds the settings that were already on screen, so "
                                  "nothing changed. %s" % (name, presets.WHAT_A_PRESET_HOLDS))
            else:
                more = "; and %d more" % (len(changed) - 8) if len(changed) > 8 else ""
                self._say("info", "Loaded preset '%s': %d setting%s changed: %s%s." % (
                    name, len(changed), "" if len(changed) == 1 else "s", "; ".join(changed[:8]), more))

    def save_preset(self) -> None:
        name = self.preset_box.currentText()
        if not name:
            self.save_preset_as()
            return
        presets.save_preset(name, self.config.preset())
        self._say("info", "Saved preset '%s'." % name)

    def save_preset_as(self, name: str | None = None) -> None:
        if name is None:
            name, ok = QInputDialog.getText(self, "Save preset", "Preset name:")
            if not ok:
                return
        try:
            path = presets.save_preset(name, self.config.preset())
        except ValueError as e:
            self._warn_box("Preset", str(e))
            return
        self._reload_presets(path.stem)
        self._say("info", "Saved preset '%s'." % path.stem)

    def delete_preset(self) -> None:
        name = self.preset_box.currentText()
        if not name:
            return
        if self._ask("Delete preset", "Delete preset '%s'?" % name) != QMessageBox.Yes:
            return
        presets.delete_preset(name)
        self._reload_presets()

    # ------------------------------------------------------------------ export
    def export(self, path, fmt: str | None = None, image_opts: export_image.ImageOptions | None = None) -> Path:
        """Write an export. fmt is taken from the file extension when omitted. An image shows
        what the plot shows (any trace, with or without a sweep); CSV and Touchstone hold the
        live sweep."""
        path = Path(path)
        fmt = (fmt or path.suffix.lstrip(".")).lower()
        if fmt in export_image.FORMATS:
            series, labels = self.plot.export_series()
            if not any(len(s.freqs) for s in series):
                raise ValueError("there is nothing on the plot to export")
            o = image_opts or self._image_opts
            o = export_image.ImageOptions(o.title, o.dpi, o.width_in, o.height_in, self.plot.unwrap(),
                                          self.config.sweep().sweep_type is SweepType.LOG, self.info.has_phase, self.plot.unit())
            out = export_image.write_image(path, self.result or SweepResult({}, [], {}), o, series, labels,
                                           markers=self.plot.export_markers())
        elif fmt not in ("csv", "s2p"):
            raise ValueError("unknown export format %r" % fmt)
        elif self.result is None:
            raise ValueError("there is no sweep to export: CSV and Touchstone hold the live sweep")
        elif fmt == "csv":
            out = export_csv.write_csv(path, self.result)
        else:
            out = export_touchstone.write_touchstone(path, self.result)
        self._say("info", "Exported %s" % out)
        return out

    def export_dialog(self, fmt: str) -> None:
        if self.result is None and fmt not in export_image.FORMATS:
            self._warn_box("Export", "There is no sweep to export: CSV and Touchstone hold the live sweep.")
            return
        opts = None
        if fmt in export_image.FORMATS:
            d = ImageExportDialog(self._image_opts, self)
            if not d.exec():
                return
            opts = self._image_opts = d.options(self.plot.unwrap(), True, True)
        start = str(Path(self.start_folder()) / ("bode." + fmt)) if self.start_folder() else "bode." + fmt
        path, _ = QFileDialog.getSaveFileName(self, "Export", start, "*." + fmt)
        if not path:
            return
        try:
            self.export(path if path.lower().endswith("." + fmt) else path + "." + fmt, fmt, opts)
            self.remember_folder(path)
        except Exception as e:
            self._warn_box("Export", "Export failed: %s" % e)

    # ------------------------------------------------------------------ closing
    def closeEvent(self, event) -> None:
        if self.state in BUSY and self.interactive:
            if QMessageBox.question(self, "Quit", "A sweep is running. Abort it and quit?") != QMessageBox.Yes:
                event.ignore()
                return
        self._save_ui_state()
        self.engine.shutdown()              # aborts cleanly and switches the generator off
        event.accept()


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return "%d:%02d" % (seconds // 60, seconds % 60)
