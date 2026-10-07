# Response metrics and the Analysis tab: design

Date: 2026-10-07. Status: **design approved by the user on 2026-10-07 ("Approved, remember to check design rules for ui, colors, interface and so on"); nothing is built; plan `docs/superpowers/plans/2026-10-07-response-metrics.md`.** It is part 1 of v3 (milestone B1 of the roadmap, `docs/spec/roadmap.md` sections 15 and 16, with a first Analysis tab taken forward from B4).

**Changed after the approval, while planning.** The rules were tried in a throw-away prototype against the theory circuits before the plan was written (clean, 2 800 noisy curves, 3 000 odd inputs). Seven rules of the approved text gave wrong or unusable answers and were replaced; the text below is the corrected one, and the user is to confirm these with the plan:

1. **Slope and order (3.3):** the approved text took the steepest half-decade window. That gave order 7 for a fifth-order Chebyshev and order 3 for a single resonance (both are steepest right next to the passband). It is now the slope the roll-off settles to: the median over all windows.
2. **No slope into a notch (3.3):** a roll-off that ends in a notch (a notch filter, an elliptic stop band) has no slope that means an order. It gets none.
3. **Ripple (3.1):** the approved text took highest minus lowest gain of the flat stretch, which reported the shoulder of every low-pass as ripple and missed a Chebyshev's ripple (its ripples are too steep to be "flat"). It is now measured between the cut-offs: the highest gain there minus the lowest dip, or minus the level when there is no dip.
4. **Level (3.1):** the median of the flattest quarter of the stretch, not of all of it: the shoulder before a cut-off pulled the plain median 0.05 dB low, which is 1.3 % of an RC cut-off frequency.
5. **Resonances (3.5):** a peak or notch must also stand 8 times the local scatter clear (noise invented resonances otherwise), the top of a flat stretch is not a peak (a wide band-pass was listed as a resonance with Q 0.03), and Q from the phase uses the law of a single resonance on pairs of points, not a straight line (the line read 15 to 20 % low at every Q).
6. **Table (4):** a resonance is a group of rows, not one row: its five numbers do not fit the columns Value, Compare, Difference. The notes take four lines at most.
7. **A new note (3.6):** a passband seen over less than a decade at an end of the sweep makes the level, and with it the cut-off, uncertain; the table says so.

Also found there: with the bench's noise (0.02 dB) the cut-off of an RC scatters by 0.45 % from sweep to sweep, because it is found between two points. That is for part 2 (a finer sweep, and a line through many points).

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
| Resonances | Every peak and every notch gets its own rows with f0 and Q; Q also from the phase. |
| Comparison | The numbers of a second trace next to the first, with the difference (their case: a 1 kΩ / 100 nF theory low-pass against the real sweep). |
| Language | Python and numpy stay. No C++ or Rust: a point costs 1.05 s in the scope, the analysis 6 ms for 400 points (measured in the prototype). |
| Look | The design rules of the app hold: every colour from `gui/theme.py`, every option with a tooltip, the window still fits a 1280 px screen, the result reviewed with the frontend-design skill. |

Success criteria:

1. On a sweep of the RC low-pass, Analyse shows the passband level within 0.1 dB, fc within 2 % of 1 / (2πRC), a slope that rounds to order 1, and no resonance.
2. On the RLC band-pass it shows f0, both cut-offs, bandwidth and Q in agreement with theory, and Q from the phase within 10 % of Q from the width.
3. On a low-pass with a hump (a second-order low-pass with Q = 2) the cut-off is counted from the flat level, the −3 dB marker stands at the same frequency, and the hump is one resonance.
4. With a theory curve chosen under "Compare with", the difference column shows how far the measured cut-off lies from the theoretical one, in percent.
5. A trace with two resonances shows both.
6. Nothing is computed, and nothing in the app changes, until Analyse is pressed; the one exception is the −3 dB marker's new rule.

## 2. What it does not do

- No type name (low-pass, band-pass ...) and no confidence figure: part 3.
- No finer sweep: part 2. Part 1 only says where one is needed ("too few points on the peak at 15.9 kHz").
- No fit, no poles and zeros: part 4.
- Nothing in the CSV or the image: part 5. The table can be copied as text.
- Nothing reaches the instruments. No bench run.
- No settings for the thresholds of section 3. They are constants in `measure/metrics.py`; they move into the Advanced settings only if they prove touchy.
- No part values from f0 (L from a known C): the user did not pick it.

## 3. The metrics

All of it works on one `Curve` (`measure/response.py`): gain in dB and unwrapped phase over frequency, a dead point has no value and a gap is not bridged. "Slope" always means the slope of a least-squares line through the points of a window, gain in dB over log10 of the frequency, so one noisy point does not decide it. A window never reaches across a gap; at an end of the curve it is moved inwards, not cut.

### 3.1 Flat stretches, level and ripple

A point is flat when the line through the points of a window of a third of a decade around it is no steeper than 3 dB/decade. A flat stretch is a run of flat points that

- spans at least a third of a decade and has at least five points, and
- stays within 3 dB from its lowest to its highest gain. A run that drifts further is cut where it leaves the 3 dB, and what remains is tested again.

Each stretch has its frequency range, its **level** (the median gain of its flattest quarter, at least three points, so that the shoulder before a cut-off or the foot of a hump does not pull it), and whether it touches the low or the high end of the curve.

The **passband level** is the level of the highest stretch. Every stretch whose level lies within 3 dB of it is a **passband**. A stretch at least 10 dB below the passband level is a **stopband floor**. A stretch in between plays no further part.

The **ripple** is measured over each passband out to its own cut-offs: the highest gain there, minus the lowest dip that is at least 0.1 dB deep, or minus the level when there is no dip. A hump before the cut-off counts: the ripple of a low-pass with a 6 dB hump is 6 dB.

A curve with no flat stretch (a resonant band-pass falls away from its top on both sides) has no passband in this sense. Then the passband level is the highest gain of the curve, refined as the markers refine a peak, the table says "Level (peak)", and there is no ripple.

Known limit: a sweep that starts less than about two decades below a first-order cut-off never sees the true level. From 1.2 decades below, the level reads 0.03 dB low and the cut-off 0.35 % high; from 0.7 decades below, 3 % high. A comparison with a theory curve over the same range cancels this, and section 3.6 has a note for the worst case.

### 3.2 Cut-offs

The cut-off level is the passband level minus 3 dB. From each side of each passband, the curve is followed outwards to the first point at or below the cut-off level; the cut-off lies between that point and the one before it, interpolated. The walk ends without a cut-off at the end of the curve, at a gap, and on reaching another passband. Without a flat stretch the curve is followed from the highest point to both sides, which is today's marker rule.

- One cut-off: `fc`.
- Two cut-offs: `fL` and `fH`, with the **centre** √(fL·fH), the **bandwidth** fH − fL and **Q** = centre / bandwidth. They bound one passband (a band-pass) or the gap between two (a band-stop).
- More than two: all are listed in ascending order as `f1`, `f2` ...; centre, bandwidth and Q are given for the pair around the highest gain.
- None: the notes say "No cut-off inside the sweep."

### 3.3 Slope and order

For each cut-off, the **roll-off** is the stretch from the cut-off outwards to the first of: a stopband floor, a notch (3.5), the end of the curve, a gap. The slope is taken over every window of half a decade inside it, and the **slope** of the roll-off is the median of those: the slope the curve settles to. A roll-off shorter than half a decade is one window, and needs three points. The **order** is the slope divided by 20 dB/decade, rounded, at least 1.

Slope and order are limits ("≥", section 3.6) when the roll-off is shorter than half a decade, or when it runs to the end of the curve and its outermost window is more than 2 dB/decade steeper than the median: the curve was still getting steeper.

A roll-off that ends in a notch gets no slope and no order.

### 3.4 Stopband attenuation

For each cut-off: the passband level minus the level of the stopband floor its roll-off ends in. With no floor, it is the passband level minus the lowest gain reached in the roll-off, as a limit, with the note that the sweep ends before the stop band levels off when the roll-off runs to the end of the curve.

### 3.5 Resonances

A **peak** is a local maximum of the gain that stands at least 1 dB above the lowest point between it and the next higher ground on each side (or the end of the run when there is none), and at least 8 times the scatter of the curve around it (estimated from the second differences of the gain over one decade). A **notch** is the same upside down. A point inside a flat stretch is neither. Every peak and every notch is a resonance; they are listed in ascending frequency. The highest point of a curve that only falls or only rises is not a peak.

Each resonance has:

- **f0** and its gain, refined with the parabola through the extreme point and its two neighbours (`response.refine`, the rule of `extremum` made available for any point). When the parabola moves the gain by 3 dB or more (three points far apart), the point itself is taken.
- **Height** (peak) or **depth** (notch): how far it stands clear of the higher of its two feet (peak) or the lower of its two shoulders (notch).
- **Q from the width.** Peak: f0 divided by the width between the two points 3 dB below its top, followed outwards from the top. Notch: f0 divided by the width between the two points 3 dB below its lower shoulder. No value when the resonance is not 3 dB high or deep on both sides (a 2 dB hump on a passband).
- **Q from the phase**, peaks only. Across a single resonance the phase turns by atan(Q·(f/f0 − f0/f)). Each pair of points, one below and one above f0, gives the Q that explains the phase turned between them; the answer is the median over the pairs inside the −3 dB width (with fewer than five points there: the two nearest points on each side). No value in a magnitude-only measurement.
- **Points:** the number of points inside its −3 dB width (without one: in its upper half). Fewer than five gives the note "Too few points on the peak at …: its top and its Q are uncertain; sweep finer around it." Part 2 hangs its finer sweep on this note.

### 3.6 How far a number holds

- **Limits.** A number the end of the sweep or a short roll-off cut short is a lower limit and reads "≥ 42.00 dB", "≥ −38.0 dB/dec", "≥ 2".
- **Flagged points** take part: a flag such as "skew unchecked" marks a whole sweep, and leaving flagged points out would leave nothing. A number is marked "(flagged)" when one of the points it rests on is flagged (the points of the passbands, the two points around a cut-off, the points of the roll-off, the points across a resonance). The share of flagged points of the curve is kept for part 3.
- **A short passband.** A passband that touches an end of the sweep and spans less than a decade gets the note that its level, and with it the cut-off, is uncertain, and to start the sweep lower (higher).
- **Too little.** Fewer than five usable points: no analysis, the notes say why.

### 3.7 The −3 dB marker

`markers._cutoffs` takes its level and its frequencies from the cut-offs of 3.2 (`metrics.passband`, `metrics.marker_pair`): one gives `fc`; two give `fL` and `fH` with bandwidth and Q as today; of more, the pair around the highest gain. On a curve with no flat stretch that is exactly today's rule. The marker keeps reading the curve as the plot shows it (relative display, Voltage rows), and it does not wait for the Analyse button.

What a user sees change: a low-pass or high-pass with a hump gets the textbook cut-off; a notch filter gets both edges (`fL`, `fH`, bandwidth, Q) where it had one; on a plain low-pass the marker moves by a few hundredths of a dB (the level is that of the flat part, not the single highest point).

## 4. The Analysis tab

A third dock, "Analysis", as a tab behind Traces and Markers on the right. From top to bottom:

- **Trace**: the trace to analyse; the live sweep first. **Compare with**: "off" first, then every trace.
- **Analyse** button, and **Copy table**.
- One line saying what the table belongs to: the trace's name (and the compared one's) and the time of the analysis. When one of them has changed, was removed or is being swept since, the line turns into a warning and adds "trace changed since this analysis". The table stays as it is until Analyse is pressed again. Before the first press the line says to press Analyse.
- The **table**. Columns: Quantity, Value, Compare, Difference; the last two are hidden with "Compare with" off or set to the analysed trace itself. Rows stand in groups under a quiet title line; a group with nothing to say is left out:
  - Passband: Level (or "Level (peak)"), Ripple, Flat from, Flat to (numbered when there are two passbands).
  - Cut-off: `fc`, or `fL` and `fH`.
  - Band: Centre, Bandwidth, Q.
  - Roll-off: "Slope, fc" and "Order, fc" per cut-off.
  - Stopband: "Beyond fc" per cut-off.
  - One group per resonance, titled "Peak at 15.91 kHz" or "Notch at …": f0, Gain at f0, Height or Depth, Q (width), Q (phase) for a peak with phase, Points.
- **Notes** under the table, four lines at most (more are scrolled): no flat stretch, a short passband, no cut-off inside the sweep, the sweep ends before the stop band levels off, too few points on a resonance, the share of flagged points, why there is no analysis. Of the compared trace only that it has no analysis.

Rules:

- The analysis reads the trace itself: gain in dB and phase, whatever the plot's vertical unit and "Difference to trace" are set to.
- Difference: a frequency, a bandwidth and a Q as a percentage of the compared value; a level, a ripple, an attenuation and a slope as a plain difference; an order as a count. Nothing where one side is missing or only a limit. Rows pair up by their name (`fc` with `fc`); a quantity only one trace has keeps its row with the other cell empty. A resonance pairs with the nearest resonance of the same kind of the other trace within a factor of 1.2 in frequency; otherwise each has its own group.
- A number that rounds to zero reads "+0.00", never "−0.00".
- The figures are right-aligned and keep their width; the names take what is left and are cut short with "…" when the column is narrow, with the full name in the tooltip. The table never scrolls sideways.
- Every control and every row has a tooltip that states the rule of its group (the user's rule of 2026-10-07; `tests/test_gui_tooltips.py`).
- Colours come from `gui/theme.py` only: the title lines in `INK_2`, the state line through `theme.status_html` (a coloured symbol carries the state, the words stay in ink).
- A trace's name never widens the panel (the boxes have a fixed width, the list that drops down shows the full names), and the panel is no wider than the Markers panel, so the window's smallest width stays 1221 px.
- The analysis runs in the GUI thread: 6 ms for 400 points.
- Nothing is remembered between runs of the app: no settings.
- The dock changes the default arrangement, so `LAYOUT_VERSION` goes to 3 and a stored layout of the old arrangement is dropped once. The dock is in the View menu and in the Settings dialog's list of panels shown at start-up.

## 5. Structure

| File | Change |
|---|---|
| `measure/metrics.py` (new) | the maths of section 3 on a `Curve`: `analyse(curve, phase) -> Metrics`, `passband(curve) -> Passband` and `marker_pair` for the marker, with `Band`, `Cutoff`, `Resonance` and `Value` (a number, is it a limit, flagged). No Qt, imports `measure/response.py` only. Written to be read by parts 2 and 3. |
| `measure/response.py` | `refine(curve, index, highest)`: the parabola of `extremum` for any point; `extremum` uses it. |
| `analysis.py` (new) | the rows and texts of the table for one `Metrics` or two, the difference rule, the notes, the clipboard text. No Qt. |
| `markers.py` | `_cutoffs` follows section 3.7; the rule "a real peak against both ends" moves to `metrics.ends_extreme`, which both use. |
| `gui/analysis_panel.py` (new) | `AnalysisPanel`: the controls, the table, the state line, the notes. |
| `gui/bode_plot.py` | `analysis_curve(trace_id)`: a trace as a curve for the panel, absolute, flagged points marked; the tooltip of the −3 dB tick. |
| `gui/main_window.py`, `io/settings.py`, `gui/dialogs.py` | the dock, the View menu entry, `LAYOUT_VERSION` 3, the panel in `PANELS` and in the Settings dialog. |
| `docs/ARCHITECTURE.md`, `docs/spec/gui.md`, `README.md`, `docs/STATE.md` | the new modules and the tab. |

## 6. Decided by me, to be checked by the user

1. The thresholds: flat is at most 3 dB/decade over a third of a decade; a stretch needs a third of a decade, five points, and stays within 3 dB; a stopband floor lies 10 dB or more below the passband; a resonance stands 1 dB and 8 times the scatter clear; the slope window is half a decade; "still getting steeper" is 2 dB/decade; a dip counts for the ripple from 0.1 dB; "too few points" is fewer than five; a short passband is less than a decade.
2. The level of a stretch is the median of its flattest quarter.
3. With no flat stretch the passband level is the peak. So a resonant band-pass keeps today's cut-offs.
4. Q from the phase is given for peaks only. At a notch the phase steps by up to 180° and its slope there belongs to the zeros, not to the Q of the resonance; a number would mislead.
5. The analysis always reads the trace in dB and absolute, independent of the plot's unit and of "Difference to trace".
6. Resonances pair up across the two traces within a factor of 1.2.
7. The table is not remembered, and there is no setting.
8. The −3 dB marker changes as section 3.7 says; that is the one change a user sees without pressing Analyse.
9. The seven changes listed at the top of this document.
10. A limit is written "≥"; the row names are short ("Slope, fc", "Beyond fc") because the column is narrow.

## 7. Tests

Pure maths (`tests/test_metrics.py`), each against the value theory gives:

- every simulated DUT: through (one passband touching both ends, no cut-off), RC low-pass and high-pass, RLC band-pass and notch, Butterworth second order;
- built in the tests with `TransferFunction.custom`: Chebyshev low-passes with 1 dB ripple (fifth and fourth order), a second-order low-pass with Q = 2 (hump), a fifth-order Butterworth, a wide band-pass with a flat top, a response with a stopband floor, two resonances side by side, a crystal's series and parallel resonance, an amplifier (20 dB flat, one pole);
- noise of the size of the bench (0.02 dB, 0.1°) and of ten times that, flagged points, dead points and a gap, a span that cuts the response short (limits);
- too few points; a resonance with too few points across it;
- Q from the phase against Q from the width on a band-pass at Q = 1, 10 and 50;
- linear sweeps, a few points per decade, repeated frequencies, heavy noise: nothing breaks, every number is finite;
- a time limit: a curve of 500 points is analysed in under 0.5 s.

Markers (`tests/test_markers.py`): the hump low-pass gives `fc` from the flat level; a notch filter gets both edges; a resonant band-pass is unchanged. Four existing tests move with the rule and are corrected.

Texts (`tests/test_analysis.py`): rows, limits, flagged marks, the difference rule, pairing of resonances, the notes, the clipboard text.

GUI offscreen (`tests/test_gui_analysis.py`): nothing computed before Analyse; the table after it; Compare columns; the state line after a new point and after a trace was removed; an empty trace; Copy table; tooltips; the panel's width and the table's columns; the dock in the default layout.

By eye, with the user: offscreen renders at 1280x720, 1536x864 and 2560x1440, reviewed with the frontend-design skill, then the running app.
