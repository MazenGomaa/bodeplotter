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
- **Right dock: live waveform view.** The last ref and dut capture in volts vs time, with the fitted sine overlaid in SINEFIT mode.
- **Bottom dock: status log.** Table with columns time / freq / V/div ref,dut / retries / flags / duration, plus a free-text log. Auto-scrolls; has a copy and clear option.
- **Status bar:** state, progress `i/n`, elapsed time, ETA.

**Dialogs:**
- **Connections:**
  - Backend (py/auto/ivi), default `py`.
  - Per-instrument resource string with a "Discover" button (lists resources). Empty fields mean "find the one supported generator and scope".
  - "Test" button: `*IDN?` of the chosen resources and which driver each one gets. Only while disconnected.
- **Skew check wizard** (§8.6): toolbar button "Skew check", status-bar indicator (Δt and age, or "skew: unchecked"), and a toolbar action "Front panel was used" that invalidates the current check.
- **Sim settings:** DUT preset and parameters, noise level.
- **Export:** format options (image DPI, size, title).

**Behaviour:**
- Closing the window during a sweep asks for confirmation, aborts cleanly, and turns the generator off.
- Window layout and last-used settings persist in `settings.json`.

---

## 11. Presets & settings

- Location: `platformdirs.user_config_dir("bodeplot")`
  - `settings.json`: connections, backend, window state, last preset.
  - `presets/<name>.json`: `SweepConfig`, `StimulusConfig`, `ScopeConfig`, `MeasureSettings`. No connection info.
- Every file has `"schema_version": 1`. Unknown keys are ignored; missing keys take defaults. Never crash on an old file.

---

## 12. Export formats

All exports include metadata: app version, timestamp, instrument IDNs, and the full config snapshot.

- **CSV**
  - Metadata as `# key: value` header lines, then the columns: `freq_hz, gain_db, phase_deg, phase_unwrapped_deg, h_re, h_im, vref_amp_v, vdut_amp_v, vdiv_ref, vdiv_dut, timebase_s, n_avg, snr_ref_db, snr_dut_db, skew_corr_deg, flags`. The header carries the skew check (Δt, measured Δt, snapped, gain mismatch, check time) or `skew: not checked`.
  - Must round-trip: a loader exists in v1, because v2 overlay needs it.
- **PNG / SVG / PDF** (matplotlib):
  - Gain and phase subplots matching the current view: wrap state, axis type, flagged markers.
  - Title, plus a footer with the date and key settings. DPI and size configurable.
- **Touchstone `.s2p`**
  - Header `# Hz S RI R 50`.
  - S21 = H; S11, S12, S22 = 0.
  - `!` comment lines state that this is a scope-based voltage transfer ratio, not a calibrated 50 Ω S-parameter measurement, list the config, and give the skew check (Δt and check time) or say that none was done.
