"""Entry point: python -m bodeplot [--sim] [--debug]"""
from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bodeplot", description="Bode plotter")
    ap.add_argument("--sim", action="store_true",
                    help="simulation mode: mock instruments and a simulated DUT, no hardware needed")
    ap.add_argument("--debug", action="store_true", help="log every instrument command and response")
    ap.add_argument("--version", action="version", version="bodeplot " + __version__)
    args = ap.parse_args(argv)
    from .app import run
    return run(simulate=True if args.sim else None, debug=args.debug)


if __name__ == "__main__":
    sys.exit(main())
