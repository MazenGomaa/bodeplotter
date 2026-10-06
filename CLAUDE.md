# CLAUDE.md

Bode plotter: PC software that sweeps a UNI-T generator and reads a UNI-T scope to draw a Bode plot. This file is an index plus the hard rules. Keep it small (a test limits its size): state, findings and design go into the files below, not here.

## Where everything lives

| Read this | For |
|---|---|
| `docs/STATE.md` | **start here**: what is done, what is next, the user's decisions, the state of the bench |
| `docs/ARCHITECTURE.md` | modules, what calls what, where each concern lives (checked against the code by a test) |
| `docs/SPEC.md` | design spec: overview and index; the detail is in `docs/spec/` (`drivers.md`, `sweep.md`, `skew.md`, `gui.md`, `web.md`, `roadmap.md`) |
| `HW_REPORT.md` | what the hardware really does: the current verified facts, and the index of the dated test runs in `docs/hw/`. It overrides the manuals where they disagree |
| `docs/superpowers/specs/`, `docs/superpowers/plans/` | approved feature designs and their implementation plans |
| `docs/feature.md` | the user's notes on parked features (LCR mode, curve tracer) |
| `docs/*.pdf` | the programming manuals (the UPO1000 manual is the one cited for the scope, as `U1K p.N`) |
| `README.md` | status, how to run, features, for a user |

Section numbers of the spec and of the hardware report are stable; source comments cite them (`SPEC.md section 8.6`, `HW_REPORT.md 13.21`). Find a section through the index table in `docs/SPEC.md` or at the end of `HW_REPORT.md`.

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
| Read-only check that both instruments answer | `.venv-hwcheck\Scripts\python.exe -W ignore hwcheck\s6_state.py "@py"` |

`tests/conftest.py` puts `src/` on the path, sets `QT_QPA_PLATFORM=offscreen` and sets `BODEPLOT_NO_HARDWARE` (every VISA open raises; never remove it: on 2026-10-06 a GUI test opened a real connection by accident). `BODEPLOT_CONFIG_DIR` redirects the settings and presets folder.

This machine: Windows 11, Python 3.14 (`py -3.14`), both instruments bound to WinUSB, so the backend is `@py`. No `pdftoppm`: extract PDF text with `pypdf` in a throwaway venv in the scratchpad. The project is a git repository with no remote.

## Hard rules for instrument work

Evidence for each is in `HW_REPORT.md`. Breaking one of these has cost a bench session before.

**Scope (UPO1054)**
- Never send `:RUN`. It can shift CH2 against CH1 by 2 ns steps, and nothing documented undoes it. Restart with `:TRIGger:SWEep AUTO`.
- Never send `:WAVeform:DATA?` unless a stopped record exists (single shot: arm, wait for STOP to hold, then fetch). An empty reply must not be retried in place: resync and take a new acquisition.
- Do not try to recover the scope with USBTMC `INITIATE_ABORT_BULK_IN` or a USB port reset; both made it stop accepting writes.
- A read with no query pending re-sends the last reply forever. Never loop "read until timeout".
- `*OPC?` after every write; plain-decimal numbers only; probe ratio as `1X`; read back timebase and V/div.
- No timebase of 50 ms/div or slower. NORMal sweep is not used. 500 uV/div is not used.
- Step tables are shipped data; never walk them at connect (the walk has frozen the scope; only `probe --walk-tables`, with the user present).
- Do not use the scope's front panel while a test runs.

**Generator (UTG932E)**
- Never send `*OPC?` or any query missing from its manual; it hangs the USB interface.
- Replies have no terminator: `read_termination = None`.
- Set the amplitude unit to VPP before setting an amplitude. High-Z is `:CHANnel<n>:LOAD 10000`.
- Never send a negative number: it is silently ignored. A negative offset goes through AMPLitude + `:BASE:HIGH` (`UniTUTG900E._set_level`).

**Safety (the user's standing rules)**
- Only SCPI commands found in the manuals in `docs/`, each cited with its manual page.
- Non-destructive: no `*RST`, no save / erase of setups, no calibration or firmware commands. Restore changed settings.
- Generator outputs stay OFF except when a test needs them, and are switched OFF in a `finally` block.
- The app never runs anything that needs elevation; no `subprocess` in `src/` (a test enforces it).
- Report failures with the exact error; never assume a result.

**Bench manners**
- Ask what is wired before EVERY bench run, even when a script guards itself. Ask before the user has to touch cables or power.
- Commit before every bench run (every bench script prints its file hash and the git commit).
- Bench scripts go in `hwcheck/`; those that only use the bench I/O layer run with `.venv-hwcheck`.
- Never pipe a bench script into `Select-Object -First N` or anything else that ends the pipeline early: the script is killed, its `finally` never runs, and the generator stays ON with the panel locked. Write the output to a file or use `-Last`. After a run that ended oddly, run `s6_state.py`.

## Keeping the documents

- A hardware finding goes into a new numbered subsection in `docs/hw/`, the fact it changes into the facts sheet of `HW_REPORT.md`, then into the driver, then into `tests/fakes.py`.
- A state change (milestone done, user decision, hand-over) goes into `docs/STATE.md`.
- A new or moved module, or a changed import, goes into the table of `docs/ARCHITECTURE.md`; `tests/test_docs.py` fails until it does.
- The user's dropped items, not to be raised again: the scope's LAN and web UI; restoring the generator's settings after a sweep; NI-VISA.
