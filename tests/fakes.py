"""Simulated instruments at the SCPI level, for testing the real drivers without hardware.

FakeScope and FakeGen are Transports. They reproduce the behaviour HW_REPORT.md records
for the UPO1054 and the UTG932E, including the faults the drivers must survive:
plain-decimal-only numbers, dropped back-to-back writes, the stale STOP after arming,
empty waveform blocks, replies one step late, 'busy' empty replies, a generator that goes
deaf after an unknown query, and an instrument that stops answering altogether.

Time is virtual: the drivers get FakeClock.sleep / FakeClock.now, so tests run instantly
and timing rules (pacing, arm sequence) can be asserted exactly.
"""
from __future__ import annotations

import math
import re
from collections import deque

import numpy as np

from bodeplot.drivers.step_tables import FALLBACK
from bodeplot.drivers.transport import Transport, TransportError

IO_TIME = 0.002         # virtual seconds one write or read takes


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += max(0.0, seconds)


def _plain(arg: str) -> float | None:
    """The scope only takes plain decimals; anything else is silently ignored."""
    return float(arg) if re.fullmatch(r"-?\d+(\.\d+)?", arg) else None


class FakeGen(Transport):
    IDN = "UNI-T Technologies,UTG900E,SIM0002,1.09"

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.replies: deque[bytes] = deque()
        self.log: list[tuple[float, str]] = []
        self.ch = {n: dict(output=False, load=50.0, unit="VRMS", wave="SQUare", freq=1000.0, amp=0.1,
                           offset=0.0, phase=0.0) for n in (1, 2)}
        self.hung = False               # deaf after an unknown query, until a clear
        self.dead = False               # writes fail (cable pulled)
        self.drop_replies = 0           # test hook: this many replies are lost (timeouts)
        self.clears = 0
        self.timeout = 3.0
        self.closed = False

    # ---- Transport
    def write(self, cmd: str) -> None:
        self.clock.sleep(IO_TIME)
        if self.dead:
            raise TransportError("write: [Errno 10060] Operation timed out")
        self.log.append((self.clock.now(), cmd))
        if self.hung:
            return
        reply = self._handle(cmd)
        if reply is not None:
            if self.drop_replies > 0:
                self.drop_replies -= 1
            else:
                self.replies.append(reply.encode("ascii"))      # no terminator (HW_REPORT G1)

    def read(self) -> bytes:
        self.clock.sleep(IO_TIME)
        if self.dead or not self.replies:
            self.clock.sleep(self.timeout)
            raise TransportError("read: timeout")
        return self.replies.popleft()

    def clear(self) -> str:
        if self.dead:
            raise TransportError("clear: device not found")
        self.clears += 1
        self.replies.clear()
        self.hung = False
        return "fake clear"

    def set_timeout(self, seconds): self.timeout = seconds
    def get_timeout(self): return self.timeout
    def close(self): self.closed = True

    # ---- behaviour
    def _handle(self, cmd: str) -> str | None:
        if cmd == "*IDN?":
            return self.IDN
        if cmd == ":SYSTem:LOCK?":
            return "1"
        m = re.fullmatch(r":CHANnel([12]):([A-Za-z:]+)(\?| .+)?", cmd)
        if not m:
            if cmd.endswith("?"):
                self.hung = True        # '*OPC?' and friends (HW_REPORT G2)
            return None
        c, name, rest = self.ch[int(m.group(1))], m.group(2), m.group(3) or ""
        key = {"OUTPut": "output", "LOAD": "load", "AMPLitude:UNIT": "unit", "BASE:WAVe": "wave",
               "BASE:FREQuency": "freq", "BASE:AMPLitude": "amp", "BASE:OFFSet": "offset",
               "BASE:PHASe": "phase"}.get(name)
        if key is None:
            if rest == "?":
                self.hung = name != "MODe"
                return "CONTINUE" if name == "MODe" else None
            return None
        if rest == "?":
            v = c[key]
            if key == "output":
                return "1" if v else "0"
            return v if isinstance(v, str) else "%.6e" % v
        arg = rest.strip()
        if key == "output":
            c[key] = arg == "ON"
        elif key in ("unit", "wave"):
            c[key] = arg
        else:
            c[key] = float(arg)
        return None

    def sent(self) -> list[str]:
        return [c for _, c in self.log]


class FakeScope(Transport):
    IDN = "UNI-T Technologies,UPO1054,SIM0001,1. 01. 0047"
    TB_STEPS = FALLBACK.timebase
    V_STEPS = FALLBACK.vdiv

    def __init__(self, clock: FakeClock, idn: str | None = None, gen: FakeGen | None = None):
        self.clock = clock
        self.idn = idn or self.IDN
        self.gen = gen                  # when given, the signal comes from the generator's state
        self.replies: deque[bytes] = deque()
        self.log: list[tuple[float, str]] = []
        self.timebase = 1e-3
        self.sweep = "AUTO"
        self.lock = False
        self.wav = dict(src="CHANnel1", mode="RAW", fmt="WORD")
        self.trig = dict(mode="EDGE", src="CHANnel1", slope="POSitive", level=0.0)
        self.ch = {n: dict(scale=0.2, offset=0.0, probe=10.0, vernier=False, coupling="DC", bwl="FULL",
                           display=True) for n in (1, 2, 3, 4)}
        # acquisition state machine
        self.mode = "run"               # "run" | "single" | "stopped"
        self.t_mark = clock.now() - 10  # when the current run / arm cycle started
        self.was_stopped = False
        self.forced = False
        self.has_record = False
        # signal at the probe TIPS: channel -> (amplitude V peak, phase rad); frequency
        self.freq = 1000.0
        self.tips = {1: (0.5, 0.0), 2: (0.5, 0.0)}
        self.tip_dc = {1: 0.0, 2: 0.0}
        self.probe_hw = {1: 10.0, 2: 10.0, 3: 10.0, 4: 10.0}   # the probes actually fitted
        self.h = None                   # callable f -> complex: DUT between the two tips
        self.delay_ch2_s = 0.0          # channel skew
        self.noise_codes = 0.0
        self.rng = np.random.default_rng(1)
        # faults
        self.dead = False
        self.die_after_data_reads: int | None = None    # stop answering after this many waveform reads
        self.empty_next = 0             # 'busy': this many ordinary replies come back empty
        self.empty_blocks = 0           # this many :WAVeform:DATA? replies carry no block
        self.stray: bytes | None = None  # one extra reply ahead of the next one: out of step
        self.ignore_single = False      # the arm command is not taken
        self.trigger_present = True
        self.forbidden: list[str] = []  # ':RUN' etc. if a driver ever sends them
        self.clears = 0
        self.data_reads = 0
        self.timeout = 5.0
        self.closed = False
        self._last_was_write = False

    # ---- Transport
    def write(self, cmd: str) -> None:
        self.clock.sleep(IO_TIME)
        if self.dead:
            raise TransportError("write %r: [Errno 10060] Operation timed out" % cmd)
        self.log.append((self.clock.now(), cmd))
        is_query = "?" in cmd
        if not is_query and self._last_was_write:
            self._last_was_write = True
            return                      # a write straight after a write is dropped (HW_REPORT S3)
        self._last_was_write = not is_query
        reply = self._handle(cmd)
        if reply is None:
            return
        if self.stray is not None:
            self.replies.append(self.stray)
            self.stray = None
        self.replies.append(reply)

    def read(self) -> bytes:
        self.clock.sleep(IO_TIME)
        if self.dead or not self.replies:
            self.clock.sleep(self.timeout)
            raise TransportError("read: timeout")
        return self.replies.popleft()

    def clear(self) -> str:
        if self.dead:
            raise TransportError("clear: no response")
        self.clears += 1
        self.replies.clear()
        self.stray = None
        self._last_was_write = False
        return "fake clear"

    def set_timeout(self, seconds): self.timeout = seconds
    def get_timeout(self): return self.timeout
    def close(self): self.closed = True

    # ---- acquisition state machine (timings from HW_REPORT.md 12.4 and 12.13)
    def status(self) -> str:
        dt = self.clock.now() - self.t_mark
        if self.mode == "stopped":
            return "STOP"
        if self.mode == "single":
            if dt < 0.03 and self.was_stopped:
                return "STOP"           # stale
            if dt < 0.22:
                return "ARMED"
            if dt < 0.33:
                return "AUTO"
            if self.trigger_present or self.forced:
                self.mode, self.has_record, self.was_stopped = "stopped", True, True
                return "STOP"
            return "READY"
        if dt < 0.05 and self.was_stopped:
            return "STOP"
        if dt < 0.23:
            return "ARMED"
        if dt < 0.40:
            return "AUTO"
        self.was_stopped = False
        return "TRIGED" if self.trigger_present else "AUTO"

    def _restart_if_running(self):
        if self.mode == "run":          # a setting change restarts the acquisition
            self.t_mark = self.clock.now() - 0.06

    # ---- commands
    def _text(self, s: str, ordinary: bool = True) -> bytes:
        if ordinary and self.empty_next > 0:
            self.empty_next -= 1
            return b"\r\n"
        return s.encode("ascii") + b"\r\n"

    @staticmethod
    def _num(v: float) -> str:
        return "%.6e" % v

    def _handle(self, cmd: str) -> bytes | None:
        up = cmd.upper()
        if up in (":RUN", "RUN", "*RST", ":AUTO") or up.startswith((":CAL", ":SYSTEM:SETUP ")):
            self.forbidden.append(cmd)
            return None
        if cmd == "*IDN?":
            return self._text(self.idn, ordinary=False)
        if cmd == "*OPC?":
            return self._text("1", ordinary=False)
        if cmd == ":SYSTem:ERRor?":
            return self._text('0,"No error"')
        if cmd.startswith(":SYSTem:LOCK"):
            if cmd.endswith("?"):
                return self._text("1" if self.lock else "0")      # 1 = locked (verified on the scope)
            self.lock = cmd.split()[-1] in ("ON", "1")
            return None
        if cmd == ":STOP":
            self.status()
            self.has_record = self.mode == "stopped" or (self.mode == "run" and self.status() == "TRIGED")
            self.mode, self.was_stopped = "stopped", True
            return None
        if cmd.startswith(":TIMebase:SCALe"):
            return self._scale(cmd, "timebase")
        m = re.match(r":CHANnel([1-4]):(\w+)(\?| .+)?$", cmd)
        if m:
            return self._channel(int(m.group(1)), m.group(2), m.group(3) or "")
        if cmd.startswith(":TRIGger:"):
            return self._trigger(cmd)
        if cmd.startswith(":WAVeform:"):
            return self._waveform(cmd)
        return None                     # unknown: silently ignored, like the real scope

    def _scale(self, cmd: str, what: str, ch: int | None = None):
        table = self.TB_STEPS if what == "timebase" else self.V_STEPS
        cur = self.timebase if what == "timebase" else self.ch[ch]["scale"]
        if cmd.endswith("?"):
            return self._text(self._num(cur))
        arg = cmd.split()[-1]
        i = min(range(len(table)), key=lambda k: abs(table[k] - cur))
        if arg == "UP":
            new = table[min(i + 1, len(table) - 1)]
        elif arg == "DOWN":
            new = table[max(i - 1, 0)]
        else:
            v = _plain(arg)
            if v is None:
                return None             # exponent notation: ignored (HW_REPORT S1)
            if ch is not None and not self.ch[ch]["display"]:
                return None             # ignored on a channel that is off (HW_REPORT 13.7)
            below = [s for s in table if s <= v * (1 + 1e-9)]
            new = max(below) if below else table[0]
        if what == "timebase":
            self.timebase = new
        else:
            # the real scope keeps the offset in divisions (HW_REPORT 13.6)
            self.ch[ch]["offset"] *= new / self.ch[ch]["scale"]
            self.ch[ch]["scale"] = new
        self._restart_if_running()
        return None

    def _channel(self, n: int, name: str, rest: str):
        c = self.ch[n]
        if name == "SCALe":
            return self._scale(f":CHANnel{n}:SCALe{rest}", "vdiv", n)
        key = {"OFFSet": "offset", "PROBe": "probe", "VERNier": "vernier", "COUPling": "coupling",
               "BWLimit": "bwl", "DISPlay": "display"}.get(name)
        if key is None:
            return None
        if rest == "?":
            v = c[key]
            if isinstance(v, bool):
                return self._text("1" if v else "0")
            return self._text(v if isinstance(v, str) else self._num(v))
        arg = rest.strip()
        if key == "probe":
            # a bare number is misread: '1' sets 10X (HW_REPORT S2)
            c[key] = float(arg[:-1]) if arg.endswith("X") else 10.0
        elif key == "offset":
            v = _plain(arg)
            if v is not None:
                step = c["scale"] / 25.0
                c[key] = round(v / step) * step
        elif key in ("vernier", "display"):
            c[key] = arg in ("1", "ON")
        else:
            c[key] = arg
        self._restart_if_running()
        return None

    def _trigger(self, cmd: str):
        if cmd == ":TRIGger:STATus?":
            return self._text(self.status())
        if cmd == ":TRIGger:FORCe":
            if self.mode == "single" and self.status() == "READY":   # only works from READY
                self.forced = True
            return None
        name, _, arg = cmd.partition(" ")
        q = name.endswith("?")
        name = name.rstrip("?")
        if name == ":TRIGger:SWEep":
            if q:
                return self._text(self.sweep)
            if arg == "SINGle":
                if not self.ignore_single:
                    self.status()
                    self.sweep, self.mode, self.t_mark = "SINGle", "single", self.clock.now()
                    self.forced, self.has_record = False, False
            elif arg == "AUTO":
                self.status()
                if self.mode != "run":
                    self.mode, self.t_mark = "run", self.clock.now()
                self.sweep = "AUTO"
            return None                 # NORMal: never reads back as set (HW_REPORT 12.13)
        key = {":TRIGger:MODE": "mode", ":TRIGger:SOURce": "src", ":TRIGger:EDGE:SLOPe": "slope",
               ":TRIGger:LEVel": "level"}.get(name)
        if key is None:
            return None
        if q:
            v = self.trig[key]
            return self._text(v if isinstance(v, str) else self._num(v))
        if key == "level":
            v = _plain(arg)
            if v is not None:
                step = self.ch[int(self.trig["src"][-1])]["scale"] / 25.0
                self.trig[key] = round(v / step) * step
        else:
            self.trig[key] = arg
        return None

    def _waveform(self, cmd: str):
        name, _, arg = cmd.partition(" ")
        if name == ":WAVeform:DATA?":
            return self._data()
        if name == ":WAVeform:PREamble?":
            c = self.ch[int(self.wav["src"][-1])]
            yinc = c["scale"] / 25.0
            return self._text("0,0,1000,1,%.6e ,%.6e,0,%.6e ,%.6e ,128" % (
                self.timebase / 50.0, -7.0 * self.timebase, yinc, round(c["offset"] / yinc)))
        key = {":WAVeform:SOURce": "src", ":WAVeform:MODE": "mode", ":WAVeform:FORMat": "fmt"}.get(name.rstrip("?"))
        if key is None:
            return None
        if name.endswith("?"):
            return self._text(self.wav[key])
        self.wav[key] = arg
        return None

    def _signal(self, n: int):
        """(amplitude V peak, phase rad, dc) at the tip of channel n."""
        if self.gen is not None:
            g = self.gen.ch[1]
            if not g["output"]:
                return 0.0, 0.0, 0.0
            self.freq = g["freq"]
            amp = g["amp"] / 2.0
            if n == 1:
                return amp, 0.0, g["offset"]
            if n == 2:
                h = self.h(self.freq) if self.h else 1.0 + 0j
                return amp * abs(h), math.atan2(h.imag, h.real), g["offset"] * abs(self.h(1e-6) if self.h else 1.0)
            return 0.0, 0.0, 0.0
        a, ph = self.tips.get(n, (0.0, 0.0))
        return a, ph, self.tip_dc.get(n, 0.0)

    def codes(self, n: int) -> np.ndarray:
        c = self.ch[n]
        yinc = c["scale"] / 25.0
        dt = self.timebase / 50.0
        t = -7.0 * self.timebase + dt * np.arange(700)
        amp, ph, dc = self._signal(n)
        delay = self.delay_ch2_s if n == 2 else 0.0
        # edge trigger on CH1, rising through its level: CH1's zero crossing is at t = 0
        # same sign convention as drivers/mock.py: a positive delay advances CH2
        tip = amp * np.sin(2 * math.pi * self.freq * (t + delay) + ph) + (dc if c["coupling"] == "DC" else 0.0)
        v_in = tip / self.probe_hw[n]
        codes = np.rint(v_in / yinc + c["offset"] / yinc) + 128
        if self.noise_codes:
            codes = codes + np.rint(self.rng.normal(0.0, self.noise_codes, 700))
        # A trace whose middle is far off scale (DC) reads about 125 on the real scope, with
        # no rail code (HW_REPORT 13.6). An AC overdrive around the centre clips cleanly.
        if abs(float(np.mean(codes)) - 128.0) > 127 + 100:
            return np.full(700, 125, dtype=np.uint8)
        return np.clip(codes, 1, 254).astype(np.uint8)       # the real rails (HW_REPORT 12.14)

    def _data(self) -> bytes:
        self.data_reads += 1
        if self.die_after_data_reads is not None and self.data_reads > self.die_after_data_reads:
            self.dead = True
            return None
        if self.empty_blocks > 0 or not (self.mode == "stopped" and self.has_record):
            self.empty_blocks = max(0, self.empty_blocks - 1)
            return b"\r\n"              # no record: no block (HW_REPORT S4)
        body = self.codes(int(self.wav["src"][-1])).tobytes()
        return b"#3700" + body + b"\r\n"

    def sent(self) -> list[str]:
        return [c for _, c in self.log]
