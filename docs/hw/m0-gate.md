# Hardware history: Milestone 0 hardware gate, verdicts and sections 1 to 11 (2026-10-05)

Part of the hardware report. The current facts and the index of all sections: `HW_REPORT.md`. This file is a dated record of what was run and seen; it is not rewritten when a later run changes the picture, so read the facts sheet first.

Date: 2026-10-05. Machine: this Windows PC only. Linux was not tested.

## Verdict after Milestone 0b and 0c: GO WITH WORKAROUNDS

Unchanged in name, but on a much firmer basis than after Milestone 0. Section 12 has the 0b detail. In short:

- **Backend is now the free one.** NI-VISA was dropped (its licence is not free for this use). Everything in 0b ran on pyvisa-py + WinUSB.
- **The I/O layer (`hwcheck/iolayer.py`) works and is tested:** 55 of 55 checks, including deliberately forcing the scope out of step and recovering.
- **Two channels can be read from one acquisition:** 450 of 450 valid captures (runs A, B, C) at 1 kHz, 1 MHz and 20 MHz with 0 errors, about 0.77 s each.
- **Channel-to-channel error, final wiring (run C, section 12.6):** gain within +0.07 / −0.16 dB and phase within 0.24° at 1 kHz, 1 MHz and 20 MHz. Repeatability is excellent (0.03° to 0.3° standard deviation).
- **Milestone 0c, 10X probes (section 12.10):** amplitude decodes to 1 Vpp within 1.5% up to 20 MHz, gain within 0.03 dB, phase within 0.1° to 1 MHz and +1.1° at 20 MHz; a clean probe swap puts the scope's own share at about +0.09 dB and +0.9° at 20 MHz. At 50 mVpp the SNR drops to 21 to 28 dB but results hold. **Use 10X by default; 1X only for small signals below about 1 MHz.**
- **The phase offsets that came and went all day are explained (section 12.11), and they were neither wiring nor a fixed scope delay.** A `:RUN` command sent after the USB session has been reopened shifts the scope's CH2 against CH1 by a whole number of 2 ns steps, about half the time, and the shift stays. My own test scripts did exactly that at every start. The I/O layer now never sends `:RUN`; with that change, 50 of 50 reconnects left the alignment untouched (26 of 50 shifted it before). Earlier statements in this report that blamed the wiring (sections 12.6 and 12.10) and, before that, a fixed 4.1 ns scope delay, are both wrong and are marked as such.

What still stands between this and a plain GO:

1. **The scope's channel alignment can be shifted by whole samples (2, 4 or 6 ns: 15°, 30°, 43° at 20 MHz) and nothing documented puts it back.** The known trigger is avoided by the layer, but whether other things re-roll it (the front panel's Run/Stop key, a power cycle, vendor software) is not tested, and which state the scope powers up in is not known. A shift is invisible at 1 kHz. So v1 needs a "both probes on one node" check before a sweep, with the measured delay either corrected in software or cleared by the re-roll tool (`hwcheck/s0c_realign.py`). SPEC.md schedules that kind of calibration for v2.
2. **The dual-channel test was done with two 1X probes on the generator output, not a BNC tee** (none available). A tee measurement is still the cleaner baseline.
3. **Using the scope's front panel while a test runs breaks it** (commands ignored, empty captures). The app will need to lock the panel or tolerate this; the lock command is documented but not tested.
4. **The scope "froze" once** while a test was being killed mid-run; the cause was not confirmed.
5. Linux is still untested. The Milestone 0 items below still apply.

---

## Verdict after Milestone 0 (original text): GO WITH WORKAROUNDS

Both instruments can be identified and controlled over USB on this machine, on two independent backends. End-to-end generator → scope measurements are correct at 1 kHz, 1 MHz and 20 MHz, 200 consecutive query/acquire cycles ran with 0 errors on each backend, and both instruments reopen after a USB replug.

It is not a plain GO because:

1. **The scope is not the model in the spec.** It identifies as `UPO1054`, and you confirmed the nameplate says UPO1054. SPEC.md says UPO1052 throughout.
2. **The scope's USB reply handling can go out of step**, and one time it could only be recovered by a power cycle. The trigger is known and avoidable (section 8, findings S4 and S5), but the driver must be written around it.
3. **The generator hangs on a query it does not know** (`*OPC?`) until a USBTMC clear is sent (finding G2).
4. Several command arguments behave differently from the manual (findings S1 to S3, S6, S7).

Every workaround below was exercised on hardware except where marked "not verified".

---

## 1. Environment

| Item | Value |
|---|---|
| OS | Microsoft Windows 11 Home, version 10.0.26200 (build 26200), 64-bit |
| Python | 3.14.6 (`C:\Users\mazen\AppData\Local\Python\pythoncore-3.14-64\python.exe`) |
| venv | `.venv-hwcheck` in the project root |
| Packages | PyVISA 1.16.2, PyVISA-py 0.8.1, pyusb 1.3.1, libusb-package 1.0.30.0 (plus their dependencies importlib_resources, typing_extensions) |
| Scripts | `hwcheck/`, raw results in `hwcheck/results/*.json` |

Notes:

- SPEC.md and both manuals live in `docs/`. I treated `C:\Users\mazen\Desktop\bodeplotter` as the project root, so `hwcheck/`, `.venv-hwcheck/` and this file are there.
- Python 3.14 satisfies the spec's "3.11+", but the spec's launcher only tries `py -3.12`, `py -3.11`, then `python`. PySide6 support for 3.14 was not checked here (no application packages were installed).
- The manuals could not be read as PDFs (no `pdftoppm` on this machine). I extracted their text with `pypdf` in a throwaway venv outside the project. Figures in the manuals were therefore not seen.
- Manual file names differ from SPEC.md section 2: present are `Uni-T_UPO1002_Programming_Manual_0824.pdf` and `UTG900E Programming Manual V1.0.pdf`. The ELV manual and the EEVblog command list are not in `docs/`.

## 2. USB enumeration and drivers

| | Scope | Generator |
|---|---|---|
| VID:PID | `5656:0832` | `6656:0834` |
| Serial | `APX1424510001` | `69746177` |
| Bus-reported name | `UPO-1000X` | `UTG900E` |
| USB manufacturer string | `UNI-T Inc.` | `uni-trend` |
| Interface class | FE / 03 / 01 (USBTMC, USB488) | FE / 03 / 01 (USBTMC, USB488) |
| Endpoints | 0x81 IN, 0x01 OUT | 0x01 OUT, 0x81 IN |

Driver history on this machine:

| Stage | Driver bound | Status |
|---|---|---|
| As found | none | Error, problem code 28 (no driver). No VISA library installed. |
| After Zadig 2.9 | `WinUSB` (libwdi 6.1.7600.16385, `oem98.inf` / `oem99.inf`) | OK |
| After NI-VISA 26.5.0 | `Usbtmc` (`ausbtmc.inf`, IVI Foundation 16.3.17614.0, `oem101.inf`) | OK |

Installing NI-VISA replaced the WinUSB binding by itself; no manual driver switch was needed. **The machine is now in the NI-VISA state**, so `@py` no longer sees the instruments. Going back to `@py` means re-running Zadig for both devices.

Software installed system-wide during this session: Zadig 2.9.788 (winget `akeo.ie.Zadig`), NI Package Manager 26.5 and NI-VISA 26.5.0 (winget `NI.ni-visa`, installed with `--accept-package-agreements`, i.e. the NI EULA was accepted through winget on your behalf). The first NI-VISA install attempt failed with installer exit code 4294841481 after installing only NI Package Manager; an identical retry succeeded.

## 3. VISA resources and backends

| Driver state | `@py` (pyvisa-py) | `@ivi` |
|---|---|---|
| No driver | no resources; libusb does not find the devices | no IVI library installed (pyvisa fell back to py) |
| WinUSB | `USB0::22102::2098::APX1424510001::0::INSTR`, `USB0::26198::2100::69746177::0::INSTR` | no IVI library installed |
| NI `Usbtmc` | no resources; libusb sees the devices but cannot open them (`NotImplementedError`) | `USB0::0x5656::0x0832::APX1424510001::INSTR`, `USB0::0x6656::0x0834::69746177::INSTR` (plus `ASRL12::INSTR`, unrelated) |

The two backends are mutually exclusive on Windows because they need different drivers. Resource strings differ in format (decimal IDs plus interface number on `@py`, hex on `@ivi`), so the app must match on VID/PID/serial, not on the literal string.

## 4. Identity

| Instrument | `*IDN?` reply | Matches spec? |
|---|---|---|
| Scope | `UNI-T Technologies,UPO1054,APX1424510001,1. 01. 0047` | **No.** Spec says UPO1052. Nameplate confirmed UPO1054. |
| Generator | `UNI-T Technologies,UTG900E,69746177,1.09` | Partly. Reports the family name `UTG900E`, not `UTG932E`. |

Scope `:SYSTem:VERSion?` → `HW:V1. 04. 0000;SW:1. 01. 0047;PD:2023-11-3;ICV:20220605`.

Manual coverage flags:

- The UPO1002 manual says only "suitable for UPO1002 series" and documents channels as `<n>: {1|2}`. It never names UPO1052 or UPO1054. The UPO1054 accepted every documented command tried, but **CH3 and CH4 are not covered by the manual and were not tested**.
- The manual's `*IDN?` example shows a different field layout (`UNI-T Technologies, UPO1000X, UPO1000, 00.00.01`); the real reply is manufacturer, model, serial, firmware. The firmware field contains spaces (`1. 01. 0047`).
- The manual documents software version V1.00.0003; the scope runs 1.01.0047.
- The generator manual says the returned model "should be same as the nameplate"; it returns `UTG900E`. The exact model therefore cannot be read from `*IDN?`. The registry rule in SPEC.md 6.3 (`UNI-T` + `UTG9`) still matches; the scope rule (`UNI-T` + `UPO1`) also matches.
- The generator manual documents software V3.06.004; the unit reports `1.09`.

## 5. Command pass/fail table

Final clean run on each backend (`s04_s05_basic_py.json`, `s04_s05_basic_ivi.json`): **71 of 71 on `@py`, 71 of 71 on `@ivi`.** Earlier runs that failed are listed in section 8 and kept as `*_run1.json` / `*_run2.json`. Replies shown are from the `@py` run; the scope's original settings differed between the two runs (it had been adjusted in between), so restore targets differ.

UPO = `docs/Uni-T_UPO1002_Programming_Manual_0824.pdf` (page n of 137). UTG = `docs/UTG900E Programming Manual V1.0.pdf` (page n of 41).

| Instrument | Command sent | Action | Manual ref | Reply (@py) | @py | @ivi |
|---|---|---|---|---|---|---|
| scope | `*IDN?` | query | UPO p.7 | `UNI-T Technologies,UPO1054,APX1424510001,1. 01. 0047` | PASS | PASS |
| scope | `*OPC?` | query | UPO p.7 | `1` | PASS | PASS |
| scope | `:SYSTem:VERSion?` | query | UPO p.13 | `HW:V1. 04. 0000;SW:1. 01. 0047;PD:2023-11-3;ICV:20220605` | PASS | PASS |
| scope | `:SYSTem:ERRor?` | query | UPO p.9 | `0,"No error"` | PASS | PASS |
| scope | `:TRIGger:STATus?` | query | UPO p.53 | `AUTO` | PASS | PASS |
| scope | `:TRIGger:MODE?` | query | UPO p.52 | `EDGE` | PASS | PASS |
| scope | `:TRIGger:SWEep?` | query | UPO p.52-53 | `AUTO` | PASS | PASS |
| scope | `:TRIGger:SOURce?` | query | UPO p.54-55 | `CHANnel1` | PASS | PASS |
| scope | `:TRIGger:LEVel?` | query | UPO p.53-54 | `8.000000e-02` | PASS | PASS |
| scope | `:TRIGger:EDGE:SLOPe?` | query | UPO p.55-56 | `POSitive` | PASS | PASS |
| scope | `:TIMebase:MODE?` | query | UPO p.22 | `MAIN` | PASS | PASS |
| scope | `:TIMebase:OFFSet?` | query | UPO p.22-23 | `0.000000e+00` | PASS | PASS |
| scope | `:ACQuire:TYPE?` | query | UPO p.92 | `NORMal` | PASS | PASS |
| scope | `:ACQuire:MEMory:DEPTh?` | query | UPO p.93 | `7K` | PASS | PASS |
| scope | `:CHANnel1:DISPlay?` | query | UPO p.18 | `1` | PASS | PASS |
| scope | `:CHANnel1:PROBe?` | query | UPO p.19-20 | `1.000000e+00` | PASS | PASS |
| scope | `:CHANnel1:OFFSet?` | query | UPO p.20 | `0.000000e+00` | PASS | PASS |
| scope | `:CHANnel1:BWLimit?` | query | UPO p.17-18 | `FULL` | PASS | PASS |
| scope | `:CHANnel1:VERNier?` | query | UPO p.21 | `0` | PASS | PASS |
| scope | `:CHANnel1:SCALe?` | query | UPO p.20-21 | `2.000000e-01` | PASS | PASS |
| scope | `:CHANnel1:COUPling?` | query | UPO p.18 | `DC` | PASS | PASS |
| scope | `:CHANnel2:DISPlay?` | query | UPO p.18 | `0` | PASS | PASS |
| scope | `:CHANnel2:PROBe?` | query | UPO p.19-20 | `1.000000e+01` | PASS | PASS |
| scope | `:CHANnel2:OFFSet?` | query | UPO p.20 | `0.000000e+00` | PASS | PASS |
| scope | `:CHANnel2:BWLimit?` | query | UPO p.17-18 | `FULL` | PASS | PASS |
| scope | `:CHANnel2:VERNier?` | query | UPO p.21 | `0` | PASS | PASS |
| scope | `:CHANnel2:SCALe?` | query | UPO p.20-21 | `9.999999e-02` | PASS | PASS |
| scope | `:CHANnel2:COUPling?` | query | UPO p.18 | `DC` | PASS | PASS |
| scope | `:TIMebase:SCALe?` | query | UPO p.23-24 | `5.000000e-04` | PASS | PASS |
| scope | `:TIMebase:SCALe 0.001` | set | UPO p.23-24 | `1.000000e-03` | PASS | PASS |
| scope | `:TIMebase:SCALe 0.0005` | restore | UPO p.23-24 | `5.000000e-04` | PASS | n/a |
| scope | `:CHANnel1:SCALe 1` | set | UPO p.20-21 | `1.000000e+00` | PASS | PASS |
| scope | `:CHANnel1:SCALe 0.2` | restore | UPO p.20-21 | `2.000000e-01` | PASS | n/a |
| scope | `:CHANnel1:COUPling AC` | set | UPO p.18 | `AC` | PASS | PASS |
| scope | `:CHANnel1:COUPling DC` | restore | UPO p.18 | `DC` | PASS | PASS |
| scope | `*OPC?` | query2 | UPO p.7 | `1` | PASS | PASS |
| scope | `:SYSTem:ERRor?` | query2 | UPO p.9 | `0,"No error"` | PASS | PASS |
| gen | `*IDN?` | query | UTG p.5 | `UNI-T Technologies,UTG900E,69746177,1.09` | PASS | PASS |
| gen | `:CHANnel1:OUTPut?` | query | UTG p.9 | `0` | PASS | PASS |
| gen | `:CHANnel2:OUTPut?` | query | UTG p.9 | `0` | PASS | PASS |
| gen | `:SYSTem:LOCK?` | query | UTG p.5 | `1` | PASS | PASS |
| gen | `:CHANnel1:MODe?` | query | UTG p.15-16 | `CONTinue` | PASS | PASS |
| gen | `:CHANnel1:BASE:WAVe?` | query | UTG p.11-12 | `SINe` | PASS | PASS |
| gen | `:CHANnel1:AMPLitude:UNIT?` | query | UTG p.11 | `VRMS` | PASS | PASS |
| gen | `:CHANnel1:BASE:OFFSet?` | query | UTG p.13 | `0.000000e+00` | PASS | PASS |
| gen | `:CHANnel1:BASE:PHASe?` | query | UTG p.12-13 | `0.000000e+00` | PASS | PASS |
| gen | `:CHANnel1:BASE:FREQuency?` | query | UTG p.12 | `5.000000e+01` | PASS | PASS |
| gen | `:CHANnel1:BASE:AMPLitude?` | query | UTG p.13 | `4.700000e+00` | PASS | PASS |
| gen | `:CHANnel1:LOAD?` | query | UTG p.11 | `1.000000e+04` | PASS | PASS |
| gen | `:CHANnel2:MODe?` | query | UTG p.15-16 | `CONTinue` | PASS | PASS |
| gen | `:CHANnel2:BASE:WAVe?` | query | UTG p.11-12 | `SINe` | PASS | PASS |
| gen | `:CHANnel2:AMPLitude:UNIT?` | query | UTG p.11 | `VPP` | PASS | PASS |
| gen | `:CHANnel2:BASE:OFFSet?` | query | UTG p.13 | `0.000000e+00` | PASS | PASS |
| gen | `:CHANnel2:BASE:PHASe?` | query | UTG p.12-13 | `0.000000e+00` | PASS | PASS |
| gen | `:CHANnel2:BASE:FREQuency?` | query | UTG p.12 | `1.000000e+03` | PASS | PASS |
| gen | `:CHANnel2:BASE:AMPLitude?` | query | UTG p.13 | `1.000000e-01` | PASS | PASS |
| gen | `:CHANnel2:LOAD?` | query | UTG p.11 | `1.000000e+04` | PASS | PASS |
| gen | `:CHANnel1:BASE:FREQuency 1234` | set | UTG p.12 | `1.234000e+03` | PASS | PASS |
| gen | `:CHANnel1:BASE:FREQuency 50` | restore | UTG p.12 | `5.000000e+01` | PASS | PASS |
| gen | `:CHANnel1:BASE:AMPLitude 0.5` | set | UTG p.13 | `5.000000e-01` | PASS | PASS |
| gen | `:CHANnel1:BASE:AMPLitude 4.7` | restore | UTG p.13 | `4.700000e+00` | PASS | PASS |
| gen | `:CHANnel1:LOAD 50` | set | UTG p.11 | `5.000000e+01` | PASS | PASS |
| gen | `:CHANnel1:LOAD 10000` | restore | UTG p.11 | `1.000000e+04` | PASS | PASS |
| gen | `:CHANnel1:BASE:AMPLitude?` | recheck | UTG p.13 | `4.700000e+00` | PASS | PASS |
| gen | `:CHANnel1:OUTPut?` | final | UTG p.9 | `0` | PASS | PASS |
| gen | `:CHANnel2:OUTPut?` | final | UTG p.9 | `0` | PASS | PASS |

Additional commands exercised in the end-to-end and robustness scripts (both backends, all worked unless noted):

| Instrument | Command | Manual ref | Result |
|---|---|---|---|
| scope | `:RUN`, `:STOP` | UPO p.8 | PASS |
| scope | `:CHANnel1:DISPlay 1` | UPO p.18 | PASS |
| scope | `:CHANnel1:PROBe 1X` | UPO p.19-20 | PASS with `X` suffix. **FAIL without it** (finding S2) |
| scope | `:CHANnel1:BWLimit FULL` | UPO p.17-18 | PASS |
| scope | `:CHANnel1:OFFSet 0.2` / `0` | UPO p.20 | PASS when followed by `*OPC?`. Dropped once when sent back to back (finding S3) |
| scope | `:ACQuire:TYPE NORMal` | UPO p.92 | PASS |
| scope | `:TIMebase:OFFSet 0` | UPO p.22-23 | PASS |
| scope | `:TIMebase:SCALe 0.0000005` | UPO p.23-24 | PASS (reads back 5e-07) |
| scope | `:TIMebase:SCALe 0.00000002` | UPO p.23-24 | **FAIL**: reads back 1e-08 (finding S6) |
| scope | `:TRIGger:MODE EDGE`, `:TRIGger:SOURce CHANnel1`, `:TRIGger:EDGE:SLOPe POSitive`, `:TRIGger:LEVel 0`, `:TRIGger:SWEep AUTO` / `SINGle` | UPO p.52-56 | PASS |
| scope | `:WAVeform:SOURce CHANnel1`, `:WAVeform:MODE NORMal`, `:WAVeform:FORMat BYTE` | UPO p.98-100 | PASS |
| scope | `:WAVeform:PREamble?` | UPO p.101-102 | PASS, but "Points" field is wrong (finding S7) |
| scope | `:WAVeform:DATA?` | UPO p.100-101 | PASS when a screen record exists. Empty reply otherwise (finding S4) |
| scope | `:WAVeform:XINCrement?`, `:YINCrement?`, `:YORigin?`, `:YREFerence?` | UPO p.102-104 | PASS |
| scope | `:WAVeform:POINts?` | UPO p.100 | **FAIL**: empty reply |
| scope | `:WAVeform:STARt?`, `:WAVeform:STOP?` | UPO p.99 | Reply `0` and `-1`; manual says 1 to 1400. Not usable |
| scope | `:MEASure:VPP? CHANnel1`, `:MEASure:FREQuency? CHANnel1` | UPO p.44, p.48 | PASS |
| gen | `:CHANnel1:OUTPut ON` / `OFF` | UTG p.9 | PASS |
| gen | `:CHANnel1:BASE:WAVe SINe` | UTG p.11-12 | PASS |
| gen | `:CHANnel1:AMPLitude:UNIT VPP` / `VRMS` | UTG p.11 | PASS |
| gen | `:CHANnel1:BASE:OFFSet 0` | UTG p.13 | PASS |
| gen | `:CHANnel1:BASE:FREQuency 1000000` / `20000000` | UTG p.12 | PASS |
| gen | `*OPC?` | **not in the UTG manual** | **FAIL**: timeout, can hang the generator (finding G2) |

Not tested: `*RST`, `:SYSTem:CAL`, `:SYSTem:CLEAr`, `:SYSTem:SETup`, `:SYSTem:CONFigure`, `:AUTO`, any save/recall, firmware or LAN-setting command (excluded as destructive or out of scope). Also not tested: scope CH2 set commands, CH3/CH4, `:MEASure:PHASe?`, `:MEASure:VAMPlitude?`, RAW waveform mode, WORD/ASCII formats, LAN access.

## 6. End-to-end test (generator CH1 → scope CH1, BNC)

Generator: sine, 1 Vpp, load 10000 Ω (High-Z), offset 0, output ON only during this step. Scope: CH1 DC, probe 1X, 0.2 V/div, edge trigger on CH1 at 0 V, NORMal waveform mode, BYTE format. Volts decoded as `(code − YREF − YOR) × YINC`, sine fitted with frequency free.

| Backend | Set | Fitted frequency | Error | Fitted Vpp (STOP fetch) | Fitted Vpp (SINGLE) | Scope `:MEASure:VPP?` | Fit SNR |
|---|---|---|---|---|---|---|---|
| `@py` | 1 kHz | 1000.01 Hz | +0.001% | 0.9825 V | 0.9828 V | 1.000 V | 35.6 dB |
| `@py` | 1 MHz | 999 988 Hz | −0.001% | 0.9894 V | 0.9992 V | 1.000 V | 35.5 dB |
| `@py` | 20 MHz | 19.9914 MHz | −0.043% | 0.9735 V | 0.9709 V | 0.992 V | 35.2 dB |
| `@ivi` | 1 kHz | 999.95 Hz | −0.005% | 0.9848 V | 0.9843 V | 1.000 V | 35.5 dB |
| `@ivi` | 1 MHz | 999 954 Hz | −0.005% | 0.9916 V | 0.9922 V | 1.000 V | 35.1 dB |
| `@ivi` | 20 MHz | 19.9855 MHz | −0.072% | 0.9966 V | 0.9999 V | 1.008 V | 34.9 dB |

All within about 3% of 1 Vpp and 0.1% of the set frequency. No clipping (ADC codes 62 to 190 of 0 to 255). Generator outputs read back `0, 0` at the end of every run, and every changed setting on both instruments read back as restored in the final runs.

What the waveform readout looks like on this scope:

| Item | Observed | Manual says |
|---|---|---|
| Points per screen record (NORMal) | **700** | 1 to 1400 (p.99) |
| Block format | `#3700` + 700 bytes + CR LF | IEEE 488.2 block (App. 2) |
| Sample interval | timebase / 50 (e.g. 10 µs at 500 µs/div) | timebase / 50 (p.102) |
| Screen width | 14 divisions (XORigin = −7 × timebase) | same (p.103) |
| YINC | V/div / 25, **input-referred** (ignores probe ratio) | V/div / 25 (p.103) |
| YREF | 128 | 128 (p.104) |
| YOR | offset / YINC, in codes (25 for +0.2 V at 0.2 V/div) | same (p.104) |
| Vertical divisions | 255 codes / 25 codes per div ≈ 10.2 div of ADC range | not stated. On-screen division count not verified |
| ADC rail codes | not reached; 0 and 255 assumed | not stated |

The sign of YOR was checked directly: with a zero-mean signal and CH1 offset +0.2 V, `(code − YREF − YOR) × YINC` gives a mean of −1.5 mV (`@py`) and −0.9 mV (`@ivi`). The alternatives give +199 mV and +399 mV. So the formula above is correct.

At 20 MHz the record is 700 points at 0.2 ns, i.e. 5 GSa/s equivalent, which is above the scope's real sample rate. Those points are interpolated by the scope. The fit still works, but the driver should not treat them as independent samples.

Single-shot acquisition (`:TRIGger:SWEep SINGle`, `:RUN`, poll `:TRIGger:STATus?` until `STOP`) completed in 0.27 to 0.33 s each time. In two of six runs the very first status poll already returned `STOP`; I could not tell whether that was the new acquisition finishing fast or a stale status. Not verified.

## 7. Timing and robustness

Timing (scope at 5 ms/div, no input signal, generator outputs OFF):

| Measurement | `@py` | `@ivi` |
|---|---|---|
| Scope `*IDN?` round trip, 20 runs | 2.9 ms mean (2.2 to 5.2) | 3.1 ms mean (2.0 to 7.9) |
| Generator `*IDN?` round trip, 20 runs | 0.50 ms mean (0.48 to 0.52) | 0.42 ms mean (0.39 to 0.46) |
| Waveform `:STOP` + wait + preamble + 700-point fetch + decode + `:RUN`, 10 runs | 224 ms mean (208 to 240) | 218 ms mean (199 to 240) |
| Waveform preamble + fetch + decode while running, 10 runs | 233 ms mean (208 to 262) | 234 ms mean (207 to 277) |

The waveform figures exclude the 0.3 s run-time guard (finding S4). With the guard, one full cycle is about 0.61 s. The fetch is slow for 700 bytes; the time is spent in the scope, not on the host.

Robustness:

| Test | `@py` | `@ivi` |
|---|---|---|
| 200 cycles of: gen `*IDN?`, gen frequency query, scope `*IDN?`, scope timebase query, guarded STOP waveform fetch + decode | 200/200, 0 errors, 0 resyncs, 122 s | 200/200, 0 errors, 0 resyncs, 123 s |
| Reopen after USB replug of both cables (instruments powered) | PASS both | PASS both |
| Reopen after power cycle of both instruments | PASS both (done once, during troubleshooting) | not done |

The 200-cycle run only passed after the workarounds in section 8 were in place. The first attempt (`@py`, no guard) failed in the timing phase before reaching the loop.

## 8. Findings and troubleshooting log

Every attempt is listed, including the ones that failed.

### Drivers

- **D1. No driver, no VISA.** Both devices showed problem code 28. `@py` listed nothing and libusb could not find them. Fixed by binding WinUSB with Zadig (you did this in the Zadig window).
- **D2. NI-VISA install.** First `winget install NI.ni-visa` failed (installer exit code 4294841481, only NI Package Manager installed). Second identical attempt succeeded after more than 10 minutes and rebound both devices to the IVI `Usbtmc` driver.

### Scope (UPO1054)

- **S1. Exponent notation is silently ignored for V/div.** `:CHANnel1:SCALe 2.000000e-01` left the scale unchanged with `0,"No error"`; `:CHANnel1:SCALe 0.2` and `200mV` worked (`dbg_vdiv.py`). `:TIMebase:SCALe 5.000000e-04` was accepted, so it is command-dependent. Workaround used everywhere after: plain decimals only.
- **S2. Probe ratio needs the `X` suffix.** `:CHANnel1:PROBe 1` set 10X and `:CHANnel1:PROBe 10` set 100X; `1X`, `10X`, `100X` work (`dbg_probe.py`). With a probe ratio other than 1X, `:CHANnel<n>:SCALe` takes an input-referred value but `:CHANnel<n>:SCALe?` and `:MEASure:VPP?` return probe-scaled values, while YINC and the decoded waveform stay input-referred (1 Vpp at 10X: `:MEASure:VPP?` = 10.0 V, decoded = 0.985 V). Simplest driver rule: keep the scope at 1X and apply probe attenuation in software.
- **S3. Commands sent back to back can be dropped.** An `:CHANnel1:OFFSet 0.2` written straight after a `:TIMebase:SCALe` write was lost with no error (`s06` run 2). Workaround: follow every scope write with `*OPC?` (replies `1`). Not seen again afterwards.
- **S4. `:WAVeform:DATA?` returns an empty reply when no screen record exists.** Seen (a) once at 1 MHz in `s06` run 2, (b) every time in the first timing run, (c) in 4 of about 18 trials when `:STOP` was sent 0 to 0.2 s after `:RUN` at 5 ms/div (`dbg_wave2.py`), and (d) always in SCAN/roll status at 50 ms/div (`dbg_wave.py`). Retrying while stopped never helps. Workaround: let the scope run for `max(0.3 s, 30 × timebase)` before `:STOP`, wait for `:TRIGger:STATus?` = `STOP`, then fetch. With this, 400 of 400 fetches succeeded. Timebases of 50 ms/div and slower were not made to work and are not needed for 50 Hz and up.
- **S5. Replies can go one step out of sync, and once could not be recovered without a power cycle.** After empty-reply `:WAVeform:DATA?` queries, the missing waveform blocks arrived later as the answers to unrelated queries. In one case (after the SCAN-mode test, with my script aborting mid-read) the scope stayed permanently one reply behind: every query returned the previous query's answer regardless of delay, across new sessions. Recovery attempts, in order: reading extra replies (no effect: the scope re-sends its last reply forever on a bare read instead of timing out, which also hung my first drain loop), USBTMC `INITIATE_CLEAR` (accepted, no effect), two back-to-back queries (no effect), `INITIATE_ABORT_BULK_IN` (then writes failed with "Pipe error"), USB port reset (then writes timed out). You then power-cycled both instruments, which fixed it. I do not know whether a plain USB replug would have been enough, because the abort and reset steps had already made things worse. In the second occurrence (`dbg_wave2.py`) the scope was back in step in the next session by itself. Workarounds: avoid S4 entirely, never retry an empty `:WAVeform:DATA?`, and verify step with a sentinel (`*IDN?` must return an IDN string) after any error. The `resync()` helper in `hwcheck/wave.py` was written for this but was never triggered in the 400 guarded cycles, so it is **not verified**.
- **S6. `:TIMebase:SCALe 0.00000002` gives 10 ns/div**, not 20 ns/div, on both backends. Cause not investigated. The driver must read the timebase back and use the value the scope reports. **Explained in 0b:** 20 ns/div is not a step this scope has (10 ns, then 25 ns, then 50 ns), so it snapped to a real step. Not a defect. See section 12.2.
- **S7. Preamble "Points" field reads 1000 while the block holds 700 points**, and `:WAVeform:POINts?` returns an empty reply. Use the block length.
- **S8. Termination.** Scope replies end with CR LF (`\r\n`). `read_termination='\n'` plus strip works on both backends.
- **S9. `*OPC?` works** on the scope and returns `1`.

### Generator (UTG900E / UTG932E)

- **G1. No reply terminator.** Replies end with no CR or LF at all (raw `*IDN?` ends `...1.09`); the end is signalled only by the USBTMC end-of-message flag. `@py` tolerated `read_termination='\n'`, but `@ivi` then timed out on every generator query (`s04_s05_basic_ivi_run1.json`, 39 of 59). With `read_termination=None` both backends pass 71 of 71.
- **G2. `*OPC?` is not supported and can hang the interface.** It is not in the UTG manual; I probed it once deliberately. Run 1: timeout, generator recovered. Run 2: timeout, then every later query timed out, also in a new session. Recovered with USBTMC `INITIATE_CLEAR` + clear-halt sent through pyusb (`dbg_gen_recover.py`), without a replug. pyvisa-py's own `inst.clear()` returned `VI_ERROR_NSUP_OPER` on this resource, and that pyusb route is not available under the NI driver; NI-VISA's `viClear` was not tried. Rule for the driver: never send the generator a query that is not in its manual.
- **G3. `:SYSTem:LOCK?` returns `1`** whenever queried over USB. I did not change it. If the front panel stays locked after remote use, `:SYSTem:LOCK OFF` (UTG p.5) is the documented release; not tested.
- **G4. Amplitude unit matters.** CH1 was in VRMS as found; `:CHANnel1:BASE:AMPLitude` is in the channel's current unit, so the driver must set `:CHANnel<n>:AMPLitude:UNIT VPP` first.
- **G5. Load.** `:CHANnel1:LOAD 10000` is High-Z and `50` is 50 Ω, as the manual says. Toggling the load did not change the amplitude readback.
- Not checked: output glitch or phase reset on frequency change, amplitude limits per load, CH2 output.

### Things I changed and could not put back exactly

- The scope and generator were power-cycled and their settings were also adjusted from the front panel between my runs, so "original state" is not well defined. The scope is currently at 5 ms/div, CH1 5 V/div, 1X, DC, edge trigger on CH1, Auto sweep, running. The trigger level was 80 mV at my very first query and 0 V later; it is 0 V now. The generator is at CH1 sine 50 Hz, 4.7 Vrms, High-Z, **both outputs OFF**.
- During `s06` run 1 the probe-ratio bug (S2) made my restore set CH1 to 10X / 200 V/div; I corrected it to 1X in the next step.

## 9. Recommended backend per OS

| OS | Recommendation | Basis |
|---|---|---|
| Windows | **`@py` (pyvisa-py) with the WinUSB driver bound by Zadig.** Revised in 0b; the Milestone 0 text recommended NI-VISA. | Both backends passed every Milestone 0 test with the same results and timing. NI-VISA is not free for this use: NI includes a licence only with NI software or NI hardware, and otherwise sells a per-computer deployment licence (listed from 201 USD; price seen second-hand). `@py` is free, and all of 0b was run on it. Its costs: one Zadig step per instrument, vendor PC software cannot see the instruments while WinUSB is bound, and pyvisa-py has no USB device clear (the I/O layer sends it through pyusb). NI-VISA 26.5 is still installed on this PC but unused; it should be uninstalled. Rohde & Schwarz VISA and Keysight IO Libraries are advertised as free alternatives; neither was tested here and their licence terms were not read. |
| Linux | `@py` (pyvisa-py + libusb) with a udev rule for `5656:0832` and `6656:0834`. | **Not tested.** This is a prediction only. The kernel `usbtmc` module may claim the devices first; whether that conflicts with pyvisa-py on these instruments is unknown. Needs its own gate run on a Linux machine. |

The spec's default of `auto` (try `@ivi`, fall back to `@py`) should become `@py` first, with `@ivi` only for users who already have a licensed VISA.

## 10. What this means for the spec

Decisions for you before Milestone 1:

1. **Scope model.** Update SPEC.md from UPO1052 to UPO1054 (4 channels). The manual in `docs/` documents 2 channels only, so CH3/CH4 commands would be `verified=False` until probed.
2. **Driver I/O rules to add to SPEC.md 9.1 / 9.2 / 9.3:**
   - Scope: plain-decimal arguments, `X` suffix on probe ratio, `*OPC?` after every write, read back timebase and V/div and use the reported values, run-time guard before `:STOP`, never retry an empty waveform block, sentinel check after any error.
   - Generator: no read termination, set amplitude unit before amplitude, never send `*OPC?` or any undocumented query, inter-command pacing by delay instead of `*OPC?`.
   - SPEC.md 9.1 says "Default `\n`; verify" for termination and "`*OPC?` or a configurable delay": both need per-instrument settings.
3. **Per-point time.** A guarded acquisition costs about 0.6 s, so a sweep point with autorange retries and averaging will be on the order of 1 to 3 s. A 50 Hz to 20 MHz sweep at 20 points/decade (113 points) is therefore a few minutes, before settling time at low frequencies.
4. **Screen record is 700 points over 14 divisions.** `min_samples_per_cycle = 20` with `target_cycles = 5` gives 700 / 5 = 140 points per cycle, which is fine, but the timebase choice must use 14 divisions and the 1-2-5 steps the scope actually accepts.

Still open from SPEC.md section 17: on-screen vertical division count, ADC rail codes, V/div range limits, LAN resource format, generator behaviour on frequency change, whether a plain USB replug recovers the out-of-step state, and anything about CH2 to CH4 as the DUT channel. The dual-channel same-acquisition readout that the Bode measurement depends on was **not** tested here; only CH1 was read.

## 11. Files

| Path | Purpose |
|---|---|
| `hwcheck/common.py`, `scpi.py`, `wave.py`, `usbclear.py` | shared helpers; `scpi.py` holds every command string with its manual page |
| `hwcheck/s03_visa_list.py` | step 3 |
| `hwcheck/s04_s05_basic.py` | steps 4 and 5 |
| `hwcheck/s06_end_to_end.py` | step 6 (the only script that turns an output on) |
| `hwcheck/s07_s08_timing_robust.py`, `s08b_reconnect.py` | steps 7 and 8 |
| `hwcheck/dbg_*.py` | troubleshooting scripts referenced in section 8 |
| `hwcheck/make_table.py` | builds the table in section 5 |
| `hwcheck/results/` | raw JSON for every run, including failed ones |

---
