# Trace overlay, theory curves and compare: design

Date: 2026-10-07. Status: **design agreed with the user in conversation on 2026-10-07; this file awaits the user's review.** Not built; the next step after approval is the implementation plan. It is milestone A3 of the roadmap (`docs/spec/roadmap.md` sections 15 and 16). A2 was parked by the user on the same day.

## 1. Purpose

Today the plot shows one sweep, and starting a new sweep throws the previous one away. To compare a measurement with an earlier one or with the ideal response, the user exports CSV files and compares them outside the app (as was done by script for the RC low-pass of `HW_REPORT.md` 14.3).

A3 puts several traces on the plot: the live sweep, earlier sweeps kept or loaded from CSV files, and theory curves; and it can draw all of them relative to one chosen trace.

What the user asked for, in their words and choices:

| Question | Decision |
|---|---|
| What to compare | Measurements against saved ones and several DUTs side by side (files), and measurements against theory: both "strongly needed". Keeping the current sweep before the next one was offered on top and not refused. |
| How a theory curve is defined | Pick a circuit and enter its parts, or enter H(s) as coefficients. Real-part models (ESR, lead inductance, probe loading) and fitting are left out. |
| What "difference" shows | Every trace relative to one reference trace, as a ratio (dB and degrees), on the two existing plots. No separate error plot. |
| How long traces live | This run of the app only. Nothing is stored. |

Success criteria:

1. A sweep, a loaded CSV and a theory curve can be on the plot together, each shown or hidden, each told apart by colour and name.
2. With a theory curve as the reference, the plot shows directly how far a measurement is from it, and the numbers agree with the same comparison done by hand.
3. With no extra trace added, the app looks and behaves as it does today, and the CSV and Touchstone exports are unchanged.

## 2. What it does not do

- No real-part circuit models, no fitting of a curve to a measurement (v3, milestone B3).
- Traces are not remembered between runs and are not part of a preset.
- No separate error plot, no markers (A4).
- A theory curve is not written to CSV or Touchstone; those exports hold the live sweep only.

## 3. Traces

Four kinds:

| Kind | Comes from | Can be removed | Notes |
|---|---|---|---|
| live | the sweep in progress or just finished | no | always present, always first; a new sweep replaces only this one |
| kept | "Keep sweep": a copy of the live sweep at that moment | yes | named "Sweep HH:MM:SS" |
| file | "Load CSV…" | yes | named after the file (without the extension) |
| theory | "Add theory…" | yes | named after the circuit and its values, e.g. "RC low-pass 1 kΩ 100 nF" |

Each trace has a name (editable, made unique by a numeric suffix when needed), a visibility tick and a colour.

**Colours.** The theme's eight series colours (`theme.SERIES`), in their fixed order, are slots. The live trace always has slot 1. A new trace takes the lowest free slot; removing a trace frees its slot. The theme's rule that series colours are never cycled stays: a trace added when all eight slots are taken is drawn in the muted colour. (In the conversation I said the colours would repeat after eight; that contradicts the theme's rule, so the design follows the theme. Say so if you want it otherwise.)

**Points.** A measured trace (live, kept, file) keeps its `PointResult`s, so flags, V/div and the re-measure menu keep working. A file whose rows have no complex H (an old or hand-made CSV with only gain and phase) gets H rebuilt from gain and phase. A theory trace has no stored points: it is evaluated when drawn, on a logarithmic grid of 50 points per decade over the union of the frequency ranges of the other traces and of the sweep settings in the panel.

## 4. Theory curves

A theory curve is a transfer function H(s) = num(s) / den(s).

The dialog offers the circuits the simulator already has, with the same part values and SI entry (1k, 100n):

| Circuit | Parts |
|---|---|
| RC low-pass, RC high-pass | R, C |
| RLC band-pass, RLC notch | R, L, C |
| Butterworth low-pass, 2nd order | cutoff frequency |
| Custom H(s) | numerator and denominator coefficients, highest power first |

Invalid entries (a part that is not positive, an empty or all-zero denominator, text that is not a number) are refused in the dialog with the reason. Double-clicking a theory trace reopens the dialog with its values.

Code: the transfer functions move out of the simulator into a module of their own, `measure/theory.py` (`TransferFunction` with `h(freq_hz)`, the presets, their labels and part tables). `SimulatedDUT` in `drivers/mock.py` becomes a `TransferFunction` plus the input impedance it adds, with its present constructors and behaviour, so Simulation mode and its tests do not change. The part tables `SIM_PARAMS` and `SIM_LABELS` move from `gui/dialogs.py` to that module, and the part-entry form of the simulation settings becomes one widget used by both dialogs.

## 5. Relative display

A box "Relative to" above the plot: "nothing" (default) or one of the traces.

With a reference chosen, every visible trace is drawn as H_trace / H_ref:

- upper plot: gain difference in dB; lower plot: phase difference in degrees, wrapped to (−180°, 180°], unwrapped per trace when "Unwrap phase" is ticked;
- the reference itself is the flat zero line, drawn in its own colour;
- the axis labels say "Gain difference" and "Phase difference", and the hover read-out says "relative to <name>".

Where the frequency points of a trace and of the reference differ, the reference is interpolated in log frequency: gain in dB linearly, phase after unwrapping linearly. A theory reference is evaluated exactly at the trace's frequencies, with no interpolation. Outside the reference's frequency range (more than 0.1 % beyond its first or last point) nothing is drawn for that trace: no extrapolation. A reference point with |H| of zero or a non-finite value gives no difference at that frequency.

Hiding the reference trace does not switch the relative display off (only its zero line disappears). Removing it sets "Relative to" back to "nothing". The live sweep may be the reference, also while it is still running; the other traces then appear as far as it has got.

**Vertical unit.** In "dB" as above. In "% of input" the upper plot shows 100 · |H_trace / H_ref| in percent. In "Voltage" (the DUT output in Vpp) a theory curve and a ratio have no meaning: theory traces are not drawn, and "Relative to" is disabled and treated as "nothing"; the trace list marks the traces that are not drawn, with the reason in a tooltip.

## 6. Code structure

| File | Change | Responsibility |
|---|---|---|
| `src/bodeplot/measure/theory.py` | new | `TransferFunction`, presets, labels and part tables; no Qt |
| `src/bodeplot/traces.py` | new | `Trace`, `TraceSet` (add, keep, remove, rename, show / hide, colour slots, reference), `relative(points, reference)`, the grid of a theory trace; no Qt |
| `src/bodeplot/drivers/mock.py` | change | `SimulatedDUT` built on `TransferFunction` |
| `src/bodeplot/gui/traces_panel.py` | new | the Traces panel: list with ticks and colour swatches, the buttons |
| `src/bodeplot/gui/dialogs.py` | change | `TheoryDialog`; the shared part-entry widget |
| `src/bodeplot/gui/bode_plot.py` | change | draws a `TraceSet`; the "Relative to" box; read-out and fit view over all visible traces |
| `src/bodeplot/gui/main_window.py` | change | the new dock and its View-menu entry; a new sweep clears only the live trace; loading files |
| `src/bodeplot/io/export_image.py` | change | draws the visible traces with a legend |
| `docs/ARCHITECTURE.md`, `docs/spec/gui.md` (section 10), `README.md`, `docs/STATE.md` | change | documentation; the architecture guard gets the new modules |

`traces.py` knows nothing about the plot; the plot and the image export both ask it "what is to be drawn" (for each visible trace: name, colour slot, frequencies, complex values, the measured points if any). That keeps the relative maths in one place and testable without a display.

The plot widget's present interface for the live sweep (`add_point`, `set_points`, `points`, `clear`) stays, so the sweep code in the main window and the existing GUI tests keep working.

## 7. GUI

- **Traces panel**, a dock like Configuration, Waveform and Status log, listed in the View menu and brought back by "Reset layout". It sits under the Waveform panel by default. One row per trace: visibility tick, colour swatch, name, kind. Buttons: **Load CSV…** (one or several files), **Add theory…**, **Keep sweep** (enabled when the live trace has points), **Remove** (enabled for a trace that can be removed). Renaming: edit the name in the row.
- **Relative to** box in the row above the plot, next to the Vertical box.
- **Hover read-out:** the nearest point among all visible traces, with the trace's name in front.
- **Fit view** and follow mode cover all visible traces as drawn (relative or absolute).
- **Re-measure** (click on a point) is offered on points of the live trace only.
- **Flagged points** of kept and file traces are drawn as crosses, as for the live sweep.
- Loading a file never touches the instruments and is allowed while a sweep runs.
- **Errors when loading:** a file that cannot be read, is not a sweep CSV or holds no points is refused with one message naming the file and the reason; the other files of the same selection still load.

## 8. Exports

- **Image (PNG, SVG, PDF):** what the plot shows: all visible traces, in their colours (print-safe on the white background), with a legend when there is more than one, relative or absolute as selected, with the matching axis labels. The footer still describes the live sweep; in relative display it also names the reference.
- **CSV, Touchstone:** unchanged, the live sweep only.

## 9. Tests (no hardware)

- `theory`: every preset against its closed formula at several frequencies; custom coefficients; invalid input refused; `SimulatedDUT` unchanged (the existing sweep tests).
- `traces`, without a display: adding, keeping, removing, renaming with unique names; colour slots (lowest free, live keeps slot 1, a ninth trace is muted); `relative` exact on a shared grid, interpolated on a different grid, nothing outside the reference's range, phase across ±180°, a zero or non-finite reference value; a theory reference evaluated exactly; the grid of a theory trace follows the other traces and the sweep settings.
- Files: a good CSV, one with only gain and phase columns, a damaged file, an empty one, several at once with one bad among them.
- GUI offscreen: load a file, add and edit a theory curve, keep a sweep, hide and remove, a new sweep leaves the other traces, relative to a theory curve reproduces the hand comparison of an RC low-pass within the measurement noise, the Voltage unit rules, the read-out names the trace, image export with several traces and in relative display.
- The existing suite stays green; with no extra trace the plot and the exports are as before (success criterion 3).

## 10. Acceptance

No bench work: nothing here touches an instrument. The stop point is the user's review of the GUI (roadmap, milestone A3), in Simulation mode or with their own CSV files, for example `gui_rc.csv` of `HW_REPORT.md` 14.3 against an RC low-pass theory curve of 997.8 Ω and 98.2 nF.
