# Spec: architecture, driver interfaces and drivers (sections 6 and 9)

Part of the design spec. Overview and the index of all sections: `docs/SPEC.md`. Section numbers are kept, because the code cites them.

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

The transfer functions of the simulated DUT live in `measure/theory.py` (`TransferFunction`); `SimulatedDUT` adds the load on the source. The same module supplies the plot's theory curves (section 10).
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
