# Hardware report

What the two instruments really do on this bench, as measured. Where this report and a manual disagree, the hardware result wins.

It has two parts:

1. **Current verified facts** (this file): what is true today, each fact with the section that holds the evidence. Read this first; it is the only part that is kept current.
2. **History** (`docs/hw/`): the dated test runs, section by section, as they were written. Index at the end of this file.

Keeping it: a new bench finding gets a new numbered subsection in a history file (the next one is section 15, a new file), and the fact it establishes or changes is edited in here in the same commit. Then the driver, then `tests/fakes.py`, so the suite keeps it. Section numbers never change: the code cites them (`HW_REPORT.md 13.21`), and `tests/test_docs.py` fails when a cited section is missing.

Verdict of the hardware gate (Milestones 0, 0b, 0c): **GO WITH WORKAROUNDS** (`docs/hw/m0-gate.md`). Milestone 7, the app on the real instruments, was accepted by the user on 2026-10-06 (13.28).

---

## Current verified facts

### Instruments and this machine

| | Scope | Generator |
|---|---|---|
| Model | UNI-T **UPO1054** (4 ch, 50 MHz). Not UPO1052. | UNI-T UTG932E |
| `*IDN?` | `UNI-T Technologies,UPO1054,APX1424510001,1. 01. 0047` | `UNI-T Technologies,UTG900E,69746177,1.09` |
| USB VID:PID | `5656:0832` | `6656:0834` |
| `@py` resource | `USB0::22102::2098::APX1424510001::0::INSTR` | `USB0::26198::2100::69746177::0::INSTR` |

- Windows 11 Home 10.0.26200, Python 3.14.6 (`py -3.14`).
- **Both instruments are bound to WinUSB (Zadig): use the `@py` backend.** `@ivi` sees nothing in this state.
- No `pdftoppm`, so the Read tool cannot open the PDFs. Extract text with `pypdf` in a throwaway venv in the scratchpad (not in `.venv-hwcheck`).
- Node.js 24 LTS at `C:\Program Files\nodejs\node.exe` (installed 2026-10-06; not on PATH in an already-open shell). The dataviz palette validator was run with it: the theme's colours pass.
- Linux has not been tested at all. `run.sh` and `scripts/99-usbtmc-unit.rules` were written but never run.

### Rules that follow from the hardware

The hard rules are also in `CLAUDE.md`, which is read every session. Evidence: sections 8 and 12, and `docs/spec/drivers.md` sections 9.1 to 9.3.

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

### Decisions and findings to keep in mind

- **Backend (user, 2026-10-05): NI-VISA is dropped** (not free for third-party use; listed from 201 USD). Use pyvisa-py (`@py`) + WinUSB. NI-VISA is still installed; the user has not asked for an uninstall.
- **Never send `:RUN`** (HW_REPORT 12.11). A `:RUN` sent after the USB session is reopened shifts scope CH2 against CH1 by 2 ns steps (states +0.15, +2.15, +4.15, -1.85 ns; 15 deg per step at 20 MHz) about half the time, and no documented command undoes it. `iolayer.py` blocks it in `write()`; restart with `:TRIGger:SWEep AUTO`. hwcheck: `scpi.S_RUN` is now `:TRIGger:SWEep AUTO`; the debug scripts whose purpose is to send `:RUN` refuse to start without `--allow-run`. `hwcheck/s0c_realign.py` (both probes on one node) checks alignment (`--check`) or re-rolls it; it is an optional bench tool, not used by the app. Untested: whether front-panel Run/Stop, a power cycle or a replug re-roll the alignment.
- **Capture method: single shot** (HW_REPORT 12.12, `hwcheck/s6_capbench.py`, run 2026-10-06). 0.8 s per capture. Free-running capture (sweep AUTO, `:STOP`, read, restart with SINGle then AUTO) was no faster and failed every second capture with `status did not reach STOP after :STOP (last TRIGED)`; cause found (HW_REPORT 12.13, `hwcheck/dbg6_freerun.py`): **a `:STOP` is only valid once the status has read `TRIGED` since the last restart**; sent earlier it either does not last or stops the scope with no record (`:WAVeform:DATA?` answers an empty block). With that rule the best free-running method takes 0.93 s, still slower than single shot. About 0.35 s of each capture is the two-channel read; shortening it has not been tried. Alignment did not move over 30 resyncs.
- **Probes:** 10X by default, scope kept at PROBe 1X with x10 in software (HW_REPORT 12.10); 1X only for small signals below about 1 MHz. No BNC tee is available: the two-channel tests use two probes on generator CH1.
- The user sometimes switches the generator output on from the front panel between runs; scripts force both outputs OFF at start and end.
- Do not use the scope's front panel while a test runs; it made the scope ignore commands.

### Scope behaviour found in Milestone 0b (section 12; `docs/spec/drivers.md` section 9)

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

### Measured and settled on the bench (do not re-derive)

- **The DC at the scope inputs is the GENERATOR's, and it varies**: about +62 mV, -9 mV and +38 mV at the probe tips at 1 Vpp on three occasions (warm-up drift is a guess, not measured). Proof: CH2 on the capacitor at 2 mV/div reads +0.3 mV at the input with the output OFF and +4.1 mV with it ON; it follows the generator's offset setting. The user's scope self-cal did NOT remove it (I first said it had; corrected in HW_REPORT 13.11). The scope's own offset is 0.3 mV or less from 500 uV to 5 mV/div; CH1's zero on the coarse steps (20 mV/div and up) wanders by 2 to 5 codes, so absolute DC is only trustworthy on the sensitive steps. GND coupling is a drawn line (code 127), not a measurement.
- **The app's DC handling is bench-proven with DC present** (auto-range re-centres with the channel offset, never picks a V/div the DC does not fit in, the driver puts the offset back in volts after a V/div change, 500 uV/div is never used): RC sweeps with +60, +100 and -100 mV of generator offset were correct down to 1 mV/div. **DC coupling stays the default**; AC coupling gives the same result (within 0.03 dB / 0.2 deg to 22 kHz, no penalty at 50 Hz with 10X probes) and is selectable in the GUI.
- **RC low-pass (1 k, 100 nF) reference result**: corner 1513 Hz (C = 105 nF), gain within 0.06 dB to 22 kHz and within about 0.6 dB down to -47 dB (340 kHz); noise floor -52 to -60 dB at 1 Vpp with 10X probes. **Timed full-range sweep: 114 points, 50 Hz to 20 MHz, 118.8 s (1.04 s per point).** The user's own sweep from the GUI on the real instruments "worked fine" (their report, no data file).
- **The generator ignores every negative number** (OFFSet, LOW; any number format; no error; firmware 1.09). The driver reaches a negative offset with AMPLitude A + 2d then `:CHANnel<n>:BASE:HIGH` A/2 - d with the output off; lowest offset = minus half the amplitude (`UniTUTG900E._set_level`). Never send the generator a negative number.
- **Scope settings are saved before and restored after every sweep, skew check and re-measure** (`Digitizer.save_setup` / `restore_setup`, `Session.begin_measurement` / `end_measurement`). Bench: all 19 settings come back, also from a channel that was off and from probe ratio 10X. Scope facts: `:CHANnel<n>:SCALe` is IGNORED on a channel that is switched off (restore DISPlay last); `:CHANnel<n>:SCALe` and `:TRIGger:LEVel` take input-referred volts and report probe-scaled ones; `:CHANnel<n>:OFFSet` is not scaled.
- **Bad-capture guard**: a capture whose reference fit is below 6 dB SNR is written to `.npz` (`captures/` next to the app's log file, or `hwcheck/results/m7/captures/`), retried up to 2 times, then flagged `REF_SUSPECT` (`measure/meters.py`, `core.save_bad_capture`). The one fault that prompted it (78.62 Hz, AC, first point after a 10 to 5 ms/div change: both channels 0.021 V instead of 0.496 V) was NOT reproduced in 40 repeats (`hwcheck/m7_repeat.py`), so the retry has only run against the simulators. Likely cause found later (13.20): the record read before the scope had finished it after a timebase change; not proven. If a `badcapture_*.npz` ever appears, look at it.
- **The RC phase lead is not an instrument effect**: same phase within 0.14 deg on every V/div step (`hwcheck/s7_rangephase.py`), probes within 0.2 deg on a through sweep. It is the capacitor's loss, measured with an LCR meter (HW_REPORT 13.18).
- Bench results of Milestone 6 (HW_REPORT 12.14): **rail codes are 1 and 254** (clip = code <= 1 or >= 254); data cover 10.1 divisions, the screen grid has 8 (user counted); overdriving CH2 does not disturb CH1; **`:SYSTem:LOCK ON` locks the panel, read-back 1 = locked**, it survives a closed session, so the driver unlocks after every measurement and on close (`probe --unlock` as the fallback).
- Earlier in Milestone 7 (HW_REPORT 13.1 to 13.6): probe tool on the real instruments 63/63; through sweeps (both probes on generator CH1) 50 Hz to 20 MHz: gain within 0.05 dB, phase within 0.3 deg, level flat within 1.3%; auto-range hysteresis; skew check always at 10 and 20 MHz; at 500 uV/div an off-scale or clipped trace reads mid-scale codes with NO rail code, so that step is not used (`UniTUPO1000.UNUSABLE_VDIV`); the scope keeps the channel offset in divisions across V/div changes.
- **Later on 2026-10-06 (HW_REPORT 13.19)**: the CH3 / CH4 gain difference follows the probes (swapping them turned the droop into a rise), so it is probe compensation. **The generator now goes off at the first failed transfer inside a scope resync** and comes back on if the scope recovers (`Digitizer.on_link_trouble`, `Session._link_trouble`, `core.measure_with_output`); this replaces the earlier decision to leave it on during the resync. Fakes only.
- **Sweep speed (HW_REPORT 13.20, `hwcheck/s7_capspeed.py`)**: of 1.05 s per point, 0.77 s is the scope's own (single-shot cycle 0.40 s at any timebase, about 0.1 s busy after STOP, `:WAVeform:DATA?` 0.12 to 0.15 s per channel); the generator's frequency set + read-back is 0.17 s; the driver's own overhead about 0.15 s. The capture margins are driver attributes now (`ARM_QUIET_S` 0.3, `STOP_HOLD_S` 0.1, `MIN_WAIT_EXTRA_S`, `STATUS_POLL_S`), values unchanged. **Do not shorten `STOP_HOLD_S` towards 0: with no hold, every capture after a timebase change returned a stale reference record (12 of 12), the signature of the bad capture of 13.9.** Shortening it to 0.05 s gains about 0.05 s, below that nothing. Quiet time 0.3 -> 0.1 s gains 0.19 s only on points with a timebase change; no double arm seen in 12 captures per value, which does not rule it out.
- **Stale-record check (HW_REPORT 13.22)**: `UniTUPO1000.acquire` throws away a record whose time span does not match the timebase that is set and acquires again, with no resync (`stats["stale_records"]`). Bench-proven with the hold time forced to 0: 13 caught, 48 of 48 captures good.
- **Continuous capture tried (user's idea, HW_REPORT 13.21, `hwcheck/s7_stream.py`)**: reading both channels from the running scope (sweep AUTO, no stop) takes 0.21 s against 0.93 s and the gain is as good, but the two channels then come from different acquisitions and the phase scatters: sd 0.3 to 0.4 deg up to 1 MHz, 6 deg (range +-11) at 20 MHz. One empty `:WAVeform:DATA?` reply in about 330 reads (resync recovered it). So single shot stays for phase. **Built on it the same evening (user's request, HW_REPORT 13.23): `Method.PREVIEW`, "Fast preview (rough phase)" in the Method box** (`Digitizer.acquire_running`, `UniTUPO1000._wait_running`, `Flag.PREVIEW`; no skew check asked for; mock and fakes model the scatter). Bench: 114 points in 52.8 s (0.46 s per point, 2.2 times faster), gain as single shot, phase sd 0.4 deg below 100 kHz rising to 3.6 deg above 5 MHz, 3 stale records caught and re-read, no empty reply. The user has not yet tried it in the GUI. The phase scatter cannot be subtracted like the skew: it is a new random value on every read. The scope also has a web UI and LAN (user); not looked at, and its own data stream is undocumented.
- **Scope built-in measurements tested (HW_REPORT 13.26, `hwcheck/s7_builtin.py`): not worth using.** `:MEASure:VPP?` / `VAMPlitude?` / `VRMS?` / `PHASe?` / `PDELay?` (U1K p.30 to 32) all answer. Amplitude in 1-code steps (0.8 %, 0.07 dB at 1 Vpp on 20 mV/div) and 1 to 2 % high; **phase only on a stopped record (`*` while running), resolution 0.36 deg**, up to 0.9 deg off at 20 MHz; 0.056 s per query stopped, 0.006 s running. It would save about 0.1 s per point and cost a factor of ten in resolution. The driver keeps `has_builtin_*` False; "Scope built-in" stays a Simulation-only method.
- **Fast preview after the user tried it (HW_REPORT 13.24)**: fixed: the Method box no longer falls back to Sine fit on every session update (`ConfigPanel.set_has_builtin`); an empty reply of the running scope no longer causes a resync and a skew prompt (sentinel check, wait 0.5 s, read again). **Not fixed: at 200 and 500 ns/div (about 0.7 to 3.5 MHz) the running scope now and then goes busy for about 3.4 s** (empty reply after 1.1 s, twice), roughly once per full preview sweep; the point then takes about 4 s. Nothing on the PC side shortens it; avoiding those two timebases in preview mode is an untried idea. The user also saw "gain drops / phase too low" near the end of a preview sweep, fixed by re-measuring: NOT reproduced in 9 bench sweeps, unexplained; ask for a screenshot or CSV.
- **+2.15 ns state in the user's GUI session (HW_REPORT 13.25, user's report only)**: the skew check read 2.15 ns repeatedly until the user restarted the scope, then +0.15 ns again. So a scope restart can reset the alignment (one observation). What shifted it is unknown; no `:RUN` was sent. Tested the same night and NOT the cause (`hwcheck/m7_previewskew.py`): ten Fast preview sweeps and twelve resyncs of a running scope, skew check after each, delay +0.08 to +0.10 ns throughout. Still open: the two killed bench scripts, reconnects, front-panel use. If it happens again, ask what was done just before. After the restart CH1 / CH2 reads +0.08 to +0.10 ns and +0.17 dB (earlier +0.14 to +0.17 ns, -0.02 dB), so the snap to +0.15 ns over-corrected by 0.06 ns on this pair too. **User decision 2026-10-06 (night): the skew check always applies the MEASURED delay; nothing is snapped any more** (`skew.evaluate`; `SkewCheck.snapped` is always False in new results; the known states only name the state in the wizard, `skew.near_state`, and feed the "fits no known state" warning on CH1 / CH2). This replaces the earlier "snap only on CH1 / CH2" rule.

- **Through calibration on the bench (section 14, 2026-10-07)**: the probes' difference on CH1 / CH2 is a gain tilt from 0.09 dB at 50 Hz to 0.18 dB at 20 MHz and a delay of 0.085 to 0.092 ns (0.5 deg at 20 MHz); with reference and DUT exchanged the same values with the opposite sign. After calibration a through sweep has no mean error. Its scatter is the noise of two single-shot measurements: standard deviation 0.008 dB and 0.05 deg with one capture per point (largest 0.03 dB, 0.19 deg), 0.004 dB and 0.03 deg with 4 averages (largest 0.013 dB, 0.13 deg). So "every point within 0.02 dB and 0.1 deg" needs averaging and is still missed by a point or so in phase. Times: calibration 62 s (58 points), 206 s with 4 averages. An RC low-pass (997.8 ohm, 98.2 nF ceramic) against its LCR model: within 0.02 dB and 0.11 deg below the corner, a steady -0.06 dB and within 0.5 deg from 1 to 100 kHz (R C 0.7 % off, or the uncorrected V/div step differences of 13.12; not separated).

### Not yet verified

The watchdog on a scope that is frozen but still on USB, whether paced table walking always avoids the freeze (one clean run), other triggers of the alignment shift (the +2.15 ns of 13.25 is unexplained), scope power-on state, a faster two-channel read, LAN, Linux, the cause of the one bad capture (HW_REPORT 13.9), what makes the generator's DC drift. See SPEC.md section 17. See also `docs/spec/roadmap.md` section 17.

---

## History: where each section lives

| Sections | Content | File |
|---|---|---|
| Verdicts, 1 to 11 | Milestone 0: environment, USB, VISA, identity, command table, end-to-end test, timing, findings S1 to S9 and G1 to G5 (section 8), backend per OS | `docs/hw/m0-gate.md` |
| 12.1 to 12.11 | Milestones 0b and 0c: commands against the UPO1000 manual, step tables, single shot, I/O layer, out-of-step recovery, dual-channel tests, 10X probes, the channel alignment fault (12.11) | `docs/hw/m0b-m0c.md` |
| 12.12 to 12.14 | Milestone 6 bench checks: capture benchmark, why free-running capture failed, rail codes, division count, panel lock | `docs/hw/m6-bench.md` |
| 13.1 to 13.12 | Milestone 7 bring-up: probe tool, first sweeps, RC low-pass, the generator's DC, restore of the scope settings, bad-capture retry | `docs/hw/m7-bringup.md` |
| 13.13 to 13.28 | Milestone 7 bench sessions with the user: skew wizard, CH3 / CH4, watchdog, panel lock, table walk, capacitor loss, sweep speed, running capture, Fast preview, the +2.15 ns state, built-in measurements, acceptance | `docs/hw/m7-bench-sessions.md` |
| 14.1 to 14.3 | Milestone A1: through calibration and through sweep with 1 and 4 averages, the user's acceptance run in the GUI with an RC low-pass | `docs/hw/a1-through-cal.md` |

Raw data of every run, failed ones included: `hwcheck/results/`.
