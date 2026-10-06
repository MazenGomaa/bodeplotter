# Project state

What is done, what is next, and the decisions that are not obvious from the code. `CLAUDE.md` points here; update this file (not `CLAUDE.md`) when the state changes. Hardware facts are not kept here: they are in `HW_REPORT.md`.

## Start here

**v1 is done and accepted. The work in hand is v2, milestone A1: through calibration.**

1. Design (approved by the user on 2026-10-06): `docs/superpowers/specs/2026-10-06-through-calibration-design.md`.
2. Implementation plan (2026-10-06): `docs/superpowers/plans/2026-10-06-through-calibration.md`. It lists six places where it departs from the design; the user chose the "Native" execution (one session, test-first, a commit per task). Check `git log` and the plan's checkboxes for how far it got.
3. It ends with a bench acceptance that needs the user at the bench (design section 10; plan Task 10): calibrate, through sweep (target 0.02 dB and 0.1 deg), the RC low-pass, reconnect. **Ask what is wired before every bench run**, commit before it, and never cut a bench script's output short.
4. Bench, as the user described it at the start of the session of 2026-10-06 (v2): scope CH1 and CH2 both on generator CH1, the app closed. That was one statement at one moment: ASK again before a run. Probes are 10X; they are trimmed for other channels than the ones they sit on (0.1 to 0.2 dB tilt), which is exactly what the calibration is meant to remove.
5. After A1: `docs/spec/roadmap.md` sections 15 and 16. Do not start A2 or anything later without the user.

The documents were split on 2026-10-06 at the user's request (`docs/spec/`, `docs/hw/`, `docs/ARCHITECTURE.md`, this file); `tests/test_docs.py` guards the split.

## Roadmap in short (user's update of 2026-10-06; full text in `docs/spec/roadmap.md`)

Order: **A. v2 on Windows** (A1 through calibration, A2 connection spec + per-driver skew states, A3 trace overlay, A4 auto markers) -> **B. v3 filter recognition** (B1 metrics, B2 classification, B3 rational fit, B4 GUI and export) -> **C. Windows full verification** on the real instruments, reported in HW_REPORT -> **D. WSL**, software only (pytest and `--sim` on Linux, OS-specific fixes; optional usbipd smoke test, labelled as not representative) -> **E. Raspberry Pi Zero 2 W**: E1 hardware gate (stop and report), E2 web frontend (FastAPI + WebSocket in `web/` next to `gui/`, same repo, shared core), E3 deployment.

- Candidate drivers, unscheduled, each with its own hardware gate first: R&S HMO1202 (USB-TMC, switch it from VCP), UNI-T UTD2052CL, JDS6600 generators (serial), tinySA Ultra (serial, magnitude only, above 30 MHz).
- Parked, see `docs/feature.md` (the user's file): LCR / impedance mode (decision after v3; it needs the v2 calibration and the v3 fitting code, so keep both reusable; the user's UT612 can be the reference meter), curve tracer (needs hardware that does not exist yet; no design work).
- Dropped by the user: the scope's LAN and web UI; restoring the generator's settings after a sweep.
- Where the roadmap update and the code disagree, the code wins: nothing is "snapped" to the skew states any more (they only name the state and feed one warning), and the drivers already sit on a `Transport` interface (only `VisaTransport` exists, `open()` still takes resource + backend).

## Milestones

- **Milestones 0, 0b, 0c (hardware gate): done. Verdict GO WITH WORKAROUNDS** (`HW_REPORT.md`, top block and section 12).
- **Milestones 1 to 5: done, against the mock drivers only.** `pytest`: 174 passed (2026-10-06). The user reviewed the GUI and asked for changes, all done (see below).
- **Milestone 6 (real drivers + probe tool): DONE 2026-10-06.**
- **Milestone 7 (bench bring-up): DONE 2026-10-06.** The user ran the acceptance from the GUI on the real instruments (connect with no pop-up, skew check, one Sine fit sweep and one Fast preview sweep of their RC filter: "both sweeps look right") and asked for the milestone to be marked done. Full record: HW_REPORT section 13 (13.13 to 13.26 are from that session). `pytest`: 264 passed (2026-10-06, night). Everything is committed (`git log`); the only untracked item is `graphify-out/`. `docs/feature.md` (the user's parked-feature notes) is tracked since 2026-10-06.
  - **What is still open (none of it blocks using the app):** (a) the trigger of the +2.15 ns alignment state (13.25); (b) FIXED 2026-10-06 night (13.27): Fast preview keeps off 200 / 500 ns/div (`DigitizerCaps.running_avoid_timebases`, `_off_busy_timebase`), 6 bench sweeps with no pause; what the scope is busy with there is unknown; (c) the user's report of a gain drop near the end of a Fast preview sweep, not reproduced in 15 bench sweeps: ask for a CSV or screenshot; (d) **LAN and the scope's web UI: DROPPED by the user** ("not an option most of the time"), do not raise it again; (e) through calibration (SPEC 15, v2) and Linux; (f) the user's two probes are compensated for the "wrong" channels (0.1 to 0.2 dB tilt), their job with the scope's cal output; (g) the unplugged-cable message was seen by the user on the bench; the "measured value" wording of the skew wizard was in their acceptance run and drew no comment.
  - **No skew pop-up on connect any more (user decision 2026-10-06 night)**: after a connect, a resync or "Front panel was used" the app only shows the red UNCHECKED status and a log line (`MainWindow._prompt_recheck`). Starting a Sine fit sweep without a valid check still asks.
  - **Bench manners learned in that session:** ask what is wired before EVERY bench run, even when a script guards itself (the user stopped a run for this); never cut a bench script's output short (see Rules for instrument work).
  - The numbered list below is the hand-over the session started from; every item is marked DONE with its result.
    1. Ask what is wired now, and check the instruments answer: `.venv-hwcheck\Scripts\python.exe -W ignore hwcheck\s6_state.py "@py"` (read-only). Commit before every bench run. Ask before the user has to touch cables or power.
    2. **DONE 2026-10-06 (HW_REPORT 13.13): skew wizard in the GUI on the real instruments** gave +0.14 ns, snapped to +0.15 ns, gain mismatch -0.019 dB; the through sweep from the GUI after it (114 points, 50 Hz to 20 MHz, 5 Vpp, 114 s): 99.6 to 100.1 % of input, phase within about 0.3 deg. The wizard's intro text named the wrong frequencies; fixed.
    3. **DONE 2026-10-06 (HW_REPORT 13.18): the RC phase lead is the capacitor's own loss.** The 100 nF is a film part; the user's LCR meter read D = 0.001 / 0.003 / 0.009 / 0.028 and Cs = 105.7 / 105.4 / 104.4 / 102.6 nF at 100 Hz / 1 k / 10 k / 100 kHz. A model with those values gives the measured phase within 0.11 deg from 5 to 100 kHz. Nothing to fix in the app. The user also has a ceramic and a mica capacitor and an LCR meter with USB (UNI-T UT612).
    4. **DONE 2026-10-06 (HW_REPORT 13.14): CH3 / CH4 work.** Their delay is +0.08 ns, not +0.15 ns, and the snap left -0.39 deg at 20 MHz, so (user decision) **the skew check now snaps only for reference CH1 / DUT CH2** (`skew.SNAP_PAIR`, `skew.snaps`); any other pair or order applies the measured value with no warning. Confirmed on the bench the same evening: +0.10 ns applied, not snapped, through sweep +0.07 deg at 20 MHz, 116 s. CH4 reads about 1 % below CH3 at 20 MHz (not corrected).
    5. **DONE 2026-10-06 (HW_REPORT 13.15): watchdog with the scope's USB cable pulled mid-sweep works**: generator off 2.6 s after the pull, 26 of 114 points kept, error shown, session dropped. After replugging (no power cycle) the scope answered at once, unlocked, on the sweep's timebase. Fixed afterwards: the false "was resynchronised" warning, and the advice now says to check the USB cable when the device is gone from the bus (`Transport.present`, `UNPLUGGED_ADVICE`); the new text has only run against the fakes. The generator-off timing was changed later the same evening (see 13.19). A scope that is frozen but still on the bus is still untested.
    6. **DONE 2026-10-06 (HW_REPORT 13.16): a power cycle clears the panel lock** (locked with `s6_lock.py on`, key ignored with a "locked" message, after the power cycle `:SYSTem:LOCK?` 0 and the panel works). The scope came back with its previous settings, sweep AUTO.
    7. **DONE 2026-10-06 (HW_REPORT 13.17): `--walk-tables` of the probe tool, paced at 250 ms, ran once to the end with no freeze**; the walked tables equal the shipped ones and were written to `%LOCALAPPDATA%\bodeplot\step_tables.json`. One run only: the two earlier freezes are still unexplained, so keep walking it only with the user present.
    8. Not bench work: Linux (never tested), the open ideas below.

## Project decisions and changes of 2026-10-06

The hardware findings of that day are in `HW_REPORT.md` ("Measured and settled on the bench").

- **GUI added on the user's request, all seen and accepted by the user ("looks fine")**: toolbar **Mode box** (Instruments / Simulation; only while disconnected; `MainWindow.set_mode`); **Settings dialog** (File > Settings or Ctrl+comma; tabs General / Instruments / Simulation; `SettingsDialog`, `ConnectionsPanel`, `SimSettingsPanel`) with the stored `startup_mode` (`instruments` default, `simulation`, `last`); `--sim` applies to that run only; **Vertical unit box** next to Fit view (dB, Voltage = DUT output in Vpp at the probe tip, % of input; `BodePlot.unit_box`, stored as `vertical_unit`; image export follows it); frequency tick labels when zoomed inside a decade (`SiAxis.tickValues`); a ticked checkbox stays visibly ticked while the panel is disabled. "Sim settings" is in the File menu only. `scope_min_gap_ms` is read from the settings file and limited to 100..2000 ms.
- "Descending resets itself" (user report): the option itself works (runs top-down, survives a restart); the only fault found was the disabled-checkbox drawing, now fixed. Whether that is what the user saw is not confirmed; ask if it happens again.
- **Open ideas, not implemented**: through calibration (SPEC section 15, v2); a faster sweep (see below). **Decided 2026-10-06: the generator's settings are NOT restored after a sweep**; output off is enough (user).
- **Reference-level warning (user asked for it, 2026-10-06)**: after a sweep, one warning in the status log when the lowest reference reading is below 30 % of the generator's amplitude setting (`core.reference_level_warning`); no flag, nothing stops. Mock only.
- **The test suite sets `BODEPLOT_NO_HARDWARE`** (every VISA open raises). Reason: on 2026-10-06 a GUI test opened a real connection to both instruments by accident. Never remove that guard.
- Real connections are implemented (Connections with empty fields finds both instruments by `*IDN?`). No `:RUN` anywhere in `src/`.

## The user's standing conditions from the Milestone 6 GO (keep them)

1. Step tables are shipped data keyed by model + firmware (`drivers/step_tables.py`). Never walked at connect. Every set is verified by read-back. Walking is only the probe tool's `--walk-tables` (paced, with a warning). Unknown firmware: stored tables, one warning, suggest the walk.
2. Pacing: minimum gap after timebase and V/div changes (`scope_min_gap_ms`, default 100) on top of `*OPC?`.
3. Watchdog: scope stops answering and the first-level resync fails -> generator safe_off, sweep stops, partial data kept, user told to power-cycle. The app never runs anything that needs elevation (no `pnputil`, no `subprocess` in `src/`; a test enforces it).
4. NORMal sweep is not used (the driver refuses it). Driver and registry are named upo1000.
5. Process: the project is in git; **commit before every bench run**. Every hwcheck script prints its file hash and git commit at start (`hwcheck/common.py`); the probe tool prints its own and the drivers' hashes.
6. Probe tool: no `:RUN`, no table walk by default, generator outputs OFF.

## What exists

- App: `src/bodeplot/`, tests in `tests/`, venv `.venv` (PySide6 6.11, pyqtgraph 0.14, numpy 2.5, Python 3.14). Run: `run.bat` (real instruments unless Settings > Start-up mode says otherwise; add `--sim` for one simulated run) or `.venv\Scripts\python -m bodeplot`. Tests: `.venv\Scripts\python -m pytest`.
- Qt-free sweep logic is `sweep/core.py`; `sweep/engine.py` is the QThread wrapper. GUI tests run offscreen with `MainWindow.interactive = False` (no modal dialogs).
- v1 skew feature, built to the user's spec (SPEC 8.6): `measure/skew.py` (states -1.85/+0.15/+2.15/+4.15 ns, snap within 0.3 ns, gain warn > 0.3 dB, `phase_corr = phase - 360 f dt`), wizard in `gui/dialogs.py`, session validity in `sweep/core.py` (`Session`, `alignment_epoch`), mock skew in `drivers/mock.py`, tests in `tests/test_skew.py`.
- GUI changes after the user's review (2026-10-06): Fit view / follow mode (`gui/bode_plot.py`), k/M number entry and axes (`gui/si_widgets.py`, `units.py`), File/View/Help menus, all panels shown at every start-up, dark theme. `gui/theme.py` holds every colour; nothing else hard-codes one except the white-background image export. The palette is the dataviz skill's reference dark palette; its validator passes (2026-10-06). The user tested the dark theme on their display and approved it.
- Screenshots of the sim GUI: `docs/screenshots/` (offscreen renders; regenerate with a script that sets `QT_QPA_PLATFORM=offscreen` and `QT_QPA_FONTDIR=C:\Windows\Fonts`).
- I/O layer for the bench: `hwcheck/iolayer.py`, test suite `hwcheck/t0b_iolayer.py` (last hardware run 55/55 on `@py`). The app drivers are a port of it.
- Real drivers: `drivers/uni_t_upo1000.py` (`UniTUPO1000`), `drivers/uni_t_utg900e.py`, on `drivers/transport.py` (`VisaTransport`; tests inject `tests/fakes.py`), with `drivers/scpi.py`, `drivers/step_tables.py`, `drivers/connect.py`. Probe tool: `python -m bodeplot.tools.probe`. Watchdog and panel lock live in `sweep/core.py` (`Session.mark_dead`, `end_measurement`), the engine drops a dead session (`_drop_if_dead`).
- Auto-range: clipped captures estimate the amplitude from the share of samples on the rails (`autorange.clipped_vpp_estimate`); `Waveform.rail_fraction`, `DigitizerCaps.data_vertical_divs`.

Older memory notes for this project are under `~/.claude/projects/C--Users-mazen-Desktop-bodeplotter-docs/memory/` (sessions used to be started in `docs/`).
