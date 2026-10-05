"""Model -> driver mapping by *IDN? pattern (SPEC.md section 6.3)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    kind: str                   # "source" | "digitizer"
    patterns: tuple[str, ...]   # all must appear in the IDN string
    driver: str                 # dotted "module:Class"
    label: str


# The real drivers arrive in Milestone 6; until then only their registry entries exist.
ENTRIES: tuple[Entry, ...] = (
    Entry("digitizer", ("UNI-T", "UPO1"), "bodeplot.drivers.uni_t_upo1002:UniTUPO1002", "UNI-T UPO1000 family"),
    Entry("source", ("UNI-T", "UTG9"), "bodeplot.drivers.uni_t_utg900e:UniTUTG900E", "UNI-T UTG900E family"),
    Entry("digitizer", ("MOCK", "UPO1SIM"), "bodeplot.drivers.mock:MockScope", "Simulated scope"),
    Entry("source", ("MOCK", "UTG9SIM"), "bodeplot.drivers.mock:MockSource", "Simulated generator"),
)


def match(idn: str, kind: str | None = None) -> Entry | None:
    for e in ENTRIES:
        if (kind is None or e.kind == kind) and all(p in idn for p in e.patterns):
            return e
    return None


def is_available(entry: Entry) -> bool:
    import importlib
    module, _, cls = entry.driver.partition(":")
    try:
        return hasattr(importlib.import_module(module), cls)
    except ImportError:
        return False
