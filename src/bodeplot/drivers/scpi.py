"""SCPI helpers shared by the real drivers: number formatting, reply validators, errors.

Ported from the bench I/O layer (hwcheck/iolayer.py), which was tested on the instruments
in Milestones 0b and 0c. Manual references used in the drivers:
  U1K = docs/Uni-T_UPO1000_Programming_Manual_0424.pdf   (page n of 99)
  UTG = docs/UTG900E Programming Manual V1.0.pdf         (page n of 41)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .base import DriverError

FLOAT_RE = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$")
ERR_RE = re.compile(r'^-?\d+,".*"$')


class ReplyError(DriverError):
    """A reply did not have the format its query must produce."""


class OutOfStep(DriverError):
    """The *IDN? sentinel after a query was not answered by an IDN string."""


class SetError(DriverError):
    """A setting did not read back as written."""


class EmptyBlock(DriverError):
    """:WAVeform:DATA? answered without a data block."""


class BlockedCommand(DriverError):
    """A command the driver must never send was refused before any I/O."""


class InstrumentUnresponsive(DriverError):
    """The instrument stopped answering and the resync did not bring it back.

    The sweep engine treats this as fatal for the connection: generator off, sweep
    stopped, partial data kept, the user is told what to do (SPEC.md section 13)."""

    def __init__(self, message: str, last_command: str | None = None, advice: str = ""):
        super().__init__(message, last_command)
        self.advice = advice


@dataclass(frozen=True)
class Command:
    """One documented command of a driver's COMMANDS table (SPEC.md section 9.1)."""
    text: str               # the long form printed in the manual, with <n> for the channel
    page: str               # manual page, e.g. "U1K p.16"
    verified: bool          # True = exercised on the real instrument (HW_REPORT.md)
    query: bool = True      # has a '?' form that the probe tool may send
    note: str = ""


# ------------------------------------------------------------------ formatters
def plain_decimal(x, max_decimals: int = 12) -> str:
    """1e-9 -> '0.000000001', 2e7 -> '20000000', 0.2 -> '0.2'. Never an exponent.

    The scope silently ignores ':CHANnel1:SCALe 2.000000e-01' (HW_REPORT.md S1). Both
    manuals' examples use plain decimals (U1K p.96, UTG p.12)."""
    x = float(x)
    if x != x or x in (float("inf"), float("-inf")):
        raise ValueError(f"not a finite number: {x!r}")
    s = f"{x:.{max_decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s


def probe_ratio(ratio) -> str:
    """U1K p.14 example ':CHAN1:PROB 10X'. A bare number is misread ('1' sets 10X:
    HW_REPORT.md S2), so the X is mandatory."""
    return plain_decimal(ratio) + "X"


# ------------------------------------------------------------------ validators
def enum(choices):
    ups = [c.upper() for c in choices]

    def check(r: str):
        u = r.upper()
        # the long form or any unambiguous leading part of it: the scope answers 'BYTE'
        # where the manual says 'BYT'
        hits = [c for c in ups if c == u or (len(u) >= 2 and c.startswith(u))]
        if len(hits) != 1:
            raise ReplyError(f"expected one of {list(choices)}, got {r!r}")
        return choices[ups.index(hits[0])]
    return check


def v_float(r: str) -> float:
    if not FLOAT_RE.match(r):
        raise ReplyError(f"expected a number, got {r!r}")
    return float(r)


def v_bool(r: str) -> bool:
    if r not in ("0", "1"):
        raise ReplyError(f"expected 0 or 1, got {r!r}")
    return r == "1"


def v_opc(r: str) -> bool:
    if r != "1":
        raise ReplyError(f"expected *OPC? reply '1', got {r!r}")
    return True


def v_err(r: str) -> str:
    if not ERR_RE.match(r):
        raise ReplyError(f"expected <number>,\"<text>\", got {r!r}")
    return r


def v_text(r: str) -> str:
    return r


def v_preamble(r: str) -> list[float]:
    f = [x.strip() for x in r.split(",")]
    if len(f) != 10 or not all(FLOAT_RE.match(x) for x in f):
        raise ReplyError(f"expected 10 numeric preamble fields, got {r!r}")
    return [float(x) for x in f]


def idn_validator(vendor: str, model_prefix: str):
    def check(r: str) -> str:
        f = r.split(",")
        if len(f) != 4 or f[0] != vendor or not f[1].startswith(model_prefix):
            raise ReplyError(f"expected a {model_prefix}xxx IDN string, got {r!r}")
        return r
    return check


def close(a: float, b: float, rel: float = 1e-4, absol: float = 1e-12) -> bool:
    return abs(a - b) <= max(rel * max(abs(a), abs(b)), absol)
