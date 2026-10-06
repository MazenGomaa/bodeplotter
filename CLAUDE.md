# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Bode plotter — working notes for Claude

PC software that sweeps a UNI-T generator and reads a UNI-T scope to draw a Bode plot. `docs/SPEC.md` is the source of truth; `HW_REPORT.md` records what the hardware really does and overrides the manuals where they disagree.

## Commands

Run from the project root (PowerShell). There is no build step and no linter or formatter configured.

| Task | Command |
|---|---|
| Run the app (creates `.venv`, installs when `requirements.txt` changed) | `run.bat` (real instruments) or `run.bat --sim`; add `--debug` to log every instrument command |
| Run the app without the launcher | `.venv\Scripts\python -m bodeplot --sim` |
| All tests (no hardware, no display) | `.venv\Scripts\python -m pytest` |
| One file / one test / by name | `.venv\Scripts\python -m pytest tests\test_sweep.py`, `... tests\test_sweep.py::test_name`, `... -k skew` |
| Probe tool (touches the real instruments) | `.venv\Scripts\python -m bodeplot.tools.probe` (`--no-acquire`, `--json FILE`, `--unlock`, `--walk-tables`) |
| Bench script (touches the real instruments) | `.venv-hwcheck\Scripts\python.exe -W ignore hwcheck\<script>.py "@py"` |

`tests/conftest.py` puts `src/` on the path, sets `QT_QPA_PLATFORM=offscreen` and sets `BODEPLOT_NO_HARDWARE`. `BODEPLOT_CONFIG_DIR` redirects the settings and presets folder (`io/settings.py`).

## Architecture

One measurement goes down this chain; each layer only knows the one below it:

1. **GUI** (`gui/main_window.py` and the panels) builds the config dataclasses in `models.py` (`SweepConfig`, `StimulusConfig`, `ScopeConfig`, `MeasureSettings`) and talks only to `SweepEngine`.
2. **`sweep/engine.py`**: `SweepEngine` owns a QThread with an `EngineWorker`. Requests go in as queued signals, results come back as signals; pause / resume / abort are called directly on the worker. It holds the one `Session` and drops it when the watchdog marks it dead.
3. **`sweep/core.py`** (no Qt, so it is what the tests and `hwcheck/m7_*.py` drive): `Session` = one source + one digitizer + the skew check that belongs to that connection; `SweepRunner` walks the plan from `sweep/plan.py`, reports through `Callbacks`, applies the skew correction and guarantees `safe_off` and the scope restore on every exit path.
4. **`measure/meters.py`**: `DualChannelScopeMeter` does one frequency point: timebase from the step table, auto-range (`sweep/autorange.py` holds the pure decisions), capture, then `measure/sinefit.py` or the scope's built-in measurement. It returns a `PointResult` with `Flag`s.
5. **Drivers** (`drivers/base.py`: `SignalSource`, `Digitizer`, `Waveform`, caps). `drivers/registry.py` maps an `*IDN?` string to a driver class; `drivers/connect.py` scans, picks and opens a real `Session`. `drivers/mock.py` implements the same interfaces with a `SimulatedDUT` (this is Simulation mode).
6. **`drivers/transport.py`**: the real drivers speak SCPI through a `Transport`. `VisaTransport` is the only place a VISA resource is opened (`visa_util.py` holds the `BODEPLOT_NO_HARDWARE` guard). `drivers/scpi.py` has the command descriptions, reply validators and the driver error types (`InstrumentUnresponsive` is what triggers the watchdog).

Two levels of simulation, used for different things:
- `drivers/mock.py` replaces the drivers. Used by `--sim`, the GUI tests and the sweep / skew tests (`make_session` fixture in `tests/conftest.py`).
- `tests/fakes.py` (`FakeScope`, `FakeGen`, `FakeClock`) replaces the Transport under the REAL drivers, reproduces the faults in `HW_REPORT.md` and records forbidden commands. Time is virtual, so pacing and arm sequences are asserted exactly. `tests/test_drivers.py` also scans `src/` for `:RUN` and `subprocess`.

`hwcheck/` is a separate program family with its own venv and its own I/O layer (`iolayer.py`, `scpi.py`); the app never imports it (the real drivers are a port of it). The dependency only runs the other way: `hwcheck/m7_*.py` import the app's drivers and `sweep/core.py` to run them headless on the bench. A hardware finding goes into `HW_REPORT.md`, then into the driver, then into `tests/fakes.py` so the suite keeps it.

Persistence (`io/`): settings and presets are JSON in the user config folder, loaded through `models.from_dict`, which falls back to defaults field by field; exports are CSV (round-trips), image, Touchstone.

## Current state (updated 2026-10-06)

- **Milestones 0, 0b, 0c (hardware gate): done. Verdict GO WITH WORKAROUNDS** (`HW_REPORT.md`, top block and section 12).
- **Milestones 1 to 5: done, against the mock drivers only.** `pytest`: 174 passed (2026-10-06). The user reviewed the GUI and asked for changes, all done (see below).
- **Milestone 6 (real drivers + probe tool): DONE 2026-10-06.**
- **Milestone 7 (bench bring-up): IN PROGRESS. Everything that can be done without a person at the bench is done; the rest waits for the user.** Full record: HW_REPORT section 13 (13.7 to 13.12 are from 2026-10-06). `pytest`: 251 passed (2026-10-06, evening). Everything is committed (`git log`); the only untracked item is `graphify-out/`.
  - **START HERE in the next session.** The user said they will be AT THE BENCH and will start the bench tests in a fresh chat. State they left it in: both instruments on USB, generator outputs OFF, scope free-running and unlocked, the 1 k / 100 nF low-pass on the breadboard (generator CH1 -> 1 k -> 100 nF to ground; CH1 probe = reference on the generator side, CH2 probe = DUT on the capacitor; both 10X).
    1. Ask what is wired now, and check the instruments answer: `.venv-hwcheck\Scripts\python.exe -W ignore hwcheck\s6_state.py "@py"` (read-only). Commit before every bench run. Ask before the user has to touch cables or power.
    2. **DONE 2026-10-06 (HW_REPORT 13.13): skew wizard in the GUI on the real instruments** gave +0.14 ns, snapped to +0.15 ns, gain mismatch -0.019 dB; the through sweep from the GUI after it (114 points, 50 Hz to 20 MHz, 5 Vpp, 114 s): 99.6 to 100.1 % of input, phase within about 0.3 deg. The wizard's intro text named the wrong frequencies; fixed.
    3. **DONE 2026-10-06 (HW_REPORT 13.18): the RC phase lead is the capacitor's own loss.** The 100 nF is a film part; the user's LCR meter read D = 0.001 / 0.003 / 0.009 / 0.028 and Cs = 105.7 / 105.4 / 104.4 / 102.6 nF at 100 Hz / 1 k / 10 k / 100 kHz. A model with those values gives the measured phase within 0.11 deg from 5 to 100 kHz. Nothing to fix in the app. The user also has a ceramic and a mica capacitor and an LCR meter with USB (UNI-T UT612).
    4. **DONE 2026-10-06 (HW_REPORT 13.14): CH3 / CH4 work.** Their delay is +0.08 ns, not +0.15 ns, and the snap left -0.39 deg at 20 MHz, so (user decision) **the skew check now snaps only for reference CH1 / DUT CH2** (`skew.SNAP_PAIR`, `skew.snaps`); any other pair or order applies the measured value with no warning. Confirmed on the bench the same evening: +0.10 ns applied, not snapped, through sweep +0.07 deg at 20 MHz, 116 s. CH4 reads about 1 % below CH3 at 20 MHz (not corrected).
    5. **DONE 2026-10-06 (HW_REPORT 13.15): watchdog with the scope's USB cable pulled mid-sweep works**: generator off 2.6 s after the pull, 26 of 114 points kept, error shown, session dropped. After replugging (no power cycle) the scope answered at once, unlocked, on the sweep's timebase. Fixed afterwards: the false "was resynchronised" warning, and the advice now says to check the USB cable when the device is gone from the bus (`Transport.present`, `UNPLUGGED_ADVICE`); the new text has only run against the fakes. The generator-off timing was changed later the same evening (see 13.19). A scope that is frozen but still on the bus is still untested.
    6. **DONE 2026-10-06 (HW_REPORT 13.16): a power cycle clears the panel lock** (locked with `s6_lock.py on`, key ignored with a "locked" message, after the power cycle `:SYSTem:LOCK?` 0 and the panel works). The scope came back with its previous settings, sweep AUTO.
    7. **DONE 2026-10-06 (HW_REPORT 13.17): `--walk-tables` of the probe tool, paced at 250 ms, ran once to the end with no freeze**; the walked tables equal the shipped ones and were written to `%LOCALAPPDATA%\bodeplot\step_tables.json`. One run only: the two earlier freezes are still unexplained, so keep walking it only with the user present.
    8. Not bench work: Linux (never tested), the open ideas below.
  - **What was settled on 2026-10-06 (do not re-derive):**
    - **The DC at the scope inputs is the GENERATOR's, and it varies**: about +62 mV, -9 mV and +38 mV at the probe tips at 1 Vpp on three occasions (warm-up drift is a guess, not measured). Proof: CH2 on the capacitor at 2 mV/div reads +0.3 mV at the input with the output OFF and +4.1 mV with it ON; it follows the generator's offset setting. The user's scope self-cal did NOT remove it (I first said it had; corrected in HW_REPORT 13.11). The scope's own offset is 0.3 mV or less from 500 uV to 5 mV/div; CH1's zero on the coarse steps (20 mV/div and up) wanders by 2 to 5 codes, so absolute DC is only trustworthy on the sensitive steps. GND coupling is a drawn line (code 127), not a measurement.
    - **The app's DC handling is bench-proven with DC present** (auto-range re-centres with the channel offset, never picks a V/div the DC does not fit in, the driver puts the offset back in volts after a V/div change, 500 uV/div is never used): RC sweeps with +60, +100 and -100 mV of generator offset were correct down to 1 mV/div. **DC coupling stays the default**; AC coupling gives the same result (within 0.03 dB / 0.2 deg to 22 kHz, no penalty at 50 Hz with 10X probes) and is selectable in the GUI.
    - **RC low-pass (1 k, 100 nF) reference result**: corner 1513 Hz (C = 105 nF), gain within 0.06 dB to 22 kHz and within about 0.6 dB down to -47 dB (340 kHz); noise floor -52 to -60 dB at 1 Vpp with 10X probes. **Timed full-range sweep: 114 points, 50 Hz to 20 MHz, 118.8 s (1.04 s per point).** The user's own sweep from the GUI on the real instruments "worked fine" (their report, no data file).
    - **The generator ignores every negative number** (OFFSet, LOW; any number format; no error; firmware 1.09). The driver reaches a negative offset with AMPLitude A + 2d then `:CHANnel<n>:BASE:HIGH` A/2 - d with the output off; lowest offset = minus half the amplitude (`UniTUTG900E._set_level`). Never send the generator a negative number.
    - **Scope settings are saved before and restored after every sweep, skew check and re-measure** (`Digitizer.save_setup` / `restore_setup`, `Session.begin_measurement` / `end_measurement`). Bench: all 19 settings come back, also from a channel that was off and from probe ratio 10X. Scope facts: `:CHANnel<n>:SCALe` is IGNORED on a channel that is switched off (restore DISPlay last); `:CHANnel<n>:SCALe` and `:TRIGger:LEVel` take input-referred volts and report probe-scaled ones; `:CHANnel<n>:OFFSet` is not scaled.
    - **Bad-capture guard**: a capture whose reference fit is below 6 dB SNR is written to `.npz` (`captures/` next to the app's log file, or `hwcheck/results/m7/captures/`), retried up to 2 times, then flagged `REF_SUSPECT` (`measure/meters.py`, `core.save_bad_capture`). The one fault that prompted it (78.62 Hz, AC, first point after a 10 to 5 ms/div change: both channels 0.021 V instead of 0.496 V) was NOT reproduced in 40 repeats (`hwcheck/m7_repeat.py`), so the retry has only run against the simulators. Likely cause found later (13.20): the record read before the scope had finished it after a timebase change; not proven. If a `badcapture_*.npz` ever appears, look at it.
    - **The RC phase lead is not an instrument effect**: same phase within 0.14 deg on every V/div step (`hwcheck/s7_rangephase.py`), probes within 0.2 deg on a through sweep. It is the capacitor's loss, measured with an LCR meter (HW_REPORT 13.18).
    - **GUI added on the user's request, all seen and accepted by the user ("looks fine")**: toolbar **Mode box** (Instruments / Simulation; only while disconnected; `MainWindow.set_mode`); **Settings dialog** (File > Settings or Ctrl+comma; tabs General / Instruments / Simulation; `SettingsDialog`, `ConnectionsPanel`, `SimSettingsPanel`) with the stored `startup_mode` (`instruments` default, `simulation`, `last`); `--sim` applies to that run only; **Vertical unit box** next to Fit view (dB, Voltage = DUT output in Vpp at the probe tip, % of input; `BodePlot.unit_box`, stored as `vertical_unit`; image export follows it); frequency tick labels when zoomed inside a decade (`SiAxis.tickValues`); a ticked checkbox stays visibly ticked while the panel is disabled. "Sim settings" is in the File menu only. `scope_min_gap_ms` is read from the settings file and limited to 100..2000 ms.
    - "Descending resets itself" (user report): the option itself works (runs top-down, survives a restart); the only fault found was the disabled-checkbox drawing, now fixed. Whether that is what the user saw is not confirmed; ask if it happens again.
  - **Open ideas, not implemented**: warn when the reference level is far below what the stimulus setting predicts (a loose ground once gave 0 dB "through" readings with a collapsed level; proposed 2026-10-06 as a 30 % threshold, the user was not sure, undecided); through calibration (SPEC section 15, v2); a faster sweep (see below). **Decided 2026-10-06: the generator's settings are NOT restored after a sweep**; output off is enough (user).
  - **Later on 2026-10-06 (HW_REPORT 13.19)**: the CH3 / CH4 gain difference follows the probes (swapping them turned the droop into a rise), so it is probe compensation. **The generator now goes off at the first failed transfer inside a scope resync** and comes back on if the scope recovers (`Digitizer.on_link_trouble`, `Session._link_trouble`, `core.measure_with_output`); this replaces the earlier decision to leave it on during the resync. Fakes only.
  - **Sweep speed (HW_REPORT 13.20, `hwcheck/s7_capspeed.py`)**: of 1.05 s per point, 0.77 s is the scope's own (single-shot cycle 0.40 s at any timebase, about 0.1 s busy after STOP, `:WAVeform:DATA?` 0.12 to 0.15 s per channel); the generator's frequency set + read-back is 0.17 s; the driver's own overhead about 0.15 s. The capture margins are driver attributes now (`ARM_QUIET_S` 0.3, `STOP_HOLD_S` 0.1, `MIN_WAIT_EXTRA_S`, `STATUS_POLL_S`), values unchanged. **Do not shorten `STOP_HOLD_S` towards 0: with no hold, every capture after a timebase change returned a stale reference record (12 of 12), the signature of the bad capture of 13.9.** Shortening it to 0.05 s gains about 0.05 s, below that nothing. Quiet time 0.3 -> 0.1 s gains 0.19 s only on points with a timebase change; no double arm seen in 12 captures per value, which does not rule it out.
  - Earlier in Milestone 7 (HW_REPORT 13.1 to 13.6): probe tool on the real instruments 63/63; through sweeps (both probes on generator CH1) 50 Hz to 20 MHz: gain within 0.05 dB, phase within 0.3 deg, level flat within 1.3%; auto-range hysteresis; skew check always at 10 and 20 MHz; at 500 uV/div an off-scale or clipped trace reads mid-scale codes with NO rail code, so that step is not used (`UniTUPO1000.UNUSABLE_VDIV`); the scope keeps the channel offset in divisions across V/div changes.
  - The user's standing conditions from the Milestone 6 GO (keep them):
    1. Step tables are shipped data keyed by model + firmware (`drivers/step_tables.py`). Never walked at connect. Every set is verified by read-back. Walking is only the probe tool's `--walk-tables` (paced, with a warning). Unknown firmware: stored tables, one warning, suggest the walk.
    2. Pacing: minimum gap after timebase and V/div changes (`scope_min_gap_ms`, default 100) on top of `*OPC?`.
    3. Watchdog: scope stops answering and the first-level resync fails -> generator safe_off, sweep stops, partial data kept, user told to power-cycle. The app never runs anything that needs elevation (no `pnputil`, no `subprocess` in `src/`; a test enforces it).
    4. NORMal sweep is not used (the driver refuses it). Driver and registry are named upo1000.
    5. Process: the project is in git; **commit before every bench run**. Every hwcheck script prints its file hash and git commit at start (`hwcheck/common.py`); the probe tool prints its own and the drivers' hashes.
    6. Probe tool: no `:RUN`, no table walk by default, generator outputs OFF.
  - Bench results of Milestone 6 (HW_REPORT 12.14): **rail codes are 1 and 254** (clip = code <= 1 or >= 254); data cover 10.1 divisions, the screen grid has 8 (user counted); overdriving CH2 does not disturb CH1; **`:SYSTem:LOCK ON` locks the panel, read-back 1 = locked**, it survives a closed session, so the driver unlocks after every measurement and on close (`probe --unlock` as the fallback).
  - **The test suite sets `BODEPLOT_NO_HARDWARE`** (every VISA open raises). Reason: on 2026-10-06 a GUI test opened a real connection to both instruments by accident. Never remove that guard.
- Real connections are implemented (Connections with empty fields finds both instruments by `*IDN?`). No `:RUN` anywhere in `src/`.

### What exists

- App: `src/bodeplot/`, tests in `tests/`, venv `.venv` (PySide6 6.11, pyqtgraph 0.14, numpy 2.5, Python 3.14). Run: `run.bat` (real instruments unless Settings > Start-up mode says otherwise; add `--sim` for one simulated run) or `.venv\Scripts\python -m bodeplot`. Tests: `.venv\Scripts\python -m pytest`.
- Qt-free sweep logic is `sweep/core.py`; `sweep/engine.py` is the QThread wrapper. GUI tests run offscreen with `MainWindow.interactive = False` (no modal dialogs).
- v1 skew feature, built to the user's spec (SPEC 8.6): `measure/skew.py` (states -1.85/+0.15/+2.15/+4.15 ns, snap within 0.3 ns, gain warn > 0.3 dB, `phase_corr = phase - 360 f dt`), wizard in `gui/dialogs.py`, session validity in `sweep/core.py` (`Session`, `alignment_epoch`), mock skew in `drivers/mock.py`, tests in `tests/test_skew.py`.
- GUI changes after the user's review (2026-10-06): Fit view / follow mode (`gui/bode_plot.py`), k/M number entry and axes (`gui/si_widgets.py`, `units.py`), File/View/Help menus, all panels shown at every start-up, dark theme. `gui/theme.py` holds every colour; nothing else hard-codes one except the white-background image export. The palette is the dataviz skill's reference dark palette; its validator passes (2026-10-06). The user tested the dark theme on their display and approved it.
- Screenshots of the sim GUI: `docs/screenshots/` (offscreen renders; regenerate with a script that sets `QT_QPA_PLATFORM=offscreen` and `QT_QPA_FONTDIR=C:\Windows\Fonts`).
- I/O layer for the bench: `hwcheck/iolayer.py`, test suite `hwcheck/t0b_iolayer.py` (last hardware run 55/55 on `@py`). The app drivers are a port of it.
- Real drivers: `drivers/uni_t_upo1000.py` (`UniTUPO1000`), `drivers/uni_t_utg900e.py`, on `drivers/transport.py` (`VisaTransport`; tests inject `tests/fakes.py`), with `drivers/scpi.py`, `drivers/step_tables.py`, `drivers/connect.py`. Probe tool: `python -m bodeplot.tools.probe`. Watchdog and panel lock live in `sweep/core.py` (`Session.mark_dead`, `end_measurement`), the engine drops a dead session (`_drop_if_dead`).
- Auto-range: clipped captures estimate the amplitude from the share of samples on the rails (`autorange.clipped_vpp_estimate`); `Waveform.rail_fraction`, `DigitizerCaps.data_vertical_divs`.

### Decisions and findings to keep in mind

- **Backend (user, 2026-10-05): NI-VISA is dropped** (not free for third-party use; listed from 201 USD). Use pyvisa-py (`@py`) + WinUSB. NI-VISA is still installed; the user has not asked for an uninstall.
- **Never send `:RUN`** (HW_REPORT 12.11). A `:RUN` sent after the USB session is reopened shifts scope CH2 against CH1 by 2 ns steps (states +0.15, +2.15, +4.15, -1.85 ns; 15 deg per step at 20 MHz) about half the time, and no documented command undoes it. `iolayer.py` blocks it in `write()`; restart with `:TRIGger:SWEep AUTO`. hwcheck: `scpi.S_RUN` is now `:TRIGger:SWEep AUTO`; the debug scripts whose purpose is to send `:RUN` refuse to start without `--allow-run`. `hwcheck/s0c_realign.py` (both probes on one node) checks alignment (`--check`) or re-rolls it; it is an optional bench tool, not used by the app. Untested: whether front-panel Run/Stop, a power cycle or a replug re-roll the alignment.
- **Capture method: single shot** (HW_REPORT 12.12, `hwcheck/s6_capbench.py`, run 2026-10-06). 0.8 s per capture. Free-running capture (sweep AUTO, `:STOP`, read, restart with SINGle then AUTO) was no faster and failed every second capture with `status did not reach STOP after :STOP (last TRIGED)`; cause found (HW_REPORT 12.13, `hwcheck/dbg6_freerun.py`): **a `:STOP` is only valid once the status has read `TRIGED` since the last restart**; sent earlier it either does not last or stops the scope with no record (`:WAVeform:DATA?` answers an empty block). With that rule the best free-running method takes 0.93 s, still slower than single shot. About 0.35 s of each capture is the two-channel read; shortening it has not been tried. Alignment did not move over 30 resyncs.
- **Probes:** 10X by default, scope kept at PROBe 1X with x10 in software (HW_REPORT 12.10); 1X only for small signals below about 1 MHz. No BNC tee is available: the two-channel tests use two probes on generator CH1.
- The user sometimes switches the generator output on from the front panel between runs; scripts force both outputs OFF at start and end.
- Do not use the scope's front panel while a test runs; it made the scope ignore commands.

### Scope behaviour found in 0b (all in HW_REPORT section 12 and SPEC 9)

- 20 ns/div is not a real timebase step (steps: 1, 2, 5, 10, **25**, 50 ns, then 1-2-5). V/div steps: 500 uV to 20 V, 1-2-5.
- `:TRIGger:SWEep SINGle` is itself the arm command. After arming from STOP the status reads stale STOP, then ARMED, AUTO, READY (about 0.67 s), then STOP after the trigger.
- A setting change just before arming causes a second arm cycle; the layer waits 0.3 s and for status != ARMED first, and requires STOP to hold 0.1 s.
- `:TRIGger:FORCe` only works from READY; sent while status reads AUTO it leaves the scope in AUTO.
- Offset and trigger level are quantised to V/div / 25.
- Empty replies to ordinary queries mean "busy": retry, no resync.
- Out-of-step mechanism: an unanswered `:WAVeform:DATA?` is answered late as a 707-byte block in place of one later reply; then the scope is in step again.
- pyvisa-py has no USB `clear()`; the layer closes the session and sends INITIATE_CLEAR via pyusb (`hwcheck/usbclear.py`).
- Generator timeout -> device clear -> one retry: proven 5 of 5. Unknown commands are blocked before sending.
- Under NI-VISA (no longer used) a read with no query pending made every later read fail with `VI_ERROR_INP_PROT_VIOL`; `pnputil /restart-device "USB\VID_5656&PID_0832\APX1424510001"` (admin) fixed it.
- The scope has frozen twice (0b, and 2026-10-06 during `build_tables()` stepping the timebase): screen frozen, every USB write times out, INITIATE_CLEAR and `pnputil /restart-device` do not help, only a power cycle by the user does. Cause unknown. Avoid re-walking the step tables; use the tables measured in 0b.

## Layout

Project root: `C:\Users\mazen\Desktop\bodeplotter`. A git repository (since 2026-10-06, branch `main`, no remote). Paths are relative to the root.

| Path | What |
|---|---|
| `docs/SPEC.md` | design spec; milestones in section 16, open items in section 17 |
| `docs/*.pdf` | the programming manuals (UPO1000 manual is the one cited for the scope, as `U1K p.N`) |
| `HW_REPORT.md` | hardware report: Milestone 0 findings S1-S9, G1-G5; section 12 = 0b, 0c, alignment fault, capture benchmark |
| `README.md` | status, how to run, features |
| `src/bodeplot/` | the app (`gui/`, `sweep/`, `measure/`, `drivers/`, `io/`) |
| `tests/` | pytest suite (mock drivers, offscreen GUI) |
| `.venv/` | app venv |
| `hwcheck/` | bench scripts and the I/O layer; `scpi.py` has every command with its manual page. Milestone 6 scripts: `s6_capbench`, `dbg6_freerun`, `s6_overdrive`, `s6_lock`, `s6_state` (read-only check) |
| `hwcheck/results/` | raw JSON of every bench run, including failed ones |
| `.venv-hwcheck/` | venv for hwcheck only: pyvisa, pyvisa-py, pyusb, libusb-package |

Run a hwcheck script (from the root): `.venv-hwcheck\Scripts\python.exe -W ignore hwcheck\<script>.py "@py"`.

Older memory notes for this project are under `~/.claude/projects/C--Users-mazen-Desktop-bodeplotter-docs/memory/` (sessions used to be started in `docs/`).

## Hardware

| | Scope | Generator |
|---|---|---|
| Model | UNI-T **UPO1054** (4 ch, 50 MHz). Not UPO1052. | UNI-T UTG932E |
| `*IDN?` | `UNI-T Technologies,UPO1054,APX1424510001,1. 01. 0047` | `UNI-T Technologies,UTG900E,69746177,1.09` |
| USB VID:PID | `5656:0832` | `6656:0834` |
| `@py` resource | `USB0::22102::2098::APX1424510001::0::INSTR` | `USB0::26198::2100::69746177::0::INSTR` |

## This machine

- Windows 11 Home 10.0.26200, Python 3.14.6 (`py -3.14`).
- **Both instruments are bound to WinUSB (Zadig): use the `@py` backend.** `@ivi` sees nothing in this state.
- No `pdftoppm`, so the Read tool cannot open the PDFs. Extract text with `pypdf` in a throwaway venv in the scratchpad (not in `.venv-hwcheck`).
- Node.js 24 LTS at `C:\Program Files\nodejs\node.exe` (installed 2026-10-06; not on PATH in an already-open shell). The dataviz palette validator was run with it: the theme's colours pass.
- Linux has not been tested at all. `run.sh` and `scripts/99-usbtmc-unit.rules` were written but never run.

## Rules for instrument work

Full detail and evidence are in `HW_REPORT.md` sections 8 and 12 and SPEC.md sections 9.1 to 9.3. The ones that cause real damage if forgotten:

**Scope**
- Never send `:RUN`.
- Never send `:WAVeform:DATA?` unless a stopped record exists (single shot: arm, wait for STOP to hold, then fetch). An empty reply must not be retried in place; the layer resyncs and takes a new acquisition.
- Do not try to recover the scope with USBTMC `INITIATE_ABORT_BULK_IN` or a USB port reset; both made it stop accepting writes.
- A read with no query pending re-sends the last reply forever. Never loop "read until timeout".
- `*OPC?` after every write; plain-decimal numbers only; probe ratio as `1X`; read back timebase and V/div.
- No timebase of 50 ms/div or slower.
- A record is 700 points over 14 divisions; volts = `(code − 128 − YOR) × YINC`.

**Generator**
- Never send `*OPC?` or any query missing from its manual; it can hang the USB interface.
- Replies have no terminator: `read_termination = None`.
- Set amplitude unit to VPP before setting amplitude. High-Z is `:CHANnel<n>:LOAD 10000`.
- Negative numbers are silently ignored (firmware 1.09). A negative offset needs the AMPLitude + `:BASE:HIGH` route (HW_REPORT 13.11).

**Safety (user's standing rules for hardware work)**
- Only SCPI commands found in `docs/`, each cited with its manual page.
- Non-destructive: no `*RST`, no save/erase of setups, no calibration or firmware commands. Restore changed settings.
- Generator outputs stay OFF except when a test needs them, and are switched OFF in a `finally` block.
- Report failures with the exact error; never assume a result.
- Ask before the user has to touch cables or power.
- Bench scripts go in `hwcheck/` and use `.venv-hwcheck` only.

## Not yet verified

The watchdog on a scope that is frozen but still on USB, whether paced table walking always avoids the freeze (one clean run), `:MEASure:PHASe?`, other triggers of the alignment shift, scope power-on state, a faster two-channel read, LAN, Linux, the cause of the one bad capture (HW_REPORT 13.9), what makes the generator's DC drift. See SPEC.md section 17.
