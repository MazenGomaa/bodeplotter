# Response metrics and the Analysis tab: design

Date: 2026-10-07. Status: **design, waiting for the user's review; nothing is built.** It is part 1 of v3 (milestone B1 of the roadmap, `docs/spec/roadmap.md` sections 15 and 16, with a first Analysis tab taken forward from B4).

## 1. Purpose

The markers of v2 find single points of a trace: the −3 dB points counted from the highest gain, the highest peak, the deepest notch. They do not know what a passband is, they see one resonance only, and they give no slope, no order and no stopband attenuation.

Part 1 reads the shape of one trace and reports its numbers in a table: the flat stretches, the cut-offs, the slope and the order, the stopband attenuation, and every resonance with its Q. The same numbers of a second trace (a theory curve, an earlier sweep) stand next to them with the difference.

What the user wants it for (2026-10-07): checking their own filters against the design values, identifying unknown circuits, and finding resonances in LC circuits, all equally. The circuits: passive RC / RL / RLC, active op-amp filters, LC ladders and crystal or ceramic filters, amplifiers and loops.

What the user chose:

| Question | Decision |
|---|---|
| How v3 is cut | Five parts, each with its own design, plan and build, each ending with something to see: 1 metrics (this document), 2 finer sweep around a found feature, 3 classification, 4 rational fit, 5 the analysis in the exports. This replaces their first choice of one v3 design ("this is getting bigger"). |
| What −3 dB counts down from | The flat passband level, in the analysis and in the −3 dB marker, so the app shows one cut-off. Without a flat stretch: the highest gain, as today. |
| When the analysis runs | Only on a button ("Analyse"). |
| Resonances | Every peak and every notch gets its own row with f0 and Q; Q also from the phase. |
| Comparison | The numbers of a second trace next to the first, with the difference (their case: a 1 kΩ / 100 nF theory low-pass against the real sweep). |
| Language | Python and numpy stay. No C++ or Rust: a point costs 1.05 s in the scope, the analysis milliseconds. |

Success criteria:

1. On a sweep of the RC low-pass, Analyse shows the passband level within 0.1 dB, fc within 2 % of 1 / (2πRC), a slope that rounds to order 1, and no resonance.
2. On the RLC band-pass it shows f0, both cut-offs, bandwidth and Q in agreement with theory, and Q from the phase within 10 % of Q from the width.
3. On a low-pass with a hump (a second-order low-pass with Q = 2) the cut-off is counted from the flat level, the −3 dB marker stands at the same frequency, and the hump is one resonance row.
4. With a theory curve chosen under "Compare with", the difference column shows how far the measured cut-off lies from the theoretical one, in percent.
5. A trace with two resonances gives two resonance rows.
6. Nothing is computed, and nothing in the app changes, until Analyse is pressed; the one exception is the −3 dB marker's new rule.

## 2. What it does not do

- No type name (low-pass, band-pass ...) and no confidence figure: part 3.
- No finer sweep: part 2. Part 1 only says where one is needed ("too few points on the resonance at 15.9 kHz").
- No fit, no poles and zeros: part 4.
- Nothing in the CSV or the image: part 5. The table can be copied as text.
- Nothing reaches the instruments. No bench run.
- No settings for the thresholds of section 3. They are constants; they move into the Advanced settings only if they prove touchy.
- No part values from f0 (L from a known C): the user did not pick it.

## 3. The metrics

All of it works on one `Curve` (`measure/response.py`): gain in dB and unwrapped phase over frequency, a dead point has no value and a gap is not bridged. "Slope" always means the slope of a least-squares line through the points of a window, gain in dB over log10 of the frequency, so one noisy point does not decide it. A window never reaches across a gap.

### 3.1 Flat stretches

A point is flat when the line through the points within a sixth of a decade on either side of it (a third of a decade in all) is no steeper than 3 dB/decade. A flat stretch is a run of flat points that

- spans at least a third of a decade and has at least five points, and
- stays within 3 dB from its lowest to its highest gain. A run that drifts further is cut where it leaves the 3 dB, and what remains is tested again.

Each stretch has: its frequency range; its **level**, the median gain of its points; its **ripple**, highest minus lowest gain; whether it touches the low or the high end of the curve.

The **passband level** is the level of the highest stretch. Every stretch whose level lies within 3 dB of it is a **passband**. A stretch at least 10 dB below the passband level is a **stopband floor**. A stretch in between is listed as a flat stretch and plays no further part.

A curve with no flat stretch (a resonant band-pass falls away from its top on both sides) has no passband in this sense. Then the passband level is the highest gain of the curve, refined as the markers refine a peak, the table says "level of the peak", and there is no ripple.

### 3.2 Cut-offs

The cut-off level is the passband level minus 3 dB. From each side of each passband that does not touch the end of the curve, the curve is followed outwards to the first point at or below the cut-off level; the cut-off lies between that point and the one before it, interpolated. Without a flat stretch the curve is followed from the highest point to both sides, which is today's marker rule.

- One cut-off: `fc`.
- Two cut-offs that bound one passband (a band-pass) or the gap between two passbands (a band-stop): `fL` and `fH`, with the **centre** √(fL·fH), the **bandwidth** fH − fL and **Q** = centre / bandwidth.
- More than two: all are listed in ascending order; centre, bandwidth and Q are given for the pair around the highest gain.
- None: the table says "no cut-off inside the sweep".

### 3.3 Slope and order

For each cut-off, the **transition** is the stretch from the cut-off outwards to the first of: a stopband floor, a notch (3.5), the end of the curve, a gap. The slope is that of the steepest window of half a decade inside the transition; a transition shorter than half a decade is one window, and needs three points. The **order** is the slope divided by 20 dB/decade, rounded, at least 1.

The slope is "at least" (section 3.6) when the transition is shorter than half a decade, or when the steepest window is the last one before the end of the curve: the curve was still getting steeper.

### 3.4 Stopband attenuation

For each cut-off: the passband level minus the level of the stopband floor its transition ends in. With no floor, it is the passband level minus the lowest gain reached on that side, as "at least", with the note "still falling at the end of the sweep" when the transition ends at the end of the curve.

### 3.5 Resonances

A **peak** is a local maximum of the gain that stands at least 1 dB above the lowest point between it and the next higher ground on each side (or the end of the curve when there is none). A **notch** is the same upside down. Every peak and every notch is a resonance; they are listed in ascending frequency. The highest point of a curve that only falls or only rises is not a peak.

Each resonance has:

- **f0** and its gain, refined with the parabola through the extreme point and its two neighbours (`response.extremum`'s rule, made available for any point).
- **Height** (peak) or **depth** (notch): how far it stands clear of the higher of its two feet (peak) or the lower of its two shoulders (notch).
- **Q from the width.** Peak: f0 divided by the width between the two points 3 dB below its top, followed outwards from the top. Notch: f0 divided by the width between the two points 3 dB below its lower shoulder. No value when the resonance is not 3 dB high or deep on both sides (a 2 dB hump on a passband).
- **Q from the phase**, peaks only: half the slope of the unwrapped phase in radians over the natural logarithm of the frequency at f0, as a magnitude. The slope is that of the line through the points inside the −3 dB width, or through the extreme point and two neighbours on each side when that holds fewer than five points. For a single resonance this equals Q. No value in a magnitude-only measurement.
- **Points across it:** the number of points inside its −3 dB width (or within its height, when it has no such width). Fewer than five gives the note "too few points on the resonance at …: its top and its Q are uncertain". Part 2 hangs its finer sweep on this note.

### 3.6 How far a number holds

- **Limits.** A number the end of the sweep or a short transition cut short carries "at least": "attenuation at least 42 dB", "slope at least −38 dB/dec, order at least 2".
- **Flagged points** take part: a flag such as "skew unchecked" marks a whole sweep, and leaving flagged points out would leave nothing. A number is marked flagged when one of the points it rests on is flagged (the points of the stretch, the two points around a cut-off, the points of the slope window, the points across a resonance). The share of flagged points of the curve is kept for part 3.
- **Too little.** Fewer than five usable points: no analysis, the table says why.

### 3.7 The −3 dB marker

`markers._cutoffs` takes its level and its frequencies from the cut-offs of 3.2: one gives `fc`; two or more give `fL` and `fH`, the pair around the highest gain, with bandwidth and Q as today. On a curve with no flat stretch that is exactly today's rule. The marker keeps reading the curve as the plot shows it (relative display, Voltage rows), and it does not wait for the Analyse button.

## 4. The Analysis tab

A third dock, "Analysis", as a tab behind Traces and Markers on the right. From top to bottom:

- **Trace**: the trace to analyse; the live sweep first. **Compare with**: "off" first, then every other trace.
- **Analyse** button, and **Copy table**.
- One line saying what the table belongs to: the trace's name and the time of the analysis. When that trace (or the compared one) has changed, was removed or is being swept since, the line adds "trace changed since this analysis". The table stays as it is until Analyse is pressed again.
- The **table**. Columns: the quantity, Value, Compare, Difference; the last two are hidden with "Compare with" off. Rows in groups, a group with nothing to say is left out:
  - Passband: level, ripple, range (one set per passband when there are two).
  - Cut-off: `fc`, or `fL` and `fH`.
  - Centre, bandwidth, Q.
  - Slope and order, per cut-off.
  - Stopband attenuation, per cut-off.
  - Resonances: one row each, "peak" or "notch" with f0, height or depth, Q (width), Q (phase), points.
- **Notes** under the table: too few points on a resonance, still falling at the end of the sweep, no cut-off inside the sweep, numbers resting on flagged points, why there is no analysis.

Rules:

- The analysis reads the trace itself: gain in dB and phase, whatever the plot's vertical unit and "Difference to trace" are set to.
- Difference: a frequency, a bandwidth and a Q as a percentage of the compared value; a level, a ripple, an attenuation and a slope as a plain difference. Cut-offs pair up by their side; a resonance pairs with the nearest resonance of the same kind of the other trace within a factor of 1.2 in frequency, otherwise its Compare cell is empty.
- A limit reads "≥ 42 dB"; a flagged number carries the mark the markers use.
- Every control and every row group has a tooltip that states its rule (the user's rule of 2026-10-07; `tests/test_gui_tooltips.py`).
- The analysis runs in the GUI thread: it is a few passes over a few hundred points.
- Nothing is remembered between runs of the app: no settings.
- The dock changes the default arrangement, so `LAYOUT_VERSION` goes to 3 and a stored layout of the old arrangement is dropped once.

## 5. Structure

| File | Change |
|---|---|
| `measure/metrics.py` (new) | the maths of section 3 on a `Curve`: `analyse(curve) -> Metrics`, with `Band`, `Cutoff`, `Resonance` and `Value` (a number, its limit, flagged). No Qt, imports `measure/response.py` only. Written to be read by parts 2 and 3. |
| `measure/response.py` | `refine(curve, index, highest)`: the parabola of `extremum` for any point; `extremum` uses it. A windowed slope helper. |
| `analysis.py` (new) | the rows and texts of the table for one `Metrics` or two, the difference rule, the clipboard text. No Qt. |
| `markers.py` | `_cutoffs` follows section 3.7. |
| `gui/analysis_panel.py` (new) | `AnalysisPanel`: the controls, the table, the stale line. It asks `TraceSet.curve(id, relative=False)` for the curves. |
| `gui/main_window.py` | the dock, the View menu entry, `LAYOUT_VERSION` 3. |
| `docs/ARCHITECTURE.md`, `docs/spec/gui.md`, `README.md`, `docs/STATE.md` | the new modules and the tab. |

## 6. Decided by me, to be checked by the user

1. The thresholds: flat is at most 3 dB/decade over a third of a decade; a stretch needs a third of a decade, five points, and stays within 3 dB; a stopband floor lies 10 dB or more below the passband; a resonance stands 1 dB clear; the slope window is half a decade; "too few points" is fewer than five.
2. The level of a stretch is the median, not the mean: a hump at its edge does not pull it.
3. With no flat stretch the passband level is the peak. So a resonant band-pass keeps today's cut-offs.
4. Q from the phase is given for peaks only. At a notch the phase steps by up to 180° and its slope there belongs to the zeros, not to the Q of the resonance; a number would mislead.
5. The analysis always reads the trace in dB and absolute, independent of the plot's unit and of "Difference to trace".
6. Resonances pair up across the two traces within a factor of 1.2.
7. The table is not remembered, and there is no setting.
8. The −3 dB marker can move on traces that have a flat stretch and a peak above it; that is the point of the user's decision, and it is the one change a user sees without pressing Analyse.

## 7. Tests

Pure maths (`tests/test_metrics.py`), each against the value theory gives:

- every simulated DUT: through (one passband touching both ends, no cut-off), RC low-pass and high-pass, RLC band-pass and notch, Butterworth second order;
- built in the tests with `TransferFunction.custom`: a Chebyshev low-pass with 1 dB ripple, a second-order low-pass with Q = 2 (hump), a fifth-order low-pass, a band-pass from a low-pass and a high-pass with a flat top, a model with two resonances (a crystal's series and parallel resonance), an amplifier (20 dB flat, one pole);
- each of them clean, with noise of the size of the bench (0.02 dB, 0.1°) and of ten times that, with flagged points, with dead points and a gap, and with a span that cuts the response short (limits);
- too few points; a resonance with three points across it (the note);
- Q from the phase against Q from the width on the RLC band-pass at Q = 1, 10 and 50;
- a time limit: a curve of 500 points is analysed in under 0.5 s.

Markers (`tests/test_markers.py`): the hump low-pass gives `fc` from the flat level; every existing test still passes.

Texts (`tests/test_analysis.py`): rows, limits, flagged marks, the difference rule, pairing of resonances, the clipboard text.

GUI offscreen (`tests/test_gui_analysis.py`): nothing computed before Analyse; the table after it; Compare columns; the stale line after a new sweep and after a trace was removed; Copy table; tooltips; the dock in the default layout.
