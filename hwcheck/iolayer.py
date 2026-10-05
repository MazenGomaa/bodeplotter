"""Milestone 0b I/O layer for the UPO1054 scope and UTG932E generator.

Manual references:
  U1K = docs/Uni-T_UPO1000_Programming_Manual_0424.pdf  (page n of 99)
  UTG = docs/UTG900E Programming Manual V1.0.pdf        (page n of 41)

What this layer guarantees (each point is exercised by t0b_iolayer.py):
  * numbers are sent the way the manuals' examples write them: plain decimals,
    never exponents; probe ratio with its X suffix
  * every setting is written, then read back and compared
  * every scope reply is checked against the format its query must return, and
    every scope query is followed by a *IDN? sentinel, so a reply that is one
    step late is detected instead of being used
  * on any reply error the scope is resynchronised: run, device clear, bounded
    flush, *IDN? sentinel
  * a waveform is only fetched after an acquisition is known to be complete
  * timebase and V/div are only ever set to steps the scope really has
  * the generator never receives a command that is not in its manual, and a
    timeout is answered with device clear plus one retry
"""
import re
import time

import pyvisa

FLOAT_RE = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$")
INT_RE = re.compile(r"^[+-]?\d+$")
ERR_RE = re.compile(r'^-?\d+,".*"$')


class IOErrorBase(Exception):
    pass


class ReplyError(IOErrorBase):
    """A reply did not have the format its query must produce."""


class OutOfStep(IOErrorBase):
    """The *IDN? sentinel after a query was not answered by an IDN string."""


class SetError(IOErrorBase):
    """A setting did not read back as written."""


class ResyncFailed(IOErrorBase):
    pass


class EmptyBlock(IOErrorBase):
    """:WAVeform:DATA? answered without a data block."""


class BlockedCommand(IOErrorBase):
    """A command that is not in the instrument's manual was refused before sending."""


# ------------------------------------------------------------------ formatters
def plain_decimal(x, max_decimals=12):
    """1e-9 -> '0.000000001', 2e7 -> '20000000', 0.2 -> '0.2'. Never an exponent.

    M0 finding S1: the scope silently ignores ':CHANnel1:SCALe 2.000000e-01'.
    Both manuals' examples use plain decimals (U1K p.96 'TIMebase:SCALe 0.005',
    UTG p.12 ':CHANnel1:BASE:FREQuency 2000').
    """
    x = float(x)
    if x != x or x in (float("inf"), float("-inf")):
        raise ValueError(f"not a finite number: {x!r}")
    s = f"{x:.{max_decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    assert "e" not in s.lower()
    return s


class ScopeFmt:
    num = staticmethod(plain_decimal)

    @staticmethod
    def probe(ratio):
        # U1K p.14 example ':CHAN1:PROB 10X'. M0 finding S2: a bare number is
        # misread ('1' sets 10X), so the X is mandatory.
        return plain_decimal(ratio) + "X"

    @staticmethod
    def channel(n):
        if n not in (1, 2, 3, 4):                 # U1K p.12: <n>: {1|2|3|4}
            raise ValueError(f"scope channel {n!r}")
        return f"CHANnel{n}"


class GenFmt:
    num = staticmethod(plain_decimal)

    @staticmethod
    def channel(n):
        if n not in (1, 2):                       # UTG p.9: n value 1, 2
            raise ValueError(f"generator channel {n!r}")
        return f"CHANnel{n}"


# ------------------------------------------------------------------ validators
def _enum(choices):
    ups = [c.upper() for c in choices]

    def check(r):
        u = r.upper()
        # accept the long form or any unambiguous leading part of it (the scope
        # answers 'BYTE', the manual says 'BYT'; both must pass)
        hits = [c for c in ups if c == u or (len(u) >= 2 and c.startswith(u))]
        if len(hits) != 1:
            raise ReplyError(f"expected one of {choices}, got {r!r}")
        return choices[ups.index(hits[0])]
    return check


def v_float(r):
    if not FLOAT_RE.match(r):
        raise ReplyError(f"expected a number, got {r!r}")
    return float(r)


def v_int(r):
    if not INT_RE.match(r):
        raise ReplyError(f"expected an integer, got {r!r}")
    return int(r)


def v_bool(r):
    if r not in ("0", "1"):
        raise ReplyError(f"expected 0 or 1, got {r!r}")
    return r == "1"


def v_opc(r):
    if r != "1":
        raise ReplyError(f"expected *OPC? reply '1', got {r!r}")
    return True


def v_err(r):
    if not ERR_RE.match(r):
        raise ReplyError(f"expected <number>,\"<text>\", got {r!r}")
    return r


def v_scope_idn(r):
    f = r.split(",")
    if len(f) != 4 or f[0] != "UNI-T Technologies" or not f[1].startswith("UPO1"):
        raise ReplyError(f"expected a UPO1xxx IDN string, got {r!r}")
    return r


def v_gen_idn(r):
    f = r.split(",")
    if len(f) != 4 or f[0] != "UNI-T Technologies" or not f[1].startswith("UTG9"):
        raise ReplyError(f"expected a UTG9xx IDN string, got {r!r}")
    return r


def v_preamble(r):
    f = [x.strip() for x in r.split(",")]
    if len(f) != 10 or not all(FLOAT_RE.match(x) for x in f):
        raise ReplyError(f"expected 10 numeric preamble fields, got {r!r}")
    return [float(x) for x in f]


V_COUPLING = _enum(["DC", "AC", "GND"])                      # U1K p.13
V_BWL = _enum(["20M", "FULL"])                               # U1K p.12
V_SWEEP = _enum(["AUTO", "NORMal", "SINGle"])                # U1K p.36
V_STATUS = _enum(["STOP", "ARMED", "READY", "TRIGED", "AUTO", "SCAN", "RESET",
                  "REPLAY", "WAIT"])                         # U1K p.37
V_TRIGMODE = _enum(["EDGE", "PULSe", "VIDeo", "SLOPe", "RUNT", "WINDow", "DELay",
                    "TIMeout", "DURation", "SHOLd", "NE", "PATTern"])   # U1K p.36
V_SLOPE = _enum(["POSitive", "NEGative", "ALTernation"])     # U1K p.39
V_ACQTYPE = _enum(["NORMal", "AVERage", "PEAKdetect", "HRESolution"])   # U1K p.65
V_WAVMODE = _enum(["NORMal", "RAW"])                         # U1K p.69
V_WAVFMT = _enum(["WORD", "BYTE", "ASCII"])                  # U1K p.69
V_TRIGSRC = _enum(["CHANnel1", "CHANnel2", "CHANnel3", "CHANnel4", "EXT", "ACLINE"])   # U1K p.38
V_WAVSRC = _enum(["CHANnel1", "CHANnel2", "CHANnel3", "CHANnel4", "MATH"])             # U1K p.70


def _close(a, b, rel=1e-4, absol=1e-12):
    return abs(a - b) <= max(rel * max(abs(a), abs(b)), absol)


def _open(rm, resource, timeout_ms):
    inst = rm.open_resource(resource)
    inst.timeout = timeout_ms
    inst.write_termination = "\n"       # both manuals: command ends with <NL>
    inst.read_termination = None        # scope: CR LF stripped by the layer; generator: no terminator
    return inst


def device_clear(dev):
    """USBTMC device clear for either backend. dev needs .rm .resource .inst.

    NI-VISA: inst.clear() (viClear). pyvisa-py 0.8.1 answers inst.clear() on a
    USB INSTR with VI_ERROR_NSUP_OPER (M0, dbg_gen_alive.py), so there the
    session is closed, INITIATE_CLEAR / CHECK_CLEAR_STATUS / clear-halt are sent
    with pyusb (usbclear.py), and the session is reopened.
    """
    try:
        dev.inst.clear()
        return "inst.clear()"
    except Exception as first:
        p = dev.resource.split("::")
        vid, pid = int(p[1], 0), int(p[2], 0)
        timeout = dev.inst.timeout
        try:
            dev.inst.close()
        except Exception:
            pass
        from usbclear import usbtmc_clear
        try:
            usbtmc_clear(vid, pid, verbose=False)
            how = f"pyusb INITIATE_CLEAR (backend clear: {getattr(first, 'abbreviation', type(first).__name__)})"
        finally:
            dev.inst = _open(dev.rm, dev.resource, timeout)
        return how


# ====================================================================== scope
class ScopeIO:
    IDN = "*IDN?"                       # U1K p.5
    OPC = "*OPC?"                       # U1K p.5
    HDIV = 14                           # U1K p.72: XORigin = -TimeScale*7
    PTS_PER_DIV = 50                    # U1K p.72: XINCrement = TimeScale/50
    CODES_PER_DIV = 25                  # U1K p.72: YINCrement = VerticalScale/25
    TB_TABLE_MAX = 0.02                 # do not walk into SCAN/roll timebases (M0 finding S4d)
    # NO_RUN. This layer never sends ':RUN'. Found in Milestone 0c (dbg0c_skew6.py,
    # 25 repetitions per case, 20 MHz on both channels): a ':RUN' sent after the
    # USB session has been (re)opened shifts CH2 against CH1 by 2, 4, 6 or 8 ns in
    # about half the cases (8/25, 13/25, 13/25, 15/25), and the shift stays until
    # the next such event. ':RUN' in a session that stays open: 0/25. Reopen plus
    # ':TRIGger:SWEep AUTO', device clear, *IDN? or WAVeform writes: 0/25 each.
    # No documented command was found that undoes a shift (dbg0c_skew7.py).
    # write() refuses ':RUN' so it cannot come back by accident.
    NO_RUN = True

    def __init__(self, rm, resource, timeout_ms=5000, log=None):
        self.rm, self.resource = rm, resource
        self.inst = rm.open_resource(resource)
        self.inst.timeout = timeout_ms
        self.inst.write_termination = "\n"      # U1K p.3: command ends with <NL>
        self.inst.read_termination = None       # replies end CR LF; stripped here
        self.log = log or (lambda *a: None)
        self.stats = dict(queries=0, empty_retries=0, reply_errors=0, out_of_step=0,
                          resyncs=0, set_retries=0, forced_triggers=0, empty_blocks=0)
        self._last_set_t = time.perf_counter()
        self.tb_steps, self.vdiv_steps = [], []
        self.tb = None                          # cached real timebase, s/div
        self.vdiv = {}                          # cached real V/div per channel
        self.idn = None

    # ---------------------------------------------------------------- raw I/O
    def _read(self):
        return self.inst.read_raw()

    def _ask_raw(self, cmd):
        self.inst.write(cmd)
        return self._read()

    def _ask_text(self, cmd):
        raw = self._ask_raw(cmd)
        try:
            return raw.decode("ascii").strip()
        except UnicodeDecodeError:
            raise ReplyError(f"binary data in reply to {cmd!r}: {raw[:12]!r} ({len(raw)} bytes)")

    def _sentinel(self, after):
        # An EMPTY sentinel reply means 'scope busy', not 'out of step' (t0b run
        # 7 on @py: three empty sentinels while stepping V/div, each followed by
        # an in-step resync). Retry it; only a non-empty wrong reply is OutOfStep.
        r = ""
        for _ in range(40):
            r = self._ask_text(self.IDN)
            if r != "":
                break
            self.stats["empty_retries"] += 1
            time.sleep(0.05)
        try:
            v_scope_idn(r)
        except ReplyError:
            raise OutOfStep(f"sentinel after {after!r} answered {r[:40]!r}")

    # ---------------------------------------------------------------- query
    def query(self, cmd, validate, empty_wait=0.05, empty_tries=40):
        """Validated, sentinel-checked query with one resync + retry on error.

        An EMPTY reply with the sentinel still in step means 'scope busy' (seen
        in dbg0b_probe.py 0.3 s after a timebase change); it is retried without
        a resync.
        """
        last = None
        for attempt in (1, 2):
            try:
                for _ in range(empty_tries):
                    self.stats["queries"] += 1
                    r = self._ask_text(cmd)
                    self._sentinel(cmd)
                    if r != "":
                        return validate(r)
                    self.stats["empty_retries"] += 1
                    time.sleep(empty_wait)
                raise ReplyError(f"only empty replies to {cmd!r}")
            except (ReplyError, OutOfStep, pyvisa.errors.VisaIOError) as e:
                last = e
                self.stats["out_of_step" if isinstance(e, OutOfStep) else "reply_errors"] += 1
                self.log(f"scope query {cmd!r} failed ({type(e).__name__}: {e}); resync")
                if attempt == 1:
                    self.resync()
        raise last

    def write(self, cmd):
        """Write, then *OPC? (U1K p.5). M0 finding S3: back-to-back writes are dropped."""
        if self.NO_RUN and cmd.strip().upper().lstrip(":") in ("RUN",):
            raise BlockedCommand("':RUN' is not sent by this layer: it can shift the channels against "
                                 "each other by whole samples (see ScopeIO.NO_RUN)")
        self.inst.write(cmd)
        if not cmd.startswith((":WAVeform", ":TRIGger:FORCe", ":TRIGger:SWEep SINGle")):
            self._last_set_t = time.perf_counter()      # see _settle_before_arm
        self.query(self.OPC, v_opc)

    # ---------------------------------------------------------------- resync
    def resync(self, run_wait=None):
        """Bring replies back in step.

        1. ':TRIGger:SWEep AUTO' and wait: replies owed for :WAVeform:DATA?
           queries that found no screen record are only produced once the scope
           has data again. NEVER ':RUN' (see NO_RUN below).
        2. device clear (viClear -> USBTMC INITIATE_CLEAR).
        3. flush the host read buffer (never a bare device read, see below).
        4. sentinel: *IDN? must be answered by an IDN string, then *OPC? by '1',
           then *IDN? by an IDN string again, three rounds in a row.
        5. if that fails: restart the USB device node and repeat step 4.
        """
        self.stats["resyncs"] += 1
        detail = {"clear": None, "flushed": 0, "sentinel_reads": []}
        try:
            self.inst.write(":TRIGger:SWEep AUTO")        # U1K p.36; restarts a stopped scope
        except Exception as e:
            detail["run_error"] = str(e)
        time.sleep(run_wait if run_wait is not None else max(0.5, 30 * (self.tb or 0.0)))
        try:
            detail["clear"] = device_clear(self)
        except Exception as e:
            detail["clear"] = f"{type(e).__name__}: {e}"
        time.sleep(0.2)
        # Flush = discard the HOST read buffer only. The first version of this
        # method flushed with bare device reads; under NI-VISA a bare read with
        # no query pending times out and every later read then fails with
        # VI_ERROR_INP_PROT_VIOL (t0b first run). Late device replies are
        # popped by the sentinel loop below instead, which always writes first.
        try:
            self.inst.flush(pyvisa.constants.BufferOperation.discard_read_buffer)
            detail["flushed"] = "host read buffer discarded"
        except Exception as e:
            detail["flushed"] = f"{type(e).__name__}: {e}"
        if self._sentinel_rounds(detail):
            self.last_resync = detail
            self.log(f"scope resync ok: {detail}")
            return detail
        # Level 2. Clear + sentinel cannot repair the 'one reply behind for ever'
        # state (M0 finding S5; under NI-VISA it shows as VI_ERROR_INP_PROT_VIOL
        # on every read, even in a new session). Restarting the USB device node
        # does (dbg0b_protviol.py), without a replug or power cycle.
        detail["device_restart"] = self._restart_device()
        detail["sentinel_reads"].append("restart")
        if self._sentinel_rounds(detail):
            self.stats["device_restarts"] = self.stats.get("device_restarts", 0) + 1
            self.last_resync = detail
            self.log(f"scope resync ok after device restart: {detail}")
            return detail
        self.last_resync = detail
        raise ResyncFailed(f"scope replies still out of step: {detail}")

    def _restart_device(self):
        """Windows only, needs an elevated process: close the session, restart
        the USB device node with pnputil, reopen. Changes no instrument setting."""
        import subprocess
        import sys
        if sys.platform != "win32":
            return "not available on this OS"
        p = self.resource.split("::")
        inst_id = f"USB\\VID_{int(p[1], 0):04X}&PID_{int(p[2], 0):04X}\\{p[3]}"
        timeout = self.inst.timeout
        try:
            self.inst.close()
        except Exception:
            pass
        r = subprocess.run(["pnputil", "/restart-device", inst_id], capture_output=True, text=True)
        time.sleep(4.0)
        last = None
        for _ in range(10):
            try:
                self.inst = self.rm.open_resource(self.resource)
                self.inst.timeout = timeout
                self.inst.write_termination = "\n"
                self.inst.read_termination = None
                return f"pnputil exit {r.returncode}: {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()}"
            except Exception as e:
                last = e
                time.sleep(1.0)
        raise ResyncFailed(f"could not reopen {self.resource} after device restart: {last}")

    def _sentinel_rounds(self, detail):
        good = 0
        for _ in range(12):
            try:
                reads = 0
                self.inst.write(self.IDN)
                ok = False
                for _ in range(6):                        # pop late replies
                    reads += 1
                    try:
                        v_scope_idn(self._read().decode("ascii", "replace").strip())
                        ok = True
                        break
                    except ReplyError:
                        continue
                detail["sentinel_reads"].append(reads)
                if ok and self._ask_text(self.OPC) == "1" and \
                        self._ask_text(self.IDN).startswith("UNI-T") and reads == 1:
                    good += 1
                else:
                    good = 0
            except pyvisa.errors.VisaIOError as e:
                detail.setdefault("visa_errors", []).append(e.abbreviation)
                good = 0
                try:                                      # a failed transfer needs a clear
                    device_clear(self)
                    time.sleep(0.2)
                except Exception:
                    pass
            if good >= 3:
                return True
        return False

    # ---------------------------------------------------------------- set + readback
    def set_verified(self, cmd, arg, validate, expect, timeout_s=2.0, tol_abs=1e-12):
        """Write '<cmd> <arg>', then poll '<cmd>?' until it validates and equals
        expect (float compared to 1e-4 relative, or tol_abs). Re-sends once if it
        never does. tol_abs exists because vertical offset and trigger level are
        quantised to one ADC code = V/div / 25 (found in t0b: 0.2 V offset at
        20 V/div reads back 0)."""
        last = None
        for attempt in (1, 2):
            self.write(f"{cmd} {arg}")
            if not cmd.startswith(":WAVeform"):     # readout selection does not restart acquisition
                self._last_set_t = time.perf_counter()
            t0 = time.perf_counter()
            while True:
                last = self.query(cmd + "?", validate)
                same = _close(last, expect, absol=tol_abs) if isinstance(expect, float) else last == expect
                if same:
                    return last
                if time.perf_counter() - t0 > timeout_s:
                    break
                time.sleep(0.05)
            self.stats["set_retries"] += 1
            self.log(f"scope set {cmd} {arg}: read back {last!r}, wanted {expect!r} (attempt {attempt})")
        raise SetError(f"{cmd} {arg}: read back {last!r}, wanted {expect!r}")

    # ---------------------------------------------------------------- connect
    def connect(self, build_tables=True):
        self.resync(run_wait=0.3)
        self.idn = self.query(self.IDN, v_scope_idn)
        self.tb = self.query(":TIMebase:SCALe?", v_float)           # U1K p.16
        self.set_verified(":WAVeform:MODE", "NORMal", V_WAVMODE, "NORMal")   # U1K p.69
        self.set_verified(":WAVeform:FORMat", "BYTE", V_WAVFMT, "BYTE")      # U1K p.69
        if build_tables:
            self.build_tables()
        return self.idn

    def build_tables(self, channel=1):
        """Walk the real steps with UP/DOWN (U1K p.16 and p.14) and cache them.
        The timebase walk stops at TB_TABLE_MAX. Restores both settings."""
        TB, V = ":TIMebase:SCALe", f":{ScopeFmt.channel(channel)}:SCALe"
        tb0, v0 = self.query(TB + "?", v_float), self.query(V + "?", v_float)
        vern = self.query(f":{ScopeFmt.channel(channel)}:VERNier?", v_bool)      # U1K p.15
        probe = self.query(f":{ScopeFmt.channel(channel)}:PROBe?", v_float)      # U1K p.14
        if vern or not _close(probe, 1.0):
            raise SetError("build_tables needs coarse V/div (VERNier 0) and probe 1X on the walk channel")

        def nudge(cmd, direction, cur, settle):
            """One UP/DOWN step. 'No change' only counts as the end of the range
            after three tries with growing waits, so a single dropped command
            cannot cut the table short."""
            for k in range(3):
                self.write(f"{cmd} {direction}")
                time.sleep(settle * (k + 1))
                nxt = self.query(cmd + "?", v_float)
                if not _close(nxt, cur):
                    return nxt
            return cur

        def walk(cmd, start, stop_at=None, settle=0.15):
            cur = self.set_verified(cmd, plain_decimal(start), v_float, float(start))
            for _ in range(60):
                nxt = nudge(cmd, "DOWN", cur, settle)
                if _close(nxt, cur):
                    break
                cur = nxt
            steps = [cur]
            for _ in range(80):
                if stop_at is not None and cur >= stop_at * 0.999:
                    break
                nxt = nudge(cmd, "UP", cur, settle)
                if _close(nxt, cur):
                    break
                cur = nxt
                steps.append(cur)
            return steps

        def check(name, steps, need_min, need_max):
            """Refuse an implausible table. In the swapped-probe run of
            s0b_dual.py the walk returned [0.005] (no timebase command took
            effect) and every later 'ceil' request silently became 5 ms/div."""
            ratios = [b / a for a, b in zip(steps, steps[1:])]
            ok = (len(steps) >= 10 and steps[0] <= need_min * 1.001 and steps[-1] >= need_max * 0.999
                  and all(1.9 <= r <= 2.6 for r in ratios))
            if not ok:
                raise SetError(f"{name} step table implausible: {[f'{s:g}' for s in steps]}")

        try:
            for attempt in (1, 2):
                try:
                    tb = walk(TB, 0.001, self.TB_TABLE_MAX)
                    check("timebase", tb, 1e-8, self.TB_TABLE_MAX)
                    vd = walk(V, 0.2, None, settle=0.25)
                    check("V/div", vd, 1e-3, 5.0)
                    self.tb_steps, self.vdiv_steps = tb, vd
                    break
                except SetError as e:
                    self.log(f"scope build_tables attempt {attempt}: {e}")
                    if attempt == 2:
                        raise
        finally:
            self.set_verified(TB, plain_decimal(tb0), v_float, tb0)
            self.set_verified(V, plain_decimal(v0), v_float, v0)
            self.tb = tb0
        return self.tb_steps, self.vdiv_steps

    # ---------------------------------------------------------------- settings
    def _pick(self, table, want, mode):
        if not table:
            raise SetError("step table not built")
        if mode == "exact":
            for s in table:
                if _close(s, want, rel=1e-3):
                    return s
            raise SetError(f"{want:g} is not a real step; steps are {[f'{s:g}' for s in table]}")
        if mode == "ceil":
            for s in table:
                if s >= want * (1 - 1e-6):
                    return s
            return table[-1]
        raise ValueError(mode)

    def set_timebase(self, s_per_div, mode="ceil"):
        step = self._pick(self.tb_steps, s_per_div, mode)
        self.tb = self.set_verified(":TIMebase:SCALe", ScopeFmt.num(step), v_float, step)   # U1K p.16
        return self.tb

    def set_vdiv(self, ch, v_per_div, mode="ceil"):
        step = self._pick(self.vdiv_steps, v_per_div, mode)
        c = ScopeFmt.channel(ch)
        self.vdiv[ch] = self.set_verified(f":{c}:SCALe", ScopeFmt.num(step), v_float, step)  # U1K p.14
        return self.vdiv[ch]

    def configure_channel(self, ch, coupling="DC", bw_limit=False, offset_v=0.0, display=True):
        c = ScopeFmt.channel(ch)
        self.set_verified(f":{c}:DISPlay", "1" if display else "0", v_bool, bool(display))   # U1K p.13
        # probe ratio is always forced to 1X: waveform data are input-referred
        # whatever the ratio (M0 finding S2), so attenuation belongs in software
        self.set_verified(f":{c}:PROBe", ScopeFmt.probe(1), v_float, 1.0)                    # U1K p.14
        self.set_verified(f":{c}:VERNier", "0", v_bool, False)                               # U1K p.15
        self.set_verified(f":{c}:COUPling", coupling, V_COUPLING, coupling)                  # U1K p.13
        bw = "20M" if bw_limit else "FULL"
        self.set_verified(f":{c}:BWLimit", bw, V_BWL, bw)                                    # U1K p.12
        vd = self.query(f":{c}:SCALe?", v_float)                                             # U1K p.14
        self.vdiv[ch] = vd
        self.set_verified(f":{c}:OFFSet", ScopeFmt.num(offset_v), v_float, float(offset_v),
                          tol_abs=vd / self.CODES_PER_DIV)                                   # U1K p.14

    def set_trigger_edge(self, ch, level_v=0.0, slope="POSitive", sweep="AUTO"):
        src = ScopeFmt.channel(ch)
        self.set_verified(":TRIGger:MODE", "EDGE", V_TRIGMODE, "EDGE")                       # U1K p.36
        self.set_verified(":TRIGger:SOURce", src, V_TRIGSRC, src)                            # U1K p.38
        self.set_verified(":TRIGger:EDGE:SLOPe", slope, V_SLOPE, slope)                      # U1K p.39
        vd = self.vdiv.get(ch) or self.query(f":{src}:SCALe?", v_float)
        self.set_verified(":TRIGger:LEVel", ScopeFmt.num(level_v), v_float, float(level_v),
                          tol_abs=vd / self.CODES_PER_DIV)                                   # U1K p.37
        self.set_verified(":TRIGger:SWEep", sweep, V_SWEEP, sweep)                           # U1K p.36

    def status(self):
        return self.query(":TRIGger:STATus?", V_STATUS)                                      # U1K p.37

    # ---------------------------------------------------------------- acquisition
    def _fetch_channel(self, ch):
        src = ScopeFmt.channel(ch)
        self.set_verified(":WAVeform:SOURce", src, V_WAVSRC, src)                            # U1K p.70
        pre = self.query(":WAVeform:PREamble?", v_preamble)                                  # U1K p.71
        self.stats["queries"] += 1
        raw = self._ask_raw(":WAVeform:DATA?")                                               # U1K p.70
        if raw[:1] != b"#" or len(raw) < 4:
            self.stats["empty_blocks"] += 1
            raise EmptyBlock(f"CH{ch}: {raw[:16]!r} ({len(raw)} bytes), tb {self.tb:g}, "
                             f"timeline {getattr(self, 'last_timeline', None)}")
        nd = int(raw[1:2])
        n = int(raw[2:2 + nd])
        need = 2 + nd + n
        while len(raw) < need:
            raw += self._read()
        self._sentinel(":WAVeform:DATA?")
        if n == 0:
            self.stats["empty_blocks"] += 1
            raise EmptyBlock(f"CH{ch}: zero-length block")
        codes = list(raw[2 + nd:need])
        xinc, xor, yinc, yor, yref = pre[4], pre[5], pre[7], pre[8], pre[9]
        return dict(dt=xinc, t0=xor, yinc=yinc, yor=yor, yref=yref, codes=codes,
                    volts=[(c - yref - yor) * yinc for c in codes],      # M0: sign of YOR verified
                    clipped=(min(codes) <= 0 or max(codes) >= 255))

    def acquire(self, chans, timeout_s=5.0, force_after_s=None):
        """One single-shot acquisition, then every requested channel is read
        from that same stopped record.

        Arming: ':TRIGger:SWEep SINGle' (U1K p.36) is itself the arm command.
        No ':RUN' may follow it: a ':RUN' sent after the single shot has armed
        cancels single mode and the scope free-runs in AUTO (dbg0b_single.py,
        sequences C and D2). The manual does not say this.

        Completion is polled on ':TRIGger:STATus?' (U1K p.37). The fetch only
        starts once a status other than STOP has been seen after arming, and
        then STOP twice in a row, and at least one screen (14 div) plus 50 ms
        has passed. A STOP left over from the previous shot therefore cannot be
        taken for this one. If the scope is still waiting for a trigger after
        force_after_s, the documented ':TRIGger:FORCe' is sent, but only from a
        waiting state: forcing while the status still read AUTO left the scope
        in AUTO (t0b run 4).

        An EmptyBlock is never retried in place (M0 finding S4/S5): the layer
        resyncs and takes a completely new acquisition, once.
        """
        if self.tb is None:
            self.tb = self.query(":TIMebase:SCALe?", v_float)
        last = None
        for attempt in (1, 2):
            try:
                self._settle_before_arm()
                self.write(":TRIGger:SWEep SINGle")                      # U1K p.36 (arms)
                t0 = time.perf_counter()
                min_wait = self.HDIV * self.tb + 0.05
                force_wait = force_after_s if force_after_s is not None else max(1.0, 60 * self.tb)
                seen, forced, armed, rearmed = [], 0, False, False
                t_stop = t_ready = None
                timeline = self.last_timeline = [(0.0, "cmd SINGle")]
                while True:
                    st = self.status()
                    el = time.perf_counter() - t0
                    if not seen or seen[-1] != st:
                        seen.append(st)
                        timeline.append((round(el, 2), st))
                    armed = armed or st != "STOP"
                    # STOP must hold for 0.1 s: in t0b run 7 a forced shot read STOP
                    # for 20 ms and then re-armed (a V/div change just before arming
                    # had the scope restarting its acquisition)
                    t_stop = (t_stop if t_stop is not None else el) if st == "STOP" else None
                    if armed and t_stop is not None and el - t_stop >= 0.1 and el >= min_wait:
                        break
                    if not armed and not rearmed and el > 1.5:
                        # status never left STOP: the arm command was not taken
                        self.write(":TRIGger:SWEep SINGle")
                        rearmed = True
                        self.stats["rearms"] = self.stats.get("rearms", 0) + 1
                    # force only after force_wait seconds spent continuously READY
                    t_ready = (t_ready if t_ready is not None else el) if st in ("READY", "WAIT") else None
                    if t_ready is not None and el - t_ready > force_wait and forced < 3:
                        self.write(":TRIGger:FORCe")                     # U1K p.36
                        forced += 1
                        t_ready = None
                        self.stats["forced_triggers"] += 1
                        timeline.append((round(time.perf_counter() - t0, 2), "cmd FORCe"))
                    if el > timeout_s:
                        raise IOErrorBase(f"acquisition not complete after {el:.1f}s, timeline {timeline}")
                    time.sleep(0.01)
                wait_s = time.perf_counter() - t0
                waves = {ch: self._fetch_channel(ch) for ch in chans}
                return dict(waves=waves, states=seen, wait_s=wait_s, forced=forced,
                            attempts=attempt, total_s=time.perf_counter() - t0)
            except (EmptyBlock, ReplyError, OutOfStep, pyvisa.errors.VisaIOError) as e:
                last = e
                self.log(f"scope acquire failed ({type(e).__name__}: {e}); resync, new acquisition")
                self.resync()
        raise last

    def _settle_before_arm(self, quiet_s=0.3, timeout_s=3.0):
        """A setting change makes the scope restart its acquisition (status
        ARMED). Arming a single shot during that restart gives two arm cycles
        (t0b run 7). So wait until quiet_s has passed since the last setting was
        written and the status is no longer ARMED."""
        t0 = time.perf_counter()
        while True:
            since = time.perf_counter() - self._last_set_t
            if since >= quiet_s and self.status() != "ARMED":
                return
            if time.perf_counter() - t0 > timeout_s:
                raise IOErrorBase("scope did not settle before arming")
            time.sleep(0.02)

    def free_run(self):
        # Sweep AUTO alone restarts a scope stopped after a single shot (status
        # TRIGED 0.8 s later, 50 of 50 in dbg0c_skew6). No ':RUN': see NO_RUN.
        self.set_verified(":TRIGger:SWEep", "AUTO", V_SWEEP, "AUTO")

    def error_queue(self):
        return self.query(":SYSTem:ERRor?", v_err)                       # U1K p.6

    def close(self):
        self.inst.close()


# ================================================================== generator
class GenIO:
    """UTG900E-family generator.

    Only the commands below are ever sent. They are the exact long forms printed
    in the UTG manual. Anything else raises BlockedCommand BEFORE any I/O, because
    an unknown query can leave this generator deaf to all commands (M0 finding
    G2: '*OPC?', which is not in its manual).
    """
    _CH = r":CHANnel[12]"
    _NUM = r"-?\d+(\.\d+)?"
    ALLOWED = [re.compile(p) for p in (
        r"^\*IDN\?$",                                                    # UTG p.5
        rf"^{_CH}:OUTPut( (ON|OFF)|\?)$",                                # UTG p.9
        rf"^{_CH}:LOAD( {_NUM}|\?)$",                                    # UTG p.11
        rf"^{_CH}:AMPLitude:UNIT( (VPP|VRMS|DBM)|\?)$",                  # UTG p.11
        rf"^{_CH}:BASE:WAVe( (SINe|SQUare|PULSe|RAMP|ARB|NOISe|DC)|\?)$",  # UTG p.11
        rf"^{_CH}:BASE:FREQuency( {_NUM}|\?)$",                          # UTG p.12
        rf"^{_CH}:BASE:PHASe( {_NUM}|\?)$",                              # UTG p.12
        rf"^{_CH}:BASE:AMPLitude( {_NUM}|\?)$",                          # UTG p.13
        rf"^{_CH}:BASE:OFFSet( {_NUM}|\?)$",                             # UTG p.13
        rf"^{_CH}:MODe\?$",                                              # UTG p.15-16 (query only)
        r"^:SYSTem:LOCK\?$",                                             # UTG p.5 (query only)
    )]
    V_WAVE = staticmethod(_enum(["SINe", "SQUare", "PULSe", "RAMP", "ARB", "NOISe", "DC"]))
    V_UNIT = staticmethod(_enum(["VPP", "VRMS", "DBM"]))

    def __init__(self, rm, resource, timeout_ms=3000, write_delay_s=0.05, log=None):
        self.rm, self.resource = rm, resource
        self.inst = rm.open_resource(resource)
        self.inst.timeout = timeout_ms
        self.inst.write_termination = "\n"      # UTG p.3
        self.inst.read_termination = None       # M0 finding G1: replies carry no terminator
        self.write_delay_s = write_delay_s      # pacing instead of *OPC?
        self.log = log or (lambda *a: None)
        self.stats = dict(queries=0, blocked=0, timeouts=0, clears=0, retries=0, set_retries=0)
        self.inject_timeout_once = False        # test hook, see t0b_iolayer.py
        self.idn = None

    def _check(self, cmd):
        if not any(p.match(cmd) for p in self.ALLOWED):
            self.stats["blocked"] += 1
            raise BlockedCommand(f"not sent, not in the UTG manual command list: {cmd!r}")

    def _clear(self):
        self.stats["clears"] += 1
        self.last_clear = device_clear(self)    # USBTMC INITIATE_CLEAR on either backend
        time.sleep(0.3)

    def write(self, cmd):
        self._check(cmd)
        self.inst.write(cmd)
        time.sleep(self.write_delay_s)

    def query(self, cmd, validate):
        """Timeout -> device clear -> one retry. A reply of the wrong format gets
        the same treatment."""
        self._check(cmd)
        last = None
        for attempt in (1, 2):
            self.stats["queries"] += 1
            old = self.inst.timeout
            try:
                if self.inject_timeout_once:
                    # fault injection: read with NO query sent, so the read really
                    # times out (a zero timeout did not: the reply was already there)
                    self.inject_timeout_once = False
                    self.inst.timeout = 300
                else:
                    self.inst.write(cmd)
                raw = self.inst.read_raw()
                return validate(raw.decode("ascii", "replace").strip())
            except pyvisa.errors.VisaIOError as e:
                last = e
                self.stats["timeouts"] += 1
                self.log(f"gen query {cmd!r}: {e}; device clear, retry={attempt == 1}")
            except ReplyError as e:
                last = e
                self.log(f"gen query {cmd!r}: {e}; device clear, retry={attempt == 1}")
            finally:
                self.inst.timeout = old
            self._clear()
            if attempt == 1:
                self.stats["retries"] += 1
        raise last

    def set_verified(self, cmd, arg, validate, expect, timeout_s=2.0, tol_abs=1e-12):
        last = None
        for attempt in (1, 2):
            self.write(f"{cmd} {arg}")
            t0 = time.perf_counter()
            while True:
                last = self.query(cmd + "?", validate)
                same = _close(last, expect, absol=tol_abs) if isinstance(expect, float) else last == expect
                if same:
                    return last
                if time.perf_counter() - t0 > timeout_s:
                    break
                time.sleep(0.05)
            self.stats["set_retries"] += 1
        raise SetError(f"gen {cmd} {arg}: read back {last!r}, wanted {expect!r}")

    def connect(self):
        self.idn = self.query("*IDN?", v_gen_idn)
        return self.idn

    def output(self, ch, on=None):
        c = GenFmt.channel(ch)
        if on is None:
            return self.query(f":{c}:OUTPut?", v_bool)
        return self.set_verified(f":{c}:OUTPut", "ON" if on else "OFF", v_bool, bool(on))    # UTG p.9

    def configure_sine(self, ch, freq_hz, amp_vpp, offset_v=0.0, load="HIGHZ"):
        c = GenFmt.channel(ch)
        ohms = 10000.0 if str(load).upper() == "HIGHZ" else float(load)      # UTG p.11: 10000 = high resistance
        self.set_verified(f":{c}:BASE:WAVe", "SINe", self.V_WAVE, "SINe")                    # UTG p.11
        self.set_verified(f":{c}:LOAD", GenFmt.num(ohms), v_float, ohms)                     # UTG p.11
        self.set_verified(f":{c}:AMPLitude:UNIT", "VPP", self.V_UNIT, "VPP")                 # UTG p.11 (M0 G4)
        self.set_frequency(ch, freq_hz)
        self.set_verified(f":{c}:BASE:AMPLitude", GenFmt.num(amp_vpp), v_float, float(amp_vpp))  # UTG p.13
        self.set_verified(f":{c}:BASE:OFFSet", GenFmt.num(offset_v), v_float, float(offset_v))   # UTG p.13

    def set_frequency(self, ch, freq_hz):
        c = GenFmt.channel(ch)
        return self.set_verified(f":{c}:BASE:FREQuency", GenFmt.num(freq_hz), v_float, float(freq_hz))  # UTG p.12

    def safe_off(self):
        """All outputs off. Never raises."""
        ok = True
        for ch in (1, 2):
            try:
                self.inst.write(f":CHANnel{ch}:OUTPut OFF")              # UTG p.9
                time.sleep(self.write_delay_s)
            except Exception:
                ok = False
        return ok

    def close(self):
        self.inst.close()
