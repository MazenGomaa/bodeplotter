# Bode plotter

PC software that drives a function generator and an oscilloscope to measure the frequency response (gain and phase) of a device under test, and shows it as a Bode plot.

Target instruments: UNI-T UPO1054 scope and UNI-T UTG932E generator, over USB. The design is in `docs/SPEC.md`; what the hardware really does is in `HW_REPORT.md`.

## Status

| Milestone | State |
|---|---|
| 0, 0b, 0c: hardware gate | Done. Verdict GO WITH WORKAROUNDS (`HW_REPORT.md`). |
| 1: skeleton | Done. |
| 2: core math | Done. |
| 3: mock drivers and engine | Done. |
| 4: GUI | Done. |
| 5: persistence and export | Done. |
| 6: real drivers and probe tool | Done 2026-10-06, tested against simulated instruments only. |
| 7: hardware bring-up | Done 2026-10-06, accepted by the user from the GUI (`HW_REPORT.md` section 13). A few items stay open, listed below. |

**The app runs on the real instruments, from the GUI.** Measured on the bench with the UPO1054 and UTG932E:

| What | Result |
|---|---|
| Through sweep (both probes on the generator), 50 Hz to 20 MHz | gain within 0.05 dB, phase within 0.3° |
| RC low-pass, 1 kΩ / 100 nF | follows the model built from the capacitor's measured loss within 0.11° to 100 kHz; correct down to −47 dB |
| Time for 114 points, 50 Hz to 20 MHz | about 115 s (Sine fit), 53 s (Fast preview) |
| Scope channels | CH1 / CH2 and CH3 / CH4 |
| Scope USB cable pulled during a sweep | generator off after 2.6 s, points kept, reconnect without a power cycle |

**What comes next** (`docs/SPEC.md` sections 15 and 16): v2 (through calibration, done and run on the bench on 2026-10-07; then a connection spec for other transports, trace overlay and theory curves, built on 2026-10-07; markers, built and accepted on 2026-10-07: v2 is done), v3 (filter recognition; started: part 1, the response metrics and the Analysis tab, was built on 2026-10-11; part 2 is a finer sweep around a found feature), a full re-verification on Windows, Linux under WSL, and a Raspberry Pi version with a web frontend. Parked ideas are in `docs/feature.md`.

Open: what occasionally puts the scope into another channel-alignment state (the skew check handles the state itself); a scope that freezes while still on USB could not be provoked; Linux is untested; LAN is not supported.

Simulation mode (`--sim`) needs no hardware.

`pytest` is green: 263 tests, no hardware and no display needed. The test suite cannot reach a real instrument: it sets `BODEPLOT_NO_HARDWARE`, which makes every VISA open fail.

## Run it

Windows: double-click `run.bat`, or `run.bat --sim`. Linux: `./run.sh --sim`.

The launcher finds Python 3.11 or newer, creates `.venv`, installs `requirements.txt` when it has changed, and starts the app. Extra arguments go to the app:

| Argument | Effect |
|---|---|
| `--sim` | simulation mode: mock generator, mock scope and a simulated DUT |
| `--debug` | verbose logging |

Tests: `.venv\Scripts\python -m pytest`.

## Real instruments

Supported: UNI-T UPO1000 family scopes (developed on a UPO1054) and UTG900E family generators (developed on a UTG932E), over USB.

- **Connect:** leave both resource fields in Connections empty and the app finds the one supported generator and scope by `*IDN?`. Or use Discover and pick them.
- **Front panel:** the scope's keys are locked while a sweep, skew check or re-measure runs, and released afterwards. If they are ever left locked: `python -m bodeplot.tools.probe --unlock`.
- **If the scope stops answering:** the app switches the generator off, stops the sweep, keeps the points measured so far and disconnects. If the scope has gone from USB it says to check the cable; otherwise switch the scope off and on, then connect again. The app never asks for administrator rights.
- **Scope settings** are read before a sweep, skew check or re-measure and put back afterwards. The generator is left with its output off; its other settings are not restored.
- **Mode:** the toolbar's Mode box switches between Instruments and Simulation while disconnected; File > Settings sets which one the app starts in.
- **Step tables:** the scope's timebase and V/div steps are shipped as data for the UPO1054 with firmware `1. 01. 0047`. Another model or firmware gets the same tables and one warning.
- **Setting:** `scope_min_gap_ms` in `settings.json` (default 100) is the pause after every timebase or V/div change.

### Probe tool

`python -m bodeplot.tools.probe` identifies both instruments, sends the query form of every command the drivers use, takes one test acquisition on scope CH1 and prints a pass/fail table. Generator outputs stay off; `:RUN` is never sent; nothing is walked.

| Option | Effect |
|---|---|
| `--no-acquire` | queries only |
| `--json FILE` | write the report to a file |
| `--unlock` | release the scope's front-panel lock and exit |
| `--walk-tables` | measure this scope's own step tables. Prints a warning first: the UPO1054 froze once during such a walk and needed a power cycle. Paced (`--gap-ms`, default 250). |

## What works

Everything below runs in simulation; on the real instruments all of it does except the "Scope built-in" method.

- **Methods** (Measurement > Method):
  - *Sine fit*: one single-shot capture per point, both channels from the same record. The accurate one.
  - *Fast preview (rough phase)*: reads the scope while it keeps running. About twice as fast with the same gain, but the two channels are different acquisitions, so the phase scatters (about 0.4° below 100 kHz, several degrees above 5 MHz). Every point is flagged `PREVIEW`, and no skew check is asked for.
  - *Scope built-in*: simulation only. The real scope's own measurements were tested and are ten times coarser (`HW_REPORT.md` 13.26).
- **Vertical unit:** dB, volts at the DUT, or percent of the input.
- **Sweep:** logarithmic or linear, 50 Hz to 20 MHz, ascending or descending; live gain and phase plots with linked axes, crosshair readout, phase unwrap, flagged points drawn as red crosses with their flags in the tooltip.
- **View:** the plots follow the curves while a sweep runs. If you pan or zoom, they stay where you put them; **Fit view** (or a double-click on either plot) snaps back to the curves, and a new sweep is followed again from its first point.
- **Look:** dark theme. Every colour lives in `src/bodeplot/gui/theme.py`. Exported images keep a white background for printing. All panels are shown at start-up, even if one was closed last time.
- **Menus:** File (connect, connections, simulation settings, export, presets, exit), View (show or hide each panel and the toolbar, fit view, unwrap phase, reset layout) and Help (log and settings folders, About). A panel closed with its X comes back from the View menu.
- **Numbers:** frequencies and voltages are shown with SI multipliers (20 MHz, 500 µV) and the frequency fields accept them (`20M`, `1.5k`; `M` is mega, `m` is milli).
- **Per point:** timebase from the scope's real step table, auto-range on both channels, averaging as a complex mean, sine fit at the generator frequency or the scope's built-in measurement.
- **Control:** pause, resume, abort (partial result kept, generator switched off on every exit path), re-measure a single point by clicking it.
- **Channel skew check and correction** (see below).
- **Traces**: keep a sweep, load saved CSV sweeps and add theory curves (RC, RLC, Butterworth, or your own H(s)) next to the live sweep; show or hide each; draw everything relative to one of them to read the difference directly.
- **Markers**: −3 dB cut-off(s) with bandwidth and Q, peak, notch, gain and phase margin, and up to eight markers of your own with a reference marker; copied as a table and drawn in the exported image (see below).
- **Analysis**: on a button, the numbers of a trace: passband level and ripple, cut-off(s), slope and filter order, stopband attenuation, and every resonance with its Q from the width and from the phase; a second trace (a theory curve, an earlier sweep) next to it with the difference.
- **Explanations and settings**: every option explains itself when the mouse rests on it (3 seconds by default). File > Settings holds the start-up mode and panels, the explanations' delay, keeping previous sweeps, the folder for files, the grid colour, debug logging, and an Advanced tab with the auto-range and noise limits. The skew wizard has its own check frequencies and captures.
- **Presets**: a preset is a saved copy of the Configuration panel. Set the panel, press Save As and name it; choosing a preset loads it and the status log says what changed.
- **Through calibration** (see below): removes the gain and phase difference between the two probes and channels at every frequency.
- **Waveform view** of the last capture with the fitted sines, and a status log table.
- **Presets and settings** as JSON in the user config folder; old or damaged files load with defaults.
- **Export:** CSV (with a loader that round-trips), PNG, SVG, PDF, Touchstone `.s2p`.
- **Simulated DUTs:** through, RC low-pass, RC high-pass, RLC band-pass, RLC notch, 2nd-order Butterworth low-pass, custom H(s); and circuits to try the analysis and the markers on: a resonant RLC low-pass (a hump before the cut-off), an RC low-pass whose stop band levels off, a band-pass with a flat top, Butterworth and Chebyshev low-passes of order 1 to 10, two resonances, a crystal (a peak and a notch close together), an amplifier with one pole, and a loop gain with three poles (gain and phase margin). File > Sim settings chooses one; the same list is under Traces > Add theory.

## Channel skew check

The UPO1054's two channels can sit a whole number of 2 ns samples apart in time and stay that way (`HW_REPORT.md` section 12.11). That is invisible at 1 kHz and up to 43 degrees at 20 MHz, and no command undoes it. So the app measures it and corrects for it:

1. Press **Skew check** and put the reference probe and the DUT probe on the same node (the generator output).
2. The app measures the delay between the channels at 10 MHz and 20 MHz, whatever the sweep range.
3. The measured delay is what is applied. The known states (−1.85, +0.15, +2.15, +4.15 ns) are only named for information, and on CH1 / CH2 a delay more than 0.3 ns from all of them gives a warning. A gain mismatch above 0.3 dB also warns.
4. Every point is then corrected: `phase_corr = phase − 360·f·Δt`.

Do the check with both probes on the generator output, **not** through the DUT: with a DUT in between it would measure the DUT's phase. Then move the DUT probe and sweep.

The check belongs to one session. After connecting, after any driver resync, and when you press **Front panel was used**, the status bar shows the skew as UNCHECKED; the app asks for the check when you start a Sine fit sweep without one. A sweep run without a valid check is not corrected and every point carries the `SKEW_UNCHECKED` flag. The delay and the time of the check are written into the sweep metadata, the CSV header and the Touchstone comments.

The simulated scope picks one of the four skew states at random each time it is opened or resynchronised, so this path is exercised in simulation too.

## Through calibration

The skew check removes one thing, the delay between the two scope channels. The two measurement paths also differ in gain, and both differences change with frequency and with which probe sits on which channel (0.1 to 0.2 dB up to 20 MHz on the bench). The calibration measures all of it once and divides it out.

1. Press **Calibrate** and put the reference probe and the DUT probe on the same node (the generator output), both at the same probe setting.
2. The app sweeps the full range of the instruments (50 Hz to 20 MHz, 58 points, about 1 minute) with Sine fit and shows the range, the largest gain deviation and the delay it found.
3. Accept. The status bar shows `cal: HH:MM, 50 Hz to 20 MHz`.

Later sweeps with the same channels, probe settings, coupling and bandwidth limit are divided by it; their points carry the `CALIBRATED` flag, and the CSV holds what was removed (`cal_gain_db`, `cal_phase_deg`), so the raw measurement can be recovered. With a calibration that covers the sweep, no skew check is needed. Outside the calibrated range the skew check is used as before.

The calibration belongs to one connection and is not saved: a reconnect, a resync or **Front panel was used** drops it. It is refused when it does not look like a through connection (more than 1 dB anywhere, or a reference far below the generator setting). It does not correct the small gain differences between the scope's V/div steps (up to about 0.09 dB).

## Comparing traces

The **Traces** panel lists what is on the plot. The live sweep is always there; a new sweep replaces only it.

- **Keep sweep** keeps the current sweep on the plot when the next one starts.
- **Load CSV…** adds sweeps saved earlier with Export > CSV, one or several at once.
- **Add theory…** adds the ideal response of a circuit: pick a circuit (RC low-pass, RC high-pass, RLC band-pass, RLC notch, a Butterworth or Chebyshev low-pass and the others of the simulator's list) and enter the parts (1k, 100n), or enter the coefficients of H(s). Double-click the kind of a theory trace to change its values.

Tick a trace to show it, double-click its name to rename it. **Difference to trace** above the plot draws every trace divided by the one you choose ("off" shows them as measured): gain difference in dB and phase difference in degrees. With a theory curve as the reference this shows how far the measurement is from the ideal circuit. A theory curve is the ideal circuit only: no component losses, no lead inductance, no probe loading.

Traces are kept for this run of the app only. The image export shows every visible trace; CSV and Touchstone hold the live sweep.

## Markers

The **Markers** panel (on the right, a tab behind the Traces panel; View > Markers) switches markers on one trace (**Markers on**, the live sweep unless you choose another). Each marker is a dashed line through both plots with its values written next to the curve, and the panel lists all of them in a table.

- **−3 dB** marks where the gain is 3 dB below the passband level (the flat part of the trace; without one, its highest gain): `fc` for a low-pass or high-pass, `fL` and `fH` with bandwidth and Q for a band-pass.
- **Peak** and **Notch** mark the highest and the lowest gain when they are real ones: not at an end of the trace and at least 1 dB clear of both ends.
- **Margins** reads the trace as a loop gain: the phase margin where the gain passes 0 dB (180° + phase) and the gain margin where the phase passes −180°.
- **Your own markers:** right-click the plot > **Add marker here**, then drag it, or right-click it to type a frequency (1k, 2.5M), to remove it, or to make it the **reference marker**; the others then show their difference to it and the slope in dB per decade. Up to eight.

Between two measured points the values are interpolated. With **Difference to trace** set, the markers measure the difference curve. **Copy values** puts a table on the clipboard, and the image export shows the markers. Untick **Values on the plot** to keep only the names on the plot and read the numbers in the table; Every marker has a colour square in the table: click it (or right-click one of your own markers > **Colour**) to pick another of the twenty palette colours for its line and dot. The image export uses the same colours, darkened for the white background. The ticks, that choice and the colours are remembered; your own markers are not.

## Analysis

The **Analysis** panel (on the right, a tab behind Traces and Markers; View > Analysis) works out the numbers of one trace when you press **Analyse**. Choose the trace under **Trace**, and under **Compare with** a second one, for example a theory curve with your design values: its numbers appear next to the measured ones, with the difference in percent (frequencies, Q) or in dB.

- **Passband:** the level of the flat part of the trace and how far the gain moves inside it. The cut-off is counted 3 dB below this level, here and in the −3 dB marker.
- **Roll-off and stop band:** the slope the curve settles to and the order that goes with it; how far below the passband the trace gets.
- **Resonances:** every peak and every notch with its frequency, its height or depth, Q from its −3 dB width and, for a peak, Q from the phase.
- **≥** means "at least": the sweep ends before the number has settled. The notes under the table say why, and where a resonance has too few points to be trusted.
- **Noise:** where an end of the trace is lost in the instrument's noise (the gain scatters from point to point), that part is left out of the table and of the automatic markers, and a note says from which frequency. A roll-off that runs into it reads "≥" down to the noise.

The table stays until you press Analyse again; the line above it warns when the trace has changed since. **Copy table** puts it on the clipboard.

## Instrument rules that matter

These come from the hardware gate and are built into the drivers (`docs/SPEC.md` section 9):

- The app never sends `:RUN` to the scope. It arms with `:TRIGger:SWEep SINGle` and returns to free-run with `:TRIGger:SWEep AUTO`.
- The generator only ever receives commands that are in its manual; an unknown query can hang it.
- A capture is clipped when any sample is on code 1 or 254 (the scope's real rail codes). The screen has 8 vertical divisions; the data reach 10.1.
- Default VISA backend is pyvisa-py (free). On Windows the instruments need the WinUSB driver, bound once per instrument with Zadig (Options → List All Devices, pick the device by its USB ID, target driver WinUSB). A vendor VISA library is optional; NI-VISA is not free for use with third-party instruments.
- Use 10X probes by default, and always above about 1 MHz. Both channels must use the same probe type and setting.

## Layout

| Path | What |
|---|---|
| `src/bodeplot/` | the application |
| `tests/` | pytest suite: mock drivers, plus the real drivers against simulated SCPI instruments (`fakes.py`) |
| `docs/SPEC.md` | design: overview and index of the sections; the detail is in `docs/spec/` (drivers, sweep, skew, gui, web, roadmap) |
| `docs/ARCHITECTURE.md` | modules, what calls what, where each concern lives (checked against the code by `tests/test_docs.py`) |
| `docs/STATE.md` | what is done and what is next |
| `docs/*.pdf` | instrument programming manuals |
| `HW_REPORT.md` | what the hardware really does: the current verified facts, and the index of the dated test runs in `docs/hw/` |
| `hwcheck/` | bench scripts, including `iolayer.py` (the tested I/O reference) and `s0c_realign.py` (optional bench tool; not used by the app). Each script prints its file hash and git commit at start; commit before every bench run. |
| `run.bat`, `run.sh` | launchers |
| `scripts/99-usbtmc-unit.rules` | Linux udev rule example (untested) |
