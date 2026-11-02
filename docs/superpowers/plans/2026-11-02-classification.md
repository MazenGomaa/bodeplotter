# Classification Implementation Plan

> **For agentic workers:** use superpowers:executing-plans (inline) task by task, test first (superpowers:test-driven-development). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a type, shape words and a confidence in percent on top of part 1's `Metrics`, refuse when the sweep cannot carry a type, and show it first in the Analysis table, with every number a setting.

**Architecture:** A new pure module `measure/classify.py` reads one `Metrics` and its `Curve` and returns a `Classification`. Its thresholds and weights are new fields of `measure/analysis_settings.py` (the Settings dialog's Analysis tab builds itself from `FIELDS`, so it gains two groups with no dialog code). `analysis.py` adds the Type group, the reasons in the notes and the comparison rule. `gui/analysis_panel.py` calls `classify` after `analyse`. `Curve` gains the two flag fields of design section 4, filled by `BodePlot.analysis_curve`.

**Spec:** `docs/superpowers/specs/2026-11-02-classification-design.md` (read it first; section numbers below are its sections). Step 2 of its order of work (every part 1 constant a setting) is done (commit `b8770b5`).

**Before Task 1:** ask the user the open question of `docs/STATE.md` (build as shown / crystal stricter / change a default), multiple choice, and fold the answer into Task 2.

**Where the rules come from.** Section 3 was run in a scratchpad prototype (`proto_classify_final.py` in the session's scratchpad, not in the repository) on 900 log sweeps and 132 linear sweeps of every theory circuit: 876 + 132 right, the 24 wrong all under-sampled (design, "Changed after the approval"). The code of Task 2 is that prototype, cleaned and with every number read from the settings. If a test of Task 2 does not behave as the design says, stop and find out why; do not adjust a test to make it pass.

## Global Constraints

- Run from the project root with `.venv\Scripts\python`. Work on the branch `v3-classification`; merge only after the user's review (Task 6).
- Nothing reaches an instrument. No bench run, no `hwcheck/` script. `BODEPLOT_NO_HARDWARE` stays set by `tests/conftest.py`.
- `measure/classify.py`, `measure/analysis_settings.py` and `analysis.py` import no Qt. No `subprocess` in `src/`. No new dependency.
- **No hard-coded value** (the user, 2026-11-02): every threshold and weight is a field of `AnalysisSettings` with a default, a range, a unit and a tooltip; `tests/test_analysis_settings.py::test_the_maths_holds_no_threshold_of_its_own` scans `classify.py` as it does `metrics.py`.
- With the settings at their defaults, part 1's results do not change (its tests pass unchanged).
- Every colour from `gui/theme.py`; every control and row has a tooltip (`tests/test_gui_tooltips.py`); `clicked` goes through `lambda _checked=False: ...`; the panel's width does not depend on its content (the window's smallest width stays 1221 px).
- A limit is written `≥ `; percentages as `85 %`.
- Commit after every task with the session's two trailer lines.
- `docs/ARCHITECTURE.md` lists the new module and the changed imports (`tests/test_docs.py`).

## Review Focus

1. **Under-sampled responses** (5 points per decade across Q 10 resonances; a crystal stepped over): a middling score and the "too few points" note, never 100 %. Tests: `test_a_coarse_sweep_is_never_sure`, `test_a_narrow_sweep_that_missed_the_peak_is_refused` (Task 2).
2. **Noise**: 0.02 and 0.2 dB change no type; 2 dB refuses; 0.5 dB gives no "Chebyshev-like". Tests: `test_noise_changes_no_type`, `test_heavy_scatter_refuses`, `test_noise_is_not_ripple` (Task 2).
3. **Flags**: SKEW_UNCHECKED on every point lowers the score by 10 and never refuses; 31 % clipped points refuse. Tests: `test_a_sweep_wide_flag_lowers_the_score_only`, `test_many_flagged_points_refuse` (Task 2); `test_analysis_curve_splits_the_flags` (Task 3).
4. **Magnitude only**: flat with −30, never all-pass. Test: `test_flat_and_all_pass` (Task 2).
5. **Compare**: types side by side, "same" / "differs", the score's difference in points; a refused trace against a classified one. Test: `test_type_rows_compare` (Task 4).

## File Structure

| File | Task | Change |
|---|---|---|
| `src/bodeplot/measure/analysis_settings.py` | 1 | groups "Classification" and "Score weights", 27 new fields |
| `src/bodeplot/measure/classify.py` (new) | 2 | `Classification`, `classify(m, c, phase, s)`, `scatter(m, c, s)` |
| `src/bodeplot/measure/response.py` | 3 | `Curve.point_flagged`, `Curve.wide_flags`; kept by `curve()` and `metrics.without_noise` |
| `src/bodeplot/gui/bode_plot.py` | 3 | `analysis_curve` fills them |
| `src/bodeplot/analysis.py` | 4 | the Type group, reasons in the notes, comparison, `GROUPS` tip |
| `src/bodeplot/gui/analysis_panel.py` | 5 | `classify` after `analyse`, the Analyse tooltip |
| tests | 1 to 5 | `test_classify.py` (new), `test_analysis_settings.py`, `test_analysis.py`, `test_gui_analysis.py` |
| docs | 6 | ARCHITECTURE, gui.md, roadmap, README, STATE |

---

### Task 1: the classification fields

- [ ] **Step 1: test first.** In `tests/test_analysis_settings.py`, extend `test_every_field_has_a_default_inside_its_range_and_a_tooltip` to require the groups `"Classification"` and `"Score weights"` and the keys below; run, expect FAIL.
- [ ] **Step 2: add the fields** to `FIELDS` (key, default, unit, range, decimals), each with a tooltip that states its rule from design section 3:
  - Classification: `crystal_ratio` 1.2 × (1.01–2, 2); `crystal_q` 10 (1–1000, 0); `allpass_deg` 90 ° (10–360, 0); `notch_db` 10 dB (1–60, 1); `shelf_lo` 3 dB (0.5–20, 1); `shelf_hi` 20 dB (3–100, 1); `ripple_db` 0.3 dB (0.01–6, 2); `ripple_scatter` 6 × (1–50, 1); `peaking_db` 1 dB (0.1–20, 1); `gain_db` 1 dB (0.1–20, 1); `min_stop_db` 10 dB (1–100, 1); `span_dec` 1 dec (0.1–5, 2); `noise_share` 0.5 share (0.05–1, 2); `scatter_db` 1 dB (0.05–10, 2); `scatter_warn` 0.3 dB (0.01–10, 2); `point_flag_share` 0.3 share (0–1, 2); `min_score` 40 % (0–100, 0).
  - Score weights (%, 0–100, whole numbers): `w_wide_flag` 10, `w_short_passband` 20, `w_limit` 10, `w_from_peak` 15, `w_noise_end` 5, `w_scatter` 10, `w_no_phase` 30, `w_few_points` 15, `w_little_stop` 20, `w_short_span` 30. The flagged share costs its share × 100 (no field: it is the share itself).
- [ ] **Step 3:** run `tests/test_analysis_settings.py` and `tests/test_settings_more.py::test_settings_dialog_analysis_tab` (the tab builds the new boxes by itself); expect PASS. Commit.

### Task 2: `measure/classify.py`

- [ ] **Step 1: tests first**, `tests/test_classify.py`, built as the prototype's sweeps (`sweep(tf, ppd, noise, lin, rng, lo, hi, n)` helper in the test file; seeded `random.Random`):
  - `test_every_theory_circuit_gets_its_type`: parametrised over the design's success criterion 1 (crystal on a linear 0.9–1.2 MHz sweep of 200 points), at 20 points per decade, clean and 0.02 dB.
  - `test_gain_only_from_a_flat_level` (design change 8): an RC sweep from 800 Hz has no "gain" word; amp has "gain +20.0 dB".
  - `test_shape_words`: rc "order 1"; butter_lpf "order 5"; rlc_lpf "peaking +6.3 dB" (±0.2); cheby_lpf "ripple 1.0 dB (Chebyshev-like)"; amp "gain +20.0 dB"; `ELLIPTIC` of `tests/test_metrics.py` "stopband notches (elliptic-like)"; rlc_bpf "Q 1"; crystal "fs" and "fp" within 0.5 %.
  - `test_noise_changes_no_type`: every circuit, 0.2 dB, 12 and 40 points per decade, four grid offsets.
  - `test_linear_sweeps`: the prototype's 132 linear sweeps, all right.
  - `test_a_coarse_sweep_is_never_sure`: two_res at 5 points per decade scores at most 85; `test_a_narrow_sweep_that_missed_the_peak_is_refused`: the crystal with 80 points over 0.9–1.2 MHz is refused or under 60.
  - Refusals, each alone: `test_a_slice_of_a_slope_is_refused` (RC 10–50 kHz), `test_a_narrow_sweep_across_a_crystal_is_not_refused`, `test_mostly_noise_is_refused` (butter_lpf over a −40 dB floor, 100 Hz–100 MHz), `test_heavy_scatter_refuses` (2 dB), `test_noise_is_not_ripple` (0.5 dB: low-pass, no ripple word, −10), `test_many_flagged_points_refuse` (31 % `point_flagged`), `test_a_sweep_wide_flag_lowers_the_score_only` (`wide_flags=["skew unchecked"]`: 90), `test_a_low_score_refuses` (`min_score` 95 refuses a short passband).
  - `test_flat_and_all_pass`: through with phase → flat 100; without → flat 70; a first-order all-pass `TF.custom([-1/w, 1], [1/w, 1])` → all-pass.
  - `test_settings_move_the_answer`: `shelf_hi` 50 makes rc_shelf a shelf; `crystal_q` 200 makes the crystal unknown.
  - `test_the_score_adds_up`: score = 100 − sum of the listed amounts, at least 0.
  - Run, expect FAIL (no module).
- [ ] **Step 2: write `classify.py`** from the prototype, in design order: `Classification` (`kind`, `words: list[str]`, `score: int | None`, `reasons: list[tuple[str, int]]`, `refused: str`); `scatter(m, c, s)` (design section 3, "The scatter"); `classify(m, c, phase=True, s=DEFAULTS)`: refusals 3.1, type 3.2 (the nine rules in their order), words 3.3, score 3.4, the low-score refusal. Reason texts are full sentences for the notes ("Phase not measured: an all-pass looks the same.", "The sweep spans less than a decade.", ...). Frequencies in words through `units.fmt_si` (4 digits). Constants left in the module only for arithmetic, as in `metrics.py`.
- [ ] **Step 3:** run `tests/test_classify.py` and `tests/test_analysis_settings.py` (add `classify.py` to the source scan); expect PASS. Full suite `--deselect tests/test_docs.py`. Commit.

### Task 3: the two kinds of flags

- [ ] **Step 1: tests first.** `tests/test_response.py` (or the file that tests `curve()`): `curve(..., point_flagged=..., wide_flags=...)` keeps them through sorting and `metrics.without_noise`; a curve built without them has `[False] * n` and `[]`. `tests/test_gui_analysis.py::test_analysis_curve_splits_the_flags`: points all with SKEW_UNCHECKED and two with CLIPPED give `wide_flags == ["skew unchecked"]` and `point_flagged` true at the two only; `flagged` unchanged (true at all). Run, expect FAIL.
- [ ] **Step 2:** add the fields to `Curve` (defaults: empty, read as all false), to `curve()` (sorted with the points), to `without_noise`; in `BodePlot.analysis_curve`: `point_flagged = [bool(p.flags & ~QUIET & ~Flag.SKEW_UNCHECKED) ...]`, `wide_flags = ["skew unchecked"]` when every point has SKEW_UNCHECKED. `Metrics.flagged_share` and part 1's "(flagged)" marks stay as they are.
- [ ] **Step 3:** run; expect PASS. Commit.

### Task 4: the table

- [ ] **Step 1: tests first**, `tests/test_analysis.py`: `test_type_group_first` (rows start with group "Type": Type, Shape, Confidence "100 %"); `test_refused_type_row` ("Not classified", the refusal's sentence first in the notes); `test_reasons_lead_the_notes` ("−10 % Skew unchecked ..." before part 1's notes); `test_type_rows_compare` (Compare holds the other type; Difference "same" / "differs" for Type, "+15 points" style for Confidence, nothing for Shape; a refused side leaves Difference empty); `test_clipboard_has_the_type`. Run, expect FAIL.
- [ ] **Step 2:** in `analysis.py`: `rows(m, other, phase, s, k=None, ko=None)` puts the Type group first when `k` is given; `notes(m, s, k=None)` puts the refusal or the reasons first; `group_tips` gains "Type" (the rule of 3.2 to 3.4 with the settings in force: the 40 % refusal, the types tried). `GROUPS` keeps its order with "Type" first.
- [ ] **Step 3:** run `tests/test_analysis.py`; expect PASS. Commit.

### Task 5: the panel

- [ ] **Step 1: tests first**, `tests/test_gui_analysis.py`: `test_the_type_comes_first_after_analyse` (RC sweep: the first group is "Type", its value "Low-pass"); `test_compare_shows_both_types` (RC against the RLC band-pass: "differs"); `test_type_rows_have_tooltips`. Run, expect FAIL.
- [ ] **Step 2:** `AnalysisPanel.analyse` calls `classify.classify(m, curve, phase, s)` for both traces (not when `m` is not ok: the refusal is part 1's reason) and passes them to `rows` and `notes`. The Analyse button's tooltip names the type and the confidence. Imports go into `docs/ARCHITECTURE.md` in Task 6.
- [ ] **Step 3:** run; expect PASS. Full suite `--deselect tests/test_docs.py`. Commit.

### Task 6: the look, the documents, the user's review

- [ ] Offscreen renders of the panel with the Type group and of the Settings dialog's Analysis tab at 1280x720, 1536x864 and 2560x1440; look at them with the frontend-design skill (the Type group must not widen the panel).
- [ ] `docs/ARCHITECTURE.md` (the new module, the changed imports and the paragraph on the analysis), `docs/spec/gui.md` (the Type group, the two new groups of the Analysis tab), `docs/spec/roadmap.md` (B2 built), `README.md`, `docs/STATE.md`. Full `pytest`, all passing.
- [ ] The user's look at the running app (`run.bat --sim`, each simulated circuit swept and analysed), then the branch review, then the merge question.
