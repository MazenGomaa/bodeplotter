# Hardware history: Milestones 0b and 0c, sections 12.1 to 12.11 (2026-10-05)

Part of the hardware report. The current facts and the index of all sections: `HW_REPORT.md`. This file is a dated record of what was run and seen; it is not rewritten when a later run changes the picture, so read the facts sheet first.

## 12. Milestone 0b

Run on 2026-10-05, same PC. All 0b results are on `@py` (pyvisa-py + WinUSB) unless stated. Raw data: `hwcheck/results/t0b_iolayer_py.json`, `s0b_dual_py_probes_1x_A.json`, `s0b_dual_py_probes_1x_B_swapped.json`, `dbg0b_probe.json`.

### 12.1 Scope commands re-verified against the UPO1000 manual

Manual: `docs/Uni-T_UPO1000_Programming_Manual_0424.pdf` (99 pages, file number 20230822, software V1.00.0018; the scope runs 1.01.0047). Text was extracted with pypdf, so figures were not seen.

Result: **every scope command used in Milestone 0 and in the I/O layer exists in the UPO1000 manual with the same syntax.** The two manuals are near-identical; the UPO1000 one covers four channels. Page references (n of 99):

| Command | UPO1000 page | Differs from the UPO1002 manual? |
|---|---|---|
| `*IDN?`, `*OPC?` | 5 | No. IDN example still shows a different field layout from the real reply |
| `:RUN`, `:STOP` | 5-6 | No |
| `:SYSTem:ERRor?` | 6 | No |
| `:SYSTem:VERSion?` | 9 | No |
| `:CHANnel<n>:BWLimit`, `:COUPling`, `:DISPlay` | 12-13 | `<n>` is now {1\|2\|3\|4} |
| `:CHANnel<n>:PROBe` | 14 | `<n>` 1 to 4. Example is still `10X` |
| `:CHANnel<n>:OFFSet`, `:SCALe` | 14 | `<n>` 1 to 9 (CH1-4, MATH, REFA-D) |
| `:CHANnel<n>:VERNier` | 15 | `<n>` 1 to 4 |
| `:TIMebase:MODE`, `:OFFSet`, `:SCALe` | 15-16 | No |
| `:MEASure:VPP?`, `:MEASure:PHASe?` | 30 | Sources now CHANnel1 to CHANnel4 |
| `:MEASure:FREQuency?` | 33 | Same |
| `:TRIGger:MODE`, `:FORCe`, `:SWEep` | 36-37 | No |
| `:TRIGger:STATus?`, `:TRIGger:LEVel` | 37 | No |
| `:TRIGger:SOURce` | 38 | CHANnel1 to CHANnel4, EXT, ACLINE |
| `:TRIGger:EDGE:SLOPe` | 39 | No |
| `:ACQuire:TYPE`, `:ACQuire:MEMory:DEPTh` | 65 | No |
| `:WAVeform:MODE`, `:FORMat`, `:STARt` | 69 | No |
| `:WAVeform:STOP`, `:SOURce`, `:POINts`, `:DATA?` | 70-71 | Source CHANnel1 to CHANnel4 |
| `:WAVeform:PREamble?` | 71 | No |
| `:WAVeform:XINCrement?`, `:XORigin?`, `:YINCrement?` | 72 | No |
| `:WAVeform:YORigin?`, `:YREFerence?` | 73 | No |

What the correct manual does and does not explain:

| Milestone 0 finding | Explained by the UPO1000 manual? |
|---|---|
| CH3 / CH4 not documented | **Yes.** Channels 1 to 4 are documented. CH3 and CH4 answer queries on hardware (display, probe, V/div, offset, coupling, BW limit). Set commands and waveform read-out on CH3/CH4 were not tested. |
| S1 exponent notation ignored | Not stated, but consistent: every command example uses plain decimals or a unit suffix (`0.005`, `500 mV`, `20V`, `1s`). Exponents appear only in replies. |
| S2 probe ratio needs `X` | Only by example (`:CHAN1:PROB 10X`). The effect of a bare number is not described. |
| S3 back-to-back writes dropped | No. |
| S4 / S5 empty waveform reply, replies out of step | No. |
| S6 20 ns/div became 10 ns/div | No. Explained by the hardware instead: see 12.2. |
| S7 preamble Points = 1000, 700 points returned, `:WAVeform:POINts?` empty | No. This manual also says NORMal mode is 1 to 1400 points. |
| Single-shot behaviour (12.3) | No. The manual lists `SINGle` as a sweep value and says nothing about arming or `:RUN`. |

The manual also contradicts itself in places (`:SYSTem:LOCK?` is described as "0 represents locked" and then exemplified as "returns 1, it represents locked"; the bandwidth-limit example uses `ON` where the syntax says `20M | FULL`). None of those commands is used.

### 12.2 What the hardware really accepts

Step tables read from the scope by walking `UP` / `DOWN` (probe 1X, coarse V/div):

| Setting | Real steps |
|---|---|
| Timebase (s/div), walked up to 20 ms | 1 ns, 2 ns, 5 ns, 10 ns, **25 ns**, 50 ns, 100 ns, 200 ns, 500 ns, 1 µs, 2 µs, 5 µs, 10 µs, 20 µs, 50 µs, 100 µs, 200 µs, 500 µs, 1 ms, 2 ms, 5 ms, 10 ms, 20 ms |
| V/div | 500 µV, 1 mV, 2 mV, 5 mV, 10 mV, 20 mV, 50 mV, 100 mV, 200 mV, 500 mV, 1 V, 2 V, 5 V, 10 V, 20 V |

Every one of those 23 timebase and 15 V/div values sets and reads back exactly with a plain-decimal argument (V/div on CH1 and CH2). A request for 20 ns/div lands on 10 ns/div whatever the format (`0.00000002`, `20ns`, `2e-8`), because 20 ns is not a step.

Other behaviour found in 0b:

- **Offset and trigger level are quantised** to one ADC code, V/div / 25 (0.2 V offset at 20 V/div reads back 0; 0.1 V trigger level at 0.2 V/div reads back 0.096).
- **An empty reply to an ordinary query means "busy"**, not out of step. Seen on `:TIMebase:SCALe?` 0.3 s after a timebase change and on `*IDN?` while stepping V/div. Retrying works.
- **Device clear is safe on the scope** on both backends.

### 12.3 Single-shot acquisition (used for acquisition-complete polling)

None of this is in either manual.

- `:TRIGger:SWEep SINGle` is itself the arm command.
- A `:RUN` sent after the shot has armed cancels single mode; the scope free-runs in AUTO and never stops.
- Status sequence after arming from a stopped scope: `STOP` (stale, first 20 ms) → `ARMED` → `AUTO` → `READY` at about 0.67 s → `STOP` after the trigger. With a signal present the sequence usually reads `STOP → ARMED → AUTO → STOP`.
- `:TRIGger:FORCe` works from `READY` (STOP within 30 ms). Sent while the status still reads `AUTO`, it leaves the scope in AUTO.
- A setting change just before arming makes the scope restart its acquisition, and the shot then runs two arm cycles (STOP for 20 ms, then armed again).

The layer therefore: waits 0.3 s after the last setting change and until the status is not `ARMED`; arms with the sweep command only; requires a non-STOP status to have been seen, then STOP held for 0.1 s, then at least one screen time; forces a trigger only after a set time continuously in `READY`.

### 12.4 I/O layer (`hwcheck/iolayer.py`) and its test (`hwcheck/t0b_iolayer.py`)

Final run on `@py`: **55 of 55 checks passed.** An earlier run on `@ivi` reached 36 of 37 before NI-VISA was dropped (the one failure was the single-shot arming, fixed afterwards and not re-run on `@ivi`).

| Requirement | How it is done | Evidence |
|---|---|---|
| Per-instrument formatter, no exponents | `plain_decimal`, `ScopeFmt` (probe `1X`, channels 1-4), `GenFmt` (channels 1-2) | 12 number cases, NaN and bad channels rejected |
| Set-then-readback for every setting | `set_verified` on both instruments, polls the read-back up to 2 s, re-sends once, raises `SetError` | 23 timebase steps, 15 V/div steps × 2 channels, coupling, BW limit, offset, trigger level/slope/source; generator sine setup, 7 frequencies 50 Hz to 20 MHz, amplitude, offset, load. A deliberately wrong expectation (20 ns/div) is caught. |
| Reply-format validation | One validator per reply type; every scope query is followed by a `*IDN?` sentinel | 11 real replies accepted, 11 wrong-format replies rejected |
| Resync: device clear, flush, `*IDN?` sentinel | `:RUN`, device clear, host-buffer flush, three clean sentinel rounds; second level: restart the USB device node | See 12.5 |
| Acquisition-complete polling before every fetch | `acquire()` as in 12.3 | 20 of 20 two-channel captures with no signal (forced trigger); 300 of 300 with signal (12.6) |
| Cached real step tables built at connect | `build_tables()` walks `UP`/`DOWN`; tables are checked for plausibility and rejected otherwise | Tables above; 20 ns/div refused as "not a real step", a 20 ns request rounds up to 25 ns |
| Generator: read termination None | set at open | all generator queries |
| Generator: unknown commands blocked | whitelist of exact manual forms, checked before any I/O | 8 commands refused (`*OPC?`, `*RST`, `:SYSTem:LOCK OFF`, `:CHANnel3:...`, abbreviated forms, exponent argument, `:SYSTem:ERRor?`), zero bytes sent, generator still answering |
| Generator: device clear + single retry on timeout | on timeout or wrong-format reply | 5 of 5 injected timeouts recovered with exactly 1 clear and 1 retry each, no stale reply left behind (also 5 of 5 on `@ivi`) |

Device clear on pyvisa-py: `inst.clear()` returns `VI_ERROR_NSUP_OPER` for USB, so the layer closes the session, sends USBTMC INITIATE_CLEAR through pyusb, and reopens. The pyvisa-py host-buffer flush is not implemented either (`NotImplementedError`); that step is a no-op on `@py`.

Defects in the layer that the tests exposed and that were fixed: flushing with bare device reads (broke NI-VISA, see 12.5), `:RUN` after arming, forcing a trigger too early, treating an empty sentinel as out of step, accepting STOP after 20 ms, and accepting a one-entry timebase table.

### 12.5 Forcing the out-of-step condition, and recovery

**How it is forced.** Send `:RUN` then `:STOP` at once at 5 ms/div, so the scope has no screen record, then ask `:WAVeform:DATA?` three times. Each gets an empty reply. Then `:RUN`.

**What then happens.** About 0.6 s later a 707-byte waveform block arrives as the answer to whatever query is in flight. After that one stray reply the scope is in step again. It does not happen every time.

**Proof and recovery (final run, 12 rounds):**

| Who received the stray reply | Rounds where it appeared | Result |
|---|---|---|
| An unchecked query, as Milestone 0's scripts would send | 3 of 6 | A `#3700...` block came back as the reply to `*OPC?`, 0.58 to 0.59 s after `:RUN`. This is the fault, demonstrated. |
| The I/O layer's own queries | 5 of 6 | Each time the layer reported "binary data in reply to ..." (to `*IDN?` or `:SYSTem:ERRor?`), resynced in one pass (sentinel clean three times running), and then passed 100 validated queries plus a two-channel capture. |

In every one of the 12 rounds the scope was in step afterwards.

Other routes tried:

- **SCAN mode route** (50 ms/div, the sequence that ended in a power cycle in Milestone 0): the stray block appeared as the reply to `:TRIGger:STATus?`, and the scope was in step afterwards. The permanent state did **not** recur.
- **Read with no query pending, on `@py`:** harmless in 3 of 3 rounds; the scope re-sends its last reply.
- **Read with no query pending, on `@ivi`:** every later read failed with `VI_ERROR_INP_PROT_VIOL`, including in new sessions and after device clear. `pnputil /restart-device "USB\VID_5656&PID_0832\APX1424510001"` (needs an elevated process) cleared it with no replug or power cycle. This is the layer's second resync level. **It was only exercised under the NI driver, never under WinUSB**, and it was never needed on `@py`.

So the permanent "one reply behind" state from Milestone 0 was not reproduced in 0b, and its trigger is still not known for certain. What is established is that the layer detects a wrong reply immediately, and that the ordinary resync fixed every case that did occur.

### 12.6 Dual-channel test

**Wiring actually used:** no BNC tee was available, so both scope probes (1X) were placed on generator CH1's output. This differs from the plan (tee). Generator: sine, 1 Vpp, High-Z. Scope: CH1 and CH2 DC, 1X, 0.2 V/div, trigger on CH1 at 0 V, timebase chosen for 5 cycles and rounded up to a real step (7 cycles on screen at all three frequencies). 50 captures per frequency; in each, both channels are read from the same stopped single-shot record, a sine is fitted to both at one frequency, and CH2/CH1 gives gain and phase.

Run A (probes as first connected), then run B with the two probes swapped at the scope inputs:

| Frequency | Timebase | Run | Gain CH2/CH1 (dB) mean ± sd [min, max] | Phase CH2 − CH1 (°) mean ± sd [min, max] | Valid |
|---|---|---|---|---|---|
| 1 kHz | 500 µs/div | A | +0.052 ± 0.006 [+0.034, +0.062] | +0.017 ± 0.028 [−0.063, +0.072] | 50/50 |
| 1 kHz | 500 µs/div | B | +0.055 ± 0.005 [+0.043, +0.069] | +0.011 ± 0.031 [−0.065, +0.067] | 50/50 |
| 1 MHz | 500 ns/div | A | +0.072 ± 0.006 [+0.060, +0.086] | +1.714 ± 0.047 [+1.614, +1.804] | 50/50 |
| 1 MHz | 500 ns/div | B | +0.064 ± 0.006 [+0.052, +0.079] | +1.347 ± 0.047 [+1.237, +1.466] | 50/50 |
| 20 MHz | 25 ns/div | A | +0.397 ± 0.041 [+0.340, +0.516] | +29.576 ± 0.321 [+29.000, +30.346] | 50/50 |
| 20 MHz | 25 ns/div | B | −0.263 ± 0.046 [−0.378, −0.157] | +29.589 ± 0.260 [+28.861, +30.131] | 50/50 |

Across all 300 captures: 0 errors, 0 resyncs, 0 empty blocks, 0 forced triggers, about 0.77 s per two-channel capture. Fit SNR about 35 dB at 1 kHz and 1 MHz, 27 dB at 20 MHz.

**Run C, after the user rewired the connection (same settings, still 1X probes on generator CH1):**

| Frequency | Gain CH2/CH1 (dB) mean ± sd [min, max] | Phase CH2 − CH1 (°) mean ± sd [min, max] | Valid |
|---|---|---|---|
| 1 kHz | +0.062 ± 0.005 [+0.052, +0.072] | +0.036 ± 0.028 [−0.016, +0.115] | 50/50 |
| 1 MHz | +0.065 ± 0.006 [+0.048, +0.076] | −0.127 ± 0.039 [−0.210, −0.034] | 50/50 |
| 20 MHz | −0.159 ± 0.048 [−0.258, −0.036] | +0.239 ± 0.276 [−0.328, +0.875] | 50/50 |

0 errors, 0 resyncs, 0 forced triggers, 0.75 to 0.78 s per capture. Raw data: `s0b_dual_py_C_rewired.json`. **This meets the expectation of about 0 dB and 0° at all three frequencies** (0.24° at 20 MHz is 33 ps).

**Superseded: see section 12.11 for the real cause.** The offset in runs A and B was a 4 ns sample shift inside the scope, triggered by my scripts' `:RUN` at connect; run C simply started in the aligned state. It was not the wiring, and it was not a fixed scope delay either. The paragraph below is kept as written at the time.

**Correction to the analysis below (written before 12.11, itself wrong).** From runs A and B I concluded that the scope itself delays CH1 by about 4.1 ns relative to CH2, because the phase offset did not move when the probes were swapped at the scope inputs. Run C disproves that: with the wiring changed and nothing else, the offset is gone. So the 4.1 ns came from how the signal was connected in runs A and B. I do not know exactly what was different (what was rewired was not recorded), and I cannot explain why the swap left the offset unchanged. The A/B separation table is kept only as a record of what was measured.

Separating the scope from the probes in runs A and B (half the sum of A and B is what stayed with the scope inputs; half the difference is what moved with the probes). **The "scope" columns here are superseded by run C:**

| Frequency | Scope gain | Probe gain mismatch | Scope phase | As a delay | Probe phase mismatch |
|---|---|---|---|---|---|
| 1 kHz | +0.053 dB | ±0.002 dB | +0.014° | not resolvable | ±0.003° |
| 1 MHz | +0.068 dB | ±0.004 dB | +1.53° | 4.25 ns | ±0.18° |
| 20 MHz | +0.067 dB | ±0.330 dB | +29.58° | 4.11 ns | ±0.01° |

Reading of the result against the expectation of about 0 dB and 0°:

- **Gain: met.** The scope's channels agree to about +0.06 dB at all three frequencies.
- **Phase in runs A and B: not met above about 100 kHz.** CH2 led CH1 by a constant 4.1 to 4.25 ns (0.0015° at 1 kHz, 1.5° at 1 MHz, 29.6° at 20 MHz), stable to 0.3°. **Run C shows this was the wiring, not the scope** (see the correction above). In run C the phase is within 0.24° everywhere.
- Only the pair CH1/CH2 was measured, at these three timebases, at 0.2 V/div, with CH1 as trigger source.
- **1X probes roll off before 20 MHz:** only 0.32 Vpp of the 1 Vpp arrived at 20 MHz (about −10 dB). The ratio is still valid because both probes roll off alike, but SNR is lower there. 10X probes or direct cables would be better for the top decade.
- At 25 ns/div the 700 points are 0.5 ns apart, i.e. interpolated by the scope. The 4.1 ns delay is larger than that spacing, and it shows up equally at 500 ns/div where points are 10 ns apart, so it is not a one-sample offset.

Runs that do not count, kept for the record:

- **First attempt (`s0b_dual_py_run1_ch2_not_connected.json`):** scope CH2 was wired to generator CH2, which my test does not drive, so CH2 read noise. The scope's own `:MEASure:VPP? CHANnel2` confirmed 0 V.
- **First swapped attempt (`..._B_swapped_run1_invalid_front_panel.json`):** the scope's front panel was being used while the test started. Timebase commands had no effect, the step table came out as a single entry, all three frequencies were captured at 5 ms/div, and 13 of the first 50 captures failed with empty blocks. The layer now rejects an implausible step table instead of carrying on.

### 12.7 Incidents during 0b

- **Scope "froze" once.** A test run was killed partway through while it was doing single-shot captures and `:STOP` cycles. In those states the display stops updating, so it may have been that; whether the front panel keys were dead was not established. It was power-cycled and has behaved since.
- **I wrongly reported that a command had not run.** The command that was interrupted had already rewritten `iolayer.py` and started the test.
- **Scope settings as found are not preserved.** A killed run never restored CH2 (it was display off, probe 10X before 0b; it is now on, 1X), and the front panel was used between runs. Generator settings were restored after every run and both outputs read OFF at the end of each.

### 12.8 What this adds for the spec

1. **No fixed scope delay correction is needed** (run C: within 0.24° at 20 MHz). But runs A and B show that connection details alone can add about 30° at 20 MHz, so the through-calibration that SPEC.md section 15 schedules for v2 (measure both inputs on the same node, divide later results by it) is worth pulling forward, or at least a "same node" sanity check in v1.
2. **Default backend `@py`**, not `auto` preferring `@ivi` (SPEC.md sections 3 and 5 and CLAUDE.md need this change; SPEC.md still recommends NI-VISA).
3. **Acquisition must be single-shot with status polling** as in 12.3, not `:STOP` on a free-running scope. SPEC.md section 9.2 currently describes the guard-then-`:STOP` method from Milestone 0.
4. **Timebase choice uses the real step table** (25 ns, not 20 ns) and 14 divisions.
5. **Per-point time:** about 0.77 s for a two-channel capture plus settling and autorange. A 113-point sweep is on the order of 2 to 4 minutes.
6. **Front-panel use during a sweep must be prevented or handled.** `:SYSTem:LOCK` exists in the manual (UPO1000 p.6) but was not tested.
7. **Probes:** use 10X or direct coax for measurements above a few MHz; the software should apply the probe ratio itself and leave the scope at 1X.

Still not verified after 0b: a tee (probe-free) baseline, CH3/CH4 as measurement channels, channel matching at other V/div and timebase settings, `:MEASure:PHASe?`, ADC rail codes and clipping detection, autorange, generator behaviour on frequency change, the device-restart recovery under WinUSB, LAN, and everything on Linux.

### 12.9 Files added in 0b

| Path | Purpose |
|---|---|
| `hwcheck/iolayer.py` | the I/O layer (`ScopeIO`, `GenIO`, formatters, validators, resync) |
| `hwcheck/t0b_iolayer.py` | its test, including the forced out-of-step rounds |
| `hwcheck/s0b_dual.py`, `s0b_identity.py` | dual-channel test, identity check |
| `hwcheck/dbg0b_*.py` | 0b troubleshooting scripts referenced above |
| `hwcheck/s0c_dual10x.py` | Milestone 0c: 10X dual-channel test (steps 3, 4, 5) |

### 12.10 Milestone 0c: dual-channel test with 10X probes, compared with run C (1X)

Run on 2026-10-05, `@py`, script `hwcheck/s0c_dual10x.py`. Raw data: `s0c_dual10x_main_py.json` (final), `s0c_dual10x_swap_py.json`, and `s0c_dual10x_main_py_run1_wiring_offset.json` (first attempt, see "Wiring" below).

**Setup.** Both probes switched to 10X, compensated by the user on the scope's cal output (reported by the scope as a 1 kHz square wave), both tips on generator CH1's output. Scope: CH1 and CH2 at `PROBe 1X` in the scope, DC, full bandwidth, offset 0, trigger on CH1 at 0 V; the ×10 is applied in software. Generator: sine, High-Z. Every capture is a single shot with both channels read from the same record through `iolayer.py`. Both generator outputs read OFF at the end of every run.

**Per-channel delay / deskew setting (step 2).** The UPO1000 manual documents **none**. Its CHANnel subsystem (p.12-15) has only BWLimit, COUPling, DISPlay, INVert, PROBe:TYPe, PROBe, OFFSet, SCALe, UNITs, VERNier and SELect; its TIMebase subsystem (p.15-17) has MODE, OFFSet, WINDow:OFFSet, SCALe, WINDow:SCALe and HOLDoff, all common to every channel. Whether the scope has a deskew setting in its front-panel menus is not known. Documented per-channel settings as logged during the run, identical for CH1 and CH2: probe ratio 1, probe type VOLTs, invert 0, vernier 0 (coarse), units VOLTs, BW limit FULL, coupling DC, offset 0, display on. Timebase offset 0, mode MAIN, acquisition NORMal.

**Step 3: 1 Vpp, 50 captures per frequency (final run, corrected wiring).**

| Frequency | Timebase | V/div used | Decoded Vpp ×10, CH1 / CH2 | Gain CH2/CH1 (dB) mean ± sd [min, max] | Phase CH2 − CH1 (°) mean ± sd [min, max] | Fit SNR CH1 / CH2 | Auto-selected V/div | Valid |
|---|---|---|---|---|---|---|---|---|
| 1 kHz | 500 µs | 20 mV | 0.985 / 0.987 | +0.018 ± 0.004 [+0.007, +0.028] | −0.095 ± 0.033 [−0.162, −0.029] | 35.4 / 35.6 dB | 20 mV both | 50/50 |
| 1 MHz | 500 ns | 20 mV | 0.996 / 0.993 | −0.032 ± 0.007 [−0.042, −0.017] | +0.013 ± 0.038 [−0.068, +0.100] | 35.4 / 35.2 dB | 20 mV both | 50/50 |
| 20 MHz | 25 ns | 20 mV | 1.014 / 1.010 | −0.029 ± 0.014 [−0.055, +0.003] | +1.081 ± 0.102 [+0.776, +1.287] | 33.0 / 33.2 dB | 20 mV both | 50/50 |

- Amplitude decodes to 1 Vpp within 1.5% at all three frequencies, so the 10X probes are flat to 20 MHz.
- Gain ratio is within 0.03 dB of 0 dB. Phase is within 0.1° up to 1 MHz and +1.1° at 20 MHz (about 150 ps).
- 0 errors, 0 resyncs, 0 forced triggers, 0 clipped, 0.76 to 0.78 s per capture.

**"Auto-selected V/div"** is what SPEC.md's rule gives from the measured amplitude: the most sensitive real step that keeps the signal at or below 0.8 of full scale. It assumes 8 vertical divisions, which has **not** been verified on this scope. With a 100 mVpp input (1 Vpp at a 10X tip) it picks 20 mV/div: 0.625 of 8 divisions, about 125 of 255 ADC codes.

**Step 4: 50 mVpp, 20 captures each (noise floor with 10X).** The scope input sees 5 mVpp; auto-selection picks 1 mV/div.

| Frequency | Run | Decoded Vpp ×10, CH1 / CH2 | Gain (dB) mean ± sd | Phase (°) mean ± sd [min, max] | Fit SNR CH1 / CH2 (lowest capture) | Valid |
|---|---|---|---|---|---|---|
| 1 kHz | first | 0.0492 / 0.0492 | −0.012 ± 0.029 | −0.215 ± 0.167 [−0.585, +0.086] | 23.5 / 23.2 dB (20.1) | 20/20 |
| 1 kHz | final, all 20 | 0.0470 / 0.0469 | −0.013 ± 0.033 | −0.297 ± 0.704 [−3.262, +0.035] | 19.1 / 18.7 dB (−30.3) | 20/20 |
| 1 kHz | final, without one bad fit | 19 captures | −0.007 ± 0.021 | −0.141 ± 0.097 [−0.380, +0.035] | 21.7 / 21.3 dB | 19 |
| 20 MHz | first | 0.0500 / 0.0498 | −0.041 ± 0.021 | (wiring offset, see below) sd 0.240 | 28.4 / 28.6 dB (25.9) | 20/20 |
| 20 MHz | final | 0.0498 / 0.0496 | −0.040 ± 0.023 | +1.126 ± 0.123 [+0.919, +1.370] | 27.4 / 27.0 dB (24.4) | 20/20 |

- At 50 mVpp the SNR falls from about 35 dB to 21 to 28 dB, and the phase spread grows from 0.03 to 0.10° to about 0.10 to 0.17° (1 kHz) and 0.12 to 0.24° (20 MHz). Mean gain and phase are unchanged within that spread, so the measurement is still usable.
- **One capture in the final 1 kHz block was fitted at the wrong frequency (1926 Hz, SNR −30 dB).** That is a weakness of this test script, which estimates the frequency from zero crossings before fitting; noise fooled it. It is not a hardware fault. The application is specified to fit at the known generator frequency (SPEC.md 8.4), which does not have this failure. Raw samples were not saved, so that capture could not be re-fitted; both versions of the statistics are shown.
- The 1 kHz SNR is lower than the 20 MHz SNR at the same amplitude. I did not investigate why; low-frequency pickup on the probes at the 5 mV level is a likely cause, not a confirmed one.
- The most sensitive step is 500 µV/div, so with 10X probes the floor is about 5 mV/div referred to the tip. Signals of a few mVpp at the tip would occupy only a few ADC codes.

**Step 5: probes swapped at the scope inputs, 20 MHz, 1 Vpp, 50 captures.**

| Orientation | Gain CH2/CH1 (dB) mean ± sd | Phase CH2 − CH1 (°) mean ± sd [min, max] |
|---|---|---|
| As in step 3 (final run) | −0.029 ± 0.014 | +1.081 ± 0.102 [+0.776, +1.287] |
| Swapped | +0.201 ± 0.015 | +0.698 ± 0.116 [+0.473, +0.996] |
| Stays with the scope inputs (half the sum) | +0.086 | +0.89 (about 124 ps) |
| Moves with the probes (half the difference) | ±0.115 | ±0.19 |

The phase stayed near 0 and did not flip: about +0.9° belongs to the scope inputs and ±0.2° to the probes. The gain did change sign, so about ±0.12 dB is probe mismatch (residual compensation difference) and +0.09 dB is the scope.

Order of events, because it matters for how far to trust this: the swapped run was taken first on the corrected wiring, then the probes were swapped back and the full step 3 and 4 run was repeated. The user confirmed that only the BNC ends changed between those two runs.

**Superseded: see section 12.11.** The offset described next was a 2 ns sample shift inside the scope, not wiring. The text is kept as written at the time.

**"Wiring": the first 0c attempt had a delay-like offset again.**

| Frequency | First attempt, phase CH2 − CH1 | As a delay | Final run |
|---|---|---|---|
| 1 kHz | −0.098° | — | −0.095° |
| 1 MHz | +0.727° | 2.0 ns | +0.013° |
| 20 MHz | +15.47° (also +15.56° at 50 mVpp) | 2.15 ns | +1.08° |

Gain and amplitude were normal in that attempt. Before the next run the user swapped the probes, "fixed the wiring again", and changed the generator's supply, all at once, and the offset was gone. So, as with the 4.1 ns offset in runs A and B, it came from the connection at the generator and not from the scope or the software, but **which of the three changes removed it was not isolated, and what exactly was wrong with the wiring is not known to me.** A constant delay of this size is what two tips on electrically different points give (2 ns is roughly 40 cm of wire, or a small series resistance working against the probe's input capacitance); that is an explanation I find plausible, not one I verified.

This has now happened twice (4.1 ns with 1X, 2.1 ns with 10X), each time invisible at 1 kHz and large at 20 MHz. It is the strongest argument so far for a "both probes on one node" check before a sweep.

**Comparison with run C (1X probes, section 12.6).**

| | 1X (run C) | 10X (0c final) |
|---|---|---|
| Signal at the scope input for 1 Vpp at the tip | 1 Vpp at 1 kHz and 1 MHz, **0.33 Vpp at 20 MHz** (−10 dB) | 0.1 Vpp, flat to 20 MHz (decodes to 0.985 to 1.014 Vpp) |
| V/div used | 200 mV | 20 mV |
| Gain CH2/CH1 at 1 kHz / 1 MHz / 20 MHz | +0.06 / +0.07 / −0.16 dB | +0.02 / −0.03 / −0.03 dB |
| Phase at 1 kHz / 1 MHz / 20 MHz | +0.04° / −0.13° / +0.24° | −0.10° / +0.01° / +1.08° |
| Phase spread (sd) at 20 MHz | 0.28° | 0.10° |
| Fit SNR at 1 kHz / 20 MHz | 35.6 / 27.0 dB | 35.5 / 33.0 dB |
| Smallest signal tried | not tried below 1 Vpp | 50 mVpp: SNR 21 to 28 dB |

Both give gain within 0.2 dB and phase within about 1° at every frequency. 10X is clearly better at 20 MHz (6 dB more SNR, a third of the phase spread, full amplitude). 1X was 0.8° closer to zero phase at 20 MHz, but that run was not swap-tested, so I would not read anything into the difference. Run C and 0c were taken with different tip wiring, which limits how exactly they can be compared.

**Recommendation: when to use 1X and when 10X.**

- **Use 10X by default**, and for anything that goes above about 1 MHz. It is flat to 20 MHz here, where 1X had already lost two thirds of the signal. It also loads the circuit under test much less than 1X does; that is general probe behaviour and was not measured here.
- **Use 1X only for small signals at low frequency**: when the signal at the test point is below roughly 50 mVpp and the sweep stays under about 1 MHz. 10X costs a factor of ten in signal (20 dB), and at 50 mVpp it was already down to 21 to 28 dB SNR. The 1 MHz limit comes from run C, where 1X still read full amplitude at 1 MHz and −10 dB at 20 MHz; where between those it starts to fall was not measured.
- **Do not mix**: both channels must use the same probe type and setting, compensated, because the ratio only cancels the probes if they match.
- **In software**: keep the scope at `PROBe 1X` and apply the ratio per channel in the application, as SPEC.md's `probe_atten` already intends. Auto-selection should work on the voltage at the scope input (tip voltage divided by the ratio).
- **Averaging** is the remedy for small signals at 10X: at 50 mVpp the single-capture phase spread was 0.1 to 0.24°, which averaging a few captures would bring down.

**Verdict after 0c (written before section 12.11; the 'connection-induced' warning in it is superseded): GO WITH WORKAROUNDS, unchanged.** 0c adds confidence (10X works to 20 MHz, the layer ran 490 more captures without a single error, the scope's own channel mismatch is about 0.09 dB and 0.9° at 20 MHz) and repeats one warning (connection-induced phase error). Not verified in 0c: the 8-division assumption behind auto-selection, 1X below 1 Vpp, any frequency between 1 MHz and 20 MHz, and the cause of the wiring offsets.

### 12.11 Channel alignment shifts by whole samples: cause, fix, and what is still open

**How it was found.** The user noticed that the CH1/CH2 phase offset was visible on the scope's own screen when one of my tests started, and went away after a channel was switched off and on at the front panel, with the wiring untouched. That ruled out wiring. Scripts: `hwcheck/dbg0c_skew.py` to `dbg0c_skew7.py`, `s0c_realign.py`. Raw data: `hwcheck/results/dbg0c_skew*.json`, `s0c_realign.json`. All measurements: both 10X probes on generator CH1, 20 MHz, 1 Vpp, 25 ns/div, single-shot two-channel captures through `iolayer.py`.

**What the fault is.**

- The CH2 − CH1 delay takes only discrete values 2.000 ns apart: about +150 ps (aligned), +2150 ps, +4150 ps and −1850 ps. At 20 MHz those are +1.1°, +15.5°, +29.9° and −13.3°.
- 2 ns is one sample period at 500 MSa/s. In two re-alignment runs the states were visited in the order +2150 → +4150 → −1850 → +150, i.e. steps of +2 ns that wrap round after 8 ns.
- Within a state the value is steady to about 0.1° at 20 MHz over hundreds of captures. The offset is visible on the scope's own display, so it is in the scope's acquisition, not in my read-out or fitting.
- It is invisible at low frequency: one step is 0.0007° at 1 kHz and 0.72° at 1 MHz.

This accounts for every unexplained offset in this report: 4.1 ns in runs A and B (two steps), about 0 in run C, 2.15 ns in the first 0c run (one step), about 0 in the final 0c runs.

**What does NOT change it** (parts 1, 2, 4 and 5; each tried 2 to 12 times, 0 changes in every case): timebase changes including a walk through all 23 steps, V/div changes on either channel including a walk through all 15 steps, coupling, bandwidth limit, trigger source, trigger loss and recovery, `:STOP` then `:RUN` in an open session, switching CH1, CH2 or CH3 off and on by command at nine different timebases and while stopped, generator output off and on, generator frequency changes, a 5 ms/div + 5 V/div excursion, and a new libusb context.

**What changes it** (part 6, 25 repetitions per case; a "slip" is a change of more than 500 ps):

| Action repeated 25 times | Slips |
|---|---|
| `iolayer` connect as it was (reopen session, `:RUN`, device clear, sentinels, WAVeform writes) | 11 |
| reopen session, then resync (`:RUN`, device clear, sentinels) | 15 |
| reopen session, wait 3 s, then the same resync | 13 |
| reopen session, `*IDN?`, timebase query, then `:RUN` | 13 |
| reopen session, then `:RUN` | 8 |
| `:RUN`, 0.3 s, device clear, in an open session | 1 |
| `:RUN` only, in an open session | 0 |
| resync in an open session | 0 |
| device clear only | 0 |
| reopen session, then device clear | 0 |
| reopen session, then `*IDN?` | 0 |
| reopen session, then `:WAVeform:MODE` + `:FORMat` | 0 |
| `:WAVeform:MODE` + `:FORMat` only | 0 |
| reopen session, then `:TRIGger:SWEep AUTO` (no `:RUN`) | 0 |
| `:TRIGger:SWEep AUTO` only | 0 |

**Cause, as far as it is established:** a `:RUN` command sent after the USB session has been reopened re-rolls the alignment in roughly half the cases (49 of 100 across the four rows that contain that combination). `:RUN` in a session that stays open did not (0 of 25, plus 1 of 25 when followed by a device clear). Waiting after the reopen does not help. Why the scope does this is not known; the manual says nothing about it. Whether it is the first `:RUN` after a reopen or any `:RUN` soon after one was not separated.

**Why it hit every test.** `iolayer.connect()` began with a resync, and the resync began with `:RUN`. Every test script therefore reopened the session and sent `:RUN` at its start, re-rolling the alignment about half the time. The Milestone 0 scripts and `t0b_iolayer.py` also send `:RUN`.

**The fix, and its verification.**

- `iolayer.py` no longer sends `:RUN` anywhere, and `ScopeIO.write()` refuses it (`BlockedCommand`). A stopped scope is restarted with `:TRIGger:SWEep AUTO` alone, which was seen to work in 50 of 50 cases (status `TRIGED` 0.8 s later).
- After the fix: the full connect, 25 times: **0 slips** (11 before). Reopen plus resync, 25 times: **0 slips** (15 before).
- Regression: `t0b_iolayer.py` again passes 55 of 55 with the changed resync, including the forced out-of-step rounds (2 of 6 proven by an unchecked query, 5 of 6 met and repaired by the layer).

**No command undoes a shift** (part 7, each tried three times from a shifted state, 0 of 18 returned to aligned): memory depth 7K → 70K → 7K, memory depth → AUTO → 7K, acquire type → PEAKdetect → NORMal, timebase mode → WINDow → MAIN, both channels off for 3 s then on, `:STOP` then sweep AUTO. Earlier (part 3) channel toggles, `:STOP`/`:RUN`, a timebase excursion and WAVeform commands also failed.

That contradicts the user's observation that a front-panel channel off/on fixed it. I could not reproduce that by command. One possibility is coincidence: the toggle was done while one of my scripts was starting, and the script's own `:RUN` re-rolled the alignment at that moment. I have no evidence either way.

**Re-alignment tool.** Since nothing undoes a shift, `hwcheck/s0c_realign.py` uses the fault itself: with both probes on one node it measures the delay and, while it is more than 1 ns from zero, reopens the session and sends `:RUN`, then measures again. Two runs: aligned after 8 re-rolls and after 7 re-rolls, each confirmed afterwards by a separate process (+143 ps and +153 ps). `--check` only measures.

**State left on the scope:** aligned (+153 ps at the last check), free-running, generator outputs OFF.

**What this means for the earlier results in this report.**

- All gain results stand; a time shift does not change gain.
- Phase results taken in the aligned state stand: run C (1X) and the final 0c runs (10X).
- Runs A and B (4.1 ns) and the first 0c run (2.15 ns) were taken in shifted states. Their repeatability figures are valid; their mean phase is the shift.
- The probe-swap comparisons need a caveat: the two halves of each swap pair were separate script runs, so the state could have changed between them. The measured phases show it did not (29.58° and 29.59° in runs A and B; +1.08° and +0.70° in 0c), so those comparisons hold, but only because both halves happened to land in the same state.
- The explanations given at the time (a fixed scope delay, then wiring, in sections 12.6 and 12.10 and in the verdict block) were wrong.

**Not known, and it matters:**

1. Whether anything else re-rolls the alignment: the front panel's Run/Stop or Single keys, a power cycle, Auto-set, UNI-T's own PC software, or a USB replug. None was tested.
2. Which state the scope is in after power-on.
3. Whether the same thing happens between other channel pairs (CH3, CH4) or with a different number of channels switched on, where the sample period, and so the step size, would differ. The 4.1 ns seen in runs A and B was two 2 ns steps as far as I can tell, but that run was not examined at the time.
4. Whether it happens over LAN, or under a vendor VISA driver.
5. Only 20 MHz at 25 ns/div was used for the investigation.

**Consequences for the application.**

1. **Never send `:RUN`.** Arm with `:TRIGger:SWEep SINGle`, return to free-run with `:TRIGger:SWEep AUTO`. This goes into the scope driver's rules alongside the Milestone 0 ones.
2. **A sweep cannot assume the channels are aligned.** Before measuring, the user should put both probes on the stimulus and let the software measure the CH2 − CH1 delay at a high frequency (20 MHz resolves one step as 14°). Then either subtract that delay from every phase result, or re-roll until it is zero. This is the through-calibration SPEC.md lists for v2; it needs to be in v1 in at least this minimal form.
3. **The check is cheap:** three captures (about 2.5 s) at one frequency separate the states by 14° with a spread of 0.1°.
4. The delay found should be stored with the result file, so a sweep taken in a shifted state can be recognised later.
