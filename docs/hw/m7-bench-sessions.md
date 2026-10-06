# Hardware history: Milestone 7 bench sessions with the user, sections 13.13 to 13.28 (2026-10-06)

Part of the hardware report. The current facts and the index of all sections: `HW_REPORT.md`. This file is a dated record of what was run and seen; it is not rewritten when a later run changes the picture, so read the facts sheet first.

These are subsections of section 13, whose header is in `docs/hw/m7-bringup.md`.

### 13.13 First bench session with the user present: skew wizard and through sweep from the GUI (2026-10-06, evening)

Both probes on generator CH1, both 10X. App started with `run.bat`, Mode = Instruments, commit `168dd4d`. Values are read from the user's two screenshots; no data file was exported.

- **Skew wizard in the GUI on the real instruments: works.** 10 MHz: +0.13 ns (+0.48 deg), gain -0.013 dB. 20 MHz: +0.15 ns (+1.07 deg), gain -0.024 dB. Measured +0.14 ns, snapped to the +0.15 ns state, gain mismatch -0.019 dB, correction at 20 MHz -1.08 deg. Same state as the headless check (+0.148 / +0.151 ns).
- **Through sweep from the GUI after accepting the check**: 114 points, 50 Hz to 20 MHz, 20 per decade, 5 Vpp, 100 mV/div on both channels, 114 s, no retries, no flags. Output 99.6 to 100.1 % of the input (within about 0.04 dB); phase within about 0.3 deg of zero over the whole range (last five points, 12.7 to 20 MHz: +0.01 to +0.26 deg, gain -0.011 to -0.026 dB).
- **Fault found and fixed**: the wizard's intro text named 0.5 MHz and 1 MHz (it still followed the sweep range) while the check ran at 10 and 20 MHz. Text only; fixed in `MainWindow.skew_freqs_hint` (commit `919814c`).
- **One enumeration miss**: the first `s6_state.py` of the session found no VISA resource at all (`list_resources` empty) although Windows and libusb showed both devices; the same script worked a few seconds later. Not reproduced, cause unknown.
- The app's log file holds no per-command lines for this run, so the command sequence was not reviewed.

### 13.14 CH3 / CH4, never used before (2026-10-06, evening)

The two probe BNCs moved to scope CH3 (reference) and CH4 (DUT), tips still on generator CH1, both 10X, channels set in the Scope panel. App at commit `919814c`. Values are read from the user's screenshots.

- **CH3 / CH4 work**: the skew check and a 114-point sweep (50 Hz to 20 MHz, 5 Vpp, 100 mV/div) ran with no retries and no flags. The sweep took 128 s against 114 s on CH1 / CH2 (about 0.92 s per point against 0.75 s at the top of the range); not looked into.
- **The delay of this pair is +0.08 to +0.09 ns, not +0.15 ns.** First check: +0.09 ns at 10 MHz (+0.34 deg), +0.08 ns at 20 MHz (+0.59 deg), gain -0.053 / -0.069 dB. Second check: +0.27 deg and +0.66 deg, gain -0.067 / -0.049 dB, measured +0.08 ns. Both were snapped to +0.15 ns, because the four states were measured on CH1 / CH2 and +0.08 ns lies inside the 0.3 ns snap window.
- **The snap over-corrects on this pair**: after accepting, the through sweep's phase falls from 0 to **-0.39 deg at 20 MHz** (-0.09, -0.21, -0.33, -0.38, -0.39 deg from 12.7 to 20 MHz). The measured value would have left about +0.1 deg. Below 1 MHz the error is under 0.03 deg.
- **CH4 reads lower than CH3 towards high frequency**: output 100 % of input at 50 Hz, falling to about 99.0 % at 20 MHz (-0.06 to -0.10 dB over the last five points). On CH1 / CH2 the same sweep stays within 99.6 to 100.1 %. The app does not correct gain; the wizard's warning threshold is 0.3 dB.
- **CH1 / CH2 repeated straight afterwards** (BNCs moved back): check +0.59 deg at 10 MHz, +1.21 deg at 20 MHz, measured +0.17 ns, snapped to +0.15 ns, gain mismatch -0.01 dB; sweep 114 s, phase -0.10 to +0.13 deg over the last five points, gain -0.002 to -0.030 dB. So the CH1 / CH2 delay has now read +0.14 and +0.17 ns in one evening (0.03 ns is 0.2 deg at 20 MHz).
- Open: whether CH3 / CH4 has the same 2 ns steps around its own +0.08 ns (not tested; it would need a `:RUN`, which is forbidden).

**Re-run on CH3 / CH4 after the snap change** (commit `ec3d897`, user decision: snap only for reference CH1 / DUT CH2; from the user's screenshot): check +0.34 deg at 10 MHz and +0.74 deg at 20 MHz, gain -0.065 / -0.068 dB, **+0.10 ns applied, not snapped**. Through sweep, 114 points in 116 s, no retries, no flags: phase +0.05, -0.07, +0.26, +0.05, **+0.07 deg** from 12.7 to 20 MHz (was -0.39 deg at 20 MHz with the snap). The gain droop of CH4 against CH3 is unchanged (about 99.0 to 99.3 % above 10 MHz, -0.045 to -0.100 dB). The sweep time is the same as on CH1 / CH2, so the 128 s of the first CH3 / CH4 run is not a property of the channel pair.

### 13.15 Watchdog with the scope's USB cable pulled during a sweep (2026-10-06, evening)

App at commit `b6dcf64`, started with `--debug`, reference CH3 / DUT CH4, full-range sweep. The user pulled the scope's USB cable after 26 of 114 points. Times are from the app's log.

- **The watchdog works on a scope that is really gone.** 19:00:01.354 first failed read (`[Errno 19] No such device (it may have been disconnected)`); resync attempt until 19:00:03.925 (`:TRIGger:SWEep AUTO` refused, eight rounds of device clear + `*IDN?`, all failed: `No device found`, then `Invalid session handle`); 19:00:03.925 `:CHANnel1:OUTPut OFF` and `:CHANnel2:OUTPut OFF` to the generator; 19:00:04.156 error shown. **Generator off 2.6 s after the cable came out.** The user saw the output light go out and the error dialog; the toolbar went back to the disconnected state and the 26 points stayed on the plot. No forbidden command in the log.
- **Scope state after replugging, no power cycle** (`s6_state.py`, read-only): answers at once, `:SYSTem:LOCK?` 0, sweep AUTO and running, timebase still 500 us/div (the sweep's value: the restore could not run), no error. So a pulled cable needs no power cycle, and no panel lock was left behind.
- **Two faults in the messages, fixed after this run**: (1) the log said "The scope was resynchronised during the sweep; the skew correction used may no longer be right" although the resync had failed; it is no longer written for a dead session. (2) The advice was to power-cycle the scope, which does not fit a pulled cable; the transport now reports whether the device is still on the bus (`Transport.present`, a USB enumeration, nothing is sent) and the advice becomes "check the scope's USB cable and that it is switched on" (`UNPLUGGED_ADVICE`). The new text has run against the simulated transport only.
- **Kept as it is (user decision)**: the generator output stays on while the resync is tried and is switched off when it fails.
- Not covered by this test: a scope that is frozen but still on the bus (writes time out instead of failing at once, so the resync takes longer).

**Second and third cable pull, with the fixes** (commit `4828300`, `--debug`, sweeps on CH1 / CH2; from the app's log and the user's screenshot). 19:08:32.767 first failed write (`[Errno 19] No such device`), 19:08:35.358 generator outputs off (2.6 s), 19:08:35.587 error with the new text: "The scope is no longer on USB. ... Check the scope's USB cable and that it is switched on, then connect again and repeat the channel skew check." No "was resynchronised" line. **Reconnect after replugging, no power cycle, same app window: worked** (19:09:13 connected, 19:09:35 a new sweep started). That sweep lost the scope again at 19:09:42.202 after 4 of 114 points, same error and the same sequence (generator off at 19:09:44.795). The user confirmed that this third loss was a deliberate pull as well.

### 13.16 A power cycle clears the panel lock (2026-10-06, evening)

`hwcheck/s6_lock.py on` with the app disconnected: `:SYSTem:LOCK?` 0 before, 1 after `:SYSTem:LOCK ON`; remote control worked while locked. The user pressed a front-panel key: ignored, and the scope showed a "locked" message. The user then power-cycled the scope (USB cable left in). After the boot the panel worked again and `:SYSTem:LOCK?` read 0 (`s6_lock.py query`), with no `:SYSTem:LOCK OFF` sent.

- **A power cycle clears the lock.** So the watchdog's advice to power-cycle a frozen scope also frees its panel; `probe --unlock` is only needed when the scope is not power-cycled.
- **Power-on state seen here** (`s6_state.py`): the scope came back with the settings it had before (5 ms/div, CH1 and CH2 at 100 mV/div, probe 1X), sweep AUTO and running, no error. One observation, not a general statement about its power-on state.

### 13.17 Paced table walk with the probe tool: no freeze (2026-10-06, evening)

`python -m bodeplot.tools.probe --walk-tables --yes` (250 ms after every step), commit `485bfe2`, user at the bench. Raw result: `hwcheck/results/m7/probe_walk_20261006.json`.

- **The walk ran to the end and the scope did not freeze.** One run; the two freezes (0b, and the unpaced `build_tables()` of 2026-10-06) are still unexplained, so this shows that a paced walk can pass, not that it always does.
- **The walked tables are identical to the shipped ones**: timebase 23 steps, 1 ns to 20 ms/div with 25 ns in place of 20 ns; V/div 15 steps, 500 uV to 20 V. The tool wrote them to `%LOCALAPPDATA%\bodeplot\step_tables.json`.
- Afterwards (`s6_state.py`): timebase 5 ms/div and CH1 100 mV/div put back, panel unlocked, sweep AUTO, no error, generator outputs off.

### 13.18 The RC phase lead is the capacitor's own loss (2026-10-06, evening)

The 100 nF of the test low-pass is a film capacitor (user). The user measured it out of circuit on their LCR meter (UNI-T UT612), series mode:

| Test frequency | Cs | D |
|---|---|---|
| 100 Hz | 105.72 nF | 0.001 |
| 1 kHz | 105.42 nF | 0.003 |
| 10 kHz | 104.36 nF | 0.009 |
| 100 kHz | 102.62 nF | 0.028 |

Model: `Zc = (D - j) / (2 pi f Cs)`, `H = Zc / (R + Zc)`, R taken as exactly 1000 ohm (not measured), Cs and log D interpolated over log f between the test frequencies. Compared with the bench values of 13.12 (mean over the V/div steps):

| Frequency | D used | Model phase | Measured phase | Lead over the ideal RC: model / measured | Measured minus model |
|---|---|---|---|---|---|
| 5 kHz | 0.0065 | -72.75 deg | -72.78 deg | +0.39 / +0.36 deg | -0.03 deg, -0.05 dB |
| 20 kHz | 0.0127 | -84.90 deg | -84.81 deg | +0.77 / +0.86 deg | +0.09 deg, -0.10 dB |
| 50 kHz | 0.0199 | -87.09 deg | -87.04 deg | +1.17 / +1.22 deg | +0.05 deg, -0.07 dB |
| 100 kHz | 0.0280 | -87.51 deg | -87.40 deg | +1.62 / +1.73 deg | +0.11 deg, -0.17 dB |

- **The capacitor's measured loss explains the phase lead to within 0.11 deg**; only the 100 kHz point uses a D that was measured at that frequency, the other three are interpolated. The app measured the circuit correctly; the "ideal RC" was the wrong reference.
- What is left (up to +0.11 deg and -0.17 dB at 100 kHz) is within what the resistor's tolerance, the breadboard contacts and the interpolation can give; not separated.
- The capacitance also falls with frequency (105.7 nF at 100 Hz to 102.6 nF at 100 kHz), so one corner frequency does not describe this part over the whole sweep.
- No capacitor was swapped; the ceramic and mica parts the user has were not needed.

### 13.19 Probe swap on CH3 / CH4; generator off earlier when the scope stops taking commands (2026-10-06, evening)

- **The CH3 / CH4 gain difference follows the probes.** The user swapped the two probe BNCs between CH3 and CH4 (tips still on generator CH1) and repeated the through sweep: the fall to about 99.0 % at 20 MHz (13.14) became a rise (user's report; no screenshot or data file). So it is the two probes, each compensated against the channel it was on before, and not a difference between the channels' own responses. Re-compensating the probes on the channels they are used on is the remedy; not done.
- **Generator off as soon as the scope fails a transfer during a resync** (user decision). Reason: with the cable pulled every write fails at once and the whole resync took 2.6 s (13.15), but on a scope that is frozen and still on the bus every write waits for its 1.5 s timeout over up to eight rounds, an estimated 15 to 35 s with the generator on (from the code, not measured). Now the first failed transfer inside the resync switches the outputs off (`Digitizer.on_link_trouble`, `Session._link_trouble`); if the scope then answers again the output is switched back on and the point is measured again (`core.measure_with_output`). Run against the simulated transport only; a real frozen scope cannot be provoked.
- **Dropped by the user**: restoring the generator's settings after a sweep. The output is switched off and that is enough.

### 13.20 Where a sweep point's time goes, and how far the capture margins can be shortened (2026-10-06, evening)

**From the app's debug log** of a real sweep (50 to 870 Hz, 25 points, 1.05 s per point): waiting for the capture 0.57 s (about 30 status polls), reading the two waveforms 0.28 s, generator commands 0.17 s, everything else 0.03 s. Inside the read, **`:WAVeform:DATA?` itself takes 0.12 to 0.15 s per channel to be answered**; the commands around it (source, `*OPC?`, preamble, sentinels) take about 0.025 s per channel.

**Bench runs** with `hwcheck/s7_capspeed.py` (the app's driver with its margins changed, commit `465a9d8`, both probes on generator CH1, CH3 / CH4, 1 Vpp, 12 captures per scenario; raw data in `hwcheck/results/m7/s7_capspeed_*.json`). Every capture was checked for driver errors, the record's sample interval, fit SNR, amplitude / gain / phase against the baseline, and STOP after the read.

- **The scope's own single-shot cycle is 0.40 s at any timebase tried**: arm command, ARMED after 0.02 s, AUTO after 0.29 s, STOP after 0.40 s (1 kHz and 1 MHz alike).
- **Baseline** (quiet 0.3 s, hold 0.1 s): 0.90 to 0.93 s per capture = wait 0.51 to 0.54 s + read 0.37 to 0.39 s; 1.09 s when the timebase changed just before (0.19 s of quiet time). 144 of 144 captures good over three runs.
- **STOP hold time** (0.10 / 0.05 / 0.02 / 0 s): the capture gets about 0.05 s shorter at 0.05 s and no shorter below that, because the read then takes longer by the same amount (0.38 -> 0.41 -> 0.44 s): the scope is busy for about 0.1 s after it reports STOP either way.
- **With no hold time, every capture after a timebase change was wrong: 12 of 12.** The reference channel (read first) came back with the sample interval of the PREVIOUS timebase and a fit amplitude of 0.030 V in place of 0.496 V (SNR -24 dB); the DUT channel, read 0.2 s later, was right (SNR 35 to 40 dB). The same captures were good at 0.02 s (12 of 12) and above. **This is the signature of the one bad capture of 13.9** (first point after a timebase change, 0.021 V in place of 0.496 V), with one difference: there both channels were wrong. It makes "the record was read before the scope had finished it" the likely cause of 13.9; not proven, since 13.9 happened with the 0.1 s hold in place.
- **Quiet time before arming** (0.3 / 0.2 / 0.1 / 0.05 / 0 s): all 240 captures good. It only costs time after a setting change (0.19 s at 0.3 s, 0.09 s at 0.2 s, nothing at 0.1 s and below, because setting and reading back the timebase already takes about 0.1 s). No double arm cycle was seen at any value; 12 captures per value do not rule out the fault that the 0.3 s was introduced for (12.4).
- **Conclusion: the margins are not where the time is.** Of about 0.92 s per capture, 0.40 s is the scope's arm cycle, about 0.1 s its work after STOP and 0.27 s its two answers to `:WAVeform:DATA?`: 0.77 s that the driver cannot shorten with this capture method. What the app adds is about 0.15 s per capture plus 0.17 s for the generator's frequency set and read-back. Nothing was changed in the driver.

### 13.21 Reading both channels from a running scope: fast, good gain, unusable phase (2026-10-06, evening)

User's idea: no single shot and no stop, read the two channels from the scope while it triggers continuously. `hwcheck/s7_stream.py` (commit `2702d2d`), both probes on generator CH1, CH3 / CH4, 1 Vpp, scope in sweep AUTO triggering on the reference. Raw data: `hwcheck/results/m7/s7_stream.json`.

| Frequency | Single shot (6 points) | Running (30 pairs) |
|---|---|---|
| 1 kHz | gain +0.053 dB (sd 0.004), phase +0.08 deg (sd 0.03), 0.93 s | gain +0.053 dB (sd 0.005), phase +0.08 deg (**sd 0.33**, -0.59 to +0.66), **0.21 s** |
| 1 MHz | gain +0.108 dB (sd 0.004), phase +0.05 deg (sd 0.05), 0.90 s | gain +0.104 dB (sd 0.005), phase -0.02 deg (**sd 0.42**, -0.85 to +0.75), 0.21 s |
| 20 MHz | gain +0.137 dB (sd 0.019), phase +0.06 deg (sd 0.10), 0.96 s | gain +0.127 dB (sd 0.018), phase -0.31 deg (**sd 5.93**, -10.83 to +10.54), 0.23 s |

- **Speed: 0.21 s for both channels against 0.93 s**, 4.4 times faster per capture. The scope answers `:WAVeform:DATA?` faster while it runs. All 90 pairs were different records (status TRIGED every time).
- **Gain is as good as single shot.**
- **Phase is not.** The two channels come from two different acquisitions, and each record is placed against its trigger with a scatter of about 0.1 sample interval of the record, and not finer than about 0.8 ns: sd 0.9 us at 1 kHz (10 us per point), 1.2 ns at 1 MHz (10 ns per point), 0.8 ns at 20 MHz. That is 0.3 to 0.4 deg sd up to 1 MHz and 6 deg sd (range +-11 deg) at 20 MHz. The mean is unbiased, so averaging helps, but 0.1 deg at 20 MHz would take about 3500 pairs.
- **No stale records**: after a generator frequency change (50 Hz, 1 kHz bands) and after a timebase change every read was of the new signal at every wait from 1 s down to 0 s (10 and 8 reads per wait). Setting and reading back the frequency or timebase already takes 0.1 to 0.2 s.
- **One empty reply in about 330 channel reads**: `:WAVeform:DATA?` on CH4 answered `b'\r\n'` in the 1 MHz frequency-change band (fifth read at wait 1.00 s). The driver's resync recovered it; the rest of that band was skipped as planned, so the 1 MHz band has no result for the shorter waits. This is the hazard of S4 / S5: a running scope sometimes has no record to give.
- **Conclusion**: continuous reading cannot replace single shot for a Bode plot, because of the phase. It could serve a fast gain-only or preview mode (estimated 0.45 s per point with the generator's 0.17 s and the 0.05 s settle; not measured as a sweep), with the empty-reply risk to handle. Nothing was changed in the app.

### 13.22 Stale-record check in the driver, proven on the bench (2026-10-06, evening)

`UniTUPO1000.acquire` now compares the time span of every record (sample interval x points) with the timebase that is set; a record that does not match is thrown away and a new acquisition is taken, without a resync, up to two times (`stats["stale_records"]`). Bench check with `s7_capspeed.py custom 0.3 0.0 0.05 0.01` (no STOP hold time, the setting that gave 12 stale captures of 12 in 13.20), commit `79930d3`: **13 stale records caught and retaken, 48 of 48 captures good**; a capture after a timebase change then takes 1.97 s (two acquisitions). With the normal 0.1 s hold the baseline block of the same run needed no retake (1.09 s per capture after a timebase change, as before).

### 13.23 Fast preview mode, timed on the bench (2026-10-06, evening)

The user asked for a preview / gain-only mode built on 13.21, with the phase shown and marked rough. `Method.PREVIEW` ("Fast preview (rough phase)" in the Method box): the sine fit as before, the channels read with `UniTUPO1000.acquire_running` from the scope in sweep AUTO. Every point is flagged `PREVIEW`; no skew check is asked for.

Bench: `m7_sweep.py preview_full 50 20e6 20 --no-skew --preview --ch=3,4`, commit `737f70a`, both probes on generator CH1, 1 Vpp. Data: `hwcheck/results/m7/m7_sweep_preview_full.csv`.

- **114 points in 52.8 s, 0.46 s per point**, against 114 to 119 s for the same sweep single shot: 2.2 times faster. A point costs about 0.21 s of measuring, 0.3 to 0.37 s on the points where the timebase changes; the rest is the generator and the settle time.
- **Gain +0.04 to +0.16 dB over the whole range**, the same picture as the single-shot through sweeps on this channel pair with the probes swapped (13.19).
- **Phase scatter (through connection, so the true value is near 0)**: sd 0.38 deg below 100 kHz (-0.92 to +0.89), 0.56 deg from 100 kHz to 1 MHz, 0.75 deg from 1 to 5 MHz, 3.64 deg above 5 MHz (-7.39 to +3.35).
- **No empty reply, no resync during the sweep. 3 stale records** were caught by the check of 13.22 and read again: reading a running scope straight after a timebase change does hand out the old record now and then (it did not in the 8 reads per wait of 13.21).
- Scope settings restored, panel unlocked, generator off, scope left in sweep AUTO.
- Not yet seen by the user in the GUI.

### 13.24 Fast preview in the user's hands: three faults, and the scope's busy episodes at 200 / 500 ns/div (2026-10-06, night)

The user ran Fast preview from the GUI and reported: (1) the Method box went back to Sine fit when the sweep ended; (2) a "channel skew check" prompt after every run, saying the scope connection was resynchronised; (3) near the end the sweep froze for a moment and "the gain drops / phase goes too low", and re-measuring the point brought it back.

- **(1) Cause found and fixed.** `ConfigPanel.set_has_builtin(False)` set the Method box to its first entry every time; it runs on every session update, and the real scope has no built-in measurement. It now only moves away from "Scope built-in". Before Fast preview existed the box only ever held Sine fit on the real instruments, so the fault could not show.
- **(2) and the freeze of (3) are one thing: an empty reply to `:WAVeform:DATA?` from the running scope.** The app's log of the user's sweeps shows one per sweep (timebase 500 ns and 200 ns/div), each followed by a resync, which ends the validity of the skew check and so raised the prompt. Reproduced on the bench (`m7_sweep.py ... --preview --amp=5`, 200 kHz to 20 MHz): 2 of 4 sweeps, 3.85 s for that point.
- **What the scope does** (`hwcheck/dbg7_empty.py`, frequency steps at 200 ns/div, 5 Vpp, CH1 / CH2):
  - 6 empty replies in 200 pair reads, then 8 in 300; the trigger status read TRIGED before every one of the 1000 channel reads, so the status does not announce it.
  - It always starts on the SECOND channel of a pair; the next read (the first channel of the next pair, about 0.5 s later) is empty too; the one after is good.
  - The link stays in step: five `*IDN?` after each of 8 empty replies were all answered correctly, and no late block arrived.
  - Timing (`--driver`): the scope takes **1.11 s to give the empty answer**, the second try again 1.11 s, the next `*IDN?` 0.68 s; about 3.4 s from the first failed read until the scope answers at its normal speed. Taking a single shot in place of the second read does not help: the `*OPC?` after the arm command then waits 2.28 s, and the point takes 4.1 s either way.
  - Seen only at 200 and 500 ns/div (about 0.7 to 3.5 MHz): about 10 in the sweeps and tests of this evening there, none at 1 us/div or 100 ns/div in the same sweeps, none in single-shot mode ever. What the scope is busy with is not known.
- **Fix for (2)**: after an empty reply `acquire_running` checks the link with the sentinel and reads again 0.5 s later, up to six times; it only resyncs if the link is out of step. Bench: 5 sweeps, one episode, no resync (`resyncs` stayed at the 1 of the connect), so no skew prompt; the point still took 4.24 s, which is the scope's own time. **The freeze itself is not fixed** and cannot be from the PC side with this read method; avoiding 200 / 500 ns/div in preview mode is an idea, not tried.
- **The gain drop of (3) was not reproduced**: in 9 bench sweeps the point measured after an episode was right (for example +0.001 dB and +0.039 dB). Not explained; a screenshot or an exported CSV of such a sweep is needed.
- **Mistake of mine, corrected**: two `dbg7_empty.py --driver` runs were piped into `Select-Object -First N`. PowerShell ends the pipeline when N lines are reached and kills the script, so its `finally` block never ran: **the generator output stayed ON at 5 Vpp (through connection only, probes on it) and the scope panel locked** for a few minutes, timebase left at 200 ns/div. Found by the read-only state check, then outputs off, panel unlocked, timebase back to 5 ms/div, verified. Rule: never cut a bench script's output short in the pipeline; filter it, or write it to a file.

### 13.25 The +2.15 ns state seen in the user's session; a scope restart brought +0.15 ns back (2026-10-06, night)

User's report, no log or screenshot: while testing the app the skew check "was always 2.15 ns"; after restarting the scope it was back to normal. The user first saw it after running the skew check once with the RC low-pass still in circuit.

- +2.15 ns is one of the four known alignment states (12.11), and it stayed over several checks until the scope was restarted, so the scope's channels really were one 2 ns step apart. The skew check cannot cause that: it only measures. Run through the low-pass it measures the filter's phase (about -90 deg at 10 and 20 MHz, at about -50 dB) and would not give a steady 2.15 ns.
- **New: a scope restart put the alignment back to +0.15 ns** (one observation). Whether a restart always does was listed as untested in 12.11.
- **What moved the alignment is not known.** The only proven trigger is a `:RUN` after the USB session is reopened, which nothing in the app or in tonight's scripts sends. New this evening and not ruled out: reading from the running scope (Fast preview), the two bench scripts that were killed without closing their session (13.24), the many reconnects, and any use of the scope's front panel. The app handled the state as designed: it measured it, snapped to +2.15 ns and corrected the phase with it.

**Follow-up the same night (`hwcheck/m7_previewskew.py`, both probes on one node, CH1 / CH2, after the scope restart).** The user confirmed that a Fast preview sweep had run in the session that showed +2.15 ns, so both suspects were tested through the app's own code:

- **Ten Fast preview sweeps (200 kHz to 20 MHz), a skew check after each: no shift.** Delay +0.08 to +0.09 ns in all 11 checks; three of the sweeps had busy episodes (8 empty replies in all), none had a resync.
- **Twelve driver resyncs while the scope was running** (what the first version of Fast preview did after an empty reply), a skew check after each: **no shift**, +0.08 to +0.10 ns in all 13 checks.
- So neither reproduces the +2.15 ns state; its trigger is still unknown.
- Side observation: this pair now reads +0.08 to +0.10 ns with a gain mismatch of +0.17 dB, where it read +0.14 to +0.17 ns and -0.02 dB earlier in the evening (13.13, 13.14). Not investigated; the probes may sit on the other channels than before, or the restart changed it. The check snaps this to +0.15 ns, which is 0.06 ns (0.4 deg at 20 MHz) away from what was measured: the same over-correction as on CH3 / CH4 in 13.14.
- At the first try the scope was not found, and at the second it did not answer the resync at connect (`the scope does not answer after a resync`); a minute later it answered normally. The user had just restarted it.

### 13.26 The scope's own measurements against the sine fit (2026-10-06, night)

`hwcheck/s7_builtin.py` (commit `e5592db`), both probes on one node, CH1 / CH2, 1 Vpp, 20 mV/div, at 50 Hz, 1 kHz, 100 kHz, 1 MHz, 10 MHz and 20 MHz. Queries only: `:MEASure:VPP?`, `:MEASure:VAMPlitude?`, `:MEASure:VRMS? CYCLe,<source>`, `:MEASure:PHASe? <source1>,<source2>`, `:MEASure:PDELay?` (U1K p.30 to 32). Each was asked on the stopped record of a single shot and on the running scope. Data: `hwcheck/results/m7/s7_builtin.json`. No error, no resync.

- **All five commands are answered**, in exponent notation. `:MEASure:PHASe?` had never been sent before.
- **Amplitude** (`VPP` and `VAMPlitude` gave the same number every time): in steps of 0.8 mV at 20 mV/div, which is one ADC code and 0.8 % of this signal (0.07 dB), and 1.1 to 1.7 % above the sine fit's value (a peak-to-peak reading includes the noise). `VRMS` over whole cycles is finer and 0.6 to 1.5 % above the fit. The DUT / reference ratio from `VPP` came out at 0.069, 0.069, 0.139, 0.137, 0.138 and 0.206 dB against 0.083, 0.099, 0.145, 0.149, 0.174 and 0.193 dB from the fit: within 0.04 dB here, but it can only move in 0.07 dB steps.
- **Phase is only answered on a STOPPED record; on the running scope the reply is `*`** (also for `PDELay`). On the stopped record it reads -0.36, 0 or +0.36 deg and nothing in between at these six frequencies: a resolution of 0.36 deg. Against the fit (+0.09, +0.10, +0.04, +0.04, +0.27, +0.50 deg) it read -0.36, -0.36, 0, 0, 0, -0.36 deg with the sources in the order reference, DUT, and the same with the opposite sign the other way round; so the error is up to about 0.9 deg at 20 MHz, and the sign convention could not be pinned down on a through connection.
- `:MEASure:PDELay?` is useless at 20 MHz (50 ns and scattering, a whole period) and coarse below (-60 us at 50 Hz, -2 us at 1 kHz, 1 ns at 1 MHz: one step each).
- **Time**: 0.056 s per query on a stopped record, 0.006 s on the running scope.
- **Conclusion: no use for the Bode plot.** Phase needs the stopped record, so the single shot's 0.5 s stays; the three queries (two amplitudes, one phase) would take 0.17 s in place of the 0.28 s waveform read, about 0.1 s per point, and would cost a factor of ten or more in resolution (0.07 dB and 0.36 deg against 0.005 dB and 0.03 deg). On the running scope only the amplitudes are available, which Fast preview already measures better. The driver keeps declaring no built-in measurement.
- The manual (p.27) says a measurement query switches the measurement on by itself; nothing was switched off afterwards, so a read-out may be left on the scope's screen.

### 13.27 Fast preview keeps off 200 and 500 ns/div: the pauses are gone (2026-10-06, night)

Both probes on the generator output, CH1 / CH2, 5 Vpp (user confirmed the wiring).

- **The busy episodes belong to the timebase** (`dbg7_empty.py --driver --tb`, 300 pair reads each with frequency steps, commit `dfe6cc9`): 100 ns/div at 1.85 to 3.2 MHz, 0 slow reads and 0 empty replies; 1 us/div at 0.74 to 1.7 MHz, 0 and 0. Against 14 episodes in 500 pair reads at 200 ns/div (13.24).
- **Change**: `DigitizerCaps.running_avoid_timebases` (UPO1000: 200 and 500 ns/div, `RUNNING_BUSY_TB`). In Fast preview the meter takes the next slower step that is not on the list if a cycle still gets 20 samples, otherwise the next faster one if a whole cycle still fits (`DualChannelScopeMeter._off_busy_timebase`). In practice 1 us/div up to about 2.5 MHz and 100 ns/div from there to 3.5 MHz. Sine fit (single shot) is unchanged and keeps using 200 and 500 ns/div.
- **Bench check** (`m7_sweep.py tbfix_preview_N 2e5 2e7 30 --preview --amp=5`, commit `9905c48`): **6 sweeps, no empty reply, no resync, slowest point 0.63 s**, 24.8 to 25.2 s per sweep of 61 points (before: 2 of 4 and 1 of 5 sweeps had a point of about 4 s).
- **Quality in the changed range (0.7 to 3.5 MHz) is the same**: gain sd 0.007 dB (before 0.008), phase sd 0.57 deg (before 0.59), over 126 and 105 points.
- Still unexplained: what the scope is busy with at those two timebases. The user's report of a gain drop near the end of a preview sweep (13.24) was not seen in these 6 sweeps either.
- **Dropped by the user**: the scope's web interface and LAN ("not an option most of the time").

### 13.28 Acceptance by the user: Milestone 7 done (2026-10-06, night)

After the last changes (measured skew value, no skew pop-up on connect, Fast preview off 200 / 500 ns/div) the user restarted the app and ran, from the GUI on the real instruments: connect, skew check with both probes on the generator, then one Sine fit sweep and one Fast preview sweep of their RC filter. Report: "both sweeps look right". No data file or screenshot of this run. The user asked for Milestone 7 to be marked done.

Open after Milestone 7 (also in SPEC.md section 17): the trigger of the +2.15 ns alignment state (13.25); what the running scope is busy with at 200 / 500 ns/div (13.24, avoided since 13.27); one unreproduced report of a gain drop in a Fast preview sweep (13.24); a scope frozen but still on USB; Linux; through calibration. Dropped by the user: LAN and the web interface, restoring the generator's settings.
