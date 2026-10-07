# Auto markers and user markers: design

Date: 2026-10-07. Status: **design agreed with the user in conversation on 2026-10-07 ("Yes continue"); this file awaits the user's review.** Not built; the next step after approval is the implementation plan. It is milestone A4 of the roadmap (`docs/spec/roadmap.md` sections 15 and 16), the last milestone of v2.

## 1. Purpose

Today a value is read from the plot by moving the mouse over a point: the read-out row shows that point. Finding a cut-off frequency, a resonance or a stability margin means hunting for the right point by hand, and between two points there is no value at all.

A4 puts markers on the plot. Automatic markers find the −3 dB points, the peak, the notch and the gain and phase margins of one trace. User markers stand at any frequency and read gain and phase there, also as a difference to a reference marker.

What the user chose:

| Question | Decision |
|---|---|
| Which markers | All four of the roadmap: −3 dB cut-off(s), peak / notch, gain and phase margin, user markers. |
| Which trace they measure | One chosen trace ("Markers on"), the live sweep by default. |
| What −3 dB counts down from | The highest gain of the trace. No level to type, no automatic passband detection (that is v3, B1). |
| Where the values are read | Written on the plot next to each marker. No Markers panel. |
| Where the controls are | A "Markers" button above the plot, next to Fit view; user markers also from the plot's right-click menu. |
| Where a user marker can stand | At any frequency inside the trace; values between points are interpolated. |
| Difference between markers | Yes: one user marker can be the reference marker, the others show their difference to it and the slope. |
| Outside the screen | In the exported image, and as a text list that can be copied. Not in the CSV, not in the status log. |

Success criteria:

1. On a sweep of the RC low-pass, ticking "−3 dB" shows fc within 2 % of 1 / (2πRC) with no further input.
2. On an RLC band-pass the peak, both −3 dB edges, the bandwidth and Q agree with theory.
3. A user marker typed to 1 kHz stands at exactly 1 kHz and reads the interpolated gain and phase.
4. With no marker switched on, the app looks and behaves as it does today.

## 2. What it does not do

- No Markers panel and no table on screen (the copied list is the table).
- No reference level or drop to type: always 3 dB below the highest gain.
- No passband detection, ripple, stopband attenuation, order or classification (v3, B1 and B2).
- Markers on one trace at a time, never on several.
- User markers are not remembered between runs and are not part of a preset.
- Nothing is written to the CSV or Touchstone exports or to the status log.
- Nothing reaches the instruments: no bench run belongs to this milestone.

## 3. What a marker reads

A marker reads the **chosen trace as it is drawn**:

- With "Relative to" set, the markers measure the difference curve (the trace divided by the reference trace). The peak of a difference curve is where the two traces differ most.
- A hidden trace has no markers. When the chosen trace is removed, the choice falls back to the live sweep.
- All marker maths is done on the gain in dB and on the unwrapped phase in degrees, whatever the vertical unit and whatever the "Unwrap phase" box says. The phase is unwrapped from the first usable point, which keeps its value between −180° and +180°.
- The label shows the gain in the selected vertical unit (dB, % or Vpp) and the phase as the phase plot shows it (wrapped or unwrapped).
- With the vertical unit Voltage, the marker rules still work on the gain (output / input): "−3 dB" is 70.7 % of the highest gain, not of the highest voltage. The label shows the voltage at that frequency. A theory curve is not drawn in Voltage and has no markers there.

**Between two points** the gain in dB and the unwrapped phase are interpolated linearly over the logarithm of the frequency. This is the rule the reference trace of A3 uses (`traces._Reference`); the new module holds it once and `traces.py` uses it from there. In Voltage the output voltage is interpolated the same way (its logarithm, linearly over log frequency).

**Dead points and gaps.** A point with |H| zero or not finite is skipped. The stretch between a dead point and its neighbours is a gap: no value is interpolated across it, no crossing is found in it, and a user marker inside it says "no value here".

**Flagged points** are used like any other (the plot draws them too). A marker whose value comes from a flagged point, or from between two points of which one is flagged, carries "(flagged)" in its label. The quiet flags of the plot (`QUIET` in `gui/bode_plot.py`) do not count.

**While a sweep runs** the markers are computed again with every new point, so they move as the curve grows.

## 4. Automatic markers

Each kind is switched on or off in the Markers menu. All are off at the first start.

### 4.1 Peak (`pk`) and notch (`nt`)

- The peak is the highest gain of the trace, the notch the lowest.
- The position is refined with a parabola through the extreme point and its two neighbours (gain in dB over log frequency), when both neighbours exist and no gap lies between the three. The phase is read at the refined frequency by the rule of section 3.
- A marker is shown only when the extreme is a real one: it is not the first or the last point of the trace, and it stands at least 1 dB above (peak) or below (notch) the gain at both ends of the trace. A low-pass therefore has no peak marker and no notch marker.
- Label: `pk 1.59 kHz  −0.02 dB  +0.3°`.

### 4.2 −3 dB (`fc`, or `fL` and `fH`)

- The level is the highest gain of the trace minus 3 dB. The highest gain is the refined peak value when a peak marker exists by the rule of 4.1 (ticked or not), otherwise the highest point.
- Going down in frequency from the maximum, the first place where the curve crosses the level is the lower edge; going up, the first crossing is the upper edge. Crossings further out are not looked for, so noise in a stopband adds no markers. The crossing frequency is interpolated by the rule of section 3.
- One edge found: it is named `fc` (low-pass or high-pass). Two edges: `fL` and `fH`, and the label of `fH` carries a second line with the bandwidth BW = fH − fL and Q = √(fL·fH) / BW.
- No edge found (the curve never falls 3 dB inside the range): nothing is drawn.
- Label: `fc 1.62 kHz  −3.01 dB  −45.2°`; second line of `fH`: `BW 820 Hz  Q 1.94`.

### 4.3 Gain margin (`GM`) and phase margin (`PM`)

Both are switched by the one menu item "Margins". The trace is taken as the loop gain L itself (see section 10, point 1).

- **Phase margin:** at each frequency where the gain crosses 0 dB, PM = 180° + phase. With several crossings the one with the smallest margin is shown. The marker's dot and label are on the phase plot: `PM 48.3° at 3.10 kHz`.
- **Gain margin:** at each frequency where the unwrapped phase crosses −180° (or −180° − k·360°), GM = −gain in dB. With several crossings the one with the smallest margin is shown. The dot and label are on the gain plot: `GM 12.4 dB at 20.0 kHz`.
- A margin with no crossing inside the range is not drawn.
- With "Relative to" set, or with no phase (magnitude-only method), the margins are not computed; the menu item stays ticked and its tooltip says why nothing is shown.

## 5. User markers

- Named `M1`, `M2`, …; a new marker takes the lowest free number. At most 8.
- Each is stored as a frequency. Its gain and phase are read from the chosen trace at that frequency by the rule of section 3.
- **Adding:** right-click on a plot > "Add marker here" (at the clicked frequency), or Markers > "Add marker" (in the middle of the visible frequency range).
- **Moving:** drag the marker's line with the mouse; the label follows while dragging. Or right-click the marker > "Set frequency…" and type a value with the SI entry the panel uses (1k, 2.5M).
- **Removing:** right-click the marker > "Remove", or Markers > "Remove all markers" (user markers only; the ticks of the automatic markers stay).
- **Outside the trace:** a marker beyond the first or last point of the trace keeps its line, and its label says `M1 50.0 MHz  outside the trace`.
- **Reference marker:** right-click a user marker > "Reference marker" (a tick; clicking it again clears it). Its label gets "(ref)". Every other user marker then shows a second line with its difference to the reference: `Δ M1  ×10.0  −20.1 dB  −71.0°  −20.1 dB/dec`. The first value is the frequency ratio, the last the slope (Δ dB divided by the decades between the two); the slope is left out when the two stand within 0.1 % of each other. Removing the reference marker clears the choice. In Voltage the Δ dB is still the difference of the gains.
- Label: `M2 5.00 kHz  −10.4 dB  −72.3°`.

## 6. On the plot

- Each marker is a thin dashed vertical line through both plots, a dot on the curve where it reads its value (gain plot and phase plot; `GM` only on the gain plot, `PM` only on the phase plot), and its label next to the dot on the gain plot (`PM`: on the phase plot).
- Labels that would overlap are moved down row by row until they are free.
- One neutral marker colour, added to `gui/theme.py`; it is not a series colour. Every marker carries its name in the label, so nothing rests on colour.
- The lines of the automatic markers cannot be dragged. The mouse read-out row, the hover tooltips of the points and the re-measure click work as before; marker items lie below the live sweep's points so that they never take a click meant for a point.
- "Fit view" and follow mode ignore the markers: a user marker far outside the data does not widen the view.

## 7. The Markers button

A push button "Markers" in the row above the plot, after "Fit view". It opens a menu:

| Item | Does |
|---|---|
| −3 dB (tick) | section 4.2 |
| Peak (tick) | section 4.1 |
| Notch (tick) | section 4.1 |
| Margins (tick) | section 4.3 |
| Markers on > (submenu) | the traces by name, one ticked; live sweep first |
| Add marker | section 5 |
| Remove all markers | section 5 |
| Copy marker values | section 8 |

- Every item has a tooltip, shown with the app's tooltip delay and switch (`tests/test_gui_tooltips.py` is extended to cover menu items of this menu). The button itself has one too.
- The plot's right-click menu is new: on an empty place "Add marker here"; on a user marker "Set frequency…", "Reference marker", "Remove". The re-measure menu of a point stays on the left click, as today.
- The button adds one button's width to the row and nothing whose text changes, so the row's minimum width stays fixed (the layout fault of A3 does not come back).
- The four ticks are stored in the settings file (`markers`: a list of the kinds that are on) and restored at the next start, like the vertical unit. The chosen trace and the user markers are not stored.

## 8. Copy and image export

**Copy marker values** puts a tab-separated table on the clipboard, one row per marker that is switched on, in the order −3 dB, peak, notch, margins, user markers:

```
Markers on: Sweep
Marker	Frequency (Hz)	Gain (dB)	Phase (deg)	Note
fL	1234.5	-3.010	45.00
fH	2054.1	-3.010	-45.00	BW 819.6 Hz, Q 1.94
pk	1591.5	0.000	0.00
PM	3100.0	0.000	-131.70	phase margin 48.30 deg
M2	5000.0	-10.400	-72.30	rel. M1: x10, -20.1 dB, -71.0 deg, -20.1 dB/dec
```

An automatic marker that is switched on and does not exist gets a row with "none" in the note and empty values. With "Relative to" set, the first line says so (`Markers on: Sweep, relative to RC low-pass 1 kΩ 100 nF`). Numbers are written with a decimal point and no unit prefix, so a spreadsheet reads them.

**Image export.** The exported PNG / SVG / PDF shows the markers as the screen does: the vertical lines, the dots and the labels, in a dark grey for the white background. `BodePlot` hands the export a list of markers with their final positions and texts, as it already hands over the series (`export_series`); the export decides nothing about them.

## 9. Structure

| Module | Role | Depends on |
|---|---|---|
| `measure/response.py` (new) | Pure functions on one curve: build a curve from frequencies and complex values (with dead points and gaps), value at a frequency, crossings of a level in gain or in phase, refined maximum and minimum. No Qt, no knowledge of traces or markers. Written so that v3 (B1 response metrics) builds on it. | `math` only |
| `markers.py` (new) | `MarkerSet`: the kinds switched on, the user markers, the reference marker, the chosen trace id. `evaluate(curve)` returns the markers with their numbers (name, frequency, gain, phase, which plot, note, difference). The rules of sections 4 and 5 live here. No Qt. | `measure/response.py` |
| `traces.py` | `_Reference` takes its interpolation from `measure/response.py` in place of its own copy; behaviour unchanged, its tests stay as they are. | adds `measure/response.py` |
| `gui/marker_layer.py` (new) | `MarkerLayer`: the graphics of the markers on the two plots, label placement, dragging, the right-click menus. Formats the label texts in the selected unit. | `markers.py`, `theme`, pyqtgraph |
| `gui/bode_plot.py` | Owns a `MarkerSet` and a `MarkerLayer`; the Markers button and its menu; at the end of `refresh()` hands the chosen trace's drawn curve to the layer; `export_markers()`, `marker_text()` for the clipboard. | the two above |
| `io/export_image.py` | `ImageMarker` (frequency, plot, y, text) and its drawing in `write_image`. | unchanged imports |
| `gui/main_window.py` | Passes the markers to the image export; loads and stores the `markers` setting. | unchanged imports |

`docs/ARCHITECTURE.md` gets the three new modules and the changed import of `traces.py` (its test fails until it does). `docs/spec/gui.md` section 10 gets the markers; `docs/SPEC.md` no longer lists auto markers as deferred.

Errors: marker maths never raises on data. A curve with fewer than two usable points has no automatic markers; every rule that finds nothing returns nothing. A typed frequency that is not a positive number is refused in the "Set frequency…" dialog and the marker stays where it was.

## 10. Decided by me, to be checked by the user

1. **Phase margin convention.** The trace is taken as the loop gain L, so PM = 180° + phase at the 0 dB crossing and GM is read where the phase crosses −180°. A setup that measures the inverted loop gain (−L, common with an injection transformer when the two probes sit on either side of the injection point) would read 180° off. The question was put to the user on 2026-10-07 and not answered; if they measure that way, an "Inverted loop" tick item is added to the menu. Not built until asked for.
2. **Voltage unit:** the rules work on the gain, the label shows volts (section 3).
3. **Peak and notch need 1 dB of prominence** over both ends of the trace and must not be an end point (section 4.1).
4. **Only the two −3 dB crossings nearest to the maximum** are marked (section 4.2).
5. **The smallest margin** is shown when there are several crossings (section 4.3).
6. **At most 8 user markers**; the four ticks are remembered between runs, the user markers are not (sections 5 and 7).

## 11. Tests

Pure maths (`tests/test_response.py`, `tests/test_markers.py`), each against the closed-form value of the simulated DUT (`measure/theory.py`):

- RC low-pass and RC high-pass on the sweep grid of 20 points per decade: `fc` within 2 % of 1 / (2πRC), phase there −45° / +45° within 1°; no peak, no notch.
- RLC band-pass: `pk` within 1 % of f0 and within 0.1 dB; `fL`, `fH`, BW and Q within 3 %.
- RLC notch: `nt` at f0 within 1 %; no peak.
- A three-pole loop gain (custom H(s)) with known crossover frequencies: PM within 1°, GM within 0.2 dB; the smallest margin is taken with two crossings; a phase that passes −180° only after unwrapping is found.
- Butterworth low-pass: `fc` at the cutoff within 1 %.
- The same curves with 0.05 dB and 0.3° of noise added (seeded): results within doubled tolerances; no extra −3 dB markers in the stopband.
- Edge cases: empty trace, one point, all points dead, a gap at the crossing, the maximum at the first and at the last point, a flat curve (through), no 0 dB crossing, a user marker outside the trace, inside a gap and exactly on a point, the reference marker removed, two markers at the same frequency (no slope).
- `traces.py`: its existing tests pass unchanged after the interpolation moves.

GUI, offscreen (`tests/test_gui_markers.py`):

- The menu ticks switch each kind on and off and the items appear and disappear; "Markers on" changes the trace and the values; a removed trace falls back to the live sweep; a hidden trace shows none.
- Add at a frequency, set frequency, drag (the layer's own handler called with a position), remove, remove all, the limit of 8.
- Reference marker: the second label line; cleared when that marker is removed.
- Relative view, the three vertical units, wrapped and unwrapped phase: positions and label texts.
- Markers follow a running sweep (points added one by one).
- Labels that would overlap are on different rows.
- The view range of "Fit view" is the same with and without markers.
- Copy: the clipboard text for a known curve. Image export: the three formats are written with markers and the SVG holds the label texts.
- The `markers` setting survives a restart; a settings file without it starts with all four off.
- Tooltips: every item of the Markers menu and of the two right-click menus has one.
