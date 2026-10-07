"""Logging to a rotating file in the user log dir (SPEC.md section 13)."""
import logging
import logging.handlers
from pathlib import Path

from platformdirs import user_log_dir

APP = "bodeplot"
_cli_debug = False          # started with --debug: the setting cannot switch that off


def log_path() -> Path:
    return Path(user_log_dir(APP, appauthor=False)) / "bodeplot.log"


def setup_logging(debug: bool = False, to_file: bool = True) -> logging.Logger:
    global _cli_debug
    _cli_debug = bool(debug)
    root = logging.getLogger(APP)
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    if to_file:
        try:
            p = log_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            h = logging.handlers.RotatingFileHandler(p, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
            h.setFormatter(fmt)
            root.addHandler(h)
        except OSError:
            pass                            # a read-only log dir must not stop the app
    if debug:
        s = logging.StreamHandler()
        s.setFormatter(fmt)
        root.addHandler(s)
    return root


def set_debug(on: bool) -> None:
    """The 'debug logging' setting: every instrument command goes into the log file, as
    with --debug (which stays on whatever the setting says)."""
    logging.getLogger(APP).setLevel(logging.DEBUG if (on or _cli_debug) else logging.INFO)
