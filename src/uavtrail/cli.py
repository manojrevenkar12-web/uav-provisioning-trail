"""uavtrail: the station and the traceability server.

uavtrail serve [--port 8000]              API and console
uavtrail issues                           systemic and one-off issues on what the server holds
uavtrail kpis                             first-pass yield, flash success, downtime
uavtrail evaluate RUN_DIR                 an emulated run against its truth
uavtrail release build SPEC --artifacts DIR --key KEY --out DIR
uavtrail certificate verify FILE          a unit's software certificate
uavtrail trail verify [UNIT]              re-verify stored trails (all units if none given)
uavtrail instructions check RELEASE       the work instruction against the recipe and release
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def _print(x: Any) -> None:
    print(json.dumps(x, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="uavtrail", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="127.0.0.1")
    sub.add_parser("issues")
    sub.add_parser("kpis")
    e = sub.add_parser("evaluate")
    e.add_argument("run_dir", type=Path)
    r = sub.add_parser("release")
    r.add_argument("action", choices=["build"])
    r.add_argument("spec", type=Path)
    r.add_argument("--artifacts", type=Path, required=True)
    r.add_argument("--key", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("certificate")
    c.add_argument("action", choices=["verify"])
    c.add_argument("file", type=Path)
    t = sub.add_parser("trail")
    t.add_argument("action", choices=["verify"])
    t.add_argument("unit", nargs="?")
    i = sub.add_parser("instructions")
    i.add_argument("action", choices=["check"])
    i.add_argument("release")
    args = ap.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        from .server import api, db

        db.bootstrap()
        api.mount_console()
        uvicorn.run(api.app, host=args.host, port=args.port, log_level="info")
    elif args.cmd == "issues":
        from .analysis.issues import analyse, watch_list
        from .server import db

        found = analyse(db.rows("select * from attempts"), db.rows("select * from recoveries"))
        _print({"issues": [x.as_dict() for x in found], "watch": watch_list(db.rows("select * from attempts"))})
    elif args.cmd == "kpis":
        from .analysis import kpi

        _print({"summary": kpi.summary(), "pareto": kpi.pareto()})
    elif args.cmd == "evaluate":
        from . import evaluate

        _print(evaluate.run(args.run_dir))
    elif args.cmd == "release":
        from . import releases

        print(releases.build(args.spec, args.artifacts, args.key, args.out))
    elif args.cmd == "certificate":
        from . import keys
        from .releases import canonical

        doc = json.loads(args.file.read_text())
        ok = keys.verify(doc["station_key"], canonical(doc["certificate"]), doc["signature"])
        print(
            ("valid: " if ok else "INVALID: ")
            + f"{doc['certificate']['unit']} signed by station key {keys.fingerprint(doc['station_key'])}"
        )
        return 0 if ok else 1
    elif args.cmd == "trail":
        from . import evaluate

        broken = evaluate.chains(args.unit)
        _print(broken or "every trail verifies")
        return 1 if broken else 0
    elif args.cmd == "instructions":
        from .analysis import instructions
        from .config import recipe, root

        spec = yaml.safe_load((root() / "releases" / f"{args.release}.yaml").read_text())
        findings = instructions.check(instructions.load(spec["instruction"]), recipe(spec["recipe"]), spec)
        _print(findings)
        return 1 if findings else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
