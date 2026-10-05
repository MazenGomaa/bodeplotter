# Bode Plotter — Design & Implementation Spec

PC software that drives a function generator and an oscilloscope to measure the frequency response (gain + phase) of a device under test (DUT) and present it as a Bode plot.

This document is the single source of truth for Claude Code. Read it fully before writing code, then follow the milestones in §16 in order.

---

## 1. Goals and non-goals

**Goals (v1)**
- Measure gain (dB) and phase (°) from **50 Hz to 20 MHz** using:
  - Scope: **UNI-T UPO1054** (4-channel, 50 MHz, UPO1000 family). Confirmed by `*IDN?` and nameplate in Milestone 0; earlier drafts of this spec said UPO1052.
  - Generator: **UNI-T UTG932E** (2-channel, sine up to 30 MHz, UTG900E family). Its `*IDN?` reports only the family name `UTG900E`.
- Python desktop GUI with a live-updating Bode plot.
- Runs on **Windows and Linux**.
- Connects over **USB (USBTMC) or LAN**, configured per instrument.
- Pluggable driver architecture, so the app is **not locked to these two models**.
- Full **simulation mode** (mock instruments + simulated DUT) so everything except the real drivers can be built and tested without hardware.

**Non-goals (v1)**
- Full probe/channel calibration over frequency, trace overlay, auto markers (v2, §15). The single-frequency **channel alignment check** of §8.6 is NOT deferred: it is required in v1.
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

```
bodeplot/
├── SPEC.md
├── README.md
├── requirements.txt
├── pyproject.toml
├── run.bat
├── run.sh
├── docs/                       # manuals (user-provided)
├── scripts/
│   └── 99-usbtmc-unit.rules    # Linux udev rule example
├── src/bodeplot/
│   ├── __main__.py             # entry: python -m bodeplot [--sim] [--debug]
│   ├── app.py                  # QApplication bootstrap
│   ├── models.py               # dataclasses: configs, results, flags
│   ├── sweep/
│   │   ├── plan.py             # frequency list generation
│   │   ├── engine.py           # SweepEngine (QThread worker)
│   │   └── autorange.py        # V/div + timebase selection
│   ├── measure/
│   │   ├── sinefit.py          # 3-param (and optional 4-param) sine fit
│   │   ├── skew.py             # channel skew check, snapping and phase correction (§8.6)
│   │   ├── meters.py           # ResponseMeter implementations
│   │   └── builtin.py          # scope built-in measurement mode
│   ├── drivers/
│   │   ├── base.py             # abstract interfaces + capability dataclasses
│   │   ├── registry.py         # model → driver class mapping, IDN matching
│   │   ├── visa_util.py        # resource open, backend select, discovery
│   │   ├── uni_t_upo1000.py    # UPO1054 / UPO1000 family driver
│   │   ├── uni_t_utg900e.py    # UTG932E / UTG900E family driver
│   │   └── mock.py             # MockSource, MockScope, SimulatedDUT
│   ├── io/
│   │   ├── presets.py          # JSON presets
│   │   ├── settings.py         # app settings (connections, backend)
│   │   ├── export_csv.py
│   │   ├── export_image.py
│   │   └── export_touchstone.py
│   ├── gui/
│   │   ├── main_window.py
│   │   ├── config_panel.py
│   │   ├── bode_plot.py
│   │   ├── waveform_view.py
│   │   ├── status_log.py
│   │   └── dialogs.py          # connection/settings, presets, export
│   └── tools/
│       └── probe.py            # instrument probe/verification utility
└── tests/
```

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

---

## 6. Architecture

```
GUI (main thread)
  │  signals/slots
  ▼
SweepEngine (QThread worker) ── owns all instrument I/O
  ├── SignalSource      (drivers/base.py)
  └── ResponseMeter     (measure/meters.py)
        └── uses Digitizer (scope driver)
```

- **All instrument I/O happens in the worker thread.** The GUI never touches a VISA resource directly.
- The engine emits Qt signals:
  - `point_measured(PointResult)`
  - `waveform_captured(WaveformPair)`
  - `log(LogEntry)`
  - `progress(i, n)`
  - `state_changed(EngineState)`
  - `finished(SweepResult)`
  - `error(str)`
- `EngineState`: `IDLE`, `CONNECTING`, `RUNNING`, `PAUSED`, `ABORTING`, `DONE`, `ERROR`.

### 6.1 Driver interfaces (`drivers/base.py`)

Capabilities are declared, never assumed. The GUI and engine adapt to them.

```python
@dataclass(frozen=True)
class SourceCaps:
    model: str
    channels: int
    sine_min_hz: float
    sine_max_hz: float
    amp_min_vpp: float          # into the selected load
    amp_max_vpp: float
    loads: tuple[str, ...]      # e.g. ("HIGHZ", "50")

class SignalSource(ABC):
    caps: SourceCaps
    def open(self, resource: str, backend: str) -> None: ...
    def close(self) -> None: ...
    def idn(self) -> str: ...
    def configure_sine(self, ch: int, freq_hz: float, amp_vpp: float,
                       offset_v: float, load: str) -> None: ...
    def set_frequency(self, ch: int, freq_hz: float) -> None: ...
    def set_output(self, ch: int, on: bool) -> None: ...
    def safe_off(self) -> None: ...   # all outputs off, never raises

@dataclass(frozen=True)
class DigitizerCaps:
    model: str
    channels: int
    bandwidth_hz: float
    max_sample_rate: float
    vdiv_steps: tuple[float, ...]       # volts/div at 1x probe
    timebase_steps: tuple[float, ...]   # s/div
    vertical_divs: float                # full-scale divisions on screen
    horizontal_divs: float
    has_builtin_amplitude: bool
    has_builtin_phase: bool

@dataclass
class Waveform:
    dt: float                 # seconds per sample
    t0: float
    volts: np.ndarray         # probe-scaled volts
    clipped: bool             # any sample at ADC rail

class Digitizer(ABC):
    caps: DigitizerCaps
    def open(self, resource: str, backend: str) -> None: ...
    def close(self) -> None: ...
    def idn(self) -> str: ...
    def configure_channel(self, ch: int, coupling: str, probe_atten: float,
                          bw_limit: bool, offset_v: float) -> None: ...
    def set_vdiv(self, ch: int, vdiv: float) -> None: ...   # probe-scaled volts/div
    def set_timebase(self, s_per_div: float) -> None: ...
    def set_trigger_edge(self, ch: int, level_v: float = 0.0) -> None: ...
    def acquire(self, chans: list[int], timeout_s: float) -> dict[int, Waveform]: ...
        # one acquisition; every channel in chans is read from that same record
    alignment_epoch: int      # incremented on connect and on every resync (§8.6)
    def builtin_amplitude(self, ch: int) -> float: ...       # optional, Vrms or Vamp
    def builtin_phase(self, ch_ref: int, ch_dut: int) -> float: ...  # optional, degrees
```

### 6.2 ResponseMeter (`measure/meters.py`)

The sweep engine depends on a `ResponseMeter`, not on a scope directly. This keeps other instrument types possible later, such as a magnitude-only spectrum analyzer.

```python
@dataclass(frozen=True)
class MeterCaps:
    has_phase: bool
    min_hz: float
    max_hz: float

class ResponseMeter(ABC):
    caps: MeterCaps
    def measure(self, freq_hz: float, settings: MeasureSettings,
                state: MeterState) -> PointResult: ...
```

- **v1 implements `DualChannelScopeMeter`** (gain + phase, wraps a `Digitizer`).
- **Future: `ScalarReceiverMeter`** (gain only, e.g. a tinySA used as a receiver). The interface exists in v1; no implementation is required.
- If `has_phase` is False, the GUI hides the phase plot and exports leave phase columns empty.

### 6.3 Driver registry

`drivers/registry.py` maps `*IDN?` patterns to driver classes. On connect:
1. Open the resource and query `*IDN?`.
2. Pick the matching driver. If nothing matches, show the IDN string and let the user choose a driver manually (with a warning).

Initial entries:
- `UNI-T` + `UPO1` → `UniTUPO1000`
- `UNI-T` + `UTG9` → `UniTUTG900E`

---

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
6. **Snap** to the known states −1.85, +0.15, +2.15, +4.15 ns: if `Δt_measured` is within 0.3 ns of one, Δt is that state's value. Otherwise warn and use `Δt_measured` unchanged.
7. **Gain mismatch** = mean of the two `gain_i`, always reported; warn if its magnitude exceeds 0.3 dB (probe compensation or a bad connection).
8. Show: Δt applied, Δt measured, snapped or not, the two per-frequency values, gain mismatch, warnings. The user accepts or repeats.

**Correction.** For every measured point: `phase_corr = phase − 360°·f·Δt`, wrapped to (−180°, 180°]. Equivalently `H_corr = H·e^{−j·2π·f·Δt}`; the stored `PointResult.h` is the corrected one, and `PointResult.skew_corr_deg` keeps the amount removed so the raw phase can be recovered. Gain is not corrected in v1; the frequency-dependent calibration of §15 stays in v2.

**Validity: once per session.** A check belongs to one connection. The app prompts for a re-check:
- after connect or reconnect,
- after any driver resync (the digitizer driver exposes an `alignment_epoch` counter that it increments on connect and on every resync; the engine compares it with the value stored at the check),
- when the user says the front panel was used (toolbar action "Front panel was used").
A sweep started without a valid check asks first; if the user declines, the sweep runs uncorrected and every point carries the `SKEW_UNCHECKED` flag.

**Records.** Δt applied, Δt measured, snapped flag, gain mismatch, check frequencies and the check time go into `SweepResult.meta["skew"]`, into the CSV `# key: value` header, and into the Touchstone `!` comment lines. With no check, those say so.

**Mock.** `MockScope` picks a random skew state (one of the four values above) at every open and at every simulated resync, applies it to the DUT channel, and exposes a way to force a state. This is what makes the path testable without hardware (§9.5, §14).

**Optional tool, not used by the app:** `hwcheck/s0c_realign.py` re-rolls the scope until it is aligned by deliberately using the fault (reopen session, `:RUN`). It stays in `hwcheck/` for bench use only. The app never sends `:RUN`.

**Limits.** One 2 ns step is 14.4° at 20 MHz and 7.2° at 10 MHz against a measurement spread of about 0.1°, so the states are easy to tell apart there; below about 1 MHz a step is under 0.7° and the check loses its meaning. The check also folds in any real difference between the two probes at the check frequencies.

---

## 9. Instrument drivers

### 9.1 Common
- Each driver has a `COMMANDS` table: a dict of name → `Cmd(template, verified, ref)`.
- All writes go through `_write`/`_query` helpers with:
  - Configurable timeout.
  - Debug logging of every command and response.
  - Per-driver sync policy: `*OPC?` after writes (scope) or a configurable inter-command delay (generator).
- Termination is per instrument (verified in Milestone 0): write termination `\n` for both; read termination `None` for both, with the scope's trailing `\r\n` stripped by the driver; generator replies have **no terminator** at all.
- **Formatter per instrument.** Numeric arguments are plain decimals, never exponent notation (`0.000000025`, `20000000`). Scope probe ratio carries its `X` suffix.
- **Set, then read back.** Every setting is written, then its query is polled (up to 2 s) until it validates and equals the value sent; one re-send, then an error. Float comparison is 1e-4 relative, or one quantisation step where the instrument quantises.
- **Reply validation.** Every reply is checked against the format its query must produce (number, 0/1, enumerated word, IDN string, error-queue entry, 10-field preamble, `#` block). A reply of the wrong format is an error, never data.
- **Resync** (scope) on any reply error: restart with `:TRIGger:SWEep AUTO`, device clear, then `*IDN?` → `*OPC?` → `*IDN?` clean three times running. On pyvisa-py the device clear is: close the session, send USBTMC INITIATE_CLEAR + CHECK_CLEAR_STATUS + clear-halt through pyusb, reopen. **This is the only recovery level in the app.** If it fails, the instrument is declared unresponsive and the watchdog of §13 takes over. The app never runs anything that needs administrator rights: restarting the USB device node (`pnputil /restart-device`) is documented in `HW_REPORT.md` for manual use only, and it did not help when the scope froze on 2026-10-06.
- **Pacing** (scope): after every timebase or V/div change nothing is sent for a minimum gap, on top of `*OPC?`. The gap is a setting (`scope_min_gap_ms`, default 100 ms).
- **Transport.** Drivers talk to a `Transport` (`drivers/transport.py`), not to pyvisa, so the driver logic is tested against simulated SCPI instruments (`tests/fakes.py`).
- **Never read from an instrument with no query pending.** Under NI-VISA this broke every later read; under pyvisa-py the scope just re-sends its last reply.
- The tested reference for all of this is `hwcheck/iolayer.py`; the app drivers are a port of it.

### 9.2 UNI-T UPO1054 (`uni_t_upo1000.py`, class `UniTUPO1000`)
Source: UPO1000 programming manual (channels 1 to 4), corrected by `HW_REPORT.md`.

**Hardware-verified rules (Milestones 0, 0b, 0c; mandatory):**
- **Never send `:RUN`.** After the USB session has been reopened, `:RUN` shifts CH2 against CH1 by 2, 4 or 6 ns in about half the cases (49 of 100), and nothing documented undoes it (§8.6). Restart a stopped scope with `:TRIGger:SWEep AUTO` (0 shifts in 50, scope running again 50 of 50). The driver's write helper must refuse `:RUN`.
- **Acquisition is single-shot with status polling:**
  1. Wait until 0.3 s have passed since the last setting change and `:TRIGger:STATus?` is not `ARMED` (a setting change restarts the scope's acquisition; arming during that gives two arm cycles).
  2. Arm with `:TRIGger:SWEep SINGle`. That command is itself the arm; nothing follows it.
  3. Poll `:TRIGger:STATus?`. Accept completion only after a status other than `STOP` has been seen (the first poll after arming reads a stale `STOP`), then `STOP` held for 0.1 s, and at least 14 × timebase + 50 ms since arming. Typical sequence: `STOP` (stale) → `ARMED` → `AUTO` → `READY` (about 0.67 s after arming) → `STOP`.
  4. If the status stays `READY` longer than the force time, send `:TRIGger:FORCe`. Only from `READY`: sent while the status reads `AUTO` it leaves the scope in AUTO.
  5. Read every wanted channel from that one stopped record: `:WAVeform:SOURce CHANnel<n>` (read back), `:WAVeform:PREamble?`, `:WAVeform:DATA?`.
  6. An empty block is never retried in place: resync, then a completely new acquisition, once.
  Why single-shot and not a free-running scope: both channels must come from the same record, and the record must be known to be complete and new. A free-running capture (sweep AUTO, `:STOP`, read, restart) was benchmarked on 2026-10-06 (`HW_REPORT.md` 12.12, 12.13): a `:STOP` is only valid once the status has read `TRIGED` since the last restart, otherwise it does not last or it stops the scope with no record; with that rule the best free-running method takes 0.93 s per capture against 0.80 s for single shot. Single shot is the method. **NORMal sweep is not used anywhere**: it never read back as set, and the driver refuses to send it.
- **Step tables are shipped as data, keyed by model + firmware** (`drivers/step_tables.py`), and are **never walked at connect**: the scope froze during such a walk on 2026-10-06 and needed a power cycle (`HW_REPORT.md` 12.13). Only values from the tables are requested, and each one is still verified by read-back when it is set. Shipped: UPO1054 firmware `1. 01. 0047`: timebase 1 ns, 2 ns, 5 ns, 10 ns, **25 ns**, 50 ns, then 1-2-5 up to 20 ms (23 steps); V/div 500 µV to 20 V in 1-2-5 steps (15 steps). A request for 20 ns/div lands on 10 ns/div. For any other model or firmware the same tables are used, the user is warned once per connection, and the warning names the walk. Walking is an explicit probe-tool option (`--walk-tables`, §9.4); its result is saved to `step_tables.json` in the settings folder and takes precedence over the shipped data.
- An empty reply to an ordinary query (or to the `*IDN?` sentinel) means "busy": retry after 50 ms, no resync.
- Channel offset and trigger level are quantised to V/div / 25.
- Do not let the user operate the front panel during a sweep: in Milestone 0b that made the scope ignore timebase commands and return empty captures. **`:SYSTem:LOCK ON` locks the whole front panel; verified 2026-10-06** (`HW_REPORT.md` 12.14): the read-back is `1` when locked (the manual's "Return format" sentence says the opposite; its example is right), remote control keeps working, and the lock survives a closed USB session. The driver locks the panel for the length of a sweep, skew check or re-measure, releases it afterwards and on disconnect, and the probe tool has `--unlock`. After a measurement the scope is also put back to sweep AUTO so that it is left running.
- Follow every write with `*OPC?` (returns `1`). Writes sent back to back are silently dropped.
- V/div in exponent notation is silently ignored; plain decimals work.
- Probe ratio needs the `X` suffix (`:CHANnel1:PROBe 1X`). A bare number is misread (`1` sets 10X). Keep the scope at 1X and apply probe attenuation in software: waveform data and YINC are input-referred, while `:CHANnel<n>:SCALe?` and `:MEASure` results are probe-scaled.
- Read back timebase and V/div after setting and use the reported value (`0.00000002` s/div came back as 10 ns/div).
- Waveform readout: `:WAVeform:SOURce CHANnel<n>`, `:WAVeform:MODE NORMal`, `:WAVeform:FORMat BYTE`, `:WAVeform:PREamble?`, `:WAVeform:DATA?`. The block is `#3700` + **700 points** + `\r\n`, covering **14 divisions**, sample interval = timebase / 50. Take the point count from the block; the preamble's Points field (1000) is wrong and `:WAVeform:POINts?` returns nothing.
- Volts = `(code − YREF − YOR) × YINC`, with YREF = 128, YINC = V/div / 25. Sign of YOR verified.
- **Never ask for `:WAVeform:DATA?` unless a screen record exists** (the single-shot procedure above guarantees it). An empty reply (`\r\n` only) must not be retried: the reply it is owed arrives about 0.6 s after the scope runs again, as a 707-byte block in place of the answer to some later query. Reply validation catches that and a resync repairs it (5 of 5 forced cases).
- Do not use timebases of 50 ms/div or slower (SCAN/roll status, no waveform data).
- A bare read with no query pending re-sends the last reply forever instead of timing out; never "drain" by reading until timeout.
- At fast timebases the 700 points are interpolated (0.2 ns spacing at 10 ns/div).
- Two channels from one acquisition: verified for CH1 + CH2 (880 of 880 valid captures in the 0b and 0c dual-channel runs, 0 errors). Channel match in the aligned state with 10X probes: gain within 0.03 dB, phase within 0.1° to 1 MHz and about +1.1° at 20 MHz, of which about +0.9° and +0.09 dB belong to the scope inputs.
- CH3/CH4: documented in the UPO1000 manual and they answer queries; set commands and waveform read-out on them are `verified=False` until probed.
- There is no documented per-channel delay or deskew command.
- **Rail codes and divisions (measured 2026-10-06, `HW_REPORT.md` 12.14):** waveform codes stop at **1 and 254**, not 0 and 255. A capture is clipped when any sample is ≤ 1 or ≥ 254. The data cover 253 codes = 10.1 divisions; the screen grid has 8. Overdriving one channel does not disturb the other.
- Not yet verified: `:MEASure:PHASe?` (the driver declares no built-in amplitude or phase measurement).

Implement from the manual:
- Channel coupling, probe ratio, V/div, offset, bandwidth limit.
- Timebase scale.
- Edge trigger source and level.
- Single acquisition, plus waiting for acquisition complete.
- Waveform readout:
  - Source select and data format.
  - Preamble or scale/offset query to convert raw codes to volts, and the sample interval.
  - Use **screen/normal mode** (not full memory) for speed, unless the manual offers a better option.
- Clip detection: samples at the min/max ADC code.
- Built-in measurements: amplitude (Vamp or Vrms) per channel and phase between channels, if the manual provides them.
- Fill `DigitizerCaps` from the manual and data sheet:
  - 50 MHz, 4 channels, up to 1 GSa/s. `horizontal_divs` = 14.
  - V/div steps: 500 µV to 20 V, 1-2-5 (verified). Timebase steps as listed above. Both come from the scope at connect, not from constants.
  - Horizontal divisions 14 (verified). Vertical division count: still to verify.

**Probes.** 10X is the default and is required above about 1 MHz: it read 1 Vpp within 1.5% up to 20 MHz, where 1X delivered a third of the signal. 1X is only for small signals (below roughly 50 mVpp at the test point) on sweeps that stay under about 1 MHz. Both channels must use the same probe type and setting, compensated. The scope stays at `PROBe 1X`; `probe_atten` is applied in software.

### 9.3 UNI-T UTG932E (`uni_t_utg900e.py`)
Source: UTG900E programming manual, corrected by `HW_REPORT.md`. The ELV manual and EEVblog list were not provided.

**Hardware-verified rules (Milestone 0, mandatory):**
- **Never send `*OPC?` or any query that is not in the UTG manual.** `*OPC?` times out and can leave the generator deaf to all commands until a USBTMC `INITIATE_CLEAR` is sent. Pace commands with a delay instead.
- Read termination `None` (replies carry no terminator).
- Set `:CHANnel<n>:AMPLitude:UNIT VPP` before `:CHANnel<n>:BASE:AMPLitude`; the amplitude is in whatever unit the channel is in.
- High-Z is `:CHANnel<n>:LOAD 10000`; 50 Ω is `:CHANnel<n>:LOAD 50`.
- Verified working: `:CHANnel<n>:OUTPut`, `:CHANnel<n>:LOAD`, `:CHANnel<n>:AMPLitude:UNIT`, `:CHANnel<n>:BASE:WAVe`, `:CHANnel<n>:BASE:FREQuency`, `:CHANnel<n>:BASE:AMPLitude`, `:CHANnel<n>:BASE:OFFSet` (set on CH1, queried on CH1 and CH2), plus queries of `:CHANnel<n>:MODe`, `:CHANnel<n>:BASE:PHASe`, `:SYSTem:LOCK`.
- `:SYSTem:LOCK?` returns 1 while under USB control.
- **Command whitelist (0b).** The driver holds the exact long forms of the commands it uses and refuses anything else before any I/O (8 of 8 unknown commands blocked, zero bytes sent).
- **Timeout → device clear → one retry (0b).** A timeout or a wrong-format reply is answered with a device clear and a single retry (5 of 5 injected timeouts recovered, no stale reply left behind).
- Frequencies from 50 Hz to 20 MHz, amplitude down to 50 mVpp, offset and load set and read back correctly (0b, 0c).

Implement:
- Waveform = sine, frequency, amplitude (Vpp), offset, load (High-Z / 50 Ω), output on/off.
- `SourceCaps`: sine up to 30 MHz. Read min frequency and amplitude limits per load from the manual.
- Known community command forms: `CHANnel<n>:BASE:FREQuency`, `CHANnel<n>:BASE:AMPLitude`, `CHANnel<n>:BASE:OFFSet`, `CHANnel<n>:BASE:WAVe`, `CHANnel<n>:LOAD`, `CHANnel<n>:OUTPut`. Confirm each against the official manual before use.
- Check whether changing the frequency glitches or disables the output. If it does, document it, and handle it in the driver with a post-change settle.

### 9.4 Probe tool (`tools/probe.py`)
`python -m bodeplot.tools.probe [--scope RES] [--gen RES] [--backend py|auto|ivi] [--no-acquire] [--unlock] [--walk-tables [--gap-ms N] [--yes]] [--json FILE]`

It follows the same rules as the app: no `:RUN`, no table walk by default, generator outputs OFF at the start and at the end and never switched on. It prints its own file hash and the drivers' hashes first.

1. Find the instruments (`*IDN?` only, USB and LAN resources; serial ports are never probed).
2. Send the query form of every `COMMANDS` entry of both drivers (scope channels 1 to 4, generator channels 1 and 2) and print a pass/fail table. Nothing is set, apart from the waveform read-out format at connect.
3. Unless `--no-acquire`: one single-shot acquisition on scope CH1; print the point count, `dt`, volt range and clip check; put the sweep back to AUTO.
4. `--json FILE` writes the report.
5. `--unlock` releases the scope's front-panel lock and does nothing else.
6. `--walk-tables` measures the scope's own timebase and V/div steps with `UP` / `DOWN`. It prints a warning (the 2026-10-06 freeze), asks for confirmation unless `--yes`, pauses `--gap-ms` (default 250, minimum 100) after every step, never goes to 50 ms/div or slower, restores both settings, and saves the tables to `step_tables.json` in the settings folder.

### 9.5 Mock instruments (`drivers/mock.py`)
- `SimulatedDUT` supports:
  - Presets: RC LPF, RC HPF, RLC band-pass, RLC notch, 2nd-order Butterworth LPF.
  - A custom H(s) via numerator/denominator coefficients.
  - Parameters in the GUI sim dialog.
- `MockSource` feeds `MockScope`. MockScope synthesises both channels:
  - Ref = stimulus × source impedance divider, using a configurable DUT input impedance.
  - Dut = H(jω) × ref.
  - Adds Gaussian noise, 8-bit quantisation, clipping at full scale, and a configurable trigger jitter.
  - Applies a 1st-order 50 MHz scope roll-off to both channels.
  - **Simulates the channel skew fault:** at every open and at every simulated resync it draws a random state from −1.85, +0.15, +2.15, +4.15 ns and advances the DUT channel by it; `force_skew_state(i)` / `skew_s` let tests pick one. `alignment_epoch` increments on each.
  - Uses the real step tables (timebase with 25 ns and no 20 ns; V/div 500 µV to 20 V), 14 horizontal divisions and 700 points per record.
- Configurable artificial latency per command (default 0 in tests, ~5 ms in GUI sim mode for realism).
- Enabled with `--sim` or a GUI toggle; the registry returns mock drivers.

---

## 10. GUI

**Main window layout:**
- **Toolbar:**
  - Connect/Disconnect, Start, Pause/Resume, Abort.
  - Export ▾ (CSV, PNG, SVG, PDF, Touchstone).
  - Preset dropdown + Save / Save As / Delete.
  - Sim-mode indicator.
- **Left dock: config panel**, grouped:
  - Sweep: type, start, stop, points/decade or N, descending.
  - Stimulus: gen channel, amplitude, offset, load.
  - Scope: ref/dut channel mapping, probe atten per channel, coupling, BW limit, target cycles.
  - Measurement: method (Sine fit / Built-in), averages, settle ms, settle cycles.
  - Inputs are disabled while a sweep is running.
- **Centre:** two vertically stacked pyqtgraph plots:
  - Gain dB and phase °, both with log or linear x-axis to match the sweep type, x-axes linked.
  - Crosshair with a readout of freq / gain / phase.
  - "Unwrap phase" checkbox, default off.
  - Flagged points drawn with distinct markers, with tooltips listing the flags.
- **Right dock: live waveform view.** The last ref and dut capture in volts vs time, with the fitted sine overlaid in SINEFIT mode.
- **Bottom dock: status log.** Table with columns time / freq / V/div ref,dut / retries / flags / duration, plus a free-text log. Auto-scrolls; has a copy and clear option.
- **Status bar:** state, progress `i/n`, elapsed time, ETA.

**Dialogs:**
- **Connections:**
  - Backend (py/auto/ivi), default `py`.
  - Per-instrument resource string with a "Discover" button (lists resources). Empty fields mean "find the one supported generator and scope".
  - "Test" button: `*IDN?` of the chosen resources and which driver each one gets. Only while disconnected.
- **Skew check wizard** (§8.6): toolbar button "Skew check", status-bar indicator (Δt and age, or "skew: unchecked"), and a toolbar action "Front panel was used" that invalidates the current check.
- **Sim settings:** DUT preset and parameters, noise level.
- **Export:** format options (image DPI, size, title).

**Behaviour:**
- Closing the window during a sweep asks for confirmation, aborts cleanly, and turns the generator off.
- Window layout and last-used settings persist in `settings.json`.

---

## 11. Presets & settings

- Location: `platformdirs.user_config_dir("bodeplot")`
  - `settings.json`: connections, backend, window state, last preset.
  - `presets/<name>.json`: `SweepConfig`, `StimulusConfig`, `ScopeConfig`, `MeasureSettings`. No connection info.
- Every file has `"schema_version": 1`. Unknown keys are ignored; missing keys take defaults. Never crash on an old file.

---

## 12. Export formats

All exports include metadata: app version, timestamp, instrument IDNs, and the full config snapshot.

- **CSV**
  - Metadata as `# key: value` header lines, then the columns: `freq_hz, gain_db, phase_deg, phase_unwrapped_deg, h_re, h_im, vref_amp_v, vdut_amp_v, vdiv_ref, vdiv_dut, timebase_s, n_avg, snr_ref_db, snr_dut_db, skew_corr_deg, flags`. The header carries the skew check (Δt, measured Δt, snapped, gain mismatch, check time) or `skew: not checked`.
  - Must round-trip: a loader exists in v1, because v2 overlay needs it.
- **PNG / SVG / PDF** (matplotlib):
  - Gain and phase subplots matching the current view: wrap state, axis type, flagged markers.
  - Title, plus a footer with the date and key settings. DPI and size configurable.
- **Touchstone `.s2p`**
  - Header `# Hz S RI R 50`.
  - S21 = H; S11, S12, S22 = 0.
  - `!` comment lines state that this is a scope-based voltage transfer ratio, not a calibrated 50 Ω S-parameter measurement, list the config, and give the skew check (Δt and check time) or say that none was done.

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

---

## 15. Roadmap (design for it, don't build it in v1)

**v2**
- **Probe/channel calibration:** sweep with both probes on the same node, store H_cal(f) per setup, and divide later measurements by it (interpolated). The single-frequency delay check of §8.6 is the v1 subset of this and must not wait for v2.
- **Trace overlay & compare:** multiple traces on the plot, load CSVs, show or hide traces, show the difference trace.
- **Auto markers:** −3 dB point(s), peak/notch, gain margin and phase margin readout, user markers.

**v3: filter recognition**
- Classify the response as LPF / HPF / BPF / BSF / all-pass / unknown.
- Report:
  - Cutoff(s) at −3 dB relative to the passband.
  - Passband gain and ripple; stopband attenuation.
  - Centre frequency, bandwidth and Q (for BPF/BSF).
  - Roll-off slope in dB/decade → estimated order.
- Rational transfer-function fit (e.g. vector fitting / least squares on complex H): show the fitted curve and list poles and zeros.
- Confidence score; refuse to classify when there are too many flags, too narrow a span, or low SNR.

**Later**
- PyInstaller builds.
- Additional drivers: other scopes and generators, and `ScalarReceiverMeter` for spectrum analyzers such as the tinySA Ultra above 20 MHz.

**Design implications for v1:**
- Keep `PointResult.h` complex and stored.
- Keep the CSV loader.
- Keep plotting able to handle multiple traces internally, even though v1 shows one.

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
7. **Hardware bring-up (with the user):**
   1. Run the probe tool and fix the failing commands.
   2. Then measure a known RC LPF (e.g. 1 kΩ + 100 nF → fc ≈ 1.59 kHz) and compare with the mock and with theory.
   3. Then sweep the full 50 Hz–20 MHz range and record the per-point timing.

Each milestone ends with `pytest` green and a short note in `README.md` describing what works.

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

Still open:
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
