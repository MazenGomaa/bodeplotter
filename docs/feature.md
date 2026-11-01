# Parked features

1. Semiconductor Curve Tracer Mode (below)
2. LCR / Impedance Analyzer Mode
3. FFT / Spectrum and Distortion Mode (at the end of this file; after the LCR phase)

---

# Feature: Semiconductor Curve Tracer Mode (parked)

Status: **parked idea, not scheduled.** Do not build until the Bode plotter v1 is finished and the user re-opens this.
Target: a second measurement mode in the Bode plotter app (roadmap "v4"), reusing its drivers, I/O layer and single-shot capture.

---

## 1. Goal

Plot I–V characteristics of small-signal semiconductors using the existing UTG932E generator + UPO1054 scope, plus a small buffer board:

- Two-terminal: diodes, LEDs, Zeners (forward and reverse).
- Three-terminal families: BJT (I_C vs V_CE for stepped I_B), JFET / MOSFET (I_D vs V_DS for stepped V_GS), transfer curves (I_D vs V_GS).
- NPN/PNP and N/P-channel by software polarity only (bipolar rails, no switch).

Not in scope: power devices beyond ~1–2 A / ±15 V, leakage currents in the µA–nA range (8-bit scope ≈ 250 levels per range), high-voltage breakdown.

---

## 2. Hardware (buffer board)

### 2.1 Block diagram

```
Gen CH1 ─[divider]─ TDA2030A ─ polyfuse ─ R_limit ─┬─ Collector/Drain   ← Scope CH1
                                                   │
                                                  DUT
                                                   │
Gen CH2 ─ TL072 buffer (×2) ─ R_base ─┬─ Base/Gate ← Scope CH3
          └─ Scope CH4 (drive side)   │
                                      Emitter/Source ─ R_sense ─ GND
                                                   ← Scope CH2
```

Derived quantities (software):
- V_CE = CH1 − CH2
- I_C = CH2 / R_sense
- I_B = (CH4 − CH3) / R_base
- V_BE = CH3 − CH2

Measuring every node lets the software correct for the voltage dropped across the sense resistor.

### 2.2 Sweep buffer: TDA2030A (bare IC, not the module)

- Supply up to ±18 V → output about ±15 V; ~3 A peak; built-in short-circuit and thermal protection (important: the DUT will short sometimes).
- Do **not** use the "TDA2030 Audio Amplifier Module 18W 6-12V": single supply, AC-coupled, cannot pass DC ramps.
- Not unity-gain stable: run it at the datasheet's recommended closed-loop gain with an input divider so that overall gain from the generator is about ×3 (±5 V in → ±15 V out).
- Add the datasheet's output Zobel network (1 Ω + 100 nF) and 1N4007 clamp diodes to both rails. Decouple both rails close to the IC.
- Heatsink: U-shape or larger, not the small 20×15 mm one.

Alternatives:
- TDA2050 (±25 V): more headroom, out of stock at Makers Electronics when checked (2026-10-06).
- Fallback if the TDA2030A misbehaves: op-amp (NE5532 / TL072) driving a TIP41C/TIP42C complementary pair inside its feedback loop. Unity-gain stable and DC-coupled, but no built-in protection: current limiting must be added.

### 2.3 Base/gate drive

- TL072 half as a ×2 buffer: generator ±5 V → about ±10 V, enough for MOSFET gates. Second half spare.
- Selectable R_base: 1 k / 10 k / 100 k (base current ranges). For MOSFETs, a low value or a jumper bypass.

### 2.4 Parts list (Makers Electronics availability as of 2026-10-06)

| Part | Purpose | Availability |
|---|---|---|
| TDA2030A + U-shape heatsink | Collector/drain sweep buffer | In stock (15 EGP IC, 16 EGP heatsink) |
| TL072 (dual) | Base/gate drive buffer | Listed |
| Polyfuse RXEF050 (72 V, 500 mA) or RXEF025 | Hard current limit | Listed |
| R_limit, selectable: 4.7 / 10 / 220 Ω, 5 W | Max current, DUT protection | Power resistors listed |
| R_sense, selectable: 1 / 10 / 100 Ω | Current ranges (A, 100 mA, 10 mA) | 1 Ω 5 W listed; use 1% for 10/100 Ω |
| R_base, selectable: 1 k / 10 k / 100 k | Base current ranges | Standard |
| 1N4007 ×2, 1 Ω + 100 nF Zobel, decoupling caps | TDA2030A stability and protection | Listed |
| DUT socket: TO-92/TO-220 socket or ZIF + screw terminals | Device mount | Check |
| Jumpers or rotary switch | Range selection | Standard |
| PCB BNC ×6: 2 generator in, 4 scope out | Instrument links | User's own source (Makers only lists chassis-mount BNC) |
| ±15 to ±18 V supply, ~2 A | Rails for TDA2030A + TL072 | Bench PSU or on-board transformer supply (undecided) |

Measure every R_sense / R_base with a DMM and enter the real values in the app (5 W power resistors are usually 5%).

### 2.5 Open hardware questions
- Is there an existing ±15 V or higher dual-rail supply, or does the board need its own?
- Range selection by jumpers, rotary switch, or relays (relays would allow software range control later).

---

## 3. Software

### 3.1 Driver additions needed
- **Generator:** DC-level output and ramp/triangle (or arbitrary) waveform, with offset. v1 drivers only cover sine.
- **Scope:** `acquire()` reading 3–4 channels from one record. Designed for, but only CH1+CH2 verified on hardware. Needs a hardware check before this mode is built.
- Probe ratio per channel in software, as in the Bode mode.

### 3.2 Measurement method
- Collector/drain sweep: slow ramp or triangle on gen CH1, about 50–500 Hz (low frequency keeps device capacitance from turning the curve into a loop). Offset so the ramp runs 0 → +V (or 0 → −V for PNP / P-channel); symmetric triangle for Zener/reverse tests.
- **Family curves by software stepping** (no synchronised staircase): for each step, set gen CH2 to a DC level, capture one full sweep (single-shot, all channels from one record), store it, next step. Overlay all steps.
- Each capture about 0.8 s → an 8-step family in about 7–10 s.
- XY plotting in the app (not the scope's XY mode). Hysteresis between rising and falling ramp can be shown or averaged.

### 3.3 Safety rules
- Generator outputs on only during a capture, off between steps (keeps the DUT cool).
- Per-sweep power limit (V × I) set by the user; abort and outputs off if exceeded.
- Every new range starts at the smallest amplitude and ramps up.
- User enters R_limit / R_sense / R_base to match the board jumpers; saved with each measurement.
- Same I/O rules as the Bode mode (no `:RUN`, single-shot acquisition, readback verification, `safe_off` in `finally`).

### 3.4 Outputs
- Curve families (I–V), transfer curves, derived values where meaningful: diode V_F at a chosen current, Zener voltage, β (h_FE) vs I_C, MOSFET V_GS(th) at a chosen I_D, on-resistance.
- CSV export of every curve (all channels + derived columns) with the board settings in the header; PNG/SVG/PDF export.

---

## 4. Before building
1. Bode plotter v1 finished (Milestones 6 and 7).
2. Hardware check: 3- and 4-channel single-shot read-out on the UPO1054; UTG932E DC and ramp/arbitrary output via SCPI.
3. Buffer board built and bench-tested on its own (stability, swing, current limit, short-circuit behaviour).
4. Then write the full spec section from this file.

---
---

# Feature: LCR / Impedance Analyzer Mode (parked)

Status: **parked idea, not scheduled.** Most of it reuses the Bode engine directly. Build after Bode v1 (Milestones 6 and 7). It is closer to ready than the curve tracer: no power stage, only a small fixture.

## 1. Principle: V-I method with a reference resistor

```
Gen CH1 ──┬── R_ref ──┬── DUT ── GND
          │           │
      Scope CH1   Scope CH2
```

- The Bode engine already measures H = V2 / V1 (complex, skew-corrected).
- Current: I = (V1 − V2) / R_ref
- **Impedance: Z = R_ref · H / (1 − H)**

Everything stays ground-referenced, so there is no conflict between the scope and generator grounds. It is the same sweep, auto-range, sine fit and single-shot capture: only the fixture and the math are new.

## 2. Accuracy drivers (why "advanced" needs care)

- **R_ref selection:** accuracy is best when |Z| is near R_ref. Use selectable ranges, e.g. 10 Ω / 100 Ω / 1 kΩ / 10 kΩ / 100 kΩ. The app recommends a range from a quick first measurement. Measure each R_ref with a DMM and enter the real value. Relays could allow auto-ranging later.
- **Phase accuracy is everything for low-loss parts.** A good capacitor sits near −90°, so its ESR/D lives in fractions of a degree: a 0.1° phase error is about 0.0017 in D. That means:
  - the skew check and correction (§8.6 of SPEC.md) is mandatory;
  - channel gain/phase matching across frequency (the v2 through-calibration) should be done first.
- **Fixture compensation (standard LCR practice), required:**
  - Open: removes stray and probe capacitance (a 10X probe adds about 10–15 pF at the DUT node).
  - Short: removes lead resistance and inductance.
  - Optional load: a known precision resistor, to correct residual gain/phase errors.
  - Stored per fixture and range, applied as correction to Z.
- **Usable range (expected, to be verified):** roughly 1 Ω to 1 MΩ with good accuracy. Below ~1 Ω (electrolytic ESR, small inductors) V2 is tiny compared to V1, so it needs averaging and a 10 Ω range; above ~1 MΩ, probe loading and the 8-bit scope dominate. The sine fit's noise rejection helps at both ends.
- **4-wire (Kelvin) sensing** at the DUT for low impedances: CH2 senses right at the DUT terminal, not at the fixture connector.
- **DC bias:** the generator offset can apply a small bias (e.g. for electrolytics), within the generator's limits.

## 3. Features

**Meter mode (single frequency, continuous readout like a bench LCR meter)**
- Standard frequencies 100 Hz / 1 kHz / 10 kHz / 100 kHz / 1 MHz, plus any custom value.
- Primary/secondary display: L/Q, C/D, R/X, |Z|/θ, ESR, with series or parallel model selectable, plus auto-select from the measured phase.
- Hold, averaging, and a tolerance/sort readout against a nominal value (e.g. "100 nF ±5% → PASS").

**Sweep mode (impedance analyzer)**
- |Z| and θ vs frequency over 50 Hz to 20 MHz, plus R, X, L, C, ESR, Q, D vs frequency.
- Self-resonant frequency (SRF) detection for capacitors and inductors.
- **Equivalent-circuit fitting:** e.g. capacitor = C + ESR + ESL; inductor = L + R_s + C_p; crystal / resonator = motional RLC + C0. Show fitted values and the fit overlay.
- Overlay and compare sweeps (shares the v2 trace overlay feature).

**Exports**
- CSV with all derived columns and the fixture/calibration info in the header.
- Touchstone .s1p (impedance converted to S11 / reflection).
- PNG/SVG/PDF.

## 4. Hardware: small fixture board (could merge with the Bode BNC board)
- BNC in from generator CH1, BNC out to scope CH1 and CH2.
- R_ref bank, 1% or better, low inductance (metal film; avoid wirewound): 10 / 100 / 1 k / 10 k / 100 k, selected by jumper or rotary switch.
- DUT connection: Kelvin clips or a test socket, short leads, ground plane.
- Optional later: an auto-balancing bridge (op-amp transimpedance stage) for better high-impedance accuracy, limited by op-amp bandwidth to roughly ≤1 MHz unless a fast op-amp is used.

## 5. Software additions
- New mode tab reusing the sweep engine (`ResponseMeter` → impedance computation layer).
- Fixture settings: R_ref value per range, which range is selected (user confirms jumper), 2- or 4-wire.
- Calibration wizard: open / short / load, stored per range and fixture, with expiry warnings like the skew check.
- Math module: Z from H, series/parallel conversions, L/C/R/Q/D/ESR, SRF finder, equivalent-circuit fitting (least squares on complex Z).
- Tests on the mock: simulated DUTs (ideal R, C with ESR/ESL, inductor with R_s/C_p, crystal) through each R_ref range; recovered values within set tolerances; open/short compensation removes injected strays.

## 6. Before building
1. Bode v1 finished and verified on hardware.
2. Channel through-calibration (v2) done; phase match across frequency known.
3. Fixture built; R_ref values measured.
4. Hardware check: measure known parts (1% resistors, a C0G capacitor, an inductor) against a reference LCR meter if one is available.

---
---

# Feature: FFT / Spectrum and Distortion Mode (parked)

Status: **parked idea, not scheduled. Bench testing comes first: nothing about this mode is planned or designed until the hardware questions of section 4 are answered on the bench.** It comes after the LCR phase. Added 2026-11-01 on the user's request; the app would then have three modes: Bode, LCR, FFT.

## 1. Would it beat the scope's built-in FFT?

Mostly no as a general spectrum analyser; yes for jobs that use the generator.

- **Limit: the app sees only 700 points per channel.** `:WAVeform:DATA?` returns the screen record, 700 points over 14 divisions, interpolated at fast timebases (`docs/spec/drivers.md`, HW_REPORT S7). The scope's own FFT runs on its internal memory (7K or more; how many points it uses is not checked). 700 points give 350 bins, a bin width of 1 / (14 × timebase) and a higher noise floor; timebases of 50 ms/div or slower are forbidden, which caps the resolution at low frequency.
- **Same in both:** the 8-bit ADC, so spurs and distortion near −40 to −50 dBFS in either FFT.
- **Scope's FFT stays better at:** live update (the app needs about 0.2 s per capture in preview style, 0.8 s single shot), finer resolution, unknown signals the app does not generate (noise, switching spurs).
- **App's FFT would be better at:**
  1. **Coherent analysis with the generator:** the app picks a stimulus frequency with a whole number of cycles in the record, so there is no leakage and no window; fundamental and harmonics measured with the sine fit at n·f. Gives THD, THD+N and per-harmonic levels. This is the strongest reason to build the mode.
  2. **Averaging:** power averaging over captures; vector (complex) averaging with a stable trigger, which lowers the noise floor.
  3. **Precision and tooling:** floating-point spectra, choice of window, markers, peak list, trace compare, CSV export, the Analysis tab.
  4. **Both channels at once:** cross-spectrum and coherence (overlaps with Bode).

Direction if built: a stimulus-driven harmonic / distortion analyser first, an averaged spectrum view second. Not a replacement for the scope's FFT on unknown signals.

## 2. Reuse
The single-shot capture, auto-range and sine fit (`measure/sinefit.py`, SPEC §8.4) of the Bode engine. A harmonic readout (fit at n·f) can work on captures the Bode sweep already takes.

## 3. Out of scope for now
Replacing the scope's live FFT; spectra of signals the app does not generate as the main use.

## 4. Before planning anything (bench tests first)
1. LCR phase done, or the user re-opens this.
2. **Bench: can the scope return more than 700 points?** `:WAVeform:MODE` other than NORMal (RAW or MAX, if the UPO1000 manual lists them), with the memory depth at 7K and above, read only from a stopped single-shot record, every command cited with its manual page. Record what comes back and how long the readout takes. This result decides whether a general spectrum view is worth building at all.
3. **Bench: the scope's own FFT as a reference.** Its record length, windows and dB floor with a known sine, so the app can be compared to it.
4. **Bench: distortion floor.** A clean generator sine fitted at 2f to 10f, to see the THD floor the scope and generator together allow.
5. Then write the spec section from this file.
