# Bode Plotter — Design & Implementation Spec

PC software that drives a function generator and an oscilloscope to measure the frequency response (gain + phase) of a device under test (DUT) and present it as a Bode plot.

This file is the overview and the index. The detail of each section is in `docs/spec/` (table below). Together they are the source of truth for the design; `HW_REPORT.md` overrides them, and the manuals, where the hardware disagrees.

---

## Where each section lives

Section numbers are stable: source comments cite them (`SPEC.md section 8.6`), and a test (`tests/test_docs.py`) fails when a cited section no longer exists or a section is listed twice.

| Section | Content | File |
|---|---|---|
| 1 | Goals and non-goals | this file |
| 2 | Reference documents and the rules for driver code | this file |
| 3 | Tech stack | this file |
| 4 | Repository layout | `docs/ARCHITECTURE.md` |
| 5 | Launcher scripts | this file |
| 6 | Architecture, driver interfaces, ResponseMeter, registry | `docs/spec/drivers.md` |
| 7 | Data models | `docs/spec/sweep.md` |
| 8.1 to 8.5 | Frequency plan, sweep start, per point, sine fit, pause / abort / re-measure | `docs/spec/sweep.md` |
| 8.6, 8.7 | Channel skew check; through calibration | `docs/spec/skew.md` |
| 9 | Instrument drivers, probe tool, mock instruments | `docs/spec/drivers.md` |
| 10, 11, 12 | GUI; presets and settings; export formats | `docs/spec/gui.md` |
| 13, 14 | Errors, safety, logging; testing | `docs/spec/sweep.md` |
| 15, 16, 17 | Roadmap; milestones; open items to verify on hardware | `docs/spec/roadmap.md` |
| 15, Phase E2 | Web frontend | `docs/spec/web.md` |

Related documents: `docs/ARCHITECTURE.md` (modules, what calls what, where each concern lives), `HW_REPORT.md` (what the hardware really does; it overrides the manuals), `docs/STATE.md` (what is done, what is next), `docs/feature.md` (the user's parked features), `docs/superpowers/specs/` and `docs/superpowers/plans/` (approved feature designs and their implementation plans).

---

## 1. Goals and non-goals

**Goals (v1)**
- Measure gain (dB) and phase (°) from **50 Hz to 20 MHz** using:
  - Scope: **UNI-T UPO1054** (4-channel, 50 MHz, UPO1000 family). Confirmed by `*IDN?` and nameplate in Milestone 0; earlier drafts of this spec said UPO1052.
  - Generator: **UNI-T UTG932E** (2-channel, sine up to 30 MHz, UTG900E family). Its `*IDN?` reports only the family name `UTG900E`.
- Python desktop GUI with a live-updating Bode plot.
- Runs on **Windows and Linux**.
- Connects over **USB (USBTMC) or LAN**, configured per instrument. (LAN was never tested and was dropped by the user on 2026-10-06; serial links are planned, §15 Phase A.)
- Pluggable driver architecture, so the app is **not locked to these two models**.
- Full **simulation mode** (mock instruments + simulated DUT) so everything except the real drivers can be built and tested without hardware.

**Non-goals (v1)**
- Full probe/channel calibration over frequency, trace overlay, auto markers (v2, §15; in progress since 2026-10-06). The single-frequency **channel alignment check** of §8.6 is NOT deferred: it is required in v1.
- Filter recognition (v3, §15).
- Standalone executables (PyInstaller is a later stage).
- Loop-gain injection workflows with amplitude profiles.

---

## 2. Reference documents (MUST read before writing drivers)

These live in `docs/`:

| File | Covers | Status |
|---|---|---|
| `docs/Uni-T_UPO1000_Programming_Manual_0424.pdf` | **Scope SCPI, the manual to cite** (UPO1000 series, channels 1 to 4; 99 pages). Page references in scope driver code use this manual. | present |
| `docs/Uni-T_UPO1002_Programming_Manual_0824.pdf` | Scope SCPI for the two-channel UPO1002 series. Same command set; used in Milestone 0 before the UPO1000 manual was supplied. | present, superseded |
| `docs/UTG900E Programming Manual V1.0.pdf` | Generator SCPI (UTG900E series, which includes the UTG932E) | present |
| `docs/UTG_Series_Programming_Manual_ELV.pdf` | Alternate English UTG900 manual (cross-reference) | not provided |
| `docs/UTG900_eevblog_commands.pdf` (optional) | Community-extracted UTG900 SCPI command list | not provided |
| `HW_REPORT.md` (project root) | Milestone 0, 0b and 0c results: what each command really does on this hardware | present |
| `hwcheck/iolayer.py` | Tested reference implementation of the instrument I/O rules in §9 (55 of 55 checks). The real drivers are built from it. | present |

Where `HW_REPORT.md` and a manual disagree, the hardware result wins.

**Rules for driver code:**
1. Never invent SCPI commands. Every command string in a driver must come from these manuals.
2. Each command entry in a driver's command table carries a comment citing the manual section or page.
3. If the manual is ambiguous or a command is missing, mark the entry `verified=False` in the command table. It is then exercised by the probe tool (§9.4) before the driver relies on it.
4. If a required document is missing from `docs/`, stop and ask the user. Do not guess.

---

## 3. Tech stack

- Python **3.11+**
- **PySide6**: GUI
- **pyqtgraph**: live plots
- **numpy**: math
- **matplotlib**: image export (PNG/SVG/PDF)
- **pyvisa** with selectable backend:
  - `@py` (**pyvisa-py**, plus `pyusb`, `libusb-package`, `zeroconf` optional). **Default.** Free, and the backend all of Milestone 0b and 0c was tested on.
  - `@ivi` (a vendor VISA library). Optional, for users who already have a licensed one. NI-VISA is **not** free for this use (NI includes a licence only with NI software or hardware; otherwise a per-computer deployment licence is sold), so the project must not require or recommend it.
- **platformdirs**: config/preset locations
- **pytest**: tests

Pin versions in `requirements.txt` (minimum versions, not exact pins, unless a known bug requires it).

---

## 4. Repository layout

Moved to `docs/ARCHITECTURE.md`, which is kept in step with the code by a test.

---

## 5. Launcher scripts

Both scripts live in the repo root, are idempotent, and forward extra arguments to the app (e.g. `run.sh --sim`).

**Behaviour (both):**
1. Locate Python ≥ 3.11:
   - Windows: try `py -3.12`, `py -3.11`, then `python`.
   - Linux: try `python3.12`, `python3.11`, then `python3`.
   - Verify the version; if none is suitable, print a clear message with install hints and exit non-zero.
2. Create `.venv` if it is missing. If venv creation fails on Linux, hint at `python3-venv`.
3. Compute a hash of `requirements.txt` and compare it to `.venv/.req_hash`. If it differs or is missing, upgrade pip, `pip install -r requirements.txt` and `pip install -e .`, then write the new hash.
4. Run `python -m bodeplot %*` / `"$@"`.
5. On failure, print the failing step and keep the console open on Windows (`pause`).

**Linux extras (run.sh):**
- If a USB instrument can't be opened due to permissions, the app (not the script) shows a hint pointing to `scripts/99-usbtmc-unit.rules` and the `udevadm` reload commands.

**Windows notes (README):**
- **Default and recommended: `@py` over USB with the WinUSB driver**, bound with Zadig once per instrument (Options → List All Devices, pick the device by USB ID, target driver WinUSB). Verified.
- `@ivi` is optional. It works technically (Milestone 0 passed on NI-VISA 26.5.0, which binds the IVI `Usbtmc` driver by itself), but NI-VISA needs a paid licence for third-party hardware and software, so the README must say so and must not present it as the normal path. Default backend selection is `py`; `auto` tries `@py` first.
- The two are mutually exclusive: with a VISA vendor's USBTMC driver bound `@py` sees nothing, and with WinUSB bound `@ivi` and vendor PC software see nothing.
- pyvisa-py has no USB device clear and no host-buffer flush; the driver layer sends USBTMC INITIATE_CLEAR itself through pyusb (§9.1).
- Resource strings differ per backend (`USB0::22102::2098::<serial>::0::INSTR` on `@py`, `USB0::0x5656::0x0832::<serial>::INSTR` on `@ivi`), so saved connections must be matched by VID/PID/serial. Scope `5656:0832`, generator `6656:0834`.
- Milestone 0 ran on Python 3.14. Add `py -3.14` and `py -3.13` to the launcher's search list.
