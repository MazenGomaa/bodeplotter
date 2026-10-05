"""SCPI command strings used by the hardware gate, each with its manual reference.

UPO = docs/Uni-T_UPO1002_Programming_Manual_0824.pdf  (page numbers "n / 137")
UTG = docs/UTG900E Programming Manual V1.0.pdf        (page numbers "n / 41")
"""

# ---------------------------------------------------------------- common
IDN = "*IDN?"                       # UPO p.7 / UTG p.5, "IEEE488.2 Common Commands"
OPC_Q = "*OPC?"                     # UPO p.7 "*OPC". NOT documented in the UTG manual.

# ---------------------------------------------------------------- scope (UPO)
# S_RUN used to be ":RUN" (UPO p.8). Milestone 0c: ":RUN" after a USB session reopen shifts the
# scope's channels against each other by whole samples (HW_REPORT.md 12.11), so no hwcheck script
# sends it any more. The name is kept so the Milestone 0 scripts still read the same; it now holds
# the command that restarts a stopped scope without that side effect (U1K p.36).
S_RUN = ":TRIGger:SWEep AUTO"
S_STOP = ":STOP"                    # UPO p.8, SYSTem Command ":STOP"
S_ERR_Q = ":SYSTem:ERRor?"          # UPO p.9, ":SYSTem:ERRor"
S_VERS_Q = ":SYSTem:VERSion?"       # UPO p.13, ":SYSTem:VERSion?"

S_CH_COUP = ":CHANnel{n}:COUPling"  # UPO p.18, {DC|AC|GND}
S_CH_DISP = ":CHANnel{n}:DISPlay"   # UPO p.18, {1|ON|0|OFF}
S_CH_PROBE = ":CHANnel{n}:PROBe"    # UPO p.19-20, 0.001X~20000X
S_CH_OFFS = ":CHANnel{n}:OFFSet"    # UPO p.20
S_CH_SCAL = ":CHANnel{n}:SCALe"     # UPO p.20-21, volts/div
S_CH_BWL = ":CHANnel{n}:BWLimit"    # UPO p.17-18, {20M|FULL}
S_CH_VERN = ":CHANnel{n}:VERNier"   # UPO p.21, fine/coarse V/div

S_TB_SCAL = ":TIMebase:SCALe"       # UPO p.23-24, s/div
S_TB_OFFS = ":TIMebase:OFFSet"      # UPO p.22-23
S_TB_MODE_Q = ":TIMebase:MODE?"     # UPO p.22, {MAIN|WINDow}

S_TRIG_MODE = ":TRIGger:MODE"       # UPO p.52, EDGE etc.
S_TRIG_SWEEP = ":TRIGger:SWEep"     # UPO p.52-53, {AUTO|NORMal|SINGle}
S_TRIG_STAT_Q = ":TRIGger:STATus?"  # UPO p.53
S_TRIG_LEV = ":TRIGger:LEVel"       # UPO p.53-54
S_TRIG_SRC = ":TRIGger:SOURce"      # UPO p.54-55
S_TRIG_SLOPE = ":TRIGger:EDGE:SLOPe"  # UPO p.55-56

S_ACQ_TYPE = ":ACQuire:TYPE"        # UPO p.92
S_ACQ_DEPTH_Q = ":ACQuire:MEMory:DEPTh?"  # UPO p.93

S_WAV_SRC = ":WAVeform:SOURce"      # UPO p.99-100, {CHANnel<n>|MATH}
S_WAV_MODE = ":WAVeform:MODE"       # UPO p.98, {NORMal|RAW}
S_WAV_FMT = ":WAVeform:FORMat"      # UPO p.98, {WORD|BYTE|ASCII}
S_WAV_POINTS_Q = ":WAVeform:POINts?"  # UPO p.100
S_WAV_START_Q = ":WAVeform:STARt?"  # UPO p.99
S_WAV_STOP_Q = ":WAVeform:STOP?"    # UPO p.99
S_WAV_DATA_Q = ":WAVeform:DATA?"    # UPO p.100-101, IEEE 488.2 block (Appendix 2 p.137)
S_WAV_PRE_Q = ":WAVeform:PREamble?"  # UPO p.101-102: Format,Type,Points,Count,Xinc,Xor,Xref,Yinc,Yor,Yref
S_WAV_XINC_Q = ":WAVeform:XINCrement?"  # UPO p.102
S_WAV_XOR_Q = ":WAVeform:XORigin?"  # UPO p.102-103
S_WAV_YINC_Q = ":WAVeform:YINCrement?"  # UPO p.103
S_WAV_YOR_Q = ":WAVeform:YORigin?"  # UPO p.104
S_WAV_YREF_Q = ":WAVeform:YREFerence?"  # UPO p.104

S_MEAS_VPP_Q = ":MEASure:VPP? CHANnel{n}"         # UPO p.44
S_MEAS_FREQ_Q = ":MEASure:FREQuency? CHANnel{n}"  # UPO p.48

# ---------------------------------------------------------------- generator (UTG)
G_OUT = ":CHANnel{n}:OUTPut"        # UTG p.9, {1|ON|0|OFF}
G_LOAD = ":CHANnel{n}:LOAD"         # UTG p.11, 1~10000 ohm, 10000 = high resistance
G_AMP_UNIT = ":CHANnel{n}:AMPLitude:UNIT"  # UTG p.11, {VPP|VRMS|DBM}
G_WAVE = ":CHANnel{n}:BASE:WAVe"    # UTG p.11-12, {SINe|SQUare|PULSe|RAMP|ARB|NOISe|DC}
G_FREQ = ":CHANnel{n}:BASE:FREQuency"  # UTG p.12, Hz
G_AMP = ":CHANnel{n}:BASE:AMPLitude"   # UTG p.13, in the channel's amplitude unit
G_OFFS = ":CHANnel{n}:BASE:OFFSet"  # UTG p.13, V
G_PHASE = ":CHANnel{n}:BASE:PHASe"  # UTG p.12-13, degrees
G_MODE = ":CHANnel{n}:MODe"         # UTG p.15-16; set form "CONTinue" per UTG p.37 example
G_LOCK_Q = ":SYSTem:LOCK?"          # UTG p.5
