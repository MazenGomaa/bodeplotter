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
