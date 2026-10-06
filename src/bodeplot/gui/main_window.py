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
from ..io.settings import AppSettings, load_settings, save_settings
from ..measure import skew
from ..models import EngineState, LogEntry, PointResult, SweepResult, SweepType
from ..sweep import plan as plan_mod
from ..sweep.engine import Configs, ConnectRequest, SessionInfo, SweepEngine
from . import theme
from .bode_plot import BodePlot
from .config_panel import ConfigPanel
from .dialogs import ConnectionsDialog, ImageExportDialog, SettingsDialog, SimSettingsDialog, SkewWizard
from .status_log import StatusLog
from .waveform_view import WaveformView

log = logging.getLogger("bodeplot.gui")
BUSY = (EngineState.CONNECTING, EngineState.RUNNING, EngineState.PAUSED, EngineState.ABORTING)


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
        self.interactive = True         # tests switch this off: no modal dialogs
        self.info = SessionInfo()
        self.state = EngineState.IDLE
        self.result: SweepResult | None = None
        self._points: list[PointResult] = []
        self._t_start = 0.0
        self._progress = (0, 0)
        self._pending_sweep = False
        self._last_reason: str | None = None
        self._image_opts = export_image.ImageOptions()

        app = QApplication.instance()
        if app is not None:
            theme.apply(app)                # before any plot widget is created
        self.setWindowTitle("Bode plotter %s" % __version__)
        self.resize(1400, 860)
        self.docks: dict[str, QDockWidget] = {}
        self.plot = BodePlot()
        self.setCentralWidget(self.plot)
        self.config = ConfigPanel()
        self.waveform = WaveformView()
        self.status_log = StatusLog()
        for title, name, widget, area in (
                ("Configuration", "dock_config", self.config, Qt.LeftDockWidgetArea),
                ("Waveform", "dock_waveform", self.waveform, Qt.RightDockWidgetArea),
                ("Status log", "dock_log", self.status_log, Qt.BottomDockWidgetArea)):
            dock = QDockWidget(title, self)
            dock.setObjectName(name)
            dock.setWidget(widget)
            self.addDockWidget(area, dock)
            self.docks[name] = dock

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

        self._build_toolbar()
        self._build_menus()
        self._build_statusbar()
        self._default_state = self.saveState()      # the layout "Reset layout" goes back to
        self._load_ui_state()
        self.config.changed.connect(self._on_config_changed)
        self._on_config_changed()
        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._update_clock)
        self._tick.start()
        self._update_actions()

    # ------------------------------------------------------------------ UI construction
    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setObjectName("toolbar_main")
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(tb)
        self.toolbar = tb

        def act(text, slot, tip=""):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if tip:
                a.setToolTip(tip)
            tb.addAction(a)
            return a

        tb.addWidget(QLabel(" Mode "))
        self.mode_box = QComboBox()
        self.mode_box.addItem("Instruments", False)
        self.mode_box.addItem("Simulation", True)
        self.mode_box.setToolTip("Real instruments or the built-in simulation, for this session. "
                                 "Disconnect to change it. The mode at start-up is in File > Settings.")
        self.mode_box.activated.connect(lambda i: self.set_mode(bool(self.mode_box.itemData(i))))
        tb.addWidget(self.mode_box)
        self.act_connect = act("Connect", self.toggle_connection)
        self.act_connections = act("Connections…", self.edit_connections)
        tb.addSeparator()
        self.act_start = act("Start", self.start_sweep)
        self.act_pause = act("Pause", self.toggle_pause)
        self.act_abort = act("Abort", self.abort)
        tb.addSeparator()
        self.act_skew = act("Skew check", self.open_skew_wizard,
                            "Measure and correct the delay between the two scope channels")
        self.act_panel = act("Front panel was used", self.front_panel_used,
                             "Tell the app the scope's front panel was used: the skew check is discarded")
        tb.addSeparator()
        export = QToolButton()
        export.setText("Export")
        export.setPopupMode(QToolButton.InstantPopup)
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
        tb.addWidget(self.preset_box)
        self.act_preset_save = act("Save", self.save_preset)
        self.act_preset_save_as = act("Save As…", self.save_preset_as)
        self.act_preset_delete = act("Delete", self.delete_preset)
        tb.addSeparator()
        # File menu only: the toolbar has no room for it, and it is a tab of Settings
        self.act_sim = QAction("Sim settings…", self)
        self.act_sim.triggered.connect(self.edit_sim_settings)
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
        m.addAction(self.act_connect)
        m.addAction(self.act_connections)
        m.addAction(self.act_sim)
        m.addAction(self.act_settings)
        m.addSeparator()
        self.export_menu = m.addMenu("&Export")
        for label, fmt in (("CSV\u2026", "csv"), ("PNG\u2026", "png"), ("SVG\u2026", "svg"), ("PDF\u2026", "pdf"),
                           ("Touchstone .s2p\u2026", "s2p")):
            self.export_menu.addAction(label, lambda fmt=fmt: self.export_dialog(fmt))
        p = m.addMenu("&Preset")
        p.addAction(self.act_preset_save)
        p.addAction(self.act_preset_save_as)
        p.addAction(self.act_preset_delete)
        m.addSeparator()
        self.act_quit = m.addAction("E&xit", self.close)
        self.act_quit.setShortcut("Ctrl+Q")

        m = mb.addMenu("&View")
        self.view_actions = {}
        for name, text in (("dock_config", "&Configuration"), ("dock_waveform", "&Waveform"),
                           ("dock_log", "&Status log")):
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
        self.act_open_logs = m.addAction("Open &log folder", self.open_log_folder)
        self.act_open_config = m.addAction("Open &settings folder", self.open_config_folder)
        m.addSeparator()
        self.act_about = m.addAction("&About Bode plotter", self.show_about)

    def reset_layout(self) -> None:
        """Every dock and the toolbar back where they started, all visible."""
        self.restoreState(self._default_state)
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
            "Channel " + self.skew_status[1],
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

    # ------------------------------------------------------------------ settings
    def _load_ui_state(self) -> None:
        s = self.settings
        if s.last_config:
            self.config.set_preset(presets.Preset.from_dict(s.last_config))
        if s.last_preset and s.last_preset in presets.list_presets():
            self.preset_box.setCurrentText(s.last_preset)
        self.plot.set_unwrap(s.unwrap_phase)
        self.act_unwrap.setChecked(s.unwrap_phase)
        try:
            if s.window_geometry:
                self.restoreGeometry(QByteArray.fromBase64(s.window_geometry.encode("ascii")))
            if s.window_state:
                self.restoreState(QByteArray.fromBase64(s.window_state.encode("ascii")))
        except Exception:                           # a bad saved layout must not stop the app
            log.warning("could not restore the window layout")
        # Every panel and the toolbar are shown at start-up, whatever was closed last time.
        # The saved layout still decides where they sit and how big they are.
        for dock in self.docks.values():
            dock.show()
        self.toolbar.show()

    def _save_ui_state(self) -> None:
        s = self.settings
        s.last_config = self.config.preset().to_dict()
        s.last_preset = self.preset_box.currentText()
        s.unwrap_phase = self.plot.unwrap()
        s.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        s.window_state = bytes(self.saveState().toBase64()).decode("ascii")
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
        c = self.config
        return Configs(c.sweep(), c.stimulus(), c.scope(), c.measure())

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
        self.act_panel.setEnabled(connected and not busy)
        can_export = bool(self.result and self.result.points) and not busy
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
        sw = self.config.sweep()
        return skew.check_frequencies(min(30e6, 50e6, max(sw.start_hz, sw.stop_hz)))

    def open_skew_wizard(self) -> bool:
        if not self.info.connected:
            return False
        wiz = SkewWizard(self.engine, self.configs, self.info.simulated, self.skew_freqs_hint(), self)
        return bool(wiz.exec())

    def front_panel_used(self) -> None:
        self.engine.front_panel_used()

    def _prompt_recheck(self, reason: str) -> None:
        """SPEC 8.6: prompt after reconnect, after any resync, and when the front panel was used."""
        self._say("warn", "Skew check needed: " + reason)
        if not self.interactive or self.state in BUSY:
            return
        if self._ask("Channel skew check", reason + "\n\nRun the skew check now?") == QMessageBox.Yes:
            self.open_skew_wizard()

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
        if check_skew and not self.info.skew_valid:
            answer = self._ask(
                "Channel skew",
                (self.info.recheck_reason or "No skew check has been done in this session.") +
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
        self.result = None
        self._points = []
        self.plot.clear()
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

    def _on_remeasured(self, result: SweepResult, point: PointResult) -> None:
        self.result = result
        self.plot.set_points(result.points)
        self._update_actions()

    def _on_error(self, message: str) -> None:
        if self.interactive and not any(isinstance(w, SkewWizard) and w.isVisible()
                                        for w in self.findChildren(SkewWizard)):
            QMessageBox.critical(self, "Error", message)

    def _on_session(self, info: SessionInfo) -> None:
        was_valid, self.info = self.info.skew_valid, info
        if not info.connected:
            self._show_skew("idle", "skew: not connected")
            self._last_reason = None
        elif info.skew_valid:
            self._show_skew("good", info.skew_text)
            self._last_reason = None
        else:
            self._show_skew("critical", "skew: UNCHECKED — " + (info.recheck_reason or ""))
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
            self.config.set_preset(presets.load_preset(name))
            self._say("info", "Loaded preset '%s'." % name)

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
        """Write the current result. fmt is taken from the file extension when omitted."""
        if self.result is None:
            raise ValueError("there is no result to export")
        path = Path(path)
        fmt = (fmt or path.suffix.lstrip(".")).lower()
        if fmt == "csv":
            out = export_csv.write_csv(path, self.result)
        elif fmt == "s2p":
            out = export_touchstone.write_touchstone(path, self.result)
        elif fmt in export_image.FORMATS:
            o = image_opts or self._image_opts
            o = export_image.ImageOptions(o.title, o.dpi, o.width_in, o.height_in, self.plot.unwrap(),
                                          self.config.sweep().sweep_type is SweepType.LOG, self.info.has_phase)
            out = export_image.write_image(path, self.result, o)
        else:
            raise ValueError("unknown export format %r" % fmt)
        self._say("info", "Exported %s" % out)
        return out

    def export_dialog(self, fmt: str) -> None:
        if self.result is None:
            return
        opts = None
        if fmt in export_image.FORMATS:
            d = ImageExportDialog(self._image_opts, self)
            if not d.exec():
                return
            opts = self._image_opts = d.options(self.plot.unwrap(), True, True)
        path, _ = QFileDialog.getSaveFileName(self, "Export", "bode." + fmt, "*." + fmt)
        if not path:
            return
        try:
            self.export(path if path.lower().endswith("." + fmt) else path + "." + fmt, fmt, opts)
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
