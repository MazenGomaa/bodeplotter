# Architecture map

Modules, what calls what, and where each concern lives. Kept by hand, checked by a test: `tests/test_docs.py` reads the module table below and fails when a module is missing from it, when a listed module no longer exists, or when a module's imports differ from its row. So this file cannot go stale silently. When that test fails, update the row (and the text around it, if the change moved a concern).

Design detail is in `docs/SPEC.md` and `docs/spec/`; what the hardware really does is in `HW_REPORT.md`.

## The chain of one measurement

One measurement goes down this chain; each layer talks to the one below it.

1. **GUI** (`gui/main_window.py` and the panels) builds the config dataclasses in `models.py` (`SweepConfig`, `StimulusConfig`, `ScopeConfig`, `MeasureSettings`) and talks only to `SweepEngine`. It never touches an instrument.
2. **`sweep/engine.py`**: `SweepEngine` owns a QThread with an `EngineWorker`. Requests go in as queued signals, results come back as signals; pause / resume / abort are called directly on the worker (flags only). It holds the one `Session` and drops it when the watchdog marks it dead.
3. **`sweep/core.py`** (no Qt, so it is what the tests and `hwcheck/m7_*.py` drive): `Session` = one source + one digitizer + the skew check and the through calibration that belong to that connection; `SweepRunner` walks the plan from `sweep/plan.py`, reports through `Callbacks`, applies the through calibration or the skew correction (the pure decisions of the calibration are in `sweep/calibration.py`) and guarantees `safe_off` and the scope restore on every exit path.
4. **`measure/meters.py`**: `DualChannelScopeMeter` does one frequency point: timebase from the step table, auto-range (`sweep/autorange.py` holds the pure decisions), capture, then `measure/sinefit.py` or the scope's built-in measurement. It returns a `PointResult` with `Flag`s.
5. **Drivers** (`drivers/base.py`: `SignalSource`, `Digitizer`, `Waveform`, caps). `drivers/registry.py` maps an `*IDN?` string to a driver class; `drivers/connect.py` scans, picks and opens a real `Session`. `drivers/mock.py` implements the same interfaces with a `SimulatedDUT` (this is Simulation mode).
6. **`drivers/transport.py`**: the real drivers speak SCPI through a `Transport`. `VisaTransport` is the only place a VISA resource is opened (`drivers/visa_util.py` holds the `BODEPLOT_NO_HARDWARE` guard). `drivers/scpi.py` has the command descriptions, reply validators and the driver error types (`InstrumentUnresponsive` is what triggers the watchdog).

Persistence (`io/`): settings and presets are JSON in the user config folder, loaded through `models.from_dict`, which falls back to defaults field by field; exports are CSV (round-trips), image, Touchstone.

**Traces on the plot** are outside that chain. `traces.py` holds results for display (the live sweep, kept sweeps, CSV files, theory curves from `measure/theory.py`) and the maths of the relative display; the plot and the image export ask it what is to be drawn. Nothing below the GUI knows it.

**Markers** are outside it too. `markers.py` holds what is switched on and the rules; `measure/response.py` is the maths on one curve, which `traces.py` also uses for the reference trace and which v3 (response metrics) is to build on. `gui/markers_panel.py` holds the controls and follows the plot's `markers_changed`. The plot asks `TraceSet.curve` for the chosen trace, lets `MarkerSet.evaluate` read it, and hands texts and positions to `gui/marker_layer.py` and to the image export.

**The analysis** (v3, part 1) sits beside the markers. `measure/metrics.py` reads the shape of one curve; `markers.py` takes its −3 dB cut-offs from it (`passband`, `marker_pair`) and leaves out the same noisy ends (`noise_ends`, `without_noise`), so the marker and the Analysis table show the same cut-off. `analysis.py` turns a `Metrics` into rows of text; `gui/analysis_panel.py` asks the plot for a trace as a curve (`BodePlot.analysis_curve`: always absolute and in dB) when Analyse is pressed, and follows the plot's `markers_changed` only to tell whether its table is still current. Every threshold of the analysis is a field of `measure/analysis_settings.py` (the user, 2026-11-02: no hard-coded value), stored in `AppSettings.analysis` and edited on the Settings dialog's Analysis tab; `MainWindow.apply_settings` hands the same `AnalysisSettings` to the plot (for the −3 dB marker) and to the panel. The classification (v3, part 3) sits on top of the metrics: `measure/classify.py` reads one `Metrics` and its `Curve` and gives a type, shape words, a confidence with its reasons, or a refusal; `analysis.py` shows it as the Type group first and its reasons first in the notes; the panel calls it after `metrics.analyse`. A flag on every point (skew unchecked) reaches it as `Curve.wide_flags`, a flag on single points as `Curve.point_flagged` (both filled by `BodePlot.analysis_curve`).

## Two levels of simulation

- `drivers/mock.py` replaces the drivers. Used by `--sim`, the GUI tests and the sweep / skew tests (`make_session` fixture in `tests/conftest.py`).
- `tests/fakes.py` (`FakeScope`, `FakeGen`, `FakeClock`) replaces the Transport under the REAL drivers, reproduces the faults in `HW_REPORT.md` and records forbidden commands. Time is virtual, so pacing and arm sequences are asserted exactly.

## Modules

Paths are relative to `src/bodeplot/`. "Imports" lists the modules of this package that the file imports, nothing else; the test compares it with the source. Empty `__init__.py` files are not listed.

| Module | What it is | Imports |
|---|---|---|
| `__init__.py` | package version | - |
| `__main__.py` | entry point: `python -m bodeplot [--sim] [--debug]` | `__init__.py`, `app.py` |
| `analysis.py` | the Analysis table as text: the Type group, rows for one trace or two with their difference, notes, clipboard text, the groups' rules with the numbers in force; no Qt | `measure/analysis_settings.py`, `measure/classify.py`, `measure/metrics.py`, `units.py` |
| `app.py` | QApplication bootstrap, theme, main window | `gui/main_window.py`, `gui/theme.py`, `logging_setup.py` |
| `logging_setup.py` | rotating log file, `log_path()` | - |
| `markers.py` | the markers of the Bode plot: what is switched on, the user's markers, the rules (-3 dB, peak, notch, margins), label and clipboard texts; no Qt | `measure/analysis_settings.py`, `measure/metrics.py`, `measure/response.py`, `units.py` |
| `models.py` | config dataclasses, `PointResult`, `SkewCheck`, `SweepResult`, `Flag`, `from_dict` / `to_jsonable` | - |
| `traces.py` | the traces of the Bode plot (live, kept, file, theory), the relative-to maths, a trace as a response curve | `measure/response.py`, `measure/theory.py`, `models.py` |
| `units.py` | SI prefixes: `fmt_si`, `parse_si` | - |
| `drivers/base.py` | interfaces `SignalSource`, `Digitizer`; `Waveform`; capability dataclasses; `DriverError` | - |
| `drivers/connect.py` | scan the bus, pick by `*IDN?`, open a real `Session` | `drivers/base.py`, `drivers/registry.py`, `drivers/step_tables.py`, `drivers/transport.py`, `drivers/visa_util.py`, `io/settings.py`, `sweep/core.py` |
| `drivers/mock.py` | `MockSource`, `MockScope`, `SimulatedDUT` (Simulation mode) | `drivers/base.py`, `drivers/step_tables.py`, `measure/theory.py` |
| `drivers/registry.py` | `*IDN?` string to driver class | - |
| `drivers/scpi.py` | command descriptions, reply validators, `InstrumentUnresponsive`, `BlockedCommand` | `drivers/base.py` |
| `drivers/step_tables.py` | shipped timebase and V/div tables per model and firmware; the user's walked tables | `io/settings.py` |
| `drivers/transport.py` | `Transport` interface, `VisaTransport`, USBTMC device clear through pyusb | `drivers/visa_util.py` |
| `drivers/uni_t_upo1000.py` | scope driver `UniTUPO1000`: single shot, running read, resync, panel lock, save / restore of the settings | `drivers/base.py`, `drivers/scpi.py`, `drivers/step_tables.py`, `drivers/transport.py` |
| `drivers/uni_t_utg900e.py` | generator driver `UniTUTG900E` | `drivers/base.py`, `drivers/scpi.py`, `drivers/transport.py` |
| `drivers/visa_util.py` | the only pyvisa import: resource manager, discovery, the `BODEPLOT_NO_HARDWARE` guard | - |
| `gui/analysis_panel.py` | the Analysis dock: the trace to analyse and the one to compare with, Analyse / Copy table, the table in groups, the line that says when it is old (trace or settings changed), the notes | `analysis.py`, `gui/theme.py`, `measure/analysis_settings.py`, `measure/classify.py`, `measure/metrics.py` |
| `gui/bode_plot.py` | gain and phase plots of a trace set, the difference display, follow / fit view, vertical unit, re-measure request; the markers' state, texts and positions, the right-click menus | `gui/color_menu.py`, `gui/marker_layer.py`, `gui/si_widgets.py`, `gui/theme.py`, `io/export_image.py`, `markers.py`, `measure/sinefit.py`, `models.py`, `traces.py`, `units.py` |
| `gui/color_menu.py` | the marker palette as a pop-up grid of colour squares | `gui/theme.py` |
| `gui/config_panel.py` | the input panel; builds the config dataclasses and presets | `gui/si_widgets.py`, `io/presets.py`, `models.py` |
| `gui/dialogs.py` | settings, connections, simulation settings, the circuit form and theory dialog, image export, skew wizard, calibration dialog | `drivers/connect.py`, `drivers/registry.py`, `drivers/visa_util.py`, `gui/si_widgets.py`, `gui/theme.py`, `io/export_image.py`, `io/settings.py`, `measure/analysis_settings.py`, `measure/skew.py`, `measure/theory.py`, `models.py`, `sweep/calibration.py`, `units.py` |
| `gui/main_window.py` | toolbar, menus, status bar, sweep control, exports; the engine's only client | `__init__.py`, `gui/analysis_panel.py`, `gui/bode_plot.py`, `gui/config_panel.py`, `gui/dialogs.py`, `gui/markers_panel.py`, `gui/status_log.py`, `gui/theme.py`, `gui/traces_panel.py`, `gui/waveform_view.py`, `io/export_csv.py`, `io/export_image.py`, `io/export_touchstone.py`, `io/presets.py`, `io/settings.py`, `logging_setup.py`, `measure/analysis_settings.py`, `measure/skew.py`, `models.py`, `sweep/calibration.py`, `sweep/engine.py`, `sweep/plan.py`, `traces.py`, `units.py` |
| `gui/marker_layer.py` | the markers as graphics on both plots: lines, dots, labels that do not overlap, dragging | `gui/theme.py`, `markers.py` |
| `gui/markers_panel.py` | the Markers dock: the trace the markers measure, the automatic markers' tick boxes, the table of values with a colour square per marker, add / remove / copy, values on the plot | `gui/bode_plot.py`, `gui/color_menu.py`, `gui/theme.py`, `markers.py` |
| `gui/si_widgets.py` | k / M number entry, SI axis | `units.py` |
| `gui/status_log.py` | point table and log text | `models.py`, `units.py` |
| `gui/theme.py` | every colour of the app, `status_html` | - |
| `gui/traces_panel.py` | the Traces dock: the list of traces; load CSV, add theory, keep, remove | `gui/dialogs.py`, `gui/theme.py`, `io/export_csv.py`, `measure/theory.py`, `traces.py` |
| `gui/waveform_view.py` | the two captured waveforms with their fits | `gui/theme.py`, `models.py`, `units.py` |
| `io/export_csv.py` | CSV writer and loader, the skew and calibration header lines | `measure/sinefit.py`, `measure/skew.py`, `models.py`, `sweep/calibration.py` |
| `io/export_image.py` | PNG / SVG / PDF with matplotlib | `io/export_csv.py`, `measure/sinefit.py`, `models.py` |
| `io/export_touchstone.py` | `.s2p` writer | `io/export_csv.py`, `models.py` |
| `io/presets.py` | presets as JSON files; what differs between two sets of settings | `io/settings.py`, `models.py`, `units.py` |
| `io/settings.py` | `AppSettings`, the config folder (`BODEPLOT_CONFIG_DIR`) | `drivers/visa_util.py`, `measure/analysis_settings.py` |
| `measure/analysis_settings.py` | every number of the analysis as a setting: `AnalysisSettings`, `FIELDS` (default, range, unit, tooltip), what is stored; no Qt | - |
| `measure/builtin.py` | gain and phase from the scope's own measurements (simulation only) | `drivers/base.py` |
| `measure/meters.py` | `DualChannelScopeMeter`: one frequency point, auto-range, bad-capture retry | `drivers/base.py`, `drivers/scpi.py`, `measure/builtin.py`, `measure/sinefit.py`, `models.py`, `sweep/autorange.py` |
| `measure/classify.py` | what kind of circuit one response is: the type, shape words, the confidence with its reasons, the refusals, from part 1's `Metrics`; no Qt | `measure/analysis_settings.py`, `measure/metrics.py`, `measure/response.py`, `units.py` |
| `measure/metrics.py` | what the shape of one response curve says: flat stretches, passband level and ripple, cut-offs, slope and order, stopband attenuation, resonances with Q from width and phase, the ends lost in the noise; no Qt | `measure/analysis_settings.py`, `measure/response.py` |
| `measure/response.py` | one response curve (gain in dB, unwrapped phase): value at a frequency, level crossings, refined extremes; no Qt | - |
| `measure/sinefit.py` | sine fit, SNR, `gain_phase`, `unwrap_deg` | - |
| `measure/theory.py` | transfer functions of ideal circuits: the simulated DUT and the plot's theory curves | `units.py` |
| `measure/skew.py` | channel skew: delay from H, correction, evaluation, texts | `models.py` |
| `sweep/autorange.py` | pure V/div and timebase decisions | - |
| `sweep/calibration.py` | through calibration, the pure part: frequencies, interpolation, plausibility, validity against the scope settings | `models.py`, `sweep/plan.py`, `units.py` |
| `sweep/core.py` | `Session`, `run_skew_check`, `run_through_cal`, `SweepRunner`, watchdog message, bad-capture files | `__init__.py`, `drivers/base.py`, `drivers/mock.py`, `drivers/scpi.py`, `measure/meters.py`, `measure/sinefit.py`, `measure/skew.py`, `models.py`, `sweep/calibration.py`, `sweep/plan.py` |
| `sweep/engine.py` | `SweepEngine` / `EngineWorker`: the QThread around `core.py` | `drivers/base.py`, `drivers/connect.py`, `drivers/mock.py`, `logging_setup.py`, `measure/meters.py`, `measure/skew.py`, `models.py`, `sweep/calibration.py`, `sweep/core.py` |
| `sweep/plan.py` | frequency list and range checks | `models.py`, `units.py` |
| `tools/probe.py` | probe tool: exercises every driver command on the real instruments | `__init__.py`, `drivers/base.py`, `drivers/connect.py`, `drivers/scpi.py`, `drivers/step_tables.py`, `drivers/uni_t_upo1000.py`, `drivers/uni_t_utg900e.py`, `io/settings.py` |

Not a clean stack, and known: `drivers/connect.py` imports `sweep/core.py` (it returns a `Session`), `sweep/core.py` imports `drivers/mock.py` (`Session.simulated_session`), and `drivers/step_tables.py` and `io/settings.py` import across `drivers/` and `io/` for the config folder and the VISA guard.

## Rules the tests enforce

| Rule | Test |
|---|---|
| Qt (PySide6, pyqtgraph) only in `gui/`, `app.py` and `sweep/engine.py` | `tests/test_docs.py` |
| pyvisa only in `drivers/visa_util.py`; pyusb only in `drivers/transport.py` | `tests/test_docs.py` |
| the app never imports `hwcheck/` (the dependency runs the other way) | `tests/test_docs.py` |
| every option of the GUI has a tooltip that explains it; tooltips wait 3 s | `tests/test_gui_tooltips.py` |
| no `:RUN` and no `subprocess` anywhere in `src/` | `tests/test_drivers.py` |
| no test reaches a real instrument (`BODEPLOT_NO_HARDWARE` in `tests/conftest.py`) | `tests/conftest.py`, `drivers/visa_util.py` |

## Where each concern lives

| Concern | Where |
|---|---|
| Generator off on every exit path | `sweep/core.py`: the `finally` blocks of `SweepRunner.run`, `remeasure`, `run_skew_check`, `run_through_cal`; `Session.close` |
| Scope settings saved and restored, panel lock | `Session.begin_measurement` / `end_measurement` in `sweep/core.py`; `save_setup` / `restore_setup` / `lock_panel` in `drivers/uni_t_upo1000.py` |
| Watchdog (instrument stops answering) | raised as `InstrumentUnresponsive` (`drivers/scpi.py`) by the drivers; handled in `sweep/core.py` (`Session.mark_dead`, `watchdog_message`); the engine closes the session (`EngineWorker._drop_if_dead`) |
| Generator off while the scope is being resynchronised | `Digitizer.on_link_trouble`, `Session._link_trouble`, `measure_with_output` in `sweep/core.py` |
| Skew check: validity per connection | `Session.skew_valid` and `alignment_epoch` in `sweep/core.py`; the maths in `measure/skew.py`; the wizard in `gui/dialogs.py` |
| Through calibration: measuring, validity, applying | `run_through_cal`, `Session.cal_for` and `SweepRunner._correct` in `sweep/core.py`; the maths and the plausibility rules in `sweep/calibration.py`; `CalDialog` in `gui/dialogs.py`; the status text in `gui/main_window.py` (`cal_in_use`) |
| Traces on the plot (overlay, theory curves, relative display) | the model and the maths in `traces.py`; drawing in `gui/bode_plot.py`; the list and its buttons in `gui/traces_panel.py`; the circuits in `measure/theory.py`; several series in an image in `io/export_image.py` |
| Markers (−3 dB, peak, notch, margins, user markers) | rules and texts in `markers.py`; curve maths in `measure/response.py`; the chosen trace as a curve in `traces.py` (`TraceSet.curve`); state, texts in the plot's unit and positions in `gui/bode_plot.py`; the controls and the table in `gui/markers_panel.py`; the palette in `gui/theme.py` (`MARKER_PALETTE`, `MARKER_DEFAULTS`), its pop-up grid in `gui/color_menu.py`, its print twins in `io/export_image.py` (`PRINT_MARKERS`); graphics and label placement in `gui/marker_layer.py`; in an image in `io/export_image.py` (`_place_labels`) |
| Analysis (type, passband, cut-offs, slope and order, attenuation, resonances) | the maths in `measure/metrics.py` and the type in `measure/classify.py`, every threshold in `measure/analysis_settings.py`; rows, difference, notes and clipboard text in `analysis.py`; the trace as a curve in `gui/bode_plot.py` (`analysis_curve`); the controls, the table and the stale line in `gui/analysis_panel.py`; the dock in `gui/main_window.py` |
| Auto-range | decisions in `sweep/autorange.py`, the loop in `measure/meters.py` |
| Step tables, pacing after range changes | `drivers/step_tables.py`; `scope_min_gap_ms` in `io/settings.py`, applied in `drivers/uni_t_upo1000.py` |
| Single-shot capture, stale-record check, resync | `drivers/uni_t_upo1000.py` (`acquire`, `acquire_running`) |
| Negative generator offset | `UniTUTG900E._set_level` in `drivers/uni_t_utg900e.py` |
| Bad-capture files | `save_bad_capture` in `sweep/core.py`, called from `measure/meters.py` |
| Tooltip texts and their delay | the texts next to each widget (`TIPS` in `gui/config_panel.py` for the Configuration panel); the 3 s delay in `gui/theme.py` (`TOOLTIP_DELAY_MS`) |
| Colours | `gui/theme.py` only (the white-background image export is the one exception) |
| Settings and presets on disk | `io/settings.py`, `io/presets.py`, `models.from_dict` |
| Settings taking effect | `MainWindow.apply_settings` in `gui/main_window.py` (explanations and grid colour through `gui/theme.py`, debug logging through `logging_setup.set_debug`, the advanced measurement limits through `ConfigPanel.advanced`); `settings.measure_overrides` checks the advanced values; the skew check's own settings travel in `Configs.skew_freqs` / `skew_captures` to `core.run_skew_check` |
| Opening a VISA resource | `drivers/transport.py` (`VisaTransport`) through `drivers/visa_util.py`, nowhere else |

## Outside the package

| Path | What |
|---|---|
| `tests/` | pytest suite: mock drivers, fakes under the real drivers, offscreen GUI, and the document guards (`tests/test_docs.py`) |
| `hwcheck/` | bench scripts and their own I/O layer (`hwcheck/iolayer.py`, `hwcheck/scpi.py`), own venv `.venv-hwcheck`. The real drivers are a port of that layer. `hwcheck/m7_*.py` import the app's drivers and `sweep/core.py` to run them headless on the bench; they run with the app venv |
| `hwcheck/results/` | raw JSON of every bench run, including failed ones |
| `docs/` | spec (`docs/SPEC.md`, `docs/spec/`), hardware history (`docs/hw/`), state (`docs/STATE.md`), the manuals (PDF), feature designs and plans (`docs/superpowers/`), the user's parked features (`docs/feature.md`), screenshots |
| `scripts/99-usbtmc-unit.rules` | Linux udev rule (never run) |
| `run.bat`, `run.sh` | launchers: create `.venv`, install when `requirements.txt` changed, start the app |
