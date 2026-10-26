"""uavsim: the emulated line.

uavsim run CAMPAIGN [--units N] [--out DIR] [--keep-db]
    builds the campaign's firmware, bundles and signed releases, starts the fixtures (QEMU and the recovery-mode
    module per slot) and the traceability server, and runs the shift through the real station software
uavsim heldout SET [--units N]
    runs every campaign of heldout/SET and scores it; the first run is recorded once
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uavtrail.config import data_dir
from uavtrail.server import db

from . import campaign as campaigns
from .line import run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="uavsim", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("campaign", type=Path)
    r.add_argument("--units", type=int)
    r.add_argument("--out", type=Path)
    r.add_argument("--keep-db", action="store_true", help="add to what the server holds instead of starting clean")
    h = sub.add_parser("heldout")
    h.add_argument("set")
    h.add_argument("--units", type=int)
    args = ap.parse_args(argv)
    if args.cmd == "heldout":
        from .heldout import score, summary_line

        report = score(args.set, args.units)
        print(summary_line(report))
        if report.get("recorded_as"):
            print("recorded as the first run of", args.set)
        return 0
    if args.cmd == "run":
        c = campaigns.load(args.campaign)
        if args.keep_db:
            db.bootstrap()
        else:
            db.reset()
        result = run(c, args.out or data_dir() / "runs" / c.name, args.units, fresh=not args.keep_db)
        print(json.dumps(result, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
