"""UNI-T UPO1000 family oscilloscope driver (developed on a UPO1054, firmware 1. 01. 0047).

Ported from the bench I/O layer hwcheck/iolayer.py. Every command is in COMMANDS with its
manual page (U1K = docs/Uni-T_UPO1000_Programming_Manual_0424.pdf) and whether it was
exercised on the real scope. The rules below come from HW_REPORT.md; each one is there
because breaking it caused a real fault on the bench.

  * Never ':RUN' (12.11: it can shift CH2 against CH1 by 2 ns steps). Restart with
    ':TRIGger:SWEep AUTO'. NORMal sweep is not used (12.13: never read back as set).
  * '*OPC?' after every write (S3), plus a minimum gap after timebase and V/div changes.
  * Plain-decimal numbers only (S1); probe ratio with its X suffix (S2).
  * Every setting is read back. Every reply is format-checked and followed by a '*IDN?'
    sentinel, so a reply that is one step late is caught instead of used (S5).
  * A waveform is read only from a stopped single-shot record (S4). An empty block is
    never retried in place: resync, then one new acquisition.
  * Timebase and V/div come from stored tables (step_tables.py); they are never walked
    at connect (12.13: the scope froze during such a walk).
  * Recovery is: sweep AUTO, device clear, sentinel. If that fails the scope is declared
    unresponsive (InstrumentUnresponsive); nothing that needs administrator rights is
    tried, and the user is told to power-cycle it.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable

import numpy as np

from . import scpi, step_tables
from .base import AcquireTimeout, Digitizer, DigitizerCaps, DriverError, Waveform
from .scpi import (BlockedCommand, Command, EmptyBlock, InstrumentUnresponsive, OutOfStep, ReplyError,
                   SetError)
from .transport import Transport, TransportError, VisaTransport

log = logging.getLogger("bodeplot.drivers.upo1000")

V_IDN = scpi.idn_validator("UNI-T Technologies", "UPO1")
V_COUPLING = scpi.enum(["DC", "AC", "GND"])                      # U1K p.13
V_BWL = scpi.enum(["20M", "FULL"])                               # U1K p.12
V_SWEEP = scpi.enum(["AUTO", "NORMal", "SINGle"])                # U1K p.36 (NORMal is never set)
V_STATUS = scpi.enum(["STOP", "ARMED", "READY", "TRIGED", "AUTO", "SCAN", "RESET", "REPLAY", "WAIT"])  # U1K p.37
V_TRIGMODE = scpi.enum(["EDGE", "PULSe", "VIDeo", "SLOPe", "RUNT", "WINDow", "DELay", "TIMeout",
                        "DURation", "SHOLd", "NE", "PATTern"])   # U1K p.36
V_SLOPE = scpi.enum(["POSitive", "NEGative", "ALTernation"])     # U1K p.39
V_WAVMODE = scpi.enum(["NORMal", "RAW"])                         # U1K p.69
V_WAVFMT = scpi.enum(["WORD", "BYTE", "ASCII"])                  # U1K p.69
V_SRC = scpi.enum(["CHANnel1", "CHANnel2", "CHANnel3", "CHANnel4", "EXT", "ACLINE", "MATH"])  # U1K p.38, p.70

UNRESPONSIVE_ADVICE = ("The scope stopped answering and could not be resynchronised. The generator "
                       "outputs have been switched off. Power-cycle the scope (off, wait 5 seconds, on), "
                       "then connect again and repeat the channel skew check.")
# the scope is gone from the USB bus (bench: cable pulled mid-sweep, HW_REPORT.md 13.15)
UNPLUGGED_ADVICE = ("The scope is no longer on USB. The generator outputs have been switched off. "
                    "Check the scope's USB cable and that it is switched on, then connect again "
                    "and repeat the channel skew check.")

_SCALE_CMD = re.compile(r"^:(TIMebase|CHANnel[1-4]):SCALe\b", re.IGNORECASE)
_FORBIDDEN = (
    (re.compile(r"^:?RUN$", re.IGNORECASE),
     "':RUN' is never sent: it can shift the channels against each other (HW_REPORT.md 12.11)"),
    (re.compile(r"^:TRIG(ger)?:SWE(ep)? +NORM", re.IGNORECASE),
     "NORMal sweep is not used: it never read back as set (HW_REPORT.md 12.13)"),
    (re.compile(r"^\*RST$|^:?AUTO$|^:SYSTem:SETup |^:CALibrate", re.IGNORECASE),
     "reset, auto-set, setup load and calibration commands are never sent"),
)


class UniTUPO1000(Digitizer):
    HDIV = 14                   # U1K p.72: XORigin = -TimeScale * 7
    PTS_PER_DIV = 50            # U1K p.72: XINCrement = TimeScale / 50
    CODES_PER_DIV = 25          # U1K p.72: YINCrement = VerticalScale / 25
    # Measured 2026-10-06 (HW_REPORT.md 12.14): waveform codes stop at 1 and 254, not 0 and
    # 255, and cover 10.1 divisions; the screen grid has 8.
    RAIL_LOW, RAIL_HIGH = 1, 254
    SCREEN_VDIVS = 8.0
    DATA_VDIVS = (RAIL_HIGH - RAIL_LOW) / CODES_PER_DIV
    # 500 uV/div is a real step of the scope but is not used. Measured 2026-10-06
    # (HW_REPORT.md 13.6): a trace more than about 5 divisions from the centre does not
    # stop at a rail code there, it comes back as mid-scale codes (around 125), so a
    # clipped or off-scale capture cannot be told from a good one. 1 mV/div clips cleanly.
    UNUSABLE_VDIV = (5e-4,)

    COMMANDS: tuple[Command, ...] = (
        Command("*IDN?", "U1K p.5", True),
        Command("*OPC?", "U1K p.5", True),
        Command(":SYSTem:ERRor?", "U1K p.6", True),
        Command(":SYSTem:LOCK", "U1K p.6", True, note="1 = locked (the manual's 'Return format' text has it reversed)"),
        Command(":STOP", "U1K p.6", True, query=False, note="not used by the driver; see HW_REPORT.md 12.13"),
        Command(":CHANnel<n>:BWLimit", "U1K p.12", True),
        Command(":CHANnel<n>:COUPling", "U1K p.13", True),
        Command(":CHANnel<n>:DISPlay", "U1K p.13", True),
        Command(":CHANnel<n>:PROBe", "U1K p.14", True, note="argument needs the X suffix"),
        Command(":CHANnel<n>:OFFSet", "U1K p.14", True, note="quantised to V/div / 25"),
        Command(":CHANnel<n>:SCALe", "U1K p.14", True, note="plain decimals only"),
        Command(":CHANnel<n>:VERNier", "U1K p.15", True),
        Command(":TIMebase:SCALe", "U1K p.16", True),
        Command(":TRIGger:MODE", "U1K p.36", True),
        Command(":TRIGger:SWEep", "U1K p.36", True, note="SINGle arms; AUTO restarts; NORMal not used"),
        Command(":TRIGger:FORCe", "U1K p.36", True, query=False, note="only from status READY"),
        Command(":TRIGger:STATus?", "U1K p.37", True),
        Command(":TRIGger:LEVel", "U1K p.37", True),
        Command(":TRIGger:SOURce", "U1K p.38", True),
        Command(":TRIGger:EDGE:SLOPe", "U1K p.39", True),
        Command(":WAVeform:MODE", "U1K p.69", True),
        Command(":WAVeform:FORMat", "U1K p.69", True),
        Command(":WAVeform:SOURce", "U1K p.70", True),
        Command(":WAVeform:DATA?", "U1K p.70", True, query=False, note="only from a stopped record"),
        Command(":WAVeform:PREamble?", "U1K p.71", True),
    )

    def __init__(self, transport_factory: Callable[[str, str], Transport] | None = None, *,
                 min_gap_s: float = 0.1, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.perf_counter, user_tables: Path | None = None):
        self._factory = transport_factory or (lambda resource, backend: VisaTransport(resource, backend))
        self.min_gap_s = float(min_gap_s)
        self._sleep, self._clock = sleep, clock
        self._user_tables = user_tables
        self.t: Transport | None = None
        self.alignment_epoch = 0
        self.dead = False
        self.warnings: list[str] = []           # for the user; drained by the session
        self.stats = dict(queries=0, empty_retries=0, reply_errors=0, out_of_step=0, resyncs=0,
                          set_retries=0, forced_triggers=0, empty_blocks=0, rearms=0, stale_records=0)
        self.idn_text = ""
        self.model = self.firmware = ""
        self.tables: step_tables.StepTables = step_tables.FALLBACK
        self.tables_exact = False
        self.tb: float | None = None
        self.vdiv: dict[int, float] = {}
        self.probe: dict[int, float] = {}
        self.offset_v: dict[int, float] = {}    # channel offset in volts at the input, as last set
        self._saved: dict | None = None         # the user's setup, see save_setup()
        self.panel_locked = False
        self.last_timeline: list = []
        self._gap_until = 0.0
        self._last_set_t = 0.0
        self._run_t = 0.0                       # when sweep AUTO was last sent (free_run)
        self.caps = self._make_caps()

    # ------------------------------------------------------------------ helpers
    def _make_caps(self) -> DigitizerCaps:
        m = re.match(r"UPO1(\d\d)(\d)", self.model or "")
        bw = int(m.group(1)) * 10e6 if m else 50e6
        channels = int(m.group(2)) if m else 4
        tb = self.tables.timebase
        return DigitizerCaps(
            model=self.model or "UPO1000", channels=channels, bandwidth_hz=bw, max_sample_rate=1e9,
            vdiv_steps=self.usable_vdiv(), timebase_steps=tb,
            # auto-range aims at the 8 screen divisions; the data reach 10.1, which is headroom
            vertical_divs=self.SCREEN_VDIVS, horizontal_divs=float(self.HDIV),
            has_builtin_amplitude=False, has_builtin_phase=False,
            min_hz=5.0 / (self.HDIV * max(tb)), max_hz=bw, data_vertical_divs=self.DATA_VDIVS,
            running_avoid_timebases=self.RUNNING_BUSY_TB)

    def usable_vdiv(self) -> tuple[float, ...]:
        return tuple(s for s in self.tables.vdiv
                     if not any(scpi.close(s, bad, rel=1e-3) for bad in self.UNUSABLE_VDIV))

    @staticmethod
    def _chan(n: int) -> str:
        if n not in (1, 2, 3, 4):                 # U1K p.12: <n>: {1|2|3|4}
            raise DriverError(f"scope channel {n!r} does not exist")
        return f"CHANnel{n}"

    def _check_alive(self, cmd: str | None = None) -> None:
        if self.t is None:
            raise DriverError("scope is not open", cmd)
        if self.dead:
            raise InstrumentUnresponsive("the scope is not answering", cmd,
                                         getattr(self, "_dead_advice", UNRESPONSIVE_ADVICE))

    def _pace(self) -> None:
        wait = self._gap_until - self._clock()
        if wait > 0:
            self._sleep(wait)

    # ------------------------------------------------------------------ raw I/O
    def _ask_text(self, cmd: str) -> str:
        self._pace()
        self.t.write(cmd)
        raw = self.t.read()
        try:
            return raw.decode("ascii").strip()
        except UnicodeDecodeError:
            raise ReplyError(f"binary data in reply to {cmd!r}: {raw[:12]!r} ({len(raw)} bytes)", cmd)

    def _sentinel(self, after: str) -> None:
        # An EMPTY sentinel reply means 'busy', not 'out of step' (HW_REPORT.md 12.3)
        r = ""
        for _ in range(40):
            r = self._ask_text("*IDN?")                              # U1K p.5
            if r != "":
                break
            self.stats["empty_retries"] += 1
            self._sleep(0.05)
        try:
            V_IDN(r)
        except ReplyError:
            raise OutOfStep(f"sentinel after {after!r} answered {r[:40]!r}", after)

    def query(self, cmd: str, validate, empty_wait: float = 0.05, empty_tries: int = 40):
        """Validated, sentinel-checked query; one resync and one retry on an error.
        An empty reply with the sentinel in step means 'busy' and is simply retried."""
        self._check_alive(cmd)
        last: Exception | None = None
        for attempt in (1, 2):
            try:
                for _ in range(empty_tries):
                    self.stats["queries"] += 1
                    r = self._ask_text(cmd)
                    self._sentinel(cmd)
                    if r != "":
                        return validate(r)
                    self.stats["empty_retries"] += 1
                    self._sleep(empty_wait)
                raise ReplyError(f"only empty replies to {cmd!r}", cmd)
            except (ReplyError, OutOfStep, TransportError) as e:
                last = e
                self.stats["out_of_step" if isinstance(e, OutOfStep) else "reply_errors"] += 1
                log.warning("scope query %r failed (%s: %s)", cmd, type(e).__name__, e)
                if attempt == 1:
                    self.resync()
        if isinstance(last, DriverError):
            raise last
        raise DriverError(str(last), cmd)

    def write(self, cmd: str) -> None:
        """Write, then '*OPC?' (U1K p.5): back-to-back writes are dropped (HW_REPORT.md S3)."""
        self._check_alive(cmd)
        for pattern, why in _FORBIDDEN:
            if pattern.match(cmd.strip()):
                raise BlockedCommand(why, cmd)
        self._pace()
        try:
            self.t.write(cmd)
        except TransportError as e:
            log.warning("scope write %r failed (%s)", cmd, e)
            self.resync()
            try:
                self.t.write(cmd)
            except TransportError as e2:
                raise DriverError(str(e2), cmd)
        now = self._clock()
        if not cmd.startswith((":WAVeform", ":TRIGger:FORCe", ":TRIGger:SWEep SINGle", ":SYSTem:LOCK")):
            self._last_set_t = now              # see _settle_before_arm
        self.query("*OPC?", scpi.v_opc)
        if _SCALE_CMD.match(cmd):
            # condition from the 2026-10-06 freeze: nothing follows a timebase or V/div
            # change sooner than min_gap_s, on top of *OPC?
            self._gap_until = self._clock() + self.min_gap_s

    def set_verified(self, cmd: str, arg: str, validate, expect, timeout_s: float = 2.0,
                     tol_abs: float = 1e-12):
        """Write '<cmd> <arg>', then poll '<cmd>?' until it reads back as expected.
        One re-send. tol_abs: offset and trigger level are quantised to V/div / 25."""
        last = None
        for attempt in (1, 2):
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
            log.warning("scope set %s %s: read back %r, wanted %r (attempt %d)", cmd, arg, last, expect, attempt)
        raise SetError(f"{cmd} {arg}: read back {last!r}, wanted {expect!r}", f"{cmd} {arg}")

    # ------------------------------------------------------------------ resync / watchdog
    def resync(self, run_wait: float | None = None) -> None:
        """Bring replies back in step: sweep AUTO and wait (owed waveform replies only
        arrive once the scope has data again), device clear, then '*IDN?' / '*OPC?' /
        '*IDN?' clean three times running. Never ':RUN'.

        This is the only recovery level. If it fails the scope is marked dead and
        InstrumentUnresponsive is raised; the sweep engine does the rest."""
        if self.t is None:
            raise DriverError("scope is not open")
        self.stats["resyncs"] += 1
        self.alignment_epoch += 1               # a skew check from before this is not trusted (SPEC 8.6)
        self._gap_until = 0.0
        old_timeout = self.t.get_timeout()
        ok = False
        try:
            self.t.set_timeout(min(old_timeout, 1.5))
            try:
                self.t.write(":TRIGger:SWEep AUTO")                  # U1K p.36
            except TransportError as e:
                log.warning("scope resync: sweep AUTO not accepted (%s)", e)
                self._link_trouble()
            self._sleep(run_wait if run_wait is not None else max(0.5, 30 * (self.tb or 0.0)))
            self._clear()
            ok = self._sentinel_rounds()
        finally:
            try:
                self.t.set_timeout(old_timeout)
            except Exception:
                pass
        if not ok:
            self.dead = True
            log.error("scope resync failed: the scope is not answering")
            self._dead_advice = UNRESPONSIVE_ADVICE if self.t.present() else UNPLUGGED_ADVICE
            raise InstrumentUnresponsive("the scope does not answer after a resync", "*IDN?",
                                         self._dead_advice)
        log.info("scope resync ok")

    def _link_trouble(self) -> None:
        """A transfer failed during the resync: the scope may be frozen, and the rest of
        the resync can then take tens of seconds of timeouts. Tell the owner now."""
        if self.on_link_trouble is not None:
            try:
                self.on_link_trouble()
            except Exception as e:              # must not break the recovery
                log.warning("link-trouble handler failed: %s", e)

    def _clear(self) -> None:
        try:
            self.t.clear()
        except Exception as e:                  # reported; the sentinel decides
            log.warning("scope device clear failed: %s", e)
        self._sleep(0.2)

    def _sentinel_rounds(self, rounds: int = 8) -> bool:
        good = 0
        for _ in range(rounds):
            try:
                reads, ok = 0, False
                self.t.write("*IDN?")
                for _ in range(6):                                   # pop late replies
                    reads += 1
                    try:
                        V_IDN(self.t.read().decode("ascii", "replace").strip())
                        ok = True
                        break
                    except ReplyError:
                        continue
                if ok and reads == 1 and self._ask_text("*OPC?") == "1" and \
                        self._ask_text("*IDN?").startswith("UNI-T"):
                    good += 1
                else:
                    good = 0
            except TransportError:
                good = 0
                self._link_trouble()
                self._clear()                   # a failed transfer needs a clear
            if good >= 3:
                return True
        return False

    # ------------------------------------------------------------------ connection
    def open(self, resource: str, backend: str = "py") -> None:
        self.close()
        self.dead = False
        try:
            self.t = self._factory(resource, backend)
        except TransportError as e:
            raise DriverError(str(e), "open")
        self.resync(run_wait=0.3)               # also counts as the new alignment epoch
        self.idn_text = self.query("*IDN?", V_IDN)
        _, self.model, _, self.firmware = self.idn_text.split(",")
        found = step_tables.lookup(self.model, self.firmware, self._user_tables)
        self.tables, self.tables_exact = found.tables, found.exact
        if found.warning:
            log.warning(found.warning)
            self.warnings.append(found.warning)             # once per connection
        self.caps = self._make_caps()
        self.tb = self.query(":TIMebase:SCALe?", scpi.v_float)                      # U1K p.16
        self.set_verified(":WAVeform:MODE", "NORMal", V_WAVMODE, "NORMal")           # U1K p.69
        self.set_verified(":WAVeform:FORMat", "BYTE", V_WAVFMT, "BYTE")              # U1K p.69
        self.panel_locked = self.query(":SYSTem:LOCK?", scpi.v_bool)                 # U1K p.6

    def close(self) -> None:
        if self.t is None:
            return
        try:
            if not self.dead and self.panel_locked:
                self.lock_panel(False)          # never leave the keyboard locked
        except Exception as e:
            log.warning("could not unlock the scope's front panel on close: %s", e)
        try:
            self.t.close()
        finally:
            self.t = None

    def idn(self) -> str:
        return self.idn_text or self.query("*IDN?", V_IDN)

    def lock_panel(self, on: bool) -> None:
        """Front-panel keyboard lock (U1K p.6). Read-back 1 = locked: verified on the
        scope together with the user 2026-10-06; the manual's 'Return format' text says
        the opposite, its example agrees with the scope. The lock survives a closed USB
        session, so close() always releases it."""
        self.set_verified(":SYSTem:LOCK", "ON" if on else "OFF", scpi.v_bool, bool(on))
        self.panel_locked = bool(on)

    def error_queue(self) -> str:
        return self.query(":SYSTem:ERRor?", scpi.v_err)                               # U1K p.6

    # ------------------------------------------------------------------ settings
    def _pick(self, table, want: float, what: str) -> float:
        step = min(table, key=lambda s: abs(s - want))
        if not scpi.close(step, want, rel=1e-3):
            log.info("scope %s %g is not a step of this scope; using %g", what, want, step)
        return step

    def configure_channel(self, ch: int, coupling: str, probe_atten: float, bw_limit: bool,
                          offset_v: float) -> None:
        c = self._chan(ch)
        if coupling not in ("DC", "AC"):
            raise DriverError(f"unsupported coupling {coupling!r}", "configure_channel")
        self.probe[ch] = float(probe_atten) or 1.0
        saved = self._saved["channels"].setdefault(ch, {}) if self._saved is not None else None
        first = saved is not None and not saved
        if first:
            saved["display"] = self.query(f":{c}:DISPlay?", scpi.v_bool)
            saved["probe"] = self.query(f":{c}:PROBe?", scpi.v_float)
        self.set_verified(f":{c}:DISPlay", "1", scpi.v_bool, True)                    # U1K p.13
        # The scope's own probe ratio stays at 1X: waveform data are input-referred whatever
        # the ratio (HW_REPORT.md S2, 12.10), so the probe ratio is applied here in software.
        self.set_verified(f":{c}:PROBe", scpi.probe_ratio(1), scpi.v_float, 1.0)      # U1K p.14
        if first:
            # read at 1X, where the read-backs are input-referred (HW_REPORT.md S2)
            saved["vernier"] = self.query(f":{c}:VERNier?", scpi.v_bool)
            saved["scale"] = self.query(f":{c}:SCALe?", scpi.v_float)
            saved["offset"] = self.query(f":{c}:OFFSet?", scpi.v_float)
            saved["coupling"] = self.query(f":{c}:COUPling?", V_COUPLING)
            saved["bwl"] = self.query(f":{c}:BWLimit?", V_BWL)
        self.set_verified(f":{c}:VERNier", "0", scpi.v_bool, False)                   # U1K p.15
        self.set_verified(f":{c}:COUPling", coupling, V_COUPLING, coupling)           # U1K p.13
        bw = "20M" if bw_limit else "FULL"
        self.set_verified(f":{c}:BWLimit", bw, V_BWL, bw)                             # U1K p.12
        vd = self.query(f":{c}:SCALe?", scpi.v_float)                                 # U1K p.14
        self.vdiv[ch] = vd
        at_input = float(offset_v) / self.probe[ch]
        self.offset_v[ch] = self.set_verified(f":{c}:OFFSet", scpi.plain_decimal(at_input), scpi.v_float,
                                              at_input, tol_abs=vd / self.CODES_PER_DIV)   # U1K p.14

    def set_vdiv(self, ch: int, vdiv: float) -> float:
        step = self._pick(self.usable_vdiv(), vdiv, "V/div")
        self.vdiv[ch] = self.set_verified(f":{self._chan(ch)}:SCALe", scpi.plain_decimal(step),
                                          scpi.v_float, step)                         # U1K p.14
        # The scope keeps the offset in DIVISIONS when V/div changes (measured 2026-10-06,
        # HW_REPORT.md 13.6: -6.24 mV at 2 mV/div read back -3.12 mV at 1 mV/div). Put the
        # volts back, or a re-centred trace runs off the screen on the next range change.
        want = self.offset_v.get(ch, 0.0)
        if abs(want) > 0.0:
            self.set_offset(ch, want)
        return self.vdiv[ch]

    def set_offset(self, ch: int, offset_v: float) -> float:
        """Offset at the scope input, positive = trace up (HW_REPORT.md 12.14: +1 division
        of offset raised the trace by 25 codes). Quantised to V/div / 25."""
        vd = self.vdiv.get(ch) or self.query(f":{self._chan(ch)}:SCALe?", scpi.v_float)
        self.offset_v[ch] = self.set_verified(f":{self._chan(ch)}:OFFSet", scpi.plain_decimal(offset_v),
                                              scpi.v_float, float(offset_v),
                                              tol_abs=vd / self.CODES_PER_DIV)           # U1K p.14
        return self.offset_v[ch]

    def set_timebase(self, s_per_div: float) -> float:
        step = self._pick(self.tables.timebase, s_per_div, "timebase")
        self.tb = self.set_verified(":TIMebase:SCALe", scpi.plain_decimal(step), scpi.v_float, step)  # U1K p.16
        return self.tb

    def set_trigger_edge(self, ch: int, level_v: float = 0.0) -> None:
        src = self._chan(ch)
        self.set_verified(":TRIGger:MODE", "EDGE", V_TRIGMODE, "EDGE")                # U1K p.36
        self.set_verified(":TRIGger:SOURce", src, V_SRC, src)                         # U1K p.38
        self.set_verified(":TRIGger:EDGE:SLOPe", "POSitive", V_SLOPE, "POSitive")     # U1K p.39
        vd = self.vdiv.get(ch) or self.query(f":{src}:SCALe?", scpi.v_float)
        at_input = float(level_v) / self.probe.get(ch, 1.0)
        self.set_verified(":TRIGger:LEVel", scpi.plain_decimal(at_input), scpi.v_float, at_input,
                          tol_abs=vd / self.CODES_PER_DIV)                            # U1K p.37
        self.set_verified(":TRIGger:SWEep", "AUTO", V_SWEEP, "AUTO")                  # U1K p.36

    _TRIG_SAVED = (("mode", ":TRIGger:MODE", V_TRIGMODE), ("src", ":TRIGger:SOURce", V_SRC),
                   ("slope", ":TRIGger:EDGE:SLOPe", V_SLOPE), ("level", ":TRIGger:LEVel", scpi.v_float))

    def save_setup(self) -> None:
        """Remember the user's timebase and trigger now, and each channel's settings the
        first time configure_channel() touches it, for restore_setup(). The bench sweeps
        left the scope on whatever range the last point used (HW_REPORT.md 13.6)."""
        if self._saved is not None:
            return
        self._saved = dict(channels={}, timebase=self.query(":TIMebase:SCALe?", scpi.v_float),   # U1K p.16
                           trig={k: self.query(cmd + "?", v) for k, cmd, v in self._TRIG_SAVED})

    def restore_setup(self) -> list[str]:
        """Put back what save_setup() remembered. Every setting is tried; the ones that
        could not be restored are returned (and logged), nothing is raised for them.
        Probe ratio other than 1X (bench, HW_REPORT.md 13.12): SCALe and the trigger level
        take input-referred volts and report probe-scaled ones; OFFSet is not scaled."""
        saved, self._saved = self._saved, None
        bad: list[str] = []
        if saved is None:
            return bad

        def put(cmd, arg, validate, expect, **kw):
            try:
                self.set_verified(cmd, arg, validate, expect, **kw)
            except InstrumentUnresponsive:
                raise
            except DriverError as e:
                bad.append("%s: %s" % (cmd, e))

        for ch, s in saved["channels"].items():
            if len(s) < 7:                      # configure_channel failed half way
                continue
            c = ":" + self._chan(ch)
            step = s["scale"] / self.CODES_PER_DIV
            # the channel is on and at 1X here; SCALe is ignored on a channel that is
            # switched off (HW_REPORT.md 13.7), so DISPlay goes last
            put(c + ":VERNier", "1" if s["vernier"] else "0", scpi.v_bool, s["vernier"])       # U1K p.15
            put(c + ":SCALe", scpi.plain_decimal(s["scale"]), scpi.v_float, s["scale"])        # U1K p.14
            put(c + ":OFFSet", scpi.plain_decimal(s["offset"]), scpi.v_float, s["offset"], tol_abs=step)
            put(c + ":COUPling", s["coupling"], V_COUPLING, s["coupling"])                     # U1K p.13
            put(c + ":BWLimit", s["bwl"], V_BWL, s["bwl"])                                     # U1K p.12
            put(c + ":PROBe", scpi.probe_ratio(s["probe"]), scpi.v_float, s["probe"])          # U1K p.14
            put(c + ":DISPlay", "1" if s["display"] else "0", scpi.v_bool, s["display"])       # U1K p.13
            self.vdiv.pop(ch, None)
            self.offset_v.pop(ch, None)
        put(":TIMebase:SCALe", scpi.plain_decimal(saved["timebase"]), scpi.v_float, saved["timebase"])  # U1K p.16
        self.tb = self.query(":TIMebase:SCALe?", scpi.v_float)
        t = saved["trig"]
        put(":TRIGger:MODE", t["mode"], V_TRIGMODE, t["mode"])                                 # U1K p.36
        put(":TRIGger:SOURce", t["src"], V_SRC, t["src"])                                      # U1K p.38
        put(":TRIGger:EDGE:SLOPe", t["slope"], V_SLOPE, t["slope"])                            # U1K p.39
        # the level is sent input-referred and read back probe-scaled, for the source's ratio
        ratio, step = 1.0, abs(t["level"]) * 0.05 + 1e-9
        if t["src"].upper().startswith("CHAN"):
            try:
                ratio = self.query(f":{t['src']}:PROBe?", scpi.v_float) or 1.0                 # U1K p.14
                step = self.query(f":{t['src']}:SCALe?", scpi.v_float) / self.CODES_PER_DIV    # U1K p.14
            except DriverError as e:
                bad.append(":TRIGger:LEVel: %s" % e)
        put(":TRIGger:LEVel", scpi.plain_decimal(t["level"] / ratio), scpi.v_float, t["level"], tol_abs=step)  # U1K p.37
        for b in bad:
            log.warning("scope setting not restored: %s", b)
        return bad

    def status(self) -> str:
        return self.query(":TRIGger:STATus?", V_STATUS)                               # U1K p.37

    def free_run(self) -> None:
        """Leave the scope running for the user: sweep AUTO restarts a stopped scope
        (HW_REPORT.md 12.11, 12.13). Never ':RUN'."""
        self.set_verified(":TRIGger:SWEep", "AUTO", V_SWEEP, "AUTO")                  # U1K p.36
        self._run_t = self._clock()

    # ------------------------------------------------------------------ acquisition
    # Margins of one single-shot capture (HW_REPORT.md 12.4). Class attributes so the bench
    # script hwcheck/s7_capspeed.py can find out how far they can be shortened.
    ARM_QUIET_S = 0.3               # since the last setting change, before arming
    STOP_HOLD_S = 0.1               # STOP must hold this long before the record is read
    MIN_WAIT_EXTRA_S = 0.05         # on top of one screen, before the record is read
    STATUS_POLL_S = 0.01            # pause between two status polls

    def _settle_before_arm(self, quiet_s: float | None = None, timeout_s: float = 3.0) -> None:
        """A setting change makes the scope restart its acquisition (status ARMED); arming
        a single shot during that gives two arm cycles (HW_REPORT.md 12.4). Wait until
        quiet_s has passed since the last setting and the status is not ARMED."""
        quiet_s = self.ARM_QUIET_S if quiet_s is None else quiet_s
        t0 = self._clock()
        while True:
            if self._clock() - self._last_set_t >= quiet_s and self.status() != "ARMED":
                return
            if self._clock() - t0 > timeout_s:
                raise AcquireTimeout("the scope did not settle before arming", ":TRIGger:STATus?")
            self._sleep(0.02)

    def _fetch_channel(self, ch: int) -> Waveform:
        src = self._chan(ch)
        self.set_verified(":WAVeform:SOURce", src, V_SRC, src)                        # U1K p.70
        pre = self.query(":WAVeform:PREamble?", scpi.v_preamble)                      # U1K p.71
        self.stats["queries"] += 1
        self._pace()
        self.t.write(":WAVeform:DATA?")                                               # U1K p.70
        raw = self.t.read()
        if raw[:1] != b"#" or len(raw) < 4:
            self.stats["empty_blocks"] += 1
            raise EmptyBlock(f"CH{ch}: {raw[:16]!r} ({len(raw)} bytes), timebase {self.tb:g}, "
                             f"timeline {self.last_timeline}", ":WAVeform:DATA?")
        nd = int(raw[1:2])
        n = int(raw[2:2 + nd])
        need = 2 + nd + n
        while len(raw) < need:
            raw += self.t.read()
        self._sentinel(":WAVeform:DATA?")
        if n == 0:
            self.stats["empty_blocks"] += 1
            raise EmptyBlock(f"CH{ch}: zero-length block", ":WAVeform:DATA?")
        codes = np.frombuffer(raw[2 + nd:need], dtype=np.uint8).astype(np.float64)
        xinc, xor, yinc, yor, yref = pre[4], pre[5], pre[7], pre[8], pre[9]
        at_rail = (codes <= self.RAIL_LOW) | (codes >= self.RAIL_HIGH)
        volts = (codes - yref - yor) * yinc * self.probe.get(ch, 1.0)
        return Waveform(dt=xinc, t0=xor, volts=volts, clipped=bool(at_rail.any()),
                        rail_fraction=float(at_rail.mean()))

    def acquire(self, chans: list[int], timeout_s: float = 5.0) -> dict[int, Waveform]:
        """A single-shot acquisition whose record has the timebase that is set.

        Read too soon after STOP following a timebase change, the scope hands out the
        record of the PREVIOUS timebase (bench: 12 of 12 with no hold time, HW_REPORT.md
        13.20; probably the bad capture of 13.9). Such a record is thrown away and a new
        acquisition taken, without a resync: the link is in step, the record is just old."""
        for left in (2, 1, 0):
            waves = self._acquire(chans, timeout_s)
            text = self._stale(waves)
            if not text:
                return waves
            self.stats["stale_records"] += 1
            if left == 0:
                raise DriverError(text + ": stale record, three times running", "acquire")
            log.warning("%s: stale record, taking a new acquisition", text)
            self._sleep(max(self.STOP_HOLD_S, 0.1))
        raise AssertionError("unreachable")

    def _stale(self, waves: dict[int, Waveform]) -> str:
        """'' or what is wrong: a record whose time span is not the timebase that is set."""
        span = self.HDIV * self.tb
        for ch, w in waves.items():
            if abs(w.dt * w.volts.size - span) > 0.02 * span:
                return "scope record of CH%d spans %.3g s, the timebase set gives %.3g s" % (
                    ch, w.dt * w.volts.size, span)
        return ""

    # Read while running at these timebases, the scope goes busy for about 3.4 s now and
    # then (14 episodes in 500 pair reads at 200 ns/div; none in 300 at 100 ns/div and none
    # in 300 at 1 us/div; HW_REPORT.md 13.24, 13.27). 500 ns/div showed the same in sweeps.
    RUNNING_BUSY_TB = (2e-7, 5e-7)
    RUN_QUIET_S = 0.1               # since the last setting change, before a read from the running scope
    RUN_EMPTY_WAIT_S = 0.5          # after an empty reply of the running scope, before the next read

    def _wait_running(self, timeout_s: float) -> None:
        """Until the scope runs in sweep AUTO and shows a triggered record. A stopped scope
        is restarted with sweep AUTO and then left running for max(0.3 s, 30 x timebase):
        before that it has no record and ':WAVeform:DATA?' is answered empty (HW_REPORT.md
        S4). With no trigger (status AUTO) the read goes ahead after 1 s: the amplitude of
        an auto-triggered record is still right."""
        t0 = self._clock()
        restarted = False
        while True:
            st = self.status()
            now = self._clock()
            if st == "STOP" and not restarted:
                self.free_run()
                restarted = True
            elif now - self._last_set_t >= self.RUN_QUIET_S and \
                    now - self._run_t >= max(0.3, 30 * self.tb) and \
                    (st == "TRIGED" or (st == "AUTO" and now - t0 > max(1.0, 60 * self.tb))):
                return
            if now - t0 > timeout_s:
                raise AcquireTimeout(f"the scope does not show a record while running (status {st})",
                                     ":TRIGger:STATus?")
            self._sleep(self.STATUS_POLL_S)

    def acquire_running(self, chans: list[int], timeout_s: float = 5.0) -> dict[int, Waveform]:
        """The channels read one after the other from the scope while it keeps triggering,
        with no single shot and no stop: 0.21 s for two channels against 0.93 s (bench,
        HW_REPORT.md 13.21). Each channel is a DIFFERENT acquisition, each placed against its
        trigger with a scatter of about a tenth of a sample and not finer than about 0.8 ns,
        so the phase between the channels scatters; the gain does not. After an empty reply
        the link is checked with the sentinel and the read is taken again 0.5 s later; a
        resync only follows if the link is out of step."""
        self._check_alive("acquire_running")
        if self.tb is None:
            self.tb = self.query(":TIMebase:SCALe?", scpi.v_float)
        last: Exception | None = None
        for _ in range(6):
            try:
                self._wait_running(timeout_s)
                waves = {ch: self._fetch_channel(ch) for ch in chans}
            except (AcquireTimeout, InstrumentUnresponsive):
                raise
            except EmptyBlock as e:
                # A running scope now and then has no record to give for a moment (bench,
                # HW_REPORT.md 13.24: 14 times in 500 pair reads at 200 ns/div, status TRIGED
                # all along, the read 0.5 s later empty as well, the one after that good).
                # The link stays in step, so check that and wait; no resync, which would
                # take 2 s and end the validity of the skew check.
                last = e
                try:
                    self._sentinel(":WAVeform:DATA?")
                except (OutOfStep, ReplyError, TransportError) as bad:
                    log.warning("scope read while running: empty reply and %s; resync", bad)
                    self.resync()
                    continue
                log.warning("scope read while running: empty reply (%s); in step, reading again", e)
                self._sleep(self.RUN_EMPTY_WAIT_S)
                continue
            except (ReplyError, OutOfStep, TransportError) as e:
                last = e
                log.warning("scope read while running failed (%s: %s); resync, then a new read",
                            type(e).__name__, e)
                self.resync()
                continue
            text = self._stale(waves)
            if not text:
                return waves
            self.stats["stale_records"] += 1
            last = DriverError(text + ": stale record", "acquire_running")
            log.warning("%s: stale record, reading again", text)
            self._sleep(0.1)
        if isinstance(last, DriverError):
            raise last
        raise DriverError(str(last), "acquire_running")

    def _acquire(self, chans: list[int], timeout_s: float = 5.0) -> dict[int, Waveform]:
        """One single-shot acquisition; every channel is read from that stopped record.

        ':TRIGger:SWEep SINGle' is itself the arm command. Completion is polled on
        ':TRIGger:STATus?': the read only starts once a status other than STOP has been
        seen after arming (a stale STOP is read first), STOP has then held for 0.1 s, and
        one screen plus 50 ms has passed. If the scope waits for a trigger too long,
        ':TRIGger:FORCe' is sent, but only from READY/WAIT. (HW_REPORT.md 12.4)"""
        self._check_alive("acquire")
        if self.tb is None:
            self.tb = self.query(":TIMebase:SCALe?", scpi.v_float)
        last: Exception | None = None
        for attempt in (1, 2):
            try:
                self._settle_before_arm()
                self.write(":TRIGger:SWEep SINGle")                                   # U1K p.36 (arms)
                t0 = self._clock()
                min_wait = self.HDIV * self.tb + self.MIN_WAIT_EXTRA_S
                force_wait = max(1.0, 60 * self.tb)
                forced, armed, rearmed = 0, False, False
                t_stop = t_ready = None
                seen: list[str] = []
                timeline = self.last_timeline = [(0.0, "cmd SINGle")]
                while True:
                    st = self.status()
                    el = self._clock() - t0
                    if not seen or seen[-1] != st:
                        seen.append(st)
                        timeline.append((round(el, 2), st))
                    armed = armed or st != "STOP"
                    t_stop = (t_stop if t_stop is not None else el) if st == "STOP" else None
                    if armed and t_stop is not None and el - t_stop >= self.STOP_HOLD_S and el >= min_wait:
                        break
                    if not armed and not rearmed and el > 1.5:
                        self.write(":TRIGger:SWEep SINGle")          # the arm command was not taken
                        rearmed = True
                        self.stats["rearms"] += 1
                    t_ready = (t_ready if t_ready is not None else el) if st in ("READY", "WAIT") else None
                    if t_ready is not None and el - t_ready > force_wait and forced < 3:
                        self.write(":TRIGger:FORCe")                                  # U1K p.36
                        forced += 1
                        t_ready = None
                        self.stats["forced_triggers"] += 1
                        timeline.append((round(self._clock() - t0, 2), "cmd FORCe"))
                    if el > timeout_s:
                        raise AcquireTimeout(f"acquisition not complete after {el:.1f} s, timeline {timeline}",
                                             ":TRIGger:STATus?")
                    self._sleep(self.STATUS_POLL_S)
                return {ch: self._fetch_channel(ch) for ch in chans}
            except AcquireTimeout:
                raise
            except InstrumentUnresponsive:
                raise
            except (EmptyBlock, ReplyError, OutOfStep, TransportError) as e:
                last = e
                log.warning("scope acquire failed (%s: %s); resync, then a new acquisition",
                            type(e).__name__, e)
                self.resync()
        if isinstance(last, DriverError):
            raise last
        raise DriverError(str(last), "acquire")
