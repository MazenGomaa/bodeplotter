# Spec: roadmap, milestones and open hardware items (sections 15, 16, 17)

Part of the design spec. Overview and the index of all sections: `docs/SPEC.md`. Section numbers are kept, because the code cites them.

## 15. Roadmap

Rewritten 2026-10-06 from the user's roadmap update of that day, which sets the plan and the order. Facts about the hardware and the code come from this document, `HW_REPORT.md` and `CLAUDE.md`; where the update assumed something that is no longer true, it is said below.

v1 (Milestones 0 to 7, §16) is done and accepted on Windows. The phases below are done in this order. The milestones of each phase are in §16.

### Phase A. v2 (in progress; finish it on Windows)

- **Through calibration** (probe / channel calibration over frequency): sweep with both probes on the same node, store `H_cal(f)` for the connection, divide later measurements by it. **Design approved by the user on 2026-10-06:** `docs/superpowers/specs/2026-10-06-through-calibration-design.md`. Not built yet. The skew check of §8.6 stays as the quick everyday alternative.
- **Architecture items, to be scheduled early in v2:**
  - *Transport-agnostic drivers.* `open()` takes a connection spec (VISA resource + backend, or serial port + baud rate) in place of today's `open(resource, backend)`; each driver declares the transports it supports; the Connections dialog (and later the web settings) adapt to that. State of the code today: the real drivers already talk through a `Transport` interface with an injectable factory (`drivers/transport.py`), but `VisaTransport` is the only implementation and `open()` still takes a VISA resource string and a backend name.
  - *Skew state table as per-driver data.* The four states (−1.85, +0.15, +2.15, +4.15 ns) are constants in `measure/skew.py`; they belong to the UPO1000 driver. Note: since 2026-10-06 nothing is snapped to them any more (§8.6 step 6): they only name the state in the wizard and feed the "fits no known state" warning. The roadmap update still calls them "snapping states".
- **Trace overlay and compare:** several traces on the plot, load CSVs, show or hide traces, show the difference trace.
- **Auto markers:** −3 dB point(s), peak / notch, gain margin and phase margin read-out, user markers.

### Phase B. v3: filter recognition

- Classify the response as LPF / HPF / BPF / BSF / all-pass / unknown.
- Report:
  - Cutoff(s) at −3 dB relative to the passband.
  - Passband gain and ripple; stopband attenuation.
  - Centre frequency, bandwidth and Q (for BPF / BSF).
  - Roll-off slope in dB/decade → estimated order.
- Rational transfer-function fit (e.g. vector fitting / least squares on complex H): show the fitted curve and list poles and zeros.
- Confidence score; refuse to classify when there are too many flags, too narrow a span, or low SNR.
- Keep the fitting code reusable: the parked LCR mode (below) depends on it.

### Phase C. Windows full verification

After v3, hardware and communication are re-checked end to end on the real instruments, and reported in `HW_REPORT.md`:

- skew check;
- dual-channel capture;
- all exports;
- a known RC low-pass and an RLC band-pass against theory (the RC has been done once, `HW_REPORT.md` 13.18; an RLC band-pass has only ever been measured on the mock);
- per-point timing.

### Phase D. WSL (software only)

- The full pytest suite and the app in `--sim` mode on Linux.
- Fix what is OS-specific: paths, launchers, `run.sh`, fonts, platformdirs. (`run.sh` and `scripts/99-usbtmc-unit.rules` exist and have never been run.)
- Optional: one hardware smoke test through usbipd-win (`*IDN?` and one dual-channel capture), clearly labelled as NOT representative of native Linux because of the USB/IP forwarding.

### Phase E. Raspberry Pi (Pi Zero 2 W, Raspberry Pi OS Lite 64-bit)

- **E1. Pi hardware gate.** The Milestone 0 / 0b / 0c checks again, natively: USB through an OTG adapter and a powered hub; kernel `usbtmc` against pyvisa-py (udev rule / unbind / blacklist); the I/O layer test suite; dual-channel capture; skew states; timing; freeze and out-of-step behaviour. **Stop and report before E2.**
- **E2. Web frontend.** FastAPI + WebSocket in `web/` next to `gui/`, sharing `sweep/core.py`, the drivers and the math. Requirements: `docs/spec/web.md`.
- **E3. Pi deployment:** systemd service, start on boot, install script, README section.

### Candidate drivers (unscheduled; each needs its own hardware gate before use)

| Instrument | Kind | Link | Notes |
|---|---|---|---|
| R&S HMO1202 | scope | SCPI over USB-TMC | its USB mode must be switched from VCP to TMC |
| UNI-T UTD2052CL | scope | per the UTD2000CL programming manual | manual not in `docs/` yet |
| JDS6600 series | generator | serial, proprietary protocol | the `jds6600` Python package as reference; needs the serial transport of Phase A |
| tinySA Ultra | spectrum analyzer | serial | `ScalarReceiverMeter`, magnitude only, for work above 30 MHz (the app's own sweeps stop at 20 MHz today) |

### Parked features (`docs/feature.md`)

- **LCR / impedance analyzer mode:** parked, unscheduled; decision after v3. It depends on the v2 calibration and on the v3 fitting code, so both are to be kept reusable. (The user owns a UNI-T UT612 LCR meter, which can serve as the reference meter that file asks for.)
- **Curve tracer mode:** heavily deferred; it needs hardware that is not available yet. Mentioned only; no design work.

### Later, unscheduled

- PyInstaller builds.

**Design implications that still hold:**
- Keep `PointResult.h` complex and stored.
- Keep the CSV loader.
- Keep plotting able to handle several traces internally.

---

## 16. Milestones (implement in order)

0. **Hardware gate (BLOCKING): DONE 2026-10-05 on Windows 11, verdict GO WITH WORKAROUNDS (see `HW_REPORT.md`). Linux not tested. Milestone 1 still needs the user's explicit GO.** Scope: verify USB enumeration, VISA access, `*IDN?` model identity, basic SCPI read/write, a decoded waveform fetch from the scope, and generator → scope end-to-end operation on this machine and OS.
   - All scripts live in `hwcheck/`; results go to `HW_REPORT.md`.
   - Stop and wait for the user's explicit GO before Milestone 1. If either instrument can't be controlled reliably, the project does not proceed.
   - Commands verified here seed the driver `COMMANDS` tables as `verified=True`.
   - **0b: DONE 2026-10-05.** Scope commands re-verified against the UPO1000 manual; I/O layer `hwcheck/iolayer.py` written and tested (55 of 55 on `@py`); two-channel read-out from one acquisition proven. NI-VISA dropped in favour of pyvisa-py + WinUSB.
   - **0c: DONE 2026-10-05.** 10X probe test; discovery and fix of the channel alignment fault (§8.6, `HW_REPORT.md` §12.10 and §12.11).
   - Verdict after 0b and 0c: GO WITH WORKAROUNDS. The user gave GO on 2026-10-05.
   - **Milestones 1 to 5: DONE 2026-10-05 against the mock drivers.** Stopped for the user's review before Milestone 6. After the review (2026-10-06): Fit view and follow mode, k/M number entry and axes, File/View/Help menus, panels always shown at start-up, dark theme (`gui/theme.py`); `pytest`: 174 passed. Milestone 6 is not yet approved. Deviations from this document: the Qt-free sweep logic lives in `sweep/core.py` with `sweep/engine.py` as the QThread wrapper; `SPEC.md` is in `docs/`, not at the root; the auto-range clip step is 7 table steps so that a far-off start still converges in 3 retries.
1. **Skeleton:** repo layout, `pyproject.toml`, `requirements.txt`, launchers, `models.py`, logging.
2. **Core math:** sine fit, sweep plan, auto-range logic. Unit tests pass.
3. **Mock drivers + engine:** a full sweep runs headless against the mock RC/RLC DUTs. Sweep tests pass.
4. **GUI:** live plots, waveform view, status log, pause/resume/abort, re-measure, wrap/unwrap, sim mode.
5. **Persistence & export:** presets, settings, CSV (with loader), PNG/SVG/PDF, Touchstone.
6. **Real drivers + probe tool: DONE 2026-10-06** (user's GO of that day, with conditions). `drivers/uni_t_upo1000.py`, `drivers/uni_t_utg900e.py`, `drivers/transport.py`, `drivers/step_tables.py`, `drivers/connect.py`, `tools/probe.py`; every command cites its manual page and carries a verified flag. Tested against simulated SCPI instruments (`tests/fakes.py`), not yet run on the real instruments: that is Milestone 7, step 1. Bench checks done in this milestone with `hwcheck/` scripts: rail codes and division count, `:SYSTem:LOCK` (`HW_REPORT.md` 12.14). Stopped for the user's review before Milestone 7.
7. **Hardware bring-up (with the user): DONE 2026-10-06**, accepted by the user from the GUI (`HW_REPORT.md` section 13; 13.28 is the acceptance). Probe tool 63 of 63; the RC low-pass agrees with a model built from the capacitor's measured loss within 0.11° to 100 kHz; full range in about 115 s for 114 points (1.04 s per point), 53 s in Fast preview. What stays open is in section 17.
   1. Run the probe tool and fix the failing commands.
   2. Then measure a known RC LPF (e.g. 1 kΩ + 100 nF → fc ≈ 1.59 kHz) and compare with the mock and with theory.
   3. Then sweep the full 50 Hz–20 MHz range and record the per-point timing.

Each milestone ends with `pytest` green and a short note in `README.md` describing what works.

**After v1 (roadmap of §15; every milestone ends with `pytest` green, the notes updated and a commit):**

Phase A, v2, on Windows:

| Milestone | Content | Tests | Stop point |
|---|---|---|---|
| A1. Through calibration | as in `docs/superpowers/specs/2026-10-06-through-calibration-design.md`. **State 2026-10-06: design approved; next step is the implementation plan, then the build.** | spec §9: pure functions, mock with tilt and skew, validity rules, fallback, CSV round trip, fakes, GUI | bench acceptance with the user (spec §10), then the user's review |
| A2. Connection spec and per-driver data | `open(spec)` with VISA or serial; drivers declare their transports; Connections dialog adapts; skew state table moves into the UPO1000 driver | existing driver and GUI tests still pass; a serial transport runs against a loop-back fake; a driver without states gets no state warning | one through sweep and one skew check on the bench to show nothing changed |
| A3. Trace overlay and compare | several traces, load CSV, show / hide, difference trace | trace model, loader, difference on mismatched grids, GUI offscreen | user's review of the GUI |
| A4. Auto markers | −3 dB, peak / notch, gain and phase margin, user markers | marker math on the mock DUTs against theory; GUI offscreen | user's review; end of v2 |

Phase B, v3:

| Milestone | Content | Tests | Stop point |
|---|---|---|---|
| B1. Response metrics | passband level and ripple, cut-offs, stopband attenuation, slope and order, centre / bandwidth / Q, as pure functions | every simulated DUT against its theory, with noise and with flagged points | none |
| B2. Classification | LPF / HPF / BPF / BSF / all-pass / unknown, confidence score, refusal rules | each DUT type recognised; refusals for narrow span, low SNR, too many flags | user's review of the rules |
| B3. Rational fit | poles and zeros from complex H, fitted curve; written to be reused (LCR mode) | recovers the poles of the simulated DUTs within tolerance; stable on noisy data | none |
| B4. GUI and export | result panel, fit overlay, report in the exports | GUI offscreen; export round trip | user's review; end of v3 |

Phase C: one milestone, the list in §15, reported in `HW_REPORT.md`. Phase D: one milestone, plus the optional usbipd smoke test. Phase E: E1 (stop and report), E2, E3 as in §15.

The candidate drivers and the parked features of §15 are not milestones until the user schedules them.

---

## 17. Open items to verify on hardware

Resolved in Milestone 0 (details in `HW_REPORT.md`):
- Scope `*IDN?` is `UNI-T Technologies,UPO1054,<serial>,1. 01. 0047`; generator `*IDN?` is `UNI-T Technologies,UTG900E,<serial>,1.09`.
- Waveform data format, scaling, and number of screen points (700 over 14 divisions).
- Acquisition-complete detection: poll `:TRIGger:STATus?` for `STOP`. A guarded capture costs about 0.6 s (0.3 s guard plus about 0.22 s fetch).

Resolved in Milestones 0b and 0c (details in `HW_REPORT.md` §12):
- Two channels from one acquisition (CH1 + CH2), single-shot, about 0.77 s per capture.
- A stale `STOP` is read right after arming a single shot; the driver waits for a non-STOP status first.
- Real timebase and V/div step tables; 20 ns/div does not exist.
- 10X versus 1X probes, and the noise floor at 50 mVpp with 10X (SNR 21 to 28 dB).
- Cause of the intermittent CH1/CH2 phase offsets: `:RUN` after a session reopen (§8.6).
- Free backend (pyvisa-py + WinUSB) carries the whole I/O layer.

Resolved in Milestone 7 on the bench, 2026-10-06 (details in `HW_REPORT.md` §13; these supersede the matching "still open" lines below):
- The app's drivers, engine and GUI run on the real instruments: skew wizard, through sweeps within 0.05 dB and 0.3° to 20 MHz, RC low-pass correct down to −47 dB (13.5 to 13.13).
- CH3 / CH4 work as measurement channels; the delay of a channel pair depends on the pair and on the probes, so the skew check applies the measured value and never a table value (13.14, 13.25).
- Watchdog with the scope's USB cable pulled: generator off after 2.6 s, partial data kept; reconnect needs no power cycle (13.15).
- A power cycle clears a panel lock left on, and (one observation) puts the channel alignment back to its usual state (13.16, 13.25).
- A paced step-table walk ran once without a freeze; the tables equal the shipped ones (13.17).
- Real per-point time: 1.05 s single shot (0.77 s of it is the scope's own), 0.46 s in Fast preview (13.20, 13.23).
- `:MEASure:PHASe?` answers, on a stopped record only, with 0.36° resolution; not used (13.26).
- The one bad capture of 13.9 is probably a record read before the scope had finished it after a timebase change; the driver now checks the record's time span and acquires again (13.20, 13.22).

Still open after Milestone 7:
- What put the scope into the +2.15 ns alignment state on 2026-10-06 (13.25); the check of §8.6 handles the state, the trigger is unknown.
- What the running scope is busy with at 200 and 500 ns/div (about 3.4 s now and then, 13.24); Fast preview keeps off those two timebases, which removed the pauses (13.27). One report of a gain drop near the end of a Fast preview sweep was not reproduced.
- A scope that is frozen but still on USB (cannot be provoked); the generator is switched off at the first failed transfer of the resync, tested against the simulated transport only.
- Linux; through calibration (§15). LAN and the scope's web interface were dropped by the user on 2026-10-06.

Still open (list from before Milestone 7):
- **Channel alignment:** whether the front panel's Run/Stop or Single keys, a power cycle, Auto-set, a USB replug or vendor PC software also shift it; which state the scope powers up in; whether other channel pairs or other numbers of active channels behave the same; whether it happens over LAN. Until these are known the §8.6 check is the only safeguard.
- **Capture method: settled 2026-10-06, single shot.** Benchmark in `HW_REPORT.md` section 12.12: a free-running capture (sweep AUTO, `:STOP`, read both channels, restart with sweep SINGle then AUTO) took the same 0.8 s when it worked and failed every second capture. Cause found (`HW_REPORT.md` 12.13): a `:STOP` sent before the status has read `TRIGED` after a restart either does not last or stops the scope with no record (empty waveform block). With that rule the best free-running method takes 0.93 s per capture, still slower than single shot. Normal sweep could not be confirmed as set. Still open: shortening the 0.35 s two-channel read.
- CH3/CH4 as measurement channels on the UPO1054.
- (Resolved 2026-10-06: the screen grid has 8 vertical divisions; waveform codes stop at 1 and 254 and cover 10.1 divisions.)
- (Resolved 2026-10-06: `:SYSTem:LOCK ON` locks the front panel, read-back 1 = locked.) Still open: whether a power cycle clears a lock left on, and whether the lock also blocks the power key.
- At 500 µV/div with a 200-division overdrive the waveform data were wrong in a different way (codes 125 to 255, the clipped low half reading mid-scale). The rail rule still flagged it. Cause not examined.
- The app drivers have only run against simulated instruments. First real run: Milestone 7.
- A step-table walk froze the scope once (2026-10-06); whether the 250 ms pacing of `--walk-tables` avoids that is untested.
- The scope froze twice (0b, and 2026-10-06 during a step-table walk); cause unconfirmed; only a power cycle helped.
- Whether the permanently out-of-step state of Milestone 0 can recur (not reproduced in 0b), and whether the device-node restart works under WinUSB.
- A BNC-tee (probe-free) channel-match baseline; all two-channel tests used probes on the generator output.
- 1X probes below 1 Vpp, and any frequency between 1 MHz and 20 MHz.
- LAN resource string format and port for both instruments, if the UTG932E has LAN at all.
- UTG932E: amplitude limits per load, behaviour on frequency change (glitch, phase reset), whether settings persist across output toggles.
- Real per-point time across the range, to tune default settle and timeout values.
- Everything on Linux (udev rule, kernel `usbtmc` vs pyvisa-py).
