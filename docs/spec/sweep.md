# Spec: data models, sweep algorithm, errors and tests (sections 7, 8, 13, 14)

Part of the design spec. Overview and the index of all sections: `docs/SPEC.md`. Section numbers are kept, because the code cites them.
Section 8.6 (channel skew) and 8.7 (through calibration) are in `docs/spec/skew.md`.

## 7. Data models (`models.py`)

```python
class SweepType(Enum): LOG, LINEAR
class Method(Enum): SINEFIT, BUILTIN

@dataclass
class SweepConfig:
    sweep_type: SweepType
    start_hz: float
    stop_hz: float
    points_per_decade: int      # LOG
    n_points: int               # LINEAR
    descending: bool = False

@dataclass
class StimulusConfig:
    gen_channel: int = 1
    amp_vpp: float = 1.0
    offset_v: float = 0.0
    load: str = "HIGHZ"

@dataclass
class ScopeConfig:
    ref_channel: int = 1
    dut_channel: int = 2
    probe_atten: dict[int, float]   # {1: 10.0, 2: 10.0}
    coupling: str = "DC"            # "DC" | "AC"
    bw_limit: bool = False
    target_cycles: float = 5.0
    min_samples_per_cycle: int = 20

@dataclass
class MeasureSettings:
    method: Method = Method.SINEFIT
    averages: int = 1
    settle_ms: float = 50.0
    settle_cycles: float = 3.0      # settle = max(settle_ms, settle_cycles/f)
    autorange_target: tuple[float, float] = (0.6, 0.8)   # fraction of full scale (p-p)
    autorange_max_retries: int = 3
    floor_fraction: float = 0.1     # below this at min V/div → BELOW_FLOOR
    acquire_timeout_s: float = 5.0

class Flag(Flag): CLIPPED, BELOW_FLOOR, AUTORANGE_FAILED, LOW_SNR, REMEASURED, BUILTIN, SKEW_UNCHECKED

@dataclass
class PointResult:
    freq_hz: float
    h: complex                  # Vdut / Vref (phasor ratio)
    gain_db: float
    phase_deg: float            # wrapped (-180, 180]
    vref_amp: float             # volts peak
    vdut_amp: float
    vdiv_ref: float
    vdiv_dut: float
    timebase: float
    n_avg: int
    snr_ref_db: float | None
    snr_dut_db: float | None
    flags: Flag
    duration_s: float
    skew_corr_deg: float = 0.0  # phase removed by the skew correction (§8.6); raw = phase_deg + this

@dataclass
class SkewCheck:                # result of the §8.6 wizard
    delay_s: float              # Δt applied (snapped state, or the measured value)
    measured_s: float
    snapped: bool
    gain_db: float              # gain mismatch DUT/ref
    freqs_hz: list[float]
    per_freq_delay_s: list[float]
    per_freq_gain_db: list[float]
    warnings: list[str]
    checked_at: str             # ISO time
    alignment_epoch: int        # digitizer epoch when checked

@dataclass
class SweepResult:
    config: dict                # full snapshot of all configs
    points: list[PointResult]   # sorted by frequency
    meta: dict                  # app version, timestamps, instrument IDNs, aborted flag,
                                # channel delay τ + check frequency/time, or "not checked" (§8.6)
```

---

## 8. Sweep algorithm

### 8.1 Frequency plan (`sweep/plan.py`)
- **LOG:** `n = ceil(decades × points_per_decade) + 1` points, geometrically spaced, start and stop included.
- **LINEAR:** `n_points` points, evenly spaced.
- Validate against `SourceCaps` and `MeterCaps`:
  - Out of range → error in the GUI before starting.
  - Above 40% of scope bandwidth → non-blocking warning: single-channel amplitudes are attenuated, but ratios remain valid.

### 8.2 Sweep start
1. Connect both instruments if not already connected.
2. Generator: `configure_sine` with the stimulus config at the first frequency, then output ON.
3. Scope:
   - `configure_channel` for both channels.
   - Edge trigger on the reference channel, level 0 V. With DC coupling and an offset, trigger at the offset. Trigger level and channel offset are quantised to V/div / 25, so read-back comparison needs that tolerance.
   - Initial V/div from a quick coarse acquisition: start at a large V/div and step down.
4. **Channel skew** (§8.6): the sweep uses the Δt of the current session's skew check. With no valid check the app asks for one first; if declined, the sweep runs uncorrected and flags every point `SKEW_UNCHECKED`.

### 8.3 Per point
1. `set_frequency`. Wait `max(settle_ms, settle_cycles / f)`.
2. **Timebase:**
   - Choose the smallest timebase step such that `horizontal_divs × s_per_div ≥ target_cycles / f` (`horizontal_divs` is 14 on the UPO1054, and a record is 700 points).
   - Only steps from the scope's real table are requested (§9.2). The table is not a pure 1-2-5 sequence: it has 25 ns, not 20 ns.
   - Read the timebase back and use the value the scope reports.
   - Also check `min_samples_per_cycle`, given the sample rate the scope reports.
   - At 20 MHz with 1 GSa/s that is 50 samples/cycle, which is fine.
3. **Auto-range** (`sweep/autorange.py`), both channels independently:
   1. Start from the previous point's V/div.
   2. Acquire. For each channel compute peak-to-peak as a fraction of full scale (`vertical_divs × vdiv`). Work on the voltage at the scope input (tip voltage ÷ probe ratio). Full scale is the 8 divisions of the screen grid (confirmed on the UPO1054, 2026-10-06); the waveform data reach further, to 10.1 divisions, which is headroom. 1 Vpp through a 10X probe selects 20 mV/div and 50 mVpp selects 1 mV/div.
   3. If above the target max, or below the target min: jump directly to the step predicted by the measured amplitude; don't step one at a time. If clipped (any sample on a rail code): estimate the amplitude from the share of samples on the rails (a centred sine clipped at ±R divisions spends `p = 1 − (2/π)·asin(R/A)` of its time there, so `A = R / cos(pπ/2)`), add 25%, and jump to the step that predicts, at least one step up. When no estimate is possible (95% or more of the samples on a rail, or the digitizer does not report the share) go up 7 steps. Hysteresis: a step that is just over the target max, with the signal still on screen, is kept when the next step would fall below the target min (without it a noisy p-p flipped between two steps on the bench).
   4. Repeat up to `autorange_max_retries`. On failure, set `AUTORANGE_FAILED` and use the last non-clipped capture if one exists.
   5. If at the most sensitive V/div the signal is still below `floor_fraction`, set `BELOW_FLOOR` and keep the measurement.
   6. Each V/div change is followed by a short settle (default 20 ms, configurable).
4. **Measure** `averages` times, with a fresh acquisition each time. Each acquisition is one single shot from which both channels are read (§9.2); it costs about 0.77 s on the UPO1054.
   - **SINEFIT:** fit both channels at the known generator frequency (§8.4). `H_i = A_dut·e^{jφ_dut} / (A_ref·e^{jφ_ref})`. Then apply the skew correction of §8.6: `H_i ← H_i·e^{−j·2π·f·Δt}`.
   - **BUILTIN:** read the scope's amplitude for both channels and the phase measurement ref→dut. Construct H from those. Set the `BUILTIN` flag.
   - **PREVIEW** ("Fast preview", added 2026-10-06 on the user's request): the same sine fit, but the two channels are read one after the other from the scope while it keeps triggering (sweep AUTO, no single shot, no stop; `Digitizer.acquire_running`). About 0.21 s per capture in place of 0.93 s; a 114-point sweep took 53 s in place of about 115 s. The gain is as accurate as SINEFIT. The phase is rough, because the two channels are different acquisitions: sd 0.4° to 100 kHz, 0.6° to 1 MHz, 0.8° to 5 MHz, 3.6° above (HW_REPORT 13.21, 13.23). Every point carries the `PREVIEW` flag; no skew check is asked for and `SKEW_UNCHECKED` is not set. An empty `:WAVeform:DATA?` reply is never retried in place: resync, then a new read.
   - Average H as the **complex mean** across captures.
5. `gain_db = 20·log10(|H|)`, `phase_deg = angle(H)` in degrees, wrapped to (-180, 180].
6. Emit `point_measured` and `waveform_captured` (last capture).
7. Check pause/abort flags between points **and** between retries/averages.

### 8.4 Sine fit (`measure/sinefit.py`)
- 3-parameter least squares at known frequency f: `v(t) = a·cos(2πft) + b·sin(2πft) + c`.
- Amplitude `= hypot(a, b)`, phase `= atan2(-b, a)`. Both channels share the same time base, so phase differences are exact.
- Residual RMS → SNR estimate in dB. If SNR < 20 dB (configurable), set `LOW_SNR`.
- Optional 4-parameter refinement (frequency as a free parameter) when residuals are high. Off by default. Never take the starting frequency from zero crossings: in Milestone 0c that locked onto 1926 Hz for a 1 kHz, 5 mVpp input in 1 of 20 captures. Start from the generator frequency.
- Use the scope-reported `dt`. Never assume it.
- Must tolerate non-integer cycle counts and DC offset.

### 8.5 Pause / resume / abort / re-measure
- **Pause:** finish the current acquisition, then wait. The generator stays on.
- **Abort:**
  - Stop after the current acquisition.
  - Generator `safe_off()`.
  - Emit `finished` with the partial result and `meta.aborted = True`.
- **Re-measure point:** the user clicks a plotted point (when not running) → context menu "Re-measure":
  - Run a single-point measurement at that frequency, using the full per-point procedure.
  - Replace the point and add the `REMEASURED` flag.
  - Generator on for the duration, off afterwards.
- `safe_off()` is called in a `finally` block on every exit path: done, abort, exception, app close.

---

## 13. Errors, safety, logging

- Every instrument error is caught at the engine level:
  - Generator `safe_off()`.
  - Emit `error` with a human-readable message plus the last command sent.
  - State → `ERROR`. Partial results are kept and exportable.
- **Watchdog.** If an instrument stops answering and the resync of §9.1 fails (`InstrumentUnresponsive`): generator `safe_off()`, the sweep stops, the points measured so far are kept, the user is told to power-cycle the scope and reconnect, and the engine closes the connection. Further calls to the dead driver fail at once without I/O. Nothing that needs elevation is tried.
- The test suite sets `BODEPLOT_NO_HARDWARE`, which makes every VISA open raise: no test can reach a real instrument.
- Timeouts are configurable per instrument.
- An acquisition timeout counts as one retry, not a crash.
- Logging uses Python `logging`, written to `user_log_dir("bodeplot")/bodeplot.log` (rotating, 5 × 2 MB). `--debug` logs every SCPI command and response.
- Linux USB permission errors show the udev hint (§5).

---

## 14. Testing (`tests/`)

All tests run against mock drivers, with no hardware and no display needed. Use `pytest-qt`, or test the engine without the GUI.

| Area | Test | Pass criteria |
|---|---|---|
| Sine fit | Clean synthetic sines, random phase/amplitude/offset, non-integer cycles | amplitude error < 0.1%, phase error < 0.1° |
| Sine fit | Noise at 30 dB SNR | phase error < 1°, SNR estimate within 3 dB |
| Plan | Log and linear generation, endpoints, validation errors | exact |
| Auto-range | Signals from 1 mV to 20 V | converges in ≤ 3 retries; clip handled |
| Sweep | Mock RC LPF, fc = 1.59 kHz, 50 Hz–20 MHz, 20 pts/dec | −3 dB within 2% of fc; phase at fc = −45° ± 1° |
| Sweep | Mock RLC BPF | peak frequency within 2%, Q within 5% |
| Control | Pause/resume/abort mid-sweep | partial result kept; `safe_off` called |
| Exports | CSV write → read round trip | identical within float tolerance |
| Exports | Touchstone and image files | valid; files created |
| Presets | Save/load; old schema with missing keys | loads with defaults |
| Skew | Mock forced into each of the four skew states; wizard measures and snaps | snapped Δt equals the injected state |
| Skew | Sweep of a through connection with each injected state, correction on | corrected phase within 0.5° of 0° at 20 MHz |
| Skew | Off-grid delay (e.g. +1.0 ns) and a 0.5 dB gain mismatch | not snapped, measured value used, both warnings raised |
| Skew | Simulated resync / reconnect / "front panel used" | check invalidated, re-check requested |
| Skew | Sweep without a check | every point flagged `SKEW_UNCHECKED`; CSV and Touchstone say "not checked" |
