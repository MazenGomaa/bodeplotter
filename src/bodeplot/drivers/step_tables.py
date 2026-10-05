"""Timebase and V/div step tables, shipped as data keyed by model + firmware.

The driver never walks the scope's steps at connect: stepping through the timebase
table froze the UPO1054 on 2026-10-06 (HW_REPORT.md 12.13). The tables below were
measured on the bench in Milestone 0b (HW_REPORT.md 12.2). Every value is still verified
by read-back each time it is set.

A table walked later with the probe tool (`python -m bodeplot.tools.probe --walk-tables`)
is saved to `step_tables.json` in the settings folder and takes precedence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("bodeplot.drivers")


@dataclass(frozen=True)
class StepTables:
    timebase: tuple[float, ...]     # s/div, ascending
    vdiv: tuple[float, ...]         # V/div at the scope input (probe 1X), ascending
    source: str


# 1, 2, 5, 10, 25 (not 20), 50 ns, then 1-2-5 up to 20 ms. 50 ms/div and slower put the
# scope in SCAN mode, where no screen record exists (HW_REPORT.md S4d): not in the table.
_UPO1054_TB = (1e-9, 2e-9, 5e-9, 1e-8, 2.5e-8, 5e-8,
               1e-7, 2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5,
               1e-4, 2e-4, 5e-4, 1e-3, 2e-3, 5e-3, 1e-2, 2e-2)
# 500 uV to 20 V in 1-2-5 steps (15 steps)
_UPO1054_V = (5e-4, 1e-3, 2e-3, 5e-3, 1e-2, 2e-2, 5e-2, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0)

# (model, firmware) exactly as the two fields appear in *IDN?
SHIPPED: dict[tuple[str, str], StepTables] = {
    ("UPO1054", "1. 01. 0047"): StepTables(_UPO1054_TB, _UPO1054_V,
                                           "measured on the bench, Milestone 0b (HW_REPORT.md 12.2)"),
}
# Used for any other UPO1xxx model or firmware, with a warning.
FALLBACK = SHIPPED[("UPO1054", "1. 01. 0047")]
USER_FILE = "step_tables.json"


@dataclass(frozen=True)
class Lookup:
    tables: StepTables
    exact: bool             # False: no entry for this model + firmware, the fallback is used
    warning: str | None


def _key(model: str, firmware: str) -> str:
    return f"{model.strip()}|{firmware.strip()}"


def load_user(path: Path) -> dict[str, StepTables]:
    from ..io.settings import read_json
    out = {}
    for key, t in read_json(path).get("tables", {}).items():
        try:
            tb = tuple(sorted(float(x) for x in t["timebase"]))
            vd = tuple(sorted(float(x) for x in t["vdiv"]))
            if len(tb) >= 5 and len(vd) >= 5:
                out[key] = StepTables(tb, vd, str(t.get("source", "walked with the probe tool")))
        except (KeyError, TypeError, ValueError):
            log.warning("ignoring a damaged entry %r in %s", key, path)
    return out


def save_user(path: Path, model: str, firmware: str, timebase, vdiv, source: str) -> None:
    from ..io.settings import read_json, write_json
    data = read_json(path)
    data["schema_version"] = 1
    data.setdefault("tables", {})[_key(model, firmware)] = {
        "timebase": [float(x) for x in timebase], "vdiv": [float(x) for x in vdiv], "source": source}
    write_json(path, data)


def lookup(model: str, firmware: str, user_file: Path | None = None) -> Lookup:
    if user_file is not None:
        user = load_user(user_file).get(_key(model, firmware))
        if user is not None:
            return Lookup(user, True, None)
    shipped = SHIPPED.get((model.strip(), firmware.strip()))
    if shipped is not None:
        return Lookup(shipped, True, None)
    return Lookup(FALLBACK, False, (
        "No timebase and V/div step tables are stored for %s firmware %r. The tables measured on a "
        "UPO1054 with firmware '1. 01. 0047' are used; every value is still checked by read-back. To "
        "measure this scope's own tables, run: python -m bodeplot.tools.probe --walk-tables"
        % (model, firmware)))
