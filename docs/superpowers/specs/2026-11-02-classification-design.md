# Classification: design

Date: 2026-11-02. Status: **design approved by the user on 2026-11-02 (plan approved: "Approved, but remember to never let values be hardcoded, and add settings for it if possible", then "Everything, part 1 included" for what becomes a setting).** The rules of section 3 are mine and are to be tried in a scratchpad prototype against the theory circuits before the implementation plan is written; a rule the prototype finds wrong is replaced and listed at the top of this document, as part 1 did. It is part 3 of v3 (milestone B2 of the roadmap, `docs/spec/roadmap.md` sections 15 and 16). B3 (the model fit, the Crystal group and the narrow crystal sweep) comes after it, the user's order of 2026-11-02 (`docs/STATE.md`).

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

### 3.1 Refusals, checked first

In this order; the first that holds is the answer, "Not classified: <reason>":

1. Part 1 has no analysis (fewer than 5 usable points).
2. The noise ends cover more than 50 % of the usable points.
3. The passband scatters more than 1 dB (the scatter of part 1, 3.5, over the passband's points).
4. More than 30 % of the points carry a flag that marks a single point (section 4).
5. The sweep, without its noise ends, spans less than 1 decade AND no resonance lies whole inside it (both of its −3 dB points found).

After the type and its score (3.2 to 3.4): a score under 40 % refuses too, with the reasons that took it down.

### 3.2 The type

Tried in this order; the first that fits is the type.

- **Crystal-like**: a peak and a notch, the notch above the peak, f_notch / f_peak under 1.2, both with Q (width) of 10 or more. Shape words: "fs <f>, fp <f>". A ceramic resonator reads the same; the tooltip says so.
- **Flat / all-pass**: one passband that touches both ends, no cut-off, no resonance 3 dB high or deep. With phase: when the phase turns by 90° or more across the sweep, **all-pass**, else **flat**. A magnitude-only sweep is flat, and the reason "phase not measured: an all-pass looks the same" takes its weight off the score.
- **Band-stop / notch**: passbands at both ends, and between them either two cut-offs bounding the gap or a notch 10 dB deep or more.
- **Band-pass**: one passband (or, with no flat stretch, part 1's peak) with a cut-off on each side.
- **Shelf**: flat stretches at both ends whose levels lie 3 dB or more and less than 20 dB apart.
- **Low-pass**: a passband at the low end, cut-offs on its high side only. A stopband floor 20 dB or more below is allowed (a low-pass with finite rejection).
- **High-pass**: the mirror.
- **Unknown**: anything else. The shape words say what was seen ("peaks at 10.0 kHz and 300 kHz").

### 3.3 Shape words

Joined with commas after the type, each only when it applies:

- "order N" from the roll-off, "order ≥ N" when it is a limit; for a band-pass with two orders, both.
- "peaking +x dB": a peak at the passband's edge standing 1 dB or more.
- "ripple x dB (Chebyshev-like)": part 1's ripple is 0.3 dB or more and the passband has dips.
- "stopband notches (elliptic-like)": a roll-off ends in a notch and the stop band comes back.
- "gain +x dB" or "loss −x dB": the passband level lies more than 1 dB from 0 dB.
- "Q x" for a band-pass or band-stop.

### 3.4 The score

Start at 100 and subtract, for each reason that holds (the reason is listed with its amount):

| Reason | Amount |
|---|---|
| A flag on the whole sweep (skew unchecked) | 10 |
| Points with a single-point flag | their share × 100 |
| A passband at an end spans less than a decade (part 1's note) | 20 |
| The order is only a limit | 10 |
| A low-pass or high-pass read from a peak with no flat stretch | 15 |
| Each noise end | 5 |
| The passband scatters more than 0.3 dB | 10 |
| Flat or all-pass without phase | 30 |
| Too few points on a resonance the type rests on | 15 |
| Less than 10 dB of stopband seen (low-pass, high-pass, band-pass) | 20 |

The score is at least 0. Under 40: refused (3.1).

## 4. Flags

`Curve` keeps `flagged` as it is (part 1's "(flagged)" marks do not change). It gains two fields, filled by `BodePlot.analysis_curve`:

- `point_flagged`: per point, a flag other than the quiet ones (`QUIET`) and other than SKEW_UNCHECKED;
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

- A **Type** group first: Type (e.g. "Low-pass"), Shape (the shape words), Confidence ("85 %"). Refused: Type reads "Not classified", Shape is empty, Confidence is the score when there is one.
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

1. Every default of section 3: the 1.2 ratio and Q 10 for crystal-like; 90° for all-pass; 10 dB for a notch that makes a band-stop; 3 to 20 dB for a shelf; 0.3 dB of ripple; 1 dB of peaking and of gain; every score weight; refusal at 30 % single-point flags.
2. The order the types are tried in (3.2).
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
