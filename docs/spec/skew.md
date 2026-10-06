# Spec: channel skew check and channel calibration (sections 8.6 and 8.7)

Part of the design spec. Overview and the index of all sections: `docs/SPEC.md`. Section numbers are kept, because the code cites them.
The rest of section 8 is in `docs/spec/sweep.md`.

### 8.6 Channel skew check and correction (required in v1)

This replaces the plain "same-node check" of the first draft of this section. Code: `measure/skew.py`, wizard in `gui/dialogs.py`, engine support in `sweep/engine.py`.

**Why.** On the UPO1054 the two channels can sit a whole number of samples apart in time, and stay that way. Measured in Milestone 0c: the DUT-minus-reference delay takes values 2.000 ns apart (about +0.15, +2.15, +4.15 and −1.85 ns for CH2 − CH1), which is 0.0007° per step at 1 kHz, 0.72° at 1 MHz and 14.4° at 20 MHz. The value is steady within a state (about 0.1° at 20 MHz). The known trigger is a `:RUN` command after the USB session has been reopened, which the driver never sends (§9.2), but other triggers (front-panel Run/Stop, power cycle, replug) and the power-on state are untested, and no documented command puts a shifted scope back. A sweep therefore cannot assume alignment. Details: `HW_REPORT.md` §12.11.

**Definition.** Δt is the DUT-channel-minus-reference-channel delay: with both probes on one node, `Δt = phase(H) / (360°·f)` where `H = V_dut / V_ref`. On the bench this was CH2 − CH1.

**Wizard** (toolbar button "Skew check"; also offered when a sweep is started with no valid check):
1. Tell the user to put the reference probe and the DUT probe on the same node (the generator output), same probe setting on both. Wait for confirmation.
2. Generator: sine, the stimulus amplitude and load from the current config, output on.
3. Measure at two frequencies: 10 MHz and 20 MHz. If the generator or the scope cannot reach 20 MHz, use the top usable frequency `f_top` and `f_top / 2`. The sweep range does not lower these frequencies (changed in Milestone 7: a check at 0.5 and 1 MHz could not resolve the delay, since 0.3 ns is 0.1° at 1 MHz). At each: 3 single-shot two-channel captures, fit both channels at that frequency, complex-average H, then `Δt_i = phase(H) / (360°·f_i)` and `gain_i = 20·log10|H|`.
4. Output off (in a `finally`).
5. `Δt_measured` = mean of the two `Δt_i`. If the two differ by more than 0.3 ns, warn (the offset is then not a pure delay).
6. **Δt applied is `Δt_measured`, always** (user decision 2026-10-06, replacing the snap below). The delay of a state depends on which probe sits on which channel (the same CH1 / CH2 pair read +0.15 ns and later +0.08 ns in one evening, HW_REPORT 13.25), so a fixed table over-corrects. The known states −1.85, +0.15, +2.15, +4.15 ns are only used to name the state in the wizard and to warn when `Δt_measured` is more than 0.3 ns from all of them. *Superseded text:* snap to the known states: if `Δt_measured` is within 0.3 ns of one, Δt is that state's value. Otherwise warn and use `Δt_measured` unchanged. The states belong to reference = CH1, DUT = CH2 only; with any other pair or order `Δt_measured` is used unchanged and without a warning (user decision 2026-10-06: CH3 / CH4 measured +0.08 ns on the bench and the snap to +0.15 ns left −0.39° at 20 MHz, HW_REPORT 13.14).
7. **Gain mismatch** = mean of the two `gain_i`, always reported; warn if its magnitude exceeds 0.3 dB (probe compensation or a bad connection).
8. Show: Δt applied, Δt measured, snapped or not, the two per-frequency values, gain mismatch, warnings. The user accepts or repeats.

**Correction.** For every measured point: `phase_corr = phase − 360°·f·Δt`, wrapped to (−180°, 180°]. Equivalently `H_corr = H·e^{−j·2π·f·Δt}`; the stored `PointResult.h` is the corrected one, and `PointResult.skew_corr_deg` keeps the amount removed so the raw phase can be recovered. Gain is not corrected in v1; the frequency-dependent calibration of §15 stays in v2.

**Validity: once per session.** A check belongs to one connection. The app marks the check as needed (red "UNCHECKED" in the status bar and a line in the status log; no pop-up, user decision 2026-10-06, the pop-up on every connect was a nuisance):
- after connect or reconnect,
- after any driver resync (the digitizer driver exposes an `alignment_epoch` counter that it increments on connect and on every resync; the engine compares it with the value stored at the check),
- when the user says the front panel was used (toolbar action "Front panel was used").
A sweep started without a valid check asks first (this is the only pop-up; Fast preview does not ask); if the user declines, the sweep runs uncorrected and every point carries the `SKEW_UNCHECKED` flag.

**Records.** Δt applied, Δt measured, snapped flag, gain mismatch, check frequencies and the check time go into `SweepResult.meta["skew"]`, into the CSV `# key: value` header, and into the Touchstone `!` comment lines. With no check, those say so.

**Mock.** `MockScope` picks a random skew state (one of the four values above) at every open and at every simulated resync, applies it to the DUT channel, and exposes a way to force a state. This is what makes the path testable without hardware (§9.5, §14).

**Optional tool, not used by the app:** `hwcheck/s0c_realign.py` re-rolls the scope until it is aligned by deliberately using the fault (reopen session, `:RUN`). It stays in `hwcheck/` for bench use only. The app never sends `:RUN`.

**Limits.** One 2 ns step is 14.4° at 20 MHz and 7.2° at 10 MHz against a measurement spread of about 0.1°, so the states are easy to tell apart there; below about 1 MHz a step is under 0.7° and the check loses its meaning. The check also folds in any real difference between the two probes at the check frequencies.


### 8.7 Through calibration (v2)

Design: `docs/superpowers/specs/2026-10-06-through-calibration-design.md`. Code: `sweep/calibration.py` (pure functions), `core.run_through_cal`, `Session.cal_for`, `CalDialog` in `gui/dialogs.py`.

**What it is.** With both probes on one node the app measures `H_cal(f) = V_dut / V_ref` over the full range of the instruments and divides every later measurement by it: `H = H_meas / H_cal(f)`. That removes the gain and phase difference between the two measurement paths (probe, scope input, channel), which the skew check does only for the delay. Both exist; the skew check stays the quick everyday step.

**Measuring.** Toolbar and File menu "Calibrate". Logarithmic, 10 points per decade, from the higher of the two instruments' lower limits (not below 50 Hz) to the lowest of the generator's upper limit, the scope's `max_hz` and 40 % of the scope bandwidth: 50 Hz to 20 MHz, 58 points, on the UPO1054 with the UTG932E. Always Sine fit on single shots, with the averages and settle times of the panel; never Fast preview. No skew correction is applied to the stored values: the calibration holds the delay. Same safety frame as a sweep.

**Plausibility.** Not accepted: any gain beyond ±1 dB, a reference below 30 % of the stimulus setting ("This does not look like a through connection"), any point flagged `REF_SUSPECT`, `CLIPPED`, `BELOW_FLOOR` or `AUTORANGE_FAILED`, a resync during the run. Warning only: a gain beyond ±0.3 dB.

**Validity.** This connection only; nothing is saved to disk. A reconnect, a resync (the digitizer's `alignment_epoch`), "Front panel was used" and a lost connection drop it. It is used only for sweeps with the same reference channel, DUT channel, probe settings, coupling and bandwidth limit; with other settings it is kept and not used. Accepting a calibration does not create or change a skew check.

**Applying.** Decided once per sweep: the calibration where it covers the frequency (point flagged `CALIBRATED`, `cal_gain_db` and `cal_phase_deg` hold what was removed, no skew correction), the skew correction outside its range if a skew check is valid, else `SKEW_UNCHECKED`. No extrapolation. Between two calibration points the gain in dB is linear in log frequency; for the phase one delay is fitted to the whole calibration, the remainder is interpolated in log frequency and the delay is added back exactly (a delay is linear in frequency, and a straight line over log f would miss it by 0.09° near 18 MHz in the +2.15 ns state). Fast preview and re-measure use the same rule.

**It does not** correct the gain differences between V/div steps (up to about 0.09 dB, HW_REPORT 13.12), and it is not a 50 Ω or S-parameter calibration.

**Mock.** `MockScope.dut_gain_tilt_db_at_20mhz` adds a gain error of the DUT channel that grows with log frequency above 1 kHz; the simulated "same node" mode keeps it and the skew.
