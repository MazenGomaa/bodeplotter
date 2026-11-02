# Classification: design

Date: 2026-11-02. Status: **design approved by the user on 2026-11-02 (plan approved: "Approved, but remember to never let values be hardcoded, and add settings for it if possible", then "Everything, part 1 included" for what becomes a setting).** The rules of section 3 are mine and are to be tried in a scratchpad prototype against the theory circuits before the implementation plan is written; a rule the prototype finds wrong is replaced and listed at the top of this document, as part 1 did. It is part 3 of v3 (milestone B2 of the roadmap, `docs/spec/roadmap.md` sections 15 and 16). B3 (the model fit, the Crystal group and the narrow crystal sweep) comes after it, the user's order of 2026-11-02 (`docs/STATE.md`).

**Changed after the approval, from the prototype (2026-11-02).** The rules were tried in a scratchpad prototype on every theory circuit before the plan was written: 900 log sweeps (15 circuits, 5 to 40 points per decade, noise 0, 0.02 and 0.2 dB, four grid offsets) and 132 linear sweeps from 0.1 to 10 times the circuit's frequency. Seven rules of the approved text gave wrong answers and were replaced (an eighth came from the table shown to the user); section 3 below is the corrected text, for the user to confirm with the plan:

1. **The type from the cut-offs' sides (3.2)**, not from passbands that touch the ends: at 12 points per decade with 0.2 dB of noise the first points are not flat, the passband did not "touch" the end, and 13 of 900 sweeps fell to unknown.
2. **One big peak for a band-pass (3.2):** two peaks 10 dB high or more with no flat passband are unknown (two_res read as band-pass, 60 of 60).
3. **A roll-off into a notch that comes back to the passband is a band-stop (3.2):** a linear sweep sees too few points below an RLC notch to find the low passband; the gain beyond the notch coming back within 3 dB of the level says it (7 linear sweeps read high-pass).
4. **A peak that falls less than 10 dB on one side is a peaking low-pass or high-pass (3.2)**, with the reason "passband not seen flat": a linear sweep of rlc_lpf never found the flat part below the hump and read band-pass at 100 % (9 sweeps).
5. **The scatter (3.1, 3.3) is the noise near the level**, from the second differences that change sign against both neighbours (noise does; a bend keeps its sign) over the points within 10 dB of the level, at least 9 of them; not the passband's scatter: 2 dB of noise broke the passband up, nothing was measured, and it read band-pass at 90 %. This estimate reads 1.0 to 1.9 times the noise (it keeps the larger steps); the refusal at 1 dB is a setting.
6. **Ripple needs 6 times the scatter (3.3):** 0.5 dB of noise read "ripple 1.1 dB (Chebyshev-like)".
7. **A new reason, a span under a decade, −30 (3.4):** a narrow sweep that stepped over a crystal's peak read high-pass at 100 %; now it is refused.
8. **"gain" only from a flat level (3.3):** a level read from a peak is that peak, not a passband gain: an RC sweep that starts 0.3 decade below fc read "gain −1.0 dB", an under-sampled Q 10 band-pass "gain −2.3 dB".

**Changed after the build, from the branch review and the simulated run (2026-11-02; the user: "LOW_SNR not counted", "Fix all, then rerun").** A simulated sweep of every circuit through the window (50 Hz to 20 MHz, 20 points per decade) left 8 of 15 not classified: the sweep sets LOW_SNR on every point below about −31 dB, so a low-pass's stop band alone made 46 % of the points "flagged". The tests had only fed theory curves, which carry no flags. A fresh reviewer found the rest:

9. **LOW_SNR is not a fault of the point (section 4):** it counts neither toward the 30 % refusal nor in the score; the noise ends and the scatter judge the SNR.
10. **A scatter that cannot be measured near the level is taken over the whole trace (3):** with fewer than 9 sign-flipping second differences near the level, the same over every usable point outside the noise ends. An open probe (pure noise) has too few points near its "level" and read band-pass or band-stop at up to 100 %; 3 dB of noise gave types back that 2 dB refused.
11. **Crystal-like holds the peak to Q 10, not the notch (3.2 rule 1):** measured from a flat level, a crystal's notch is broad (Q about 8 even at 1000 points per decade), so a wide log sweep could never read crystal-like; it read band-stop 65 to 80 %. Of the 900 log sweeps: 854 right (the build: 836); the crystal is right from 40 points per decade up.
12. **The ripple word only on a low-pass, high-pass or band-pass, and at most 3 dB (`ripple_max_db`, 3.3):** a crystal read "band-stop, ripple 19.4 dB (Chebyshev-like)", a coarse rc_shelf "flat, ripple 0.5 dB".
13. **Unknown shows no confidence (section 6):** "Unknown, 100 %" read as a contradiction. The score still exists and still refuses under 40.

Rulings made in the build where this text was silent: with `crystal_q` at 200 the Q 100 crystal on a linear sweep is a band-pass by rule 7 (the plan had said unknown); a band-pass read from a peak counts the points between its cut-offs for "too few points"; a band-stop rests on its notch, an unknown with several peaks on its peaks.

Known limits, left as they are: a response sampled too coarsely to show its features is misread with a middling score (two_res at 5 points per decade, its second peak never sampled: low-pass or high-pass at 70 %; the Q = 100 crystal with 50 points over 300 kHz: low-pass at 55 %). The notes' "too few points ... sweep finer" (part 1) and the finer sweep (part 2, B3) are the remedy. The LC trap over a −19 dB floor (`tests/test_metrics.py`, TRAP_SHELF) reads as a shelf, just inside the 20 dB limit.

## 1. Purpose

Part 1 reads the numbers of a trace: passbands, cut-offs, roll-off and order, stopband, resonances, noise ends. Part 3 reads them as a whole and names the circuit: a type, a few shape words, a confidence in percent with its reasons, and a refusal when the sweep cannot carry a type. A crystal reads as crystal-like, not unknown.

What the user chose (2026-11-02, multiple-choice questions):

| Question | Decision |
|---|---|
| Types | Low-pass, high-pass, band-pass, band-stop / notch, all-pass, flat (wire or amplifier), shelf, crystal-like, unknown. |
| Details | The type plus shape words built from part 1's metrics: order, peaking, ripple ("Chebyshev-like"), stopband notches ("elliptic-like"), gain. No family names that need the phase or a fit (Butterworth against Bessel is B3's job). |
| Confidence | A percentage from 0 to 100: each reason subtracts a fixed amount; the reasons are listed. |
| Flags | Only flags that mark single points count toward a refusal. A flag on the whole sweep (SKEW_UNCHECKED) lowers the score and is listed; it never refuses. |
| Span | Refused only when the sweep spans under one decade AND holds no whole resonance. A narrow sweep across a crystal still classifies. |
| Low SNR | Refused when the noise ends cover more than half the points, or the passband scatters more than 1 dB. |
| Low score | Refused under 40 %: "Not classified", with the reasons. |
| Display | A "Type" group first in the Analysis table; the reasons in the notes; with "Compare with", the other trace's type, and "same" or "differs". Copy table includes it. |
| Numbers | No hard-coded value: every threshold and weight of this part, and every constant of part 1's `metrics.py`, is a setting with a default, a range and a tooltip, on a new Analysis tab of the Settings dialog. |

Success criteria:

1. Every theory circuit of `measure/theory.py` gets its type with the defaults, clean and with the bench's noise: through → flat; rc_lpf, butter2_lpf, rlc_lpf, butter_lpf, cheby_lpf, amp, loop3 → low-pass; rc_hpf → high-pass; rlc_bpf, wide_bpf → band-pass; rlc_notch → band-stop; rc_shelf → low-pass (its stop band levels off at −40 dB, beyond the 20 dB limit of a shelf, 3.2); crystal → crystal-like; two_res → unknown, with both peaks named.
2. The shape words match the circuit: order 1 for the RC, order 5 for the fifth-order Butterworth, "peaking" for rlc_lpf at Q = 2, "ripple 1.0 dB (Chebyshev-like)" for cheby_lpf, "gain +20 dB" for amp.
3. Each refusal fires on its own case and not on the others; a narrow sweep across a crystal is not refused; SKEW_UNCHECKED on every point is not refused.
4. With the settings at their defaults, part 1 gives exactly the numbers it gives today (its tests pass unchanged).
5. A setting changed in the Settings dialog changes the next analysis, and the state line says the settings changed since the table was made.

## 2. What it does not do

- No family names (Butterworth, Bessel) and no poles or zeros: B3.
- No Crystal group (ESR, C0, C1, load capacitance) and no narrow crystal sweep: B3. Crystal-like names fs and fp in its shape words only.
- Nothing in the CSV or the image: part 5.
- No OK / not OK verdict against a reference trace: the Compare column shows the two types side by side.
- Nothing reaches the instruments. No bench run.

## 3. The rules

All of it reads one `Metrics` (part 1) and the `Curve` it was made from. Every number in this section is a setting (section 5); the figure given is its default.

**The scatter** used below is the noise near the level: over the usable points outside the noise ends whose gain lies within 10 dB (`floor_db`) of the level, the second differences that change sign against both neighbours, their median times the factor of part 1 (`metrics.SIGMA_OF_D2`). With fewer than 9 (`noise_points`) of them, the same over every usable point outside the noise ends (an open probe has too few points near its level); 0 with fewer than 9 there too.

### 3.1 Refusals, checked first

In this order; the first that holds is the answer, "Not classified: <reason>":

1. Part 1 has no analysis (fewer than 5 usable points).
2. The noise ends cover more than 50 % of the usable points.
3. The scatter is more than 1 dB.
4. More than 30 % of the points carry a flag that marks a single point (section 4).
5. The sweep, without its noise ends, spans less than 1 decade AND no resonance lies whole inside it (Q from the width found).

After the type and its score (3.2 to 3.4): a score under 40 % refuses too, with the reasons that took it down.

### 3.2 The type

The cut-offs in ascending frequency give their sides: "high" (the passband lies below, a low-pass edge) or "low". Tried in this order; the first that fits is the type.

1. **Crystal-like**: a peak of Q (width) 10 or more and a notch above it, f_notch / f_peak under 1.2 (the notch has no Q limit: from a flat level it is broad). A ceramic resonator reads the same; the tooltip says so.
2. **Flat / all-pass**: a passband, no cut-off, no resonance 3 dB high or deep. With phase: when the phase turns by 90° or more across the sweep, all-pass, else flat. A magnitude-only sweep is flat, with the reason "phase not measured".
3. **Unknown, several peaks**: no flat passband and two or more peaks 10 dB high or more.
4. **Band-stop, from a notch**: a notch, and a roll-off that ends in it beyond which the gain comes back within 3 dB of the level (its stopband value under 3 dB).
5. **Peaking low-pass / high-pass**: no flat passband, cut-offs low then high, and the gain falls 10 dB or more on one side only: the side that falls less is the passband the sweep never saw flat (reason "passband not seen flat"; shape word "peaking").
6. **Low-pass / high-pass / shelf**: every cut-off on the high side (low-pass) or every one on the low side (high-pass). When a flat stretch beyond the cut-offs lies 3 dB or more and less than 20 dB below the level, it is a **shelf** instead, with its step.
7. **Band-pass**: cut-offs low then high.
8. **Band-stop**: cut-offs high then low, with two passbands or a notch 10 dB deep or more.
9. **Unknown**: anything else; the shape words list the resonances seen.

### 3.3 Shape words

Joined with commas after the type, each only when it applies:

- crystal-like: "fs <f>, fp <f>".
- "order N" for each roll-off with an order (low-pass, high-pass, band-pass), "order ≥ N" when it is a limit.
- "peaking +x dB": a peak at least 1 dB over a flat level on the passband's side of a cut-off; "peaking" alone for rule 5.
- "ripple x dB (Chebyshev-like)": a low-pass, high-pass or band-pass whose ripple (part 1) is 0.3 dB or more, 3 dB or less (`ripple_max_db`; more is a resonance) and 6 times the scatter or more, and there is no peaking.
- "stopband notches (elliptic-like)": a low-pass, high-pass or band-pass roll-off that ends in a notch (no slope, a stopband value).
- shelf: "high-frequency step −x dB" or "low-frequency step"; "notch at <f>" when it has one.
- "Q x" for a band-pass or band-stop with a centre.
- "gain +x dB" or "loss −x dB": the level comes from a flat stretch and lies more than 1 dB from 0 dB (a level read from a peak is that peak, not a passband gain).
- unknown: "<peak or notch> at <f>" for each resonance.

### 3.4 The score

Start at 100 and subtract, for each reason that holds (the reason is listed with its amount):

| Reason | Amount |
|---|---|
| A flag on the whole sweep (skew unchecked) | 10 |
| Points with a single-point flag | their share × 100 |
| A passband at an end spans less than a decade (part 1's note) | 20 |
| An order is only a limit | 10 |
| A low-pass or high-pass read from a peak, or rule 5 | 15 |
| Each noise end | 5 |
| The scatter is more than 0.3 dB | 10 |
| Flat or all-pass without phase | 30 |
| Too few points on a resonance the type rests on (crystal-like; a band-pass from a peak) | 15 |
| Less than 10 dB of stopband seen (low-pass, high-pass, band-pass) | 20 |
| The sweep spans less than a decade (not for crystal-like) | 30 |

The score is at least 0. Under 40: refused (3.1).

## 4. Flags

`Curve` keeps `flagged` as it is (part 1's "(flagged)" marks do not change). It gains two fields, filled by `BodePlot.analysis_curve`:

- `point_flagged`: per point, a flag other than the quiet ones (`QUIET`), SKEW_UNCHECKED and LOW_SNR (on every point of a deep stop band; the noise rules judge it): `bode_plot.NOT_A_FAULT`;
- `wide_flags`: the names of the flags that mark every point (today SKEW_UNCHECKED), shown as "skew unchecked".

Both survive `curve()` and `metrics.without_noise`. A curve built without them (tests, theory curves) has no flags of either kind.

## 5. Settings: no hard-coded value

- `measure/analysis_settings.py` (new, no Qt): `AnalysisSettings`, a frozen dataclass holding every value of section 3 and every constant of `metrics.py` (FLAT_SLOPE to MIN_POINTS, the noise rules included), each with its default; and `FIELDS`: key → group, label, unit, lowest, highest, whole number or not, tooltip. A number lives there and nowhere else.
- `metrics.analyse`, `passband`, `marker_pair`, `noise_ends` and `classify.classify` take `s: AnalysisSettings = AnalysisSettings()`; the module constants go. `markers._cutoffs` passes the same settings, so the −3 dB marker keeps agreeing with the table.
- `io/settings.py`: `AppSettings.analysis`, stored like `advanced`: only what differs from the default; unknown keys and values outside their range dropped on load; a function makes the `AnalysisSettings`.
- The Settings dialog gets an **Analysis** tab built from `FIELDS`, in groups: Passband and flat stretches; Cut-off and roll-off; Resonances; Noise floor; Classification; Score weights. Each value has a spin box limited to its range and a tooltip; a **Defaults** button as on the Advanced tab. The tab scrolls, so the dialog still fits a 1280×720 screen.
- A changed setting does not redo the table by itself: the state line says "settings changed since this analysis" until Analyse is pressed again.
- This step comes first and alone: part 1's results must not move by one digit.

## 6. The Analysis table

- A **Type** group first: Type (e.g. "Low-pass"), Shape (the shape words), Confidence ("85 %"). Refused: Type reads "Not classified", Shape is empty, Confidence is the score when there is one. Unknown: Confidence is empty, and Compare with shows no difference in points.
- The reasons go in the notes before part 1's notes, as "−10 % skew unchecked". The four-line limit holds; the rest scrolls.
- With Compare with: the Compare column holds the other trace's type, shape and score; Difference reads "same" or "differs" for the type, the score's difference in points, nothing for the shape.
- Tooltips state each rule (`tests/test_gui_tooltips.py`). Colours from `gui/theme.py` only.

## 7. Structure

| File | Change |
|---|---|
| `measure/analysis_settings.py` (new) | `AnalysisSettings`, `FIELDS` (section 5). |
| `measure/classify.py` (new) | `classify(m, c, phase, s) -> Classification`: type, words, score, reasons as (text, amount), the refusal. No Qt; imports `metrics`, `response`, `analysis_settings`. |
| `measure/metrics.py` | its constants move into `AnalysisSettings`; every function that read one takes `s`. |
| `measure/response.py` | `Curve.point_flagged`, `Curve.wide_flags` (section 4). |
| `markers.py` | passes the settings to `metrics`. |
| `analysis.py` | the Type group, the reasons in the notes, the comparison rule, the clipboard text. |
| `io/settings.py`, `gui/dialogs.py` | `AppSettings.analysis`, the Analysis tab. |
| `gui/bode_plot.py`, `gui/analysis_panel.py`, `gui/main_window.py` | the two flag fields; `classify` after `analyse`; the settings passed through; the state line's new warning. |
| `docs/ARCHITECTURE.md`, `docs/spec/gui.md`, `docs/spec/roadmap.md`, `README.md`, `docs/STATE.md` | the new modules, the tab, the state. |

## 8. Decided by me, to be checked by the user

1. Every default of section 3: the 1.2 ratio and Q 10 for crystal-like; 90° for all-pass; 10 dB for a notch that makes a band-stop, for several peaks and for the stopband a type needs; 3 to 20 dB for a shelf; 0.3 dB and 6 times the scatter for ripple; 1 dB of peaking and of gain; every score weight; refusal at 30 % single-point flags and at 1 dB of scatter.
2. The order the types are tried in (3.2), and the eight changes at the top of this document.
3. rc_shelf at its default values (stop band at −40 dB) is a low-pass with finite rejection, not a shelf.
4. two_res is unknown, with both peaks in its shape words, rather than a new "multi-band" type.
5. Every part 1 constant is a setting, including the noise detection's tuning; their tooltips explain what each does but most are not worth changing.

## 9. Tests

- `tests/test_classify.py` (new): every theory circuit against its type and shape words, clean, with 0.02 dB / 0.1° noise and ten times that, 5 to 40 points per decade, log and linear; each refusal alone; the narrow crystal sweep not refused; SKEW_UNCHECKED alone not refused; the score's sum; flat against all-pass with and without phase; a changed setting changes the type (a shelf limit of 50 dB makes rc_shelf a shelf).
- `tests/test_analysis_settings.py` (new): every field has a tooltip and a default inside its range; storing and loading round trip; unknown keys and values outside the range dropped; `metrics.py` and `classify.py` hold no numeric thresholds of their own (a source scan).
- `tests/test_metrics.py`, `tests/test_markers.py`: unchanged, and passing.
- `tests/test_analysis.py`: the Type group, the reasons, Compare, the clipboard.
- `tests/test_gui_analysis.py`, `tests/test_gui_tooltips.py`, a dialog test: the group after Analyse; the Analysis tab, its Defaults button, its tooltips; the state line after a changed setting.
- By eye, with the user: `run.bat --sim`, each simulated circuit swept and analysed; offscreen renders of the table and the tab at 1280×720.
