# Hardware history: Milestone 7 bring-up, sections 13.1 to 13.12 (2026-10-06)

Part of the hardware report. The current facts and the index of all sections: `HW_REPORT.md`. This file is a dated record of what was run and seen; it is not rewritten when a later run changes the picture, so read the facts sheet first.

## 13. Milestone 7: bench bring-up of the app's own drivers (started 2026-10-06)

Raw data: `hwcheck/results/m7/`. Setup so far: both 10X probes on generator CH1 (a "through" measurement: expected 0 dB, 0 degrees). A commit was made before every run.

### 13.1 Probe tool, first run on the real instruments

`python -m bodeplot.tools.probe --json hwcheck/results/m7/probe_run1.json`: **63 checks, 0 failed.** Every query form of every command in both drivers answered in the expected format (generator channels 1 and 2, scope channels 1 to 4), the single-shot test acquisition on CH1 returned 700 points (with a forced trigger, there being no signal), generator outputs read back OFF at the end, and the stored step tables matched this model and firmware.

### 13.2 Sweeps through the app's engine (`hwcheck/m7_sweep.py`)

The script uses the same code as the GUI (`drivers/connect.py`, `sweep/core.py`): find the instruments, skew check, sweep, generator off, panel unlocked, scope back to sweep AUTO.

| Run | Range | Points | Errors | Gain (through) | Phase (through) | Time per point |
|---|---|---|---|---|---|---|
| through_short | 1 kHz to 1 MHz | 10 | 0 | -0.014 to +0.028 dB | -0.14 to +0.03 deg | 1.35 s |
| through_full | 50 Hz to 20 MHz | 30 | 0 (1 point AUTORANGE_FAILED) | -0.027 to +0.044 dB | -0.28 to +0.06 deg | 1.74 s |
| through_short2 | 1 kHz to 1 MHz | 10 | 0 | -0.015 to +0.035 dB | -0.18 to +0.02 deg | 1.4 s |
| lowstart | 50 Hz to 1 MHz | 9 | 0 | within 0.04 dB | within 0.14 deg | 1.4 s |
| hf_repeat | 100 kHz to 20 MHz | 11 | 0 | -0.051 to +0.008 dB | -0.10 to +0.07 deg | 1.3 s |

- Scope counters over all runs: 0 reply errors, 0 out-of-step, 0 empty blocks, 0 resyncs after the one at connect. Generator: 0 timeouts.
- After every run: generator outputs OFF, panel lock 0, scope sweep AUTO.
- Connect takes 2.0 s. The skew check takes 10 to 23 s. One capture point costs 0.75 s when the timebase stays and about 1.05 s when it changes; settling and generator commands add about 0.3 s.
- The skew check at 10 and 20 MHz measured +0.15 and +0.14 ns and snapped to the +0.15 ns state.

### 13.3 Problems found, and what was done

1. **OPEN: the signal level at high frequency changed from run to run.** With nothing touched on the bench (user's statement), the reference amplitude at 20 MHz was 0.034 V peak in `through_full` and 0.30 V in `hf_repeat` (0.5 V expected; Milestone 0c read 1 Vpp within 1.5% up to 20 MHz). In `through_full` the level already fell from about 200 kHz (0.44 V at 365 kHz, 0.32 V at 889 kHz), while the three runs that stopped at 1 MHz were flat (0.49 V at 1 MHz). Both probes saw the same level each time, so the gain stayed within 0.05 dB. Cause not known: a loose ground clip or contact, or the generator. The user is checking the wiring. It matters for a real DUT because a low reference level costs signal-to-noise (SNR fell from 36 to 27 dB) and can hide a wiring fault.
2. **Fixed: auto-range flipped between two V/div steps.** At 8.2 MHz in `through_full` (10.5 mVpp at the input) the measured p-p sat on the upper target, so the step alternated between 2 and 5 mV/div until the retries ran out: 11 s and an AUTORANGE_FAILED flag. Auto-range now stays on a step that is just over the upper target while the signal is still on screen and the next step would fall below the lower target.
3. **Fixed: the skew check could not resolve the delay when the sweep stopped at 1 MHz.** The check used the top of the sweep, so it ran at 0.5 and 1 MHz, where 0.3 ns is 0.1 degree. Three such checks measured +0.04, 0.00 and -0.16 ns; the last one disagreed between its two frequencies by 0.32 ns and was not snapped. The check now always runs at 10 and 20 MHz when the instruments reach them, whatever the sweep range.

### 13.4 Not done yet

The known RC low-pass, compared with theory and with the simulation; the timed full-range sweep on a real DUT; a sweep from the GUI on the real instruments (only the headless path has run).
### 13.5 After the user fixed the wiring (2026-10-06)

The user checked and fixed the wiring (what exactly was wrong was not reported). Two more through runs, nothing else changed:

| Run | Range | Points | Flags | Reference level | Gain | Phase | Sweep time |
|---|---|---|---|---|---|---|---|
| through_full2 | 50 Hz to 20 MHz | 30 | none | 0.492 to 0.504 V peak over the whole range (0.504 V at 20 MHz) | -0.015 to +0.042 dB | -0.19 to +0.14 deg | 34.9 s (1.16 s per point) |
| hf_repeat2 | 100 kHz to 20 MHz | 11 | none | 0.492 to 0.503 V peak | -0.029 to +0.004 dB | -0.14 to +0.02 deg | 13.8 s |

**Problem 1 of 13.3 is closed as a wiring fault**: the level is now flat within 1.3% from 50 Hz to 20 MHz, as in Milestone 0c, and the two runs agree. No auto-range retries and no flags in either run (the hysteresis fix was in). Skew check: +0.148 and +0.151 ns, snapped to +0.15 ns. Scope counters: 0 errors, 0 resyncs after connect; generator outputs OFF at the end.

Lesson for the app: a through measurement shows 0 dB even when the reference level has collapsed, so the reference amplitude itself is worth watching. Not implemented: a warning when the reference level is far below the level the stimulus setting predicts.
### 13.6 RC low-pass (1 kOhm, 100 nF) and what it exposed (2026-10-06)

Wiring: generator CH1 -> 1 kOhm -> 100 nF to ground; CH1 probe (reference) on the generator side, CH2 probe (DUT) on the capacitor; both 10X. Sweeps 50 Hz to 20 MHz, 10 points per decade, no skew check (the probes are not on one node), DC coupling. Data: `results/m7/m7_sweep_rc_1k_100n.*`, `..._dcfix.*`, `results/s7_smallsig_py.json`, `results/s7_smallsig_offset_py.json`.

**What worked.** From 50 Hz to 22 kHz (0 to -23 dB) the measurement follows a first-order low-pass with a corner of 1515 Hz (nominal 1592 Hz; that is 105 nF if the resistor is exactly 1 kOhm, inside a normal capacitor tolerance): gain within +/-0.06 dB of that curve, phase within +0.1 / -0.2 degrees up to 3 kHz and drifting to +0.9 degrees at 22 kHz. No instrument errors in either sweep; generator OFF, panel unlocked and sweep AUTO at the end.

**What failed.** Above about 28 kHz (below -25 dB) the DUT channel went wrong: AUTORANGE_FAILED at several points, then from 44 to 55 kHz readings 14 to 18 dB too low with SNR near 0, then amplitudes of exactly zero (-350 dB). The signal there is still 2.5 to 4 mVpp at the scope input, which the scope can measure.

**Cause 1: DC on the signal.** CH2 carries +6.2 mV of DC at the scope input (about 62 mV at the probe tip), CH1 about +7.6 mV. Where it comes from is not established (generator offset error, or the scope's inputs). At 5 and 2 mV/div the trace simply sits high (codes centred on 161 and 205) and reads correctly: 4.1 and 4.04 mVpp, SNR 25 and 30 dB. At 1 mV/div the DC is 6.2 divisions, beyond the 5.06-division data range: 485 of 700 samples on code 254, fitted amplitude 0.63 mVpp instead of 4.0.

**Cause 2: the 500 uV/div step returns wrong data without any clip indication.** With the trace off scale at 500 uV/div the codes were 75 to 125, none on a rail; in 12.14 an overdriven signal there read 125 on its clipped half. In every such case the reading is bounded by code 125 on one side. One explanation that fits all three observations: 500 uV/div is a x2 digital zoom of the 1 mV/div range whose arithmetic wraps around instead of clipping (a clipped 254 becomes 2 x (254 - 128) + 128 = 380, which wraps to 124). **This explanation is an inference; it was not tested.** The practical fact is measured: at 500 uV/div an off-scale or clipped trace cannot be told from a good one.

**Cause 3: the scope keeps the channel offset in divisions, not volts, when V/div changes.** An offset of -6.24 mV set at 2 mV/div (which centred the trace: codes 102 to 153) read back -3.12 mV after changing to 1 mV/div and -1.56 mV at 500 uV/div. Setting -6.24 mV again at 500 uV/div put every sample on code 1, so the offset does not behave normally on that step either.

**Changes made in the app (all tested against the simulators, 223 tests; NOT yet re-run on the bench):**
1. Auto-range measures the DC of each channel and re-centres the trace with the channel offset when its middle is more than one division from the screen centre (`Digitizer.set_offset`).
2. Auto-range never selects a V/div at which DC plus signal peak would not fit in the data range (`autorange.min_vdiv_for_dc`); this also covers scopes with no offset command.
3. The driver puts the offset back in volts after every V/div change.
4. The driver no longer uses 500 uV/div; 1 mV/div is the most sensitive step. Cost: 6 dB of range at the bottom.

A bench sweep with only change 1 and 2 in place (`rc_1k_100n_dcfix`) still failed in the same region, which is what led to findings 2 and 3.

**Open after this section:**
- Re-run the RC sweep on the bench with all four changes.
- The user's suggestion: use AC coupling on the scope for this measurement. Not tried yet. It would remove the DC problem at its root; its cost is a high-pass corner at low frequency that must be checked on both channels (the 50 Hz points). It can be tried from the app today (`ScopeConfig.coupling = "AC"`), and should be compared with the DC-coupled, offset-corrected sweep before choosing the default.
- The user saw CH2 "jumping around" on the scope during the sweep and the scope left on 500 uV/div afterwards. The jumping is auto-range and the offset changes at work. The app does not restore the scope's V/div, timebase and offset after a sweep; it only goes back to sweep AUTO and unlocks the panel.
- Where the 6 to 8 mV of DC at the inputs comes from.
- Phase drift of about +1 degree between 3 and 40 kHz against the ideal RC (component, probe or scope: not examined).

### 13.7 The DC is not the scope's own input offset (2026-10-06)

The user ran the scope's self calibration, removed all probes and reported that an offset was still visible at 500 uV/div. `hwcheck/s7_dcoffset.py` then read CH1 and CH2 with the inputs open, channel offset 0, timebase 10 ms/div (140 ms record), at nine V/div steps in DC, AC and GND coupling. Generator outputs OFF throughout. Data: `results/s7_dcoffset_py.json`. 0 reply errors, 0 empty blocks.

| V/div | CH1, DC coupling | CH2, DC coupling |
|---|---|---|
| 500 uV | +0.165 mV (+0.33 div) | +0.290 mV (+0.58 div) |
| 1 mV | +0.136 mV (+0.14 div) | +0.266 mV (+0.27 div) |
| 2 mV | +0.104 mV (+0.05 div) | +0.228 mV (+0.11 div) |
| 5 mV | -0.145 mV (-0.03 div) | +0.007 mV (0.00 div) |
| 10 mV | -0.72 mV (-0.07 div) | -0.55 mV (-0.05 div) |
| 20 mV | -1.5 mV (-0.08 div) | -2.0 mV (-0.10 div) |
| 50 mV to 1 V | -0.09 to -0.11 div | -0.12 div |

- **The scope's own offset is 0.3 mV or less on the steps from 500 uV to 5 mV/div.** That is 0.3 to 0.6 division at 500 uV/div, which is what the user saw on the screen. On the steps from 10 mV/div up it is a constant -0.1 division (about 2.5 codes).
- AC coupling gives the same numbers as DC coupling within 0.03 mV on the sensitive steps. So this residual is generated after the coupling switch and **AC coupling does not remove it**.
- GND coupling returns code 127 on every sample at every step, with zero noise. It is a drawn line, not a measurement of the input stage.
- Open-input noise: 7 codes rms at 500 uV/div, 3 at 1 mV/div, 1.5 at 2 mV/div (mains pickup included).
- **The +6.2 mV (CH2) and +8.6 mV (CH1) measured in 13.6 are 20 times larger than this.** So they did not come from the scope's input stage as it is now. Two explanations remain: the generator output carries 60 to 90 mV of DC (seen through the 10X probes), or the scope had a larger offset that the self calibration removed. `hwcheck/s7_dcsource.py` (written, NOT yet run; needs the probes back on the RC) separates the two: DC with the generator output OFF, ON at 1 Vpp and 0.1 Vpp, and ON with the generator's offset set to cancel it.
- New scope fact: **`:CHANnel<n>:SCALe` is ignored on a channel that is switched off** (`:CHANnel<n>:DISPlay 0`): no error, the read-back stays at the old value. CH2 was off when the script started (left so by the user); the restore switched it off first and then could not put 50 mV/div back. Restored by hand (display on, scale, display off). The scripts now restore DISPlay last.
### 13.8 Generator DC check and the RC sweep re-run: the DC is gone, the sweep passes (2026-10-06)

**Corrected by 13.11: the DC is the generator's and it came back later. The conclusion below that the self calibration removed it is wrong. The sweep results stand.**

RC low-pass wired again by the user (as in 13.6). Data: `results/s7_dcsource_py.json`, `results/m7/m7_sweep_rc_retest.*`.

**`hwcheck/s7_dcsource.py`** (DC of both channels, corrected with the open-input reading of 13.7):

| Case | CH1 at the scope input | CH2 at the scope input |
|---|---|---|
| output OFF, 2 mV/div | +0.17 mV | +0.27 mV |
| ON 1 Vpp 1 kHz, 20 mV/div | -0.43 mV | -1.10 mV |
| ON 1 Vpp 35 kHz, CH1 20 mV/div, CH2 2 mV/div | -0.02 mV | -0.69 mV |
| ON 0.1 Vpp 1 kHz, 5 mV/div | +0.02 mV | +0.11 mV |

- **The +6.2 mV (CH2) and +8.6 mV (CH1) of 13.6 are gone.** In the same condition as then (1 Vpp, 35 kHz, CH2 at 2 mV/div) CH2 now reads -0.7 mV. Every reading is within about 1 mV of the open-input value, which at 20 mV/div is 1 to 2 codes.
- So the generator does not put out 60 to 90 mV of DC. What changed between 13.6 and now is the scope's self calibration (and the probes were removed and put back). **The self calibration removing the offset is the explanation that fits; it was not proven** (there is no measurement of the open inputs from before it).
- The last step (generator offset set to cancel the DC) failed: `:CHANnel1:BASE:OFFSet -0.011` read back `0.0`. Not followed up, there being nothing left to cancel. Outputs OFF at the end, no restore failures.

**RC sweep re-run** (`m7_sweep.py rc_retest 50 20000000 10 --no-skew`, DC coupling, with the four changes of 13.6): 58 points in 65.1 s, **no AUTORANGE_FAILED**, 0 scope errors, 0 resyncs after connect, generator OFF, panel unlocked and sweep AUTO at the end. The most sensitive step used was 1 mV/div.

| Range | Gain against a first-order low-pass, corner 1513 Hz | Phase against it |
|---|---|---|
| 50 Hz to 22.5 kHz (0 to -23 dB) | -0.05 to +0.05 dB | -0.1 to +1.1 deg |
| 22.5 to 110 kHz (to -37 dB) | -0.08 to +0.17 dB | +0.7 to +2.8 deg |
| 110 to 340 kHz (to -47 dB) | -0.19 to +0.47 dB | up to +5 deg |
| above 430 kHz | noise: DUT SNR 1 dB and lower, readings between -51 and -64 dB | meaningless |

- The measurement is correct down to about -47 dB (340 kHz, 2.2 mV at the tip, SNR 2 dB). LOW_SNR is flagged from 35 kHz (SNR 19 dB) and BELOW_FLOOR from 1.3 MHz. The floor of this setup is about -52 to -60 dB with 1 Vpp and 10X probes.
- The phase leads the ideal RC more and more with frequency (+1 deg at 22 kHz, +2.8 deg at 110 kHz). A series resistance of roughly 0.5 to 1 ohm in the capacitor branch (ESR plus contacts) would do that. This is an estimate from two points, not a measurement.
- AC coupling was not needed for this run. Whether it should be offered is still open; note from 13.7 that it does not remove the scope's own residual offset.

### 13.9 Scope settings restored after a sweep; AC-coupled RC sweep (2026-10-06)

**Restore.** The app now reads the scope's timebase, trigger (mode, source, slope, level) and, for each channel it uses, display, probe ratio, vernier, V/div, offset, coupling and bandwidth limit before a sweep, skew check or re-measure, and puts them back afterwards (`Digitizer.save_setup` / `restore_setup`, `Session.begin_measurement` / `end_measurement`). The channel display is restored last because SCALe is ignored on a channel that is off (13.7). Bench: `m7_sweep.py rc_ac` compared 17 settings read before and after the sweep: **all 17 identical**; panel unlocked, sweep AUTO, generator OFF. Not tested on hardware: a scope probe ratio other than 1X at the start, and a channel that was off at the start (covered by the simulated scope only).

**AC coupling** (`m7_sweep.py rc_ac 50 20000000 10 --no-skew --ac`, data `results/m7/m7_sweep_rc_ac.*`): 58 points in 65.0 s, no AUTORANGE_FAILED, 0 scope errors.
- Up to 22 kHz the AC-coupled gain and phase agree with the DC-coupled run of 13.8 within 0.03 dB and 0.2 degrees. Below -40 dB both are in the noise and differ by up to 0.8 dB.
- At 50 and 63 Hz the reference level is 0.3% lower than with DC coupling and gain and phase are unchanged (-0.007 dB, -1.82 deg at 50 Hz in both). The AC corner is therefore far below 50 Hz with 10X probes and is the same on both channels. With 1X probes the corner is ten times higher; not measured.
- AC coupling gave no advantage on this DUT now that the input DC is gone. DC stays the default; AC is already selectable in the GUI (scope panel, Coupling).

**OPEN: one bad capture.** The point at 78.62 Hz (the first one after the timebase changed from 10 to 5 ms/div) read 0.021 V on BOTH channels instead of 0.496 V, with SNR -28 dB, and was flagged only LOW_SNR; gain -0.08 dB, phase +0.34 deg (should be -3.0). The same point was correct in the DC run. The record did not contain a 78.62 Hz sine at the stated sample interval: either the generator had not changed frequency yet, or the record came from before the timebase change. Which one is not known; the raw waveform is not kept. One event in about 230 sweep points on hardware today. The app has no check that would retry such a capture (the reference level check proposed in 13.5 would have caught it).

### 13.10 Retry for a capture that does not hold the stimulus (2026-10-06)

Response to the bad point of 13.9. When the sine fit of the REFERENCE channel has an SNR below 6 dB (`MeasureSettings.bad_ref_snr_db`; a normal reference reads 28 to 38 dB, the bad capture read -28 dB), the capture is not used: both raw waveforms are written to an `.npz` file, the app waits one settling time and acquires again, up to 2 times (`bad_capture_retries`). If the reference is still wrong the point is kept and flagged `REF_SUSPECT`. Each event is a warning in the status log with the file path. Files go to `captures/` next to the app's log file (GUI) or `hwcheck/results/m7/captures/` (`m7_sweep.py`), at most 50 per connection.

Bench after the change: two AC-coupled RC sweeps, 50 Hz to 20 kHz, 28 points each (`m7_sweep_rc_ac_retry1`, `..._retry2`): no bad capture occurred, no flags other than SKEW_UNCHECKED, reference SNR 31 dB or better, scope settings restored, 0 scope errors. **The fault of 13.9 did not come back in these 56 points, so the retry path itself has run only against the simulators** (3 tests). The cause of that one bad capture is still unknown; the next occurrence will leave its raw waveforms behind.

### 13.11 Open items worked through with nobody at the bench (2026-10-06, later)

Setup left by the user: both instruments on USB, the 1 k / 100 nF low-pass on the breadboard, probes as in 13.6. No cable or power change was possible.

**Timed full-range sweep** (`m7_sweep.py rc_timed_full 50 20000000 20 --no-skew`, the GUI's default density): **114 points in 118.8 s, 1.04 s per point** (0.72 to 1.96 s measuring), connect 2.0 s, 5 auto-range retries in total, 0 scope errors, 0 resyncs after connect, no AUTORANGE_FAILED, scope settings restored. Gain against a 1513 Hz first-order low-pass: -0.06 to +0.02 dB up to 22.6 kHz, -0.65 to +0.24 dB from there to 345 kHz. 66 points unflagged, 9 LOW_SNR, 39 BELOW_FLOOR.

**CORRECTION to 13.8: the DC comes from the generator, and it changes over time. The self calibration did not remove it.** Evidence (`s7_dcsource_py.json` = second run, `..._run1.json` = the run of 13.8, `s7_gendc_py.json`):

| Reading (CH2 on the capacitor, 2 mV/div, where one code is 0.8 mV at the tip) | Run of 13.8 | Now |
|---|---|---|
| generator output OFF | +0.27 mV at the input | +0.28 mV at the input |
| generator ON, 1 Vpp, 35 kHz | -0.69 mV at the input (about -9 mV at the tip) | +4.08 mV at the input (**+38.5 mV at the tip**) |
| generator ON, 0.1 Vpp, 1 kHz (5 mV/div) | +0.11 mV | +0.77 mV (+7.6 mV at the tip) |

- With the output OFF the scope reads the same as right after the self calibration, so the scope's zero on the sensitive steps has not moved. With the output ON the DC appears. It is the generator's.
- It is on the capacitor through the 1 k resistor, it follows the generator's offset setting (+20 mV set: +21.8 mV; +30 mV set: +32.7 mV at 100 kHz), and it is smaller at a smaller amplitude.
- Three values so far at 1 Vpp: about +62 mV (13.6, after long sweeps), about -9 mV (13.8, after the generator had been idle), +38.5 mV now (after several sweeps). **A drift with warm-up would fit; that is a guess, nothing was measured against time or temperature.**
- CH1 on its coarse steps cannot measure this: at 20 and 50 mV/div its zero moved by 2 to 5 codes between runs (output OFF at 20 mV/div: -0.02 mV in 13.8, +1.59 mV now), which is 30 to 100 mV at a 10X probe tip.

**The app's DC handling (the four changes of 13.6) is now proven on the bench with DC present**, which 13.8 could not show because there was almost none then:

| Run | Generator offset set | Result |
|---|---|---|
| `rc_dc_plus60` (50 Hz to 20 MHz, 58 points) | +60 mV (about +100 mV at the tips with the generator's own DC: more than the original fault) | no AUTORANGE_FAILED, no CLIPPED, DUT down to 1 mV/div, gain -0.04 to +0.02 dB to 22.6 kHz and -0.05 to +0.93 dB to 345 kHz, 66.4 s |
| `rc_offset_0.1` (1 to 100 kHz, 7 points) | +100 mV | correct, DUT down to 1 mV/div |
| `rc_offset_-0.1` | -100 mV | correct, DUT down to 1 mV/div |

So DC coupling with the offset handling works with at least +/-100 mV of DC at the tips, and AC coupling (13.9) is the other way round the same problem.

**The generator ignores every negative number** (`s7_genoffset.py`, `dbg7_genoffset_neg.py`; firmware 1.09). `:CHANnel1:BASE:OFFSet` with 0.001 to 0.5 reads back exactly and moves the output (+0.1 V set: +101 mV measured). With any negative value (-0.001 to -0.5, written as `-0.1`, `-1e-1` or `-1.000000e-01`) the read-back keeps the previous value and the output does not move. `:CHANnel1:BASE:LOW -0.6` is ignored in the same way. The manual gives the offset range as "0~+/-max" (UTG p.13). No error is reported.
- What works, with positive numbers only: at offset 0 set the amplitude to A + 2d, then `:CHANnel1:BASE:HIGH` (UTG p.13) to A/2 - d. The bottom of the wave stays, the top comes down: read-backs offset -d and amplitude A (tried: A = 1, d = 0.1, 0.3, 0.5; A = 0.2, d = 0.05). Measured at the output: -84 mV for -0.1 V and -289 mV for -0.3 V (at 50 mV/div, where one code is 20 mV at the tip).
- Limit: HIGH cannot go below 0 this way, so the lowest offset is minus half the amplitude.
- The app's generator driver now does this (`UniTUTG900E._set_level`): never sends a negative number, sets a negative offset by the route above with the output off, verifies offset and amplitude by read-back, and refuses an offset below minus half the amplitude with a plain message. Before, a negative offset in the GUI ended the sweep with a read-back error. `:CHANnel<n>:BASE:HIGH` is added to the driver's command list.

### 13.12 More open items, still with nobody at the bench (2026-10-06, later)

**Restore from an awkward scope state** (`hwcheck/m7_restore.py`: set the scope up, run a 5-point sweep through the app, compare 19 settings before and after; data `results/m7/m7_restore_run1.json` and `m7_restore.json`).
- CH2 switched off before the sweep (50 mV/div, offset 20 mV; CH1 500 mV/div, 1 ms/div): **all 19 settings came back**, CH2 off again with its scale and offset.
- CH1 at probe ratio 10X, AC, 20 MHz limit, offset 0.1 V, trigger slope negative, level 2 V: first run, **everything came back except the trigger level** (2.0 V before, 2.4 V after). Cause: `:TRIGger:LEVel` takes input-referred volts and reports probe-scaled ones (0.2 sent at 10X reads back 2.0), like `:CHANnel<n>:SCALe` (0.05 sent reads back 0.5). `:CHANnel<n>:OFFSet` is not scaled (0.1 sent reads back 0.1). The restore sent the read-back value, the scope clamped it at 2.4 V. Fixed: the level is divided by the trigger source's probe ratio before it is sent. **Second run: all 19 settings came back in both cases.**
- The simulated scope now reports V/div and trigger level probe-scaled, as the real one does.
- 0 scope errors in both runs; generator OFF, panel unlocked, sweep AUTO, start state put back at the end.

**The bad capture of 13.9 could not be reproduced** (`hwcheck/m7_repeat.py`, data `results/m7/m7_repeat_ac.json`): 40 AC-coupled sweeps from 50 to 100 Hz, each crossing the 10 to 5 ms/div change, 200 points in 327 s: **0 rejected captures**, 0 scope errors. So the fault is rarer than about one in 13 such transitions (95 % bound for 0 in 40), and its cause is still not known. The retry of 13.10 stays as the guard.

**Phase lead of the RC filter above 20 kHz.**
- Fits to the recorded sweeps (`hwcheck/a7_phase_lead.py`, no instrument; points from 300 Hz up to where the DUT SNR is 20 dB): capacitance 104.9 to 105.1 nF in every run and model. A series resistance alone needs 0.6 to 1.3 ohm depending on the run's frequency span, a constant loss angle alone 0.56 to 0.78 deg (tan d 0.010 to 0.014), both together 0.4 to 1.0 ohm with 0.2 to 0.45 deg. Both together leave at most 0.6 deg of phase error; neither alone describes the data, and the fitted values move with the span, so **these are descriptions, not measurements of the capacitor**.
- **The lead is not a V/div-range effect of the scope** (`hwcheck/s7_rangephase.py`, AC coupled): the same capacitor voltage measured with CH2 on every step it fits on, CH1 fixed at 20 mV/div.

| Frequency | CH2 steps compared | Phase on each step | Gain on each step | Lead over the ideal RC |
|---|---|---|---|---|
| 5 kHz | 5, 10, 20 mV/div | -72.76, -72.79, -72.78 deg | -10.786, -10.794, -10.792 dB | +0.4 deg |
| 20 kHz | 2, 5, 10, 20 mV/div | -84.75, -84.83, -84.89, -84.78 deg | -22.45, -22.44, -22.36, -22.51 dB | +0.8 to +0.9 deg |
| 50 kHz | 1, 2, 5, 10 mV/div | -87.00, -87.11, -86.99, -87.06 deg | -30.29, -30.34, -30.32, -30.21 dB | +1.2 to +1.3 deg |
| 100 kHz | 1, 2 mV/div | -87.35, -87.45 deg | -36.32, -36.41 dB | +1.7 to +1.8 deg |

  Where the signal fills at least 0.8 division the steps agree within 0.14 deg and 0.09 dB. (Smaller than that the scatter grows: at 100 kHz on 20 mV/div, 0.1 division, the spread is 7.6 deg.)
- With the through sweeps of 13.5 (both probes on one node: phase within 0.2 deg to 20 MHz) this leaves the circuit itself: the capacitor's loss, its series resistance, and the breadboard contacts and ground lead. Telling those apart needs another capacitor or an LCR meter, so a person at the bench.

**Image export follows the vertical unit**: PNG, SVG and PDF now draw the upper plot in dB, Vpp or percent of the input, whichever the Vertical box shows (`ImageOptions.unit`).
