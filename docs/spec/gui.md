# Spec: GUI, presets and settings, exports (sections 10, 11, 12)

Part of the design spec. Overview and the index of all sections: `docs/SPEC.md`. Section numbers are kept, because the code cites them.

## 10. GUI

**Main window layout:**
- **Toolbar:**
  - Connect/Disconnect, Start, Pause/Resume, Abort.
  - Export ▾ (CSV, PNG, SVG, PDF, Touchstone).
  - Preset dropdown + Save / Save As / Delete.
  - Sim-mode indicator.
- **Left dock: config panel**, grouped:
  - Sweep: type, start, stop, points/decade or N, descending.
  - Stimulus: gen channel, amplitude, offset, load.
  - Scope: ref/dut channel mapping, probe atten per channel, coupling, BW limit, target cycles.
  - Measurement: method (Sine fit / Built-in), averages, settle ms, settle cycles.
  - Inputs are disabled while a sweep is running.
- **Centre:** two vertically stacked pyqtgraph plots:
  - Gain dB and phase °, both with log or linear x-axis to match the sweep type, x-axes linked.
  - Crosshair with a readout of freq / gain / phase.
  - "Unwrap phase" checkbox, default off.
  - Flagged points drawn with distinct markers, with tooltips listing the flags.
- **Window layout (user's review of 2026-10-07, `LAYOUT_VERSION` 3 since the Analysis tab):** the window reads in working order. Left: set up (Configuration). Centre: the plot, at least half the width. Right: reading the result (Traces, with Markers and Analysis as tabs behind it). Underneath, a low strip for what is watched while a sweep runs: the status log and, at its right end, the waveform. The first sizes are shares of the window (right column 27 % of the width, strip 20 % of the height), so that they fit any screen; the window's smallest width is about 1220 px at 100 % scale. A window layout stored by an earlier arrangement is not restored (`saveState` / `restoreState` carry the version), so the new one shows once; after that the user's own arrangement is kept. Start is the one accented toolbar button.
- **Bottom strip, right: live waveform view.** The last ref and dut capture in volts vs time, with the fitted sine overlaid in SINEFIT mode.
- **Bottom strip, left: status log.** Table with columns time / freq / V/div ref,dut / retries / flags / duration, plus a free-text log. Auto-scrolls; has a copy and clear option.
- **Status bar:** state, progress `i/n`, elapsed time, ETA.

**Dialogs:**
- **Connections:**
  - Backend (py/auto/ivi), default `py`.
  - Per-instrument resource string with a "Discover" button (lists resources). Empty fields mean "find the one supported generator and scope".
  - "Test" button: `*IDN?` of the chosen resources and which driver each one gets. Only while disconnected.
- **Skew check wizard** (§8.6): toolbar button "Skew check", status-bar indicator (Δt and age, or "skew: unchecked"), and a toolbar action "Front panel was used" that invalidates the current check.
- **Through calibration** (§8.7): toolbar button and File menu entry "Calibrate" next to "Skew check"; a dialog with the instruction, a progress bar, the summary (range, points, largest gain deviation, delay found, warnings) and Accept / Measure again / Cancel / Discard calibration. The status bar shows `cal: HH:MM, range` when a through calibration applies to the current scope settings, otherwise the skew state. A sweep that a calibration covers does not ask for the skew check.
- **Traces** (v2, milestone A3; design `docs/superpowers/specs/2026-10-07-trace-overlay-design.md`): the plot shows any number of traces: the live sweep, kept sweeps, CSV files and theory curves. A dock "Traces" lists them (visibility tick, colour, name, kind) with the buttons Load CSV…, Add theory…, Keep sweep, Remove. A new sweep replaces only the live trace. A theory curve is a circuit of `measure/theory.py` with entered part values, or H(s) as coefficients; it is drawn at 50 points per decade over the range of the other traces and of the sweep settings. A box "Difference to trace" (called "Relative to" until the user's review of 2026-10-07; first entry "off") draws every visible trace divided by one reference trace (gain difference in dB, phase difference in degrees; a measured reference is interpolated in log frequency, a theory reference is evaluated exactly; nothing is drawn outside the reference's range). With the vertical unit Voltage, theory curves and the relative display are off. The first eight traces take the theme's eight series colours; further ones are drawn muted. Traces live for one run of the app; they are not stored. The read-out names the trace under the cursor; re-measure works on the live sweep only. The read-out sits in a row of its own under the controls and never changes the layout; the Configuration panel is never narrower than its fields.
- **Markers** (v2, milestone A4; design `docs/superpowers/specs/2026-10-07-auto-markers-design.md`): a dock "Markers", a tab behind the Traces panel (user's review of 2026-10-07: a Markers button in the row above the plot crowded it and made the vertical unit read as a marker setting), holds the controls, content first (the trace box and the four ticks on top, the table with all the height that is left, the actions under it, the look in one row at the bottom): the trace the markers measure ("Markers on", the live sweep by default), a tick box per automatic marker, Add marker / Remove all / Copy values, "Values on the plot" (off: a marker carries its name only), a colour per marker (user's request of 2026-10-07: every table row has a colour square, as the traces have; a click on it, or "Colour" in a user marker's right-click menu, opens a grid of the twenty colours of `theme.MARKER_PALETTE`: two neutrals and nine hues in a bright and a deep step, each at least 4.5 : 1 on the plot surface. The line and the dot take the colour; the label stays in ink, because coloured text is hard to read. Defaults: −3 dB white, peak amber, notch deep violet, M1 to M8 eight different colours, the margins grey. The colour belongs to the marker's name and is stored. The exported image draws each marker in the print twin of its colour, `export_image.PRINT_MARKERS`), and a table of every marker with frequency, gain, phase and note. The automatic markers: −3 dB (`fc`, or `fL` and `fH` with bandwidth and Q; 3 dB below the passband level, which is the level of the flat part of the trace and, without one, its highest gain: `measure/metrics.py`, since v3), peak `pk` and notch `nt` (refined between the points; only when not at an end of the trace and 1 dB clear of both ends), gain margin `GM` and phase margin `PM` (the trace taken as the loop gain: PM = 180° + phase at the 0 dB crossing, GM where the unwrapped phase passes −180°, which means that it stands at least 2° clear of it on one side before and on the other side after: a phase that only wobbles around ±180°, as that of an inverting stage, gives no GM; the smallest when there are several; not in the relative display, not without phase). User markers `M1` to `M8` stand at any frequency (right-click > "Add marker here", drag, or right-click the marker > "Set frequency…"); one can be the reference marker, the others then show frequency ratio, Δ dB, Δ deg and dB/decade. Values between points are interpolated (gain in dB and unwrapped phase, linearly over log frequency); a gap is not bridged. Each marker is a dashed line through both plots, a dot on the curve and its text next to it, on the side where the curve does not go; labels do not cover each other and stay inside their plot (a label moves down, else up, else to the other side of its marker; in the image it also keeps clear of the legend); "Fit view" ignores markers. The markers read the trace as drawn (also the difference curve of "Relative to"); with the unit Voltage the rules still work on the gain, on the rows that have a voltage (the others are not drawn, so the markers do not see them). "Copy values" puts a tab-separated table on the clipboard (the frequency in Hz with two decimals, more below 1 kHz so that six digits stay); the exported image shows the markers as the screen does. "Add marker" needs the chosen trace on the plot. The four ticks, "Values on the plot" and the chosen colours are stored in `settings.json` (`markers`, `marker_values`, `marker_colors`: marker name to palette name); user markers and the chosen trace are not.
- **Analysis** (v3, part 1; design `docs/superpowers/specs/2026-10-07-response-metrics-design.md`): a dock "Analysis", a tab behind Traces and Markers. "Trace" chooses what is analysed, "Compare with" a second trace ("off" first). Nothing is worked out until **Analyse** is pressed; the table then stays, and a line above it names the trace and the time and turns into a warning ("trace changed since this analysis") when the trace was swept again, changed or removed. The table has the columns Quantity, Value, Compare, Difference (the last two only with a second trace) and groups under quiet title lines: Passband (level, ripple, where the flat part lies), Cut-off (`fc`, or `fL` and `fH`), Band (centre, bandwidth, Q), Roll-off (slope in dB/decade and order per cut-off), Stopband (attenuation beyond each cut-off), and one group per resonance ("Peak at …", "Notch at …": f0, gain, height or depth, Q from the −3 dB width, Q from the phase for a peak, points across it). "≥" marks a lower limit: the sweep ends before the number has settled. "(flagged)" marks a number that rests on a flagged point. Differences are percent for frequencies and Q, plain for everything in dB. Notes under the table, four lines at most, say what the numbers do not: no flat part, a passband seen over less than a decade, no cut-off inside the sweep, the stop band not reached, too few points on a resonance (the hook for the finer sweep of part 2), flagged points. The analysis reads the trace itself in dB, whatever the vertical unit and "Difference to trace" show. "Copy table" puts the table and the notes on the clipboard, tab-separated. The figures keep their width and the names take the rest, so the table never scrolls sideways; a trace's name never widens the panel. Nothing of it is stored. The rules and thresholds are in the design's section 3.
- **Every option explains itself** (design rule, user 2026-10-07): each field of the Configuration panel (and its label), each toolbar item, each option above the plot, each button of the Traces panel and of the status log has a tooltip that says what it does, in a full sentence. Tooltips appear after the mouse has rested for 3 seconds (`theme.TOOLTIP_DELAY_MS`, applied through the application style), so they do not flicker up in passing. The menus show the same texts. A new option without an explanation fails `tests/test_gui_tooltips.py`.
- **Sim settings:** DUT preset and parameters, noise level.
- **Export:** format options (image DPI, size, title).

**Behaviour:**
- Closing the window during a sweep asks for confirmation, aborts cleanly, and turns the generator off.
- Window layout and last-used settings persist in `settings.json`.

---

## 11. Presets & settings

**Presets.** A preset is a saved copy of the Configuration panel (sweep, stimulus, scope, measurement) and nothing else. Save As (toolbar or File > Preset) stores the panel under a new name; Save overwrites the selected preset; choosing a preset loads it, and the status log says what it changed or that nothing did. What is typed into a number field counts without Enter (`ConfigPanel.commit`).

**Settings dialog (extended 2026-10-07 on the user's request).** Tabs General, Advanced, Instruments, Simulation. Everything is stored in `settings.json` (`io/settings.py`: out-of-range values are limited, wrong ones fall back to the default) and takes effect at once through `MainWindow.apply_settings`.

- *General:* start-up mode; pause after a scope range change; unwrap phase; open the skew wizard after every connect (off by default: the pop-up on every connect was removed on 2026-10-06); show explanations, and after how long (0 to 10 s, default 3 s); keep previous sweeps as traces (off, or 1 to 6; older ones are removed, sweeps the user kept stay); the folder for Export and Load CSV (empty: the folder used last, which is remembered); grid colour of the plots (a colour, or the theme's own); which panels are shown at start-up (all four by default; a panel not shown is in the View menu); log every instrument command (as `--debug`).
- *Advanced:* limits that apply to every sweep, whatever a preset holds: how much of the screen the signal should fill (60 to 80 %), auto-range retries (3), noise floor (10 %), capture timeout (5 s), the SNR below which a point is flagged LOW_SNR (20 dB), bad-capture retries (2); a Defaults button. Only values that differ from the defaults are stored.
- *The skew check's own settings* are in the wizard, not in this dialog: the two check frequencies (10 and 20 MHz) and the captures per frequency (3), with a Defaults button; the upper frequency is limited to what both instruments reach.

- Location: `platformdirs.user_config_dir("bodeplot")`
  - `settings.json`: connections, backend, window state, last preset, the vertical unit, the automatic markers switched on (`markers`), their look (`marker_values`, `marker_colors`).
  - `presets/<name>.json`: `SweepConfig`, `StimulusConfig`, `ScopeConfig`, `MeasureSettings`. No connection info.
- Every file has `"schema_version": 1`. Unknown keys are ignored; missing keys take defaults. Never crash on an old file.

---

## 12. Export formats

All exports include metadata: app version, timestamp, instrument IDNs, and the full config snapshot.

- **CSV**
  - Metadata as `# key: value` header lines, then the columns: `freq_hz, gain_db, phase_deg, phase_unwrapped_deg, h_re, h_im, vref_amp_v, vdut_amp_v, vdiv_ref, vdiv_dut, timebase_s, n_avg, snr_ref_db, snr_dut_db, skew_corr_deg, flags, cal_gain_db, cal_phase_deg`. The header carries the skew check (Δt, measured Δt, snapped, gain mismatch, check time) or `skew: not checked`. The header also carries `cal: applied | applied in part | none` (in part: some points lie outside the calibrated range; `meta_json` then has `cal_covered: false`) and, when applied, `cal_checked_at`, `cal_range_hz`, `cal_points`, `cal_max_gain_db`; the calibration itself (frequencies and complex values) is in `meta_json` under `cal`.
  - Must round-trip: a loader exists in v1, because v2 overlay needs it.
- **PNG / SVG / PDF** (matplotlib):
  - Gain and phase subplots matching the current view: wrap state, axis type, flagged points, the markers of §10.
  - Title, plus a footer with the date and key settings. DPI and size configurable. With several traces the image shows every visible one, in its colour and with a legend, relative or absolute as the plot does. CSV and Touchstone hold the live sweep only.
- **Touchstone `.s2p`**
  - Header `# Hz S RI R 50`.
  - S21 = H; S11, S12, S22 = 0.
  - `!` comment lines state that this is a scope-based voltage transfer ratio, not a calibrated 50 Ω S-parameter measurement, list the config, and give the skew check (Δt and check time) or say that none was done, and the same calibration facts.
