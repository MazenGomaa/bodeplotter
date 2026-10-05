"""Open a real generator + scope session: find the instruments, pick their drivers.

Identification uses '*IDN?' only, which both manuals document (U1K p.5, UTG p.5). Nothing
else is sent to an instrument before its driver is known: an unknown query can hang the
generator (HW_REPORT.md G2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from . import registry, visa_util
from .base import DriverError
from .transport import TransportError, VisaTransport

log = logging.getLogger("bodeplot.drivers")


@dataclass
class Found:
    resource: str
    idn: str
    entry: registry.Entry | None


def identify(resource: str, backend: str, timeout_s: float = 2.0) -> str:
    """The raw *IDN? reply of one resource ('' when it does not answer)."""
    t = None
    try:
        t = VisaTransport(resource, backend, timeout_s)
        t.write("*IDN?")
        return t.read().decode("ascii", "replace").strip()
    except TransportError as e:
        log.info("no *IDN? reply from %s: %s", resource, e)
        return ""
    finally:
        if t is not None:
            t.close()


def scan(backend: str, only: tuple[str, ...] = ()) -> list[Found]:
    """*IDN? of every USB or LAN instrument resource (serial ports are never probed), or
    of just the resources named in `only`."""
    out = []
    for r in (only or visa_util.discover(backend)):
        if not (r.upper().endswith("INSTR") and r.upper().startswith(("USB", "TCPIP"))):
            continue
        idn = identify(r, backend)
        out.append(Found(r, idn, registry.match(idn) if idn else None))
    return out


def _pick(found: list[Found], kind: str, wanted: str) -> Found:
    if wanted:
        for f in found:
            if f.resource == wanted:
                if f.entry is None or f.entry.kind != kind:
                    raise DriverError("%s answered *IDN? with %r, which is not a supported %s."
                                      % (wanted, f.idn, "generator" if kind == "source" else "scope"))
                return f
        raise DriverError("%s was not found. Check the cable, and that the instrument uses the WinUSB "
                          "driver (Zadig) for the pyvisa-py backend." % wanted)
    hits = [f for f in found if f.entry is not None and f.entry.kind == kind
            and not f.entry.driver.startswith("bodeplot.drivers.mock")]
    what = "generator" if kind == "source" else "scope"
    if not hits:
        raise DriverError("No supported %s was found. Check the cable and power, and that the "
                          "instrument uses the WinUSB driver (Zadig) for the pyvisa-py backend." % what)
    if len(hits) > 1:
        raise DriverError("More than one %s was found (%s). Choose one in Connections."
                          % (what, ", ".join(f.resource for f in hits)))
    return hits[0]


def open_session(backend: str, source_resource: str = "", digitizer_resource: str = "",
                 scope_min_gap_s: float = 0.1):
    """Identify both instruments, build their drivers and open the session. Blank resource
    strings mean 'find the one supported instrument of that kind'."""
    from ..io.settings import config_dir
    from ..sweep.core import Session
    from .step_tables import USER_FILE

    want_src, want_dig = source_resource.strip(), digitizer_resource.strip()
    found = scan(backend, (want_src, want_dig) if want_src and want_dig else ())
    src_f = _pick(found, "source", want_src)
    dig_f = _pick(found, "digitizer", want_dig)
    source = registry.load(src_f.entry)()
    digitizer = registry.load(dig_f.entry)(min_gap_s=scope_min_gap_s, user_tables=config_dir() / USER_FILE)
    session = Session(source, digitizer, simulated=False)
    session.open(src_f.resource, dig_f.resource, backend)
    return session
