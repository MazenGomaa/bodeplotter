# Bode plotter — working notes for Claude

PC software that sweeps a UNI-T generator and reads a UNI-T scope to draw a Bode plot. `docs/SPEC.md` is the source of truth; `HW_REPORT.md` records what the hardware really does and overrides the manuals where they disagree.

## Current state (updated 2026-10-06)

- **Milestones 0, 0b, 0c (hardware gate): done. Verdict GO WITH WORKAROUNDS** (`HW_REPORT.md`, top block and section 12).
- **Milestones 1 to 5: done, against the mock drivers only.** `pytest`: 174 passed (2026-10-06). The user reviewed the GUI and asked for changes, all done (see below).
- **Milestone 6 (real drivers + probe tool): the user said GO on 2026-10-06, with conditions. IN PROGRESS. Stop after Milestone 6 with a report; do NOT start Milestone 7 (bench bring-up).** The user's conditions:
  1. Step tables: ship the measured timebase and V/div tables as data keyed by model + firmware. Never walk them at connect. Each set is still verified by read-back. Table walking is an explicit probe-tool option (`--walk-tables`) with pacing and a warning. Unknown firmware: use the stored tables, warn once, suggest the walk.
  2. Pacing: a configurable minimum gap after timebase and V/div changes (start at 100 ms) on top of `*OPC?`.
  3. Watchdog: if the scope stops answering and the first-level resync fails: generator safe_off, stop the sweep, keep the partial data, tell the user to power-cycle the scope. The app never runs anything that needs elevation (no `pnputil` in the app path; it stays documented in HW_REPORT.md).
  4. SPEC.md fixes: section 1 "UPO1002 family"; 9.2 "tables are walked at connect"; the section 10 skew bullet misplaced inside the Connections dialog; reconcile the "sweep AUTO is a no-op" note in the test suite with HW_REPORT 12.13; remove NORMal sweep from use; rename the driver/registry to upo1000 if cheap.
  5. Process: the project is in git; **commit before every bench run**. Every hwcheck/probe script prints its own file hash at start.
  6. Probe tool: no `:RUN`, no table walk by default, generator outputs OFF.
  7. Also verify on hardware in Milestone 6: deliberately overdrive one channel, record ADC rail codes and the vertical division count, then fix clip detection and auto-range; `:SYSTem:LOCK` on the scope (watch for the manual's 0/1 contradiction).
- The app runs in simulation only; choosing a real connection reports "Milestone 6" and does nothing. Nothing in `src/` talks to an instrument. No `:RUN` anywhere in `src/`.

### What exists

- App: `src/bodeplot/`, tests in `tests/`, venv `.venv` (PySide6 6.11, pyqtgraph 0.14, numpy 2.5, Python 3.14). Run: `run.bat --sim` or `.venv\Scripts\python -m bodeplot --sim`. Tests: `.venv\Scripts\python -m pytest`.
- Qt-free sweep logic is `sweep/core.py`; `sweep/engine.py` is the QThread wrapper. GUI tests run offscreen with `MainWindow.interactive = False` (no modal dialogs).
- v1 skew feature, built to the user's spec (SPEC 8.6): `measure/skew.py` (states -1.85/+0.15/+2.15/+4.15 ns, snap within 0.3 ns, gain warn > 0.3 dB, `phase_corr = phase - 360 f dt`), wizard in `gui/dialogs.py`, session validity in `sweep/core.py` (`Session`, `alignment_epoch`), mock skew in `drivers/mock.py`, tests in `tests/test_skew.py`.
- GUI changes after the user's review (2026-10-06): Fit view / follow mode (`gui/bode_plot.py`), k/M number entry and axes (`gui/si_widgets.py`, `units.py`), File/View/Help menus, all panels shown at every start-up, dark theme. `gui/theme.py` holds every colour; nothing else hard-codes one except the white-background image export. The palette is the dataviz skill's reference dark palette; its validator passes (2026-10-06). The user tested the dark theme on their display and approved it.
- Screenshots of the sim GUI: `docs/screenshots/` (offscreen renders; regenerate with a script that sets `QT_QPA_PLATFORM=offscreen` and `QT_QPA_FONTDIR=C:\Windows\Fonts`).
- I/O layer for the bench: `hwcheck/iolayer.py`, test suite `hwcheck/t0b_iolayer.py` (last hardware run 55/55 on `@py`). Milestone 6 is to be built from it.

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

Project root: `C:\Users\mazen\Desktop\bodeplotter`. Not a git repository. Paths are relative to the root.

| Path | What |
|---|---|
| `docs/SPEC.md` | design spec; milestones in section 16, open items in section 17 |
| `docs/*.pdf` | the programming manuals (UPO1000 manual is the one cited for the scope, as `U1K p.N`) |
| `HW_REPORT.md` | hardware report: Milestone 0 findings S1-S9, G1-G5; section 12 = 0b, 0c, alignment fault, capture benchmark |
| `README.md` | status, how to run, features |
| `src/bodeplot/` | the app (`gui/`, `sweep/`, `measure/`, `drivers/`, `io/`) |
| `tests/` | pytest suite (mock drivers, offscreen GUI) |
| `.venv/` | app venv |
| `hwcheck/` | bench scripts and the I/O layer; `scpi.py` has every command with its manual page |
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

**Safety (user's standing rules for hardware work)**
- Only SCPI commands found in `docs/`, each cited with its manual page.
- Non-destructive: no `*RST`, no save/erase of setups, no calibration or firmware commands. Restore changed settings.
- Generator outputs stay OFF except when a test needs them, and are switched OFF in a `finally` block.
- Report failures with the exact error; never assume a result.
- Ask before the user has to touch cables or power.
- Bench scripts go in `hwcheck/` and use `.venv-hwcheck` only.

## Not yet verified

Real drivers in the app (Milestone 6), CH3/CH4, `:MEASure:PHASe?`, ADC rail codes, on-screen vertical divisions (8 assumed), other triggers of the alignment shift, scope power-on state, `:SYSTem:LOCK`, a faster two-channel read, LAN, Linux, the GUI's modal dialogs on a real display. See SPEC.md section 17.
