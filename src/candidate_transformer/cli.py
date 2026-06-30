"""Command-line surface: point it at inputs (+ an optional config), get JSON.

Examples
--------
    candidate-transformer samples/*.csv samples/*.json samples/notes/*.txt \\
        github:robsmith -o out/default.json
    candidate-transformer samples/... -c config/custom_output.json -o out/custom.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="candidate-transformer",
        description="Turn messy multi-source candidate data into one canonical profile per person.")
    ap.add_argument("inputs", nargs="+",
                    help="input files (.csv/.json/.txt) and/or GitHub refs (github:user)")
    ap.add_argument("-c", "--config", help="runtime output config (JSON)")
    ap.add_argument("-o", "--out", help="write JSON here (default: stdout)")
    ap.add_argument("-v", "--verbose", action="store_true", help="log progress to stderr")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s", stream=sys.stderr)

    config = None
    if args.config:
        with open(args.config, encoding="utf-8") as fh:
            config = json.load(fh)

    results = run_pipeline(args.inputs, config)
    text = json.dumps(results, indent=2, ensure_ascii=False)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {len(results)} candidate(s) -> {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
