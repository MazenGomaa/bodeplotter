"""UNI-T UTG900E family function generator driver (developed on a UTG932E, firmware 1.09).

Ported from the bench I/O layer hwcheck/iolayer.py. Manual: UTG = docs/UTG900E Programming
Manual V1.0.pdf. Rules from HW_REPORT.md:

  * Only the commands in ALLOWED are ever sent, in the exact long form the manual prints.
    Anything else is refused before any I/O: an unknown query ('*OPC?' is one) can leave
    this generator deaf to every command until a USBTMC clear (G2).
  * Replies carry no terminator (G1). Commands are paced with a delay, not with '*OPC?'.
  * A timeout or a malformed reply is answered with a device clear and one retry.
  * The amplitude unit is set to VPP before the amplitude (G4). High-Z is LOAD 10000.
  * safe_off() switches both outputs off and never raises.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Callable

from . import scpi
from .base import DriverError, SignalSource, SourceCaps
from .scpi import BlockedCommand, Command, InstrumentUnresponsive, ReplyError, SetError
from .transport import Transport, TransportError, VisaTransport

log = logging.getLogger("bodeplot.drivers.utg900e")

V_IDN = scpi.idn_validator("UNI-T Technologies", "UTG9")
V_WAVE = scpi.enum(["SINe", "SQUare", "PULSe", "RAMP", "ARB", "NOISe", "DC"])   # UTG p.11
V_UNIT = scpi.enum(["VPP", "VRMS", "DBM"])                                      # UTG p.11

_CH = r":CHANnel[12]"
_NUM = r"-?\d+(\.\d+)?"


class UniTUTG900E(SignalSource):
    COMMANDS: tuple[Command, ...] = (
        Command("*IDN?", "UTG p.5", True),
        Command(":SYSTem:LOCK?", "UTG p.5", True, note="query only; returns 1 under USB control"),
        Command(":CHANnel<n>:OUTPut", "UTG p.9", True),
        Command(":CHANnel<n>:LOAD", "UTG p.11", True, note="10000 = High-Z"),
        Command(":CHANnel<n>:AMPLitude:UNIT", "UTG p.11", True),
        Command(":CHANnel<n>:BASE:WAVe", "UTG p.11", True),
        Command(":CHANnel<n>:BASE:FREQuency", "UTG p.12", True),
        Command(":CHANnel<n>:BASE:PHASe", "UTG p.12", True, note="queried only"),
        Command(":CHANnel<n>:BASE:AMPLitude", "UTG p.13", True),
        Command(":CHANnel<n>:BASE:OFFSet", "UTG p.13", True, note="negative values are ignored (firmware 1.09)"),
        Command(":CHANnel<n>:BASE:HIGH", "UTG p.13", True, note="used to reach a negative offset"),
        Command(":CHANnel<n>:MODe?", "UTG p.15", True, note="query only"),
    )
    ALLOWED = tuple(re.compile(p) for p in (
        r"^\*IDN\?$",                                                       # UTG p.5
        r"^:SYSTem:LOCK\?$",                                                # UTG p.5 (query only)
        rf"^{_CH}:OUTPut( (ON|OFF)|\?)$",                                   # UTG p.9
        rf"^{_CH}:LOAD( {_NUM}|\?)$",                                       # UTG p.11
        rf"^{_CH}:AMPLitude:UNIT( (VPP|VRMS|DBM)|\?)$",                     # UTG p.11
        rf"^{_CH}:BASE:WAVe( (SINe|SQUare|PULSe|RAMP|ARB|NOISe|DC)|\?)$",   # UTG p.11
        rf"^{_CH}:BASE:FREQuency( {_NUM}|\?)$",                             # UTG p.12
        rf"^{_CH}:BASE:PHASe\?$",                                           # UTG p.12 (query only)
        rf"^{_CH}:BASE:AMPLitude( {_NUM}|\?)$",                             # UTG p.13
        rf"^{_CH}:BASE:OFFSet( {_NUM}|\?)$",                                # UTG p.13
        rf"^{_CH}:BASE:HIGH( {_NUM}|\?)$",                                  # UTG p.13
        rf"^{_CH}:MODe\?$",                                                 # UTG p.15 (query only)
    ))
    # *IDN? names only the family (UTG900E), so the limits are the smallest of the family
    # that includes the UTG932E: sine to 30 MHz. The manual gives the amplitude range only
    # as "1 mVpp ~ max. output" (UTG p.13); 10 Vpp is the limit used here. Bench-tested:
    # 50 Hz to 20 MHz, 50 mVpp to 1 Vpp, High-Z. Every value is read back when set.
    caps = SourceCaps(model="UTG900E", channels=2, sine_min_hz=1e-6, sine_max_hz=30e6,
                      amp_min_vpp=1e-3, amp_max_vpp=10.0, loads=("HIGHZ", "50"))

    def __init__(self, transport_factory: Callable[[str, str], Transport] | None = None, *,
                 write_delay_s: float = 0.05, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.perf_counter):
        self._factory = transport_factory or (lambda resource, backend: VisaTransport(resource, backend, 3.0))
        self.write_delay_s = write_delay_s
        self._sleep, self._clock = sleep, clock
        self.t: Transport | None = None
        self.idn_text = ""
        self.warnings: list[str] = []
        self.stats = dict(queries=0, blocked=0, timeouts=0, clears=0, retries=0, set_retries=0)

    # ------------------------------------------------------------------ I/O
    @staticmethod
    def _chan(n: int) -> str:
        if n not in (1, 2):                       # UTG p.9: n value 1, 2
            raise DriverError(f"generator channel {n!r} does not exist")
        return f"CHANnel{n}"

    def _check(self, cmd: str) -> None:
        if self.t is None:
            raise DriverError("generator is not open", cmd)
        if not any(p.match(cmd) for p in self.ALLOWED):
            self.stats["blocked"] += 1
            raise BlockedCommand(f"not sent: not in the UTG900E command list: {cmd!r}", cmd)

    def _clear(self) -> None:
        self.stats["clears"] += 1
        try:
            self.t.clear()
        except Exception as e:
            log.warning("generator device clear failed: %s", e)
        self._sleep(0.3)

    def write(self, cmd: str) -> None:
        self._check(cmd)
        try:
            self.t.write(cmd)
        except TransportError as e:
            raise DriverError(f"generator write failed: {e}", cmd)
        self._sleep(self.write_delay_s)         # pacing instead of *OPC?

    def query(self, cmd: str, validate):
        """Timeout or malformed reply -> device clear -> one retry."""
        self._check(cmd)
        last: Exception | None = None
        for attempt in (1, 2):
            self.stats["queries"] += 1
            try:
                self.t.write(cmd)
                return validate(self.t.read().decode("ascii", "replace").strip())
            except TransportError as e:
                last = e
                self.stats["timeouts"] += 1
            except ReplyError as e:
                last = e
            log.warning("generator query %r failed (%s); device clear%s", cmd, last,
                        ", retry" if attempt == 1 else "")
            self._clear()
            if attempt == 1:
                self.stats["retries"] += 1
        if isinstance(last, TransportError):
            raise InstrumentUnresponsive(
                f"the generator does not answer {cmd!r}: {last}", cmd,
                "The generator stopped answering. Check its USB cable, power-cycle it, then connect again.")
        raise last

    def set_verified(self, cmd: str, arg: str, validate, expect, timeout_s: float = 2.0,
                     tol_abs: float = 1e-12):
        last = None
        for _ in (1, 2):
            self.write(f"{cmd} {arg}")
            t0 = self._clock()
            while True:
                last = self.query(cmd + "?", validate)
                same = scpi.close(last, expect, absol=tol_abs) if isinstance(expect, float) else last == expect
                if same:
                    return last
                if self._clock() - t0 > timeout_s:
                    break
                self._sleep(0.05)
            self.stats["set_retries"] += 1
        raise SetError(f"generator {cmd} {arg}: read back {last!r}, wanted {expect!r}", f"{cmd} {arg}")

    # ------------------------------------------------------------------ SignalSource
    def open(self, resource: str, backend: str = "py") -> None:
        self.close()
        try:
            self.t = self._factory(resource, backend)
        except TransportError as e:
            raise DriverError(str(e), "open")
        self.idn_text = self.query("*IDN?", V_IDN)
        self.safe_off()                         # outputs are OFF unless a measurement needs them

    def close(self) -> None:
        if self.t is None:
            return
        try:
            self.safe_off()
            self.t.close()
        finally:
            self.t = None

    def idn(self) -> str:
        return self.idn_text or self.query("*IDN?", V_IDN)

    def output(self, ch: int) -> bool:
        return self.query(f":{self._chan(ch)}:OUTPut?", scpi.v_bool)                  # UTG p.9

    def configure_sine(self, ch: int, freq_hz: float, amp_vpp: float, offset_v: float, load: str) -> None:
        c = self._chan(ch)
        if load not in self.caps.loads:
            raise DriverError(f"unsupported load {load!r}", "configure_sine")
        if not (self.caps.amp_min_vpp <= amp_vpp <= self.caps.amp_max_vpp):
            raise DriverError(f"amplitude {amp_vpp:g} Vpp is outside {self.caps.amp_min_vpp:g} to "
                              f"{self.caps.amp_max_vpp:g} Vpp", "configure_sine")
        ohms = 10000.0 if load == "HIGHZ" else float(load)       # UTG p.11: 10000 = high resistance
        self.set_verified(f":{c}:BASE:WAVe", "SINe", V_WAVE, "SINe")                          # UTG p.11
        self.set_verified(f":{c}:LOAD", scpi.plain_decimal(ohms), scpi.v_float, ohms)         # UTG p.11
        self.set_verified(f":{c}:AMPLitude:UNIT", "VPP", V_UNIT, "VPP")                       # UTG p.11
        self.set_frequency(ch, freq_hz)
        self._set_level(c, float(amp_vpp), float(offset_v))

    def _set_level(self, c: str, amp_vpp: float, offset_v: float) -> None:
        """Amplitude and offset. This generator (firmware 1.09) ignores every NEGATIVE
        number it is sent: ':BASE:OFFSet -0.1' and ':BASE:LOW -0.6' leave the value as it
        was, in any number format, with no error (HW_REPORT.md 13.11). A negative offset
        -d is reached with positive numbers only: at offset 0 the amplitude is widened to
        A + 2d, then the top is pulled down to A/2 - d with ':BASE:HIGH'; the bottom stays
        at -(A/2 + d). Measured: the read-backs give offset -d and amplitude A, and the DC
        at the output moves. That needs A/2 - d >= 0 and the output OFF meanwhile."""
        amp = lambda v: self.set_verified(f":{c}:BASE:AMPLitude", scpi.plain_decimal(v, 4), scpi.v_float,
                                          float(v), tol_abs=1e-6)                             # UTG p.13
        offs = lambda v: self.set_verified(f":{c}:BASE:OFFSet", scpi.plain_decimal(v, 4), scpi.v_float,
                                           float(v), tol_abs=1e-6)                            # UTG p.13
        if offset_v >= 0:
            offs(0.0)                           # from a known state: the last offset may be negative
            amp(amp_vpp)
            offs(offset_v)
            return
        d = -offset_v
        if d > amp_vpp / 2 + 1e-9:
            raise DriverError(
                "This generator cannot be set to an offset of %g V at %g Vpp: it ignores negative "
                "values, and the route around that only reaches down to minus half the amplitude "
                "(%g V here). Use an offset of %g V or higher." % (offset_v, amp_vpp, -amp_vpp / 2, -amp_vpp / 2),
                "configure_sine")
        if amp_vpp + 2 * d > self.caps.amp_max_vpp:
            raise DriverError("An offset of %g V at %g Vpp is outside what the generator can be set to."
                              % (offset_v, amp_vpp), "configure_sine")
        if self.query(f":{c}:OUTPut?", scpi.v_bool):                                          # UTG p.9
            raise DriverError("A negative offset can only be set while the generator output is off.",
                              "configure_sine")
        offs(0.0)
        amp(amp_vpp + 2 * d)
        high = amp_vpp / 2 - d
        self.set_verified(f":{c}:BASE:HIGH", scpi.plain_decimal(high, 4), scpi.v_float, float(high),
                          tol_abs=1e-4)                                                       # UTG p.13
        got_off = self.query(f":{c}:BASE:OFFSet?", scpi.v_float)
        got_amp = self.query(f":{c}:BASE:AMPLitude?", scpi.v_float)
        if abs(got_off - offset_v) > 1e-3 or abs(got_amp - amp_vpp) > 1e-3:
            raise SetError("generator offset %g V at %g Vpp: read back offset %g V, amplitude %g Vpp"
                           % (offset_v, amp_vpp, got_off, got_amp), f":{c}:BASE:HIGH")

    def set_frequency(self, ch: int, freq_hz: float) -> None:
        if not (self.caps.sine_min_hz <= freq_hz <= self.caps.sine_max_hz):
            raise DriverError(f"frequency {freq_hz:g} Hz is out of range", "set_frequency")
        self.set_verified(f":{self._chan(ch)}:BASE:FREQuency", scpi.plain_decimal(freq_hz, 6),
                          scpi.v_float, float(freq_hz))                                       # UTG p.12

    def set_output(self, ch: int, on: bool) -> None:
        self.set_verified(f":{self._chan(ch)}:OUTPut", "ON" if on else "OFF", scpi.v_bool, bool(on))  # UTG p.9

    def safe_off(self) -> None:
        """Both outputs off. Never raises; no read, so it works on a half-dead link."""
        if self.t is None:
            return
        for ch in (1, 2):
            try:
                self.t.write(f":CHANnel{ch}:OUTPut OFF")                                      # UTG p.9
                self._sleep(self.write_delay_s)
            except Exception as e:
                log.error("could not switch generator output %d off: %s", ch, e)
