# Hardware history: Milestone A1, through calibration on the bench, section 14 (2026-10-07)

Part of the hardware report. The current facts and the index of all sections: `HW_REPORT.md`. This file is a dated record of what was run and seen; it is not rewritten when a later run changes the picture, so read the facts sheet first.

## 14. Milestone A1: through calibration on the bench (2026-10-07)

Wiring for 14.1 and 14.2, confirmed by the user before each run: both 10X probes on generator CH1's output, scope CH1 and CH2, the app closed. Code: commit `7761596` (14.1) and `6b83774` (14.2), branch `a1-through-calibration`. Script: `hwcheck/m8_throughcal.py` (the app's own drivers and `sweep/core.py`, headless): a through calibration, then a through sweep over the same range at 20 points per decade with the calibration applied. Reference CH1, DUT CH2, 1 Vpp, DC coupling, Sine fit. Raw data: `hwcheck/results/m8/`.

The acceptance target of the design (section 1, criterion 1): a through sweep reads 0 dB and 0° within 0.02 dB and 0.1° up to 20 MHz.

### 14.1 Calibration and through sweep, one capture per point

Calibration: 58 points, 50 Hz to 20 MHz, 62.1 s, accepted with no warning. Largest gain deviation 0.182 dB (at 15.9 MHz); the gain difference rises from +0.09 dB at 50 Hz to +0.18 dB at 20 MHz (the probes' tilt). Fitted delay +0.085 ns; the phase reaches +0.52° at 20 MHz. Neighbouring calibration points differ by about 0.01 dB and 0.05°: that is the noise of one single-shot measurement.

Through sweep with it applied: 114 points in 113.9 s, all flagged `CALIBRATED`, both channels on 20 mV/div throughout.

| | Mean | Standard deviation | Largest | Points over the target |
|---|---|---|---|---|
| Gain | +0.003 dB | 0.008 dB | 0.030 dB at 15.9 MHz | 2 of 114 |
| Phase | 0.000° | 0.052° | 0.157° at 5.08 MHz | 7 of 114 |

The mean is zero in each of the three bands (50 Hz to 10 kHz, to 1 MHz, to 20 MHz) and the points over the target are scattered with no trend. Verdict of the script: OUTSIDE the targets.

Afterwards: generator outputs off, panel lock 0, scope sweep AUTO; scope counters show the one resync of the connect, no empty reply, no stale record.

### 14.2 The same with 4 averages

Calibration 205.5 s: largest gain deviation 0.181 dB, delay +0.092 ns. Sweep 395.4 s.

| | Mean | Standard deviation | Largest | Points over the target |
|---|---|---|---|---|
| Gain | +0.000 dB | 0.004 dB | 0.013 dB at 4.05 MHz | 0 of 114 |
| Phase | +0.003° | 0.029° | 0.134° at 20 MHz | 1 of 114 |

Both standard deviations halved with four times the captures, so what the first run showed is noise, not an error of the correction. The one point left over is −0.134° at 20 MHz; above 1 MHz the phase scatter is 0.045°, so it is about 3 standard deviations. Not separated from it: the fitted delay moved from +0.085 ns to +0.092 ns between the two calibrations, 14 minutes apart, which is 0.05° at 20 MHz; a slow drift of the channel delay may be part of that point.

Result against the target: the correction leaves no mean error. "Every point within 0.02 dB and 0.1°" is not reachable with one capture per point (the limits sit at about 2 standard deviations); with 4 averages it is met for the gain and missed by one point for the phase.

### 14.3 The user's acceptance run in the GUI

Done by the user on the real instruments, reported in their words and with two exported files (copies in `hwcheck/results/m8/gui_through.csv` and `gui_rc.csv`). The panel was set to reference CH2, DUT CH1 (the reverse of 14.1) and 5 Vpp, one capture per point.

1. **Calibrate, accept.** Summary: largest gain deviation 0.207 dB, delay −0.08 ns. That is 14.1 seen from the other side: the same pair with reference and DUT exchanged gives the same magnitudes with the opposite sign (−0.09 dB at 50 Hz to −0.19 dB at 20 MHz in the stored calibration).
2. **Through sweep, 50 Hz to 20 MHz, Sine fit** (114 points, all `CALIBRATED`): gain mean −0.000 dB, standard deviation 0.009 dB, largest 0.033 dB (2 points over 0.02 dB); phase mean +0.012°, standard deviation 0.052°, largest 0.186° (5 points over 0.1°). The same picture as 14.1.
3. **RC low-pass**, DUT probe moved to the filter output. Parts measured by the user with the LCR meter: resistor 997.8 Ω (Rs at 1 kHz); ceramic capacitor Cs 98.19 nF with D 0.000 at 1 kHz, 98.34 nF with D 0.003 at 100 kHz. Model: capacitor as Cs in series with D / (2πf·Cs), C and D interpolated in log frequency between the two readings, plus the 10X probe on the output node (10 MΩ parallel 12 pF, nominal).

   | Band | Gain, measured minus model | Phase, measured minus model |
   |---|---|---|
   | 50 Hz to 1 kHz | mean −0.004 dB, largest 0.019 dB | mean −0.01°, largest 0.11° |
   | 1 kHz to 10 kHz | mean −0.059 dB, largest 0.107 dB | mean −0.20°, largest 0.45° |
   | 10 kHz to 100 kHz | mean −0.060 dB, largest 0.088 dB | mean +0.17°, largest 0.47° |
   | 100 kHz to 1 MHz | mean −0.18 dB, largest 0.62 dB | mean +1.3°, largest 3.0° |

   Measured −3 dB point 1615.8 Hz against 1624.5 Hz from the LCR values (−0.5 %). The steady −0.06 dB in the stop band equals a product R·C that is 0.7 % larger than the LCR readings give; the DUT channel also steps down through its V/div ranges there, and their gain differences (up to about 0.09 dB, 13.12) are not corrected by a through calibration. Which of the two it is was not separated. First flagged point: 818 kHz (`LOW_SNR`, −54.6 dB); from 1.15 MHz `BELOW_FLOOR`.
4. **Disconnect, connect again:** the status bar shows the skew as UNCHECKED and no calibration. The calibration did not survive the reconnect, as designed.

Also reported by the user: no skew prompt on connect. That is the behaviour decided on 2026-10-06 (13.28 and `docs/STATE.md`: the status bar and the log say that the check is needed; only starting a Sine fit sweep without a check or a calibration asks).
