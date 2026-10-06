# HW_REPORT — Milestone 0, 0b and 0c hardware gate

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

## 12. Milestone 0b

Run on 2026-10-05, same PC. All 0b results are on `@py` (pyvisa-py + WinUSB) unless stated. Raw data: `hwcheck/results/t0b_iolayer_py.json`, `s0b_dual_py_probes_1x_A.json`, `s0b_dual_py_probes_1x_B_swapped.json`, `dbg0b_probe.json`.

### 12.1 Scope commands re-verified against the UPO1000 manual

Manual: `docs/Uni-T_UPO1000_Programming_Manual_0424.pdf` (99 pages, file number 20230822, software V1.00.0018; the scope runs 1.01.0047). Text was extracted with pypdf, so figures were not seen.

Result: **every scope command used in Milestone 0 and in the I/O layer exists in the UPO1000 manual with the same syntax.** The two manuals are near-identical; the UPO1000 one covers four channels. Page references (n of 99):

| Command | UPO1000 page | Differs from the UPO1002 manual? |
|---|---|---|
| `*IDN?`, `*OPC?` | 5 | No. IDN example still shows a different field layout from the real reply |
| `:RUN`, `:STOP` | 5-6 | No |
| `:SYSTem:ERRor?` | 6 | No |
| `:SYSTem:VERSion?` | 9 | No |
| `:CHANnel<n>:BWLimit`, `:COUPling`, `:DISPlay` | 12-13 | `<n>` is now {1\|2\|3\|4} |
| `:CHANnel<n>:PROBe` | 14 | `<n>` 1 to 4. Example is still `10X` |
| `:CHANnel<n>:OFFSet`, `:SCALe` | 14 | `<n>` 1 to 9 (CH1-4, MATH, REFA-D) |
| `:CHANnel<n>:VERNier` | 15 | `<n>` 1 to 4 |
| `:TIMebase:MODE`, `:OFFSet`, `:SCALe` | 15-16 | No |
| `:MEASure:VPP?`, `:MEASure:PHASe?` | 30 | Sources now CHANnel1 to CHANnel4 |
| `:MEASure:FREQuency?` | 33 | Same |
| `:TRIGger:MODE`, `:FORCe`, `:SWEep` | 36-37 | No |
| `:TRIGger:STATus?`, `:TRIGger:LEVel` | 37 | No |
| `:TRIGger:SOURce` | 38 | CHANnel1 to CHANnel4, EXT, ACLINE |
| `:TRIGger:EDGE:SLOPe` | 39 | No |
| `:ACQuire:TYPE`, `:ACQuire:MEMory:DEPTh` | 65 | No |
| `:WAVeform:MODE`, `:FORMat`, `:STARt` | 69 | No |
| `:WAVeform:STOP`, `:SOURce`, `:POINts`, `:DATA?` | 70-71 | Source CHANnel1 to CHANnel4 |
| `:WAVeform:PREamble?` | 71 | No |
| `:WAVeform:XINCrement?`, `:XORigin?`, `:YINCrement?` | 72 | No |
| `:WAVeform:YORigin?`, `:YREFerence?` | 73 | No |

What the correct manual does and does not explain:

| Milestone 0 finding | Explained by the UPO1000 manual? |
|---|---|
| CH3 / CH4 not documented | **Yes.** Channels 1 to 4 are documented. CH3 and CH4 answer queries on hardware (display, probe, V/div, offset, coupling, BW limit). Set commands and waveform read-out on CH3/CH4 were not tested. |
| S1 exponent notation ignored | Not stated, but consistent: every command example uses plain decimals or a unit suffix (`0.005`, `500 mV`, `20V`, `1s`). Exponents appear only in replies. |
| S2 probe ratio needs `X` | Only by example (`:CHAN1:PROB 10X`). The effect of a bare number is not described. |
| S3 back-to-back writes dropped | No. |
| S4 / S5 empty waveform reply, replies out of step | No. |
| S6 20 ns/div became 10 ns/div | No. Explained by the hardware instead: see 12.2. |
| S7 preamble Points = 1000, 700 points returned, `:WAVeform:POINts?` empty | No. This manual also says NORMal mode is 1 to 1400 points. |
| Single-shot behaviour (12.3) | No. The manual lists `SINGle` as a sweep value and says nothing about arming or `:RUN`. |

The manual also contradicts itself in places (`:SYSTem:LOCK?` is described as "0 represents locked" and then exemplified as "returns 1, it represents locked"; the bandwidth-limit example uses `ON` where the syntax says `20M | FULL`). None of those commands is used.

### 12.2 What the hardware really accepts

Step tables read from the scope by walking `UP` / `DOWN` (probe 1X, coarse V/div):

| Setting | Real steps |
|---|---|
| Timebase (s/div), walked up to 20 ms | 1 ns, 2 ns, 5 ns, 10 ns, **25 ns**, 50 ns, 100 ns, 200 ns, 500 ns, 1 µs, 2 µs, 5 µs, 10 µs, 20 µs, 50 µs, 100 µs, 200 µs, 500 µs, 1 ms, 2 ms, 5 ms, 10 ms, 20 ms |
| V/div | 500 µV, 1 mV, 2 mV, 5 mV, 10 mV, 20 mV, 50 mV, 100 mV, 200 mV, 500 mV, 1 V, 2 V, 5 V, 10 V, 20 V |

Every one of those 23 timebase and 15 V/div values sets and reads back exactly with a plain-decimal argument (V/div on CH1 and CH2). A request for 20 ns/div lands on 10 ns/div whatever the format (`0.00000002`, `20ns`, `2e-8`), because 20 ns is not a step.

Other behaviour found in 0b:

- **Offset and trigger level are quantised** to one ADC code, V/div / 25 (0.2 V offset at 20 V/div reads back 0; 0.1 V trigger level at 0.2 V/div reads back 0.096).
- **An empty reply to an ordinary query means "busy"**, not out of step. Seen on `:TIMebase:SCALe?` 0.3 s after a timebase change and on `*IDN?` while stepping V/div. Retrying works.
- **Device clear is safe on the scope** on both backends.

### 12.3 Single-shot acquisition (used for acquisition-complete polling)

None of this is in either manual.

- `:TRIGger:SWEep SINGle` is itself the arm command.
- A `:RUN` sent after the shot has armed cancels single mode; the scope free-runs in AUTO and never stops.
- Status sequence after arming from a stopped scope: `STOP` (stale, first 20 ms) → `ARMED` → `AUTO` → `READY` at about 0.67 s → `STOP` after the trigger. With a signal present the sequence usually reads `STOP → ARMED → AUTO → STOP`.
- `:TRIGger:FORCe` works from `READY` (STOP within 30 ms). Sent while the status still reads `AUTO`, it leaves the scope in AUTO.
- A setting change just before arming makes the scope restart its acquisition, and the shot then runs two arm cycles (STOP for 20 ms, then armed again).

The layer therefore: waits 0.3 s after the last setting change and until the status is not `ARMED`; arms with the sweep command only; requires a non-STOP status to have been seen, then STOP held for 0.1 s, then at least one screen time; forces a trigger only after a set time continuously in `READY`.

### 12.4 I/O layer (`hwcheck/iolayer.py`) and its test (`hwcheck/t0b_iolayer.py`)

Final run on `@py`: **55 of 55 checks passed.** An earlier run on `@ivi` reached 36 of 37 before NI-VISA was dropped (the one failure was the single-shot arming, fixed afterwards and not re-run on `@ivi`).

| Requirement | How it is done | Evidence |
|---|---|---|
| Per-instrument formatter, no exponents | `plain_decimal`, `ScopeFmt` (probe `1X`, channels 1-4), `GenFmt` (channels 1-2) | 12 number cases, NaN and bad channels rejected |
| Set-then-readback for every setting | `set_verified` on both instruments, polls the read-back up to 2 s, re-sends once, raises `SetError` | 23 timebase steps, 15 V/div steps × 2 channels, coupling, BW limit, offset, trigger level/slope/source; generator sine setup, 7 frequencies 50 Hz to 20 MHz, amplitude, offset, load. A deliberately wrong expectation (20 ns/div) is caught. |
| Reply-format validation | One validator per reply type; every scope query is followed by a `*IDN?` sentinel | 11 real replies accepted, 11 wrong-format replies rejected |
| Resync: device clear, flush, `*IDN?` sentinel | `:RUN`, device clear, host-buffer flush, three clean sentinel rounds; second level: restart the USB device node | See 12.5 |
| Acquisition-complete polling before every fetch | `acquire()` as in 12.3 | 20 of 20 two-channel captures with no signal (forced trigger); 300 of 300 with signal (12.6) |
| Cached real step tables built at connect | `build_tables()` walks `UP`/`DOWN`; tables are checked for plausibility and rejected otherwise | Tables above; 20 ns/div refused as "not a real step", a 20 ns request rounds up to 25 ns |
| Generator: read termination None | set at open | all generator queries |
| Generator: unknown commands blocked | whitelist of exact manual forms, checked before any I/O | 8 commands refused (`*OPC?`, `*RST`, `:SYSTem:LOCK OFF`, `:CHANnel3:...`, abbreviated forms, exponent argument, `:SYSTem:ERRor?`), zero bytes sent, generator still answering |
| Generator: device clear + single retry on timeout | on timeout or wrong-format reply | 5 of 5 injected timeouts recovered with exactly 1 clear and 1 retry each, no stale reply left behind (also 5 of 5 on `@ivi`) |

Device clear on pyvisa-py: `inst.clear()` returns `VI_ERROR_NSUP_OPER` for USB, so the layer closes the session, sends USBTMC INITIATE_CLEAR through pyusb, and reopens. The pyvisa-py host-buffer flush is not implemented either (`NotImplementedError`); that step is a no-op on `@py`.

Defects in the layer that the tests exposed and that were fixed: flushing with bare device reads (broke NI-VISA, see 12.5), `:RUN` after arming, forcing a trigger too early, treating an empty sentinel as out of step, accepting STOP after 20 ms, and accepting a one-entry timebase table.

### 12.5 Forcing the out-of-step condition, and recovery

**How it is forced.** Send `:RUN` then `:STOP` at once at 5 ms/div, so the scope has no screen record, then ask `:WAVeform:DATA?` three times. Each gets an empty reply. Then `:RUN`.

**What then happens.** About 0.6 s later a 707-byte waveform block arrives as the answer to whatever query is in flight. After that one stray reply the scope is in step again. It does not happen every time.

**Proof and recovery (final run, 12 rounds):**

| Who received the stray reply | Rounds where it appeared | Result |
|---|---|---|
| An unchecked query, as Milestone 0's scripts would send | 3 of 6 | A `#3700...` block came back as the reply to `*OPC?`, 0.58 to 0.59 s after `:RUN`. This is the fault, demonstrated. |
| The I/O layer's own queries | 5 of 6 | Each time the layer reported "binary data in reply to ..." (to `*IDN?` or `:SYSTem:ERRor?`), resynced in one pass (sentinel clean three times running), and then passed 100 validated queries plus a two-channel capture. |

In every one of the 12 rounds the scope was in step afterwards.

Other routes tried:

- **SCAN mode route** (50 ms/div, the sequence that ended in a power cycle in Milestone 0): the stray block appeared as the reply to `:TRIGger:STATus?`, and the scope was in step afterwards. The permanent state did **not** recur.
- **Read with no query pending, on `@py`:** harmless in 3 of 3 rounds; the scope re-sends its last reply.
- **Read with no query pending, on `@ivi`:** every later read failed with `VI_ERROR_INP_PROT_VIOL`, including in new sessions and after device clear. `pnputil /restart-device "USB\VID_5656&PID_0832\APX1424510001"` (needs an elevated process) cleared it with no replug or power cycle. This is the layer's second resync level. **It was only exercised under the NI driver, never under WinUSB**, and it was never needed on `@py`.

So the permanent "one reply behind" state from Milestone 0 was not reproduced in 0b, and its trigger is still not known for certain. What is established is that the layer detects a wrong reply immediately, and that the ordinary resync fixed every case that did occur.

### 12.6 Dual-channel test

**Wiring actually used:** no BNC tee was available, so both scope probes (1X) were placed on generator CH1's output. This differs from the plan (tee). Generator: sine, 1 Vpp, High-Z. Scope: CH1 and CH2 DC, 1X, 0.2 V/div, trigger on CH1 at 0 V, timebase chosen for 5 cycles and rounded up to a real step (7 cycles on screen at all three frequencies). 50 captures per frequency; in each, both channels are read from the same stopped single-shot record, a sine is fitted to both at one frequency, and CH2/CH1 gives gain and phase.

Run A (probes as first connected), then run B with the two probes swapped at the scope inputs:

| Frequency | Timebase | Run | Gain CH2/CH1 (dB) mean ± sd [min, max] | Phase CH2 − CH1 (°) mean ± sd [min, max] | Valid |
|---|---|---|---|---|---|
| 1 kHz | 500 µs/div | A | +0.052 ± 0.006 [+0.034, +0.062] | +0.017 ± 0.028 [−0.063, +0.072] | 50/50 |
| 1 kHz | 500 µs/div | B | +0.055 ± 0.005 [+0.043, +0.069] | +0.011 ± 0.031 [−0.065, +0.067] | 50/50 |
| 1 MHz | 500 ns/div | A | +0.072 ± 0.006 [+0.060, +0.086] | +1.714 ± 0.047 [+1.614, +1.804] | 50/50 |
| 1 MHz | 500 ns/div | B | +0.064 ± 0.006 [+0.052, +0.079] | +1.347 ± 0.047 [+1.237, +1.466] | 50/50 |
| 20 MHz | 25 ns/div | A | +0.397 ± 0.041 [+0.340, +0.516] | +29.576 ± 0.321 [+29.000, +30.346] | 50/50 |
| 20 MHz | 25 ns/div | B | −0.263 ± 0.046 [−0.378, −0.157] | +29.589 ± 0.260 [+28.861, +30.131] | 50/50 |

Across all 300 captures: 0 errors, 0 resyncs, 0 empty blocks, 0 forced triggers, about 0.77 s per two-channel capture. Fit SNR about 35 dB at 1 kHz and 1 MHz, 27 dB at 20 MHz.

**Run C, after the user rewired the connection (same settings, still 1X probes on generator CH1):**

| Frequency | Gain CH2/CH1 (dB) mean ± sd [min, max] | Phase CH2 − CH1 (°) mean ± sd [min, max] | Valid |
|---|---|---|---|
| 1 kHz | +0.062 ± 0.005 [+0.052, +0.072] | +0.036 ± 0.028 [−0.016, +0.115] | 50/50 |
| 1 MHz | +0.065 ± 0.006 [+0.048, +0.076] | −0.127 ± 0.039 [−0.210, −0.034] | 50/50 |
| 20 MHz | −0.159 ± 0.048 [−0.258, −0.036] | +0.239 ± 0.276 [−0.328, +0.875] | 50/50 |

0 errors, 0 resyncs, 0 forced triggers, 0.75 to 0.78 s per capture. Raw data: `s0b_dual_py_C_rewired.json`. **This meets the expectation of about 0 dB and 0° at all three frequencies** (0.24° at 20 MHz is 33 ps).

**Superseded: see section 12.11 for the real cause.** The offset in runs A and B was a 4 ns sample shift inside the scope, triggered by my scripts' `:RUN` at connect; run C simply started in the aligned state. It was not the wiring, and it was not a fixed scope delay either. The paragraph below is kept as written at the time.

**Correction to the analysis below (written before 12.11, itself wrong).** From runs A and B I concluded that the scope itself delays CH1 by about 4.1 ns relative to CH2, because the phase offset did not move when the probes were swapped at the scope inputs. Run C disproves that: with the wiring changed and nothing else, the offset is gone. So the 4.1 ns came from how the signal was connected in runs A and B. I do not know exactly what was different (what was rewired was not recorded), and I cannot explain why the swap left the offset unchanged. The A/B separation table is kept only as a record of what was measured.

Separating the scope from the probes in runs A and B (half the sum of A and B is what stayed with the scope inputs; half the difference is what moved with the probes). **The "scope" columns here are superseded by run C:**

| Frequency | Scope gain | Probe gain mismatch | Scope phase | As a delay | Probe phase mismatch |
|---|---|---|---|---|---|
| 1 kHz | +0.053 dB | ±0.002 dB | +0.014° | not resolvable | ±0.003° |
| 1 MHz | +0.068 dB | ±0.004 dB | +1.53° | 4.25 ns | ±0.18° |
| 20 MHz | +0.067 dB | ±0.330 dB | +29.58° | 4.11 ns | ±0.01° |

Reading of the result against the expectation of about 0 dB and 0°:

- **Gain: met.** The scope's channels agree to about +0.06 dB at all three frequencies.
- **Phase in runs A and B: not met above about 100 kHz.** CH2 led CH1 by a constant 4.1 to 4.25 ns (0.0015° at 1 kHz, 1.5° at 1 MHz, 29.6° at 20 MHz), stable to 0.3°. **Run C shows this was the wiring, not the scope** (see the correction above). In run C the phase is within 0.24° everywhere.
- Only the pair CH1/CH2 was measured, at these three timebases, at 0.2 V/div, with CH1 as trigger source.
- **1X probes roll off before 20 MHz:** only 0.32 Vpp of the 1 Vpp arrived at 20 MHz (about −10 dB). The ratio is still valid because both probes roll off alike, but SNR is lower there. 10X probes or direct cables would be better for the top decade.
- At 25 ns/div the 700 points are 0.5 ns apart, i.e. interpolated by the scope. The 4.1 ns delay is larger than that spacing, and it shows up equally at 500 ns/div where points are 10 ns apart, so it is not a one-sample offset.

Runs that do not count, kept for the record:

- **First attempt (`s0b_dual_py_run1_ch2_not_connected.json`):** scope CH2 was wired to generator CH2, which my test does not drive, so CH2 read noise. The scope's own `:MEASure:VPP? CHANnel2` confirmed 0 V.
- **First swapped attempt (`..._B_swapped_run1_invalid_front_panel.json`):** the scope's front panel was being used while the test started. Timebase commands had no effect, the step table came out as a single entry, all three frequencies were captured at 5 ms/div, and 13 of the first 50 captures failed with empty blocks. The layer now rejects an implausible step table instead of carrying on.

### 12.7 Incidents during 0b

- **Scope "froze" once.** A test run was killed partway through while it was doing single-shot captures and `:STOP` cycles. In those states the display stops updating, so it may have been that; whether the front panel keys were dead was not established. It was power-cycled and has behaved since.
- **I wrongly reported that a command had not run.** The command that was interrupted had already rewritten `iolayer.py` and started the test.
- **Scope settings as found are not preserved.** A killed run never restored CH2 (it was display off, probe 10X before 0b; it is now on, 1X), and the front panel was used between runs. Generator settings were restored after every run and both outputs read OFF at the end of each.

### 12.8 What this adds for the spec

1. **No fixed scope delay correction is needed** (run C: within 0.24° at 20 MHz). But runs A and B show that connection details alone can add about 30° at 20 MHz, so the through-calibration that SPEC.md section 15 schedules for v2 (measure both inputs on the same node, divide later results by it) is worth pulling forward, or at least a "same node" sanity check in v1.
2. **Default backend `@py`**, not `auto` preferring `@ivi` (SPEC.md sections 3 and 5 and CLAUDE.md need this change; SPEC.md still recommends NI-VISA).
3. **Acquisition must be single-shot with status polling** as in 12.3, not `:STOP` on a free-running scope. SPEC.md section 9.2 currently describes the guard-then-`:STOP` method from Milestone 0.
4. **Timebase choice uses the real step table** (25 ns, not 20 ns) and 14 divisions.
5. **Per-point time:** about 0.77 s for a two-channel capture plus settling and autorange. A 113-point sweep is on the order of 2 to 4 minutes.
6. **Front-panel use during a sweep must be prevented or handled.** `:SYSTem:LOCK` exists in the manual (UPO1000 p.6) but was not tested.
7. **Probes:** use 10X or direct coax for measurements above a few MHz; the software should apply the probe ratio itself and leave the scope at 1X.

Still not verified after 0b: a tee (probe-free) baseline, CH3/CH4 as measurement channels, channel matching at other V/div and timebase settings, `:MEASure:PHASe?`, ADC rail codes and clipping detection, autorange, generator behaviour on frequency change, the device-restart recovery under WinUSB, LAN, and everything on Linux.

### 12.9 Files added in 0b

| Path | Purpose |
|---|---|
| `hwcheck/iolayer.py` | the I/O layer (`ScopeIO`, `GenIO`, formatters, validators, resync) |
| `hwcheck/t0b_iolayer.py` | its test, including the forced out-of-step rounds |
| `hwcheck/s0b_dual.py`, `s0b_identity.py` | dual-channel test, identity check |
| `hwcheck/dbg0b_*.py` | 0b troubleshooting scripts referenced above |
| `hwcheck/s0c_dual10x.py` | Milestone 0c: 10X dual-channel test (steps 3, 4, 5) |

### 12.10 Milestone 0c: dual-channel test with 10X probes, compared with run C (1X)

Run on 2026-10-05, `@py`, script `hwcheck/s0c_dual10x.py`. Raw data: `s0c_dual10x_main_py.json` (final), `s0c_dual10x_swap_py.json`, and `s0c_dual10x_main_py_run1_wiring_offset.json` (first attempt, see "Wiring" below).

**Setup.** Both probes switched to 10X, compensated by the user on the scope's cal output (reported by the scope as a 1 kHz square wave), both tips on generator CH1's output. Scope: CH1 and CH2 at `PROBe 1X` in the scope, DC, full bandwidth, offset 0, trigger on CH1 at 0 V; the ×10 is applied in software. Generator: sine, High-Z. Every capture is a single shot with both channels read from the same record through `iolayer.py`. Both generator outputs read OFF at the end of every run.

**Per-channel delay / deskew setting (step 2).** The UPO1000 manual documents **none**. Its CHANnel subsystem (p.12-15) has only BWLimit, COUPling, DISPlay, INVert, PROBe:TYPe, PROBe, OFFSet, SCALe, UNITs, VERNier and SELect; its TIMebase subsystem (p.15-17) has MODE, OFFSet, WINDow:OFFSet, SCALe, WINDow:SCALe and HOLDoff, all common to every channel. Whether the scope has a deskew setting in its front-panel menus is not known. Documented per-channel settings as logged during the run, identical for CH1 and CH2: probe ratio 1, probe type VOLTs, invert 0, vernier 0 (coarse), units VOLTs, BW limit FULL, coupling DC, offset 0, display on. Timebase offset 0, mode MAIN, acquisition NORMal.

**Step 3: 1 Vpp, 50 captures per frequency (final run, corrected wiring).**

| Frequency | Timebase | V/div used | Decoded Vpp ×10, CH1 / CH2 | Gain CH2/CH1 (dB) mean ± sd [min, max] | Phase CH2 − CH1 (°) mean ± sd [min, max] | Fit SNR CH1 / CH2 | Auto-selected V/div | Valid |
|---|---|---|---|---|---|---|---|---|
| 1 kHz | 500 µs | 20 mV | 0.985 / 0.987 | +0.018 ± 0.004 [+0.007, +0.028] | −0.095 ± 0.033 [−0.162, −0.029] | 35.4 / 35.6 dB | 20 mV both | 50/50 |
| 1 MHz | 500 ns | 20 mV | 0.996 / 0.993 | −0.032 ± 0.007 [−0.042, −0.017] | +0.013 ± 0.038 [−0.068, +0.100] | 35.4 / 35.2 dB | 20 mV both | 50/50 |
| 20 MHz | 25 ns | 20 mV | 1.014 / 1.010 | −0.029 ± 0.014 [−0.055, +0.003] | +1.081 ± 0.102 [+0.776, +1.287] | 33.0 / 33.2 dB | 20 mV both | 50/50 |

- Amplitude decodes to 1 Vpp within 1.5% at all three frequencies, so the 10X probes are flat to 20 MHz.
- Gain ratio is within 0.03 dB of 0 dB. Phase is within 0.1° up to 1 MHz and +1.1° at 20 MHz (about 150 ps).
- 0 errors, 0 resyncs, 0 forced triggers, 0 clipped, 0.76 to 0.78 s per capture.

**"Auto-selected V/div"** is what SPEC.md's rule gives from the measured amplitude: the most sensitive real step that keeps the signal at or below 0.8 of full scale. It assumes 8 vertical divisions, which has **not** been verified on this scope. With a 100 mVpp input (1 Vpp at a 10X tip) it picks 20 mV/div: 0.625 of 8 divisions, about 125 of 255 ADC codes.

**Step 4: 50 mVpp, 20 captures each (noise floor with 10X).** The scope input sees 5 mVpp; auto-selection picks 1 mV/div.

| Frequency | Run | Decoded Vpp ×10, CH1 / CH2 | Gain (dB) mean ± sd | Phase (°) mean ± sd [min, max] | Fit SNR CH1 / CH2 (lowest capture) | Valid |
|---|---|---|---|---|---|---|
| 1 kHz | first | 0.0492 / 0.0492 | −0.012 ± 0.029 | −0.215 ± 0.167 [−0.585, +0.086] | 23.5 / 23.2 dB (20.1) | 20/20 |
| 1 kHz | final, all 20 | 0.0470 / 0.0469 | −0.013 ± 0.033 | −0.297 ± 0.704 [−3.262, +0.035] | 19.1 / 18.7 dB (−30.3) | 20/20 |
| 1 kHz | final, without one bad fit | 19 captures | −0.007 ± 0.021 | −0.141 ± 0.097 [−0.380, +0.035] | 21.7 / 21.3 dB | 19 |
| 20 MHz | first | 0.0500 / 0.0498 | −0.041 ± 0.021 | (wiring offset, see below) sd 0.240 | 28.4 / 28.6 dB (25.9) | 20/20 |
| 20 MHz | final | 0.0498 / 0.0496 | −0.040 ± 0.023 | +1.126 ± 0.123 [+0.919, +1.370] | 27.4 / 27.0 dB (24.4) | 20/20 |

- At 50 mVpp the SNR falls from about 35 dB to 21 to 28 dB, and the phase spread grows from 0.03 to 0.10° to about 0.10 to 0.17° (1 kHz) and 0.12 to 0.24° (20 MHz). Mean gain and phase are unchanged within that spread, so the measurement is still usable.
- **One capture in the final 1 kHz block was fitted at the wrong frequency (1926 Hz, SNR −30 dB).** That is a weakness of this test script, which estimates the frequency from zero crossings before fitting; noise fooled it. It is not a hardware fault. The application is specified to fit at the known generator frequency (SPEC.md 8.4), which does not have this failure. Raw samples were not saved, so that capture could not be re-fitted; both versions of the statistics are shown.
- The 1 kHz SNR is lower than the 20 MHz SNR at the same amplitude. I did not investigate why; low-frequency pickup on the probes at the 5 mV level is a likely cause, not a confirmed one.
- The most sensitive step is 500 µV/div, so with 10X probes the floor is about 5 mV/div referred to the tip. Signals of a few mVpp at the tip would occupy only a few ADC codes.

**Step 5: probes swapped at the scope inputs, 20 MHz, 1 Vpp, 50 captures.**

| Orientation | Gain CH2/CH1 (dB) mean ± sd | Phase CH2 − CH1 (°) mean ± sd [min, max] |
|---|---|---|
| As in step 3 (final run) | −0.029 ± 0.014 | +1.081 ± 0.102 [+0.776, +1.287] |
| Swapped | +0.201 ± 0.015 | +0.698 ± 0.116 [+0.473, +0.996] |
| Stays with the scope inputs (half the sum) | +0.086 | +0.89 (about 124 ps) |
| Moves with the probes (half the difference) | ±0.115 | ±0.19 |

The phase stayed near 0 and did not flip: about +0.9° belongs to the scope inputs and ±0.2° to the probes. The gain did change sign, so about ±0.12 dB is probe mismatch (residual compensation difference) and +0.09 dB is the scope.

Order of events, because it matters for how far to trust this: the swapped run was taken first on the corrected wiring, then the probes were swapped back and the full step 3 and 4 run was repeated. The user confirmed that only the BNC ends changed between those two runs.

**Superseded: see section 12.11.** The offset described next was a 2 ns sample shift inside the scope, not wiring. The text is kept as written at the time.

**"Wiring": the first 0c attempt had a delay-like offset again.**

| Frequency | First attempt, phase CH2 − CH1 | As a delay | Final run |
|---|---|---|---|
| 1 kHz | −0.098° | — | −0.095° |
| 1 MHz | +0.727° | 2.0 ns | +0.013° |
| 20 MHz | +15.47° (also +15.56° at 50 mVpp) | 2.15 ns | +1.08° |

Gain and amplitude were normal in that attempt. Before the next run the user swapped the probes, "fixed the wiring again", and changed the generator's supply, all at once, and the offset was gone. So, as with the 4.1 ns offset in runs A and B, it came from the connection at the generator and not from the scope or the software, but **which of the three changes removed it was not isolated, and what exactly was wrong with the wiring is not known to me.** A constant delay of this size is what two tips on electrically different points give (2 ns is roughly 40 cm of wire, or a small series resistance working against the probe's input capacitance); that is an explanation I find plausible, not one I verified.

This has now happened twice (4.1 ns with 1X, 2.1 ns with 10X), each time invisible at 1 kHz and large at 20 MHz. It is the strongest argument so far for a "both probes on one node" check before a sweep.

**Comparison with run C (1X probes, section 12.6).**

| | 1X (run C) | 10X (0c final) |
|---|---|---|
| Signal at the scope input for 1 Vpp at the tip | 1 Vpp at 1 kHz and 1 MHz, **0.33 Vpp at 20 MHz** (−10 dB) | 0.1 Vpp, flat to 20 MHz (decodes to 0.985 to 1.014 Vpp) |
| V/div used | 200 mV | 20 mV |
| Gain CH2/CH1 at 1 kHz / 1 MHz / 20 MHz | +0.06 / +0.07 / −0.16 dB | +0.02 / −0.03 / −0.03 dB |
| Phase at 1 kHz / 1 MHz / 20 MHz | +0.04° / −0.13° / +0.24° | −0.10° / +0.01° / +1.08° |
| Phase spread (sd) at 20 MHz | 0.28° | 0.10° |
| Fit SNR at 1 kHz / 20 MHz | 35.6 / 27.0 dB | 35.5 / 33.0 dB |
| Smallest signal tried | not tried below 1 Vpp | 50 mVpp: SNR 21 to 28 dB |

Both give gain within 0.2 dB and phase within about 1° at every frequency. 10X is clearly better at 20 MHz (6 dB more SNR, a third of the phase spread, full amplitude). 1X was 0.8° closer to zero phase at 20 MHz, but that run was not swap-tested, so I would not read anything into the difference. Run C and 0c were taken with different tip wiring, which limits how exactly they can be compared.

**Recommendation: when to use 1X and when 10X.**

- **Use 10X by default**, and for anything that goes above about 1 MHz. It is flat to 20 MHz here, where 1X had already lost two thirds of the signal. It also loads the circuit under test much less than 1X does; that is general probe behaviour and was not measured here.
- **Use 1X only for small signals at low frequency**: when the signal at the test point is below roughly 50 mVpp and the sweep stays under about 1 MHz. 10X costs a factor of ten in signal (20 dB), and at 50 mVpp it was already down to 21 to 28 dB SNR. The 1 MHz limit comes from run C, where 1X still read full amplitude at 1 MHz and −10 dB at 20 MHz; where between those it starts to fall was not measured.
- **Do not mix**: both channels must use the same probe type and setting, compensated, because the ratio only cancels the probes if they match.
- **In software**: keep the scope at `PROBe 1X` and apply the ratio per channel in the application, as SPEC.md's `probe_atten` already intends. Auto-selection should work on the voltage at the scope input (tip voltage divided by the ratio).
- **Averaging** is the remedy for small signals at 10X: at 50 mVpp the single-capture phase spread was 0.1 to 0.24°, which averaging a few captures would bring down.

**Verdict after 0c (written before section 12.11; the 'connection-induced' warning in it is superseded): GO WITH WORKAROUNDS, unchanged.** 0c adds confidence (10X works to 20 MHz, the layer ran 490 more captures without a single error, the scope's own channel mismatch is about 0.09 dB and 0.9° at 20 MHz) and repeats one warning (connection-induced phase error). Not verified in 0c: the 8-division assumption behind auto-selection, 1X below 1 Vpp, any frequency between 1 MHz and 20 MHz, and the cause of the wiring offsets.

### 12.11 Channel alignment shifts by whole samples: cause, fix, and what is still open

**How it was found.** The user noticed that the CH1/CH2 phase offset was visible on the scope's own screen when one of my tests started, and went away after a channel was switched off and on at the front panel, with the wiring untouched. That ruled out wiring. Scripts: `hwcheck/dbg0c_skew.py` to `dbg0c_skew7.py`, `s0c_realign.py`. Raw data: `hwcheck/results/dbg0c_skew*.json`, `s0c_realign.json`. All measurements: both 10X probes on generator CH1, 20 MHz, 1 Vpp, 25 ns/div, single-shot two-channel captures through `iolayer.py`.

**What the fault is.**

- The CH2 − CH1 delay takes only discrete values 2.000 ns apart: about +150 ps (aligned), +2150 ps, +4150 ps and −1850 ps. At 20 MHz those are +1.1°, +15.5°, +29.9° and −13.3°.
- 2 ns is one sample period at 500 MSa/s. In two re-alignment runs the states were visited in the order +2150 → +4150 → −1850 → +150, i.e. steps of +2 ns that wrap round after 8 ns.
- Within a state the value is steady to about 0.1° at 20 MHz over hundreds of captures. The offset is visible on the scope's own display, so it is in the scope's acquisition, not in my read-out or fitting.
- It is invisible at low frequency: one step is 0.0007° at 1 kHz and 0.72° at 1 MHz.

This accounts for every unexplained offset in this report: 4.1 ns in runs A and B (two steps), about 0 in run C, 2.15 ns in the first 0c run (one step), about 0 in the final 0c runs.

**What does NOT change it** (parts 1, 2, 4 and 5; each tried 2 to 12 times, 0 changes in every case): timebase changes including a walk through all 23 steps, V/div changes on either channel including a walk through all 15 steps, coupling, bandwidth limit, trigger source, trigger loss and recovery, `:STOP` then `:RUN` in an open session, switching CH1, CH2 or CH3 off and on by command at nine different timebases and while stopped, generator output off and on, generator frequency changes, a 5 ms/div + 5 V/div excursion, and a new libusb context.

**What changes it** (part 6, 25 repetitions per case; a "slip" is a change of more than 500 ps):

| Action repeated 25 times | Slips |
|---|---|
| `iolayer` connect as it was (reopen session, `:RUN`, device clear, sentinels, WAVeform writes) | 11 |
| reopen session, then resync (`:RUN`, device clear, sentinels) | 15 |
| reopen session, wait 3 s, then the same resync | 13 |
| reopen session, `*IDN?`, timebase query, then `:RUN` | 13 |
| reopen session, then `:RUN` | 8 |
| `:RUN`, 0.3 s, device clear, in an open session | 1 |
| `:RUN` only, in an open session | 0 |
| resync in an open session | 0 |
| device clear only | 0 |
| reopen session, then device clear | 0 |
| reopen session, then `*IDN?` | 0 |
| reopen session, then `:WAVeform:MODE` + `:FORMat` | 0 |
| `:WAVeform:MODE` + `:FORMat` only | 0 |
| reopen session, then `:TRIGger:SWEep AUTO` (no `:RUN`) | 0 |
| `:TRIGger:SWEep AUTO` only | 0 |

**Cause, as far as it is established:** a `:RUN` command sent after the USB session has been reopened re-rolls the alignment in roughly half the cases (49 of 100 across the four rows that contain that combination). `:RUN` in a session that stays open did not (0 of 25, plus 1 of 25 when followed by a device clear). Waiting after the reopen does not help. Why the scope does this is not known; the manual says nothing about it. Whether it is the first `:RUN` after a reopen or any `:RUN` soon after one was not separated.

**Why it hit every test.** `iolayer.connect()` began with a resync, and the resync began with `:RUN`. Every test script therefore reopened the session and sent `:RUN` at its start, re-rolling the alignment about half the time. The Milestone 0 scripts and `t0b_iolayer.py` also send `:RUN`.

**The fix, and its verification.**

- `iolayer.py` no longer sends `:RUN` anywhere, and `ScopeIO.write()` refuses it (`BlockedCommand`). A stopped scope is restarted with `:TRIGger:SWEep AUTO` alone, which was seen to work in 50 of 50 cases (status `TRIGED` 0.8 s later).
- After the fix: the full connect, 25 times: **0 slips** (11 before). Reopen plus resync, 25 times: **0 slips** (15 before).
- Regression: `t0b_iolayer.py` again passes 55 of 55 with the changed resync, including the forced out-of-step rounds (2 of 6 proven by an unchecked query, 5 of 6 met and repaired by the layer).

**No command undoes a shift** (part 7, each tried three times from a shifted state, 0 of 18 returned to aligned): memory depth 7K → 70K → 7K, memory depth → AUTO → 7K, acquire type → PEAKdetect → NORMal, timebase mode → WINDow → MAIN, both channels off for 3 s then on, `:STOP` then sweep AUTO. Earlier (part 3) channel toggles, `:STOP`/`:RUN`, a timebase excursion and WAVeform commands also failed.

That contradicts the user's observation that a front-panel channel off/on fixed it. I could not reproduce that by command. One possibility is coincidence: the toggle was done while one of my scripts was starting, and the script's own `:RUN` re-rolled the alignment at that moment. I have no evidence either way.

**Re-alignment tool.** Since nothing undoes a shift, `hwcheck/s0c_realign.py` uses the fault itself: with both probes on one node it measures the delay and, while it is more than 1 ns from zero, reopens the session and sends `:RUN`, then measures again. Two runs: aligned after 8 re-rolls and after 7 re-rolls, each confirmed afterwards by a separate process (+143 ps and +153 ps). `--check` only measures.

**State left on the scope:** aligned (+153 ps at the last check), free-running, generator outputs OFF.

**What this means for the earlier results in this report.**

- All gain results stand; a time shift does not change gain.
- Phase results taken in the aligned state stand: run C (1X) and the final 0c runs (10X).
- Runs A and B (4.1 ns) and the first 0c run (2.15 ns) were taken in shifted states. Their repeatability figures are valid; their mean phase is the shift.
- The probe-swap comparisons need a caveat: the two halves of each swap pair were separate script runs, so the state could have changed between them. The measured phases show it did not (29.58° and 29.59° in runs A and B; +1.08° and +0.70° in 0c), so those comparisons hold, but only because both halves happened to land in the same state.
- The explanations given at the time (a fixed scope delay, then wiring, in sections 12.6 and 12.10 and in the verdict block) were wrong.

**Not known, and it matters:**

1. Whether anything else re-rolls the alignment: the front panel's Run/Stop or Single keys, a power cycle, Auto-set, UNI-T's own PC software, or a USB replug. None was tested.
2. Which state the scope is in after power-on.
3. Whether the same thing happens between other channel pairs (CH3, CH4) or with a different number of channels switched on, where the sample period, and so the step size, would differ. The 4.1 ns seen in runs A and B was two 2 ns steps as far as I can tell, but that run was not examined at the time.
4. Whether it happens over LAN, or under a vendor VISA driver.
5. Only 20 MHz at 25 ns/div was used for the investigation.

**Consequences for the application.**

1. **Never send `:RUN`.** Arm with `:TRIGger:SWEep SINGle`, return to free-run with `:TRIGger:SWEep AUTO`. This goes into the scope driver's rules alongside the Milestone 0 ones.
2. **A sweep cannot assume the channels are aligned.** Before measuring, the user should put both probes on the stimulus and let the software measure the CH2 − CH1 delay at a high frequency (20 MHz resolves one step as 14°). Then either subtract that delay from every phase result, or re-roll until it is zero. This is the through-calibration SPEC.md lists for v2; it needs to be in v1 in at least this minimal form.
3. **The check is cheap:** three captures (about 2.5 s) at one frequency separate the states by 14° with a spread of 0.1°.
4. The delay found should be stored with the result file, so a sweep taken in a shifted state can be recognised later.

### 12.12 Capture-speed benchmark: single shot against free running (2026-10-06)

Script `hwcheck/s6_capbench.py`, raw data `hwcheck/results/s6_capbench_py.json`. Setup as in 12.10: both 10X probes on generator CH1, 1 Vpp sine, High-Z, backend `@py`. 20 captures per block, both channels read from one acquisition. Order: A, B, A. No `:RUN` was sent.

- **A, single shot:** `ScopeIO.acquire()` (`:TRIGger:SWEep SINGle`, poll for STOP, read both channels).
- **B, free running:** sweep AUTO running, wait `max(0.3 s, 30 x timebase)`, `:STOP`, poll for STOP, read both channels, restart with sweep SINGle then AUTO.

| Method | Frequency | Captures OK | Time per good capture | Time per capture incl. failures | CH2 - CH1 delay |
|---|---|---|---|---|---|
| A (first) | 1 kHz | 20/20 | 0.80 s | 0.80 s | n/a (noise at 1 kHz) |
| A (first) | 1 MHz | 20/20 | 0.78 s | 0.78 s | +0.01 ns, sd 0.11 |
| A (first) | 20 MHz | 20/20 | 0.83 s | 0.83 s | +0.147 ns, sd 0.013 |
| B | 1 kHz | 10/20 | 0.81 s | 3.46 s | n/a |
| B | 1 MHz | 10/20 | 0.81 s | 3.46 s | 0.00 ns, sd 0.15 |
| B | 20 MHz | 10/20 | 0.86 s | 3.48 s | +0.147 ns, sd 0.014 |
| A (second) | 1 kHz | 20/20 | 0.81 s | 0.81 s | n/a |
| A (second) | 1 MHz | 20/20 | 0.79 s | 0.79 s | +0.02 ns, sd 0.09 |
| A (second) | 20 MHz | 20/20 | 0.82 s | 0.82 s | +0.143 ns, sd 0.014 |

Findings:

1. **Free running is not faster.** When it works it costs 0.81 to 0.86 s per capture (0.30 s run wait, 0.13 s stop, 0.35 to 0.39 s read, 0.03 s restart), the same as single shot (0.40 to 0.42 s arm-to-stop, 0.35 to 0.36 s read).
2. **Free running is not reliable as written.** Every second capture failed in all three blocks (30 of 60) with the exact error `status did not reach STOP after :STOP (last TRIGED)`: after a restart by sweep SINGle then AUTO, the next `:STOP` did not stop the scope within 5 s. After the layer's resync the following capture worked, then the next failed again. The cause was not investigated further.
3. **The channel alignment did not move.** The 20 MHz delay stayed between +0.115 and +0.170 ns over all blocks, across 30 resyncs (each a session close, USB clear and reopen) with no `:RUN`. This agrees with 12.11.
4. About 0.35 s of every capture is the read of two channels (source select with read-back, preamble, data, each followed by the `*IDN?` sentinel). That is where time could be saved, not in the capture method. Not attempted.

**Decision: the app uses single-shot capture.** Budget 0.8 s per capture.
### 12.13 Why free-running capture failed, and a scope freeze (2026-10-06)

Script `hwcheck/dbg6_freerun.py`; raw data `hwcheck/results/dbg6_freerun_py_run1.json`, `_run2.json` (the same variants run twice; the second time by mistake, because a script edit had not been applied) and `dbg6_freerun_py.json` (run 3). Setup as in 12.12, 20 MHz, 8 cycles per variant. Each cycle: restart the stopped scope, send `:STOP`, poll `:TRIGger:STATus?`, read both channels if it stopped. No `:RUN` was sent.

| Restart after a `:STOP` | When `:STOP` was sent | Stopped on the first `:STOP` | Time per cycle |
|---|---|---|---|
| sweep SINGle, then AUTO | 0.3 s later (as in 12.12) | 1/8 and 0/8; the second `:STOP` always worked | n/a |
| sweep SINGle, then AUTO | 1.5 s later | 7/8 and 7/8 | 2.05 s |
| sweep SINGle, then AUTO | when status read TRIGED | 8/8 | 1.44 s |
| sweep AUTO only | when status read TRIGED | 8/8 | **0.93 s** |
| sweep NORMal, then AUTO | when status read TRIGED | 8/8 | 1.17 s |
| sweep SINGle, then NORMal | when status read TRIGED | 6/8 (one cycle never reached TRIGED, one needed a second `:STOP`) | 1.45 s |

**Cause.** A restart is not immediate. After "sweep SINGle, then AUTO" the status reads STOP, ARMED (0.04 s), AUTO (0.22 s), STOP (0.33 s: the single shot completes), ARMED (0.42 s), AUTO (0.62 s) and only then TRIGED (0.89 s). `:TRIGger:SWEep?` still answers `SINGle` at 0.3 s and `AUTO` only later: the scope carries out the single shot first and applies the change to AUTO afterwards. A `:STOP` sent at 0.3 s lands inside that sequence; the status reads STOP for about 0.09 s and then the pending restart runs anyway (ARMED, AUTO, TRIGED). That is the 12.12 failure `status did not reach STOP after :STOP (last TRIGED)`.

**A worse case of the same thing.** In runs 1 and 2 a variant sent `:STOP` 0.3 s after a restart whose sweep already read AUTO (status ARMED then AUTO, never TRIGED). The scope stopped and stayed stopped, but with no record: `:WAVeform:DATA?` answered `b'\r\n'` (2 bytes), 8 of 8 cycles in both runs. The layer's resync recovered all 16.

**Rule.** `:STOP` followed by a waveform read is only valid once `:TRIGger:STATus?` has read `TRIGED` since the last restart. The Milestone 0 rule "let it run max(0.3 s, 30 x timebase)" is not enough after a restart.

**Other observations.**
- `:TRIGger:SWEep AUTO` alone did restart a scope stopped by `:STOP` with the sweep already AUTO (8/8, TRIGED after 0.40 s). This contradicted a note in `t0b_iolayer.py` that it is a no-op; that note was an inference and has been corrected (see 12.14 C).
- After `:TRIGger:SWEep NORMal` the read-back was `AUTO` in 6 of 8 cycles and `SINGle` in 2: NORMal sweep was never confirmed as set. Not examined further.
- The CH2 - CH1 delay stayed at +0.12 to +0.17 ns in every cycle of all three runs.

**Speed.** The best free-running method costs 0.93 s per capture against 0.80 s for single shot. Each restart costs one arm cycle (about 0.4 s) whichever way it is done, and a single shot needs exactly one. **Single shot stays.**

**Scope freeze.** The first attempt to run this script failed during set-up, before any of the above: while `build_tables()` was stepping the timebase, `*OPC?` timed out, the resync reported success, and then every write failed with `[Errno 10060] Operation timed out`. The user confirmed the scope's screen was frozen. A USBTMC INITIATE_CLEAR was accepted with no effect, and `pnputil /restart-device` reported success with no effect; only a power cycle by the user brought it back. No installer was running at the time (user's statement). Cause unknown. This is the second freeze during a step-table walk or setting sequence (the first was in 0b, 12.7). The script now uses the step tables measured in 0b instead of walking them.
### 12.14 Milestone 6 bench checks: rail codes, division count, front-panel lock (2026-10-06)

All scripts now print their own file hash and git commit at start, and a commit was made before each run.

**A. Overdrive** (`hwcheck/s6_overdrive.py`, `results/s6_overdrive_py.json`). Both 10X probes on generator CH1, 1 kHz sine, 1 Vpp, i.e. 0.1 Vpp at each scope input. CH1 stayed at 20 mV/div; CH2 was overdriven by V/div and, separately, pushed off the top and bottom with its offset. 3 single shots per case, 66 captures, no errors.

| CH2 case | Signal on CH2 | Lowest code | Highest code | Samples on the lowest / highest code |
|---|---|---|---|---|
| 20 mV/div (reference) | 5 div p-p | 67 | 192 | not clipped |
| 10 mV/div | 10 div p-p | 6 | 252 to 253 | not clipped |
| 5 mV/div | 20 div p-p | **1** | **254** | 222 / 238 of 700 |
| 2 mV/div | 50 div p-p | 1 | 254 | 294 / 308 |
| 1 mV/div | 100 div p-p | 1 | 254 | 322 / 336 |
| 500 uV/div | 200 div p-p | 125 | 255 | 336 / 6 to 8 (see finding 4) |
| 20 mV/div, offset +3 to +6 div | pushed off the top | - | 254 | 139 to 440 |
| 20 mV/div, offset +8 div | entirely above | 254 | 254 | 700 |
| 20 mV/div, offset -3 to -6 div | pushed off the bottom | 1 | - | 105 to 420 |
| 20 mV/div, offset -8 div | entirely below | 1 | 1 | 700 |

Findings:

1. **The rail codes are 1 and 254**, not 0 and 255. The rule used until now ("code <= 0 or >= 255") flagged none of the clipped captures above except the 500 uV/div one. Clip detection is now "any code <= 1 or >= 254".
2. **The waveform data cover 253 codes = 10.1 divisions**, 5.06 above and below the centre code 128. The screen grid has **8 vertical divisions** (the user counted them). So a signal can be up to about 1 division off screen at each edge and still be read correctly: at 10 mV/div the 10-division signal read codes 6 to 253, unclipped. Auto-range keeps aiming at the 8 screen divisions; the rest is headroom.
3. **Overdriving CH2 does not disturb CH1.** CH1 read codes 68 to 192 or 193 (span 124 or 125) in every case.
4. **At 500 uV/div with a 200-division overdrive the data are wrong in a different way**: the clipped low half reads code 125 (mid-scale) instead of 1, and a few samples read 255. The rail rule still flags the capture (255 >= 254). Cause not examined.
5. The share of samples on the rails gives the true amplitude of a clipped sine: 20, 50 and 100 divisions p-p were estimated as 19.7, 46 and 108. Auto-range now uses this to reach the right V/div in one jump.
6. The vertical offset moves the trace by exactly offset / (V/div / 25) codes, and the preamble's YOR field reports it.

**B. `:SYSTem:LOCK`** (`hwcheck/s6_lock.py`, `results/s6_lock_*_py.json`; U1K p.6).

| Step | `:SYSTem:LOCK?` | Front panel (user's observation) | Remote control |
|---|---|---|---|
| before | `0` | normal | works |
| after `:SYSTem:LOCK ON`, USB session closed | `1` | **no reaction to keys or knobs** | queries and a set-and-restore work |
| after `:SYSTem:LOCK OFF` | `0` | **keys work again** | works |

- **`1` means locked.** The manual's "Return format" sentence ("0 represents locked, 1 represents unlock") is wrong; its example ("Query returns 1, it represents locked") is right.
- The lock **survives a closed USB session**, so software that sets it must release it. The app does so after every measurement and on disconnect, and the probe tool has `--unlock`.
- Not tested: whether a power cycle clears a lock that was left on, and whether the power key is locked too.

**C. Reconciliation with the layer's test suite.** `t0b_iolayer.py` said that sweep AUTO written to a scope stopped by `:STOP` "is a no-op". That was an inference from a forcing test, not an observation. 12.13 watched the status: sweep AUTO alone restarts such a scope (8 of 8). The note in the test suite is corrected; the SINGle-then-AUTO restart is kept there because the forcing rounds are reliable with it (55 of 55).

**D. Incident.** While the app's real drivers were being written, one automated test opened a real connection: it found both instruments over USB, identified them and (as far as can be told) began the driver's connect sequence before the test ended and disconnected. No output was switched on (the generator driver forces both outputs off when it opens). A read-only check afterwards (`hwcheck/s6_state.py`) showed both generator outputs OFF, the scope unlocked, sweep AUTO, error queue empty. The test suite now sets `BODEPLOT_NO_HARDWARE`, which makes every VISA open raise, so no test can reach an instrument.

**What Milestone 6 did not do:** the app's own drivers and the probe tool have run only against simulated instruments. Their first run on the real scope and generator is Milestone 7, step 1.
## 13. Milestone 7: bench bring-up of the app's own drivers (started 2026-10-06)

Raw data: `hwcheck/results/m7/`. Setup so far: both 10X probes on generator CH1 (a "through" measurement: expected 0 dB, 0 degrees). A commit was made before every run.

### 13.1 Probe tool, first run on the real instruments

`python -m bodeplot.tools.probe --json hwcheck/results/m7/probe_run1.json`: **63 checks, 0 failed.** Every query form of every command in both drivers answered in the expected format (generator channels 1 and 2, scope channels 1 to 4), the single-shot test acquisition on CH1 returned 700 points (with a forced trigger, there being no signal), generator outputs read back OFF at the end, and the stored step tables matched this model and firmware.

### 13.2 Sweeps through the app's engine (`hwcheck/m7_sweep.py`)

The script uses the same code as the GUI (`drivers/connect.py`, `sweep/core.py`): find the instruments, skew check, sweep, generator off, panel unlocked, scope back to sweep AUTO.

| Run | Range | Points | Errors | Gain (through) | Phase (through) | Time per point |
|---|---|---|---|---|---|---|
| through_short | 1 kHz to 1 MHz | 10 | 0 | -0.014 to +0.028 dB | -0.14 to +0.03 deg | 1.35 s |
| through_full | 50 Hz to 20 MHz | 30 | 0 (1 point AUTORANGE_FAILED) | -0.027 to +0.044 dB | -0.28 to +0.06 deg | 1.74 s |
| through_short2 | 1 kHz to 1 MHz | 10 | 0 | -0.015 to +0.035 dB | -0.18 to +0.02 deg | 1.4 s |
| lowstart | 50 Hz to 1 MHz | 9 | 0 | within 0.04 dB | within 0.14 deg | 1.4 s |
| hf_repeat | 100 kHz to 20 MHz | 11 | 0 | -0.051 to +0.008 dB | -0.10 to +0.07 deg | 1.3 s |

- Scope counters over all runs: 0 reply errors, 0 out-of-step, 0 empty blocks, 0 resyncs after the one at connect. Generator: 0 timeouts.
- After every run: generator outputs OFF, panel lock 0, scope sweep AUTO.
- Connect takes 2.0 s. The skew check takes 10 to 23 s. One capture point costs 0.75 s when the timebase stays and about 1.05 s when it changes; settling and generator commands add about 0.3 s.
- The skew check at 10 and 20 MHz measured +0.15 and +0.14 ns and snapped to the +0.15 ns state.

### 13.3 Problems found, and what was done

1. **OPEN: the signal level at high frequency changed from run to run.** With nothing touched on the bench (user's statement), the reference amplitude at 20 MHz was 0.034 V peak in `through_full` and 0.30 V in `hf_repeat` (0.5 V expected; Milestone 0c read 1 Vpp within 1.5% up to 20 MHz). In `through_full` the level already fell from about 200 kHz (0.44 V at 365 kHz, 0.32 V at 889 kHz), while the three runs that stopped at 1 MHz were flat (0.49 V at 1 MHz). Both probes saw the same level each time, so the gain stayed within 0.05 dB. Cause not known: a loose ground clip or contact, or the generator. The user is checking the wiring. It matters for a real DUT because a low reference level costs signal-to-noise (SNR fell from 36 to 27 dB) and can hide a wiring fault.
2. **Fixed: auto-range flipped between two V/div steps.** At 8.2 MHz in `through_full` (10.5 mVpp at the input) the measured p-p sat on the upper target, so the step alternated between 2 and 5 mV/div until the retries ran out: 11 s and an AUTORANGE_FAILED flag. Auto-range now stays on a step that is just over the upper target while the signal is still on screen and the next step would fall below the lower target.
3. **Fixed: the skew check could not resolve the delay when the sweep stopped at 1 MHz.** The check used the top of the sweep, so it ran at 0.5 and 1 MHz, where 0.3 ns is 0.1 degree. Three such checks measured +0.04, 0.00 and -0.16 ns; the last one disagreed between its two frequencies by 0.32 ns and was not snapped. The check now always runs at 10 and 20 MHz when the instruments reach them, whatever the sweep range.

### 13.4 Not done yet

The known RC low-pass, compared with theory and with the simulation; the timed full-range sweep on a real DUT; a sweep from the GUI on the real instruments (only the headless path has run).
### 13.5 After the user fixed the wiring (2026-10-06)

The user checked and fixed the wiring (what exactly was wrong was not reported). Two more through runs, nothing else changed:

| Run | Range | Points | Flags | Reference level | Gain | Phase | Sweep time |
|---|---|---|---|---|---|---|---|
| through_full2 | 50 Hz to 20 MHz | 30 | none | 0.492 to 0.504 V peak over the whole range (0.504 V at 20 MHz) | -0.015 to +0.042 dB | -0.19 to +0.14 deg | 34.9 s (1.16 s per point) |
| hf_repeat2 | 100 kHz to 20 MHz | 11 | none | 0.492 to 0.503 V peak | -0.029 to +0.004 dB | -0.14 to +0.02 deg | 13.8 s |

**Problem 1 of 13.3 is closed as a wiring fault**: the level is now flat within 1.3% from 50 Hz to 20 MHz, as in Milestone 0c, and the two runs agree. No auto-range retries and no flags in either run (the hysteresis fix was in). Skew check: +0.148 and +0.151 ns, snapped to +0.15 ns. Scope counters: 0 errors, 0 resyncs after connect; generator outputs OFF at the end.

Lesson for the app: a through measurement shows 0 dB even when the reference level has collapsed, so the reference amplitude itself is worth watching. Not implemented: a warning when the reference level is far below the level the stimulus setting predicts.
### 13.6 RC low-pass (1 kOhm, 100 nF) and what it exposed (2026-10-06)

Wiring: generator CH1 -> 1 kOhm -> 100 nF to ground; CH1 probe (reference) on the generator side, CH2 probe (DUT) on the capacitor; both 10X. Sweeps 50 Hz to 20 MHz, 10 points per decade, no skew check (the probes are not on one node), DC coupling. Data: `results/m7/m7_sweep_rc_1k_100n.*`, `..._dcfix.*`, `results/s7_smallsig_py.json`, `results/s7_smallsig_offset_py.json`.

**What worked.** From 50 Hz to 22 kHz (0 to -23 dB) the measurement follows a first-order low-pass with a corner of 1515 Hz (nominal 1592 Hz; that is 105 nF if the resistor is exactly 1 kOhm, inside a normal capacitor tolerance): gain within +/-0.06 dB of that curve, phase within +0.1 / -0.2 degrees up to 3 kHz and drifting to +0.9 degrees at 22 kHz. No instrument errors in either sweep; generator OFF, panel unlocked and sweep AUTO at the end.

**What failed.** Above about 28 kHz (below -25 dB) the DUT channel went wrong: AUTORANGE_FAILED at several points, then from 44 to 55 kHz readings 14 to 18 dB too low with SNR near 0, then amplitudes of exactly zero (-350 dB). The signal there is still 2.5 to 4 mVpp at the scope input, which the scope can measure.

**Cause 1: DC on the signal.** CH2 carries +6.2 mV of DC at the scope input (about 62 mV at the probe tip), CH1 about +7.6 mV. Where it comes from is not established (generator offset error, or the scope's inputs). At 5 and 2 mV/div the trace simply sits high (codes centred on 161 and 205) and reads correctly: 4.1 and 4.04 mVpp, SNR 25 and 30 dB. At 1 mV/div the DC is 6.2 divisions, beyond the 5.06-division data range: 485 of 700 samples on code 254, fitted amplitude 0.63 mVpp instead of 4.0.

**Cause 2: the 500 uV/div step returns wrong data without any clip indication.** With the trace off scale at 500 uV/div the codes were 75 to 125, none on a rail; in 12.14 an overdriven signal there read 125 on its clipped half. In every such case the reading is bounded by code 125 on one side. One explanation that fits all three observations: 500 uV/div is a x2 digital zoom of the 1 mV/div range whose arithmetic wraps around instead of clipping (a clipped 254 becomes 2 x (254 - 128) + 128 = 380, which wraps to 124). **This explanation is an inference; it was not tested.** The practical fact is measured: at 500 uV/div an off-scale or clipped trace cannot be told from a good one.

**Cause 3: the scope keeps the channel offset in divisions, not volts, when V/div changes.** An offset of -6.24 mV set at 2 mV/div (which centred the trace: codes 102 to 153) read back -3.12 mV after changing to 1 mV/div and -1.56 mV at 500 uV/div. Setting -6.24 mV again at 500 uV/div put every sample on code 1, so the offset does not behave normally on that step either.

**Changes made in the app (all tested against the simulators, 223 tests; NOT yet re-run on the bench):**
1. Auto-range measures the DC of each channel and re-centres the trace with the channel offset when its middle is more than one division from the screen centre (`Digitizer.set_offset`).
2. Auto-range never selects a V/div at which DC plus signal peak would not fit in the data range (`autorange.min_vdiv_for_dc`); this also covers scopes with no offset command.
3. The driver puts the offset back in volts after every V/div change.
4. The driver no longer uses 500 uV/div; 1 mV/div is the most sensitive step. Cost: 6 dB of range at the bottom.

A bench sweep with only change 1 and 2 in place (`rc_1k_100n_dcfix`) still failed in the same region, which is what led to findings 2 and 3.

**Open after this section:**
- Re-run the RC sweep on the bench with all four changes.
- The user's suggestion: use AC coupling on the scope for this measurement. Not tried yet. It would remove the DC problem at its root; its cost is a high-pass corner at low frequency that must be checked on both channels (the 50 Hz points). It can be tried from the app today (`ScopeConfig.coupling = "AC"`), and should be compared with the DC-coupled, offset-corrected sweep before choosing the default.
- The user saw CH2 "jumping around" on the scope during the sweep and the scope left on 500 uV/div afterwards. The jumping is auto-range and the offset changes at work. The app does not restore the scope's V/div, timebase and offset after a sweep; it only goes back to sweep AUTO and unlocks the panel.
- Where the 6 to 8 mV of DC at the inputs comes from.
- Phase drift of about +1 degree between 3 and 40 kHz against the ideal RC (component, probe or scope: not examined).

### 13.7 The DC is not the scope's own input offset (2026-10-06)

The user ran the scope's self calibration, removed all probes and reported that an offset was still visible at 500 uV/div. `hwcheck/s7_dcoffset.py` then read CH1 and CH2 with the inputs open, channel offset 0, timebase 10 ms/div (140 ms record), at nine V/div steps in DC, AC and GND coupling. Generator outputs OFF throughout. Data: `results/s7_dcoffset_py.json`. 0 reply errors, 0 empty blocks.

| V/div | CH1, DC coupling | CH2, DC coupling |
|---|---|---|
| 500 uV | +0.165 mV (+0.33 div) | +0.290 mV (+0.58 div) |
| 1 mV | +0.136 mV (+0.14 div) | +0.266 mV (+0.27 div) |
| 2 mV | +0.104 mV (+0.05 div) | +0.228 mV (+0.11 div) |
| 5 mV | -0.145 mV (-0.03 div) | +0.007 mV (0.00 div) |
| 10 mV | -0.72 mV (-0.07 div) | -0.55 mV (-0.05 div) |
| 20 mV | -1.5 mV (-0.08 div) | -2.0 mV (-0.10 div) |
| 50 mV to 1 V | -0.09 to -0.11 div | -0.12 div |

- **The scope's own offset is 0.3 mV or less on the steps from 500 uV to 5 mV/div.** That is 0.3 to 0.6 division at 500 uV/div, which is what the user saw on the screen. On the steps from 10 mV/div up it is a constant -0.1 division (about 2.5 codes).
- AC coupling gives the same numbers as DC coupling within 0.03 mV on the sensitive steps. So this residual is generated after the coupling switch and **AC coupling does not remove it**.
- GND coupling returns code 127 on every sample at every step, with zero noise. It is a drawn line, not a measurement of the input stage.
- Open-input noise: 7 codes rms at 500 uV/div, 3 at 1 mV/div, 1.5 at 2 mV/div (mains pickup included).
- **The +6.2 mV (CH2) and +8.6 mV (CH1) measured in 13.6 are 20 times larger than this.** So they did not come from the scope's input stage as it is now. Two explanations remain: the generator output carries 60 to 90 mV of DC (seen through the 10X probes), or the scope had a larger offset that the self calibration removed. `hwcheck/s7_dcsource.py` (written, NOT yet run; needs the probes back on the RC) separates the two: DC with the generator output OFF, ON at 1 Vpp and 0.1 Vpp, and ON with the generator's offset set to cancel it.
- New scope fact: **`:CHANnel<n>:SCALe` is ignored on a channel that is switched off** (`:CHANnel<n>:DISPlay 0`): no error, the read-back stays at the old value. CH2 was off when the script started (left so by the user); the restore switched it off first and then could not put 50 mV/div back. Restored by hand (display on, scale, display off). The scripts now restore DISPlay last.
### 13.8 Generator DC check and the RC sweep re-run: the DC is gone, the sweep passes (2026-10-06)

**Corrected by 13.11: the DC is the generator's and it came back later. The conclusion below that the self calibration removed it is wrong. The sweep results stand.**

RC low-pass wired again by the user (as in 13.6). Data: `results/s7_dcsource_py.json`, `results/m7/m7_sweep_rc_retest.*`.

**`hwcheck/s7_dcsource.py`** (DC of both channels, corrected with the open-input reading of 13.7):

| Case | CH1 at the scope input | CH2 at the scope input |
|---|---|---|
| output OFF, 2 mV/div | +0.17 mV | +0.27 mV |
| ON 1 Vpp 1 kHz, 20 mV/div | -0.43 mV | -1.10 mV |
| ON 1 Vpp 35 kHz, CH1 20 mV/div, CH2 2 mV/div | -0.02 mV | -0.69 mV |
| ON 0.1 Vpp 1 kHz, 5 mV/div | +0.02 mV | +0.11 mV |

- **The +6.2 mV (CH2) and +8.6 mV (CH1) of 13.6 are gone.** In the same condition as then (1 Vpp, 35 kHz, CH2 at 2 mV/div) CH2 now reads -0.7 mV. Every reading is within about 1 mV of the open-input value, which at 20 mV/div is 1 to 2 codes.
- So the generator does not put out 60 to 90 mV of DC. What changed between 13.6 and now is the scope's self calibration (and the probes were removed and put back). **The self calibration removing the offset is the explanation that fits; it was not proven** (there is no measurement of the open inputs from before it).
- The last step (generator offset set to cancel the DC) failed: `:CHANnel1:BASE:OFFSet -0.011` read back `0.0`. Not followed up, there being nothing left to cancel. Outputs OFF at the end, no restore failures.

**RC sweep re-run** (`m7_sweep.py rc_retest 50 20000000 10 --no-skew`, DC coupling, with the four changes of 13.6): 58 points in 65.1 s, **no AUTORANGE_FAILED**, 0 scope errors, 0 resyncs after connect, generator OFF, panel unlocked and sweep AUTO at the end. The most sensitive step used was 1 mV/div.

| Range | Gain against a first-order low-pass, corner 1513 Hz | Phase against it |
|---|---|---|
| 50 Hz to 22.5 kHz (0 to -23 dB) | -0.05 to +0.05 dB | -0.1 to +1.1 deg |
| 22.5 to 110 kHz (to -37 dB) | -0.08 to +0.17 dB | +0.7 to +2.8 deg |
| 110 to 340 kHz (to -47 dB) | -0.19 to +0.47 dB | up to +5 deg |
| above 430 kHz | noise: DUT SNR 1 dB and lower, readings between -51 and -64 dB | meaningless |

- The measurement is correct down to about -47 dB (340 kHz, 2.2 mV at the tip, SNR 2 dB). LOW_SNR is flagged from 35 kHz (SNR 19 dB) and BELOW_FLOOR from 1.3 MHz. The floor of this setup is about -52 to -60 dB with 1 Vpp and 10X probes.
- The phase leads the ideal RC more and more with frequency (+1 deg at 22 kHz, +2.8 deg at 110 kHz). A series resistance of roughly 0.5 to 1 ohm in the capacitor branch (ESR plus contacts) would do that. This is an estimate from two points, not a measurement.
- AC coupling was not needed for this run. Whether it should be offered is still open; note from 13.7 that it does not remove the scope's own residual offset.

### 13.9 Scope settings restored after a sweep; AC-coupled RC sweep (2026-10-06)

**Restore.** The app now reads the scope's timebase, trigger (mode, source, slope, level) and, for each channel it uses, display, probe ratio, vernier, V/div, offset, coupling and bandwidth limit before a sweep, skew check or re-measure, and puts them back afterwards (`Digitizer.save_setup` / `restore_setup`, `Session.begin_measurement` / `end_measurement`). The channel display is restored last because SCALe is ignored on a channel that is off (13.7). Bench: `m7_sweep.py rc_ac` compared 17 settings read before and after the sweep: **all 17 identical**; panel unlocked, sweep AUTO, generator OFF. Not tested on hardware: a scope probe ratio other than 1X at the start, and a channel that was off at the start (covered by the simulated scope only).

**AC coupling** (`m7_sweep.py rc_ac 50 20000000 10 --no-skew --ac`, data `results/m7/m7_sweep_rc_ac.*`): 58 points in 65.0 s, no AUTORANGE_FAILED, 0 scope errors.
- Up to 22 kHz the AC-coupled gain and phase agree with the DC-coupled run of 13.8 within 0.03 dB and 0.2 degrees. Below -40 dB both are in the noise and differ by up to 0.8 dB.
- At 50 and 63 Hz the reference level is 0.3% lower than with DC coupling and gain and phase are unchanged (-0.007 dB, -1.82 deg at 50 Hz in both). The AC corner is therefore far below 50 Hz with 10X probes and is the same on both channels. With 1X probes the corner is ten times higher; not measured.
- AC coupling gave no advantage on this DUT now that the input DC is gone. DC stays the default; AC is already selectable in the GUI (scope panel, Coupling).

**OPEN: one bad capture.** The point at 78.62 Hz (the first one after the timebase changed from 10 to 5 ms/div) read 0.021 V on BOTH channels instead of 0.496 V, with SNR -28 dB, and was flagged only LOW_SNR; gain -0.08 dB, phase +0.34 deg (should be -3.0). The same point was correct in the DC run. The record did not contain a 78.62 Hz sine at the stated sample interval: either the generator had not changed frequency yet, or the record came from before the timebase change. Which one is not known; the raw waveform is not kept. One event in about 230 sweep points on hardware today. The app has no check that would retry such a capture (the reference level check proposed in 13.5 would have caught it).

### 13.10 Retry for a capture that does not hold the stimulus (2026-10-06)

Response to the bad point of 13.9. When the sine fit of the REFERENCE channel has an SNR below 6 dB (`MeasureSettings.bad_ref_snr_db`; a normal reference reads 28 to 38 dB, the bad capture read -28 dB), the capture is not used: both raw waveforms are written to an `.npz` file, the app waits one settling time and acquires again, up to 2 times (`bad_capture_retries`). If the reference is still wrong the point is kept and flagged `REF_SUSPECT`. Each event is a warning in the status log with the file path. Files go to `captures/` next to the app's log file (GUI) or `hwcheck/results/m7/captures/` (`m7_sweep.py`), at most 50 per connection.

Bench after the change: two AC-coupled RC sweeps, 50 Hz to 20 kHz, 28 points each (`m7_sweep_rc_ac_retry1`, `..._retry2`): no bad capture occurred, no flags other than SKEW_UNCHECKED, reference SNR 31 dB or better, scope settings restored, 0 scope errors. **The fault of 13.9 did not come back in these 56 points, so the retry path itself has run only against the simulators** (3 tests). The cause of that one bad capture is still unknown; the next occurrence will leave its raw waveforms behind.

### 13.11 Open items worked through with nobody at the bench (2026-10-06, later)

Setup left by the user: both instruments on USB, the 1 k / 100 nF low-pass on the breadboard, probes as in 13.6. No cable or power change was possible.

**Timed full-range sweep** (`m7_sweep.py rc_timed_full 50 20000000 20 --no-skew`, the GUI's default density): **114 points in 118.8 s, 1.04 s per point** (0.72 to 1.96 s measuring), connect 2.0 s, 5 auto-range retries in total, 0 scope errors, 0 resyncs after connect, no AUTORANGE_FAILED, scope settings restored. Gain against a 1513 Hz first-order low-pass: -0.06 to +0.02 dB up to 22.6 kHz, -0.65 to +0.24 dB from there to 345 kHz. 66 points unflagged, 9 LOW_SNR, 39 BELOW_FLOOR.

**CORRECTION to 13.8: the DC comes from the generator, and it changes over time. The self calibration did not remove it.** Evidence (`s7_dcsource_py.json` = second run, `..._run1.json` = the run of 13.8, `s7_gendc_py.json`):

| Reading (CH2 on the capacitor, 2 mV/div, where one code is 0.8 mV at the tip) | Run of 13.8 | Now |
|---|---|---|
| generator output OFF | +0.27 mV at the input | +0.28 mV at the input |
| generator ON, 1 Vpp, 35 kHz | -0.69 mV at the input (about -9 mV at the tip) | +4.08 mV at the input (**+38.5 mV at the tip**) |
| generator ON, 0.1 Vpp, 1 kHz (5 mV/div) | +0.11 mV | +0.77 mV (+7.6 mV at the tip) |

- With the output OFF the scope reads the same as right after the self calibration, so the scope's zero on the sensitive steps has not moved. With the output ON the DC appears. It is the generator's.
- It is on the capacitor through the 1 k resistor, it follows the generator's offset setting (+20 mV set: +21.8 mV; +30 mV set: +32.7 mV at 100 kHz), and it is smaller at a smaller amplitude.
- Three values so far at 1 Vpp: about +62 mV (13.6, after long sweeps), about -9 mV (13.8, after the generator had been idle), +38.5 mV now (after several sweeps). **A drift with warm-up would fit; that is a guess, nothing was measured against time or temperature.**
- CH1 on its coarse steps cannot measure this: at 20 and 50 mV/div its zero moved by 2 to 5 codes between runs (output OFF at 20 mV/div: -0.02 mV in 13.8, +1.59 mV now), which is 30 to 100 mV at a 10X probe tip.

**The app's DC handling (the four changes of 13.6) is now proven on the bench with DC present**, which 13.8 could not show because there was almost none then:

| Run | Generator offset set | Result |
|---|---|---|
| `rc_dc_plus60` (50 Hz to 20 MHz, 58 points) | +60 mV (about +100 mV at the tips with the generator's own DC: more than the original fault) | no AUTORANGE_FAILED, no CLIPPED, DUT down to 1 mV/div, gain -0.04 to +0.02 dB to 22.6 kHz and -0.05 to +0.93 dB to 345 kHz, 66.4 s |
| `rc_offset_0.1` (1 to 100 kHz, 7 points) | +100 mV | correct, DUT down to 1 mV/div |
| `rc_offset_-0.1` | -100 mV | correct, DUT down to 1 mV/div |

So DC coupling with the offset handling works with at least +/-100 mV of DC at the tips, and AC coupling (13.9) is the other way round the same problem.

**The generator ignores every negative number** (`s7_genoffset.py`, `dbg7_genoffset_neg.py`; firmware 1.09). `:CHANnel1:BASE:OFFSet` with 0.001 to 0.5 reads back exactly and moves the output (+0.1 V set: +101 mV measured). With any negative value (-0.001 to -0.5, written as `-0.1`, `-1e-1` or `-1.000000e-01`) the read-back keeps the previous value and the output does not move. `:CHANnel1:BASE:LOW -0.6` is ignored in the same way. The manual gives the offset range as "0~+/-max" (UTG p.13). No error is reported.
- What works, with positive numbers only: at offset 0 set the amplitude to A + 2d, then `:CHANnel1:BASE:HIGH` (UTG p.13) to A/2 - d. The bottom of the wave stays, the top comes down: read-backs offset -d and amplitude A (tried: A = 1, d = 0.1, 0.3, 0.5; A = 0.2, d = 0.05). Measured at the output: -84 mV for -0.1 V and -289 mV for -0.3 V (at 50 mV/div, where one code is 20 mV at the tip).
- Limit: HIGH cannot go below 0 this way, so the lowest offset is minus half the amplitude.
- The app's generator driver now does this (`UniTUTG900E._set_level`): never sends a negative number, sets a negative offset by the route above with the output off, verifies offset and amplitude by read-back, and refuses an offset below minus half the amplitude with a plain message. Before, a negative offset in the GUI ended the sweep with a read-back error. `:CHANnel<n>:BASE:HIGH` is added to the driver's command list.

### 13.12 More open items, still with nobody at the bench (2026-10-06, later)

**Restore from an awkward scope state** (`hwcheck/m7_restore.py`: set the scope up, run a 5-point sweep through the app, compare 19 settings before and after; data `results/m7/m7_restore_run1.json` and `m7_restore.json`).
- CH2 switched off before the sweep (50 mV/div, offset 20 mV; CH1 500 mV/div, 1 ms/div): **all 19 settings came back**, CH2 off again with its scale and offset.
- CH1 at probe ratio 10X, AC, 20 MHz limit, offset 0.1 V, trigger slope negative, level 2 V: first run, **everything came back except the trigger level** (2.0 V before, 2.4 V after). Cause: `:TRIGger:LEVel` takes input-referred volts and reports probe-scaled ones (0.2 sent at 10X reads back 2.0), like `:CHANnel<n>:SCALe` (0.05 sent reads back 0.5). `:CHANnel<n>:OFFSet` is not scaled (0.1 sent reads back 0.1). The restore sent the read-back value, the scope clamped it at 2.4 V. Fixed: the level is divided by the trigger source's probe ratio before it is sent. **Second run: all 19 settings came back in both cases.**
- The simulated scope now reports V/div and trigger level probe-scaled, as the real one does.
- 0 scope errors in both runs; generator OFF, panel unlocked, sweep AUTO, start state put back at the end.

**The bad capture of 13.9 could not be reproduced** (`hwcheck/m7_repeat.py`, data `results/m7/m7_repeat_ac.json`): 40 AC-coupled sweeps from 50 to 100 Hz, each crossing the 10 to 5 ms/div change, 200 points in 327 s: **0 rejected captures**, 0 scope errors. So the fault is rarer than about one in 13 such transitions (95 % bound for 0 in 40), and its cause is still not known. The retry of 13.10 stays as the guard.

**Phase lead of the RC filter above 20 kHz.**
- Fits to the recorded sweeps (`hwcheck/a7_phase_lead.py`, no instrument; points from 300 Hz up to where the DUT SNR is 20 dB): capacitance 104.9 to 105.1 nF in every run and model. A series resistance alone needs 0.6 to 1.3 ohm depending on the run's frequency span, a constant loss angle alone 0.56 to 0.78 deg (tan d 0.010 to 0.014), both together 0.4 to 1.0 ohm with 0.2 to 0.45 deg. Both together leave at most 0.6 deg of phase error; neither alone describes the data, and the fitted values move with the span, so **these are descriptions, not measurements of the capacitor**.
- **The lead is not a V/div-range effect of the scope** (`hwcheck/s7_rangephase.py`, AC coupled): the same capacitor voltage measured with CH2 on every step it fits on, CH1 fixed at 20 mV/div.

| Frequency | CH2 steps compared | Phase on each step | Gain on each step | Lead over the ideal RC |
|---|---|---|---|---|
| 5 kHz | 5, 10, 20 mV/div | -72.76, -72.79, -72.78 deg | -10.786, -10.794, -10.792 dB | +0.4 deg |
| 20 kHz | 2, 5, 10, 20 mV/div | -84.75, -84.83, -84.89, -84.78 deg | -22.45, -22.44, -22.36, -22.51 dB | +0.8 to +0.9 deg |
| 50 kHz | 1, 2, 5, 10 mV/div | -87.00, -87.11, -86.99, -87.06 deg | -30.29, -30.34, -30.32, -30.21 dB | +1.2 to +1.3 deg |
| 100 kHz | 1, 2 mV/div | -87.35, -87.45 deg | -36.32, -36.41 dB | +1.7 to +1.8 deg |

  Where the signal fills at least 0.8 division the steps agree within 0.14 deg and 0.09 dB. (Smaller than that the scatter grows: at 100 kHz on 20 mV/div, 0.1 division, the spread is 7.6 deg.)
- With the through sweeps of 13.5 (both probes on one node: phase within 0.2 deg to 20 MHz) this leaves the circuit itself: the capacitor's loss, its series resistance, and the breadboard contacts and ground lead. Telling those apart needs another capacitor or an LCR meter, so a person at the bench.

**Image export follows the vertical unit**: PNG, SVG and PDF now draw the upper plot in dB, Vpp or percent of the input, whichever the Vertical box shows (`ImageOptions.unit`).

### 13.13 First bench session with the user present: skew wizard and through sweep from the GUI (2026-10-06, evening)

Both probes on generator CH1, both 10X. App started with `run.bat`, Mode = Instruments, commit `168dd4d`. Values are read from the user's two screenshots; no data file was exported.

- **Skew wizard in the GUI on the real instruments: works.** 10 MHz: +0.13 ns (+0.48 deg), gain -0.013 dB. 20 MHz: +0.15 ns (+1.07 deg), gain -0.024 dB. Measured +0.14 ns, snapped to the +0.15 ns state, gain mismatch -0.019 dB, correction at 20 MHz -1.08 deg. Same state as the headless check (+0.148 / +0.151 ns).
- **Through sweep from the GUI after accepting the check**: 114 points, 50 Hz to 20 MHz, 20 per decade, 5 Vpp, 100 mV/div on both channels, 114 s, no retries, no flags. Output 99.6 to 100.1 % of the input (within about 0.04 dB); phase within about 0.3 deg of zero over the whole range (last five points, 12.7 to 20 MHz: +0.01 to +0.26 deg, gain -0.011 to -0.026 dB).
- **Fault found and fixed**: the wizard's intro text named 0.5 MHz and 1 MHz (it still followed the sweep range) while the check ran at 10 and 20 MHz. Text only; fixed in `MainWindow.skew_freqs_hint` (commit `919814c`).
- **One enumeration miss**: the first `s6_state.py` of the session found no VISA resource at all (`list_resources` empty) although Windows and libusb showed both devices; the same script worked a few seconds later. Not reproduced, cause unknown.
- The app's log file holds no per-command lines for this run, so the command sequence was not reviewed.

### 13.14 CH3 / CH4, never used before (2026-10-06, evening)

The two probe BNCs moved to scope CH3 (reference) and CH4 (DUT), tips still on generator CH1, both 10X, channels set in the Scope panel. App at commit `919814c`. Values are read from the user's screenshots.

- **CH3 / CH4 work**: the skew check and a 114-point sweep (50 Hz to 20 MHz, 5 Vpp, 100 mV/div) ran with no retries and no flags. The sweep took 128 s against 114 s on CH1 / CH2 (about 0.92 s per point against 0.75 s at the top of the range); not looked into.
- **The delay of this pair is +0.08 to +0.09 ns, not +0.15 ns.** First check: +0.09 ns at 10 MHz (+0.34 deg), +0.08 ns at 20 MHz (+0.59 deg), gain -0.053 / -0.069 dB. Second check: +0.27 deg and +0.66 deg, gain -0.067 / -0.049 dB, measured +0.08 ns. Both were snapped to +0.15 ns, because the four states were measured on CH1 / CH2 and +0.08 ns lies inside the 0.3 ns snap window.
- **The snap over-corrects on this pair**: after accepting, the through sweep's phase falls from 0 to **-0.39 deg at 20 MHz** (-0.09, -0.21, -0.33, -0.38, -0.39 deg from 12.7 to 20 MHz). The measured value would have left about +0.1 deg. Below 1 MHz the error is under 0.03 deg.
- **CH4 reads lower than CH3 towards high frequency**: output 100 % of input at 50 Hz, falling to about 99.0 % at 20 MHz (-0.06 to -0.10 dB over the last five points). On CH1 / CH2 the same sweep stays within 99.6 to 100.1 %. The app does not correct gain; the wizard's warning threshold is 0.3 dB.
- **CH1 / CH2 repeated straight afterwards** (BNCs moved back): check +0.59 deg at 10 MHz, +1.21 deg at 20 MHz, measured +0.17 ns, snapped to +0.15 ns, gain mismatch -0.01 dB; sweep 114 s, phase -0.10 to +0.13 deg over the last five points, gain -0.002 to -0.030 dB. So the CH1 / CH2 delay has now read +0.14 and +0.17 ns in one evening (0.03 ns is 0.2 deg at 20 MHz).
- Open: whether CH3 / CH4 has the same 2 ns steps around its own +0.08 ns (not tested; it would need a `:RUN`, which is forbidden).

**Re-run on CH3 / CH4 after the snap change** (commit `ec3d897`, user decision: snap only for reference CH1 / DUT CH2; from the user's screenshot): check +0.34 deg at 10 MHz and +0.74 deg at 20 MHz, gain -0.065 / -0.068 dB, **+0.10 ns applied, not snapped**. Through sweep, 114 points in 116 s, no retries, no flags: phase +0.05, -0.07, +0.26, +0.05, **+0.07 deg** from 12.7 to 20 MHz (was -0.39 deg at 20 MHz with the snap). The gain droop of CH4 against CH3 is unchanged (about 99.0 to 99.3 % above 10 MHz, -0.045 to -0.100 dB). The sweep time is the same as on CH1 / CH2, so the 128 s of the first CH3 / CH4 run is not a property of the channel pair.

### 13.15 Watchdog with the scope's USB cable pulled during a sweep (2026-10-06, evening)

App at commit `b6dcf64`, started with `--debug`, reference CH3 / DUT CH4, full-range sweep. The user pulled the scope's USB cable after 26 of 114 points. Times are from the app's log.

- **The watchdog works on a scope that is really gone.** 19:00:01.354 first failed read (`[Errno 19] No such device (it may have been disconnected)`); resync attempt until 19:00:03.925 (`:TRIGger:SWEep AUTO` refused, eight rounds of device clear + `*IDN?`, all failed: `No device found`, then `Invalid session handle`); 19:00:03.925 `:CHANnel1:OUTPut OFF` and `:CHANnel2:OUTPut OFF` to the generator; 19:00:04.156 error shown. **Generator off 2.6 s after the cable came out.** The user saw the output light go out and the error dialog; the toolbar went back to the disconnected state and the 26 points stayed on the plot. No forbidden command in the log.
- **Scope state after replugging, no power cycle** (`s6_state.py`, read-only): answers at once, `:SYSTem:LOCK?` 0, sweep AUTO and running, timebase still 500 us/div (the sweep's value: the restore could not run), no error. So a pulled cable needs no power cycle, and no panel lock was left behind.
- **Two faults in the messages, fixed after this run**: (1) the log said "The scope was resynchronised during the sweep; the skew correction used may no longer be right" although the resync had failed; it is no longer written for a dead session. (2) The advice was to power-cycle the scope, which does not fit a pulled cable; the transport now reports whether the device is still on the bus (`Transport.present`, a USB enumeration, nothing is sent) and the advice becomes "check the scope's USB cable and that it is switched on" (`UNPLUGGED_ADVICE`). The new text has run against the simulated transport only.
- **Kept as it is (user decision)**: the generator output stays on while the resync is tried and is switched off when it fails.
- Not covered by this test: a scope that is frozen but still on the bus (writes time out instead of failing at once, so the resync takes longer).

**Second and third cable pull, with the fixes** (commit `4828300`, `--debug`, sweeps on CH1 / CH2; from the app's log and the user's screenshot). 19:08:32.767 first failed write (`[Errno 19] No such device`), 19:08:35.358 generator outputs off (2.6 s), 19:08:35.587 error with the new text: "The scope is no longer on USB. ... Check the scope's USB cable and that it is switched on, then connect again and repeat the channel skew check." No "was resynchronised" line. **Reconnect after replugging, no power cycle, same app window: worked** (19:09:13 connected, 19:09:35 a new sweep started). That sweep lost the scope again at 19:09:42.202 after 4 of 114 points, same error and the same sequence (generator off at 19:09:44.795). Whether this third loss was a deliberate pull is not recorded in the log; the user is asked.
