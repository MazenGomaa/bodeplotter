# Through calibration: design

Date: 2026-10-06. Status: **approved by the user on 2026-10-06** (design in conversation, then this file). Not built yet; the next step is the implementation plan. It is milestone A1 of the roadmap in `SPEC.md` sections 15 and 16.

## 1. Purpose

A sweep measures the DUT through two measurement paths (probe, scope input, channel). The paths are not identical: on the bench the same pair of probes gave a gain tilt of 0.1 to 0.2 dB up to 20 MHz, a channel delay of 0.08 to 0.15 ns, and both changed when the probes were moved to other channels (`HW_REPORT.md` 13.14, 13.19, 13.25).

A through calibration measures that difference once, with both probes on the same node, and divides it out of every later measurement. The skew check (`SPEC.md` 8.6) does the same for one quantity, the delay; the calibration covers gain and phase at every frequency.

Decisions taken by the user:

| Question | Decision |
|---|---|
| Relation to the skew check | Both exist. The quick skew check stays for everyday use; the calibration is an optional extra step. The app uses whichever is valid, the calibration first. |
| Validity | This connection only, like the skew check. Nothing is saved to disk. |
| Frequencies | Always the full range of the instruments, 10 points per decade (about 1 minute). Later sweeps are interpolated. |

Success criteria:

1. After a calibration, a through sweep reads 0 dB and 0° within the measurement noise (target on the bench: 0.02 dB, 0.1° up to 20 MHz with Sine fit).
2. A sweep without a calibration behaves exactly as it does today.
3. A corrected result says that it was corrected, in the table and in every export, and the raw measurement can be recovered from it.

## 2. What it does not do

- It does not correct gain differences between V/div steps (up to about 0.09 dB, `HW_REPORT.md` 13.12). A through sweep only uses the steps the full signal needs.
- It does not survive a reconnect, a resync or front-panel use.
- It is not a 50 Ω or S-parameter calibration. The Touchstone export keeps its warning.

## 3. Data

New dataclass in `models.py`:

```python
@dataclass
class ThroughCal:
    freqs_hz: list[float]        # ascending
    h: list[complex]             # raw Vdut / Vref at each frequency, NO skew correction applied
    checked_at: str              # ISO time
    alignment_epoch: int         # digitizer epoch when measured
    ref_channel: int
    dut_channel: int
    probe_atten: dict[int, float]
    coupling: str
    bw_limit: bool
    amp_vpp: float               # stimulus used, for the record
    warnings: list[str]
```

Derived values for display (computed, not stored): largest `|gain|` in dB, the delay fitted to the phase, the frequency range.

`PointResult` gets two fields, both default 0.0 so old results still load:

- `cal_gain_db`: gain removed by the calibration; raw gain = `gain_db + cal_gain_db`.
- `cal_phase_deg`: phase removed by the calibration; raw phase = `phase_deg + cal_phase_deg`.

New flag `Flag.CALIBRATED`, appended at the end of the enum. It is a quiet flag (it does not mark a point as suspect in the plot or the image export).

## 4. Measuring it

`sweep/core.py`, new function next to `run_skew_check`:

```python
def run_through_cal(session, stim, scope_cfg, meas, should_stop, sleep, on_log, on_progress) -> ThroughCal
```

- Frequencies: logarithmic, 10 per decade, from the highest of the two instruments' lower limits (not below 50 Hz) to the lowest of their upper limits (not above the scope's `max_hz`). On the UPO1054 and UTG932E that is 50 Hz to 20 MHz, 57 points.
- Method: Sine fit, single shot, the averages and settle times from the panel. Never Fast preview: its phase scatter would be built into every later result.
- No skew correction is applied to the stored values: the calibration contains the delay.
- It uses the same safety frame as a sweep and the skew check: `begin_measurement`, generator off and scope restored in a `finally`, the watchdog path on `InstrumentUnresponsive`, `measure_with_output` per point.
- In simulation the mock's "same node" switch is used, as the skew wizard does.
- It does not store the result. The caller does that with `Session.accept_cal`, after the user accepted.

Plausibility checks, added to `warnings`:

| Condition | Text | Effect |
|---|---|---|
| any `|gain|` above 1 dB, or the reference below 30 % of the stimulus setting | "This does not look like a through connection" | the dialog does not offer Accept |
| any point flagged `REF_SUSPECT`, `CLIPPED`, `BELOW_FLOOR` or `AUTORANGE_FAILED` | names the frequency and the flag | the dialog does not offer Accept |
| any `|gain|` above 0.3 dB | "Gain mismatch ... check probe compensation" (the skew check's wording) | warning only |
| aborted | no result | nothing to accept |

## 5. Validity

`Session` gets `cal: ThroughCal | None`, `accept_cal(cal)`, `invalidate_cal()` and:

```python
def cal_for(self, scope_cfg) -> ThroughCal | None
```

which returns the calibration only if all of these hold:

- its `alignment_epoch` equals the digitizer's (so a reconnect or a resync ends it);
- reference channel, DUT channel, both probe settings, coupling and bandwidth limit equal those of `scope_cfg`.

`front_panel_used()` and `mark_dead()` drop it, as they drop the skew check. A calibration that fails the epoch test is dropped; one that only fails the settings test is kept (the user may switch back) and simply not used.

Accepting a calibration does not create or change a skew check. The two are independent records.

## 6. Applying it

`sweep/calibration.py` (new, no Qt, pure functions):

```python
def response_at(cal, freq_hz) -> complex | None   # None outside [f_min, f_max]
def correct(h_meas, cal, freq_hz) -> tuple[complex, float, float] | None   # h, removed dB, removed deg
```

- Interpolation is in log frequency: gain in dB linearly, phase after unwrapping linearly. A frequency within 0.1 % of a calibration point uses that point.
- Outside the calibrated range (more than 0.1 % beyond the first or last point) there is no extrapolation: `None`.

`SweepRunner` decides once per sweep which correction applies (`Session.cal_for(scope_cfg)`, else the skew delay, else none) and logs it:

| State | Per point | Log line at the start |
|---|---|---|
| calibration valid and covers the frequency | `H = H_meas / H_cal(f)`; `cal_gain_db`, `cal_phase_deg` filled; `CALIBRATED` set; no skew correction | "Through calibration of HH:MM applied." |
| calibration valid, frequency outside its range | skew correction if a skew check is valid, else `SKEW_UNCHECKED` | one warning naming the range |
| no calibration, skew check valid | as today | as today |
| neither | as today (`SKEW_UNCHECKED`) | as today |

Fast preview uses the calibration in the same way. Its phase scatter remains.

Re-measuring a point uses the same rule as the sweep it belongs to at the time of the re-measure.

## 7. Engine and GUI

Engine (`sweep/engine.py`), mirroring the skew check:

- request `run_cal(cfg)`, result signal `cal_measured(ThroughCal)`, request `accept_cal(cal)`, and the existing `progress` signal during the run; abort works as for a sweep.
- `SessionInfo` gets `cal_valid: bool` and `cal_text: str` (for the current scope settings).

GUI:

- Toolbar and File menu: **Calibrate**, next to Skew check. Enabled when connected and idle.
- `CalDialog` in `gui/dialogs.py`, modelled on `SkewWizard`: the instruction (both probes on the generator output, same probe setting, about 1 minute), Start, a progress bar, Cancel; then the summary (range, number of points, largest gain deviation, delay found, warnings) with Accept, Measure again and Cancel. A "Discard calibration" button when one exists.
- Status bar, where the skew state is shown today: "cal: HH:MM, 50 Hz to 20 MHz" when a calibration applies to the current settings; otherwise the skew text as today.
- Starting a Sine fit sweep with a calibration that applies does not ask for a skew check. If the sweep range goes beyond the calibration and no skew check is valid, the existing question is asked, with one more sentence saying which part is not covered.
- The status table shows the `CALIBRATED` flag like the other flags.

## 8. Exports

- **CSV:** header lines `# cal: applied | none`, `# cal_checked_at`, `# cal_range_hz`, `# cal_points`, `# cal_max_gain_db`; two new columns at the end, `cal_gain_db` and `cal_phase_deg`. The loader accepts files without them (defaults 0.0).
- **Touchstone:** the same facts in `!` comment lines.
- **Image:** unchanged.
- The calibration itself is included in `SweepResult.meta["cal"]` (frequencies and complex values), so a saved result documents what was divided out.

## 9. Simulation and tests

Mock scope (`drivers/mock.py`): an optional frequency-dependent gain error on the DUT channel (`dut_gain_tilt_db_at_20mhz`, 0 by default, proportional to log frequency above 1 kHz), on top of the existing constant gain error and the skew delay. The simulated "same node" mode keeps both, so a calibration sees them.

Tests (no hardware):

- `calibration.response_at` and `correct`: exact at a point, interpolated between points, `None` outside, phase unwrapping across ±180°.
- Mock: tilt 0.2 dB and skew state +2.15 ns; a through sweep after calibration is within 0.02 dB and 0.1°; an RC low-pass matches theory within the tolerances the existing RC test uses, with the tilt present.
- Validity: reconnect, resync, front panel, changed channel, changed probe setting, changed coupling.
- Fallback: a sweep reaching beyond the calibrated range uses the skew check there and logs the warning.
- A calibration through a simulated RC filter (not a through) is refused.
- CSV round trip with and without calibration; old CSV files still load.
- Real drivers against `tests/fakes.py`: calibration then sweep, generator off and scope restored afterwards, no `:RUN`.
- GUI (offscreen): the Calibrate action, the dialog's accept path, the status text, no skew question when a calibration applies.

## 10. Bench acceptance

With the user at the bench, both probes on generator CH1:

1. Calibrate. Note the summary (largest gain deviation, delay).
2. Through sweep, full range, Sine fit: expect within 0.02 dB and 0.1°.
3. RC low-pass: compare with the model built from the capacitor's LCR readings (`HW_REPORT.md` 13.18).
4. Reconnect: the calibration must be gone.

Results go into `HW_REPORT.md` section 13.

## 11. Files touched

`models.py`, `sweep/calibration.py` (new), `sweep/core.py`, `sweep/engine.py`, `gui/main_window.py`, `gui/dialogs.py`, `gui/bode_plot.py` and `io/export_image.py` (quiet flag), `io/export_csv.py`, `io/export_touchstone.py`, `drivers/mock.py`, tests, `docs/SPEC.md` (sections 8.6, 12, 15), `README.md`.
