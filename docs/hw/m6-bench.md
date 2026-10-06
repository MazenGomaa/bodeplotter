# Hardware history: Milestone 6 bench checks, sections 12.12 to 12.14 (2026-10-06)

Part of the hardware report. The current facts and the index of all sections: `HW_REPORT.md`. This file is a dated record of what was run and seen; it is not rewritten when a later run changes the picture, so read the facts sheet first.

These are subsections of section 12, whose header is in `docs/hw/m0b-m0c.md`.

### 12.12 Capture-speed benchmark: single shot against free running (2026-10-06)

Script `hwcheck/s6_capbench.py`, raw data `hwcheck/results/s6_capbench_py.json`. Setup as in 12.10: both 10X probes on generator CH1, 1 Vpp sine, High-Z, backend `@py`. 20 captures per block, both channels read from one acquisition. Order: A, B, A. No `:RUN` was sent.

- **A, single shot:** `ScopeIO.acquire()` (`:TRIGger:SWEep SINGle`, poll for STOP, read both channels).
- **B, free running:** sweep AUTO running, wait `max(0.3 s, 30 x timebase)`, `:STOP`, poll for STOP, read both channels, restart with sweep SINGle then AUTO.

| Method | Frequency | Captures OK | Time per good capture | Time per capture incl. failures | CH2 - CH1 delay |
|---|---|---|---|---|---|
| A (first) | 1 kHz | 20/20 | 0.80 s | 0.80 s | n/a (noise at 1 kHz) |
| A (first) | 1 MHz | 20/20 | 0.78 s | 0.78 s | +0.01 ns, sd 0.11 |
| A (first) | 20 MHz | 20/20 | 0.83 s | 0.83 s | +0.147 ns, sd 0.013 |
| B | 1 kHz | 10/20 | 0.81 s | 3.46 s | n/a |
| B | 1 MHz | 10/20 | 0.81 s | 3.46 s | 0.00 ns, sd 0.15 |
| B | 20 MHz | 10/20 | 0.86 s | 3.48 s | +0.147 ns, sd 0.014 |
| A (second) | 1 kHz | 20/20 | 0.81 s | 0.81 s | n/a |
| A (second) | 1 MHz | 20/20 | 0.79 s | 0.79 s | +0.02 ns, sd 0.09 |
| A (second) | 20 MHz | 20/20 | 0.82 s | 0.82 s | +0.143 ns, sd 0.014 |

Findings:

1. **Free running is not faster.** When it works it costs 0.81 to 0.86 s per capture (0.30 s run wait, 0.13 s stop, 0.35 to 0.39 s read, 0.03 s restart), the same as single shot (0.40 to 0.42 s arm-to-stop, 0.35 to 0.36 s read).
2. **Free running is not reliable as written.** Every second capture failed in all three blocks (30 of 60) with the exact error `status did not reach STOP after :STOP (last TRIGED)`: after a restart by sweep SINGle then AUTO, the next `:STOP` did not stop the scope within 5 s. After the layer's resync the following capture worked, then the next failed again. The cause was not investigated further.
3. **The channel alignment did not move.** The 20 MHz delay stayed between +0.115 and +0.170 ns over all blocks, across 30 resyncs (each a session close, USB clear and reopen) with no `:RUN`. This agrees with 12.11.
4. About 0.35 s of every capture is the read of two channels (source select with read-back, preamble, data, each followed by the `*IDN?` sentinel). That is where time could be saved, not in the capture method. Not attempted.

**Decision: the app uses single-shot capture.** Budget 0.8 s per capture.
### 12.13 Why free-running capture failed, and a scope freeze (2026-10-06)

Script `hwcheck/dbg6_freerun.py`; raw data `hwcheck/results/dbg6_freerun_py_run1.json`, `_run2.json` (the same variants run twice; the second time by mistake, because a script edit had not been applied) and `dbg6_freerun_py.json` (run 3). Setup as in 12.12, 20 MHz, 8 cycles per variant. Each cycle: restart the stopped scope, send `:STOP`, poll `:TRIGger:STATus?`, read both channels if it stopped. No `:RUN` was sent.

| Restart after a `:STOP` | When `:STOP` was sent | Stopped on the first `:STOP` | Time per cycle |
|---|---|---|---|
| sweep SINGle, then AUTO | 0.3 s later (as in 12.12) | 1/8 and 0/8; the second `:STOP` always worked | n/a |
| sweep SINGle, then AUTO | 1.5 s later | 7/8 and 7/8 | 2.05 s |
| sweep SINGle, then AUTO | when status read TRIGED | 8/8 | 1.44 s |
| sweep AUTO only | when status read TRIGED | 8/8 | **0.93 s** |
| sweep NORMal, then AUTO | when status read TRIGED | 8/8 | 1.17 s |
| sweep SINGle, then NORMal | when status read TRIGED | 6/8 (one cycle never reached TRIGED, one needed a second `:STOP`) | 1.45 s |

**Cause.** A restart is not immediate. After "sweep SINGle, then AUTO" the status reads STOP, ARMED (0.04 s), AUTO (0.22 s), STOP (0.33 s: the single shot completes), ARMED (0.42 s), AUTO (0.62 s) and only then TRIGED (0.89 s). `:TRIGger:SWEep?` still answers `SINGle` at 0.3 s and `AUTO` only later: the scope carries out the single shot first and applies the change to AUTO afterwards. A `:STOP` sent at 0.3 s lands inside that sequence; the status reads STOP for about 0.09 s and then the pending restart runs anyway (ARMED, AUTO, TRIGED). That is the 12.12 failure `status did not reach STOP after :STOP (last TRIGED)`.

**A worse case of the same thing.** In runs 1 and 2 a variant sent `:STOP` 0.3 s after a restart whose sweep already read AUTO (status ARMED then AUTO, never TRIGED). The scope stopped and stayed stopped, but with no record: `:WAVeform:DATA?` answered `b'\r\n'` (2 bytes), 8 of 8 cycles in both runs. The layer's resync recovered all 16.

**Rule.** `:STOP` followed by a waveform read is only valid once `:TRIGger:STATus?` has read `TRIGED` since the last restart. The Milestone 0 rule "let it run max(0.3 s, 30 x timebase)" is not enough after a restart.

**Other observations.**
- `:TRIGger:SWEep AUTO` alone did restart a scope stopped by `:STOP` with the sweep already AUTO (8/8, TRIGED after 0.40 s). This contradicted a note in `t0b_iolayer.py` that it is a no-op; that note was an inference and has been corrected (see 12.14 C).
- After `:TRIGger:SWEep NORMal` the read-back was `AUTO` in 6 of 8 cycles and `SINGle` in 2: NORMal sweep was never confirmed as set. Not examined further.
- The CH2 - CH1 delay stayed at +0.12 to +0.17 ns in every cycle of all three runs.

**Speed.** The best free-running method costs 0.93 s per capture against 0.80 s for single shot. Each restart costs one arm cycle (about 0.4 s) whichever way it is done, and a single shot needs exactly one. **Single shot stays.**

**Scope freeze.** The first attempt to run this script failed during set-up, before any of the above: while `build_tables()` was stepping the timebase, `*OPC?` timed out, the resync reported success, and then every write failed with `[Errno 10060] Operation timed out`. The user confirmed the scope's screen was frozen. A USBTMC INITIATE_CLEAR was accepted with no effect, and `pnputil /restart-device` reported success with no effect; only a power cycle by the user brought it back. No installer was running at the time (user's statement). Cause unknown. This is the second freeze during a step-table walk or setting sequence (the first was in 0b, 12.7). The script now uses the step tables measured in 0b instead of walking them.
### 12.14 Milestone 6 bench checks: rail codes, division count, front-panel lock (2026-10-06)

All scripts now print their own file hash and git commit at start, and a commit was made before each run.

**A. Overdrive** (`hwcheck/s6_overdrive.py`, `results/s6_overdrive_py.json`). Both 10X probes on generator CH1, 1 kHz sine, 1 Vpp, i.e. 0.1 Vpp at each scope input. CH1 stayed at 20 mV/div; CH2 was overdriven by V/div and, separately, pushed off the top and bottom with its offset. 3 single shots per case, 66 captures, no errors.

| CH2 case | Signal on CH2 | Lowest code | Highest code | Samples on the lowest / highest code |
|---|---|---|---|---|
| 20 mV/div (reference) | 5 div p-p | 67 | 192 | not clipped |
| 10 mV/div | 10 div p-p | 6 | 252 to 253 | not clipped |
| 5 mV/div | 20 div p-p | **1** | **254** | 222 / 238 of 700 |
| 2 mV/div | 50 div p-p | 1 | 254 | 294 / 308 |
| 1 mV/div | 100 div p-p | 1 | 254 | 322 / 336 |
| 500 uV/div | 200 div p-p | 125 | 255 | 336 / 6 to 8 (see finding 4) |
| 20 mV/div, offset +3 to +6 div | pushed off the top | - | 254 | 139 to 440 |
| 20 mV/div, offset +8 div | entirely above | 254 | 254 | 700 |
| 20 mV/div, offset -3 to -6 div | pushed off the bottom | 1 | - | 105 to 420 |
| 20 mV/div, offset -8 div | entirely below | 1 | 1 | 700 |

Findings:

1. **The rail codes are 1 and 254**, not 0 and 255. The rule used until now ("code <= 0 or >= 255") flagged none of the clipped captures above except the 500 uV/div one. Clip detection is now "any code <= 1 or >= 254".
2. **The waveform data cover 253 codes = 10.1 divisions**, 5.06 above and below the centre code 128. The screen grid has **8 vertical divisions** (the user counted them). So a signal can be up to about 1 division off screen at each edge and still be read correctly: at 10 mV/div the 10-division signal read codes 6 to 253, unclipped. Auto-range keeps aiming at the 8 screen divisions; the rest is headroom.
3. **Overdriving CH2 does not disturb CH1.** CH1 read codes 68 to 192 or 193 (span 124 or 125) in every case.
4. **At 500 uV/div with a 200-division overdrive the data are wrong in a different way**: the clipped low half reads code 125 (mid-scale) instead of 1, and a few samples read 255. The rail rule still flags the capture (255 >= 254). Cause not examined.
5. The share of samples on the rails gives the true amplitude of a clipped sine: 20, 50 and 100 divisions p-p were estimated as 19.7, 46 and 108. Auto-range now uses this to reach the right V/div in one jump.
6. The vertical offset moves the trace by exactly offset / (V/div / 25) codes, and the preamble's YOR field reports it.

**B. `:SYSTem:LOCK`** (`hwcheck/s6_lock.py`, `results/s6_lock_*_py.json`; U1K p.6).

| Step | `:SYSTem:LOCK?` | Front panel (user's observation) | Remote control |
|---|---|---|---|
| before | `0` | normal | works |
| after `:SYSTem:LOCK ON`, USB session closed | `1` | **no reaction to keys or knobs** | queries and a set-and-restore work |
| after `:SYSTem:LOCK OFF` | `0` | **keys work again** | works |

- **`1` means locked.** The manual's "Return format" sentence ("0 represents locked, 1 represents unlock") is wrong; its example ("Query returns 1, it represents locked") is right.
- The lock **survives a closed USB session**, so software that sets it must release it. The app does so after every measurement and on disconnect, and the probe tool has `--unlock`.
- Not tested: whether a power cycle clears a lock that was left on, and whether the power key is locked too.

**C. Reconciliation with the layer's test suite.** `t0b_iolayer.py` said that sweep AUTO written to a scope stopped by `:STOP` "is a no-op". That was an inference from a forcing test, not an observation. 12.13 watched the status: sweep AUTO alone restarts such a scope (8 of 8). The note in the test suite is corrected; the SINGle-then-AUTO restart is kept there because the forcing rounds are reliable with it (55 of 55).

**D. Incident.** While the app's real drivers were being written, one automated test opened a real connection: it found both instruments over USB, identified them and (as far as can be told) began the driver's connect sequence before the test ended and disconnected. No output was switched on (the generator driver forces both outputs off when it opens). A read-only check afterwards (`hwcheck/s6_state.py`) showed both generator outputs OFF, the scope unlocked, sweep AUTO, error queue empty. The test suite now sets `BODEPLOT_NO_HARDWARE`, which makes every VISA open raise, so no test can reach an instrument.

**What Milestone 6 did not do:** the app's own drivers and the probe tool have run only against simulated instruments. Their first run on the real scope and generator is Milestone 7, step 1.
